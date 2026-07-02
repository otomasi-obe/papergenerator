"""Fetcher untuk PubMed/MEDLINE - https://www.ncbi.nlm.nih.gov/books/NBK25501/

Free API, no key required (but recommended for higher rate limits).
Set NCBI_API_KEY for 10 req/sec, otherwise limited to 3 req/sec.
"""

import logging
import os
import re
from typing import Iterable
from defusedxml import ElementTree as ET

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

ESEARCH_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# PublicationType rules — checked in order, first match wins
_PAPER_TYPE_RULES = [
    ("congress", "inproceedings"),
    ("academic dissertation", "dissertation"),
    ("technical report", "technical-report"),
    ("preprint", "preprint"),
    ("systematic review", "systematic-review"),
    ("meta-analysis", "meta-analysis"),
    ("review", "review"),
    ("journal article", "journal-article"),
]

# Retraction / correction detection
_RETRACTION_RE = re.compile(r"retract|correct", re.IGNORECASE)


def _normalize_month(month: str) -> str:
    """Normalize month string (number or name) to two-digit string."""
    _month_map = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    lowered = month.lower()[:3]
    if lowered in _month_map:
        return _month_map[lowered]
    try:
        return f"{int(month):02d}"
    except ValueError:
        return "01"


def _parse_date_element(el) -> int | None:
    """Parse year from XML date element (Year/Month/Day). Returns year int or None."""
    year_text = (el.findtext("Year") or "").strip()
    if not year_text:
        return None
    try:
        return int(year_text)
    except (ValueError, TypeError):
        return None


def _parse_pub_date(article, medline) -> int | None:
    """Resolve publication year. Prefers ArticleDate (electronic) over PubDate (print)."""
    article_date = article.find("ArticleDate")
    if article_date is not None:
        year = _parse_date_element(article_date)
        if year is not None:
            return year
    pub_date = medline.find(".//PubDate")
    if pub_date is not None:
        return _parse_date_element(pub_date)
    return None


def _parse_keywords_and_subjects(article_el) -> tuple[list[str], list[str]]:
    """Extract keywords (KeywordList + MeSH non-major) and subjects (MeSH MajorTopic).

    Returns (keywords, subjects) where:
    - keywords: from <Keyword> elements + DescriptorName where MajorTopicYN != 'Y'
    - subjects: from DescriptorName where MajorTopicYN == 'Y'
    """
    keywords: list[str] = []
    seen_kw: set[str] = set()
    for kw_el in article_el.findall(".//Keyword"):
        kw = (kw_el.text or "").strip()
        if kw and kw not in seen_kw:
            seen_kw.add(kw)
            keywords.append(kw)
    for mh_el in article_el.findall(".//MeshHeading/DescriptorName"):
        if mh_el.get("MajorTopicYN") != "Y":
            kw = (mh_el.text or "").strip()
            if kw and kw not in seen_kw:
                seen_kw.add(kw)
                keywords.append(kw)
    subjects: list[str] = []
    seen_subj: set[str] = set()
    for mh_el in article_el.findall(".//MeshHeading/DescriptorName"):
        if mh_el.get("MajorTopicYN") == "Y":
            descriptor = (mh_el.text or "").strip()
            if descriptor and descriptor not in seen_subj:
                seen_subj.add(descriptor)
                subjects.append(descriptor)
    return keywords, subjects


def _parse_paper_type(article) -> tuple[str, bool]:
    """Detect paper type and retraction status from PublicationTypeList.

    Returns (type, is_retracted).
    """
    pub_type_texts = [
        (pt_el.text or "").strip().lower()
        for pt_el in article.findall(".//PublicationTypeList/PublicationType")
        if pt_el.text
    ]
    paper_type = "journal-article"  # default
    for rule_key, rule_val in _PAPER_TYPE_RULES:
        if any(rule_key in pt for pt in pub_type_texts):
            paper_type = rule_val
            break
    is_retracted = bool(_RETRACTION_RE.search(" ".join(pub_type_texts)))
    return paper_type, is_retracted


def _parse_funders(article_el) -> list[str]:
    """Extract funder/agency names from GrantList."""
    funders: list[str] = []
    seen: set[str] = set()
    for grant_el in article_el.findall(".//GrantList/Grant"):
        agency = (grant_el.findtext("Agency") or "").strip()
        if agency and agency not in seen:
            seen.add(agency)
            funders.append(agency)
    return funders


def _parse_affiliations(article) -> list[str]:
    """Extract all unique author affiliations from Article element."""
    affs: list[str] = []
    seen: set[str] = set()
    for author_el in article.findall(".//AuthorList/Author"):
        for aff_el in author_el.findall(".//AffiliationInfo/Affiliation"):
            aff = (aff_el.text or "").strip()
            if aff and aff not in seen:
                seen.add(aff)
                affs.append(aff)
    return affs


def _parse_article(article) -> Paper | None:
    """Parse PubmedArticle XML element into a Paper."""
    medline = article.find(".//MedlineCitation")
    if medline is None:
        return None

    pmid_elem = medline.find(".//PMID")
    pmid = pmid_elem.text if pmid_elem is not None else None

    article_elem = medline.find(".//Article")
    if article_elem is None:
        return None

    title_elem = article_elem.find(".//ArticleTitle")
    title = "".join(title_elem.itertext()) if title_elem is not None else None
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

    # Abstract — join ALL AbstractText sections with itertext (handles structured abstracts)
    abstract_parts = []
    for at in article_elem.findall(".//Abstract/AbstractText"):
        label = at.get("Label", "")
        full = "".join(at.itertext())
        if label:
            abstract_parts.append(f"{label}: {full}")
        else:
            abstract_parts.append(full)
    abstract = " ".join(abstract_parts) if abstract_parts else None

    # Year — prefer ArticleDate (electronic) over PubDate (print)
    year = _parse_pub_date(article_elem, medline)

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

    # Language
    lang_elem = article_elem.find(".//Language")
    language = lang_elem.text.strip() if lang_elem is not None and lang_elem.text else None

    # Paper type and retraction detection
    paper_type, is_retracted = _parse_paper_type(article_elem)

    # Keywords and MeSH subjects
    keywords, subjects = _parse_keywords_and_subjects(article)

    # Funders
    funders = _parse_funders(article)

    # Author affiliations
    affiliations = _parse_affiliations(article_elem)

    # Build landing page URL
    landing_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

    # Build PDF URL: prioritize PMC free full text, then DOI
    pdf_url = None
    if pmc_id:
        pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
    elif doi:
        pdf_url = f"https://doi.org/{doi}"

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
        url=landing_url,
        pdf_url=pdf_url,
        is_open_access=bool(pmc_id),  # PMC articles are open access
        type=paper_type,
        publisher="NLM",
        keywords=keywords,
        subjects=subjects if subjects else None,
        affiliations=affiliations if affiliations else None,
        language=language,
        is_retracted=is_retracted,
        funders=funders,
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
