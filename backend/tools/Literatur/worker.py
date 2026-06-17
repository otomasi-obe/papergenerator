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

from sqlalchemy import or_
from sqlalchemy import update as sa_update
from sqlalchemy.exc import DBAPIError, OperationalError

from database.models import LiteratureItem, SlrJob, db, safe_commit
from tools.Literatur.paper import Paper
from tools.Literatur.pipeline import run as run_slr_pipeline
from utils.ai_tools.model_config import get_primary_generate_model

log = logging.getLogger(__name__)

SLR_MAX_WORKERS = int(os.getenv("SLR_MAX_WORKERS", "10"))
POLL_INTERVAL = 1.5  # seconds between queue polls when idle
JOB_TIMEOUT = 1500  # 25 min — kill jobs running past this
SWEEP_EVERY_N_POLLS = 40  # ~ once a minute at POLL_INTERVAL=1.5s

_started = False
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_pump_thread: threading.Thread | None = None
_inflight: set[str] = set()
_inflight_lock = threading.Lock()

# Lock FD held at module level to prevent GC releasing the fcntl lock
_slr_lock_fd = None


class WorkerCancelled(Exception):
    """Raised inside the progress callback when a job has been cancelled."""

    pass


def _gen_id():
    return uuid.uuid4().hex[:12]


def _safe_commit(job_id: str | None = None, where: str = "") -> bool:
    try:
        safe_commit()
        return True
    except Exception:
        db.session.rollback()
        log.exception("slr commit failed for job=%s where=%s", job_id, where)
        return False


def enqueue_slr_job(
    *,
    paper_id: str,
    user_id: int,
    query: str,
    conversation_id: str | None = None,
    sources: list[str] | None = None,
    per_source: int = 60,
    top_k: int = 50,
    year_from: int | None = None,
    ai_summarize: bool = True,
    ai_model: str | None = None,
) -> SlrJob:
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
        ai_model=(ai_model or get_primary_generate_model())[:40],
        status="queued",
        stage="queued",
        progress=0,
        progress_message="Job queued",
    )
    db.session.add(job)
    safe_commit()
    return job


def _sweep_dead_running_jobs(app, *, reason: str = "Worker restart") -> int:
    """Kill orphaned 'running' jobs whose started_at is missing or older than
    JOB_TIMEOUT. Returns number of rows updated. Caller must hold app context.
    """
    try:
        now = datetime.now(timezone.utc)
        timeout_cutoff = now - timedelta(seconds=JOB_TIMEOUT)
        q = db.session.query(SlrJob).filter(
            SlrJob.status == "running",
            or_(SlrJob.started_at.is_(None), SlrJob.started_at < timeout_cutoff),
        )
        n = q.update(
            {"status": "error", "error": f"Job timeout ({reason})", "finished_at": now},
            synchronize_session=False,
        )
        if n:
            log.warning("slr.sweep killed %d dead 'running' job(s) reason=%s", n, reason)
            _safe_commit(where=f"sweep:{reason}")
        else:
            # keep the txn clean even if no rows touched
            try:
                safe_commit()
            except Exception:
                db.session.rollback()
        return n
    except (OperationalError, DBAPIError) as e:
        log.warning(
            "slr.sweep skipped due to DB busy/lock (reason=%s); jobs will sweep "
            "on next worker tick: %s",
            reason,
            e,
        )
        try:
            db.session.rollback()
        except Exception as _e:
            log.warning("slr rollback during DB busy failed: %s", _e)
        return 0


def start_slr_workers(app) -> None:
    """Idempotent: launch the pump thread once per process.

    Uses fcntl lock so only ONE gunicorn worker runs the SLR pump.
    This prevents 16 workers × 10 SLR threads = 160 concurrent SLR jobs
    (which would overwhelm PostgreSQL and external APIs).
    The DB-backed atomic claim still works for multi-process safety.
    """
    global _started, _executor, _pump_thread, _slr_lock_fd
    with _lock:
        if _started:
            return

        # Acquire exclusive fcntl lock — only one gunicorn worker gets this.
        _slr_marker = "/tmp/papergenerator-slr-workers.lock"
        try:
            import fcntl as _fcntl
            _fd = open(_slr_marker, "w")
            try:
                _fcntl.flock(_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                # We got the lock — this worker runs the SLR pool
                _fd.write(str(os.getpid()))
                _fd.flush()
                _slr_lock_fd = _fd  # hold ref to prevent GC
            except (IOError, OSError):
                # Another worker already has it — skip
                _fd.close()
                log.info("SLR worker pool already running in another process, skipping")
                return
        except Exception:
            log.exception("Failed to acquire SLR worker lock")
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
            target=_pump_loop, args=(app,), daemon=True, name="slr-pump"
        )
        _pump_thread.start()
        log.info("SLR worker pool started (max=%d, single-process)", SLR_MAX_WORKERS)


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
        queued_count = db.session.query(SlrJob).filter(SlrJob.status == "queued").count()
        if queued_count >= 5:
            try:
                _sweep_dead_running_jobs(app, reason="Job timeout")
            except Exception:
                log.exception("slr.opportunistic sweep failed")
    except Exception:
        log.exception("slr.queued_count probe failed")

    # Pull up to `free` queued jobs and atomically transition to 'running'.
    candidates = (
        db.session.query(SlrJob)
        .filter(SlrJob.status == "queued")
        .order_by(SlrJob.queued_at.asc())
        .limit(free * 2)
        .all()
    )
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
        stmt = (
            sa_update(SlrJob)
            .where(SlrJob.id == job.id, SlrJob.status == "queued")
            .values(
                status="running",
                started_at=now,
                stage="fetching",
                progress=1,
                progress_message="Worker picked up the job",
            )
        )
        try:
            result = db.session.execute(stmt)
            safe_commit()
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
            # NOTE: already inside outer app_context from _run_job
            try:
                if cancel_event.is_set():
                    try:
                        info["cancelled"] = True
                    except Exception:
                        pass
                    raise WorkerCancelled()
                j = (
                    db.session.query(SlrJob)
                    .filter_by(id=job_id)
                    .with_for_update(skip_locked=True)
                    .first()
                )
                if not j:
                    return
                if j.status == "cancelled":
                    cancel_event.set()
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
                j.stage = stage[:40]
                j.progress_message = _stage_message(stage, info)[:200]
                j.progress = _stage_to_pct(stage, info)
                _safe_commit(job_id, where="progress")
            except WorkerCancelled:
                raise
            except Exception:
                log.exception("slr.progress callback failed job=%s", job_id)

        def save_cb(records: list[dict]):
            """Final save: update scores/summaries for existing rows, insert new ones."""
            # NOTE: already inside outer app_context from _run_job
            try:
                # Re-fetch job to get fresh state
                j = db.session.query(SlrJob).filter_by(id=job_id).first()
                if not j or j.status != "running":
                    return

                # Load existing DOIs for this job
                existing = db.session.query(LiteratureItem.id, LiteratureItem.doi).filter_by(
                    slr_job_id=job_id
                ).all()
                existing_by_doi = {d.lower(): id for id, d in existing if d}

                seen_dois: set[str] = set()
                for rec in records:
                    title = (rec.get("title") or "").strip()
                    if not title:
                        continue
                    doi_raw = rec.get("doi") or None
                    doi_key = (doi_raw or "").strip().lower()
                    if doi_key and doi_key in seen_dois:
                        continue

                    pi = rec.get("publisher_info") or {}
                    
                    # Update existing or insert new
                    if doi_key and doi_key in existing_by_doi:
                        item = db.session.get(LiteratureItem, existing_by_doi[doi_key])
                        if item:
                            item.score_total = rec.get("score_total")
                            item.score_breakdown = rec.get("score_breakdown") or {}
                            item.summary = rec.get("summary") or ""
                            item.gap_riset = rec.get("gap_riset") or ""
                            item.citations = rec.get("citations")
                            item.is_relevant = bool(rec.get("is_relevant", True))
                    else:
                        item = LiteratureItem(
                            paper_id=job.paper_id,
                            user_id=job.user_id,
                            source_kind="slr",
                            source=rec.get("venue") or rec.get("publisher") or rec.get("source") or "",
                            title=title,
                            authors=rec.get("authors") or [],
                            year=rec.get("year") or pi.get("year"),
                            venue=rec.get("venue") or pi.get("venue") or "",
                            publisher=rec.get("publisher") or pi.get("publisher") or "",
                            doi=doi_raw,
                            url=rec.get("url") or "",
                            pdf_url=rec.get("pdf_url") or None,
                            abstract=rec.get("abstract") or "",
                            summary=rec.get("summary") or "",
                            gap_riset=rec.get("gap_riset") or "",
                            citations=rec.get("citations"),
                            score_total=rec.get("score_total"),
                            score_breakdown=rec.get("score_breakdown") or {},
                            must_read=bool(rec.get("score_total", 0) >= 85),
                            is_relevant=bool(rec.get("is_relevant", True)),
                            slr_job_id=job_id,
                        )
                        db.session.add(item)
                        if doi_key:
                            seen_dois.add(doi_key)
                _safe_commit(job_id, where="save_cb.final")
                log.info("slr.save_cb: updated %d papers for job=%s", len(records), job_id)
            except Exception as e:
                log.exception("slr.save_cb failed job=%s: %s", job_id, e)

        # Track streaming state for this job (mutable container to avoid function attribute LSP warning)
        streaming_state = {'cleared': False}

        def source_save_cb(papers: list):
            """Streaming save per-source: insert papers immediately after fetch."""
            # NOTE: already inside outer app_context from _run_job
            try:
                    j = db.session.query(SlrJob).filter_by(id=job_id).first()
                    if not j or j.status != "running":
                        return

                    # Clear on first source (re-run scenario)
                    if not streaming_state['cleared']:
                        db.session.query(LiteratureItem).filter_by(slr_job_id=job_id).delete(
                            synchronize_session=False
                        )
                        streaming_state['cleared'] = True

                    # Load existing DOIs
                    existing_dois = set(
                        d for (d,) in db.session.query(LiteratureItem.doi).filter_by(
                            slr_job_id=job_id
                        ).all() if d
                    )
                    existing_dois = {d.lower() for d in existing_dois}

                    count = 0
                    for p in papers:
                        title = (p.title or "").strip()
                        if not title:
                            continue
                        doi_raw = p.doi or None
                        doi_key = (doi_raw or "").strip().lower()
                        if doi_key and doi_key in existing_dois:
                            continue

                        item = LiteratureItem(
                            paper_id=job.paper_id,
                            user_id=job.user_id,
                            source_kind="slr",
                            source=p.venue or p.publisher or p.source or "",
                            title=title,
                            authors=p.authors or [],
                            year=p.year,
                            venue=p.venue or "",
                            publisher=p.publisher or "",
                            doi=doi_raw,
                            url=p.url or "",
                            pdf_url=p.pdf_url or None,
                            abstract=p.abstract or "",
                            summary="",
                            gap_riset="",
                            citations=p.citations,
                            score_total=None,  # Will be updated in final save_cb
                            score_breakdown={},
                            must_read=False,
                            is_relevant=True,
                            slr_job_id=job_id,
                        )
                        db.session.add(item)
                        if doi_key:
                            existing_dois.add(doi_key)
                        count += 1

                    if count > 0:
                        _safe_commit(job_id, where="source_save_cb.streaming")
                        log.info("slr.source_save_cb: saved %d papers for job=%s", count, job_id)
            except Exception as e:
                log.exception("slr.source_save_cb failed job=%s: %s", job_id, e)

        try:
            payload = run_slr_pipeline(
                query=job.query,
                sources=(job.sources or None),
                per_source=int(job.per_source) if job.per_source is not None else 60,
                top_k=int(job.top_k) if job.top_k is not None else 50,
                year_from=job.year_from,
                ai_summarize=bool(job.ai_summarize),
                ai_model=job.ai_model or None,
                progress_cb=progress,
                save_cb=save_cb,
                source_save_cb=source_save_cb,
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
                    .where(SlrJob.id == job_id, SlrJob.status.in_(("running", "cancelled")))
                    .values(
                        status="cancelled",
                        stage="cancelled",
                        progress_message="Job cancelled",
                        finished_at=now,
                    )
                )
                _safe_commit(job_id, where="cancelled")
            except Exception:
                db.session.rollback()
                log.exception("slr.cancel commit failed job=%s", job_id)
            return
        except Exception as e:
            log.exception(
                "slr.pipeline error job=%s query=%r sources=%s",
                job_id,
                (job.query or "")[:200],
                (job.sources or []),
            )
            j = db.session.query(SlrJob).filter_by(id=job_id).first()
            if j:
                j.status = "error"
                j.stage = "error"
                j.error = str(e)[:2000]
                j.finished_at = datetime.now(timezone.utc)
                _safe_commit(job_id, where="error")
            return

        # Detect a totally empty pipeline run — every source failed (e.g.
        # transient network) — and surface as an error instead of a silent
        # 'done with 0 results'.
        stats = payload.get("stats") or {}
        total_unique = int(stats.get("total_unique_papers") or 0)
        top = payload.get("top_k") or []
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

        # Recycle session after long pipeline run
        try:
            db.session.rollback()
        except Exception as _e:
            log.warning("slr session recycle rollback failed: %s", _e)
        try:
            db.session.remove()
        except Exception:
            log.warning("slr.literature session.remove() failed job=%s", job_id, exc_info=True)

        # Re-fetch the job row through the new session
        job = db.session.query(SlrJob).filter_by(id=job_id).first()
        if not job:
            return

        # Save cb already persisted rows during pipeline. Just mark done.

        j = db.session.query(SlrJob).filter_by(id=job_id).first()
        if not j:
            return
        # Don't overwrite a row that was cancelled/errored mid-flight.
        if j.status not in ("running",):
            return
        j.status = "done"
        j.stage = "done"
        j.progress = 100
        j.progress_message = f"Selesai. {len(top)} paper teratas tersimpan ke Literatur tab."
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
        return (
            f"{info.get('source', '?')} → {info.get('count', 0)} hasil "
            f"({info.get('completed', 0)}/{info.get('total', 0)})"
        )
    if stage == "dedup_done":
        return f"Dedup selesai: {info.get('count', 0)} unique paper"
    if stage == "scoring":
        return f"Ranking {info.get('count', 0)} paper (SBERT + sitasi + recency)…"
    if stage == "scored":
        return f"{info.get('count', 0)} paper terskor"
    if stage == "summarizing":
        return f"Scoring programmatik {info.get('count', 0)} paper…"
    if stage == "summarized":
        return f"Scoring selesai ({info.get('done', 0)}/{info.get('total', 0)})"
    if stage == "complete":
        return f"Selesai: top-{info.get('top_k', 0)} dari {info.get('total', 0)} paper"
    return stage
