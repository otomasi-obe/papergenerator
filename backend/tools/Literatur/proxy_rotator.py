"""
Proxy Rotator — Multi-source proxy pool with health checking and IP rotation.
Uses free HTTP/HTTPS proxies from reliable aggregators.
Rotates IP per request to bypass academic API rate limits.

Usage:
    from proxy_rotator import get_proxy_client
    
    client, proxy_url = get_proxy_client()
    r = client.get("https://api.openalex.org/works?search=test")
    report_result(proxy_url, r.status_code == 200)
"""
import httpx
import json
import random
import re
import threading
import time
from datetime import datetime
from pathlib import Path

CACHE_FILE = Path("/tmp/proxy_pool.json")

# Reliable free proxy APIs with structured responses
PROXY_API_SOURCES = [
    # Free Proxy List (free-proxy-list.net style)
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=all&anonymity=anonymous,elite",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=yes&anonymity=elite",
]

# GitHub raw proxy lists (updated frequently)
GITHUB_PROXY_LISTS = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_raw.txt",
]

# Test endpoint for health check
TEST_URL = "https://httpbin.org/ip"
# Fallback test endpoint
TEST_URL_FALLBACK = "https://api.ipify.org"


class ProxyPool:
    """Thread-safe proxy pool with health checking, rotation, and fail tracking."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._proxies: list[dict] = []  # [{url, last_ok, last_fail, failures, latency}]
        self._current_idx = 0
        self._refreshing = False
        self._last_refresh = 0
        self._loaded = False
    
    def _load_cache(self) -> bool:
        """Load cached proxies from disk."""
        if CACHE_FILE.exists():
            try:
                data = json.loads(CACHE_FILE.read_text())
                self._proxies = data.get("proxies", [])
                self._last_refresh = data.get("last_refresh", 0)
                if time.time() - self._last_refresh < 600:
                    self._loaded = True
                    return True
            except Exception as _e:
                print(f"[proxy_rotator] _load_cache failed: {_e}")
        return False
    
    def _save_cache(self):
        """Save proxies to disk cache."""
        try:
            CACHE_FILE.write_text(json.dumps({
                "proxies": self._proxies[:500],
                "last_refresh": time.time()
            }))
        except Exception as _e:
            print(f"[proxy_rotator] _save_cache failed: {_e}")
    
    def refresh(self, force=False) -> int:
        """Fetch fresh proxies from multiple sources. Returns count of new proxies."""
        now = time.time()
        if not force and now - self._last_refresh < 300:
            return 0
        
        # TOCTOU fix: check+set _refreshing inside lock
        with self._lock:
            if self._refreshing:
                return 0
            self._refreshing = True
        
        raw_proxies = []
        
        # Source 1: ProxyScrape API (structured)
        for url in PROXY_API_SOURCES:
            try:
                with httpx.Client(timeout=15.0) as c:
                    r = c.get(url)
                    if r.status_code == 200:
                        lines = r.text.strip().split("\n")
                        for line in lines:
                            line = line.strip()
                            if line and ":" in line and len(line) < 30:
                                raw_proxies.append(f"http://{line}")
            except Exception as _e:
                print(f"[proxy_rotator] ProxyScrape fetch failed for {url}: {_e}")
        
        # Source 2: GitHub proxy lists
        for url in GITHUB_PROXY_LISTS:
            try:
                with httpx.Client(timeout=15.0, follow_redirects=True) as c:
                    r = c.get(url)
                    if r.status_code == 200:
                        lines = r.text.strip().split("\n")
                        for line in lines:
                            line = line.strip()
                            if line and ":" in line and len(line) < 30:
                                raw_proxies.append(f"http://{line}")
            except Exception as _e:
                print(f"[proxy_rotator] GitHub proxy list fetch failed for {url}: {_e}")
        
        # Deduplicate + validate format
        seen = set()
        unique = []
        ip_pattern = re.compile(r'^http[s]?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}$')
        for p in raw_proxies:
            if p not in seen and ip_pattern.match(p):
                seen.add(p)
                unique.append(p)
        
        with self._lock:
            self._proxies = [{"url": u, "last_ok": 0, "last_fail": 0, 
                            "failures": 0, "latency": 0} for u in unique]
            self._last_refresh = now
            self._loaded = True
            self._current_idx = 0
        
        self._save_cache()
        self._refreshing = False
        return len(unique)
    
    def health_check(self, max_proxies=30, timeout=8.0) -> int:
        """Test proxies against httpbin. Keep only working ones. Returns count of working."""
        if not self._proxies:
            return 0
        
        with self._lock:
            # Test more candidates for better pool
            candidates = [p["url"] for p in self._proxies[:max_proxies * 3]]
        
        working = []
        
        def test_proxy(proxy_url):
            try:
                start = time.time()
                with httpx.Client(proxy=proxy_url, timeout=timeout) as c:
                    r = c.get(TEST_URL)
                    latency = time.time() - start
                    if r.status_code == 200:
                        return (proxy_url, latency)
            except:
                try:
                    start = time.time()
                    with httpx.Client(proxy=proxy_url, timeout=timeout) as c:
                        r = c.get(TEST_URL_FALLBACK)
                        latency = time.time() - start
                        if r.status_code == 200:
                            return (proxy_url, latency)
                except Exception as _e:
                    pass  # Both primary and fallback test endpoints failed; proxy is dead
            return None
        
        # Parallel health check
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(10, len(candidates))) as pool:
            futures = {pool.submit(test_proxy, url): url for url in candidates[:max_proxies]}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    working.append(result)
        
        # Sort by latency (fastest first)
        working.sort(key=lambda x: x[1])
        
        with self._lock:
            self._proxies = [{"url": url, "last_ok": time.time(), "last_fail": 0,
                            "failures": 0, "latency": lat} for url, lat in working]
            self._current_idx = 0
        
        self._save_cache()
        return len(working)
    
    def get_proxy(self) -> str | None:
        """Get next proxy (round-robin, skip failed ones)."""
        with self._lock:
            if not self._proxies:
                return None
            good = [p for p in self._proxies if p["failures"] < 3]
            if not good:
                # Reset all and try again
                for p in self._proxies:
                    p["failures"] = 0
                good = self._proxies
            idx = self._current_idx % len(good)
            self._current_idx = idx + 1
            return good[idx]["url"]
    
    def mark_success(self, proxy_url: str):
        with self._lock:
            for p in self._proxies:
                if p["url"] == proxy_url:
                    p["last_ok"] = time.time()
                    p["failures"] = 0
                    break
    
    def mark_failure(self, proxy_url: str):
        with self._lock:
            for p in self._proxies:
                if p["url"] == proxy_url:
                    p["last_fail"] = time.time()
                    p["failures"] += 1
                    break
    
    @property
    def pool_size(self):
        with self._lock:
            return len(self._proxies)
    
    @property
    def active_count(self):
        with self._lock:
            return sum(1 for p in self._proxies if p["failures"] < 3)


# Global singleton
_pool = ProxyPool()
_pool_lock = threading.Lock()
_initialized = False
_direct_fallback_count = 0


def init_pool(health_check=True, max_health=30) -> int:
    """Initialize proxy pool. Returns number of working proxies."""
    global _initialized
    with _pool_lock:
        if _initialized and _pool.active_count > 0:
            return _pool.active_count
        
        if not _pool._load_cache() or _pool.pool_size < 5:
            _pool.refresh(force=True)
        
        if health_check and _pool.pool_size > 0:
            working = _pool.health_check(max_proxies=max_health)
        else:
            working = _pool.pool_size
        
        _initialized = True
        return working


def get_proxy_client(timeout=15.0) -> tuple[httpx.Client, str | None]:
    """Get httpx client with rotating proxy. Falls back to direct if no proxy.
    Returns (client, proxy_url). proxy_url is None if direct.
    """
    global _direct_fallback_count
    
    proxy_url = _pool.get_proxy()
    if proxy_url:
        try:
            client = httpx.Client(proxy=proxy_url, timeout=timeout)
            return client, proxy_url
        except:
            _pool.mark_failure(proxy_url)
    
    # Fallback: direct connection
    _direct_fallback_count += 1
    return httpx.Client(timeout=timeout), None


def report_result(proxy_url: str | None, success: bool):
    """Report success/failure for a proxy."""
    if proxy_url:
        if success:
            _pool.mark_success(proxy_url)
        else:
            _pool.mark_failure(proxy_url)


def refresh_pool() -> int:
    """Force refresh proxy pool (call periodically)."""
    return _pool.refresh(force=True)


def pool_stats() -> dict:
    """Get pool statistics."""
    return {
        "total": _pool.pool_size,
        "active": _pool.active_count,
        "direct_fallbacks": _direct_fallback_count,
        "last_refresh": datetime.fromtimestamp(_pool._last_refresh).strftime("%H:%M:%S") 
                        if _pool._last_refresh else "never"
    }


if __name__ == "__main__":
    import sys
    
    print("🔍 Initializing proxy pool...")
    t0 = time.time()
    count = init_pool(health_check=True, max_health=20)
    elapsed = time.time() - t0
    ps = pool_stats()
    print(f"✅ {count} working proxies (health check in {elapsed:.0f}s)")
    print(f"   Pool: {ps['total']} total, {ps['active']} active")
    
    # Test requests
    for i in range(3):
        client, proxy = get_proxy_client()
        try:
            r = client.get("https://api.openalex.org/works?search=test&per_page=1&mailto=test@example.com")
            ip_info = "?"
            try:
                r2 = client.get("https://httpbin.org/ip", timeout=5)
                ip_info = r2.json().get("origin", "?")
            except Exception as _e:
                print(f"  [WARN] IP lookup via httpbin failed: {_e}")
            print(f"  [{i+1}] proxy={''.join((proxy or 'direct')[:40])} IP={ip_info} → HTTP {r.status_code}")
            report_result(proxy, r.status_code == 200)
        except Exception as e:
            print(f"  [{i+1}] proxy={''.join((proxy or 'direct')[:40])} → ERROR: {str(e)[:60]}")
            report_result(proxy, False)
        finally:
            client.close()
    
    ps = pool_stats()
    print(f"\n📊 Final: {ps['total']} total, {ps['active']} active, {ps['direct_fallbacks']} direct fallbacks")
