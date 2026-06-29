"""Fetcher untuk Embase (Elsevier) - https://www.embase.com

Requires ELSEVIER_API_KEY from https://dev.elsevier.com
Embase API tersedia via Elsevier Search API endpoint /search/embase.
"""

import logging
from typing import Iterable

from ..paper import Paper
from ._elsevier import BASE, fetch_paginated, _parse_embase_entry, elsevier_enabled

log = logging.getLogger(__name__)


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    if not elsevier_enabled():
        return iter([])

    query_parts = [query]
    if filters:
        if filters.get("year_from") or filters.get("year_to"):
            year_from = filters.get("year_from", "1900")
            year_to = filters.get("year_to", "2100")
            query_parts.append(f"PUBYEAR >= {year_from} AND PUBYEAR <= {year_to}")
        if filters.get("subject"):
            query_parts.append(f"SUBJAREA({filters['subject']})")

    params = {"query": " AND ".join(query_parts), "sort": "-relevancy"}
    entries = fetch_paginated(client, f"{BASE}/search/embase", params, limit, 200)

    for entry in entries:
        if entry.get("error"):
            continue
        paper = _parse_embase_entry(entry)
        if paper:
            yield paper