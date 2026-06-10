"""Fetcher untuk Springer/Nature - https://dev.springernature.com

Requires SPRINGER_API_KEY from https://dev.springernature.com
Free tier available with rate limits
"""

import logging
import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://api.springernature.com/meta/v2/json"

_warned = False


def _parse_record(record: dict) -> Paper | None:
    title = record.get("title")
    if not title:
        return None

    authors = []
    creators = record.get("creators", [])
    if isinstance(creators, list):
        for creator in creators:
            if isinstance(creator, dict):
                name = creator.get("creator", "").strip()
                if name:
                    authors.append(name)
            elif isinstance(creator, str):
                authors.append(creator.strip())

    year = None
    pub_date = record.get("publicationDate")
    if pub_date:
        try:
            year = int(pub_date.split("-")[0])
        except (ValueError, IndexError):
            pass

    doi = record.get("doi")
    url = record.get("url", [])
    if isinstance(url, list) and url:
        url = url[0].get("value") if isinstance(url[0], dict) else url[0]
    elif isinstance(url, dict):
        url = url.get("value")

    return Paper(
        source="springer",
        source_id=doi or record.get("identifier", ""),
        title=title,
        authors=authors,
        abstract=record.get("abstract"),
        year=year,
        venue=record.get("publicationName"),
        venue_type="journal" if record.get("contentType") == "Article" else None,
        doi=doi,
        url=url or (doi and f"https://doi.org/{doi}"),
        is_open_access=record.get("openaccess") == "true",
        type=record.get("contentType"),
        publisher="Springer Nature",
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Filters: {'subject': 'Computer Science', 'year': '2020-2024'}
    """
    global _warned
    api_key = os.getenv("SPRINGER_API_KEY")
    if not api_key:
        if not _warned:
            logging.getLogger(__name__).info("springer fetcher skipped: SPRINGER_API_KEY not set")
            _warned = True
        return iter([])

    rl = RateLimiter(0.5)  # Conservative rate limit
    per_page = min(limit, 100)
    fetched = 0
    start = 1  # Springer uses 1-based indexing

    while fetched < limit:
        rl.wait()
        params = {
            "q": query,
            "api_key": api_key,
            "p": min(per_page, limit - fetched),
            "s": start,
        }

        if filters:
            if filters.get("subject"):
                params["subject"] = filters["subject"]
            if filters.get("year"):
                params["date"] = filters["year"]

        data = fetch_json(client, BASE, params=params)
        if not data:
            return

        records = data.get("records", [])
        if not records:
            return

        for record in records:
            paper = _parse_record(record)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        start += len(records)
        total = int(data.get("result", [{}])[0].get("total", 0))
        if start > total:
            return
