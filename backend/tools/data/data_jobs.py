"""
Data extraction jobs — async file processing with SSE progress streaming.

Upload files → extract text → AI format (tabel + grafik + analisa) → auto-generate charts.
Uses AiJob with kind="data_extract" for persistence across refresh.

Endpoints:
    POST   /api/papers/<paper_id>/data-jobs              — create job (upload files + prompt)
    GET    /api/papers/<paper_id>/data-jobs              — list jobs for paper
    GET    /api/data-jobs/<job_id>                       — get job status
    GET    /api/data-jobs/<job_id>/stream                — SSE progress stream
    POST   /api/data-jobs/<job_id>/cancel                — cancel job
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import redis
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename

from database.models import AiJob, Paper, PaperImage, db, safe_commit

log = logging.getLogger(__name__)

data_jobs = Blueprint("data_jobs", __name__)

# Redis for SSE pub/sub
_REDIS = None


def get_redis():
    global _REDIS
    if _REDIS is None:
        try:
            _REDIS = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                decode_responses=True,
            )
        except Exception:
            return None
    # Health check: reconnect if stale
    try:
        _REDIS.ping()
    except Exception:
        try:
            _REDIS.close()
        except Exception:
            pass
        _REDIS = None
        return get_redis()
    return _REDIS


def _progress_channel(job_id: str) -> str:
    return f"datajob:{job_id}:progress"


def _cancel_key(job_id: str) -> str:
    return f"datajob:{job_id}:cancel"


def _publish(job_id: str, payload: dict) -> None:
    try:
        msg = json.dumps(payload, default=str)
        _r = get_redis()
        if _r:
            _r.publish(_progress_channel(job_id), msg)
            _r.setex(f"datajob:{job_id}:last", 86400, msg)
    except Exception:
        pass


def _is_cancelled(job_id: str) -> bool:
    try:
        _r = get_redis()
        return bool(_r.get(_cancel_key(job_id))) if _r else False
    except Exception:
        return False


# ── Allowed file extensions ──────────────────────────────────────────────────

ALLOWED_EXTS = {".pdf", ".xlsx", ".xls", ".csv", ".tsv", ".doc", ".docx", ".pptx", ".ppt"}


# ── Endpoints ───────────────────────────────────────────────────────────────

@data_jobs.route("/api/papers/<paper_id>/data-jobs", methods=["POST"])
@jwt_required()
def create_data_job(paper_id: str):
    """Create a data extraction job. Accepts multipart with files[] + optional prompt."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Unauthorized"}), 401

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    # ── Bug fix #1: Auto-mark stale data_extract jobs as error ────────
    # Jobs stuck >10 min without progress update (worker died, restart, etc.)
    stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
    stale_jobs = AiJob.query.filter_by(
        paper_id=paper_id, user_id=user_id, kind="data_extract"
    ).filter(
        AiJob.status.in_(["queued", "running"]),
        AiJob.updated_at < stale_threshold,
    ).all()
    for sj in stale_jobs:
        sj.status = "error"
        sj.stage = "error"
        sj.error = "Job timeout — worker tidak respons (>10 menit tanpa update)"
        safe_commit()
        log.info("Auto-marked stale data job %s as error", sj.id)

    # Check for active job
    active = AiJob.query.filter_by(
        paper_id=paper_id, user_id=user_id, kind="data_extract"
    ).filter(
        AiJob.status.in_(["queued", "running"])
    ).first()
    if active:
        return jsonify({
            "error": "Sedang ada proses data yang berjalan. Tunggu sampai selesai.",
            "job_id": active.id,
        }), 409

    # Collect uploaded files (optional — text-only mode allowed)
    uploaded = request.files.getlist("files")
    prompt = (request.form.get("prompt") or "").strip()

    # Allow text-only mode: if no files, prompt must be non-empty
    if not uploaded and not prompt:
        return jsonify({"error": "Upload file atau masukkan instruksi teks"}), 400

    # Save files to temp dir (if any)
    temp_dir = tempfile.mkdtemp(prefix="datajob_") if uploaded else ""
    file_paths = []
    file_names = []
    if uploaded:
        for f in uploaded:
            fname = secure_filename(f.filename or "file")
            ext = Path(fname).suffix.lower()
            if ext not in ALLOWED_EXTS:
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                return jsonify({"error": f"Format tidak didukung: {ext}"}), 400
            dest = os.path.join(temp_dir, fname)
            f.save(dest)
            file_paths.append(dest)
            file_names.append(f.filename or fname)

    # Create job
    job_id = uuid.uuid4().hex[:16]
    job = AiJob(
        id=job_id,
        user_id=user_id,
        paper_id=paper_id,
        kind="data_extract",
        status="queued",
        progress=0,
        stage="queued",
        prompt=prompt or f"Ekstrak {len(file_paths)} file data",
        result={
            "file_names": file_names,
            "file_count": len(file_paths),
            "text_only": len(file_paths) == 0,
        },
    )
    db.session.add(job)
    safe_commit()

    # Start worker thread
    from tools.data.data_worker import run_data_job
    # Get Flask app from current context
    from flask import current_app
    flask_app = current_app._get_current_object()

    t = threading.Thread(
        target=run_data_job,
        args=(flask_app, job_id, file_paths, file_names, paper_id, user_id, prompt),
        daemon=True,
    )
    t.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "file_count": len(file_paths),
        "text_only": len(file_paths) == 0,
    }), 202


@data_jobs.route("/api/papers/<paper_id>/data-jobs", methods=["GET"])
@jwt_required()
def list_data_jobs(paper_id: str):
    """List data extraction jobs for a paper."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Unauthorized"}), 401

    jobs = AiJob.query.filter_by(
        paper_id=paper_id, user_id=user_id, kind="data_extract"
    ).order_by(AiJob.started_at.desc()).limit(20).all()

    return jsonify({
        "jobs": [
            {
                "id": j.id,
                "status": j.status,
                "progress": j.progress,
                "stage": j.stage,
                "prompt": j.prompt,
                "result": j.result,
                "error": j.error,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
            for j in jobs
        ]
    }), 200


@data_jobs.route("/api/data-jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_data_job(job_id: str):
    """Get job status."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Unauthorized"}), 401

    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "id": job.id,
        "paper_id": job.paper_id,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "prompt": job.prompt,
        "result": job.result,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }), 200


@data_jobs.route("/api/data-jobs/<job_id>/stream", methods=["GET"])
def stream_data_job(job_id: str):
    """SSE stream for job progress. Accepts token via query param (EventSource doesn't send custom headers)."""
    # EventSource doesn't support custom headers, so we accept token via query param
    # Support both 'token' (JWT) and 'csrf_token' (CSRF cookie) for backward compatibility
    token = request.args.get('token') or request.args.get('csrf_token')
    user_id = None
    
    if token:
        try:
            from flask_jwt_extended import decode_token
            # Try decoding as JWT token first
            decoded = decode_token(token)
            user_id = int(decoded['sub'])
        except Exception:
            # If decode fails, token might be CSRF token - fall through to cookie auth
            pass
    
    # Also try cookie-based auth (reads access_token_cookie)
    if not user_id:
        try:
            from flask_jwt_extended import verify_jwt_in_request
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
        except Exception:
            pass
    
    if not user_id:
        return jsonify({"error": "Missing authorization token", "code": "UNAUTHORIZED"}), 401

    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    app = current_app._get_current_object()

    def event_stream():
        with app.app_context():
            _r = get_redis()
            if not _r:
                yield "event: error\ndata: {\"message\": \"Redis unavailable\"}\n\n"
                return
            pubsub = _r.pubsub()
            try:
                pubsub.subscribe(_progress_channel(job_id))
            except Exception:
                pass

            # Send last snapshot first
            try:
                last = _r.get(f"datajob:{job_id}:last")
                if last:
                    yield f"event: progress\ndata: {last}\n\n"
            except Exception:
                pass

            # Check if already done
            try:
                j = AiJob.query.get(job_id)
                if j and j.status in ("done", "error", "cancelled"):
                    yield f"event: {j.status}\ndata: {json.dumps({'status': j.status, 'progress': j.progress, 'result': j.result, 'error': j.error}, default=str)}\n\n"
                    return
            except Exception:
                pass

            # Stream live events
            try:
                deadline = time.time() + 900  # 15 min max (data tools AI calls can take time)
                _hb_counter = [0]  # mutable counter for DB polling
                while time.time() < deadline:
                    msg = pubsub.get_message(timeout=3)
                    if msg and msg["type"] == "message":
                        data = msg["data"]
                        yield f"event: progress\ndata: {data}\n\n"
                        # Check for terminal event
                        try:
                            payload = json.loads(data)
                            if payload.get("status") in ("done", "error", "cancelled"):
                                yield f"event: {payload['status']}\ndata: {data}\n\n"
                                return
                        except (json.JSONDecodeError, KeyError):
                            pass
                    else:
                        # Heartbeat — also check DB periodically for terminal status
                        yield f": heartbeat\n\n"
                        # Every 5th heartbeat (~15s), poll DB for job completion
                        # This catches cases where Redis pub/sub event was missed
                        _hb_counter[0] += 1
                        if _hb_counter[0] % 5 == 0:
                            try:
                                with app.app_context():
                                    j = AiJob.query.get(job_id)
                                    if j and j.status in ("done", "error", "cancelled"):
                                        result_data = json.dumps({
                                            'status': j.status, 'progress': j.progress,
                                            'result': j.result, 'error': j.error
                                        }, default=str)
                                        yield f"event: {j.status}\ndata: {result_data}\n\n"
                                        return
                            except Exception:
                                pass
            except GeneratorExit:
                pass
            finally:
                try:
                    pubsub.unsubscribe()
                    pubsub.close()
                except Exception:
                    pass

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@data_jobs.route("/api/data-jobs/<job_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_data_job(job_id: str):
    """Cancel a running data job."""
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Unauthorized"}), 401

    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status in ("done", "error", "cancelled"):
        return jsonify({"error": f"Job already {job.status}"}), 400

    # Set cancel flag in Redis
    try:
        _r = get_redis()
        if _r:
            _r.setex(_cancel_key(job_id), 300, "1")
    except Exception:
        pass

    job.status = "cancelled"
    job.stage = "cancelled"
    safe_commit()

    _publish(job_id, {"status": "cancelled", "progress": job.progress, "stage": "cancelled"})

    return jsonify({"status": "cancelled"}), 200


def get_data_items_for_paper(paper_id: str, user_id: int, max_tables: int = 10, max_charts: int = 10) -> str:
    """
    Get formatted data items (tables + charts) for injection into chat/paperfull context.
    Returns a markdown string with all tables and charts from this paper.
    """
    # Get all done data jobs for this paper
    jobs = AiJob.query.filter_by(
        paper_id=paper_id, user_id=user_id, kind="data_extract", status="done"
    ).order_by(AiJob.updated_at.desc()).limit(5).all()

    if not jobs:
        return ""

    parts = []
    table_count = 0
    chart_count = 0

    for job in jobs:
        result = job.result or {}
        tables = result.get("tables", [])
        charts = result.get("charts", [])

        # Add tables
        for tbl in tables:
            if table_count >= max_tables:
                break
            name = tbl.get("name", f"Tabel {table_count + 1}")
            cols = tbl.get("columns", [])
            rows = tbl.get("rows", [])
            analysis = tbl.get("analysis", "")

            parts.append(f"### {name}")
            if cols and rows:
                # Format as markdown table
                parts.append("| " + " | ".join(cols) + " |")
                parts.append("| " + " | ".join(["---"] * len(cols)) + " |")
                for row in rows[:20]:  # Cap at 20 rows
                    while len(row) < len(cols):
                        row.append("")
                    parts.append("| " + " | ".join([str(c) for c in row[:len(cols)]]) + " |")
                parts.append("")

            if analysis:
                parts.append(f"**Analisa:** {analysis}\n")

            table_count += 1

        # Add charts
        for chart in charts:
            if chart_count >= max_charts:
                break
            title = chart.get("title", f"Grafik {chart_count + 1}")
            kind = chart.get("kind", "bar")
            analysis = chart.get("analysis", "")
            url = chart.get("url", "")

            parts.append(f"### {title} ({kind})")
            if url:
                parts.append(f"![{title}]({url})")
            if analysis:
                parts.append(f"**Analisa:** {analysis}\n")

            chart_count += 1

        if table_count >= max_tables and chart_count >= max_charts:
            break

    if not parts:
        return ""

    header = f"**Total: {table_count} tabel, {chart_count} grafik**\n"
    return header + "\n".join(parts)
