#!/usr/bin/env python3
"""Test DBLP fetcher - memastikan dapat data paper dan link download REAL"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from slr.fetchers import dblp
from slr.http_client import get_client

def test_dblp():
    print("=" * 80)
    print("TESTING DBLP FETCHER")
    print("=" * 80)
    
    client = get_client()
    query = "deep learning"
    limit = 5
    
    print(f"\n🔍 Query: '{query}' (limit: {limit})")
    print("-" * 80)
    
    papers = list(dblp.search(client, query, limit=limit))
    
    if not papers:
        print("❌ GAGAL: Tidak ada paper yang ditemukan!")
        return False
    
    print(f"\n✅ Berhasil mendapatkan {len(papers)} paper\n")
    
    success_count = 0
    for i, paper in enumerate(papers, 1):
        print(f"\n📄 Paper {i}:")
        print(f"   Title: {paper.title[:80]}...")
        print(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
        print(f"   Year: {paper.year}")
        print(f"   DOI: {paper.doi or 'N/A'}")
        print(f"   Venue: {paper.venue or 'N/A'}")
        print(f"   Venue Type: {paper.venue_type or 'N/A'}")
        print(f"   Type: {paper.type or 'N/A'}")
        
        # Verify download link
        if paper.url:
            print(f"   📥 Download URL: {paper.url}")
            if any(x in paper.url for x in ["doi.org", "arxiv.org/pdf", ".pdf", "dblp.org"]):
                print(f"   ✅ VALID LINK")
                success_count += 1
            else:
                print(f"   ⚠️  Link tersedia: {paper.url[:60]}...")
                success_count += 1
        else:
            print(f"   ❌ TIDAK ADA DOWNLOAD LINK!")
    
    print("\n" + "=" * 80)
    print(f"HASIL: {success_count}/{len(papers)} paper memiliki link download")
    print("=" * 80)
    
    return success_count >= len(papers) * 0.8

if __name__ == "__main__":
    try:
        success = test_dblp()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
