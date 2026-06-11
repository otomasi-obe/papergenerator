"""Fetcher untuk CORE API - https://api.core.ac.uk/v3"""

import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_post_json
from ..paper import Paper

BASE = "https://api.core.ac.uk/v3/search/works"


def _parse(item: dict) -> Paper | None:
    title = item.get("title")
    if not title:
        return None
    
    authors = []
    for a in item.get("authors", []):
        name = a.get("name")
        if name:
            authors.append(name)
    
    # CORE returns year as string, need to convert
    year = None
    year_str = item.get("yearPublished")
    if year_str:
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            pass
    
    # Extract DOI from identifiers
    doi = None
    identifiers = item.get("identifiers", {})
    if isinstance(identifiers, dict):
        doi = identifiers.get("doi")
    
    # Get PDF URL - CORE specializes in open access
    pdf_url = item.get("downloadUrl") or item.get("sourceFulltextUrls")
    if isinstance(pdf_url, list):
        pdf_url = pdf_url[0] if pdf_url else None
    
    # Landing page
    url = item.get("urls", [None])[0] if item.get("urls") else None
    if not url and doi:
        url = f"https://doi.org/{doi}"
    
    return Paper(
        source="core",
        source_id=str(item.get("id", "")),
        title=title,
        authors=authors,
        abstract=item.get("abstract"),
        year=year,
        venue=item.get("publisher"),
        venue_type=None,
        doi=doi,
        url=url,
        pdf_url=pdf_url,
        citations=None,  # CORE doesn't provide citation counts
        is_open_access=True,  # CORE only indexes OA content
        type=None,
        publisher=item.get("publisher"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search CORE. Requires CORE_API_KEY environment variable."""
    api_key = os.getenv("CORE_API_KEY")
    if not api_key:
        return
    
    rl = RateLimiter(1.0)  # Conservative rate limiting
    fetched = 0
    page = 1
    page_size = min(limit, 100)
    
    while fetched < limit:
        rl.wait()
        
        body = {
            "q": query,
            "limit": min(page_size, limit - fetched),
            "offset": fetched,
        }
        
        # Add filters if provided
        if filters:
            if "year" in filters:
                body["year"] = filters["year"]
            if "type" in filters:
                body["type"] = filters["type"]
        
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
        
        # CORE uses offset pagination
        total = data.get("totalHits", 0)
        if fetched >= total:
            return
