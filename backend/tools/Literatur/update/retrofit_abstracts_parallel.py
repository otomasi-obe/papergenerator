#!/usr/bin/env python3
"""
Retrofit: Fetch missing abstracts via OpenAlex DOI lookup — PARALLEL version
=============================================================================
ThreadPoolExecutor with 10 workers. Each worker has own httpx client.
Target: 215K papers → ~30 minutes (vs 28h single-threaded).

Usage:
    cd /home/sirobo/papergenerator/backend
    .venv/bin/python -u tools/Literatur/update/retrofit_abstracts_parallel.py [--workers N]
"""

import os
import sys
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [retrofit] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("retrofit")

DB_CONFIG = {
    "host": "/var/run/postgresql",
    "database": "paper_database",
    "user": "sirobo",
}

DELAY = 0.05  # 20 req/sec per worker
WORKERS = 10
SAVE_EVERY = 1000

# Shared state
_lock = threading.Lock()
_stats = {"processed": 0, "enriched": 0}


def decode_abstract(inverted_index: dict) -> str:
    """Decode OpenAlex abstract_inverted_index → plain text."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def fetch_one(client: httpx.Client, paper_id: int, doi: str) -> tuple[int, str | None]:
    """Fetch abstract for one paper. Returns (paper_id, abstract) or (paper_id, None)."""
    try:
        time.sleep(DELAY)
        r = client.get(f"https://api.openalex.org/works/doi:{doi}", timeout=15.0)
        if r.status_code == 200:
            data = r.json()
            ai = data.get("abstract_inverted_index")
            if ai:
                abstract = decode_abstract(ai)[:5000]
                if abstract:
                    return (paper_id, abstract)
    except Exception:
        pass
    return (paper_id, None)


def main():
    workers = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--workers" else WORKERS

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Count total missing
    cur.execute("SELECT count(*) FROM papers WHERE abstract IS NULL OR trim(abstract) = ''")
    total_missing = cur.fetchone()[0]
    log.info(f"Papers without abstract: {total_missing:,}")
    log.info(f"Starting {workers} parallel workers")

    t_start = time.time()
    batch_num = 0

    while True:
        # Fetch next batch
        cur.execute("""
            SELECT id, doi FROM papers
            WHERE (abstract IS NULL OR trim(abstract) = '')
            AND doi IS NOT NULL AND doi != ''
            ORDER BY id
            LIMIT 1000
        """)
        rows = cur.fetchall()
        if not rows:
            break

        # Parallel fetch
        updates = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(fetch_one, httpx.Client(timeout=15.0), pid, doi): pid
                for pid, doi in rows
            }
            for future in as_completed(futures):
                paper_id, abstract = future.result()
                if abstract:
                    updates.append((abstract, paper_id))

        # Batch update
        if updates:
            for abstract, paper_id in updates:
                cur.execute(
                    "UPDATE papers SET abstract = %s WHERE id = %s",
                    (abstract, paper_id)
                )
            conn.commit()

        with _lock:
            _stats["processed"] += len(rows)
            _stats["enriched"] += len(updates)

        batch_num += 1
        elapsed = time.time() - t_start
        rate = _stats["processed"] / max(elapsed, 0.1)
        pct = 100.0 * _stats["processed"] / total_missing
        remaining = total_missing - _stats["processed"]
        eta = (remaining / rate) / 3600 if rate > 0 else 0

        if batch_num % 2 == 0:
            print(f"[{_stats['processed']:>7,}/{total_missing:,} {pct:5.1f}%] "
                  f"enriched={_stats['enriched']:>6,} "
                  f"rate={rate:.0f}/s ETA={eta:.1f}h", flush=True)

    conn.close()

    elapsed = time.time() - t_start
    print(f"\n{'='*60}", flush=True)
    print(f"DONE: {_stats['processed']:,} processed, {_stats['enriched']:,} enriched in {elapsed:.1f}s", flush=True)
    hit_rate = 100.0 * _stats["enriched"] / max(_stats["processed"], 1)
    print(f"Hit rate: {hit_rate:.1f}%", flush=True)


if __name__ == "__main__":
    main()