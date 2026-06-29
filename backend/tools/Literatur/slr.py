"""SLR orchestrator — intelligent pipeline with LLM-assisted routing.

Architecture:
    Keyword → slrFetch.analyze_keyword() → route_fetchers()
        → ThreadPoolExecutor parallel fetch (6 workers, per-fetcher rate limiting)
        → Collect + incremental dedup
        → slrSummarize.summarize() → groups + statistics
        → Return to frontend with progress streaming (0-100%)

Usage:
    from tools.Literatur.slr import slr_new_bp
    app.register_blueprint(slr_new_bp)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from tools.Literatur.fetchers import ALL as FETCHER_ALL
from tools.Literatur.http_client import RateLimiter, get_client
from tools.Literatur.paper import Paper
from tools.Literatur.slrFetch import analyze_keyword, route_fetchers, guess_fetchers
from tools.Literatur.slrSummarize import summarize as summarize_papers

log = logging.getLogger(__name__)
slr_new_bp = Blueprint("slr_new", __name__)

# ── Configuration ─────────────────────────────────────────────────────────

MAX_WORKERS = 6
FETCH_TIMEOUT_SEC = 120
FETCH_LIMIT_PER_FETCHER = 30
PARTIAL_RESULTS_PREVIEW = 20
REDIS_KEY_PREFIX = "slr_new:"
REDIS_PROGRESS_TTL = 600  # 10 min

# ── Redis (best-effort) ───────────────────────────────────────────────────

_redis: Any = None
try:
    import redis as _redis_mod

    _r = _redis_mod.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=0,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        password=os.getenv("REDIS_PASSWORD") or None,
    )
    _r.ping()
    _redis = _r
except Exception:
    log.warning("Redis unavailable for SLR orchestrator; using in-memory progress")
    _redis = None

# ── In-memory job store ──────────────────────────────────────────────────

_jobs: dict[str, "SLRJob"] = {}
_jobs_lock = threading.Lock()

# Per-fetcher rate limiters (shared across workers)
_rate_limiters: dict[str, RateLimiter] = {}


# ── Job tracking class ────────────────────────────────────────────────────

class SLRJob:
    """Tracks state of one SLR job.

    In-memory storage. Redis used for cross-process progress visibility.
    Thread-safe via the orchestrator lock.
    """

    __slots__ = (
        "job_id", "paper_id", "keyword", "top_n", "user_id",
        "status", "stage", "progress_pct", "stage_detail",
        "error", "results", "partial_results", "summary_result",
        "sources_completed", "sources_total", "sources_running", "sources_pending",
        "papers_fetched", "all_papers_count",
        "started_at", "stopped",
        "per_source",
    )

    def __init__(
        self,
        job_id: str,
        paper_id: str,
        keyword: str,
        top_n: int,
        user_id: int,
        per_source: int = 30,
    ):
        self.job_id = job_id
        self.paper_id = paper_id
        self.keyword = keyword
        self.top_n = top_n
        self.user_id = user_id
        self.status = "pending"
        self.stage = "pending"
        self.progress_pct = 0.0
        self.stage_detail = ""
        self.error: str | None = None
        self.results: list[dict] | None = None
        self.partial_results: list[dict] = []
        self.summary_result: dict | None = None
        self.sources_completed: list[str] = []
        self.sources_total = 0
        self.sources_running: list[str] = []
        self.sources_pending: list[str] = []
        self.papers_fetched = 0
        self.all_papers_count = 0
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.stopped = threading.Event()
        self.per_source = per_source

    def to_dict(self) -> dict:
        """Serialize to dict for API responses and Redis.

        Field mapping for frontend compatibility:
        - status: keep original ('pending'/'analyzing'/'fetching'/etc) for filtering
        - progress_pct → progress (0-100)
        - stage_detail → progress_message
        """
        d: dict[str, Any] = {
            "id": self.job_id,
            "job_id": self.job_id,
            "paper_id": self.paper_id,
            "user_id": self.user_id,
            "query": self.keyword,
            "status": self.status,
            "stage": self.stage,
            "progress": int(self.progress_pct),
            "progress_pct": self.progress_pct,
            "progress_message": self.stage_detail,
            "stage_detail": self.stage_detail,
            "sources_completed": list(self.sources_completed),
            "sources_total": self.sources_total,
            "sources_running": list(self.sources_running),
            "sources_pending": list(self.sources_pending),
            "papers_fetched": self.papers_fetched,
            "all_papers_count": self.all_papers_count,
            "error": self.error,
            "partial_results": self.partial_results[:PARTIAL_RESULTS_PREVIEW],
            "results": self.results,
        }

        # Include summary result if available (for detailed endpoint)
        if self.summary_result is not None:
            d["summary_result"] = self.summary_result

        return d

    def cancel(self):
        """Signal cancellation to running workers."""
        self.stopped.set()


# ── Redis progress helpers ────────────────────────────────────────────────

def _redis_key(job_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}{job_id}"


def _push_progress(job: SLRJob):
    """Write job progress to Redis (best-effort)."""
    if _redis is None:
        return
    try:
        data = json.dumps(job.to_dict())
        _redis.setex(_redis_key(job.job_id), REDIS_PROGRESS_TTL, data)
    except Exception:
        pass


def _stream_partial_results(job: SLRJob, new_papers: list[dict]):
    """Append new papers to partial_results and push to Redis."""
    job.partial_results.extend(new_papers)
    job.papers_fetched += len(new_papers)
    _push_progress(job)


# ── Rate limiter factory ──────────────────────────────────────────────────

def _get_rate_limiters() -> dict[str, RateLimiter]:
    """Return shared rate limiters dict, seeded with optimized intervals for high-quality sources."""
    if not _rate_limiters:
        # Tier 1 Premium - aggressive but respectful (Scopus prioritized)
        _rate_limiters["scopus"] = RateLimiter(min_interval=0.8)  # Premium source, be respectful
        _rate_limiters["sciencedirect"] = RateLimiter(min_interval=1.0)  # Elsevier
        _rate_limiters["ieee"] = RateLimiter(min_interval=1.2)  # IEEE premium
        _rate_limiters["pubmed"] = RateLimiter(min_interval=0.4)  # Fast, reliable
        _rate_limiters["europepmc"] = RateLimiter(min_interval=0.5)  # Good performance
        
        # Tier 2 Broad - moderate intervals
        _rate_limiters["openalex"] = RateLimiter(min_interval=0.3)  # Very fast
        _rate_limiters["crossref"] = RateLimiter(min_interval=0.5)  # Reliable
        _rate_limiters["semantic_scholar"] = RateLimiter(min_interval=0.8)  # Moderate
        _rate_limiters["dimensions"] = RateLimiter(min_interval=1.0)
        _rate_limiters["lens"] = RateLimiter(min_interval=1.2)
        
        # Tier 3 Specialized - varied intervals
        _rate_limiters["arxiv"] = RateLimiter(min_interval=0.3)  # Fast preprints
        _rate_limiters["dblp"] = RateLimiter(min_interval=0.5)  # CS bibliography
        _rate_limiters["pmc"] = RateLimiter(min_interval=0.5)  # PMC full-text
        _rate_limiters["biorxiv"] = RateLimiter(min_interval=1.0)  # Preprints
        _rate_limiters["plos"] = RateLimiter(min_interval=1.0)  # PLOS journals
        
        # Tier 4 Indonesian - respectful to local infrastructure
        _rate_limiters["sinta"] = RateLimiter(min_interval=1.5)  # Indonesian source
        
        # Tier 5 Books and others - conservative
        _rate_limiters["google_books"] = RateLimiter(min_interval=1.0)
        _rate_limiters["open_library"] = RateLimiter(min_interval=1.2)
        _rate_limiters["doab"] = RateLimiter(min_interval=1.5)
        _rate_limiters["oapen"] = RateLimiter(min_interval=1.5)
        _rate_limiters["gutendex"] = RateLimiter(min_interval=1.0)
        _rate_limiters["cambridge"] = RateLimiter(min_interval=2.0)  # Scraping
        
        # Others
        _rate_limiters["doaj"] = RateLimiter(min_interval=1.5)
        _rate_limiters["zenodo"] = RateLimiter(min_interval=1.0)
        _rate_limiters["datacite"] = RateLimiter(min_interval=1.0)
        _rate_limiters["openaire"] = RateLimiter(min_interval=1.0)
        _rate_limiters["hal"] = RateLimiter(min_interval=1.5)
        
    return _rate_limiters


# ── LLM call helper ──────────────────────────────────────────────────────

def _get_llm_call() -> Callable[[str, str], str] | None:
    """Build an llm_call(system_prompt, user_message) -> str wrapper.

    Uses utils.ai_tools.model_router.route_chat_call when available.
    Returns None if the model router is unreachable — downstream code
    falls back to guess_fetchers / programmatic summarize.
    """
    try:
        from utils.ai_tools.model_router import route_chat_call  # noqa: F401
    except (ImportError, Exception) as e:
        log.debug("model_router unavailable (%s), using rule-based fallback", e)
        return None

    def llm_call(system_prompt: str, user_message: str) -> str:
        """Call the chat model via route_chat_call. Raises on failure."""
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 4096,
            "temperature": 0.3,
        }
        resp, _model_used = route_chat_call(
            json=payload,
            timeout=120,
        )
        # resp is a requests.Response — extract message content
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("LLM returned non-string content")
        return content

    return llm_call


# ── Orchestrator ──────────────────────────────────────────────────────────

class SLROrchestrator:
    """Manages SLR jobs: start, poll, cancel.

    Pipeline: analyze_keyword → route_fetchers → parallel fetch → summarize.
    All job state is in-memory; cross-process progress via Redis.
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=MAX_WORKERS,
            thread_name_prefix="slr-fetch",
        )

    def start_job(
        self,
        paper_id: str,
        keyword: str,
        top_n: int,
        user_id: int,
        sources: list[str] | None = None,
        year_from: int | None = None,
        ai_summarize: bool = False,
        per_source: int = 30,
    ) -> str:
        """Create and start a new SLR job. Returns job_id string."""
        job_id = f"slr_{uuid.uuid4().hex[:12]}"

        with _jobs_lock:
            job = SLRJob(
                job_id=job_id, paper_id=paper_id, keyword=keyword,
                top_n=top_n, user_id=user_id, per_source=per_source,
            )
            _jobs[job_id] = job

        # Register job in Redis set for cross-worker discovery
        try:
            if _redis is not None:
                set_key = f"slr_new:paper:{paper_id}:{user_id}"
                _redis.sadd(set_key, job_id)
                _redis.expire(set_key, 10800)  # 3 hours
        except Exception:
            pass

        # Push initial job state to Redis so it's immediately visible to all workers
        _push_progress(job)

        # Fire-and-forget the pipeline in a background thread
        thread = threading.Thread(
            target=self._run_pipeline,
            args=(job, keyword, top_n, sources, year_from, ai_summarize),
            daemon=True,
            name=f"slr-run-{job_id}",
        )
        thread.start()

        return job_id

    def get_job(self, job_id: str) -> dict | None:
        """Get job status dict, or None if not found."""
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                # Try Redis (cross-process fallback)
                if _redis is not None:
                    try:
                        data = _redis.get(_redis_key(job_id))
                        if data:
                            return json.loads(data)
                    except Exception:
                        pass
                return None
            return job.to_dict()

    def get_job_summary(self, job_id: str) -> dict | None:
        """Get job summary_result (grouped/summarized output) if complete."""
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return None
            if job.summary_result is None:
                return None
            return job.summary_result

    def cancel_job(self, job_id: str):
        """Cancel a running job."""
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return
            job.status = "cancelled"
            job.stage = "cancelled"
            job.progress_pct = 0
            job.stage_detail = "Cancelled by user"
            job.cancel()
            _push_progress(job)

    # ── Pipeline internals ─────────────────────────────────────────────

    def _run_pipeline(
        self,
        job: SLRJob,
        keyword: str,
        top_n: int,
        sources: list[str] | None,
        year_from: int | None,
        ai_summarize: bool,
    ):
        """Full pipeline: analyze → fetch → summarize → complete."""
        try:
            # ── Stage 1: Analyze keyword (0-10%) ──────────────────────
            self._set_stage(job, "analyzing", 2.0, "Analyzing keyword for source routing...")

            llm_call = _get_llm_call()

            try:
                analysis = analyze_keyword(keyword, llm_call=llm_call)
            except Exception as exc:
                log.warning("analyze_keyword failed (%s), using guess_fetchers", exc)
                analysis = guess_fetchers(keyword)

            # Route fetchers: {fetcher_name: [queries...]}
            fetch_map = route_fetchers(analysis)

            # If user explicitly provided sources, override
            if sources:
                available = set(FETCHER_ALL.keys())
                user_sources = [s for s in sources if s in available]
                if user_sources:
                    fetch_map = {s: [keyword] for s in user_sources}

            if not fetch_map:
                self._set_error(job, "No fetcher sources available for this query")
                return

            fetcher_names = list(fetch_map.keys())
            total_queries = sum(len(qs) for qs in fetch_map.values())

            job.sources_total = len(fetcher_names)
            job.sources_pending = list(fetcher_names)

            self._set_stage(
                job, "analyzing", 10.0,
                f"Analyzed → {len(fetcher_names)} sources, "
                f"{total_queries} queries, "
                f"domains: {', '.join(analysis.get('domains', ['general']))}",
            )

            # ── Stage 2: Parallel fetch (10-70%) ──────────────────────
            self._set_stage(job, "fetching", 10.0, "Starting parallel fetchers...")

            filters: dict = {}
            if year_from:
                filters["year_from"] = year_from

            all_papers: list[Paper] = []
            seen_keys: dict[str, int] = {}  # dedup_key → index in all_papers

            sources_running_set: set[str] = set(fetcher_names)
            sources_done: set[str] = set()

            # Build flat task list: (fetcher_name, query)
            fetch_tasks: list[tuple[str, str]] = []
            for fn, queries in fetch_map.items():
                for q in queries:
                    fetch_tasks.append((fn, q))

            # Submit all fetch tasks
            futures = {}
            for fn, q in fetch_tasks:
                future = self._executor.submit(
                    self._fetch_single_source, fn, q, job.per_source, filters
                )
                futures[future] = (fn, q)

            job.sources_running = list(sources_running_set)
            job.sources_pending = []
            _push_progress(job)

            # Process results as they complete
            for future in as_completed(futures, timeout=FETCH_TIMEOUT_SEC):
                fn, q = futures[future]
                if job.stopped.is_set():
                    continue

                try:
                    papers = future.result()
                except Exception as exc:
                    log.warning("Fetcher %s (q=%s) failed: %s", fn, q[:30], exc)
                    papers = []

                sources_done.add(fn)
                sources_running_set.discard(fn)
                completed_count = len(sources_done)

                # Dedup incrementally against existing results
                new_papers: list[Paper] = []
                for p in papers:
                    k = p.dedup_key()
                    if k not in seen_keys:
                        seen_keys[k] = len(all_papers)
                        all_papers.append(p)
                        new_papers.append(p)

                # Update progress
                pct_progress = 10.0 + (completed_count / len(fetcher_names)) * 60.0
                job.sources_completed = list(sources_done)
                job.sources_running = list(sources_running_set)
                job.sources_pending = [
                    s for s in fetcher_names
                    if s not in sources_done and s not in sources_running_set
                ]

                # Stream preview of latest papers to frontend
                partial_dicts = []
                for p in new_papers:
                    try:
                        d = p.to_dict()
                    except Exception:
                        d = {"title": p.title, "source": p.source}
                    partial_dicts.append(d)
                if partial_dicts:
                    _stream_partial_results(job, partial_dicts)

                self._set_stage(
                    job, "fetching", min(pct_progress, 70.0),
                    f"Fetched {completed_count}/{len(fetcher_names)} sources "
                    f"({len(all_papers)} unique papers)",
                    extra={"all_papers_count": len(all_papers)},
                )

            if job.stopped.is_set():
                self._set_stage(job, "cancelled", 0.0, "Cancelled by user")
                return

            # ── Stage 3: Summarize (70-95%) ───────────────────────────
            self._set_stage(
                job, "summarizing", 70.0,
                f"Processing {len(all_papers)} papers: dedup → rank → group...",
            )

            # Convert Paper objects → dicts for slrSummarize
            paper_dicts = []
            for p in all_papers:
                try:
                    d = p.to_dict()
                    # Remove fields not expected by summarize (avoids noise)
                    d.pop("db_score", None)
                    d.pop("venue_type", None)
                    paper_dicts.append(d)
                except Exception:
                    paper_dicts.append({
                        "source": p.source,
                        "source_id": p.source_id,
                        "title": p.title,
                        "authors": p.authors,
                        "year": p.year,
                        "doi": p.doi,
                        "url": p.url,
                        "pdf_url": p.pdf_url,
                        "abstract": p.abstract,
                        "venue": p.venue,
                        "publisher": p.publisher,
                        "type": p.type,
                        "is_open_access": p.is_open_access,
                        "citations": p.citations,
                    })

            self._set_stage(
                job, "summarizing", 78.0,
                f"Deduplicating and ranking {len(paper_dicts)} papers...",
            )

            # Call slrSummarize.summarize() — returns top_n × 5 grouped results
            summarize_llm = llm_call if ai_summarize else None
            try:
                summary_result = summarize_papers(
                    papers=paper_dicts,
                    query=keyword,
                    top_n=top_n,
                    llm_call=summarize_llm,
                )
            except Exception as exc:
                log.warning("summarize_papers failed (%s), building fallback", exc)
                summary_result = self._fallback_summarize(paper_dicts, keyword, top_n)

            self._set_stage(
                job, "summarizing", 90.0,
                f"Grouped into {len(summary_result.get('groups', []))} categories "
                f"({summary_result.get('total_returned', 0)} papers returned)",
            )

            # ── Stage 4: Save & complete (95-100%) ────────────────────
            self._set_stage(job, "summarizing", 95.0, "Saving results...")

            # Extract flat paper list from groups for DB save
            all_result_papers = []
            for group in summary_result.get("groups", []):
                all_result_papers.extend(group.get("papers", []))

            # Best-effort DB save (non-blocking)
            self._save_to_db(job, all_result_papers[:top_n * 5])

            # Build final results list (flat, top_n for compatibility)
            final_results = all_result_papers[:top_n]

            with _jobs_lock:
                job.results = final_results
                job.summary_result = summary_result
                job.status = "completed"
                job.stage = "complete"
                job.progress_pct = 100.0
                job.all_papers_count = summary_result.get("total_fetched", len(all_papers))
                job.stage_detail = (
                    f"Complete: {summary_result.get('total_returned', len(final_results))} papers "
                    f"in {len(summary_result.get('groups', []))} groups "
                    f"(from {summary_result.get('total_fetched', 0)} fetched, "
                    f"{summary_result.get('total_unique', 0)} unique)"
                )
                job.partial_results = final_results[:PARTIAL_RESULTS_PREVIEW]

            _push_progress(job)

        except Exception as exc:
            log.exception("SLR pipeline failed for job %s", job.job_id)
            self._set_error(job, f"Pipeline error: {exc}")

    # ── Helpers ─────────────────────────────────────────────────────────

    def _set_stage(
        self, job: SLRJob, stage: str, pct: float, detail: str,
        extra: dict | None = None,
    ):
        with _jobs_lock:
            job.stage = stage
            job.progress_pct = pct
            job.stage_detail = detail
            if stage in ("fetching", "ranking", "summarizing", "complete"):
                job.status = stage
            if extra:
                for k, v in extra.items():
                    setattr(job, k, v)
        _push_progress(job)

    def _set_error(self, job: SLRJob, msg: str):
        with _jobs_lock:
            job.status = "error"
            job.stage = "error"
            job.error = msg
        _push_progress(job)

    @staticmethod
    def _fallback_summarize(paper_dicts: list[dict], keyword: str, top_n: int) -> dict:
        """Fallback when slrSummarize fails — basic dedup + rank."""
        from tools.Literatur.slrSummarize import programmatic_dedup, programmatic_rank

        try:
            unique = programmatic_dedup(paper_dicts)
            ranked = programmatic_rank(unique, keyword)
            limit = top_n * 5
            top = ranked[:limit]
            return {
                "total_fetched": len(paper_dicts),
                "total_unique": len(unique),
                "total_returned": len(top),
                "groups": [{"label": "All Results", "description": "Ranked papers", "count": len(top), "papers": top}],
                "method_distribution": {"All Results": len(top)},
                "statistics": {},
            }
        except Exception:
            return {
                "total_fetched": len(paper_dicts),
                "total_unique": len(paper_dicts),
                "total_returned": min(len(paper_dicts), top_n * 5),
                "groups": [{"label": "All Results", "description": "", "count": len(paper_dicts[:top_n * 5]), "papers": paper_dicts[:top_n * 5]}],
                "method_distribution": {"All Results": min(len(paper_dicts), top_n * 5)},
                "statistics": {},
            }

    @staticmethod
    def _save_to_db(job: SLRJob, papers: list[dict]):
        """Save SLR results as LiteratureItem records (best-effort, non-blocking)."""
        try:
            from sqlalchemy.exc import IntegrityError
        except ImportError:
            log.debug("SQLAlchemy not available, skipping DB save")
            return

        try:
            from main import app as _flask_app
            ctx = _flask_app.app_context()
            ctx.push()
        except Exception:
            ctx = None

        try:
            from utils.database.models import LiteratureItem, db, safe_commit

            saved = 0
            for p in papers:
                doi = (p.get("doi") or "").strip() or None
                # Skip if DOI already exists for this paper_id
                if doi:
                    existing = LiteratureItem.query.filter_by(
                        paper_id=job.paper_id, doi=doi
                    ).first()
                    if existing:
                        continue
                else:
                    # For papers without DOI, skip if same title already exists
                    title_norm = (p.get("title") or "").strip().lower()
                    if title_norm:
                        existing = LiteratureItem.query.filter_by(
                            paper_id=job.paper_id, title_norm=title_norm
                        ).first()
                        if existing:
                            continue

                item = LiteratureItem(
                    paper_id=job.paper_id,
                    user_id=job.user_id,
                    source_kind="slr",
                    source=(p.get("source") or "slr")[:40],
                    title=(p.get("title") or "").strip(),
                    title_norm=(p.get("title") or "").strip().lower() or None,
                    authors=p.get("authors") or [],
                    year=p.get("year"),
                    doi=doi,
                    url=(p.get("url") or p.get("pdf_url") or "").strip(),
                    pdf_url=p.get("pdf_url") or None,
                    abstract=(p.get("abstract") or "").strip(),
                    citations=p.get("citations"),
                    score_total=p.get("relevance_score"),
                    score_breakdown=p.get("score_breakdown", {}),
                    notes=(p.get("summary") or "")[:1000],
                    is_checked=True,
                    slr_job_id=None,
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(item)
                saved += 1
                if saved >= 100:
                    break

            try:
                safe_commit()
                log.info(
                    "SLR saved %d LiteratureItems for paper %s job %s",
                    saved, job.paper_id, job.job_id,
                )
            except IntegrityError:
                db.session.rollback()
                log.warning(
                    "IntegrityError saving LiteratureItems for job %s (likely duplicate DOI)",
                    job.job_id,
                )
            except Exception:
                db.session.rollback()
                log.warning("Failed to save LiteratureItems for job %s", job.job_id, exc_info=True)
        except Exception as exc:
            log.warning("_save_to_db error: %s", exc)
        finally:
            if ctx:
                try:
                    ctx.pop()
                except Exception:
                    pass

    @staticmethod
    def _fetch_single_source(
        source_name: str,
        query: str,
        limit: int,
        filters: dict | None,
    ) -> list[Paper]:
        """Execute a single fetcher with rate limiting.

        Creates its own httpx.Client. Returns list of Paper objects.
        On any error, returns empty list.
        """
        fetcher_mod = FETCHER_ALL.get(source_name)
        if fetcher_mod is None or not hasattr(fetcher_mod, "search"):
            log.warning("Fetcher %s has no search function; skipping", source_name)
            return []

        # Get or create per-fetcher rate limiter
        rate_limiters = _get_rate_limiters()
        limiter = rate_limiters.get(source_name)
        if limiter is None:
            limiter = RateLimiter(min_interval=3.0)
            rate_limiters[source_name] = limiter

        try:
            with get_client() as client:
                limiter.wait()
                papers = list(fetcher_mod.search(client, query, limit, filters))
                return papers
        except Exception as exc:
            log.debug("Fetcher %s error: %s", source_name, exc)
            return []


# ── Global instance ──────────────────────────────────────────────────────

_orchestrator = SLROrchestrator()


def start_slr_job(
    paper_id: str,
    keyword: str,
    top_n: int = 10,
    user_id: int = 0,
    sources: list[str] | None = None,
    year_from: int | None = None,
    ai_summarize: bool = False,
    per_source: int = 30,
) -> str:
    """Public entry point for starting an SLR job. Returns job_id."""
    return _orchestrator.start_job(
        paper_id=paper_id, keyword=keyword, top_n=top_n,
        user_id=user_id, sources=sources, year_from=year_from,
        ai_summarize=ai_summarize, per_source=per_source,
    )


def get_slr_job(job_id: str) -> dict | None:
    """Public entry point for polling job status."""
    return _orchestrator.get_job(job_id)


def get_slr_summary(job_id: str) -> dict | None:
    """Public entry point for getting grouped/summarized results."""
    return _orchestrator.get_job_summary(job_id)


# ── Flask endpoints ───────────────────────────────────────────────────────

@slr_new_bp.route("/api/papers/<paper_id>/slr/new", methods=["POST"])
@jwt_required(optional=True)
def slr_start(paper_id):
    """Start a new SLR job.

    Body (JSON):
    {
        "query": "keyword search term",
        "top_k": 10,
        "sources": ["openalex", "crossref"],  # optional
        "year_from": 2020,                     # optional
        "ai_summarize": false                  # optional
    }

    Returns:
        {job_id: "slr_abc123", status: "started"}
    """
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}

    query = (data.get("query") or "").strip()
    top_k = int(data.get("top_k", data.get("top_n", 10)))
    sources = data.get("sources")  # list or None
    year_from = data.get("year_from")  # int or None
    ai_summarize = bool(data.get("ai_summarize", False))

    if not query:
        return jsonify({"error": "Missing query"}), 400

    if top_k < 1:
        top_k = 10
    if top_k > 200:
        top_k = 200

    user_id = 0
    try:
        user_id = int(get_jwt_identity() or 0)
    except Exception:
        pass

    job_id = start_slr_job(
        paper_id=paper_id, keyword=query, top_n=top_k,
        user_id=user_id, sources=sources,
        year_from=year_from, ai_summarize=ai_summarize,
    )

    return jsonify({
        "job_id": job_id,
        "status": "started",
        "poll_url": f"/api/slr/new/jobs/{job_id}",
    }), 202


@slr_new_bp.route("/api/slr/new/jobs/<job_id>", methods=["GET"])
def slr_status(job_id):
    """Get SLR job status + partial/final results."""
    job_data = get_slr_job(job_id)
    if job_data is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job_data)


@slr_new_bp.route("/api/slr/new/jobs/<job_id>/summary", methods=["GET"])
def slr_summary(job_id):
    """Get grouped/summarized results for a completed SLR job.

    Returns the full summary_result from slrSummarize:
    {
        "total_fetched": int,
        "total_unique": int,
        "total_returned": int,
        "groups": [
            {"label": str, "description": str, "count": int, "papers": [...]},
            ...
        ],
        "method_distribution": {"group_label": count, ...},
        "statistics": {"by_source": {}, "by_year": {}, "by_type": {}, "open_access_count": int}
    }
    """
    # First check job exists and is complete
    job_data = get_slr_job(job_id)
    if job_data is None:
        return jsonify({"error": "Job not found"}), 404

    if job_data.get("status") != "completed":
        return jsonify({
            "error": "Job not yet complete",
            "status": job_data.get("status"),
            "progress": job_data.get("progress", 0),
        }), 202

    summary = get_slr_summary(job_id)
    if summary is None:
        # Fallback: return from job_data if summary_result was embedded
        embedded = job_data.get("summary_result")
        if embedded:
            return jsonify(embedded)
        return jsonify({"error": "No summary available"}), 404

    return jsonify(summary)


@slr_new_bp.route("/api/slr/new/jobs/<job_id>", methods=["DELETE"])
def slr_cancel(job_id):
    """Cancel a running SLR job."""
    _orchestrator.cancel_job(job_id)
    return jsonify({"status": "cancelled", "job_id": job_id})


# ── End of slr.py ─────────────────────────────────────────────────────────
