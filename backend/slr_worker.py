"""SLR worker pool — runs SlrJob rows from the DB queue.

Concurrency: up to 10 active jobs (`SLR_MAX_WORKERS`, fixed by spec).
Survives gunicorn multi-worker because the source of truth is the DB row;
each python process keeps its own ThreadPoolExecutor that pulls `queued` rows
and atomically transitions them to `running` via a single conditional UPDATE.

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
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, update as sa_update

from models import LiteratureItem, SlrJob, db
from SLR.pipeline import run as run_slr_pipeline

log = logging.getLogger(__name__)

SLR_MAX_WORKERS = int(os.getenv("SLR_MAX_WORKERS", "10"))
POLL_INTERVAL = 1.5     # seconds between queue polls when idle
JOB_TIMEOUT = 1500      # 25 min — kill jobs running past this
SWEEP_EVERY_N_POLLS = 40  # ~ once a minute at POLL_INTERVAL=1.5s

_started = False
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_pump_thread: threading.Thread | None = None
_inflight: set[str] = set()
_inflight_lock = threading.Lock()


class WorkerCancelled(Exception):
    """Raised inside the progress callback when a job has been cancelled."""
    pass


def _gen_id():
    return uuid.uuid4().hex[:12]


def _safe_commit(job_id: str | None = None, where: str = "") -> bool:
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        log.exception("slr commit failed for job=%s where=%s", job_id, where)
        return False


def enqueue_slr_job(*, paper_id: str, user_id: int,
                    query: str,
                    conversation_id: str | None = None,
                    sources: list[str] | None = None,
                    per_source: int = 60,
                    top_k: int = 50,
                    year_from: int | None = None,
                    ai_summarize: bool = True,
                    ai_model: str = "V-OPUS") -> SlrJob:
    """Insert an SlrJob row in `queued` status and return it. Workers pick it up."""
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
    return job


def _sweep_dead_running_jobs(app, *, reason: str = "Worker restart") -> int:
    """Kill orphaned 'running' jobs whose started_at is missing or older than
    JOB_TIMEOUT. Returns number of rows updated. Caller must hold app context.
    """
    now = datetime.now(timezone.utc)
    timeout_cutoff = now - timedelta(seconds=JOB_TIMEOUT)
    boot_cutoff = now - timedelta(minutes=30)
    cutoff = max(timeout_cutoff, boot_cutoff) if reason != "Worker restart" else boot_cutoff
    # On boot, sweep anything 'running' for >30min OR with no started_at.
    # On periodic sweep, also kill jobs running past JOB_TIMEOUT.
    if reason == "Worker restart":
        q = db.session.query(SlrJob).filter(
            SlrJob.status == "running",
            or_(SlrJob.started_at.is_(None), SlrJob.started_at < cutoff),
        )
    else:
        q = db.session.query(SlrJob).filter(
            SlrJob.status == "running",
            or_(SlrJob.started_at.is_(None),
                SlrJob.started_at < timeout_cutoff),
        )
    n = q.update(
        {"status": "error", "error": reason, "finished_at": now},
        synchronize_session=False,
    )
    if n:
        log.info("slr.sweep killed %d dead 'running' job(s) reason=%s", n, reason)
        _safe_commit(where=f"sweep:{reason}")
    else:
        # keep the txn clean even if no rows touched
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return n


def start_slr_workers(app) -> None:
    """Idempotent: launch the pump thread once per process."""
    global _started, _executor, _pump_thread
    with _lock:
        if _started:
            return
        _started = True

        # Boot recovery: kill orphaned 'running' jobs from a previous process.
        try:
            with app.app_context():
                _sweep_dead_running_jobs(app, reason="Worker restart")
        except Exception:
            log.exception("slr.boot sweep failed")

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
    tick = 0
    while True:
        try:
            with app.app_context():
                if tick % SWEEP_EVERY_N_POLLS == 0 and tick > 0:
                    try:
                        _sweep_dead_running_jobs(app, reason="Job timeout")
                    except Exception:
                        log.exception("slr.periodic sweep failed")
                _dispatch_pending(app)
        except Exception:
            log.exception("slr.pump loop iteration failed")
        tick += 1
        time.sleep(POLL_INTERVAL)


def _dispatch_pending(app):
    # Decide how many slots are free without holding the DB transaction.
    with _inflight_lock:
        free = SLR_MAX_WORKERS - len(_inflight)
    if free <= 0:
        return

    # Opportunistic sweep: under heavy queue pressure, don't wait for the
    # periodic sweep to clear timed-out 'running' rows.
    try:
        queued_count = (db.session.query(SlrJob)
                        .filter(SlrJob.status == "queued")
                        .count())
        if queued_count >= 5:
            try:
                _sweep_dead_running_jobs(app, reason="Job timeout")
            except Exception:
                log.exception("slr.opportunistic sweep failed")
    except Exception:
        log.exception("slr.queued_count probe failed")

    # Pull up to `free` queued jobs and atomically transition to 'running'.
    candidates = (db.session.query(SlrJob)
                  .filter(SlrJob.status == "queued")
                  .order_by(SlrJob.queued_at.asc())
                  .limit(free * 2)
                  .all())
    if not candidates:
        return

    for job in candidates:
        with _inflight_lock:
            if len(_inflight) >= SLR_MAX_WORKERS:
                return
            if job.id in _inflight:
                continue

        # Atomic claim: single conditional UPDATE. Whoever flips queued→running
        # first wins, regardless of process or thread.
        now = datetime.now(timezone.utc)
        stmt = (sa_update(SlrJob)
                .where(SlrJob.id == job.id, SlrJob.status == "queued")
                .values(status="running",
                        started_at=now,
                        stage="fetching",
                        progress=1,
                        progress_message="Worker picked up the job"))
        try:
            result = db.session.execute(stmt)
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception("slr.claim commit failed job=%s", job.id)
            continue

        if getattr(result, "rowcount", 0) != 1:
            # Someone else (another process / thread) claimed it.
            continue

        with _inflight_lock:
            _inflight.add(job.id)
        try:
            _executor.submit(_run_job_safely, app, job.id)
        except Exception:
            with _inflight_lock:
                _inflight.discard(job.id)
            log.exception("slr.executor.submit failed job=%s", job.id)


def _run_job_safely(app, job_id: str):
    try:
        _run_job(app, job_id)
    except Exception:
        log.exception("slr.run_job %s crashed", job_id)
    finally:
        with _inflight_lock:
            _inflight.discard(job_id)


def _run_job(app, job_id: str):
    with app.app_context():
        job = db.session.query(SlrJob).filter_by(id=job_id).first()
        if not job:
            return

        cancel_event = threading.Event()

        def progress(stage: str, info: dict):
            # Re-check status on every callback. Conditional UPDATE so we never
            # overwrite a 'cancelled' / 'error' / 'done' row, and signal the
            # pipeline by raising WorkerCancelled when the user cancelled.
            try:
                with app.app_context():
                    j = db.session.query(SlrJob).filter_by(id=job_id).first()
                    if not j:
                        return
                    if j.status == "cancelled":
                        cancel_event.set()
                        # Expose the cancel signal to the pipeline so fetchers
                        # running in their own ThreadPoolExecutor can poll it
                        # between source completions instead of stalling on
                        # in-flight HTTP requests.
                        try:
                            info["cancelled"] = True
                        except Exception:
                            pass
                        raise WorkerCancelled()
                    if j.status != "running":
                        return
                    try:
                        info["cancelled"] = cancel_event.is_set()
                    except Exception:
                        pass
                    stmt = (sa_update(SlrJob)
                            .where(SlrJob.id == job_id,
                                   SlrJob.status == "running")
                            .values(stage=stage[:40],
                                    progress_message=_stage_message(
                                        stage, info)[:200],
                                    progress=_stage_to_pct(stage, info)))
                    db.session.execute(stmt)
                    _safe_commit(job_id, where="progress")
            except WorkerCancelled:
                raise
            except Exception:
                log.exception("slr.progress callback failed job=%s", job_id)

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
        except WorkerCancelled:
            log.info("slr.job cancelled by user job=%s", job_id)
            # Atomic update: set cancellation-related fields in one statement so
            # we don't accidentally clobber a concurrent UPDATE (e.g. the cancel
            # endpoint's own commit, or a late-arriving progress write) and so
            # we never resurrect a stale in-memory `j` with status='running'.
            now = datetime.now(timezone.utc)
            try:
                db.session.execute(
                    sa_update(SlrJob)
                    .where(SlrJob.id == job_id,
                           SlrJob.status.in_(("running", "cancelled")))
                    .values(status="cancelled",
                            stage="cancelled",
                            progress_message="Job cancelled",
                            finished_at=now)
                )
                _safe_commit(job_id, where="cancelled")
            except Exception:
                db.session.rollback()
                log.exception("slr.cancel commit failed job=%s", job_id)
            return
        except Exception as e:
            log.exception(
                "slr.pipeline error job=%s query=%r sources=%s",
                job_id, (job.query or "")[:200], (job.sources or []),
            )
            j = db.session.query(SlrJob).filter_by(id=job_id).first()
            if j:
                j.status = "error"
                j.stage = "error"
                j.error = str(e)[:2000]
                j.finished_at = datetime.now(timezone.utc)
                _safe_commit(job_id, where="error")
            return

        # Persist top_k records as LiteratureItem rows (pinned=False, source_kind='slr').
        # Replaces any prior literature rows for THIS job. Other SLR jobs on the
        # same paper keep their rows so the user's pins/edits survive.
        try:
            db.session.query(LiteratureItem).filter_by(slr_job_id=job_id).delete(
                synchronize_session=False)
            _safe_commit(job_id, where="literature.delete")
        except Exception:
            log.exception("slr.literature delete failed job=%s", job_id)

        top = payload.get("top_k") or []

        # Detect a totally empty pipeline run — every source failed (e.g.
        # transient network) — and surface as an error instead of a silent
        # 'done with 0 results'.
        stats = payload.get("stats") or {}
        total_unique = int(stats.get("total_unique_papers") or 0)
        if not top and total_unique == 0:
            j = db.session.query(SlrJob).filter_by(id=job_id).first()
            if j and j.status == "running":
                j.status = "error"
                j.stage = "error"
                j.error = (
                    "No papers found from any source. Try a different query "
                    "or check upstream API health."
                )
                j.progress_message = j.error
                j.finished_at = datetime.now(timezone.utc)
                _safe_commit(job_id, where="error.empty")
            return

        # Pre-load existing DOIs for this paper so a re-run doesn't shadow rows
        # the user may have pinned/edited from a previous SLR run.
        existing_dois: set[str] = set()
        try:
            rows = (db.session.query(LiteratureItem.doi)
                    .filter(LiteratureItem.paper_id == job.paper_id,
                            LiteratureItem.doi.isnot(None))
                    .all())
            for (d,) in rows:
                if d:
                    existing_dois.add(d.strip().lower())
        except Exception:
            log.exception("slr.literature doi preload failed job=%s", job_id)

        for rec in top:
            try:
                title = (rec.get("title") or "").strip()
                if not title:
                    # Predatory / malformed records sometimes slip through
                    # with empty titles. Skip them.
                    continue
                doi_raw = rec.get("doi") or None
                doi_key = (doi_raw or "").strip().lower()
                if doi_key and doi_key in existing_dois:
                    # Don't shadow a row the user may have already pinned/edited.
                    continue
                pi = rec.get("publisher_info") or {}
                item = LiteratureItem(
                    paper_id=job.paper_id,
                    user_id=job.user_id,
                    source_kind='slr',
                    source=rec.get("source") or '',
                    title=title,
                    authors=rec.get("authors") or [],
                    year=rec.get("year") or pi.get("year"),
                    venue=rec.get("venue") or pi.get("venue") or '',
                    publisher=rec.get("publisher") or pi.get("publisher") or '',
                    doi=doi_raw,
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
                if doi_key:
                    existing_dois.add(doi_key)
            except Exception:
                log.exception("slr.literature insert failed")
        _safe_commit(job_id, where="literature.insert")

        j = db.session.query(SlrJob).filter_by(id=job_id).first()
        if not j:
            return
        # Don't overwrite a row that was cancelled/errored mid-flight.
        if j.status not in ("running",):
            return
        j.status = "done"
        j.stage = "done"
        j.progress = 100
        j.progress_message = (
            f"Selesai. {len(top)} paper teratas tersimpan ke Literatur tab."
        )
        j.result = payload
        j.finished_at = datetime.now(timezone.utc)
        _safe_commit(job_id, where="done")


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
