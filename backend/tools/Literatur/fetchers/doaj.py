"""Fetcher untuk DOAJ — Directory of Open Access Journals.

REST API v3: https://doaj.org/api/v3/search/articles/{query}
Keyless. Returns OA journal articles only.
"""

import logging
from typing import Iterable
from urllib.parse import quote

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://doaj.org/api/v3/search/articles"


def _parse(item: dict) -> Paper | None:
    bib = item.get("bibjson") or {}
    title = bib.get("title")
    if not title:
        return None

    authors = []
    for a in bib.get("author") or []:
        name = a.get("name") or ""
        if name:
            authors.append(name.strip())

    year = None
    y = bib.get("year")
    if y:
        try:
            year = int(str(y)[:4])
        except (ValueError, TypeError):
            pass

    # DOI
    doi = None
    for ident in bib.get("identifier") or []:
        if ident.get("type") == "doi":
            doi = ident.get("id")
            break

    # Links
    links = bib.get("link") or []
    pdf_url = None
    landing_url = None
    for lnk in links:
        t = lnk.get("type", "")
        u = lnk.get("url", "")
        if t == "fulltext" and not landing_url:
            landing_url = u
        if t == "pdf" or (u and u.lower().endswith(".pdf")):
            pdf_url = u
    if not landing_url and doi:
        landing_url = f"https://doi.org/{doi}"
    if not pdf_url:
        pdf_url = landing_url

    venue = (bib.get("journal") or {}).get("title")
    publisher = (bib.get("journal") or {}).get("publisher")
    abstract = bib.get("abstract")
    keywords = [k for k in bib.get("keywords") or [] if k]

    return Paper(
        source="doaj",
        source_id=item.get("id") or doi or "",
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=venue,
        venue_type="journal",
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        is_open_access=True,  # DOAJ indexes only OA journals
        type="journal-article",
        publisher=publisher,
        keywords=keywords,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search DOAJ articles via REST API v3. No key required."""
    rl = RateLimiter(0.5)
    per_page = min(limit, 100)
    fetched = 0
    page = 1

    encoded = quote(query)
    url = f"{BASE}/{encoded}"

    while fetched < limit:
        rl.wait()
        params = {
            "page": page,
            "pageSize": min(per_page, limit - fetched),
        }
        data = fetch_json(client, url, params=params)
        if not data:
            return

        results = data.get("results") or []
        if not results:
            return

        for item in results:
            paper = _parse(item)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        total = data.get("total", 0)
        if page * per_page >= total:
            return
        page += 1
