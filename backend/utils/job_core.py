"""
Shared job & usage helpers — free of any ``main`` circular import.

Both ``main.py`` and the ``tools.chat.*`` / ``tools.paperfull.*`` modules
import from here so there is no circular dependency.

``main.py`` must call ``init_job_core(app, model)`` once at startup before
any of the helper functions are invoked from background threads.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from flask import Flask

log = logging.getLogger(__name__)

# ── Module-level state, set by init_job_core() ──────────────────────────────
_app: Flask | None = None
_ai_model: str = ""
_init_lock = threading.Lock()


def init_job_core(app: Flask, ai_model: str = "") -> None:
    """Call once from ``main.py`` after the Flask app is created."""
    global _app, _ai_model
    with _init_lock:
        _app = app
        _ai_model = ai_model


def get_core_app() -> Flask:
    """Return the Flask app stored by ``init_job_core``."""
    if _app is None:
        raise RuntimeError(
            "job_core not initialised — main.py must call init_job_core(app, model) "
            "before any background thread can use these helpers."
        )
    return _app


# ── Job CRUD helpers ────────────────────────────────────────────────────────


def _job_create(job_id: str, user_id: int, prompt: str, paper_id: str | None = None):
    """Create an AiJob row.

    ``paper_id`` is now first-class so the chat-initiated path can bind the job
    to the paper that triggered it. Frontend uses the paper_id link to:
      - resume an in-flight job after page reload
      - show the recent-done badge on the paper card
      - look up the active job from /api/papers/<paper_id>/ai-jobs/active
    Older callers that pass only 3 positional args still work because paper_id
    has a default of None.
    """
    from utils.database.models import AiJob, db, safe_commit

    job = AiJob(
        id=job_id,
        user_id=user_id,
        paper_id=paper_id,
        status="queued",
        prompt=prompt,
    )
    db.session.add(job)
    # BUG-_DOUBLE_ROLLBACK: safe_commit() already does rollback internally on failure
    safe_commit()
    return job


def _job_get(job_id: str, user_id: int):
    from utils.database.models import AiJob

    return AiJob.query.filter_by(id=job_id, user_id=user_id).first()


def _job_set_done(job_id: str, user_id: int, paper_data: dict, elapsed_s: int):
    from utils.database.models import db, safe_commit

    job = _job_get(job_id, user_id)
    if not job:
        return
    job.status = "done"
    job.progress = 100
    job.stage = "combine"
    existing = job.result if isinstance(job.result, dict) else {}
    chunks_done = list(existing.get("chunks_done") or [])
    if "combine" not in chunks_done:
        chunks_done.append("combine")
    job.result = {
        **existing,
        "chunks_done": chunks_done,
        "partial_paper": paper_data,
        "elapsed_seconds": int(elapsed_s),
    }
    job.error = None
    job.timeout = False
    safe_commit()


def _job_set_error(job_id: str, user_id: int, error_msg: str, timeout_flag: bool = False):
    from utils.database.models import db, safe_commit

    job = _job_get(job_id, user_id)
    if not job:
        return
    job.status = "error"
    job.error = error_msg
    job.timeout = bool(timeout_flag)
    safe_commit()


# ── Auth helper ─────────────────────────────────────────────────────────────


def _get_current_user_id():
    from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        return int(identity) if identity else None
    except Exception:
        return None


# ── API usage logging ───────────────────────────────────────────────────────


def _log_api_usage(endpoint: str, usage: dict, user_id=None):
    """Insert usage row + bump per-user monthly counter (token quota tracking).

    Called from a daemon thread, so it owns its own app context via
    ``get_core_app()``.
    """
    from utils.database.models import ApiUsageLog, db, safe_commit

    app = get_core_app()
    try:
        with app.app_context():
            log_entry = ApiUsageLog(
                user_id=user_id,
                endpoint=endpoint,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                model=_ai_model,
            )
            db.session.add(log_entry)

            if user_id is not None:
                from utils.database.models import User

                now = datetime.now(timezone.utc)
                month_key = now.strftime("%Y-%m")
                tokens = int(usage.get("total_tokens", 0))
                u = User.query.get(int(user_id))
                if u:
                    if (u.usage_month_key or "") != month_key:
                        u.usage_month_key = month_key
                        u.token_used_month = 0
                        for _attempt in range(3):
                            try:
                                safe_commit()
                                break
                            except Exception:
                                db.session.rollback()
                                if _attempt == 2:
                                    raise
                                time.sleep(1)
                    # Atomic increment to prevent race condition across workers
                    db.session.query(User).filter(User.id == int(user_id)).update(
                        {User.token_used_month: User.token_used_month + tokens},
                        synchronize_session='evaluate',
                    )
                    for _attempt in range(3):
                        try:
                            safe_commit()
                            break
                        except Exception:
                            db.session.rollback()
                            if _attempt == 2:
                                raise
                            time.sleep(1)
    except Exception as e:
        log.warning("Failed to log API usage: %s", e)
