#!/usr/bin/env python3
"""Test all SLR fetchers — check if each can fetch papers and handle errors gracefully.

This script tests:
1. Import of all fetchers
2. Basic search for each fetcher (limit=5 papers)
3. Proxy rotation (if configured)
4. Error handling and rate limiting
5. Rolling IP/VPN support via ProxyPool

Usage:
    cd /home/sirobo/papergenerator/backend
    python3 tools/Literatur/test_all_fetchers.py

Environment Variables (optional):
    SLR_PROXY_LIST       — comma-separated proxy URLs
    SLR_PROXY_API_KEY    — ScraperAPI or similar service key
    OPENALEX_API_KEY     — OpenAlex API key (higher rate limits)
    S2_API_KEY           — Semantic Scholar API key
    NCBI_API_KEY         — PubMed API key
"""

import logging
import os
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.Literatur.fetchers import ALL as FETCHERS
from tools.Literatur.http_client import get_client, ProxyPool

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
log = logging.getLogger(__name__)

# Test query
TEST_QUERY = "machine learning"
TEST_LIMIT = 5

# Track results
results = {}


def test_fetcher(name: str, fetcher_module) -> dict:
    """Test a single fetcher."""
    start = time.time()
    result = {
        "name": name,
        "status": "unknown",
        "papers_fetched": 0,
        "duration": 0.0,
        "error": None,
    }
    
    try:
        log.info("=" * 60)
        log.info("Testing fetcher: %s", name)
        log.info("=" * 60)
        
        # Create client
        client = get_client(rotating_ua=True)
        
        # Try to fetch papers
        papers = list(fetcher_module.search(
            client=client,
            query=TEST_QUERY,
            limit=TEST_LIMIT,
            filters={},
        ))
        
        result["papers_fetched"] = len(papers)
        result["duration"] = time.time() - start
        
        if papers:
            result["status"] = "✓ SUCCESS"
            log.info("✓ %s: fetched %d papers in %.2f sec", name, len(papers), result["duration"])
            
            # Log first paper as sample
            p = papers[0]
            log.info("  Sample: %s | %s | %s", p.title[:60], p.source, p.year)
        else:
            result["status"] = "⚠ NO RESULTS"
            log.warning("⚠ %s: no papers returned (%.2f sec)", name, result["duration"])
        
        client.close()
        
    except Exception as exc:
        result["status"] = "✗ FAILED"
        result["error"] = str(exc)[:200]
        result["duration"] = time.time() - start
        log.error("✗ %s failed: %s", name, exc)
    
    return result


def main():
    log.info("=" * 60)
    log.info("SLR FETCHER SCREENING TEST")
    log.info("=" * 60)
    log.info("Query: %s", TEST_QUERY)
    log.info("Limit: %d papers per fetcher", TEST_LIMIT)
    log.info("Total fetchers: %d", len(FETCHERS))
    log.info("=" * 60)
    
    # Check proxy configuration
    pool = ProxyPool.from_env()
    if pool.enabled:
        log.info("✓ Proxy/VPN enabled:")
        if pool.proxies:
            log.info("  - Direct proxies: %d", len(pool.proxies))
        if pool.api_key:
            log.info("  - Proxy API: configured (ScraperAPI or similar)")
    else:
        log.info("⚠ Proxy/VPN NOT configured (direct connections only)")
        log.info("  Set SLR_PROXY_LIST or SLR_PROXY_API_KEY for IP rotation")
    
    log.info("=" * 60)
    
    # Test all fetchers
    start_total = time.time()
    
    for name, fetcher in FETCHERS.items():
        result = test_fetcher(name, fetcher)
        results[name] = result
        
        # Sleep between tests to respect rate limits
        time.sleep(1.0)
    
    elapsed_total = time.time() - start_total
    
    # Summary
    log.info("")
    log.info("=" * 60)
    log.info("TEST SUMMARY")
    log.info("=" * 60)
    
    success_count = sum(1 for r in results.values() if r["status"] == "✓ SUCCESS")
    no_results_count = sum(1 for r in results.values() if r["status"] == "⚠ NO RESULTS")
    failed_count = sum(1 for r in results.values() if r["status"] == "✗ FAILED")
    
    total_papers = sum(r["papers_fetched"] for r in results.values())
    
    log.info("Total fetchers: %d", len(results))
    log.info("✓ Success: %d (returned papers)", success_count)
    log.info("⚠ No results: %d (no papers, but no error)", no_results_count)
    log.info("✗ Failed: %d (errors)", failed_count)
    log.info("Total papers fetched: %d", total_papers)
    log.info("Total time: %.1f sec", elapsed_total)
    log.info("=" * 60)
    
    # Detailed results
    log.info("")
    log.info("DETAILED RESULTS:")
    log.info("-" * 60)
    
    for name, res in sorted(results.items(), key=lambda x: (x[1]["status"], x[0])):
        status_icon = res["status"]
        papers = res["papers_fetched"]
        duration = res["duration"]
        error = res["error"]
        
        log.info("%-25s %s  %2d papers  %.2f sec", name, status_icon, papers, duration)
        if error:
            log.info("  └─ Error: %s", error[:100])
    
    log.info("-" * 60)
    
    # Show failed fetchers that need attention
    failed_fetchers = [name for name, r in results.items() if r["status"] == "✗ FAILED"]
    if failed_fetchers:
        log.warning("")
        log.warning("ATTENTION: %d fetchers need debugging:", len(failed_fetchers))
        for name in failed_fetchers:
            log.warning("  - %s: %s", name, results[name]["error"][:80])
    
    log.info("")
    log.info("Test complete. Check logs above for details.")
    
    # Exit code
    if failed_count > len(FETCHERS) // 2:
        log.error("More than 50%% of fetchers failed — something is wrong")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
