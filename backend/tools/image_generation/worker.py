"""
Image generation worker — priority queue + parallel workers per tier.

Architecture
============
- Multiple worker threads per badge tier (elite=3, pro=2, starter=1, trial=1).
- One dispatcher per tier pulls `queued` jobs filtered by badge, ordered by priority desc + created_at asc (FIFO within priority).
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
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class _Worker(threading.Thread):
    """Single worker — processes jobs sequentially, no timeout."""

    def __init__(self, app, tier: str, worker_idx: int):
        super().__init__(name=f"img-worker-{tier}-{worker_idx}", daemon=True)
        self.app = app
        self.tier = tier
        self.worker_idx = worker_idx
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
                log.exception("img-worker[%s-%d]: unhandled error processing %s", self.tier, self.worker_idx, job_id)

    def _process(self, job_id: str):
        # ponytail: no watchdog timeout — user requirement.
        # No max_retries limit — keep retrying until success.

        try:
            from sqlalchemy import update  # noqa: PLC0415

            from utils.database.models import ImageGenJob, PaperImage, db, safe_commit  # noqa: PLC0415
            from tools.editor.utils import safe_paper_image_dir  # noqa: PLC0415

            with self.app.app_context():
                now = datetime.now(timezone.utc)
                worker_name = f"{self.tier}-{self.worker_idx}"
                result = db.session.execute(
                    update(ImageGenJob)
                    .where(ImageGenJob.id == job_id, ImageGenJob.status == "queued")
                    .values(status="running", worker=worker_name, started_at=now)
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
                    # Get badge from job record for tier-based model selection
                    badge = None
                    try:
                        with self.app.app_context():
                            job2 = db.session.get(ImageGenJob, job_id)
                            if job2:
                                badge = job2.badge
                    except Exception:
                        pass
                    res = api_generate_image(
                        prompt, str(out_path),
                        compress=True,
                        max_size_mb=1.0,
                        badge=badge,
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
                    "img-worker[%s-%d]: done job=%s file=%s size=%s",
                    self.tier, self.worker_idx, job_id, filename,
                    res.get("size") if res else "unknown",
                )
            except Exception as e:
                log.exception("img-worker[%s-%d]: failed job=%s", self.tier, self.worker_idx, job_id)
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
                            "img-worker[%s-%d]: job=%s re-queued (retry %d): %s",
                            self.tier, self.worker_idx, job_id, current_retry + 1, str(e)[:200],
                        )

        except Exception:
            log.exception("img-worker[%s-%d]: outer error for %s", self.tier, self.worker_idx, job_id)


class _Dispatcher(threading.Thread):
    """Picks up queued jobs from DB for a specific tier, routes to that tier's workers."""

    def __init__(self, app, workers: List[_Worker], tier: str, poll_interval: float = 2.0):
        super().__init__(name=f"img-dispatcher-{tier}", daemon=True)
        self.app = app
        self.workers = workers
        self.tier = tier
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._dispatched: set[str] = set()
        self._lock = threading.Lock()
        self._worker_idx = 0  # round-robin

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
                    # Filter by badge tier = this dispatcher's tier
                    queued = (
                        ImageGenJob.query.filter_by(status="queued", badge=self.tier)
                        .order_by(ImageGenJob.priority.desc(), ImageGenJob.created_at.asc())
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
                            # Round-robin across workers in this tier
                            worker = self.workers[self._worker_idx % len(self.workers)]
                            self._worker_idx += 1
                            worker.submit(jid)
            except Exception:
                log.exception("img-dispatcher[%s]: poll failed", self.tier)
            time.sleep(self.poll_interval)


# Global state
_workers_by_tier: Dict[str, List[_Worker]] = {}
_dispatchers_by_tier: Dict[str, _Dispatcher] = {}
_started = False
_start_lock = threading.Lock()


def get_dispatcher(tier: str) -> Optional[_Dispatcher]:
    return _dispatchers_by_tier.get(tier)


def start_image_workers(app):
    """Idempotent: starts worker pools + dispatchers per tier once per process."""
    from config.badge_tiers import get_max_parallel_jobs  # noqa: PLC0415
    global _started, _workers_by_tier, _dispatchers_by_tier
    with _start_lock:
        if _started:
            return

        tiers = ["elite", "pro", "starter", "trial"]
        for tier in tiers:
            max_workers = get_max_parallel_jobs(tier)
            workers = [_Worker(app, tier, i) for i in range(max_workers)]
            for w in workers:
                w.start()
            _workers_by_tier[tier] = workers

            dispatcher = _Dispatcher(app, workers, tier)
            dispatcher.start()
            _dispatchers_by_tier[tier] = dispatcher

        _started = True
        total_workers = sum(len(w) for w in _workers_by_tier.values())
        log.info("image worker pool started: %d workers (%s)", total_workers,
                 ", ".join(f"{t}={len(w)}" for t, w in _workers_by_tier.items()))


def submit_now(job_id: str, badge: str = None):
    """Optional: skip the DB poll and dispatch a freshly-created job immediately."""
    if not badge:
        # Try to get badge from job
        from utils.database.models import ImageGenJob, db
        from main import app
        try:
            with app.app_context():
                job = db.session.get(ImageGenJob, job_id)
                if job:
                    badge = job.badge
        except Exception:
            pass

    tier = badge or "trial"
    dispatcher = _dispatchers_by_tier.get(tier)
    workers = _workers_by_tier.get(tier)
    if not dispatcher or not workers:
        return

    with dispatcher._lock:
        if len(dispatcher._dispatched) > 100:
            try:
                from utils.database.models import ImageGenJob, db
                with dispatcher.app.app_context():
                    active_ids = {
                        r[0] for r in db.session.query(ImageGenJob.id).filter(
                            ImageGenJob.id.in_(list(dispatcher._dispatched)),
                            ImageGenJob.status.in_(('queued', 'running'))
                        ).all()
                    }
                dispatcher._dispatched = active_ids
            except Exception as e:
                log.debug("submit_now: dispatched-set cleanup skipped: %s", e)
        if job_id in dispatcher._dispatched:
            return
        dispatcher._dispatched.add(job_id)

    # Round-robin submit
    worker = workers[dispatcher._worker_idx % len(workers)]
    dispatcher._worker_idx += 1
    worker.submit(job_id)


def get_queue_position(job_id: str) -> int:
    """Return 1-based queue position for a job (0 = running, -1 = done/error)."""
    try:
        from utils.database.models import ImageGenJob, db
        from main import app
        with app.app_context():
            queued = (
                ImageGenJob.query.filter_by(status="queued")
                .order_by(ImageGenJob.priority.desc(), ImageGenJob.created_at.asc())
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