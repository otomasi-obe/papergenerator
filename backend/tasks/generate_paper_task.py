"""
RQ task — generate full paper with progress events.
Runs inside an RQ worker (separate process), so it MUST create its own Flask
app context to touch the database. Progress events are published to Redis,
streamed to the browser by jobs_bp.stream_job (SSE).
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


def _checkpoint(job_id: str, stage: str, percent: int, status: str | None = None, **extra) -> None:
    """Persist progress to DB + publish to Redis for SSE subscribers."""
    from jobs_bp import publish_progress, _REDIS, cancel_key
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
            db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

    publish_progress(job_id, payload)


def _is_cancelled(job_id: str) -> bool:
    from jobs_bp import _REDIS, cancel_key
    try:
        return bool(_REDIS.exists(cancel_key(job_id)))
    except Exception:
        return False


def run_generate_paper(job_id: str, user_id: int, paper_id: str,
                       prompt: str, topic: str | None = None,
                       style: str | None = None) -> dict:
    """Worker entrypoint."""
    # Build a Flask app context inside the worker so SQLAlchemy can talk to the DB.
    from app import app  # noqa: F401  (boots the global Flask app + DB binding)
    from models import AiJob, Paper, db

    with app.app_context():
        try:
            _checkpoint(job_id, "outline", 5, status="running")
            if _is_cancelled(job_id):
                _checkpoint(job_id, "cancelled", 5, status="cancelled")
                return {"status": "cancelled"}

            # Stage 1: outline (we lean on the existing generator; emit progress
            # at logical stages even though the underlying call is one-shot).
            from generate_ai_json_paper_aiotomasi import generate_paper_json

            _checkpoint(job_id, "sections", 25)
            t0 = time.time()
            paper_data = generate_paper_json(
                judul=prompt,
                custom_prompt="",
                topic=topic,
                style=style,
            )
            _checkpoint(job_id, "references", 70)

            # Defensive defaults (mirror app.py post-processing)
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

            if _is_cancelled(job_id):
                _checkpoint(job_id, "cancelled", 70, status="cancelled")
                return {"status": "cancelled"}

            _checkpoint(job_id, "persisting", 90)

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

            job = AiJob.query.filter_by(id=job_id).first()
            if job:
                job.result = {"paper_id": paper_id, "elapsed": int(time.time() - t0)}
                job.status = "done"
                job.progress = 100
                job.stage = "done"
                db.session.commit()

            _checkpoint(job_id, "done", 100, status="done", paper_id=paper_id)
            return {"status": "done", "paper_id": paper_id}

        except Exception as e:
            tb = traceback.format_exc(limit=3)
            err_msg = f"{type(e).__name__}: {e}"
            try:
                job = AiJob.query.filter_by(id=job_id).first()
                if job:
                    job.status = "error"
                    job.error = err_msg + "\n" + tb
                    db.session.commit()
            except Exception:
                pass
            _checkpoint(job_id, "error", 100, status="error", error=err_msg)
            raise
