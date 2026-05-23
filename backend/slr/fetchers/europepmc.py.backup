"""Fetcher untuk Europe PMC - https://www.ebi.ac.uk/europepmc/webservices/rest"""
from typing import Iterable
from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _parse(item: dict) -> Paper | None:
    title = item.get("title")
    if not title:
        return None
    title = title.rstrip(".").strip()

    authors = []
    author_str = item.get("authorString")
    if author_str:
        authors = [a.strip() for a in author_str.split(",") if a.strip()]

    year = None
    if item.get("pubYear"):
        try:
            year = int(item["pubYear"])
        except (ValueError, TypeError):
            pass

    return Paper(
        source="europepmc",
        source_id=item.get("id", ""),
        title=title,
        authors=authors,
        abstract=item.get("abstractText"),
        year=year,
        venue=item.get("journalTitle"),
        venue_type="journal" if item.get("journalTitle") else None,
        doi=item.get("doi"),
        url=f"https://europepmc.org/article/{item.get('source')}/{item.get('id')}" if item.get("id") else None,
        citations=item.get("citedByCount"),
        is_open_access=item.get("isOpenAccess") == "Y",
        type=item.get("pubType"),
    )


def search(client, query: str, limit: int = 25,
           filters: dict | None = None) -> Iterable[Paper]:
    rl = RateLimiter(0.3)
    per_page = min(limit, 100)
    fetched = 0
    cursor = "*"

    full_query = query
    if filters:
        if filters.get("open_access"):
            full_query += " AND OPEN_ACCESS:Y"
        if filters.get("has_abstract"):
            full_query += " AND HAS_ABSTRACT:Y"

    while fetched < limit:
        rl.wait()
        params = {
            "query": full_query,
            "format": "json",
            "pageSize": min(per_page, limit - fetched),
            "cursorMark": cursor,
            "resultType": "core",
        }
        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        results = ((data.get("resultList") or {}).get("result")) or []
        if not results:
            return
        for r in results:
            paper = _parse(r)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        next_cursor = data.get("nextCursorMark")
        if not next_cursor or next_cursor == cursor:
            return
        if cursor != "*" and next_cursor == cursor:
            import logging
            logging.getLogger(__name__).warning("europepmc cursor stuck at %s, breaking", cursor)
            return
        cursor = next_cursor
