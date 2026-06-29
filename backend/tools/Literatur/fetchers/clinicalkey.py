"""Fetcher untuk ClinicalKey (Elsevier) - https://www.clinicalkey.com

Requires ELSEVIER_API_KEY from https://dev.elsevier.com
ClinicalKey API tersedia via Elsevier Search API endpoint /search/clinicalKey.
Mencakup buku, bab, clinical overview, drug monograph, guideline, procedure, dll.
"""

import logging
from typing import Iterable

from ..paper import Paper
from ._elsevier import BASE, fetch_paginated, _parse_ck_entry, elsevier_enabled

log = logging.getLogger(__name__)


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    if not elsevier_enabled():
        return iter([])

    params: dict = {"query": query, "sort": "-relevance"}
    if filters:
        if filters.get("year_from") or filters.get("year_to"):
            year_from = filters.get("year_from", "1900")
            year_to = filters.get("year_to", "2100")
            params["date"] = f"{year_from}-{year_to}"
        if filters.get("content_type"):
            params["content_type"] = filters["content_type"]
        if filters.get("open_access"):
            params["openaccess"] = "true"

    entries = fetch_paginated(client, f"{BASE}/search/clinicalKey", params, limit, 100)

    for entry in entries:
        if entry.get("error"):
            continue
        paper = _parse_ck_entry(entry)
        if paper:
            yield paper