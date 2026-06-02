#!/usr/bin/env python3
"""Test Taylor & Francis fetcher - verifikasi bahwa fetcher di-skip dengan benar"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from slr.fetchers import taylor_francis
from slr.http_client import get_client

def test_taylor_francis():
    print("=" * 80)
    print("TESTING TAYLOR & FRANCIS FETCHER")
    print("=" * 80)
    
    client = get_client()
    query = "education"
    limit = 5
    
    print(f"\n🔍 Query: '{query}' (limit: {limit})")
    print("⚠️  Note: Taylor & Francis tidak memiliki public API")
    print("   Konten T&F dapat diakses via Crossref/OpenAlex")
    print("-" * 80)
    
    papers = list(taylor_francis.search(client, query, limit=limit))
    
    if papers:
        print("❌ UNEXPECTED: Fetcher seharusnya return empty list!")
        return False
    
    print("\n✅ BENAR: Fetcher di-skip dengan benar (return empty list)")
    print("   Taylor & Francis content accessible via crossref/openalex fetchers")
    
    print("\n" + "=" * 80)
    print("HASIL: Fetcher berfungsi sesuai expected (skip dengan benar)")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    try:
        success = test_taylor_francis()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
