"""Paper Database Cache Module.

Provides fast lookup and caching of paper metadata in PostgreSQL.
Used by SLR orchestrator to:
1. Check DB first (cache hit) before fetching from API
2. Sync new papers from API to DB
3. Track which papers came from which source

Optimized for 713K+ papers with:
- Combined weighted tsvector (title weight A=1.0, abstract weight B=0.4)
- ts_rank_cd with cover-density + doc-length normalization
- Citation log boost + recency bonus
- Two-phase AND→OR fallback for flexible matching
- No slow ILIKE scan — uses trigram index for fuzzy title fallback
"""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import datetime
from typing import Iterable

import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values, Json

from tools.Literatur.paper import Paper

log = logging.getLogger(__name__)

# Database connection settings
DB_CONFIG = {
    "host": os.getenv("PAPER_DB_HOST", "/var/run/postgresql"),
    "port": int(os.getenv("PAPER_DB_PORT", "5432")),
    "database": os.getenv("PAPER_DB_NAME", "paper_database"),
    "user": os.getenv("PAPER_DB_USER", "sirobo"),
    "password": os.getenv("PAPER_DB_PASS", ""),
}

# Connection pool — thread-safe, supports up to 5 concurrent connections per process.
# With 16 gunicorn workers: max 80 connections. PG max_connections=300, safe headroom.
_pool: pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> pool.ThreadedConnectionPool:
    """Lazy-init connection pool with double-checked locking."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=5,
                    **DB_CONFIG,
                )
    return _pool


def get_connection():
    """Get database connection from pool."""
    return _get_pool().getconn()


def put_connection(conn):
    """Return connection to pool."""
    _get_pool().putconn(conn)


def normalize_title(title: str | None) -> str | None:
    """Normalize title for dedup lookup."""
    if not title:
        return None
    return re.sub(r'[^a-z0-9]+', '', title.lower())


def paper_to_dict(paper: Paper) -> dict:
    """Convert Paper object to dict for DB insert."""
    return {
        "doi": paper.doi,
        "title": paper.title,
        "authors": Json(paper.authors) if paper.authors else None,
        "year": paper.year,
        "venue": paper.venue,
        "venue_type": paper.venue_type,
        "abstract": paper.abstract,
        "citations": paper.citations,
        "is_open_access": paper.is_open_access,
        "url": paper.url,
        "pdf_url": paper.pdf_url,
        "source": paper.source,
        "source_id": paper.source_id,
        "paper_type": paper.type,
        "publisher": getattr(paper, "publisher", None),
    }


def save_papers(papers: list[Paper], source: str | None = None) -> int:
    """
    Save papers to database. Returns number of papers saved.
    
    Upserts papers (insert or update on conflict).
    Also tracks which source each paper came from.
    """
    if not papers:
        return 0
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Prepare papers for insert
            paper_data = []
            source_data = []
            
            for p in papers:
                title_norm = normalize_title(p.title)
                if not title_norm:
                    continue
                
                paper_dict = paper_to_dict(p)
                paper_data.append((
                    paper_dict["doi"],
                    paper_dict["title"],
                    paper_dict["authors"],
                    paper_dict["year"],
                    paper_dict["venue"],
                    paper_dict["venue_type"],
                    paper_dict["abstract"],
                    paper_dict["citations"],
                    paper_dict["is_open_access"],
                    paper_dict["url"],
                    paper_dict["pdf_url"],
                    paper_dict["source"] or source,
                    paper_dict["source_id"],
                    paper_dict["paper_type"],
                    paper_dict["publisher"],
                ))
                
                # Track source
                source_data.append((
                    paper_dict["source"] or source,
                    paper_dict["source_id"],
                ))
            
            if not paper_data:
                return 0
            
            # Upsert papers - use ON CONFLICT on DOI only
            # title_normalized is no longer UNIQUE (regular index for search)
            insert_query = """
                INSERT INTO papers (
                    doi, title, authors, year, venue, venue_type, abstract,
                    citations, is_open_access, url, pdf_url, source, source_id,
                    paper_type, publisher
                ) VALUES %s
                ON CONFLICT (doi) WHERE doi IS NOT NULL DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, papers.title),
                    authors = COALESCE(EXCLUDED.authors, papers.authors),
                    year = COALESCE(EXCLUDED.year, papers.year),
                    venue = COALESCE(EXCLUDED.venue, papers.venue),
                    venue_type = COALESCE(EXCLUDED.venue_type, papers.venue_type),
                    abstract = COALESCE(EXCLUDED.abstract, papers.abstract),
                    citations = COALESCE(EXCLUDED.citations, papers.citations),
                    is_open_access = COALESCE(EXCLUDED.is_open_access, papers.is_open_access),
                    url = COALESCE(EXCLUDED.url, papers.url),
                    pdf_url = COALESCE(EXCLUDED.pdf_url, papers.pdf_url),
                    source = COALESCE(EXCLUDED.source, papers.source),
                    source_id = COALESCE(EXCLUDED.source_id, papers.source_id),
                    paper_type = COALESCE(EXCLUDED.paper_type, papers.paper_type),
                    publisher = COALESCE(EXCLUDED.publisher, papers.publisher),
                    updated_at = NOW();
            """
            
            execute_values(cur, insert_query, paper_data, page_size=100)
            
            # Get paper IDs for source tracking - batch fetch by DOI and title
            paper_ids = {}
            dois = [p[0] for p in paper_data if p[0]]
            titles = [normalize_title(p[1]) for p in paper_data if not p[0] and normalize_title(p[1])]
            
            if dois:
                cur.execute(
                    "SELECT id, doi FROM papers WHERE doi = ANY(%s)",
                    (dois,)
                )
                for row in cur.fetchall():
                    paper_ids[row[1]] = row[0]
            
            if titles:
                cur.execute(
                    "SELECT id, title_normalized FROM papers WHERE title_normalized = ANY(%s)",
                    (titles,)
                )
                for row in cur.fetchall():
                    paper_ids[f"title:{row[1]}"] = row[0]
            
            # Upsert paper_sources
            source_insert = """
                INSERT INTO paper_sources (paper_id, source, source_id)
                VALUES %s
                ON CONFLICT (paper_id, source) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    fetched_at = NOW();
            """
            
            source_records = []
            for i, (src, src_id) in enumerate(source_data):
                doi = paper_data[i][0]
                title_norm = normalize_title(paper_data[i][1])
                # Try DOI first, then title_normalized
                paper_id = paper_ids.get(doi) or paper_ids.get(f"title:{title_norm}")
                if paper_id:
                    source_records.append((paper_id, src, src_id))
            
            if source_records:
                execute_values(cur, source_insert, source_records, page_size=100)
            
            conn.commit()
            return len(paper_data)
    
    except Exception as e:
        conn.rollback()
        log.error(f"Error saving papers: {e}")
        raise
    finally:
        put_connection(conn)


# ─── Optimized Full-Text Search ──────────────────────────────────────────────
#
# Architecture:
# 1. Combined weighted tsvector:
#    setweight(title_tsv, 'A') || setweight(COALESCE(abstract_tsv, ''), 'B')
#    Weight A (title) = 1.0, Weight B (abstract) = 0.4
#
# 2. ts_rank_cd with normalization bitmask 34 (2|32):
#    - Bit 2 (cover density): rewards terms appearing close together → higher for
#      papers where all matched terms cluster in a sentence vs scattered.
#      Important for academic search — a paper about "PID control" that mentions
#      "optimization" nearby is more relevant than one that mentions them far apart.
#    - Bit 32 (doc length): divides by (1 + log(len)) → fair comparison between
#      short titles/abstracts and long detailed ones.
#
# 3. Hybrid score:
#    ts_rank_cd × 10.0          — text relevance (dominant factor, range ~0–10)
#    + ln(citations+1) × 0.5    — citation log boost (0 for uncited, ~4 for 3000+)
#    + (year-1900)/100 × 0.3    — recency bonus (0.36→0.39 for 2020→2030)
#
# 4. Two-phase matching:
#    Phase 1: AND of all query terms (plainto_tsquery) — strict, precise
#    Phase 2: if < limit results, OR of terms — broader, still ranked by score
#    Phase 3: trigram similarity on title as last resort (rare)

# ── Generic words to exclude from OR fallback queries ─────────────────
# These appear in thousands of papers regardless of domain. Including them
# in OR queries floods results with irrelevant papers.
_OR_FILTER_WORDS = {
    # Standard stopwords (already handled by tsvector but kept for safety)
    "a", "an", "the", "in", "on", "of", "to", "by", "is", "be", "at",
    "or", "as", "if", "no", "so", "we", "he", "she", "it", "they",
    "and", "for", "with", "from", "that", "this", "are", "was", "but",
    "not", "can", "all", "any", "has", "its", "may", "who", "which",
    "their", "how", "what", "why", "use", "also", "been", "were",
    "will", "have", "had", "do", "does", "did", "into", "than",
    "just", "more", "most", "new", "other", "some", "such", "only",
    "over", "when", "where", "each", "about", "after", "before",
    "between", "during", "these", "those",
    # Generic academic/method words — high-frequency, non-discriminative
    "based", "using", "through", "approach", "method", "methods",
    "model", "system", "systems", "data", "review",
    "analysis", "study", "studies", "research", "paper",
    "technique", "techniques", "algorithm", "algorithms",
    "framework", "application", "applications",
    "development", "validation", "evaluation", "implementation",
    "design", "performance", "comparative", "comparison",
    "effect", "impact", "role", "case", "survey",
    "overview", "challenge", "challenges", "issue", "issues",
    "trend", "advance", "advances", "recent", "comprehensive",
    "state", "art",
    # ML/CV method words — match 90%+ of CS papers regardless of domain
    "deep", "learning", "machine", "neural", "network", "networks",
    "computer", "vision", "image", "images", "video",
    "detection", "recognition", "classification", "prediction",
    "predicting", "enhanced", "improved", "novel", "automatic",
    "automated", "efficient", "robust", "hybrid", "optimization",
    "object", "feature", "features", "extraction", "segmentation",
    "architecture", "architectures", "transfer", "training",
    "dataset", "datasets", "benchmark", "accuracy", "precision",
    "scalable", "adaptive", "embedded", "embedding", "embeddings",
}
_OR_MIN_WORD_LEN = 3  # Discard words shorter than this


def _filter_or_words(words: list[str]) -> list[str]:
    """Filter words for OR fallback: remove generic/method terms.

    Only keeps domain-specific content words that are discriminative
    for the search. Skipping generic terms prevents irrelevant papers
    from polluting OR fallback results.
    """
    filtered = []
    seen = set()
    for w in words:
        wl = w.lower()
        if wl in _OR_FILTER_WORDS:
            continue
        if len(wl) < _OR_MIN_WORD_LEN:
            continue
        if wl not in seen:
            filtered.append(wl)
            seen.add(wl)
    return filtered

def _build_search_query(
    conn,
    conditions: list[str],
    params: list,
    query: str,
    limit: int,
    year_from: int | None = None,
    year_to: int | None = None,
    sources: list[str] | None = None,
    venue_types: list[str] | None = None,
    open_access_only: bool = False,
) -> str:
    """Build WHERE clause + params array for search_papers()."""
    
    # Full-text search: combined weighted tsvector
    if query:
        conditions.append("""
            (title_tsv @@ plainto_tsquery('english', %s) 
             OR abstract_tsv @@ plainto_tsquery('english', %s))
        """)
        params.extend([query, query])
    
    # Year filters
    if year_from:
        conditions.append("year >= %s")
        params.append(year_from)
    if year_to:
        conditions.append("year <= %s")
        params.append(year_to)
    
    # Source filter
    if sources:
        conditions.append(
            "(source = ANY(%s) OR EXISTS ("
            "SELECT 1 FROM paper_sources ps "
            "WHERE ps.paper_id = papers.id "
            "AND ps.source = ANY(%s)))"
        )
        params.append(sources)
        params.append(sources)
    
    # Venue type filter
    if venue_types:
        conditions.append("venue_type = ANY(%s)")
        params.append(venue_types)
    
    # Open access filter
    if open_access_only:
        conditions.append("is_open_access = TRUE")
    
    return " AND ".join(conditions) if conditions else "TRUE"


_SCORE_EXPR = """\
    ts_rank_cd(
        setweight(title_tsv, 'A') || setweight(COALESCE(abstract_tsv, ''), 'B'),
        plainto_tsquery('english', %s),
        34
    ) * 10.0
    -- citations + recency disabled per user request — pure title/abstract relevance only
"""

_COLUMNS = """
    doi, title, authors, year, venue, venue_type, abstract,
    citations, is_open_access, url, pdf_url, source, source_id,
    paper_type, publisher
"""


def _row_to_paper(row) -> Paper:
    """Convert a DB row tuple to Paper object.
    
    Row layout: doi, title, authors, year, venue, venue_type, abstract,
    citations, is_open_access, url, pdf_url, source, source_id,
    paper_type, publisher, score
    """
    return Paper(
        doi=row[0],
        title=row[1],
        authors=row[2] if row[2] else [],
        year=row[3],
        venue=row[4],
        venue_type=row[5],
        abstract=row[6],
        citations=row[7],
        is_open_access=row[8],
        url=row[9],
        pdf_url=row[10],
        source=row[11],
        source_id=row[12],
        type=row[13],
        publisher=row[14],
        db_score=float(row[15]) if row[15] is not None else None,
    )


def search_papers(
    query: str,
    limit: int = 100,
    year_from: int | None = None,
    year_to: int | None = None,
    sources: list[str] | None = None,
    venue_types: list[str] | None = None,
    open_access_only: bool = False,
) -> list[Paper]:
    """
    Search papers in paper_database with optimized hybrid ranking.
    
    Returns list of Paper objects sorted by relevance score:
    - ts_rank_cd (cover density + doc-length normalized, title weight A, abstract B)
    - Citation log boost
    - Recency bonus
    
    Two-phase: AND first for precision, OR fallback if too few results.
    
    Performance: 8-40ms for typical queries on 713K papers.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # ── Phase 1: AND query (precise) ──
            conditions: list[str] = []
            params: list = []
            
            where_clause = _build_search_query(
                conn, conditions, params, query, limit,
                year_from=year_from, year_to=year_to,
                sources=sources, venue_types=venue_types,
                open_access_only=open_access_only,
            )
            
            # CRITICAL: _SCORE_EXPR contains %s which appears BEFORE the WHERE
            # clause in the SQL text. Params are consumed in SQL text order,
            # so the SELECT %s must come BEFORE the WHERE %s in the params list.
            # Insert at position 0 to fix ordering.
            params.insert(0, query)  # for _SCORE_EXPR in SELECT
            params.append(limit)     # for LIMIT
            
            search_query = f"""
                SELECT {_COLUMNS},
                       ({_SCORE_EXPR}) AS score
                FROM papers
                WHERE {where_clause}
                ORDER BY score DESC
                LIMIT %s;
            """
            
            cur.execute(search_query, params)
            rows = cur.fetchall()
            
            papers = [_row_to_paper(r) for r in rows]
            
            # ── Phase 2: OR fallback (broader) ──
            if len(papers) < limit and query:
                log.info(
                    "search_papers: AND query returned %d (< %d), trying OR fallback",
                    len(papers), limit,
                )
                papers = _search_or_fallback(
                    cur, query, limit,
                    year_from=year_from, year_to=year_to,
                    sources=sources, venue_types=venue_types,
                    open_access_only=open_access_only,
                    seen_papers=papers,
                )
            
            # ── Phase 3: Trigram similarity backup (last resort) ──
            if len(papers) < limit and query:
                log.info(
                    "search_papers: OR fallback returned %d (< %d), trying trigram",
                    len(papers), limit,
                )
                papers = _search_trigram_fallback(
                    cur, query, limit,
                    year_from=year_from, year_to=year_to,
                    sources=sources, venue_types=venue_types,
                    open_access_only=open_access_only,
                    seen_papers=papers,
                )
            
            return papers
    
    except Exception as e:
        log.error(f"Error searching papers: {e}")
        return []
    finally:
        put_connection(conn)


def _search_or_fallback(
    cur,
    query: str,
    limit: int,
    year_from: int | None = None,
    year_to: int | None = None,
    sources: list[str] | None = None,
    venue_types: list[str] | None = None,
    open_access_only: bool = False,
    seen_papers: list[Paper] | None = None,
) -> list[Paper]:
    """OR-based fallback: build tsquery with | between words."""
    seen_dois = {p.doi for p in (seen_papers or []) if p.doi}
    seen_titles = {normalize_title(p.title) for p in (seen_papers or []) if p.title}
    
    # Build OR tsquery: filter generic words first, then join with |
    words = re.findall(r"[a-zA-Z0-9]+", query.lower())
    filtered_words = _filter_or_words(words)
    if not filtered_words:
        log.warning("_search_or_fallback: all words filtered out for query='%s'", query[:80])
        return list(seen_papers or [])
    or_query = " | ".join(filtered_words)
    log.info("_search_or_fallback: %d words → %d filtered, or_query=%s",
             len(words), len(filtered_words), or_query[:120])
    
    conditions: list[str] = []
    params: list = []
    
    # Use to_tsquery with OR | separators for broader matching
    conditions.append("""
        (title_tsv @@ to_tsquery('english', %s) 
         OR abstract_tsv @@ to_tsquery('english', %s))
    """)
    params.extend([or_query, or_query])
    
    if year_from:
        conditions.append("year >= %s")
        params.append(year_from)
    if year_to:
        conditions.append("year <= %s")
        params.append(year_to)
    if sources:
        conditions.append(
            "(source = ANY(%s) OR EXISTS ("
            "SELECT 1 FROM paper_sources ps "
            "WHERE ps.paper_id = papers.id "
            "AND ps.source = ANY(%s)))"
        )
        params.append(sources)
        params.append(sources)
    if venue_types:
        conditions.append("venue_type = ANY(%s)")
        params.append(venue_types)
    if open_access_only:
        conditions.append("is_open_access = TRUE")
    
    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    
    fetch_limit = limit * 3  # oversample, dedup later
    
    search_query = f"""
        SELECT {_COLUMNS},
               ({_SCORE_EXPR}) AS score
        FROM papers
        WHERE {where_clause}
        ORDER BY score DESC
        LIMIT %s;
    """
    # SELECT %s must be BEFORE WHERE %s (same ordering fix as search_papers)
    params.insert(0, or_query)  # for _SCORE_EXPR in SELECT
    params.append(fetch_limit)  # for LIMIT
    
    cur.execute(search_query, params)
    rows = cur.fetchall()
    
    papers = list(seen_papers or [])
    for r in rows:
        p = _row_to_paper(r)
        # Minimum score threshold: weak OR matches (db_score < 0.15) are noise
        if p.db_score is not None and p.db_score < 0.15:
            continue
        doi_key = p.doi.lower() if p.doi else None
        title_key = normalize_title(p.title)
        if (doi_key and doi_key in seen_dois) or (title_key and title_key in seen_titles):
            continue
        papers.append(p)
        if doi_key:
            seen_dois.add(doi_key)
        if title_key:
            seen_titles.add(title_key)
        if len(papers) >= limit:
            break
    
    return papers


def _search_trigram_fallback(
    cur,
    query: str,
    limit: int,
    year_from: int | None = None,
    year_to: int | None = None,
    sources: list[str] | None = None,
    venue_types: list[str] | None = None,
    open_access_only: bool = False,
    seen_papers: list[Paper] | None = None,
) -> list[Paper]:
    """Trigram similarity fallback using pg_trgm on title."""
    seen_dois = {p.doi for p in (seen_papers or []) if p.doi}
    seen_titles = {normalize_title(p.title) for p in (seen_papers or []) if p.title}
    
    conditions: list[str] = ["similarity(title, %s) > 0.15"]
    params: list = [query]
    
    if year_from:
        conditions.append("year >= %s")
        params.append(year_from)
    if year_to:
        conditions.append("year <= %s")
        params.append(year_to)
    if sources:
        conditions.append(
            "(source = ANY(%s) OR EXISTS ("
            "SELECT 1 FROM paper_sources ps "
            "WHERE ps.paper_id = papers.id "
            "AND ps.source = ANY(%s)))"
        )
        params.append(sources)
        params.append(sources)
    if venue_types:
        conditions.append("venue_type = ANY(%s)")
        params.append(venue_types)
    if open_access_only:
        conditions.append("is_open_access = TRUE")
    
    where_clause = " AND ".join(conditions)
    fetch_limit = limit * 3
    
    search_query = f"""
        SELECT {_COLUMNS},
               similarity(title, %s) * 10.0
               + COALESCE(LN(NULLIF(citations, 0) + 1), 0) * 0.5
               + (COALESCE(year, 2000) - 1900) / 100.0 * 0.3 AS score
        FROM papers
        WHERE {where_clause}
        ORDER BY score DESC
        LIMIT %s;
    """
    # SELECT similarity %s comes before WHERE %s in SQL text
    params.insert(0, query)   # for SELECT similarity()
    params.append(fetch_limit)  # for LIMIT
    
    cur.execute(search_query, params)
    rows = cur.fetchall()
    
    papers = list(seen_papers or [])
    for r in rows:
        p = _row_to_paper(r)
        doi_key = p.doi.lower() if p.doi else None
        title_key = normalize_title(p.title)
        if (doi_key and doi_key in seen_dois) or (title_key and title_key in seen_titles):
            continue
        papers.append(p)
        if doi_key:
            seen_dois.add(doi_key)
        if title_key:
            seen_titles.add(title_key)
        if len(papers) >= limit:
            break
    
    return papers


def get_papers_by_dois(dois: list[str]) -> dict[str, Paper]:
    """Get papers by DOIs. Returns dict of doi -> Paper."""
    if not dois:
        return {}
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT " + _COLUMNS + " FROM papers WHERE doi = ANY(%s);", (dois,))
            
            papers = {}
            for row in cur.fetchall():
                papers[row[0]] = _row_to_paper(row)
            
            return papers
    
    except Exception as e:
        log.error(f"Error getting papers by DOIs: {e}")
        return {}
    finally:
        put_connection(conn)


def get_papers_by_titles(titles: list[str]) -> dict[str, Paper]:
    """Get papers by normalized titles. Returns dict of normalized_title -> Paper."""
    if not titles:
        return {}
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Normalize titles for lookup
            normalized = [normalize_title(t) for t in titles if t]
            
            cur.execute(f"""
                SELECT {_COLUMNS}
                FROM papers
                WHERE title_normalized = ANY(%s);
            """, (normalized,))
            
            papers = {}
            for row in cur.fetchall():
                title_norm = normalize_title(row[1])
                if title_norm:
                    papers[title_norm] = _row_to_paper(row)
            
            return papers
    
    except Exception as e:
        log.error(f"Error getting papers by titles: {e}")
        return {}
    finally:
        put_connection(conn)


def create_slr_job(
    query: str,
    sources: list[str],
    limit_per_source: int,
) -> int:
    """Create SLR job record. Returns job ID."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO slr_jobs (query, sources, limit_per_source, status)
                VALUES (%s, %s, %s, 'running')
                RETURNING id;
            """, (query, Json(sources), limit_per_source))
            
            job_id = cur.fetchone()[0]
            conn.commit()
            return job_id
    
    except Exception as e:
        conn.rollback()
        log.error(f"Error creating SLR job: {e}")
        raise
    finally:
        put_connection(conn)


def complete_slr_job(
    job_id: int,
    total_papers: int,
    cached_papers: int,
    new_papers: int,
    status: str = "completed",
):
    """Mark SLR job as completed."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE slr_jobs
                SET status = %s,
                    total_papers = %s,
                    cached_papers = %s,
                    new_papers = %s,
                    completed_at = NOW()
                WHERE id = %s;
            """, (status, total_papers, cached_papers, new_papers, job_id))
            conn.commit()
    
    except Exception as e:
        conn.rollback()
        log.error(f"Error completing SLR job: {e}")
        raise
    finally:
        put_connection(conn)


def save_slr_papers(job_id: int, paper_ids: list[int], scores: list[float] | None = None):
    """Save SLR papers mapping."""
    if not paper_ids:
        return
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            records = []
            for i, paper_id in enumerate(paper_ids):
                score = scores[i] if scores else None
                records.append((job_id, paper_id, score, i + 1))
            
            execute_values(cur, """
                INSERT INTO slr_papers (job_id, paper_id, relevance_score, rank)
                VALUES %s
                ON CONFLICT (job_id, paper_id) DO UPDATE SET
                    relevance_score = EXCLUDED.relevance_score,
                    rank = EXCLUDED.rank;
            """, records, page_size=100)
            
            conn.commit()
    
    except Exception as e:
        conn.rollback()
        log.error(f"Error saving SLR papers: {e}")
        raise
    finally:
        put_connection(conn)


def get_slr_papers(job_id: int) -> list[Paper]:
    """Get all papers for an SLR job."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    p.doi, p.title, p.authors, p.year, p.venue, p.venue_type,
                    p.abstract, p.citations, p.is_open_access, p.url, p.pdf_url,
                    p.source, p.source_id, p.paper_type, p.publisher
                FROM papers p
                JOIN slr_papers sp ON p.id = sp.paper_id
                WHERE sp.job_id = %s
                ORDER BY sp.relevance_score DESC, sp.rank;
            """, (job_id,))
            
            papers = []
            for row in cur.fetchall():
                papers.append(Paper(
                    doi=row[0],
                    title=row[1],
                    authors=row[2] if row[2] else [],
                    year=row[3],
                    venue=row[4],
                    venue_type=row[5],
                    abstract=row[6],
                    citations=row[7],
                    is_open_access=row[8],
                    url=row[9],
                    pdf_url=row[10],
                    source=row[11],
                    source_id=row[12],
                    type=row[13],
                    publisher=row[14],
                ))
            
            return papers
    
    except Exception as e:
        log.error(f"Error getting SLR papers: {e}")
        return []
    finally:
        put_connection(conn)


def get_db_stats() -> dict:
    """Get database statistics."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM papers;")
            total_papers = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(DISTINCT source) FROM paper_sources;")
            total_sources = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM slr_jobs;")
            total_jobs = cur.fetchone()[0]
            
            return {
                "total_papers": total_papers,
                "total_sources": total_sources,
                "total_jobs": total_jobs,
            }
    
    except Exception as e:
        log.error(f"Error getting DB stats: {e}")
        return {}
    finally:
        put_connection(conn)