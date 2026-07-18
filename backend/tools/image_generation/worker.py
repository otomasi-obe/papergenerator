"""
Image generation worker — single sequential queue.

Architecture
============
- ONE worker thread processes image jobs one at a time (no concurrent API calls).
- A dispatcher pulls `queued` jobs from DB ordered by created_at (FIFO).
- No timeout, no retry limit — jobs keep retrying until they succeed.
- Frontend polls /api/image-jobs/<id> which returns queue_position.

Persistence
===========
- All jobs in `image_gen_jobs` table — survive restarts.
- On startup, queued/running jobs are re-queued.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class _Worker(threading.Thread):
    """Single worker — processes jobs sequentially, no timeout."""

    def __init__(self, app):
        super().__init__(name="img-worker-0", daemon=True)
        self.app = app
        self.worker_id = 0
        self.q: "queue.Queue[str]" = queue.Queue()
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()
        self.q.put("")

    def submit(self, job_id: str):
        self.q.put(job_id)

    def qsize(self) -> int:
        return self.q.qsize()

    def run(self):
        while not self._stop_event.is_set():
            try:
                job_id = self.q.get(timeout=1.0)
            except queue.Empty:
                continue
            if job_id == "":
                break
            try:
                self._process(job_id)
            except Exception:
                log.exception("img-worker: unhandled error processing %s", job_id)

    def _process(self, job_id: str):
        # ponytail: no watchdog timeout — user requirement.
        # No max_retries limit — keep retrying until success.

        try:
            from sqlalchemy import update  # noqa: PLC0415

            from utils.database.models import ImageGenJob, PaperImage, db, safe_commit  # noqa: PLC0415
            from tools.editor.utils import safe_paper_image_dir  # noqa: PLC0415

            with self.app.app_context():
                now = datetime.now(timezone.utc)
                result = db.session.execute(
                    update(ImageGenJob)
                    .where(ImageGenJob.id == job_id, ImageGenJob.status == "queued")
                    .values(status="running", worker="api-0", started_at=now)
                )
                safe_commit()
                if result.rowcount == 0:
                    return

                job = db.session.get(ImageGenJob, job_id)
                if job is None:
                    return
                paper_id = job.paper_id
                user_id = job.user_id
                prompt = job.prompt
                retry_count = getattr(job, "retry_count", 0) or 0

                paper_dir = safe_paper_image_dir(paper_id)

            if paper_dir is None:
                with self.app.app_context():
                    job2 = db.session.get(ImageGenJob, job_id)
                    if job2:
                        job2.status = "error"
                        job2.error = "Invalid paper_id (path resolution failed)"
                        job2.finished_at = datetime.now(timezone.utc)
                        safe_commit()
                return

            out_path: Optional[Path] = None
            try:
                paper_dir.mkdir(parents=True, exist_ok=True)

                target_filename = None
                with self.app.app_context():
                    _job_check = db.session.get(ImageGenJob, job_id)
                    if _job_check and _job_check.target_path:
                        target_filename = _job_check.target_path

                if target_filename:
                    safe_name = os.path.basename(target_filename)
                    base, fext = os.path.splitext(safe_name)
                    base = re.sub(r'[^A-Za-z0-9_.-]', '_', base)
                    safe_name = base + fext
                    if fext.lower() not in ('.jpg', '.jpeg', '.png'):
                        safe_name = base + '.jpg'
                    final_filename = safe_name
                    counter = 1
                    while (paper_dir / final_filename).exists():
                        base2, fext2 = os.path.splitext(safe_name)
                        final_filename = f"{base2}_{counter}.jpg"
                        counter += 1
                    filename = final_filename
                else:
                    filename = f"{uuid.uuid4().hex}.jpg"
                out_path = paper_dir / filename

                # ─── Generate via single API (no timeout) ───
                res: dict = {}
                try:
                    from tools.image_generation.image_api_v2 import generate_image as api_generate_image  # noqa: PLC0415
                    res = api_generate_image(
                        prompt, str(out_path),
                        compress=True,
                        max_size_mb=1.0,
                    )
                except Exception as api_err:
                    raise RuntimeError(f"API image generation failed: {api_err}")

                with self.app.app_context():
                    img = PaperImage(
                        paper_id=paper_id,
                        user_id=user_id,
                        filename=filename,
                        original_name=filename,
                        file_path=f"{paper_id}/{filename}",
                    )
                    db.session.add(img)
                    db.session.flush()

                    job2 = db.session.get(ImageGenJob, job_id)
                    if job2:
                        if job2.status == "cancelled":
                            try:
                                db.session.delete(img)
                            except Exception:
                                pass
                            try:
                                if out_path and out_path.exists():
                                    out_path.unlink()
                            except Exception:
                                pass
                        else:
                            job2.status = "done"
                            job2.image_id = img.id
                            job2.finished_at = datetime.now(timezone.utc)
                    safe_commit()

                # Save to user storage
                try:
                    from utils.core.user_storage import get_username, get_paper_base_by_id, _ensure_dir
                    import shutil
                    username = get_username(user_id=user_id)
                    paper_base = get_paper_base_by_id(username, paper_id)
                    image_dir = _ensure_dir(paper_base / "image")
                    dest = image_dir / Path(out_path).name
                    if out_path.resolve() != dest.resolve():
                        shutil.copy2(str(out_path), str(dest))
                except Exception:
                    log.warning("Gagal simpan image ke user storage", exc_info=True)

                log.info(
                    "img-worker: done job=%s file=%s size=%s",
                    job_id, filename,
                    res.get("size") if res else "unknown",
                )
            except Exception as e:
                log.exception("img-worker: failed job=%s", job_id)
                try:
                    if out_path and out_path.exists():
                        out_path.unlink()
                except Exception:
                    pass

                # Re-queue: no retry limit — keep trying until success
                with self.app.app_context():
                    job2 = db.session.get(ImageGenJob, job_id)
                    if job2 and job2.status != "cancelled":
                        current_retry = getattr(job2, "retry_count", 0) or 0
                        job2.status = "queued"
                        job2.retry_count = current_retry + 1
                        job2.error = f"Retry {current_retry + 1}: {str(e)[:300]}"
                        job2.worker = None
                        safe_commit()
                        log.warning(
                            "img-worker: job=%s re-queued (retry %d): %s",
                            job_id, current_retry + 1, str(e)[:200],
                        )

        except Exception:
            log.exception("img-worker: outer error for %s", job_id)


class _Dispatcher(threading.Thread):
    """Picks up queued jobs from DB, routes to the single worker."""

    def __init__(self, app, worker: _Worker, poll_interval: float = 2.0):
        super().__init__(name="img-dispatcher", daemon=True)
        self.app = app
        self.worker = worker
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._dispatched: set[str] = set()
        self._lock = threading.Lock()

    def stop(self):
        self._stop_event.set()

    def mark_dispatched(self, job_id: str):
        with self._lock:
            self._dispatched.add(job_id)

    def run(self):
        from utils.database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

        with self.app.app_context():
            stale = ImageGenJob.query.filter(ImageGenJob.status.in_(["queued", "running"])).all()
            for j in stale:
                if j.status == "running":
                    j.status = "queued"
                    j.worker = None
            safe_commit()

        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    queued = (
                        ImageGenJob.query.filter_by(status="queued")
                        .order_by(ImageGenJob.created_at.asc())
                        .limit(20)
                        .all()
                    )
                    ids = [j.id for j in queued]

                    # Clean up _dispatched: remove IDs no longer queued/running
                    if self._dispatched:
                        active_ids = {
                            r[0] for r in db.session.query(ImageGenJob.id)
                            .filter(ImageGenJob.status.in_(["queued", "running"]))
                            .all()
                        }
                        with self._lock:
                            self._dispatched.intersection_update(active_ids)

                for jid in ids:
                    with self._lock:
                        if jid not in self._dispatched:
                            self._dispatched.add(jid)
                            self.worker.submit(jid)
            except Exception:
                log.exception("img-dispatcher: poll failed")
            time.sleep(self.poll_interval)


_worker: Optional[_Worker] = None
_dispatcher: Optional[_Dispatcher] = None
_started = False
_start_lock = threading.Lock()


def get_dispatcher() -> Optional[_Dispatcher]:
    return _dispatcher


def start_image_workers(app):
    """Idempotent: starts single worker + dispatcher once per process."""
    global _started, _worker, _dispatcher
    with _start_lock:
        if _started:
            return
        _worker = _Worker(app)
        _worker.start()
        _dispatcher = _Dispatcher(app, _worker)
        _dispatcher.start()
        _started = True
        log.info("image worker pool started: 1 sequential worker (no timeout)")


def submit_now(job_id: str):
    """Optional: skip the DB poll and dispatch a freshly-created job immediately."""
    if not _dispatcher or not _worker:
        return
    with _dispatcher._lock:
        if len(_dispatcher._dispatched) > 100:
            try:
                from utils.database.models import ImageGenJob, db
                with _dispatcher.app.app_context():
                    active_ids = {
                        r[0] for r in db.session.query(ImageGenJob.id).filter(
                            ImageGenJob.id.in_(list(_dispatcher._dispatched)),
                            ImageGenJob.status.in_(('queued', 'running'))
                        ).all()
                    }
                _dispatcher._dispatched = active_ids
            except Exception as e:
                log.debug("submit_now: dispatched-set cleanup skipped: %s", e)
        if job_id in _dispatcher._dispatched:
            return
        _dispatcher._dispatched.add(job_id)
    _worker.submit(job_id)


def get_queue_position(job_id: str) -> int:
    """Return 1-based queue position for a job (0 = running, -1 = done/error)."""
    try:
        from utils.database.models import ImageGenJob, db
        from main import app
        with app.app_context():
            queued = (
                ImageGenJob.query.filter_by(status="queued")
                .order_by(ImageGenJob.created_at.asc())
                .all()
            )
            for i, j in enumerate(queued):
                if j.id == job_id:
                    return i + 1
            running = ImageGenJob.query.filter_by(status="running").all()
            for j in running:
                if j.id == job_id:
                    return 0  # Currently being processed
            return -1  # Done or error
    except Exception:
        return -1
