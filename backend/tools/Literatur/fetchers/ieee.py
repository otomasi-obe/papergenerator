"""Fetcher untuk IEEE Xplore — browser-emulation (tanpa API key).

Mengikuti pola PaperRiset/SLR/ieee.py:
- POST /rest/search untuk search (session cookie bootstrap)
- GET /rest/document/{aid}/abstract untuk enrich abstract + authors + keywords
- Tanpa UNDIP proxy
- Tanpa download PDF (metadata only)

Rate limit ketat dengan retry + backoff + proxy rotation.
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

ROWS_PER_PAGE = 100

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

_CONTENT_TYPE_VENUE_MAP = {
    "conferences": "conference",
    "journals": "journal",
    "magazines": "journal",
    "books": "book",
    "early access articles": "preprint",
    "standards": "standard",
    "courses": "course",
}

_CONTENT_TYPE_PAPER_TYPE_MAP = {
    "conferences": "conference-paper",
    "journals": "journal-article",
    "magazines": "article",
    "books": "book-chapter",
    "early access articles": "preprint",
    "standards": "technical-report",
    "courses": "misc",
}


def _bootstrap_session(client, query: str) -> bool:
    """Hit IEEE search page to populate cookies."""
    try:
        url = f"{IEEE_BASE}/search/searchresult.jsp?newsearch=true&queryText={query}"
        r = client.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=20)
        return r.status_code in (200, 301, 302)
    except Exception as e:
        log.debug("ieee bootstrap: %s", e)
        return False


def _post_search(client, query: str, page_number: int) -> dict | None:
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

    for attempt in range(5):
        try:
            r = client.post(SEARCH_API, json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = min(4 * (2 ** attempt), 90)
                log.warning("ieee 429 rate-limit, wait %ds", wait)
                time.sleep(wait)
                continue
            log.debug("ieee search HTTP %s", r.status_code)
            return None
        except Exception as e:
            wait = min(4 * (2 ** attempt), 60)
            log.debug("ieee search attempt %d err: %s | wait %ds", attempt + 1, e, wait)
            time.sleep(wait)
    return None


def _fetch_one_abstract(client, aid: str, retries: int = 3) -> dict:
    url = ABSTRACT_API.format(aid)
    delay = 2
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{IEEE_BASE}/document/{aid}",
        "Origin": IEEE_BASE,
        "X-Requested-With": "XMLHttpRequest",
    }
    for attempt in range(retries):
        try:
            r = client.get(url, headers=headers, timeout=25)
            if r.status_code == 429:
                time.sleep(min(delay * (2 ** attempt), 30))
                continue
            if r.status_code in (403, 404):
                return {}
            if not r.text.strip():
                time.sleep(delay * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            time.sleep(delay * (attempt + 1))
    return {}


def _build_paper(r: dict, ab: dict) -> Paper | None:
    aid = str(r.get("articleNumber", "")).strip()
    title = strip_html(r.get("articleTitle", "")).strip()
    if not title:
        return None

    abstract = ab.get("abstract", "") or r.get("abstract", "")

    # Authors: prefer abstract API version (richer)
    authors_list = []
    affiliations = []
    raw_authors = ab.get("authors", None)
    if isinstance(raw_authors, dict):
        al = raw_authors.get("authors", [])
    elif isinstance(raw_authors, list):
        al = raw_authors
    else:
        al = []
    for a in al:
        if isinstance(a, dict):
            name = a.get("preferredName", a.get("normalizedName", a.get("name", "")))
            if name and name not in authors_list:
                authors_list.append(name)
            aff = a.get("affiliation", "")
            if aff and aff not in affiliations:
                affiliations.append(aff)
    if not authors_list:
        # fallback to search record
        raw = r.get("authors", [])
        if isinstance(raw, list):
            for a in raw:
                if isinstance(a, dict):
                    name = a.get("preferredName", a.get("normalizedName", ""))
                    if name and name not in authors_list:
                        authors_list.append(name)

    # Keywords from abstract API
    keywords = []
    seen_kw = set()
    for kw_group in ab.get("keywords", []):
        if isinstance(kw_group, dict):
            for kw in kw_group.get("kwd", []):
                if isinstance(kw, dict):
                    kw_val = kw.get("value", kw.get("kwd", ""))
                else:
                    kw_val = str(kw)
                if kw_val and kw_val not in seen_kw:
                    keywords.append(kw_val)
                    seen_kw.add(kw_val)

    # Year
    year = None
    py = ab.get("publicationYear") or r.get("publicationYear")
    if py:
        try:
            year = int(str(py)[:4])
        except (ValueError, TypeError):
            pass

    venue = (ab.get("publicationTitle") or r.get("publicationTitle") or "").strip() or None

    pub_type_text = (r.get("contentType") or "").strip().lower()
    venue_type = _CONTENT_TYPE_VENUE_MAP.get(pub_type_text)
    paper_type = _CONTENT_TYPE_PAPER_TYPE_MAP.get(pub_type_text)

    # URLs (no proxy needed)
    landing_url = f"{IEEE_BASE}/document/{aid}" if aid else None
    pdf_url = f"{IEEE_BASE}/stamp/stamp.jsp?tp=&arnumber={aid}" if aid else None

    # Open access detection
    oa_flag = r.get("openAccessFlag") or r.get("isOpenAccess")
    if isinstance(oa_flag, str):
        is_oa = oa_flag.lower() in ("true", "1", "yes")
    else:
        is_oa = bool(oa_flag)

    return Paper(
        source="ieee",
        source_id=aid or r.get("doi", ""),
        title=title,
        authors=authors_list,
        abstract=strip_html(abstract).strip() if abstract else None,
        year=year,
        venue=venue,
        venue_type=venue_type,
        doi=r.get("doi"),
        url=landing_url,
        pdf_url=pdf_url,
        citations=r.get("citationCount"),
        is_open_access=is_oa,
        type=paper_type,
        publisher="IEEE",
        keywords=keywords or None,
        affiliations=affiliations or None,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search IEEE Xplore via browser-emulation (no API key needed).

    Strategy:
    1. Bootstrap session (warmup GET for cookies)
    2. POST /rest/search for paper records
    3. Enrich via GET /rest/document/{aid}/abstract for each paper
    4. Rate limit + retry + backoff with proxy rotation support

    Args:
        client: httpx.Client (supports proxy rotation).
        limit: Max papers to return.
        filters: Optional dict with keys:
            - content_type (str): filter by content type (Conferences, Journals, etc.)
    """
    rl = RateLimiter(2.0)

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

        # Enrich each record with abstract
        for r in records:
            if fetched >= limit:
                return
            aid = str(r.get("articleNumber", "")).strip()
            if aid:
                ab = _fetch_one_abstract(client, aid)
                time.sleep(0.5)  # polite spacing between abstract fetches
            else:
                ab = {}
            paper = _build_paper(r, ab)
            if paper:
                yield paper
                fetched += 1

        if len(records) < ROWS_PER_PAGE:
            return
        page += 1
        if page > 50:
            log.info("ieee: free search capped at ~5000 results")
            return
