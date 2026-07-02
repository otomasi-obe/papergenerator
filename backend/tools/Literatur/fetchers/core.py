"""Fetcher untuk CORE API - https://api.core.ac.uk/v3"""

import logging
import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from ..http_client import RateLimiter, fetch_post_json, env_required
from ..paper import Paper

_ENV_PATH = Path(__file__).resolve().parents[4] / ".env"
load_dotenv(_ENV_PATH, override=False)

BASE = "https://api.core.ac.uk/v3/search/works"

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
    
    # CORE returns year as string, need to convert
    year = None
    year_str = item.get("yearPublished")
    if year_str:
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            pass
    
    # Extract DOI from identifiers (CORE returns a LIST of {type, identifier})
    doi = item.get("doi")
    identifiers = item.get("identifiers")
    if not doi and isinstance(identifiers, list):
        for ident in identifiers:
            if isinstance(ident, dict) and ident.get("type") == "doi":
                doi = ident.get("identifier")
                break
    elif not doi and isinstance(identifiers, dict):
        doi = identifiers.get("doi")
    
    # Get PDF URL - CORE specializes in open access
    pdf_url = item.get("downloadUrl") or item.get("sourceFulltextUrls")
    if isinstance(pdf_url, list):
        pdf_url = pdf_url[0] if pdf_url else None
    
    # Landing page — CORE v3 uses "links" array with type/url
    url = None
    links = item.get("links", [])
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict) and link.get("type") == "display":
                url = link.get("url")
                break
    if not url:
        url = item.get("urls", [None])[0] if item.get("urls") else None
    if not url and doi:
        url = f"https://doi.org/{doi}"

    # CORE venue: use document source if available, not publisher
    raw_source = item.get("source", {}).get("identifier") if isinstance(item.get("source"), dict) else None
    venue = raw_source or item.get("documentType")

    # Normalize venue_type and type
    _core_type_map = {
        "journal article": "journal-article",
        "conference paper": "conference-paper",
        "book chapter": "book",
        "book": "book",
        "thesis": "book",
        "dataset": "dataset",
        "preprint": "preprint",
        "report": "journal-article",
    }
    doc_type = item.get("documentType", "").lower() if item.get("documentType") else None
    normalized_type = _core_type_map.get(doc_type, doc_type) if doc_type else None
    venue_type = "repository"  # CORE is a repository aggregator

    return Paper(
        source="core",
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
        citations=None,  # CORE doesn't provide citation counts
        is_open_access=True,  # CORE only indexes OA content
        type=normalized_type,
        publisher=item.get("publisher"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    if not env_required(log, "CORE_API_KEY", "core"):
        return
    api_key = os.getenv("CORE_API_KEY")
    
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
            "sort": [],
        }
        
        # Add filters if provided
        if filters:
            if "year" in filters:
                body["year"] = filters["year"]
            if "type" in filters:
                body["type"] = filters["type"]
        
        headers = {"Authorization": f"Bearer {api_key}", "User-Agent": "Hermes/1.0 (research)", "Accept": "application/json"}
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
