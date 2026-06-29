"""Fetcher untuk IEEE Xplore - https://ieeexplore.ieee.org

Menggunakan endpoint internal /rest/search yang keyless (tidak butuh API key).
Strategi browser-emulation: hit homepage dulu untuk dapat cookie, lalu POST
ke /rest/search. Hasil basic metadata lalu enrich dengan abstract via
/rest/document/{aid}/abstract.

PDF download: IEEE PDF biasanya butuh subscription. Untuk Open Access papers,
url html_url tetap valid. Cek juga via Unpaywall (DOI-based) untuk OA mirror.
"""

import logging
import os
import time
from typing import Iterable
from urllib.parse import quote_plus

from ..http_client import RateLimiter, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

IEEE_BASE = "https://ieeexplore.ieee.org"
SEARCH_API = IEEE_BASE + "/rest/search"
ABSTRACT_API = IEEE_BASE + "/rest/document/{}/abstract"

ROWS_PER_PAGE = 25  # smaller per call so we don't hit IEEE rate limits

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Origin": IEEE_BASE,
}


def _bootstrap_session(client, query: str) -> bool:
    """Hit IEEE search page to populate cookies for the JSON API."""
    try:
        warmup_url = f"{IEEE_BASE}/search/searchresult.jsp?newsearch=true&queryText={query}"
        r = client.get(warmup_url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=20)
        return r.status_code in (200, 301, 302)
    except Exception as e:
        log.debug("ieee bootstrap error: %s", e)
        return False


def _post_search(client, query: str, page_number: int) -> dict | None:
    """POST to /rest/search with browser-like headers."""
    payload = {
        "newsearch": True,
        "queryText": query,
        "pageNumber": page_number,
        "rowsPerPage": ROWS_PER_PAGE,
        "returnType": "SEARCH",
        "highlight": True,
        "returnFacets": ["ALL"],
        "sortType": "most-relevant",
    }
    headers = dict(HEADERS)
    headers["Referer"] = (
        f"{IEEE_BASE}/search/searchresult.jsp?newsearch=true&queryText={quote_plus(query)}"
    )

    for attempt in range(3):
        try:
            r = client.post(SEARCH_API, json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(min(4 * (2 ** attempt), 30))
                continue
            log.debug("ieee search HTTP %s", r.status_code)
            return None
        except Exception as e:
            log.debug("ieee search attempt %d err: %s", attempt + 1, e)
            time.sleep(2)
    return None


def _parse_record(r: dict) -> Paper | None:
    title = (r.get("articleTitle") or "").strip()
    if not title:
        return None
    title = strip_html(title) or title

    aid = str(r.get("articleNumber", "")).strip()

    authors = []
    raw = r.get("authors", []) or []
    if isinstance(raw, list):
        for a in raw:
            if isinstance(a, dict):
                name = a.get("preferredName") or a.get("normalizedName") or ""
                if name:
                    authors.append(name)

    year = None
    py = r.get("publicationYear")
    if py:
        try:
            year = int(str(py)[:4])
        except (ValueError, TypeError):
            pass

    venue = r.get("publicationTitle") or None
    pub_type = (r.get("contentType") or "").lower()
    venue_type = None
    if pub_type:
        if "conference" in pub_type:
            venue_type = "conference"
        elif "journal" in pub_type or "magazine" in pub_type or "transactions" in pub_type:
            venue_type = "journal"
        elif "early access" in pub_type:
            venue_type = "preprint"

    landing_url = aid and f"{IEEE_BASE}/document/{aid}"
    pdf_url = aid and f"{IEEE_BASE}/stamp/stamp.jsp?tp=&arnumber={aid}"

    # Check is_open_access: IEEE uses boolean or string "true"/"1"
    oa_flag = r.get("openAccessFlag") or r.get("isOpenAccess")
    if isinstance(oa_flag, str):
        is_oa = oa_flag.lower() in ("true", "1", "yes")
    else:
        is_oa = bool(oa_flag)

    # Normalize type
    _ieee_type_map = {
        "conferences": "conference-paper",
        "journals": "journal-article",
        "magazines": "journal-article",
        "early access articles": "preprint",
    }
    normalized_type = _ieee_type_map.get(pub_type, pub_type or None)

    return Paper(
        source="ieee",
        source_id=aid or (r.get("doi") or ""),
        title=title,
        authors=authors,
        abstract=strip_html(r.get("abstract")),
        year=year,
        venue=venue,
        venue_type=venue_type,
        doi=r.get("doi"),
        url=landing_url or None,
        pdf_url=pdf_url or None,
        citations=r.get("citationCount"),
        is_open_access=is_oa,
        type=normalized_type,
        publisher="IEEE",
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search IEEE Xplore via keyless internal API.
    
    No API key required. Uses browser-emulation cookies from a warmup request.
    """
    rl = RateLimiter(1.5)  # be polite, IEEE rate limits aggressively

    # Warmup to get session cookies
    _bootstrap_session(client, query)
    rl.wait()

    fetched = 0
    page = 1
    total_records = None

    while fetched < limit:
        rl.wait()
        data = _post_search(client, query, page)
        if not data:
            return

        records = data.get("records") or []
        if not records:
            return

        if total_records is None:
            total_records = int(data.get("totalRecords") or 0)
            log.info("ieee search '%s' total=%d", query[:40], total_records)

        for r in records:
            paper = _parse_record(r)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        if len(records) < ROWS_PER_PAGE:
            return
        page += 1
        # IEEE caps free search at first 5000 results (~50 pages)
        if page > 50:
            return
