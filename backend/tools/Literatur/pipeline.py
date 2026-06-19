"""Tool Literatur — pipeline: DB-first → API fallback → ML scoring → AI rerank.

Flow:
1. DB-FILTER: PostgreSQL FTS + hybrid score (title + abstract)
2. API-FALLBACK: if DB < MIN_FETCH_TARGET (1000), call orchestrator.fetch_titles()
   → parallel multi-source API fetch with DB dedup
3. ML-SCORING: SBERT cosine (50%) + citations (10%) + TF-IDF (10%) + recency (8%)
   + venue (10%) + keyword (7%) + author (5%) — programmatic, no LLM
4. TAMPIL FASE 1: save scored results → frontend
5. AI-RANK: AI re-rank untuk urutan relevansi final
6. TAMPIL FASE 2: update ranking hasil AI

Minimum 1000 papers per topic. Semua paper disimpan ke paper_database.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Callable

from .paper import Paper
from . import db_cache
from .text_cleaner import detect_mojibake

log = logging.getLogger(__name__)

# Minimum target per topic — auto trigger API fetch if DB insufficient
MIN_FETCH_TARGET = 1000


def _paper_record(idx: int, p: Paper, rank: int | None = None, score_total: float | None = None) -> dict:
    """Build paper record dict for frontend/save."""
    return {
        "id": idx,
        "rank": rank,  # AI rank position (1 = paling relevan)
        "title": p.title,
        "authors": p.authors,
        "doi": p.doi,
        "url": p.url,
        "pdf_url": p.pdf_url,
        "source": p.source,
        "year": p.year,
        "venue": p.venue,
        "publisher": p.publisher,
        "citations": p.citations,
        "abstract": p.abstract,
        "db_score": round(p.db_score, 4) if p.db_score else None,
        "score_total": round(score_total, 4) if score_total else None,
        "is_open_access": p.is_open_access,
        "publisher_info": {
            "publisher": p.publisher,
            "venue": p.venue,
            "venue_type": p.venue_type,
            "type": p.type,
            "year": p.year,
            "is_open_access": p.is_open_access,
        },
    }


def _stats(query: str, papers: list[Paper]) -> dict:
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
    }


def _ai_rerank(query: str, papers: list[Paper], ai_model: str | None) -> list[int] | None:
    """Send papers to AI for relevance re-ranking. Returns reordered indices or None.
    
    Issues fixed June 2026:
    - Hanya top 50 paper dikirim (sebelumnya SEMUA paper → overflow context)
    - Filter paper dengan teks garbled (mojibake) sebelum dikirim ke AI
    - Prompt diperkuat: AI diinstruksikan menolak paper mojibake
    """
    if not papers:
        return None

    # ── Filter: hanya top 50 + bersih dari mojibake ──
    # Paper di pipeline sudah terurut berdasarkan ML score (sebelum AI rerank)
    # Ambil top 50 yang teksnya bersih. Ini mencegah:
    # 1. Context window overflow (1000+ paper)
    # 2. AI memberikan perhatian ke paper sampah
    # 3. Hallucination karena model kewalahan
    clean_papers = []
    for p in papers:
        t_mojo = detect_mojibake(p.title)
        a_mojo = detect_mojibake(p.abstract)
        if t_mojo > 0.5 or a_mojo > 0.5:
            continue  # Skip paper dengan teks garbled
        clean_papers.append(p)
        if len(clean_papers) >= 50:
            break

    if not clean_papers:
        log.warning("tool_literatur.ai_rerank: no clean papers after mojibake filter")
        return None

    # Map original indices for return
    original_indices = {id(p): i for i, p in enumerate(papers)}
    clean_list = clean_papers  # Items already sorted by score

    # Build input: only title + abstract (citations is NOT relevance)
    items = []
    for p in clean_papers:
        # Truncate abstract to 500 chars to save tokens
        abstr = (p.abstract or "")[:500]
        items.append({
            "id": id(p),  # Use Python id as unique identifier
            "title": p.title or "",
            "abstract": abstr,
            "citations": p.citations or 0,
        })

    system_prompt = f"""Anda adalah asisten riset akademik. Tugas Anda: urutkan ulang paper berdasarkan RELEVANSI LANGSUNG dengan topik penelitian spesifik user.

TOPIK: {query}

ATURAN KRITIS:
1. Paper yang PALING RELEVAN adalah yang secara LANGSUNG membahas topik "{query}" — judul atau abstract menyebut topik utama.
2. Paper yang judulnya mengandung "{query}" secara eksplisit → HARUS di atas.
3. Paper yang hanya menyebut kata kunci sekilas (contoh: di daftar referensi, di list aplikasi) → tempatkan di bawah.
4. Paper dengan judul atau abstract yang tidak jelas, rusak (garbled), atau tidak bisa dibaca → tempatkan di PALING BAWAH.
5. Jumlah sitasi BUKAN indikator relevansi — jangan biarkan paper populer yang tidak relevan menang.

Daftar paper (format: id|judul|abstract|sitasi). Urutkan dari yang PALING RELEVAN (1) ke yang KURANG RELEVAN.

Output HARUS berupa JSON array berisi ID saja, berurutan dari paling relevan:
[<id1>, <id2>, <id3>, ...]

HANYA output JSON array, tidak ada teks lain — tidak ada markdown, tidak ada backticks, tidak ada penjelasan."""

    user_text = "\n".join(
        f"{it['id']}|{it['title']}|{it['abstract']}|sitasi:{it['citations']}"
        for it in items
    )

    try:
        from utils.ai_tools.model_router import route_chat_call
        resp, model_used = route_chat_call(
            model=ai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0.3,
            max_tokens=65536,  # 64K output token
            timeout=120,
        )
        # route_chat_call returns (requests.Response, model_name) tuple
        data = resp.json() if hasattr(resp, 'json') else resp
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        match = re.search(r'\[[\d,\s]+\]', content)
        if match:
            raw_ids = json.loads(match.group())
            # Map Python object IDs back to sequential indices
            valid = []
            for obj_id in raw_ids:
                if isinstance(obj_id, int):
                    orig_idx = original_indices.get(obj_id)
                    if orig_idx is not None:
                        valid.append(orig_idx)
            if len(valid) >= 10:
                log.info(
                    "tool_literatur.ai_rerank: reordered %d papers (got %d valid indices)",
                    len(papers), len(valid),
                )
                return valid
    except Exception as e:
        log.warning("tool_literatur.ai_rerank failed: %s", e)

    return None


def _apply_rerank(papers: list[Paper], reordered_indices: list[int]) -> list[Paper]:
    """Apply AI re-ranking: put AI-ranked papers first, then remaining."""
    papers_map = {i: p for i, p in enumerate(papers)}
    result = []
    seen = set()
    for idx in reordered_indices:
        if idx in papers_map and idx not in seen:
            result.append(papers_map[idx])
            seen.add(idx)
    for i, p in enumerate(papers):
        if i not in seen:
            result.append(p)
    return result


def run(
    query: str,
    top_k: int = 50,
    year_from: int | None = None,
    sources: list[str] | None = None,
    ai_model: str | None = None,
    progress_cb: Callable[[str, dict], None] | None = None,
    save_cb: Callable[[list[dict]], None] | None = None,
    pinned_dois: list[str] | None = None,
    enable_snowball: bool = True,
) -> dict:
    """Jalankan tool literatur: DB filter → tampil → AI rank → tampil.

    progress_cb dipanggil di tiap milestone:
    - "db_searching" / "db_scored" — dari DB
    - "snowballing" / "snowballed" — citation chaining
    - "displaying_initial" / "displayed_initial" — tampil hasil PG
    - "ai_reranking" / "ai_reranked" — AI rerank
    - "displaying_final" / "complete" — tampil final

    save_cb dipanggil 2x:
    - Setelah DB scoring (hasil awal, phase 1)
    - Setelah AI rerank (hasil final, phase 2)

    pinned_dois: list DOI paper yang di-pin user → active learning signal
    enable_snowball: aktifkan citation snowballing (default True)
    """
    # ── 1. DB FILTER: PostgreSQL scoring ──────────────────────────────
    if progress_cb:
        progress_cb("db_searching", {"query": query, "top_k": top_k})

    fetch_limit = top_k * 10  # Oversample untuk AI rerank headroom
    if year_from:
        fetch_limit = fetch_limit * 2  # Extra headroom untuk year filter

    papers = db_cache.search_papers(
        query=query,
        limit=fetch_limit,
        year_from=year_from,
        sources=sources,
    )
    log.info("tool_literatur.db_search: got %d papers from paper_database", len(papers))

    # Year post-filter (search_papers sudah filter di SQL, safety net)
    if year_from:
        papers = [p for p in papers if p.year and p.year >= year_from]

    # ── 1b. API FALLBACK: fetch if DB insufficient ───────────────────────
    if len(papers) < MIN_FETCH_TARGET:
        log.info("tool_literatur.api_fallback: DB has %d papers < %d target, fetching from APIs",
                 len(papers), MIN_FETCH_TARGET)
        if progress_cb:
            progress_cb("api_fetching", {
                "db_count": len(papers), "target": MIN_FETCH_TARGET,
                "sources": sources or [],
            })

        try:
            from .orchestrator import fetch_titles
            api_papers = fetch_titles(
                query=query,
                sources=sources,
                max_total=MIN_FETCH_TARGET,
                use_cache=True,  # DB-first internally
                progress_cb=lambda stage, info: (
                    progress_cb(f"fetch_{stage}", info) if progress_cb else None
                ),
            )
            if api_papers:
                # Merge: prefer API results (freshly dedupped), append unique DB papers
                existing_titles = {p.title.lower() for p in api_papers}
                for p in papers:
                    if (p.title or "").lower() not in existing_titles:
                        api_papers.append(p)
                papers = api_papers
                log.info("tool_literatur.api_fallback: fetched %d papers total", len(papers))
        except Exception as e:
            log.warning("tool_literatur.api_fallback failed: %s", e)
            # Continue with whatever DB returned

        if progress_cb:
            progress_cb("api_fetched", {"count": len(papers)})

    # ── 1c. ML SCORING + ACTIVE LEARNING + SNOWBALLING ──────────────
    ml_scored = {}
    prisma_stats = {
        "identified": len(papers),
        "screened": 0,
        "eligible": 0,
        "included": 0,
        "duplicates_removed": 0,
        "snowball_added": 0,
    }

    try:
        from .scoring import score_papers_with_feedback

        # Build pinned_papers list dari pinned_dois
        pinned_papers = []
        if pinned_dois:
            pinned_papers = [p for p in papers if p.doi and p.doi.lower() in {d.lower() for d in pinned_dois}]
            if pinned_papers:
                log.info("active_learning: %d pinned papers dari %d DOIs",
                         len(pinned_papers), len(pinned_dois))

        scored_results = score_papers_with_feedback(
            query, papers, pinned_papers=pinned_papers if pinned_papers else None,
        )
        for sp in scored_results:
            ml_scored[sp.paper.title.lower()] = sp
        log.info("tool_literatur.ml_scoring: scored %d papers", len(scored_results))

        # ── 1d. CITATION SNOWBALLING ──────────────────────────────
        # Ambil top-10 seed papers dari hasil scoring
        if enable_snowball and len(scored_results) >= 10:
            if progress_cb:
                progress_cb("snowballing", {"seed_count": 10})
            try:
                from .snowball import snowball
                top_seeds = [sp.paper for sp in scored_results[:10]]
                snowball_papers = snowball(
                    top_seeds, query,
                    top_n_seeds=10, max_per_seed=10, max_total=100,
                )
                if snowball_papers:
                    # Score snowball papers
                    snowball_scored = score_papers_with_feedback(
                        query, snowball_papers, pinned_papers=pinned_papers if pinned_papers else None,
                    )
                    # Merge: snowball papers sebagai supplementary
                    snowball_titles = {}
                    for sp in snowball_scored:
                        key = sp.paper.title.lower()
                        old = ml_scored.get(key)
                        # Jika paper sudah ada, merge citation info; jangan ganti kalau score lama lebih tinggi
                        if old and sp.score_total <= old.score_total:
                            continue
                        snowball_titles[key] = sp
                        ml_scored[key] = sp
                    prisma_stats["snowball_added"] = len(snowball_titles)
                    log.info("snowballing: merged %d new papers", len(snowball_titles))
                    if progress_cb:
                        progress_cb("snowballed", {
                            "found": len(snowball_papers),
                            "merged": len(snowball_titles),
                        })
            except Exception as e:
                log.warning("snowballing failed: %s", e)

    except Exception as e:
        log.warning("tool_literatur.ml_scoring failed: %s", e)
        # Fall through — papers still usable without ML scores

    # Sort by score_total descending if available, else db_score
    if ml_scored:
        def _get_score(p: Paper) -> float:
            sp = ml_scored.get((p.title or "").lower())
            return sp.score_total if sp else 0.0
        papers.sort(key=_get_score, reverse=True)
    else:
        papers.sort(key=lambda p: p.db_score or 0, reverse=True)

    # ── KEYWORD BOOST (ringan): hanya sebagai safety net ──
    # scoring.py 17% weight + long-term boost sudah mencakup keyword match.
    # Boost di pipeline hanya additive kecil untuk preventif.
    query_lower = query.lower()
    query_terms = re.findall(r'[a-z0-9]{3,}', query_lower)
    if query_terms and ml_scored:
        def _keyword_boost(p: Paper) -> float:
            """Small additive boost (max 0.3) — tidak overwrite ML score."""
            title = (p.title or '').lower()
            if query_lower in title:
                return 0.3
            # All query terms in title → small boost
            if all(term in title for term in query_terms):
                return 0.2
            # Partial match in title
            title_matches = sum(1 for term in query_terms if term in title)
            if title_matches / len(query_terms) >= 0.5:
                return 0.1
            return 0.0

        # Final sort: ml_score + keyword boost (additive, not replacing)
        def _final_key(p: Paper) -> float:
            sp = ml_scored.get((p.title or '').lower())
            ml = sp.score_total if sp else 0.0
            return ml + _keyword_boost(p)
        papers.sort(key=_final_key, reverse=True)
        log.info("tool_literatur.keyword_boost: applied additive boost on ML scores")
    elif query_terms:
        # No ML scores — use db_score + keyword boost (legacy fallback)
        def _keyword_score(p: Paper) -> float:
            title = (p.title or '').lower()
            abstract = (p.abstract or '').lower()
            if query_lower in title:
                return 3.0
            if all(term in title for term in query_terms):
                return 2.0
            title_matches = sum(1 for term in query_terms if term in title)
            if title_matches > 0:
                return 1.0 * title_matches / len(query_terms)
            if all(term in abstract for term in query_terms):
                return 0.5
            return 0.0

        papers.sort(key=lambda p: (p.db_score or 0) + _keyword_score(p) * 2.0, reverse=True)

    if progress_cb:
        progress_cb("db_scored", {"count": len(papers)})

    # ── 2. TAMPIL FASE 1: hasil DB scoring ─────────────────────────────
    if progress_cb:
        progress_cb("displaying_initial", {"count": len(papers)})

    # Simpan hasil scoring ke frontend
    if save_cb:
        records_phase1 = [
            _paper_record(i, p,
                          score_total=(
                              ml_scored.get((p.title or "").lower()).score_total
                              if ml_scored.get((p.title or "").lower()) else None
                          ))
            for i, p in enumerate(papers)
        ]
        try:
            save_cb(records_phase1)
            log.info("tool_literatur.phase1_save: saved %d scored papers", len(records_phase1))
        except Exception as e:
            log.warning("tool_literatur.phase1_save failed: %s", e)

    if progress_cb:
        progress_cb("displayed_initial", {"count": len(papers)})

    # ── 3. AI RERANK ───────────────────────────────────────────────────
    if progress_cb:
        progress_cb("ai_reranking", {"count": len(papers)})

    reordered = _ai_rerank(query, papers, ai_model)

    if reordered:
        papers = _apply_rerank(papers, reordered)
        log.info("tool_literatur.ai_rerank: applied new ordering")
        if progress_cb:
            progress_cb("ai_reranked", {"count": len(papers)})
    else:
        log.info("tool_literatur.ai_rerank: skipped (no valid reorder)")
        if progress_cb:
            progress_cb("ai_reranked", {"count": len(papers), "skipped": True})

    # ── 4. TAMPIL FASE 2: hasil AI ranking ─────────────────────────────
    if progress_cb:
        progress_cb("displaying_final", {"count": min(len(papers), top_k)})

    # Build final records dengan AI rank position
    all_records = []
    ai_rank_map = {}
    if reordered:
        # Build rank lookup: paper title → AI rank position
        for rank_pos, p in enumerate(papers, 1):
            key = (p.title or "").lower()
            ai_rank_map[key] = rank_pos

    for i, p in enumerate(papers):
        rank = ai_rank_map.get((p.title or "").lower())
        sp = ml_scored.get((p.title or "").lower())
        st = sp.score_total if sp else None
        all_records.append(_paper_record(i, p, rank=rank, score_total=st))

    top_k_records = all_records[:top_k]

    # Simpan hasil AI ranking
    if save_cb:
        try:
            save_cb(all_records)
            log.info("tool_literatur.phase2_save: saved %d AI-ranked papers", len(all_records))
        except Exception as e:
            log.warning("tool_literatur.phase2_save failed: %s", e)

    if progress_cb:
        progress_cb("complete", {
            "total": len(all_records),
            "top_k": len(top_k_records),
            "ai_reranked": bool(reordered),
        })

    stats = _stats(query, papers)
    stats["ai_reranked"] = bool(reordered)
    stats["prisma"] = {
        "identified": len(papers),
        "screened": len(papers),  # All papers screened by ML
        "eligible": sum(1 for sp in ml_scored.values() if sp.is_relevant),
        "included": min(len(top_k_records), top_k),
        "duplicates_removed": 0,  # DB dedup already handled upstream
        "snowball_added": prisma_stats.get("snowball_added", 0),
    }

    return {
        "query": query,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": stats,
        "papers": all_records,
        "top_k": top_k_records,
    }


def save(payload: dict, out_path: str) -> None:
    from pathlib import Path
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))