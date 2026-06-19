#!/usr/bin/env python3
"""
Retrofit: Fetch missing abstracts via OpenAlex DOI lookup
==========================================================
Scans papers without abstracts, enriches via OpenAlex API.
Rate: 10 req/sec (polite), batch 100 papers.
Target: 215K papers → ~6 hours.

Usage:
    cd /home/sirobo/papergenerator/backend
    .venv/bin/python -u tools/Literatur/update/retrofit_abstracts.py [--batch N] [--delay F]
"""

import os
import sys
import time
import logging

import httpx
import psycopg2

DB_CONFIG = {
    "host": "/var/run/postgresql",
    "database": "paper_database",
    "user": "sirobo",
}

BATCH_SIZE = 100
DELAY = 0.1  # 10 req/sec
SAVE_EVERY = 500  # commit every N enriched
logging.basicConfig(level=logging.INFO, format="%(asctime)s [retrofit] %(levelname)s: %(message)s")
# Suppress httpx INFO log spam
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("retrofit")


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


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


def fetch_abstract_oa(client: httpx.Client, doi: str) -> str | None:
    """Look up abstract via OpenAlex DOI. Returns abstract string or None."""
    try:
        r = client.get(f"https://api.openalex.org/works/doi:{doi}", timeout=15.0)
        if r.status_code != 200:
            return None
        data = r.json()
        ai = data.get("abstract_inverted_index")
        if ai:
            return decode_abstract(ai)[:5000]
    except Exception:
        pass
    return None


def main():
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--batch" else BATCH_SIZE
    delay = float(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--delay" else DELAY

    conn = get_conn()
    cur = conn.cursor()

    # Count total
    cur.execute("SELECT count(*) FROM papers WHERE abstract IS NULL OR trim(abstract) = ''")
    total_missing = cur.fetchone()[0]
    log.info(f"Papers without abstract: {total_missing:,}")

    client = httpx.Client(timeout=15.0)

    total_processed = 0
    total_enriched = 0
    t_start = time.time()

    while True:
        # Fetch batch of papers without abstracts that have DOI
        cur.execute("""
            SELECT id, doi FROM papers
            WHERE (abstract IS NULL OR trim(abstract) = '')
            AND doi IS NOT NULL AND doi != ''
            ORDER BY id
            LIMIT %s
        """, (batch_size,))

        rows = cur.fetchall()
        if not rows:
            break

        updates = []  # list of (abstract, id)
        for paper_id, doi in rows:
            time.sleep(delay)
            abstract = fetch_abstract_oa(client, doi)
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
            total_enriched += len(updates)

        total_processed += len(rows)
        elapsed = time.time() - t_start
        rate = total_processed / max(elapsed, 0.1)
        pct = 100.0 * total_processed / total_missing

        # Checkpoint
        if total_processed % SAVE_EVERY == 0 or not rows:
            remaining = total_missing - total_processed
            eta = (remaining / rate) / 3600 if rate > 0 else 0
            print(f"[{total_processed:>7,}/{total_missing:,} {pct:5.1f}%] "
                  f"enriched={total_enriched:>6,} "
                  f"rate={rate:.0f}/s ETA={eta:.1f}h", flush=True)

    conn.close()
    client.close()

    elapsed = time.time() - t_start
    print(f"\n{'='*60}", flush=True)
    print(f"DONE: {total_processed:,} processed, {total_enriched:,} enriched in {elapsed:.1f}s", flush=True)
    hit_rate = 100.0 * total_enriched / max(total_processed, 1)
    print(f"Hit rate: {hit_rate:.1f}%", flush=True)


if __name__ == "__main__":
    main()