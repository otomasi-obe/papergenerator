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

from tools.Literatur.paper import Paper
from . import db_cache
from .text_cleaner import detect_mojibake, clean_abstract, clean_title

log = logging.getLogger(__name__)

# Minimum target per topic — auto trigger API fetch if DB insufficient
MIN_FETCH_TARGET = 1000


def _paper_record(idx: int, p: Paper, original_rank: int | None = None, new_rank: int | None = None, review: str = "", relevance_score: float | None = None) -> dict:
    """Build paper record dict for frontend/save."""
    return {
        "id": idx,
        "original_rank": original_rank or idx + 1,  # 1-based index in pre-AI list
        "new_rank": new_rank or idx + 1,             # 1-based index in post-AI list
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
        "review": review or (getattr(p, "review", None) or ""),
        "relevance_score": round(relevance_score, 4) if relevance_score else round(getattr(p, "relevance_score", 0) or 0, 4),
        "db_score": round(p.db_score, 4) if p.db_score else None,
        "score_total": round(relevance_score, 4) if relevance_score else round(getattr(p, "relevance_score", 0) or 0, 4),
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
    
    PERBAIKAN: candidate pool sekarang = top 50 ML score
    + semua paper dengan full query phrase di title (keyword match).
    Ini mencegah AI hanya melihat paper ML-favored yang mungkin
    tidak relevan secara keyword.
    """
    if not papers:
        return None

    # ── Build candidate pool: top 50 ML + keyword-matched papers ──
    # Dua sumber kandidat:
    # 1. Top 50 paper dari ML ranking (sudah di-sort oleh caller)
    # 2. Semua paper yang judulnya mengandung query phrase utuh
    #    (keyword match = sinyal relevance terkuat)
    query_lower = query.lower().strip().replace('-', ' ')
    keyword_pool = []
    ml_pool = []
    seen_ids = set()

    for p in papers:
        t_mojo = detect_mojibake(p.title)
        a_mojo = detect_mojibake(p.abstract)
        if t_mojo > 0.5 or a_mojo > 0.5:
            continue  # Skip paper dengan teks garbled
        pid = id(p)
        if pid in seen_ids:
            continue

        # Keyword match: check using scoring.py's _keyword_density_score
        # (handles partial matches, term overlap, not just exact substring)
        from .scoring import _keyword_density_score
        kw_score = _keyword_density_score(query, p)
        is_keyword_match = kw_score >= 0.5  # ≥50% keyword density = relevant

        if is_keyword_match and len(keyword_pool) < 30:
            keyword_pool.append(p)
            seen_ids.add(pid)

        if len(ml_pool) < 50:
            ml_pool.append(p)
            seen_ids.add(pid)

    # Merge: keyword-matched first, then ML top-50 (dedup via seen_ids already)
    clean_papers = keyword_pool + [p for p in ml_pool if id(p) not in {id(k) for k in keyword_pool}]

    # Cap at 80 papers (50 ML + up to 30 keyword = max 80)
    if len(clean_papers) > 80:
        clean_papers = clean_papers[:80]

    if not clean_papers:
        log.warning("tool_literatur.ai_rerank: no clean papers after mojibake filter")
        return None

    log.info(
        "tool_literatur.ai_rerank: candidate pool %d papers (%d keyword-matched, %d ML)",
        len(clean_papers), len(keyword_pool),
        len([p for p in ml_pool if id(p) not in {id(k) for k in keyword_pool}]),
    )

    # Map original indices for return
    original_indices = {id(p): i for i, p in enumerate(papers)}
    clean_list = clean_papers  # keyword-first, then ML

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
            json={
                "model": ai_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                "temperature": 0.3,
                "max_tokens": 65536,  # 64K output token
            },
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


# ── Generic academic/method words to exclude from OR search ───────────
# These are words that appear in thousands of computer-science papers
# regardless of actual domain. Filtering them from OR queries prevents
# irrelevant papers from drowning the results.
_GENERIC_ACADEMIC_WORDS = {
    # Standard stopwords
    "a", "an", "the", "in", "on", "of", "to", "by", "is", "be", "at",
    "or", "as", "if", "no", "so", "we", "he", "she", "it", "they",
    "and", "for", "with", "from", "that", "this", "are", "was", "but",
    "not", "can", "all", "any", "has", "its", "may", "who", "which",
    "their", "how", "what", "why", "use", "also", "been", "were",
    "will", "have", "had", "do", "does", "did", "into", "than",
    "just", "more", "most", "new", "other", "some", "such", "only",
    "over", "when", "where", "each", "about", "after", "before",
    "between", "during", "these", "those",
    # Generic academic/method words — high-frequency across all CS domains
    "based", "using", "through", "approach", "method", "methods",
    "model", "models", "system", "systems", "data", "review",
    "analysis", "study", "studies", "research", "paper",
    "technique", "techniques", "algorithm", "algorithms",
    "framework", "frameworks", "application", "applications",
    "development", "validation", "evaluation", "implementation",
    "design", "performance", "comparative", "comparison",
    "effect", "impact", "role", "case", "survey",
    "overview", "challenge", "challenges", "issue", "issues",
    "trend", "trends", "advance", "advances", "recent",
    "review", "comprehensive", "state", "art",
    # Generic ML/CV method words — filter for multi-domain specificity
    "deep", "learning", "machine", "neural", "network", "networks",
    "computer", "vision", "image", "images", "video",
    "detection", "recognition", "classification", "prediction",
    "predicting", "enhanced", "improved", "novel", "automatic",
    "automated", "efficient", "robust", "hybrid", "optimization",
    "object", "feature", "features", "extraction", "segmentation",
    "architecture", "architectures", "transfer", "training",
    "dataset", "datasets", "benchmark", "benchmarks",
    "accuracy", "precision", "scalable", "adaptive",
    "embedded", "embedding", "embeddings",
    # Words with hyphens that become meaningless after splitting
    "state-of-the-art", "end-to-end", "real-time", "plug-and-play",
    "attention-based", "attention-enhanced",
}
_WORDS_MIN_LEN = 3  # Ignore words shorter than this in OR queries


def _extract_core_query(raw_query: str) -> str:
    """Extract core topic keywords from a potentially verbose title/query.

    For academic paper titles like:
    "Computer Vision-Based Prediction of Glycemic Index and Glycemic Load
    for Indonesian Foods: Development and Validation of a Deep Learning
    Model with Embedded Nutritional Biochemistry Framework"

    We want to extract the core DOMAIN keywords:
    - "glycemic index", "glycemic load", "indonesian foods",
    - "nutritional biochemistry"
    
    While filtering out METHOD descriptors:
    - "computer vision", "deep learning", "model", "prediction",
    - "development", "validation", "framework"

    Returns a cleaned query string suitable for DB full-text search.
    """
    cleaned = raw_query.lower().strip().replace('-', ' ').replace(':', ' ')
    words = cleaned.split()
    
    if len(words) <= 5:
        # Short query — return as-is (likely a simple topic)
        return raw_query.strip()
    
    # Split at colon to separate main title from subtitle (if any)
    raw_lower = raw_query.lower().strip()
    if ':' in raw_lower:
        parts = raw_lower.split(':', 1)
        main_title = parts[0].strip()
        subtitle = parts[1].strip() if len(parts) > 1 else ''
    else:
        main_title = raw_lower
        subtitle = ''
    
    # Extract content words from each part
    main_words = main_title.replace('-', ' ').split()
    sub_words = subtitle.replace('-', ' ').split() if subtitle else []
    
    # Filter: keep words that are domain-specific, skip generic/method words
    content_main = [w for w in main_words 
                    if w.lower() not in _GENERIC_ACADEMIC_WORDS and len(w) >= _WORDS_MIN_LEN]
    content_sub = [w for w in sub_words 
                    if w.lower() not in _GENERIC_ACADEMIC_WORDS and len(w) >= _WORDS_MIN_LEN]
    
    # Build 2-3 word phrases from content words (for phrase matching)
    all_content = content_main + content_sub
    all_content_dedup = list(dict.fromkeys(all_content))  # dedup, preserve order
    
    # Build the cleaned query: extract the most discriminative content words.
    # Strategy: For long queries, use only 2-3 most specific keywords for the
    # AND phase (DB FTS). More words → AND requires ALL tokens → 0 results for
    # niche topics. Short focused query + OR fallback = better coverage.
    #
    # Priority: main title content words (usually the core topic),
    # then subtitle content (domain/context), then all deduped content.
    
    if content_main:
        core = ' '.join(content_main[:3])
    elif content_sub:
        core = ' '.join(content_sub[:3])
    else:
        core = raw_query.strip()
    
    # If core is empty or too short, fallback to full content
    if not core or len(core.split()) < 2:
        core = ' '.join(all_content_dedup[:3])
    
    if core and len(core) > 3:
        return core
    return raw_query.strip()


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

    # Preprocess query for DB search: extract core domain keywords,
    # filter out generic method/academic words that drown results.
    # e.g. "Computer Vision-Based Prediction of Glycemic Index..."
    # → "glycemic index glycemic load indonesian foods nutritional biochemistry"
    search_query = _extract_core_query(query)
    log.info("tool_literatur.query_preprocess: '%s' → search_query='%s'",
             query[:80], search_query[:120])

    fetch_limit = top_k * 10  # Oversample untuk AI rerank headroom
    if year_from:
        fetch_limit = fetch_limit * 2  # Extra headroom untuk year filter

    papers = db_cache.search_papers(
        query=search_query,
        limit=fetch_limit,
        year_from=year_from,
        sources=sources,
    )
    log.info("tool_literatur.db_search: got %d papers from paper_database (search_query='%s')", len(papers), search_query[:80])

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
                query=search_query,  # Use preprocessed query for API too
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

    # ── KEYWORD MULTIPLICATIVE BOOST (PIPELINE-LEVEL) ──
    # scoring.py sudah handle keyword di level ML (weight 25% + phrase-based boost).
    # Di pipeline, kita reinforce dengan boost tambahan: paper yang judulnya
    # mengandung key phrases (2+ word sequences) → extra boost.
    # Ini safety net kalau scoring.py gagal load (exception).
    from .scoring import _extract_key_phrases
    key_phrases = _extract_key_phrases(query)
    def _keyword_mult(p: Paper) -> float:
        """Multiplicative keyword boost — 1.0 (no boost) to 1.3x."""
        title = (p.title or '').lower().replace('-', ' ')
        abstract = (p.abstract or '').lower().replace('-', ' ')
        title_hits = sum(1 for ph in key_phrases if ph in title)
        abs_hits = sum(1 for ph in key_phrases if ph in abstract and ph not in title)
        if title_hits >= 2:
            return 1.3
        if title_hits >= 1:
            return 1.15
        if abs_hits >= 2:
            return 1.1
        if abs_hits >= 1:
            return 1.05
        return 1.0

    # Apply multiplicative boost + re-sort
    if ml_scored:
        def _final_key(p: Paper) -> float:
            sp = ml_scored.get((p.title or '').lower())
            ml = sp.score_total if sp else 0.0
            return ml * _keyword_mult(p)
        papers.sort(key=_final_key, reverse=True)
    else:
        # No ML scores — db_score + multiplicative keyword
        def _final_key_db(p: Paper) -> float:
            db = p.db_score or 0
            return db * _keyword_mult(p)
        papers.sort(key=_final_key_db, reverse=True)
    log.info("tool_literatur.keyword_boost: applied multiplicative boost")

    if progress_cb:
        progress_cb("db_scored", {"count": len(papers)})

    # ── 2. TAMPIL FASE 1: hasil DB scoring ─────────────────────────────
    if progress_cb:
        progress_cb("displaying_initial", {"count": len(papers)})

    # Simpan hasil scoring ke frontend
    if save_cb:
        records_phase1 = [
            _paper_record(i, p,
                          original_rank=i + 1,
                          relevance_score=(
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

    # Build final records: track original rank (pre-AI) and new rank (post-AI)
    all_records = []
    ai_rank_map = {}  # title → new rank
    if reordered:
        for rank_pos, p in enumerate(papers, 1):
            key = (p.title or "").lower()
            ai_rank_map[key] = rank_pos

    for i, p in enumerate(papers):
        title_key = (p.title or "").lower()
        new_rank = ai_rank_map.get(title_key)
        sp = ml_scored.get(title_key)
        ml_score = sp.score_total if sp else None
        review = getattr(p, "review", None) or ""
        all_records.append(_paper_record(
            i, p,
            original_rank=i + 1,
            new_rank=new_rank,
            review=review,
            relevance_score=ml_score,
        ))

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