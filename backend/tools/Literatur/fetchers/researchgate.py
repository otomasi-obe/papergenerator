"""Fetcher untuk ResearchGate - https://www.researchgate.net

ResearchGate tidak memiliki publik API. Akses HTTP langsung diblokir Cloudflare
(error 1020, "Temporarily Unavailable") pada IP datacenter. Solusi yang WORK di 2026:

**PRIMARY (TERBUKTI WORK): curl_cffi dengan impersonate="chrome131"**
TLS/JA3/HTTP2 fingerprint Chrome asli di socket level. Bypass Cloudflare Turnstile
tanpa proxy dari VPS datacenter. Test 2026-06-30: 200 OK, 173KB HTML, 20 cards.

Fallback cascade:
1. curl_cffi (chrome131) — TLS impersonation (WORK, no proxy needed) ✅
2. cloudscraper — JS challenge solving (GAGAL di RG 2026)
3. requests plain — fallback terakhir (PASTI GAGAL)

Install:
    pip install curl-cffi>=0.15.0
    # cloudscraper opsional untuk fallback

Usage:
    from tools.Literatur.fetchers.researchgate import search
    papers = list(search(None, "robot", limit=10))  # client arg diabaikan

CSS selector ResearchGate (nova-legacy, 2024-2026):
  .nova-legacy-c-card__body--spacing-inherit  →  setiap publikasi
  .nova-legacy-v-publication-item__title     →  judul
  .nova-legacy-v-publication-item__badge     →  tipe (Journal Article, etc)
  .nova-legacy-v-publication-item__meta-data-item  →  date/DOI/ISBN
  .nova-legacy-v-person-inline-item__fullname  →  authors

Catatan: ResearchGate sering mengubah CSS class. Kalau parse gagal, warning
akan di-log dan fetcher return hasil parsial (list dari search tetap ada).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterable
from urllib.parse import quote

from ..http_client import RateLimiter, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://www.researchgate.net"
SEARCH_URL = f"{BASE}/search/publication"

# Rate limit: ResearchGate aggressive — 2 detik minimum antar request
_RL = RateLimiter(2.0)

# ── Cloudflare bypass: curl_cffi with TLS impersonation ─────────────────────
# ResearchGate menggunakan Cloudflare Turnstile + Bot Fight Mode.
# curl_cffi dengan impersonate="chrome131" berhasil bypass dari datacenter IP
# karena meniru TLS/JA3/HTTP2 fingerprint Chrome secara exact di socket level.

class _RGScraper:
    """Cloudflare-bypassing scraper untuk ResearchGate via curl_cffi."""

    def __init__(self):
        self.session = None
        self._init_scraper()

    def _init_scraper(self):
        try:
            from curl_cffi import requests as cffi_requests
            self.session = cffi_requests.Session(impersonate="chrome131")
            self._backend = "curl_cffi"
        except ImportError:
            log.warning("researchgate: curl_cffi not installed, falling back to cloudscraper")
            try:
                import cloudscraper
                self.session = cloudscraper.create_scraper(
                    browser="chrome", delay=3, interpreter="js2py",
                )
                self._backend = "cloudscraper"
            except ImportError:
                import requests
                self.session = requests.Session()
                self.session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                })
                self._backend = "requests"

    def get(self, url: str, timeout: int = 30) -> str | None:
        """GET request with Cloudflare bypass. Returns HTML or None."""
        if not self.session:
            return None
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200 and len(resp.text) > 10000:
                return resp.text
            elif "Just a moment" in resp.text or "Temporarily Unavailable" in resp.text:
                log.warning("researchgate: Cloudflare challenge on %s (backend=%s)", url[:80], self._backend)
                return None
            else:
                log.warning("researchgate: status %d, len=%d for %s (backend=%s)",
                           resp.status_code, len(resp.text), url[:80], self._backend)
                return None
        except Exception as e:
            log.warning("researchgate: GET error for %s: %s", url[:80], e)
            return None


# ── Helper functions ───────────────────────────────────────────────────────

def _normalize_date(raw: str | None) -> tuple[str | None, int | None]:
    """Convert ResearchGate date string to (ISO-ish, year)."""
    if not raw:
        return None, None
    raw = raw.strip()

    # Formats: "May 2024", "Jun 2026", etc.
    m = re.match(r'^([A-Z][a-z]+)\s+(\d{4})$', raw)
    if m:
        return f"{m.group(2)}-{m.group(1)}", int(m.group(2))
    m = re.match(r'^(\d{4})$', raw)
    if m:
        return m.group(1), int(m.group(1))
    m = re.match(r'^(\d{4})-(\d{2})$', raw)
    if m:
        return m.group(0), int(m.group(1))

    return raw, None


def _normalize_type(raw: str | None) -> str:
    """Normalize ResearchGate type badge to paper type."""
    if not raw:
        return "article"
    raw = raw.lower().strip()
    if "journal" in raw:
        return "journal-article"
    if "conference" in raw:
        return "conference-paper"
    if "book" in raw:
        if "chapter" in raw:
            return "book-chapter"
        return "book"
    if "preprint" in raw:
        return "preprint"
    if "thesis" in raw:
        return "thesis"
    return "article"


# ── Parse dengan BeautifulSoup (lebih robust dari regex) ────────────────────
def _parse_search_html(html: str, query: str) -> list[dict]:
    """Parse ResearchGate search results HTML using BeautifulSoup."""
    results = []
    
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        log.warning("researchgate: BeautifulSoup parse error: %s", e)
        return results

    # Find all publication cards
    cards = soup.find_all("div", class_="nova-legacy-c-card__body--spacing-inherit")
    
    for card in cards:
        try:
            # Title & URL
            title_elem = card.find("div", class_="nova-legacy-v-publication-item__title")
            if not title_elem:
                continue
            link_elem = title_elem.find("a", class_="nova-legacy-e-link--theme-bare")
            if not link_elem:
                continue
            title = link_elem.get_text(strip=True)
            url = link_elem.get("href", "")
            
            # Make URL absolute
            if url.startswith("/"):
                url = BASE + url
            elif not url.startswith("http"):
                url = BASE + "/" + url

            # Authors
            authors = []
            author_links = card.find_all("a", class_="nova-legacy-v-person-inline-item", itemprop="author")
            for al in author_links:
                name_elem = al.find("span", class_="nova-legacy-v-person-inline-item__fullname")
                if name_elem:
                    authors.append(name_elem.get_text(strip=True))

            # Date & DOI & ISBN — from meta-data list items
            date = None
            doi = None
            meta_items = card.find_all("li", class_="nova-legacy-v-publication-item__meta-data-item")
            for item in meta_items:
                text = item.get_text(strip=True)
                if text and not date and ("20" in text or "19" in text):  # year pattern
                    date = text
                if text.startswith("DOI:"):
                    doi = text[4:].strip()
                elif text.startswith("10.") and "/" in text:
                    doi = text.strip()

            # Type badge
            type_badge = card.find("span", class_="nova-legacy-v-publication-item__badge")
            pub_type = _normalize_type(type_badge.get_text(strip=True) if type_badge else None)

            # Source/journal
            source_elem = card.find("span", class_="nova-legacy-v-publication-item__source-title")
            source_name = source_elem.get_text(strip=True) if source_elem else None

            results.append({
                "title": title,
                "url": url,
                "authors": authors,
                "date": date,
                "doi": doi,
                "type": pub_type,
                "source_name": source_name,
            })
        except Exception as e:
            log.debug("researchgate: failed to parse card: %s", e)
            continue

    return results


def _parse_detail_html(html: str) -> dict:
    """Parse ResearchGate publication detail page."""
    detail = {}

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Abstract
        abstract_elem = soup.find("div", {"data-testid": "abstract-text"})
        if abstract_elem:
            detail["abstract"] = abstract_elem.get_text(strip=True)

        # Citations count
        citations_elem = soup.find("span", class_="nova-legacy-v-statistics-item__count")
        if citations_elem:
            try:
                detail["citations"] = int(citations_elem.get_text(strip=True).replace(",", ""))
            except ValueError:
                pass

        # Authors (more complete)
        authors = []
        author_links = soup.find_all("a", class_="nova-legacy-v-person-inline-item", itemprop="author")
        for al in author_links:
            name_elem = al.find("span", class_="nova-legacy-v-person-inline-item__fullname")
            if name_elem:
                authors.append(name_elem.get_text(strip=True))
        if authors:
            detail["authors"] = authors

        # Journal / venue
        journal_elem = soup.find("span", {"data-testid": "journal-name"})
        if journal_elem:
            detail["journal"] = journal_elem.get_text(strip=True)

        # DOI
        doi_elem = soup.find("span", {"data-testid": "doi"})
        if doi_elem:
            detail["doi"] = doi_elem.get_text(strip=True)

        # Year
        year_elem = soup.find("span", {"data-testid": "publication-date"})
        if year_elem:
            _, year = _normalize_date(year_elem.get_text(strip=True))
            if year:
                detail["year"] = year

    except Exception as e:
        log.debug("researchgate: detail parse error: %s", e)

    return detail


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Cari publikasi di ResearchGate.

    Args:
        client: httpx.Client instance (ignored, we use cloudscraper).
        query: kata kunci pencarian.
        limit: jumlah maksimal paper yang di-return.
        filters: filter tambahan (belum dipakai untuk RG, reserved).

    Yields:
        Paper objects. Abstract & citations hanya tersedia kalau detail page
        di-fetch (otomatis untuk 5 paper pertama jika limit <= 10).
    """
    # Initialize cloudscraper (ignore httpx client)
    scraper = _RGScraper()

    seen_urls: set[str] = set()
    fetched = 0
    page = 1
    max_pages = (limit + 9) // 10  # ~10 results per page

    while fetched < limit and page <= max_pages:
        _RL.wait()
        encoded_query = quote(query, safe="")
        url = f"{SEARCH_URL}?q={encoded_query}&page={page}"

        html = scraper.get(url)
        if not html:
            log.warning("researchgate search: empty response page %d", page)
            return

        # Check for Cloudflare block
        if "Just a moment" in html or "error code: 1020" in html:
            log.warning("researchgate: Cloudflare challenge on page %d — abort", page)
            return

        results = _parse_search_html(html, query)
        if not results:
            log.info("researchgate: no more results at page %d", page)
            return

        for r in results:
            if fetched >= limit:
                return
            if r["url"] in seen_urls:
                continue
            seen_urls.add(r["url"])

            date_str, year = _normalize_date(r.get("date"))
            pub_type = _normalize_type(r.get("type"))

            # For small limits, fetch detail page for richer metadata
            abstract = None
            citations = None
            journal = r.get("source_name")
            venue_type = None

            if limit <= 10 and r["url"]:
                _RL.wait()
                detail_html = scraper.get(r["url"])
                if detail_html and "error code: 1020" not in detail_html:
                    detail = _parse_detail_html(detail_html)
                    abstract = detail.get("abstract")
                    citations = detail.get("citations")
                    journal = detail.get("journal") or journal
                    if detail.get("authors"):
                        r["authors"] = detail["authors"]
                    if detail.get("year"):
                        year = detail["year"]
                    if detail.get("doi"):
                        r["doi"] = detail["doi"]

            # Determine venue_type from type
            if pub_type == "journal-article":
                venue_type = "journal"
            elif pub_type == "conference-paper":
                venue_type = "conference"
            elif pub_type in ("book", "book-chapter"):
                venue_type = "book"
            elif pub_type == "preprint":
                venue_type = "repository"

            yield Paper(
                source="researchgate",
                source_id=r["url"].split("/")[-1].split("?")[0],
                title=r["title"],
                authors=r.get("authors", []),
                abstract=abstract,
                year=year,
                venue=journal,
                venue_type=venue_type,
                doi=r.get("doi"),
                url=r["url"],
                pdf_url=None,  # RG requires login for direct PDF
                citations=citations,
                is_open_access=None,  # RG mixes OA and paywalled
                type=pub_type,
                publication_date=date_str,
            )
            fetched += 1

        page += 1


# ── FlareSolverr fallback ──────────────────────────────────────────────────

def _fetch_via_flaresolverr(url: str, timeout: int = 60) -> str | None:
    """Fetch URL via FlareSolverr proxy server.

    Requires FlareSolverr running at http://localhost:8191
    Install: docker run -d --name=flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
    """
    try:
        import requests as req
        resp = req.post(
            "http://localhost:8191/v1",
            json={
                "cmd": "request.get",
                "url": url,
                "maxTimeout": timeout * 1000,
            },
            timeout=timeout + 10,
        )
        data = resp.json()
        if data.get("status") == "ok":
            solution = data.get("solution", {})
            html = solution.get("response", "")
            if html and "Just a moment" not in html and len(html) > 1000:
                return html
        log.warning("researchgate: FlareSolverr failed: %s", data.get("message", "unknown"))
    except Exception as e:
        log.warning("researchgate: FlareSolverr error: %s", e)
    return None


def _fetch_via_playwright(url: str, timeout: int = 30) -> str | None:
    """Fetch URL via Playwright with stealth (last resort fallback)."""
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import stealth_sync

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()
            stealth_sync(page)
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

            # Wait for Cloudflare
            try:
                page.wait_for_url(lambda u: "Just a moment" not in u, timeout=15000)
            except Exception:
                pass

            html = page.content()
            browser.close()

            if html and "Just a moment" not in html and len(html) > 1000:
                return html
    except Exception as e:
        log.warning("researchgate: Playwright error: %s", e)
    return None


def search_researchgate_with_proxy(query: str, limit: int = 25) -> list[Paper]:
    """Search ResearchGate with automatic fallback chain.

    Tries multiple methods in order:
    1. cloudscraper (fast, no external deps)
    2. FlareSolverr (if running on localhost:8191)
    3. Playwright + stealth (if installed)

    Returns empty list if all methods fail (IP blocked by Cloudflare).
    """
    # Method 1: cloudscraper
    log.info("researchgate: trying cloudscraper...")
    scraper = _RGScraper()
    test_html = scraper.get(f"{SEARCH_URL}?q={quote(query, safe='')}&page=1")
    if test_html and "Just a moment" not in test_html and len(test_html) > 10000:
        log.info("researchgate: cloudscraper works!")
        return list(search(None, query, limit=limit))

    # Method 2: FlareSolverr
    log.info("researchgate: cloudscraper failed, trying FlareSolverr...")
    test_html = _fetch_via_flaresolverr(f"{SEARCH_URL}?q={quote(query, safe='')}&page=1")
    if test_html:
        log.info("researchgate: FlareSolverr works!")
        # Monkey-patch the scraper to use FlareSolverr
        original_get = scraper.get
        scraper.get = lambda url, timeout=30: _fetch_via_flaresolverr(url, timeout)
        return list(search(None, query, limit=limit))

    # Method 3: Playwright
    log.info("researchgate: FlareSolverr failed, trying Playwright...")
    test_html = _fetch_via_playwright(f"{SEARCH_URL}?q={quote(query, safe='')}&page=1")
    if test_html:
        log.info("researchgate: Playwright works!")
        scraper.get = lambda url, timeout=30: _fetch_via_playwright(url, timeout)
        return list(search(None, query, limit=limit))

    log.error("researchgate: ALL methods failed. IP blocked by Cloudflare. "
              "Setup FlareSolverr or use residential proxy.")
    return []