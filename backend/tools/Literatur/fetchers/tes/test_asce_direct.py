"""Simple test untuk ASCE Library scraper - tanpa circular import"""

import requests
from bs4 import BeautifulSoup
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_asce_direct():
    """Test ASCE Library scraping langsung tanpa import module"""
    
    base_url = "https://ascelibrary.org"
    search_url = f"{base_url}/action/doSearch"
    
    query = "machine learning"
    params = {
        "AllField": query,
        "pageSize": 5,
        "startPage": 0
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": base_url
    }
    
    print(f"\n{'='*70}")
    print(f"Testing ASCE Library Direct Scraping")
    print(f"{'='*70}")
    print(f"URL: {search_url}")
    print(f"Query: {query}")
    print(f"{'='*70}\n")
    
    try:
        print("📡 Sending request to ASCE Library...")
        response = requests.get(search_url, params=params, headers=headers, timeout=30)
        print(f"✅ Response status: {response.status_code}")
        print(f"📄 Response size: {len(response.text)} bytes")
        
        if response.status_code != 200:
            print(f"\n❌ Error: Got status code {response.status_code}")
            print(f"Response text preview:\n{response.text[:500]}")
            return
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Debug: Print page title
        page_title = soup.find('title')
        print(f"\n📋 Page title: {page_title.get_text() if page_title else 'No title found'}")
        
        # Look for different possible selectors
        print("\n🔍 Searching for paper items with different selectors...")
        
        selectors = [
            ('div.item__body', 'item__body class'),
            ('div.card-body', 'card-body class'),
            ('article', 'article tag'),
            ('div.search-result', 'search-result class'),
            ('div.result-item', 'result-item class'),
            ('li.search-result', 'li search-result'),
        ]
        
        found_items = []
        for selector, desc in selectors:
            items = soup.select(selector)
            print(f"   - {desc}: {len(items)} items")
            if items and not found_items:
                found_items = items
        
        if not found_items:
            print("\n⚠️  No paper items found with any selector!")
            print("\n💡 Saving HTML to file for inspection...")
            with open('/home/sirobo/papergenerator/asce_response.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
            print("✅ Saved to: /home/sirobo/papergenerator/asce_response.html")
            print("\n📝 Please check Chrome browser and inspect the page structure:")
            print("   1. Open Developer Tools (F12)")
            print("   2. Go to Elements tab")
            print("   3. Search for paper/article elements")
            print("   4. Note the class names and structure")
            return
        
        print(f"\n✅ Found {len(found_items)} paper items!")
        print("\n" + "="*70)
        print("Sample Paper Data:")
        print("="*70)
        
        # Parse first few items
        for i, item in enumerate(found_items[:3], 1):
            print(f"\n📄 Paper {i}:")
            
            # Try to find title
            title_selectors = ['h5.item__title a', 'h3 a', 'h4 a', 'a.title']
            title = None
            for sel in title_selectors:
                title_elem = item.select_one(sel)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    break
            
            print(f"   Title: {title if title else '❌ Not found'}")
            
            # Try to find authors
            author_selectors = ['ul.rlist--inline a', 'div.authors a', 'span.author']
            authors = []
            for sel in author_selectors:
                author_elems = item.select(sel)
                if author_elems:
                    authors = [a.get_text(strip=True) for a in author_elems]
                    break
            
            print(f"   Authors: {', '.join(authors[:3]) if authors else '❌ Not found'}")
            
            # Print raw HTML snippet for debugging
            print(f"\n   Raw HTML snippet:")
            print(f"   {str(item)[:300]}...")
            print(f"   {'-'*68}")
        
        print(f"\n{'='*70}")
        print("✅ Test completed! Check the output above for structure details.")
        print("="*70)
        
    except requests.RequestException as e:
        print(f"\n❌ Network error: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_asce_direct()
