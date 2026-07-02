"""
Chat search tools — multi-backend web search with news, images, videos,
OSINT (Crossref, GitHub, Wikipedia, Wayback), and fetcher-style rate limiting.

Backends (12 total):
  ── DDGS ──
  - DDGS text()      → general web (primary)
  - DDGS news()      → berita terkini
  - DDGS images()    → image search
  - DDGS videos()    → video search
  - DDGS threads()   → forum/social media (Reddit, etc.)
  - DDGS extract()   → page content extraction (summary of a URL)

  ── Academic ──
  - ArXiv            → paper preprints
  - OpenAlex         → academic papers (primary)
  - Semantic Scholar  → academic papers (fallback)
  - Crossref          → papers with full metadata (OSINT)

  ── OSINT ──
  - GitHub           → code, repos, commits
  - Wikipedia        → knowledge articles
  - Wayback Machine   → historical page snapshots (Internet Archive)

Rate-limit strategy (mirrors bulk_fetch_v2.py fetcher architecture):
  - Per-backend threading.Lock + delay → prevents burst-over-limit
  - Auto-skip after 3 consecutive failures → unblocks stuck queries
  - Exponential backoff on transient errors (429, connection reset)
  - In-memory TTL cache → deduplicates identical queries
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Rate limiters — per-backend
# ═══════════════════════════════════════════════════════════════════════════════

# DDGS backends
_ddgs_text_lock = threading.Lock()
_ddgs_news_lock = threading.Lock()
_ddgs_images_lock = threading.Lock()
_ddgs_videos_lock = threading.Lock()
_ddgs_books_lock = threading.Lock()
_ddgs_extract_lock = threading.Lock()

_last_ddgs_text = 0.0
_last_ddgs_news = 0.0
_last_ddgs_images = 0.0
_last_ddgs_videos = 0.0
_last_ddgs_books = 0.0
_last_ddgs_extract = 0.0

DDGS_TEXT_DELAY = 2.0
DDGS_NEWS_DELAY = 2.0
DDGS_IMAGES_DELAY = 2.5
DDGS_VIDEOS_DELAY = 2.5
DDGS_BOOKS_DELAY = 2.5
DDGS_EXTRACT_DELAY = 1.5
DDGS_BACKOFF_BASE = 2.0
DDGS_MAX_RETRIES = 3
DDGS_CONSECUTIVE_FAIL_THRESHOLD = 3

_ddgs_text_fails = 0
_ddgs_news_fails = 0
_ddgs_images_fails = 0
_ddgs_videos_fails = 0
_ddgs_books_fails = 0
_ddgs_extract_fails = 0

# ArXiv
_arxiv_lock = threading.Lock()
_last_arxiv = 0.0
ARXIV_MIN_INTERVAL = 4.0

# Semantic Scholar
_s2_lock = threading.Lock()
_last_s2 = 0.0
S2_MIN_INTERVAL = 1.5

# OSINT backends
_crossref_lock = threading.Lock()
_last_crossref = 0.0
_github_lock = threading.Lock()
_last_github = 0.0
_wiki_lock = threading.Lock()
_last_wiki = 0.0
_wayback_lock = threading.Lock()
_last_wayback = 0.0

CROSSREF_MIN_INTERVAL = 1.0
GITHUB_MIN_INTERVAL = 1.5   # 60 req/hr unauthenticated
WIKI_MIN_INTERVAL = 1.0
WAYBACK_MIN_INTERVAL = 1.5

# ═══════════════════════════════════════════════════════════════════════════════
# In-memory cache (LRU with TTL)
# ═══════════════════════════════════════════════════════════════════════════════

_cache_lock = threading.Lock()
_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
MAX_CACHE_SIZE = 500
CACHE_TTL_WEB = 300
CACHE_TTL_NEWS = 120
CACHE_TTL_RECENT = 180
CACHE_TTL_IMAGES = 600      # images don't change much
CACHE_TTL_VIDEOS = 600
CACHE_TTL_BOOKS = 600       # book info stable
CACHE_TTL_EXTRACT = 600     # page content rarely changes
CACHE_TTL_CROSSREF = 600    # paper metadata stable
CACHE_TTL_GITHUB = 300
CACHE_TTL_WIKI = 600
CACHE_TTL_WAYBACK = 600


def _cache_key(backend: str, query: str, limit: int, **kwargs) -> str:
    raw = f"{backend}|{query.lower().strip()}|{limit}"
    for k in sorted(kwargs):
        raw += f"|{k}={kwargs[k]}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        if time.monotonic() > expires_at:
            del _cache[key]
            return None
        _cache.move_to_end(key)
        return result


def _cache_set(key: str, result: dict, ttl: int):
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
        else:
            _cache[key] = (time.monotonic() + ttl, result)
            while len(_cache) > MAX_CACHE_SIZE:
                _cache.popitem(last=False)


def _rate_limit(last_ref: float, interval: float, lock: threading.Lock) -> float:
    with lock:
        now = time.monotonic()
        gap = now - last_ref
        if gap < interval:
            time.sleep(interval - gap)
            now = time.monotonic()
        return now


def _osint_rate_limit(
    lock: threading.Lock,
    last_ref: float,
    interval: float,
) -> float:
    """Standard rate limit for OSINT backends. Returns new timestamp."""
    with lock:
        now = time.monotonic()
        gap = now - last_ref
        if gap < interval:
            time.sleep(interval - gap)
            now = time.monotonic()
        return now


# ═══════════════════════════════════════════════════════════════════════════════
# Query Cleaner — strip conversational filler before sending to search APIs
# ═══════════════════════════════════════════════════════════════════════════════

# Indonesian filler words/patterns to strip from search queries
_ID_FILLER = re.compile(
    r'\b('
    r'carikan|carikanlah|carilah|tolong|mohon|bisa|bisa tolong|'
    r'saya mau|saya ingin|saya perlu|aku mau|aku ingin|'
    r'untuk|buat|bagi|kepada|dari|dengan|oleh|'
    r'ya|yaa|yah|dong|nih|sih|deh|kok|kan|tuh|'
    r'tolong carikan|tolong cari|cari tahu|carikan saya|'
    r'jurnal2nya|jurnalnya|jurnal-jurnalnya|jurnal|paper-nya|paper|'
    r'referensi|refrensi|daftar pustaka|'
    r'sebenarnya|sepertinya|mungkin|kayaknya|kayak|'
    r'gimana|bagaimana|kenapa|mengapa|apa saja|'
    r'sebenarnya|coba|bantu|bantuin|'
    r'ini|itu|tersebut|berikut|tentang|mengenai|soal|'
    r'dan|atau|juga|serta|'
    r'ya jurnal|ya jurnal scopus|scopus ya|'
    r'\d+'  # bare numbers like "20"
    r')\b',
    re.IGNORECASE,
)

# English filler words/patterns
_EN_FILLER = re.compile(
    r'\b('
    r'please|kindly|could you|can you|would you|'
    r'find me|find some|find any|search for|look for|look up|'
    r'i need|i want|i\'d like|i\'m looking for|'
    r'about|regarding|related to|'
    r'some|any|the|a|an|in|on|of|to|for|and|or|with|'
    r'papers|articles|journals|references|sources|'
    r'for my|for the|for a|'
    r'can you find|help me find|help me search|'
    r'give me|show me|list me|'
    r'recent|recently|latest|new|newest|'
    r'scholar|scopus indexed|scopus journal|'
    r'\d+'  # bare numbers
    r')\b',
    re.IGNORECASE,
)

# Punctuation cleanup (keep only alphanumeric, spaces, and key symbols)
_PUNCT_CLEAN = re.compile(r'[^\w\s\-"]')
_MULTI_SPACE = re.compile(r'\s+')


def clean_search_query(raw_message: str) -> str:
    """Clean conversational user message into a search-engine-friendly query.

    Strips Indonesian & English filler words, numbers, punctuation, and
    collapses whitespace. Returns a concise keyword query suitable for
    OpenAlex, Semantic Scholar, Crossref, DuckDuckGo, etc.

    Examples:
        "Financial Management in Halal Logistics carikan jurnal2nya untuk referensi 20 ya jurnal scopus ya"
        → "financial management halal logistics"

        "tolong carikan paper tentang machine learning untuk prediksi harga saham"
        → "machine learning prediksi harga saham"

        "can you find me recent articles about blockchain in supply chain management"
        → "blockchain supply chain management"
    """
    if not raw_message:
        return ""

    q = raw_message.strip()

    # Remove punctuation (keep words, spaces, hyphens, quotes)
    q = _PUNCT_CLEAN.sub(' ', q)

    # Strip Indonesian filler
    q = _ID_FILLER.sub(' ', q)

    # Strip English filler
    q = _EN_FILLER.sub(' ', q)

    # Collapse whitespace & trim
    q = _MULTI_SPACE.sub(' ', q).strip()

    # If cleaning removed everything, fall back to original (stripped)
    if not q:
        q = _MULTI_SPACE.sub(' ', raw_message).strip()

    # Cap at reasonable length (search APIs don't need more)
    if len(q) > 200:
        q = q[:200].rsplit(' ', 1)[0]

    log.info("clean_search_query: '%s' → '%s'", raw_message[:80], q)
    return q


# ═══════════════════════════════════════════════════════════════════════════════
# Intent detection keywords
# ═══════════════════════════════════════════════════════════════════════════════

# ── GLOBAL non-search keywords ────────────────────────────────────────────
# If ANY of these appear in the message, ALL search intents are suppressed.
# This is the first line of defense against false positive intent detection.
_NON_SEARCH_KEYWORDS = {
    # Editing / revision (Indonesian)
    "perbaiki", "perbaikin", "perbaikiin", "betulin", "benahin",
    "edit", "editing", "revisi", "revisian", "koreksi",
    "ganti", "gantian", "ubah", "rubah", "modif",
    "tulis", "nulis", "nulisin",
    "terapkan", "terapin", "apply", "applied",
    "simpan", "nyimpen", "save",
    "lanjut", "lanjutkan", "lanjutin", "continue",
    "sambung", "sambungin", "sambungkan",
    "rapikan", "rapihin", "beresin", "neat",
    "buatin", "bikinin", "bikin", "create",
    "hapus", "delete", "remove", "buang",
    "pindah", "move", "cut",
    # Translation
    "terjemahkan", "terjemahin", "translate", "translatekan", "convert",
    "ubah ke english", "ubah ke indonesia", "ke english", "ke indonesia",
    # Definition / clarification
    "definisi", "definition", "pengertian", "apa itu", "apakah",
    "jelaskan", "explain", "terangkan", "describe",
    "contoh", "example", "misalnya",
    # Grammar / typo
    "grammar", "typo", "grammar", "ejaan", "spelling",
    "tata bahasa", "kata baku", "kata tidak baku",
    # Chat prompt / system
    "prompt", "system prompt", "template chat", "chat prompt",
}

# Combined: if any of these words (as a whole word) appear in the message,
# skip ALL intent detection (return empty).
def _has_non_search_keywords(message: str) -> bool:
    """Check if message contains ANY global non-search keyword (word boundary)."""
    msg_lower = message.lower()
    for kw in _NON_SEARCH_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', msg_lower):
            return True
    return False


INTENT_KEYWORDS = {
    "web_search": {
        "keywords": [
            "cari di internet", "search online", "google",
            "cari info", "cari informasi", "search for",
            "look up", "find online", "web search",
            "browse", "carikan di web", "cari di web",
            "cari tahu", "search web",
        ],
        "weight": 1,
    },
    "news_search": {
        "keywords": [
            "berita", "news", "terkini", "terbaru",
            "latest news", "breaking", "headline",
            "kejadian", "peristiwa", "hari ini",
            "today", "recent", "baru saja",
            "update", "terupdate", "current",
        ],
        "weight": 2,
    },
    "image_search": {
        "keywords": [
            "cari gambar", "search image", "gambar tentang",
            "foto", "photo", "picture", "ilustrasi",
            "cari ilustrasi", "visual", "image of",
        ],
        "weight": 1,
    },
    "video_search": {
        "keywords": [
            "cari video", "search video", "video tentang",
            "tutorial video", "youtube", "rekaman",
        ],
        "weight": 1,
    },
    "github_search": {
        "keywords": [
            "cari di github", "github", "source code",
            "kode sumber", "repository", "repo",
            "open source code", "cari kode",
        ],
        "weight": 1,
    },
    "wikipedia_search": {
        "keywords": [
            "wikipedia", "wiki", "cari di wiki",
            "definisi", "ensiklopedia", "encyclopedia",
        ],
        "weight": 1,
    },
    "arxiv_search": {
        "keywords": [
            "arxiv", "preprint", "paper terbaru", "latest paper",
            "recent paper", "paper terkini",
        ],
        "weight": 1,
    },
    "academic_search": {
        "keywords": [
            "cari paper", "search paper", "find paper",
            "cari jurnal", "search journal", "find journal",
            "carikan paper", "carikan jurnal",
            "carikan referensi", "cari referensi",
            "tolong cari paper", "tolong carikan jurnal",
            "cari literature", "search literature", "find literature",
            "cari literatur", "carikan literatur",
            "apa kata riset terbaru", "riset terbaru tentang",
            "latest research on", "recent studies on",
            "studi terbaru tentang", "penelitian terbaru tentang",
            "search for papers on", "find papers about",
            "previous study about", "penelitian sebelumnya tentang",
        ],
        "weight": 1,
        "invalidator": [
            "abstrak", "tulis", "perbaiki", "edit", "ganti", "revisi",
            "apply", "terapkan", "simpan", "update", "lanjutkan",
            "definisi", "jelaskan", "contoh", "pengertian",
            "hapus", "prompt", "template",
            "lanjut", "sambung", "buat section", "buat bab",
        ],
    },
    "research_gap": {
        "keywords": [
            "research gap", "celah penelitian", "gap penelitian",
            "kesenjangan penelitian", "gap analysis",
            "what hasn't been studied", "apa yang belum diteliti",
            "novelty", "kebaruan",
        ],
        "weight": 2,
    },
    "slr": {
        "keywords": [
            "slr", "systematic literature review",
            "tinjauan literatur sistematis", "literature review lengkap",
            "riset literatur mendalam", "comprehensive review",
        ],
        "weight": 3,
    },
}


def detect_intent(message: str) -> list[str]:
    """Detect search/research intents from user message.

    Returns list of intent names sorted by weight (highest first).
    Uses invalidator keywords to suppress intents on non-search messages.

    First checks global _NON_SEARCH_KEYWORDS — if ANY match, returns empty
    (no search intents). This prevents false positives on editing,
    revision, definition, and chat-prompt queries.
    """
    if not message or _has_non_search_keywords(message):
        return []
    msg = f" {message.lower().strip()} "
    detected = []
    for intent, cfg in INTENT_KEYWORDS.items():
        keywords = cfg.get("keywords", [])
        invalidators = cfg.get("invalidator", [])
        # Check if message contains ANY invalidator keyword → skip this intent
        if invalidators and any(f" {kw} " in msg or kw in msg for kw in invalidators):
            continue
        if any(f" {kw} " in msg or kw in msg for kw in keywords):
            detected.append((intent, cfg["weight"]))
    if not detected:
        return []
    detected.sort(key=lambda x: -x[1])
    return [d[0] for d in detected]


# ═══════════════════════════════════════════════════════════════════════════════
# DDGS import helper
# ═══════════════════════════════════════════════════════════════════════════════

_DDGS_AVAILABLE = None


def _ddgs_available() -> bool:
    global _DDGS_AVAILABLE
    if _DDGS_AVAILABLE is None:
        try:
            from ddgs import DDGS  # noqa: F401
            _DDGS_AVAILABLE = True
        except ImportError:
            log.error("ddgs not installed — DDGS backends unavailable")
            _DDGS_AVAILABLE = False
    return _DDGS_AVAILABLE


# ═══════════════════════════════════════════════════════════════════════════════
# DDGS — Web Search (text)
# ═══════════════════════════════════════════════════════════════════════════════

def web_search(
    query: str,
    limit: int = 5,
    timelimit: str | None = None,
    region: str = "id-id",
    use_cache: bool = True,
) -> dict[str, Any]:
    """Search the web using DuckDuckGo.

    Returns:
        {"success": bool, "results": [{"title", "url", "snippet", "date"}], "error": str}
    """
    return _ddgs_search(
        backend="text",
        query=query,
        limit=limit,
        timelimit=timelimit,
        region=region,
        use_cache=use_cache,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DDGS — News
# ═══════════════════════════════════════════════════════════════════════════════

def web_news(
    query: str,
    limit: int = 8,
    region: str = "id-id",
    use_cache: bool = True,
) -> dict[str, Any]:
    """Search recent news using DuckDuckGo News."""
    return _ddgs_search(
        backend="news",
        query=query,
        limit=limit,
        region=region,
        use_cache=use_cache,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DDGS — Images (NEW)
# ═══════════════════════════════════════════════════════════════════════════════

def ddgs_images(
    query: str,
    limit: int = 10,
    region: str = "id-id",
    use_cache: bool = True,
) -> dict[str, Any]:
    """Search images using DuckDuckGo Images.

    Returns:
        {"success": bool, "results": [{"title", "url", "image_url", "thumbnail", "source", "width", "height"}], "error": str}
    """
    return _ddgs_search(
        backend="images",
        query=query,
        limit=limit,
        region=region,
        use_cache=use_cache,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DDGS — Videos (NEW)
# ═══════════════════════════════════════════════════════════════════════════════

def ddgs_videos(
    query: str,
    limit: int = 8,
    region: str = "id-id",
    use_cache: bool = True,
) -> dict[str, Any]:
    """Search videos using DuckDuckGo Videos.

    Returns:
        {"success": bool, "results": [{"title", "url", "thumbnail", "duration", "source", "views"}], "error": str}
    """
    return _ddgs_search(
        backend="videos",
        query=query,
        limit=limit,
        region=region,
        use_cache=use_cache,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DDGS — Books (NEW)
# ═══════════════════════════════════════════════════════════════════════════════

def ddgs_books(
    query: str,
    limit: int = 8,
    region: str = "id-id",
    use_cache: bool = True,
) -> dict[str, Any]:
    """Search books using DuckDuckGo Books.

    Returns:
        {"success": bool, "results": [{"title", "url", "snippet", "authors", "source", "year"}], "error": str}
    """
    return _ddgs_search(
        backend="books",
        query=query,
        limit=limit,
        region=region,
        use_cache=use_cache,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DDGS — Threads / Social Media (site-restricted text search)
# ═══════════════════════════════════════════════════════════════════════════════

def ddgs_threads(
    query: str,
    limit: int = 10,
    region: str = "id-id",
    use_cache: bool = True,
) -> dict[str, Any]:
    """Search forum/social media via site-restricted DDGS text search.

    Since ddgs.threads() is not implemented in ddgs 9.14.4,
    uses site:reddit.com|stackexchange.com|medium.com filter on text search.

    Returns:
        {"success": bool, "results": [{"title", "url", "snippet", "date", "source"}], "error": str}
    """
    site_filter = "(site:reddit.com OR site:stackexchange.com OR site:medium.com OR site:news.ycombinator.com)"
    full_query = f"{query} {site_filter}"
    return web_search(full_query, limit=limit, region=region, use_cache=use_cache)


# ═══════════════════════════════════════════════════════════════════════════════
# DDGS — Extract (page content) (NEW)
# ═══════════════════════════════════════════════════════════════════════════════

def ddgs_extract(
    url: str,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Extract/summarize a web page using DuckDuckGo extract.

    Returns:
        {"success": bool, "results": [{"title", "url", "content"}], "error": str}
    """
    global _ddgs_extract_fails, _last_ddgs_extract
    backend = "extract"

    if not _ddgs_available():
        return {"success": False, "results": [], "error": "ddgs not installed"}
    if _ddgs_extract_fails >= DDGS_CONSECUTIVE_FAIL_THRESHOLD:
        return {"success": False, "results": [], "error": f"ddgs_extract auto-skipped"}

    ck = _cache_key(backend, url, 1)
    ttl = CACHE_TTL_EXTRACT
    if use_cache:
        cached = _cache_get(ck)
        if cached is not None:
            return cached

    from ddgs import DDGS

    last_error = None
    for attempt in range(DDGS_MAX_RETRIES + 1):
        now = _rate_limit(
            _last_ddgs_extract if attempt == 0 else 0.0,
            DDGS_EXTRACT_DELAY, _ddgs_extract_lock,
        )
        try:
            with DDGS() as client:
                extracted = client.extract(url)
            _last_ddgs_extract = time.monotonic()
            _ddgs_extract_fails = 0

            if extracted:
                results = [{
                    "title": extracted.get("title", ""),
                    "url": url,
                    "content": extracted.get("content", "") or "",
                    "date": extracted.get("date", ""),
                }]
            else:
                results = []

            result = {"success": len(results) > 0, "results": results, "error": None}
            _cache_set(ck, result, ttl)
            return result

        except Exception as e:
            last_error = str(e)
            is_rate_limited = any(kw in last_error.lower() for kw in ("403", "429", "ratelimit"))
            is_transient = any(kw in last_error.lower() for kw in (
                "timeout", "connection", "reset", "refused", "temporary",
            ))
            if is_rate_limited or is_transient:
                backoff = DDGS_BACKOFF_BASE * (2 ** attempt)
                time.sleep(backoff)
                continue
            break

    _ddgs_extract_fails += 1
    return {"success": False, "results": [], "error": last_error or "unknown error"}


def _ddgs_search(
    backend: str,
    query: str,
    limit: int = 5,
    timelimit: str | None = None,
    region: str = "id-id",
    use_cache: bool = True,
) -> dict[str, Any]:
    """Core DDGS search with rate limiting, auto-skip, backoff, and caching."""
    global _last_ddgs_text, _last_ddgs_news, _last_ddgs_images, _last_ddgs_videos, _last_ddgs_books
    global _ddgs_text_fails, _ddgs_news_fails, _ddgs_images_fails, _ddgs_videos_fails, _ddgs_books_fails

    if not _ddgs_available():
        return {"success": False, "results": [], "error": "ddgs not installed"}

    limit = min(limit, 30 if backend in ("images", "videos") else 20)

    # TTL per backend
    ttl_map = {
        "news": CACHE_TTL_NEWS,
        "images": CACHE_TTL_IMAGES,
        "videos": CACHE_TTL_VIDEOS,
        "books": CACHE_TTL_BOOKS,
    }
    ttl: int = ttl_map.get(backend, CACHE_TTL_RECENT if timelimit else CACHE_TTL_WEB)
    ck: str = _cache_key(backend, query, limit, timelimit=timelimit or "", region=region)

    if use_cache:
        cached = _cache_get(ck)
        if cached is not None:
            log.info("ddgs_%s '%s': %d results (cached)", backend, query[:60], len(cached.get("results", [])))
            return cached

    # Backend config map
    config = {
        "text":   {"fails": _ddgs_text_fails,    "lock": _ddgs_text_lock,    "delay": DDGS_TEXT_DELAY,
                   "last": _last_ddgs_text,      "method": "text",           "params": {}},
        "news":   {"fails": _ddgs_news_fails,    "lock": _ddgs_news_lock,    "delay": DDGS_NEWS_DELAY,
                   "last": _last_ddgs_news,      "method": "news",           "params": {}},
        "images": {"fails": _ddgs_images_fails,  "lock": _ddgs_images_lock,  "delay": DDGS_IMAGES_DELAY,
                   "last": _last_ddgs_images,    "method": "images",         "params": {}},
        "videos": {"fails": _ddgs_videos_fails,  "lock": _ddgs_videos_lock,  "delay": DDGS_VIDEOS_DELAY,
                   "last": _last_ddgs_videos,    "method": "videos",         "params": {}},
        "books":  {"fails": _ddgs_books_fails,   "lock": _ddgs_books_lock,   "delay": DDGS_BOOKS_DELAY,
                   "last": _last_ddgs_books,     "method": "books",          "params": {}},
    }

    cfg = config.get(backend)
    if cfg is None:
        return {"success": False, "results": [], "error": f"Unknown DDGS backend: {backend}"}

    fails = cfg["fails"]
    if fails >= DDGS_CONSECUTIVE_FAIL_THRESHOLD:
        return {"success": False, "results": [], "error": f"ddgs_{backend} auto-skipped after {fails} failures"}

    from ddgs import DDGS

    last_error = None
    for attempt in range(DDGS_MAX_RETRIES + 1):
        now = _rate_limit(cfg["last"] if attempt == 0 else 0.0, cfg["delay"], cfg["lock"])

        try:
            results = []
            with DDGS() as client:
                method = getattr(client, cfg["method"])
                kwargs = {"max_results": limit}
                if region:
                    kwargs["region"] = region
                if timelimit and backend == "text":
                    kwargs["timelimit"] = timelimit

                iterator = method(query, **kwargs)

                for i, hit in enumerate(iterator):
                    if i >= limit:
                        break

                    if backend == "news":
                        results.append({
                            "title": hit.get("title", ""),
                            "url": hit.get("url", ""),
                            "snippet": hit.get("body", ""),
                            "date": hit.get("date", ""),
                            "source": hit.get("source", ""),
                            "image": hit.get("image", ""),
                        })
                    elif backend == "images":
                        results.append({
                            "title": hit.get("title", ""),
                            "url": hit.get("url", ""),
                            "image_url": hit.get("image", ""),
                            "thumbnail": hit.get("thumbnail", ""),
                            "source": hit.get("source", ""),
                            "width": hit.get("width"),
                            "height": hit.get("height"),
                        })
                    elif backend == "videos":
                        results.append({
                            "title": hit.get("title", ""),
                            "url": hit.get("url", ""),
                            "thumbnail": hit.get("thumbnail", ""),
                            "duration": hit.get("duration", ""),
                            "source": hit.get("source", ""),
                            "views": hit.get("views", ""),
                            "snippet": hit.get("description", ""),
                        })
                    elif backend == "books":
                        results.append({
                            "title": hit.get("title", ""),
                            "url": hit.get("url", ""),
                            "snippet": hit.get("description", hit.get("body", "")),
                            "authors": hit.get("authors", ""),
                            "source": hit.get("source", ""),
                            "year": hit.get("year", ""),
                        })
                    else:
                        results.append({
                            "title": hit.get("title", ""),
                            "url": hit.get("href") or hit.get("url", ""),
                            "snippet": hit.get("body", ""),
                            "date": hit.get("date", ""),
                        })

            # Success
            _update_backend_state(backend, time.monotonic(), 0)

            result = {"success": True, "results": results, "error": None}
            if use_cache:
                _cache_set(ck, result, ttl)
            log.info("ddgs_%s '%s': %d results (attempt %d)", backend, query[:60], len(results), attempt + 1)
            return result

        except Exception as e:
            last_error = str(e)
            is_rate_limited = "403" in last_error or "429" in last_error or "ratelimit" in last_error.lower()
            is_transient = any(kw in last_error.lower() for kw in (
                "timeout", "connection", "reset", "refused", "temporary",
            ))
            if is_rate_limited or is_transient:
                backoff = DDGS_BACKOFF_BASE * (2 ** attempt)
                log.warning("ddgs_%s: transient error (attempt %d/%d), backoff %.1fs: %s",
                            backend, attempt + 1, DDGS_MAX_RETRIES + 1, backoff, last_error[:100])
                time.sleep(backoff)
                continue
            else:
                log.warning("ddgs_%s: non-transient error: %s", backend, last_error[:200])
                break

    # All retries exhausted
    _increment_backend_fails(backend)
    return {"success": False, "results": [], "error": last_error or "unknown error"}


def _update_backend_state(backend: str, timestamp: float, fails: int):
    """Reset backend state after success."""
    global _last_ddgs_text, _last_ddgs_news, _last_ddgs_images, _last_ddgs_videos, _last_ddgs_books
    global _ddgs_text_fails, _ddgs_news_fails, _ddgs_images_fails, _ddgs_videos_fails, _ddgs_books_fails
    if backend == "text":
        _last_ddgs_text = timestamp; _ddgs_text_fails = fails
    elif backend == "news":
        _last_ddgs_news = timestamp; _ddgs_news_fails = fails
    elif backend == "images":
        _last_ddgs_images = timestamp; _ddgs_images_fails = fails
    elif backend == "videos":
        _last_ddgs_videos = timestamp; _ddgs_videos_fails = fails
    elif backend == "books":
        _last_ddgs_books = timestamp; _ddgs_books_fails = fails


def _increment_backend_fails(backend: str):
    """Increment fail counter and log if threshold reached."""
    global _ddgs_text_fails, _ddgs_news_fails, _ddgs_images_fails, _ddgs_videos_fails, _ddgs_books_fails
    count = 0
    if backend == "text":
        _ddgs_text_fails += 1; count = _ddgs_text_fails
    elif backend == "news":
        _ddgs_news_fails += 1; count = _ddgs_news_fails
    elif backend == "images":
        _ddgs_images_fails += 1; count = _ddgs_images_fails
    elif backend == "videos":
        _ddgs_videos_fails += 1; count = _ddgs_videos_fails
    elif backend == "books":
        _ddgs_books_fails += 1; count = _ddgs_books_fails
    if count >= DDGS_CONSECUTIVE_FAIL_THRESHOLD:
        log.warning("ddgs_%s: auto-skip threshold reached (%d fails)", backend, count)


# ═══════════════════════════════════════════════════════════════════════════════
# Combined news + recent web
# ═══════════════════════════════════════════════════════════════════════════════

def combined_news_search(query: str, limit: int = 8) -> dict[str, Any]:
    """Run both news() and text(timelimit='d') in parallel, merge results."""
    results: dict[str, Any] = {"success": False, "results": [], "error": None}
    all_items: list[dict] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {
            ex.submit(web_news, query, limit): "news",
            ex.submit(web_search, query, limit, timelimit="d"): "recent_web",
        }
        for fut in as_completed(futures):
            source = futures[fut]
            try:
                data = fut.result()
                if data.get("success") and data.get("results"):
                    for item in data["results"]:
                        url = item.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            item["source"] = source
                            all_items.append(item)
            except Exception as e:
                log.warning("combined_news: %s failed: %s", source, e)

    news_items = [i for i in all_items if i.get("date")]
    web_items = [i for i in all_items if not i.get("date")]
    news_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    all_items = news_items + web_items

    results["success"] = len(all_items) > 0
    results["results"] = all_items[:limit]
    if not results["success"]:
        results["error"] = "No results from news or recent web search"
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# ArXiv
# ═══════════════════════════════════════════════════════════════════════════════

def arxiv_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search arXiv for papers."""
    global _last_arxiv
    with _arxiv_lock:
        now = time.monotonic()
        gap = now - _last_arxiv
        if gap < ARXIV_MIN_INTERVAL:
            time.sleep(ARXIV_MIN_INTERVAL - gap)
        _last_arxiv = time.monotonic()

    try:
        from tools.Literatur.fetchers.arxiv import search as arxiv_search_fn
        from tools.Literatur.http_client import get_client

        results = []
        with get_client() as client:
            for paper in arxiv_search_fn(client, query, limit=limit):
                results.append({
                    "title": paper.title or "",
                    "authors": paper.authors[:5] if paper.authors else [],
                    "abstract": (paper.abstract or "")[:500],
                    "year": paper.year,
                    "url": paper.url or "",
                    "doi": paper.doi or "",
                    "source": "arxiv",
                })
        log.info("arxiv_search '%s': %d results", query[:60], len(results))
        return {"success": True, "results": results, "error": None}
    except Exception as e:
        log.warning("arxiv_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Academic search (OpenAlex → Semantic Scholar → Crossref)
# ═══════════════════════════════════════════════════════════════════════════════

def academic_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search academic papers via OpenAlex with Semantic Scholar fallback."""
    result = _openalex_search(query, limit)
    if result["success"] and result["results"]:
        return result

    global _last_s2
    with _s2_lock:
        now = time.monotonic()
        gap = now - _last_s2
        if gap < S2_MIN_INTERVAL:
            time.sleep(S2_MIN_INTERVAL - gap)
        _last_s2 = time.monotonic()

    try:
        from tools.Literatur.fetchers.semantic_scholar import search as s2_search_fn
        from tools.Literatur.http_client import get_client

        results = []
        with get_client() as client:
            for paper in s2_search_fn(client, query, limit=limit):
                results.append({
                    "title": paper.title or "",
                    "authors": paper.authors[:5] if paper.authors else [],
                    "abstract": (paper.abstract or "")[:500],
                    "year": paper.year,
                    "venue": paper.venue or "",
                    "citations": paper.citations,
                    "doi": paper.doi or "",
                    "url": paper.url or "",
                    "source": "semantic_scholar",
                    "open_access": paper.is_open_access,
                })
        log.info("academic_search (S2) '%s': %d results", query[:60], len(results))
        return {"success": True, "results": results, "error": None}
    except Exception as e:
        log.warning("academic_search error: %s", e)
        # Final fallback: ResearchGate HTML scrape (Cloudflare may block)
        try:
            from tools.Literatur.fetchers.researchgate import search as rg_search_fn
            from tools.Literatur.http_client import get_client
            results = []
            with get_client() as client:
                for paper in rg_search_fn(client, query, limit=limit):
                    results.append({
                        "title": paper.title or "",
                        "authors": paper.authors[:5] if paper.authors else [],
                        "abstract": (paper.abstract or "")[:500],
                        "year": paper.year,
                        "venue": paper.venue or "",
                        "citations": paper.citations,
                        "doi": paper.doi or "",
                        "url": paper.url or "",
                        "source": "researchgate",
                        "open_access": paper.is_open_access,
                    })
            if results:
                log.info("academic_search (RG) '%s': %d results", query[:60], len(results))
                return {"success": True, "results": results, "error": None}
        except Exception as rg_err:
            log.warning("academic_search (RG fallback) error: %s", rg_err)
        return {"success": False, "results": [], "error": str(e)}


def _openalex_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Quick OpenAlex search — no API key, fast, reliable."""
    try:
        import httpx
        resp = httpx.get(
            "https://api.openalex.org/works",
            params={
                "search": query,
                "per_page": min(limit, 25),
                "select": "id,title,publication_year,cited_by_count,doi,authorships,primary_location,open_access",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            return {"success": False, "results": [], "error": f"OpenAlex HTTP {resp.status_code}"}

        data = resp.json()
        results = []
        for work in data.get("results", []):
            title = work.get("title", "")
            if not title:
                continue
            authors = []
            for auth in (work.get("authorships") or [])[:5]:
                author = auth.get("author", {})
                if author.get("display_name"):
                    authors.append(author["display_name"])
            loc = work.get("primary_location") or {}
            source = loc.get("source") or {}
            venue = source.get("display_name", "")
            doi = (work.get("doi") or "").replace("https://doi.org/", "")
            oa_info = work.get("open_access") or {}
            oa_url = oa_info.get("oa_url", "")

            results.append({
                "title": title,
                "authors": authors,
                "abstract": "",
                "year": work.get("publication_year"),
                "venue": venue,
                "citations": work.get("cited_by_count"),
                "doi": doi,
                "url": oa_url or f"https://doi.org/{doi}" if doi else "",
                "source": "openalex",
                "open_access": bool(oa_url),
            })
        log.info("openalex_search '%s': %d results", query[:60], len(results))
        return {"success": True, "results": results, "error": None}
    except Exception as e:
        log.warning("openalex_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# OSINT — Crossref (NEW) — papers with full metadata, no API key
# ═══════════════════════════════════════════════════════════════════════════════

def crossref_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search academic papers via Crossref REST API.

    Free, no API key required. Returns full metadata: DOI, authors, journal,
    publication date, abstract, references count, citations.
    """
    global _last_crossref
    _last_crossref = _osint_rate_limit(_crossref_lock, _last_crossref, CROSSREF_MIN_INTERVAL)

    ck = _cache_key("crossref", query, limit)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    try:
        import httpx
        resp = httpx.get(
            "https://api.crossref.org/works",
            params={
                "query": query,
                "rows": min(limit, 25),
            },
            timeout=15.0,
        )
        if resp.status_code != 200:
            return {"success": False, "results": [], "error": f"Crossref HTTP {resp.status_code}"}

        data = resp.json()
        items = data.get("message", {}).get("items", [])
        results = []
        for item in items:
            title = item.get("title", [])
            title = title[0] if title else ""
            if not title:
                continue

            authors = []
            for a in (item.get("author") or [])[:5]:
                given = a.get("given", "")
                family = a.get("family", "")
                if given or family:
                    authors.append(f"{given} {family}".strip())

            pub = item.get("published-print", {})
            date_parts = pub.get("date-parts", [[None]])[0]
            year = date_parts[0] if date_parts else None

            container = item.get("container-title", [])
            venue = container[0] if container else ""

            doi = item.get("DOI", "")
            abstract = item.get("abstract", "")
            if abstract and len(abstract) > 800:
                abstract = abstract[:800] + "..."

            link_list = item.get("link", [])
            url = ""
            for lk in link_list:
                if lk.get("content-type") in ("text/html", "application/pdf"):
                    url = lk.get("URL", "")
                    break
            if not url and doi:
                url = f"https://doi.org/{doi}"

            results.append({
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "year": year,
                "venue": venue,
                "citations": item.get("is-referenced-by-count"),
                "reference_count": item.get("reference-count"),
                "doi": doi,
                "url": url,
                "publisher": item.get("publisher", ""),
                "source": "crossref",
            })

        log.info("crossref_search '%s': %d results", query[:60], len(results))
        result = {"success": len(results) > 0, "results": results, "error": None if results else "No results"}
        _cache_set(ck, result, CACHE_TTL_CROSSREF)
        return result
    except Exception as e:
        log.warning("crossref_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# OSINT — GitHub Code Search (NEW) — no auth, 60 req/hr
# ═══════════════════════════════════════════════════════════════════════════════

def github_search(query: str, limit: int = 8, search_type: str = "repositories") -> dict[str, Any]:
    """Search GitHub for repositories, code, or commits.

    Free, no auth. Rate limit: ~10 req/min unauthenticated.
    search_type: 'repositories', 'code', 'commits', 'issues', 'topics'

    Returns:
        {"success": bool, "results": [...], "error": str}
    """
    global _last_github
    _last_github = _osint_rate_limit(_github_lock, _last_github, GITHUB_MIN_INTERVAL)

    ck = _cache_key("github", f"{search_type}:{query}", limit)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    try:
        import httpx
        valid_types = {"repositories", "code", "commits", "issues", "topics"}
        if search_type not in valid_types:
            search_type = "repositories"

        resp = httpx.get(
            f"https://api.github.com/search/{search_type}",
            params={"q": query, "per_page": min(limit, 30)},
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "PaperGenerator/1.0",
            },
            timeout=15.0,
        )
        if resp.status_code == 403:
            return {"success": False, "results": [], "error": "GitHub rate limit exceeded (60/hr unauth)"}
        if resp.status_code != 200:
            return {"success": False, "results": [], "error": f"GitHub HTTP {resp.status_code}"}

        data = resp.json()
        results = []
        for item in data.get("items", [])[:limit]:
            if search_type == "repositories":
                results.append({
                    "title": item.get("full_name", item.get("name", "")),
                    "url": item.get("html_url", ""),
                    "snippet": (item.get("description") or "")[:300],
                    "language": item.get("language", ""),
                    "stars": item.get("stargazers_count", 0),
                    "forks": item.get("forks_count", 0),
                    "updated": item.get("updated_at", ""),
                    "topics": item.get("topics", []),
                    "source": "github_repo",
                })
            elif search_type == "code":
                repo = item.get("repository", {})
                results.append({
                    "title": f"{item.get('path', '')} — {repo.get('full_name', '')}",
                    "url": item.get("html_url", ""),
                    "snippet": "",
                    "repo": repo.get("full_name", ""),
                    "source": "github_code",
                })
            else:
                results.append({
                    "title": item.get("title", item.get("name", item.get("path", ""))),
                    "url": item.get("html_url", ""),
                    "snippet": (item.get("description", item.get("body", "")) or "")[:300],
                    "source": f"github_{search_type}",
                })

        log.info("github_search '%s' (%s): %d results", query[:60], search_type, len(results))
        result = {"success": len(results) > 0, "results": results, "error": None if results else "No results"}
        _cache_set(ck, result, CACHE_TTL_GITHUB)
        return result
    except Exception as e:
        log.warning("github_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# OSINT — Wikipedia (NEW) — free REST API
# ═══════════════════════════════════════════════════════════════════════════════

def wikipedia_search(query: str, limit: int = 5, lang: str = "en") -> dict[str, Any]:
    """Search Wikipedia articles via REST API.

    Free, no API key. lang: 'en', 'id', 'ms', etc.

    Returns:
        {"success": bool, "results": [{"title", "url", "snippet", "pageid", "wordcount"}], "error": str}
    """
    global _last_wiki
    _last_wiki = _osint_rate_limit(_wiki_lock, _last_wiki, WIKI_MIN_INTERVAL)

    ck = _cache_key("wikipedia", f"{lang}:{query}", limit)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    try:
        import httpx
        resp = httpx.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": min(limit, 20),
                "srprop": "snippet|wordcount|size",
            },
            timeout=10.0,
            headers={"User-Agent": "PaperGenerator/1.0 (https://paperfull.app; rofiqcp@gmail.com)"},
        )
        if resp.status_code != 200:
            return {"success": False, "results": [], "error": f"Wikipedia HTTP {resp.status_code}"}

        data = resp.json()
        search_results = data.get("query", {}).get("search", [])
        results = []
        for sr in search_results:
            title = sr.get("title", "")
            if not title:
                continue
            encoded_title = quote(title.replace(" ", "_"))
            results.append({
                "title": title,
                "url": f"https://{lang}.wikipedia.org/wiki/{encoded_title}",
                "snippet": (sr.get("snippet", "") or "").replace('<span class="searchmatch">', '**').replace('</span>', '**'),
                "pageid": sr.get("pageid"),
                "wordcount": sr.get("wordcount"),
                "source": "wikipedia",
            })

        log.info("wikipedia_search '%s' (%s): %d results", query[:60], lang, len(results))
        result = {"success": len(results) > 0, "results": results, "error": None if results else "No results"}
        _cache_set(ck, result, CACHE_TTL_WIKI)
        return result
    except Exception as e:
        log.warning("wikipedia_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# OSINT — Wayback Machine (NEW) — Internet Archive
# ═══════════════════════════════════════════════════════════════════════════════

def wayback_search(url: str) -> dict[str, Any]:
    """Check Wayback Machine for historical snapshots of a URL.

    Free, no API key. Returns the closest available snapshot.

    Returns:
        {"success": bool, "results": [{"original_url", "wayback_url", "timestamp", "available"}], "error": str}
    """
    global _last_wayback
    _last_wayback = _osint_rate_limit(_wayback_lock, _last_wayback, WAYBACK_MIN_INTERVAL)

    ck = _cache_key("wayback", url, 1)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    try:
        import httpx
        resp = httpx.get(
            "https://archive.org/wayback/available",
            params={"url": url},
            timeout=10.0,
            headers={"User-Agent": "PaperGenerator/1.0"},
        )
        if resp.status_code != 200:
            return {"success": False, "results": [], "error": f"Wayback HTTP {resp.status_code}"}

        data = resp.json()
        snapshots = data.get("archived_snapshots", {})
        results = []

        if isinstance(snapshots, dict):
            closest = snapshots.get("closest", {})
            if closest and closest.get("available"):
                timestamp = closest.get("timestamp", "")
                wayback_url = closest.get("url", "")
                # Format timestamp: 20240101120000 → 2024-01-01
                ts_formatted = ""
                if len(timestamp) >= 8:
                    ts_formatted = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
                    if len(timestamp) >= 10:
                        ts_formatted += f" {timestamp[8:10]}:{timestamp[10:12]}"

                results.append({
                    "original_url": url,
                    "wayback_url": wayback_url or f"https://web.archive.org/web/{timestamp}/{url}",
                    "timestamp": timestamp,
                    "ts_formatted": ts_formatted,
                    "available": True,
                    "source": "wayback",
                })

        if not results:
            results.append({
                "original_url": url,
                "wayback_url": "",
                "timestamp": None,
                "ts_formatted": "",
                "available": False,
                "source": "wayback",
            })

        log.info("wayback_search '%s': available=%s", url[:60], results[0].get("available"))
        result = {"success": True, "results": results, "error": None}
        _cache_set(ck, result, CACHE_TTL_WAYBACK)
        return result
    except Exception as e:
        log.warning("wayback_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Parallel multi-search (pre-AI intent-based)
# ═══════════════════════════════════════════════════════════════════════════════

def execute_searches(intents: list[str], query: str, limit: int = 5) -> dict[str, Any]:
    """Execute multiple searches in parallel based on detected intents."""
    if not intents:
        return {"context": "", "has_results": False, "needs_slr_offer": False}

    # Clean the raw user message into a concise search query
    clean_query = clean_search_query(query)
    if not clean_query:
        clean_query = query  # fallback

    searches: dict[str, tuple[str, Any, str, int]] = {}
    for intent in intents:
        if intent == "news_search":
            searches["news"] = ("Berita Terkini", combined_news_search, clean_query, min(limit, 8))
            searches["web"] = ("Web Search", web_search, clean_query, min(limit, 5))
        elif intent == "web_search":
            searches["web"] = ("Web Search (DuckDuckGo)", web_search, clean_query, limit)
        elif intent == "image_search":
            searches["images"] = ("Gambar (DuckDuckGo)", ddgs_images, clean_query, min(limit, 10))
        elif intent == "video_search":
            searches["videos"] = ("Video (DuckDuckGo)", ddgs_videos, clean_query, min(limit, 8))
        elif intent == "github_search":
            searches["github"] = ("GitHub Repos", github_search, clean_query, min(limit, 8))
        elif intent == "wikipedia_search":
            searches["wiki"] = ("Wikipedia", wikipedia_search, clean_query, min(limit, 5))
        elif intent == "arxiv_search":
            searches["arxiv"] = ("ArXiv Search", arxiv_search, clean_query, min(limit, 10))
        elif intent == "academic_search":
            # Skip pre-flight — let AI decide which Literatur fetchers to use
            # via search tags [SCHOLAR:q], [SCOPUS:q], [CROSSREF:q], etc.
            pass
        elif intent == "research_gap":
            # Skip pre-flight — let AI decide which fetchers to use
            pass
        elif intent == "slr":
            pass

    if not searches:
        # SLR intent intentionally adds no searches here (handled by SLR pipeline),
        # and any other intent without a mapping should return early gracefully.
        return {"context": "", "has_results": False, "needs_slr_offer": "slr" in intents}

    results: dict[str, tuple[str, dict]] = {}
    with ThreadPoolExecutor(max_workers=min(5, max(1, len(searches)))) as ex:
        futures = {}
        for key, (label, fn, q, lim) in searches.items():
            futures[ex.submit(fn, q, lim)] = (key, label)
        for fut in as_completed(futures):
            key, label = futures[fut]
            try:
                results[key] = (label, fut.result())
            except Exception as e:
                results[key] = (label, {"success": False, "results": [], "error": str(e)})

    parts = []
    has_results = False
    for key, (label, data) in results.items():
        if not data.get("success") or not data.get("results"):
            err = data.get("error", "no results")
            parts.append(f"### {label}\n(No results: {err})\n")
            continue
        has_results = True
        items = data["results"]
        parts.append(f"### {label} — {len(items)} hasil ditemukan\n")
        parts.extend(_format_result_items(items, key))

    context = ""
    if parts:
        context = "## HASIL PENCARIAN OTOMATIS (gunakan sebagai referensi)\n\n" + "\n".join(parts)

    return {
        "context": context,
        "has_results": has_results,
        "needs_slr_offer": "slr" in intents or "research_gap" in intents,
    }


def _format_result_items(items: list[dict], source_type: str) -> list[str]:
    """Format result items into markdown lines. Shared by execute_searches and format_search_results_for_ai.
    
    Outputs each item as a clickable markdown link so AI naturally copies the link format.
    """
    lines = []
    for i, item in enumerate(items, 1):
        title = item.get("title", "Untitled")
        year = item.get("year", "")
        authors_list = item.get("authors", [])
        authors = ", ".join(authors_list[:3]) if authors_list else ""
        if len(authors_list) > 3:
            authors += " et al."
        url = item.get("url", item.get("wayback_url", ""))
        doi = item.get("doi", "")
        venue = item.get("venue", "")
        citations = item.get("citations")
        snippet = item.get("snippet", item.get("abstract", ""))
        if snippet and len(snippet) > 300:
            snippet = snippet[:300] + "..."
        source = item.get("source", "")
        date = item.get("date", "")
        image_url = item.get("image_url", "")

        # Build markdown link — this is KEY for Phase 2 to copy links
        link_url = ""
        if doi:
            link_url = f"https://doi.org/{doi}" if not doi.startswith("http") else doi
        elif url:
            link_url = url

        if link_url:
            line = f"{i}. [{title}]({link_url})"
        else:
            line = f"{i}. **{title}**"

        if authors:
            line += f"\n   Authors: {authors}"
        if year:
            line += f" ({year})"
        if date and source_type in ("news", "videos"):
            line += f" [📅 {date[:10]}]"
        if venue:
            line += f"\n   Venue: {venue}"
        if citations is not None:
            line += f" | Citations: {citations}"
        if doi and not link_url.startswith("https://doi.org/"):
            line += f"\n   DOI: {doi}"
        if url and link_url != url:
            line += f"\n   URL: {url}"
        if image_url:
            line += f"\n   🖼️ Image: {image_url}"
        if source:
            line += f" [Source: {source}]"
        if snippet:
            line += f"\n   {snippet}"
        lines.append(line + "\n")
    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# Search tag extraction from AI response (two-phase flow)
# ═══════════════════════════════════════════════════════════════════════════════

_SEARCH_TAG_RE = re.compile(
    r"\[(WEBSEARCH|NEWS|ARXIV|SCHOLAR|IMAGE|VIDEO|BOOKS|THREADS|EXTRACT|CROSSREF|GITHUB|WIKI|WAYBACK|"
    r"SCOPUS|IEEE|PUBMED|DBLP|DIMENSIONS|CORE|DOAJ|PLOS|OPENAIRE|EUROPEPMC|SINTA|"
    r"ZENODO|DATACITE|SCIENCEDIRECT|OPENALEX|SEMANTIC_SCHOLAR|PUBLISHERS):"
    r"([^\]]{1,500})\]",
    re.IGNORECASE,
)


def extract_search_tags(text: str) -> list[dict]:
    """Extract search commands from AI text.

    Returns list of {"type": "...", "query": "...", "raw": "[...]"}.
    """
    type_map = {
        "WEBSEARCH": "web",
        "NEWS": "news",
        "ARXIV": "arxiv",
        "SCHOLAR": "scholar",
        "IMAGE": "image",
        "VIDEO": "video",
        "BOOKS": "books",
        "THREADS": "threads",
        "EXTRACT": "extract",
        "CROSSREF": "crossref",
        "GITHUB": "github",
        "WIKI": "wiki",
        "WAYBACK": "wayback",
        # Literatur fetcher tag types (Phase 1.5 → Literatur fetchers)
        "SCOPUS": "scopus",
        "IEEE": "ieee",
        "PUBMED": "pubmed",
        "DBLP": "dblp",
        "DIMENSIONS": "dimensions",
        "CORE": "core",
        "DOAJ": "doaj",
        "PLOS": "plos",
        "OPENAIRE": "openaire",
        "EUROPEPMC": "europepmc",
        "SINTA": "sinta",
        "ZENODO": "zenodo",
        "DATACITE": "datacite",
        "SCIENCEDIRECT": "sciencedirect",
        "OPENALEX": "openalex",
        "SEMANTIC_SCHOLAR": "semantic_scholar",
        "PUBLISHERS": "crossref_publishers",
    }
    tags = []
    for m in _SEARCH_TAG_RE.finditer(text):
        tag_type = m.group(1).upper()
        query = m.group(2).strip()
        tags.append({
            "type": type_map.get(tag_type, "web"),
            "query": query,
            "raw": m.group(0),
        })
    return tags


def strip_search_tags(text: str) -> str:
    """Remove search tags from AI text."""
    return _SEARCH_TAG_RE.sub("", text).strip()


def _literatur_fetch(fetcher_name: str, query: str, limit: int = 10) -> dict[str, Any]:
    """Generic bridge to Literatur fetchers.

    Calls `fetcher.search(client, query, limit)` from tools.Literatur.fetchers
    and converts Paper objects into the dict format expected by Phase 1.5.

    Each Literatur fetcher already handles its own rate limiting, retries,
    API key checks, and error handling.
    """
    try:
        from tools.Literatur.fetchers import ALL as FETCHER_REGISTRY
        from tools.Literatur.http_client import get_client

        fetcher_mod = FETCHER_REGISTRY.get(fetcher_name)
        if not fetcher_mod:
            return {"success": False, "results": [], "error": f"Unknown fetcher: {fetcher_name}"}

        results = []
        with get_client() as client:
            for paper in fetcher_mod.search(client, query, limit=limit):
                results.append({
                    "title": paper.title or "",
                    "authors": paper.authors[:5] if paper.authors else [],
                    "abstract": (paper.abstract or "")[:500],
                    "year": paper.year,
                    "venue": paper.venue or "",
                    "venue_type": paper.venue_type or "",
                    "doi": paper.doi or "",
                    "url": paper.url or "",
                    "pdf_url": paper.pdf_url or "",
                    "citations": paper.citations,
                    "is_open_access": paper.is_open_access,
                    "publisher": paper.publisher or "",
                    "source": paper.source or fetcher_name,
                })

        log.info("literatur_fetch [%s] '%s': %d results", fetcher_name, query[:60], len(results))
        return {"success": len(results) > 0, "results": results, "error": None if results else "No results"}

    except Exception as e:
        log.warning("literatur_fetch [%s] error: %s", fetcher_name, e)
        return {"success": False, "results": [], "error": str(e)}


# Literatur fetcher types that route to _literatur_fetch instead of standalone functions
_LITERATUR_FETCHER_TYPES = {
    "scopus", "ieee", "pubmed", "dblp", "dimensions", "core",
    "doaj", "plos", "openaire", "europepmc", "sinta",
    "zenodo", "datacite", "sciencedirect",
    "openalex", "semantic_scholar", "crossref_publishers",
}


def parse_requested_count(text: str) -> int:
    """Parse the number of papers requested by the user from their message.

    Looks for patterns like "20 referensi", "50 jurnal", "cari 100 paper",
    "20 ya", etc. Returns the requested count, or 0 if not found.
    """
    import re

    # Pattern: number followed by (optional words) + referensi/jurnal/paper/references/literatur/sumber/artikel
    # Also matches "20 ya" at end of message (Indonesian colloquial)
    patterns = [
        # "20 referensi" or "20 jurnal" (number BEFORE keyword)
        r'(\d+)\s*(?:referensi|jurnal|jurnal2|paper|papers|references|literatur|sumber|artikel|ref)\b',
        # "referensi 20" or "jurnal 50" (keyword BEFORE number — Indonesian colloquial)
        r'(?:referensi|jurnal|jurnal2|paper|papers|references|literatur|sumber|artikel|ref)\s*(\d+)',
        # "cari 50" or "cukup 30" or "sebanyak 100"
        r'(?:cari|cukup|sebanyak|jumlah|min(?:imum)?|dengan|buat|bikin|siapkan|sedial[ai]n|berikan)\s*(\d+)',
        # "20 ya" anywhere in message (Indonesian: "20 ya")
        r'(\d+)\s*ya\b',
        # "20 scopus" or "20 terindeks"
        r'(\d+)\s*(?:scopus|indexed|terindeks|terindex)',
    ]

    text_lower = text.lower().strip()
    for pat in patterns:
        m = re.search(pat, text_lower)
        if m:
            count = int(m.group(1))
            if 5 <= count <= 500:  # Reasonable bounds
                return count

    return 0


def execute_tag_search(tag: dict, limit: int = 0) -> dict[str, Any]:
    """Execute a single search tag and return results.

    If limit > 0, use it instead of the default per-fetcher limit.
    """
    t = tag["type"]
    q = tag["query"]

    # Determine fetch limit: use provided limit, or default
    _fetch_limit = limit if limit > 0 else 10
    # For multi-fetcher queries, fetch more per fetcher to ensure enough results
    # Cap at 50 per fetcher to avoid API rate limits
    _fetch_limit = min(_fetch_limit, 50)

    # Route Literatur fetcher types to generic bridge
    if t in _LITERATUR_FETCHER_TYPES:
        return _literatur_fetch(t, q, limit=_fetch_limit)

    dispatch = {
        "web":      lambda: web_search(q, limit=min(_fetch_limit, 15)),
        "news":     lambda: combined_news_search(q, limit=min(_fetch_limit, 15)),
        "arxiv":    lambda: _literatur_fetch("arxiv", q, limit=_fetch_limit),
        "scholar":  lambda: academic_search(q, limit=min(_fetch_limit, 15)),
        "image":    lambda: ddgs_images(q, limit=min(_fetch_limit, 15)),
        "video":    lambda: ddgs_videos(q, limit=min(_fetch_limit, 15)),
        "books":    lambda: ddgs_books(q, limit=min(_fetch_limit, 15)),
        "threads":  lambda: ddgs_threads(q, limit=min(_fetch_limit, 15)),
        "extract":  lambda: ddgs_extract(q),
        "crossref": lambda: _literatur_fetch("crossref", q, limit=_fetch_limit),
        "github":   lambda: github_search(q, limit=min(_fetch_limit, 15)),
        "wiki":     lambda: wikipedia_search(q, limit=min(_fetch_limit, 10)),
        "wayback":  lambda: wayback_search(q),
    }
    fn = dispatch.get(t)
    if fn:
        return fn()
    return {"success": False, "results": [], "error": f"Unknown type: {t}"}


def format_search_results_for_ai(all_results: list[dict]) -> str:
    """Format collected search results into a context block for AI phase 2."""
    if not all_results:
        return ""

    label_map = {
        "web": "Web Search", "news": "Berita Terkini", "arxiv": "ArXiv",
        "scholar": "Academic (OpenAlex/S2)", "image": "Gambar (DDGS)",
        "video": "Video (DDGS)", "books": "Buku (DDGS)",
        "threads": "Forum/Sosial Media",
        "extract": "Konten Halaman", "crossref": "Crossref",
        "github": "GitHub", "wiki": "Wikipedia", "wayback": "Wayback Machine",
        # Literatur fetcher labels
        "scopus": "Scopus (Elsevier)", "ieee": "IEEE Xplore",
        "pubmed": "PubMed", "dblp": "DBLP",
        "dimensions": "Dimensions", "core": "CORE",
        "doaj": "DOAJ", "plos": "PLOS",
        "openaire": "OpenAIRE", "europepmc": "Europe PMC",
        "sinta": "SINTA (Indonesia)", "zenodo": "Zenodo",
        "datacite": "DataCite", "sciencedirect": "ScienceDirect",
        "openalex": "OpenAlex", "semantic_scholar": "Semantic Scholar",
        "crossref_publishers": "Crossref Publishers (Springer/Wiley/Emerald/SSRN/dll)",
    }

    parts = ["## HASIL PENCARIAN REAL (gunakan sebagai referensi NYATA)\n"]
    for block in all_results:
        source_type = block["type"]
        query = block["query"]
        data = block["data"]
        label = label_map.get(source_type, source_type)

        if not data.get("success") or not data.get("results"):
            err = data.get("error", "no results")
            parts.append(f"### {label} untuk \"{query}\" — Tidak ada hasil ({err})\n")
            continue

        items = data["results"]
        parts.append(f"### {label} untuk \"{query}\" — {len(items)} hasil\n")
        parts.extend(_format_result_items(items, source_type))

    parts.append(
        "\n⚠️ REFERENSI DI ATAS ADALAH DATA REAL DARI PENCARIAN. "
        "Gunakan authors, year, title, DOI yang TEPAT dari data di atas saat menyitasi. "
        "JANGAN mengarang referensi yang tidak ada di hasil pencarian.\n"
    )
    return "\n".join(parts)


def format_search_event_for_frontend(tag: dict, data: dict) -> dict:
    """Format a search result as a frontend-friendly event payload."""
    source_type = tag["type"]
    query = tag["query"]
    label_map = {
        "web": "web_search", "news": "news_search", "arxiv": "arxiv_search",
        "scholar": "scholar_search", "image": "image_search", "video": "video_search",
        "books": "books_search",
        "threads": "threads_search", "extract": "extract", "crossref": "crossref_search",
        "github": "github_search", "wiki": "wiki_search", "wayback": "wayback_search",
        # Literatur fetcher labels
        "scopus": "scopus_search", "ieee": "ieee_search",
        "pubmed": "pubmed_search", "dblp": "dblp_search",
        "dimensions": "dimensions_search", "core": "core_search",
        "doaj": "doaj_search", "plos": "plos_search",
        "openaire": "openaire_search", "europepmc": "europepmc_search",
        "sinta": "sinta_search", "zenodo": "zenodo_search",
        "datacite": "datacite_search", "sciencedirect": "sciencedirect_search",
        "openalex": "openalex_search", "semantic_scholar": "semantic_scholar_search",
        "crossref_publishers": "publishers_search",
    }
    label = label_map.get(source_type, source_type)

    items = []
    if data.get("success") and data.get("results"):
        for item in data["results"]:
            items.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "year": item.get("year"),
                "authors": item.get("authors", [])[:3],
                "doi": item.get("doi", ""),
                "venue": item.get("venue", ""),
                "citations": item.get("citations"),
                "date": item.get("date", ""),
                "image_url": item.get("image_url", ""),
                "snippet": (item.get("snippet", item.get("abstract", "")) or "")[:200],
            })

    return {
        "type": label,
        "query": query,
        "icon": "🔍",
        "count": len(items),
        "results": items,
        "error": data.get("error"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SLR trigger
# ═══════════════════════════════════════════════════════════════════════════════

def trigger_slr_job(paper_id: str, user_id: int, query: str, conversation_id: str | None = None) -> dict:
    """Trigger an SLR job via the worker system."""
    try:
        from tools.Literatur.worker import enqueue_slr_job

        job = enqueue_slr_job(
            paper_id=paper_id,
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            sources=None,
            per_source=None,
            top_k=None,
            year_from=None,
            ai_summarize=True,
            ai_model="VIOLA-GENERATE",
        )
        log.info("SLR job triggered: %s for paper=%s query=%s", job.id, paper_id, query[:60])
        return {
            "success": True,
            "job_id": job.id,
            "status": job.status,
        }
    except Exception as e:
        log.exception("Failed to trigger SLR job: %s", e)
        return {"success": False, "error": str(e)}