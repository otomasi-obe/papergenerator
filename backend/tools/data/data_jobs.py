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

from utils.database.models import AiJob, Paper, PaperImage, db, safe_commit

log = logging.getLogger(__name__)

data_jobs = Blueprint("data_jobs", __name__)

# Redis for SSE pub/sub
_REDIS = None


def get_redis(_depth=0):
    global _REDIS
    MAX_REDIS_RETRIES = 3
    if _REDIS is None:
        try:
            _REDIS = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                decode_responses=True,
            )
        except Exception:
            return None
    # Health check: reconnect if stale (with recursion guard)
    try:
        _REDIS.ping()
    except Exception:
        try:
            _REDIS.close()
        except Exception:
            pass
        _REDIS = None
        if _depth < MAX_REDIS_RETRIES:
            return get_redis(_depth + 1)
        return None
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
            _r.setex(f"datajob:{job_id}:last", 3600, msg)
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


# ── Helpers ─────────────────────────────────────────────────────────────────

def _cleanup_stale_data_jobs(paper_id: str, user_id: int, threshold_minutes: int = 3) -> int:
    """Auto-mark stale data_extract jobs as error and clean Redis keys. Returns count of cleaned jobs."""
    stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    stale_jobs = AiJob.query.filter_by(
        paper_id=paper_id, user_id=user_id, kind="data_extract"
    ).filter(
        AiJob.status.in_(["queued", "running"]),
        AiJob.updated_at < stale_threshold,
    ).all()
    for sj in stale_jobs:
        sj.status = "error"
        sj.stage = "error"
        sj.error = f"Job timeout — worker tidak respons (>{threshold_minutes} menit tanpa update)"
        # Clean Redis keys so SSE doesn't show stale progress
        _clean_redis_job_keys(sj.id)
        log.info("Auto-marked stale data job %s as error (paper=%s, user=%s)", sj.id, paper_id, user_id)
    if stale_jobs:
        safe_commit()  # single commit for all cleaned jobs
    return len(stale_jobs)


def _clean_redis_job_keys(job_id: str) -> int:
    """Delete all Redis keys for a data job. Returns count of keys deleted."""
    count = 0
    try:
        r = get_redis()
        if r:
            for suffix in ("last", "cancel"):
                key = f"datajob:{job_id}:{suffix}"
                if r.delete(key):
                    count += 1
    except Exception:
        pass
    return count


# ── Endpoints ───────────────────────────────────────────────────────────────

def _finish_error_direct(job_id, error_msg):
    """Mark job as error directly (used when worker thread fails to start)."""
    try:
        job = AiJob.query.get(job_id)
        if job:
            job.status = "error"
            job.stage = "error"
            job.error = error_msg
            job.finished_at = datetime.now(timezone.utc)
            safe_commit()
        _publish(job_id, {"status": "error", "stage": "error", "progress": 0, "error": error_msg})
        _clean_redis_job_keys(job_id)
    except Exception:
        pass


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
    _cleanup_stale_data_jobs(paper_id, user_id)

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
            # Magic bytes validation — reject files with mismatched content
            try:
                from tools.File.file_extractor import FILE_SIGNATURES, detect_file_type  # noqa: PLC0415
                with open(dest, "rb") as _mf:
                    _header = _mf.read(16)
                _detected = detect_file_type(_header, fname)
            except ImportError:
                _detected = ext  # fallback: trust extension if module unavailable
            if _detected is None:
                # No known signature matched — likely a spoofed extension
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                return jsonify({"error": f"File content does not match expected format: {fname}"}), 400
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

    # Publish initial state to Redis so SSE has something to show immediately
    # (before the worker thread gets CPU time to publish its first event)
    _publish(job_id, {
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "Mempersiapkan pemrosesan..." if prompt else f"Mempersiapkan ekstraksi {len(file_paths)} file...",
        "file_count": len(file_paths),
        "text_only": len(file_paths) == 0,
    })
    log.debug("DATA_JOB_DEBUG: Published initial queued state — job_id=%s", job_id)

    # Start worker thread
    from tools.data.data_worker import run_data_job
    # Get Flask app from current context
    from flask import current_app
    flask_app = current_app._get_current_object()

    try:
        t = threading.Thread(
            target=run_data_job,
            args=(flask_app, job_id, file_paths, file_names, paper_id, user_id, prompt),
            daemon=True,
        )
        t.start()
        log.debug("DATA_JOB_DEBUG: Worker thread started — job_id=%s", job_id)
    except Exception as e:
        log.exception("Failed to start data job worker thread for %s", job_id)
        _finish_error_direct(job_id, "Gagal memulai pemrosesan. Silakan coba lagi.")
        return jsonify({"error": "Gagal memulai pemrosesan. Silakan coba lagi."}), 500

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

    # Auto-cleanup stale jobs (frontend polls this endpoint every few seconds)
    _cleanup_stale_data_jobs(paper_id, user_id)

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

    # Fallback: read JWT from httpOnly cookie (EventSource sends it automatically)
    if not user_id:
        cookie_token = request.cookies.get('access_token_cookie')
        if cookie_token:
            try:
                from flask_jwt_extended import decode_token
                decoded = decode_token(cookie_token)
                user_id = int(decoded['sub'])
            except Exception:
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

    # If job is stuck and stale, auto-mark as error so frontend doesn't hang
    if job.paper_id and job.status in ("queued", "running"):
        _cleanup_stale_data_jobs(job.paper_id, user_id)
        # Re-fetch to get updated status
        job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
        if not job or job.status == "error":
            return jsonify({"error": job.error if job else "Job expired", "code": "JOB_STALE"}), 410

    app = current_app._get_current_object()

    def event_stream():
        with app.app_context():
            _r = get_redis()
            if not _r:
                yield "data: {\"status\": \"error\", \"error\": \"Redis unavailable\"}\n\n"
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
                    yield f"data: {last}\n\n"
            except Exception:
                pass

            # Check if already done
            try:
                j = AiJob.query.get(job_id)
                if j and j.status in ("done", "error", "cancelled"):
                    yield f"data: {json.dumps({'status': j.status, 'progress': j.progress, 'result': j.result, 'error': j.error}, default=str)}\n\n"
                    return
            except Exception:
                pass

            # Stream live events
            try:
                deadline = time.time() + 900  # 15 min max
                _hb_counter = [0]
                while time.time() < deadline:
                    msg = pubsub.get_message(timeout=3)
                    if msg and msg["type"] == "message":
                        data = msg["data"]
                        yield f"data: {data}\n\n"
                        # Check for terminal event
                        try:
                            payload = json.loads(data)
                            if payload.get("status") in ("done", "error", "cancelled"):
                                _clean_redis_job_keys(job_id)
                                return
                        except (json.JSONDecodeError, KeyError):
                            pass
                    else:
                        # Heartbeat
                        yield ": heartbeat\n\n"
                        # Every 5th heartbeat (~15s), poll DB
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
                                        yield f"data: {result_data}\n\n"
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
    # Clean Redis keys so SSE doesn't show stale progress
    _clean_redis_job_keys(job_id)

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
