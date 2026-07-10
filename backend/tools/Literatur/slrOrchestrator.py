"""SLR Orchestrator — parallel fetchers + summarizer pipeline.

Architecture:
    Keyword → slrFetch.analyze_keyword() → route_fetchers()
        → ThreadPoolExecutor parallel fetch (no limit, all data)
        → Collect all papers (dedup on-the-fly)
        → slrSummarize.summarize() → groups + statistics
        → Return structured results

Usage:
    from tools.Literatur.slrOrchestrator import run_slr
    
    result = run_slr(
        keyword="deep learning medical image",
        top_n=20,
        llm_call=my_llm_func,  # optional
        max_workers=8,
    )
    # result = {groups, statistics, total_fetched, total_unique, total_returned}
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Optional

from dotenv import load_dotenv

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ROOT_ENV, override=False)

from tools.Literatur.fetchers import ALL as FETCHER_ALL
from tools.Literatur.http_client import RateLimiter, get_client
from tools.Literatur.paper import Paper
from tools.Literatur.slrFetch import analyze_keyword, route_fetchers, guess_fetchers
from tools.Literatur.slrSummarize import (
    programmatic_dedup,
    programmatic_rank,
    programmatic_group,
)

log = logging.getLogger(__name__)

# Setup logging directory (absolute path)
_SLR_LOG_DIR_ENV = os.getenv("SLR_LOG_DIR")
if _SLR_LOG_DIR_ENV:
    _LOG_DIR = Path(_SLR_LOG_DIR_ENV)
else:
    # Default: /home/sirobo/papergenerator/backend/log/slr
    _LOG_DIR = Path(__file__).resolve().parents[3] / "log" / "slr"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOG_FILE = _LOG_DIR / "slrOrchestrator.log"
_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
if not any(isinstance(h, logging.FileHandler) for h in log.handlers):
    log.addHandler(_file_handler)
log.info("slrOrchestrator initialized with logging to %s", _LOG_FILE)

# ── Configuration ──────────────────────────────────────────────────────────

MAX_WORKERS_DEFAULT = 8
FETCH_TIMEOUT_SEC = 300  # 5 min total fetch
# PER_FETCHER_LIMIT removed — per-fetcher limit is now computed dynamically as top_n * 2 in run_slr()
RATE_LIMITERS: dict[str, RateLimiter] = {}


def _get_rate_limiters() -> dict[str, RateLimiter]:
    """Return shared rate limiters (lazy init)."""
    global RATE_LIMITERS
    if not RATE_LIMITERS:
        # Tier 1 Premium
        RATE_LIMITERS["scopus"] = RateLimiter(min_interval=0.8)
        RATE_LIMITERS["sciencedirect"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["ieee"] = RateLimiter(min_interval=1.2)
        RATE_LIMITERS["pubmed"] = RateLimiter(min_interval=0.4)
        RATE_LIMITERS["europepmc"] = RateLimiter(min_interval=0.5)

        # Tier 2 Broad
        RATE_LIMITERS["openalex"] = RateLimiter(min_interval=0.3)
        RATE_LIMITERS["crossref"] = RateLimiter(min_interval=0.5)
        RATE_LIMITERS["semantic_scholar"] = RateLimiter(min_interval=0.8)
        RATE_LIMITERS["dimensions"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["lens"] = RateLimiter(min_interval=1.2)

        # Tier 3 Specialized
        RATE_LIMITERS["arxiv"] = RateLimiter(min_interval=0.3)
        RATE_LIMITERS["dblp"] = RateLimiter(min_interval=0.5)
        RATE_LIMITERS["pmc"] = RateLimiter(min_interval=0.5)
        RATE_LIMITERS["biorxiv"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["plos"] = RateLimiter(min_interval=1.0)

        # Tier 4 Indonesian
        RATE_LIMITERS["sinta"] = RateLimiter(min_interval=1.5)

        # Tier 5 Books
        RATE_LIMITERS["google_books"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["open_library"] = RateLimiter(min_interval=1.2)
        RATE_LIMITERS["doab"] = RateLimiter(min_interval=1.5)
        RATE_LIMITERS["oapen"] = RateLimiter(min_interval=1.5)
        RATE_LIMITERS["gutendex"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["cambridge"] = RateLimiter(min_interval=2.0)

        # Others
        RATE_LIMITERS["doaj"] = RateLimiter(min_interval=1.5)
        RATE_LIMITERS["zenodo"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["datacite"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["openaire"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["hal"] = RateLimiter(min_interval=1.5)
        RATE_LIMITERS["unpaywall"] = RateLimiter(min_interval=0.5)
        RATE_LIMITERS["biorxiv"] = RateLimiter(min_interval=1.0)
        RATE_LIMITERS["pmc"] = RateLimiter(min_interval=0.5)

    return RATE_LIMITERS


# ── Fetch worker ───────────────────────────────────────────────────────────

def _fetch_single_source(
    fetcher_name: str,
    query: str,
    limit: Optional[int] = None,
    filters: Optional[dict] = None,
) -> list[Paper]:
    """Fetch papers from single source. No hard limit if limit=None."""
    if fetcher_name not in FETCHER_ALL:
        log.warning("Fetcher %s not found in ALL", fetcher_name)
        return []

    fetcher = FETCHER_ALL[fetcher_name]
    rate_limiters = _get_rate_limiters()
    rl = rate_limiters.get(fetcher_name, RateLimiter(min_interval=0.5))

    try:
        client = get_client()
        rl.wait()
        
        log.info(
            "Fetcher %s: query=%s, limit=%s",
            fetcher_name, query[:50], limit,
        )
        
        papers = list(fetcher.search(
            client=client,
            query=query,
            limit=limit,
            filters=filters or {},
        ))
        
        log.info(
            "Fetcher %s: fetched %d papers (query=%s)",
            fetcher_name, len(papers), query[:50],
        )
        
        return papers
        
    except Exception as exc:
        log.warning(
            "Fetcher %s failed (query=%s): %s",
            fetcher_name, query[:50], exc,
        )
        return []


# ── Main orchestrator ──────────────────────────────────────────────────────

def run_slr(
    keyword: str,
    top_n: int = 20,
    llm_call: Optional[Callable[[str, str], str]] = None,
    max_workers: int = MAX_WORKERS_DEFAULT,
    year_from: Optional[int] = None,
) -> dict:
    """Run full SLR pipeline: analyze → fetch all → dedup → rank → group → summarize.
    
    Parameters
    ----------
    keyword : str
        User's search keyword (e.g., "deep learning medical image analysis")
    top_n : int
        Number of top papers to return per group (default 20)
    llm_call : callable, optional
        LLM function (system_prompt, user_msg) -> str for keyword analysis & summarization.
        If None, falls back to rule-based guess_fetchers.
    max_workers : int
        Number of parallel fetch workers (default 8)
    year_from : int, optional
        Filter papers from this year onward
    
    Returns
    -------
    dict
        {
            "total_fetched": int,
            "total_unique": int,
            "total_returned": int,
            "groups": [
                {
                    "label": str,
                    "description": str,
                    "semantic_coherence": float,
                    "count": int,
                    "min_papers_met": bool,
                    "papers": [Paper dict, ...],
                }
            ],
            "method_distribution": {group_label: count, ...},
            "grouping_notes": str,
            "statistics": {by_source, by_year, by_type, by_language, ...},
        }
    """
    start_time = time.time()
    log.info("Starting SLR pipeline for keyword: %s", keyword)
    
    # ── Stage 1: Analyze keyword ────────────────────────────────────────
    log.info("Stage 1: Analyzing keyword...")
    try:
        analysis = analyze_keyword(keyword, llm_call=llm_call)
    except Exception as exc:
        log.warning("analyze_keyword failed (%s), falling back to guess_fetchers", exc)
        analysis = guess_fetchers(keyword)
    
    # Route fetchers → {fetcher_name: [queries...]}
    fetch_map = route_fetchers(analysis)
    
    if not fetch_map:
        log.error("No fetchers available for keyword: %s", keyword)
        return {
            "total_fetched": 0,
            "total_unique": 0,
            "total_returned": 0,
            "groups": [],
            "method_distribution": {},
            "grouping_notes": "No fetchers available",
            "statistics": {},
        }
    
    fetcher_names = list(fetch_map.keys())
    total_queries = sum(len(qs) for qs in fetch_map.values())
    
    log.info(
        "Analyzed: %d fetchers, %d queries, domains: %s",
        len(fetcher_names), total_queries, analysis.get("domains", []),
    )
    
    # Per-fetcher limit: top_n * 2 (e.g. top_k=50, 3 fetchers → 300 raw papers)
    per_fetcher_limit = max(top_n * 2, 20)  # minimum 20 per fetcher
    log.info("Per-fetcher limit: %d (top_n=%d × 2)", per_fetcher_limit, top_n)
    
    # ── Stage 2: Parallel fetch ─────────────────────────────────────────
    log.info("Stage 2: Parallel fetching from %d sources...", len(fetcher_names))
    
    filters: dict = {}
    if year_from:
        filters["year_from"] = year_from
    
    all_papers: list[Paper] = []
    seen_keys: dict[str, int] = {}  # dedup_key → index
    
    # Build flat task list: (fetcher_name, query)
    fetch_tasks: list[tuple[str, str]] = []
    for fn, queries in fetch_map.items():
        for q in queries:
            fetch_tasks.append((fn, q))
    
    log.info("Submitting %d fetch tasks...", len(fetch_tasks))
    
    # Submit all tasks
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="slr-fetch") as executor:
        futures = {}
        for fn, q in fetch_tasks:
            future = executor.submit(
                _fetch_single_source,
                fn, q,
                limit=per_fetcher_limit,  # = top_n * 2 per fetcher
                filters=filters,
            )
            futures[future] = (fn, q)
        
        # Collect results as they complete
        completed = 0
        try:
            for future in as_completed(futures, timeout=FETCH_TIMEOUT_SEC):
                fn, q = futures[future]
                try:
                    papers = future.result()
                except Exception as exc:
                    log.warning("Fetch task %s (q=%s) failed: %s", fn, q[:30], exc)
                    papers = []
                
                # Dedup on-the-fly
                for p in papers:
                    k = p.dedup_key()
                    if k not in seen_keys:
                        seen_keys[k] = len(all_papers)
                        all_papers.append(p)
                
                completed += 1
                if completed % max(1, len(fetch_tasks) // 5) == 0:
                    log.info(
                        "Fetch progress: %d/%d tasks completed, %d unique papers so far",
                        completed, len(fetch_tasks), len(all_papers),
                    )
        except TimeoutError:
            log.warning("Fetch timeout after %ds — %d/%d tasks completed, using partial results",
                        FETCH_TIMEOUT_SEC, completed, len(futures))
            for f in futures:
                f.cancel()
    
    elapsed = time.time() - start_time
    log.info(
        "Fetch complete: %d unique papers in %.1f sec",
        len(all_papers), elapsed,
    )
    
    # ── Stage 3: Convert to dicts for summarization ──────────────────────
    log.info("Stage 3: Converting papers to dicts...")
    paper_dicts = []
    for p in all_papers:
        try:
            d = p.to_dict()
            d.pop("db_score", None)
            d.pop("venue_type", None)
            paper_dicts.append(d)
        except Exception as exc:
            log.warning("Failed to convert paper %s: %s", p.source_id, exc)
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
    
    total_fetched = len(paper_dicts)
    log.info("Converted %d papers", total_fetched)
    
    # ── Stage 4: Dedup ──────────────────────────────────────────────────
    log.info("Stage 4: Deduplicating %d papers...", total_fetched)
    try:
        unique_papers = programmatic_dedup(paper_dicts)
    except Exception as exc:
        log.warning("programmatic_dedup failed (%s), using raw list", exc)
        unique_papers = paper_dicts
    
    total_unique = len(unique_papers)
    log.info("Dedup result: %d unique papers (removed %d duplicates)",
             total_unique, total_fetched - total_unique)
    
    # ── Stage 5: Rank ──────────────────────────────────────────────────
    log.info("Stage 5: Ranking %d papers by relevance...", total_unique)
    try:
        ranked_papers = programmatic_rank(unique_papers, keyword)
    except Exception as exc:
        log.warning("programmatic_rank failed (%s), using original order", exc)
        ranked_papers = unique_papers
    
    log.info("Ranked papers")
    
    # ── Stage 6: Group ──────────────────────────────────────────────────
    log.info("Stage 6: Grouping papers by method/theme...")
    try:
        grouping_result = programmatic_group(ranked_papers, min_group_size=20)
    except Exception as exc:
        log.error("programmatic_group failed (%s)", exc)
        grouping_result = {
            "groups": [{
                "label": "All Results",
                "description": "Ranked papers",
                "semantic_coherence": 0.5,
                "count": len(ranked_papers),
                "min_papers_met": len(ranked_papers) >= 20,
                "papers": ranked_papers[:top_n * 5],
            }],
            "grouping_notes": "Grouping failed; returning raw ranked results",
            "groups_with_min_papers": 1 if len(ranked_papers) >= 20 else 0,
            "groups_below_min_papers": 0 if len(ranked_papers) >= 20 else 1,
        }
    
    groups = grouping_result["groups"]
    log.info("Grouped into %d groups", len(groups))
    
    # ── Stage 7: Build statistics ───────────────────────────────────────
    log.info("Stage 7: Building statistics...")
    
    by_source: dict[str, int] = {}
    by_year: dict[int, int] = {}
    by_type: dict[str, int] = {}
    by_language: dict[str, int] = {"id": 0, "en": 0}
    open_access_count = 0
    
    for p in ranked_papers:
        by_source[p.get("source", "unknown")] = by_source.get(p.get("source", "unknown"), 0) + 1
        if p.get("year"):
            by_year[p["year"]] = by_year.get(p["year"], 0) + 1
        by_type[p.get("type", "unknown")] = by_type.get(p.get("type", "unknown"), 0) + 1
        lang = p.get("language_origin", "en")
        by_language[lang] = by_language.get(lang, 0) + 1
        if p.get("is_open_access"):
            open_access_count += 1
    
    method_dist: dict[str, int] = {}
    for group in groups:
        method_dist[group["label"]] = group["count"]
    
    total_returned = sum(len(g.get("papers", [])) for g in groups)
    
    result = {
        "total_fetched": total_fetched,
        "total_unique": total_unique,
        "total_returned": total_returned,
        "groups": groups,
        "method_distribution": method_dist,
        "grouping_notes": grouping_result.get("grouping_notes", ""),
        "statistics": {
            "by_source": by_source,
            "by_year": dict(sorted(by_year.items(), reverse=True)),
            "by_type": by_type,
            "by_language": by_language,
            "open_access_count": open_access_count,
            "groups_with_min_papers": grouping_result.get("groups_with_min_papers", 0),
            "groups_below_min_papers": grouping_result.get("groups_below_min_papers", 0),
        },
    }
    
    elapsed_total = time.time() - start_time
    log.info(
        "SLR complete: %d fetched → %d unique → %d returned in %.1f sec",
        total_fetched, total_unique, total_returned, elapsed_total,
    )
    
    return result


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.DEBUG)
    
    result = run_slr(
        keyword="deep learning medical image analysis",
        top_n=10,
        max_workers=6,
    )
    
    print("\n" + "="*80)
    print("SLR RESULT")
    print("="*80)
    print(json.dumps({
        "total_fetched": result["total_fetched"],
        "total_unique": result["total_unique"],
        "total_returned": result["total_returned"],
        "groups_count": len(result["groups"]),
        "statistics": result["statistics"],
    }, indent=2))
