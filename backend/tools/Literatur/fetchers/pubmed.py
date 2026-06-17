"""Fetcher untuk PubMed/MEDLINE - https://www.ncbi.nlm.nih.gov/books/NBK25501/

Free API, no key required (but recommended for higher rate limits).
Set NCBI_API_KEY for 10 req/sec, otherwise limited to 3 req/sec.
"""

import logging
import os
import time
from typing import Iterable
from xml.etree import ElementTree as ET

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

ESEARCH_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _parse_article(article) -> Paper | None:
    """Parse PubmedArticle XML element"""
    medline = article.find(".//MedlineCitation")
    if medline is None:
        return None

    pmid_elem = medline.find(".//PMID")
    pmid = pmid_elem.text if pmid_elem is not None else None

    article_elem = medline.find(".//Article")
    if article_elem is None:
        return None

    title_elem = article_elem.find(".//ArticleTitle")
    title = title_elem.text if title_elem is not None else None
    if not title:
        return None

    # Authors
    authors = []
    author_list = article_elem.find(".//AuthorList")
    if author_list is not None:
        for author in author_list.findall(".//Author"):
            last = author.find("LastName")
            first = author.find("ForeName")
            if last is not None and first is not None:
                authors.append(f"{first.text} {last.text}")
            elif last is not None:
                authors.append(last.text)

    # Abstract
    abstract_elem = article_elem.find(".//Abstract/AbstractText")
    abstract = abstract_elem.text if abstract_elem is not None else None

    # Year
    year = None
    pub_date = article_elem.find(".//Journal/JournalIssue/PubDate/Year")
    if pub_date is not None:
        try:
            year = int(pub_date.text)
        except (ValueError, TypeError):
            pass

    # Venue
    journal = article_elem.find(".//Journal/Title")
    venue = journal.text if journal is not None else None

    # DOI and PMC ID
    doi = None
    pmc_id = None
    article_ids = article.find(".//PubmedData/ArticleIdList")
    if article_ids is not None:
        for aid in article_ids.findall("ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text
            elif aid.get("IdType") == "pmc":
                pmc_id = aid.text

    # Build PDF URL: prioritize PMC free full text, then DOI, then landing page
    pdf_url = None
    if pmc_id:
        # PMC articles have free full text PDFs
        pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
    elif doi:
        # Try DOI resolver (may redirect to publisher)
        pdf_url = f"https://doi.org/{doi}"
    else:
        # Fallback to PubMed landing page
        pdf_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

    return Paper(
        source="pubmed",
        source_id=pmid or "",
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=venue,
        venue_type="journal",
        doi=doi,
        url=pdf_url,
        is_open_access=bool(pmc_id),  # PMC articles are open access
        type="journal-article",
        publisher="NLM",
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Filters: {'year_from': '2020', 'year_to': '2024', 'article_type': 'Journal Article'}
    """
    api_key = os.getenv("NCBI_API_KEY")
    # With key: 10 req/sec, without: 3 req/sec
    rl = RateLimiter(0.1 if api_key else 0.35)

    # Build query
    query_parts = [query]
    if filters:
        if filters.get("year_from") or filters.get("year_to"):
            year_from = filters.get("year_from", "1900")
            year_to = filters.get("year_to", "2100")
            query_parts.append(f"{year_from}:{year_to}[dp]")
        if filters.get("article_type"):
            query_parts.append(f"{filters['article_type']}[pt]")

    full_query = " AND ".join(query_parts)

    # Step 1: Search for PMIDs
    rl.wait()
    search_params = {
        "db": "pubmed",
        "term": full_query,
        "retmax": min(limit, 10000),
        "retmode": "json",
        "sort": "relevance",
    }
    if api_key:
        search_params["api_key"] = api_key

    try:
        search_data = fetch_json(client, ESEARCH_BASE, params=search_params)
        if not search_data:
            logging.getLogger(__name__).warning("PubMed search failed: no response")
            return
    except Exception as e:
        logging.getLogger(__name__).warning(f"PubMed search failed: {e}")
        return

    id_list = search_data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return

    # Step 2: Fetch details in batches
    fetched = 0
    batch_size = 200
    for i in range(0, len(id_list), batch_size):
        if fetched >= limit:
            break

        batch_ids = id_list[i : i + batch_size]
        rl.wait()

        fetch_params = {
            "db": "pubmed",
            "id": ",".join(batch_ids),
            "retmode": "xml",
        }
        if api_key:
            fetch_params["api_key"] = api_key

        try:
            resp = client.get(EFETCH_BASE, params=fetch_params)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as e:
            logging.getLogger(__name__).warning(f"PubMed fetch failed: {e}")
            continue

        for article in root.findall(".//PubmedArticle"):
            paper = _parse_article(article)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
