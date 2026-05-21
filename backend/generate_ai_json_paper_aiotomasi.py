"""
IEEE Paper Generator — AIOTOMASI Edition
- Menggunakan AIOTOMASI_API, AIOTOMASI_APIKEY, AIOTOMASI_MODEL dari .env
- Menggunakan requests langsung (API mengembalikan JSON dengan header text/event-stream)
- Input: JUDUL dan CUSTOM PROMPT dari user
- Record waktu + token
- Simpan hasil JSON ke output/
"""

import os
import re
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv
import requests
from json_repair import repair_json

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

AIOTOMASI_API    = os.getenv("AIOTOMASI_API")
AIOTOMASI_APIKEY = os.getenv("AIOTOMASI_APIKEY")
AIOTOMASI_MODEL  = os.getenv("AIOTOMASI_MODEL", "VIOLAGPT")

# ── Prompt file path ──────────────────────────────────────────────────────────
PROMPT_FILE = BASE_DIR / "prompt" / "prompt.txt"

USER_TEMPLATE = """Topic description: {judul}

Based on the topic description above:
1. Generate a professional, publication-ready academic title in English that best represents this topic.
2. Write a complete research paper about this exact topic, incorporating all specific details mentioned (location, institution, system name, equipment, data, etc.).
3. All sections, equations, figures, tables, and references must be directly relevant to this topic.
4. If the topic description (and additional instructions) does NOT include numeric data (dataset size, accuracy, latency, voltage, etc.), you MUST generate estimated/simulation-based numeric values that fit the topic and keep them consistent across the abstract, tables, figures, Results, and Section V.
5. The output must include all sections through Section V (CONCLUSION); do not stop early.
6. LOCATION & INSTITUTION: If the topic description mentions a university, department, laboratory, city, province, or country — use it EXACTLY in authors[].affiliation and authors[].location. Also ground the Introduction and Methodology in that location (e.g., "conducted at Universitas X in Surabaya"). Do NOT replace user-specified locations with generic placeholders.
7. EQUATIONS: Use equations from the TOPIC GUIDE if one is provided. Otherwise, use domain-appropriate formulas from the system prompt's DOMAIN FORMULA REFERENCE. Every equation must directly match the methodology described (e.g., PID formula for a PID control paper, DH transform for a robot kinematics paper). Do NOT use generic or unrelated placeholder math.
8. DATA CONSISTENCY: Pick one fixed set of numeric values at the start and use them identically in the abstract, every table row, every text paragraph, and the conclusion. Do NOT round differently in different sections (e.g., do not say "~95%" in the abstract but "95.4%" in the table — use 95.4% everywhere).
9. TEXT FORMATTING: Use \\b...\\b for bold, \\i...\\i for italic, \\u...\\u for underline inside "text" field values and table "Rows" strings. Do NOT use **...** or *...* (Markdown is not supported by the DOCX renderer).

Additional instructions: {custom_prompt}
"""


def _call_aiotomasi(messages: list, api_key: str, base_url: str, model: str, timeout: float = 1200.0, progress_cb=None) -> str:
    """Call AIOTOMASI API via requests with SSE streaming."""
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True)
    resp.raise_for_status()

    content = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    content += delta["content"]
                    if progress_cb:
                        progress_cb(len(content))
            except json.JSONDecodeError:
                pass
        elif line.startswith("{"):
            try:
                full = json.loads(line)
                if full.get("choices"):
                    msg = full["choices"][0].get("message", {})
                    if msg.get("content"):
                        content += msg["content"]
                        if progress_cb:
                            progress_cb(len(content))
            except json.JSONDecodeError:
                pass

    if not content:
        raise ValueError("API returned empty content")

    return content


# ── Fallback model chain ──────────────────────────────────────────────────────
# Order: try the primary model first, then walk down the list. Each entry is
# attempted independently; if all fail the last exception is re-raised.
FALLBACK_MODELS = ["V-OPUS", "V-CLAUDE", "V-GPT", "V-GLM"]


def _call_aiotomasi_with_fallback(messages: list, api_key: str, base_url: str, primary_model: str, timeout: float = 1200.0, progress_cb=None) -> tuple:
    """Try primary_model first, then walk FALLBACK_MODELS on transient errors.
    Returns (content, model_used). Raises the last exception if everything fails.
    """
    chain = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    last_err = None
    for idx, m in enumerate(chain):
        try:
            content = _call_aiotomasi(messages, api_key, base_url, m, timeout=timeout, progress_cb=progress_cb)
            return content, m
        except Exception as e:
            last_err = e
            # Don't retry on auth (401/403) — those are config errors, not upstream flakiness
            err_str = str(e)
            if "401" in err_str or "403" in err_str:
                raise
            print(f"[fallback] model={m} failed ({err_str[:120]}); trying next…", flush=True)
            continue
    raise last_err if last_err else RuntimeError("All fallback models failed")


# ── Callable API ─────────────────────────────────────────────────────────────
def generate_paper_json(
    judul: str,
    custom_prompt: str = "",
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    topic: str = None,
    style: str = None,
    progress_cb=None,
) -> dict:
    """
    Generate a complete IEEE conference paper JSON via AIOTOMASI API.

    Args:
        judul: Paper title / topic.
        custom_prompt: Additional instructions for the AI.
        api_key: API key (falls back to AIOTOMASI_APIKEY env var).
        base_url: API base URL (falls back to AIOTOMASI_API env var).
        model: Model name (falls back to AIOTOMASI_MODEL env var).
        topic: Topic guide file name (without .txt).
        style: Style guide file name (without .txt).
        progress_cb: Optional callable(chars_done: int) for progress feedback.

    Returns:
        Parsed paper dict.

    Raises:
        ValueError: If the API key/URL is missing or JSON cannot be parsed.
    """
    _api_key  = api_key or AIOTOMASI_APIKEY
    _base_url = base_url or AIOTOMASI_API
    _model    = model or AIOTOMASI_MODEL

    if not _api_key:
        raise ValueError("AIOTOMASI_APIKEY tidak ditemukan di environment")
    if not _base_url:
        raise ValueError("AIOTOMASI_API tidak ditemukan di environment")

    # ── Load system prompt ────────────────────────────────────────────────────
    if PROMPT_FILE.exists():
        system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    else:
        raise ValueError("prompt.txt not found")

    # Append humanize rules
    humanize_file = BASE_DIR / "prompt" / "humanize.txt"
    if humanize_file.exists():
        system_prompt += "\n\n" + humanize_file.read_text(encoding="utf-8")

    # Append style guide
    if style:
        style_file = BASE_DIR / "prompt" / "style" / f"{style}.txt"
        if style_file.exists():
            system_prompt += "\n\n" + style_file.read_text(encoding="utf-8")

    # Append topic guide
    if topic:
        topic_file = BASE_DIR / "prompt" / "topic" / f"{topic}.txt"
        if topic_file.exists():
            system_prompt += "\n\n" + topic_file.read_text(encoding="utf-8")

    user_message = (
        USER_TEMPLATE
        .replace("{judul}", judul)
        .replace("{custom_prompt}", custom_prompt if custom_prompt else "(no additional instructions)")
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    raw_content, model_used = _call_aiotomasi_with_fallback(messages, _api_key, _base_url, _model, progress_cb=progress_cb)
    print(f"[generate_paper_json] succeeded using model={model_used}", flush=True)

    # Strip markdown fences if present
    clean = re.sub(r"^```(?:json)?\s*", "", raw_content.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)

    # Parse JSON with json_repair fallback
    paper_json = None
    try:
        paper_json = json.loads(clean)
    except json.JSONDecodeError as e1:
        try:
            repaired = repair_json(clean, return_objects=True)
            if isinstance(repaired, dict) and repaired:
                paper_json = repaired
            else:
                raise ValueError(f"json_repair did not return a dict: {type(repaired)}")
        except Exception as e2:
            raise ValueError(f"JSON parse failed: {e1} | repair: {e2}")

    if not isinstance(paper_json, dict):
        raise ValueError(f"Expected dict, got {type(paper_json)}")

    return paper_json


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not AIOTOMASI_APIKEY:
        sys.exit("ERROR: AIOTOMASI_APIKEY tidak ditemukan di .env")
    if not AIOTOMASI_API:
        sys.exit("ERROR: AIOTOMASI_API tidak ditemukan di .env")

    print("=" * 65)
    print("  IEEE Paper Generator — powered by AIOTOMASI")
    print(f"  Model    : {AIOTOMASI_MODEL}")
    print(f"  Endpoint : {AIOTOMASI_API}")
    print("=" * 65)

    # ── Input dari user ───────────────────────────────────────────────────────
    print("\nMasukkan JUDUL paper IEEE:")
    judul = input("JUDUL  : ").strip()
    if not judul:
        sys.exit("ERROR: Judul tidak boleh kosong.")

    print("\nMasukkan CUSTOM PROMPT tambahan (opsional, tekan Enter untuk skip):")
    print("(contoh: Focus on real-time performance, use YOLO-based architecture)\n")
    custom_prompt = input("CUSTOM : ").strip()

    print(f"\n{'─'*65}")
    print(f"[JUDUL]  {judul}")
    print(f"[CUSTOM] {custom_prompt if custom_prompt else '(kosong)'}")
    print(f"{'─'*65}")
    print("Mengirim ke AIOTOMASI...\n")

    t_start = time.perf_counter()

    paper_json = None
    json_valid = False
    json_err   = ""

    try:
        paper_json = generate_paper_json(
            judul=judul,
            custom_prompt=custom_prompt,
        )
        json_valid = True
    except Exception as e:
        json_err = str(e)

    elapsed = time.perf_counter() - t_start
    print(f"\n  [DONE] {elapsed:.1f}s")

    # ── Simpan output ─────────────────────────────────────────────────────────
    safe_topic = re.sub(r'[^a-zA-Z0-9_]', '_', judul[:50])
    timestamp  = time.strftime("%Y%m%d_%H%M%S")
    out_stem   = f"{timestamp}_{safe_topic}"

    json_path = None
    if json_valid and paper_json:
        json_path = OUTPUT_DIR / f"{out_stem}.json"
        json_path.write_text(
            json.dumps(paper_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Laporan ───────────────────────────────────────────────────────────────
    print("=" * 65)
    print("  HASIL")
    print("=" * 65)
    print(f"  Elapsed time : {elapsed:.2f} s  ({elapsed/60:.1f} menit)")
    print(f"  JSON valid   : {'✓ YA' if json_valid else '✗ TIDAK — ' + json_err}")
    if json_path:
        print(f"  JSON saved   : {json_path}")
    print("=" * 65)

    if json_valid and paper_json:
        title = paper_json.get("title", "(no title)")
        print(f"\n[JUDUL] {title}\n")

    return paper_json


if __name__ == "__main__":
    main()
