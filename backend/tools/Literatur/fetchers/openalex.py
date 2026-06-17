"""Fetcher untuk OpenAlex - https://api.openalex.org"""

import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://api.openalex.org/works"


def _reconstruct_abstract(inv_index: dict | None) -> str | None:
    if not inv_index:
        return None
    pos_map = {}
    for word, positions in inv_index.items():
        for p in positions:
            pos_map[p] = word
    if not pos_map:
        return None
    max_pos = max(pos_map.keys())
    return " ".join(pos_map.get(i, "") for i in range(max_pos + 1)).strip()


def _parse_work(w: dict) -> Paper | None:
    title = w.get("title") or w.get("display_name")
    if not title:
        return None

    authors = []
    for a in w.get("authorships", []) or []:
        author = a.get("author") or {}
        name = author.get("display_name")
        if name:
            authors.append(name)

    venue = None
    venue_type = None
    publisher = None
    primary_loc = w.get("primary_location") or {}
    src = primary_loc.get("source") or {}
    if src:
        venue = src.get("display_name")
        venue_type = src.get("type")
        publisher = src.get("host_organization_name")

    doi = w.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/") :]

    # Get PDF URL from open_access field or primary_location
    oa_info = w.get("open_access") or {}
    pdf_url = oa_info.get("oa_url")
    
    # Try primary location PDF
    if not pdf_url:
        pdf_url = primary_loc.get("pdf_url")
    
    # Fallback to DOI or landing page
    if not pdf_url and doi:
        pdf_url = f"https://doi.org/{doi}"
    if not pdf_url:
        pdf_url = primary_loc.get("landing_page_url") or w.get("id")

    return Paper(
        source="openalex",
        source_id=(w.get("id") or "").rsplit("/", 1)[-1],
        title=title,
        authors=authors,
        abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
        year=w.get("publication_year"),
        venue=venue,
        venue_type=venue_type,
        doi=doi,
        url=pdf_url,
        pdf_url=pdf_url if oa_info.get("is_oa") else None,
        citations=w.get("cited_by_count"),
        is_open_access=oa_info.get("is_oa"),
        type=w.get("type"),
        publisher=publisher,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search OpenAlex. filters contoh: {'type': 'article', 'is_paratext': 'false'}"""
    rl = RateLimiter(0.12)
    per_page = min(limit, 50)
    fetched = 0
    cursor = "*"

    filter_parts = []
    if filters:
        if filters.get("require_abstract", False):
            filter_parts.append("has_abstract:true")
        for k, v in filters.items():
            if k == "require_abstract":
                continue
            filter_parts.append(f"{k}:{v}")
    filter_str = ",".join(filter_parts)

    while fetched < limit:
        rl.wait()
        params = {
            "search": query,
            "per_page": min(per_page, limit - fetched),
            "cursor": cursor,
            "sort": "relevance_score:desc",
            "mailto": os.getenv("SLR_CONTACT_EMAIL") or "research@example.com",
        }
        if filter_str:
            params["filter"] = filter_str
        api_key = os.getenv("OPENALEX_API_KEY")
        if api_key:
            params["api_key"] = api_key
        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        results = data.get("results", [])
        if not results:
            return
        for w in results:
            paper = _parse_work(w)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not cursor:
            return
