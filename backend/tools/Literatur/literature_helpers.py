"""Standalone helpers for literature retrieval — used by chat/editor.

Only depends on DB models + log. No circular imports with old slr_api.
"""

from __future__ import annotations

import logging
import re

from utils.database.models import LiteratureItem, db

log = logging.getLogger(__name__)

_MAX_TITLE_LEN = 200
_MAX_ABSTRACT_LEN = 500

def _sanitize_lit_text(txt: str | None, max_len: int = 500) -> str:
    """Clean and truncate a literature text field."""
    if not txt:
        return ""
    # Remove mojibake patterns (common in older data)
    txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)
    txt = txt.replace("\xa0", " ").strip()
    if len(txt) > max_len:
        txt = txt[:max_len].rstrip() + "…"
    return txt


def get_pinned_literature(paper_id: str, user_id: int, max_items: int = 10) -> str:
    """Ambil literature yang di-check user, format sebagai blok teks utk
    injeksi ke system prompt (chat / paperfull).

    HANYA return item dengan is_checked=True (user klik check).
    Returns empty string kalau tidak ada checked item.
    """
    if not paper_id or not user_id:
        return ""
    try:
        items = (
            db.session.query(LiteratureItem)
            .filter_by(paper_id=paper_id, user_id=user_id, is_checked=True)
            .order_by(LiteratureItem.pinned.desc(), LiteratureItem.score_total.desc())
            .limit(max_items)
            .all()
        )
        if not items:
            return ""

        lines: list[str] = []
        for i, it in enumerate(items, 1):
            authors_list = it.authors or []
            authors = ", ".join(authors_list[:3])
            if len(authors_list) > 3:
                authors += " et al."

            header_parts = [f"[{i}] {_sanitize_lit_text(it.title, _MAX_TITLE_LEN) or 'Untitled'}"]
            if authors:
                header_parts.append(f"— {authors}")
            if it.year:
                header_parts.append(f"({it.year})")
            lines.append(" ".join(header_parts))

            if it.doi:
                lines.append(f"    DOI: {it.doi}")
            elif it.url:
                lines.append(f"    URL: {it.url}")

            # Prefer summary (AI-generated) over raw abstract
            description = _sanitize_lit_text(it.summary or it.abstract, _MAX_ABSTRACT_LEN)
            if description:
                lines.append(f"    {description}")
            lines.append("")  # blank separator

        return "\n".join(lines).strip()
    except Exception as e:
        log.warning("[get_pinned_literature] failed for paper=%s: %s", paper_id, e)
        return ""
