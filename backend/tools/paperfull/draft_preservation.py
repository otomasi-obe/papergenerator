"""Deterministic classification and verbatim preservation for uploaded user drafts.

AI prompt instructions are advisory; this module provides the actual guarantee by
replacing matching generated sections with the exact extracted draft text and then
verifying equality before persistence.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

_SOURCE_RE = re.compile(r"^\s*=== Extracted from: (?P<name>.+?) ===\s*\n?", re.I)
_HEADING_ALIASES = {
    "abstract": ("abstract", "abstrak"),
    "introduction": ("introduction", "pendahuluan", "latar belakang"),
    "literature_review": ("literature review", "related work", "tinjauan pustaka", "kajian pustaka", "landasan teori"),
    "methodology": ("methodology", "methods", "materials and methods", "research method", "metode", "metodologi", "metode penelitian"),
    "results": ("results", "hasil", "hasil penelitian"),
    "discussion": ("discussion", "pembahasan"),
    "results_discussion": ("results and discussion", "hasil dan pembahasan"),
    "conclusion": ("conclusion", "conclusions", "kesimpulan", "simpulan"),
    "acknowledgments": ("acknowledgment", "acknowledgments", "acknowledgement", "ucapan terima kasih"),
    "references": ("references", "bibliography", "daftar pustaka", "referensi"),
}
_ALIAS_TO_KEY = {alias: key for key, aliases in _HEADING_ALIASES.items() for alias in aliases}
_HEADING_RE = re.compile(
    r"^\s*(?:(?:\d+(?:\.\d+)*)|(?:[IVXLC]+))[.)]?\s+|^\s*",
    re.I,
)
_PLACEHOLDER_RE = re.compile(r"\[(?:TODO|LENGKAPI|FILL(?:\s+HERE)?)\]|\.{3,}", re.I)


def split_extracted_source(text: str, fallback_name: str = "uploaded-file") -> tuple[str, str]:
    match = _SOURCE_RE.match(text or "")
    if not match:
        return fallback_name, text or ""
    return match.group("name").strip(), (text or "")[match.end():]


def _normalise_heading(line: str) -> str:
    value = _HEADING_RE.sub("", line.strip(), count=1)
    value = re.sub(r"[:\-–—]+$", "", value).strip().lower()
    return re.sub(r"\s+", " ", value)


def _heading_key(line: str) -> str | None:
    normalised = _normalise_heading(line)
    return _ALIAS_TO_KEY.get(normalised)


def classify_uploaded_text(text: str, filename: str = "") -> dict[str, Any]:
    """Classify extracted upload as narrative_draft, raw_data, or reference_context."""
    name, body = split_extracted_source(text, filename or "uploaded-file")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    headings = [(index, _heading_key(line)) for index, line in enumerate(lines)]
    heading_keys = [key for _, key in headings if key]
    long_paragraphs = [line for line in lines if len(line.split()) >= 20]
    numeric_tokens = re.findall(r"(?<!\w)[+-]?(?:\d+[.,]?\d*|[.,]\d+)%?(?!\w)", body)
    words = re.findall(r"\b[^\W\d_]{3,}\b", body, re.UNICODE)
    numeric_ratio = len(numeric_tokens) / max(1, len(numeric_tokens) + len(words))
    table_signals = body.count("|") + body.count("\t")

    reasons: list[str] = []
    if ext in {"csv", "xls", "xlsx", "tsv"}:
        return {"kind": "raw_data", "confidence": 1.0, "filename": name, "reasons": [f".{ext} data format"]}
    # Multiple recognised academic headings strongly indicate a draft even when
    # individual extracted paragraphs are short (DOCX line extraction commonly
    # splits prose into short lines).  Require at least two headings plus either
    # two moderately long lines or a DOC/DOCX container.
    moderately_long = [line for line in lines if len(line.split()) >= 7]
    if len(set(heading_keys)) >= 2 and (len(moderately_long) >= 2 or ext in {"doc", "docx"}):
        reasons.extend([f"{len(set(heading_keys))} academic headings", f"{len(moderately_long)} narrative lines"])
        if ext in {"doc", "docx"}:
            reasons.append(f".{ext} narrative document")
        return {"kind": "narrative_draft", "confidence": min(0.99, 0.70 + 0.04 * len(set(heading_keys))), "filename": name, "reasons": reasons}
    if numeric_ratio >= 0.18 or table_signals >= 20:
        return {"kind": "raw_data", "confidence": min(0.95, 0.65 + numeric_ratio), "filename": name, "reasons": ["numeric/table-dominant content"]}
    return {"kind": "reference_context", "confidence": 0.55, "filename": name, "reasons": ["no reliable draft or raw-data signature"]}


def parse_draft_sections(text: str, filename: str = "") -> dict[str, Any]:
    """Parse recognised academic headings while preserving section text exactly."""
    name, body = split_extracted_source(text, filename or "uploaded-file")
    lines = body.splitlines()
    boundaries: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        key = _heading_key(line)
        if key:
            boundaries.append((index, key, line))
    sections: dict[str, Any] = {}
    for boundary_index, (line_index, key, title) in enumerate(boundaries):
        if key == "references":
            continue
        end = boundaries[boundary_index + 1][0] if boundary_index + 1 < len(boundaries) else len(lines)
        content = "\n".join(lines[line_index + 1:end])
        # Ignore entirely empty sections; the AI may generate them.
        if not content.strip():
            continue
        sections[key] = {
            "key": key,
            "title": title,
            "content": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "has_placeholders": bool(_PLACEHOLDER_RE.search(content)),
        }
    return {"filename": name, "sections": sections, "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}


def collect_draft_manifest(texts: list[str]) -> tuple[list[str], list[str], dict[str, Any]]:
    """Partition Data/Draft uploads into raw data, references, and protected drafts."""
    data_texts: list[str] = []
    reference_texts: list[str] = []
    drafts: list[dict[str, Any]] = []
    classifications: list[dict[str, Any]] = []
    for text in texts:
        classification = classify_uploaded_text(text)
        classifications.append(classification)
        if classification["kind"] == "raw_data":
            data_texts.append(text)
        elif classification["kind"] == "narrative_draft":
            parsed = parse_draft_sections(text, classification["filename"])
            if parsed["sections"]:
                drafts.append(parsed)
                reference_texts.append(text)
            else:
                reference_texts.append(text)
        else:
            reference_texts.append(text)
    return data_texts, reference_texts, {"drafts": drafts, "classifications": classifications}


def _canonical_section_title(title: str) -> str | None:
    return _heading_key(title or "")


def _text_items(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict) and item.get("id") == "text"]


def _set_section_text(section: dict[str, Any], exact_text: str) -> None:
    content = section.get("content")
    non_text = [item for item in content if isinstance(item, dict) and item.get("id") != "text"] if isinstance(content, list) else []
    section["content"] = [{"id": "text", "text": exact_text}] + non_text


def apply_verbatim_drafts(paper: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Overlay exact draft sections on normalized paper and return verification audit."""
    protected: dict[str, dict[str, Any]] = {}
    for draft in manifest.get("drafts", []):
        for key, section in draft.get("sections", {}).items():
            protected.setdefault(key, {**section, "source_file": draft.get("filename", "")})

    matches: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for key, source in protected.items():
        if source.get("has_placeholders"):
            # Partial placeholders need an explicit span-aware editor; until then,
            # fail safe by preserving the entire section verbatim.
            pass
        if key == "abstract":
            paper["abstract"] = source["content"]
            actual = paper.get("abstract", "")
        else:
            target = None
            for field, section in paper.items():
                if field.startswith("section") and isinstance(section, dict) and _canonical_section_title(str(section.get("title", ""))) == key:
                    target = section
                    break
            if target is None:
                unmatched.append(key)
                continue
            target["title"] = source["title"]
            _set_section_text(target, source["content"])
            items = _text_items(target.get("content"))
            actual = items[0].get("text", "") if items else ""
        exact = actual == source["content"]
        matches.append({
            "section": key, "source_file": source["source_file"], "exact": exact,
            "expected_sha256": source["sha256"],
            "actual_sha256": hashlib.sha256(actual.encode("utf-8")).hexdigest(),
            "changed_characters": 0 if exact else _changed_character_count(source["content"], actual),
        })

    mismatches = [item for item in matches if not item["exact"]]
    status = "verified" if protected and not mismatches and not unmatched else ("not_applicable" if not protected else "failed")
    return {
        "status": status,
        "protected_sections": len(protected), "exact_matches": len(matches) - len(mismatches),
        "mismatches": len(mismatches), "unmatched_sections": unmatched, "sections": matches,
    }


def _changed_character_count(expected: str, actual: str) -> int:
    common = min(len(expected), len(actual))
    return sum(expected[i] != actual[i] for i in range(common)) + abs(len(expected) - len(actual))


def assert_verbatim_preserved(audit: dict[str, Any]) -> None:
    if audit.get("status") == "failed":
        raise ValueError(
            "Draft preservation failed: "
            f"{audit.get('mismatches', 0)} mismatches, "
            f"unmatched={audit.get('unmatched_sections', [])}"
        )


def draft_prompt_block(manifest: dict[str, Any]) -> str:
    """Build compact prompt guidance; exact enforcement still occurs programmatically."""
    blocks = []
    for draft in manifest.get("drafts", []):
        for key, section in draft.get("sections", {}).items():
            blocks.append(
                f"--- PROTECTED SECTION: {key} | SHA256 {section['sha256']} ---\n"
                f"TITLE: {section['title']}\nCONTENT (COPY EXACTLY):\n{section['content']}"
            )
    if not blocks:
        return ""
    return (
        "## USER DRAFT — PROTECTED VERBATIM TEXT\n"
        "The blocks below were written by the user. Copy every protected title and content EXACTLY, character for character. "
        "Do not paraphrase, translate, humanize, correct grammar, alter punctuation, or reorder paragraphs. "
        "Generate only sections not present in the protected blocks. Existing text outside explicit placeholders is immutable.\n\n"
        + "\n\n".join(blocks)
    )
