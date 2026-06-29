"""Fetcher untuk bioRxiv/medRxiv API — preprints biologi & medis.

Base: https://api.biorxiv.org/
No auth required. Returns metadata for preprints including DOI, title,
authors, date, version, category, abstract, and published DOI.

Two endpoints:
  - /details/{server}/{doi}         — single preprint by DOI
  - /details/{server}/{from}/{to}   — date range listing
  - /pubmed/{server}/{doi}          — PubMed IDs linked to preprints

We search via Crossref filter type:posted-content + source:bioRxiv/medRxiv
then enrich with bioRxiv API.
"""

import logging
from typing import Iterable

from ..http_client import RateLimiter, fetch_json, normalize_doi
from ..paper import Paper

BASE = "https://api.biorxiv.org"

log = logging.getLogger(__name__)


def _parse_detail(data: dict) -> Paper | None:
    """Parse a bioRxiv/medRxiv detail response."""
    title = data.get("title")
    if not title:
        return None

    authors_str = data.get("authors", "")
    authors = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []

    year = None
    date_str = data.get("date")
    if date_str:
        try:
            year = int(date_str[:4])
        except (ValueError, TypeError):
            pass

    doi = data.get("doi")
    published_doi = data.get("published")  # DOI of journal version if published

    # Landing page and PDF URL
    server = data.get("server", "biorxiv")
    landing_url = f"https://www.{server}.org/content/{doi}" if doi else None
    pdf_url = f"https://www.{server}.org/content/{doi}v1.full.pdf" if doi else None

    return Paper(
        source="biorxiv",
        source_id=doi or "",
        title=title,
        authors=authors,
        abstract=data.get("abstract"),
        year=year,
        venue=server,
        venue_type="preprint",
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        citations=None,
        is_open_access=True,
        type="preprint",
        publisher="medRxiv" if server == "medrxiv" else "bioRxiv",
    )


def lookup(client, doi: str, server: str = "biorxiv") -> Paper | None:
    """Look up a single preprint by DOI."""
    doi_clean = normalize_doi(doi)
    if not doi_clean:
        return None

    rl = RateLimiter(0.3)
    rl.wait()

    url = f"{BASE}/details/{server}/{doi_clean}"
    data = fetch_json(client, url)
    if not data:
        return None

    collection = data.get("collection", [])
    if not collection:
        return None

    return _parse_detail(collection[0])


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search bioRxiv/medRxiv preprints.

    Strategy: use Crossref to find posted-content on bioRxiv/medRxiv,
    then enrich with bioRxiv API for abstracts.
    Fallback: search Crossref with type filter.
    """
    from .crossref import search as crossref_search

    rl = RateLimiter(0.4)
    fetched = 0
    seen_dois = set()

    # Search via Crossref for bioRxiv/medRxiv posted content
    cr_filters = dict(filters) if filters else {}
    cr_filters["type"] = "posted-content"

    for paper in crossref_search(client, query, limit * 2, cr_filters):
        if not paper.doi:
            continue
        if paper.doi in seen_dois:
            continue

        # Check if it's from bioRxiv or medRxiv
        is_biorxiv = (paper.publisher and
                      any(s in paper.publisher.lower() for s in ["biorxiv", "medrxiv", "cold spring"]))
        if not is_biorxiv and paper.venue:
            is_biorxiv = any(s in paper.venue.lower() for s in ["biorxiv", "medrxiv"])
        if not is_biorxiv:
            continue

        seen_dois.add(paper.doi)

        # Try to enrich from bioRxiv API
        server = "medrxiv" if (paper.publisher and "medrxiv" in paper.publisher.lower()) else "biorxiv"
        rl.wait()
        enriched = lookup(client, paper.doi, server=server)

        if enriched:
            # Merge: keep Crossref abstract if bioRxiv has none
            if not enriched.abstract and paper.abstract:
                enriched.abstract = paper.abstract
            yield enriched
        else:
            # Yield Crossref paper with preprint flag
            paper.source = "biorxiv"
            paper.is_open_access = True
            paper.type = "preprint"
            yield paper

        fetched += 1
        if fetched >= limit:
            return
