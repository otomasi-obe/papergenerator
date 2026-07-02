"""Fetcher untuk Semantic Scholar - https://api.semanticscholar.org/graph/v1

Enhancements ported from findpapers connector:
- isOpenAccess field parsing
- s2FieldsOfStudy + fieldsOfStudy parsing
- Better venue type mapping from publicationVenue.type
- publicationDate parsing (not just year)
- Expanded type normalization (Dataset, News, LettersAndComments, MetaAnalysis, Study, CaseReport, ClinicalTrial)
- Bulk search endpoint (/paper/search/bulk) for large result sets
- Author list with proper name extraction
"""

import os
from datetime import date
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

# Standard search endpoint
BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
# Bulk search endpoint — returns more results per call, paginated via token
BULK_BASE = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

FIELDS = ",".join(
    [
        "paperId",
        "externalIds",
        "title",
        "abstract",
        "year",
        "publicationDate",
        "authors",
        "venue",
        "publicationVenue",
        "publicationTypes",
        "citationCount",
        "openAccessPdf",
        "isOpenAccess",
        "fieldsOfStudy",
        "s2FieldsOfStudy",
    ]
)

# Mapping from publicationTypes to venue_type
_VENUE_TYPE_MAP = {
    "JournalArticle": "journal",
    "Conference": "conference",
    "Book": "book",
    "Review": "journal",
    "Editorial": "journal",
    "Letter": "journal",
    "CaseReport": "journal",
    "ClinicalTrial": "journal",
    "Dataset": "repository",
    "News": "other",
    "LettersAndComments": "journal",
    "MetaAnalysis": "journal",
    "Study": "journal",
}

# Mapping from publicationTypes to Paper.type
_TYPE_MAP = {
    "JournalArticle": "journal-article",
    "Conference": "conference-paper",
    "Book": "book",
    "Review": "journal-article",
    "Editorial": "journal-article",
    "Letter": "journal-article",
    "CaseReport": "case-report",
    "ClinicalTrial": "clinical-trial",
    "Dataset": "dataset",
    "News": "news",
    "LettersAndComments": "letters-and-comments",
    "MetaAnalysis": "meta-analysis",
    "Study": "study",
}

# Mapping from publicationVenue.type → venue_type (takes precedence when present)
_PUB_VENUE_TYPE_MAP = {
    "journal": "journal",
    "conference": "conference",
    "book": "book",
    "repository": "repository",
}

# Threshold: use bulk search when limit exceeds this
_BULK_THRESHOLD = 100


def _parse_date(item: dict) -> date | None:
    """Extract publication date. Prefers publicationDate; falls back to year."""
    date_str = (item.get("publicationDate") or "").strip()
    if date_str:
        try:
            return date.fromisoformat(date_str[:10])
        except ValueError:
            pass
    year = item.get("year")
    if year:
        try:
            return date(int(year), 1, 1)
        except (ValueError, TypeError):
            pass
    return None


def _parse_fields_of_study(item: dict) -> list[str]:
    """Extract combined fieldsOfStudy + s2FieldsOfStudy categories."""
    fields = set()
    for f in item.get("fieldsOfStudy") or []:
        if isinstance(f, str) and f.strip():
            fields.add(f.strip())
    for entry in item.get("s2FieldsOfStudy") or []:
        if isinstance(entry, dict):
            cat = (entry.get("category") or "").strip()
            if cat and cat not in fields:
                fields.add(cat)
    return sorted(fields) if fields else []


def _parse_authors(item: dict) -> list[str]:
    """Extract author names from the authors field."""
    authors = []
    authors_raw = item.get("authors") or item.get("author") or []
    if isinstance(authors_raw, str):
        # Sometimes it's a comma-separated string
        return [a.strip() for a in authors_raw.split(",") if a.strip()]
    for a in authors_raw:
        if isinstance(a, str):
            if a.strip():
                authors.append(a.strip())
        elif isinstance(a, dict):
            name = a.get("name")
            if name and name.strip():
                authors.append(name.strip())
    return authors


def _parse(item: dict) -> Paper | None:
    title = item.get("title")
    if not title:
        return None

    authors = _parse_authors(item)
    ext = item.get("externalIds") or {}
    doi = ext.get("DOI")
    pub_venue = item.get("publicationVenue") or {}

    # Venue type: prefer publicationVenue.type, fall back to publicationTypes mapping
    venue_type = None
    pv_type = (pub_venue.get("type") or "").strip().lower()
    if pv_type:
        venue_type = _PUB_VENUE_TYPE_MAP.get(pv_type, pv_type)
    if not venue_type:
        pub_types = item.get("publicationTypes") or []
        if pub_types:
            first = pub_types[0]
            venue_type = _VENUE_TYPE_MAP.get(first, first.lower() if isinstance(first, str) else None)

    # Normalize type
    normalized_type = None
    pub_types = item.get("publicationTypes") or []
    if pub_types:
        normalized_type = _TYPE_MAP.get(pub_types[0], pub_types[0].lower() if isinstance(pub_types[0], str) else None)

    # Parsed date → year
    parsed_date = _parse_date(item)

    # Landing page URL
    landing_url = f"https://www.semanticscholar.org/paper/{item.get('paperId')}" if item.get("paperId") else None

    # PDF link if available
    pdf_info = item.get("openAccessPdf") or {}
    pdf_url = pdf_info.get("url")

    # isOpenAccess: explicit field from S2, fallback to presence of openAccessPdf
    raw_oa = item.get("isOpenAccess")
    oa = bool(raw_oa) if raw_oa is not None else bool(pdf_info)

    fields_of_study = _parse_fields_of_study(item)

    return Paper(
        source="semantic_scholar",
        source_id=(item.get("paperId") or ""),
        title=title,
        authors=authors,
        abstract=item.get("abstract"),
        year=parsed_date.year if parsed_date else item.get("year"),
        venue=item.get("venue") or pub_venue.get("name"),
        venue_type=venue_type,
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url if oa else None,
        citations=item.get("citationCount"),
        is_open_access=oa,
        type=normalized_type,
        publisher=pub_venue.get("publisher"),
        publication_date=parsed_date.isoformat() if parsed_date else None,
        fields_of_study=fields_of_study if fields_of_study else None,
    )


def _search_standard(client, query: str, limit: int, filters: dict | None, api_key: str | None,
                     rl: RateLimiter, headers: dict) -> Iterable[Paper]:
    """Standard paginated search via /paper/search."""
    per_page = min(limit, 100)
    fetched = 0
    offset = 0

    while fetched < limit:
        rl.wait()
        params = {
            "query": query,
            "limit": min(per_page, limit - fetched),
            "offset": offset,
            "fields": FIELDS,
            "sort": "relevance",
        }
        if filters:
            if "year" in filters:
                params["year"] = filters["year"]
            if "venue" in filters:
                params["venue"] = filters["venue"]
            if "publication_types" in filters:
                params["publicationTypes"] = filters["publication_types"]
            if "open_access" in filters and filters["open_access"]:
                params["openAccessPdf"] = ""
            if "since" in filters:
                params.setdefault("publicationDateOrYear", f"{filters['since']}:")
            if "until" in filters:
                sd = filters.get("since", "")
                params.setdefault("publicationDateOrYear", f"{sd}:{filters['until']}")

        data = fetch_json(client, BASE, params=params, headers=headers)
        if not data:
            return
        items = data.get("data") or []
        if not items:
            return
        for it in items:
            paper = _parse(it)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        offset += len(items)
        if not data.get("next"):
            return


def _search_bulk(client, query: str, limit: int, filters: dict | None, api_key: str | None,
                 rl: RateLimiter, headers: dict) -> Iterable[Paper]:
    """Bulk search via /paper/search/bulk — uses token-based pagination.

    The bulk endpoint is designed for retrieving large result sets. It returns
    a ``token`` field for pagination instead of offsets.
    """
    fetched = 0
    token = None

    while fetched < limit:
        rl.wait()
        page_size = min(limit - fetched, 1000)  # bulk allows larger pages
        params = {
            "query": query,
            "fields": FIELDS,
            "limit": page_size,
            "sort": "relevance",
        }
        if token:
            params["token"] = token
        if filters:
            if "year" in filters:
                params["year"] = filters["year"]
            if "venue" in filters:
                params["venue"] = filters["venue"]
            if "publicationDateOrYear" in filters:
                params["publicationDateOrYear"] = filters["publicationDateOrYear"]
            if "since" in filters:
                params["publicationDateOrYear"] = f"{filters['since']}:"
            if "until" in filters:
                sd = filters.get("since", "")
                params["publicationDateOrYear"] = f"{sd}:{filters['until']}"
            if "publication_types" in filters:
                params["publicationTypes"] = filters["publication_types"]

        data = fetch_json(client, BULK_BASE, params=params, headers=headers)
        if not data:
            return
        items = data.get("data") or []
        if not items:
            return
        for it in items:
            paper = _parse(it)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        token = data.get("token")
        if not token or len(items) < page_size:
            return


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Free tier rate limit ketat (~1 req/sec). Set S2_API_KEY untuk tinggi.

    Automatically selects the bulk search endpoint when ``limit`` > 100
    for more efficient large result sets. Falls back to standard pagination
    for smaller queries (more stable ordering).
    """
    api_key = os.getenv("S2_API_KEY")
    contact_email = os.getenv("SLR_CONTACT_EMAIL") or "research@example.com"
    # Free tier: 1 req per 10s without key, 1 req/s with key
    rl = RateLimiter(0.5 if api_key else 10.0)
    headers = {"x-api-key": api_key, "User-Agent": f"PaperRiset-SLR/0.1 ({contact_email})"} if api_key else {"User-Agent": f"PaperRiset-SLR/0.1 ({contact_email})"}

    yield from _search_standard(client, query, limit, filters, api_key, rl, headers)
