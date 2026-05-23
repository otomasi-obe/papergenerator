import time
import httpx

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
    return httpx.Client(timeout=DEFAULT_TIMEOUT, headers=DEFAULT_HEADERS, follow_redirects=True)


def fetch_json(client: httpx.Client, url: str, params: dict | None = None,
               headers: dict | None = None, retries: int = 2) -> dict | None:
    for attempt in range(retries + 1):
        try:
            r = client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 503) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None
        except (httpx.HTTPError, ValueError):
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
    return None


def fetch_text(client: httpx.Client, url: str, params: dict | None = None,
               retries: int = 2) -> str | None:
    for attempt in range(retries + 1):
        try:
            r = client.get(url, params=params)
            if r.status_code == 200:
                return r.text
            if r.status_code in (429, 503) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None
        except httpx.HTTPError:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
    return None
