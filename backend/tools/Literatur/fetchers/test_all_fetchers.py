#!/usr/bin/env python3
"""
Comprehensive test: 34 fetchers × 5 domain queries.
Uses signal alarm for per-test timeout (15s default) to avoid stalls.
Output: JSON results + summary CSV in output/ directory.
"""

import sys
import os
import json
import csv
import time
import signal
import traceback
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

# Setup paths
BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

# Load .env
from dotenv import load_dotenv
load_dotenv(BACKEND.parent / ".env", override=False)

from tools.Literatur.fetchers import ALL
from tools.Literatur.http_client import get_client
from tools.Literatur.paper import Paper

# ── 5 Domain Queries ──────────────────────────────────────────────────────
QUERIES = {
    "AI/ML": "transformer attention mechanism deep learning",
    "Medical": "mRNA vaccine cancer immunotherapy",
    "Environment": "microplastic pollution marine ecosystem",
    "Education": "project based learning STEM education",
    "Economics": "monetary policy inflation central bank digital currency",
}

LIMIT_PER_QUERY = 5
TIMEOUT_SEC = 20  # per fetcher-query pair
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Exclude batch alias
FETCHERS = {name: mod for name, mod in ALL.items() if name != "crossref_publishers"}


class TimeoutError(Exception):
    pass


def _alarm_handler(signum, frame):
    raise TimeoutError("alarm timeout")


def paper_to_dict(p):
    return {
        "title": p.title[:120] if p.title else "",
        "authors": p.authors[:3] if p.authors else [],
        "year": p.year,
        "doi": p.doi,
        "url": p.url,
        "pdf_url": p.pdf_url,
        "venue": p.venue,
        "is_open_access": p.is_open_access,
        "type": p.type,
    }


def test_fetcher(name, search_fn, query, limit):
    """Test a single fetcher with a single query. Returns (papers, elapsed, error)."""
    client = get_client(rotating_ua=True)
    papers = []
    error = None
    start = time.monotonic()

    # Set alarm for timeout
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(TIMEOUT_SEC)

    try:
        for paper in search_fn(client, query, limit=limit):
            papers.append(paper_to_dict(paper))
            if len(papers) >= limit:
                break
    except TimeoutError:
        error = f"TIMEOUT after {TIMEOUT_SEC}s"
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:150]}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

    elapsed = time.monotonic() - start
    return papers, round(elapsed, 2), error


def main():
    # Reset logging to WARNING to reduce noise
    import logging
    logging.getLogger().setLevel(logging.WARNING)
    for lname in ("tools.Literatur", "http_client", "httpx", "urllib3"):
        logging.getLogger(lname).setLevel(logging.WARNING)

    print(f"=== PaperGenerator Fetcher Comprehensive Test ===")
    print(f"Fetchers: {len(FETCHERS)} | Queries: {len(QUERIES)} | Limit/query: {LIMIT_PER_QUERY} | Timeout: {TIMEOUT_SEC}s")
    print(f"Started: {datetime.now().isoformat()}")
    print()

    results = {}
    summary_rows = []
    total_tests = len(FETCHERS) * len(QUERIES)
    test_num = 0

    for fname in sorted(FETCHERS.keys()):
        mod = FETCHERS[fname]
        search_fn = getattr(mod, "search", None)
        if not search_fn:
            continue

        results[fname] = {}
        for domain, query in QUERIES.items():
            test_num += 1
            papers, elapsed, error = test_fetcher(fname, search_fn, query, LIMIT_PER_QUERY)
            results[fname][domain] = {
                "query": query,
                "papers": papers,
                "elapsed_sec": elapsed,
                "error": error,
                "count": len(papers),
            }
            status = "OK" if not error and papers else ("EMPTY" if not error else "ERR")
            marker = "✓" if status == "OK" else ("—" if status == "EMPTY" else "✗")
            print(f"  [{test_num:3d}/{total_tests}] {marker} {fname:20s} | {domain:12s} | {len(papers):2d} papers | {elapsed:5.1f}s" + (f" | {error[:80]}" if error else ""))

            summary_rows.append({
                "fetcher": fname,
                "domain": domain,
                "query": query,
                "count": len(papers),
                "elapsed_sec": elapsed,
                "status": status,
                "error": (error or "")[:200],
            })

    # ── Save Results ──────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = OUTPUT_DIR / "test_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "date": datetime.now().isoformat(),
                "total_fetchers": len(FETCHERS),
                "total_queries": len(QUERIES),
                "limit_per_query": LIMIT_PER_QUERY,
                "timeout_sec": TIMEOUT_SEC,
            },
            "results": results,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nJSON: {json_path}")

    # CSV
    csv_path = OUTPUT_DIR / "test_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["fetcher", "domain", "query", "count", "elapsed_sec", "status", "error"])
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"CSV:  {csv_path}")

    # ── Pretty Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 110)
    print("FETCHER SUMMARY (sorted by total papers)")
    print("=" * 110)
    print(f"{'Fetcher':20s} | {'Papers':>6s} | {'Avg(s)':>6s} | {'OK':>3s} | {'MT':>3s} | {'ERR':>3s} | AI  Med Env Edu Eco")
    print("-" * 110)

    fetcher_stats = []
    for fname in sorted(results.keys()):
        dd = results[fname]
        total = sum(d["count"] for d in dd.values())
        avg_t = sum(d["elapsed_sec"] for d in dd.values()) / len(dd) if dd else 0
        ok = sum(1 for d in dd.values() if d["count"] > 0 and not d["error"])
        empty = sum(1 for d in dd.values() if d["count"] == 0 and not d["error"])
        err = sum(1 for d in dd.values() if d["error"])
        counts = [dd.get(d, {}).get("count", 0) for d in QUERIES]
        fetcher_stats.append((fname, total, avg_t, ok, empty, err, counts))

    fetcher_stats.sort(key=lambda x: x[1], reverse=True)
    for fname, total, avg_t, ok, empty, err, counts in fetcher_stats:
        c = " ".join(f"{n:3d}" for n in counts)
        print(f"{fname:20s} | {total:6d} | {avg_t:6.1f} | {ok:3d} | {empty:3d} | {err:3d} | {c}")

    # Domain summary
    print(f"\n{'Domain':12s} | {'Total':>6s} | {'Working fetchers':>16s}")
    print("-" * 40)
    for domain in QUERIES:
        total = sum(results.get(fn, {}).get(domain, {}).get("count", 0) for fn in results)
        working = sum(1 for fn in results if results[fn].get(domain, {}).get("count", 0) > 0)
        print(f"{domain:12s} | {total:6d} | {working:16d}")

    grand = sum(d["count"] for fn in results for d in results[fn].values())
    total_ok = sum(1 for fn in results for d in results[fn].values() if d["count"] > 0 and not d["error"])
    total_err = sum(1 for fn in results for d in results[fn].values() if d["error"])
    total_empty = sum(1 for fn in results for d in results[fn].values() if d["count"] == 0 and not d["error"])
    print(f"\nGRAND TOTAL: {grand} papers | {total_ok} OK | {total_empty} EMPTY | {total_err} ERR")
    print(f"Finished: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
