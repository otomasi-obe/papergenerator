"""Fetcher untuk Scopus (Elsevier) - https://dev.elsevier.com

Requires ELSEVIER_API_KEY from https://dev.elsevier.com
Scopus has broader coverage than ScienceDirect (includes non-Elsevier content)
"""

import logging
import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://api.elsevier.com/content/search/scopus"

_warned = False


def _parse_entry(entry: dict) -> Paper | None:
    title = entry.get("dc:title")
    if not title:
        return None

    authors = []
    author_str = entry.get("dc:creator", "")
    if author_str:
        authors.append(author_str)

    year = None
    cover_date = entry.get("prism:coverDate")
    if cover_date:
        try:
            year = int(cover_date.split("-")[0])
        except (ValueError, IndexError):
            pass

    doi = entry.get("prism:doi")
    scopus_id = entry.get("dc:identifier", "").replace("SCOPUS_ID:", "")

    # Determine venue type
    venue_type = None
    agg_type = entry.get("prism:aggregationType", "").lower()
    if "journal" in agg_type:
        venue_type = "journal"
    elif "conference" in agg_type:
        venue_type = "conference"
    elif "book" in agg_type:
        venue_type = "book"

    return Paper(
        source="scopus",
        source_id=scopus_id,
        title=title,
        authors=authors,
        abstract=None,  # Scopus search API doesn't return abstracts
        year=year,
        venue=entry.get("prism:publicationName"),
        venue_type=venue_type,
        doi=doi,
        url=entry.get("link", [{}])[0].get("@href") if entry.get("link") else None,
        citations=int(entry.get("citedby-count", 0)) if entry.get("citedby-count") else None,
        is_open_access=entry.get("openaccess") == "1",
        type=entry.get("prism:aggregationType"),
        publisher=entry.get("dc:publisher"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Filters: {'year_from': '2020', 'year_to': '2024', 'subject': 'COMP'}
    Subject codes: COMP (Computer Science), ENGI (Engineering), MEDI (Medicine), etc.
    """
    global _warned
    api_key = os.getenv("ELSEVIER_API_KEY")
    if not api_key:
        if not _warned:
            logging.getLogger(__name__).info("scopus fetcher skipped: ELSEVIER_API_KEY not set")
            _warned = True
        return iter([])

    rl = RateLimiter(0.5)  # ~2 req/sec
    per_page = min(limit, 200)
    fetched = 0
    start = 0

    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json",
    }

    # Build query with filters
    query_parts = [query]
    if filters:
        if filters.get("year_from") or filters.get("year_to"):
            year_from = filters.get("year_from", "1900")
            year_to = filters.get("year_to", "2100")
            query_parts.append(f"PUBYEAR >= {year_from} AND PUBYEAR <= {year_to}")
        if filters.get("subject"):
            query_parts.append(f"SUBJAREA({filters['subject']})")

    full_query = " AND ".join(query_parts)

    while fetched < limit:
        rl.wait()
        params = {
            "query": full_query,
            "count": min(per_page, limit - fetched),
            "start": start,
            "sort": "-relevancy",
        }

        data = fetch_json(client, BASE, params=params, headers=headers)
        if not data:
            return

        results = data.get("search-results", {})
        entries = results.get("entry", [])
        if not entries:
            return

        for entry in entries:
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
