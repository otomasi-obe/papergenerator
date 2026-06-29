"""Fetcher untuk Gutendex — Project Gutenberg catalog API.

Base: https://gutendex.com/books
Auth: none. Project Gutenberg = 70,000+ free ebooks (public domain).

Excellent for:
  - Full-text public domain books
  - Classic literature in multiple languages
  - Format: txt, epub, html, mobi downloads
"""

import logging
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://gutendex.com/books"

log = logging.getLogger(__name__)


def _parse_book(item: dict) -> Paper | None:
    """Parse Gutendex book into Paper."""
    title = item.get("title")
    if not title:
        return None

    authors = []
    for a in item.get("authors", []):
        name = a.get("name")
        if name:
            authors.append(name)

    # Languages
    langs = item.get("languages", [])
    lang_str = ", ".join(langs) if langs else None

    # Subjects / bookshelves
    subjects = item.get("subjects", [])
    bookshelves = item.get("bookshelves", [])

    # Download formats
    formats = item.get("formats", {})
    url = formats.get("text/html") or formats.get("text/plain") or formats.get("application/epub+zip")
    txt_url = formats.get("text/plain", None)  # PDF not available on Gutendex

    # Download count (NOT citations)
    downloads = item.get("download_count")

    return Paper(
        source="gutendex",
        source_id=str(item.get("id", "")),
        title=title,
        authors=authors,
        abstract=f"Subjects: {', '.join(subjects[:8])}" if subjects else None,
        year=None,
        venue=None,
        venue_type="repository",
        doi=None,
        url=url,
        pdf_url=None,  # Gutendex doesn't serve PDF; text/epub formats are the primary delivery
        citations=None,  # download count is not citations
        is_open_access=True,
        type="book",
        publisher="Project Gutenberg",
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search Project Gutenberg via Gutendex.

    Args:
        query: Search term (supports title and author fields)
        limit: Max results
        filters: {'language': 'en', 'topic': '...', 'author_year_start': 1800}
    """
    rl = RateLimiter(0.3)
    fetched = 0

    # Build search URL
    search_term = query
    if filters:
        if filters.get("topic"):
            search_term = search_term
        if filters.get("language"):
            # Gutendex uses ?languages=en filter
            pass

    page = 1
    while fetched < limit:
        rl.wait()
        params = {
            "search": search_term,
            "page": page,
        }
        if filters:
            if filters.get("language"):
                params["languages"] = filters["language"]
            if filters.get("topic"):
                params["topic"] = filters["topic"]
            if filters.get("author_year_start"):
                params["author_year_start"] = filters["author_year_start"]
            if filters.get("author_year_end"):
                params["author_year_end"] = filters["author_year_end"]

        data = fetch_json(client, BASE, params=params)
        if not data:
            return

        results = data.get("results", [])
        if not results:
            return

        for book in results:
            paper = _parse_book(book)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        if not data.get("next"):
            return
        page += 1
