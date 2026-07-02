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

    bioRxiv API does not support text search — only date-range queries.
    Strategy: get recent preprints from last 30 days, filter client-side
    by query keywords, then enrich via bioRxiv API.

    Fallback: use Crossref to find bioRxiv/medRxiv DOIs, then enrich.
    """
    import datetime as _dt
    from .crossref import search as crossref_search

    rl = RateLimiter(0.4)
    fetched = 0
    seen_dois = set()

    query_terms = [t.lower() for t in query.split() if len(t) > 3]
    if not query_terms:
        query_terms = [query.lower()]

    # Strategy 1: Get recent preprints via date-range API (broad sweep)
    try:
        today = _dt.date.today()
        # Sweep last 30 days in chunks of 7 days
        for day_offset in range(30, 0, -7):
            if fetched >= limit:
                return
            end_dt = today - _dt.timedelta(days=day_offset)
            start_dt = end_dt - _dt.timedelta(days=6)
            start_str = start_dt.strftime("%Y-%m-%d")
            end_str = end_dt.strftime("%Y-%m-%d")

            rl.wait()
            url = f"{BASE}/details/biorxiv/{start_str}/{end_str}"
            data = fetch_json(client, url)
            if not data:
                collection = []
            else:
                collection = data.get("collection", [])

            for item in collection:
                if fetched >= limit:
                    return
                title = (item.get("title") or "").lower()
                abstract = (item.get("abstract") or "").lower()
                haystack = f"{title} {abstract}"

                # Client-side keyword filter: match at least 1 term
                if not any(t in haystack for t in query_terms):
                    continue

                doi = item.get("doi")
                if doi and doi in seen_dois:
                    continue
                if doi:
                    seen_dois.add(doi)

                paper = _parse_detail(item)
                if paper:
                    yield paper
                    fetched += 1

            if fetched >= limit:
                return

            # Also check medRxiv
            rl.wait()
            url_m = f"{BASE}/details/medrxiv/{start_str}/{end_str}"
            data_m = fetch_json(client, url_m)
            if not data_m:
                collection_m = []
            else:
                collection_m = data_m.get("collection", [])

            for item in collection_m:
                if fetched >= limit:
                    return
                title = (item.get("title") or "").lower()
                abstract = (item.get("abstract") or "").lower()
                haystack = f"{title} {abstract}"

                if not any(t in haystack for t in query_terms):
                    continue

                doi = item.get("doi")
                if doi and doi in seen_dois:
                    continue
                if doi:
                    seen_dois.add(doi)

                paper = _parse_detail(item)
                if paper:
                    yield paper
                    fetched += 1

    except Exception as e:
        log.warning("biorxiv date-range error: %s", e)

    # Strategy 2: Fallback via Crossref
    if fetched >= limit:
        return

    cr_filters = dict(filters) if filters else {}
    cr_filters["type"] = "posted-content"
    cr_filters["from-date"] = (_dt.date.today() - _dt.timedelta(days=365)).strftime("%Y-%m-%d")

    for paper in crossref_search(client, query, limit * 3, cr_filters):
        if fetched >= limit:
            return
        if not paper.doi:
            continue
        if paper.doi in seen_dois:
            continue

        is_biorxiv = (paper.publisher and
                      any(s in paper.publisher.lower() for s in ["biorxiv", "medrxiv", "cold spring"]))
        if not is_biorxiv and paper.venue:
            is_biorxiv = any(s in paper.venue.lower() for s in ["biorxiv", "medrxiv"])
        if not is_biorxiv:
            continue

        seen_dois.add(paper.doi)

        server = "medrxiv" if (paper.publisher and "medrxiv" in paper.publisher.lower()) else "biorxiv"
        rl.wait()
        enriched = lookup(client, paper.doi, server=server)

        if enriched:
            if not enriched.abstract and paper.abstract:
                enriched.abstract = paper.abstract
            yield enriched
        else:
            paper.source = "biorxiv"
            paper.is_open_access = True
            paper.type = "preprint"
            yield paper

        fetched += 1
