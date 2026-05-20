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

POST /api/jobs/<job_id>/cancel
    Best-effort cancel (sets status=cancelled, worker checks the flag).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Optional

import redis
from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask_jwt_extended import get_jwt_identity, jwt_required

from models import AiJob, Paper, db


jobs_bp = Blueprint("jobs_bp", __name__)


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


@jobs_bp.route("/api/papers/<paper_id>/generate", methods=["POST"])
@jwt_required()
def enqueue_generate(paper_id: str):
    user_id = int(get_jwt_identity())
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "paper not found"}), 404

    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

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
    from tasks.generate_paper_task import run_generate_paper

    q = Queue("paper", connection=_REDIS)
    q.enqueue(
        run_generate_paper,
        args=(job_id, user_id, paper_id, prompt, body.get("topic"), body.get("style")),
        job_id=job_id,
        job_timeout=900,  # 15 min hard cap; UX shows progress so user knows it's alive
        result_ttl=3600,
    )

    publish_progress(job_id, {"stage": "queued", "percent": 0})
    return jsonify({"job_id": job_id, "status": "queued"})


@jobs_bp.route("/api/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id: str):
    user_id = int(get_jwt_identity())
    job: Optional[AiJob] = AiJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job.to_dict())


@jobs_bp.route("/api/jobs/<job_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_job(job_id: str):
    user_id = int(get_jwt_identity())
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


@jobs_bp.route("/api/papers/<paper_id>/active-jobs", methods=["GET"])
@jwt_required()
def active_jobs(paper_id: str):
    """Used by the UI on paper-load to resume any in-flight generation."""
    user_id = int(get_jwt_identity())
    rows = (
        AiJob.query
        .filter_by(user_id=user_id, paper_id=paper_id)
        .filter(AiJob.status.in_(["queued", "running"]))
        .order_by(AiJob.started_at.desc())
        .limit(5)
        .all()
    )
    return jsonify({"jobs": [j.to_dict() for j in rows]})


@jobs_bp.route("/api/jobs/<job_id>/stream", methods=["GET"])
@jwt_required()
def stream_job(job_id: str):
    """SSE stream. Pumps a snapshot first (so late subscribers catch up), then
    pubsub events until the job terminates or the client disconnects."""
    user_id = int(get_jwt_identity())
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
