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

The legacy `POST /api/papers/<paper_id>/slr` is now async-only: it enqueues
a job and returns 202 + job_id immediately. Callers must poll
`GET /api/slr/jobs/<job_id>` for status and results.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import defer

from database.models import LiteratureItem, Paper, PaperFile, SlrJob, db
from paper_generation.utils import PAPER_ID_RE
from workers.slr_worker import enqueue_slr_job

log = logging.getLogger(__name__)
slr_bp = Blueprint("slr", __name__)

JOB_ID_RE = re.compile(r"^[A-Za-z0-9]{6,32}$")

_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s]+$")
_URL_RE = re.compile(r"^(https?://|/)", re.IGNORECASE)

_VALID_SOURCE_KINDS = {"slr", "manual", "file"}
_VALID_JOB_STATUSES = {"queued", "running", "done", "error", "cancelled"}

# In-memory token bucket for rate limiting. Keyed by (user_id, endpoint).
# Each value is a list of unix-epoch timestamps (floats) of recent requests
# within the current 60-second window. Sufficient for single-process Flask;
# replaced by a real limiter (F-28) when sharing across workers becomes
# necessary.
_RATE_BUCKETS: "defaultdict[tuple[int, str], list[float]]" = defaultdict(list)
_RATE_WINDOW_SEC = 60.0
_RATE_MAX_REQUESTS = 10


def _err(message: str, code: str, status: int):
    """Build a JSON error response with stable `code` for frontend i18n."""
    return jsonify({"error": message, "code": code}), status


def _check_rate_limit(
    user_id: int,
    endpoint: str,
    max_requests: int = _RATE_MAX_REQUESTS,
    window_sec: float = _RATE_WINDOW_SEC,
):
    """Simple per-user token bucket. Returns (ok, retry_after_seconds)."""
    now = time.monotonic()
    key = (user_id, endpoint)
    bucket = _RATE_BUCKETS[key]
    cutoff = now - window_sec
    # drop expired timestamps
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)

    # Cleanup: remove empty buckets to prevent memory leak
    if not bucket and key in _RATE_BUCKETS:
        del _RATE_BUCKETS[key]
        return True, 0

    if len(bucket) >= max_requests:
        retry_after = max(1, int(window_sec - (now - bucket[0])) + 1)
        return False, retry_after
    bucket.append(now)
    return True, 0


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


@slr_bp.route("/api/papers/<paper_id>/slr/jobs", methods=["POST"])
@jwt_required()
def create_slr_job(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)

    # F-28: simple per-user in-memory rate limit (10 jobs/minute).
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
    query = (body.get("query") or body.get("topic") or "").strip()
    if not query:
        return _err("query is required", "QUERY_REQUIRED", 400)

    sources = body.get("sources") or None
    if sources is not None and not isinstance(sources, list):
        return _err("sources must be a list", "SOURCES_INVALID", 400)

    per_source = _safe_per_source(body.get("per_source"))
    top_k = _safe_top_k(body.get("top_k"))
    year_from, year_err = _validate_year(body.get("year_from"))
    if year_err:
        return year_err

    ai_summarize = bool(body.get("ai_summarize", True))
    ai_model = (body.get("ai_model") or os.getenv("MODELGENERATE") or "VIOLA-GENERATE").strip()
    if ai_model not in {"VIOLA-CHAT", "VIOLA-GENERATE"}:
        ai_model = os.getenv("MODELGENERATE") or "VIOLA-GENERATE"

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


@slr_bp.route("/api/papers/<paper_id>/slr/jobs", methods=["GET"])
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


@slr_bp.route("/api/papers/<paper_id>/slr/jobs/wait", methods=["GET"])
@jwt_required()
def wait_slr_jobs(paper_id: str):
    """Long-poll for SlrJob changes for this paper.

    Holds the connection for up to 30 s, returning as soon as `max(updated_at)`
    moves past the caller's `?after=<unix_ts>` cursor. Frontend uses this to
    avoid hammering the DB with 2-3 s polls — and to dodge the proxy 524 the
    cheap polls were causing under load.
    """
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    try:
        after = float(request.args.get("after", "0"))
    except (TypeError, ValueError):
        after = 0.0

    deadline = time.monotonic() + 30.0
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


@slr_bp.route("/api/slr/jobs/<job_id>", methods=["GET"])
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


@slr_bp.route("/api/slr/jobs/<job_id>", methods=["DELETE"])
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
            db.session.commit()
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
            db.session.commit()
        except Exception:
            db.session.rollback()
            return _err("delete failed", "JOB_DELETE_FAILED", 500)
        return jsonify({"deleted": True}), 200
    return _err(f"unknown status {job.status}", "JOB_STATUS_UNKNOWN", 400)


# ─── LITERATURE ITEMS ─────────────────────────────────────────────────────


@slr_bp.route("/api/papers/<paper_id>/literature", methods=["GET"])
@jwt_required()
def list_literature(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    base_q = (
        db.session.query(LiteratureItem)
        .filter_by(paper_id=paper_id, user_id=user_id)
        .order_by(
            LiteratureItem.pinned.desc(),
            LiteratureItem.score_total.desc(),
            LiteratureItem.created_at.desc(),
        )
    )

    # Backward-compat: only switch to paginated wrapper when caller actually
    # passes `page` or `page_size`. Otherwise return the original flat list.
    page_arg = request.args.get("page")
    size_arg = request.args.get("page_size")
    if page_arg is None and size_arg is None:
        return jsonify([i.to_dict() for i in base_q.all()])

    try:
        page = int(page_arg) if page_arg is not None else 1
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(size_arg) if size_arg is not None else 50
    except (TypeError, ValueError):
        page_size = 50
    page = max(1, page)
    page_size = max(1, min(page_size, 200))

    total = base_q.count()
    items = base_q.offset((page - 1) * page_size).limit(page_size).all()
    return jsonify(
        {
            "items": [i.to_dict() for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@slr_bp.route("/api/papers/<paper_id>/literature", methods=["POST"])
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

    item = LiteratureItem(
        paper_id=paper_id,
        user_id=user_id,
        source_kind=source_kind,
        source=(body.get("source") or "")[:40],
        title=title[:1000],
        authors=body.get("authors") or [],
        year=year_value,
        venue=(body.get("venue") or "")[:500],
        publisher=(body.get("publisher") or "")[:500],
        doi=doi_norm,
        url=url_norm,
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
    db.session.commit()
    return jsonify(item.to_dict()), 201


@slr_bp.route("/api/papers/<paper_id>/literature/<int:item_id>", methods=["PATCH"])
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
        "abstract",
        "summary",
        "citations",
        "must_read",
        "is_relevant",
        "notes",
        "pinned",
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
        elif k in ("must_read", "is_relevant", "pinned"):
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
        setattr(item, k, v)
    db.session.commit()
    return jsonify(item.to_dict())


@slr_bp.route("/api/papers/<paper_id>/literature/<int:item_id>", methods=["DELETE"])
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
    db.session.commit()
    return jsonify({"ok": True})


@slr_bp.route("/api/papers/<paper_id>/literature/bulk-delete", methods=["POST"])
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
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("slr.literature.bulk_delete commit failed paper=%s", paper_id)
        return _err("bulk delete failed", "LITERATURE_BULK_DELETE_FAILED", 500)
    return jsonify({"deleted": deleted})


@slr_bp.route("/api/papers/<paper_id>/literature/bulk-patch", methods=["POST"])
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

    allowed_fields = {"pinned", "must_read", "is_relevant"}
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
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("slr.literature.bulk_patch commit failed paper=%s", paper_id)
        return _err("bulk patch failed", "LITERATURE_BULK_PATCH_FAILED", 500)
    return jsonify({"updated": int(updated or 0)})


@slr_bp.route("/api/papers/<paper_id>/literature/from-files", methods=["POST"])
@jwt_required()
def import_from_files(paper_id: str):
    """Buat satu LiteratureItem per file PaperFile (yang sudah punya
    extracted_text). Aman dipanggil berkali-kali — kita skip kalau file_id
    sudah pernah diimport."""
    user_id = _current_user_id()
    if user_id is None:
        return _err("Unauthorized", "UNAUTHORIZED", 401)
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    files = (
        PaperFile.query.filter_by(paper_id=paper_id, user_id=user_id)
        .order_by(PaperFile.created_at.desc())
        .all()
    )
    existing_file_ids = {
        i.file_id
        for i in db.session.query(LiteratureItem)
        .filter_by(paper_id=paper_id)
        .filter(LiteratureItem.file_id.isnot(None))
        .all()
    }
    created = []
    for f in files:
        if f.id in existing_file_ids:
            continue
        excerpt = (f.extracted_text or "").strip()
        # Use first non-empty line as title; cap.
        title = excerpt.split("\n", 1)[0] if excerpt else f.original_name
        title = (title or f.original_name)[:300]
        item = LiteratureItem(
            paper_id=paper_id,
            user_id=user_id,
            source_kind="file",
            source=f.ext.lstrip("."),
            title=title,
            authors=[],
            year=None,
            venue="",
            publisher="",
            doi=None,
            url=f"/api/papers/{paper_id}/files/{f.id}/preview",
            abstract=excerpt[:3000],
            summary=excerpt[:600],
            file_id=f.id,
            pinned=True,
        )
        db.session.add(item)
        created.append(item)
    db.session.commit()
    return jsonify({"created": [i.to_dict() for i in created]})


# ─── Legacy /slr endpoint (now async-only) ────────────────────────────────


@slr_bp.route("/api/papers/<paper_id>/slr", methods=["POST"])
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
        top_k = max(10, min(int(body.get("top_k", body.get("limit", 50))), 100))
    except (TypeError, ValueError):
        top_k = 50
    per_source = _safe_per_source(body.get("per_source"))
    year_from, year_err = _validate_year(body.get("year_from"))
    if year_err:
        return year_err

    ai_model = (body.get("ai_model") or os.getenv("MODELGENERATE") or "VIOLA-GENERATE").strip()
    if ai_model not in {"VIOLA-CHAT", "VIOLA-GENERATE"}:
        ai_model = os.getenv("MODELGENERATE") or "VIOLA-GENERATE"
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
        return default
    return max(10, min(k, 100))


def _safe_per_source(value, default=60):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(10, min(n, 100))
