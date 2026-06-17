"""Fetcher untuk Cambridge Core - https://www.cambridge.org/core

Cambridge Core menyajikan HTML hasil pencarian tanpa proteksi Cloudflare,
sehingga di-scrape langsung (httpx + BeautifulSoup). Mengambil judul, penulis,
jurnal, tahun, DOI, dan URL artikel.

Cakupan: luas — sains, teknik, humaniora, hukum, kedokteran.
"""

import logging
import re
from typing import Iterable
from urllib.parse import quote_plus

from ..http_client import RateLimiter, fetch_text
from ..paper import Paper

logger = logging.getLogger(__name__)

BASE = "https://www.cambridge.org"
SEARCH_URL = f"{BASE}/core/search"


def _parse_results(html_text: str) -> list[Paper]:
    """Parse Cambridge Core search results HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text, "html.parser")
    papers = []

    # Each result is in ul.details (server-rendered, no do-not-mathjax class)
    for ul in soup.select("ul.details"):
        try:
            title_link = ul.select_one("li.title h3 a.part-link")
            if not title_link:
                continue
            title = title_link.get_text(strip=True)
            href = title_link.get("href", "")
            url = BASE + href if href.startswith("/") else href

            authors = []
            for a in ul.select("li.author a.more-by-this-author"):
                name = a.get_text(strip=True)
                if name:
                    authors.append(name)

            venue = None
            year = None
            dd_elem = ul.select_one("dt.source + dd")
            if dd_elem:
                journal_link = dd_elem.select_one("a.productParent")
                if journal_link:
                    venue = journal_link.get_text(strip=True)
                year_match = re.search(r"\b(19|20)\d{2}\b", dd_elem.get_text())
                if year_match:
                    year = int(year_match.group())

            if not year:
                date_span = ul.select_one("span.date")
                if date_span:
                    m = re.search(r"\b(19|20)\d{2}\b", date_span.get_text())
                    if m:
                        year = int(m.group())

            doi = None
            doi_link = ul.select_one('a[href*="doi.org"]')
            if doi_link:
                doi_href = doi_link.get("href", "")
                if "doi.org/" in doi_href:
                    doi = doi_href.split("doi.org/")[-1]

            papers.append(Paper(
                source="cambridge",
                source_id=href.rsplit("/", 1)[-1] if href else "",
                title=title,
                authors=authors,
                abstract=None,
                year=year,
                venue=venue,
                venue_type="journal",
                doi=doi,
                url=url,
                pdf_url=None,
                citations=None,
                is_open_access=None,
                type="journal-article",
                publisher="Cambridge University Press",
            ))
        except Exception as e:
            logger.warning(f"Error parsing Cambridge result: {e}")
            continue

    return papers


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Search Cambridge Core dengan men-scrape halaman hasil pencarian.

    filters: dict opsional dengan key 'year_start' / 'year_end'.
    """
    rl = RateLimiter(1.0)
    fetched = 0
    page_num = 1
    per_page = 20

    while fetched < limit:
        rl.wait()

        params = f"?q={quote_plus(query)}&page={page_num}"
        if filters:
            if "year_start" in filters:
                params += f"&filters[datePublished][from]={filters['year_start']}"
            if "year_end" in filters:
                params += f"&filters[datePublished][to]={filters['year_end']}"

        url = SEARCH_URL + params
        logger.info(f"Fetching Cambridge Core page {page_num}: {url}")

        html = fetch_text(client, url)
        if not html:
            logger.warning(f"No response from Cambridge Core page {page_num}")
            return

        papers = _parse_results(html)
        if not papers:
            return

        for paper in papers:
            yield paper
            fetched += 1
            if fetched >= limit:
                return

        page_num += 1
        if len(papers) < per_page:
            return
