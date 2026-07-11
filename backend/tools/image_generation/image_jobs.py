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

from utils.database.models import ImageGenJob, Paper, db, safe_commit
from tools.editor.utils import PAPER_ID_RE

log = logging.getLogger(__name__)

image_jobs = Blueprint("image_jobs", __name__, url_prefix="/api/image-jobs")

# Cap the prompt length to avoid abuse / pathological inputs.
MAX_PROMPT_CHARS = 2000
# Max simultaneously queued+running jobs per user — cheap throttle that also
# prevents one paper from monopolizing the 4-account pool.
MAX_INFLIGHT_PER_USER = 12


@image_jobs.route("", methods=["POST"])
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
        ImageGenJob.status.in_(["queued", "running"]),
    ).count()
    if inflight >= MAX_INFLIGHT_PER_USER:
        return jsonify({"error": f"Maks {MAX_INFLIGHT_PER_USER} job aktif. Tunggu dulu."}), 429

    job = ImageGenJob(
        id=uuid.uuid4().hex,
        user_id=user_id,
        paper_id=paper_id,
        prompt=prompt,
        status="queued",
    )
    db.session.add(job)
    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise

    # Hand off to dispatcher immediately for lower latency. If the worker pool
    # isn't started yet, the dispatcher's DB poll will pick it up next tick.
    try:
        from .worker import submit_now  # noqa: PLC0415

        submit_now(job.id)
    except Exception:
        log.exception("submit_now failed (job will still run via dispatcher poll)")

    return jsonify({"id": job.id, "status": job.status})


@image_jobs.route("", methods=["GET"])
@jwt_required()
def list_image_jobs():
    try:

        user_id = int(get_jwt_identity())

    except (ValueError, TypeError):

        return jsonify({"error": "Invalid user identity"}), 401
    # Return active jobs + the 30 most recent finished ones, so the frontend can
    # reattach UI on reload without paging.
    active = (
        ImageGenJob.query.filter(
            ImageGenJob.user_id == user_id, ImageGenJob.status.in_(["queued", "running"])
        )
        .order_by(ImageGenJob.created_at.asc())
        .all()
    )
    recent_done = (
        ImageGenJob.query.filter(
            ImageGenJob.user_id == user_id, ImageGenJob.status.in_(["done", "error"])
        )
        .order_by(ImageGenJob.created_at.desc())
        .limit(30)
        .all()
    )
    return jsonify({"jobs": [j.to_dict() for j in (active + recent_done)]})


@image_jobs.route("/<job_id>", methods=["GET"])
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


@image_jobs.route("/<job_id>/cancel", methods=["POST"])
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
    if job.status in ("done", "error", "cancelled"):
        return jsonify({"id": job.id, "status": job.status})
    from datetime import datetime, timezone  # noqa: PLC0415

    job.status = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    safe_commit()
    return jsonify({"id": job.id, "status": job.status})


@image_jobs.route("/regenerate", methods=["POST"])
@jwt_required()
def regenerate_images():
    """Regenerate specific images or all images for a paper.
    
    Body:
    {
        "paper_id": "paper_id",
        "image_ids": [1, 2, 3]  // optional - specific PaperImage IDs to regenerate
        // if image_ids omitted: regenerate ALL images for this paper
    }
    """
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    data = request.get_json(silent=True) or {}
    paper_id = (data.get("paper_id") or "").strip()
    image_ids = data.get("image_ids")  # optional list of PaperImage IDs

    if not paper_id or not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper_id"}), 400

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    # Get images to regenerate
    from utils.database.models import ImageGenJob, PaperImage, db, safe_commit  # noqa: PLC0415
    
    if image_ids:
        # Specific images - verify they belong to this paper
        images = PaperImage.query.filter(
            PaperImage.id.in_(image_ids),
            PaperImage.paper_id == paper_id,
            PaperImage.user_id == user_id
        ).all()
        if len(images) != len(image_ids):
            return jsonify({"error": "Some images not found or don't belong to this paper"}), 404
    else:
        # Regenerate ALL images for this paper
        images = PaperImage.query.filter_by(paper_id=paper_id, user_id=user_id).all()
    
    if not images:
        return jsonify({"error": "No images to regenerate"}), 404

    # Get original prompts from ImageGenJob history for these images
    # We need to find the ImageGenJobs that created these images
    job_ids = [img.id for img in images]  # These are PaperImage IDs
    original_jobs = ImageGenJob.query.filter(
        ImageGenJob.image_id.in_(job_ids),
        ImageGenJob.paper_id == paper_id,
        ImageGenJob.user_id == user_id,
        ImageGenJob.status == "done"
    ).all()
    
    if not original_jobs:
        return jsonify({"error": "No original generation jobs found for these images"}), 400

    # Delete the existing PaperImage records (files will be overwritten by new jobs)
    for img in images:
        db.session.delete(img)
    
    # Also delete the old ImageGenJob records for cleanliness (they're done anyway)
    for job in original_jobs:
        db.session.delete(job)
    
    safe_commit()

    # Create new ImageGenJobs with same prompts
    new_job_ids = []
    for job in original_jobs:
        new_job = ImageGenJob(
            id=uuid.uuid4().hex,
            user_id=user_id,
            paper_id=paper_id,
            prompt=job.prompt,
            status="queued",
            target_path=job.target_path,
        )
        db.session.add(new_job)
        new_job_ids.append(new_job.id)
    
    safe_commit()

    # Submit first job immediately, dispatcher picks up rest
    try:
        from tools.image_generation.worker import submit_now  # noqa: PLC0415
        for jid in new_job_ids:
            try:
                submit_now(jid)
            except Exception:
                pass  # dispatcher poll will pick up
    except Exception:
        pass

    return jsonify({
        "message": f"Regenerating {len(new_job_ids)} image(s)",
        "job_ids": new_job_ids
    })
