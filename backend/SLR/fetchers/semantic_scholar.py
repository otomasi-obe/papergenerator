"""Fetcher untuk Semantic Scholar - https://api.semanticscholar.org/graph/v1"""
import os
from typing import Iterable
from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://api.semanticscholar.org/graph/v1/paper/search"

FIELDS = ",".join([
    "paperId", "externalIds", "title", "abstract", "year",
    "authors", "venue", "publicationVenue", "publicationTypes",
    "citationCount", "openAccessPdf", "publicationDate",
])


def _parse(p: dict) -> Paper | None:
    title = p.get("title")
    if not title:
        return None

    authors = [a.get("name") for a in (p.get("authors") or []) if a.get("name")]
    ext = p.get("externalIds") or {}
    doi = ext.get("DOI")
    pub_venue = p.get("publicationVenue") or {}

    venue_type = None
    pub_types = p.get("publicationTypes") or []
    if pub_types:
        venue_type = pub_types[0]

    return Paper(
        source="semantic_scholar",
        source_id=p.get("paperId", ""),
        title=title,
        authors=authors,
        abstract=p.get("abstract"),
        year=p.get("year"),
        venue=p.get("venue") or pub_venue.get("name"),
        venue_type=pub_venue.get("type") or venue_type,
        doi=doi,
        url=f"https://www.semanticscholar.org/paper/{p.get('paperId')}" if p.get("paperId") else None,
        citations=p.get("citationCount"),
        is_open_access=bool(p.get("openAccessPdf")),
        type=venue_type,
        publisher=pub_venue.get("publisher"),
    )


def search(client, query: str, limit: int = 25,
           filters: dict | None = None) -> Iterable[Paper]:
    """Free tier rate limit ketat (~1 req/sec). Set S2_API_KEY untuk lebih tinggi."""
    api_key = os.getenv("S2_API_KEY")
    rl = RateLimiter(0.1 if api_key else 1.1)
    headers = {"x-api-key": api_key} if api_key else None
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
        }
        if filters:
            if "year" in filters:
                params["year"] = filters["year"]
            if "venue" in filters:
                params["venue"] = filters["venue"]

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
