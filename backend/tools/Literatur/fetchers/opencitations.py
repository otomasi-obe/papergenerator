"""Fetcher untuk OpenCitations — citation index enrichment.

Since text search is removed from OpenCitations Meta API, this fetcher
uses Crossref to discover DOIs, then enriches with OpenCitations metadata
(authors, year, venue, citations, references).
"""

import logging
import os
from typing import Iterable
from urllib.parse import quote

from ..http_client import RateLimiter, fetch_json, normalize_doi
from ..paper import Paper

BASE = "https://opencitations.net/index/api/v1"
META_BASE = "https://api.opencitations.net/meta/v1"

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
    """Get incoming citations for a DOI."""
    d = _normalize(doi)
    if not d:
        return []
    rl = RateLimiter(0.3)
    rl.wait()
    data = fetch_json(client, f"{BASE}/citations/{d}")
    return data if isinstance(data, list) else []


def get_references(client, doi: str) -> list[dict]:
    """Get outgoing references for a DOI."""
    d = _normalize(doi)
    if not d:
        return []
    rl = RateLimiter(0.3)
    rl.wait()
    data = fetch_json(client, f"{BASE}/references/{d}")
    return data if isinstance(data, list) else []


def get_citation_count(client, doi: str) -> int | None:
    """Get citation count for a DOI."""
    d = _normalize(doi)
    if not d:
        return None
    rl = RateLimiter(0.3)
    rl.wait()
    data = fetch_json(client, f"{BASE}/citation-count/{d}")
    if data and isinstance(data, dict):
        return data.get("count")
    return None


def _enrich_doi(client, doi: str) -> Paper | None:
    """Enrich a single DOI with OpenCitations metadata."""
    if not doi:
        return None
    rl = RateLimiter(0.3)
    rl.wait()
    data = fetch_json(client, f"{META_BASE}/metadata/{doi}")
    if not data:
        return None
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        return None
    return _parse_metadata(data)


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search via Crossref DOI discovery, then enrich with OpenCitations.

    OpenCitations doesn't support text search anymore. Strategy:
    1. Get DOIs from Crossref for the query
    2. Enrich each DOI with OpenCitations metadata
    """
    from .crossref import search as crossref_search

    rl = RateLimiter(0.5)
    fetched = 0
    seen_dois = set()

    cr_filters = dict(filters) if filters else {}

    # Get DOIs from Crossref first (fast batch)
    cr_papers = []
    try:
        for p in crossref_search(client, query, min(limit * 2, 50), cr_filters):
            cr_papers.append(p)
            if len(cr_papers) >= limit * 2:
                break
    except Exception:
        return

    for cr_paper in cr_papers:
        if fetched >= limit:
            return
        doi = cr_paper.doi
        if not doi or doi in seen_dois:
            continue
        seen_dois.add(doi)

        rl.wait()
        try:
            paper = _enrich_doi(client, doi)
        except Exception:
            paper = None
        if paper:
            # Merge: keep Crossref abstract if OpenCitations has none
            if not paper.abstract and cr_paper.abstract:
                paper.abstract = cr_paper.abstract
            if not paper.year and cr_paper.year:
                paper.year = cr_paper.year
            if not paper.authors and cr_paper.authors:
                paper.authors = cr_paper.authors
            yield paper
            fetched += 1
        else:
            # Fallback: yield Crossref paper directly if OC enrichment fails
            yield cr_paper
            fetched += 1
