"""Fetcher untuk Open Library API (Internet Archive) — buku metadata + cover.

Base: https://openlibrary.org/
Auth: none (free, no key). NOT for bulk/backend use — real-time low-volume only.
For bulk: use monthly data dumps.

Endpoints:
  - /search.json?q=...     — search works
  - /isbn/{isbn}.json      — lookup by ISBN
  - /authors/{olid}.json   — author details
  - /works/{olid}.json     — work details
  - Covers API: https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg
"""

import logging
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://openlibrary.org"
COVERS = "https://covers.openlibrary.org"

log = logging.getLogger(__name__)
_WARNED = False


def _parse_doc(doc: dict) -> Paper | None:
    """Parse Open Library search document into Paper (book)."""
    title = doc.get("title")
    if not title:
        return None

    authors = doc.get("author_name") or []
    if isinstance(authors, str):
        authors = [authors]

    year = None
    first_pub = doc.get("first_publish_year")
    pub_years = doc.get("publish_year")
    if first_pub:
        year = first_pub
    elif pub_years and isinstance(pub_years, list):
        year = pub_years[0]

    # ISBN
    isbn_list = doc.get("isbn") or []
    isbn = isbn_list[0] if isbn_list else None

    # Cover
    cover_id = doc.get("cover_i")
    cover_url = None
    if cover_id:
        cover_url = f"{COVERS}/b/id/{cover_id}-M.jpg"
    elif isbn:
        cover_url = f"{COVERS}/b/isbn/{isbn}-L.jpg"

    # Subject (NOT abstract — subjects are topics, not abstracts)
    subjects = doc.get("subject") or []

    # URL
    key = doc.get("key", "")
    url = f"{BASE}{key}" if key else None

    # Publisher: handle both list and string cases
    publisher_raw = doc.get("publisher")
    if isinstance(publisher_raw, list):
        publisher = publisher_raw[0] if publisher_raw else None
    elif isinstance(publisher_raw, str):
        publisher = publisher_raw
    else:
        publisher = None

    return Paper(
        source="open_library",
        source_id=doc.get("edition_key", [""])[0] if doc.get("edition_key") else key.strip("/"),
        title=title,
        authors=authors,
        abstract=None,  # Open Library search doesn't provide abstracts; subjects ≠ abstract
        year=year,
        venue=None,
        venue_type="book",
        doi=None,
        url=url,
        pdf_url=None,
        citations=None,
        is_open_access=(doc.get("ebook_access") == "public"),
        type="book",
        publisher=publisher,
    )


def lookup_isbn(client, isbn: str) -> Paper | None:
    """Look up a book by ISBN."""
    if not isbn:
        return None
    # Strip dashes
    isbn = isbn.replace("-", "").replace(" ", "")

    rl = RateLimiter(0.3)
    rl.wait()

    data = fetch_json(client, f"{BASE}/isbn/{isbn}.json")
    if not data:
        return None

    title = data.get("title")
    if not title:
        return None

    authors = []
    for a in data.get("authors") or []:
        name = a.get("name", "")
        if name:
            authors.append(name)

    year = data.get("publish_date", "")
    if year and isinstance(year, str) and year[:4].isdigit():
        year = int(year[:4])
    else:
        year = None

    # Cover
    cover_url = None
    if data.get("covers"):
        cover_id = data["covers"][0]
        cover_url = f"{COVERS}/b/id/{cover_id}-M.jpg"

    isbn_13 = None
    isbn_list = data.get("isbn_13") or []
    if isinstance(isbn_list, list) and isbn_list:
        isbn_13 = isbn_list[0]
    elif isinstance(isbn_list, str):
        isbn_13 = isbn_list

    return Paper(
        source="open_library",
        source_id=isbn_13 or data.get("key", "").strip("/"),
        title=title,
        authors=authors,
        abstract=data.get("description", {}).get("value") if isinstance(data.get("description"), dict) else data.get("description"),
        year=year,
        venue=None,
        venue_type="book",
        doi=None,
        url=f"{BASE}/book/{data.get('key', '').strip('/')}",
        pdf_url=None,
        citations=None,
        is_open_access=False,
        type="book",
        publisher=", ".join(data.get("publishers") or []) if isinstance(data.get("publishers"), list) else data.get("publishers"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search Open Library. NOT for bulk — use data dumps for bulk.

    IMPORTANT: Open Library API policy restricts backend/bulk usage.
    This is for real-time, low-volume searches only.
    """
    global _WARNED
    if not _WARNED:
        log.info(
            "open_library: real-time only (low-volume). For bulk use monthly dumps: "
            "https://openlibrary.org/developers/dumps"
        )
        _WARNED = True

    rl = RateLimiter(0.5)
    fetched = 0
    page = 1

    while fetched < limit:
        rl.wait()
        params = {
            "q": query,
            "limit": min(limit - fetched, 100),
            "page": page,
        }
        if filters and filters.get("subject"):
            params["subject"] = filters["subject"]
        if filters and filters.get("author"):
            params["author"] = filters["author"]

        data = fetch_json(client, f"{BASE}/search.json", params=params)
        if not data:
            return

        docs = data.get("docs", [])
        if not docs:
            return

        for doc in docs:
            paper = _parse_doc(doc)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        page += 1
