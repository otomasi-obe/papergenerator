"""ResearchGate fetcher menggunakan MCP Playwright untuk bypass Cloudflare.

Pendekatan hybrid:
- curl_cffi (primary, existing researchgate.py) — TLS impersonation, cepat
- MCP Playwright (ini) — Full browser fallback, 98% bypass

Usage:
    from tools.Literatur.fetchers.researchgate_mcp import search

    # Sync interface — kompatibel dengan ALL registry
    papers = list(search(None, "machine learning", limit=10))
"""

from __future__ import annotations

import logging
import re
from typing import Iterable
from urllib.parse import quote

from bs4 import BeautifulSoup

from .mcp_client import PlaywrightMCPClient, _run_async
from ..http_client import RateLimiter, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://www.researchgate.net"
SEARCH_URL = f"{BASE}/search/publication"

_RL = RateLimiter(2.0)


# ══════════════════════════════════════════════════════════════════════════════
# Type normalization (mirror dari researchgate.py)
# ══════════════════════════════════════════════════════════════════════════════

_TYPE_MAP = {
    "journal article": "journal-article",
    "conference paper": "conference-paper",
    "book": "book",
    "book chapter": "book-chapter",
    "thesis": "thesis",
    "preprint": "preprint",
    "patent": "patent",
    "dataset": "dataset",
    "presentation": "presentation",
    "article": "journal-article",
}


def _normalize_type(raw: str | None) -> str:
    """Normalize RG publication badge ke tipe standar."""
    if not raw:
        return "article"
    return _TYPE_MAP.get(raw.strip().lower(), "article")


# ══════════════════════════════════════════════════════════════════════════════
# Parser
# ══════════════════════════════════════════════════════════════════════════════

def _parse_card(card_elem) -> Paper | None:
    """Parse single publication card menjadi Paper object."""
    try:
        # Title
        title_elem = card_elem.select_one(
            ".nova-legacy-v-publication-item__title"
        )
        if not title_elem:
            return None
        title = strip_html(title_elem.get_text())
        if not title:
            return None

        # URL (for source_id)
        url = None
        link_elem = title_elem.find("a")
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if href.startswith("/"):
                url = BASE + href
            elif href.startswith("http"):
                url = href

        # source_id from URL or title fallback
        source_id = ""
        if url:
            source_id = url.rstrip("/").split("/")[-1].split("?")[0]
        if not source_id:
            source_id = re.sub(r"[^a-zA-Z0-9]+", "_", title[:50])

        # Authors — scope to <a itemprop="author"> for precision
        authors = []
        author_links = card_elem.find_all(
            "a", class_="nova-legacy-v-person-inline-item"
        )
        for author_link in author_links:
            name_span = author_link.find(
                "span", class_="nova-legacy-v-person-inline-item__fullname"
            )
            if name_span:
                name = strip_html(name_span.get_text())
                if name:
                    authors.append(name)
        # Fallback: broader selector
        if not authors:
            for elem in card_elem.select(".nova-legacy-v-person-inline-item__fullname"):
                name = strip_html(elem.get_text())
                if name:
                    authors.append(name)

        # Type (Journal Article, Conference Paper, etc)
        pub_type = None
        type_elem = card_elem.select_one(
            ".nova-legacy-v-publication-item__badge"
        )
        if type_elem:
            pub_type = strip_html(type_elem.get_text())

        # Metadata: date, DOI
        year = None
        doi = None

        meta_items = card_elem.select(
            ".nova-legacy-v-publication-item__meta-data-item"
        )
        for meta in meta_items:
            text = meta.get_text().strip()

            # Date
            if re.search(
                r"(January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+\d{4}",
                text,
            ):
                year_match = re.search(r"\d{4}", text)
                if year_match:
                    year = int(year_match.group())

            # DOI
            if "DOI:" in text or "doi.org" in text:
                doi_match = re.search(r"10\.\d{4,}/[^\s]+", text)
                if doi_match:
                    doi = doi_match.group()

        # Venue type from publication type
        normalized_type = _normalize_type(pub_type)
        venue_type = None
        if normalized_type == "journal-article":
            venue_type = "journal"
        elif normalized_type == "conference-paper":
            venue_type = "conference"
        elif normalized_type in ("book", "book-chapter"):
            venue_type = "book"
        elif normalized_type == "preprint":
            venue_type = "repository"

        return Paper(
            source="researchgate",
            source_id=source_id,
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            url=url,
            type=normalized_type,
            venue_type=venue_type,
        )

    except Exception as e:
        log.warning("researchgate_mcp: parse card error: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Async search via MCP
# ══════════════════════════════════════════════════════════════════════════════

async def search_async(query: str, limit: int = 10) -> list[Paper]:
    """Search ResearchGate via MCP Playwright (async)."""
    url = f"{SEARCH_URL}?q={quote(query, safe='')}"

    try:
        async with PlaywrightMCPClient() as client:
            result = await client.fetch_page(
                url,
                wait_selector=".nova-legacy-c-card__body--spacing-inherit",
                timeout=30,
            )

            if not result.get("success"):
                log.error(
                    "researchgate_mcp: fetch failed: %s", result.get("error")
                )
                return []

            html = result.get("html", "")
            if len(html) < 10000:
                log.warning(
                    "researchgate_mcp: suspicious short HTML (%d bytes)",
                    len(html),
                )
                return []

            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(
                ".nova-legacy-c-card__body--spacing-inherit"
            )

            papers = []
            for card in cards[:limit]:
                paper = _parse_card(card)
                if paper:
                    papers.append(paper)

            log.info(
                "researchgate_mcp: extracted %d papers from %d cards",
                len(papers),
                len(cards),
            )
            return papers

    except Exception as e:
        log.error("researchgate_mcp: search error: %s", e)
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Sync interface — kompatibel dengan fetcher framework (ALL registry)
# ══════════════════════════════════════════════════════════════════════════════

def search(
    client, query: str, limit: int = 10, filters: dict | None = None
) -> Iterable[Paper]:
    """Search ResearchGate via MCP Playwright (sync wrapper).

    Args:
        client: Ignored (untuk kompatibilitas interface).
        query: Search query.
        limit: Max results.
        filters: Ignored (reserved for future use).

    Yields:
        Paper objects.
    """
    _RL.wait()

    papers = _run_async(search_async(query, limit))

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
