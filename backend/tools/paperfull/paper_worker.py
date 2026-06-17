"""
RQ task — generate full paper with progress events.
Runs inside an RQ worker (separate process), so it MUST create its own Flask
app context to touch the database. Progress events are published to Redis,
streamed to the browser by jobs_bp.stream_job (SSE).

Pipeline: chunked orchestrator (generate_paper_json_chunked) with checkpoint
+ cancel + resume callbacks wired to AiJob rows. The legacy single-shot
generate_paper_json() is no longer used here — callers that still want the
one-shot path go through app._run_generate_full_job(chunked=False).

Dev note: when RQ/Redis is not configured, jobs_bp falls back to the
threaded path in app.py (_run_generate_full_job). Both paths now share the
same checkpoint shape so resume works regardless of which worker ran the
original generation.
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend/ is on sys.path when this module is loaded by `rq worker`.
HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _checkpoint(
    job_id: str,
    stage: str,
    percent: int,
    status: str | None = None,
    partial: dict | None = None,
    **extra,
) -> None:
    """Persist progress to DB + publish to Redis for SSE subscribers.

    When ``partial`` is provided, the canonical resume shape
    (``{chunks_done, partial_paper}``) is written to AiJob.result so /resume
    can re-feed it to generate_paper_json_chunked(resume_state=...).
    """
    from tools.paperfull.jobs import publish_progress
    from database.models import AiJob, db, safe_commit

    payload = {"stage": stage, "percent": percent, **extra}
    if status:
        payload["status"] = status

    try:
        job = AiJob.query.filter_by(id=job_id).first()
        if job:
            job.stage = stage
            job.progress = max(0, min(100, int(percent)))
            if status:
                job.status = status
            if partial is not None:
                existing = job.result if isinstance(job.result, dict) else {}
                chunks_done = list(existing.get("chunks_done") or [])
                if stage and stage not in chunks_done:
                    chunks_done.append(stage)
                job.result = {
                    **existing,
                    "chunks_done": chunks_done,
                    "partial_paper": partial,
                    "last_stage": stage,
                    "last_progress": int(percent),
                }
            safe_commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    publish_progress(job_id, payload)


def _is_cancelled(job_id: str) -> bool:
    """Check both the Redis cancel flag and AiJob.status='cancelled'.

    The orchestrator polls this between chunks; the chat /cancel endpoint
    flips the DB status, the SSE-fronted /jobs/<id>/cancel sets the Redis key.
    Either signal aborts the run.
    """
    from tools.paperfull.jobs import _REDIS, cancel_key
    from database.models import AiJob

    try:
        if _REDIS.exists(cancel_key(job_id)):
            return True
    except Exception:
        pass
    try:
        j = AiJob.query.filter_by(id=job_id).first()
        return bool(j and j.status == "cancelled")
    except Exception:
        return False


def run_generate_paper(
    job_id: str,
    user_id: int,
    paper_id: str,
    prompt: str,
    topic: str | None = None,
    style: str | None = None,
    language: str | None = None,
    *,
    resume_state: dict | None = None,
    custom_prompt: str | None = None,
    model: str | None = None,
) -> dict:
    """Worker entrypoint — runs the chunked orchestrator with checkpoint hooks.

    ``resume_state`` (when provided) is a dict with ``chunks_done`` +
    ``partial_paper`` produced by a previous run. Pass-through to the
    orchestrator so it skips already-completed chunks.
    """
    # Build a Flask app context inside the worker so SQLAlchemy can talk to the DB.
    from main import app  # noqa: F401  (boots the global Flask app + DB binding)
    from database.models import AiJob, Paper, db, safe_commit
    from PaperRiset.eks.editor.chunked import (
        GenerationCancelled,
        generate_paper_json_chunked,
    )

    with app.app_context():
        t0 = time.time()
        try:
            _checkpoint(job_id, "starting", 1, status="running")

            def _checkpoint_cb(stage: str, progress: int, partial: dict) -> None:
                _checkpoint(job_id, stage, progress, status="running", partial=partial)

            paper_data = generate_paper_json_chunked(
                judul=prompt,
                custom_prompt=custom_prompt or "",
                topic=topic,
                style=style,
                language=language,
                model=model,
                checkpoint_cb=_checkpoint_cb,
                cancel_check=lambda: _is_cancelled(job_id),
                resume_state=resume_state,
                paper_id=paper_id,
                user_id=user_id,
            )

            # Defensive defaults (mirror app.py post-processing).
            paper_data.setdefault(
                "authors",
                [
                    {
                        "name": "Author Name",
                        "affiliation": "Department, University",
                        "location": "City, Country",
                        "email": "author@example.com",
                    }
                ],
            )
            paper_data.setdefault("keywords", [])
            paper_data.setdefault("sections", [])
            paper_data.setdefault("references", [])
            paper_data.setdefault("figures", [])
            paper_data.setdefault("tables", [])
            paper_data.setdefault("equations", [])

            # Persist into Paper.data so the editor reflects the new content
            # the moment generation finishes (no extra reload needed).
            if paper_id:
                paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
                if paper:
                    paper.data = paper_data
                    paper.title = (
                        (paper_data.get("title") or "").strip()
                        or paper.title
                        or "Untitled"
                    )
                    paper.updated_at = datetime.now(timezone.utc)
                    safe_commit()
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"[run_generate_paper] Paper.data updated successfully: paper_id={paper_id}, user_id={user_id}, sections={len(paper_data.get('sections', []))}")
                else:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"[run_generate_paper] Paper NOT FOUND with id={paper_id}, user_id={user_id}")
                    paper_any = Paper.query.filter_by(id=paper_id).first()
                    if paper_any:
                        logger.warning(f"[run_generate_paper] Paper EXISTS but user_id mismatch: paper_id={paper_id}, expected_user_id={user_id}, actual_user_id={paper_any.user_id}")
                    else:
                        logger.warning(f"[run_generate_paper] Paper does NOT exist in database: paper_id={paper_id}")

            # ── Persist paper to editor BEFORE image generation ─────────────
            # Send done checkpoint immediately so editor shows content right away.
            # Image generation runs in background after this.
            _checkpoint(
                job_id,
                "done",
                100,
                status="done",
                partial=paper_data,
                paper_id=paper_id,
                elapsed=int(time.time() - t0),
            )

            # ── Auto-generate images in BACKGROUND ──────────────────────────
            # Enqueue figure images (Gemini) and data charts (matplotlib)
            # These run asynchronously - editor already has paper content.
            if paper_id:
                import threading
                # BUG-6.3: daemon=False so thread isn't silently killed on exit.
                # Error handling in _generate_images_background updates DB status.
                t = threading.Thread(
                    target=_generate_images_background,
                    args=(paper_id, user_id, paper_data),
                    daemon=False,
                    name=f"image-bg-{paper_id[:8]}",
                )
                t.start()

            return {"status": "done", "paper_id": paper_id}

        except GenerationCancelled as gc:
            _checkpoint(
                job_id,
                gc.stage,
                0,
                status="cancelled",
                cancelled_at_stage=gc.stage,
                elapsed=int(time.time() - t0),
            )
            return {"status": "cancelled", "stage": gc.stage}

        except Exception as e:
            tb = traceback.format_exc(limit=3)
            err_msg = f"{type(e).__name__}: {e}"
            try:
                job = AiJob.query.filter_by(id=job_id).first()
                if job:
                    job.status = "error"
                    job.error = (err_msg + "\n" + tb)[:4000]
                    safe_commit()
            except Exception:
                pass
            _checkpoint(job_id, "error", 100, status="error", error=err_msg)
            raise


def _auto_enqueue_figure_images(
    paper_id: str, user_id: int, paper_data: dict
) -> None:
    """Enqueue image generation jobs for all figure prompts in paper_data.

    Only visual/illustration figures (diagrams, architectures, system drawings)
    are enqueued here — they go through Gemini image generation.

    Data charts (graphs from uploaded files) are handled separately by
    the Data tools pipeline (matplotlib) and are NOT auto-generated here.

    Each figure with a non-empty ``Prompt`` field becomes an ImageGenJob.
    The figure's ``ImageNumber`` and ``Title`` are included in the prompt
    context so Gemini produces relevant illustrations.
    """
    import logging
    import uuid

    from database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

    logger = logging.getLogger(__name__)

    figures = paper_data.get("figures", [])
    if not figures:
        logger.info(
            "[auto_image] No figures in paper_data for paper_id=%s", paper_id
        )
        return

    enqueued = 0
    for fig in figures:
        prompt = str(fig.get("Prompt") or "").strip()
        if not prompt:
            continue

        # Skip data/chart figures — those are matplotlib territory
        fig_id = str(fig.get("ID") or "").lower()
        if any(kw in fig_id for kw in ("data", "chart", "grafik", "plot")):
            logger.info(
                "[auto_image] Skipping data figure '%s' (chart/plot)",
                fig.get("ID"),
            )
            continue

        # Enrich prompt with figure context for better results
        img_number = fig.get("ImageNumber") or fig.get("Title") or "Figure"
        title = fig.get("Title") or ""
        enriched = (
            f"{prompt}\n\n"
            f"Context: This is {img_number} ({title}) for an academic paper. "
            f"Style: clean technical diagram, professional academic publication, "
            f"high contrast, clear labels."
        )

        # Throttle check: skip if user already has too many inflight jobs
        inflight = ImageGenJob.query.filter(
            ImageGenJob.user_id == user_id,
            ImageGenJob.status.in_(["queued", "running"]),
        ).count()
        if inflight >= 12:
            logger.warning(
                "[auto_image] User %d has %d inflight jobs, stopping",
                user_id,
                inflight,
            )
            break

        job = ImageGenJob(
            id=uuid.uuid4().hex,
            user_id=user_id,
            paper_id=paper_id,
            prompt=enriched[:2000],  # MAX_PROMPT_CHARS
            status="queued",
        )
        db.session.add(job)
        enqueued += 1

    if enqueued:
        safe_commit()
        logger.info(
            "[auto_image] Enqueued %d image jobs for paper_id=%s",
            enqueued,
            paper_id,
        )
        # Submit first job immediately for lower latency; dispatcher
        # will pick up the rest on its next poll tick.
        try:
            from tools.image_generation.worker import (  # noqa: PLC0415
                get_dispatcher,
                submit_now,
            )

            # Re-query to get the IDs we just committed
            new_jobs = (
                ImageGenJob.query.filter_by(
                    paper_id=paper_id, user_id=user_id, status="queued"
                )
                .order_by(ImageGenJob.created_at.asc())
                .limit(enqueued)
                .all()
            )
            for j in new_jobs:
                submit_now(j.id)
        except Exception:
            logger.warning(
                "[auto_image] submit_now failed, dispatcher poll will pick up",
                exc_info=True,
            )
    else:
        logger.info(
            "[auto_image] No figure prompts to enqueue for paper_id=%s",
            paper_id,
        )


def _generate_images_background(
    paper_id: str, user_id: int, paper_data: dict
) -> None:
    """
    Background task: generate all images after paper is already shown in editor.

    This runs in a background thread (non-daemon) so it doesn't block the
    main generation flow and won't be silently killed on process exit.
    1. Enqueue figure images (Gemini) - these go through ImageGenJob queue
    2. Generate data charts (matplotlib) - these run in parallel threads
    """
    import logging
    from tools.data.auto_data_tools import auto_generate_data_charts

    logger = logging.getLogger(__name__)

    try:
        logger.info("[image_bg] Starting background image generation for paper_id=%s", paper_id)

        # 1. Enqueue figure images (Gemini) - these use the existing ImageGenJob queue
        _auto_enqueue_figure_images(paper_id, user_id, paper_data)

        # 2. Generate data charts (matplotlib) in parallel
        results = auto_generate_data_charts(paper_id, user_id, paper_data)
        if results["charts_generated"] > 0:
            logger.info(
                "[image_bg] Generated %d data charts for paper_id=%s",
                results["charts_generated"],
                paper_id,
            )
            # Update paper_data with generated chart paths
            from database.models import Paper, db, safe_commit
            paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
            if paper:
                paper.data = paper_data
                safe_commit()

        logger.info("[image_bg] Background image generation complete for paper_id=%s", paper_id)

    except Exception:
        logger.warning(
            "[image_bg] Error in background image generation for paper_id=%s",
            paper_id,
            exc_info=True,
        )
        # BUG-6.3: update DB so error is visible instead of silent death
        try:
            from database.models import Paper, db, safe_commit  # noqa: PLC0415
            paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
            if paper and paper.data:
                paper.data["image_gen_error"] = "Image generation failed — see server logs"
                safe_commit()
        except Exception:
            logger.warning(
                "[image_bg] Failed to record image gen error in DB for paper_id=%s",
                paper_id,
                exc_info=True,
            )