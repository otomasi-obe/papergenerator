"""
Single-shot full paper generation — VIOLA-GENERATE
===================================================
Generates a complete academic paper in a single API call using MODELGENERATE
from env (VIOLA-GENERATE). Replaces the chunked orchestrator for jobs that
prefer one round-trip with the full prompt.txt schema rather than 7 stitched
chunks.

Architecture
------------
1. SYSTEM prompt   = prompt.txt + humanize.txt + optional style/topic guides.
2. USER message    = topic + project memory (via custom_prompt) + recent chat
                     history + literature catalog + attached file extracts +
                     additional instructions.
3. API call        = MODELGENERATE from env (no fallback chain), timeout=900s,
                     max_tokens=32000, temperature=0.7.
4. Post-process    = json_repair fallback on parse error, flatten the
                     section1..N keys produced by prompt.txt into a sections
                     array, then walk the tree and lift figures/tables/
                     equations into top-level lists so app._run_generate_full_job
                     gets the canonical paper shape.

Hard rules:
  * Model is read from MODELGENERATE env var (VIOLA-GENERATE). No hard-coded model.
  * If generation fails, raise — no other model is attempted.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

import requests
from json_repair import repair_json

from utils.core.env_loader import load_app_env
from utils.core.storage_helper import _get_username_from_user_id, get_generation_log_path
from utils.ai_tools.model_config import get_primary_generate_model, get_generate_model_chain, get_retry_count

# GenerationCancelled is re-exported via app._run_generate_full_job; this module
# does not raise it itself but the caller imports it from generate_paper_chunked.

log = logging.getLogger(__name__)

# ── Generator turn-log helpers ───────────────────────────────────────────────
# We persist the actual prompt sent to the AI and the raw reply (plus parsed
# shape + validation) under
#   backend/user/<username>/<paper_id>/generation/<job_id>/
# using the new storage structure from storage_helper.py
import datetime as _dt
import json as _json


def _gen_log_dir(user_id, paper_id, job_id) -> Path | None:
    """Build (and create) the per-job log directory.

    Layout: ``backend/user/<username>/<paper_id>/generation/<job_id>/``.
    Uses the new storage structure from storage_helper.py.
    """
    try:
        username = _get_username_from_user_id(user_id)
        d = get_generation_log_path(username, paper_id, job_id)
        return d
    except Exception as e:
        log.warning("[generator-log] mkdir failed: %s", e)
        return None


def _gen_log_write(dirpath: Path | None, name: str, payload) -> None:
    if dirpath is None:
        return
    try:
        path = dirpath / name
        if isinstance(payload, (dict, list)):
            path.write_text(
                _json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            path.write_text(str(payload), encoding="utf-8")
    except Exception as e:
        log.warning("[generator-log] write %s failed: %s", name, e)


def _validate_paper_shape(paper: dict) -> dict:
    """Return a `{"ok": bool, "issues": [...]}` report describing whether the
    AI's reply contains a complete paper. The job runner can branch on this
    BEFORE persisting a half-empty paper to the editor."""
    issues: list[str] = []
    if not isinstance(paper, dict):
        return {"ok": False, "issues": ["paper is not a dict"]}
    sections = paper.get("sections")
    if not isinstance(sections, list) or len(sections) < 4:
        n = len(sections) if isinstance(sections, list) else 0
        issues.append(f"sections has {n} entries (need >=4)")
    if not (paper.get("abstract") or "").strip():
        issues.append("abstract empty")
    refs = paper.get("references")
    if not isinstance(refs, list) or len(refs) < 5:
        n = len(refs) if isinstance(refs, list) else 0
        issues.append(f"references has {n} entries (need >=5)")
    if not (paper.get("title") or "").strip():
        issues.append("title empty")
    return {"ok": not issues, "issues": issues}


# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
load_app_env()

AIOTOMASI_API = os.getenv("AIOTOMASI_API")
AIOTOMASI_APIKEY = os.getenv("AIOTOMASI_APIKEY")

PROMPT_FILE = BASE_DIR.parent / "paperfull" / "prompt" / "prompt.txt"
HUMANIZE_FILE = BASE_DIR.parent / "tools" / "paperfull" / "prompt" / "humanize.txt"

# Model for single-shot generation from env (VIOLA-GENERATE). No fallback chain.
SINGLE_SHOT_MODEL = get_primary_generate_model()
_MODEL_CHAIN = get_generate_model_chain()
_RETRY_COUNT = get_retry_count()


# ── System prompt builder ────────────────────────────────────────────────────
def _load_system_prompt(style: str | None = None, topic: str | None = None) -> str:
    """Concatenate prompt.txt + humanize.txt + optional style/topic guides.

    The full schema, drafting rules, and humanize rules form the SYSTEM prompt
    so the AI sees the same authoritative ruleset the legacy single-call path
    used. Style/topic guides are appended only when the corresponding file
    exists, so a missing prompt/topic/<slug>.txt is silently skipped.
    """
    if not PROMPT_FILE.exists():
        raise ValueError(f"prompt.txt not found at {PROMPT_FILE}")

    parts: list[str] = [PROMPT_FILE.read_text(encoding="utf-8")]

    if HUMANIZE_FILE.exists():
        parts.append(HUMANIZE_FILE.read_text(encoding="utf-8"))

    if style:
        style_file = BASE_DIR.parent / "tools" / "paperfull" / "prompt" / "style" / f"{style}.txt"
        if style_file.exists():
            parts.append(
                f"## CITATION STYLE GUIDE — {style}\n" + style_file.read_text(encoding="utf-8")
            )

    if topic:
        topic_file = BASE_DIR.parent / "tools" / "paperfull" / "prompt" / "topic" / f"{topic}.txt"
        if topic_file.exists():
            parts.append(f"## TOPIC GUIDE — {topic}\n" + topic_file.read_text(encoding="utf-8"))

    return "\n\n".join(parts)


# ── Context loaders (DB-backed, gracefully degrade) ──────────────────────────
def _load_chat_history(conv_id: str | None, limit: int = 10) -> str:
    """Return last `limit` ChatMessage rows for `conv_id`, oldest first.

    Returns "" when ``conv_id`` is falsy, the DB query fails (e.g. no app
    context), or the conversation is empty. Each message is capped at 500
    chars so a single runaway turn cannot blow the prompt budget.
    """
    if not conv_id:
        return ""
    try:
        from database.models import ChatMessage, db

        msgs = (
            db.session.query(ChatMessage)
            .filter_by(conversation_id=conv_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        if not msgs:
            return ""
        lines = ["## Recent chat history (oldest -> newest)"]
        for m in reversed(msgs):
            content = (m.content or "")[:500]
            if content:
                lines.append(f"**{m.role}**: {content}")
        return "\n".join(lines)
    except Exception as e:
        log.warning("[_load_chat_history] failed: %s", e)
        return ""


def _load_literature(paper_id: str | None, limit: int = 50) -> str:
    """Top `limit` LiteratureItem rows ordered by pinned, must_read, score."""
    if not paper_id:
        return ""
    try:
        from database.models import LiteratureItem, db

        items = (
            db.session.query(LiteratureItem)
            .filter_by(paper_id=paper_id)
            .order_by(
                LiteratureItem.pinned.desc(),
                LiteratureItem.must_read.desc(),
                LiteratureItem.score_total.desc(),
            )
            .limit(limit)
            .all()
        )
        if not items:
            return ""
        lines = [
            "## Literature catalog (authoritative reference list — use ONLY these entries; do NOT fabricate references)"
        ]
        for i, it in enumerate(items, 1):
            authors_list = it.authors or []
            authors = ", ".join(authors_list[:3])
            if len(authors_list) > 3:
                authors += " et al."
            marker = "[MUST READ] " if (it.pinned or it.must_read) else ""
            bits = [f"[L{i}] {marker}{it.title or 'Untitled'}"]
            if authors:
                bits.append(f"— {authors}")
            if it.year:
                bits.append(f"({it.year})")
            if it.venue:
                bits.append(f"in {it.venue}")
            if it.doi:
                bits.append(f"DOI: {it.doi}")
            elif it.url:
                bits.append(f"URL: {it.url}")
            line = " ".join(bits)
            if it.summary:
                line += f"\n   Summary: {it.summary[:200]}"
            lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        log.warning("[_load_literature] failed: %s", e)
        return ""


def _load_attached_files(paper_id: str | None, limit: int = 5, char_cap: int = 800) -> str:
    """Top `limit` PaperFile rows; each extracted_text is truncated to char_cap."""
    if not paper_id:
        return ""
    try:
        from database.models import PaperFile, db

        files = (
            db.session.query(PaperFile)
            .filter_by(paper_id=paper_id)
            .order_by(PaperFile.created_at.desc())
            .limit(limit)
            .all()
        )
        if not files:
            return ""
        lines = ["## Attached file extracts (reference materials)"]
        for f in files:
            text = (f.extracted_text or "")[:char_cap]
            if text:
                lines.append(f"**{f.original_name}** ({f.ext}):")
                lines.append(text)
                lines.append("")
        out = "\n".join(lines).strip()
        return out
    except Exception as e:
        log.warning("[_load_attached_files] failed: %s", e)
        return ""


# ── Direct API call (no fallback) ────────────────────────────────────────────
def _call_v_opus(
    messages: list,
    api_key: str,
    base_url: str,
    timeout: float | None = None,
    progress_cb=None,
) -> str:
    """POST messages to /chat/completions with MODELGENERATE, stream=True.

    No fallback chain — a failure here propagates to the caller. The endpoint
    streams Server-Sent Events shaped like OpenAI's chat-completions stream
    (data: {chunk}, terminated by data: [DONE]); some upstream proxies emit
    a single non-SSE JSON line, so we accept both shapes.
    """
    from utils.core.retry_helper import get_retry_config
    
    if timeout is None:
        _, timeout = get_retry_config()
    
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": 32000,
        "temperature": 0.7,
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
                        try:
                            progress_cb(len(content))
                        except Exception:
                            pass
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
                            try:
                                progress_cb(len(content))
                            except Exception:
                                pass
            except json.JSONDecodeError:
                pass

    if not content:
        raise ValueError("AI returned empty content")
    return content


# ── JSON parsing + shape normalization ───────────────────────────────────────
def _parse_json_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON; fall back to json_repair."""
    clean = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e1:
        try:
            repaired = repair_json(clean, return_objects=True)
            if isinstance(repaired, dict) and repaired:
                return repaired
            raise ValueError(f"json_repair did not return a dict: {type(repaired)}")
        except Exception as e2:
            raise ValueError(f"JSON parse failed: {e1} | repair: {e2}")


_SECTION_KEY_RE = re.compile(r"^section(\d+)$")
_SUBSECTION_KEY_RE = re.compile(r"^section(\d+)([a-z])$")


def _lift_subsections(sec: dict) -> dict:
    """Lift ``section2a``/``section3b`` style nested dicts into a
    ``subsections: [...]`` list, in alphabetical order of their suffix.

    Mutates and returns the given section dict. Already-canonical sections
    (those that already carry a ``subsections`` list) are returned untouched.
    """
    if not isinstance(sec, dict):
        return sec
    if isinstance(sec.get("subsections"), list):
        return sec

    sub_pairs: list[tuple[str, dict]] = []
    drop_keys: list[str] = []
    for k, v in sec.items():
        m = _SUBSECTION_KEY_RE.fullmatch(k)
        if m and isinstance(v, dict):
            sub_pairs.append((m.group(2), dict(v)))
            drop_keys.append(k)
    if not sub_pairs:
        return sec
    sub_pairs.sort(key=lambda p: p[0])
    for k in drop_keys:
        sec.pop(k, None)
    sec["subsections"] = [s for _, s in sub_pairs]
    return sec


def _normalize_paper_shape(raw: dict) -> dict:
    """Convert prompt.txt's flat ``sectionN`` keys into a ``sections`` array
    and lift figures/tables/equations into top-level lists.

    The prompt.txt schema returns top-level keys ``section1`` .. ``section5``
    (plus ``title``, ``abstract``, ``keywords``, ``authors``, ``references``)
    and within each section nests ``section2a``, ``section3b`` etc as
    subsections. Downstream renderers and ``_run_generate_full_job`` expect a
    single ``sections: [...]`` array (each with ``subsections: [...]``) and
    pre-extracted ``figures``/``tables``/``equations`` lists. This adapter
    performs all three transformations while tolerating an already-canonical
    input (re-running on a normalized paper is a no-op).
    """
    if not isinstance(raw, dict):
        raise ValueError(f"Expected dict, got {type(raw)}")

    # Build sections array from either canonical "sections" list or flat keys.
    sections_array: list = []
    if isinstance(raw.get("sections"), list):
        sections_array = [s for s in raw["sections"] if isinstance(s, dict)]
    else:
        section_pairs: list[tuple[int, dict]] = []
        for k, v in raw.items():
            m = _SECTION_KEY_RE.fullmatch(k)
            if m and isinstance(v, dict):
                section_pairs.append((int(m.group(1)), dict(v)))
        section_pairs.sort(key=lambda p: p[0])
        for idx, sec in section_pairs:
            sec.setdefault("title", f"SECTION {idx}")
            sections_array.append(sec)

    # Lift nested "sectionNx" keys into a canonical "subsections" list so the
    # renderer sees the same shape the legacy chunked path produced.
    for sec in sections_array:
        _lift_subsections(sec)

    # references can come back as a list, a {"items": [...]} dict, the
    # prompt.txt {"title": "REFERENCES", "content": [...]} shape, or a
    # bare dict-of-strings. Handle each without confusing the title for
    # a reference entry.
    refs = raw.get("references", [])
    if isinstance(refs, dict):
        if isinstance(refs.get("items"), list):
            refs = refs["items"]
        elif isinstance(refs.get("content"), list):
            refs = refs["content"]
        else:
            refs = [v for k, v in refs.items() if isinstance(v, str) and k.lower() != "title"]
    if not isinstance(refs, list):
        refs = []

    paper = {
        "title": raw.get("title", "") or "",
        "abstract": raw.get("abstract", "") or "",
        "keywords": raw.get("keywords") or [],
        "authors": raw.get("authors")
        or [
            {
                "name": "Author Name",
                "affiliation": "Department, University",
                "location": "City, Country",
                "email": "author@example.com",
            }
        ],
        "sections": sections_array,
        "acknowledgment": raw.get("acknowledgment", "") or "",
        "references": refs,
        "figures": [],
        "tables": [],
        "equations": [],
    }

    def _extract(obj, item_type: str, collection: list) -> None:
        """Walk dicts and lists; collect every dict whose ``id`` matches.

        Critically, when we descend into a list we must check each element
        for an ``id`` match itself (content arrays in the prompt.txt schema
        hold the figure/table/equation dicts directly), not only as a
        container to recurse into.
        """
        if isinstance(obj, dict):
            if obj.get("id") == item_type:
                collection.append(obj)
            for value in obj.values():
                _extract(value, item_type, collection)
        elif isinstance(obj, list):
            for item in obj:
                _extract(item, item_type, collection)

    for sec in sections_array:
        _extract(sec, "gambar", paper["figures"])
        _extract(sec, "tabel", paper["tables"])
        _extract(sec, "rumus", paper["equations"])

    return paper


# ── Main entry point ─────────────────────────────────────────────────────────
def generate_paper_json_single(
    judul: str,
    custom_prompt: str = "",
    *,
    api_key: str = None,
    base_url: str = None,
    topic: str = None,
    style: str = None,
    progress_cb=None,
    paper_id=None,
    conv_id=None,
    job_id=None,
    user_id=None,
) -> dict:
    """Single-shot full paper generation — uses MODELGENERATE from env.

    Args:
        judul: Paper title / topic description.
        custom_prompt: Additional instructions; carries project memory facts,
            optional outline, and output settings injected by
            ``chat_tools._generate_full_paper``. May contain a
            ``## Literature catalog`` block (DB literature load is then
            skipped to avoid duplication) and/or a ``[REFERENCE DOCUMENTS]``
            block (file-extract load is then skipped).
        api_key: API key (falls back to ``AIOTOMASI_APIKEY`` env var).
        base_url: API base URL (falls back to ``AIOTOMASI_API`` env var).
        topic: Topic guide slug — loads ``prompt/topic/<slug>.txt`` if present.
        style: Citation style slug — loads ``prompt/style/<slug>.txt`` if
            present.
        progress_cb: Optional callable(chars_done: int) for streaming feedback.
        paper_id: Optional paper ID — used to load up to 50 ``LiteratureItem``
            rows (pinned + must_read first) and up to 5 ``PaperFile`` rows
            (each extracted_text capped at 800 chars).
        conv_id: Optional conversation ID — used to load the last 10
            ``ChatMessage`` rows (each capped at 500 chars).

    Returns:
        Paper dict with the canonical shape::

            {"title": str, "abstract": str, "keywords": [...],
             "authors": [...], "sections": [{"title": str, "content": [...]},
             ...], "acknowledgment": str, "references": [...], "figures": [],
             "tables": [], "equations": []}

        Figures/tables/equations are extracted from within the sections tree
        into the top-level lists.

    Raises:
        ValueError: If ``api_key`` / ``base_url`` resolve to empty, or the
            response cannot be parsed as JSON even after ``json_repair``.
        requests.HTTPError: If the AI returns a non-2xx response.
    """
    _api_key = api_key or AIOTOMASI_APIKEY
    _base_url = base_url or AIOTOMASI_API
    if not _api_key:
        raise ValueError("AIOTOMASI_APIKEY not found in environment")
    if not _base_url:
        raise ValueError("AIOTOMASI_API not found in environment")

    system_prompt = _load_system_prompt(style=style, topic=topic)

    # ── Build user message ───────────────────────────────────────────────────
    user_parts: list[str] = [f"Topic / title: {judul}"]

    if custom_prompt and custom_prompt.strip():
        user_parts.append(custom_prompt.strip())

    # Load workflow context if available
    if paper_id and user_id:
        try:
            from tools.editor.workflow_integration import load_workflow_context
            workflow_ctx = load_workflow_context(paper_id, user_id)
            if workflow_ctx:
                user_parts.append(workflow_ctx)
                log.info("[generate_paper_json_single] Injected workflow context")
        except Exception as e:
            log.warning("[generate_paper_json_single] Failed to load workflow context: %s", e)

    history_block = _load_chat_history(conv_id, limit=10)
    if history_block:
        user_parts.append(history_block)

    # When chat_tools already injected the curated literature catalog into
    # custom_prompt we skip the DB load to avoid duplicating ~50 entries.
    has_lit_in_custom = bool(custom_prompt and "## Literature catalog" in custom_prompt)
    if not has_lit_in_custom:
        lit_block = _load_literature(paper_id, limit=50)
        if lit_block:
            user_parts.append(lit_block)

    # Same dedup logic for attached files: if app._run_generate_full_job
    # already inlined PDF extracts via [REFERENCE DOCUMENTS], skip the DB load.
    has_files_in_custom = bool(custom_prompt and "[REFERENCE DOCUMENTS]" in custom_prompt)
    if not has_files_in_custom:
        files_block = _load_attached_files(paper_id, limit=5, char_cap=800)
        if files_block:
            user_parts.append(files_block)

    user_parts.append(
        "Generate the complete paper following the system prompt schema. "
        "Return ONLY a JSON object — no markdown fences, no commentary."
    )

    user_message = "\n\n".join(user_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    sys_kb = len(system_prompt.encode("utf-8")) / 1024
    user_kb = len(user_message.encode("utf-8")) / 1024
    log.info(
        "[generate_paper_json_single] system=%.1fKB user=%.1fKB model=%s",
        sys_kb,
        user_kb,
        SINGLE_SHOT_MODEL,
    )
    log.info(
        "[generate_paper_json_single] starting (system=%.1fKB user=%.1fKB model=%s)",
        sys_kb,
        user_kb,
        SINGLE_SHOT_MODEL,
    )

    # Persist the EXACT request being sent to the AI so we can inspect it
    # without waiting for the response. Useful when the reply is later
    # incomplete — most of the time the prompt is fine and the truncation is
    # purely model-side, but occasionally we discover the user/system message
    # is missing a section because of a downstream bug.
    gen_dir = _gen_log_dir(user_id, paper_id, job_id)
    _gen_log_write(
        gen_dir,
        "00_request.json",
        {
            "ts": _dt.datetime.utcnow().isoformat() + "Z",
            "model": model,
            "user_id": user_id,
            "paper_id": paper_id,
            "conv_id": conv_id,
            "job_id": job_id,
            "judul": judul,
            "topic": topic,
            "style": style,
            "system_kb": round(sys_kb, 2),
            "user_kb": round(user_kb, 2),
            "messages": messages,
        },
    )

    # Call the API with the full prompt
    from utils.core.retry_helper import get_retry_config
    _, timeout = get_retry_config()
    
    t_start = time.time()
    raw_content = _call_v_opus(
        messages, _api_key, _base_url, timeout=timeout, progress_cb=progress_cb
    )
    elapsed = time.time() - t_start
    log.info(
        "[generate_paper_json_single] received %d chars in %.1fs",
        len(raw_content),
        elapsed,
    )

    # Persist raw reply BEFORE parsing — if json parsing fails we still want
    # the actual upstream bytes on disk for triage.
    _gen_log_write(gen_dir, "01_raw_response.txt", raw_content)
    _gen_log_write(
        gen_dir,
        "01_raw_response_meta.json",
        {
            "ts": _dt.datetime.utcnow().isoformat() + "Z",
            "elapsed_seconds": round(elapsed, 2),
            "raw_chars": len(raw_content),
        },
    )

    raw_paper = _parse_json_response(raw_content)
    paper_json = _normalize_paper_shape(raw_paper)

    # Persist parsed + normalized paper + validation. Job runner reads
    # 02_validation.json to decide whether to retry / surface a useful error
    # to the chat instead of saving a half-empty paper to the editor.
    _gen_log_write(gen_dir, "02_parsed.json", raw_paper)
    _gen_log_write(gen_dir, "02_normalized.json", paper_json)
    _gen_log_write(gen_dir, "02_validation.json", _validate_paper_shape(paper_json))
    return paper_json
