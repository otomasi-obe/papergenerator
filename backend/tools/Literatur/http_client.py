"""HTTP client with proxy rotation, User-Agent rotation, and advanced retry logic.

Environment variables:
  SLR_PROXY_LIST    — comma-separated proxy URLs (e.g. "http://proxy1:8080,http://proxy2:8080")
  SLR_PROXY_API_KEY — API key for proxy services (ScraperAPI, BrightData, etc.)
  SLR_PROXY_API_URL — base URL for proxy API service (default: ScraperAPI format)

When SLR_PROXY_LIST is set, requests rotate through proxies randomly.
When SLR_PROXY_API_KEY is set, requests go through the proxy API service.
Both can be combined (API service takes priority).
"""

import logging
import os
import random
import time
from typing import Optional

import httpx

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0

# ── shared utilities (dipakai oleh banyak fetcher) ──────────────────────
import re as _re
import html as _html

_STRIP_HTML_TAG_RE = _re.compile(r"<[^>]+>")
_STRIP_WS_RE = _re.compile(r"\s+")
_WARNED_GLOBALS: dict[str, bool] = {}


def strip_html(s: str) -> str:
    s = _STRIP_HTML_TAG_RE.sub(" ", s or "")
    s = _html.unescape(s)
    return _STRIP_WS_RE.sub(" ", s).strip()


def normalize_doi(doi: str) -> str | None:
    if not doi:
        return None
    d = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if d.startswith(prefix):
            d = d[len(prefix) :]
            break
    return d or None


def env_required(logger, key: str, name: str) -> bool:
    """Check env var; warn once per key if missing. Returns True if set."""
    if os.getenv(key):
        return True
    warn_key = (name, key)
    if warn_key not in _WARNED_GLOBALS:
        logger.info("%s fetcher skipped: %s not set", name, key)
        _WARNED_GLOBALS[warn_key] = True
    return False

# Rotating User-Agent pool to reduce fingerprinting
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:127.0) Gecko/20100101 Firefox/127.0",
    "PaperRiset-SLR/0.1 (mailto:research@example.com)",
]

DEFAULT_HEADERS = {
    "User-Agent": "PaperRiset-SLR/0.1 (mailto:research@example.com)",
    "Accept": "application/json",
}


class ProxyPool:
    """Manages rotating proxy pool for IP rotation.

    Supports two modes:
    1. Direct proxy list (SLR_PROXY_LIST env var)
    2. Proxy API service (SLR_PROXY_API_KEY env var, e.g. ScraperAPI)

    Usage:
        pool = ProxyPool.from_env()
        if pool.enabled:
            transport = httpx.HTTPTransport(proxy=pool.next())
            client = httpx.Client(transport=transport)
    """

    def __init__(self, proxies: list[str] | None = None,
                 api_key: str | None = None, api_url: str | None = None):
        self.proxies = proxies or []
        self.api_key = api_key
        self.api_url = api_url or "http://api.scraperapi.com"
        self._idx = 0
        if self.proxies:
            random.shuffle(self.proxies)

    @classmethod
    def from_env(cls) -> "ProxyPool":
        proxy_list_str = os.getenv("SLR_PROXY_LIST", "")
        api_key = os.getenv("SLR_PROXY_API_KEY", "")
        api_url = os.getenv("SLR_PROXY_API_URL", "")
        proxies = [p.strip() for p in proxy_list_str.split(",") if p.strip()] if proxy_list_str else []
        pool = cls(proxies=proxies, api_key=api_key, api_url=api_url)
        if pool.enabled:
            log.info("ProxyPool active: %d direct proxies + %s",
                     len(proxies), "API key set" if api_key else "no API key")
        return pool

    @property
    def enabled(self) -> bool:
        return bool(self.proxies) or bool(self.api_key)

    def next(self) -> str | None:
        """Get next proxy URL. Rotates round-robin through the shuffled list."""
        if self.api_key:
            # ScraperAPI format — routes through their service
            return f"{self.api_url}?api_key={self.api_key}&url="
        if not self.proxies:
            return None
        proxy = self.proxies[self._idx % len(self.proxies)]
        self._idx += 1
        if self._idx >= len(self.proxies):
            random.shuffle(self.proxies)
            self._idx = 0
        return proxy


# Module-level singleton proxy pool
_pool: ProxyPool | None = None


def get_proxy_pool() -> ProxyPool:
    global _pool
    if _pool is None:
        _pool = ProxyPool.from_env()
    return _pool


def get_random_ua() -> str:
    """Get a random User-Agent string for request rotation."""
    return random.choice(_USER_AGENTS)


class RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self):
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.monotonic()


def get_client(proxy: str | None = None, rotating_ua: bool = False) -> httpx.Client:
    """Create an httpx client with optional proxy and UA rotation.

    Args:
        proxy: Override proxy URL. If None, uses ProxyPool from env.
        rotating_ua: If True, use a random User-Agent from the pool.
    """
    pool = get_proxy_pool()
    if proxy is None and pool.enabled:
        proxy = pool.next()

    timeout = httpx.Timeout(
        timeout=30.0,
        connect=10.0,
        read=25.0,
        write=10.0,
        pool=10.0
    )

    headers = dict(DEFAULT_HEADERS)
    if rotating_ua:
        headers["User-Agent"] = get_random_ua()

    if proxy and not proxy.startswith("http://api.scraperapi.com"):
        transport = httpx.HTTPTransport(proxy=proxy)
        return httpx.Client(timeout=timeout, headers=headers,
                            follow_redirects=True, transport=transport)
    else:
        return httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)


# Retryable HTTP status codes (transient server errors)
_RETRYABLE_STATUS = {429, 502, 503, 504}


def _should_rotate_proxy(status_code: int) -> bool:
    """Check if we should rotate proxy for this status code."""
    return status_code in {403, 429, 503}


def fetch_json(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 2,
) -> dict | None:
    """Fetch JSON with automatic proxy rotation on 403/429/503."""
    pool = get_proxy_pool()

    for attempt in range(retries + 1):
        try:
            r = client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return None
            if _should_rotate_proxy(r.status_code) and pool.enabled and attempt < retries:
                # Rotate proxy and create a fresh client
                new_proxy = pool.next()
                if new_proxy and not new_proxy.startswith("http://api.scraperapi.com"):
                    log.debug("Rotating proxy on %d: %s", r.status_code, new_proxy[:30])
                    client.close()
                    transport = httpx.HTTPTransport(proxy=new_proxy)
                    client._transport = transport
                    client._timeout = httpx.Timeout(30.0, connect=10.0, read=25.0, write=10.0, pool=10.0)
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code in _RETRYABLE_STATUS and attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code not in (200, 404):
                log.warning("fetch_json non-200 status=%s url=%s", r.status_code, url[:120])
            return None
        except httpx.TimeoutException:
            log.warning("Timeout on attempt %d/%d for %s", attempt + 1, retries + 1, url[:80])
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except httpx.HTTPError as e:
            log.warning("HTTP error on attempt %d/%d: %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except httpx.HTTPError as e:
            log.warning("HTTP error on attempt %d/%d: %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except ValueError:
            return None
    return None


def fetch_post_json(
    client: httpx.Client,
    url: str,
    json_body: dict | None = None,
    headers: dict | None = None,
    retries: int = 2,
) -> dict | None:
    for attempt in range(retries + 1):
        try:
            r = client.post(url, json=json_body, headers=headers)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return None
            if r.status_code in _RETRYABLE_STATUS and attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code not in (200, 404):
                log.warning("fetch_post non-200 status=%s url=%s", r.status_code, url[:120])
            return None
        except httpx.TimeoutException:
            log.warning("Timeout on POST attempt %d/%d for %s", attempt + 1, retries + 1, url[:80])
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except httpx.HTTPError as e:
            log.warning("HTTP error on POST attempt %d/%d: %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except ValueError:
            return None
    return None


def fetch_text(
    client: httpx.Client, url: str, params: dict | None = None, retries: int = 2
) -> str | None:
    for attempt in range(retries + 1):
        try:
            r = client.get(url, params=params)
            if r.status_code == 200:
                return r.text
            if r.status_code in _RETRYABLE_STATUS and attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code not in (200, 404):
                log.warning("fetch_text non-200 status=%s url=%s", r.status_code, url[:120])
            return None
        except httpx.TimeoutException:
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except httpx.HTTPError:
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
    return None
