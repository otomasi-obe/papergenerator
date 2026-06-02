"""Test untuk ASCE Library Playwright scraper

Test ini memverifikasi bahwa scraper ASCE dapat:
1. Bypass Cloudflare protection dengan Playwright
2. Mengambil data paper dari search results
3. Parse metadata paper dengan benar
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

import logging
import requests

# Import Paper class first
from slr.fetchers.paper import Paper

# Now import asce search function directly
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


# Import the actual functions from asce.py
exec(open(backend_path / "slr" / "fetchers" / "riset" / "asce.py").read().replace("from ..paper import Paper", ""))


def test_asce_search_basic():
    """Test basic search functionality"""
    print("\n" + "="*70)
    print("TEST 1: Basic ASCE Search")
    print("="*70)
    
    query = "machine learning"
    limit = 3
    
    print(f"Query: {query}")
    print(f"Limit: {limit}")
    print("-"*70)
    
    try:
        # Create dummy client (not used by Playwright implementation)
        client = requests.Session()
        
        # Perform search
        papers = list(search(client, query, limit=limit))
        
        print(f"\n✅ Found {len(papers)} papers")
        
        if len(papers) == 0:
            print("⚠️  No papers found - possible issues:")
            print("   - Cloudflare blocking")
            print("   - Website structure changed")
            print("   - Network issues")
            return False
        
        # Display results
        for i, paper in enumerate(papers, 1):
            print(f"\n📄 Paper {i}:")
            print(f"   Title: {paper.title[:80]}...")
            print(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
            print(f"   Publication: {paper.publication}")
            print(f"   Date: {paper.pub_date}")
            print(f"   DOI: {paper.doi}")
            print(f"   URL: {paper.url}")
            if paper.abstract:
                print(f"   Abstract: {paper.abstract[:150]}...")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_asce_search_with_filters():
    """Test search with year filters"""
    print("\n" + "="*70)
    print("TEST 2: ASCE Search with Filters")
    print("="*70)
    
    query = "civil engineering"
    limit = 2
    filters = {
        "year_start": 2020,
        "year_end": 2024
    }
    
    print(f"Query: {query}")
    print(f"Limit: {limit}")
    print(f"Filters: {filters}")
    print("-"*70)
    
    try:
        client = requests.Session()
        papers = list(search(client, query, limit=limit, filters=filters))
        
        print(f"\n✅ Found {len(papers)} papers with filters")
        
        for i, paper in enumerate(papers, 1):
            print(f"\n📄 Paper {i}:")
            print(f"   Title: {paper.title[:80]}...")
            print(f"   Date: {paper.pub_date}")
            print(f"   DOI: {paper.doi}")
        
        return len(papers) > 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_asce_paper_metadata():
    """Test that paper metadata is properly extracted"""
    print("\n" + "="*70)
    print("TEST 3: Paper Metadata Validation")
    print("="*70)
    
    query = "structural engineering"
    limit = 2
    
    print(f"Query: {query}")
    print(f"Limit: {limit}")
    print("-"*70)
    
    try:
        client = requests.Session()
        papers = list(search(client, query, limit=limit))
        
        if not papers:
            print("⚠️  No papers to validate")
            return False
        
        print(f"\n✅ Validating {len(papers)} papers")
        
        all_valid = True
        for i, paper in enumerate(papers, 1):
            print(f"\n📄 Paper {i} Validation:")
            
            # Check required fields
            checks = {
                "Title": bool(paper.title),
                "Source": paper.source == "asce",
                "URL": bool(paper.url),
            }
            
            # Check optional but expected fields
            optional_checks = {
                "Authors": bool(paper.authors),
                "DOI": bool(paper.doi),
                "Publication": bool(paper.publication),
                "Abstract": bool(paper.abstract),
            }
            
            # Print required checks
            for field, passed in checks.items():
                status = "✅" if passed else "❌"
                print(f"   {status} {field}: {passed}")
                if not passed:
                    all_valid = False
            
            # Print optional checks
            for field, passed in optional_checks.items():
                status = "✅" if passed else "⚠️ "
                print(f"   {status} {field}: {passed}")
            
            # Print actual values
            print(f"\n   Values:")
            print(f"   - Title: {paper.title[:60]}...")
            print(f"   - Authors: {len(paper.authors)} author(s)")
            print(f"   - DOI: {paper.doi or 'N/A'}")
            print(f"   - URL: {paper.url[:60]}...")
        
        return all_valid
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all ASCE scraper tests"""
    print("\n" + "="*70)
    print("ASCE LIBRARY PLAYWRIGHT SCRAPER TEST SUITE")
    print("="*70)
    
    results = {
        "Basic Search": test_asce_search_basic(),
    }
    
    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(results.values())
    
    print(f"\n{passed}/{total} tests passed")
    print("="*70)
    
    return all(results.values())


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
