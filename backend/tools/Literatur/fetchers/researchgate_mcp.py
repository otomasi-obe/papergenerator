"""ResearchGate fetcher menggunakan MCP Playwright untuk bypass Cloudflare.

Pendekatan:
- curl_cffi (primary, existing) — TLS impersonation, cepat, low resource
- MCP Playwright (fallback) — Full browser, 100% bypass, heavy resource

Usage:
    from tools.Literatur.fetchers.researchgate_mcp import search

    papers = list(search(None, "machine learning", limit=10))
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Iterable
from urllib.parse import quote

from bs4 import BeautifulSoup

from .mcp_client import PlaywrightMCPClient
from ..http_client import RateLimiter, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://www.researchgate.net"
SEARCH_URL = f"{BASE}/search/publication"

_RL = RateLimiter(2.0)


# ══════════════════════════════════════════════════════════════════════════════
# Parser (reuse dari researchgate.py)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_card(card_elem) -> Paper | None:
    """Parse single publication card menjadi Paper object."""
    try:
        # Title
        title_elem = card_elem.select_one(".nova-legacy-v-publication-item__title")
        if not title_elem:
            return None
        title = strip_html(title_elem.get_text())

        # Authors
        authors = []
        author_elems = card_elem.select(".nova-legacy-v-person-inline-item__fullname")
        for author_elem in author_elems:
            name = strip_html(author_elem.get_text())
            if name:
                authors.append(name)

        # Type (Journal Article, Conference Paper, etc)
        pub_type = None
        type_elem = card_elem.select_one(".nova-legacy-v-publication-item__badge")
        if type_elem:
            pub_type = strip_html(type_elem.get_text())

        # Metadata: date, DOI, ISBN, etc
        year = None
        doi = None
        isbn = None
        
        meta_items = card_elem.select(".nova-legacy-v-publication-item__meta-data-item")
        for meta in meta_items:
            text = meta.get_text().strip()
            
            # Date (e.g., "September 2023")
            if re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}", text):
                year_match = re.search(r"\d{4}", text)
                if year_match:
                    year = int(year_match.group())
            
            # DOI
            if "DOI:" in text or "doi.org" in text:
                doi_match = re.search(r"10\.\d{4,}/[^\s]+", text)
                if doi_match:
                    doi = doi_match.group()
            
            # ISBN
            if "ISBN:" in text:
                isbn_match = re.search(r"ISBN:\s*([\d\-]+)", text)
                if isbn_match:
                    isbn = isbn_match.group(1)

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            isbn=isbn,
            type=pub_type or "Unknown",
            source="ResearchGate (MCP Playwright)",
        )

    except Exception as e:
        log.warning("researchgate_mcp: parse card error: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Async search via MCP
# ══════════════════════════════════════════════════════════════════════════════

async def search_async(query: str, limit: int = 10) -> list[Paper]:
    """Search ResearchGate via MCP Playwright (async).
    
    Args:
        query: Search query
        limit: Max results
        
    Returns:
        List of Paper objects
    """
    url = f"{SEARCH_URL}?q={quote(query)}"
    
    try:
        async with PlaywrightMCPClient() as client:
            result = await client.fetch_page(
                url,
                wait_selector=".nova-legacy-c-card__body",
                timeout=30
            )
            
            if not result.get("success"):
                log.error("researchgate_mcp: fetch failed: %s", result.get("error"))
                return []
            
            html = result.get("html", "")
            if len(html) < 10000:
                log.warning("researchgate_mcp: suspicious short HTML (%d bytes)", len(html))
                return []
            
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(".nova-legacy-c-card__body--spacing-inherit")
            
            papers = []
            for card in cards[:limit]:
                paper = _parse_card(card)
                if paper:
                    papers.append(paper)
            
            log.info("researchgate_mcp: extracted %d papers from %d cards", len(papers), len(cards))
            return papers

    except Exception as e:
        log.error("researchgate_mcp: search error: %s", e)
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Sync interface (untuk kompatibilitas dengan fetcher framework existing)
# ══════════════════════════════════════════════════════════════════════════════

def search(client, query: str, limit: int = 10) -> Iterable[Paper]:
    """Search ResearchGate via MCP Playwright (sync wrapper).
    
    Args:
        client: Ignored (untuk kompatibilitas interface)
        query: Search query
        limit: Max results
        
    Yields:
        Paper objects
    """
    _RL.wait()
    
    papers = asyncio.run(search_async(query, limit))
    
    for paper in papers:
        yield paper


# ══════════════════════════════════════════════════════════════════════════════
# CLI Testing
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    query = sys.argv[1] if len(sys.argv) > 1 else "robot"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    print(f"\n🔍 Searching ResearchGate (MCP Playwright): '{query}' (limit={limit})\n")
    
    papers = list(search(None, query, limit))
    
    print(f"\n✅ Found {len(papers)} papers:\n")
    for i, paper in enumerate(papers, 1):
        print(f"{i}. {paper.title}")
        print(f"   Authors: {', '.join(paper.authors[:3])}")
        if paper.year:
            print(f"   Year: {paper.year}")
        if paper.doi:
            print(f"   DOI: {paper.doi}")
        print(f"   Type: {paper.type}")
        print()
