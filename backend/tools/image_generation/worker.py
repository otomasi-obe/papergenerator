"""
Image generation worker pool.

Architecture
============
- Pure API-only workers: no accounts, no browsers, no Playwright.
- Workers process jobs via image_api_v2.py providers (Alibaba, AG, Cloudflare).
- A central dispatcher pulls `queued` jobs from DB and pushes to the worker
  with the shortest local queue.

Persistence
===========
- All jobs are persisted in `image_gen_jobs` so they survive process restarts
  and frontend page reloads. The frontend polls /api/image-jobs/<id>.
- On startup, any `queued` or `running` jobs are re-queued into worker queues
  (running ones are demoted to queued).
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

REPO_ROOT = Path(__file__).resolve().parent


class _Worker(threading.Thread):
    """One worker processes image generation jobs via API providers."""

    def __init__(self, app, worker_id: int):
        super().__init__(name=f"img-worker-{worker_id}", daemon=True)
        self.app = app
        self.worker_id = worker_id
        self.q: "queue.Queue[str]" = queue.Queue()
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()
        self.q.put("")  # unblock get()

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
                    log.exception(
                        "img-worker %d: unhandled error processing %s",
                        self.worker_id, job_id,
                    )
    def _process(self, job_id: str):
        # Watchdog timeout: fail job if processing takes > 10 minutes
        # Uses threading.Timer instead of signal.SIGALRM (which only works in main thread)
        watchdog_timeout = int(os.getenv("IMAGE_GEN_WATCHDOG_TIMEOUT", "120"))
        generate_timeout = int(os.getenv("IMAGE_GEN_GENERATE_TIMEOUT", "60"))
        max_job_retries = int(os.getenv("IMAGE_GEN_MAX_RETRIES", "3"))

        _timed_out = threading.Event()
        _timer = threading.Timer(watchdog_timeout, _timed_out.set)
        _timer.daemon = True
        _timer.start()

        try:
            from sqlalchemy import update  # noqa: PLC0415

            from utils.database.models import ImageGenJob, PaperImage, db, safe_commit  # noqa: PLC0415
            from tools.editor.utils import safe_paper_image_dir  # noqa: PLC0415

            with self.app.app_context():
                # Atomic claim: only the FIRST worker that flips status from
                # 'queued' to 'running' actually proceeds. This is the single
                # source of truth that defends against (a) the dispatcher
                # double-dispatching (window between check and submit) and
                # (b) a user cancelling between our read and write.
                now = datetime.now(timezone.utc)
                result = db.session.execute(
                    update(ImageGenJob)
                    .where(ImageGenJob.id == job_id, ImageGenJob.status == "queued")
                    .values(status="running", worker=f"api-{self.worker_id}", started_at=now)
                )
                safe_commit()
                if result.rowcount == 0:
                    # Lost the race or job is cancelled/done/missing.
                    return

                job = db.session.get(ImageGenJob, job_id)
                if job is None:
                    return
                paper_id = job.paper_id
                user_id = job.user_id
                prompt = job.prompt
                # Track retry count
                retry_count = getattr(job, "retry_count", 0) or 0

                # Resolve paper image dir under app_context: user/<username>/<paper_id>/image/
                paper_dir = safe_paper_image_dir(paper_id)

            if paper_dir is None:
                with self.app.app_context():
                    from utils.database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

                    job2 = db.session.get(ImageGenJob, job_id)
                    if job2:
                        job2.status = "error"
                        job2.error = "Invalid paper_id (path resolution failed)"
                        job2.finished_at = datetime.now(timezone.utc)
                        safe_commit()
                return

            # Long-running work outside DB transaction (no app_context needed).
            out_path: Optional[Path] = None
            ext = ".jpg"
            try:
                paper_dir.mkdir(parents=True, exist_ok=True)

                # Use target_path from job if available (meaningful filename from paper JSON)
                # Fall back to uuid hash for backward compatibility
                target_filename = None
                with self.app.app_context():
                    _job_check = db.session.get(ImageGenJob, job_id)
                    if _job_check and _job_check.target_path:
                        target_filename = _job_check.target_path

                if target_filename:
                    # Sanitize: strip any path traversal
                    safe_name = os.path.basename(target_filename)
                    # Replace spaces and other unsafe chars with underscores
                    base, fext = os.path.splitext(safe_name)
                    base = re.sub(r'[^A-Za-z0-9_.-]', '_', base)
                    safe_name = base + fext
                    # Ensure .jpg extension
                    if fext.lower() not in ('.jpg', '.jpeg', '.png'):
                        safe_name = base + '.jpg'
                    # Avoid collision if file already exists
                    final_filename = safe_name
                    counter = 1
                    while (paper_dir / final_filename).exists():
                        base2, fext2 = os.path.splitext(safe_name)
                        final_filename = f"{base2}_{counter}.jpg"
                        counter += 1
                    filename = final_filename
                else:
                    filename = f"{uuid.uuid4().hex}{ext}"
                out_path = paper_dir / filename

                # ─── API-ONLY: all generation via API providers (Alibaba, AG, Cloudflare) ───
                res: dict = {}
                try:
                    from tools.image_generation.image_api_v2 import generate_image as api_generate_image  # noqa: PLC0415
                    res = api_generate_image(
                        prompt, str(out_path),
                        compress=True,
                        max_size_mb=1.0,
                        generate_timeout_s=generate_timeout,
                    )
                except Exception as api_err:
                    raise RuntimeError(
                        f"API image generation failed: {api_err}"
                    )

                with self.app.app_context():
                    img = PaperImage(
                        paper_id=paper_id,
                        user_id=user_id,
                        filename=filename,
                        original_name=filename,
                        # file_path is relative reference only; actual serving
                        # uses safe_paper_dir(paper_id) / filename, not this field.
                        file_path=f"{paper_id}/{filename}",
                    )
                    db.session.add(img)
                    db.session.flush()

                    job2 = db.session.get(ImageGenJob, job_id)
                    if job2:
                        # Respect a concurrent cancel: if the job was cancelled
                        # while we were generating, don't overwrite that status.
                        if job2.status == "cancelled":
                            # Drop the freshly-created image (orphaned) and the
                            # file on disk.
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

                # Simpan ke user storage (user/<username>/<paper_id>/image/)
                # Note: image sudah tersimpan di safe_paper_image_dir — ini adalah salinan
                # ke user storage yang menggunakan paper_id (bukan judul_paper)
                try:
                    from utils.core.user_storage import get_username, get_paper_base_by_id, _ensure_dir
                    import shutil
                    username = get_username(user_id=user_id)
                    paper_base = get_paper_base_by_id(username, paper_id)
                    image_dir = _ensure_dir(paper_base / "image")
                    dest = image_dir / Path(out_path).name
                    shutil.copy2(str(out_path), str(dest))
                except Exception:
                    log.warning("Gagal simpan image ke user storage", exc_info=True)

                log.info(
                    "img-worker %d: done job=%s file=%s size=%s",
                    self.worker_id,
                    job_id,
                    filename,
                    res.get("size") if res else "unknown",
                )
            except Exception as e:
                log.exception("img-worker %d: failed job=%s", self.worker_id, job_id)
                try:
                    if out_path and out_path.exists():
                        out_path.unlink()
                except Exception:
                    pass
                
                # Job-level retry: re-queue if under max retries
                with self.app.app_context():
                    from utils.database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

                    job2 = db.session.get(ImageGenJob, job_id)
                    if job2 and job2.status != "cancelled":
                        current_retry = getattr(job2, "retry_count", 0) or 0
                        if current_retry < max_job_retries:
                            # Re-queue for retry
                            job2.status = "queued"
                            job2.retry_count = current_retry + 1
                            job2.error = f"Retry {current_retry + 1}/{max_job_retries}: generation failed"
                            job2.worker = None
                            safe_commit()
                            log.warning(
                                "img-worker %d: job=%s re-queued (retry %d/%d): %s",
                                self.worker_id, job_id, current_retry + 1,
                                max_job_retries, str(e)[:200],
                            )
                        else:
                            # Max retries exceeded — final failure
                            job2.status = "error"
                            job2.error = "Image generation failed after all retries"
                            job2.finished_at = datetime.now(timezone.utc)
                            safe_commit()
                            log.error(
                                "img-worker %d: job=%s failed permanently after %d retries: %s",
                                self.worker_id, job_id, max_job_retries, str(e)[:200],
                            )

        finally:
            # Cancel the timer
            _timer.cancel()
            if _timed_out.is_set():
                log.warning("img-worker %d: job %s exceeded watchdog timeout", self.worker_id, job_id)

                # ─── Cleanup partial output file ───
                out_path_var = locals().get("out_path")
                if out_path_var is not None and out_path_var.exists():
                    try:
                        out_path_var.unlink()
                        log.info(
                            "img-worker %d: cleaned up partial output %s after timeout",
                            self.worker_id, out_path_var,
                        )
                    except Exception:
                        pass

                # ─── Update job status ke error ───
                try:
                    with self.app.app_context():
                        from utils.database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

                        job2 = db.session.get(ImageGenJob, job_id)
                        if job2 is not None and job2.status == "running":
                            job2.status = "error"
                            job2.error = "Watchdog timeout — generation took too long"
                            job2.finished_at = datetime.now(timezone.utc)
                            safe_commit()
                            log.info(
                                "img-worker %d: job %s marked error after watchdog timeout",
                                self.worker_id, job_id,
                            )
                except Exception:
                    log.exception(
                        "img-worker %d: error updating job %s status after timeout",
                        self.worker_id, job_id,
                    )


class _Dispatcher(threading.Thread):
    """Picks up newly-queued jobs from the DB and routes them to the worker
    with the shortest local queue. We don't bind a job to an account upfront —
    bottlenecks naturally even out via the shortest-queue heuristic.
    """

    def __init__(self, app, workers: list[_Worker], poll_interval: float = 1.5):
        super().__init__(name="img-dispatcher", daemon=True)
        self.app = app
        self.workers = workers
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        # Track which job_ids are already submitted to avoid double-dispatch.
        self._dispatched: set[str] = set()
        self._lock = threading.Lock()

    def stop(self):
        self._stop_event.set()

    def mark_dispatched(self, job_id: str):
        with self._lock:
            self._dispatched.add(job_id)

    def _least_loaded_worker(self) -> _Worker:
        return min(self.workers, key=lambda w: w.qsize())

    def run(self):
        from utils.database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

        # On startup: requeue any queued/running jobs that were left behind by a
        # previous process. Running ones are demoted because their browser
        # session is gone.
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
                # Submit all queued ids. _Worker._process atomically flips
                # queued→running, so duplicate submissions become cheap no-ops.
                # This also recovers jobs manually reset to queued after a
                # worker/browser hang.
                for jid in ids:
                    self._least_loaded_worker().submit(jid)
                # Bound the dispatched set: drop entries that left the active
                # set on the DB side (done/error/cancelled). Without this the
                # set grows unboundedly across the process lifetime.
                if len(self._dispatched) > 256:
                    with self.app.app_context():
                        active = {
                            r[0]
                            for r in db.session.query(ImageGenJob.id)
                            .filter(ImageGenJob.status.in_(["queued", "running"]))
                            .all()
                        }
                    with self._lock:
                        self._dispatched.intersection_update(active)
            except Exception:
                log.exception("img-dispatcher: poll failed")
            time.sleep(self.poll_interval)


_workers: list[_Worker] = []
_dispatcher: Optional[_Dispatcher] = None
_started = False
_start_lock = threading.Lock()


def get_dispatcher() -> Optional[_Dispatcher]:
    return _dispatcher


def start_image_workers(app):
    """Idempotent: starts workers + dispatcher once per process."""
    global _started, _workers, _dispatcher
    with _start_lock:
        if _started:
            return
        num_workers = int(os.environ.get("IMAGE_GEN_WORKERS", "2"))
        for i in range(num_workers):
            w = _Worker(app, i)
            w.start()
            _workers.append(w)
        _dispatcher = _Dispatcher(app, _workers)
        _dispatcher.start()
        _started = True
        log.info("image worker pool started: %d API-only workers", len(_workers))


def submit_now(job_id: str):
    """Optional: skip the DB poll and dispatch a freshly-created job
    immediately (latency optimization). Safe to no-op if the dispatcher is
    not yet up — the next poll will pick the job up anyway.
    """
    if not _dispatcher or not _workers:
        return
    with _dispatcher._lock:
        # Periodic cleanup: if _dispatched grows too large, prune completed jobs
        if len(_dispatcher._dispatched) > 100:
            try:
                from utils.database.models import ImageGenJob, db
                # DB access requires a Flask app_context. submit_now() may be
                # called from a worker thread (e.g. paper_worker._auto_enqueue_figure_images)
                # that has no active app_context, so push one explicitly.
                with _dispatcher.app.app_context():
                    active_ids = {
                        r[0] for r in db.session.query(ImageGenJob.id).filter(
                            ImageGenJob.id.in_(list(_dispatcher._dispatched)),
                            ImageGenJob.status.in_(('queued', 'running'))
                        ).all()
                    }
                _dispatcher._dispatched = active_ids
            except Exception as e:
                log.debug("submit_now: dispatched-set cleanup skipped: %s", e)  # Best effort cleanup
        if job_id in _dispatcher._dispatched:
            return
        _dispatcher._dispatched.add(job_id)
    min(_workers, key=lambda w: w.qsize()).submit(job_id)
