"""Shared Elsevier API helpers — Scopus, ScienceDirect, ClinicalKey, Embase.

Implements elsapy patterns from https://github.com/ElsevierDev/elsapy:
  - X-ELS-APIKey + X-ELS-Insttoken headers (insttoken unlocks SD/CK/Embase)
  - Start-based pagination (compatible with all Elsevier search indexes)
  - User-Agent, Accept, and rate limiting
"""

import logging
import os
from typing import Any

from ..http_client import RateLimiter, fetch_json, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

ELSEVIER_API_KEY = "8d60fa37d8a11e09ab1992f8ed87f1b0"

BASE = "https://api.elsevier.com/content"


def _get_headers() -> dict:
    headers = {
        "X-ELS-APIKey": os.getenv("ELSEVIER_API_KEY") or ELSEVIER_API_KEY,
        "Accept": "application/json",
    }
    inst_token = os.getenv("ELSEVIER_INST_TOKEN", "")
    if inst_token:
        headers["X-ELS-Insttoken"] = inst_token
    return headers


def elsevier_enabled() -> bool:
    return bool(os.getenv("ELSEVIER_API_KEY") or ELSEVIER_API_KEY)


def fetch_paginated(
    client, url: str, params: dict, limit: int, per_page: int
) -> list[dict]:
    rl = RateLimiter(0.5)
    fetched = 0
    start = 0
    all_entries: list[dict] = []

    max_pages = (limit // per_page) + 2

    for _ in range(max_pages):
        rl.wait()
        current_params = dict(params, count=min(per_page, limit - fetched), start=start)
        data = fetch_json(client, url, headers=_get_headers(), params=current_params)
        if not data:
            break
        results = data.get("search-results", {})
        entries = results.get("entry", [])
        if not entries:
            break
        all_entries.extend(entries)
        fetched += len(entries)
        start += len(entries)
        total = int(results.get("opensearch:totalResults", 0))
        if start >= total or fetched >= limit:
            break
    return all_entries


def _parse_scopus_entry(e: dict) -> Paper | None:
    title = e.get("dc:title")
    if not title:
        return None

    authors = []
    creator = (e.get("dc:creator") or "").strip()
    if creator:
        authors.append(creator)

    year = None
    cover = e.get("prism:coverDate")
    if cover:
        try:
            year = int(cover.split("-")[0])
        except (ValueError, IndexError):
            pass

    doi = e.get("prism:doi")
    scopus_id = (e.get("dc:identifier") or "").replace("SCOPUS_ID:", "")

    abstract = e.get("dc:description") or e.get("prism:teaser")
    if abstract:
        abstract = strip_html(abstract) or None

    agg = (e.get("prism:aggregationType") or "").lower()
    if "journal" in agg:
        venue_type = "journal"
    elif "conference" in agg:
        venue_type = "conference"
    elif "book" in agg:
        venue_type = "book"
    else:
        venue_type = None

    return Paper(
        source="scopus",
        source_id=scopus_id,
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=e.get("prism:publicationName"),
        venue_type=venue_type,
        doi=doi,
        url=entry_link(e.get("link")),
        citations=int(e.get("citedby-count", 0)) if e.get("citedby-count") else None,
        is_open_access=e.get("openaccess") == "1",
        type=e.get("prism:aggregationType"),
        publisher=e.get("dc:publisher"),
    )


def _parse_sd_entry(e: dict) -> Paper | None:
    title = e.get("dc:title")
    if not title:
        return None

    authors = []
    authors_data = e.get("authors", {}).get("author", [])
    if isinstance(authors_data, dict):
        authors_data = [authors_data]
    for a in authors_data:
        name = a.get("$", "").strip()
        if name:
            authors.append(name)

    year = None
    cover = e.get("prism:coverDate")
    if cover:
        try:
            year = int(cover.split("-")[0])
        except (ValueError, IndexError):
            pass

    doi = e.get("prism:doi")
    pii = e.get("pii")

    agg = e.get("prism:aggregationType")
    return Paper(
        source="sciencedirect",
        source_id=pii or doi or "",
        title=title,
        authors=authors,
        abstract=e.get("dc:description"),
        year=year,
        venue=e.get("prism:publicationName"),
        venue_type="journal" if agg == "Journal" else None,
        doi=doi,
        url=e.get("prism:url") or (doi and f"https://doi.org/{doi}"),
        is_open_access=e.get("openaccess") == "1",
        type=agg,
        publisher="Elsevier",
    )


def _parse_embase_entry(e: dict) -> Paper | None:
    title = e.get("dc:title")
    if not title:
        return None

    authors = []
    creator = (e.get("dc:creator") or "").strip()
    if creator:
        authors.append(creator)

    year = None
    cover = e.get("prism:coverDate")
    if cover:
        try:
            year = int(cover.split("-")[0])
        except (ValueError, IndexError):
            pass

    doi = e.get("prism:doi")
    embase_id = (e.get("embase:EID") or e.get("dc:identifier") or "").replace("EMBASE_ID:", "").replace("EID:", "")

    abstract = e.get("dc:description") or e.get("prism:teaser")
    if abstract:
        abstract = strip_html(abstract) or None

    agg = (e.get("prism:aggregationType") or "").lower()
    if "journal" in agg:
        venue_type = "journal"
    elif "conference" in agg:
        venue_type = "conference"
    elif "book" in agg:
        venue_type = "book"
    else:
        venue_type = None

    return Paper(
        source="embase",
        source_id=embase_id,
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=e.get("prism:publicationName"),
        venue_type=venue_type,
        doi=doi,
        url=entry_link(e.get("link")),
        citations=int(e.get("citedby-count", 0)) if e.get("citedby-count") else None,
        is_open_access=e.get("openaccess") == "1",
        type=e.get("prism:aggregationType"),
        publisher=e.get("dc:publisher"),
    )


_CK_TYPE_MAP = {
    "chapter": "book",
    "book": "book",
    "journal": "journal",
    "article": "journal",
    "conference": "conference",
    "drug": "reference",
    "drug monograph": "reference",
    "clinical overview": "clinical",
    "clinical": "clinical",
    "procedure": "clinical",
    "guideline": "clinical",
}


def _parse_ck_entry(e: dict) -> Paper | None:
    title = e.get("dc:title")
    if not title:
        return None

    authors = []
    authors_data = e.get("authors", {}).get("author", [])
    if isinstance(authors_data, dict):
        authors_data = [authors_data]
    for a in authors_data:
        name = (a.get("$") or a.get("given-name") or a.get("full-name") or "").strip()
        if name:
            authors.append(name)
    creator = (e.get("dc:creator") or "").strip()
    if creator and not authors:
        authors.append(creator)

    year = None
    cover = e.get("prism:coverDate")
    if cover:
        try:
            year = int(cover.split("-")[0])
        except (ValueError, IndexError):
            pass

    doi = e.get("prism:doi")
    pii = e.get("pii") or e.get("ck:id") or ""

    ck_type = (e.get("ck:type") or e.get("prism:aggregationType") or "").lower()
    venue_type = _CK_TYPE_MAP.get(ck_type)

    abstract = e.get("dc:description") or e.get("prism:teaser")
    if abstract:
        abstract = strip_html(abstract) or None

    return Paper(
        source="clinicalkey",
        source_id=pii,
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=e.get("prism:publicationName") or e.get("ck:bookTitle"),
        venue_type=venue_type,
        doi=doi,
        url=e.get("prism:url") or e.get("ck:url") or (doi and f"https://doi.org/{doi}"),
        is_open_access=e.get("openaccess") == "1",
        type=e.get("ck:type") or e.get("prism:aggregationType"),
        publisher="Elsevier (ClinicalKey)",
    )


def entry_link(link_data: Any) -> str | None:
    if not link_data:
        return None
    if isinstance(link_data, list):
        link_data = link_data[0]
    if isinstance(link_data, dict):
        href = link_data.get("@href")
        return href
    return None