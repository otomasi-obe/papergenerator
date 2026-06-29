"""Fetcher untuk DataCite - https://datacite.org

https://support.datacite.org/docs/api

Keyless REST API for searching DataCite's registry of 125M+ research DOIs.
DataCite is the global DOI registration agency for research data, software,
preprints, and other scholarly outputs.
Endpoint: https://api.datacite.org/dois?query=...&page[size]=N
"""

import logging
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://api.datacite.org/dois"
USER_AGENT = "MonitoringVokasi/1.0 (mailto:research@example.com)"


def _parse(item: dict) -> Paper | None:
    attr = item.get("attributes") or {}
    title = attr.get("titles") or []
    if isinstance(title, list):
        title = title[0] if title else None
    if isinstance(title, dict):
        title = title.get("title")
    if not title:
        return None

    authors = []
    for c in attr.get("creators", []) or []:
        name = (c.get("name") or "").strip()
        if name:
            authors.append(name)

    year = None
    pub_year = attr.get("publicationYear") or attr.get("created")
    if pub_year:
        try:
            year = int(str(pub_year)[:4])
        except (ValueError, TypeError):
            pass

    doi = attr.get("doi")
    landing_url = attr.get("url") or (doi and f"https://doi.org/{doi}")

    abstract = attr.get("descriptions") or []
    if abstract:
        first = abstract[0] if isinstance(abstract, list) else abstract
        if isinstance(first, dict):
            abstract = first.get("description")
        elif isinstance(first, str):
            abstract = first
        else:
            abstract = None
    else:
        abstract = None

    publisher = attr.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")

    # PDF from contentUrl (rare, but sometimes present)
    pdf_url = None
    content = attr.get("contentUrl") or []
    if content:
        first = content[0] if isinstance(content, list) else content
        if isinstance(first, str) and first.lower().endswith(".pdf"):
            pdf_url = first

    # Normalize venue_type from resourceTypeGeneral
    _dc_vt_map = {
        "Journal": "journal",
        "JournalArticle": "journal",
        "ConferencePaper": "conference",
        "Conference": "conference",
        "Book": "book",
        "BookChapter": "book",
        "Dataset": "repository",
        "Software": "repository",
        "Preprint": "repository",
        "Report": "repository",
        "Thesis": "book",
        "Other": "unknown",
        "OutputManagementPlan": "dataset",
        "Workflow": "dataset",
        "Text": "unknown",
        "InteractiveResource": "unknown",
        "Sound": "unknown",
        "Image": "unknown",
        "DataPaper": "dataset",
        "Model": "dataset",
    }
    raw_rtype = attr.get("types", {}).get("resourceTypeGeneral") if isinstance(attr.get("types"), dict) else None
    venue_type = _dc_vt_map.get(raw_rtype, "unknown") if raw_rtype else None

    # Normalize type
    _dc_type_map = {
        "Journal": "journal-article",
        "JournalArticle": "journal-article",
        "ConferencePaper": "conference-paper",
        "Conference": "conference-paper",
        "Book": "book",
        "BookChapter": "book",
        "Dataset": "dataset",
        "Software": "dataset",
        "Preprint": "preprint",
        "Report": "journal-article",
        "Thesis": "book",
        "Text": None,
        "Other": None,
        "DataPaper": "dataset",
        "OutputManagementPlan": "dataset",
        "Workflow": "dataset",
        "Model": "dataset",
    }
    raw_type_val = attr.get("types", {}).get("resourceType") if isinstance(attr.get("types"), dict) else None
    normalized_type = _dc_type_map.get(raw_rtype, None) if raw_rtype else (raw_type_val or None)

    return Paper(
        source="datacite",
        source_id=str(item.get("id", doi or "")),
        title=title,
        authors=authors,
        abstract=abstract or None,
        year=year,
        venue=attr.get("container", {}).get("title") if isinstance(attr.get("container"), dict) else None,
        venue_type=venue_type,
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        is_open_access=None,  # DataCite doesn't flag OA consistently
        type=normalized_type,
        publisher=publisher,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search DataCite DOIs. No API key required."""
    rl = RateLimiter(0.5)
    per_page = min(limit, 50)
    fetched = 0
    page = 1

    while fetched < limit:
        rl.wait()
        params = {
            "query": query,
            "page[size]": min(per_page, limit - fetched),
            "page[number]": page,
            "sort": "-relevance",
        }
        if filters:
            if filters.get("year_from"):
                params["query"] += f" AND publicationYear:[{filters['year_from']} TO *]"

        headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.api+json"}
        data = fetch_json(client, BASE, params=params, headers=headers)
        if not data:
            return
        items = data.get("data") or []
        if not items:
            return
        for item in items:
            paper = _parse(item)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        meta = data.get("meta") or {}
        total = meta.get("totalPages", 0) * per_page
        try:
            total = int(total)
        except (ValueError, TypeError):
            total = 0
        if page * per_page >= total:
            return
        page += 1
