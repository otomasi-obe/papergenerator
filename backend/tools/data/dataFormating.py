"""
Data Formatting via AI
======================
Kirim data mentah (markdown/text) ke AI untuk:
1. Merapikan dan format data menjadi tabel terstruktur
2. Rekomendasikan 3-5 jenis grafik yang cocok

Alur:
  file upload → file_extractor → markdown → AI → JSON terstruktur

Output JSON:
{
  "tables": [...],
  "chart_recommendations": [...],
  "summary": {...}
}
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import requests

from utils.ai_tools.model_router import route_chat_call
from tools.File.file_extractor import extract_to_markdown

log = logging.getLogger(__name__)

# ── System prompt loader ─────────────────────────────────────────────────────

_PROMPT_PATH = Path(__file__).parent / "dataPrompt.txt"
_PROMPT_CACHE: str | None = None
_PROMPT_MTIME: float | None = None


def _load_system_prompt() -> str:
    """Load system prompt dari dataPrompt.txt (dengan cache)."""
    global _PROMPT_CACHE, _PROMPT_MTIME
    try:
        mtime = _PROMPT_PATH.stat().st_mtime
        if _PROMPT_CACHE is not None and _PROMPT_MTIME == mtime:
            return _PROMPT_CACHE
        _PROMPT_CACHE = _PROMPT_PATH.read_text(encoding="utf-8")
        _PROMPT_MTIME = mtime
    except FileNotFoundError:
        log.warning("dataPrompt.txt not found, using minimal fallback")
        _PROMPT_CACHE = (
            "Kamu adalah ahli analisis data. "
            "Format data mentah menjadi tabel dan rekomendasikan grafik yang cocok. "
            "Jawab dalam format JSON."
        )
    return _PROMPT_CACHE


# ── JSON extraction ──────────────────────────────────────────────────────────

def _extract_json_from_response(text: str) -> dict | None:
    """
    Extract JSON dari response AI.
    AI sering membungkus JSON dalam ```json ... ``` atau menyisipkan teks ekstra.
    """
    # Strategy 1: Extract from code block ```json ... ```
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            # Even code block might have extra data — try raw_decode
            try:
                obj, _ = json.JSONDecoder().raw_decode(m.group(1).strip())
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 2: Brace-counting — find first complete {…} object
    brace_obj = _extract_first_json_object(text)
    if brace_obj is not None:
        return brace_obj

    # Strategy 3: Try json.loads on entire text (might work if clean)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 4: raw_decode from first { position
    brace_start = text.find('{')
    if brace_start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[brace_start:])
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _extract_first_json_object(text: str) -> dict | None:
    """
    Find the first complete JSON object in text using brace counting.
    Handles nested objects, strings with braces, and escaped quotes.
    """
    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == '\\' and in_string:
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                json_str = text[start:i + 1]
                try:
                    obj = json.loads(json_str)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    return None
                return None

    return None


def _validate_and_fix_output(data: dict) -> dict:
    """Validasi dan perbaiki output JSON dari AI."""
    if not isinstance(data, dict):
        data = {"tables": [], "chart_recommendations": [], "summary": {}}

    # Pastikan ada tables
    if "tables" not in data:
        data["tables"] = []

    # Pastikan tiap tabel punya field wajib
    for tbl in data["tables"]:
        if "columns" not in tbl:
            tbl["columns"] = []
        if "rows" not in tbl:
            tbl["rows"] = []
        if "name" not in tbl:
            tbl["name"] = "Tabel Tanpa Nama"
        if "column_types" not in tbl:
            # Auto-detect: jika semua value di kolom bisa float → numerik
            types = []
            for col_idx in range(len(tbl["columns"])):
                sample_vals = [
                    row[col_idx] for row in tbl["rows"][:10]
                    if col_idx < len(row) and row[col_idx] != ""
                ]
                is_numeric = all(
                    _is_number(v) for v in sample_vals
                ) if sample_vals else False
                types.append("numerik" if is_numeric else "kategori")
            tbl["column_types"] = types

    # Pastikan ada chart_recommendations
    if "chart_recommendations" not in data:
        data["chart_recommendations"] = []

    # Pastikan ada summary
    if "summary" not in data:
        total_rows = sum(len(t.get("rows", [])) for t in data["tables"])
        data["summary"] = {
            "data_overview": f"Ditemukan {len(data['tables'])} tabel dengan total {total_rows} baris.",
            "key_insights": [],
            "warnings": [],
        }

    return data


def _is_number(val: str) -> bool:
    """Check apakah string bisa dikonversi ke float."""
    try:
        float(val.replace(",", ""))
        return True
    except (ValueError, AttributeError):
        return False


# ── Public API ───────────────────────────────────────────────────────────────

def format_data_with_ai(
    raw_text: str,
    filename: str | None = None,
) -> dict:
    """
    Kirim data mentah ke AI untuk diformat.

    Args:
        raw_text: Data mentah (markdown, CSV, text, dll)
        filename: Nama file asli (opsional, untuk konteks)

    Returns:
        dict dengan keys: tables, chart_recommendations, summary
    """
    system_prompt = _load_system_prompt()

    # Batasi ukuran input (max ~15000 chars untuk konteks)
    if len(raw_text) > 15000:
        raw_text = raw_text[:15000] + "\n\n... [data terpotong, sisa data terlalu panjang]"

    user_msg = f"Berikut data mentah yang perlu diformat:\n\n"
    if filename:
        user_msg += f"Nama file: {filename}\n\n"
    user_msg += raw_text

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 16000,
    }

    try:
        # Use shorter timeout for data tools (60s per endpoint, not default 180s)
        # Data formatting should complete quickly; long hangs indicate upstream issues
        resp, model_used = route_chat_call(json=payload, timeout=90)
        # Robust JSON parsing — AI API may return malformed response (streaming chunks, extra text)
        try:
            resp_data = resp.json()
        except json.JSONDecodeError:
            # Try raw_decode to extract first valid JSON object
            text = resp.text
            log.warning("resp.json() failed, trying raw_decode on response text (%d chars)", len(text))
            try:
                resp_data, _ = json.JSONDecoder().raw_decode(text)
            except (json.JSONDecodeError, ValueError):
                log.error("AI API returned non-JSON response: %s", text[:300])
                return {
                    "tables": [],
                    "chart_recommendations": [],
                    "summary": {
                        "data_overview": "AI API mengembalikan response yang tidak valid.",
                        "key_insights": [],
                        "warnings": ["AI API response bukan JSON yang valid."],
                    },
                    "_raw_response": text[:500],
                }
        
        if "choices" not in resp_data or not resp_data["choices"]:
            log.error("AI API returned response without choices: %s", resp_data)
            return {
                "tables": [],
                "chart_recommendations": [],
                "summary": {
                    "data_overview": "AI API mengembalikan response yang tidak valid (tidak ada choices).",
                    "key_insights": [],
                    "warnings": ["AI API response tidak memiliki field 'choices'."],
                },
                "_raw_response": str(resp_data)[:500],
            }
        content = resp_data["choices"][0]["message"]["content"]

        result = _extract_json_from_response(content)
        if result is None:
            log.warning("AI response tidak bisa di-parse sebagai JSON: %s", content[:200])
            return {
                "tables": [],
                "chart_recommendations": [],
                "summary": {
                    "data_overview": "Gagal memproses data dengan AI.",
                    "key_insights": [],
                    "warnings": ["AI response tidak dalam format JSON yang valid."],
                },
                "_raw_response": content[:500],
            }

        result = _validate_and_fix_output(result)
        result["_model_used"] = model_used
        return result

    except Exception as e:
        log.error("format_data_with_ai failed: %s", e)
        return {
            "tables": [],
            "chart_recommendations": [],
            "summary": {
                "data_overview": f"Error saat memproses data: {e}",
                "key_insights": [],
                "warnings": [str(e)],
            },
        }


def format_file_with_ai(filepath: str | Path, filename: str | None = None) -> dict:
    """
    Extract file ke markdown, lalu kirim ke AI.

    Args:
        filepath: Path ke file yang diupload
        filename: Nama file asli (opsional)

    Returns:
        dict sama dengan format_data_with_ai
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return {
            "tables": [],
            "chart_recommendations": [],
            "summary": {
                "data_overview": f"File tidak ditemukan: {filepath}",
                "key_insights": [],
                "warnings": ["File tidak ditemukan"],
            },
        }

    markdown = extract_to_markdown(filepath, filename=filename)
    if not markdown:
        return {
            "tables": [],
            "chart_recommendations": [],
            "summary": {
                "data_overview": f"Gagal mengekstrak data dari file: {filepath.name}",
                "key_insights": [],
                "warnings": ["File mungkin kosong atau format tidak didukung"],
            },
        }

    return format_data_with_ai(markdown, filename=filename or filepath.name)
