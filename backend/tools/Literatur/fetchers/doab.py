"""Fetcher untuk DOAB — Directory of Open Access Books.

DOAB catalogs 80,000+ peer-reviewed OA books.
Strategy: search via OpenAlex with type:book filter (covers DOAB content)
since DOAB REST API is slow/unreliable.

Fallback: OAI-PMH (very slow, ~2min for 25 books) — disabled by default.
"""

import logging
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

log = logging.getLogger(__name__)

DOAB_REST = "https://directory.doabooks.org/rest/search"
OPENALEX_BASE = "https://api.openalex.org/works"


def _parse_openalex_book(w: dict) -> Paper | None:
    title = w.get("title") or w.get("display_name")
    if not title:
        return None

    authors = []
    for a in w.get("authorships", []) or []:
        author = a.get("author") or {}
        name = author.get("display_name")
        if name:
            authors.append(name)

    doi = None
    raw_doi = w.get("doi")
    if raw_doi:
        doi = raw_doi.split("doi.org/")[-1].strip()

    oa_info = w.get("open_access") or {}
    pdf_url = oa_info.get("oa_url")
    primary_loc = w.get("primary_location") or {}
    landing = (f"https://doi.org/{doi}" if doi else
               primary_loc.get("landing_page_url") or w.get("id"))

    return Paper(
        source="doab",
        source_id=(w.get("id") or "").rsplit("/", 1)[-1],
        title=title,
        authors=authors,
        abstract=None,  # inverted index not expanded here
        year=w.get("publication_year"),
        venue=None,
        venue_type="book",
        doi=doi,
        url=landing,
        pdf_url=pdf_url or landing,
        is_open_access=oa_info.get("is_oa", True),
        type="book",
        publisher=(primary_loc.get("source") or {}).get("host_organization_name"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search OA books via OpenAlex (type:book, is_oa:true) — proxies DOAB content."""
    import os
    rl = RateLimiter(1.0)
    per_page = min(limit, 50)
    fetched = 0
    cursor = "*"

    while fetched < limit:
        rl.wait()
        params = {
            "search": query,
            "filter": "type:book,is_oa:true",
            "per_page": min(per_page, limit - fetched),
            "cursor": cursor,
            "sort": "relevance_score:desc",
            "mailto": os.getenv("SLR_CONTACT_EMAIL") or "research@example.com",
            "select": "id,doi,title,display_name,publication_year,authorships,open_access,primary_location",
        }
        api_key = os.getenv("OPENALEX_API_KEY")
        if api_key:
            params["api_key"] = api_key

        data = fetch_json(client, OPENALEX_BASE, params=params)
        if not data:
            return

        results = data.get("results", [])
        if not results:
            return

        for w in results:
            paper = _parse_openalex_book(w)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        cursor = (data.get("meta") or {}).get("next_cursor")
        if not cursor:
            return
