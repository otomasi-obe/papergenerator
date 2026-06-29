"""Fetcher untuk PubMed Central (PMC) — full-text biomedis OA.

Uses E-utilities (esearch + efetch) to find and retrieve PMC articles.
Full-text available as JATS XML for OA subset.

Base: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
PMC-specific: PMC ID (PMCID) for full-text retrieval.
"""

import logging
import os
import re
from typing import Iterable

from ..http_client import RateLimiter, fetch_json, fetch_text, strip_html
from ..paper import Paper

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESUMMARY = f"{EUTILS}/esummary.fcgi"
ESEARCH = f"{EUTILS}/esearch.fcgi"
EFETCH = f"{EUTILS}/efetch.fcgi"

log = logging.getLogger(__name__)


def _parse_esummary(doc: dict) -> Paper | None:
    """Parse PMC esummary document."""
    uid = doc.get("uid", "")
    if not uid:
        return None

    title = doc.get("title")
    if not title:
        return None

    # Authors
    authors = []
    author_list = doc.get("authors") or []
    if isinstance(author_list, list):
        for a in author_list:
            name = a.get("name") if isinstance(a, dict) else str(a)
            if name:
                authors.append(name)

    # Year
    year = None
    pub_date = doc.get("pubdate", "")
    if pub_date:
        m = re.search(r"(\d{4})", pub_date)
        if m:
            year = int(m.group(1))

    # Journal
    journal = doc.get("source") or doc.get("fulljournalname")

    # DOI from articleids
    doi = None
    pmcid = f"PMC{uid}"
    pmid = None
    for aid in doc.get("articleids") or []:
        idtype = aid.get("idtype") or aid.get("name", "")
        idval = aid.get("value", "")
        if idtype in ("doi", "DOI"):
            doi = idval
        elif idtype == "pmid":
            pmid = idval
        elif idtype == "pmcid":
            pmcid = idval if idval.startswith("PMC") else f"PMC{idval}"

    # PDF URL from PMC
    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"

    return Paper(
        source="pmc",
        source_id=pmcid,
        title=strip_html(title),
        authors=authors,
        abstract=None,  # esummary doesn't include abstract; enrich later
        year=year,
        venue=strip_html(journal) if journal else None,
        venue_type="journal",
        doi=doi,
        url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
        pdf_url=pdf_url,
        citations=None,
        is_open_access=True,
        type="journal-article",
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search PMC for full-text OA biomedical articles.

    Uses esearch to get PMC IDs, then esummary for metadata.
    """
    api_key = os.getenv("NCBI_API_KEY", "")
    email = os.getenv("SLR_CONTACT_EMAIL") or "research@example.com"

    # Rate limit: 3/sec without key, 10/sec with key
    rl = RateLimiter(0.35 if not api_key else 0.12)
    fetched = 0

    # Build search query
    full_query = query
    if filters:
        if filters.get("year"):
            full_query += f" AND {filters['year']}[pdat]"
        if filters.get("journal"):
            full_query += f" AND {filters['journal']}[journal]"

    # Step 1: esearch to get PMC IDs
    rl.wait()
    search_params = {
        "db": "pmc",
        "term": full_query,
        "retmax": limit,
        "retmode": "json",
        "sort": "relevance",
        "tool": "PaperRiset",
        "email": email,
    }
    if api_key:
        search_params["api_key"] = api_key

    search_data = fetch_json(client, ESEARCH, params=search_params)
    if not search_data:
        return

    esearch_result = search_data.get("esearchresult", {})
    id_list = esearch_result.get("idlist", [])
    if not id_list:
        return

    # Step 2: esummary for metadata
    rl.wait()
    summary_params = {
        "db": "pmc",
        "id": ",".join(id_list),
        "retmode": "json",
        "tool": "PaperRiset",
        "email": email,
    }
    if api_key:
        summary_params["api_key"] = api_key

    summary_data = fetch_json(client, ESUMMARY, params=summary_params)
    if not summary_data:
        return

    result = summary_data.get("result", {})
    uids = result.get("uids", [])

    for uid in uids:
        doc = result.get(uid)
        if not doc or not isinstance(doc, dict):
            continue
        paper = _parse_esummary(doc)
        if paper:
            # Enrich abstract from PubMed if DOI available
            if not paper.abstract and paper.doi:
                from .openalex import enrich_abstract_via_doi
                paper.abstract = enrich_abstract_via_doi(paper.doi, client)
            yield paper
            fetched += 1
            if fetched >= limit:
                return
