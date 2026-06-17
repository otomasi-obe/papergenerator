import logging
import time

import httpx

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_HEADERS = {
    "User-Agent": "PaperRiset-SLR/0.1 (mailto:research@example.com)",
    "Accept": "application/json",
}


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


def get_client() -> httpx.Client:
    timeout = httpx.Timeout(
        timeout=30.0,  # Overall timeout (increased for bulk fetch)
        connect=10.0,  # Connection timeout
        read=25.0,     # Read timeout
        write=10.0,    # Write timeout
        pool=10.0      # Pool timeout
    )
    return httpx.Client(timeout=timeout, headers=DEFAULT_HEADERS, follow_redirects=True)


# Retryable HTTP status codes (transient server errors)
_RETRYABLE_STATUS = {429, 502, 503, 504}


def fetch_json(
    client: httpx.Client,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    retries: int = 2,
) -> dict | None:
    for attempt in range(retries + 1):
        try:
            r = client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    # Invalid JSON body — retrying won't help
                    return None
            if r.status_code in _RETRYABLE_STATUS and attempt < retries:
                # Exponential backoff: 2s, 4s, 8s...
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code not in (200, 404):
                log.warning("fetch_json non-200 status=%s url=%s", r.status_code, url[:120])
            return None
        except httpx.TimeoutException:
            print(f"⚠️  Timeout on attempt {attempt + 1}/{retries + 1}")
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except httpx.HTTPError as e:
            print(f"⚠️  HTTP error on attempt {attempt + 1}/{retries + 1}: {e}")
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except ValueError:
            # Invalid response body — retrying won't help
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
            print(f"⚠️  Timeout on POST attempt {attempt + 1}/{retries + 1}")
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            return None
        except httpx.HTTPError as e:
            print(f"⚠️  HTTP error on POST attempt {attempt + 1}/{retries + 1}: {e}")
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
