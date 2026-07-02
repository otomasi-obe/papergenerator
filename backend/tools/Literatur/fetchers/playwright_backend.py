"""Playwright backend untuk bypass Cloudflare di ResearchGate.

Menggunakan rebrowser-playwright (patched Playwright) + playwright-stealth
untuk melewati Cloudflare bot detection.

Usage:
    from tools.Literatur.fetchers.playwright_backend import fetch_page, search_researchgate

    # Fetch single page
    html = fetch_page("https://www.researchgate.net/publication/123456")

    # Search ResearchGate
    results = search_researchgate("robot", limit=10)
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

log = logging.getLogger(__name__)

# ── Browser launch ─────────────────────────────────────────────────────────

def _launch_browser(headless: bool = True):
    """Launch rebrowser-playwright chromium with stealth."""
    try:
        from rebrowser_playwright.sync_api import sync_playwright
    except ImportError:
        # Fallback to regular playwright
        from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    )
    return pw, browser


def _apply_stealth(context):
    """Apply playwright-stealth to context."""
    try:
        from playwright_stealth import stealth_sync
        # stealth_sync applies to page, not context
        # We'll apply it per-page
        return True
    except ImportError:
        return False


def _human_like_delay(min_s: float = 0.5, max_s: float = 2.0):
    """Random delay to simulate human behavior."""
    time.sleep(random.uniform(min_s, max_s))


def _human_like_interaction(page):
    """Simulate human-like mouse movements and scrolling."""
    try:
        # Random mouse movements
        for _ in range(random.randint(2, 5)):
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            page.mouse.move(x, y, steps=random.randint(5, 15))
            time.sleep(random.uniform(0.1, 0.4))

        # Scroll down
        page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
        time.sleep(random.uniform(0.5, 1.5))
    except Exception:
        pass  # Non-critical


# ── Public API ─────────────────────────────────────────────────────────────

def fetch_page(url: str, wait_selector: str | None = None, timeout: int = 30) -> Optional[str]:
    """Fetch page HTML using Playwright with Cloudflare bypass.

    Args:
        url: URL to fetch.
        wait_selector: CSS selector to wait for (ensures page loaded).
        timeout: Max wait time in seconds.

    Returns:
        HTML content string, or None if failed.
    """
    pw, browser = None, None
    try:
        pw, browser = _launch_browser(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()

        # Apply stealth
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except ImportError:
            pass

        # Navigate
        response = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

        # Wait for Cloudflare challenge to resolve (if any)
        if "Just a moment" in page.title() or (response and response.status == 403):
            log.warning("playwright: Cloudflare challenge detected, waiting...")
            # Wait for challenge to resolve (up to 15 seconds)
            try:
                page.wait_for_url(lambda url: "Just a moment" not in url, timeout=15000)
            except Exception:
                pass

        # Wait for specific selector if provided
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=timeout * 1000)
            except Exception:
                log.warning("playwright: selector '%s' not found", wait_selector)

        # Human-like interaction
        _human_like_interaction(page)

        html = page.content()
        browser.close()
        pw.stop()
        return html

    except Exception as e:
        log.error("playwright fetch_page error: %s", e)
        try:
            if browser:
                browser.close()
            if pw:
                pw.stop()
        except Exception:
            pass
        return None


def fetch_pages(urls: list[str], delay_range: tuple[float, float] = (2.0, 5.0)) -> dict[str, str]:
    """Fetch multiple pages in a single browser session.

    Args:
        urls: List of URLs to fetch.
        delay_range: Random delay range between requests (min, max) seconds.

    Returns:
        Dict mapping URL -> HTML content (only successful fetches).
    """
    results = {}
    pw, browser = None, None
    try:
        pw, browser = _launch_browser(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        for url in urls:
            try:
                page = context.new_page()

                # Apply stealth
                try:
                    from playwright_stealth import stealth_sync
                    stealth_sync(page)
                except ImportError:
                    pass

                response = page.goto(url, timeout=30000, wait_until="domcontentloaded")

                # Handle Cloudflare
                if "Just a moment" in page.title() or (response and response.status == 403):
                    try:
                        page.wait_for_url(lambda u: "Just a moment" not in u, timeout=15000)
                    except Exception:
                        pass

                _human_like_interaction(page)
                html = page.content()
                page.close()

                if html and len(html) > 1000:
                    results[url] = html

                time.sleep(random.uniform(*delay_range))

            except Exception as e:
                log.warning("playwright: failed to fetch %s: %s", url[:80], e)
                try:
                    page.close()
                except Exception:
                    pass

        browser.close()
        pw.stop()

    except Exception as e:
        log.error("playwright fetch_pages error: %s", e)
        try:
            if browser:
                browser.close()
            if pw:
                pw.stop()
        except Exception:
            pass

    return results
