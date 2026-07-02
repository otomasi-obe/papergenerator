"""Fetcher untuk Zenodo - https://zenodo.org

https://developers.zenodo.org/

Keyless REST API for searching Zenodo's research repository. Zenodo hosts
open-access publications, datasets, software, and other research outputs
from CERN and the global research community. Each record gets a DOI.
Endpoint: https://zenodo.org/api/records?q=...&size=N
"""

import logging
from typing import Iterable
from urllib.parse import quote

from ..http_client import RateLimiter, fetch_json, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://zenodo.org/api/records"


def _parse(hit: dict) -> Paper | None:
    metadata = hit.get("metadata") or {}
    title = metadata.get("title")
    if not title:
        return None

    authors = []
    for c in metadata.get("creators", []) or []:
        name = (c.get("name") or "").strip()
        if name:
            authors.append(name)

    year = None
    pub_date = metadata.get("publication_date") or metadata.get("date") or ""
    if pub_date:
        try:
            year = int(str(pub_date)[:4])
        except (ValueError, TypeError):
            pass

    doi = metadata.get("doi") or hit.get("doi")
    landing_url = hit.get("links", {}).get("self_html") or (doi and f"https://doi.org/{doi}")

    pdf_url = None
    for f in hit.get("files", []) or []:
        key = f.get("key", "")
        ftype = f.get("type", "")
        url = f.get("links", {}).get("self")
        if url and (key.lower().endswith(".pdf") or "pdf" in ftype.lower()):
            pdf_url = url
            break
        if url and not pdf_url and not key.lower().endswith(".pdf"):
            # First file as fallback (often dataset, but could be paper)
            pdf_url = url

    # Normalize venue_type from resource_type
    rt = metadata.get("resource_type", {}) if isinstance(metadata.get("resource_type"), dict) else {}
    raw_vt = rt.get("type", "")
    _zenodo_vt_map = {
        "publication": "journal",
        "article": "journal",
        "conferencepaper": "conference",
        "preprint": "repository",
        "workingpaper": "repository",
        "report": "repository",
        "book": "book",
        "booksection": "book",
        "dataset": "repository",
        "software": "repository",
        "other": "unknown",
    }
    venue_type = _zenodo_vt_map.get(raw_vt.lower(), "unknown")

    # Normalize type
    _zenodo_type_map = {
        "publication": "journal-article",
        "article": "journal-article",
        "conferencepaper": "conference-paper",
        "preprint": "preprint",
        "workingpaper": "preprint",
        "report": "journal-article",
        "book": "book",
        "booksection": "book",
        "dataset": "dataset",
        "software": "dataset",
        "other": None,
    }
    normalized_type = _zenodo_type_map.get(raw_vt.lower(), raw_vt or None)

    return Paper(
        source="zenodo",
        source_id=str(hit.get("id", "")),
        title=title,
        authors=authors,
        abstract=strip_html(metadata.get("description")),
        year=year,
        venue=metadata.get("journal", {}).get("title") if isinstance(metadata.get("journal"), dict) else None,
        venue_type=venue_type,
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        is_open_access=True,  # Zenodo is open access
        type=normalized_type,
        publisher=metadata.get("publisher"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search Zenodo research outputs. No API key required."""
    rl = RateLimiter(0.5)
    per_page = min(limit, 50)
    fetched = 0
    page = 1

    while fetched < limit:
        rl.wait()
        params = {
            "q": query,
            "size": min(per_page, limit - fetched),
            "page": page,
            "sort": "bestmatch",
        }
        # Optional: filter to publications only if not specified
        if not (filters and filters.get("include_datasets")):
            params["type"] = "publication"
        if filters:
            if filters.get("year_from"):
                params["published_after"] = f"{filters['year_from']}-01-01"
            if filters.get("open_access"):
                params["access_right"] = "open"

        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return
        for h in hits:
            paper = _parse(h)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        total = data.get("hits", {}).get("total", 0)
        if isinstance(total, dict):
            total = total.get("value", 0)
        try:
            total = int(total)
        except (ValueError, TypeError):
            total = 0
        if page * per_page >= total:
            return
        page += 1
