#!/usr/bin/env python3
"""
Test semua fetcher dengan target 500 paper, query berbeda-beda.
Cek screening detail: title, authors, year, doi, url, abstract.
Timeout 120s per fetcher.
Output: JSON + CSV + laporan screening ke output/test_500/
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

BACKEND = Path(__file__).resolve().parents[2]  # .../backend/tools/Literatur → ... → backend
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv
load_dotenv(BACKEND.parent / ".env", override=True)

import logging
logging.getLogger().setLevel(logging.WARNING)
for lname in ("tools.Literatur", "http_client", "httpx", "urllib3", "httpcore"):
    logging.getLogger(lname).setLevel(logging.WARNING)

from tools.Literatur.fetchers import ALL
from tools.Literatur.http_client import get_client

# ── Konfigurasi ──────────────────────────────────────────────────────────

TARGET = 500          # target papers per fetcher
TIMEOUT_SEC = 120     # timeout per fetcher (lebih panjang untuk 500)
OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "test_500"

# Query berbeda-beda per fetcher (sesuai strength masing2)
FETCHER_QUERIES = {
    "arxiv":            "deep learning neural network architecture optimization",
    "openalex":         "climate change renewable energy carbon emission policy",
    "crossref":         "machine learning natural language processing text classification",
    "semantic_scholar": "graph neural network knowledge graph embedding representation",
    "pubmed":           "diabetes mellitus treatment insulin resistance metabolic syndrome",
    "pmc":              "COVID-19 SARS-CoV-2 vaccine efficacy immunization clinical trial",
    "europepmc":        "cancer tumor immunotherapy checkpoint inhibitor therapy",
    "biorxiv":          "CRISPR gene editing protein folding molecular biology",
    "zenodo":           "open science research data",
    "datacite":         "biodiversity ecology species conservation habitat loss",
    "openaire":         "EU research innovation funding horizon grants collaboration",
    "scopus":           "machine learning deep learning neural network",
    "core":             "open access institutional repository preprint scholarly",
    "ieee":             "embedded system FPGA real-time signal processing hardware",
    "dblp":             "distributed system database query optimization performance",
    "doaj":             "public health epidemiology disease prevention community health",
    "hal":              "physics simulation computational method",
    "plos":             "evolutionary biology genetics population genome sequencing",
    "sinta":            "pendidikan vokasi kompetensi kurikulum pembelajaran",
    "orcid":            "machine learning",
    "unpaywall":        "open access full text PDF availability scholarly article",
    "opencitations":    "machine learning deep learning",
    "google_books":     "artificial intelligence history philosophy technology society",
    "open_library":     "machine learning",
    "doab":             "economics development policy governance institutions",
    "oapen":            "humanities social science history culture European",
    "gutendex":         "philosophy science nature mathematics classic literature",
    "dimensions":       "global health infectious disease pandemic response policy",
    "lens":             "patent innovation technology transfer intellectual property",
    "wos":              "interdisciplinary research cross-domain collaboration impact",
    "sciencedirect":    "materials science nanotechnology semiconductor polymer",
    "embase":           "pharmacology drug interaction adverse effect clinical",
    "clinicalkey":      "clinical practice guideline evidence-based medicine diagnosis",
    "cambridge":        "political science governance democracy institution law",
    "web":              "sustainable development goal SDG implementation progress",
}

# Fetcher yang known slow/broken — skip atau warning
KNOWN_TIMEOUT = {"oapen"}
KNOWN_BROKEN = {"dblp", "biorxiv", "unpaywall", "opencitations"}
KNOWN_NEED_KEY = {"dimensions", "lens", "wos", "sciencedirect", "embase", "clinicalkey"}
KNOWN_RATE_LIMITED = {"semantic_scholar", "google_books"}

EXCLUDE = {"crossref_publishers"}  # alias, skip

# ── Helpers ───────────────────────────────────────────────────────────────

class TimeoutError(Exception):
    pass

def _alarm(signum, frame):
    raise TimeoutError(f"TIMEOUT {TIMEOUT_SEC}s")

def screening_detail(papers: list[dict]) -> dict:
    """Cek kelengkapan field setiap paper."""
    total = len(papers)
    if total == 0:
        return {"total": 0}

    has_title = sum(1 for p in papers if p.get("title"))
    has_authors = sum(1 for p in papers if p.get("authors"))
    has_year = sum(1 for p in papers if p.get("year"))
    has_doi = sum(1 for p in papers if p.get("doi"))
    has_url = sum(1 for p in papers if p.get("url"))
    has_abstract = sum(1 for p in papers if p.get("abstract"))
    has_pdf = sum(1 for p in papers if p.get("pdf_url"))
    has_venue = sum(1 for p in papers if p.get("venue"))
    has_type = sum(1 for p in papers if p.get("type"))
    has_is_oa = sum(1 for p in papers if p.get("is_open_access") is not None)

    completeness_score = (
        has_title + has_authors + has_year + has_doi + has_url + has_abstract
    ) / (total * 6) * 100

    return {
        "total": total,
        "has_title": has_title,
        "has_title_pct": round(has_title/total*100, 1),
        "has_authors": has_authors,
        "has_authors_pct": round(has_authors/total*100, 1),
        "has_year": has_year,
        "has_year_pct": round(has_year/total*100, 1),
        "has_doi": has_doi,
        "has_doi_pct": round(has_doi/total*100, 1),
        "has_url": has_url,
        "has_url_pct": round(has_url/total*100, 1),
        "has_abstract": has_abstract,
        "has_abstract_pct": round(has_abstract/total*100, 1),
        "has_pdf_url": has_pdf,
        "has_pdf_pct": round(has_pdf/total*100, 1),
        "has_venue": has_venue,
        "has_venue_pct": round(has_venue/total*100, 1),
        "has_type": has_type,
        "has_type_pct": round(has_type/total*100, 1),
        "has_is_oa": has_is_oa,
        "has_is_oa_pct": round(has_is_oa/total*100, 1),
        "completeness_score": round(completeness_score, 1),
        "sample": papers[:3],
    }

def paper_to_dict(p) -> dict:
    return {
        "title": p.title[:150] if p.title else None,
        "authors": p.authors[:5] if p.authors else [],
        "year": p.year,
        "doi": p.doi,
        "url": p.url,
        "pdf_url": p.pdf_url,
        "venue": p.venue,
        "is_open_access": p.is_open_access,
        "type": p.type,
        "abstract": (p.abstract[:200] if p.abstract else None),
    }

def test_one(fname, mod, query) -> tuple[list, float, str | None]:
    client = get_client(rotating_ua=True)
    papers = []
    error = None
    start = time.monotonic()

    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(TIMEOUT_SEC)
    try:
        for p in mod.search(client, query, limit=TARGET):
            papers.append(paper_to_dict(p))
            if len(papers) >= TARGET:
                break
    except TimeoutError as e:
        error = str(e)
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

    elapsed = round(time.monotonic() - start, 1)
    return papers, elapsed, error


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fetchers = {k: v for k, v in ALL.items() if k not in EXCLUDE}
    total = len(fetchers)

    print(f"=== Test 500 Papers per Fetcher ===")
    print(f"Fetchers: {total} | Target: {TARGET} | Timeout: {TIMEOUT_SEC}s")
    print(f"Started: {datetime.now().isoformat()}")
    print()

    all_results = {}
    summary_rows = []
    i = 0

    for fname in sorted(fetchers.keys()):
        i += 1
        mod = fetchers[fname]
        if not hasattr(mod, "search"):
            print(f"  [{i:3d}/{total}] SKIP {fname} (no search fn)")
            continue

        query = FETCHER_QUERIES.get(fname, "machine learning artificial intelligence")
        tag = ""
        if fname in KNOWN_TIMEOUT: tag = "[SLOW]"
        elif fname in KNOWN_BROKEN: tag = "[BROKEN]"
        elif fname in KNOWN_NEED_KEY: tag = "[KEY?]"
        elif fname in KNOWN_RATE_LIMITED: tag = "[RATE]"

        print(f"  [{i:3d}/{total}] Testing {fname:22s} {tag}")
        print(f"         Query: {query[:80]}")

        papers, elapsed, error = test_one(fname, mod, query)
        screen = screening_detail(papers)

        # Rate-limit-friendly delay between fetchers
        if i < total:
            time.sleep(3)

        status = "OK" if papers and not error else ("EMPTY" if not error else "ERR")
        if error and papers:
            status = "PARTIAL"  # got some before timeout/error

        marker = {"OK":"✓","EMPTY":"—","ERR":"✗","PARTIAL":"~"}[status]

        print(f"         {marker} {len(papers):4d} papers | {elapsed:6.1f}s | status={status}" +
              (f" | {error[:80]}" if error else ""))
        if papers:
            s = screen
            print(f"         Screening: title={s['has_title_pct']}% auth={s['has_authors_pct']}% "
                  f"year={s['has_year_pct']}% doi={s['has_doi_pct']}% "
                  f"url={s['has_url_pct']}% abs={s['has_abstract_pct']}% "
                  f"complete={s['completeness_score']}%")
        print()

        all_results[fname] = {
            "query": query,
            "count": len(papers),
            "elapsed_sec": elapsed,
            "status": status,
            "error": error or "",
            "screening": screen,
            "papers": papers,
        }

        summary_rows.append({
            "fetcher": fname,
            "query": query[:60],
            "count": len(papers),
            "target_pct": round(len(papers)/TARGET*100, 1),
            "elapsed_sec": elapsed,
            "status": status,
            "error": (error or "")[:150],
            "has_title_pct": screen.get("has_title_pct", 0),
            "has_authors_pct": screen.get("has_authors_pct", 0),
            "has_year_pct": screen.get("has_year_pct", 0),
            "has_doi_pct": screen.get("has_doi_pct", 0),
            "has_url_pct": screen.get("has_url_pct", 0),
            "has_abstract_pct": screen.get("has_abstract_pct", 0),
            "completeness_score": screen.get("completeness_score", 0),
            "known_issue": tag,
        })

    # ── Save ──────────────────────────────────────────────────────────────

    ts = datetime.now().strftime("%Y%m%d_%H%M")

    # JSON (tanpa paper samples untuk ukuran kecil)
    lite = {k: {kk: vv for kk, vv in v.items() if kk != "papers"} for k, v in all_results.items()}
    json_path = OUTPUT_DIR / f"results_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"meta": {"date": datetime.now().isoformat(), "target": TARGET},
                   "results": lite}, f, indent=2, ensure_ascii=False, default=str)

    # CSV
    csv_path = OUTPUT_DIR / f"summary_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        writer.writeheader()
        writer.writerows(summary_rows)

    # ── Final Report ──────────────────────────────────────────────────────

    print("=" * 110)
    print("LAPORAN AKHIR - RANKING FETCHER (by count desc)")
    print("=" * 110)
    print(f"{'Fetcher':22s} | {'Count':>5s} | {'%Target':>7s} | {'Time':>6s} | {'Status':8s} | "
          f"{'Title%':>6s} | {'Auth%':>5s} | {'Year%':>5s} | {'DOI%':>5s} | {'URL%':>5s} | {'Abs%':>5s} | {'Comp%':>5s}")
    print("-" * 110)

    sorted_rows = sorted(summary_rows, key=lambda r: r["count"], reverse=True)
    reach_500 = []
    partial = []
    empty = []

    for r in sorted_rows:
        c = r["count"]
        print(f"{r['fetcher']:22s} | {c:5d} | {r['target_pct']:6.1f}% | {r['elapsed_sec']:6.1f}s | "
              f"{r['status']:8s} | {r['has_title_pct']:5.1f}% | {r['has_authors_pct']:4.1f}% | "
              f"{r['has_year_pct']:4.1f}% | {r['has_doi_pct']:4.1f}% | {r['has_url_pct']:4.1f}% | "
              f"{r['has_abstract_pct']:4.1f}% | {r['completeness_score']:4.1f}%"
              + (f"  {r['known_issue']}" if r['known_issue'] else ""))
        if c >= 500:
            reach_500.append(r['fetcher'])
        elif c > 0:
            partial.append(r['fetcher'])
        else:
            empty.append(r['fetcher'])

    grand = sum(r["count"] for r in summary_rows)
    ok_cnt = sum(1 for r in summary_rows if r["status"] == "OK")
    partial_cnt = sum(1 for r in summary_rows if r["status"] == "PARTIAL")
    err_cnt = sum(1 for r in summary_rows if r["status"] == "ERR")
    empty_cnt = sum(1 for r in summary_rows if r["status"] == "EMPTY")

    print()
    print(f"TOTAL PAPERS   : {grand}")
    print(f"FETCHERS REACH 500+ : {len(reach_500)} -> {', '.join(reach_500)}")
    print(f"FETCHERS PARTIAL    : {len(partial)} -> {', '.join(partial)}")
    print(f"FETCHERS EMPTY/ERR  : {len(empty)} -> {', '.join(empty)}")
    print()
    print(f"Status OK={ok_cnt} PARTIAL={partial_cnt} ERR={err_cnt} EMPTY={empty_cnt}")
    print(f"Finished: {datetime.now().isoformat()}")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")


if __name__ == "__main__":
    main()
