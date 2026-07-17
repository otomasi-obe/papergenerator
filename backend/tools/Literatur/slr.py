"""SLR + Literature blueprint.

Endpoints:

- POST   /api/papers/<paper_id>/slr/jobs            — enqueue an SLR job
- GET    /api/papers/<paper_id>/slr/jobs            — list this paper's jobs
- GET    /api/slr/jobs/<job_id>                     — job status + result snapshot
- DELETE /api/slr/jobs/<job_id>                     — cancel/delete a job
- GET    /api/papers/<paper_id>/literature          — list LiteratureItem rows
- POST   /api/papers/<paper_id>/literature          — add a manual literature row
- PATCH  /api/papers/<paper_id>/literature/<id>     — edit a row
- DELETE /api/papers/<paper_id>/literature/<id>     — delete a row
- POST   /api/papers/<paper_id>/literature/from-files — import attached PDFs/DOCXs
                                                       as Literature rows
- GET    /api/papers/<paper_id>/literature/pinned   — pinned items formatted
                                                       for prompt injection

The legacy `POST /api/papers/<paper_id>/slr` is now async-only: it enqueues
a job and returns 202 + job_id immediately. Callers must poll
`GET /api/slr/jobs/<job_id>` for status and results.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from io import BytesIO
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import redis
from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import defer

from utils.database.models import LiteratureItem, Paper, PaperFile, SlrJob, db, safe_commit
from tools.editor.utils import PAPER_ID_RE
from tools.Literatur.worker import enqueue_slr_job
from tools.Literatur.fetchers import ALL as FETCHER_ALL
from tools.Literatur.http_client import RateLimiter, get_client
from tools.Literatur.paper import Paper as PaperObj
from tools.Literatur.slrFetch import analyze_keyword, route_fetchers, guess_fetchers
from tools.Literatur.slrSummarize import summarize as summarize_papers
from utils.ai_tools.model_config import get_primary_generate_model

log = logging.getLogger(__name__)
slr_api = Blueprint("slr_api", __name__)


# ━━━ SLR ORCHESTRATOR CONSTANTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAX_WORKERS = 6
# Single fetcher must not exceed this per-source budget.
FETCH_TIMEOUT_SEC = int(os.getenv("SLR_FETCH_TIMEOUT_SEC", "45"))
FETCH_LIMIT_PER_FETCHER = 30
PARTIAL_RESULTS_PREVIEW = 20
REDIS_KEY_PREFIX = "slr_new:"
REDIS_PROGRESS_TTL = 10800  # 3 hours (SLR jobs can take 15+ min)
ANALYZE_TIMEOUT_SEC = int(os.getenv("SLR_ANALYZE_TIMEOUT_SEC", "12"))
_push_count = 0  # throttle counter for DB persistence in _push_progress
_push_count_lock = threading.Lock()  # BUG-B1: protect counter from race under MAX_WORKERS=6 threads

# In-memory job store
_jobs: dict[str, "SLRJob"] = {}
_jobs_lock = threading.Lock()

# Per-fetcher rate limiters
_rate_limiters: dict[str, RateLimiter] = {}

JOB_ID_RE = re.compile(r"^[A-Za-z0-9_]{6,32}$")
FETCHER_ALIASES = {
    "scholar": "semantic_scholar",
    "semantic": "semantic_scholar",
    "semantic-scholar": "semantic_scholar",
    "googlebooks": "google_books",
    "openlibrary": "open_library",
    "science_direct": "sciencedirect",
    "europe_pmc": "europepmc",
}


def _normalize_fetcher_name(name: str, available: set[str] | None = None) -> str | None:
    key = re.sub(r"[^a-z0-9_\-]+", "", (name or "").strip().lower())
    key = FETCHER_ALIASES.get(key, key.replace("-", "_"))
    if available is None:
        available = set(FETCHER_ALL.keys())
    return key if key in available else None


def _parse_inline_fetcher_queries(keyword: str, available: set[str] | None = None) -> tuple[str, dict[str, list[str]]]:
    """Parse `arxiv:robot ieee:agv` into fetcher→queries.

    Text before the first recognized `source:` remains the plain keyword and
    still goes through AI routing. Unknown prefixes are treated as normal text.
    """
    if available is None:
        available = set(FETCHER_ALL.keys())
    matches = []
    for match in re.finditer(r"(?<!\S)([A-Za-z][A-Za-z0-9_\-]{1,40}):", keyword):
        source = _normalize_fetcher_name(match.group(1), available)
        if source:
            matches.append((match.start(), match.end(), source))
    if not matches:
        return keyword.strip(), {}

    plain_parts: list[str] = []
    fetch_map: dict[str, list[str]] = {}
    if matches[0][0] > 0:
        plain_parts.append(keyword[:matches[0][0]].strip())

    for index, (_start, end, source) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(keyword)
        query = keyword[end:next_start].strip()
        if query:
            fetch_map.setdefault(source, []).append(query)

    return " ".join(part for part in plain_parts if part).strip(), fetch_map

# Redis client for cross-process rate limiting + orchestrator job discovery.
# Falls back to in-memory if Redis unavailable.
_redis_client: redis.Redis | None = None
try:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis_client = redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
    )
    _redis_client.ping()
    log.info("Redis connected for SLR rate limiter + orchestrator jobs")
except Exception as e:
    log.warning("Redis unavailable for rate limiter, falling back to in-memory: %s", e)
    _redis_client = None


# ─── Redis-based cross-worker job discovery ───────────────────────────────


def _get_orch_jobs_from_redis(paper_id: str, user_id: int) -> list[dict]:
    """Read in-progress SLR orchestrator jobs from Redis (cross-worker).

    When the job was started on a different gunicorn worker, the in-memory
    _jobs dict on *this* worker is empty. This function reads the job-set
    registered in Redis by SLROrchestrator.start_job() and fetches each
    job's progress blob from Redis.
    """
    if _redis_client is None:
        return []
    try:
        set_key = f"slr_new:paper:{paper_id}:{user_id}"
        job_ids = _redis_client.smembers(set_key)
        results = []
        for jid in job_ids:
            if isinstance(jid, bytes):
                jid = jid.decode("utf-8", "ignore")
            raw = _redis_client.get(f"slr_new:{jid}")
            if raw:
                try:
                    d = json.loads(raw)
                    # Filter by paper_id and user_id (now included in to_dict)
                    if d.get("paper_id") == paper_id and d.get("user_id") == user_id:
                        db_job = db.session.query(SlrJob.status).filter_by(id=jid, paper_id=paper_id, user_id=user_id).first()
                        if not db_job or db_job[0] in ("done", "error", "cancelled"):
                            _redis_client.srem(set_key, jid)
                            _redis_client.delete(f"slr_new:{jid}")
                            continue
                        results.append(d)
                except Exception:
                    pass
        return results
    except Exception:
        return []




_INJECTION_RE = re.compile(
    r"^(ignore|disregard|forget|override|system|instruction|prompt|"
    r"new instructions|you are now|act as|pretend)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)

_MAX_TITLE_LEN = 300
_MAX_ABSTRACT_LEN = 500


def _sanitize_lit_text(text: str | None, max_len: int) -> str:
    """Strip prompt-injection patterns and truncate literature text fields.

    Prevents adversarial titles/abstracts from hijacking LLM prompts via
    instruction-injection when literature items are injected into system
    prompts (BUG-9.1).
    """
    if not text:
        return ""
    # Remove lines that look like instruction injection
    cleaned = _INJECTION_RE.sub("", text)
    # Collapse any resulting blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Truncate to safe length
    return cleaned.strip()[:max_len]


_RELEVANCE_STOPWORDS = {
    "untuk", "dan", "yang", "dengan", "pada", "dalam", "atau", "dari", "ke",
    "di", "ini", "itu", "adalah", "akan", "sudah", "belum", "tidak",
    "bisa", "dapat", "harus", "perlu", "masih", "sangat", "lebih",
    "juga", "hanya", "saja", "lain", "semua", "setiap", "beberapa",
    "seperti", "sebagai", "menjadi", "merupakan", "mengenai", "terkait",
    "hubungan", "kaitan", "berkaitan", "berhubungan",
    # English stopwords
    "the", "and", "for", "with", "from", "into", "a", "an", "of", "to",
    "in", "on", "by", "is", "be", "at", "or", "as", "if", "no", "so",
    "that", "this", "are", "was", "but", "not", "can", "all", "any",
    "has", "its", "may", "who", "which", "their", "how", "what", "why",
    "use", "also", "been", "were", "will", "have", "had", "do", "does",
    "did", "than", "just", "more", "most", "new", "other", "some",
    "such", "only", "over", "when", "where", "each", "about", "after",
    "before", "between", "during", "these", "those",
    # Generic academic/method words (shared with _GENERIC_ACADEMIC_WORDS)
    "system", "sistem", "process", "proses", "model", "data",
    "review", "analysis", "study", "studies", "research", "paper",
    "method", "methods", "metode", "algorithm", "algorithms",
    "framework", "application", "applications", "development",
    "validation", "evaluation", "implementation", "design",
    "performance", "comparison", "perbandingan", "effect", "impact",
    "role", "case", "survey", "survei", "overview", "challenge",
    "challenges", "issue", "issues", "trend", "trends", "advance",
    "advances", "recent", "comprehensive", "state", "art",
    "based", "using", "through", "approach", "pendekatan",
    "technique", "techniques", "teknik", "kultur", "pemanfaatan",
    "penerapan", "kajian", "studi", "analisis", "implementasi",
    "pembangunan", "pengembangan", "penelitian", "metodologi",
    "perancangan", "evaluasi", "validasi", "optimasi", "tinjauan",
    "eksplorasi", "investigasi", "eksperimen", "simulasi", "pemodelan",
    # Engineering/industrial generic terms
    "monitoring", "kontrol", "control", "industrial", "industri",
    # Generic ML/CV words
    "deep", "learning", "machine", "neural", "network", "networks",
    "computer", "vision", "image", "images", "video", "detection",
    "recognition", "classification", "prediction", "predicting",
    "enhanced", "improved", "novel", "automatic", "automated",
    "efficient", "robust", "hybrid", "optimization", "object",
    "feature", "features", "extraction", "segmentation",
    "architecture", "architectures", "transfer", "training",
    "dataset", "datasets", "benchmark", "benchmarks", "accuracy",
    "precision", "scalable", "adaptive", "embedded", "embedding",
    "embeddings",
    # Indonesian academic filler words that appear everywhere and drown relevance
    "metode", "menggunakan", "berbasis", "karakterisasi", "pengembangan",
    "sistem", "aplikasi", "perancangan", "analisis", "studi", "penelitian",
    "implementasi", "desain", "model", "pendekatan", "teknik", "proses",
    "hasil", "data", "informasi", "teknologi", "website", "web", "android",
    "berbasis", "online", "digital", "otomatis", "otomatisasi",
}


def _extract_core_topics(keyword: str, llm_call: Callable | None = None) -> list[str]:
    """Use LLM to extract core topic terms from a research query.

    Returns a list of domain-specific terms that represent the MAIN SUBJECT,
    not generic academic words. Falls back to regex extraction if LLM unavailable.
    """
    if not keyword or not keyword.strip():
        return []

    if llm_call is None:
        # Fallback: regex extraction (old behavior)
        kw = keyword.lower()
        terms = {t for t in re.findall(r"[a-z0-9]+", kw) if len(t) >= 3} - _RELEVANCE_STOPWORDS
        from tools.Literatur.slrFetch import _detect_language, _translate_id_to_en
        if _detect_language(keyword) in ("id", "mixed"):
            en_kw = _translate_id_to_en(keyword)
            en_terms = {t for t in re.findall(r"[a-z0-9]+", en_kw.lower()) if len(t) >= 3} - _RELEVANCE_STOPWORDS
            terms |= en_terms
        return list(terms)

    system_prompt = (
        "You are a research topic analyzer. Given a research title/query, extract ONLY the core domain-specific terms "
        "that define the MAIN SUBJECT of the research. Exclude generic academic words like 'method', 'analysis', 'system', "
        "'development', 'design', 'based', 'using', etc.\n\n"
        "Rules:\n"
        "1. Extract 3-8 core terms that are UNIQUE to this specific research domain\n"
        "2. Include BOTH the original language terms AND their English equivalents\n"
        "3. A paper is relevant ONLY if it discusses these specific topics\n"
        "4. Think about what makes this research DIFFERENT from unrelated papers\n"
        "5. Focus on NOUNS and domain jargon, not verbs or methodology words\n"
        "6. Do NOT split compound terms that only make sense together (e.g. keep 'space telescope' as one term, "
        "do NOT extract 'space' or 'luar angkasa' alone — they are too generic without the full phrase)\n"
        "7. Each term should be specific enough that finding it in a paper title/abstract strongly suggests the paper "
        "is about your research topic. If a term could appear in many unrelated fields, it's too generic\n\n"
        "Example:\n"
        "Query: 'Karakterisasi Eksoplanet Berbasis Metode Transit menggunakan Data Fotometri Teleskop Luar Angkasa'\n"
        "Core terms: exoplanet, eksoplanet, transit photometry, fotometri transit, planetary transit, "
        "planetary atmosphere, atmosfer planet\n"
        "NOT: karakterisasi, metode, berbasis, menggunakan, data, luar, angkasa, space, telescope\n\n"
        "Example:\n"
        "Query: 'Pengaruh Pemberian Pupuk Organik terhadap Pertumbuhan Tanaman Padi'\n"
        "Core terms: pupuk organik, organic fertilizer, padi, rice, plant growth, pertumbuhan tanaman\n"
        "NOT: pengaruh, pemberian, terhadap, tanaman (too generic alone)\n\n"
        "Example:\n"
        "Query: 'Optimasi SCADA untuk Monitoring Distribusi Air Bersih'\n"
        "Core terms: scada, water distribution, distribusi air, supervisory control, clean water, air bersih\n"
        "NOT: optimasi, monitoring, untuk, sistem\n\n"
        "Return ONLY a JSON object: {\"core_terms\": [\"term1\", \"term2\", ...]}\n"
        "No explanation, no markdown, just the JSON."
    )

    try:
        raw = llm_call(system_prompt, f"Query: {keyword}")
        # Parse JSON from response
        data = _parse_core_terms_json(raw)
        terms = data.get("core_terms", [])
        if isinstance(terms, list) and len(terms) >= 2:
            # Lowercase and deduplicate
            clean = list({t.lower().strip() for t in terms if isinstance(t, str) and len(t.strip()) >= 2})
            log.info("LLM extracted %d core terms for '%s': %s", len(clean), keyword[:50], clean)
            return clean
    except Exception as exc:
        log.warning("_extract_core_topics LLM failed (%s), using regex fallback", exc)

    # Fallback
    return _extract_core_topics(keyword, llm_call=None)


def _parse_core_terms_json(text: str) -> dict:
    """Extract JSON from LLM response, tolerating markdown fences."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _filter_relevant_papers(keyword: str, papers: list[Any], core_terms: list[str] | None = None) -> list[Any]:
    """Drop clearly off-topic search hits before ranking/saving.

    When core_terms (from LLM) are provided, uses semantic matching against
    domain-specific terms. Falls back to regex when core_terms is empty.
    """
    if not core_terms:
        # Legacy fallback: regex extraction
        kw = (keyword or "").lower()
        required = {t for t in re.findall(r"[a-z0-9]+", kw) if len(t) >= 3} - _RELEVANCE_STOPWORDS
        from tools.Literatur.slrFetch import _detect_language, _translate_id_to_en
        if _detect_language(keyword) in ("id", "mixed"):
            en_kw = _translate_id_to_en(keyword)
            en_terms = {t for t in re.findall(r"[a-z0-9]+", en_kw.lower()) if len(t) >= 3} - _RELEVANCE_STOPWORDS
            required |= en_terms
        core_terms = list(required)

    if not core_terms:
        return papers  # no terms = keep all

    # Separate single-word terms from multi-word phrases
    single_terms = set()
    phrase_terms = []
    for t in core_terms:
        t = t.lower().strip()
        words = t.split()
        if len(words) > 1:
            phrase_terms.append(t)
        else:
            if len(t) >= 2:
                single_terms.add(t)

    # Domain anchors for common engineering/control queries
    anchors = {"scada", "iot", "plc", "hmi", "supervisory", "automation", "sensor", "actuator"}
    active_anchors = single_terms & anchors

    # Threshold: LLM terms are already domain-specific → 1 hit is enough
    # Regex fallback terms are noisy → need min 3 (handled in fallback path)
    min_hits = 1 if core_terms is not None else max(1, min(3, len(single_terms) + len(phrase_terms)))

    kept: list[Paper] = []
    for p in papers:
        hay = " ".join([
            getattr(p, "title", "") or "",
            getattr(p, "abstract", "") or "",
            getattr(p, "venue", "") or "",
        ]).lower()
        if not hay:
            continue
        if active_anchors and not any(a in hay for a in active_anchors):
            continue

        # Count single-word term matches
        single_hits = sum(1 for t in single_terms if t in hay)
        # Count phrase matches (each phrase = 1 hit, independent of singles)
        phrase_hits = sum(1 for pt in phrase_terms if pt in hay)
        total_score = single_hits + phrase_hits

        if total_score >= min_hits:
            kept.append(p)
    return kept


# ─── Pinned literature helper ────────────────────────────────────────────


def get_pinned_literature(paper_id: str, user_id: int, max_items: int = 10) -> str:
    """Ambil literature yang di-check user, format sebagai blok teks utk
    injeksi ke system prompt (chat / paperfull).

    HANYA return item dengan is_checked=True (user klik check).
    Returns empty string kalau tidak ada checked item.
    """
    if not paper_id or not user_id:
        return ""
    try:
        items = (
            db.session.query(LiteratureItem)
            .filter_by(paper_id=paper_id, user_id=user_id, is_checked=True)
            .order_by(LiteratureItem.pinned.desc(), LiteratureItem.score_total.desc())
            .limit(max_items)
            .all()
        )
        if not items:
            return ""

        lines: list[str] = []
        for i, it in enumerate(items, 1):
            authors_list = it.authors or []
            authors = ", ".join(authors_list[:3])
            if len(authors_list) > 3:
                authors += " et al."

            header_parts = [f"[{i}] {_sanitize_lit_text(it.title, _MAX_TITLE_LEN) or 'Untitled'}"]
            if authors:
                header_parts.append(f"— {authors}")
            if it.year:
                header_parts.append(f"({it.year})")
            lines.append(" ".join(header_parts))

            if it.doi:
                lines.append(f"    DOI: {it.doi}")
            elif it.url:
                lines.append(f"    URL: {it.url}")

            # Prefer summary (AI-generated) over raw abstract
            description = _sanitize_lit_text(it.summary or it.abstract, _MAX_ABSTRACT_LEN)
            if description:
                lines.append(f"    {description}")
            lines.append("")  # blank separator

        return "\n".join(lines).strip()
    except Exception as e:
        log.warning("[get_pinned_literature] failed for paper=%s: %s", paper_id, e)
        return ""

_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s]+$")
_URL_RE = re.compile(r"^(https?://|/)", re.IGNORECASE)

_VALID_SOURCE_KINDS = {"slr", "manual", "file"}
_VALID_JOB_STATUSES = {"queued", "running", "done", "error", "cancelled"}

# Rate limiter: Redis-backed (cross-process) with in-memory fallback.
# Keyed by (user_id, endpoint). Sliding window: count requests in last N seconds.
_RATE_BUCKETS: defaultdict[str, list[float]] = defaultdict(list)
_RATE_LOCK = threading.Lock()
_RATE_WINDOW_SEC = 60.0
_RATE_MAX_REQUESTS = 10

# Long-poll concurrency cap: max simultaneous long-poll connections.
# Prevents thread starvation — with 128 gunicorn threads, cap at 80.
_LONGPOLL_SEMAPHORE = threading.Semaphore(80)


def _check_rate_limit(
    user_id: int,
    endpoint: str,
    max_requests: int = _RATE_MAX_REQUESTS,
    window_sec: float = _RATE_WINDOW_SEC,
):
    """Cross-process rate limit via Redis sorted set. Falls back to in-memory."""
    key = f"rl:{user_id}:{endpoint}"
    now = time.time()

    if _redis_client:
        try:
            pipe = _redis_client.pipeline()
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, now - window_sec)
            # Count remaining
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {f"{now}": now})
            # Set expiry on key
            pipe.expire(key, int(window_sec) + 5)
            results = pipe.execute()
            count = results[1]  # zcard result

            if count >= max_requests:
                # Over limit — remove the request we just added
                _redis_client.zrem(key, f"{now}")
                # Calculate retry_after from oldest entry
                oldest = _redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = max(1, int(window_sec - (now - oldest[0][1])) + 1)
                else:
                    retry_after = int(window_sec)
                return False, retry_after
            return True, 0
        except Exception as e:
            log.warning("Redis rate limiter failed, falling back to in-memory: %s", e)
            # Fall through to in-memory

    # In-memory fallback: rate limit via thread-safe sliding window per worker.
    # Multi-worker: each worker enforces independently (per-worker limit = N× total for N workers).
    # This is acceptable for SLR since user typically single-threaded, and 10 jobs/min per worker is loose.
    with _RATE_LOCK:
        # Remove expired entries
        _RATE_BUCKETS[key] = [ts for ts in _RATE_BUCKETS[key] if now - ts < window_sec]
        count = len(_RATE_BUCKETS[key])
        
        if count >= max_requests:
            # Over limit
            if _RATE_BUCKETS[key]:
                oldest_ts = _RATE_BUCKETS[key][0]
                retry_after = max(1, int(window_sec - (now - oldest_ts)) + 1)
            else:
                retry_after = int(window_sec)
            return False, retry_after
        
        # Add current request
        _RATE_BUCKETS[key].append(now)
        return True, 0


def _err(message: str, code: str, status: int):
    """Build a JSON error response with stable `code` for frontend i18n."""
    return jsonify({"error": message, "code": code}), status


def _validate_year(value):
    """Return (year_or_None, err_response_or_None).

    None / "" -> (None, None) (unset is OK).
    Anything else must parse to int and lie in [1500, current_year + 1].
    """
    if value is None or value == "":
        return None, None
    try:
        y = int(value)
    except (TypeError, ValueError):
        return None, _err(f"invalid year: {value!r}", "YEAR_INVALID", 400)
    current_year = datetime.now(timezone.utc).year
    if y < 1500 or y > current_year + 1:
        return None, _err(
            f"year out of range: must be between 1500 and {current_year + 1}",
            "YEAR_OUT_OF_RANGE",
            400,
        )
    return y, None


def _normalize_doi(value):
    if not value:
        return None
    v = str(value).strip().lower()
    v = v.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    return v if _DOI_RE.match(v) else None


def _safe_url(value):
    if not value:
        return None
    v = str(value).strip()
    return v if _URL_RE.match(v) else None


def _current_user_id() -> int | None:
    raw = get_jwt_identity()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _paper_or_404(paper_id: str, user_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return None, _err("Invalid paper id", "PAPER_ID_INVALID", 400)
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return None, _err("Paper not found", "PAPER_NOT_FOUND", 404)
    return paper, None


# ─── SLR JOBS ─────────────────────────────────────────────────────────────


@slr_api.route("/api/papers/<paper_id>/slr/jobs", methods=["POST"])
@jwt_required()
def create_slr_job(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    # ── Quota gate ────────────────────────────────────────────────────
    from utils.quota import quota_exceeded
    exceeded, info = quota_exceeded(user_id)
    if exceeded:
        return jsonify(info), 429

    # F-28: simple per-user in-memory rate limit (10 jobs/minute).
    ok, retry_after = _check_rate_limit(user_id, "create_slr_job")
    if not ok:
        if retry_after == -1:
            return _err("Rate limiting unavailable, try again later", "RATE_LIMIT_UNAVAILABLE", 503)
        return (
            jsonify(
                {
                    "error": "Rate limit: max 10 SLR jobs/minute",
                    "code": "RATE_LIMITED",
                    "retry_after": retry_after,
                }
            ),
            429,
        )

    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    query = (body.get("query") or body.get("topic") or "").strip()
    if not query:
        return _err("query is required", "QUERY_REQUIRED", 400)
    plain_query, inline_fetch_map = _parse_inline_fetcher_queries(query)

    sources = body.get("sources") or None
    if sources is not None and not isinstance(sources, list):
        return _err("sources must be a list", "SOURCES_INVALID", 400)

    per_source = _safe_per_source(body.get("per_source"))
    top_k = _safe_top_k(body.get("top_k"))

    # Per fetcher = topK × 5. More candidates = better ranking. Return capped to topK.
    # Example: topK=100, 3 fetchers → per_source=500, total=1500 fetched, return 100.
    if not body.get("per_source"):
        per_source = top_k * 5

    year_from, year_err = _validate_year(body.get("year_from"))
    if year_err:
        return year_err

    year_to, year_to_err = _validate_year(body.get("year_to"))
    if year_to_err:
        return year_to_err

    # Validate year range
    if year_from and year_to and year_to < year_from:
        return _err("year_to must be >= year_from", "YEAR_RANGE_INVALID", 400)

    ai_summarize = bool(body.get("ai_summarize", True))
    ai_model = (body.get("ai_model") or get_primary_generate_model()).strip()
    if ai_model not in {"VIOLA-CHAT", "VIOLA-GENERATE"}:
        ai_model = get_primary_generate_model()

    conv_id = body.get("conversation_id") or None

    log.info(
        "slr.create user=%d paper=%s query=%s top_k=%d ai_model=%s",
        user_id,
        paper_id,
        query[:60],
        top_k,
        ai_model,
    )

    # New SLR system (v3) — delegates to orchestrator with parallel fetchers
    job_id = _orchestrator.start_job(
        paper_id=paper_id,
        keyword=query,
        top_n=top_k,
        user_id=user_id,
        sources=sources,
        year_from=year_from,
        year_to=year_to,
        ai_summarize=ai_summarize,
        per_source=per_source,
        inline_fetch_map=inline_fetch_map or None,
        plain_keyword=plain_query or None,
    )

    return jsonify({
        "id": job_id,
        "job_id": job_id,
        "status": "started",
        "poll_url": f"/api/slr/jobs/{job_id}",
    }), 202


@slr_api.route("/api/papers/<paper_id>/slr/jobs", methods=["GET"])
@jwt_required()
def list_slr_jobs(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    # Optional filters: ?status=queued,running  ?limit=<n>
    status_param = (request.args.get("status") or "").strip()
    statuses = None
    if status_param:
        requested = {s.strip() for s in status_param.split(",") if s.strip()}
        invalid = requested - _VALID_JOB_STATUSES
        if invalid:
            return _err(
                f"invalid status value(s): {sorted(invalid)}",
                "STATUS_INVALID",
                400,
            )
        statuses = requested

    try:
        limit = int(request.args.get("limit", 30))
    except (TypeError, ValueError):
        limit = 30
    limit = max(1, min(limit, 100))

    try:
        # Defer the large `result` JSON column so each poll only ships the
        # status fields. Callers that need the full payload hit
        # `GET /api/slr/jobs/<job_id>?include_result=true`.
        q = (
            db.session.query(SlrJob)
            .options(defer(SlrJob.result))
            .filter_by(paper_id=paper_id, user_id=user_id)
        )
        if statuses:
            q = q.filter(SlrJob.status.in_(statuses))
        jobs = q.order_by(SlrJob.queued_at.desc()).limit(limit).all()
        result = [j.to_dict() for j in jobs]

        # Also include new orchestrator jobs (Redis-based, cross-worker) for this paper
        try:
            orch_jobs = _get_orch_jobs_from_redis(paper_id, user_id)
            for job in orch_jobs:
                if statuses is None or job.get("status") in statuses:
                    result.append(job)
        except Exception:
            pass

        return jsonify(result)
    except (OperationalError, DBAPIError) as e:
        # Postgres busy / lock timeout / connection blip → tell the frontend
        # to back off and retry instead of bubbling up as a 500/524.
        db.session.rollback()
        log.warning("slr.list_jobs DB busy paper=%s: %s", paper_id, e)
        return jsonify({"error": "DB busy, retry", "code": "DB_BUSY"}), 503


@slr_api.route("/api/slr/jobs/<job_id>/stream", methods=["GET"])
def stream_slr_job(job_id: str):
    """SSE stream for SLR job progress. Real-time updates without polling.
    
    Accepts token via query param (EventSource can't send headers).
    Returns:
        event: snapshot   — initial job state
        event: progress   — progress updates (stage, percent, papers_count)
        event: partial    — incremental paper results as fetchers complete
        event: done       — job finished (success/error/cancelled)
    """
    # SECURITY: Prefer httpOnly cookie auth — query param token is visible in logs/URLs.
    # EventSource sends cookies automatically on same-origin requests.
    # Only use query param as last-resort fallback for legacy clients.
    token = request.args.get('token')
    user_id = None

    if token:
        try:
            from flask_jwt_extended import decode_token
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
        except Exception:
            pass

    # Cookie auth is preferred over query param
    if not user_id:
        cookie_token = request.cookies.get('access_token_cookie')
        if cookie_token:
            try:
                from flask_jwt_extended import decode_token
                decoded = decode_token(cookie_token)
                user_id = int(decoded['sub'])
            except Exception:
                pass

    if not user_id:
        try:
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
        except Exception:
            pass

    if not user_id:
        return jsonify({"error": "Missing authorization", "code": "UNAUTHORIZED"}), 401
    
    # Verify job ownership (check both orchestrator in-memory and DB)
    job_dict = _orchestrator.get_job(job_id)
    if not job_dict or job_dict.get('user_id') != user_id:
        # Try DB fallback
        db_job = db.session.query(SlrJob).filter_by(id=job_id, user_id=user_id).first()
        if not db_job:
            return jsonify({"error": "Job not found", "code": "JOB_NOT_FOUND"}), 404
    
    def gen():
        # Snapshot: send current state immediately
        if job_dict:
            snap = {
                "stage": job_dict.get("stage", "queued"),
                "percent": int(job_dict.get("progress_pct", 0)),
                "status": job_dict.get("status", "running"),
                "papers_count": job_dict.get("papers_fetched", 0),
                "eta_seconds": job_dict.get("eta_seconds"),
                "eta_display": job_dict.get("eta_display"),
            }
        else:
            snap = {"stage": "queued", "percent": 0, "status": "running", "papers_count": 0, "eta_seconds": None, "eta_display": ""}
        yield f"event: snapshot\ndata: {json.dumps(snap)}\n\n"
        
        # If already terminal, send done and exit
        if job_dict and job_dict.get("status") in ("done", "error", "cancelled"):
            payload = {
                "status": job_dict["status"],
                "stage_detail": job_dict.get("stage_detail") or job_dict.get("progress_message") or "",
            }
            yield f"event: done\ndata: {json.dumps(payload)}\n\n"
            return
        
        # Subscribe to Redis pubsub channel for this job
        if _redis_client is None:
            yield ": no redis\n\n"
            return
        
        pubsub = _redis_client.pubsub(ignore_subscribe_messages=True)
        channel = f"slr_progress:{job_id}"
        pubsub.subscribe(channel)
        
        try:
            t0 = time.time()
            last_ping = t0
            while True:
                msg = pubsub.get_message(timeout=1.0)
                if msg and msg.get("type") == "message":
                    data = msg.get("data") or "{}"
                    # Parse to check if terminal
                    try:
                        parsed = json.loads(data)
                        event_type = parsed.get("event_type", "progress")
                        if event_type == "partial":
                            yield f"event: partial\ndata: {data}\n\n"
                        else:
                            yield f"event: progress\ndata: {data}\n\n"
                        
                        # Check if done
                        if parsed.get("status") in ("done", "error", "cancelled"):
                            payload = {
                                "status": parsed.get("status"),
                                "stage_detail": parsed.get("stage_detail") or parsed.get("progress_message") or "",
                            }
                            yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                            break
                    except Exception:
                        yield f"event: progress\ndata: {data}\n\n"
                
                # Heartbeat every 15s
                if time.time() - last_ping > 15:
                    yield ": ping\n\n"
                    last_ping = time.time()
                
                # Hard cap 20 min per stream
                if time.time() - t0 > 1200:
                    break
        finally:
            try:
                pubsub.unsubscribe()
                pubsub.close()
            except Exception:
                pass
    
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    from flask import Response, stream_with_context
    return Response(stream_with_context(gen()), headers=headers)


@slr_api.route("/api/papers/<paper_id>/slr/jobs/wait", methods=["GET"])
@jwt_required()
def wait_slr_jobs(paper_id: str):
    """Long-poll for SlrJob changes for this paper.

    Holds the connection for up to 10 s, returning as soon as `max(updated_at)`
    moves past the caller's `?after=<unix_ts>` cursor. Frontend uses this to
    avoid hammering the DB with 2-3 s polls — and to dodge the proxy 524 the
    cheap polls were causing under load.

    Concurrency cap: semaphore limits simultaneous long-pollers to 80 (out of
    128 gunicorn threads). Excess clients get immediate 503 with fallback to
    short-poll. Prevents thread starvation under heavy concurrent use.
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    # Semaphore: if all slots taken, return immediately — client falls back to short-poll
    acquired = _LONGPOLL_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        return jsonify({"jobs": [], "ts": 0, "noop": True, "busy": True}), 503
    try:
        return _wait_slr_jobs_inner(paper_id, user_id)
    finally:
        _LONGPOLL_SEMAPHORE.release()


def _wait_slr_jobs_inner(paper_id: str, user_id: int):
    """Inner long-poll logic after semaphore is acquired."""
    try:
        after = float(request.args.get("after", "0"))
    except (TypeError, ValueError):
        after = 0.0

    deadline = time.monotonic() + 10.0
    poll_step = 2.0
    try:
        while time.monotonic() < deadline:
            try:
                latest = (
                    db.session.query(db.func.max(SlrJob.updated_at))
                    .filter_by(paper_id=paper_id, user_id=user_id)
                    .scalar()
                )
            except (OperationalError, DBAPIError) as e:
                db.session.rollback()
                log.warning("slr.wait_jobs probe DB busy paper=%s: %s", paper_id, e)
                return jsonify({"error": "DB busy, retry", "code": "DB_BUSY"}), 503

            ts = latest.timestamp() if latest else 0.0

            # Check new orchestrator jobs too (Redis-based, cross-worker)
            orch_jobs = []
            try:
                orch_jobs = _get_orch_jobs_from_redis(paper_id, user_id)
            except Exception:
                pass

            if ts > after or (orch_jobs and len(orch_jobs) > 0):
                jobs = (
                    db.session.query(SlrJob)
                    .options(defer(SlrJob.result))
                    .filter_by(paper_id=paper_id, user_id=user_id)
                    .order_by(SlrJob.queued_at.desc())
                    .limit(30)
                    .all()
                )
                # Close the read txn so we don't pin a snapshot across the
                # caller's polling cycle. Rollback is enough for read-only.
                db.session.rollback()

                job_dicts = [j.to_dict() for j in jobs]
                # Add orchestrator jobs (Redis-based, cross-worker)
                job_dicts.extend(orch_jobs)

                return jsonify(
                    {
                        "jobs": job_dicts,
                        "ts": ts,
                    }
                )
            # Release the implicit read txn between polls so other writers
            # (the worker pool) don't block waiting on us.
            db.session.rollback()
            time.sleep(poll_step)
    except (OperationalError, DBAPIError) as e:
        db.session.rollback()
        log.warning("slr.wait_jobs DB busy paper=%s: %s", paper_id, e)
        return jsonify({"error": "DB busy, retry", "code": "DB_BUSY"}), 503

    return jsonify({"jobs": [], "ts": after, "noop": True})




# ─── LITERATURE ITEMS ─────────────────────────────────────────────────────


@slr_api.route("/api/papers/<paper_id>/literature", methods=["GET"])
@jwt_required()
def list_literature(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    try:
        from tools.Literatur.text_cleaner import detect_mojibake
        base_q = (
            db.session.query(LiteratureItem)
            .filter_by(paper_id=paper_id, user_id=user_id)
        )

        # Fetch ordered results
        raw_items = base_q.order_by(
            LiteratureItem.pinned.desc(),
            LiteratureItem.score_total.desc(),
            LiteratureItem.created_at.desc(),
        ).all()

        # ── Post-filter: demote mojibake items ──
        # Items with garbled text get pushed to the bottom regardless
        # of their stored score. Prevents old mojibake data from
        # appearing at the top after scoring changes.
        clean_items = []
        mojibake_items = []
        for item in raw_items:
            t_mojo = detect_mojibake(item.title)
            a_mojo = detect_mojibake(item.abstract)
            if max(t_mojo, a_mojo) > 0.3:
                mojibake_items.append(item)
            else:
                clean_items.append(item)
        items_sorted = clean_items + mojibake_items

        # Backward-compat: only switch to paginated wrapper when caller actually
        # passes `page` or `page_size`. Otherwise return the original flat list.
        page_arg = request.args.get("page")
        size_arg = request.args.get("page_size")
        if page_arg is None and size_arg is None:
            # Return all items — frontend handles client-side pagination (pageSize 100/200)
            return jsonify([i.to_dict() for i in items_sorted])

        try:
            page = int(page_arg) if page_arg is not None else 1
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(size_arg) if size_arg is not None else 50
        except (TypeError, ValueError):
            page_size = 50
        page = max(1, page)
        page_size = max(1, min(page_size, 500))

        total = len(items_sorted)
        start = (page - 1) * page_size
        items_page = items_sorted[start:start + page_size]
        return jsonify(
            {
                "items": [i.to_dict() for i in items_page],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        )
    except Exception as e:
        log.exception("list_literature failed for paper_id=%s", paper_id)
        return _err(f"Gagal memuat literatur: {e}", "LITERATURE_LOAD_ERROR", 500)


@slr_api.route("/api/papers/<paper_id>/literature", methods=["POST"])
@jwt_required()
def create_literature(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        return _err("title is required", "TITLE_REQUIRED", 400)

    raw_doi = body.get("doi")
    if raw_doi:
        doi_norm = _normalize_doi(raw_doi)
        if doi_norm is None:
            return _err(f"invalid doi: {raw_doi!r}", "DOI_INVALID", 400)
    else:
        doi_norm = None

    # Dedup: same DOI on the same paper can't exist twice (DB has a partial
    # unique index but we want a friendly 409 instead of an IntegrityError).
    if doi_norm is not None:
        existing = (
            db.session.query(LiteratureItem).filter_by(paper_id=paper_id, doi=doi_norm).first()
        )
        if existing is not None:
            return (
                jsonify(
                    {
                        "error": f"literature with DOI {doi_norm} already exists",
                        "code": "DOI_DUPLICATE",
                        "existing_id": existing.id,
                    }
                ),
                409,
            )

    # Dedup by normalized title (catches papers without DOI)
    if title:
        title_norm = re.sub(r'[^a-z0-9]+', '', title.lower())[:500]
        if title_norm:
            existing_title = (
                db.session.query(LiteratureItem)
                .filter_by(paper_id=paper_id, title_norm=title_norm)
                .first()
            )
            if existing_title is not None:
                # Title match exists — if no DOI to distinguish, reject as duplicate
                # If caller provided a DOI and the existing row has no DOI, still reject
                return (
                    jsonify(
                        {
                            "error": f"literature with same title already exists (id={existing_title.id})",
                            "code": "TITLE_DUPLICATE",
                            "existing_id": existing_title.id,
                        }
                    ),
                    409,
                )
    else:
        title_norm = ""

    raw_url = body.get("url")
    if raw_url:
        url_norm = _safe_url(raw_url)
        if url_norm is None:
            return _err(
                "invalid url: must be http(s):// or relative path",
                "URL_INVALID",
                400,
            )
    else:
        url_norm = None

    year_value, year_err = _validate_year(body.get("year"))
    if year_err:
        return year_err

    source_kind = (body.get("source_kind") or "manual")[:20]
    if source_kind not in _VALID_SOURCE_KINDS:
        return _err(
            f"invalid source_kind: {source_kind!r}; must be one of "
            f"{sorted(_VALID_SOURCE_KINDS)}",
            "SOURCE_KIND_INVALID",
            400,
        )

    raw_pdf_url = body.get("pdf_url")
    pdf_url_norm = _safe_url(raw_pdf_url) if raw_pdf_url else None

    item = LiteratureItem(
        paper_id=paper_id,
        user_id=user_id,
        source_kind=source_kind,
        source=(body.get("source") or "")[:40],
        title=title[:1000],
        title_norm=title_norm,
        authors=body.get("authors") or [],
        year=year_value,
        venue=(body.get("venue") or "")[:500],
        publisher=(body.get("publisher") or "")[:500],
        doi=doi_norm,
        url=url_norm,
        pdf_url=pdf_url_norm,
        abstract=body.get("abstract") or "",
        summary=body.get("summary") or "",
        citations=_safe_int(body.get("citations")),
        score_total=_safe_float(body.get("score_total")),
        score_breakdown=body.get("score_breakdown") or {},
        must_read=bool(body.get("must_read", False)),
        is_relevant=bool(body.get("is_relevant", True)),
        notes=(body.get("notes") or ""),
        pinned=bool(body.get("pinned", False)),
    )
    db.session.add(item)
    safe_commit()
    return jsonify(item.to_dict()), 201


@slr_api.route("/api/papers/<paper_id>/literature/<int:item_id>", methods=["PATCH"])
@jwt_required()
def update_literature(paper_id: str, item_id: int):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    item = (
        db.session.query(LiteratureItem)
        .filter_by(id=item_id, paper_id=paper_id, user_id=user_id)
        .first()
    )
    if not item:
        return _err("Literature item not found", "LITERATURE_NOT_FOUND", 404)

    body = request.get_json(silent=True) or {}
    editable = {
        "title",
        "authors",
        "year",
        "venue",
        "publisher",
        "doi",
        "url",
        "pdf_url",
        "abstract",
        "summary",
        "citations",
        "must_read",
        "is_relevant",
        "notes",
        "pinned",
        "is_checked",
        "source",
        "source_kind",
    }
    for k, v in body.items():
        if k not in editable:
            continue
        if k == "year":
            year_value, year_err = _validate_year(v)
            if year_err:
                return year_err
            v = year_value
        elif k == "citations":
            v = _safe_int(v)
        elif k in ("must_read", "is_relevant", "pinned", "is_checked"):
            v = bool(v)
        elif k == "authors":
            if not isinstance(v, list):
                continue
        elif k == "source_kind":
            if v not in _VALID_SOURCE_KINDS:
                return _err(
                    f"invalid source_kind: {v!r}; must be one of " f"{sorted(_VALID_SOURCE_KINDS)}",
                    "SOURCE_KIND_INVALID",
                    400,
                )
        elif k == "doi":
            if v in (None, ""):
                v = None
            else:
                normalized = _normalize_doi(v)
                if normalized is None:
                    return _err(f"invalid doi: {v!r}", "DOI_INVALID", 400)
                v = normalized
        elif k == "url":
            if v in (None, ""):
                v = None
            else:
                safe = _safe_url(v)
                if safe is None:
                    return _err(
                        "invalid url: must be http(s):// or relative path",
                        "URL_INVALID",
                        400,
                    )
                v = safe
        elif k == "pdf_url":
            if v in (None, ""):
                v = None
            else:
                safe = _safe_url(v)
                if safe is None:
                    return _err(
                        "invalid pdf_url: must be http(s):// or relative path",
                        "PDF_URL_INVALID",
                        400,
                    )
                v = safe
        setattr(item, k, v)
    safe_commit()
    return jsonify(item.to_dict())


@slr_api.route("/api/papers/<paper_id>/literature/<int:item_id>", methods=["DELETE"])
@jwt_required()
def delete_literature(paper_id: str, item_id: int):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    item = (
        db.session.query(LiteratureItem)
        .filter_by(id=item_id, paper_id=paper_id, user_id=user_id)
        .first()
    )
    if not item:
        return _err("Literature item not found", "LITERATURE_NOT_FOUND", 404)
    db.session.delete(item)
    safe_commit()
    return jsonify({"ok": True})


@slr_api.route("/api/papers/<paper_id>/literature/clear", methods=["POST"])
@jwt_required()
def clear_literature(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    try:
        deleted = (
            db.session.query(LiteratureItem)
            .filter(
                LiteratureItem.paper_id == paper_id,
                LiteratureItem.user_id == user_id,
            )
            .delete(synchronize_session=False)
        )
        safe_commit()
        log.info("slr.literature.clear user=%d paper=%s deleted=%d", user_id, paper_id, deleted)
        return jsonify({"deleted": deleted})
    except Exception:
        db.session.rollback()
        log.exception("slr.literature.clear failed paper=%s", paper_id)
        return _err("clear literature failed", "LITERATURE_CLEAR_FAILED", 500)


@slr_api.route("/api/papers/<paper_id>/literature/bulk-delete", methods=["POST"])
@jwt_required()
def bulk_delete_literature(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    raw_ids = body.get("ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return _err("ids must be a non-empty list", "IDS_REQUIRED", 400)
    ids: list[int] = []
    for v in raw_ids:
        try:
            ids.append(int(v))
        except (TypeError, ValueError):
            return _err(f"invalid id: {v!r}", "IDS_INVALID", 400)

    log.info("slr.literature.bulk_delete user=%d paper=%s ids=%d", user_id, paper_id, len(ids))

    rows = (
        db.session.query(LiteratureItem)
        .filter(
            LiteratureItem.paper_id == paper_id,
            LiteratureItem.user_id == user_id,
            LiteratureItem.id.in_(ids),
        )
        .all()
    )
    deleted = 0
    try:
        for r in rows:
            db.session.delete(r)
            deleted += 1
        safe_commit()
    except Exception:
        db.session.rollback()
        log.exception("slr.literature.bulk_delete commit failed paper=%s", paper_id)
        return _err("bulk delete failed", "LITERATURE_BULK_DELETE_FAILED", 500)
    return jsonify({"deleted": deleted})


@slr_api.route("/api/papers/<paper_id>/literature/bulk-patch", methods=["POST"])
@jwt_required()
def bulk_patch_literature(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    raw_ids = body.get("ids")
    patch = body.get("patch") or {}
    if not isinstance(raw_ids, list) or not raw_ids:
        return _err("ids must be a non-empty list", "IDS_REQUIRED", 400)
    if not isinstance(patch, dict) or not patch:
        return _err("patch must be a non-empty object", "PATCH_REQUIRED", 400)

    ids: list[int] = []
    for v in raw_ids:
        try:
            ids.append(int(v))
        except (TypeError, ValueError):
            return _err(f"invalid id: {v!r}", "IDS_INVALID", 400)

    allowed_fields = {"pinned", "must_read", "is_relevant", "is_checked"}
    invalid_fields = set(patch.keys()) - allowed_fields
    if invalid_fields:
        return _err(
            f"invalid patch field(s): {sorted(invalid_fields)}; "
            f"only {sorted(allowed_fields)} are allowed",
            "PATCH_FIELD_INVALID",
            400,
        )
    normalized_patch = {k: bool(v) for k, v in patch.items()}

    log.info(
        "slr.literature.bulk_patch user=%d paper=%s ids=%d patch=%s",
        user_id,
        paper_id,
        len(ids),
        normalized_patch,
    )

    try:
        updated = (
            db.session.query(LiteratureItem)
            .filter(
                LiteratureItem.paper_id == paper_id,
                LiteratureItem.user_id == user_id,
                LiteratureItem.id.in_(ids),
            )
            .update(normalized_patch, synchronize_session=False)
        )
        safe_commit()
    except Exception:
        db.session.rollback()
        log.exception("slr.literature.bulk_patch commit failed paper=%s", paper_id)
        return _err("bulk patch failed", "LITERATURE_BULK_PATCH_FAILED", 500)
    return jsonify({"updated": int(updated or 0)})


@slr_api.route("/api/papers/<paper_id>/literature/upload-pdf", methods=["POST"])
@jwt_required()
def upload_pdf_literature(paper_id: str):
    """Upload PDF files directly to Literature tab.
    
    For each PDF:
    1. Extract metadata (title, authors, DOI, year, abstract, venue)
    2. Match against existing SLR entries (by DOI or normalized title)
    3. If match found: attach file to existing entry, mark as checked
    4. If no match: create new LiteratureItem with extracted metadata
    
    Returns: {created: [...], matched: [...], total: N}
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    
    # Get uploaded files
    files = request.files.getlist('files')
    if not files:
        return _err("No files uploaded", "NO_FILES", 400)
    
    # Get existing SLR entries for matching
    existing_items = (
        db.session.query(LiteratureItem)
        .filter_by(paper_id=paper_id, user_id=user_id)
        .all()
    )
    existing_dois = {
        (i.doi or "").lower().strip() 
        for i in existing_items if i.doi
    }
    existing_titles_norm = {
        _normalize_title_for_match(i.title)
        for i in existing_items if i.title
    }
    doi_to_item = {(i.doi or "").lower().strip(): i for i in existing_items if i.doi}
    title_norm_to_item = {_normalize_title_for_match(i.title): i for i in existing_items if i.title}
    
    created = []
    matched = []
    
    import json as _json
    import uuid
    from tools.Literatur.pdf_metadata_extractor import extract_metadata_from_pdf, _normalize_title as _norm_title
    
    # Save files temporarily and extract metadata
    MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB per file (unrestricted)
    
    for f in files:
        if not f.filename:
            continue
        
        # Validate PDF extension only
        if not f.filename.lower().endswith('.pdf'):
            return _err(f"Only PDF files are accepted, got: {f.filename}", "INVALID_FILE_TYPE", 400)
        
        # Validate file size BEFORE saving to prevent memory exhaustion
        try:
            f.stream.seek(0, 2)  # Seek to end
            file_size = f.stream.tell()
            f.stream.seek(0)  # Reset to beginning
            if file_size > MAX_FILE_SIZE:
                return _err(
                    f"File too large ({file_size / (1024*1024):.1f}MB). Maximum allowed is 1000MB per file.",
                    "FILE_TOO_LARGE",
                    400
                )
            if file_size == 0:
                return _err("Empty file uploaded", "EMPTY_FILE", 400)
        except Exception as e:
            log.error("Failed to check file size: %s", e)
            return _err("Failed to read uploaded file", "READ_ERROR", 400)
        
        # Save to temp location
        temp_dir = Path('/tmp/papergenerator_uploads')
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{uuid.uuid4()}.pdf"
        
        try:
            f.save(str(temp_path))
        except Exception as e:
            log.error("Failed to save uploaded file: %s", e)
            continue
        
        # Extract metadata from PDF
        try:
            meta = extract_metadata_from_pdf(
                temp_path,
                existing_dois=existing_dois,
                existing_titles_norm=existing_titles_norm,
            )
        except Exception as e:
            log.error("Metadata extraction failed: %s", e)
            meta = {
                'title': f.filename or "Untitled",
                'authors': [],
                'year': None,
                'doi': None,
                'abstract': '',
                'venue': '',
                'publisher': '',
            }
        finally:
            # Clean up temp file
            try:
                temp_path.unlink()
            except Exception:
                pass
        
        # Check for match against existing SLR entries
        matched_item = None
        match_type = None
        
        # Priority 1: Match by DOI
        if meta.get('doi'):
            doi_key = meta['doi'].lower().strip()
            matched_item = doi_to_item.get(doi_key)
            if matched_item:
                match_type = 'doi'
        
        # Priority 2: Match by normalized title
        if not matched_item and meta.get('title'):
            title_key = _norm_title(meta['title'])
            matched_item = title_norm_to_item.get(title_key)
            if matched_item:
                match_type = 'title'
        
        if matched_item:
            # Attach to existing SLR entry
            if not matched_item.file_id:
                # Store PDF metadata in PaperFile for future reference
                pf = PaperFile(
                    paper_id=paper_id,
                    user_id=user_id,
                    filename=f"{uuid.uuid4()}.pdf",
                    original_name=f.filename or "Untitled.pdf",
                    ext='.pdf',
                    size_bytes=0,
                    file_path='',
                    extracted_text='',
                    meta_title=(meta.get('title') or '')[:5000],
                    meta_authors=_json.dumps(meta.get('authors') or [])[:5000],
                    meta_doi=(meta.get('doi') or '')[:500],
                    meta_year=meta.get('year'),
                    meta_abstract=(meta.get('abstract') or '')[:10000],
                    meta_venue=(meta.get('venue') or '')[:500],
                    meta_publisher=(meta.get('publisher') or '')[:500],
                )
                db.session.add(pf)
                db.session.flush()
                matched_item.file_id = pf.id
                matched_item.url = f"/api/papers/{paper_id}/files/{pf.id}/preview"
            # Enrich sparse SLR entries
            title_n = re.sub(r'[^a-z0-9]+', '', (meta.get('title') or '').lower())[:500]
            if not matched_item.title_norm and title_n:
                matched_item.title_norm = title_n
            if not matched_item.authors and meta.get('authors'):
                matched_item.authors = meta['authors']
            if not matched_item.year and meta.get('year'):
                matched_item.year = meta['year']
            if not matched_item.venue and meta.get('venue'):
                matched_item.venue = meta['venue'][:200]
            if not matched_item.publisher and meta.get('publisher'):
                matched_item.publisher = meta['publisher'][:200]
            matched.append({
                'id': matched_item.id,
                'title': matched_item.title,
                'match_type': match_type,
                'doi': matched_item.doi,
            })
        else:
            # Create new LiteratureItem
            # Store PDF metadata in PaperFile
            pf = PaperFile(
                paper_id=paper_id,
                user_id=user_id,
                filename=f"{uuid.uuid4()}.pdf",
                original_name=f.filename or "Untitled.pdf",
                ext='.pdf',
                size_bytes=0,
                file_path='',
                extracted_text='',
                meta_title=(meta.get('title') or '')[:5000],
                meta_authors=_json.dumps(meta.get('authors') or [])[:5000],
                meta_doi=(meta.get('doi') or '')[:500],
                meta_year=meta.get('year'),
                meta_abstract=(meta.get('abstract') or '')[:10000],
                meta_venue=(meta.get('venue') or '')[:500],
                meta_publisher=(meta.get('publisher') or '')[:500],
            )
            db.session.add(pf)
            db.session.flush()
            
            item = LiteratureItem(
                paper_id=paper_id,
                user_id=user_id,
                source_kind='file',
                source='pdf',
                title=(meta.get('title') or f.filename or 'Untitled')[:300],
                title_norm=re.sub(r'[^a-z0-9]+', '', (meta.get('title') or '').lower())[:500],
                authors=meta.get('authors') or [],
                year=meta.get('year'),
                venue=(meta.get('venue') or '')[:200],
                publisher=(meta.get('publisher') or '')[:200],
                doi=meta.get('doi'),
                url=f"/api/papers/{paper_id}/files/{pf.id}/preview",
                abstract=(meta.get('abstract') or '')[:3000],
                summary=(meta.get('abstract') or '')[:600],
                file_id=pf.id,
                pinned=True,
            )
            db.session.add(item)
            created.append(item)
    
    safe_commit()
    
    return jsonify({
        "created": [i.to_dict() for i in created],
        "matched": matched,
        "total": len(created) + len(matched),
    })


@slr_api.route("/api/papers/<paper_id>/literature/from-files", methods=["POST"])
@jwt_required()
def import_from_files(paper_id: str):
    """Import from existing PaperFile records (legacy, uses stored metadata).
    
    Returns: {created: [...], matched: [...], total: N}
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    # Get all files for this paper
    files = (
        PaperFile.query.filter_by(paper_id=paper_id, user_id=user_id)
        .order_by(PaperFile.created_at.desc())
        .all()
    )
    
    # Get existing file_ids that are already imported
    existing_file_ids = {
        i.file_id
        for i in db.session.query(LiteratureItem)
        .filter_by(paper_id=paper_id)
        .filter(LiteratureItem.file_id.isnot(None))
        .all()
    }
    
    # Get existing SLR entries for matching
    existing_items = (
        db.session.query(LiteratureItem)
        .filter_by(paper_id=paper_id, user_id=user_id)
        .all()
    )
    existing_dois = {
        (i.doi or "").lower().strip() 
        for i in existing_items if i.doi
    }
    existing_titles_norm = {
        _normalize_title_for_match(i.title)
        for i in existing_items if i.title
    }
    # Map for quick lookup
    doi_to_item = {(i.doi or "").lower().strip(): i for i in existing_items if i.doi}
    title_norm_to_item = {_normalize_title_for_match(i.title): i for i in existing_items if i.title}
    
    created = []
    matched = []
    
    import json as _json
    
    for f in files:
        if f.id in existing_file_ids:
            continue
        
        # Use stored metadata from PaperFile (extracted during upload)
        # No need for file on disk!
        # After jsonb_migration_001 is applied, f.meta_authors will be a list
        # directly. Handle both the old Text (JSON string) and new JSONB (list).
        meta_authors = []
        if f.meta_authors:
            if isinstance(f.meta_authors, list):
                meta_authors = f.meta_authors
            else:
                try:
                    meta_authors = _json.loads(f.meta_authors)
                except (ValueError, TypeError):
                    pass
        
        meta = {
            'title': f.meta_title or f.original_name or f"File {f.id}",
            'authors': meta_authors or [],
            'year': f.meta_year,
            'doi': f.meta_doi or None,
            'abstract': f.meta_abstract or (f.extracted_text or "")[:3000],
            'venue': f.meta_venue or "",
            'publisher': f.meta_publisher or "",
        }
        
        # Check for match against existing SLR entries
        matched_item = None
        match_type = None
        
        # Priority 1: Match by DOI
        if meta.get('doi'):
            doi_key = meta['doi'].lower().strip()
            matched_item = doi_to_item.get(doi_key)
            if matched_item:
                match_type = 'doi'
        
        # Priority 2: Match by normalized title
        if not matched_item and meta.get('title'):
            from tools.Literatur.pdf_metadata_extractor import _normalize_title as _norm_title
            title_key = _norm_title(meta['title'])
            matched_item = title_norm_to_item.get(title_key)
            if matched_item:
                match_type = 'title'
        
        if matched_item:
            # Attach file to existing SLR entry
            if not matched_item.file_id:  # Don't overwrite existing file attachment
                matched_item.file_id = f.id
                matched_item.url = f"/api/papers/{paper_id}/files/{f.id}/preview"
            # Enrich sparse SLR entries
            title_n = re.sub(r'[^a-z0-9]+', '', (meta.get('title') or '').lower())[:500]
            if not matched_item.title_norm and title_n:
                matched_item.title_norm = title_n
            if not matched_item.authors and meta.get('authors'):
                matched_item.authors = meta['authors']
            if not matched_item.year and meta.get('year'):
                matched_item.year = meta['year']
            if not matched_item.venue and meta.get('venue'):
                matched_item.venue = meta['venue'][:200]
            if not matched_item.publisher and meta.get('publisher'):
                matched_item.publisher = meta['publisher'][:200]
            matched.append({
                'id': matched_item.id,
                'title': matched_item.title,
                'match_type': match_type,
                'doi': matched_item.doi,
            })
        else:
            # Create new LiteratureItem
            item = LiteratureItem(
                paper_id=paper_id,
                user_id=user_id,
                source_kind="file",
                source=f.ext.lstrip(".") if f.ext else "pdf",
                title=(meta.get('title') or f.original_name or f"File {f.id}")[:300],
                title_norm=re.sub(r'[^a-z0-9]+', '', (meta.get('title') or '').lower())[:500],
                authors=meta.get('authors') or [],
                year=meta.get('year'),
                venue=(meta.get('venue') or "")[:200],
                publisher=(meta.get('publisher') or "")[:200],
                doi=meta.get('doi'),
                url=f"/api/papers/{paper_id}/files/{f.id}/preview",
                abstract=(meta.get('abstract') or "")[:3000],
                summary=(meta.get('abstract') or "")[:600],
                file_id=f.id,
                pinned=True,
            )
            db.session.add(item)
            created.append(item)
    
    safe_commit()
    
    return jsonify({
        "created": [i.to_dict() for i in created],
        "matched": matched,
        "total": len(created) + len(matched),
    })


def _normalize_title_for_match(title: str) -> str:
    """Normalize title for matching: lowercase, strip non-alphanumeric."""
    return re.sub(r'[^a-z0-9]+', '', (title or "").lower())


# ─── Legacy /slr endpoint (now async-only) ────────────────────────────────


@slr_api.route("/api/papers/<paper_id>/slr", methods=["POST"])
@jwt_required()
def run_slr_legacy(paper_id: str):
    """Legacy endpoint: enqueues a job and returns 202 + job_id immediately.

    Callers must poll GET /api/slr/jobs/<job_id> for status and results.
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    # F-28: same in-memory rate limit as the new endpoint, keyed under the
    # same bucket so legacy clients can't bypass it.
    ok, retry_after = _check_rate_limit(user_id, "create_slr_job")
    if not ok:
        return (
            jsonify(
                {
                    "error": "Rate limit: max 10 SLR jobs/minute",
                    "code": "RATE_LIMITED",
                    "retry_after": retry_after,
                }
            ),
            429,
        )

    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    query = (body.get("query") or body.get("topic") or paper.title or "").strip()
    if not query:
        return _err("query required", "QUERY_REQUIRED", 400)

    try:
        top_k = max(5, min(int(body.get("top_k", body.get("limit", 50))), 500))
    except (TypeError, ValueError):
        top_k = 50
    per_source = _safe_per_source(body.get("per_source"))

    # Per fetcher = topK × 5. More candidates = better ranking. Return capped to topK.
    if not body.get("per_source"):
        default_source_count = 5
        active_sources = body.get("sources") or None
        source_count = max(len(active_sources) if active_sources else default_source_count, 1)
        per_source = max(per_source, (top_k * 5 // source_count) + 1)

    year_from, year_err = _validate_year(body.get("year_from"))
    if year_err:
        return year_err

    year_to, year_to_err = _validate_year(body.get("year_to"))
    if year_to_err:
        return year_to_err

    ai_model = (body.get("ai_model") or get_primary_generate_model()).strip()
    if ai_model not in {"VIOLA-CHAT", "VIOLA-GENERATE"}:
        ai_model = get_primary_generate_model()
    log.info(
        "slr.create user=%d paper=%s query=%s top_k=%d ai_model=%s",
        user_id,
        paper.id,
        query[:60],
        top_k,
        ai_model,
    )

    job = enqueue_slr_job(
        paper_id=paper.id,
        user_id=user_id,
        query=query,
        sources=body.get("sources"),
        per_source=per_source,
        top_k=top_k,
        year_from=year_from,
        ai_summarize=bool(body.get("ai_summarize", True)),
        ai_model=ai_model,
    )
    return jsonify({"job_id": job.id, "status": job.status}), 202


# ─── CHECKED LITERATURE (marked as read/reviewed) ─────────────────────────


@slr_api.route("/api/papers/<paper_id>/literature/checked", methods=["GET"])
@jwt_required()
def get_checked_literature(paper_id: str):
    """Return all checked literature items for a paper."""
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    # Get items where is_checked is true
    items = LiteratureItem.query.filter_by(
        paper_id=paper_id,
        user_id=user_id,
        is_checked=True,
    ).order_by(LiteratureItem.score_total.desc().nullslast()).all()

    result = []
    for it in items:
        d = it.to_dict()
        result.append({
            "id": d["id"],
            "title": d.get("title", ""),
            "authors": d.get("authors", []),
            "abstract": d.get("abstract", ""),
            "year": d.get("year"),
            "publisher": d.get("publisher", ""),
            "venue": d.get("venue", ""),
            "doi": d.get("doi"),
            "citations": d.get("citations", 0),
            "url": d.get("url", ""),
        })

    return jsonify({"items": result})


@slr_api.route("/api/papers/<paper_id>/literature/checked/export", methods=["GET"])
@jwt_required()
def export_checked_literature(paper_id: str):
    """Download checked literature as DOCX or PDF."""
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    _paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    fmt = (request.args.get("format") or "docx").lower().strip()
    if fmt not in {"docx", "pdf"}:
        return _err("format must be docx or pdf", "FORMAT_INVALID", 400)

    items = LiteratureItem.query.filter_by(
        paper_id=paper_id,
        user_id=user_id,
        is_checked=True,
    ).order_by(LiteratureItem.score_total.desc().nullslast()).all()
    if not items:
        return _err("Tidak ada literatur yang di-check", "NO_CHECKED_LITERATURE", 404)

    title_source = (getattr(_paper, "title", "") or "").strip()
    if not title_source or title_source.lower() == "untitled":
        title_source = next((it.title for it in items if it.title), "selected_literature")
    safe_title = re.sub(r"[^A-Za-z0-9\u00C0-\u024F_-]+", "_", title_source).strip("_")
    safe_title = re.sub(r"_+", "_", safe_title)[:80] or "selected_literature"
    safe_name = f"Literature_{safe_title}"
    if fmt == "docx":
        try:
            from docx import Document
        except Exception as e:
            log.exception("DOCX export unavailable: %s", e)
            return _err("DOCX export dependency unavailable", "DOCX_UNAVAILABLE", 500)
        doc = Document()
        doc.add_heading("Selected Literature", level=1)
        doc.add_paragraph(f"Paper ID: {paper_id}")
        doc.add_paragraph(f"Total: {len(items)}")
        for idx, it in enumerate(items, 1):
            doc.add_heading(f"{idx}. {it.title or 'Untitled'}", level=2)
            authors = ", ".join(it.authors or []) if isinstance(it.authors, list) else (it.authors or "")
            rows = [
                ("Authors", authors),
                ("Year", str(it.year or "")),
                ("Venue/Publisher", it.venue or it.publisher or ""),
                ("DOI", it.doi or ""),
                ("URL", it.url or ""),
                ("PDF URL", it.pdf_url or ""),
                ("Citations", str(it.citations or 0)),
                ("Source", it.source or ""),
            ]
            for label, value in rows:
                if value:
                    p = doc.add_paragraph()
                    p.add_run(f"{label}: ").bold = True
                    p.add_run(value)
            if it.abstract:
                doc.add_paragraph("Abstract:").runs[0].bold = True
                doc.add_paragraph(it.abstract)
            if it.summary:
                doc.add_paragraph("Summary:").runs[0].bold = True
                doc.add_paragraph(it.summary)
        bio = BytesIO()
        doc.save(bio)
        bio.seek(0)
        return send_file(
            bio,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=f"{safe_name}.docx",
        )

    # ponytail: basic text-only PDF; upgrade to reportlab if rich tables/styles are needed.
    lines: list[str] = ["Selected Literature", f"Paper ID: {paper_id}", f"Total: {len(items)}", ""]
    for idx, it in enumerate(items, 1):
        lines.append(f"{idx}. {it.title or 'Untitled'}")
        authors = ", ".join(it.authors or []) if isinstance(it.authors, list) else (it.authors or "")
        for label, value in [
            ("Authors", authors), ("Year", it.year), ("Venue/Publisher", it.venue or it.publisher),
            ("DOI", it.doi), ("URL", it.url), ("PDF URL", it.pdf_url),
            ("Citations", it.citations), ("Source", it.source),
        ]:
            if value not in (None, ""):
                lines.append(f"{label}: {value}")
        if it.abstract:
            lines.extend(["Abstract:", it.abstract])
        if it.summary:
            lines.extend(["Summary:", it.summary])
        lines.append("")

    def _pdf_escape(text: str) -> str:
        return str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    page_chunks: list[list[str]] = [[]]
    for raw in lines:
        wrapped = re.findall(r".{1,95}(?:\s+|$)", str(raw).replace("\n", " ")) or [""]
        for line in wrapped:
            if len(page_chunks[-1]) >= 54:
                page_chunks.append([])
            page_chunks[-1].append(line.strip())

    objects: list[bytes] = [b""]
    pages_obj_id = 2
    page_ids: list[int] = []
    content_ids: list[int] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    for chunk in page_chunks:
        content_ops = ["BT", "/F1 10 Tf", "50 800 Td", "14 TL"]
        for line in chunk:
            content_ops.append(f"({_pdf_escape(line)}) Tj")
            content_ops.append("T*")
        content_ops.append("ET")
        stream = "\n".join(content_ops).encode("latin-1", "replace")
        content_id = len(objects)
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page_id = len(objects)
        objects.append(
            f"<< /Type /Page /Parent {pages_obj_id} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
        content_ids.append(content_id)
        page_ids.append(page_id)
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_obj_id] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj_id in range(1, len(objects)):
        offsets.append(out.tell())
        out.write(f"{obj_id} 0 obj\n".encode())
        out.write(objects[obj_id])
        out.write(b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects)}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    out.seek(0)
    return send_file(out, mimetype="application/pdf", as_attachment=True, download_name=f"{safe_name}.pdf")


# ─── PINNED LITERATURE (prompt preview) ───────────────────────────────────


@slr_api.route("/api/papers/<paper_id>/literature/pinned", methods=["GET"])
@jwt_required()
def get_pinned_literature_endpoint(paper_id: str):
    """Return pinned items formatted for prompt injection.

    Frontend bisa pakai ini untuk preview apa yang akan dikirim ke
    chat / paperfull sebagai SLR context.
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    try:
        max_items = int(request.args.get("max_items", 10))
    except (TypeError, ValueError):
        max_items = 10
    max_items = max(1, min(max_items, 50))

    formatted = get_pinned_literature(paper_id, user_id, max_items=max_items)
    return jsonify({
        "formatted": formatted,
        "has_items": bool(formatted),
        "paper_id": paper_id,
    })


# ─── helpers ──────────────────────────────────────────────────────────────


def _safe_int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_year_from(value):
    """Parse year_from with a sane bound. None for unset/invalid."""
    if value is None:
        return None
    try:
        y = int(value)
    except (TypeError, ValueError):
        return None
    if not (1500 <= y <= 2100):
        return None
    return y


def _safe_top_k(value, default=50):
    try:
        k = int(value)
    except (TypeError, ValueError):
        k = default
    return max(5, min(k, 500))


def _safe_per_source(value, default=60):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(10, min(n, 100))


@slr_api.route("/api/slr/cache/stats", methods=["GET"])
@jwt_required()
def cache_stats():
    """Return DB cache statistics.
    
    Response:
    {
        "total_papers": int,
        "total_sources": int,
        "sources": {"openalex": 100, "arxiv": 50, ...},
        "total_jobs": int,
        "year_distribution": {2024: 100, 2023: 80, ...}
    }
    """
    from . import db_cache
    
    try:
        stats = db_cache.get_db_stats()
        return jsonify(stats)
    except Exception as e:
        log.warning(f"Failed to get cache stats: {e}")
        return _err("Failed to get cache stats", "CACHE_ERROR", 500)


@slr_api.route("/api/slr/cache/search", methods=["GET"])
@jwt_required()
def cache_search():
    """Search papers in DB cache.
    
    Query params:
    - q: search query (required)
    - limit: max results (default 50)
    - year_from: filter by year
    - year_to: filter by year
    - sources: filter by sources (comma-separated)
    
    Response:
    {
        "papers": [
            {
                "doi": "...",
                "title": "...",
                "authors": [...],
                "year": 2024,
                "venue": "...",
                "abstract": "...",
                "citations": 10,
                "is_open_access": true,
                "url": "...",
                "source": "openalex"
            }
        ],
        "count": int
    }
    """
    from . import db_cache
    
    query = request.args.get("q", "").strip()
    if not query:
        return _err("Query parameter 'q' is required", "MISSING_QUERY", 400)
    
    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 100))  # prevent abuse/exhaustion
    
    try:
        year_from = int(request.args.get("year_from")) if request.args.get("year_from") else None
    except (TypeError, ValueError):
        year_from = None
    
    try:
        year_to = int(request.args.get("year_to")) if request.args.get("year_to") else None
    except (TypeError, ValueError):
        year_to = None
    
    sources_str = request.args.get("sources", "").strip()
    sources = [s.strip() for s in sources_str.split(",") if s.strip()] if sources_str else None
    
    try:
        papers = db_cache.search_papers(
            query=query,
            limit=limit,
            year_from=year_from,
            year_to=year_to,
            sources=sources,
        )
        
        return jsonify({
            "papers": [
                {
                    "doi": p.doi,
                    "title": p.title,
                    "authors": p.authors,
                    "year": p.year,
                    "venue": p.venue,
                    "venue_type": p.venue_type,
                    "abstract": p.abstract,
                    "citations": p.citations,
                    "is_open_access": p.is_open_access,
                    "url": p.url,
                    "pdf_url": p.pdf_url,
                    "source": p.source,
                    "source_id": p.source_id,
                    "type": p.type,
                    "publisher": p.publisher,
                }
                for p in papers
            ],
            "count": len(papers),
        })
    except Exception as e:
        log.warning(f"Failed to search cache: {e}")
        return _err("Failed to search cache", "CACHE_ERROR", 500)


@slr_api.route("/api/slr/mega-fetch/status", methods=["GET"])
@jwt_required()
def mega_fetch_status():
    """Get mega fetch daemon progress and stats.

    Response:
    {
        "overall": {
            "total_topics": 2000,
            "done_topics": 150,
            "running_topics": 3,
            "pending_topics": 1847,
            "error_topics": 0,
            "total_fetched": 15000000,
            "total_target": 200000000,
            "pct": 7.5
        },
        "per_field": [
            {
                "field": "Computer Science",
                "topics": 100,
                "done": 10,
                "fetched": 1000000,
                "target": 10000000,
                "pct": 10.0
            }
        ],
        "recent": [...]
    }
    """
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            dbname=os.getenv("DB_NAME", "paper_database"),
            user=os.getenv("DB_USER", "papergenerator"),
            password=os.getenv("DB_PASSWORD", ""),
        )
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Overall stats
        cur.execute("""
            SELECT
                COUNT(*) as total_topics,
                COUNT(*) FILTER (WHERE status = 'done') as done_topics,
                COUNT(*) FILTER (WHERE status = 'running') as running_topics,
                COUNT(*) FILTER (WHERE status = 'pending') as pending_topics,
                COUNT(*) FILTER (WHERE status = 'error') as error_topics,
                COALESCE(SUM(fetched_count), 0) as total_fetched,
                COALESCE(SUM(target_count), 0) as total_target,
                ROUND(100.0 * COALESCE(SUM(fetched_count), 0) / NULLIF(SUM(target_count), 0), 2) as pct
            FROM mega_fetch_progress
        """)
        overall = dict(cur.fetchone())

        # Per field
        cur.execute("""
            SELECT
                field_name as field,
                COUNT(*) as topics,
                COUNT(*) FILTER (WHERE status = 'done') as done,
                COALESCE(SUM(fetched_count), 0) as fetched,
                COALESCE(SUM(target_count), 0) as target,
                ROUND(100.0 * COALESCE(SUM(fetched_count), 0) / NULLIF(SUM(target_count), 0), 2) as pct
            FROM mega_fetch_progress
            GROUP BY field_name
            ORDER BY field_name
        """)
        per_field = [dict(r) for r in cur.fetchall()]

        # Recent activity (last 10 completed/running)
        cur.execute("""
            SELECT field_name, topic, fetched_count, target_count, status,
                   started_at, finished_at, updated_at
            FROM mega_fetch_progress
            WHERE status IN ('done', 'running')
            ORDER BY updated_at DESC
            LIMIT 10
        """)
        recent = [dict(r) for r in cur.fetchall()]

        # Papers in DB
        cur.execute("SELECT COUNT(*) as total FROM papers")
        papers_total = dict(cur.fetchone())["total"]

        cur.close()
        conn.close()

        return jsonify({
            "overall": overall,
            "per_field": per_field,
            "recent": recent,
            "papers_in_db": papers_total,
        })
    except Exception as e:
        log.warning(f"Failed to get mega fetch status: {e}")
        return _err("Failed to get status", "STATUS_ERROR", 500)


# ─── LITERATURE REVIEW (per-item AI review) ───────────────────────────────


@slr_api.route("/api/papers/<paper_id>/literature/<int:item_id>/review", methods=["POST"])
@jwt_required()
def review_literature_item(paper_id: str, item_id: int):
    """Generate AI review for a single literature item.

    Uses the summarizer's AI chat to produce a concise academic review
    based on the item's title + abstract. Stores the result in
    LiteratureItem.review and returns it.
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    item = (
        db.session.query(LiteratureItem)
        .filter_by(id=item_id, paper_id=paper_id, user_id=user_id)
        .first()
    )
    if not item:
        return _err("Literature item not found", "LITERATURE_NOT_FOUND", 404)

    abstract = (item.abstract or "").strip()
    if not abstract:
        return _err("Abstract kosong, tidak bisa di-review", "NO_ABSTRACT", 400)

    try:
        from tools.Literatur.summarizer import _ai_chat

        prompt = (
            "You are an academic literature reviewer. Given the following paper, "
            "write a concise 2-3 sentence review covering: (1) the main contribution, "
            "(2) the method/approach, (3) strengths or limitations. "
            "Be faithful — do NOT invent data.\n\n"
            f"Title: {item.title or 'Untitled'}\n"
            f"Year: {item.year or 'Unknown'}\n"
            f"Abstract: {abstract}\n\n"
            "Respond with plain text only (no JSON, no markdown)."
        )

        content = _ai_chat(
            [{"role": "user", "content": prompt}],
            max_tokens=1024,
            timeout=60,
        )

        if not content:
            # Fallback: extractive summary from abstract
            from tools.Literatur.summarizer import summarize
            content = summarize(abstract, query=item.title, n_sentences=3)

        if content:
            item.review = content
            safe_commit()

        return jsonify({"review": content or "", "id": item_id})

    except Exception as e:
        log.exception("review_literature_item failed item=%d: %s", item_id, e)
        return _err(f"Review gagal: {e}", "REVIEW_ERROR", 500)


@slr_api.route("/api/papers/<paper_id>/literature/review-pinned", methods=["POST"])
@jwt_required()
def review_pinned_literature(paper_id: str):
    """Generate AI review for all pinned literature items.

    Reviews each pinned item sequentially. Returns array of results.
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    items = (
        db.session.query(LiteratureItem)
        .filter_by(paper_id=paper_id, user_id=user_id, pinned=True)
        .order_by(LiteratureItem.updated_at.desc())
        .limit(20)
        .all()
    )

    if not items:
        return jsonify({"results": []})

    results = []
    try:
        from tools.Literatur.summarizer import _ai_chat, summarize

        for item in items:
            abstract = (item.abstract or "").strip()
            if not abstract:
                results.append({
                    "id": item.id,
                    "status": "skipped",
                    "reason": "no abstract",
                })
                continue

            prompt = (
                "You are an academic literature reviewer. Given the following paper, "
                "write a concise 2-3 sentence review covering: (1) the main contribution, "
                "(2) the method/approach, (3) strengths or limitations. "
                "Be faithful — do NOT invent data.\n\n"
                f"Title: {item.title or 'Untitled'}\n"
                f"Year: {item.year or 'Unknown'}\n"
                f"Abstract: {abstract}\n\n"
                "Respond with plain text only (no JSON, no markdown)."
            )

            try:
                content = _ai_chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=1024,
                    timeout=60,
                )
                if not content:
                    content = summarize(abstract, query=item.title, n_sentences=3)

                if content:
                    item.review = content
                    results.append({
                        "id": item.id,
                        "status": "success",
                        "review": content,
                    })
                else:
                    results.append({
                        "id": item.id,
                        "status": "error",
                        "reason": "AI returned empty response",
                    })
            except Exception as e:
                results.append({
                    "id": item.id,
                    "status": "error",
                    "reason": str(e)[:200],
                })

        safe_commit()
    except Exception as e:
        db.session.rollback()
        log.exception("review_pinned_literature failed paper=%s: %s", paper_id, e)
        return _err(f"Review gagal: {e}", "REVIEW_ERROR", 500)

    return jsonify({"results": results})

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SLR ORCHESTRATOR (merged from original slr.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_redis: Any = None
try:
    import redis as _redis_mod
    # Use REDIS_URL if available for consistency with slr_api.py
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis = _redis_mod.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
    )
    _redis.ping()
    log.info("Redis connected for SLR orchestrator")
except Exception as e:
    log.warning("Redis unavailable for SLR orchestrator; using in-memory progress: %s", e)
    _redis = None

# ── In-memory job store ──────────────────────────────────────────────────
# BUG-B2 FIX: _jobs/_jobs_lock/_rate_limiters declared at module top-level (lines 71-75).
# Removed duplicate declarations here — re-declaring would replace the dicts with empty ones
# at module load, causing endpoint handlers (which import the top-level refs) to never see
# jobs created by the orchestrator section below.


# ── Job tracking class ────────────────────────────────────────────────────

class SLRJob:
    """Tracks state of one SLR job.

    In-memory storage. Redis used for cross-process progress visibility.
    Thread-safe via the orchestrator lock.
    """

    __slots__ = (
        "job_id", "paper_id", "keyword", "top_n", "user_id",
        "status", "stage", "progress_pct", "stage_detail",
        "error", "results", "partial_results", "summary_result",
        "sources_completed", "sources_total", "sources_running", "sources_pending",
        "papers_fetched", "all_papers_count",
        "started_at", "eta_seconds", "eta_display", "stopped",
        "per_source", "sources",
        "year_from", "year_to",
    )

    def __init__(
        self,
        job_id: str,
        paper_id: str,
        keyword: str,
        top_n: int,
        user_id: int,
        per_source: int = 30,
        sources: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ):
        self.job_id = job_id
        self.paper_id = paper_id
        self.keyword = keyword
        self.top_n = top_n
        self.user_id = user_id
        self.status = "pending"
        self.stage = "pending"
        self.progress_pct = 0.0
        self.stage_detail = ""
        self.error: str | None = None
        self.results: list[dict] | None = None
        self.partial_results: list[dict] = []
        self.summary_result: dict | None = None
        self.sources_completed: list[str] = []
        self.sources_total = 0
        self.sources_running: list[str] = []
        self.sources_pending: list[str] = []
        self.papers_fetched = 0
        self.all_papers_count = 0
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.stopped = threading.Event()
        self.per_source = per_source
        self.sources = list(sources or [])
        self.year_from = year_from
        self.year_to = year_to
        # ETA fields
        self.eta_seconds: int | None = None
        self.eta_display: str = ""

    def to_dict(self) -> dict:
        """Serialize to dict for API responses and Redis.

        Field mapping for frontend compatibility:
        - status: keep original ('pending'/'analyzing'/'fetching'/etc) for filtering
        - progress_pct → progress (0-100)
        - stage_detail → progress_message
        """
        d: dict[str, Any] = {
            "id": self.job_id,
            "job_id": self.job_id,
            "paper_id": self.paper_id,
            "user_id": self.user_id,
            "query": self.keyword,
            "status": self.status,
            "stage": self.stage,
            "progress": int(self.progress_pct),
            "progress_pct": self.progress_pct,
            "progress_message": self.stage_detail,
            "stage_detail": self.stage_detail,
            "sources_completed": list(self.sources_completed),
            "sources_total": self.sources_total,
            "sources_running": list(self.sources_running),
            "sources_pending": list(self.sources_pending),
            "papers_fetched": self.papers_fetched,
            "all_papers_count": self.all_papers_count,
            "sources": list(self.sources),
            "error": self.error,
            "eta_seconds": self.eta_seconds,
            "eta_display": self.eta_display,
            "partial_results": self.partial_results[:PARTIAL_RESULTS_PREVIEW],
            "results": self.results,
        }

        # Include summary result if available (for detailed endpoint)
        if self.summary_result is not None:
            d["summary_result"] = self.summary_result

        return d

    def cancel(self):
        """Signal cancellation to running workers."""
        self.stopped.set()


# ── Redis progress helpers ────────────────────────────────────────────────

def _redis_key(job_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}{job_id}"


def _push_progress(job: SLRJob):
    """Write job progress to Redis (best-effort) + publish to pubsub channel for SSE."""
    # Unified: use _redis_client (the canonical Redis instance)
    client = _redis_client if _redis_client is not None else _redis
    if client is None:
        return
    try:
        data = json.dumps(job.to_dict())
        client.setex(_redis_key(job.job_id), REDIS_PROGRESS_TTL, data)
        # Publish to pubsub channel for SSE subscribers
        _publish_progress_to_pubsub(client, data)
    except Exception:
        pass
    # Throttled DB persistence: every 5th push (keeps job row fresh across restarts)
    global _push_count
    with _push_count_lock:  # BUG-B1 FIX: thread-safe counter increment
        _push_count += 1
        do_persist = (_push_count % 5 == 0)
    if do_persist:
        _persist_job_to_db(job)


def _publish_progress_to_pubsub(client, job_json: str):
    """Publish job progress to Redis pubsub channel (for SSE streaming)."""
    try:
        channel = f"slr_progress:{json.loads(job_json).get('job_id', '')}"
        client.publish(channel, job_json)
    except Exception:
        pass


def _persist_job_to_db(job: SLRJob):
    """Persist orchestrator job to DB SlrJob table."""
    # Push Flask app context for background thread safety
    ctx = None
    try:
        try:
            from flask import current_app
            if current_app and hasattr(current_app, 'app_context'):
                ctx = current_app.app_context()
                ctx.push()
            else:
                raise RuntimeError("No current_app")
        except (RuntimeError, ImportError):
            try:
                from main import app as _flask_app
                ctx = _flask_app.app_context()
                ctx.push()
            except ImportError as e:
                log.error("Flask app unavailable, skipping persist: %s", e)
                return

        from utils.database.models import SlrJob as DbSlrJob, db, safe_commit
        
        now = datetime.now(timezone.utc)
        db_job = db.session.query(DbSlrJob).filter_by(id=job.job_id).first()
        if not db_job:
            db_job = DbSlrJob(
                id=job.job_id,
                user_id=job.user_id,
                paper_id=job.paper_id,
                query=job.keyword,
                sources=job.sources,
                top_k=job.top_n,
                year_from=getattr(job, "year_from", None),
                year_to=getattr(job, "year_to", None),
                status=job.status,
                stage=job.stage,
                progress=int(job.progress_pct),
                progress_message=job.stage_detail,
                queued_at=now,
                updated_at=now,
            )
            db.session.add(db_job)
        else:
            db_job.status = job.status
            db_job.stage = job.stage
            db_job.progress = int(job.progress_pct)
            db_job.sources = job.sources
            db_job.year_from = getattr(job, "year_from", None)
            db_job.year_to = getattr(job, "year_to", None)
            db_job.progress_message = job.stage_detail
            db_job.updated_at = now  # CRITICAL: eksplisit set untuk long-poll detection
            if job.status == "done":
                db_job.finished_at = now
                # Persist the final summary result (grouped output) to DB
                db_job.result = job.summary_result or {}
            elif job.status == "error":
                db_job.error = job.error or ""
                db_job.finished_at = now
        
        safe_commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        log.warning("Failed to persist job %s to DB: %s", job.job_id, e)
    finally:
        if ctx:
            try:
                ctx.pop()
            except Exception as e:
                log.warning("Error popping Flask app context: %s", e)


def _stream_partial_results(job: SLRJob, new_papers: list[dict]):
    """Append new papers to partial_results and push to Redis + pubsub for SSE."""
    job.partial_results.extend(new_papers)
    job.papers_fetched += len(new_papers)
    _push_progress(job)
    # Also publish a dedicated partial event with the new papers
    client = _redis_client if _redis_client is not None else _redis
    if client is not None:
        try:
            partial_event = {
                "event_type": "partial",
                "status": job.status,
                "stage": job.stage,
                "papers_count": len(job.partial_results),
                "new_papers_count": len(new_papers),
                "new_papers": new_papers[:20],  # cap at 20 for SSE payload size
            }
            channel = f"slr_progress:{job.job_id}"
            client.publish(channel, json.dumps(partial_event))
        except Exception:
            pass


# ── Rate limiter factory ──────────────────────────────────────────────────

def _get_rate_limiters() -> dict[str, RateLimiter]:
    """Return shared rate limiters dict, seeded with optimized intervals for high-quality sources."""
    if not _rate_limiters:
        # Tier 1 Premium - aggressive but respectful (Scopus prioritized)
        _rate_limiters["scopus"] = RateLimiter(min_interval=0.8)  # Premium source, be respectful
        _rate_limiters["sciencedirect"] = RateLimiter(min_interval=1.0)  # Elsevier
        _rate_limiters["ieee"] = RateLimiter(min_interval=1.2)  # IEEE premium
        _rate_limiters["pubmed"] = RateLimiter(min_interval=0.4)  # Fast, reliable
        _rate_limiters["europepmc"] = RateLimiter(min_interval=0.5)  # Good performance
        
        # Tier 2 Broad - moderate intervals
        _rate_limiters["openalex"] = RateLimiter(min_interval=0.3)  # Very fast
        _rate_limiters["crossref"] = RateLimiter(min_interval=0.5)  # Reliable
        _rate_limiters["semantic_scholar"] = RateLimiter(min_interval=0.8)  # Moderate
        _rate_limiters["dimensions"] = RateLimiter(min_interval=1.0)
        _rate_limiters["lens"] = RateLimiter(min_interval=1.2)
        
        # Tier 3 Specialized - varied intervals
        _rate_limiters["arxiv"] = RateLimiter(min_interval=0.3)  # Fast preprints
        _rate_limiters["dblp"] = RateLimiter(min_interval=0.5)  # CS bibliography
        _rate_limiters["pmc"] = RateLimiter(min_interval=0.5)  # PMC full-text
        _rate_limiters["biorxiv"] = RateLimiter(min_interval=1.0)  # Preprints
        _rate_limiters["plos"] = RateLimiter(min_interval=1.0)  # PLOS journals
        
        # Tier 4 Indonesian - respectful to local infrastructure
        _rate_limiters["sinta"] = RateLimiter(min_interval=1.5)  # Indonesian source
        
        # Tier 5 Books and others - conservative
        _rate_limiters["google_books"] = RateLimiter(min_interval=1.0)
        _rate_limiters["open_library"] = RateLimiter(min_interval=1.2)
        _rate_limiters["doab"] = RateLimiter(min_interval=1.5)
        _rate_limiters["oapen"] = RateLimiter(min_interval=1.5)
        _rate_limiters["gutendex"] = RateLimiter(min_interval=1.0)
        _rate_limiters["cambridge"] = RateLimiter(min_interval=2.0)  # Scraping
        
        # Others
        _rate_limiters["doaj"] = RateLimiter(min_interval=1.5)
        _rate_limiters["zenodo"] = RateLimiter(min_interval=1.0)
        _rate_limiters["datacite"] = RateLimiter(min_interval=1.0)
        _rate_limiters["openaire"] = RateLimiter(min_interval=1.0)
        _rate_limiters["hal"] = RateLimiter(min_interval=1.5)
        
    return _rate_limiters


# ── LLM call helper ──────────────────────────────────────────────────────

def _estimate_text_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def _log_slr_ai_usage(user_id: int | None, model: str, prompt: str, completion: str) -> None:
    if not user_id:
        return
    try:
        from utils.ai_tools.tools_api import _log_tool_usage
        _log_tool_usage(
            int(user_id),
            "slr",
            model or "VIOLA-CHAT",
            _estimate_text_tokens(prompt),
            _estimate_text_tokens(completion),
        )
    except Exception as e:
        log.warning("SLR token tracking failed for user=%s: %s", user_id, e)


def _limit_words(text: str, max_words: int) -> str:
    if not text:
        return ""
    words = text.strip().split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]) + "…"


def _make_gap_riset(title: str, abstract: str, query: str = "") -> str:
    text = (abstract or title or "").strip()
    if not text:
        return "Belum ada gap riset: metadata abstract/review kosong."
    focus = (query or title or "topik terkait").strip()
    gap = (
        f"Gap riset potensial: {focus}, namun masih perlu dibandingkan "
        f"dengan studi terbaru pada konteks, metode, dan metrik berbeda."
    )
    return _limit_words(gap, 25)


def _get_llm_call(user_id: int | None = None) -> Callable[[str, str], str] | None:
    """Build an llm_call(system_prompt, user_message) -> str wrapper.

    Uses utils.ai_tools.model_router.route_chat_call when available.
    Returns None if the model router is unreachable — downstream code
    falls back to guess_fetchers / programmatic summarize.
    """
    try:
        from utils.ai_tools.model_router import route_chat_call  # noqa: F401
    except (ImportError, Exception) as e:
        log.debug("model_router unavailable (%s), using rule-based fallback", e)
        return None

    def llm_call(system_prompt: str, user_message: str) -> str:
        """Call the chat model via route_chat_call. Raises on failure."""
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 16384,
            "temperature": 0.3,
        }
        resp, model_used = route_chat_call(
            json=payload,
            timeout=120,
        )
        # resp is a requests.Response — extract message content
        # Some providers append SSE "data: [DONE]\n\n" to the response body;
        # strip it before JSON parsing.
        raw_text = resp.text.strip()
        if raw_text.endswith("data: [DONE]"):
            raw_text = raw_text[:raw_text.rfind("data: [DONE]")].strip()
        # Also strip trailing \n\n or whitespace
        raw_text = raw_text.rstrip()
        data = json.loads(raw_text)
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("LLM returned non-string content")
        _log_slr_ai_usage(user_id, model_used, system_prompt + user_message, content)
        return content

    return llm_call


# ── Orchestrator ──────────────────────────────────────────────────────────

class SLROrchestrator:
    """Manages SLR jobs: start, poll, cancel.

    Pipeline: analyze_keyword → route_fetchers → parallel fetch → summarize.
    All job state is in-memory; cross-process progress via Redis.
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix="slr-fetch",
        )
        self._swept = False

    def _sweep_orphaned_jobs(self):
        """Reset jobs stuck as 'running' in DB/Redis from a dead process."""
        if self._swept:
            return
        self._swept = True
        # Use raw SQL — may run before DB is fully ready in some workers.
        try:
            import psycopg2
            db_url = os.environ.get("DATABASE_URL", "")
            if not db_url:
                return
            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            cur.execute(
                "UPDATE slr_jobs SET status='error', stage='error', "
                "progress_message='Job interrupted by server restart. Please run SLR again.' "
                "WHERE status IN ('running', 'queued', 'pending')"
            )
            count = cur.rowcount
            conn.commit()
            cur.close()
            conn.close()
            if count:
                log.info("slr.sweep: reset %d orphaned jobs to error", count)
        except Exception as e:
            # Table not ready yet (e.g., first worker import) — skip silently
            if "UndefinedTable" not in str(type(e)):
                log.exception("slr.sweep failed")
        # Also clean Redis keys for orphaned jobs
        try:
            if _redis is not None:
                for key in _redis.scan_iter("slr_new:slr_*"):
                    try:
                        data = _redis.get(key)
                        if data:
                            d = json.loads(data)
                            if d.get("status") in ("running", "queued", "pending"):
                                _redis.delete(key)
                    except Exception:
                        pass
        except Exception:
            pass

    def start_job(
        self,
        paper_id: str,
        keyword: str,
        top_n: int,
        user_id: int,
        sources: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        ai_summarize: bool = False,
        per_source: int = 30,
        inline_fetch_map: dict[str, list[str]] | None = None,
        plain_keyword: str | None = None,
    ) -> str:
        """Create and start a new SLR job. Returns job_id string."""
        # Lazy sweep — runs once per worker process on first job start
        self._sweep_orphaned_jobs()
        
        job_id = f"slr_{uuid.uuid4().hex[:12]}"

        with _jobs_lock:
            job = SLRJob(
                job_id=job_id, paper_id=paper_id, keyword=keyword,
                top_n=top_n, user_id=user_id, per_source=per_source, sources=sources,
                year_from=year_from, year_to=year_to,
            )
            _jobs[job_id] = job

        # Register job in Redis set for cross-worker discovery
        try:
            if _redis is not None:
                set_key = f"slr_new:paper:{paper_id}:{user_id}"
                _redis.sadd(set_key, job_id)
                _redis.expire(set_key, 10800)  # 3 hours
        except Exception:
            pass

        # Push initial job state to Redis so it's immediately visible to all workers
        _push_progress(job)
        _persist_job_to_db(job)  # persist to DB on creation

        # Fire-and-forget the pipeline in a background thread
        thread = threading.Thread(
            target=self._run_pipeline,
            args=(job, keyword, top_n, sources, year_from, year_to, ai_summarize, inline_fetch_map, plain_keyword),
            daemon=False,
            name=f"slr-run-{job_id}",
        )
        thread.start()

        return job_id

    def get_job(self, job_id: str) -> dict | None:
        """Get job status dict, or None if not found."""
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                # Try Redis (cross-process fallback)
                if _redis is not None:
                    try:
                        data = _redis.get(_redis_key(job_id))
                        if data:
                            return json.loads(data)
                    except Exception:
                        pass
                # Try DB (survives restart / Redis expiry)
                try:
                    from utils.database.models import SlrJob as DbSlrJob
                    db_job = db.session.query(DbSlrJob).filter_by(id=job_id).first()
                    if db_job is not None:
                        return db_job.to_dict()
                except Exception:
                    pass
                return None
            return job.to_dict()

    def get_job_summary(self, job_id: str) -> dict | None:
        """Get job summary_result (grouped/summarized output) if complete."""
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return None
            if job.summary_result is None:
                return None
            return job.summary_result

    def cancel_job(self, job_id: str):
        """Cancel a running job."""
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return
            job.status = "cancelled"
            job.stage = "cancelled"
            job.progress_pct = 0
            job.stage_detail = "Cancelled by user"
            job.cancel()
            _push_progress(job)
            _persist_job_to_db(job)

    # ── Pipeline internals ─────────────────────────────────────────────

    def _run_pipeline(
        self,
        job: SLRJob,
        keyword: str,
        top_n: int,
        sources: list[str] | None,
        year_from: int | None,
        year_to: int | None,
        ai_summarize: bool,
        inline_fetch_map: dict[str, list[str]] | None = None,
        plain_keyword: str | None = None,
    ):
        """Full pipeline: analyze → fetch → summarize → complete."""
        try:
            # ── Stage 1: Analyze keyword (0-10%) ──────────────────────
            self._set_stage(job, "analyzing", 2.0, "Analyzing keyword for source routing...")

            routing_keyword = plain_keyword or keyword

            # Fetcher routing MUST use slrFetchPrompt.txt via analyze_keyword().
            # Timeout keeps the UI responsive; fallback only if the AI route fails.
            llm_for_fetch = _get_llm_call(job.user_id)
            if llm_for_fetch:
                with ThreadPoolExecutor(max_workers=1, thread_name_prefix="slr-analyze") as analyze_executor:
                    analyze_future = analyze_executor.submit(analyze_keyword, routing_keyword, llm_call=llm_for_fetch)
                    try:
                        analysis = analyze_future.result(timeout=ANALYZE_TIMEOUT_SEC)
                        self._set_stage(job, "analyzing", 8.0, "Fetcher dipilih dengan slrFetchPrompt.txt...")
                    except TimeoutError:
                        analyze_future.cancel()
                        log.warning("analyze_keyword timeout after %ss; using local fallback", ANALYZE_TIMEOUT_SEC)
                        analysis = guess_fetchers(routing_keyword)
                        self._set_stage(job, "analyzing", 8.0, "Fetcher AI timeout; using local fallback...")
                    except Exception as exc:
                        log.warning("analyze_keyword failed (%s); using local fallback", exc)
                        analysis = guess_fetchers(routing_keyword)
                        self._set_stage(job, "analyzing", 8.0, "Fetcher AI failed; using local fallback...")
            else:
                analysis = guess_fetchers(routing_keyword)
                self._set_stage(job, "analyzing", 8.0, "Fetcher AI unavailable; using local fallback...")

            # Extract core topic terms via LLM (parallel with fetcher routing, reuse same llm_call)
            core_terms = _extract_core_topics(keyword, llm_call=llm_for_fetch)
            log.info("Core topic terms for relevance filter: %s", core_terms)
            
            fetch_map = route_fetchers(analysis)
            if not fetch_map:
                fetch_map = {"explicit": [keyword]}

            for source, queries in (inline_fetch_map or {}).items():
                fetch_map.setdefault(source, [])
                fetch_map[source].extend(q for q in queries if q)

            # If user explicitly provided sources, override
            if sources:
                available = set(FETCHER_ALL.keys())
                user_sources = [s for s in (_normalize_fetcher_name(str(src), available) for src in sources) if s]
                if user_sources:
                    fetch_map = {s: [routing_keyword or keyword] for s in user_sources}

            if not fetch_map:
                self._set_error(job, "No fetcher sources available for this query")
                return

            fetcher_names = list(fetch_map.keys())
            total_queries = sum(len(qs) for qs in fetch_map.values())

            job.sources = fetcher_names
            job.sources_total = len(fetcher_names)
            job.sources_pending = list(fetcher_names)

            self._set_stage(
                job, "analyzing", 10.0,
                f"Analyzed → {len(fetcher_names)} sources, "
                f"{total_queries} queries, "
                f"domains: {', '.join(analysis.get('domains', ['general']))}",
            )

            # ── Post-filter year range BEFORE any DB save ─────────────────
            # Applied after all papers fetched, before first _save_to_db call.
            # (Fetchers also receive year_from/year_to for native filtering)

            # ── Stage 2: Parallel fetch (10-70%) ──────────────────────
            self._set_stage(job, "fetching", 10.0, "Starting parallel fetchers...")

            filters: dict = {}
            # NOTE: year_from/year_to are deliberately NOT passed to native fetchers.
            # Native API year filters (Crossref from-pub-date, OpenAlex from_publication_date, etc.)
            # shrink the fetch pool drastically for niche topics. Instead, we fetch broadly
            # (like the no-filter run) and apply year range as a post-fetch safety filter
            # (line ~3152) so it acts as a true SUBSET of the unfiltered results.

            all_papers: list[Paper] = []
            seen_keys: dict[str, int] = {}  # dedup_key → index in all_papers

            sources_running_set: set[str] = set(fetcher_names)
            sources_done: set[str] = set()
            source_remaining: dict[str, int] = {fn: len(queries) for fn, queries in fetch_map.items()}
            completed_tasks = 0

            # Build flat task list: cap each fetcher to N×5 across its queries.
            fetch_tasks: list[tuple[str, str, int]] = []
            for fn, queries in fetch_map.items():
                per_query_limit = max(1, (job.per_source + len(queries) - 1) // len(queries))
                for q in queries:
                    fetch_tasks.append((fn, q, per_query_limit))

            # Submit all fetch tasks
            futures = {}
            for fn, q, limit in fetch_tasks:
                future = self._executor.submit(
                    self._fetch_single_source, fn, q, limit, filters
                )
                futures[future] = (fn, q)

            job.sources_running = list(sources_running_set)
            job.sources_pending = []
            _push_progress(job)

            def absorb_fetch_result(fn: str, papers: list[Paper]):
                nonlocal completed_tasks
                completed_tasks += 1
                source_remaining[fn] = max(0, source_remaining.get(fn, 1) - 1)
                if source_remaining[fn] == 0:
                    sources_done.add(fn)
                    sources_running_set.discard(fn)
                completed_count = len(sources_done)

                new_papers: list[Paper] = []
                for p in papers:
                    k = p.dedup_key()
                    if k not in seen_keys:
                        seen_keys[k] = len(all_papers)
                        all_papers.append(p)
                        new_papers.append(p)

                job.sources_completed = list(sources_done)
                job.sources_running = list(sources_running_set)
                job.sources_pending = [s for s in fetcher_names if s not in sources_done and s not in sources_running_set]

                partial_dicts = []
                for p in new_papers:
                    try:
                        partial_dicts.append(p.to_dict())
                    except Exception:
                        partial_dicts.append({"title": p.title, "source": p.source})
                if partial_dicts:
                    _stream_partial_results(job, partial_dicts)
                    # ponytail: do NOT save partial fetcher batches to DB here.
                    # Year filter + relevance filter run after all fetchers finish (line ~3144).
                    # Saving pre-filter items means old/off-topic papers persist and reappear.

                pct_progress = 10.0 + (completed_count / len(fetcher_names)) * 60.0
                self._set_stage(
                    job, "fetching", min(pct_progress, 70.0),
                    f"Fetched {completed_count}/{len(fetcher_names)} sources "
                    f"({len(all_papers)} unique papers)",
                    extra={"all_papers_count": len(all_papers)},
                )

            try:
                completed_futures = as_completed(futures, timeout=FETCH_TIMEOUT_SEC)
                for future in completed_futures:
                    fn, q = futures[future]
                    if job.stopped.is_set():
                        continue
                    try:
                        papers = future.result()
                    except Exception as exc:
                        log.warning("Fetcher %s (q=%s) failed: %s", fn, q[:30], exc)
                        papers = []
                    absorb_fetch_result(fn, papers)
            except TimeoutError:
                timed_out = [(future, *futures[future]) for future in futures if not future.done()]
                log.warning(
                    "SLR fetch timeout after %ss for job %s: %d/%d tasks unfinished; using partial results",
                    FETCH_TIMEOUT_SEC, job.job_id, len(timed_out), len(futures),
                )
                for future, fn, _q in timed_out:
                    future.cancel()
                    absorb_fetch_result(fn, [])
                # ponytail: unfinished fetch threads may finish later; isolate fetchers or use process pool if they leak resources.

            if job.stopped.is_set():
                self._set_stage(job, "cancelled", 0.0, "Cancelled by user")
                return

            # ── Stage 3: Summarize (70-95%) ───────────────────────────
            # Post-filter year range (universal safety net for all fetchers)
            if year_from or year_to:
                before_year = len(all_papers)
                all_papers = [
                    p for p in all_papers
                    if (not year_from or not p.year or p.year >= year_from)
                    and (not year_to or not p.year or p.year <= year_to)
                ]
                removed_year = before_year - len(all_papers)
                if removed_year > 0:
                    log.info("Post-filter removed %d papers outside year range %s-%s", removed_year, year_from, year_to)

            before_filter = len(all_papers)
            all_papers = _filter_relevant_papers(keyword, all_papers, core_terms=core_terms)
            removed_irrelevant = before_filter - len(all_papers)

            if not all_papers:
                job.results = []
                job.summary_result = {
                    "groups": [],
                    "total_fetched": before_filter,
                    "total_unique": 0,
                    "total_returned": 0,
                    "stats": {"removed_irrelevant": removed_irrelevant},
                }
                job.status = "done"
                job.stage = "complete"
                job.progress_pct = 100.0
                job.stage_detail = f"Complete: 0 relevant papers (filtered {removed_irrelevant} off-topic results)"
                _push_progress(job)
                _persist_job_to_db(job)
                return

            self._set_stage(
                job, "summarizing", 70.0,
                f"Processing {len(all_papers)} relevant papers: filtered {removed_irrelevant} off-topic results...",
            )

            # Prepare paper dicts for summarizer
            paper_dicts = []
            for p in all_papers:
                try:
                    d = p.to_dict()
                    # Remove fields not expected by summarize (avoids noise)
                    d.pop("db_score", None)
                    d.pop("venue_type", None)
                    paper_dicts.append(d)
                except Exception:
                    paper_dicts.append({
                        "source": p.source,
                        "source_id": p.source_id,
                        "title": p.title,
                        "authors": p.authors,
                        "year": p.year,
                        "doi": p.doi,
                        "url": p.url,
                        "pdf_url": p.pdf_url,
                        "abstract": p.abstract,
                        "venue": p.venue,
                        "publisher": p.publisher,
                        "type": p.type,
                        "is_open_access": p.is_open_access,
                        "citations": p.citations,
                    })

            # Local summarize only. slrSummarizePrompt.txt batch-review sent the same
            # system prompt multiple times in one SLR run; keep one AI call for fetcher
            # selection only, then dedup/rank/group locally.
            # Dynamic timeout: 60s base + 1s per 100 papers (capped at 300s)
            summarize_timeout = int(os.getenv("SLR_SUMMARIZE_TIMEOUT_SEC", "60"))
            dynamic_timeout = min(60 + len(paper_dicts) // 100, 300)
            summarize_timeout = max(summarize_timeout, dynamic_timeout)
            
            self._set_stage(
                job, "summarizing", 78.0,
                f"Deduplicating, ranking and grouping {len(paper_dicts)} papers...",
            )

            # Call slrSummarize.summarize() — returns top_n × 5 grouped results.
            # Never let this block the whole SLR job; fallback ranking is better than 78% stuck.
            summarize_llm = _get_llm_call(job.user_id)
            summary_result = None
            summarize_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="slr-summarize")
            summarize_future = summarize_executor.submit(
                summarize_papers,
                papers=paper_dicts,
                query=keyword,
                top_n=top_n,
                llm_call=summarize_llm,
            )
            try:
                summary_result = summarize_future.result(timeout=summarize_timeout)
            except TimeoutError:
                log.warning("summarize_papers timeout after %ss, building fallback", summarize_timeout)
                summarize_future.cancel()
                summary_result = self._fallback_summarize(paper_dicts, keyword, top_n)
                # Update progress so UI doesn't stay stuck at 78%
                self._set_stage(
                    job, "summarizing", 85.0,
                    f"Fallback summarization complete ({summary_result.get('total_unique', 0)} unique)"
                )
            except Exception as exc:
                log.warning("summarize_papers failed (%s), building fallback", exc)
                summary_result = self._fallback_summarize(paper_dicts, keyword, top_n)
                self._set_stage(
                    job, "summarizing", 85.0,
                    f"Fallback summarization complete ({summary_result.get('total_unique', 0)} unique)"
                )
            finally:
                # ponytail: summarize may call a slow upstream LLM; process isolation would kill it harder.
                summarize_executor.shutdown(wait=False, cancel_futures=True)

            self._set_stage(
                job, "summarizing", 90.0,
                f"Grouped into {len(summary_result.get('groups', []))} categories "
                f"({summary_result.get('total_returned', 0)} papers returned)",
            )

            db_cancelled = False
            try:
                with db.session.no_autoflush:
                    db_cancelled = db.session.query(SlrJob.status).filter_by(id=job.job_id).scalar() == "cancelled"
            except Exception:
                db_cancelled = False
            if job.stopped.is_set() or db_cancelled:
                self._set_stage(job, "cancelled", 0.0, "Cancelled by user")
                return

            # ── Stage 4: Save & complete (95-100%) ────────────────────
            self._set_stage(job, "summarizing", 95.0, "Saving results...")

            # Extract flat paper list from groups for DB save
            all_result_papers = []
            for group in summary_result.get("groups", []):
                all_result_papers.extend(group.get("papers", []))

            # Best-effort DB save (non-blocking)
            # Save only top_n papers to DB (capped by user request)
            self._save_to_db(job, all_result_papers[:top_n])

            # Build final results list (flat, top_n for compatibility)
            final_results = all_result_papers[:top_n]

            with _jobs_lock:
                job.results = final_results
                job.summary_result = summary_result
                job.status = "done"
                job.stage = "complete"
                job.progress_pct = 100.0
                job.all_papers_count = summary_result.get("total_fetched", len(all_papers))
                job.stage_detail = (
                    f"Complete: {summary_result.get('total_returned', len(final_results))} papers "
                    f"in {len(summary_result.get('groups', []))} groups "
                    f"(from {summary_result.get('total_fetched', 0)} fetched, "
                    f"{summary_result.get('total_unique', 0)} unique)"
                )
                job.partial_results = final_results[:PARTIAL_RESULTS_PREVIEW]

            _push_progress(job)
            _persist_job_to_db(job)  # persist completion to DB

            # ── Token deduction for SLR (inside app context) ──────────────
            try:
                from flask import current_app
                if current_app:
                    with current_app.app_context():
                        from utils.database.models import ApiUsageLog, User as _SlrUser
                        from utils.database.models import db as _slr_db, safe_commit as _slr_commit
                        # Estimate actual LLM tokens used (not the full result JSON)
                        # Prompt: keyword + ~75 papers × 400 chars abstract ≈ 30k chars / 4 = 7.5k tokens
                        # Completion: ~75 reviews × 200 chars ≈ 15k chars / 4 = 3.75k tokens
                        # Only count if LLM was actually called (summarize_llm not None)
                        _prompt_t = max(1, len(keyword) // 4)
                        _comp_t = 0
                        _total = _prompt_t
                        if summarize_llm is not None:
                            # Token estimate: top_n papers × 400 chars abstract / 4 + top_n reviews × 200 chars / 4
                            _batches = (top_n + 49) // 50  # ceil(top_n / 50)
                            _prompt_t = min(8000, max(1, (len(keyword) + top_n * 400) // 4))
                            _comp_t = max(1, (top_n * 200) // 4)
                            _total = _prompt_t + _comp_t
                        _log_entry = ApiUsageLog(
                            user_id=int(job.user_id),
                            endpoint="/api/papers/slr/jobs",
                            model="slr-orchestrator",
                            prompt_tokens=_prompt_t,
                            completion_tokens=_comp_t,
                            total_tokens=_total,
                            created_at=datetime.now(timezone.utc),
                        )
                        _slr_db.session.add(_log_entry)
                        _slr_user = _SlrUser.query.get(int(job.user_id))
                        if _slr_user and _slr_user.role != "admin":
                            _now = datetime.now(timezone.utc)
                            _mk = _now.strftime("%Y-%m")
                            if (_slr_user.usage_month_key or "") != _mk:
                                _slr_user.usage_month_key = _mk
                                _slr_user.token_used_month = 0
                            _slr_user.token_used_month = int(_slr_user.token_used_month or 0) + _total
                        _slr_commit()
                        log.info("SLR_TOKEN_DEDUCT user=%d job=%s prompt=%d comp=%d total=%d",
                                 job.user_id, job.job_id, _prompt_t, _comp_t, _total)
                else:
                    # fallback: no current_app, try main app
                    try:
                        from main import app as _main_app
                        with _main_app.app_context():
                            from utils.database.models import ApiUsageLog, User as _SlrUser
                            from utils.database.models import db as _slr_db, safe_commit as _slr_commit
                            _prompt_t = max(1, len(keyword) // 4)
                            _comp_t = 0
                            _total = _prompt_t
                            if summarize_llm is not None:
                                _prompt_t = min(8000, max(1, (len(keyword) + top_n * 400) // 4))
                                _comp_t = max(1, (top_n * 200) // 4)
                                _total = _prompt_t + _comp_t
                            _log_entry = ApiUsageLog(
                                user_id=int(job.user_id),
                                endpoint="/api/papers/slr/jobs",
                                model="slr-orchestrator",
                                prompt_tokens=_prompt_t,
                                completion_tokens=_comp_t,
                                total_tokens=_total,
                                created_at=datetime.now(timezone.utc),
                            )
                            _slr_db.session.add(_log_entry)
                            _slr_user = _SlrUser.query.get(int(job.user_id))
                            if _slr_user and _slr_user.role != "admin":
                                _now = datetime.now(timezone.utc)
                                _mk = _now.strftime("%Y-%m")
                                if (_slr_user.usage_month_key or "") != _mk:
                                    _slr_user.usage_month_key = _mk
                                    _slr_user.token_used_month = 0
                                _slr_user.token_used_month = int(_slr_user.token_used_month or 0) + _total
                            _slr_commit()
                            log.info("SLR_TOKEN_DEDUCT user=%d job=%s prompt=%d comp=%d total=%d",
                                     job.user_id, job.job_id, _prompt_t, _comp_t, _total)
                    except Exception as _te2:
                        log.warning("SLR_TOKEN_DEDUCT_FAILED user=%d job=%s (fallback): %s",
                                    job.user_id, job.job_id, _te2)
            except Exception as _te:
                log.warning("SLR_TOKEN_DEDUCT_FAILED user=%d job=%s: %s",
                            job.user_id, job.job_id, _te)

        except Exception as exc:
            log.exception("SLR pipeline failed for job %s", job.job_id)
            self._set_error(job, f"Pipeline error: {exc}")

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _compute_eta(job: SLRJob) -> tuple[int | None, str]:
        """Compute ETA using simple linear extrapolation."""
        # Guard: no ETA at the very start (elapsed too small → huge noisy estimate)
        if job.progress_pct <= 1.0 or job.progress_pct >= 100:
            return None, ""
        try:
            started = datetime.fromisoformat(job.started_at.replace('Z', '+00:00'))
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            if elapsed <= 0:
                return None, ""
            eta_seconds = min(int((elapsed / job.progress_pct) * (100.0 - job.progress_pct)), 7200)
            if eta_seconds < 60:
                return eta_seconds, f"{eta_seconds} detik"
            if eta_seconds < 3600:
                mins, secs = divmod(eta_seconds, 60)
                return eta_seconds, f"{mins}m {secs}s" if secs else f"{mins} menit"
            hours, rest = divmod(eta_seconds, 3600)
            mins = rest // 60
            return eta_seconds, f"{hours}j {mins}m" if mins else f"{hours} jam"
        except Exception:
            return None, ""

    def _set_stage(
        self, job: SLRJob, stage: str, pct: float, detail: str,
        extra: dict | None = None,
    ):
        with _jobs_lock:
            job.stage = stage
            job.progress_pct = pct
            job.stage_detail = detail
            # Only set status during terminal stages; intermediate stages keep "running"
            if stage in ("done", "error", "cancelled"):
                job.status = stage
            elif job.status not in ("done", "error", "cancelled"):
                job.status = "running"
            if extra:
                for k, v in extra.items():
                    setattr(job, k, v)
            job.eta_seconds, job.eta_display = self._compute_eta(job)
        _push_progress(job)
        # Persist to DB on every stage update so frontend sees real-time progress
        # (Redis push above is fast, DB write ~5-10ms, acceptable overhead)
        _persist_job_to_db(job)

    def _set_error(self, job: SLRJob, msg: str):
        with _jobs_lock:
            job.status = "error"
            job.stage = "error"
            job.error = msg
        _push_progress(job)
        _persist_job_to_db(job)  # persist error state

    @staticmethod
    def _fallback_summarize(paper_dicts: list[dict], keyword: str, top_n: int) -> dict:
        """Fallback when slrSummarize fails — fast rank only (assumes upstream already deduped)."""
        from tools.Literatur.slrSummarize import programmatic_rank

        try:
            ranked = programmatic_rank(paper_dicts, keyword)
            top = ranked[:top_n]
            return {
                "total_fetched": len(paper_dicts),
                "total_unique": len(paper_dicts),
                "total_returned": len(top),
                "groups": [{"label": "All Results", "description": "Ranked papers", "count": len(top), "papers": top}],
                "method_distribution": {"All Results": len(top)},
                "statistics": {},
            }
        except Exception:
            return {
                "total_fetched": len(paper_dicts),
                "total_unique": len(paper_dicts),
                "total_returned": min(len(paper_dicts), top_n),
                "groups": [{"label": "All Results", "description": "", "count": min(len(paper_dicts), top_n), "papers": paper_dicts[:top_n]}],
                "method_distribution": {"All Results": min(len(paper_dicts), top_n)},
                "statistics": {},
            }

    @staticmethod
    def _save_to_db(job: SLRJob, papers: list[dict]):
        """Save SLR results as LiteratureItem records (best-effort, non-blocking)."""
        log.debug("_save_to_db called: job_id=%s, papers=%d", job.job_id, len(papers))
        
        try:
            from sqlalchemy.exc import IntegrityError
        except ImportError:
            log.debug("SQLAlchemy not available, skipping DB save")
            return

        ctx = None
        try:
            try:
                from flask import current_app
                if current_app and hasattr(current_app, 'app_context'):
                    ctx = current_app.app_context()
                    ctx.push()
                else:
                    raise RuntimeError("No current_app")
            except (RuntimeError, ImportError):
                try:
                    from main import app as _flask_app
                    ctx = _flask_app.app_context()
                    ctx.push()
                except ImportError as e:
                    log.error("Flask app unavailable, skipping DB save: %s", e)
                    return
        except Exception as e:
            log.error("Failed to push Flask app context: %s", e)
            return

        try:
            from utils.database.models import LiteratureItem, db, safe_commit

            saved = 0
            skipped = 0
            
            for p in papers:
                try:
                    doi = (p.get("doi") or "").strip() or None
                    title = (p.get("title") or "").strip()
                    abstract = (p.get("abstract") or p.get("review") or "").strip()
                    review = _limit_words((p.get("review") or "").strip(), 50)
                    summary = (review or _limit_words(abstract, 50) or _limit_words(title, 50))
                    gap = (p.get("gap_riset") or p.get("gap") or _make_gap_riset(
                        title=title,
                        abstract=abstract,
                        query=job.keyword or "",
                    ))[:1000]
                    title_norm = re.sub(r'[^a-z0-9]+', '', title.lower()) or None

                    # Debug missing year source
                    year_raw = p.get("year")
                    if title and not year_raw:
                        log.debug("SLR missing year for paper: %s", title[:80])

                    existing = None
                    if doi:
                        existing = db.session.query(LiteratureItem).filter_by(
                            paper_id=job.paper_id, doi=doi
                        ).first()
                    if existing is None and title_norm:
                        existing = db.session.query(LiteratureItem).filter_by(
                            paper_id=job.paper_id, title_norm=title_norm
                        ).first()
                    if existing:
                        if abstract and not (existing.abstract or "").strip():
                            existing.abstract = abstract[:3000]
                        if summary and not (existing.summary or "").strip():
                            existing.summary = summary
                        if review and not (existing.review or "").strip():
                            existing.review = review
                        if gap and not (existing.gap_riset or "").strip():
                            existing.gap_riset = gap
                        # Always update relevance score for final ranked papers
                        if p.get("relevance_score") is not None:
                            existing.score_total = p.get("relevance_score")
                        existing.slr_job_id = job.job_id
                        skipped += 1
                        continue

                    item = LiteratureItem(
                        paper_id=job.paper_id,
                        user_id=job.user_id,
                        source_kind="slr",
                        source=(p.get("source") or "slr")[:40],
                        title=(p.get("title") or "").strip(),
                        title_norm=re.sub(r'[^a-z0-9]+', '', (p.get("title") or "").strip().lower()) or None,
                        authors=p.get("authors") or [],
                        year=(p.get("year") or p.get("publication_year")),
                        doi=doi,
                        url=p.get("url") or None,
                        pdf_url=p.get("pdf_url") or None,
                        abstract=(p.get("abstract") or p.get("review") or "").strip()[:3000],
                        review=_limit_words((p.get("review") or "").strip(), 50),
                        summary=(_limit_words((p.get("review") or "").strip(), 50) or _limit_words((p.get("abstract") or "").strip(), 50) or _limit_words((p.get("title") or "").strip(), 50)),
                        gap_riset=_make_gap_riset(
                            title=(p.get("title") or "").strip(),
                            abstract=(p.get("abstract") or p.get("review") or "").strip(),
                            query=job.keyword or "",
                        ),
                        citations=p.get("citations"),
                        score_total=p.get("relevance_score"),
                        score_breakdown=p.get("score_breakdown", {}),
                        notes=(p.get("summary") or "")[:1000],
                        is_checked=False,
                        slr_job_id=job.job_id,
                        created_at=datetime.now(timezone.utc),
                    )
                    db.session.add(item)
                    try:
                        db.session.flush()
                    except IntegrityError:
                        db.session.rollback()
                        skipped += 1
                        continue
                    saved += 1
                    if saved >= 500:
                        break
                except Exception as e:
                    db.session.rollback()
                    log.warning("Error creating LiteratureItem for paper %s: %s", p.get("title", "?")[:30], e)
                    continue

            if saved > 0:
                try:
                    safe_commit()
                    log.info(
                        "SLR saved %d LiteratureItems (skipped %d) for paper %s job %s",
                        saved, skipped, job.paper_id, job.job_id,
                    )
                except IntegrityError as e:
                    db.session.rollback()
                    log.warning(
                        "IntegrityError saving LiteratureItems for job %s: %s",
                        job.job_id, e,
                    )
                except Exception as e:
                    db.session.rollback()
                    log.error("Failed to commit LiteratureItems for job %s: %s", job.job_id, e, exc_info=True)
            else:
                log.debug("No new papers to save (all skipped or filtered)")
                
        except Exception as exc:
            log.error("_save_to_db outer error: %s", exc, exc_info=True)
        finally:
            if ctx:
                try:
                    ctx.pop()
                    log.debug("Flask app context popped")
                except Exception as e:
                    log.warning("Error popping Flask app context: %s", e)

    @staticmethod
    def _fetch_single_source(
        source_name: str,
        query: str,
        limit: int,
        filters: dict | None,
    ) -> list[Paper]:
        """Execute a single fetcher with rate limiting.

        Creates its own httpx.Client. Returns list of Paper objects.
        On any error, returns empty list.
        """
        fetcher_mod = FETCHER_ALL.get(source_name)
        if fetcher_mod is None or not hasattr(fetcher_mod, "search"):
            log.warning("Fetcher %s has no search function; skipping", source_name)
            return []

        # Get or create per-fetcher rate limiter
        rate_limiters = _get_rate_limiters()
        limiter = rate_limiters.get(source_name)
        if limiter is None:
            limiter = RateLimiter(min_interval=3.0)
            rate_limiters[source_name] = limiter

        try:
            with get_client() as client:
                limiter.wait()
                papers = list(fetcher_mod.search(client, query, limit, filters))
                return papers
        except Exception as exc:
            log.debug("Fetcher %s error: %s", source_name, exc)
            return []


# ── Global instance ──────────────────────────────────────────────────────

_orchestrator = SLROrchestrator()


def _get_slr_job_data(job_id: str) -> dict | None:
    """Internal helper: get job status from orchestrator."""
    return _orchestrator.get_job(job_id)


def _get_slr_summary_data(job_id: str) -> dict | None:
    """Internal helper: get grouped/summarized results from orchestrator."""
    return _orchestrator.get_job_summary(job_id)


# ── Flask endpoints ───────────────────────────────────────────────────────

@slr_api.route("/api/papers/<paper_id>/slr/orch", methods=["POST"])
@jwt_required()
def slr_start(paper_id):
    """Start a new SLR job via orchestrator v3.

    Body (JSON):
    {
        "query": "keyword search term",
        "top_k": 10,
        "sources": ["openalex", "crossref"],  # optional
        "year_from": 2020,                     # optional
        "ai_summarize": false                  # optional
    }

    Returns:
        {job_id: "slr_abc123", status: "started"}
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    ok, retry_after = _check_rate_limit(user_id, "create_slr_job")
    if not ok:
        return jsonify({"error": "Rate limit", "code": "RATE_LIMITED", "retry_after": retry_after}), 429

    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    query = (data.get("query") or data.get("topic") or "").strip()
    if not query:
        return _err("query is required", "QUERY_REQUIRED", 400)

    top_k = int(data.get("top_k", data.get("top_n", 10)))
    sources = data.get("sources") or None
    year_from = data.get("year_from")
    year_to = data.get("year_to")
    ai_summarize = bool(data.get("ai_summarize", False))
    per_source = _safe_per_source(data.get("per_source"))

    if top_k < 1:
        top_k = 10
    if top_k > 200:
        top_k = 200

    # Validate year range
    if year_from and year_to and year_to < year_from:
        return _err("year_to must be >= year_from", "YEAR_RANGE_INVALID", 400)

    log.info("slr.orch.create user=%d paper=%s query=%s top_k=%d", user_id, paper_id, query[:60], top_k)

    job_id = _orchestrator.start_job(
        paper_id=paper_id, keyword=query, top_n=top_k,
        user_id=user_id, sources=sources,
        year_from=year_from, year_to=year_to, ai_summarize=ai_summarize,
        per_source=per_source,
    )

    return jsonify({
        "id": job_id,
        "job_id": job_id,
        "status": "started",
        "poll_url": f"/api/slr/jobs/{job_id}",
    }), 202


@slr_api.route("/api/slr/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_slr_job(job_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    if not JOB_ID_RE.match(job_id):
        return _err("Invalid job id", "JOB_ID_INVALID", 400)
    include_result = request.args.get("include_result", "false").lower() == "true"
    # Check DB-backed SlrJob first
    job = db.session.query(SlrJob).filter_by(id=job_id, user_id=user_id).first()
    if job:
        return jsonify(job.to_dict(include_result=include_result))
    # Check orchestrator v3 in-memory/Redis jobs
    orch_job = _orchestrator.get_job(job_id)
    if orch_job:
        # Verify owner to prevent cross-user disclosure
        if str(orch_job.get("user_id") or "") != str(user_id):
            return _err("Job not found", "JOB_NOT_FOUND", 404)
        return jsonify(orch_job)
    return _err("Job not found", "JOB_NOT_FOUND", 404)


@slr_api.route("/api/slr/jobs/<job_id>/summary", methods=["GET"])
@jwt_required()
def slr_summary(job_id):
    """Get grouped/summarized results for a completed orchestrator SLR job."""
    user_id = _current_user_id()
    if not user_id:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    if not JOB_ID_RE.match(job_id):
        return _err("Invalid job id", "JOB_ID_INVALID", 400)
    job_data = _get_slr_job_data(job_id)
    if job_data is None:
        return _err("Job not found", "JOB_NOT_FOUND", 404)
    # Verify ownership for orchestrator jobs
    if "user_id" in job_data and str(job_data["user_id"]) != str(user_id):
        return _err("Job not found", "JOB_NOT_FOUND", 404)
    if job_data.get("status") != "done":
        return jsonify({"error": "Job not yet complete", "status": job_data.get("status"), "progress": job_data.get("progress", 0)}), 202
    summary = _get_slr_summary_data(job_id)
    if summary is None:
        embedded = job_data.get("summary_result")
        if embedded:
            return jsonify(embedded)
        return jsonify({"error": "No summary available"}), 404
    return jsonify(summary)


@slr_api.route("/api/slr/jobs/<job_id>", methods=["DELETE"])
@jwt_required()
def cancel_slr_job(job_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    if not JOB_ID_RE.match(job_id):
        return _err("Invalid job id", "JOB_ID_INVALID", 400)
    # Try DB-backed SlrJob first
    job = db.session.query(SlrJob).filter_by(id=job_id, user_id=user_id).first()
    if job:
        log.info("slr.cancel user=%d job=%s status=%s", user_id, job.id, job.status)
        if job.status in ("queued", "running", "pending"):
            # Cancel both DB row and in-memory orchestrator. DB-only cancel leaves
            # the worker running until it writes progress again after refresh.
            # ponytail: current summarize call cannot be killed mid-request; it exits at next checkpoint.
            try:
                _orchestrator.cancel_job(job_id)
            except Exception:
                pass
            job.status = "cancelled"
            job.stage = "cancelled"
            job.progress_message = "Cancelled by user"
            job.finished_at = datetime.now(timezone.utc)
            try:
                safe_commit()
            except Exception:
                db.session.rollback()
                return _err("cancel failed", "JOB_CANCEL_FAILED", 500)
            return jsonify({"id": job.id, "status": "cancelled"}), 200
        elif job.status in ("done", "error", "cancelled"):
            kids = db.session.query(LiteratureItem).filter_by(slr_job_id=job.id).count()
            if kids:
                db.session.query(LiteratureItem).filter_by(slr_job_id=job.id).update(
                    {"slr_job_id": None}, synchronize_session=False
                )
            try:
                db.session.delete(job)
                safe_commit()
            except Exception:
                db.session.rollback()
                return _err("delete failed", "JOB_DELETE_FAILED", 500)
            return jsonify({"deleted": True}), 200
        return _err(f"unknown status {job.status}", "JOB_STATUS_UNKNOWN", 400)
    # Try orchestrator v3 / Redis snapshot cleanup. A hard refresh can leave
    # a Redis-only running card even when the DB row is gone.
    try:
        _orchestrator.cancel_job(job_id)
    except Exception:
        pass
    if _redis_client is not None:
        try:
            raw = _redis_client.get(f"slr_new:{job_id}")
            if raw:
                d = json.loads(raw)
                if d.get("user_id") == user_id:
                    paper_id = d.get("paper_id")
                    if paper_id:
                        _redis_client.srem(f"slr_new:paper:{paper_id}:{user_id}", job_id)
                    _redis_client.delete(f"slr_new:{job_id}")
                    return jsonify({"id": job_id, "status": "cancelled", "deleted_stale": True}), 200
        except Exception:
            pass
    return _err("Job not found", "JOB_NOT_FOUND", 404)


# ── End of slr.py ─────────────────────────────────────────────────────────
