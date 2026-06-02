"""Auto-memory extraction for the chat workflow.

Hooks into chat.py right after the user's message is committed to extract
durable facts (jurusan, topik, metode, …) and persist them via
``chat_tools._save_memory`` without forcing the LLM to call ``SaveMemory``.

The extractor is a two-layer pipeline:

1. **Regex layer** — fast, free, deterministic. Recognises:
   * AI's last assistant message announces ``[key=<name>]`` (the prompt's
     state-machine marker) → user's reply is treated as that key's value.
   * AI's last message contains an ``[OPSI]…[/OPSI]`` block, user replies
     with ``"1"``, ``"pilih 2"``, ``"yang ketiga"``, … → resolve to the
     option's text.
   * Explicit ``ingat: <text>`` / ``simpan: key=<k> value=<v>`` patterns.

2. **LLM fallback (MODELCHAT)** — only fired when an expected key is known
   but the regex layer came up empty. Tight prompt, strict JSON, 64-token
   cap, 10 s timeout. Any failure is swallowed (logged at warning level).

The module never raises into the request path — every public entry returns
``[]`` on internal failure so a buggy extractor cannot break chat.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import requests

try:
    from chat.tools import _save_memory  # type: ignore
except Exception:  # pragma: no cover — defensive import for tests
    _save_memory = None  # type: ignore

log = logging.getLogger(__name__)

_STOPWORDS = {
    "oke",
    "ok",
    "okay",
    "lanjut",
    "ya",
    "tidak",
    "yes",
    "no",
    "hmm",
    "iya",
    "yep",
    "nope",
    "udah",
    "sudah",
    "ga",
    "gak",
    "engga",
}

_ORDINAL_MAP = {
    "pertama": 1,
    "kesatu": 1,
    "satu": 1,
    "kedua": 2,
    "dua": 2,
    "ketiga": 3,
    "tiga": 3,
    "keempat": 4,
    "empat": 4,
    "kelima": 5,
    "lima": 5,
}

_OPSI_RE = re.compile(r"\[OPSI\](.*?)\[/OPSI\]", re.DOTALL | re.IGNORECASE)
_OPTION_LINE_RE = re.compile(r"^\s*(\d+)\s*[\)\.\-:]\s*(.+?)\s*$", re.MULTILINE)
_KEY_MARKER_RE = re.compile(r"\[key=([a-zA-Z_][a-zA-Z0-9_]*)\]")
_NUMERIC_REPLY_RE = re.compile(r"^\s*([1-9])\s*$")
_PILIH_RE = re.compile(r"^\s*pilih\s+(\d+)\s*$", re.IGNORECASE)
_YANG_ORDINAL_RE = re.compile(
    r"^\s*yang\s+(pertama|kesatu|kedua|ketiga|keempat|kelima)\s*$",
    re.IGNORECASE,
)
_INGAT_RE = re.compile(r"\bingat\s*:\s*(.+)", re.IGNORECASE)
_SIMPAN_RE = re.compile(
    r"\bsimpan\s*:\s*key\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+value\s*=\s*(.+)",
    re.IGNORECASE,
)

_LLM_TIMEOUT_S = 10.0
_LLM_MAX_TOKENS = 64
_LLM_MODEL = os.getenv("MODELCHAT") or "VIOLA-CHAT"
_LLM_SYSTEM = (
    "From this user reply to a question about <expected_key>, return strict JSON: "
    '{"value": "<extracted value>"} or null. '
    "No prose, no markdown, no explanation. Cap value 200 chars."
)

BULK_EXTRACT_PROMPT = """
Extract research paper planning information from this user message.

Return JSON with these keys (only include if clearly stated):
- jurusan: academic department/major
- topik: research topic
- latar_belakang: background/motivation
- literatur_status: "belum" | "sudah" | "sebagian"
- metode: research method/approach
- data_status: "belum" | "sudah" | "estimasi"
- kesimpulan_target: expected conclusion/findings

Return {{}} if no clear information extractable.

User message: {user_msg}
"""


@dataclass
class ExtractedFact:
    """A single fact extracted from a user reply."""

    key: str
    value: str
    kind: str = "fact"
    source: str = "regex"  # "regex" or "llm"


@dataclass
class _ParsedAssistant:
    expected_key: Optional[str] = None
    options: dict[int, str] = field(default_factory=dict)


# ── parsers ────────────────────────────────────────────────────────────────


def _parse_assistant(msg: Optional[str]) -> _ParsedAssistant:
    parsed = _ParsedAssistant()
    if not msg:
        return parsed
    m = _KEY_MARKER_RE.search(msg)
    if m:
        parsed.expected_key = m.group(1).strip().lower()
    om = _OPSI_RE.search(msg)
    if om:
        block = om.group(1)
        for line in _OPTION_LINE_RE.finditer(block):
            idx = int(line.group(1))
            text = line.group(2).strip()
            if text:
                parsed.options[idx] = text
    return parsed


def _resolve_option_index(user_msg: str) -> Optional[int]:
    if not user_msg:
        return None
    s = user_msg.strip()
    m = _NUMERIC_REPLY_RE.match(s)
    if m:
        return int(m.group(1))
    m = _PILIH_RE.match(s)
    if m:
        return int(m.group(1))
    m = _YANG_ORDINAL_RE.match(s)
    if m:
        return _ORDINAL_MAP.get(m.group(1).lower())
    return None


# ── confidence filter ─────────────────────────────────────────────────────


def _confidence_ok(value: str, last_assistant_msg: Optional[str]) -> bool:
    v = (value or "").strip()
    if len(v) < 3:
        return False
    if v.lower() in _STOPWORDS:
        return False
    if last_assistant_msg and v.lower() in last_assistant_msg.lower():
        # Pure echo of a chunk of the assistant's own message.
        # Allow short option text (already resolved by us); reject long echoes.
        if len(v) > 80:
            return False
    return True


# ── layer 1: regex ────────────────────────────────────────────────────────


def _regex_layer(
    user_msg: str,
    parsed: _ParsedAssistant,
) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    if not user_msg:
        return facts
    text = user_msg.strip()

    # 1. simpan: key=<k> value=<v>
    sm = _SIMPAN_RE.search(text)
    if sm:
        key = sm.group(1).strip().lower()
        value = sm.group(2).strip()
        facts.append(ExtractedFact(key=key, value=value, source="regex"))
        return facts

    # 2. ingat: <free text> — only useful if we know what key it answers.
    im = _INGAT_RE.search(text)
    if im and parsed.expected_key:
        value = im.group(1).strip()
        if value:
            facts.append(ExtractedFact(key=parsed.expected_key, value=value, source="regex"))
            return facts
    if im and not parsed.expected_key:
        # Stash under a generic key so it's still preserved.
        value = im.group(1).strip()
        if value:
            facts.append(ExtractedFact(key="catatan", value=value, source="regex"))
            return facts

    # 3. option-reply against [OPSI] block.
    if parsed.options:
        idx = _resolve_option_index(text)
        if idx and idx in parsed.options and parsed.expected_key:
            facts.append(
                ExtractedFact(
                    key=parsed.expected_key,
                    value=parsed.options[idx],
                    source="regex",
                )
            )
            return facts

    # 4. plain free-text reply when expected_key is known.
    if parsed.expected_key and len(text) > 5:
        if text.lower() in _STOPWORDS:
            return facts
        # Avoid treating "1) X 2) Y" style replies as the answer.
        if _NUMERIC_REPLY_RE.match(text):
            return facts
        facts.append(ExtractedFact(key=parsed.expected_key, value=text, source="regex"))

    return facts


# ── layer 2: LLM fallback ─────────────────────────────────────────────────


def _llm_fallback_layer(
    expected_key: str,
    user_msg: str,
) -> Optional[ExtractedFact]:
    if not expected_key or not user_msg or len(user_msg.strip()) <= 10:
        return None

    base = (os.getenv("AIOTOMASI_API") or "").rstrip("/")
    api_key = os.getenv("AIOTOMASI_APIKEY") or ""
    if not base or not api_key:
        return None

    url = base + "/chat/completions"
    sys_msg = _LLM_SYSTEM.replace("<expected_key>", expected_key)
    payload = {
        "model": _LLM_MODEL,
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg.strip()},
        ],
        "max_tokens": _LLM_MAX_TOKENS,
        "temperature": 0.0,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_LLM_TIMEOUT_S)
        if resp.status_code != 200:
            log.warning("auto_memory LLM fallback HTTP %s", resp.status_code)
            return None
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content or content.lower() == "null":
            return None
        # Strip code fences if any.
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return None
        value = (parsed.get("value") or "").strip()
        if not value:
            return None
        value = value[:200]
        return ExtractedFact(key=expected_key, value=value, source="llm")
    except Exception as exc:  # pragma: no cover — network / parse errors
        log.warning("auto_memory LLM fallback failed: %s", exc)
        return None


# ── bulk extraction ───────────────────────────────────────────────────


def extract_bulk_info(user_msg: str, paper_id: str, user_id: int) -> dict[str, str]:
    """Extract multiple research paper planning facts from a single user message."""
    if not user_msg or not user_msg.strip():
        return {}

    base = (os.getenv("AIOTOMASI_API") or "").rstrip("/")
    api_key = os.getenv("AIOTOMASI_APIKEY") or ""
    if not base or not api_key:
        log.warning("extract_bulk_info: API credentials not configured")
        return {}

    url = base + "/chat/completions"
    prompt = BULK_EXTRACT_PROMPT.format(user_msg=user_msg.strip())
    payload = {
        "model": _LLM_MODEL,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 256,
        "temperature": 0.0,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15.0)
        if resp.status_code != 200:
            log.warning("extract_bulk_info: HTTP %s", resp.status_code)
            return {}

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        if not content:
            return {}

        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)

        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            log.warning("extract_bulk_info: response not a dict")
            return {}

        result = {}
        valid_keys = {
            "jurusan",
            "topik",
            "latar_belakang",
            "literatur_status",
            "metode",
            "data_status",
            "kesimpulan_target",
        }

        for key, value in parsed.items():
            if key in valid_keys and value and isinstance(value, str):
                result[key] = value.strip()

        if result:
            log.info("extract_bulk_info: extracted %d facts from first message", len(result))

        return result

    except json.JSONDecodeError as exc:
        log.warning("extract_bulk_info: JSON parse error: %s", exc)
        return {}
    except requests.RequestException as exc:
        log.warning("extract_bulk_info: request failed: %s", exc)
        return {}
    except Exception as exc:
        log.warning("extract_bulk_info: unexpected error: %s", exc)
        return {}


# ── persistence ───────────────────────────────────────────────────────────


def _persist(paper_id: str, user_id: int, fact: ExtractedFact) -> bool:
    if _save_memory is None:
        log.warning("auto_memory: _save_memory unavailable; skipping persist")
        return False
    try:
        result = _save_memory(paper_id, user_id, fact.key, fact.value, kind=fact.kind)
        log.info(
            "auto_memory saved key=%s source=%s kind=%s -> %s",
            fact.key,
            fact.source,
            fact.kind,
            (result or "")[:80],
        )
        return True
    except Exception as exc:
        log.warning("auto_memory persist failed for key=%s: %s", fact.key, exc)
        return False


# ── public API ────────────────────────────────────────────────────────────


def extract_facts(
    paper_id: str,
    user_id: int,
    conv,
    user_msg: str,
    last_assistant_msg: Optional[str] = None,
) -> list[ExtractedFact]:
    """Extract facts from ``user_msg`` and persist them via ``_save_memory``.

    Returns the list of saved facts (empty on no-op or failure).
    """
    try:
        if not user_msg or not user_msg.strip():
            return []
        if not paper_id:
            return []

        parsed = _parse_assistant(last_assistant_msg)
        facts = _regex_layer(user_msg, parsed)

        if not facts and parsed.expected_key:
            llm_fact = _llm_fallback_layer(parsed.expected_key, user_msg)
            if llm_fact:
                facts = [llm_fact]

        kept: list[ExtractedFact] = []
        for f in facts:
            f.value = (f.value or "").strip()
            if not _confidence_ok(f.value, last_assistant_msg):
                continue
            if _persist(paper_id, user_id, f):
                kept.append(f)
        return kept
    except Exception as exc:  # pragma: no cover — never surface
        log.warning("auto_memory.extract_facts crashed: %s", exc)
        return []


__all__ = ["ExtractedFact", "extract_facts", "extract_bulk_info"]
