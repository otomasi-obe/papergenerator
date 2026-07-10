"""Fetcher untuk ScienceDirect (Elsevier) - https://dev.elsevier.com

Requires ELSEVIER_API_KEY from https://dev.elsevier.com

NOTE: ScienceDirect Search API requires special entitlement.
If your key lacks SD Search access, use Scopus instead.
"""

import logging
from typing import Iterable

from ..paper import Paper
from ._elsevier import BASE, fetch_paginated, _parse_sd_entry, elsevier_enabled

log = logging.getLogger(__name__)


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    if not elsevier_enabled():
        return iter([])

    params: dict = {"query": query, "sort": "-relevance"}
    if filters:
        if filters.get("year_from") or filters.get("year_to"):
            params["date"] = f"{filters.get('year_from', '1900')}-{filters.get('year_to', '2100')}"
        if filters.get("open_access"):
            params["openaccess"] = "true"

    entries = fetch_paginated(client, f"{BASE}/search/sciencedirect", params, limit, 100)

    # ScienceDirect Search API needs special entitlement; if key lacks it the
    # call returns 401 and we get no entries. Fall back to Scopus (same Elsevier
    # umbrella, same API key) so Elsevier papers still surface.
    if not entries:
        try:
            from .scopus import search as scopus_search
            yield from scopus_search(client, query, limit=limit, filters=filters)
        except Exception as e:
            log.warning("ScienceDirect fallback to Scopus failed: %s", e)
        return

    for entry in entries:
        if entry.get("error"):
            continue
        paper = _parse_sd_entry(entry)
        if paper:
            yield paper
