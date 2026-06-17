"""Reference normalization for the export pipeline.

The AI emits references as structured dicts (``{authors, title, journal,
volume, pages, doi, type, ...}``) nested under ``references.content`` (or as a
bare list). Most journal generators' ``_add_references`` read ``item["text"]``
and skip anything without it — so structured-only references render as empty.

This module walks the references in-place and injects a formatted ``text``
field (using the shared multi-style ``reference_formatter``) for any dict that
lacks one. Running it once in the export route — before the journal builder —
fixes reference rendering for every generator uniformly, the same way the image
reconcile step fixes figures.

Idempotent: a reference that already has a non-empty ``text`` is left untouched.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Journal template code -> citation style slug understood by reference_formatter.
# Default is IEEE numbered (the overwhelming majority of these templates).
_JOURNAL_STYLE = {
    "APA": "apa",
    "MDPI": "apa",         # MDPI uses an APA-like author-date in many templates
    "Springer": "apa",
    "Elsevier": "apa",
    "ACM": "acs",
}


def style_for_journal(journal_code: str | None) -> str:
    if not journal_code:
        return "ieee"
    return _JOURNAL_STYLE.get(str(journal_code).strip(), "ieee")


def _iter_ref_items(references):
    """Yield (container_list, index, item) for every reference dict/string,
    handling both the ``{title, content:[...]}`` dict shape and a bare list."""
    if isinstance(references, dict):
        content = references.get("content")
        if isinstance(content, list):
            for i, item in enumerate(content):
                yield content, i, item
    elif isinstance(references, list):
        for i, item in enumerate(references):
            yield references, i, item


def normalize_references(paper_data: dict, style: str = "ieee") -> int:
    """Inject formatted ``text`` into structured reference dicts in-place.

    Returns the number of references that received a freshly formatted ``text``.
    """
    if not isinstance(paper_data, dict):
        return 0
    references = paper_data.get("references")
    if references is None:
        return 0

    try:
        from tools.preview.reference_formatter import format_reference
    except Exception:
        log.warning("reference_formatter unavailable; skipping reference normalize", exc_info=True)
        return 0

    injected = 0
    for _container, idx, item in _iter_ref_items(references):
        if not isinstance(item, dict):
            continue
        existing = str(item.get("text") or item.get("Text") or "").strip()
        if existing:
            continue
        try:
            formatted = format_reference(item, style=style, index=idx + 1)
        except Exception:
            log.warning("format_reference failed for ref #%d", idx + 1, exc_info=True)
            continue
        formatted = (formatted or "").strip()
        if formatted:
            item["text"] = formatted
            injected += 1
    return injected
