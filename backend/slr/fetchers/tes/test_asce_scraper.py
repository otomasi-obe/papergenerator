"""Test script untuk ASCE Library scraper"""

import sys
import logging
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

import requests
from slr.fetchers.riset.asce import search

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_asce_search():
    """Test ASCE Library search functionality"""
    
    # Create HTTP client
    session = requests.Session()
    
    # Test query
    query = "machine learning civil engineering"
    limit = 5
    
    print(f"\n{'='*60}")
    print(f"Testing ASCE Library Scraper")
    print(f"{'='*60}")
    print(f"Query: {query}")
    print(f"Limit: {limit}")
    print(f"{'='*60}\n")
    
    try:
        # Perform search
        papers = list(search(session, query, limit=limit))
        
        print(f"\nFound {len(papers)} papers:\n")
        
        for i, paper in enumerate(papers, 1):
            print(f"\n{i}. {paper.title}")
            print(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
            print(f"   Publication: {paper.publication}")
            print(f"   Date: {paper.pub_date}")
            print(f"   DOI: {paper.doi}")
            print(f"   URL: {paper.url}")
            if paper.abstract:
                abstract_preview = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
                print(f"   Abstract: {abstract_preview}")
            print(f"   {'-'*58}")
        
        if len(papers) == 0:
            print("\n⚠️  No papers found. Possible reasons:")
            print("   - Website structure has changed")
            print("   - Cloudflare blocking the request")
            print("   - Network issues")
            print("\n💡 Check Chrome browser to see the actual page structure")
        else:
            print(f"\n✅ Successfully scraped {len(papers)} papers from ASCE Library!")
            
    except Exception as e:
        print(f"\n❌ Error during scraping: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_asce_search()
