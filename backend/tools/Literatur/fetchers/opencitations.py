"""Fetcher untuk OpenCitations — open citation indices (COCI, Meta).

Provides citation data as a complement to Crossref/OpenAlex.
No API key required. Token optional for performance.

Endpoints:
  - /citations/{DOI}     — incoming citations
  - /references/{DOI}    — outgoing references
  - /citation-count/{DOI}
  - /metadata/{DOI}      — bibliographic metadata

We use /metadata for paper lookup and /citations for enrichment.
"""

import logging
import os
from typing import Iterable
from urllib.parse import quote

from ..http_client import RateLimiter, fetch_json, normalize_doi
from ..paper import Paper

BASE = "https://opencitations.net/index/api/v1"
META_BASE = "https://opencitations.net/meta/api/v1"

log = logging.getLogger(__name__)


def _parse_metadata(item: dict) -> Paper | None:
    """Parse OpenCitations Meta API metadata response."""
    title = item.get("title")
    if not title:
        return None

    authors = []
    author_str = item.get("author")
    if author_str:
        authors = [a.strip() for a in author_str.split(";") if a.strip()]

    year = None
    date_str = item.get("date")
    if date_str:
        try:
            year = int(date_str[:4])
        except (ValueError, TypeError):
            pass

    doi = item.get("doi")

    # Normalize venue_type from item.get("type") — OpenCitations "type" is venue-level
    raw_type = item.get("type", "")
    _oc_vt_map = {
        "journal article": "journal",
        "article": "journal",
        "conference paper": "conference",
        "proceedings": "conference",
        "book": "book",
        "book chapter": "book",
        "dataset": "repository",
        "preprint": "repository",
        "report": "repository",
        "other": "unknown",
    }
    venue_type = _oc_vt_map.get(raw_type.lower(), "unknown") if raw_type else None

    # Normalize type (same input, different output)
    _oc_type_map = {
        "journal article": "journal-article",
        "article": "journal-article",
        "conference paper": "conference-paper",
        "proceedings": "conference-paper",
        "book": "book",
        "book chapter": "book",
        "dataset": "dataset",
        "preprint": "preprint",
        "report": "journal-article",
        "other": None,
    }
    normalized_type = _oc_type_map.get(raw_type.lower()) if raw_type else None

    return Paper(
        source="opencitations",
        source_id=doi or item.get("omid", ""),
        title=title,
        authors=authors,
        abstract=None,
        year=year,
        venue=item.get("venue"),
        venue_type=venue_type,
        doi=doi,
        url=f"https://doi.org/{doi}" if doi else None,
        pdf_url=None,
        citations=None,
        is_open_access=None,
        type=normalized_type,
        publisher=item.get("publisher"),
    )


def _normalize(doi: str) -> str | None:
    return normalize_doi(doi)


def get_citations(client, doi: str) -> list[dict]:
    d = _normalize(doi)
    if not d:
        return []
    rl = RateLimiter(0.3)
    rl.wait()
    data = fetch_json(client, f"{BASE}/citations/{d}")
    return data if isinstance(data, list) else []


def get_references(client, doi: str) -> list[dict]:
    d = _normalize(doi)
    if not d:
        return []
    rl = RateLimiter(0.3)
    rl.wait()
    data = fetch_json(client, f"{BASE}/references/{d}")
    return data if isinstance(data, list) else []


def get_citation_count(client, doi: str) -> int | None:
    d = _normalize(doi)
    if not d:
        return None
    rl = RateLimiter(0.3)
    rl.wait()
    data = fetch_json(client, f"{BASE}/citation-count/{d}")
    if data and isinstance(data, dict):
        return data.get("count")
    return None


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search OpenCitations Meta for papers by title/DOI.

    OpenCitations is primarily a citation index, not a search engine.
    For broad discovery, use the Meta API search endpoint.
    """
    rl = RateLimiter(0.3)
    fetched = 0

    # Meta API search endpoint changed — disable for now
    log.warning("OpenCitations search disabled (Meta API endpoint changed)")
    return
    
    # TODO: Fix endpoint or use DOI-based citation enrichment only
