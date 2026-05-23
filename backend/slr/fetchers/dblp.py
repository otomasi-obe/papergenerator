"""Fetcher untuk DBLP - https://dblp.org/search/publ/api (CS-focused)"""
from typing import Iterable
from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://dblp.org/search/publ/api"


def _parse_hit(hit: dict) -> Paper | None:
    info = hit.get("info") or {}
    title = info.get("title")
    if not title:
        return None
    title = title.rstrip(".").strip()

    authors_block = (info.get("authors") or {}).get("author") or []
    if isinstance(authors_block, dict):
        authors_block = [authors_block]
    authors = []
    for a in authors_block:
        if isinstance(a, dict):
            name = a.get("text")
            if name:
                authors.append(name)
        elif isinstance(a, str):
            authors.append(a)

    year = None
    if info.get("year"):
        try:
            year = int(info["year"])
        except (ValueError, TypeError):
            pass

    venue = info.get("venue")
    pub_type = info.get("type")
    venue_type = None
    if pub_type:
        pl = pub_type.lower()
        if "conference" in pl or "workshop" in pl:
            venue_type = "conference"
        elif "journal" in pl:
            venue_type = "journal"

    return Paper(
        source="dblp",
        source_id=hit.get("@id") or info.get("key", ""),
        title=title,
        authors=authors,
        abstract=None,  # DBLP tidak menyediakan abstract
        year=year,
        venue=venue,
        venue_type=venue_type,
        doi=info.get("doi"),
        url=info.get("url") or info.get("ee"),
        type=pub_type,
    )


def search(client, query: str, limit: int = 25,
           filters: dict | None = None) -> Iterable[Paper]:
    rl = RateLimiter(0.5)
    per_page = min(limit, 1000)
    fetched = 0
    offset = 0

    while fetched < limit:
        rl.wait()
        params = {
            "q": query,
            "format": "json",
            "h": min(per_page, limit - fetched),
            "f": offset,
        }
        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        result = (data.get("result") or {})
        hits_block = (result.get("hits") or {})
        hits = hits_block.get("hit") or []
        if not hits:
            return
        for hit in hits:
            paper = _parse_hit(hit)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        total = int(hits_block.get("@total", 0))
        offset += len(hits)
        if offset >= total:
            return
