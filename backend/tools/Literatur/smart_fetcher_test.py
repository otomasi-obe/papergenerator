#!/usr/bin/env python3
"""Smart SLR fetcher test — only test working fetchers with proxy rotation.

This script:
1. Tests only reliable fetchers (skip broken ones)
2. Sets up proxy rotation if available
3. Has shorter timeouts to avoid hanging
4. Provides summary of working vs broken fetchers

Usage:
    cd /home/sirobo/papergenerator/backend
    python3 tools/Literatur/smart_fetcher_test.py
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

# Test configuration
TEST_QUERY = "machine learning"
TEST_LIMIT = 3  # Smaller limit for faster testing
TIMEOUT_PER_FETCHER = 15  # 15 sec timeout per fetcher

# Categorize fetchers by reliability
TIER_1_STABLE = [
    "arxiv",           # ✓ Very reliable, free
    "dblp",            # ✓ Reliable CS source
    "plos",            # ✓ Works well
    "zenodo",          # ✓ Reliable
    "datacite",        # ✓ Works
    "sinta",           # ✓ Indonesian source works
    "orcid",           # ✓ Author database works
    "pmc",             # ✓ PubMed Central works
]

TIER_2_RATE_LIMITED = [
    "openalex",        # ⚠ 429 rate limits without key
    "crossref",        # ✓ Works but slow due to abstract enrichment
    "semantic_scholar", # ⚠ 429 rate limits without key
    "pubmed",          # ✓ Works but needs proper rate limiting
    "europepmc",       # ⚠ Often returns no results
    "google_books",    # ⚠ 429 rate limits
]

TIER_3_NEEDS_KEYS = [
    "scopus",          # Requires SCOPUS_API_KEY
    "sciencedirect",   # Requires ELSEVIER_API_KEY
    "ieee",            # Sometimes works, sometimes doesn't
    "dimensions",      # Requires API key
    "lens",            # Requires API key
    "core",            # Requires API key
    "embase",          # Requires ELSEVIER_API_KEY
    "clinicalkey",     # Requires ELSEVIER_API_KEY
]

TIER_4_PROBLEMATIC = [
    "doaj",            # ✗ Timeouts
    "hal",             # ⚠ Often no results
    "openaire",        # ✗ API endpoint changed
    "opencitations",   # ✗ Endpoint changed
    "unpaywall",       # ⚠ 422 errors on many DOIs
    "biorxiv",         # ⚠ Depends on crossref (slow)
    "cambridge",       # ⚠ Scraping (fragile)
    "crossref_publishers", # ⚠ Slow batch operation
]

TIER_5_BOOK_FETCHERS = [
    "google_books",
    "open_library",
    "doab",
    "oapen", 
    "gutendex",
]

# Skip these entirely (known broken)
SKIP_FETCHERS = set(TIER_4_PROBLEMATIC + ["openaire", "opencitations"])

def test_fetcher(name: str, fetcher_module, timeout: int = 15) -> dict:
    """Test a single fetcher with timeout."""
    start = time.time()
    result = {
        "name": name,
        "status": "unknown",
        "papers_fetched": 0,
        "duration": 0.0,
        "error": None,
        "tier": get_tier(name),
    }
    
    try:
        log.info("Testing %s (tier: %s)...", name, result["tier"])
        
        # Create client with proxy rotation
        client = get_client(rotating_ua=True)
        
        # Test with timeout
        papers = []
        fetch_start = time.time()
        
        for paper in fetcher_module.search(
            client=client,
            query=TEST_QUERY,
            limit=TEST_LIMIT,
            filters={},
        ):
            papers.append(paper)
            # Break early if timeout
            if time.time() - fetch_start > timeout:
                break
        
        result["papers_fetched"] = len(papers)
        result["duration"] = time.time() - start
        
        if papers:
            result["status"] = "✓ SUCCESS"
            log.info("✓ %s: %d papers in %.1f sec", name, len(papers), result["duration"])
            
            # Log first paper sample
            p = papers[0]
            log.info("  └─ Sample: %s | %s", p.title[:50], p.year)
        else:
            result["status"] = "⚠ NO RESULTS"
            log.warning("⚠ %s: no papers (%.1f sec)", name, result["duration"])
        
        client.close()
        
    except Exception as exc:
        result["status"] = "✗ ERROR"
        result["error"] = str(exc)[:100]
        result["duration"] = time.time() - start
        log.error("✗ %s failed: %s", name, str(exc)[:100])
    
    return result


def get_tier(name: str) -> str:
    """Get tier for fetcher name."""
    if name in TIER_1_STABLE:
        return "1-STABLE"
    elif name in TIER_2_RATE_LIMITED:
        return "2-RATE-LIMITED"
    elif name in TIER_3_NEEDS_KEYS:
        return "3-NEEDS-KEYS"
    elif name in TIER_4_PROBLEMATIC:
        return "4-PROBLEMATIC"
    elif name in TIER_5_BOOK_FETCHERS:
        return "5-BOOKS"
    else:
        return "UNKNOWN"


def main():
    log.info("=" * 60)
    log.info("SMART SLR FETCHER TEST")
    log.info("=" * 60)
    log.info("Query: %s", TEST_QUERY)
    log.info("Limit: %d papers per fetcher", TEST_LIMIT)
    log.info("Timeout: %d sec per fetcher", TIMEOUT_PER_FETCHER)
    
    # Check proxy status
    pool = ProxyPool.from_env()
    if pool.enabled:
        log.info("✓ Proxy/VPN rotation: ENABLED")
        if pool.proxies:
            log.info("  └─ Direct proxies: %d", len(pool.proxies))
        if pool.api_key:
            log.info("  └─ Proxy API: configured")
    else:
        log.info("⚠ Proxy/VPN rotation: DISABLED")
        log.info("  └─ Set SLR_PROXY_LIST or SLR_PROXY_API_KEY for IP rotation")
    
    # Check API keys
    keys_present = []
    key_vars = ["OPENALEX_API_KEY", "S2_API_KEY", "NCBI_API_KEY", "SCOPUS_API_KEY", "ELSEVIER_API_KEY"]
    for var in key_vars:
        if os.getenv(var):
            keys_present.append(var)
    
    if keys_present:
        log.info("✓ API keys found: %s", ", ".join(keys_present))
    else:
        log.info("⚠ No API keys configured (using free tiers only)")
    
    log.info("=" * 60)
    
    # Test priority fetchers first
    test_order = (
        TIER_1_STABLE +
        [f for f in TIER_2_RATE_LIMITED if f not in SKIP_FETCHERS] +
        [f for f in TIER_3_NEEDS_KEYS if f in FETCHERS and os.getenv(f.upper() + "_API_KEY")]
    )
    
    results = {}
    start_total = time.time()
    
    for name in test_order:
        if name not in FETCHERS:
            log.warning("Fetcher %s not found in registry", name)
            continue
            
        if name in SKIP_FETCHERS:
            log.info("Skipping %s (known problematic)", name)
            continue
        
        result = test_fetcher(name, FETCHERS[name], TIMEOUT_PER_FETCHER)
        results[name] = result
        
        # Brief pause between tests
        time.sleep(1.0)
    
    elapsed_total = time.time() - start_total
    
    # Summary
    log.info("")
    log.info("=" * 60)
    log.info("TEST SUMMARY")
    log.info("=" * 60)
    
    success = [r for r in results.values() if r["status"] == "✓ SUCCESS"]
    no_results = [r for r in results.values() if r["status"] == "⚠ NO RESULTS"]
    errors = [r for r in results.values() if r["status"] == "✗ ERROR"]
    
    total_papers = sum(r["papers_fetched"] for r in results.values())
    
    log.info("Total tested: %d fetchers", len(results))
    log.info("✓ Working: %d fetchers (%d papers)", len(success), total_papers)
    log.info("⚠ No results: %d fetchers", len(no_results))
    log.info("✗ Errors: %d fetchers", len(errors))
    log.info("Skipped: %d fetchers (known issues)", len(SKIP_FETCHERS))
    log.info("Total time: %.1f sec", elapsed_total)
    
    # Working fetchers
    if success:
        log.info("")
        log.info("WORKING FETCHERS:")
        for r in sorted(success, key=lambda x: -x["papers_fetched"]):
            log.info("  ✓ %-20s %2d papers  %.1f sec  [%s]", 
                     r["name"], r["papers_fetched"], r["duration"], r["tier"])
    
    # Problematic fetchers
    if errors:
        log.info("")
        log.info("ERROR FETCHERS (need debugging):")
        for r in errors:
            log.info("  ✗ %-20s %s", r["name"], r["error"][:60])
    
    # Fetchers that returned no results
    if no_results:
        log.info("")
        log.info("NO RESULTS (may need API keys or different queries):")
        for r in no_results:
            log.info("  ⚠ %-20s [%s]", r["name"], r["tier"])
    
    log.info("")
    log.info("RECOMMENDATION:")
    if len(success) >= 5:
        log.info("✓ %d fetchers working - SLR system is functional!", len(success))
        if not pool.enabled:
            log.info("  Consider adding proxy rotation to avoid rate limits")
    else:
        log.info("⚠ Only %d fetchers working - consider API keys or proxy setup", len(success))
    
    log.info("=" * 60)
    
    # Return success if we have at least 3 working fetchers
    return 0 if len(success) >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())