"""
Job blueprint — async paper generation backed by Redis + RQ, with SSE progress
streaming and a 'resume' endpoint so the UI can re-attach to a running job after
the user reloads or switches papers (rofiq.txt #4).

Endpoints
---------
POST /api/papers/<paper_id>/generate
    Enqueue a generate-paper job. Returns {job_id}.

GET  /api/jobs/<job_id>
    Job status snapshot (status/progress/stage/error).

GET  /api/jobs/<job_id>/stream         (SSE)
    Server-Sent Events stream of {stage, percent, partial} until job terminates.

GET  /api/papers/<paper_id>/active-jobs
    List active jobs (queued|running) for this paper, so the UI can resume.

GET  /api/papers/<paper_id>/ai-jobs/active
    Single active job (queued|running|paused) for the paper, or null.

POST /api/jobs/<job_id>/cancel
POST /api/ai-jobs/<job_id>/cancel
    Best-effort cancel (sets status=cancelled, worker checks the flag).

POST /api/ai-jobs/<job_id>/resume
    Re-enqueue with resume_state read from the row's checkpoint.

POST /api/ai-jobs/<job_id>/retry-section
    Body {stage}. Removes the stage from chunks_done + matching section from
    partial_paper.sections, then re-enqueues so just that chunk regenerates.

GET  /api/me/ai-jobs/recent
    Filterable inbox of the user's recent jobs (badge + recently-done lookup).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis
from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.models import AiJob, Paper, db

jobs = Blueprint("jobs", __name__)


# Single Redis connection reused across requests/workers.
_REDIS = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
)


def get_redis() -> redis.Redis:
    return _REDIS


def progress_channel(job_id: str) -> str:
    return f"job:{job_id}:progress"


def cancel_key(job_id: str) -> str:
    return f"job:{job_id}:cancel"


def publish_progress(job_id: str, payload: dict) -> None:
    """Worker calls this to push progress events. UI subscribes via SSE."""
    try:
        _REDIS.publish(progress_channel(job_id), json.dumps(payload, default=str))
        # Keep last snapshot for late subscribers (24h TTL).
        _REDIS.setex(f"job:{job_id}:last", 86400, json.dumps(payload, default=str))
    except Exception:
        pass


# ── Endpoints ───────────────────────────────────────────────────────────────


@jobs.route("/api/papers/<paper_id>/generate", methods=["POST"])
@jwt_required()
def enqueue_generate(paper_id: str):
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # Build custom_prompt dengan status context dari status.json
    custom_prompt = body.get("custom_prompt", "")
    
    # Check if user wants to include status.json data
    include_status = body.get("include_status", True)  # Default True untuk auto-include
    if include_status:
        try:
            from utils.core.user_storage import build_status_context, get_username
            
            selected_facts = body.get("selected_facts")  # None = all
            selected_files = body.get("selected_files")  # None = all
            selected_tables = body.get("selected_tables")  # None = all
            
            username = get_username(user_id=user_id)
            status_context = build_status_context(
                username, 
                paper_id,
                selected_facts=selected_facts,
                selected_files=selected_files,
                selected_tables=selected_tables
            )
            
            if status_context:
                custom_prompt = (custom_prompt + "\n\n" + status_context).strip()
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.warning(f"Failed to build status context for paper {paper_id}: {e}")

    job_id = uuid.uuid4().hex[:16]
    job = AiJob(
        id=job_id,
        user_id=user_id,
        paper_id=paper_id,
        kind="generate_paper",
        status="queued",
        progress=0,
        stage="queued",
        prompt=prompt[:4000],
    )
    db.session.add(job)
    db.session.commit()

    # Lazy import so this blueprint can be imported even if RQ is missing during
    # cold paths (alembic, tests).
    from rq import Queue

    from tools.paperfull.paper_worker import run_generate_paper

    q = Queue("paper", connection=_REDIS)
    q.enqueue(
        run_generate_paper,
        job_id,
        user_id,
        paper_id,
        prompt,
        body.get("topic"),
        body.get("style"),
        custom_prompt=custom_prompt,
        job_id=job_id,
        job_timeout=900,  # 15 min hard cap; UX shows progress so user knows it's alive
        result_ttl=3600,
    )

    publish_progress(job_id, {"stage": "queued", "percent": 0})
    return jsonify({"job_id": job_id, "status": "queued"})


@jobs.route("/api/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id: str):
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job: Optional[AiJob] = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job.to_dict())


@jobs.route("/api/jobs/<job_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_job(job_id: str):
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    if job.status in ("done", "error", "cancelled"):
        return jsonify({"ok": True, "status": job.status})
    _REDIS.setex(cancel_key(job_id), 3600, "1")
    job.status = "cancelled"
    db.session.commit()
    publish_progress(job_id, {"stage": "cancelled", "percent": job.progress, "status": "cancelled"})
    return jsonify({"ok": True})


@jobs.route("/api/papers/<paper_id>/active-jobs", methods=["GET"])
@jwt_required()
def active_jobs(paper_id: str):
    """Used by the UI on paper-load to resume any in-flight generation."""
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    rows = (
        AiJob.query.filter_by(user_id=user_id, paper_id=paper_id)
        .filter(AiJob.status.in_(["queued", "running"]))
        .order_by(AiJob.started_at.desc())
        .limit(5)
        .all()
    )
    return jsonify({"jobs": [j.to_dict() for j in rows]})


@jobs.route("/api/jobs/<job_id>/stream", methods=["GET"])
@jwt_required()
def stream_job(job_id: str):
    """SSE stream. Pumps a snapshot first (so late subscribers catch up), then
    pubsub events until the job terminates or the client disconnects."""
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404

    def gen():
        # Snapshot from DB so reconnect shows current state immediately.
        snap = {
            "stage": job.stage or "queued",
            "percent": int(job.progress or 0),
            "status": job.status,
        }
        yield f"event: snapshot\ndata: {json.dumps(snap)}\n\n"

        # If job already terminal, send done and exit.
        if job.status in ("done", "error", "cancelled"):
            yield f"event: done\ndata: {json.dumps({'status': job.status})}\n\n"
            return

        pubsub = _REDIS.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(progress_channel(job_id))
        try:
            t0 = time.time()
            last_ping = t0
            while True:
                msg = pubsub.get_message(timeout=1.0)
                if msg and msg.get("type") == "message":
                    data = msg.get("data") or "{}"
                    yield f"event: progress\ndata: {data}\n\n"
                    try:
                        parsed = json.loads(data)
                        if parsed.get("status") in ("done", "error", "cancelled"):
                            yield f"event: done\ndata: {json.dumps({'status': parsed.get('status')})}\n\n"
                            break
                    except Exception:
                        pass
                # Heartbeat every 15s so proxies don't kill the connection.
                if time.time() - last_ping > 15:
                    yield ": ping\n\n"
                    last_ping = time.time()
                # Hard cap 20 min per stream (resubscribe on client side).
                if time.time() - t0 > 1200:
                    break
        finally:
            try:
                pubsub.close()
            except Exception:
                pass

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(stream_with_context(gen()), headers=headers)


# ── Phase 1c — chunked generate workflow endpoints ──────────────────────────
#
# These endpoints power the chat-side progress bubble and the recent-done
# inbox badge. They live alongside the legacy /api/jobs/* routes so older
# clients keep working until they migrate.


_NON_TERMINAL = ("queued", "running", "paused", "pending")
_RESUMABLE = ("paused", "cancelled", "error")


def _enqueue_resume(job: AiJob, resume_state: dict | None) -> None:
    """Re-enqueue a job with optional resume_state.

    Tries the RQ path first (if Redis + the worker module are reachable).
    Falls back to the in-process threaded runner from app.py so dev
    environments without an RQ worker still progress. Both paths read the
    same resume_state shape.
    """
    # Lazy imports so this module stays importable in alembic/test contexts.
    try:
        from rq import Queue

        from tools.paperfull.paper_worker import run_generate_paper

        q = Queue("paper", connection=_REDIS)
        q.enqueue(
            run_generate_paper,
            args=(
                job.id,
                job.user_id,
                job.paper_id,
                job.prompt or "",
                None,
                None,
            ),
            kwargs={"resume_state": resume_state} if resume_state else {},
            job_id=job.id,
            job_timeout=900,
            result_ttl=3600,
        )
        publish_progress(
            job.id, {"stage": job.stage or "queued", "percent": int(job.progress or 0)}
        )
        return
    except Exception:
        pass

    # Fallback: kick off in-process via app._run_generate_full_job. This is the
    # same path used by the chat tool and /api/generate-full POST.
    try:
        import threading

        from main import _run_generate_full_job

        threading.Thread(
            target=_run_generate_full_job,
            args=(job.id, job.prompt or "", job.user_id),
            kwargs={
                "paper_id": job.paper_id,
                "resume_state": resume_state,
                "chunked": True,
            },
            daemon=True,
        ).start()
    except Exception:
        # Surface in the row so the UI can show "Resume failed".
        job.status = "error"
        job.error = "resume failed: no worker available"
        db.session.commit()


@jobs.route("/api/papers/<paper_id>/ai-jobs/active", methods=["GET"])
@jwt_required()
def ai_jobs_active(paper_id: str):
    """Return the most recent non-terminal generate_paper job for this paper.

    Used by the chat surface on paper-load to re-attach a progress bubble.
    Returns ``{"job": {...}}`` or ``{"job": null}``.
    """
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    job = (
        AiJob.query.filter_by(user_id=user_id, paper_id=paper_id, kind="generate_paper")
        .filter(AiJob.status.in_(_NON_TERMINAL))
        .order_by(AiJob.started_at.desc())
        .first()
    )
    return jsonify({"job": job.to_dict() if job else None})


@jobs.route("/api/ai-jobs/<job_id>/cancel", methods=["POST"])
@jwt_required()
def ai_jobs_cancel(job_id: str):
    """Mirror of /api/jobs/<job_id>/cancel under the new path prefix."""
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    if job.status in ("done", "cancelled"):
        return jsonify({"job": job.to_dict()})
    # Set the cancel flag for both the RQ worker (Redis key) and the chunked
    # orchestrator's DB-based cancel_check.
    try:
        _REDIS.setex(cancel_key(job_id), 3600, "1")
    except Exception:
        pass
    job.status = "cancelled"
    db.session.commit()
    publish_progress(
        job_id,
        {
            "stage": job.stage or "cancelled",
            "percent": int(job.progress or 0),
            "status": "cancelled",
        },
    )
    return jsonify({"job": job.to_dict()})


@jobs.route("/api/ai-jobs/<job_id>/resume", methods=["POST"])
@jwt_required()
def ai_jobs_resume(job_id: str):
    """Resume a paused/cancelled/errored job from its last checkpoint."""
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    if job.status not in _RESUMABLE:
        return (
            jsonify(
                {
                    "error": f"cannot resume from status={job.status}",
                    "job": job.to_dict(),
                }
            ),
            409,
        )

    result = job.result if isinstance(job.result, dict) else {}
    resume_state = {
        "chunks_done": list(result.get("chunks_done") or []),
        "partial_paper": result.get("partial_paper") or {},
    }

    # Clear any stale cancel flag — previous /cancel may have set it.
    try:
        _REDIS.delete(cancel_key(job_id))
    except Exception:
        pass

    job.status = "queued"
    job.error = None
    db.session.commit()

    _enqueue_resume(job, resume_state)
    return jsonify(
        {
            "job": job.to_dict(),
            "resume_state": {
                "chunks_done": resume_state["chunks_done"],
            },
        }
    )


@jobs.route("/api/ai-jobs/<job_id>/retry-section", methods=["POST"])
@jwt_required()
def ai_jobs_retry_section(job_id: str):
    """Retry a single chunk (e.g. ``section_3``).

    Removes the stage from ``chunks_done`` and, when the stage is a section,
    drops the matching entry from ``partial_paper.sections`` so the resumed
    run regenerates it cleanly. Other chunks stay cached.
    """
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    if job.status not in _RESUMABLE + ("done",):
        return (
            jsonify(
                {
                    "error": f"cannot retry from status={job.status}",
                    "job": job.to_dict(),
                }
            ),
            409,
        )

    body = request.get_json(silent=True) or {}
    stage = (body.get("stage") or "").strip()
    if not stage:
        return jsonify({"error": "stage required"}), 400

    result = job.result if isinstance(job.result, dict) else {}
    chunks_done = [s for s in (result.get("chunks_done") or []) if s != stage]
    # Always re-run combine after a retry so the final assembly reflects the
    # regenerated chunk.
    chunks_done = [s for s in chunks_done if s != "combine"]
    partial = dict(result.get("partial_paper") or {})

    if stage.startswith("section_"):
        try:
            idx = int(stage.split("_", 1)[1]) - 1
            sections = list(partial.get("sections") or [])
            if 0 <= idx < len(sections):
                sections.pop(idx)
                partial["sections"] = sections
        except Exception:
            pass
    elif stage == "outline":
        partial.pop("outline", None)
        partial["sections"] = []
        # Outline drives every later chunk's context — invalidate them all.
        chunks_done = []
    elif stage == "references":
        partial.pop("references", None)

    job.result = {**result, "chunks_done": chunks_done, "partial_paper": partial}
    job.status = "queued"
    job.error = None
    job.stage = stage
    db.session.commit()

    try:
        _REDIS.delete(cancel_key(job_id))
    except Exception:
        pass

    _enqueue_resume(
        job,
        {
            "chunks_done": chunks_done,
            "partial_paper": partial,
        },
    )
    return jsonify({"job": job.to_dict()})


@jobs.route("/api/me/ai-jobs/recent", methods=["GET"])
@jwt_required()
def ai_jobs_recent():
    """Recent jobs for the current user — feeds the inbox badge.

    Query params:
      - status: single status to filter on (default: ``done``)
      - since:  ISO 8601 timestamp; only jobs with started_at >= since
      - limit:  default 20, max 50
    """
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    status_filter = (request.args.get("status") or "").strip()
    since_raw = request.args.get("since")
    try:
        limit = min(50, max(1, int(request.args.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20

    q = AiJob.query.filter_by(user_id=user_id, kind="generate_paper")
    if status_filter:
        q = q.filter_by(status=status_filter)
    else:
        # Show both active and done jobs for the bell icon
        q = q.filter(AiJob.status.in_(["done", "running", "queued", "pending"]))

    if since_raw:
        try:
            # tolerate trailing 'Z'
            since_dt = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            q = q.filter(AiJob.started_at >= since_dt)
        except ValueError:
            return jsonify({"error": "invalid since timestamp"}), 400

    rows = q.order_by(AiJob.started_at.desc()).limit(limit).all()
    return jsonify({"jobs": [r.to_dict() for r in rows]})
