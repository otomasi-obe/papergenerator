"""Fetcher untuk Unpaywall API — resolve DOI → Open Access PDF locations.

Not a search engine — used to enrich DOIs with legal OA PDF URLs.
Can also do lightweight "search" by querying Crossref first then resolving via Unpaywall.

Env: SLR_CONTACT_EMAIL (required param for Unpaywall API)
"""

import logging
import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_json, normalize_doi
from ..paper import Paper

BASE = "https://api.unpaywall.org/v2"

log = logging.getLogger(__name__)


def _parse(data: dict) -> Paper | None:
    """Parse Unpaywall response into Paper."""
    title = data.get("title")
    if not title:
        return None

    authors = []
    for a in data.get("author", []) or []:
        given = a.get("given", "")
        family = a.get("family", "")
        full = f"{given} {family}".strip()
        if full:
            authors.append(full)

    doi = data.get("doi")
    year = None
    if data.get("year"):
        try:
            year = int(data["year"])
        except (ValueError, TypeError):
            pass
    if not year and data.get("published_date"):
        try:
            year = int(data["published_date"][:4])
        except (ValueError, TypeError):
            pass

    # Get best OA PDF location
    best = data.get("best_oa_location") or {}
    pdf_url = best.get("url_for_pdf")
    oa_url = best.get("url")

    # Fallback: scan all OA locations for PDF
    if not pdf_url:
        for loc in data.get("oa_locations") or []:
            if loc.get("url_for_pdf"):
                pdf_url = loc["url_for_pdf"]
                break

    # Fallback: DOI landing
    if not pdf_url and doi:
        pdf_url = f"https://doi.org/{doi}"
    if not oa_url and doi:
        oa_url = f"https://doi.org/{doi}"

    # Normalize venue_type from genre
    raw_genre = data.get("genre")
    _uw_vt_map = {
        "journal": "journal",
        "journal article": "journal",
        "primary report": "journal",
        "review article": "journal",
        "book": "book",
        "book chapter": "book",
        "conference": "conference",
        "preprint": "repository",
        "repository": "repository",
        "dataset": "repository",
        "software": "repository",
        "report": "repository",
        "thesis": "book",
    }
    venue_type = _uw_vt_map.get(raw_genre.lower(), "unknown") if isinstance(raw_genre, str) else None

    # Normalize type
    _uw_type_map = {
        "journal": "journal-article",
        "journal article": "journal-article",
        "primary report": "journal-article",
        "review article": "journal-article",
        "book": "book",
        "book chapter": "book",
        "conference": "conference-paper",
        "preprint": "preprint",
        "repository": "preprint",
        "dataset": "dataset",
        "software": "dataset",
        "report": "journal-article",
        "thesis": "book",
    }
    normalized_type = _uw_type_map.get(raw_genre.lower()) if isinstance(raw_genre, str) else None

    is_oa = data.get("is_oa", False)

    return Paper(
        source="unpaywall",
        source_id=doi or "",
        title=title,
        authors=authors,
        abstract=None,  # Unpaywall does not return abstracts
        year=year,
        venue=data.get("journal_name"),
        venue_type=venue_type,
        doi=doi,
        url=oa_url,
        pdf_url=pdf_url if is_oa else None,
        citations=None,
        is_open_access=is_oa,
        type=normalized_type,
        publisher=data.get("publisher"),
    )


def lookup(client, doi: str) -> Paper | None:
    doi_clean = normalize_doi(doi)
    if not doi_clean:
        return None

    email = os.getenv("SLR_CONTACT_EMAIL") or "sirobo@undip.ac.id"
    rl = RateLimiter(0.1)  # 100k/day = ~1.2/sec, we stay conservative
    rl.wait()

    url = f"{BASE}/{doi_clean}"
    params = {"email": email}
    data = fetch_json(client, url, params=params)
    if not data:
        return None
    return _parse(data)


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search Unpaywall indirectly: query Crossref for DOIs, then resolve via Unpaywall.

    Since Unpaywall is a DOI resolver (not a search engine), we use Crossref
    to get candidate DOIs and then enrich each with Unpaywall OA data.
    This gives us papers with guaranteed OA PDF links.
    
    Note: Unpaywall returns 422 for book chapter DOIs and some edge cases.
    We skip those silently.
    """
    from .crossref import search as crossref_search

    rl = RateLimiter(0.15)
    email = os.getenv("SLR_CONTACT_EMAIL") or "sirobo@undip.ac.id"
    fetched = 0

    # Get DOIs from Crossref first
    for paper in crossref_search(client, query, limit * 2, filters):
        if not paper.doi:
            continue

        # Skip book chapters and other known problematic types (422 errors)
        if paper.doi and any(x in paper.doi.lower() for x in ['/oso/', '/cbo/', '/9780', '/978-', 'fmatter']):
            continue

        rl.wait()
        url = f"{BASE}/{paper.doi}"
        params = {"email": email}
        data = fetch_json(client, url, params=params)

        if data and data.get("is_oa"):
            enriched = _parse(data)
            if enriched:
                # Merge abstract from Crossref paper
                if not enriched.abstract and paper.abstract:
                    enriched.abstract = paper.abstract
                yield enriched
                fetched += 1
                if fetched >= limit:
                    return
