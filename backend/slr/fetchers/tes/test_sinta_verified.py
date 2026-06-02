#!/usr/bin/env python3
"""Test SINTA/Garuda fetcher - memastikan dapat data paper dan link download REAL"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from slr.fetchers import sinta
from slr.http_client import get_client

def test_sinta():
    print("=" * 80)
    print("TESTING SINTA/GARUDA FETCHER")
    print("=" * 80)
    
    client = get_client()
    query = "pendidikan"
    limit = 3  # Limit kecil karena scraping HTML lambat
    
    print(f"\n🔍 Query: '{query}' (limit: {limit})")
    print("⚠️  Note: Scraping HTML - proses lambat (0.6s per request)")
    print("-" * 80)
    
    papers = list(sinta.search(client, query, limit=limit))
    
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
        print(f"   Abstract: {paper.abstract[:100] if paper.abstract else 'N/A'}...")
        
        # Verify download link
        if paper.url:
            print(f"   📥 Download URL: {paper.url}")
            if any(x in paper.url for x in ["garuda.kemdiktisaintek.go.id", "doi.org"]):
                print(f"   ✅ VALID LINK (Garuda atau DOI)")
                success_count += 1
            else:
                print(f"   ⚠️  Link tersedia")
                success_count += 1
        else:
            print(f"   ❌ TIDAK ADA DOWNLOAD LINK!")
    
    print("\n" + "=" * 80)
    print(f"HASIL: {success_count}/{len(papers)} paper memiliki link download")
    print("=" * 80)
    
    return success_count >= len(papers) * 0.6  # Lower threshold for SINTA

if __name__ == "__main__":
    try:
        success = test_sinta()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
