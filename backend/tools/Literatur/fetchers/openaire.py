"""Fetcher untuk OpenAIRE Graph - https://graph.openaire.eu

https://graph.openaire.eu/docs/10.1.0/apis/graph-api/

Keyless public API aggregating scholarly metadata from European and global
repositories. Endpoint: https://api.openaire.eu/search/publications
Response uses XML-namespace nested JSON (oaf:result structure).
"""

import logging
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://api.openaire.eu/search/publications"


def _text(item) -> str:
    """Extract text from <ns:tag>$$value</ns:tag> or plain strings."""
    if not item:
        return ""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("$", "")
    if isinstance(item, list):
        return " ".join(_text(x) for x in item)
    return str(item)


def _parse(result_item: dict) -> Paper | None:
    """Parse a single result from OpenAIRE's nested JSON response."""
    # Each item has keys: header, metadata (no 'result' wrapper)
    oaf = (result_item.get("metadata") or {}).get("oaf:entity", {}) or {}
    r = oaf.get("oaf:result", {}) or {}
    if not r:
        return None

    # Title: list of objects with $ or direct string
    title_raw = r.get("title", []) or []
    if isinstance(title_raw, list):
        # Find the main title first (classid == "main title"), else first item
        main = next((x for x in title_raw if isinstance(x, dict) and x.get("@classid") == "main title"), None)
        title = _text(main) if main else (_text(title_raw[0]) if title_raw else "")
    else:
        title = _text(title_raw)
    if not title:
        return None

    # Authors: creator list
    authors = []
    creators = r.get("creator", []) or []
    if isinstance(creators, dict):
        creators = [creators]
    for c in creators:
        name = _text(c)
        if name:
            authors.append(name)

    # Year from dateofacceptance or publicationdate
    year = None
    for date_key in ("dateofacceptance", "publicationdate"):
        d = r.get(date_key, {}) or {}
        ds = _text(d)
        try:
            year = int(ds[:4])
            break
        except (ValueError, TypeError):
            pass

    # DOI from pid
    doi = None
    pid = r.get("pid") or {}
    if isinstance(pid, dict):
        doi = pid.get("$")
    elif isinstance(pid, list) and pid:
        for p in pid:
            if isinstance(p, dict) and p.get("@classid") == "doi":
                doi = p.get("$")
                break

    # Abstract: description list
    abstract_raw = r.get("description", []) or []
    abstract = _text(abstract_raw) if isinstance(abstract_raw, list) and abstract_raw else _text(abstract_raw)

    # Venue: journal -> name or source
    venue = None
    publisher = None
    journal = r.get("journal", {}) or {}
    if isinstance(journal, dict):
        venue = journal.get("name") or journal.get("$")
    source = r.get("source", {}) or {}
    if isinstance(source, dict):
        publisher = source.get("name") or source.get("publisher")

    # PDF URL: webresource
    pdf_url = None
    landing_url = None
    webresources = r.get("webresource", []) or []
    if isinstance(webresources, dict):
        webresources = [webresources]
    for wr in webresources:
        url = wr.get("url", {}) or {}
        u = url.get("$") if isinstance(url, dict) else url
        if not u:
            continue
        if u.lower().endswith(".pdf"):
            pdf_url = u
        elif not landing_url:
            landing_url = u

    if not pdf_url and doi:
        landing_url = landing_url or f"https://doi.org/{doi}"
    if not landing_url and doi:
        landing_url = f"https://doi.org/{doi}"

    # Open access flag — check for actual OA indicators
    is_oa = None
    # OpenAIRE has openaccess flag in the metadata
    oa_str = _text(r.get("openaccess") or {})
    if oa_str and oa_str.lower() in ("true", "yes", "1"):
        is_oa = True
    elif oa_str and oa_str.lower() in ("false", "no", "0"):
        is_oa = False

    return Paper(
        source="openaire",
        source_id=str(r.get("id", doi or "")),
        title=title,
        authors=authors,
        abstract=abstract or None,
        year=year,
        venue=venue,
        venue_type="journal" if venue else "repository",
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        is_open_access=is_oa,
        type=r.get("type") or None,
        publisher=publisher,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search OpenAIRE publications. No API key required.

    Uses 'keywords' param for full-text search (broader than 'title').
    API still works (deprecated May 31, 2026 but live).
    """
    rl = RateLimiter(0.3)
    fetched = 0
    page = 1

    while fetched < limit:
        rl.wait()
        params = {
            "keywords": query,
            "size": min(limit - fetched, 25),
            "page": page,
            "format": "json",
        }
        data = fetch_json(client, BASE, params=params)
        if not data:
            return

        # JSON response structure: data['response']['results']['result']
        response = data.get("response", {})
        if not response:
            return

        results_wrapper = response.get("results", {})
        if not results_wrapper:
            return

        results = results_wrapper.get("result", [])
        if not results:
            return

        # results can be a single dict or list
        if isinstance(results, dict):
            results = [results]

        for item in results:
            paper = _parse(item)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        # Check if there are more pages
        header = response.get("header", {})
        total_obj = header.get("total", {})
        total = int(total_obj.get("$", 0)) if isinstance(total_obj, dict) else 0
        if page * params["size"] >= total:
            return
        page += 1