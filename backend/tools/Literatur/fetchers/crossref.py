"""Fetcher untuk Crossref - https://api.crossref.org"""

import html
import os
import re
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://api.crossref.org/works"


def _parse_item(item: dict) -> Paper | None:
    title_list = item.get("title") or []
    title = title_list[0] if title_list else None
    if not title:
        return None

    authors = []
    for a in item.get("author", []) or []:
        given = a.get("given", "")
        family = a.get("family", "")
        full = f"{given} {family}".strip()
        if full:
            authors.append(full)

    year = None
    issued = (item.get("issued") or {}).get("date-parts")
    if issued and issued[0]:
        year = issued[0][0]

    venue_list = item.get("container-title") or []
    venue = venue_list[0] if venue_list else None

    abstract = item.get("abstract")
    if abstract:
        # Crossref abstract sering dibungkus tag JATS
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        abstract = html.unescape(abstract)

    # Build PDF URL: prioritize link array, then DOI
    doi = item.get("DOI")
    pdf_url = None
    
    # Check for direct PDF links in link array
    links = item.get("link", [])
    for link in links:
        if link.get("content-type") == "application/pdf":
            pdf_url = link.get("URL")
            break
    
    # Fallback to DOI resolver
    if not pdf_url and doi:
        pdf_url = f"https://doi.org/{doi}"
    
    # Last resort: use URL field
    if not pdf_url:
        pdf_url = item.get("URL")

    return Paper(
        source="crossref",
        source_id=doi or "",
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=venue,
        venue_type=item.get("type"),
        doi=doi,
        url=pdf_url,
        citations=item.get("is-referenced-by-count"),
        type=item.get("type"),
        publisher=item.get("publisher"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Filter contoh: {'type': 'journal-article', 'from-pub-date': '2020'}"""
    rl = RateLimiter(0.25)
    per_page = min(limit, 100)
    fetched = 0
    offset = 0

    filter_parts = []
    if filters:
        for k, v in filters.items():
            filter_parts.append(f"{k}:{v}")

    while fetched < limit:
        rl.wait()
        params = {
            "query": query,
            "rows": min(per_page, limit - fetched),
            "offset": offset,
            "sort": "relevance",
            "order": "desc",
            "mailto": os.getenv("SLR_CONTACT_EMAIL") or "research@example.com",
            "select": "DOI,title,author,issued,container-title,abstract,type,publisher,URL,is-referenced-by-count",
        }
        if filter_parts:
            params["filter"] = ",".join(filter_parts)

        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        items = ((data.get("message") or {}).get("items")) or []
        if not items:
            return
        for item in items:
            paper = _parse_item(item)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        offset += len(items)
        if len(items) < per_page:
            return
