"""
Image generation worker pool.

Architecture
============
- 4 workers, one per Gemini account (account1..account4).
- Each worker = a dedicated thread + a single GeminiAccount + a private FIFO queue.
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
UPLOADS_DIR = REPO_ROOT / "uploads"

# Lazy import: GeminiPool needs Playwright + Chrome and is heavy.
_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            from imageGenerator.CreateImageGemini import GeminiPool  # noqa: PLC0415
            _pool = GeminiPool.from_env()
        return _pool


class _Worker(threading.Thread):
    """One worker drives exactly one GeminiAccount, sequentially."""

    def __init__(self, app, account_name: str):
        super().__init__(name=f"img-worker-{account_name}", daemon=True)
        self.app = app
        self.account_name = account_name
        self.q: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        self.q.put(None)  # unblock get()

    def submit(self, job_id: str):
        self.q.put(job_id)

    def qsize(self) -> int:
        return self.q.qsize()

    def run(self):
        while not self._stop.is_set():
            try:
                job_id = self.q.get(timeout=1.0)
            except queue.Empty:
                continue
            if job_id is None:
                break
            try:
                self._process(job_id)
            except Exception:
                log.exception("img-worker %s: unhandled error processing %s",
                              self.account_name, job_id)

    def _process(self, job_id: str):
        from models import ImageGenJob, PaperImage, db  # noqa: PLC0415
        from paper_utils import safe_paper_dir  # noqa: PLC0415

        with self.app.app_context():
            job = db.session.get(ImageGenJob, job_id)
            if not job or job.status not in ('queued', 'running'):
                return
            job.status = 'running'
            job.worker = self.account_name
            job.started_at = datetime.now(timezone.utc)
            db.session.commit()

            paper_id = job.paper_id
            user_id = job.user_id
            prompt = job.prompt

        # Long-running work outside DB transaction (no app_context needed).
        out_path: Optional[Path] = None
        ext = ".jpg"
        try:
            paper_dir = UPLOADS_DIR / paper_id
            paper_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{uuid.uuid4().hex}{ext}"
            out_path = paper_dir / filename

            pool = _get_pool()
            # Use only THIS account on the pool. The simplest way is to call the
            # account directly (skipping pool's round-robin), so two workers
            # never race on the same browser profile.
            acc = next((a for a in pool.accounts if a.name == self.account_name), None)
            if acc is None:
                raise RuntimeError(f"Account {self.account_name} tidak ada di pool")
            acc.launch(pool._pw)
            res = acc.generate_image(prompt, out_path, generate_timeout_s=240)

            try:
                from compress import compress_image  # noqa: PLC0415
                compress_image(out_path, max_size_mb=1.0)
            except Exception:
                pass

            with self.app.app_context():
                img = PaperImage(
                    paper_id=paper_id,
                    user_id=user_id,
                    filename=filename,
                    original_name=f"generated_{filename}",
                    file_path=f"{paper_id}/{filename}",
                )
                db.session.add(img)
                db.session.flush()

                job2 = db.session.get(ImageGenJob, job_id)
                if job2:
                    job2.status = 'done'
                    job2.image_id = img.id
                    job2.finished_at = datetime.now(timezone.utc)
                db.session.commit()

            log.info("img-worker %s: done job=%s file=%s size=%s",
                     self.account_name, job_id, filename, res.get('size'))
        except Exception as e:
            log.exception("img-worker %s: failed job=%s", self.account_name, job_id)
            try:
                if out_path and out_path.exists():
                    out_path.unlink()
            except Exception:
                pass
            with self.app.app_context():
                from models import ImageGenJob, db  # noqa: PLC0415
                job2 = db.session.get(ImageGenJob, job_id)
                if job2:
                    job2.status = 'error'
                    job2.error = str(e)[:500]
                    job2.finished_at = datetime.now(timezone.utc)
                    db.session.commit()


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
        self._stop = threading.Event()
        # Track which job_ids are already submitted to avoid double-dispatch.
        self._dispatched: set[str] = set()
        self._lock = threading.Lock()

    def stop(self):
        self._stop.set()

    def mark_dispatched(self, job_id: str):
        with self._lock:
            self._dispatched.add(job_id)

    def _least_loaded_worker(self) -> _Worker:
        return min(self.workers, key=lambda w: w.qsize())

    def run(self):
        from models import ImageGenJob, db  # noqa: PLC0415
        # On startup: requeue any queued/running jobs that were left behind by a
        # previous process. Running ones are demoted because their browser
        # session is gone.
        with self.app.app_context():
            stale = ImageGenJob.query.filter(ImageGenJob.status.in_(['queued', 'running'])).all()
            for j in stale:
                if j.status == 'running':
                    j.status = 'queued'
                    j.worker = None
            db.session.commit()

        while not self._stop.is_set():
            try:
                with self.app.app_context():
                    queued = (
                        ImageGenJob.query
                        .filter_by(status='queued')
                        .order_by(ImageGenJob.created_at.asc())
                        .limit(20)
                        .all()
                    )
                    ids = [j.id for j in queued]
                with self._lock:
                    new_ids = [i for i in ids if i not in self._dispatched]
                for jid in new_ids:
                    self._least_loaded_worker().submit(jid)
                    with self._lock:
                        self._dispatched.add(jid)
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
        if job_id in _dispatcher._dispatched:
            return
        _dispatcher._dispatched.add(job_id)
    min(_workers, key=lambda w: w.qsize()).submit(job_id)
