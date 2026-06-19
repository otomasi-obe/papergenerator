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

import logging
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import redis
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import defer

from database.models import LiteratureItem, Paper, PaperFile, SlrJob, db, safe_commit
from tools.editor.utils import PAPER_ID_RE
from tools.Literatur.worker import enqueue_slr_job
from utils.ai_tools.model_config import get_primary_generate_model

log = logging.getLogger(__name__)
slr_api = Blueprint("slr_api", __name__)

JOB_ID_RE = re.compile(r"^[A-Za-z0-9]{6,32}$")

# Redis client for cross-process rate limiting.
# Falls back to in-memory if Redis unavailable.
_redis_client: redis.Redis | None = None
try:
    _redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=0,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
    _redis_client.ping()
except Exception:
    log.warning("Redis unavailable for rate limiter, falling back to in-memory")
    _redis_client = None


# ─── Prompt-injection sanitizer ──────────────────────────────────────────

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
_RATE_BUCKETS: "defaultdict[tuple[int, str], list[float]]" = defaultdict(list)
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

    # In-memory fallback REMOVED — multi-worker unsafe. Hard-reject when Redis down.
    return False, -1


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

    sources = body.get("sources") or None
    if sources is not None and not isinstance(sources, list):
        return _err("sources must be a list", "SOURCES_INVALID", 400)

    per_source = _safe_per_source(body.get("per_source"))
    top_k = _safe_top_k(body.get("top_k"))

    # N×10 fetch strategy: ambil top_k × 10 paper untuk AI re-ranking
    # Jika user tidak set per_source eksplisit, scale otomatis
    if not body.get("per_source"):
        default_source_count = 5  # OpenAlex, Crossref, arXiv, IEEE, SINTA
        active_sources = sources if sources else None
        source_count = max(len(active_sources) if active_sources else default_source_count, 1)
        n_x10 = top_k * 10
        per_source = max(per_source, (n_x10 // source_count) + 1)

    year_from, year_err = _validate_year(body.get("year_from"))
    if year_err:
        return year_err

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

    job = enqueue_slr_job(
        paper_id=paper_id,
        user_id=user_id,
        conversation_id=conv_id,
        query=query,
        sources=sources,
        per_source=per_source,
        top_k=top_k,
        year_from=year_from,
        ai_summarize=ai_summarize,
        ai_model=ai_model,
    )
    return jsonify(job.to_dict()), 202


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
        return jsonify([j.to_dict() for j in jobs])
    except (OperationalError, DBAPIError) as e:
        # Postgres busy / lock timeout / connection blip → tell the frontend
        # to back off and retry instead of bubbling up as a 500/524.
        db.session.rollback()
        log.warning("slr.list_jobs DB busy paper=%s: %s", paper_id, e)
        return jsonify({"error": "DB busy, retry", "code": "DB_BUSY"}), 503


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
            if ts > after:
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
                return jsonify(
                    {
                        "jobs": [j.to_dict() for j in jobs],
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


@slr_api.route("/api/slr/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_slr_job(job_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    if not JOB_ID_RE.match(job_id):
        return _err("Invalid job id", "JOB_ID_INVALID", 400)
    include_result = request.args.get("include_result", "false").lower() == "true"
    job = db.session.query(SlrJob).filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return _err("Job not found", "JOB_NOT_FOUND", 404)
    return jsonify(job.to_dict(include_result=include_result))


@slr_api.route("/api/slr/jobs/<job_id>", methods=["DELETE"])
@jwt_required()
def cancel_slr_job(job_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    if not JOB_ID_RE.match(job_id):
        return _err("Invalid job id", "JOB_ID_INVALID", 400)
    job = db.session.query(SlrJob).filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return _err("Job not found", "JOB_NOT_FOUND", 404)
    log.info("slr.cancel user=%d job=%s status=%s", user_id, job.id, job.status)
    if job.status in ("queued", "running"):
        job.status = "cancelled"
        job.stage = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        try:
            safe_commit()
        except Exception:
            db.session.rollback()
            log.exception("slr.cancel commit failed job=%s", job.id)
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
                    f"File too large ({file_size / (1024*1024):.1f}MB). Maximum allowed is 30MB per file.",
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

    # N×10 fetch strategy: ambil top_k × 10 paper untuk AI re-ranking
    if not body.get("per_source"):
        default_source_count = 5
        active_sources = body.get("sources") or None
        source_count = max(len(active_sources) if active_sources else default_source_count, 1)
        n_x10 = top_k * 10
        per_source = max(per_source, (n_x10 // source_count) + 1)

    year_from, year_err = _validate_year(body.get("year_from"))
    if year_err:
        return year_err

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
            host="localhost",
            dbname="paper_database",
            user="sirobo",
            password="paper2026",
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
