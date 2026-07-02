"""Web search fetcher using DuckDuckGo for academic paper discovery.

Strategy:
1. Search DuckDuckGo with academic-focused queries (arxiv, pubmed, PDF, DOI).
2. Classify result URLs by source (arxiv, pubmed, semanticscholar, DOI, PDF, web).
3. Extract paper IDs and delegate to existing fetchers for full metadata.
4. Fall back to landing-page scraping for unknown sources.
5. Deduplicate by DOI/title.

Requires: ddgs (pip install ddgs)
Environment: SLR_DUCKDUCKGO_MAX_RESULTS (default 20)
"""

import logging
import re
from typing import Iterable

from ..http_client import RateLimiter, fetch_text, strip_html, normalize_doi
from ..paper import Paper

try:
    import ddgs
    _DDGS_AVAILABLE = True
except ImportError:
    _DDGS_AVAILABLE = False

log = logging.getLogger(__name__)

# ── URL classification patterns ────────────────────────────────────────

_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)
_PUBMED_URL_RE = re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/(\d+)", re.IGNORECASE)
_DOI_URL_RE = re.compile(r"doi\.org/(10\.\d{4,}/[^\s]+)", re.IGNORECASE)
_PDF_URL_RE = re.compile(r"\.pdf(?:\?|$)", re.IGNORECASE)
_SEMANTICSCHOLAR_URL_RE = re.compile(r"semanticscholar\.org/paper/(?:[^/]+/)?([0-9a-f]{40})", re.IGNORECASE)

# Academic domains that we can scrape for metadata
_ACADEMIC_DOMAINS = frozenset({
    "arxiv.org", "biorxiv.org", "medrxiv.org",
    "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
    "semanticscholar.org",
    "link.springer.com", "nature.com", "science.org",
    "ieee.org", "ieeexplore.ieee.org",
    "acm.org", "dl.acm.org",
    "thelancet.com", "nejm.org", "bmj.com",
    "plos.org", "journals.plos.org",
    "openreview.net",
    "proceedings.neurips.cc", "icml.cc", "iclr.cc",
    "aaai.org", "ijcai.org",
    "sciencedirect.com", "elsevier.com",
    "wiley.com", "onlinelibrary.wiley.com",
    "tandfonline.com", "taylorandfrancis.com",
    "mdpi.com", "www.mdpi.com",
    "frontiersin.org",
    "peerj.com",
    "jstor.org",
    "arxiv.deeppaper.ai",
})

# Domains we can't reliably scrape (paywalled, dynamic)
_SKIP_DOMAINS = frozenset({
    "youtube.com", "youtu.be",
    "twitter.com", "x.com",
    "facebook.com", "instagram.com",
    "reddit.com",
    "github.com", "gitlab.com",
    "researchgate.net",  # often blocks scraping
})


def _classify_url(url: str) -> tuple[str, str]:
    """Classify a URL and extract its ID.

    Returns (source, id) where source is one of:
    'arxiv', 'pubmed', 'doi', 'pdf', 'semanticscholar', 'web', 'skip'
    """
    if any(d in url for d in _SKIP_DOMAINS):
        return "skip", ""

    m = _ARXIV_URL_RE.search(url)
    if m:
        return "arxiv", m.group(1)

    m = _PUBMED_URL_RE.search(url)
    if m:
        return "pubmed", m.group(1)

    m = _DOI_URL_RE.search(url)
    if m:
        return "doi", m.group(1)

    m = _SEMANTICSCHOLAR_URL_RE.search(url)
    if m:
        return "semanticscholar", m.group(1)

    if _PDF_URL_RE.search(url):
        return "pdf", ""

    if any(d in url for d in _ACADEMIC_DOMAINS):
        return "web", ""

    return "web", ""


def _build_search_queries(query: str) -> list[str]:
    """Build multiple academic-focused search queries from a user query.

    Combines the query with academic source hints to surface papers
    from multiple databases.
    """
    # Clean query
    q = query.strip()
    if not q:
        return []

    # Primary: broad academic search
    queries = [
        f"{q} arxiv OR pubmed OR semanticscholar",
        f"{q} filetype:pdf academic paper",
    ]

    # If query looks like a DOI, search for it directly
    doi_match = re.search(r"(10\.\d{4,}/[^\s]+)", q)
    if doi_match:
        queries.insert(0, doi_match.group(1))

    return queries


def _scrape_landing_page(url: str, client) -> Paper | None:
    """Scrape an academic landing page for basic paper metadata.

    Extracts title, authors, abstract, DOI, keywords from meta tags.
    This is a best-effort fallback for sources we don't have a dedicated
    fetcher for.
    """
    try:
        text = fetch_text(client, url, retries=1)
        if not text:
            return None
    except Exception as e:
        log.debug("web: failed to fetch %s: %s", url[:80], e)
        return None

    # Extract from meta tags
    title = _extract_meta(text, [
        "citation_title", "dc.title", "dc.title.alternative",
        "og:title", "twitter:title", "title",
    ])
    if not title:
        return None

    abstract = _extract_meta(text, [
        "citation_abstract", "dc.description", "dc.description.abstract",
        "description", "og:description", "twitter:description",
    ])

    authors = _extract_meta_list(text, [
        "citation_author", "dc.creator", "dc.creator.personalname",
    ])

    doi = _extract_meta(text, [
        "citation_doi", "dc.identifier", "dc.identifier.doi", "doi",
    ])
    if doi:
        doi = normalize_doi(doi)

    keywords = _extract_meta_list(text, [
        "citation_keywords", "citation_keyword", "dc.subject", "keywords",
    ])

    venue = _extract_meta(text, [
        "citation_journal_title", "citation_conference_title",
        "citation_book_title", "dc.publisher",
    ])

    year_str = _extract_meta(text, [
        "citation_publication_date", "citation_date", "dc.date",
        "dc.date.issued", "article:published_time",
    ])
    year = None
    if year_str:
        m = re.search(r"(\d{4})", year_str)
        if m:
            year = int(m.group(1))

    pdf_url = _extract_meta(text, ["citation_pdf_url"])

    return Paper(
        source="web",
        source_id=url,
        title=strip_html(title) or title,
        authors=[strip_html(a) for a in authors] if authors else [],
        abstract=strip_html(abstract) if abstract else None,
        year=year,
        venue=strip_html(venue) if venue else None,
        doi=doi,
        url=url,
        pdf_url=pdf_url or None,
        keywords=[strip_html(k) for k in keywords] if keywords else [],
        is_open_access=None,
    )


def _extract_meta(html: str, keys: list[str]) -> str | None:
    """Extract the first non-empty meta tag content from HTML."""
    for key in keys:
        # Match both name= and property= attributes
        for attr in ("name", "property"):
            pattern = rf'<meta\s+[^>]*{attr}="{re.escape(key)}"[^>]*content="([^"]*)"'
            m = re.search(pattern, html, re.IGNORECASE)
            if m and m.group(1).strip():
                return m.group(1).strip()
            # Also try content before name
            pattern2 = rf'<meta\s+[^>]*content="([^"]*)"[^>]*{attr}="{re.escape(key)}"'
            m2 = re.search(pattern2, html, re.IGNORECASE)
            if m2 and m2.group(1).strip():
                return m2.group(1).strip()
    return None


def _extract_meta_list(html: str, keys: list[str]) -> list[str]:
    """Extract all meta tag values for a list of keys."""
    results = []
    for key in keys:
        for attr in ("name", "property"):
            pattern = rf'<meta\s+[^>]*{attr}="{re.escape(key)}"[^>]*content="([^"]*)"'
            for m in re.finditer(pattern, html, re.IGNORECASE):
                val = m.group(1).strip()
                if val:
                    results.append(val)
    return results


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search academic papers via DuckDuckGo web search.

    Discovers papers from multiple sources (arxiv, pubmed, semanticscholar,
    DOI landing pages, PDFs) and enriches them using existing fetchers
    or landing-page scraping.

    Args:
        client: httpx.Client instance.
        query: Search query (can be keywords, DOI, or paper title).
        limit: Maximum number of papers to return.
        filters: Optional dict with keys:
            - year_from (int): Minimum publication year.
            - year_to (int): Maximum publication year.

    Yields:
        Paper objects with full metadata where available.
    """
    if not _DDGS_AVAILABLE:
        log.warning("web fetcher skipped: ddgs package not installed. Run: pip install ddgs")
        return

    max_results = int(__import__("os").getenv("SLR_DUCKDUCKGO_MAX_RESULTS", "20"))
    queries = _build_search_queries(query)
    if not queries:
        return

    rl = RateLimiter(2.0)  # DuckDuckGo is free but be polite

    # Phase 1: Discover URLs from search results
    discovered: dict[str, tuple[str, str]] = {}  # url -> (source, id)
    with ddgs.DDGS() as ddg:
        for q in queries:
            rl.wait()
            try:
                results = ddg.text(q, max_results=max_results)
                if not results:
                    continue
                for r in results:
                    url = r.get("href", "")
                    if not url:
                        continue
                    source, pid = _classify_url(url)
                    if source == "skip":
                        continue
                    if url not in discovered:
                        discovered[url] = (source, pid)
            except Exception as e:
                log.debug("web: DuckDuckGo query failed (%s): %s", q[:40], e)
                continue

    if not discovered:
        log.info("web: no results for '%s'", query[:60])
        return

    log.info("web: discovered %d candidate URLs for '%s'", len(discovered), query[:60])

    # Phase 2: Group by source and enrich
    arxiv_ids: list[str] = []
    pubmed_ids: list[str] = []
    dois: list[str] = []
    web_urls: list[str] = []

    for url, (source, pid) in discovered.items():
        if source == "arxiv" and pid:
            arxiv_ids.append(pid)
        elif source == "pubmed" and pid:
            pubmed_ids.append(pid)
        elif source == "doi" and pid:
            dois.append(pid)
        elif source == "semanticscholar":
            # We could fetch from S2 API, but let's treat as web for now
            web_urls.append(url)
        elif source == "pdf":
            web_urls.append(url)
        else:
            web_urls.append(url)

    # Phase 3: Fetch full metadata from dedicated fetchers
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()

    def _yield_unique(paper: Paper) -> Paper | None:
        """Deduplicate by DOI or normalized title."""
        if paper.doi:
            doi_key = paper.doi.strip().lower()
            if doi_key in seen_dois:
                return None
            seen_dois.add(doi_key)
        title_key = paper.title.strip().lower()[:80] if paper.title else ""
        if title_key and len(title_key) > 10:
            if title_key in seen_titles:
                return None
            seen_titles.add(title_key)
        return paper

    # 3a: Arxiv batch
    if arxiv_ids:
        try:
            from . import arxiv as arxiv_mod
            batch_query = " OR ".join(arxiv_ids[:10])
            for paper in arxiv_mod.search(client, batch_query, limit=len(arxiv_ids)):
                paper = _yield_unique(paper)
                if paper:
                    yield paper
        except Exception as e:
            log.debug("web: arxiv enrichment failed: %s", e)

    # 3b: PubMed batch
    if pubmed_ids:
        try:
            from . import pubmed as pubmed_mod
            for paper in pubmed_mod.search(client, " OR ".join(pubmed_ids[:5]), limit=len(pubmed_ids)):
                paper = _yield_unique(paper)
                if paper:
                    yield paper
        except Exception as e:
            log.debug("web: pubmed enrichment failed: %s", e)

    # 3c: DOI via CrossRef
    if dois:
        try:
            from . import crossref as crossref_mod
            for doi in dois[:5]:
                m = re.search(r"(10\.\d{4,}/[^\s]+)", doi)
                if m:
                    for paper in crossref_mod.search(client, f"doi:{m.group(1)}", limit=1):
                        paper = _yield_unique(paper)
                        if paper:
                            yield paper
        except Exception as e:
            log.debug("web: crossref enrichment failed: %s", e)

    # 3d: Web scraping fallback for remaining URLs
    for url in web_urls[:limit]:
        try:
            paper = _scrape_landing_page(url, client)
            if paper:
                paper = _yield_unique(paper)
                if paper:
                    yield paper
        except Exception as e:
            log.debug("web: scrape failed for %s: %s", url[:60], e)
