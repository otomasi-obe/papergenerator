#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/sirobo/papergenerator/backend/slr')

from fetchers import dblp
import httpx

print("Testing DBLP fetcher directly...")
print("="*80)

client = httpx.Client(timeout=30.0)

try:
    papers = list(dblp.search(client, "machine learning", limit=3))
    print(f"\nPapers found: {len(papers)}")
    
    for i, paper in enumerate(papers, 1):
        print(f"\n{i}. {paper.title}")
        print(f"   Authors: {', '.join(paper.authors[:3])}")
        print(f"   Year: {paper.year}")
        print(f"   DOI: {paper.doi}")
        print(f"   URL: {paper.url}")
        print(f"   Source ID: {paper.source_id}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    client.close()
