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

The legacy synchronous `POST /api/papers/<paper_id>/slr` is kept as a thin
wrapper that enqueues a job and waits up to 25 s for it to finish so old
callers (chat tools / tests) keep working. New callers should use the job
endpoints.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from models import (LiteratureItem, Paper, PaperFile, ProjectMemory, SlrJob,
                    db)
from paper_utils import PAPER_ID_RE
from slr_worker import enqueue_slr_job

log = logging.getLogger(__name__)
slr_bp = Blueprint("slr", __name__)

JOB_ID_RE = re.compile(r"^[A-Za-z0-9]{6,32}$")


def _current_user_id() -> int | None:
    raw = get_jwt_identity()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _paper_or_404(paper_id: str, user_id: int):
    if not PAPER_ID_RE.match(paper_id):
        return None, (jsonify({"error": "Invalid paper id"}), 400)
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return None, (jsonify({"error": "Paper not found"}), 404)
    return paper, None


# ─── SLR JOBS ─────────────────────────────────────────────────────────────

@slr_bp.route("/api/papers/<paper_id>/slr/jobs", methods=["POST"])
@jwt_required()
def create_slr_job(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    query = (body.get("query") or body.get("topic") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    sources = body.get("sources") or None
    if sources is not None and not isinstance(sources, list):
        return jsonify({"error": "sources must be a list"}), 400

    try:
        per_source = max(10, min(int(body.get("per_source", 60)), 100))
    except (TypeError, ValueError):
        per_source = 60
    try:
        top_k = max(10, min(int(body.get("top_k", 50)), 100))
    except (TypeError, ValueError):
        top_k = 50
    try:
        year_from = int(body["year_from"]) if body.get("year_from") else None
    except (TypeError, ValueError):
        year_from = None

    ai_summarize = bool(body.get("ai_summarize", True))
    ai_model = (body.get("ai_model") or "V-OPUS").strip()
    if ai_model not in {"V-OPUS", "V-CLAUDE", "V-GPT", "V-GLM"}:
        ai_model = "V-OPUS"

    conv_id = body.get("conversation_id") or None

    job_id = enqueue_slr_job(
        paper_id=paper_id, user_id=user_id,
        conversation_id=conv_id,
        query=query, sources=sources,
        per_source=per_source, top_k=top_k, year_from=year_from,
        ai_summarize=ai_summarize, ai_model=ai_model,
    )
    job = SlrJob.query.filter_by(id=job_id).first()
    return jsonify(job.to_dict() if job else {"id": job_id}), 202


@slr_bp.route("/api/papers/<paper_id>/slr/jobs", methods=["GET"])
@jwt_required()
def list_slr_jobs(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    jobs = (SlrJob.query
            .filter_by(paper_id=paper_id, user_id=user_id)
            .order_by(SlrJob.queued_at.desc())
            .limit(30)
            .all())
    return jsonify([j.to_dict() for j in jobs])


@slr_bp.route("/api/slr/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_slr_job(job_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    if not JOB_ID_RE.match(job_id):
        return jsonify({"error": "Invalid job id"}), 400
    include_result = request.args.get("include_result", "false").lower() == "true"
    job = SlrJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict(include_result=include_result))


@slr_bp.route("/api/slr/jobs/<job_id>", methods=["DELETE"])
@jwt_required()
def cancel_slr_job(job_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    if not JOB_ID_RE.match(job_id):
        return jsonify({"error": "Invalid job id"}), 400
    job = SlrJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.status in ("queued", "running"):
        job.status = "cancelled"
        job.stage = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
    db.session.delete(job)
    db.session.commit()
    return jsonify({"ok": True})


# ─── LITERATURE ITEMS ─────────────────────────────────────────────────────

@slr_bp.route("/api/papers/<paper_id>/literature", methods=["GET"])
@jwt_required()
def list_literature(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    items = (LiteratureItem.query
             .filter_by(paper_id=paper_id)
             .order_by(LiteratureItem.pinned.desc(),
                       LiteratureItem.score_total.desc(),
                       LiteratureItem.created_at.desc())
             .all())
    return jsonify([i.to_dict() for i in items])


@slr_bp.route("/api/papers/<paper_id>/literature", methods=["POST"])
@jwt_required()
def create_literature(paper_id: str):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    item = LiteratureItem(
        paper_id=paper_id,
        user_id=user_id,
        source_kind=(body.get("source_kind") or "manual")[:20],
        source=(body.get("source") or "")[:40],
        title=title[:1000],
        authors=body.get("authors") or [],
        year=_safe_int(body.get("year")),
        venue=(body.get("venue") or "")[:500],
        publisher=(body.get("publisher") or "")[:500],
        doi=(body.get("doi") or None),
        url=(body.get("url") or "")[:1000],
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
        return jsonify({"error": "Unauthorized"}), 401
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    item = LiteratureItem.query.filter_by(id=item_id, paper_id=paper_id).first()
    if not item:
        return jsonify({"error": "Literature item not found"}), 404

    body = request.get_json(silent=True) or {}
    editable = {
        "title", "authors", "year", "venue", "publisher", "doi", "url",
        "abstract", "summary", "citations", "must_read", "is_relevant",
        "notes", "pinned", "source", "source_kind",
    }
    for k, v in body.items():
        if k not in editable:
            continue
        if k == "year":
            v = _safe_int(v)
        elif k == "citations":
            v = _safe_int(v)
        elif k in ("must_read", "is_relevant", "pinned"):
            v = bool(v)
        elif k == "authors":
            if not isinstance(v, list):
                continue
        setattr(item, k, v)
    db.session.commit()
    return jsonify(item.to_dict())


@slr_bp.route("/api/papers/<paper_id>/literature/<int:item_id>", methods=["DELETE"])
@jwt_required()
def delete_literature(paper_id: str, item_id: int):
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err
    item = LiteratureItem.query.filter_by(id=item_id, paper_id=paper_id).first()
    if not item:
        return jsonify({"error": "Literature item not found"}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True})


@slr_bp.route("/api/papers/<paper_id>/literature/from-files", methods=["POST"])
@jwt_required()
def import_from_files(paper_id: str):
    """Buat satu LiteratureItem per file PaperFile (yang sudah punya
    extracted_text). Aman dipanggil berkali-kali — kita skip kalau file_id
    sudah pernah diimport."""
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    files = (PaperFile.query
             .filter_by(paper_id=paper_id, user_id=user_id)
             .order_by(PaperFile.created_at.desc())
             .all())
    existing_file_ids = {
        i.file_id for i in LiteratureItem.query
        .filter_by(paper_id=paper_id).filter(LiteratureItem.file_id.isnot(None))
        .all()
    }
    created = []
    for f in files:
        if f.id in existing_file_ids:
            continue
        excerpt = (f.extracted_text or "").strip()
        # Use first non-empty line as title; cap.
        title = (excerpt.split("\n", 1)[0] if excerpt else f.original_name)
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


# ─── Legacy sync /slr endpoint (back-compat) ──────────────────────────────

@slr_bp.route("/api/papers/<paper_id>/slr", methods=["POST"])
@jwt_required()
def run_slr_legacy(paper_id: str):
    """Old synchronous endpoint. Enqueues a job and polls up to 25 s.

    New callers should use POST /slr/jobs. This wrapper exists because the
    chat tool layer + a couple of tests still hit the old shape and expect
    `results` back inline.
    """
    user_id = _current_user_id()
    if user_id is None:
        return jsonify({"error": "Unauthorized"}), 401
    paper, err = _paper_or_404(paper_id, user_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    topic = (body.get("topic") or body.get("query") or "").strip()
    if not topic:
        return jsonify({"error": "topic required"}), 400
    try:
        limit = max(5, min(int(body.get("limit", 30)), 50))
    except (TypeError, ValueError):
        limit = 30

    cache_key = f"slr:{topic.lower()[:100]}"
    if not body.get("refresh", False):
        cached = ProjectMemory.query.filter_by(paper_id=paper_id, key=cache_key).first()
        if cached:
            try:
                import json as _json
                payload = _json.loads(cached.value)
                if isinstance(payload, dict) and payload.get("results"):
                    return jsonify({**payload, "cached": True})
            except Exception:
                pass

    job_id = enqueue_slr_job(
        paper_id=paper_id, user_id=user_id, query=topic,
        per_source=40, top_k=limit, ai_summarize=True,
    )
    deadline = time.time() + 25.0
    while time.time() < deadline:
        time.sleep(1.0)
        job = SlrJob.query.filter_by(id=job_id).first()
        if not job:
            break
        if job.status in ("done", "error", "cancelled"):
            break

    job = SlrJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job vanished"}), 500
    if job.status != "done":
        return jsonify({
            "error": f"Job still {job.status}. Use /slr/jobs/{job_id} to poll.",
            "job_id": job_id,
            "status": job.status,
        }), 202

    payload = job.result or {}
    top = payload.get("top_k") or []
    results = []
    for r in top[:limit]:
        results.append({
            "title": r.get("title"),
            "authors": r.get("authors") or [],
            "year": r.get("year"),
            "doi": r.get("doi"),
            "url": r.get("url"),
            "abstract": r.get("abstract") or "",
            "summary": r.get("summary") or "",
            "citations": r.get("citations") or 0,
            "source": r.get("source"),
            "venue": r.get("venue") or "",
        })
    out = {
        "results": results,
        "sources_used": list((payload.get("stats") or {}).get("papers_by_source") or {}),
        "sources_failed": [],
        "topic": topic,
        "generated_at": payload.get("generated_at"),
        "cached": False,
        "job_id": job_id,
    }

    # Update cache.
    import json as _json
    mem = ProjectMemory.query.filter_by(paper_id=paper_id, key=cache_key).first()
    if mem:
        mem.value = _json.dumps(out, ensure_ascii=False)
        mem.kind = "slr_cache"
        mem.updated_at = datetime.now(timezone.utc)
    else:
        mem = ProjectMemory(
            paper_id=paper_id, user_id=user_id,
            key=cache_key, value=_json.dumps(out, ensure_ascii=False),
            kind="slr_cache",
        )
        db.session.add(mem)
    db.session.commit()
    return jsonify(out)


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
