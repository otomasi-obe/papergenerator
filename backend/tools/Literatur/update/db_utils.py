"""
Shared utilities for standalone bulk fetchers (CORE, Scopus, ScienceDirect).
DB connection, upsert, topic loading.
"""

import json
import os
import sys
import time
import logging
import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── DB Config ────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "/var/run/postgresql",
    "database": "paper_database",
    "user": "sirobo",
}
BATCH_SIZE = 100
_log = logging.getLogger("bulk_fetch")


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


# ── Upsert ───────────────────────────────────────────────────────────────────
def upsert_papers(conn, papers: list[dict]) -> int:
    """Batch upsert papers. Returns count of NEW papers inserted."""
    if not papers:
        return 0
    cur = conn.cursor()
    new_count = 0
    cols = ['doi', 'title', 'authors', 'year', 'venue', 'venue_type', 'abstract',
            'citations', 'is_open_access', 'url', 'pdf_url', 'source', 'source_id',
            'paper_type', 'publisher']

    for i in range(0, len(papers), BATCH_SIZE):
        batch = papers[i:i + BATCH_SIZE]
        if not batch:
            continue

        # Dedup within batch by title_normalized (lowercased title)
        seen_titles = set()
        deduped = []
        for p in batch:
            tkey = p.get('title', '').lower()
            if tkey and tkey not in seen_titles:
                seen_titles.add(tkey)
                deduped.append(p)
        batch = deduped
        if not batch:
            continue

        placeholders = []
        values = []
        for p in batch:
            placeholders.append('(' + ','.join(['%s'] * len(cols)) + ')')
            values.extend([
                    None if c == 'doi' and not p.get(c, '') else p.get(c, '')
                    for c in cols
                ])

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
        except Exception as e:
            conn.rollback()
            _log.error(f"upsert batch failed: {e}")
            continue

    conn.commit()
    cur.close()
    return new_count


# ── Topic Loading ────────────────────────────────────────────────────────────
def load_all_topics(data_dir: str) -> list[dict]:
    """
    Load and deduplicate topics from all JSON files in data_dir.
    Returns list of {field, topic} dicts with unique topics.
    """
    topics_map = {}  # topic_lower -> {field, topic}

    json_files = [
        os.path.join(data_dir, "mega_topics.json"),
        os.path.join(data_dir, "mega_topics_v3.json"),
        os.path.join(data_dir, "topics.json"),
    ]

    for fp in json_files:
        if not os.path.exists(fp):
            _log.warning(f"file not found: {fp}")
            continue
        with open(fp) as f:
            data = json.load(f)
        for item in data:
            topic = item.get("topic", "").strip()
            field = item.get("field", "").strip()
            if not topic:
                continue
            key = topic.lower()
            if key not in topics_map:
                topics_map[key] = {"field": field, "topic": topic}

    topics = list(topics_map.values())
    _log.info(f"Loaded {len(topics)} unique topics from {len(json_files)} files")
    return topics


def log_progress(source: str, topic: str, fetched: int, inserted: int, elapsed: float):
    rate = fetched / max(elapsed, 0.1)
    print(f"[{source}] {topic[:60]:60s} | fetched={fetched:5d} inserted={inserted:5d} | {rate:.0f} rec/s")