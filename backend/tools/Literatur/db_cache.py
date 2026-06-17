"""Paper Database Cache Module.

Provides fast lookup and caching of paper metadata in PostgreSQL.
Used by SLR orchestrator to:
1. Check DB first (cache hit) before fetching from API
2. Sync new papers from API to DB
3. Track which papers came from which source
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Iterable

import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values, Json

from .paper import Paper

log = logging.getLogger(__name__)

# Database connection settings
DB_CONFIG = {
    "host": os.getenv("PAPER_DB_HOST", "localhost"),
    "port": int(os.getenv("PAPER_DB_PORT", "5432")),
    "database": os.getenv("PAPER_DB_NAME", "paper_database"),
    "user": os.getenv("PAPER_DB_USER", "sirobo"),
    "password": os.getenv("PAPER_DB_PASS", "paper2026"),
}

# Connection pool — thread-safe, supports up to 50 concurrent connections
_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    """Lazy-init connection pool."""
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=50,
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
    import re
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
    Search papers in database. Returns list of Paper objects.
    
    Uses full-text search on title and abstract.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Build query
            conditions = []
            params = []
            
            # Full-text search
            if query:
                conditions.append("""
                    (title_tsv @@ plainto_tsquery('english', %s) 
                     OR abstract_tsv @@ plainto_tsquery('english', %s)
                     OR title ILIKE %s)
                """)
                params.extend([query, query, f"%{query}%"])
            
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
            
            where_clause = " AND ".join(conditions) if conditions else "TRUE"
            
            search_query = f"""
                SELECT 
                    doi, title, authors, year, venue, venue_type, abstract,
                    citations, is_open_access, url, pdf_url, source, source_id,
                    paper_type, publisher
                FROM papers
                WHERE {where_clause}
                ORDER BY 
                    ts_rank(title_tsv, plainto_tsquery('english', %s)) DESC,
                    citations DESC,
                    year DESC
                LIMIT %s;
            """
            
            params.append(query)
            params.append(limit)
            
            cur.execute(search_query, params)
            
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
        log.error(f"Error searching papers: {e}")
        return []
    finally:
        put_connection(conn)


def get_papers_by_dois(dois: list[str]) -> dict[str, Paper]:
    """Get papers by DOIs. Returns dict of doi -> Paper."""
    if not dois:
        return {}
    
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    doi, title, authors, year, venue, venue_type, abstract,
                    citations, is_open_access, url, pdf_url, source, source_id,
                    paper_type, publisher
                FROM papers
                WHERE doi = ANY(%s);
            """, (dois,))
            
            papers = {}
            for row in cur.fetchall():
                papers[row[0]] = Paper(
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
                )
            
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
            
            cur.execute("""
                SELECT 
                    doi, title, authors, year, venue, venue_type, abstract,
                    citations, is_open_access, url, pdf_url, source, source_id,
                    paper_type, publisher
                FROM papers
                WHERE title_normalized = ANY(%s);
            """, (normalized,))
            
            papers = {}
            for row in cur.fetchall():
                title_norm = normalize_title(row[1])
                if title_norm:
                    papers[title_norm] = Paper(
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
                    )
            
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
            
            cur.execute("""
                SELECT source, COUNT(*) 
                FROM paper_sources 
                GROUP BY source 
                ORDER BY COUNT(*) DESC;
            """)
            sources = {row[0]: row[1] for row in cur.fetchall()}
            
            cur.execute("SELECT COUNT(*) FROM slr_jobs;")
            total_jobs = cur.fetchone()[0]
            
            cur.execute("""
                SELECT year, COUNT(*) 
                FROM papers 
                WHERE year IS NOT NULL 
                GROUP BY year 
                ORDER BY year DESC 
                LIMIT 10;
            """)
            year_dist = {row[0]: row[1] for row in cur.fetchall()}
            
            return {
                "total_papers": total_papers,
                "total_sources": total_sources,
                "sources": sources,
                "total_jobs": total_jobs,
                "year_distribution": year_dist,
            }
    
    except Exception as e:
        log.error(f"Error getting DB stats: {e}")
        return {}
    finally:
        put_connection(conn)
