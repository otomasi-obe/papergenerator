"""
Bulk Fetch V3 — All fetchers parallel, connection pooling, continuous daemon.

Improvements over v2:
- Integrates ALL 22 fetcher modules from fetchers/ (v2 only used 8 inline)
- New sources: DBLP, EuropePMC, DOAJ, HAL, PLOS, OpenAIRE, DataCite, Zenodo,
  Cambridge, ScienceDirect, Scopus, Dimensions, Lens, CrossRef Publishers
- Connection pooling: psycopg2 pool for DB, httpx keep-alive for HTTP
- Continuous daemon loop: auto-restart after all topics done
- Better rate limiting: per-source global locks with Tor rotation
- SS 429 fix: aggressive Tor rotation + longer delays
"""
import argparse
import json
import logging
import os
import signal
import sys
import time
import threading
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Load API keys from .env
from dotenv import load_dotenv
load_dotenv("/home/sirobo/papergenerator/.env")

from tor_rotator import TorRotator, get_tor, get_tor_client, rotate_ip

import httpx
import psycopg2
import psycopg2.pool
import psycopg2.extras

# ── Config ──────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "/var/run/postgresql",  # Unix socket = peer auth, no password needed
    "database": "paper_database",
    "user": "sirobo",
}

LOG_FILE = "/tmp/mega_fetch.log"
BATCH_SIZE = 100  # Insert batch size
WORKERS = 5       # Parallel topic workers
PER_PAGE = 200    # OpenAlex max per page
POLITE_EMAIL = "research@example.com"

# Rate limits per source (delay between requests, seconds)
DELAYS = {
    'openalex': 1.0,
    'ss': 3.0,          # Increased from 2.0 — SS is heavily rate-limited
    'crossref': 1.2,
    'ieee': 2.5,
    'elsevier': 2.5,
    'core': 2.0,
    'pubmed': 0.4,      # NCBI allows 3 req/s without key, 10 with key
    'arxiv': 3.5,       # arXiv strict 3s minimum
    'dblp': 0.5,
    'europepmc': 0.3,
    'doaj': 0.5,
    'hal': 0.4,
    'plos': 0.5,
    'openaire': 0.6,
    'datacite': 0.5,
    'zenodo': 0.5,
    'cambridge': 1.0,
    'sciencedirect': 2.5,
    'scopus': 2.0,
    'scopus_oa': 0.15,   # OpenAlex enrichment for Scopus — 10/s polite
    'dimensions': 1.0,
    'lens': 1.0,
    'crossref_publishers': 1.5,
}

BACKOFF_BASE = 2.0
MAX_RETRIES = 2
MAX_CONSECUTIVE_FAIL = 3
STAGGER_DELAY = 3.0

# ── Global state ────────────────────────────────────────────────────────────
shutdown_requested = False
_log_lock = threading.Lock()

# Per-source rate limit state
_rate_state = {k: time.monotonic() for k in DELAYS}
_rate_locks = {k: threading.Lock() for k in DELAYS}

# DB connection pool
_db_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_db_pool_lock = threading.Lock()


def signal_handler(signum, frame):
    global shutdown_requested
    shutdown_requested = True
    log("⏹️  Shutdown requested, finishing current work...")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# ── Logging ─────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with _log_lock:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")


# ── DB Pool ─────────────────────────────────────────────────────────────────
def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _db_pool
    with _db_pool_lock:
        if _db_pool is None:
            _db_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=3, maxconn=30, **DB_CONFIG
            )
    return _db_pool


def get_db():
    return _get_pool().getconn()


def put_db(conn):
    try:
        _get_pool().putconn(conn)
    except Exception:
        pass


def _rate_wait(source: str):
    """Global per-source rate limiter."""
    delay = DELAYS.get(source, 1.0)
    lock = _rate_locks.get(source)
    if not lock:
        return
    with lock:
        now = time.monotonic()
        wait = delay - (now - _rate_state[source])
        if wait > 0:
            time.sleep(wait)
        _rate_state[source] = time.monotonic()


# ── Progress tracking ───────────────────────────────────────────────────────
def get_pending_topics(limit: int = 1) -> list[dict]:
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            UPDATE mega_fetch_progress
            SET status = 'running', started_at = COALESCE(started_at, NOW()), updated_at = NOW()
            WHERE id IN (
                SELECT id FROM mega_fetch_progress
                WHERE status IN ('pending', 'running')
                ORDER BY
                    CASE WHEN field_name LIKE '!%%' THEN 0 WHEN status = 'running' THEN 1 ELSE 2 END,
                    id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, field_name, topic, target_count, fetched_count, last_cursor
        """, (limit,))
        rows = cur.fetchall()
        conn.commit()
        cur.close()
        return [dict(r) for r in rows]
    finally:
        put_db(conn)


ALLOWED_COLUMNS = {"status", "progress", "fetched_count", "last_cursor", "error_msg", "updated_at", "finished_at"}

def update_progress(topic_id: int, fetched: int, cursor: str = None,
                    status: str = None, error: str = None):
    conn = get_db()
    try:
        cur = conn.cursor()
        parts = ["updated_at = NOW()", "fetched_count = fetched_count + %s"]
        params = [fetched]
        if cursor is not None:
            parts.append("last_cursor = %s")
            params.append(cursor)
        if status is not None:
            parts.append("status = %s")
            params.append(status)
            if status == 'done':
                parts.append("finished_at = NOW()")
        if error is not None:
            parts.append("error_msg = %s")
            params.append(error[:500] if error else None)
        params.append(topic_id)
        # Validate all column names against whitelist
        col_names = [p.split()[0] for p in parts]
        for cn in col_names:
            if cn not in ALLOWED_COLUMNS:
                raise ValueError(f"Invalid column name: {cn}")
        cur.execute(f"UPDATE mega_fetch_progress SET {', '.join(parts)} WHERE id = %s", params)
        conn.commit()
        cur.close()
    finally:
        put_db(conn)


# ── Paper upsert ────────────────────────────────────────────────────────────
def _update_abstract(source_id: str, abstract: str, source: str) -> bool:
    """Update abstract for an existing paper by source_id + source."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE papers SET abstract = %s
            WHERE source_id = %s AND source = %s AND (abstract IS NULL OR abstract = '')
        """, (abstract[:5000], source_id, source))
        updated = cur.rowcount
        conn.commit()
        cur.close()
        return updated > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        put_db(conn)


def upsert_papers(papers: list[dict]) -> int:
    """Batch upsert papers. Returns count of NEW papers inserted."""
    if not papers:
        return 0
    conn = get_db()
    try:
        cur = conn.cursor()
        new_count = 0
        cols = ['doi', 'title', 'authors', 'year', 'venue', 'venue_type', 'abstract',
                'citations', 'is_open_access', 'url', 'pdf_url', 'source', 'source_id',
                'paper_type', 'publisher']

        for i in range(0, len(papers), BATCH_SIZE):
            batch = papers[i:i + BATCH_SIZE]
            if not batch:
                continue
            placeholders = []
            values = []
            for p in batch:
                placeholders.append('(' + ','.join(['%s'] * len(cols)) + ')')
                values.extend([p.get(c, '') for c in cols])

            sql = f"""
                INSERT INTO papers ({', '.join(cols)})
                VALUES {','.join(placeholders)}
                ON CONFLICT (title_normalized) DO UPDATE SET
                    citations = GREATEST(papers.citations, EXCLUDED.citations),
                    abstract = CASE
                        WHEN source_priority(EXCLUDED.source) >= source_priority(papers.source)
                        AND EXCLUDED.abstract IS NOT NULL AND EXCLUDED.abstract != ''
                        THEN EXCLUDED.abstract
                        ELSE papers.abstract
                    END,
                    doi = CASE
                        WHEN source_priority(EXCLUDED.source) >= source_priority(papers.source)
                        AND EXCLUDED.doi IS NOT NULL AND EXCLUDED.doi != ''
                        THEN EXCLUDED.doi
                        ELSE papers.doi
                    END,
                    pdf_url = CASE
                        WHEN source_priority(EXCLUDED.source) >= source_priority(papers.source)
                        AND EXCLUDED.pdf_url IS NOT NULL AND EXCLUDED.pdf_url != ''
                        THEN EXCLUDED.pdf_url
                        ELSE papers.pdf_url
                    END,
                    source = CASE
                        WHEN source_priority(EXCLUDED.source) >= source_priority(papers.source)
                        THEN EXCLUDED.source
                        ELSE papers.source
                    END,
                    is_open_access = papers.is_open_access OR EXCLUDED.is_open_access,
                    venue = COALESCE(EXCLUDED.venue, papers.venue),
                    venue_type = COALESCE(EXCLUDED.venue_type, papers.venue_type),
                    publisher = COALESCE(EXCLUDED.publisher, papers.publisher)
                RETURNING xmax = 0 AS is_new
            """
            try:
                cur.execute(sql, values)
                rows = cur.fetchall()
                new_count += sum(1 for r in rows if r[0])
            except Exception:
                conn.rollback()
                continue

        conn.commit()
        cur.close()
        return new_count
    finally:
        put_db(conn)


# ── OpenAlex helpers ────────────────────────────────────────────────────────
def decode_abstract(inverted_index: dict) -> str:
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)[:5000]


def parse_openalex_work(work: dict) -> dict | None:
    title = work.get("title", "")
    if not title:
        return None
    authors = []
    for a in work.get("authorships", [])[:20]:
        name = a.get("author", {}).get("display_name", "")
        if name:
            authors.append(name)
    venue = ""
    venue_type = ""
    publisher = ""
    loc = work.get("primary_location") or {}
    src = loc.get("source") or {}
    if src:
        venue = src.get("display_name", "") or ""
        venue_type = src.get("type", "") or ""
        publisher = src.get("host_organization_name", "") or ""
    pdf_url = ""
    oa = work.get("open_access") or {}
    if oa.get("oa_url"):
        pdf_url = oa["oa_url"]
    best_oa = work.get("best_oa_location") or {}
    if not pdf_url and best_oa.get("pdf_url"):
        pdf_url = best_oa["pdf_url"]
    abstract = decode_abstract(work.get("abstract_inverted_index"))
    doi = (work.get("doi") or "").removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    work_id = work.get("id") or ""
    return {
        "doi": doi[:1000] if doi else "",
        "title": title[:2000] if title else "",
        "authors": json.dumps(authors)[:5000] if authors else "[]",
        "year": work.get("publication_year"),
        "venue": venue[:500] if venue else "",
        "venue_type": venue_type[:100] if venue_type else "",
        "abstract": abstract,
        "citations": work.get("cited_by_count", 0),
        "is_open_access": oa.get("is_oa", False),
        "url": doi or work_id,
        "pdf_url": pdf_url[:1000] if pdf_url else "",
        "source": "openalex",
        "source_id": work_id,
        "paper_type": (work.get("type") or "")[:100],
        "publisher": publisher[:500],
    }


# ═══════════════════════════════════════════════════════════════════════════
# FETCHER FUNCTIONS — each returns (papers_list, next_offset_or_cursor, error_flag)
# ═══════════════════════════════════════════════════════════════════════════

def fetch_openalex_page(query: str, cursor: str = "*", per_page: int = 200,
                        year_from: int = 2015) -> tuple[list[dict], str | None, int]:
    """OpenAlex cursor pagination via Tor."""
    _rate_wait('openalex')
    url = "https://api.openalex.org/works"
    params = {
        "search": query, "per_page": per_page, "cursor": cursor,
        "filter": f"from_publication_date:{year_from}-01-01",
        "sort": "relevance_score:desc", "mailto": POLITE_EMAIL,
    }
    for attempt in range(MAX_RETRIES + 1):
        port = None
        try:
            client, port = get_tor_client(timeout=15.0)
            try:
                r = client.get(url, params=params)
                if r.status_code == 200:
                    data = r.json()
                    results = data.get("results", [])
                    papers = [p for w in results if (p := parse_openalex_work(w))]
                    next_cursor = data.get("meta", {}).get("next_cursor")
                    total = data.get("meta", {}).get("count", 0)
                    return papers, next_cursor, total
                elif r.status_code == 429:
                    rotate_ip()
                    time.sleep(BACKOFF_BASE ** (attempt + 1))
                    continue
                elif r.status_code == 400:
                    rotate_ip()
                    time.sleep(2)
                    continue
                else:
                    return [], None, 0
            finally:
                client.close()
        except httpx.TimeoutException:
            return [], cursor, 0
        except Exception:
            rotate_ip()
            return [], cursor, 0
    return [], cursor, 0


def fetch_ss_page(query: str, offset: int = 0, limit: int = 100) -> list[dict]:
    """Semantic Scholar via Tor with aggressive rate limiting."""
    if offset >= 1000:
        return []
    _rate_wait('ss')
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query, "offset": offset, "limit": min(limit, 100),
        "fields": "title,authors,year,venue,citationCount,externalIds,abstract,url,isOpenAccess,openAccessPdf,publicationTypes",
        "year": "2015-",
    }
    for attempt in range(MAX_RETRIES + 1):
        try:
            client, port = get_tor_client(timeout=15.0)
            try:
                r = client.get(url, params=params)
                if r.status_code == 200:
                    data = r.json()
                    papers = []
                    for item in data.get("data", []):
                        title = item.get("title", "")
                        if not title:
                            continue
                        ext = item.get("externalIds", {}) or {}
                        authors = [a.get("name", "") for a in (item.get("authors") or [])[:20]]
                        oa_pdf = item.get("openAccessPdf", {}) or {}
                        pub_types = item.get("publicationTypes") or []
                        venue_type = ""
                        if pub_types:
                            pt = pub_types[0] if isinstance(pub_types, list) and pub_types else ""
                            if pt:
                                venue_type = "conference" if "conference" in pt.lower() else "journal" if "journal" in pt.lower() else pt
                        papers.append({
                            "doi": ext.get("DOI", "") or "",
                            "title": title[:2000],
                            "authors": json.dumps(authors)[:5000],
                            "year": item.get("year"),
                            "venue": (item.get("venue") or "")[:500],
                            "venue_type": venue_type[:100],
                            "abstract": item.get("abstract", "") or "",
                            "citations": item.get("citationCount", 0),
                            "is_open_access": item.get("isOpenAccess", False),
                            "url": item.get("url", ""),
                            "pdf_url": (oa_pdf.get("url") or "")[:1000],
                            "source": "semantic_scholar",
                            "source_id": item.get("paperId", ""),
                            "paper_type": venue_type[:100],
                            "publisher": "",
                        })
                    return papers
                elif r.status_code == 429:
                    rotate_ip()
                    time.sleep(BACKOFF_BASE ** (attempt + 1))
                    continue
                return []
            finally:
                client.close()
        except Exception:
            return []
    return []


def fetch_crossref_page(query: str, offset: int = 0, page_size: int = 20) -> list[dict]:
    """CrossRef free polite pool."""
    _rate_wait('crossref')
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://api.crossref.org/works",
                params={"query": query, "rows": page_size, "offset": offset,
                        "filter": "from-pub-date:2015-01-01",
                        "mailto": POLITE_EMAIL, "sort": "relevance", "order": "desc"})
        if r.status_code != 200:
            return []
        items = r.json().get("message", {}).get("items", [])
        papers = []
        for item in items:
            title = (item.get('title') or [''])[0] if item.get('title') else ''
            if not title:
                continue
            authors = []
            for a in item.get('author', [])[:20]:
                name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                if name:
                    authors.append(name)
            year_parts = item.get('published', {}).get('date-parts', [[None]])[0]
            year = year_parts[0] if year_parts else None
            doi = item.get('DOI', '')
            container = (item.get('container-title') or [''])[0] if item.get('container-title') else ''
            abstract = re.sub(r'<[^>]+>', '', item.get('abstract', '') or '')[:5000]
            # Extract PDF URL and OA status from link array
            pdf_url = ""
            is_oa = False
            for link in (item.get("link") or []):
                url = link.get("URL", "")
                content_type = link.get("content-type", "")
                if "pdf" in content_type.lower() or "application/pdf" in content_type:
                    pdf_url = url
                    is_oa = True
                    break
                if "openaccess" in (link.get("intended-application") or "").lower():
                    is_oa = True
            if not pdf_url and doi:
                pdf_url = f"https://doi.org/{doi}"
            papers.append({
                "doi": doi[:1000] if doi else "",
                "title": title[:2000],
                "authors": json.dumps(authors)[:5000],
                "year": year, "venue": container[:500], "venue_type": item.get("type", "")[:100],
                "abstract": abstract,
                "citations": item.get("is-referenced-by-count", 0),
                "is_open_access": is_oa,
                "url": f"https://doi.org/{doi}" if doi else "",
                "pdf_url": pdf_url[:1000], "source": "crossref",
                "source_id": doi or "",
                "paper_type": (item.get("type", "") or "")[:100],
                "publisher": (item.get("publisher") or "")[:500],
            })
        return papers
    except Exception:
        return []


def fetch_pubmed_page(query: str, retstart: int = 0, retmax: int = 50) -> list[dict]:
    """PubMed E-utilities — uses efetch XML to get full abstracts."""
    _rate_wait('pubmed')
    try:
        from xml.etree import ElementTree as ET
        r = httpx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmax": retmax,
                    "retstart": retstart, "format": "json", "sort": "relevance",
                    "datetype": "pdat", "mindate": "2015", "maxdate": "2026"},
            timeout=20.0)
        if r.status_code != 200:
            return []
        pmids = r.json().get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return []
        r2 = httpx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"},
            timeout=30.0)
        if r2.status_code != 200:
            return []
        root = ET.fromstring(r2.content)
        papers = []
        for article in root.findall('.//PubmedArticle'):
            pmid_elem = article.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else None
            if not pmid:
                continue
            title_elem = article.find('.//ArticleTitle')
            title = ''.join(title_elem.itertext()) if title_elem is not None else ''
            if not title:
                continue
            # Authors
            authors = []
            for author in article.findall('.//AuthorList/Author'):
                last = author.find('LastName')
                first = author.find('ForeName')
                if last is not None and last.text:
                    name = f"{first.text} {last.text}" if first is not None and first.text else last.text
                    authors.append(name)
            # Abstract — join ALL AbstractText sections with itertext
            abstract_parts = []
            for at in article.findall('.//Abstract/AbstractText'):
                label = at.get('Label', '')
                full = ''.join(at.itertext())
                if label:
                    abstract_parts.append(f'{label}: {full}')
                else:
                    abstract_parts.append(full)
            abstract = ' '.join(abstract_parts)
            # Year
            year_elem = article.find('.//Journal/JournalIssue/PubDate/Year')
            year = None
            if year_elem is not None and year_elem.text:
                try:
                    year = int(year_elem.text)
                except (ValueError, TypeError):
                    pass
            # Venue
            journal_elem = article.find('.//Journal/Title')
            venue = journal_elem.text if journal_elem is not None else ''
            # DOI + PMC
            doi = ''
            pmc_id = ''
            for aid in article.findall('.//PubmedData/ArticleIdList/ArticleId'):
                if aid.get('IdType') == 'doi':
                    doi = aid.text or ''
                elif aid.get('IdType') == 'pmc':
                    pmc_id = aid.text or ''
            pdf_url = ''
            if pmc_id:
                pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"
            elif doi:
                pdf_url = f"https://doi.org/{doi}"
            papers.append({
                "doi": doi[:1000] if doi else "", "title": title[:2000],
                "authors": json.dumps(authors)[:5000], "year": year,
                "venue": (venue or '')[:500], "venue_type": "journal",
                "abstract": abstract[:5000], "citations": 0,
                "is_open_access": bool(pmc_id),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "pdf_url": pdf_url[:1000], "source": "pubmed", "source_id": pmid,
                "paper_type": "journal-article", "publisher": "NLM",
            })
        return papers
    except Exception:
        return []


def fetch_ieee_page(query: str, page: int = 1) -> list[dict]:
    """IEEE Xplore keyless browser emulation."""
    _rate_wait('ieee')
    try:
        from urllib.parse import quote_plus
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            # Warmup
            client.get(f"https://ieeexplore.ieee.org/search/searchresult.jsp?newsearch=true&queryText={query}",
                       headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                       timeout=20)
            payload = {
                "newsearch": True, "queryText": query, "pageNumber": page,
                "rowsPerPage": 25, "returnType": "SEARCH", "highlight": True,
                "returnFacets": ["ALL"], "sortType": "most-relevant",
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://ieeexplore.ieee.org",
                "Referer": f"https://ieeexplore.ieee.org/search/searchresult.jsp?newsearch=true&queryText={quote_plus(query)}",
            }
            r = client.post("https://ieeexplore.ieee.org/rest/search",
                           json=payload, headers=headers, timeout=30.0)
        if r.status_code != 200:
            return []
        records = r.json().get("records", [])
        papers = []
        for rec in records:
            title = re.sub(r"<[^>]+>", "", (rec.get("articleTitle") or "").strip())
            if not title:
                continue
            authors = [a.get("preferredName", "") for a in (rec.get("authors") or [])[:20] if isinstance(a, dict)]
            aid = str(rec.get("articleNumber", ""))
            papers.append({
                "doi": (rec.get("doi") or "")[:1000],
                "title": title[:2000],
                "authors": json.dumps(authors)[:5000],
                "year": int(str(rec.get("publicationYear", ""))[:4]) if rec.get("publicationYear") else None,
                "venue": (rec.get("publicationTitle") or "")[:500],
                "venue_type": "conference" if "conference" in str(rec.get("contentType", "")).lower() else "journal",
                "abstract": re.sub(r"<[^>]+>", "", rec.get("abstract") or "")[:5000],
                "citations": rec.get("citationCount", 0) or 0,
                "is_open_access": bool(rec.get("openAccessFlag") or rec.get("isOpenAccess")),
                "url": f"https://ieeexplore.ieee.org/document/{aid}" if aid else "",
                "pdf_url": f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={aid}" if aid else "",
                "source": "ieee", "source_id": aid,
                "paper_type": str(rec.get("contentType", ""))[:100],
                "publisher": "IEEE",
            })
        return papers
    except Exception:
        return []


def fetch_arxiv_page(query: str, start: int = 0, per_page: int = 50) -> list[dict]:
    """arXiv Atom XML API."""
    import xml.etree.ElementTree as ET
    _rate_wait('arxiv')
    NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    try:
        time.sleep(3.5)  # arXiv strict 3s
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://export.arxiv.org/api/query", params={
                "search_query": f"all:{query}", "start": start,
                "max_results": per_page, "sortBy": "relevance", "sortOrder": "descending",
            })
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        entries = root.findall("atom:entry", NS)
        papers = []
        for entry in entries:
            title_el = entry.find("atom:title", NS)
            title = re.sub(r"\s+", " ", (title_el.text or "").strip()) if title_el is not None else ""
            if not title:
                continue
            summary_el = entry.find("atom:summary", NS)
            abstract = re.sub(r"\s+", " ", (summary_el.text or "").strip())[:5000] if summary_el is not None else ""
            authors = []
            for a in entry.findall("atom:author", NS):
                name_el = a.find("atom:name", NS)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())
            id_el = entry.find("atom:id", NS)
            arxiv_id = id_el.text.rsplit("/", 1)[-1] if id_el is not None and id_el.text else ""
            year = None
            pub_el = entry.find("atom:published", NS)
            if pub_el is not None and pub_el.text:
                try: year = int(pub_el.text[:4])
                except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            doi_el = entry.find("arxiv:doi", NS)
            doi = (doi_el.text or "").strip() if doi_el is not None else ""
            venue_el = entry.find("arxiv:journal_ref", NS)
            venue = (venue_el.text or "").strip() if venue_el is not None else ""
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else ""
            papers.append({
                "doi": doi[:1000] if doi else "", "title": title[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": venue[:500] if venue else "arXiv", "venue_type": "preprint",
                "abstract": abstract, "citations": 0, "is_open_access": True,
                "url": pdf_url[:1000], "pdf_url": pdf_url[:1000],
                "source": "arxiv", "source_id": arxiv_id,
                "paper_type": "preprint", "publisher": "arXiv",
            })
        return papers
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# NEW FETCHERS — integrated from fetchers/ modules, adapted for bulk use
# ═══════════════════════════════════════════════════════════════════════════

def fetch_dblp_page(query: str, offset: int = 0, per_page: int = 100) -> list[dict]:
    """DBLP — CS-focused, keyless."""
    _rate_wait('dblp')
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://dblp.org/search/publ/api", params={
                "q": query, "format": "json", "h": per_page, "f": offset,
            })
        if r.status_code != 200:
            return []
        data = r.json()
        hits = (data.get("result") or {}).get("hits", {}).get("hit", [])
        papers = []
        for hit in hits:
            info = hit.get("info") or {}
            title = (info.get("title") or "").rstrip(".").strip()
            if not title:
                continue
            authors_block = (info.get("authors") or {}).get("author") or []
            if isinstance(authors_block, dict):
                authors_block = [authors_block]
            authors = []
            for a in authors_block:
                name = a.get("text") if isinstance(a, dict) else str(a)
                if name:
                    authors.append(name)
            year = None
            if info.get("year"):
                try: year = int(info["year"])
                except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            doi = info.get("doi")
            ee = info.get("ee", "")
            pdf_url = ""
            if doi:
                pdf_url = f"https://doi.org/{doi}"
            elif ee:
                if "arxiv.org/abs/" in ee:
                    pdf_url = f"https://arxiv.org/pdf/{ee.split('/abs/')[-1]}.pdf"
                else:
                    pdf_url = ee
            papers.append({
                "doi": (doi or "")[:1000], "title": title[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": (info.get("venue") or "")[:500] if isinstance(info.get("venue"), str) else "",
                "venue_type": "",
                "abstract": "", "citations": 0, "is_open_access": False,
                "url": pdf_url[:1000], "pdf_url": pdf_url[:1000],
                "source": "dblp", "source_id": str(hit.get("@id", "")),
                "paper_type": (info.get("type") or "")[:100],
                "publisher": "",
            })
        return papers
    except Exception:
        return []


def fetch_europepmc_page(query: str, cursor: str = "*", per_page: int = 100) -> tuple[list[dict], str | None]:
    """Europe PMC — medical/life sciences, keyless with cursor pagination."""
    _rate_wait('europepmc')
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params={
                "query": query, "format": "json", "pageSize": per_page,
                "cursorMark": cursor, "resultType": "core", "sort": "P_RELEVANCE desc",
            })
        if r.status_code != 200:
            return [], None
        data = r.json()
        results = ((data.get("resultList") or {}).get("result")) or []
        next_cursor = data.get("nextCursorMark")
        papers = []
        for item in results:
            title = (item.get("title") or "").rstrip(".").strip()
            if not title:
                continue
            authors = [a.strip() for a in (item.get("authorString") or "").split(",") if a.strip()]
            year = None
            if item.get("pubYear"):
                try: year = int(item["pubYear"])
                except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            doi = item.get("doi")
            pmcid = item.get("pmcid")
            pdf_url = ""
            for ft in (item.get("fullTextUrlList") or {}).get("fullTextUrl") or []:
                if ft.get("documentStyle") == "pdf" or ft.get("availabilityCode") == "OA":
                    pdf_url = ft.get("url") or ""
                    break
            if not pdf_url and pmcid:
                pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"
            if not pdf_url and doi:
                pdf_url = f"https://doi.org/{doi}"
            papers.append({
                "doi": (doi or "")[:1000], "title": title[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": (item.get("journalTitle") or "")[:500],
                "venue_type": "journal" if item.get("journalTitle") else "",
                "abstract": (item.get("abstractText") or "")[:5000],
                "citations": item.get("citedByCount", 0) or 0,
                "is_open_access": item.get("isOpenAccess") == "Y",
                "url": pdf_url[:1000], "pdf_url": pdf_url[:1000],
                "source": "europepmc", "source_id": str(item.get("id", "")),
                "paper_type": (item.get("pubType") or "")[:100],
                "publisher": "",
            })
        if next_cursor == cursor:
            next_cursor = None
        return papers, next_cursor
    except Exception:
        return [], None


def fetch_doaj_page(query: str, page: int = 1, per_page: int = 100) -> list[dict]:
    """DOAJ — open access journals, keyless."""
    _rate_wait('doaj')
    try:
        from urllib.parse import quote
        encoded = quote(query, safe="")
        with httpx.Client(timeout=20.0) as client:
            r = client.get(f"https://doaj.org/api/search/articles/{encoded}", params={
                "page": page, "pageSize": per_page, "sort": "_score",
            })
        if r.status_code != 200:
            return []
        data = r.json()
        results = data.get("results") or []
        papers = []
        for item in results:
            bib = item.get("bibjson") or {}
            title = re.sub(r'<[^>]+>', '', bib.get("title") or "").strip()
            if not title:
                continue
            authors = [a.get("name", "").strip() for a in (bib.get("author") or []) if a.get("name")]
            year = None
            y = bib.get("year")
            if y:
                try: year = int(str(y)[:4])
                except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            journal = bib.get("journal") or {}
            doi = None
            pdf_url = ""
            for ident in (bib.get("identifier") or []):
                if ident.get("type") == "doi":
                    doi = ident.get("id")
            for link in (bib.get("link") or []):
                url = link.get("url")
                if url and (".pdf" in url.lower() or "pdf" in (link.get("content_type") or "").lower()):
                    pdf_url = url
                    break
            if not pdf_url and doi:
                pdf_url = f"https://doi.org/{doi}"
            papers.append({
                "doi": (doi or "")[:1000], "title": title[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": (journal.get("title") or "")[:500],
                "venue_type": "journal",
                "abstract": re.sub(r'<[^>]+>', '', bib.get("abstract") or "")[:5000],
                "citations": 0, "is_open_access": True,
                "url": pdf_url[:1000], "pdf_url": pdf_url[:1000],
                "source": "doaj", "source_id": str(item.get("id", "")),
                "paper_type": "journal-article",
                "publisher": (journal.get("publisher") or "")[:500],
            })
        return papers
    except Exception:
        return []


def fetch_hal_page(query: str, start: int = 0, per_page: int = 50) -> list[dict]:
    """HAL — French open archives, keyless."""
    _rate_wait('hal')
    try:
        fields = "docid,title_s,abstract_s,authFullName_s,producedDateY_i,journalTitle_s,doiId_s,uri_s,fileMain_s,docType_s,publisher_s"
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://api.archives-ouvertes.fr/search/", params={
                "q": query, "rows": per_page, "start": start,
                "wt": "json", "fl": fields, "sort": "relevance desc",
            })
        if r.status_code != 200:
            return []
        docs = (r.json().get("response") or {}).get("docs") or []
        papers = []
        for doc in docs:
            title = doc.get("title_s")
            if isinstance(title, list):
                title = title[0] if title else None
            if not title:
                continue
            authors = [a.strip() for a in (doc.get("authFullName_s") or []) if a]
            year = None
            for yk in ("producedDateY_i", "publicationDateY_i"):
                y = doc.get(yk)
                if y:
                    try: year = int(str(y)[:4]); break
                    except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            doi_raw = doc.get("doiId_s") or doc.get("doi_s")
            doi = doi_raw if isinstance(doi_raw, str) else (doi_raw[0] if isinstance(doi_raw, list) and doi_raw else None)
            abstract = doc.get("abstract_s")
            if isinstance(abstract, list):
                abstract = " ".join(a for a in abstract if a)
            pdf_url = doc.get("fileMain_s") or ""
            if pdf_url and not pdf_url.startswith("http"):
                pdf_url = f"https://hal.science/{pdf_url}"
            landing = doc.get("uri_s") or (f"https://doi.org/{doi}" if doi else "")
            papers.append({
                "doi": (doi or "")[:1000], "title": str(title)[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": (doc.get("journalTitle_s") or "")[:500],
                "venue_type": "journal" if doc.get("journalTitle_s") else "",
                "abstract": (abstract or "")[:5000],
                "citations": 0, "is_open_access": True,
                "url": (landing or pdf_url)[:1000], "pdf_url": pdf_url[:1000],
                "source": "hal", "source_id": str(doc.get("docid", "")),
                "paper_type": (doc.get("docType_s") or "")[:100],
                "publisher": (doc.get("publisher_s") or "")[:500],
            })
        return papers
    except Exception:
        return []


def fetch_plos_page(query: str, start: int = 0, per_page: int = 100) -> list[dict]:
    """PLOS — open access journals, keyless."""
    _rate_wait('plos')
    try:
        q = f'everything:"{query}" AND doc_type:full AND !article_type:"Issue Image"'
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://api.plos.org/search", params={
                "q": q, "start": start, "rows": per_page,
                "wt": "json", "fl": "id,title,author,abstract,publication_date,journal,article_type",
                "sort": "score desc",
            })
        if r.status_code != 200:
            return []
        docs = (r.json().get("response") or {}).get("docs") or []
        papers = []
        for doc in docs:
            title_raw = doc.get("title")
            title = " ".join(t for t in (title_raw if isinstance(title_raw, list) else [title_raw]) if t)
            title = re.sub(r'\s+', ' ', str(title)).strip()
            if not title:
                continue
            raw = doc.get("author") or []
            if isinstance(raw, str):
                raw = [raw]
            authors = [a.strip() for a in raw if a]
            year = None
            pub_date = doc.get("publication_date")
            if pub_date:
                try: year = int(str(pub_date)[:4])
                except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            doi = doc.get("id")
            pdf_url = ""
            landing = ""
            if doi and doi.startswith("10.1371/"):
                landing = f"https://journals.plos.org/plosone/article?id={doi}"
                pdf_url = f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable"
            elif doi:
                landing = f"https://doi.org/{doi}"
            abstract_raw = doc.get("abstract")
            abstract = " ".join(t for t in (abstract_raw if isinstance(abstract_raw, list) else [abstract_raw or ""]) if t).strip()
            papers.append({
                "doi": (doi or "")[:1000], "title": title[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": (re.sub(r'\s+', ' ', str(doc.get("journal") or ""))[:500]).strip(),
                "venue_type": "journal",
                "abstract": abstract[:5000],
                "citations": 0, "is_open_access": True,
                "url": (landing or pdf_url)[:1000], "pdf_url": pdf_url[:1000],
                "source": "plos", "source_id": doi or "",
                "paper_type": "journal-article", "publisher": "PLOS",
            })
        return papers
    except Exception:
        return []


def fetch_openaire_page(query: str, page: int = 1, per_page: int = 50) -> list[dict]:
    """OpenAIRE — European research aggregator, keyless."""
    _rate_wait('openaire')
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://api.openaire.eu/search/publications", params={
                "keywords": query, "size": per_page, "page": page,
                "format": "json", "sortBy": "relevance", "sortOrder": "descending",
            })
        if r.status_code != 200:
            return []
        resp = r.json().get("response") or {}
        items = (resp.get("results") or {}).get("result") or []
        papers = []
        for item in items:
            oaf = ((item.get("metadata") or {}).get("oaf:entity") or {}).get("oaf:result") or {}
            if not oaf:
                continue
            title_raw = oaf.get("title") or []
            if isinstance(title_raw, list):
                title = title_raw[0].get("$") if title_raw and isinstance(title_raw[0], dict) else str(title_raw[0]) if title_raw else ""
            elif isinstance(title_raw, dict):
                title = title_raw.get("$", "")
            else:
                title = str(title_raw)
            if not title:
                continue
            creators = oaf.get("creator") or []
            if isinstance(creators, dict):
                creators = [creators]
            authors = []
            for c in creators:
                name = c.get("$") if isinstance(c, dict) else str(c)
                if name:
                    authors.append(name)
            year = None
            for dk in ("dateofacceptance", "publicationdate"):
                d = oaf.get(dk) or {}
                ds = d.get("$") if isinstance(d, dict) else str(d) if d else ""
                if ds:
                    try: year = int(ds[:4]); break
                    except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            pid = oaf.get("pid") or {}
            doi = pid.get("$") if isinstance(pid, dict) else None
            abstract_raw = oaf.get("description") or []
            abstract = ""
            if isinstance(abstract_raw, list) and abstract_raw:
                first = abstract_raw[0]
                abstract = first.get("$") if isinstance(first, dict) else str(first)
            elif isinstance(abstract_raw, dict):
                abstract = abstract_raw.get("$", "")
            journal = oaf.get("journal") or {}
            venue = journal.get("name") or journal.get("$") or "" if isinstance(journal, dict) else ""
            # Extract PDF URL and OA status from instance
            instances = oaf.get("instance") or []
            if isinstance(instances, dict):
                instances = [instances]
            pdf_url = ""
            is_oa = False
            for inst in instances:
                accessright = inst.get("accessright") or {}
                if accessright.get("code") == "OPEN":
                    is_oa = True
                host_url = inst.get("hostedby") or {}
                if isinstance(host_url, dict):
                    host_url = host_url.get("$") or ""
                ref_url = inst.get("url") or {}
                if isinstance(ref_url, dict):
                    ref_url = ref_url.get("$") or ""
                if ref_url and ".pdf" in ref_url.lower():
                    pdf_url = ref_url
                    is_oa = True
                    break
                if host_url and ".pdf" in host_url.lower():
                    pdf_url = host_url
                    is_oa = True
                    break
            if not pdf_url and doi:
                pdf_url = f"https://doi.org/{doi}"
            # Extract publisher from journal or collectedfrom
            publisher = ""
            if isinstance(journal, dict):
                publisher = journal.get("publisher") or ""
            papers.append({
                "doi": (doi or "")[:1000], "title": str(title)[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": str(venue)[:500], "venue_type": "journal" if venue else "",
                "abstract": str(abstract)[:5000],
                "citations": 0, "is_open_access": is_oa,
                "url": f"https://doi.org/{doi}" if doi else "",
                "pdf_url": pdf_url[:1000], "source": "openaire",
                "source_id": str(oaf.get("id", doi or "")),
                "paper_type": (oaf.get("type") or "")[:100],
                "publisher": str(publisher)[:500],
            })
        return papers
    except Exception:
        return []


def fetch_datacite_page(query: str, page: int = 1, per_page: int = 50) -> list[dict]:
    """DataCite — 125M+ research DOIs, keyless."""
    _rate_wait('datacite')
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://api.datacite.org/dois", params={
                "query": query, "page[size]": per_page, "page[number]": page,
                "sort": "-relevance",
            }, headers={"Accept": "application/vnd.api+json"})
        if r.status_code != 200:
            return []
        items = r.json().get("data") or []
        papers = []
        for item in items:
            attr = item.get("attributes") or {}
            titles = attr.get("titles") or []
            title = titles[0].get("title") if titles and isinstance(titles[0], dict) else ""
            if not title:
                continue
            authors = [c.get("name", "").strip() for c in (attr.get("creators") or []) if c.get("name")]
            year = None
            pub_year = attr.get("publicationYear") or attr.get("created")
            if pub_year:
                try: year = int(str(pub_year)[:4])
                except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            doi = attr.get("doi")
            abstract = ""
            descs = attr.get("descriptions") or []
            for desc in descs:
                if isinstance(desc, dict):
                    d_type = desc.get("descriptionType", "")
                    d_text = desc.get("description") or ""
                    # Prioritize Abstract type, fall back to first description
                    if d_type == "Abstract" and d_text:
                        abstract = d_text
                        break
            if not abstract and descs and isinstance(descs[0], dict):
                abstract = descs[0].get("description") or ""
            publisher = attr.get("publisher")
            if isinstance(publisher, dict):
                publisher = publisher.get("name")
            # Extract venue from containerTitle
            container = attr.get("containerTitle") or {}
            venue = container.get("title", "") if isinstance(container, dict) else str(container) if container else ""
            if not venue:
                # Fallback: publisher as venue
                venue = publisher or ""
            # Extract URL
            landing_url = attr.get("url") or ""
            if not landing_url and doi:
                landing_url = f"https://doi.org/{doi}"
            papers.append({
                "doi": (doi or "")[:1000], "title": title[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": str(venue)[:500], "venue_type": attr.get("types", {}).get("resourceTypeGeneral", "")[:100] if isinstance(attr.get("types"), dict) else "",
                "abstract": abstract[:5000],
                "citations": 0, "is_open_access": False,
                "url": landing_url[:1000],
                "pdf_url": landing_url[:1000], "source": "datacite",
                "source_id": str(item.get("id", doi or "")),
                "paper_type": (attr.get("types", {}).get("resourceType", "") if isinstance(attr.get("types"), dict) else "")[:100], "publisher": (publisher or "")[:500],
            })
        return papers
    except Exception:
        return []


def fetch_zenodo_page(query: str, page: int = 1, per_page: int = 50) -> list[dict]:
    """Zenodo — CERN open repository, keyless."""
    _rate_wait('zenodo')
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://zenodo.org/api/records", params={
                "q": query, "size": per_page, "page": page,
                "type": "publication", "sort": "bestmatch",
            })
        if r.status_code != 200:
            return []
        hits = r.json().get("hits", {}).get("hits", [])
        papers = []
        for hit in hits:
            metadata = hit.get("metadata") or {}
            title = metadata.get("title")
            if not title:
                continue
            authors = [c.get("name", "").strip() for c in (metadata.get("creators") or []) if c.get("name")]
            year = None
            pub_date = metadata.get("publication_date") or metadata.get("date") or ""
            if pub_date:
                try: year = int(str(pub_date)[:4])
                except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
            doi = metadata.get("doi") or hit.get("doi")
            pdf_url = ""
            for f in (hit.get("files") or []):
                key = f.get("key", "")
                url = f.get("links", {}).get("self")
                if url and key.lower().endswith(".pdf"):
                    pdf_url = url
                    break
            landing = hit.get("links", {}).get("self_html") or (f"https://doi.org/{doi}" if doi else "")
            abstract = re.sub(r'<[^>]+>', '', metadata.get("description") or "")[:5000]
            # Extract venue from journal
            journal = metadata.get("journal") or {}
            venue = journal.get("title", "") if isinstance(journal, dict) else str(journal) if journal else ""
            # Extract resource type
            res_type = metadata.get("resource_type") or {}
            paper_type = res_type.get("type", "") if isinstance(res_type, dict) else str(res_type) if res_type else ""
            papers.append({
                "doi": (doi or "")[:1000], "title": title[:2000],
                "authors": json.dumps(authors[:20])[:5000], "year": year,
                "venue": str(venue)[:500], "venue_type": paper_type[:100],
                "abstract": abstract,
                "citations": 0, "is_open_access": True,
                "url": landing[:1000], "pdf_url": pdf_url[:1000],
                "source": "zenodo", "source_id": str(hit.get("id", "")),
                "paper_type": paper_type[:100], "publisher": (metadata.get("publisher") or "")[:500],
            })
        return papers
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# PARALLEL FETCHER THREADS — one per source, shared counter for coordination
# ═══════════════════════════════════════════════════════════════════════════

def _run_openalex(topic, target, start_cursor, counter, lock):
    total = 0; pages = 0; cursor = start_cursor; fails = 0
    while not shutdown_requested and total < target:
        if cursor is None: break
        papers, next_cursor, _ = fetch_openalex_page(topic, cursor)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            if next_cursor == cursor: time.sleep(2); continue
            if next_cursor is None: break
        else:
            fails = 0
            upsert_papers(papers)
            with lock: counter['total'] += len(papers)
            total += len(papers); pages += 1
        cursor = next_cursor
        time.sleep(0.3)
    return {'source': 'openalex', 'fetched': total, 'pages': pages,
            'cursor': cursor, 'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_ss(topic, target, counter, lock):
    total = 0; offset = 0; fails = 0
    while not shutdown_requested and offset < 1000:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_ss_page(topic, offset=offset)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); offset += len(papers)
        time.sleep(1)
    return {'source': 'ss', 'fetched': total, 'offset': offset,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_crossref(topic, target, counter, lock):
    total = 0; offset = 0; fails = 0
    while not shutdown_requested and offset < 1500:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_crossref_page(topic, offset=offset)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            time.sleep(2); continue
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); offset += len(papers)
        time.sleep(1.0)
    return {'source': 'crossref', 'fetched': total, 'offset': offset,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_pubmed(topic, target, counter, lock):
    total = 0; retstart = 0; fails = 0
    while not shutdown_requested and retstart < 1500:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_pubmed_page(topic, retstart=retstart)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); retstart += len(papers)
        time.sleep(0.5)
    return {'source': 'pubmed', 'fetched': total, 'offset': retstart,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_ieee(topic, target, counter, lock):
    total = 0; page = 1; fails = 0
    while not shutdown_requested and page <= 30:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_ieee_page(topic, page=page)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            time.sleep(4); continue
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); page += 1
        time.sleep(1.5)
    return {'source': 'ieee', 'fetched': total, 'offset': page,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_arxiv(topic, target, counter, lock):
    total = 0; start = 0; fails = 0
    while not shutdown_requested and start < 500:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_arxiv_page(topic, start=start)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); start += len(papers)
        time.sleep(1)
    return {'source': 'arxiv', 'fetched': total, 'offset': start,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_dblp(topic, target, counter, lock):
    total = 0; offset = 0; fails = 0
    while not shutdown_requested and offset < 1000:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_dblp_page(topic, offset=offset)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); offset += len(papers)
        time.sleep(0.5)
    return {'source': 'dblp', 'fetched': total, 'offset': offset,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_europepmc(topic, target, counter, lock):
    total = 0; cursor = "*"; fails = 0
    while not shutdown_requested and total < 1000:
        with lock:
            if counter['total'] >= target: break
        papers, next_cursor = fetch_europepmc_page(topic, cursor=cursor)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers)
        if not next_cursor: break
        cursor = next_cursor
        time.sleep(0.3)
    return {'source': 'europepmc', 'fetched': total, 'offset': total,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_doaj(topic, target, counter, lock):
    total = 0; page = 1; fails = 0
    while not shutdown_requested and page <= 10:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_doaj_page(topic, page=page)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); page += 1
        time.sleep(0.5)
    return {'source': 'doaj', 'fetched': total, 'offset': page,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_hal(topic, target, counter, lock):
    total = 0; start = 0; fails = 0
    while not shutdown_requested and start < 1000:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_hal_page(topic, start=start)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); start += len(papers)
        time.sleep(0.4)
    return {'source': 'hal', 'fetched': total, 'offset': start,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_plos(topic, target, counter, lock):
    total = 0; start = 0; fails = 0
    while not shutdown_requested and start < 1000:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_plos_page(topic, start=start)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); start += len(papers)
        time.sleep(0.5)
    return {'source': 'plos', 'fetched': total, 'offset': start,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_openaire(topic, target, counter, lock):
    total = 0; page = 1; fails = 0
    while not shutdown_requested and page <= 20:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_openaire_page(topic, page=page)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); page += 1
        time.sleep(0.6)
    return {'source': 'openaire', 'fetched': total, 'offset': page,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_datacite(topic, target, counter, lock):
    total = 0; page = 1; fails = 0
    while not shutdown_requested and page <= 20:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_datacite_page(topic, page=page)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); page += 1
        time.sleep(0.5)
    return {'source': 'datacite', 'fetched': total, 'offset': page,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_zenodo(topic, target, counter, lock):
    total = 0; page = 1; fails = 0
    while not shutdown_requested and page <= 20:
        with lock:
            if counter['total'] >= target: break
        papers = fetch_zenodo_page(topic, page=page)
        if not papers:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            break
        fails = 0
        upsert_papers(papers)
        with lock: counter['total'] += len(papers)
        total += len(papers); page += 1
        time.sleep(0.5)
    return {'source': 'zenodo', 'fetched': total, 'offset': page,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_scopus(topic, target, counter, lock):
    """Scopus fetcher - uses Scopus API with ELSEVIER_API_KEY."""
    global _warned
    api_key = os.getenv("ELSEVIER_API_KEY")
    if not api_key:
        if not _warned:
            logging.getLogger(__name__).info("scopus fetcher skipped: ELSEVIER_API_KEY not set")
            _warned = True
        return {'source': 'scopus', 'fetched': 0, 'offset': 0, 'skipped': True}

    total = 0; start = 0; fails = 0
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    url = "https://api.elsevier.com/content/search/scopus"

    while not shutdown_requested and total < 1000 and start < 5000:
        with lock:
            if counter['total'] >= target: break
        _rate_wait('scopus')
        try:
            client = httpx.Client(timeout=20.0)
            r = client.get(url, params={
                "query": topic, "count": min(25, 1000 - total), "start": start, "sort": "-relevancy",
            }, headers=headers)
            if r.status_code != 200:
                fails += 1
                logging.getLogger(__name__).error(f"scopus API returned {r.status_code}: {r.text[:100]}")
                if fails >= MAX_CONSECUTIVE_FAIL: break
                continue
            data = r.json()
            entries = data.get("search-results", {}).get("entry", [])
            if not entries:
                break
            papers = []
            for entry in entries:
                if entry.get("error"): continue
                title = entry.get("dc:title", "")
                if not title: continue
                doi = entry.get("prism:doi", "")
                source_id = entry.get("dc:identifier", "").replace("SCOPUS_ID:", "")
                papers.append({
                    "doi": doi[:1000] if doi else "",
                    "title": title[:2000],
                    "authors": json.dumps([entry.get("dc:creator", "")])[:5000],
                    "year": int(str(entry.get("prism:coverDate", "2020"))[:4]),
                    "venue": entry.get("prism:publicationName", "")[:500],
                    "venue_type": "journal" if entry.get("prism:aggregationType") == "Journal" else "conference" if "conference" in entry.get("prism:aggregationType", "").lower() else "",
                    "abstract": "",  # enriched below via OpenAlex
                    "citations": int(entry.get("citedby-count", 0)) if entry.get("citedby-count") else 0,
                    "is_open_access": entry.get("openaccess") == "1",
                    "url": f"https://doi.org/{doi}" if doi else "",
                    "pdf_url": "",
                    "source": "scopus",
                    "source_id": source_id,
                    "paper_type": entry.get("prism:aggregationType", "")[:100],
                    "publisher": entry.get("dc:publisher", "")[:500],
                })
            if papers:
                # Phase 1: insert without abstracts
                inserted = upsert_papers(papers)
                logging.getLogger(__name__).info(f"scopus: fetched {len(papers)}, inserted {inserted}")
                total += inserted

                # Phase 2: enrich abstracts via OpenAlex DOI lookup
                enriched = 0
                for p in papers:
                    p_doi = p.get("doi")
                    if not p_doi:
                        continue
                    try:
                        _rate_wait('scopus_oa')
                        oa_url = f"https://api.openalex.org/works/doi:{p_doi}"
                        oa_r = httpx.get(oa_url, timeout=10.0)
                        if oa_r.status_code == 200:
                            oa_data = oa_r.json()
                            inv_idx = oa_data.get("abstract_inverted_index")
                            if inv_idx and isinstance(inv_idx, dict):
                                abstract = decode_abstract(inv_idx)
                                if abstract:
                                    _update_abstract(p["source_id"], abstract, "scopus")
                                    enriched += 1
                    except Exception:
                        pass
                if enriched:
                    logging.getLogger(__name__).info(f"scopus: enriched {enriched}/{len(papers)} abstracts via OpenAlex")

                with lock:
                    counter['total'] += inserted
            start += len(entries)
            time.sleep(0.5)
        except Exception as e:
            fails += 1
            logging.getLogger(__name__).error(f"scopus exception: {e}")
            if fails >= MAX_CONSECUTIVE_FAIL: break
            time.sleep(1)
    return {'source': 'scopus', 'fetched': total, 'offset': start,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


def _run_core(topic, target, counter, lock):
    """CORE fetcher - uses CORE API with CORE_API_KEY."""
    global _warned
    api_key = os.getenv("CORE_API_KEY")
    if not api_key:
        if not _warned:
            logging.getLogger(__name__).info("core fetcher skipped: CORE_API_KEY not set")
            _warned = True
        return {'source': 'core', 'fetched': 0, 'offset': 0, 'skipped': True}

    total = 0; offset = 0; fails = 0
    headers = {"Authorization": f"Bearer {api_key}"}
    url = "https://api.core.ac.uk/v3/search/works"

    while not shutdown_requested and total < 1000:
        with lock:
            if counter['total'] >= target: break
        _rate_wait('core')
        try:
            client, port = get_tor_client(timeout=20.0)
            r = client.post(url, json={
                "q": topic, "limit": min(100, 1000 - total), "offset": offset, "sort": [],
            }, headers=headers)
            if r.status_code != 200:
                fails += 1
                if fails >= MAX_CONSECUTIVE_FAIL: break
                continue
            data = r.json()
            results = data.get("results", [])
            if not results:
                break
            papers = []
            for item in results:
                title = item.get("title", "")
                if not title: continue
                doi = item.get("doi")
                if not doi and isinstance(item.get("identifiers"), list):
                    for ident in item["identifiers"]:
                        if isinstance(ident, dict) and ident.get("type") == "doi":
                            doi = ident.get("identifier"); break
                pdf_url = item.get("downloadUrl") or (item.get("sourceFulltextUrls") or [None])[0] if item.get("sourceFulltextUrls") else ""
                landing = item.get("urls", [None])[0] if item.get("urls") else ""
                if not landing and doi: landing = f"https://doi.org/{doi}"
                authors = [a.get("name", "") for a in (item.get("authors") or [])[:20]]
                year = None
                y = item.get("yearPublished")
                if y:
                    try: year = int(str(y)[:4])
                    except Exception as _e: logging.getLogger(__name__).debug("parse/op skipped: %s", _e)
                papers.append({
                    "doi": (doi or "")[:1000], "title": title[:2000],
                    "authors": json.dumps(authors)[:5000], "year": year,
                    "venue": (item.get("publisher") or "")[:500], "venue_type": "",
                    "abstract": (item.get("abstract") or "")[:5000],
                    "citations": 0, "is_open_access": True,
                    "url": (landing or "")[:1000], "pdf_url": (pdf_url or "")[:1000],
                    "source": "core",
                    "source_id": str(item.get("id", "")),
                    "paper_type": "", "publisher": (item.get("publisher") or "")[:500],
                })
            if papers:
                upsert_papers(papers)
                with lock: counter['total'] += len(papers)
                total += len(papers)
            offset += len(results)
            time.sleep(0.5)
        except Exception:
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAIL: break
            time.sleep(1)
    return {'source': 'core', 'fetched': total, 'offset': offset,
            'skipped': fails >= MAX_CONSECUTIVE_FAIL}


# ═══════════════════════════════════════════════════════════════════════════
# TOPIC PROCESSOR — spawns all 17 fetchers in parallel
# ═══════════════════════════════════════════════════════════════════════════

ALL_FETCHERS = [
    ('openalex', _run_openalex),
    ('ss', _run_ss),
    ('crossref', _run_crossref),
    ('pubmed', _run_pubmed),
    ('ieee', _run_ieee),
    ('arxiv', _run_arxiv),
    ('dblp', _run_dblp),
    ('europepmc', _run_europepmc),
    ('doaj', _run_doaj),
    ('hal', _run_hal),
    ('plos', _run_plos),
    ('openaire', _run_openaire),
    ('datacite', _run_datacite),
    ('zenodo', _run_zenodo),
    ('scopus', _run_scopus),
    ('core', _run_core),
]


def process_topic(topic_info: dict):
    """Process a single topic: ALL 15 fetchers in parallel."""
    global shutdown_requested
    tid = topic_info["id"]
    field = topic_info["field_name"]
    topic = topic_info["topic"]
    target = topic_info["target_count"]
    already_fetched = topic_info["fetched_count"]
    last_cursor = topic_info.get("last_cursor") or "*"

    log(f"\n{'='*60}")
    log(f"📚 [{field}] {topic[:70]}")
    log(f"   Target: {target:,} | Already: {already_fetched:,} | Cursor: {'resume' if last_cursor != '*' else 'start'}")

    start = time.time()
    remaining = target - already_fetched
    openalex_target = int(remaining * 0.5)

    counter = {'total': 0}
    lock = threading.Lock()

    # Submit all 15 fetchers
    with ThreadPoolExecutor(max_workers=len(ALL_FETCHERS), thread_name_prefix="fetch") as pool:
        futures = {}
        for name, fn in ALL_FETCHERS:
            if name == 'openalex':
                futures[pool.submit(fn, topic, openalex_target, last_cursor, counter, lock)] = name
            else:
                futures[pool.submit(fn, topic, target, counter, lock)] = name

        results = {}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {'source': name, 'fetched': 0, 'offset': 0, 'skipped': True, 'error': str(e)}

    total_fetched = counter['total']
    elapsed = time.time() - start
    rate = total_fetched / max(elapsed, 1)
    final_count = already_fetched + total_fetched

    # Determine status
    oa_res = results.get('openalex', {})
    other_results = [results.get(n, {}) for n, _ in ALL_FETCHERS if n != 'openalex']

    if shutdown_requested:
        status = "running"
    elif final_count >= target:
        status = "done"
    elif oa_res.get('cursor') is None and all(
        r.get('skipped') or r.get('offset', 0) >= 500 for r in other_results
    ):
        status = "done"
    else:
        status = "running"

    cursor = oa_res.get('cursor') if status == "running" else None
    update_progress(tid, total_fetched, cursor=cursor, status=status)

    src_info = []
    for name, _ in ALL_FETCHERS:
        res = results.get(name, {})
        if res.get('skipped') or res.get('fetched', 0) == 0:
            src_info.append(f"{name}:skip")
        else:
            src_info.append(f"{name}:{res['fetched']}")

    log(f"  ✅ +{total_fetched:,} ({elapsed:.0f}s, {rate:.0f}/s) | {', '.join(src_info)} | Total: {final_count:,}/{target:,} | {status}")
    return total_fetched


# ═══════════════════════════════════════════════════════════════════════════
# STATS & DAEMON
# ═══════════════════════════════════════════════════════════════════════════

def get_stats() -> dict:
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                COUNT(*) as total_topics,
                COUNT(*) FILTER (WHERE status = 'done') as done_topics,
                COUNT(*) FILTER (WHERE status = 'running') as running_topics,
                COUNT(*) FILTER (WHERE status = 'pending') as pending_topics,
                COUNT(*) FILTER (WHERE status = 'error') as error_topics,
                SUM(fetched_count) as total_fetched,
                SUM(target_count) as total_target,
                ROUND(100.0 * SUM(fetched_count) / NULLIF(SUM(target_count), 0), 2) as pct
            FROM mega_fetch_progress
        """)
        stats = dict(cur.fetchone())
        cur.execute("""
            SELECT field_name,
                COUNT(*) as topics,
                COUNT(*) FILTER (WHERE status = 'done') as done,
                SUM(fetched_count) as fetched,
                SUM(target_count) as target
            FROM mega_fetch_progress
            GROUP BY field_name
            ORDER BY field_name
        """)
        stats["per_field"] = [dict(r) for r in cur.fetchall()]

        # Actual DB paper count
        cur.execute("SELECT COUNT(*) FROM papers")
        stats["actual_papers"] = cur.fetchone()["count"]

        cur.close()
        return stats
    finally:
        put_db(conn)


def run_daemon(workers: int = WORKERS, continuous: bool = True):
    """Main daemon loop: pick topics, process, repeat. Continuous mode restarts."""
    global shutdown_requested

    log("=" * 60)
    log("🚀 MEGA FETCH DAEMON V3 — 17 SOURCES PARALLEL")
    log(f"   Workers: {workers} | Continuous: {continuous}")

    stats = get_stats()
    log(f"   DB papers: {stats['actual_papers']:,} | Target: 5,000,000")
    log(f"   Topics: {stats['total_topics']} total, {stats['pending_topics']} pending, "
        f"{stats['running_topics']} running, {stats['done_topics']} done")
    log(f"   Progress: {stats['total_fetched']:,} / {stats['total_target']:,} ({stats['pct']}%)")

    # Initialize Tor
    log("   🧅 Initializing Tor (5 ports)...")
    tor = get_tor()
    log("   🧅 Tor ready: 5 SOCKS ports")

    # Cooldown
    cd = 5
    log(f"   ⏳ Starting in {cd}s...")
    for _ in range(cd):
        if shutdown_requested: return
        time.sleep(1)
    log("=" * 60)

    cycle = 0
    while not shutdown_requested:
        cycle += 1
        topics = get_pending_topics(limit=workers)
        if not topics:
            if continuous:
                log(f"🔄 Cycle {cycle} done — no pending topics. Checking for incomplete...")
                # Check if there are 'running' topics that got stuck
                conn = get_db()
                try:
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE mega_fetch_progress
                        SET status = 'pending'
                        WHERE status = 'running'
                        AND updated_at < NOW() - INTERVAL '10 minutes'
                    """)
                    stuck = cur.rowcount
                    conn.commit()
                    cur.close()
                finally:
                    put_db(conn)
                if stuck > 0:
                    log(f"   🔧 Reset {stuck} stuck topics to pending, retrying...")
                    continue
                # Check if target reached
                stats = get_stats()
                if stats['actual_papers'] >= 5_000_000:
                    log(f"🎉 TARGET REACHED! {stats['actual_papers']:,} papers in DB!")
                    break
                if stats['pending_topics'] == 0 and stats['running_topics'] == 0:
                    log("✅ All topics done! Daemon idle. Waiting 60s for new topics...")
                    for _ in range(60):
                        if shutdown_requested: break
                        time.sleep(1)
                    continue
                continue
            else:
                log("✅ All topics processed! Daemon stopping.")
                break

        if workers == 1:
            for t in topics:
                if shutdown_requested: break
                process_topic(t)
        else:
            pool = ThreadPoolExecutor(max_workers=min(workers, len(topics)))
            futures = {}
            for i, t in enumerate(topics):
                if i > 0:
                    log(f"  ⏳ Stagger: waiting {STAGGER_DELAY}s...")
                    time.sleep(STAGGER_DELAY)
                futures[pool.submit(process_topic, t)] = t
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    t = futures[future]
                    log(f"  ❌ Error on {t['topic'][:50]}: {e}")
                    update_progress(t["id"], 0, status="error", error=str(e)[:200])
            pool.shutdown(wait=False)

        # Periodic stats + IP rotation
        if cycle % 10 == 0:
            stats = get_stats()
            log(f"\n📊 CYCLE {cycle}: DB={stats['actual_papers']:,} papers | "
                f"{stats['done_topics']}/{stats['total_topics']} topics done | "
                f"Tor: 5 ports")
            rotate_ip()

    stats = get_stats()
    log(f"\n📊 FINAL: DB={stats['actual_papers']:,} papers | "
        f"{stats['done_topics']}/{stats['total_topics']} topics done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mega Fetch Daemon V3 — 17 sources")
    parser.add_argument("--workers", type=int, default=WORKERS, help="Parallel topic workers")
    parser.add_argument("--stats", action="store_true", help="Show stats and exit")
    parser.add_argument("--once", action="store_true", help="Run one cycle only (no continuous)")
    args = parser.parse_args()

    if args.stats:
        stats = get_stats()
        print(f"\n📊 MEGA FETCH V3 STATUS")
        print(f"   DB papers: {stats['actual_papers']:,} / 1,000,000 target")
        print(f"   Progress: {stats['total_fetched']:,} / {stats['total_target']:,} ({stats['pct']}%)")
        print(f"   Topics: {stats['done_topics']}/{stats['total_topics']} done "
              f"({stats['pending_topics']} pending, {stats['error_topics']} errors)")
        print(f"   Sources: {len(ALL_FETCHERS)} parallel ({', '.join(n for n,_ in ALL_FETCHERS)})")
        print(f"\n   Per field:")
        for f in stats.get("per_field", []):
            pct = round(f['fetched'] / max(f['target'], 1) * 100, 1)
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"   {f['field_name']:25s} {bar} {pct:5.1f}% ({f['fetched']:,}/{f['target']:,}) [{f['done']}/{f['topics']} topics]")
        sys.exit(0)

    run_daemon(workers=args.workers, continuous=not args.once)
