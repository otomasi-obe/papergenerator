"""End-to-end SLR pipeline.

Algoritma sesuai spec:

1. SEARCH dulu semua API (max 10 worker, judul + metadata yg gratis disertakan
   sumber). Lihat orchestrator.fetch_titles.
2. RANK dengan kombinasi sinyal SBERT + TF-IDF + citation + recency + venue
   quality (scoring.score_papers). Hasil disort descending.
3. SUMMARIZE top-K (default 50) dengan AI MODELGENERATE (summarizer.summarize_with_ai),
   sisanya pakai extractive supaya tetap dapat preview cepat.
4. Output JSON siap dipakai frontend.

Pipeline ini dipanggil dari `slr_jobs.run_slr_job` (worker queue) sehingga
panggilan AI yang lama tidak memblokir API request.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .orchestrator import fetch_titles, pick_sources_for_topic
from .paper import Paper
from .scoring import ScoredPaper, score_papers
from .summarizer import summarize as extractive_summarize
from .summarizer import summarize_with_ai
from .unpaywall import enrich_papers_without_pdf
from . import db_cache

log = logging.getLogger(__name__)


def _publisher_info(p: Paper) -> dict:
    return {
        "publisher": p.publisher,
        "venue": p.venue,
        "venue_type": p.venue_type,
        "type": p.type,
        "year": p.year,
        "is_open_access": p.is_open_access,
    }


def _paper_record(idx: int, sp: ScoredPaper, summary: str | None = None, gap_riset: str | None = None) -> dict:
    p = sp.paper
    return {
        "id": idx,
        "title": p.title,
        "authors": p.authors,
        "publisher_info": _publisher_info(p),
        "doi": p.doi,
        "url": p.url,
        "pdf_url": p.pdf_url,
        "source": p.source,
        "year": p.year,
        "venue": p.venue,
        "publisher": p.publisher,
        "citations": p.citations,
        "abstract": p.abstract,
        "summary": summary or "",
        "gap_riset": gap_riset or "",
        "score_total": sp.score_total,
        "score_breakdown": sp.score_breakdown or {},
        "is_relevant": sp.is_relevant,
        "must_read": sp.must_read,
    }


def _stats(query: str, papers: list[Paper], scored: list[ScoredPaper]) -> dict:
    by_source: dict[str, int] = {}
    by_year: dict[int, int] = {}
    n_with_abs = 0
    n_with_doi = 0
    for p in papers:
        by_source[p.source] = by_source.get(p.source, 0) + 1
        if p.year:
            by_year[p.year] = by_year.get(p.year, 0) + 1
        if p.abstract:
            n_with_abs += 1
        if p.doi:
            n_with_doi += 1
    return {
        "query": query,
        "total_unique_papers": len(papers),
        "with_abstract": n_with_abs,
        "with_doi": n_with_doi,
        "papers_by_source": by_source,
        "papers_by_year": dict(sorted(by_year.items(), reverse=True)),
        "scored": len(scored),
        "must_read_count": sum(1 for s in scored if s.must_read),
        "is_relevant_count": sum(1 for s in scored if s.is_relevant),
    }


def run(
    query: str,
    sources: list[str] | None = None,
    per_source: int = 60,
    max_total: int | None = None,
    top_k: int = 50,
    year_from: int | None = None,
    skip_predatory: bool = True,
    ai_summarize: bool = False,
    ai_model: str | None = None,
    progress_cb: Callable[[str, dict], None] | None = None,
    save_cb: Callable[[list[dict]], None] | None = None,
    source_save_cb: Callable[[list[Paper]], None] | None = None,
) -> dict:
    """Eksekusi penuh pipeline. progress_cb dipanggil di tiap milestone:
    - "fetching" / "source_done" / "dedup_done" — dari orchestrator
    - "scoring" / "scored" — dari sini
    - "summarizing" / "summarized" / "complete" — dari sini

    save_cb dipanggil dengan list paper records setelah fetch selesai (streaming save).
    source_save_cb dipanggil per-source setelah fetch selesai (true streaming).
    Returns dict siap di-dump JSON.
    """
    sources = sources or pick_sources_for_topic(query)

    # Build filters dict to pass year_from to fetchers that support it
    filters = {}
    if year_from:
        filters["year_from"] = year_from

    # 1. FETCH — DB FIRST from paper_database (PostgreSQL full-text search)
    # target = top_k × 5 for scoring headroom
    target = top_k * 5

    # When year_from is set, fetch 2x then filter so we don't end up below target.
    # (some fetchers don't support year filtering at API level)
    fetch_target = target
    if year_from:
        fetch_target = target * 2

    # DB-FIRST: query paper_database using PostgreSQL full-text search + sorting
    log.info("slr.db_search: query=%s sources=%s limit=%d year_from=%s", query, sources, fetch_target, year_from)
    raw_papers = db_cache.search_papers(
        query=query,
        limit=fetch_target,
        year_from=year_from,
        sources=sources,
    )
    log.info("slr.db_search: got %d papers from paper_database", len(raw_papers))

    # Fallback to API if DB returns too few results
    if len(raw_papers) < top_k:
        log.info("slr.api_fallback: DB returned %d, need at least %d, fetching from APIs", len(raw_papers), top_k)
        api_papers = fetch_titles(
            query=query,
            sources=sources,
            limit_per_source=per_source,
            filters=filters if filters else None,
            max_total=fetch_target,
            skip_predatory=skip_predatory,
            progress_cb=progress_cb,
            source_save_cb=source_save_cb,
        )
        # Merge and deduplicate
        seen_dois = {p.doi for p in raw_papers if p.doi}
        seen_titles = {db_cache.normalize_title(p.title) for p in raw_papers}
        for ap in api_papers:
            doi_norm = ap.doi.lower() if ap.doi else None
            title_norm = db_cache.normalize_title(ap.title)
            if (doi_norm and doi_norm in seen_dois) or (title_norm and title_norm in seen_titles):
                continue
            raw_papers.append(ap)
            if doi_norm:
                seen_dois.add(doi_norm)
            if title_norm:
                seen_titles.add(title_norm)
        log.info("slr.merged: %d total papers after API fallback + dedup", len(raw_papers))
    elif progress_cb:
        progress_cb("fetching", {"count": len(raw_papers)})

    # Post-filter for fetchers that don't support year filtering at API level
    if year_from:
        raw_papers = [p for p in raw_papers if p.year and p.year >= year_from]
        if max_total:
            raw_papers = raw_papers[:max_total]

    if not raw_papers:
        if progress_cb:
            progress_cb("complete", {"top_k": 0, "total": 0})
        return {
            "query": query,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stats": {
                "query": query,
                "total_unique_papers": 0,
                "papers_by_source": {},
                "papers_by_year": {},
                "scored": 0,
                "must_read_count": 0,
                "is_relevant_count": 0,
                "with_abstract": 0,
                "with_doi": 0,
            },
            "papers": [],
            "top_k": [],
        }

    # 2. RANK (programmatic — no AI)
    if progress_cb:
        progress_cb("scoring", {"count": len(raw_papers)})
    scored = score_papers(query, raw_papers)
    if progress_cb:
        progress_cb("scored", {"count": len(scored)})

    # Stable indices by id() for joining back later.
    score_lookup = {id(s.paper): s for s in scored}

    # 2.5 Enrich with Unpaywall PDF URLs for papers missing pdf_url
    try:
        top_records = []
        for sp in scored[:top_k]:
            p = sp.paper
            top_records.append({
                "doi": p.doi,
                "pdf_url": p.pdf_url,
            })
        n_enriched = enrich_papers_without_pdf(top_records)
        if n_enriched:
            log.info("slr.unpaywall: enriched %d/%d papers with pdf_url", n_enriched, len(top_records))
        for i, sp in enumerate(scored[:top_k]):
            if i < len(top_records) and top_records[i].get("pdf_url"):
                sp.paper.pdf_url = top_records[i]["pdf_url"]
    except Exception as e:
        log.warning("slr.unpaywall enrichment failed: %s", e)

    # 2.6 Streaming save: save ALL papers to DB immediately after fetch+rank
    # This allows frontend to show papers as they come in (streaming).
    if save_cb:
        all_records_for_save = []
        for global_idx, p in enumerate(raw_papers):
            sp = score_lookup.get(id(p))
            if sp is None:
                continue
            all_records_for_save.append(_paper_record(global_idx, sp, summary="", gap_riset=""))
        try:
            save_cb(all_records_for_save)
        except Exception as e:
            log.warning("slr.save_cb failed: %s", e)

    # 3. AI SUMMARIZE top-K (rest gets extractive)
    top_scored = scored[:top_k]
    summaries: dict[int, dict] = {}
    ai_used = False
    top_input = []
    for i, sp in enumerate(top_scored):
        top_input.append(
            {
                "id": i,
                "title": sp.paper.title,
                "year": sp.paper.year,
                "abstract": sp.paper.abstract or "",
            }
        )

    if ai_summarize and top_input:
        if progress_cb:
            progress_cb("summarizing", {"count": len(top_input)})
        try:
            summaries, ai_used = summarize_with_ai(
                top_input,
                query=query,
                model=ai_model,
                progress_cb=progress_cb,
            )
        except BaseException as e:
            # Preserve any partial summaries the summarizer attached before
            # the cancel/error so we still return useful data on cancellation.
            partial = getattr(e, "partial_summaries", None)
            if isinstance(partial, dict):
                summaries = partial
            partial_ai_used = getattr(e, "partial_ai_used", None)
            if isinstance(partial_ai_used, bool):
                ai_used = partial_ai_used
            if isinstance(e, Exception) and not isinstance(e, KeyboardInterrupt):
                # Re-raise progress-callback-driven cancels (e.g. WorkerCancelled
                # in slr_worker) so the worker can mark the job cancelled.
                # Generic AI errors are swallowed and we continue with extractive.
                exc_name = e.__class__.__name__
                if (
                    exc_name in ("WorkerCancelled", "CancelledByCaller")
                    or "cancel" in exc_name.lower()
                ):
                    raise
                log.warning("AI summarize failed: %s", e)
                if not isinstance(partial, dict):
                    summaries = {}
            else:
                raise

    # 4. Assemble records (with summaries if any)
    top_pos = {id(s.paper): i for i, s in enumerate(top_scored)}
    global_pos = {id(p): i for i, p in enumerate(raw_papers)}

    def _get_summary_gap(top_idx: int, paper) -> tuple[str, str]:
        """Return (summary, gap_riset) for a paper."""
        if top_idx >= 0 and top_idx in summaries:
            entry = summaries[top_idx]
            if isinstance(entry, dict):
                return entry.get("summary", ""), entry.get("gap_riset", "")
            else:
                # Legacy format (string) from partial_summaries
                return entry, ""
        return "", ""  # No extractive fallback — user wants clean data

    all_records: list[dict] = []
    for global_idx, p in enumerate(raw_papers):
        sp = score_lookup.get(id(p))
        if sp is None:
            continue
        top_idx = top_pos.get(id(sp.paper), -1)
        summary, gap_riset = _get_summary_gap(top_idx, p)
        all_records.append(_paper_record(global_idx, sp, summary=summary, gap_riset=gap_riset))

    top_records = []
    for top_idx, sp in enumerate(top_scored):
        global_idx = global_pos.get(id(sp.paper))
        if global_idx is None:
            continue
        summary, gap_riset = _get_summary_gap(top_idx, sp.paper)
        top_records.append(_paper_record(global_idx, sp, summary=summary, gap_riset=gap_riset))

    if progress_cb:
        progress_cb("complete", {"top_k": len(top_records), "total": len(all_records)})

    stats = _stats(query, raw_papers, scored)
    stats["ai_summary_used"] = bool(ai_used)

    return {
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": stats,
        "papers": all_records,
        "top_k": top_records,
    }


def save(payload: dict, out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def run_and_save(query: str, out_path: str | Path = "results/slr.json", **kwargs) -> Path:
    payload = run(query, **kwargs)
    return save(payload, out_path)
