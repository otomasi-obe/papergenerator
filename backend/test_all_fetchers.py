#!/usr/bin/env python3
"""Comprehensive fetcher test - tests ALL 32 fetchers with proper queries.

Usage:
    cd /home/sirobo/papergenerator/backend
    python3 test_all_fetchers.py [--fetcher NAME] [--limit N]
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.Literatur.fetchers import ALL as FETCHERS
from tools.Literatur.http_client import get_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger(__name__)

# Test queries per domain
TEST_QUERIES = {
    # CS/AI - for arxiv, dblp, ieee, semantic_scholar
    "cs": "machine learning",
    # Medical - for pubmed, pmc, europepmc, biorxiv, embase, clinicalkey
    "medical": "diabetes treatment",
    # General - for crossref, openalex, core, dimensions, lens
    "general": "climate change",
    # Books - for google_books, open_library, doab, oapen, gutendex
    "books": "artificial intelligence",
    # Regional - for sinta
    "indonesia": "pendidikan",
}

# Expected working fetchers (no API key required or have hardcoded keys)
TIER_1_FREE = [
    "arxiv", "dblp", "plos", "zenodo", "datacite", "sinta",
    "pmc", "orcid", "pubmed", "crossref", "hal",
]

# Rate-limited but should work
TIER_2_RATE_LIMITED = [
    "openalex", "semantic_scholar", "doaj", "europepmc", "ieee",
    "google_books", "biorxiv",
]

# Need API keys
TIER_3_NEEDS_KEYS = [
    "scopus", "sciencedirect", "lens", "dimensions", "core",
    "embase", "clinicalkey",
]

# Known broken (API changes)
TIER_4_BROKEN = [
    "openaire", "opencitations",
]

# Special (secondary/enrichment)
TIER_5_SPECIAL = [
    "unpaywall", "cambridge", "open_library", "doab", "oapen", "gutendex",
]


def get_query_for_fetcher(name: str) -> str:
    """Get appropriate test query for fetcher."""
    if name in ("pubmed", "pmc", "europepmc", "biorxiv", "embase", "clinicalkey"):
        return TEST_QUERIES["medical"]
    elif name in ("arxiv", "dblp", "ieee", "semantic_scholar"):
        return TEST_QUERIES["cs"]
    elif name == "sinta":
        return TEST_QUERIES["indonesia"]
    elif name in ("google_books", "open_library", "doab", "oapen", "gutendex"):
        return TEST_QUERIES["books"]
    else:
        return TEST_QUERIES["general"]


def test_fetcher(name: str, limit: int = 3, timeout: int = 30) -> dict:
    """Test a single fetcher."""
    if name not in FETCHERS:
        return {
            "name": name,
            "status": "NOT_FOUND",
            "error": "Fetcher not in registry",
        }
    
    query = get_query_for_fetcher(name)
    result = {
        "name": name,
        "query": query,
        "status": "UNKNOWN",
        "papers": [],
        "count": 0,
        "duration": 0.0,
        "error": None,
    }
    
    start = time.time()
    
    try:
        log.info(f"Testing {name} with query: {query}")
        client = get_client(rotating_ua=True)
        
        papers = []
        fetch_start = time.time()
        
        for paper in FETCHERS[name].search(
            client=client,
            query=query,
            limit=limit,
            filters={},
        ):
            papers.append({
                "title": paper.title[:80],
                "authors": paper.authors[:3],
                "year": paper.year,
                "doi": paper.doi,
                "source_id": paper.source_id[:50] if paper.source_id else None,
            })
            
            # Timeout check
            if time.time() - fetch_start > timeout:
                log.warning(f"{name}: timeout after {timeout}s")
                break
        
        result["papers"] = papers
        result["count"] = len(papers)
        result["duration"] = time.time() - start
        
        if papers:
            result["status"] = "SUCCESS"
            log.info(f"✓ {name}: {len(papers)} papers in {result['duration']:.1f}s")
        else:
            result["status"] = "NO_RESULTS"
            log.warning(f"⚠ {name}: no results in {result['duration']:.1f}s")
        
        client.close()
        
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)[:200]
        result["duration"] = time.time() - start
        log.error(f"✗ {name}: {str(e)[:100]}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Test all literature fetchers")
    parser.add_argument("--fetcher", help="Test specific fetcher only")
    parser.add_argument("--limit", type=int, default=3, help="Papers per fetcher")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per fetcher (seconds)")
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--skip-broken", action="store_true", help="Skip known broken fetchers")
    args = parser.parse_args()
    
    log.info("=" * 70)
    log.info("COMPREHENSIVE FETCHER TEST")
    log.info("=" * 70)
    log.info(f"Limit: {args.limit} papers per fetcher")
    log.info(f"Timeout: {args.timeout}s per fetcher")
    
    # Check API keys
    keys = {
        "OPENALEX_API_KEY": os.getenv("OPENALEX_API_KEY"),
        "S2_API_KEY": os.getenv("S2_API_KEY"),
        "NCBI_API_KEY": os.getenv("NCBI_API_KEY"),
        "SCOPUS_API_KEY": os.getenv("SCOPUS_API_KEY"),
        "ELSEVIER_API_KEY": os.getenv("ELSEVIER_API_KEY"),
        "LENS_API_KEY": os.getenv("LENS_API_KEY"),
        "DIMENSIONS_API_KEY": os.getenv("DIMENSIONS_API_KEY"),
        "CORE_API_KEY": os.getenv("CORE_API_KEY"),
        "GOOGLE_BOOKS_API_KEY": os.getenv("GOOGLE_BOOKS_API_KEY"),
    }
    
    keys_found = [k for k, v in keys.items() if v]
    if keys_found:
        log.info(f"✓ API keys: {', '.join(keys_found)}")
    else:
        log.info("⚠ No API keys configured (testing free tier only)")
    
    log.info("=" * 70)
    
    # Determine which fetchers to test
    if args.fetcher:
        test_list = [args.fetcher]
    else:
        test_list = list(FETCHERS.keys())
        if args.skip_broken:
            test_list = [f for f in test_list if f not in TIER_4_BROKEN]
    
    results = []
    start_total = time.time()
    
    for name in test_list:
        result = test_fetcher(name, limit=args.limit, timeout=args.timeout)
        results.append(result)
        
        # Brief pause between fetchers
        time.sleep(1.0)
    
    elapsed = time.time() - start_total
    
    # Summary
    log.info("")
    log.info("=" * 70)
    log.info("SUMMARY")
    log.info("=" * 70)
    
    success = [r for r in results if r["status"] == "SUCCESS"]
    no_results = [r for r in results if r["status"] == "NO_RESULTS"]
    errors = [r for r in results if r["status"] == "ERROR"]
    not_found = [r for r in results if r["status"] == "NOT_FOUND"]
    
    total_papers = sum(r["count"] for r in results)
    
    log.info(f"Total tested: {len(results)} fetchers")
    log.info(f"✓ Success: {len(success)} fetchers ({total_papers} papers)")
    log.info(f"⚠ No results: {len(no_results)} fetchers")
    log.info(f"✗ Errors: {len(errors)} fetchers")
    if not_found:
        log.info(f"? Not found: {len(not_found)} fetchers")
    log.info(f"Total time: {elapsed:.1f}s")
    
    if success:
        log.info("")
        log.info("SUCCESS:")
        for r in sorted(success, key=lambda x: -x["count"]):
            log.info(f"  ✓ {r['name']:20s} {r['count']:2d} papers  {r['duration']:5.1f}s")
    
    if errors:
        log.info("")
        log.info("ERRORS:")
        for r in errors:
            log.info(f"  ✗ {r['name']:20s} {r['error'][:60]}")
    
    if no_results:
        log.info("")
        log.info("NO RESULTS:")
        for r in no_results:
            log.info(f"  ⚠ {r['name']:20s}")
    
    # Save to JSON if requested
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(results, indent=2))
        log.info(f"\nResults saved to {output_path}")
    
    # Exit code
    if len(success) < 5:
        log.error(f"\n⚠ Only {len(success)} fetchers working - needs fixes!")
        return 1
    else:
        log.info(f"\n✓ {len(success)} fetchers working - system operational!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
