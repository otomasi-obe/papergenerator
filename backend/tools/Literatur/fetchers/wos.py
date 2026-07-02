"""Web of Science Starter API fetcher.

API docs: https://developer.clarivate.com/apis/wos-starter
Requires WOS_API_KEY env var. Rate limit: 1 req/sec (free trial).
"""

import logging
from collections.abc import Iterable
from typing import Any

from ..http_client import RateLimiter, fetch_json, env_required
from ..paper import Paper

log = logging.getLogger(__name__)

BASE_URL = "https://api.clarivate.com/apis/wos-starter/v1/documents"
PAGE_SIZE = 50

# WoS document type → (venue_type, paper_type)
_WOS_TYPE_MAP: dict[str, tuple[str, str]] = {
    "article": ("journal", "article"),
    "review": ("journal", "article"),
    "review article": ("journal", "article"),
    "letter": ("journal", "article"),
    "editorial material": ("journal", "article"),
    "editorial": ("journal", "article"),
    "correction": ("journal", "article"),
    "retraction": ("journal", "article"),
    "note": ("journal", "article"),
    "proceedings paper": ("conference", "conference_paper"),
    "meeting": ("conference", "conference_paper"),
    "meeting abstract": ("conference", "conference_paper"),
    "conference paper": ("conference", "conference_paper"),
    "book": ("book", "book"),
    "book chapter": ("book", "book_chapter"),
    "book review": ("book", "book_chapter"),
    "dissertation": ("thesis", "thesis"),
    "thesis": ("thesis", "thesis"),
    "phd thesis": ("thesis", "thesis"),
    "masters thesis": ("thesis", "thesis"),
    "technical report": ("repository", "report"),
    "report": ("repository", "report"),
    "preprint": ("repository", "preprint"),
    "data paper": ("journal", "article"),
    "software review": ("journal", "article"),
    "bibliography": ("journal", "article"),
    "other": ("journal", "article"),
}

# WoS sourceType → venue_type (overrides document type when present)
_WOS_SOURCE_TYPE_MAP: dict[str, str] = {
    "journal": "journal",
    "conference": "conference",
    "conference proceedings": "conference",
    "book": "book",
    "book series": "book",
}

# Month strings → month number
_WOS_MONTH_MAP: dict[str, int] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    "WIN": 1, "SPR": 4, "SUM": 7, "FAL": 10, "FALL": 10, "AUT": 10,
    "JAN-FEB": 1, "MAR-APR": 3, "MAY-JUN": 5,
    "JUL-AUG": 7, "SEP-OCT": 9, "NOV-DEC": 11,
}


def _parse_year(source_meta: dict) -> int | None:
    """Extract publication year from source metadata."""
    year = source_meta.get("publishYear")
    if year is None:
        return None
    try:
        return int(year)
    except (ValueError, TypeError):
        return None


def _extract_citations(doc: dict[str, Any]) -> int | None:
    """Extract WoS Core citation count."""
    for entry in doc.get("citations") or []:
        if entry.get("db", "").upper() == "WOS":
            count = entry.get("count")
            if count is not None:
                try:
                    return int(count)
                except (ValueError, TypeError):
                    pass
    return None


def _parse_hit(doc: dict[str, Any]) -> Paper | None:
    """Parse a single WoS hit into a Paper."""
    title = (doc.get("title") or "").strip()
    if not title:
        return None

    # Authors
    authors = []
    names = doc.get("names") or {}
    for a in names.get("authors") or []:
        display_name = (a.get("displayName") or "").strip()
        if display_name:
            authors.append(display_name)

    # Source / venue
    source_meta = doc.get("source") or {}
    venue = (source_meta.get("sourceTitle") or "").strip() or None
    year = _parse_year(source_meta)

    # Identifiers
    identifiers = doc.get("identifiers") or {}
    doi = (identifiers.get("doi") or "").strip() or None

    # URL
    links = doc.get("links") or {}
    url = (links.get("record") or "").strip() or None

    # Citations
    citations = _extract_citations(doc)

    # Document type mapping
    raw_types = [(t or "").lower() for t in (doc.get("types") or [])]
    venue_type = None
    paper_type = None
    for t in raw_types:
        if t in _WOS_TYPE_MAP:
            venue_type, paper_type = _WOS_TYPE_MAP[t]
            break

    # Source type can override venue_type
    raw_source_types = [(t or "").lower() for t in (doc.get("sourceTypes") or [])]
    for t in raw_source_types:
        if t in _WOS_SOURCE_TYPE_MAP:
            venue_type = _WOS_SOURCE_TYPE_MAP[t]
            break

    # Publisher
    publisher = (source_meta.get("publisher") or "").strip() or None

    return Paper(
        source="wos",
        source_id=doi or url or title,
        title=title,
        authors=authors,
        abstract=None,  # WoS Starter API does not return abstracts
        year=year,
        venue=venue,
        venue_type=venue_type,
        doi=doi,
        url=url,
        pdf_url=None,
        citations=citations,
        is_open_access=None,
        type=paper_type,
        publisher=publisher,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search Web of Science Starter API.

    Args:
        client: httpx.Client instance.
        query: Search query string.
        limit: Maximum number of papers to return.
        filters: Optional dict with keys:
            - year_from (int): Start year for date filter.
            - year_to (int): End year for date filter.

    Yields:
        Paper objects.
    """
    if not env_required(log, "WOS_API_KEY", "WoS"):
        return

    rl = RateLimiter(1.0)
    page = 1
    fetched = 0

    # Build date filter using WoS PY= syntax
    date_filter = ""
    if filters:
        year_from = filters.get("year_from")
        year_to = filters.get("year_to")
        if year_from or year_to:
            yf = int(year_from) if year_from else 1900
            yt = int(year_to) if year_to else 2099
            date_filter = f" AND PY=({yf}-{yt})"

    full_query = f"({query}){date_filter}" if date_filter else query  # noqa: E501

    while fetched < limit:
        rl.wait()
        page_size = min(PAGE_SIZE, limit - fetched)
        params = {
            "q": full_query,
            "db": "WOS",
            "limit": page_size,
            "page": page,
            "sortField": "PY+D",
        }
        headers = {"X-ApiKey": __import__("os").getenv("WOS_API_KEY", "")}

        data = fetch_json(client, BASE_URL, params=params, headers=headers)
        if not data:
            break

        hits = data.get("hits") or []
        if not hits:
            break

        for hit in hits:
            paper = _parse_hit(hit)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        if len(hits) < page_size:
            break
        page += 1
