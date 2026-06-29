"""Fetcher untuk Dimensions API - https://app.dimensions.ai/api"""

import logging
import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_post_json, env_required
from ..paper import Paper

BASE = "https://app.dimensions.ai/api/dsl/v2"


def _parse(item: dict) -> Paper | None:
    title = item.get("title")
    if not title:
        return None
    
    # Dimensions returns authors as list of strings or dicts
    authors = []
    raw_authors = item.get("authors", [])
    for a in raw_authors:
        if isinstance(a, str):
            authors.append(a)
        elif isinstance(a, dict):
            name = a.get("name") or f"{a.get('first_name', '')} {a.get('last_name', '')}".strip()
            if name:
                authors.append(name)
    
    # Extract year
    year = item.get("year")
    
    # Get DOI
    doi = item.get("doi")
    
    # PDF URL (Dimensions provides links)
    pdf_url = item.get("linkout")
    
    # Landing page
    url = doi and f"https://doi.org/{doi}"
    
    # Venue info
    venue = None
    venue_type = None
    journal = item.get("journal")
    if isinstance(journal, dict):
        venue = journal.get("title")
        venue_type = "journal"
    
    publisher = None
    publisher_info = item.get("publisher")
    if isinstance(publisher_info, dict):
        publisher = publisher_info.get("name")
    elif isinstance(publisher_info, str):
        publisher = publisher_info
    
    return Paper(
        source="dimensions",
        source_id=str(item.get("id", "")),
        title=title,
        authors=authors,
        abstract=item.get("abstract"),
        year=year,
        venue=venue,
        venue_type=venue_type,
        doi=doi,
        url=url,
        pdf_url=pdf_url,
        citations=item.get("times_cited"),
        is_open_access=item.get("open_access", []).__contains__("oa_all") if item.get("open_access") else None,
        type=item.get("type"),
        publisher=publisher,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    if not env_required(log, "DIMENSIONS_API_KEY", "dimensions"):
        return
    api_key = os.getenv("DIMENSIONS_API_KEY")
    
    rl = RateLimiter(1.0)  # Conservative rate limiting
    fetched = 0
    skip = 0
    page_size = min(limit, 100)
    
    while fetched < limit:
        rl.wait()
        
        # Build DSL query
        dsl_query = f'search publications for "{query}"'
        
        # Add filters
        filter_parts = []
        if filters:
            if "year" in filters:
                filter_parts.append(f'where year = {filters["year"]}')
            if "type" in filters:
                filter_parts.append(f'where type = "{filters["type"]}"')
        
        if filter_parts:
            dsl_query += " " + " ".join(filter_parts)
        
        dsl_query += f" return publications[all] limit {min(page_size, limit - fetched)} skip {skip}"
        
        body = {"query": dsl_query}
        headers = {"Authorization": f"JWT {api_key}"}
        
        data = fetch_post_json(client, BASE, json_body=body, headers=headers)
        
        if not data:
            return
        
        results = data.get("publications", [])
        if not results:
            return
        
        for item in results:
            paper = _parse(item)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        
        # Dimensions uses skip/limit pagination
        total = data.get("_stats", {}).get("total_count", 0)
        skip += len(results)
        if skip >= total:
            return
