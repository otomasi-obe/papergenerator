"""
Image generation worker pool.

Architecture
============
- 4 workers, one per Gemini account (account1..account4).
- Each worker = a dedicated thread + a single GeminiAccount + a private FIFO queue.
- Each worker creates its OWN sync_playwright() instance in its own thread
  (Playwright sync API is greenlet-based and bound to the creating thread).
- A central dispatcher pulls `queued` jobs from the database and pushes them to
  the worker with the shortest local queue. Within a worker, jobs run strictly
  sequentially (the persistent Chrome profile cannot be shared concurrently).
- Browsers stay launched (warm) between jobs; we only re-launch on hard failure.

Persistence
===========
- All jobs are persisted in `image_gen_jobs` so they survive process restarts
  and frontend page reloads. The frontend polls /api/image-jobs/<id>.
- On startup, any `queued` or `running` jobs are re-queued into worker queues
  (running ones are demoted to queued: their browser session is gone).
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent
UPLOADS_DIR = REPO_ROOT / "data/uploads"


class _Worker(threading.Thread):
    """One worker drives exactly one GeminiAccount, sequentially.

    Each worker creates its own sync_playwright() + GeminiAccount in its own
    thread. Playwright's sync API uses greenlets bound to the creating thread,
    so sharing across threads causes 'Cannot switch to a different thread'.
    """

    def __init__(self, app, account_name: str):
        super().__init__(name=f"img-worker-{account_name}", daemon=True)
        self.app = app
        self.account_name = account_name
        self.q: "queue.Queue[str]" = queue.Queue()
        self._stop_event = threading.Event()
        # Per-worker Playwright + Account (created in run() thread)
        self._pw_cm = None
        self._pw = None
        self._acc = None
        self._browser_healthy = True

    def stop(self):
        self._stop_event.set()
        self.q.put(None)  # unblock get()

    def submit(self, job_id: str):
        self.q.put(job_id)

    def qsize(self) -> int:
        return self.q.qsize()

    def _init_browser(self):
        """Create Playwright + GeminiAccount in THIS thread."""
        from tools.image_generation.CreateImageGemini import (  # noqa: PLC0415
            GeminiAccount,
        )
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        self._pw_cm = sync_playwright()
        self._pw = self._pw_cm.__enter__()
        try:
            self._acc = GeminiAccount.from_env(self.account_name)
        except Exception:
            # Clean up playwright on account init failure
            if self._pw_cm is not None:
                try:
                    self._pw_cm.__exit__(None, None, None)
                except Exception:
                    pass
                self._pw_cm = None
                self._pw = None
            raise
        log.info("img-worker %s: Playwright + account initialized", self.account_name)

    def _close_browser(self):
        """Cleanup Playwright + account."""
        if self._acc is not None:
            try:
                self._acc.close()
            except Exception:
                pass
            self._acc = None
        if self._pw_cm is not None:
            try:
                self._pw_cm.__exit__(None, None, None)
            except Exception:
                pass
            self._pw_cm = None
            self._pw = None

    def run(self):
        try:
            self._init_browser()
        except Exception:
            log.exception(
                "img-worker %s: failed to initialize browser, worker exiting",
                self.account_name,
            )
            self._dead = True
            # Drain pending jobs and mark as error so they don't hang forever
            while not self.q.empty():
                try:
                    orphan_job_id = self.q.get_nowait()
                    try:
                        with self.app.app_context():
                            from database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415
                            orphan = db.session.get(ImageGenJob, orphan_job_id)
                            if orphan and orphan.status == "running":
                                orphan.status = "error"
                                orphan.error = "Worker unavailable (browser init failed)"
                                orphan.finished_at = datetime.now(timezone.utc)
                                safe_commit()
                    except Exception:
                        log.warning("Failed to mark orphan job %s as error", orphan_job_id, exc_info=True)
                except queue.Empty:
                    break
            return

        try:
            while not self._stop_event.is_set():
                try:
                    job_id = self.q.get(timeout=1.0)
                except queue.Empty:
                    # Idle health check: if browser crashed while idle, re-init
                    if self._acc is None:
                        log.info("img-worker %s: browser died while idle, re-initializing", self.account_name)
                        self._init_browser()
                    continue
                if job_id is None:
                    break
                # Ensure browser is healthy before processing
                try:
                    if self._acc is None:
                        self._init_browser()
                    self._process(job_id)
                except Exception:
                    log.exception(
                        "img-worker %s: unhandled error processing %s",
                        self.account_name,
                        job_id,
                    )
        finally:
            self._close_browser()

    def _process(self, job_id: str):
        # Watchdog timeout: fail job if processing takes > 10 minutes
        # Uses threading.Timer instead of signal.SIGALRM (which only works in main thread)
        watchdog_timeout = int(os.getenv("IMAGE_GEN_WATCHDOG_TIMEOUT", "600"))
        generate_timeout = int(os.getenv("IMAGE_GEN_GENERATE_TIMEOUT", "300"))
        max_job_retries = int(os.getenv("IMAGE_GEN_MAX_RETRIES", "3"))
        # Prefer API-first approach (pollinations.ai etc.)
        use_api_first = os.environ.get("IMAGE_GEN_API_FIRST", "1") == "1"
        _timed_out = threading.Event()
        _timer = threading.Timer(watchdog_timeout, _timed_out.set)
        _timer.daemon = True
        _timer.start()

        try:
            from sqlalchemy import update  # noqa: PLC0415

            from database.models import ImageGenJob, PaperImage, db, safe_commit  # noqa: PLC0415
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
                    .values(status="running", worker=self.account_name, started_at=now)
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
                    from database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

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
                    # Ensure .jpg extension
                    base, fext = os.path.splitext(safe_name)
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

                # ─── API-FIRST: try free API providers before headless browser ───
                # This eliminates: cookie expiry, UI drift, browser crashes, RAM overhead
                res: dict = {}
                api_success = False

                if use_api_first:
                    try:
                        from tools.image_generation.image_api import generate_image as api_generate_image  # noqa: PLC0415
                        res = api_generate_image(
                            prompt, str(out_path),
                            compress=True,
                            max_size_mb=1.0,
                            generate_timeout_s=generate_timeout,
                        )
                        api_success = True
                        log.info(
                            "img-worker %s: API-first success via %s (cached=%s)",
                            self.account_name,
                            res.get("provider", "unknown"),
                            res.get("cached", False),
                        )
                    except Exception as api_err:
                        log.warning(
                            "img-worker %s: API-first failed (%s), falling back to headless",
                            self.account_name, str(api_err)[:150]
                        )
                        # Clean up partial output before fallback
                        if out_path and out_path.exists():
                            try:
                                out_path.unlink()
                            except Exception:
                                pass

                # ─── FALLBACK: headless Chrome via Gemini (existing system) ───
                if not api_success:
                    acc = self._acc
                    if acc is None:
                        raise RuntimeError(
                            f"Account {self.account_name} not initialized (browser init failed)"
                        )

                    # Retry browser launch up to 3 times with exponential backoff
                    launch_attempts = 3
                    for attempt in range(1, launch_attempts + 1):
                        try:
                            acc.launch(self._pw)
                            break
                        except Exception as launch_err:
                            if attempt == launch_attempts:
                                raise RuntimeError(
                                    f"Browser launch gagal setelah {launch_attempts} percobaan: {launch_err}"
                                )
                            log.warning(
                                "Browser launch attempt %d/%d failed: %s. Retrying...",
                                attempt,
                                launch_attempts,
                                launch_err,
                            )
                            # Close and cleanup before retry
                            try:
                                acc.close()
                            except Exception:
                                pass
                            # Exponential backoff: 2s, 4s
                            time.sleep(2**attempt)

                    res = acc.generate_image(prompt, out_path, generate_timeout_s=generate_timeout)

                    # Compression is critical: large images cause upload/display failures.
                    # If compression fails, we must fail the job rather than storing
                    # a 10MB+ image that will break the frontend.
                    try:
                        from tools.image_generation.compress import compress_image  # noqa: PLC0415

                        if not compress_image(out_path, max_size_mb=1.0):
                            raise RuntimeError(
                                f"Image compression failed: could not reduce {out_path.name} to <1MB. "
                                f"Original size: {out_path.stat().st_size // 1024}KB"
                            )
                        log.info(
                            "Image compressed successfully: %s -> %dKB",
                            out_path.name,
                            out_path.stat().st_size // 1024,
                        )
                    except Exception as compress_err:
                        log.error(
                            "Compression failed for %s: %s", out_path, compress_err, exc_info=True
                        )
                        # Delete the uncompressed image
                        try:
                            if out_path and out_path.exists():
                                out_path.unlink()
                        except Exception:
                            pass
                        raise RuntimeError(f"Image compression failed: {compress_err}")

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
                    "img-worker %s: done job=%s file=%s size=%s",
                    self.account_name,
                    job_id,
                    filename,
                    res.get("size") if res else "unknown",
                )
            except Exception as e:
                log.exception("img-worker %s: failed job=%s", self.account_name, job_id)
                try:
                    if out_path and out_path.exists():
                        out_path.unlink()
                except Exception:
                    pass
                
                # Job-level retry: re-queue if under max retries
                with self.app.app_context():
                    from database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

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
                                "img-worker %s: job=%s re-queued (retry %d/%d): %s",
                                self.account_name, job_id, current_retry + 1,
                                max_job_retries, str(e)[:200],
                            )
                        else:
                            # Max retries exceeded — final failure
                            job2.status = "error"
                            job2.error = "Image generation failed after all retries"
                            job2.finished_at = datetime.now(timezone.utc)
                            safe_commit()
                            log.error(
                                "img-worker %s: job=%s failed permanently after %d retries: %s",
                                self.account_name, job_id, max_job_retries, str(e)[:200],
                            )

        finally:
            # Cancel the timer
            _timer.cancel()
            if _timed_out.is_set():
                log.warning("img-worker %s: job %s exceeded watchdog timeout", self.account_name, job_id)

                # ─── Force-close browser yang menggantung ───
                try:
                    self._close_browser()
                except Exception:
                    log.exception(
                        "img-worker %s: error closing browser after timeout",
                        self.account_name,
                    )

                # ─── Re-init browser untuk job berikutnya ───
                self._browser_healthy = False
                try:
                    self._init_browser()
                except Exception:
                    log.exception(
                        "img-worker %s: error re-initializing browser after timeout",
                        self.account_name,
                    )

                # ─── Cleanup partial output file ───
                out_path_var = locals().get("out_path")
                if out_path_var is not None and out_path_var.exists():
                    try:
                        out_path_var.unlink()
                        log.info(
                            "img-worker %s: cleaned up partial output %s after timeout",
                            self.account_name, out_path_var,
                        )
                    except Exception:
                        pass

                # ─── Update job status ke error ───
                try:
                    with self.app.app_context():
                        from database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

                        job2 = db.session.get(ImageGenJob, job_id)
                        if job2 is not None and job2.status == "running":
                            job2.status = "error"
                            job2.error = "Watchdog timeout — browser dibunuh paksa"
                            job2.finished_at = datetime.now(timezone.utc)
                            safe_commit()
                            log.info(
                                "img-worker %s: job %s marked error after watchdog timeout",
                                self.account_name, job_id,
                            )
                except Exception:
                    log.exception(
                        "img-worker %s: error updating job %s status after timeout",
                        self.account_name, job_id,
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
        from database.models import ImageGenJob, db, safe_commit  # noqa: PLC0415

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
                # Atomically claim each id: only the thread that successfully
                # adds it to `_dispatched` submits it. This closes the window
                # where the poll loop and submit_now() could both route the
                # same job to a worker. The atomic claim in `_Worker._process`
                # is the second line of defence; this avoids paying the cost
                # of starting a second browser run that will then no-op.
                with self._lock:
                    to_submit = [i for i in ids if i not in self._dispatched]
                    for jid in to_submit:
                        self._dispatched.add(jid)
                for jid in to_submit:
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
        names_env = os.environ.get("GEMINI_PROFILES", "account1,account2,account3,account4")
        names = [n.strip() for n in names_env.split(",") if n.strip()]
        for n in names:
            w = _Worker(app, n)
            w.start()
            _workers.append(w)
        _dispatcher = _Dispatcher(app, _workers)
        _dispatcher.start()
        _started = True
        log.info("image worker pool started: %d workers", len(_workers))


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
                from database.models import ImageGenJob, db
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
