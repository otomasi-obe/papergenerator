"""Fetcher untuk Google Books API — buku metadata, cover, ISBN lookup.

Base: https://www.googleapis.com/books/v1/volumes
Auth: API key (free tier ~1000 req/day). Without key rate-limited.

Env: GOOGLE_BOOKS_API_KEY or GOOGLE_API_KEY
"""

import logging
import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://www.googleapis.com/books/v1/volumes"

log = logging.getLogger(__name__)


def _parse_volume(item: dict) -> Paper | None:
    """Parse Google Books volume into Paper (book format)."""
    vol_info = item.get("volumeInfo") or {}
    title = vol_info.get("title")
    if not title:
        return None

    subtitle = vol_info.get("subtitle")
    if subtitle:
        title = f"{title}: {subtitle}"

    authors = vol_info.get("authors") or []

    # Abstract from description
    abstract = vol_info.get("description")

    # Year
    year = None
    pub_date = vol_info.get("publishedDate") or ""
    if pub_date:
        try:
            year = int(pub_date[:4])
        except (ValueError, TypeError):
            pass

    # ISBN
    isbn = None
    for ident in vol_info.get("industryIdentifiers") or []:
        if ident.get("type") in ("ISBN_13", "ISBN_10"):
            isbn = ident.get("identifier")
            break

    # Publisher
    publisher = vol_info.get("publisher")

# Categories (subjects) — not the name of the publication venue
    categories = vol_info.get("categories") or []

    # URL — preview or info link
    preview_link = vol_info.get("previewLink")
    info_link = vol_info.get("infoLink")

    # Cover image
    thumbnail = None
    img_links = vol_info.get("imageLinks") or {}
    thumbnail = img_links.get("thumbnail")

    # Page count
    pages = vol_info.get("pageCount")

    return Paper(
        source="google_books",
        source_id=item.get("id", ""),
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=None,  # Books don't have a journal/conference venue
        venue_type="book",
        doi=None,  # Books rarely have DOIs; ISBN is primary identifier
        url=preview_link or info_link,
        pdf_url=None,
        citations=None,
        is_open_access=vol_info.get("accessInfo", {}).get("pdf", {}).get("isAvailable"),
        type="book",
        publisher=publisher,
    )


def lookup_isbn(client, isbn: str) -> Paper | None:
    """Look up a book by ISBN."""
    if not isbn:
        return None

    key = os.getenv("GOOGLE_BOOKS_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    rl = RateLimiter(0.3)
    rl.wait()

    params = {"q": f"isbn:{isbn}"}
    if key:
        params["key"] = key

    data = fetch_json(client, BASE, params=params)
    if not data:
        return None

    items = data.get("items", [])
    if not items:
        return None

    return _parse_volume(items[0])


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search Google Books.

    Args:
        query: Free text search. Supports intitle:, inauthor:, subject: prefixes.
        limit: Max results.
        filters: {'intitle': '...', 'inauthor': '...', 'subject': '...', 'lang': 'en'}
    """
    key = os.getenv("GOOGLE_BOOKS_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
    rl = RateLimiter(0.3)
    per_page = min(limit, 40)
    fetched = 0
    start = 0

    # Build query with special prefixes
    full_query = query
    if filters:
        if filters.get("intitle"):
            full_query = f"intitle:{filters['intitle']} {full_query}"
        if filters.get("inauthor"):
            full_query = f"inauthor:{filters['inauthor']} {full_query}"

    while fetched < limit:
        rl.wait()
        params = {
            "q": full_query,
            "startIndex": start,
            "maxResults": min(per_page, limit - fetched),
        }
        if key:
            params["key"] = key
        if filters:
            if filters.get("lang"):
                params["langRestrict"] = filters["lang"]
            if filters.get("subject"):
                params["q"] = f"subject:{filters['subject']} {params['q']}"

        data = fetch_json(client, BASE, params=params)
        if not data:
            return

        items = data.get("items", [])
        if not items:
            return

        for item in items:
            paper = _parse_volume(item)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        start += len(items)
        if start >= data.get("totalItems", 0):
            return
