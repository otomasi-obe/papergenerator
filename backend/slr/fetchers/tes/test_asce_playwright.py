"""Test ASCE Library dengan Playwright untuk bypass Cloudflare"""

import asyncio
from playwright.async_api import async_playwright
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def test_asce_playwright():
    """Test ASCE Library menggunakan Playwright"""
    
    base_url = "https://ascelibrary.org"
    query = "machine learning"
    search_url = f"{base_url}/action/doSearch?AllField={query}&pageSize=5"
    
    print(f"\n{'='*70}")
    print(f"Testing ASCE Library dengan Playwright")
    print(f"{'='*70}")
    print(f"URL: {search_url}")
    print(f"{'='*70}\n")
    
    async with async_playwright() as p:
        # Launch browser dengan headless mode
        print("🚀 Launching browser...")
        browser = await p.chromium.launch(headless=True)  # headless=True untuk server tanpa display
        
        # Create context dengan user agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        try:
            print(f"📡 Navigating to: {search_url}")
            await page.goto(search_url, wait_until="networkidle", timeout=60000)
            
            # Wait for Cloudflare challenge to complete
            print("⏳ Waiting for Cloudflare challenge...")
            await page.wait_for_timeout(5000)  # Wait 5 seconds
            
            # Get page title
            title = await page.title()
            print(f"📋 Page title: {title}")
            
            # Check if still on Cloudflare page
            if "Just a moment" in title or "Cloudflare" in title:
                print("⚠️  Still on Cloudflare challenge page, waiting longer...")
                await page.wait_for_timeout(10000)  # Wait another 10 seconds
                title = await page.title()
                print(f"📋 New page title: {title}")
            
            # Get current URL
            current_url = page.url
            print(f"🔗 Current URL: {current_url}")
            
            # Save screenshot
            screenshot_path = "/home/sirobo/papergenerator/asce_screenshot.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"📸 Screenshot saved to: {screenshot_path}")
            
            # Get page content
            content = await page.content()
            
            # Save HTML
            html_path = "/home/sirobo/papergenerator/asce_page.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"💾 HTML saved to: {html_path}")
            
            # Try to find search results
            print("\n🔍 Looking for search results...")
            
            # Try different selectors
            selectors = [
                'div.item__body',
                'div.card-body',
                'article',
                'div.search-result',
                'div.result-item',
                '[class*="result"]',
                '[class*="item"]',
            ]
            
            for selector in selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    print(f"   ✅ Found {len(elements)} elements with selector: {selector}")
                    
                    # Get details from first few elements
                    for i, elem in enumerate(elements[:3], 1):
                        print(f"\n   📄 Element {i}:")
                        
                        # Get text content
                        text = await elem.text_content()
                        if text:
                            preview = text.strip()[:200]
                            print(f"      Text preview: {preview}...")
                        
                        # Get HTML
                        html = await elem.inner_html()
                        print(f"      HTML preview: {html[:200]}...")
                else:
                    print(f"   ❌ No elements found with selector: {selector}")
            
            # Look for any links that might be papers
            print("\n🔗 Looking for paper links...")
            links = await page.query_selector_all('a[href*="/doi/"]')
            print(f"   Found {len(links)} DOI links")
            
            for i, link in enumerate(links[:5], 1):
                href = await link.get_attribute('href')
                text = await link.text_content()
                print(f"   {i}. {text.strip()[:50]} -> {href}")
            
            print(f"\n{'='*70}")
            print("✅ Test completed!")
            print(f"📸 Check screenshot: {screenshot_path}")
            print(f"💾 Check HTML: {html_path}")
            print("="*70)
            
            # Keep browser open for manual inspection
            print("\n⏸️  Browser will stay open for 30 seconds for manual inspection...")
            await page.wait_for_timeout(30000)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            
            # Save error screenshot
            try:
                await page.screenshot(path="/home/sirobo/papergenerator/asce_error.png")
                print("📸 Error screenshot saved")
            except:
                pass
        
        finally:
            await browser.close()
            print("\n🔚 Browser closed")

if __name__ == "__main__":
    asyncio.run(test_asce_playwright())
