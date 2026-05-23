"""
Image generation jobs API.

Endpoints:
  POST /api/image-jobs           — enqueue a new generate-image job
  GET  /api/image-jobs           — list current user's recent jobs (active first)
  GET  /api/image-jobs/<id>      — poll a single job
"""
from __future__ import annotations

import logging
import uuid

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from database.models import ImageGenJob, Paper, db
from paper_generation.utils import PAPER_ID_RE

log = logging.getLogger(__name__)

image_jobs_bp = Blueprint("image_jobs", __name__, url_prefix="/api/image-jobs")

# Cap the prompt length to avoid abuse / pathological inputs.
MAX_PROMPT_CHARS = 2000
# Max simultaneously queued+running jobs per user — cheap throttle that also
# prevents one paper from monopolizing the 4-account pool.
MAX_INFLIGHT_PER_USER = 12


@image_jobs_bp.route("", methods=["POST"])
@jwt_required()
def create_image_job():
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    data = request.get_json(silent=True) or {}
    paper_id = (data.get("paper_id") or "").strip()
    prompt = (data.get("prompt") or "").strip()

    if not paper_id or not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper_id"}), 400
    if not prompt:
        return jsonify({"error": "prompt kosong"}), 400
    if len(prompt) > MAX_PROMPT_CHARS:
        return jsonify({"error": f"prompt > {MAX_PROMPT_CHARS} char"}), 400

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    inflight = ImageGenJob.query.filter(
        ImageGenJob.user_id == user_id,
        ImageGenJob.status.in_(['queued', 'running']),
    ).count()
    if inflight >= MAX_INFLIGHT_PER_USER:
        return jsonify({"error": f"Maks {MAX_INFLIGHT_PER_USER} job aktif. Tunggu dulu."}), 429

    job = ImageGenJob(
        id=uuid.uuid4().hex,
        user_id=user_id,
        paper_id=paper_id,
        prompt=prompt,
        status='queued',
    )
    db.session.add(job)
    db.session.commit()

    # Hand off to dispatcher immediately for lower latency. If the worker pool
    # isn't started yet, the dispatcher's DB poll will pick it up next tick.
    try:
        from image_worker import submit_now  # noqa: PLC0415
        submit_now(job.id)
    except Exception:
        log.exception("submit_now failed (job will still run via dispatcher poll)")

    return jsonify({"id": job.id, "status": job.status})


@image_jobs_bp.route("", methods=["GET"])
@jwt_required()
def list_image_jobs():
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    # Return active jobs + the 30 most recent finished ones, so the frontend can
    # reattach UI on reload without paging.
    active = (
        ImageGenJob.query
        .filter(ImageGenJob.user_id == user_id,
                ImageGenJob.status.in_(['queued', 'running']))
        .order_by(ImageGenJob.created_at.asc())
        .all()
    )
    recent_done = (
        ImageGenJob.query
        .filter(ImageGenJob.user_id == user_id,
                ImageGenJob.status.in_(['done', 'error']))
        .order_by(ImageGenJob.created_at.desc())
        .limit(30)
        .all()
    )
    return jsonify({"jobs": [j.to_dict() for j in (active + recent_done)]})


@image_jobs_bp.route("/<job_id>", methods=["GET"])
@jwt_required()
def get_image_job(job_id: str):
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = ImageGenJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict())


@image_jobs_bp.route("/<job_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_image_job(job_id: str):
    """Mark a job as cancelled. Workers cooperate by checking status before
    writing the final 'done' or 'error' state, so a cancelled job will not
    end up creating a stray PaperImage row even if the generation actually
    completes a moment later."""
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    job = ImageGenJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.status in ('done', 'error', 'cancelled'):
        return jsonify({"id": job.id, "status": job.status})
    from datetime import datetime, timezone  # noqa: PLC0415
    job.status = 'cancelled'
    job.finished_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"id": job.id, "status": job.status})
