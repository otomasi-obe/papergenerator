"""Fetcher untuk Lens.org API - https://api.lens.org/scholarly"""

import logging
import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_post_json, env_required
from ..paper import Paper

BASE = "https://api.lens.org/scholarly/search"

log = logging.getLogger(__name__)


def _parse(item: dict) -> Paper | None:
    title = item.get("title")
    if not title:
        return None
    
    authors = []
    for a in item.get("authors", []):
        name = a.get("name")
        if name:
            authors.append(name)
    
    # Extract year from publication date
    year = None
    pub_date = item.get("publication_date")
    if pub_date and isinstance(pub_date, str):
        try:
            year = int(pub_date.split("-")[0])
        except (ValueError, IndexError):
            pass
    
    # Get DOI
    doi = item.get("doi")
    
    # Get PDF URL if available
    pdf_url = None
    urls = item.get("urls", [])
    for url_obj in urls:
        if isinstance(url_obj, dict):
            url = url_obj.get("url", "")
            if "pdf" in url.lower():
                pdf_url = url
                break
    
    # Landing page
    url = item.get("url")
    if not url and doi:
        url = f"https://doi.org/{doi}"
    
    # Extract venue info
    venue = None
    publisher = None
    source = item.get("source")
    if isinstance(source, dict):
        venue = source.get("title")
        publisher = source.get("publisher")
    
    return Paper(
        source="lens",
        source_id=str(item.get("lens_id", "")),
        title=title,
        authors=authors,
        abstract=item.get("abstract"),
        year=year,
        venue=venue,
        venue_type=None,
        doi=doi,
        url=url,
        pdf_url=pdf_url,
        citations=item.get("citation_count"),
        is_open_access=item.get("open_access", {}).get("is_oa") if isinstance(item.get("open_access"), dict) else None,
        type=item.get("type"),
        publisher=publisher,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    if not env_required(log, "LENS_API_KEY", "lens"):
        return
    api_key = os.getenv("LENS_API_KEY")
    
    rl = RateLimiter(1.0)  # Conservative rate limiting
    fetched = 0
    offset = 0
    page_size = min(limit, 50)
    
    while fetched < limit:
        rl.wait()
        
        body = {
            "query": {
                "match": {
                    "title.abstract": query
                }
            },
            "size": min(page_size, limit - fetched),
            "from": offset,
            "sort": [],
        }
        
        # Add filters if provided
        if filters:
            if "year" in filters:
                body["query"] = {
                    "bool": {
                        "must": [
                            {"match": {"title.abstract": query}},
                            {"term": {"year_published": filters["year"]}}
                        ]
                    }
                }
        
        headers = {"Authorization": f"Bearer {api_key}"}
        data = fetch_post_json(client, BASE, json_body=body, headers=headers)
        
        if not data:
            return
        
        results = data.get("results", [])
        if not results:
            return
        
        for item in results:
            paper = _parse(item)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        
        # Lens uses offset pagination
        total = data.get("total", 0)
        offset += len(results)
        if offset >= total:
            return
