"""Fetcher untuk ScienceDirect (Elsevier) - https://dev.elsevier.com

Requires ELSEVIER_API_KEY from https://dev.elsevier.com
Free tier: 5000 requests/week per API key
"""

import logging
import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://api.elsevier.com/content/search/sciencedirect"

_warned = False


def _parse_entry(entry: dict) -> Paper | None:
    title = entry.get("dc:title")
    if not title:
        return None

    authors = []
    authors_data = entry.get("authors", {}).get("author", [])
    if isinstance(authors_data, dict):
        authors_data = [authors_data]
    for a in authors_data:
        name = a.get("$", "").strip()
        if name:
            authors.append(name)

    year = None
    cover_date = entry.get("prism:coverDate")
    if cover_date:
        try:
            year = int(cover_date.split("-")[0])
        except (ValueError, IndexError):
            pass

    doi = entry.get("prism:doi")
    pii = entry.get("pii")

    return Paper(
        source="sciencedirect",
        source_id=pii or doi or "",
        title=title,
        authors=authors,
        abstract=entry.get("dc:description"),
        year=year,
        venue=entry.get("prism:publicationName"),
        venue_type="journal" if entry.get("prism:aggregationType") == "Journal" else None,
        doi=doi,
        url=entry.get("prism:url") or (doi and f"https://doi.org/{doi}"),
        is_open_access=entry.get("openaccess") == "1",
        type=entry.get("prism:aggregationType"),
        publisher="Elsevier",
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Filters: {'year_from': '2020', 'year_to': '2024', 'open_access': True}
    """
    global _warned
    api_key = os.getenv("ELSEVIER_API_KEY")
    if not api_key:
        if not _warned:
            logging.getLogger(__name__).info(
                "sciencedirect fetcher skipped: ELSEVIER_API_KEY not set"
            )
            _warned = True
        return iter([])

    rl = RateLimiter(0.5)  # ~2 req/sec to be safe
    per_page = min(limit, 100)
    fetched = 0
    start = 0

    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json",
    }

    while fetched < limit:
        rl.wait()
        params = {
            "query": query,
            "count": min(per_page, limit - fetched),
            "start": start,
        }

        if filters:
            if filters.get("year_from") or filters.get("year_to"):
                year_from = filters.get("year_from", "1900")
                year_to = filters.get("year_to", "2100")
                params["date"] = f"{year_from}-{year_to}"
            if filters.get("open_access"):
                params["openaccess"] = "true"

        data = fetch_json(client, BASE, params=params, headers=headers)
        if not data:
            return

        results = data.get("search-results", {})
        entries = results.get("entry", [])
        if not entries:
            return

        for entry in entries:
            # Skip error entries
            if entry.get("error"):
                continue
            paper = _parse_entry(entry)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        start += len(entries)
        total = int(results.get("opensearch:totalResults", 0))
        if start >= total:
            return
