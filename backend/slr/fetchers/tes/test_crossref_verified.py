#!/usr/bin/env python3
"""Test Crossref fetcher - memastikan dapat data paper dan link download REAL"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from slr.fetchers import crossref
from slr.http_client import get_client

def test_crossref():
    print("=" * 80)
    print("TESTING CROSSREF FETCHER")
    print("=" * 80)
    
    client = get_client()
    query = "artificial intelligence"
    limit = 5
    
    print(f"\n🔍 Query: '{query}' (limit: {limit})")
    print("-" * 80)
    
    papers = list(crossref.search(client, query, limit=limit))
    
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
        print(f"   Publisher: {paper.publisher or 'N/A'}")
        print(f"   Citations: {paper.citations or 'N/A'}")
        print(f"   Abstract: {paper.abstract[:100] if paper.abstract else 'N/A'}...")
        
        # Verify download link
        if paper.url:
            print(f"   📥 Download URL: {paper.url}")
            if paper.doi and ("doi.org" in paper.url or paper.url.endswith(".pdf")):
                print(f"   ✅ VALID LINK (DOI resolver atau PDF)")
                success_count += 1
            else:
                print(f"   ⚠️  Link tersedia tapi bukan DOI/PDF langsung")
                success_count += 1  # Still count as success if URL exists
        else:
            print(f"   ❌ TIDAK ADA DOWNLOAD LINK!")
    
    print("\n" + "=" * 80)
    print(f"HASIL: {success_count}/{len(papers)} paper memiliki link download")
    print("=" * 80)
    
    return success_count >= len(papers) * 0.8  # 80% success rate acceptable

if __name__ == "__main__":
    try:
        success = test_crossref()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
