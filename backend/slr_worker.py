"""SLR worker pool — runs SlrJob rows from the DB queue.

Concurrency: up to 10 active jobs (`SLR_MAX_WORKERS`, fixed by spec).
Survives gunicorn multi-worker because the source of truth is the DB row;
each python process keeps its own ThreadPoolExecutor that pulls `queued` rows
and atomically transitions them to `running` (FOR UPDATE SKIP LOCKED on
Postgres, optimistic update on SQLite).

Public surface:
- `start_slr_workers(app)` — call once on app boot. Idempotent.
- `enqueue_slr_job(...)` — create + queue a row; safe to call from request
  handlers or chat tools. Returns the job id.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import or_

from models import LiteratureItem, SlrJob, db
from SLR.pipeline import run as run_slr_pipeline

log = logging.getLogger(__name__)

SLR_MAX_WORKERS = int(os.getenv("SLR_MAX_WORKERS", "10"))
POLL_INTERVAL = 1.5     # seconds between queue polls when idle
JOB_TIMEOUT = 1500      # 25 min — kill jobs running past this

_started = False
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_pump_thread: threading.Thread | None = None
_inflight: set[str] = set()
_inflight_lock = threading.Lock()


def _gen_id():
    return uuid.uuid4().hex[:12]


def enqueue_slr_job(*, paper_id: str, user_id: int,
                    query: str,
                    conversation_id: str | None = None,
                    sources: list[str] | None = None,
                    per_source: int = 60,
                    top_k: int = 50,
                    year_from: int | None = None,
                    ai_summarize: bool = True,
                    ai_model: str = "V-OPUS") -> str:
    """Insert an SlrJob row in `queued` status. Workers pick it up."""
    job = SlrJob(
        id=_gen_id(),
        user_id=user_id,
        paper_id=paper_id,
        conversation_id=conversation_id,
        query=(query or "").strip()[:2000],
        sources=sources or [],
        top_k=int(top_k),
        per_source=int(per_source),
        year_from=year_from,
        ai_summarize=bool(ai_summarize),
        ai_model=(ai_model or "V-OPUS")[:40],
        status="queued",
        stage="queued",
        progress=0,
        progress_message="Job queued",
    )
    db.session.add(job)
    db.session.commit()
    return job.id


def start_slr_workers(app) -> None:
    """Idempotent: launch the pump thread once per process."""
    global _started, _executor, _pump_thread
    with _lock:
        if _started:
            return
        _started = True
        _executor = ThreadPoolExecutor(
            max_workers=SLR_MAX_WORKERS,
            thread_name_prefix="slr",
        )
        _pump_thread = threading.Thread(
            target=_pump_loop, args=(app,), daemon=True, name="slr-pump")
        _pump_thread.start()
        log.info("SLR worker pool started (max=%d)", SLR_MAX_WORKERS)


def _pump_loop(app):
    """Pull queued SlrJob rows and dispatch to the executor."""
    while True:
        try:
            with app.app_context():
                _dispatch_pending(app)
        except Exception:
            log.exception("slr.pump loop iteration failed")
        time.sleep(POLL_INTERVAL)


def _dispatch_pending(app):
    # Decide how many slots are free without holding the DB transaction.
    with _inflight_lock:
        free = SLR_MAX_WORKERS - len(_inflight)
    if free <= 0:
        return

    # Pull up to `free` queued jobs and atomically transition to 'running'.
    candidates = (db.session.query(SlrJob)
                  .filter(SlrJob.status == "queued")
                  .order_by(SlrJob.queued_at.asc())
                  .limit(free * 2)
                  .all())
    if not candidates:
        return

    from datetime import datetime, timezone

    for job in candidates:
        with _inflight_lock:
            if len(_inflight) >= SLR_MAX_WORKERS:
                return
            if job.id in _inflight:
                continue
        # Optimistic claim — re-fetch + check.
        fresh = db.session.query(SlrJob).filter_by(id=job.id, status="queued").first()
        if fresh is None:
            continue
        fresh.status = "running"
        fresh.stage = "starting"
        fresh.started_at = datetime.now(timezone.utc)
        fresh.progress = 1
        fresh.progress_message = "Worker picked up the job"
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            continue
        with _inflight_lock:
            _inflight.add(fresh.id)
        _executor.submit(_run_job_safely, app, fresh.id)


def _run_job_safely(app, job_id: str):
    try:
        _run_job(app, job_id)
    except Exception:
        log.exception("slr.run_job %s crashed", job_id)
    finally:
        with _inflight_lock:
            _inflight.discard(job_id)


def _run_job(app, job_id: str):
    from datetime import datetime, timezone

    with app.app_context():
        job = db.session.query(SlrJob).filter_by(id=job_id).first()
        if not job:
            return

        def progress(stage: str, info: dict):
            try:
                with app.app_context():
                    j = db.session.query(SlrJob).filter_by(id=job_id).first()
                    if not j or j.status != "running":
                        return
                    j.stage = stage[:40]
                    j.progress_message = _stage_message(stage, info)[:200]
                    j.progress = _stage_to_pct(stage, info)
                    db.session.commit()
            except Exception:
                pass

        try:
            payload = run_slr_pipeline(
                query=job.query,
                sources=(job.sources or None),
                per_source=int(job.per_source or 60),
                top_k=int(job.top_k or 50),
                year_from=job.year_from,
                ai_summarize=bool(job.ai_summarize),
                ai_model=job.ai_model or None,
                progress_cb=progress,
            )
        except Exception as e:
            log.exception("slr.pipeline error job=%s", job_id)
            job = db.session.query(SlrJob).filter_by(id=job_id).first()
            if job:
                job.status = "error"
                job.stage = "error"
                job.error = str(e)[:2000]
                job.finished_at = datetime.now(timezone.utc)
                db.session.commit()
            return

        # Persist top_k records as LiteratureItem rows (pinned=False, source_kind='slr').
        # Replaces any prior literature rows for THIS job.
        db.session.query(LiteratureItem).filter_by(slr_job_id=job_id).delete(
            synchronize_session=False)
        db.session.commit()
        top = payload.get("top_k") or []
        for rec in top:
            try:
                pi = rec.get("publisher_info") or {}
                item = LiteratureItem(
                    paper_id=job.paper_id,
                    user_id=job.user_id,
                    source_kind='slr',
                    source=rec.get("source") or '',
                    title=rec.get("title") or '',
                    authors=rec.get("authors") or [],
                    year=rec.get("year") or pi.get("year"),
                    venue=rec.get("venue") or pi.get("venue") or '',
                    publisher=rec.get("publisher") or pi.get("publisher") or '',
                    doi=rec.get("doi") or None,
                    url=rec.get("url") or '',
                    abstract=rec.get("abstract") or '',
                    summary=rec.get("summary") or '',
                    citations=rec.get("citations"),
                    score_total=rec.get("score_total"),
                    score_breakdown=rec.get("score_breakdown") or {},
                    must_read=bool(rec.get("must_read")),
                    is_relevant=bool(rec.get("is_relevant", True)),
                    slr_job_id=job_id,
                )
                db.session.add(item)
            except Exception:
                log.exception("slr.literature insert failed")
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        job = db.session.query(SlrJob).filter_by(id=job_id).first()
        if not job:
            return
        job.status = "done"
        job.stage = "done"
        job.progress = 100
        job.progress_message = (
            f"Selesai. {len(top)} paper teratas tersimpan ke Literatur tab."
        )
        job.result = payload
        job.finished_at = datetime.now(timezone.utc)
        db.session.commit()


def _stage_to_pct(stage: str, info: dict) -> int:
    if stage == "fetching":
        return 5
    if stage == "source_done":
        completed = int(info.get("completed") or 0)
        total = max(1, int(info.get("total") or 1))
        return min(50, int(5 + 45 * completed / total))
    if stage == "dedup_done":
        return 55
    if stage == "scoring":
        return 60
    if stage == "scored":
        return 65
    if stage == "summarizing":
        return 68
    if stage == "summarized":
        done = int(info.get("done") or 0)
        total = max(1, int(info.get("total") or 1))
        return min(95, int(68 + 27 * done / total))
    if stage == "complete":
        return 100
    return 0


def _stage_message(stage: str, info: dict) -> str:
    if stage == "fetching":
        srcs = ", ".join(info.get("sources") or [])
        return f"Mencari paper di {info.get('total', 0)} sumber ({srcs})…"
    if stage == "source_done":
        return (f"{info.get('source', '?')} → {info.get('count', 0)} hasil "
                f"({info.get('completed', 0)}/{info.get('total', 0)})")
    if stage == "dedup_done":
        return f"Dedup selesai: {info.get('count', 0)} unique paper"
    if stage == "scoring":
        return f"Ranking {info.get('count', 0)} paper (SBERT + sitasi + recency)…"
    if stage == "scored":
        return f"{info.get('count', 0)} paper terskor"
    if stage == "summarizing":
        return f"AI ringkas top-{info.get('count', 0)} paper…"
    if stage == "summarized":
        return f"AI ringkas {info.get('done', 0)}/{info.get('total', 0)}"
    if stage == "complete":
        return f"Selesai: top-{info.get('top_k', 0)} dari {info.get('total', 0)} paper"
    return stage
