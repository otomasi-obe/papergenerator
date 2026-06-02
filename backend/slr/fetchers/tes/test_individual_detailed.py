#!/usr/bin/env python3
"""Test individual fetchers dengan detail error handling"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from slr.fetchers import ALL
from slr.http_client import get_client

def test_single_fetcher(name: str, module, query: str = "machine learning", limit: int = 3):
    """Test single fetcher dengan detail"""
    print(f"\n{'='*70}")
    print(f"Testing: {name.upper()}")
    print(f"{'='*70}")
    
    try:
        client = get_client()
        print(f"Query: '{query}', Limit: {limit}")
        print("Fetching...", end=" ", flush=True)
        
        start = time.time()
        papers = list(module.search(client, query, limit=limit))
        elapsed = time.time() - start
        
        if papers:
            print(f"✅ SUCCESS")
            print(f"  Papers found: {len(papers)}")
            print(f"  Time: {elapsed:.2f}s")
            print(f"  Papers with URL: {sum(1 for p in papers if p.url)}")
            print(f"  Papers with DOI: {sum(1 for p in papers if p.doi)}")
            print(f"  Open access: {sum(1 for p in papers if p.is_open_access)}")
            
            # Show first paper
            if papers:
                p = papers[0]
                print(f"\n  Sample paper:")
                print(f"    Title: {p.title[:60]}...")
                print(f"    URL: {p.url}")
                print(f"    Year: {p.year}")
            
            return True
        else:
            print(f"⚠️  NO RESULTS")
            print(f"  Time: {elapsed:.2f}s")
            print(f"  Possible reasons:")
            print(f"    - API key required")
            print(f"    - Subscription needed")
            print(f"    - Rate limited")
            print(f"    - No public API")
            return False
            
    except Exception as e:
        print(f"❌ ERROR")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {str(e)[:100]}")
        return False

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║              TEST ALL FETCHERS - DETAILED DIAGNOSTICS                ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    results = {}
    
    for name in sorted(ALL.keys()):
        module = ALL[name]
        success = test_single_fetcher(name, module)
        results[name] = success
        
        # Delay between fetchers to avoid rate limiting
        time.sleep(2)
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    print(f"\n✅ Success: {success_count}/{total_count}")
    print(f"❌ Failed: {total_count - success_count}/{total_count}")
    
    print("\n✅ Working fetchers:")
    for name, success in sorted(results.items()):
        if success:
            print(f"  - {name}")
    
    print("\n❌ Failed fetchers:")
    for name, success in sorted(results.items()):
        if not success:
            print(f"  - {name}")
    
    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    main()
