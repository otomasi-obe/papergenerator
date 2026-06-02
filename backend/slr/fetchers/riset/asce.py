"""Fetcher untuk ASCE Library - https://ascelibrary.org

American Society of Civil Engineers (ASCE) Library.
Web scraping implementation using Playwright to bypass Cloudflare protection.
"""

import asyncio
import logging
from typing import Iterable
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

from ..paper import Paper

logger = logging.getLogger(__name__)


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Search ASCE Library using Playwright to bypass Cloudflare.

    Args:
        client: HTTP client (not used, Playwright manages its own browser)
        query: Search query string
        limit: Maximum number of results to return
        filters: Optional filters (year_start, year_end, content_type)

    Yields:
        Paper objects with metadata from ASCE Library
    """
    # Run async scraping in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        papers = loop.run_until_complete(_async_search(query, limit, filters))
        for paper in papers:
            yield paper
    finally:
        loop.close()


async def _async_search(query: str, limit: int, filters: dict | None) -> list[Paper]:
    """Async implementation of ASCE search using Playwright"""

    base_url = "https://ascelibrary.org"
    search_url = f"{base_url}/action/doSearch"

    # Build search parameters
    params = {
        "AllField": query,
        "pageSize": min(limit, 50),
        "startPage": 0,
    }

    # Add filters if provided
    if filters:
        if "year_start" in filters:
            params["AfterYear"] = filters["year_start"]
        if "year_end" in filters:
            params["BeforeYear"] = filters["year_end"]
        if "content_type" in filters:
            params["ContentItemType"] = filters["content_type"]

    # Build full URL with parameters
    param_str = "&".join([f"{k}={quote_plus(str(v))}" for k, v in params.items()])
    full_url = f"{search_url}?{param_str}"

    logger.info(f"Searching ASCE Library for: {query}")

    papers = []

    async with async_playwright() as p:
        try:
            # Launch browser in headless mode
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )

            # Create context with realistic user agent
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )

            page = await context.new_page()

            # Navigate to search page
            logger.info(f"Navigating to: {full_url}")
            await page.goto(full_url, wait_until="domcontentloaded", timeout=60000)

            # Wait for Cloudflare challenge to complete
            logger.info("Waiting for Cloudflare challenge...")
            await page.wait_for_timeout(5000)

            # Check if we're past Cloudflare
            title = await page.title()
            if "Just a moment" in title or "Cloudflare" in title:
                logger.info("Still on Cloudflare page, waiting longer...")
                await page.wait_for_timeout(10000)

            # Wait for search results to load
            try:
                # Wait for any of these selectors that might contain results
                await page.wait_for_selector(
                    "div.item__body, article.item, div.search-result, div.card",
                    timeout=15000,
                )
            except PlaywrightTimeout:
                logger.warning("Timeout waiting for search results")

            # Get page content
            content = await page.content()

            # Parse with BeautifulSoup
            soup = BeautifulSoup(content, "html.parser")

            # Try multiple selectors to find paper items
            paper_items = []
            selectors = [
                "div.item__body",
                "article.item",
                "div.search-result",
                "div.card-body",
                "li.search-result",
            ]

            for selector in selectors:
                items = soup.select(selector)
                if items:
                    logger.info(f"Found {len(items)} items with selector: {selector}")
                    paper_items = items
                    break

            if not paper_items:
                logger.warning("No paper items found with any selector")
                # Save HTML for debugging
                debug_path = "/tmp/asce_debug.html"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"Saved HTML to {debug_path} for debugging")
                return papers

            # Parse each paper item
            for item in paper_items[:limit]:
                try:
                    paper = _parse_paper_item(item, base_url)
                    if paper:
                        papers.append(paper)
                except Exception as e:
                    logger.warning(f"Error parsing paper item: {e}")
                    continue

            logger.info(f"Successfully scraped {len(papers)} papers from ASCE Library")

        except Exception as e:
            logger.error(f"Error during Playwright scraping: {e}")
        finally:
            await browser.close()

    return papers


def _parse_paper_item(item, base_url: str) -> Paper | None:
    """
    Parse a single paper item from ASCE search results.

    Args:
        item: BeautifulSoup element containing paper data
        base_url: Base URL for constructing full URLs

    Returns:
        Paper object or None if parsing fails
    """
    try:
        # Extract title and URL - try multiple selectors
        title = None
        url = None

        title_selectors = [
            "h5.item__title a",
            "h3.item__title a",
            "h4 a",
            "a.title",
            "div.title a",
        ]

        for selector in title_selectors:
            title_elem = item.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                href = title_elem.get("href", "")
                if href:
                    url = base_url + href if href.startswith("/") else href
                break

        if not title:
            return None

        # Extract authors
        authors = []
        author_selectors = [
            "ul.rlist--inline a",
            "div.authors a",
            "span.author",
            "div.contrib-author",
        ]

        for selector in author_selectors:
            author_elems = item.select(selector)
            if author_elems:
                authors = [
                    a.get_text(strip=True) for a in author_elems if a.get_text(strip=True)
                ]
                break

        # Extract publication info
        publication = ""
        pub_date = ""

        pub_selectors = [
            "div.item__meta",
            "div.meta",
            "span.publication",
        ]

        for selector in pub_selectors:
            pub_info = item.select_one(selector)
            if pub_info:
                pub_text = pub_info.get_text(strip=True)
                # Try to split by common separators
                parts = pub_text.split("|")
                if len(parts) >= 1:
                    publication = parts[0].strip()
                if len(parts) >= 2:
                    pub_date = parts[1].strip()
                break

        # Extract DOI
        doi = ""
        doi_elem = item.select_one('a[href*="doi.org"]')
        if doi_elem:
            doi_url = doi_elem.get('href', '')
            if 'doi.org/' in doi_url:
                doi = doi_url.split('doi.org/')[-1]

        # Extract abstract
        abstract = ""
        abstract_selectors = [
            'div.item__description',
            'div.abstract',
            'p.abstract',
        ]

        for selector in abstract_selectors:
            abstract_elem = item.select_one(selector)
            if abstract_elem:
                abstract = abstract_elem.get_text(strip=True)
                break

        return Paper(
            title=title,
            authors=authors,
            abstract=abstract,
            url=url or "",
            doi=doi,
            publication=publication,
            pub_date=pub_date,
            source="asce",
        )

    except Exception as e:
        logger.warning(f"Error parsing paper item: {e}")
        return None
