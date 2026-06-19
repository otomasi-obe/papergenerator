#!/usr/bin/env python3
"""
Retrofit abstracts: OpenAlex DOI lookup → Semantic Scholar fallback
Parallel mode: 10 threads, ~10 req/s, targets crossref+openalex+scopus+core
Skips: pubmed (0% hit), ssrn (0% hit)
"""

import os, sys, time, logging, threading, queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx, psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [retrofit] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("retrofit")

DB = {"host": "/var/run/postgresql", "database": "paper_database", "user": "sirobo"}
WORKERS = 10
DELAY = 0.05

_lock = threading.Lock()
stats = {"processed": 0, "oa_hits": 0, "ss_hits": 0, "miss": 0}

def decode_oa(inv):
    if not inv or not isinstance(inv, dict): return ""
    pos = []
    for w, ps in inv.items():
        for p in ps: pos.append((p, w))
    pos.sort()
    return " ".join(w for _, w in pos)[:5000]

_thread_local = threading.local()

def get_client():
    if not hasattr(_thread_local, "client"):
        _thread_local.client = httpx.Client(timeout=15.0)
    return _thread_local.client


def enrich_one(doi: str) -> tuple[str, str] | None:
    """Returns (api_source, abstract) or None. Tries OpenAlex then Semantic Scholar."""
    client = get_client()
    time.sleep(DELAY)
    # Phase 1: OpenAlex
    try:
        r = client.get(f"https://api.openalex.org/works/doi:{doi}", timeout=15.0)
        if r.status_code == 200:
            js = r.json()
            ab = decode_oa(js.get("abstract_inverted_index"))
            if ab: return ("oa", ab)
    except:
        pass
    # Phase 2: Semantic Scholar
    try:
        r = client.get(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}", params={"fields": "title,abstract"}, timeout=15.0)
        if r.status_code == 200:
            js = r.json()
            ab = (js.get("abstract") or "").strip()
            if ab: return ("ss", ab[:5000])
    except:
        pass
    return None

def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM papers WHERE (abstract IS NULL OR trim(abstract) = '') AND doi IS NOT NULL AND doi != '' AND source NOT IN ('ssrn', 'dblp', 'pubmed')")
    total = cur.fetchone()[0]
    log.info(f"Papers to enrich (skipped ssrn/dblp/pubmed = 0% hit): {total:,}")

    t0 = time.time()
    batch_no = 0

    while True:
        cur.execute("""
            SELECT id, doi FROM papers
            WHERE (abstract IS NULL OR trim(abstract) = '')
            AND doi IS NOT NULL AND doi != ''
            AND source NOT IN ('ssrn', 'dblp', 'pubmed')
            ORDER BY source, id
            LIMIT 500
        """)
        rows = cur.fetchall()
        if not rows: break

        updates = []
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            fut = {pool.submit(enrich_one, doi): (pid, doi) for pid, doi in rows}
            for f in as_completed(fut):
                pid, doi = fut[f]
                result = f.result()
                if result:
                    api, ab = result
                    updates.append((ab, pid))
                    with _lock:
                        if api == "oa": stats["oa_hits"] += 1
                        else: stats["ss_hits"] += 1
                else:
                    with _lock: stats["miss"] += 1

        if updates:
            for ab, pid in updates:
                cur.execute("UPDATE papers SET abstract=%s WHERE id=%s", (ab, pid))
            conn.commit()

        with _lock:
            stats["processed"] += len(rows)

        batch_no += 1
        elapsed = time.time() - t0
        rate = stats["processed"] / max(elapsed, 0.1)
        pct = 100.0 * stats["processed"] / total
        rem = total - stats["processed"]
        eta = (rem / rate) / 3600 if rate > 0 else 0
        hit = stats["oa_hits"] + stats["ss_hits"]
        oa_pct = 100.0 * stats["oa_hits"] / max(stats["processed"], 1)
        ss_pct = 100.0 * stats["ss_hits"] / max(stats["processed"], 1)

        if batch_no % 2 == 0:
            print(f"[{stats['processed']:>7,}/{total:,} {pct:5.1f}%] OA={stats['oa_hits']:>5,}({oa_pct:.0f}%) SS={stats['ss_hits']:>5,}({ss_pct:.0f}%) rate={rate:.0f}/s ETA={eta:.1f}h", flush=True)

    conn.close()
    el = time.time() - t0
    print(f"\nDONE: {stats['processed']:,} processed, {stats['oa_hits']+stats['ss_hits']:,} enriched ({stats['oa_hits']:,} OA + {stats['ss_hits']:,} SS) in {el:.0f}s, hit rate: {100*(stats['oa_hits']+stats['ss_hits'])/max(stats['processed'],1):.1f}%", flush=True)

if __name__ == "__main__":
    main()