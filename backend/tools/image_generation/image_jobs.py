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
from flask_jwt_extended import get_jwt_identity, jwt_required, current_user

from utils.database.models import ImageGenJob, Paper, PaperImage, User, db, safe_commit
from tools.editor.utils import PAPER_ID_RE
from config.badge_tiers import TIER_RANK  # noqa: PLC0415

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
        badge=current_user.badge if current_user else None,
        priority=TIER_RANK.get(current_user.badge, 0) if current_user else 0,
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

        submit_now(job.id, badge=job.badge)
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
    result = job.to_dict()
    # Add queue position for frontend display
    try:
        from .worker import get_queue_position
        result["queue_position"] = get_queue_position(job_id)
    except Exception:
        result["queue_position"] = -1
    return jsonify(result)


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
    """Re-generate existing images for a paper.
    Body: { paper_id, image_ids? }
    - image_ids omitted/null -> regenerate ALL images for this paper
    - image_ids = [id1, id2, ...] -> regenerate only selected images
    Returns: { jobs: [{id, paper_id, figure_number}] }
    """
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid user identity"}), 401

    data = request.get_json(silent=True) or {}
    paper_id = (data.get("paper_id") or "").strip()
    image_ids = data.get("image_ids")

    if not paper_id or not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper_id"}), 400

    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    # Fetch target images
    if image_ids and isinstance(image_ids, list):
        images = PaperImage.query.filter(
            PaperImage.id.in_(image_ids),
            PaperImage.paper_id == paper_id,
            PaperImage.user_id == user_id,
        ).all()
    else:
        images = PaperImage.query.filter_by(paper_id=paper_id, user_id=user_id).all()

    if not images:
        return jsonify({"error": "Tidak ada image untuk di-re-generate"}), 404

    # ── Recover prompt + target_path from previous ImageGenJob(s) ──────
    # PaperImage has no prompt/target_path columns — look up the last
    # completed ImageGenJob that produced each image (via image_id FK).
    # Also fall back to matching by paper_id + prompt when image_id link
    # is missing (legacy jobs created before image_id was set).
    image_id_list = [img.id for img in images]
    prev_jobs = (
        ImageGenJob.query
        .filter(
            ImageGenJob.paper_id == paper_id,
            ImageGenJob.user_id == user_id,
            ImageGenJob.status == "done",
        )
        .order_by(ImageGenJob.finished_at.desc())
        .all()
    )
    # Map image_id → (prompt, target_path) from linked jobs
    job_map: dict[int, dict] = {}
    for j in prev_jobs:
        if j.image_id and j.image_id not in job_map:
            job_map[j.image_id] = {"prompt": j.prompt or "", "target_path": j.target_path or ""}

    # Delete old PaperImage rows + files so worker creates fresh ones
    # (otherwise we get duplicates instead of replace)
    from pathlib import Path as _Path  # noqa: PLC0415
    from tools.editor.utils import safe_paper_image_dir  # noqa: PLC0415

    img_dir = safe_paper_image_dir(paper_id)
    regen_specs = []
    for img in images:
        info = job_map.get(img.id, {})
        prompt = info.get("prompt", "")
        target_path = info.get("target_path", "") or img.original_name
        if not prompt:
            continue  # skip images with no recoverable prompt
        regen_specs.append({"prompt": prompt, "target_path": target_path})
        # Remove old file from disk
        if img_dir:
            try:
                old_file = img_dir / img.filename
                if old_file.exists():
                    old_file.unlink()
            except Exception:
                pass
        db.session.delete(img)

    if not regen_specs:
        return jsonify({"error": "Tidak ada prompt yang bisa di-recover untuk re-generate"}), 404

    created = []
    for spec in regen_specs:
        job = ImageGenJob(
            id=uuid.uuid4().hex,
            user_id=user_id,
            paper_id=paper_id,
            prompt=spec["prompt"],
            target_path=spec["target_path"][:500] if spec["target_path"] else None,
            status="queued",
            badge=current_user.badge if current_user else None,
            priority=TIER_RANK.get(current_user.badge, 0) if current_user else 0,
        )
        db.session.add(job)
        created.append(job)

    try:
        safe_commit()
    except Exception:
        db.session.rollback()
        raise

    # Submit all jobs
    try:
        from .worker import submit_now  # noqa: PLC0415
        for job in created:
            submit_now(job.id, badge=job.badge)
    except Exception:
        log.exception("submit_now failed (jobs will still run via dispatcher poll)")

    return jsonify({
        "jobs": [{"id": j.id, "paper_id": j.paper_id, "status": j.status}
                 for j in created]
    })
