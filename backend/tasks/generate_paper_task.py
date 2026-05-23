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

import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend/ is on sys.path when this module is loaded by `rq worker`.
HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _checkpoint(job_id: str, stage: str, percent: int, status: str | None = None,
                partial: dict | None = None, **extra) -> None:
    """Persist progress to DB + publish to Redis for SSE subscribers.

    When ``partial`` is provided, the canonical resume shape
    (``{chunks_done, partial_paper}``) is written to AiJob.result so /resume
    can re-feed it to generate_paper_json_chunked(resume_state=...).
    """
    from jobs_bp import publish_progress
    from models import AiJob, db

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
            db.session.commit()
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
    from jobs_bp import _REDIS, cancel_key
    from models import AiJob

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


def run_generate_paper(job_id: str, user_id: int, paper_id: str,
                       prompt: str, topic: str | None = None,
                       style: str | None = None,
                       *, resume_state: dict | None = None,
                       custom_prompt: str | None = None,
                       model: str | None = None) -> dict:
    """Worker entrypoint — runs the chunked orchestrator with checkpoint hooks.

    ``resume_state`` (when provided) is a dict with ``chunks_done`` +
    ``partial_paper`` produced by a previous run. Pass-through to the
    orchestrator so it skips already-completed chunks.
    """
    # Build a Flask app context inside the worker so SQLAlchemy can talk to the DB.
    from app import app  # noqa: F401  (boots the global Flask app + DB binding)
    from models import AiJob, Paper, db
    from paper_generation.chunked import (
        generate_paper_json_chunked,
        GenerationCancelled,
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
                model=model,
                checkpoint_cb=_checkpoint_cb,
                cancel_check=lambda: _is_cancelled(job_id),
                resume_state=resume_state,
            )

            # Defensive defaults (mirror app.py post-processing).
            paper_data.setdefault("authors", [{
                "name": "Author Name", "affiliation": "Department, University",
                "location": "City, Country", "email": "author@example.com",
            }])
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
                        paper_data.get("title")
                        or (paper_data.get("data") or {}).get("title")
                        or paper.title
                        or "Untitled"
                    )
                    paper.updated_at = datetime.now(timezone.utc)
                    db.session.commit()

            # Final checkpoint stores the canonical paper under partial_paper
            # so GET /api/job/<id> can serve it directly without a separate
            # column. status='done' marks the row terminal for /recent.
            _checkpoint(job_id, "done", 100, status="done",
                        partial=paper_data, paper_id=paper_id,
                        elapsed=int(time.time() - t0))
            return {"status": "done", "paper_id": paper_id}

        except GenerationCancelled as gc:
            _checkpoint(job_id, gc.stage, 0, status="cancelled",
                        cancelled_at_stage=gc.stage,
                        elapsed=int(time.time() - t0))
            return {"status": "cancelled", "stage": gc.stage}

        except Exception as e:
            tb = traceback.format_exc(limit=3)
            err_msg = f"{type(e).__name__}: {e}"
            try:
                job = AiJob.query.filter_by(id=job_id).first()
                if job:
                    job.status = "error"
                    job.error = (err_msg + "\n" + tb)[:4000]
                    db.session.commit()
            except Exception:
                pass
            _checkpoint(job_id, "error", 100, status="error", error=err_msg)
            raise
