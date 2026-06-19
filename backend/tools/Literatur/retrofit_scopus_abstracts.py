#!/usr/bin/env python3
"""Retrofit Scopus paper abstracts via OpenAlex DOI lookup.
Scopus Search API doesn't return abstracts. This script enriches existing
Scopus papers by looking up their DOIs on OpenAlex and extracting abstracts.

Usage:
    .venv/bin/python tools/Literatur/retrofit_scopus_abstracts.py [--batch N] [--dry-run]
"""
import os, sys, time, argparse
import httpx
import psycopg2
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

DB_CONFIG = {
    'host': '/var/run/postgresql',
    'database': 'paper_database',
    'user': 'sirobo',
}

BATCH_SIZE = 50
DRY_RUN = False


def decode_abstract(inverted_index: dict) -> str:
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)[:5000]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, default=BATCH_SIZE)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=0, help='Max papers to process (0=all)')
    args = parser.parse_args()

    global DRY_RUN
    DRY_RUN = args.dry_run
    batch_size = args.batch
    limit = args.limit

    # Email for OpenAlex (polite pool)
    email = os.getenv("OPENALEX_EMAIL", "papergenerator@otomasi.app")

    pool = psycopg2.pool.ThreadedConnectionPool(1, 3, **DB_CONFIG)
    get_conn = lambda: pool.getconn()
    put_conn = lambda c: pool.putconn(c)

    # Count total
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM papers
        WHERE source = 'scopus'
        AND doi IS NOT NULL AND doi != ''
        AND (abstract IS NULL OR abstract = '')
    """)
    total = cur.fetchone()[0]
    cur.close()
    put_conn(conn)

    print(f"📚 {total} Scopus papers need abstract enrichment")
    if limit and limit < total:
        print(f"   Processing first {limit}")
        total = limit

    processed = 0
    enriched = 0
    failed = 0
    start_time = time.monotonic()

    while processed < total:
        conn = get_conn()
        cur = conn.cursor()
        remaining = min(batch_size, total - processed)

        cur.execute("""
            SELECT source_id, doi, title FROM papers
            WHERE source = 'scopus'
            AND doi IS NOT NULL AND doi != ''
            AND (abstract IS NULL OR abstract = '')
            LIMIT %s OFFSET %s
        """, (remaining, processed))
        rows = cur.fetchall()
        cur.close()
        put_conn(conn)

        if not rows:
            break

        updates = []
        for source_id, doi, title in rows:
            try:
                url = f"https://api.openalex.org/works/doi:{doi}"
                params = {"mailto": email}
                r = httpx.get(url, params=params, timeout=15.0)

                if r.status_code == 404:
                    continue  # DOI not in OpenAlex

                if r.status_code == 429:
                    print(f"  ⚠️ Rate limited, sleeping 60s...")
                    time.sleep(60)
                    continue

                if r.status_code != 200:
                    failed += 1
                    continue

                data = r.json()
                inv_idx = data.get("abstract_inverted_index")
                if not inv_idx or not isinstance(inv_idx, dict):
                    continue

                abstract = decode_abstract(inv_idx)
                if not abstract:
                    continue

                if not DRY_RUN:
                    updates.append((abstract[:5000], source_id))
                    enriched += 1
                else:
                    print(f"  [DRY] {title[:60]}... → {len(abstract)} chars")
                    enriched += 1

            except httpx.TimeoutException:
                failed += 1
                continue
            except Exception as e:
                failed += 1
                continue

            # Polite rate: ~10 req/s
            time.sleep(0.1)

        # Batch update DB
        if updates and not DRY_RUN:
            conn = get_conn()
            cur = conn.cursor()
            try:
                cur.executemany("""
                    UPDATE papers SET abstract = %s
                    WHERE source_id = %s AND source = 'scopus'
                    AND (abstract IS NULL OR abstract = '')
                """, updates)
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"  ❌ DB update error: {e}")
                enriched -= len(updates)
                failed += len(updates)
            finally:
                cur.close()
                put_conn(conn)

        processed += len(rows)
        elapsed = time.monotonic() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        print(f"  [{processed}/{total}] enriched={enriched} failed={failed} "
              f"({rate:.0f}/s, {elapsed:.0f}s)")

    elapsed = time.monotonic() - start_time
    print(f"\n✅ Done: {enriched} abstracts enriched, {failed} failed "
          f"({elapsed:.0f}s, {total/elapsed:.1f}/s)")

    pool.closeall()


if __name__ == '__main__':
    main()