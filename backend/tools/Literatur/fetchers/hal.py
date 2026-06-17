"""Fetcher untuk HAL (Hyper Articles en Ligne) - https://hal.science

https://api.archives-ouvertes.fr/docs/search

Keyless Solr-backed API from CNRS. Aggregates French and international
research from universities, labs, and repositories.
Endpoint: https://api.archives-ouvertes.fr/search/?q=...&wt=json
"""

import logging
from typing import Iterable
from urllib.parse import quote

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://api.archives-ouvertes.fr/search/"


def _parse(doc: dict) -> Paper | None:
    title = doc.get("title_s")
    if isinstance(title, list):
        title = title[0] if title else None
    if not title:
        return None

    authors = []
    for a in doc.get("authFullName_s", []) or []:
        if a:
            authors.append(a.strip())

    year = None
    for yk in ("producedDateY_i", "publicationDateY_i"):
        y = doc.get(yk)
        if y:
            try:
                year = int(str(y)[:4])
                break
            except (ValueError, TypeError):
                pass

    doi_raw = doc.get("doiId_s") or doc.get("doi_s")
    doi = doi_raw if isinstance(doi_raw, str) else (doi_raw[0] if isinstance(doi_raw, list) and doi_raw else None)

    abstract = doc.get("abstract_s")
    if isinstance(abstract, list):
        abstract = " ".join(a for a in abstract if a)

    # HAL provides direct PDF and landing URL
    pdf_url = doc.get("fileMain_s")
    landing = doc.get("uri_s") or (doi and f"https://doi.org/{doi}")
    if pdf_url and not pdf_url.startswith("http"):
        pdf_url = f"https://hal.science/{pdf_url}"

    return Paper(
        source="hal",
        source_id=str(doc.get("docid", "")),
        title=title,
        authors=authors,
        abstract=abstract or None,
        year=year,
        venue=doc.get("journalTitle_s"),
        venue_type="journal" if doc.get("journalTitle_s") else None,
        doi=doi,
        url=landing or pdf_url,
        pdf_url=pdf_url,
        is_open_access=True,  # HAL is a preprint/repository
        type=doc.get("docType_s"),
        publisher=doc.get("publisher_s"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search HAL open archives. No API key required."""
    rl = RateLimiter(0.4)
    per_page = min(limit, 50)
    fetched = 0
    start = 0

    fields = "docid,title_s,abstract_s,authFullName_s,producedDateY_i,journalTitle_s,doiId_s,uri_s,fileMain_s,docType_s,publisher_s"

    while fetched < limit:
        rl.wait()
        params = {
            "q": query,
            "rows": min(per_page, limit - fetched),
            "start": start,
            "wt": "json",
            "fl": fields,
            "sort": "relevance desc",
        }
        if filters:
            if filters.get("year_from"):
                params["fq"] = f"producedDateY_i:[{filters['year_from']} TO *]"

        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        resp = data.get("response") or {}
        docs = resp.get("docs") or []
        if not docs:
            return
        for doc in docs:
            paper = _parse(doc)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        total = resp.get("numFound", 0)
        start += len(docs)
        if start >= total:
            return
