"""Test sederhana untuk ASCE Playwright scraper - standalone version"""

import asyncio
import logging
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_asce_scraping():
    """Test ASCE scraping dengan Playwright"""
    
    query = "machine learning"
    base_url = "https://ascelibrary.org"
    search_url = f"{base_url}/action/doSearch"
    
    params = {
        "AllField": query,
        "pageSize": 5,
        "startPage": 0
    }
    
    param_str = "&".join([f"{k}={quote_plus(str(v))}" for k, v in params.items()])
    full_url = f"{search_url}?{param_str}"
    
    print("\n" + "="*70)
    print("ASCE LIBRARY PLAYWRIGHT SCRAPER TEST")
    print("="*70)
    print(f"URL: {full_url}")
    print("="*70 + "\n")
    
    async with async_playwright() as p:
        try:
            print("🚀 Launching browser...")
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            
            print(f"📡 Navigating to: {full_url}")
            await page.goto(full_url, wait_until="domcontentloaded", timeout=60000)
            
            print("⏳ Waiting for Cloudflare challenge...")
            await page.wait_for_timeout(5000)
            
            title = await page.title()
            print(f"📋 Page title: {title}")
            
            if "Just a moment" in title or "Cloudflare" in title:
                print("⚠️  Still on Cloudflare page, waiting longer...")
                await page.wait_for_timeout(10000)
                title = await page.title()
                print(f"📋 New title: {title}")
            
            # Try to wait for results
            try:
                await page.wait_for_selector(
                    'div.item__body, article.item, div.search-result',
                    timeout=15000
                )
                print("✅ Search results loaded")
            except Exception as e:
                print(f"⚠️  Timeout waiting for results: {e}")
            
            # Get content
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            # Save HTML for inspection
            html_path = "/home/sirobo/papergenerator/backend/slr/fetchers/tes/asce_result.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"💾 HTML saved to: {html_path}")
            
            # Try multiple selectors
            print("\n🔍 Searching for paper items...")
            selectors = [
                'div.item__body',
                'article.item',
                'div.search-result',
                'div.card-body',
                'li.search-result',
                '[class*="item"]'
            ]
            
            found_items = []
            for selector in selectors:
                items = soup.select(selector)
                print(f"   - {selector}: {len(items)} items")
                if items and not found_items:
                    found_items = items
            
            if not found_items:
                print("\n❌ No paper items found with any selector")
                print("💡 Check the saved HTML file to inspect the page structure")
                
                # Look for any links
                all_links = soup.find_all('a', href=True)
                print(f"\n📊 Found {len(all_links)} total links on page")
                
                # Look for DOI links
                doi_links = [a for a in all_links if 'doi' in a.get('href', '').lower()]
                print(f"📊 Found {len(doi_links)} DOI links")
                
                return False
            
            print(f"\n✅ Found {len(found_items)} paper items!")
            print("\n" + "="*70)
            print("SAMPLE PAPERS:")
            print("="*70)
            
            # Parse first few items
            for i, item in enumerate(found_items[:3], 1):
                print(f"\n📄 Paper {i}:")
                
                # Try to find title
                title_elem = item.select_one('h5.item__title a, h3 a, h4 a, a.title')
                if title_elem:
                    title_text = title_elem.get_text(strip=True)
                    href = title_elem.get('href', '')
                    print(f"   Title: {title_text[:80]}...")
                    print(f"   URL: {base_url + href if href.startswith('/') else href}")
                else:
                    print(f"   Title: ❌ Not found")
                
                # Try to find authors
                author_elems = item.select('ul.rlist--inline a, div.authors a')
                if author_elems:
                    authors = [a.get_text(strip=True) for a in author_elems[:3]]
                    print(f"   Authors: {', '.join(authors)}")
                else:
                    print(f"   Authors: ❌ Not found")
                
                # Try to find DOI
                doi_elem = item.select_one('a[href*="doi.org"]')
                if doi_elem:
                    doi_url = doi_elem.get('href', '')
                    doi = doi_url.split('doi.org/')[-1] if 'doi.org/' in doi_url else doi_url
                    print(f"   DOI: {doi}")
                else:
                    print(f"   DOI: ❌ Not found")
                
                print(f"   {'-'*68}")
            
            print(f"\n{'='*70}")
            print(f"✅ TEST COMPLETED SUCCESSFULLY!")
            print(f"   - Found {len(found_items)} papers")
            print(f"   - HTML saved for inspection")
            print("="*70)
            
            await browser.close()
            return True
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                await browser.close()
            except:
                pass
            
            return False


if __name__ == "__main__":
    success = asyncio.run(test_asce_scraping())
    print(f"\n{'='*70}")
    print(f"Final Result: {'✅ PASSED' if success else '❌ FAILED'}")
    print("="*70)
