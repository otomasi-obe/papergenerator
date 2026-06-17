"""Fetcher untuk DOAJ - Directory of Open Access Journals.

https://doaj.org/api/docs

Keyless public API. Returns peer-reviewed open-access journal articles.
Endpoint: https://doaj.org/api/search/articles/{query}?page=N&pageSize=M
All DOAJ articles are open access by definition.
"""

import html
import logging
import re
from typing import Iterable
from urllib.parse import quote

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://doaj.org/api/search/articles"
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip() or None


def _parse(result: dict) -> Paper | None:
    bib = result.get("bibjson") or {}
    title = _clean(bib.get("title"))
    if not title:
        return None

    authors = []
    for a in bib.get("author", []) or []:
        name = (a.get("name") or "").strip()
        if name:
            authors.append(name)

    year = None
    y = bib.get("year")
    if y:
        try:
            year = int(str(y)[:4])
        except (ValueError, TypeError):
            pass

    journal = bib.get("journal") or {}
    venue = journal.get("title")
    publisher = journal.get("publisher")

    doi = None
    landing_url = None
    pdf_url = None
    for ident in bib.get("identifier", []) or []:
        if ident.get("type") == "doi":
            doi = ident.get("id")
    for link in bib.get("link", []) or []:
        url = link.get("url")
        if not url:
            continue
        ltype = (link.get("type") or "").lower()
        content_type = (link.get("content_type") or "").lower()
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            pdf_url = url
        elif ltype == "fulltext" and not landing_url:
            landing_url = url

    if not pdf_url and doi:
        pdf_url = f"https://doi.org/{doi}"
    if not landing_url:
        landing_url = pdf_url or (doi and f"https://doi.org/{doi}")

    return Paper(
        source="doaj",
        source_id=str(result.get("id", "")),
        title=title,
        authors=authors,
        abstract=_clean(bib.get("abstract")),
        year=year,
        venue=venue,
        venue_type="journal",
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        is_open_access=True,  # DOAJ only indexes open access
        type="journal-article",
        publisher=publisher,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search DOAJ open-access articles. No API key required."""
    rl = RateLimiter(0.5)
    per_page = min(limit, 100)
    fetched = 0
    page = 1

    while fetched < limit:
        rl.wait()
        encoded = quote(query, safe="")
        url = f"{BASE}/{encoded}"
        params = {
            "page": page,
            "pageSize": min(per_page, limit - fetched),
            "sort": "_score",
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
