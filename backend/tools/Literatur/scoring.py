"""Scoring + ranking paper tanpa LLM (gratis penuh).

Mengkombinasi 7 sinyal yang diekstrak dari kode 10 repo SLR rujukan:

1. SBERT cosine similarity terhadap topik query        (PROMPTHEUS A2) — 50%
2. TF-IDF cosine sebagai sinyal pelengkap (no-embedding fallback) — 10%
3. Citation impact (log-normalized)                    (paper-qa enrichment) — 10%
4. Recency (sigmoid 5-tahun)                           (gpt-researcher sort) — 8%
5. Source / venue quality bonus                        (paper-qa retraction — 10%
   pattern + dblp venue typing)
6. Keyword density (exact query terms in title)        — 7%
7. Author prestige (team-size proxy)                   — 5%

Output:
    score_total    -> 0..1
    score_breakdown -> dict per komponen
    must_read       -> bool (>= 0.55)
    is_relevant     -> bool (>= 0.45, threshold tightened for precision)

Tidak menggunakan API berbayar. Embedding dipakai pakai
`all-MiniLM-L6-v2` (model lokal, 80 MB, ~3 ms/abstract di CPU). Bila
`sentence_transformers` tidak terinstall (mis. lingkungan slim / CI),
embedder otomatis fallback ke TF-IDF (max_features=384, normalized) dengan
sentinel `_TFIDF_FALLBACK` sehingga cosine downstream tetap jalan.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .paper import Paper
from .text_cleaner import clean_abstract, clean_title, detect_mojibake

log = logging.getLogger(__name__)

_SBERT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_SBERT = None  # lazy
_TFIDF_FALLBACK = "TFIDF_FALLBACK"

_HIGH_QUALITY_VENUE_TOKENS = (
    "ieee",
    "acm",
    "springer",
    "elsevier",
    "nature",
    "science",
    "transactions",
    "proceedings",
    "annals",
    "communications",
)


def _get_sbert():
    """Return the SBERT model, or the sentinel `_TFIDF_FALLBACK` string when
    `sentence_transformers` is missing / fails to load. Cached per-process."""
    global _SBERT
    if _SBERT is None:
        try:
            from sentence_transformers import SentenceTransformer

            _SBERT = SentenceTransformer(_SBERT_MODEL)
        except Exception as e:
            log.warning(
                "sentence_transformers unavailable, using TF-IDF fallback: %s",
                e,
            )
            _SBERT = _TFIDF_FALLBACK
    return _SBERT


def _build_text(p: Paper) -> str:
    title = clean_title(p.title or "")
    abstract = clean_abstract(p.abstract or "")
    return f"{title}. {abstract}".strip(". ").strip()


@dataclass
class ScoredPaper:
    paper: Paper
    score_total: float
    score_breakdown: dict
    must_read: bool
    is_relevant: bool


def _sigmoid(x: float, k: float = 1.0) -> float:
    return 1.0 / (1.0 + math.exp(-k * x))


def _recency_score(year: int | None) -> float:
    if not year:
        return 0.3
    now = datetime.now(timezone.utc).year
    age = max(0, now - int(year))
    return _sigmoid(2.0 - age / 3.0)


def _citation_score(citations: int | None) -> float:
    if citations is None or citations < 0:
        return 0.0
    return min(1.0, math.log1p(citations) / math.log1p(500))


def _venue_score(p: Paper) -> float:
    base = 0.3
    venue = (p.venue or p.publisher or "").lower()
    if any(t in venue for t in _HIGH_QUALITY_VENUE_TOKENS):
        base = 0.85
    elif p.venue_type == "journal":
        base = 0.6
    elif p.venue_type == "conference":
        base = 0.55
    elif p.venue_type == "preprint":
        base = 0.4
    if p.is_open_access:
        base = min(1.0, base + 0.05)
    return base


def _keyword_density_score(query: str, p: Paper) -> float:
    """Bonus for papers whose title/abstract directly contain query terms.

    Returns 0.0–1.0:
    - Full query phrase in title → 1.0 (perfect match — mutlak paling relevan)
    - Full query phrase in abstract → 0.8
    - All meaningful terms in title → 0.7+
    - Partial terms in title → proportional
    - Terms only in abstract → lower score (0.2–0.5)

    Abstract matching diperluas (sebelumnya title-only). User ingin
    paper yang benar2 relate, bukan yang hanya menyebut 1 kata kunci.
    """
    title = (p.title or "").lower()
    abstract = (p.abstract or "").lower()
    query_lower = query.lower().strip()

    if not title and not abstract:
        return 0.0

    # Full phrase match in title → absolutely relevant
    if query_lower in title:
        return 1.0

    # Full phrase match in abstract → very relevant
    if query_lower in abstract:
        return 0.8

    # Individual term matching
    _stopwords = {
        "and", "the", "for", "with", "from", "that", "this", "are",
        "was", "but", "not", "can", "all", "any", "has", "its", "may",
        "who", "which", "their", "how", "what", "why", "use", "based",
        "using", "study", "analysis", "approach", "method", "model",
        "system", "data", "also", "been", "were", "will", "have",
    }
    terms = [
        t.lower() for t in re.findall(r"[a-zA-Z]{3,}", query_lower)
        if t.lower() not in _stopwords
    ]
    if not terms:
        # Short query fallback
        terms = [t.lower() for t in re.findall(r"[a-zA-Z0-9]{2,}", query_lower)]
        if not terms:
            return 0.0

    n = len(terms)
    # Title match counts 3x vs abstract match
    title_matched = sum(1 for t in terms if re.search(rf'\b{re.escape(t)}\b', title))
    abs_matched = sum(1 for t in terms if re.search(rf'\b{re.escape(t)}\b', abstract))

    # Cap at meaningful level — a paper with 1/5 terms should not score high
    # unless it matches the unique/longest terms
    score = (title_matched * 3 + abs_matched) / (n * 4) if n > 0 else 0

    # Boost for matching the LONGEST terms (most specific) — these are
    # typically the most meaningful signal of relevance
    if terms and title_matched > 0:
        longest = sorted(terms, key=len, reverse=True)[:3]
        longest_in_title = sum(1 for t in longest if re.search(rf'\b{re.escape(t)}\b', title))
        if longest_in_title >= 2:
            score = max(score, 0.65)  # At least medium-high if longest terms appear

    return min(1.0, score)


def _author_prestige_score(p: Paper) -> float:
    """Signal based on author count and name recognition.

    Heuristic: papers with multiple authors (≥3) tend to come from established
    research groups. Well-known author names from top venues get a small bonus.
    This is a lightweight proxy for author h-index when we don't have it.
    """
    if not p.authors:
        return 0.0
    n = len(p.authors)
    # Solo author → base, 2-3 → moderate, 4+ → higher (team science signal)
    if n >= 4:
        return 0.6
    elif n >= 3:
        return 0.45
    elif n >= 2:
        return 0.3
    else:
        return 0.15


def _has_signal(p: Paper) -> bool:
    if not (p.abstract and len(p.abstract.strip()) > 80):
        return False
    return bool(p.title and p.title.strip())


def _embed(texts: Sequence[str], batch_size: int = 200) -> np.ndarray:
    """Encode `texts` to L2-normalized dense vectors.

    Prefers SBERT (`all-MiniLM-L6-v2`, 384-dim). When `sentence_transformers`
    is not available, falls back to a TF-IDF vectorizer with `max_features=384`
    and L2 normalization, which keeps cosine math downstream unchanged.

    BUG-EMBED_BATCH_MEMORY: SBERT path processes in chunks of `batch_size` to
    prevent memory spikes with 1000+ papers. TF-IDF fallback always processes
    all texts together (shared vocabulary required).
    """
    sbert = _get_sbert()
    if sbert == _TFIDF_FALLBACK:
        if not texts:
            return np.zeros((0, 768), dtype=np.float32)
        try:
            vec = TfidfVectorizer(
                max_features=768,
                ngram_range=(1, 3),
                analyzer="char_wb",
                sublinear_tf=True,
            )
            mat = vec.fit_transform(list(texts)).astype(np.float32).toarray()
        except ValueError:
            # Empty vocab (e.g. all-stopword inputs) → fall back to zeros.
            return np.zeros((len(texts), 768), dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    texts_list = list(texts)
    if len(texts_list) <= batch_size:
        return sbert.encode(
            texts_list,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

    # BUG-EMBED_BATCH_MEMORY: chunked processing to prevent memory spikes
    chunks = []
    for i in range(0, len(texts_list), batch_size):
        chunk = texts_list[i:i + batch_size]
        emb = sbert.encode(
            chunk,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        chunks.append(emb)
    return np.concatenate(chunks, axis=0)


def score_papers(
    query: str,
    papers: Iterable[Paper],
    sbert_threshold: float = 0.45,
    must_read_threshold: float = 0.55,
) -> list[ScoredPaper]:
    """Skor batch paper. Paper tanpa abstract tetap di-skor pakai title-only +
    penalti pada score_breakdown.has_signal."""
    plist = list(papers)
    if not plist:
        return []

    # ── Deteksi apakah SBERT tersedia ──
    # TF-IDF fallback kurang akurat secara semantik → keyword + struktur text
    # mendapat bobot lebih besar.
    _using_sbert = _get_sbert() != _TFIDF_FALLBACK

    texts = [_build_text(p) for p in plist]
    has_signal = [_has_signal(p) for p in plist]

    # Strategi A2 PROMPTHEUS: SBERT cosine.
    embs = _embed([query] + texts)
    q_emb, doc_emb = embs[0:1], embs[1:]
    sbert_sims = (doc_emb @ q_emb.T).flatten()

    # Sinyal pelengkap: TF-IDF cosine. Bekerja walau abstract pendek.
    try:
        max_df = 1.0 if len(plist) < 20 else 0.9
        vec = TfidfVectorizer(
            max_df=max_df,
            min_df=1,
            ngram_range=(1, 3),
            analyzer="char_wb",
            sublinear_tf=True,
        )
        mat = vec.fit_transform([query] + texts)
        tfidf_sims = cosine_similarity(mat[0:1], mat[1:]).flatten()
    except ValueError:
        tfidf_sims = np.zeros(len(plist))

    out: list[ScoredPaper] = []
    for i, p in enumerate(plist):
        sbert_s = float(sbert_sims[i])
        tfidf_s = float(tfidf_sims[i])
        cite_s = _citation_score(p.citations)
        recency_s = _recency_score(p.year)
        venue_s = _venue_score(p)
        keyword_s = _keyword_density_score(query, p)
        author_s = _author_prestige_score(p)
        signal_penalty = 0.0 if has_signal[i] else 0.15

        # ── Tekstualitas: deteksi mojibake ──
        # Paper dengan teks rusak (mojibake) di-judul atau abstract
        # mendapat penalty multiplicative HARD sehingga tidak bisa menang
        # dari SBERT atau FTS score.
        garbled_title = detect_mojibake(p.title)
        garbled_abs = detect_mojibake(p.abstract)
        text_quality = 1.0 - max(garbled_title, garbled_abs)
        # text_quality: 0.0 (garbled total) → 1.0 (clean)
        # Multiplicative: paper garbled → score_total ~0

        # ── Keyword density weight dinaikkan ──
        # Keyword match di judul/abstract lebih penting dari venue/sitasi
        # untuk relevance ranking. User ingin paper yang judulnya
        # mengandung kata kunci lebih diutamakan.
        #
        # ADAPTIVE: saat SBERT tersedia → keyword 17%, SBERT 40%.
        # Saat TF-IDF fallback → keyword 25%, SBERT 25% (TF-IDF kurang
        # akurat secara semantik, keyword matching lebih reliable).
        if _using_sbert:
            w_sbert, w_tfidf, w_cite, w_recency, w_venue, w_kw, w_author = (
                0.40, 0.10, 0.08, 0.08, 0.10, 0.17, 0.07
            )
        else:
            w_sbert, w_tfidf, w_cite, w_recency, w_venue, w_kw, w_author = (
                0.25, 0.15, 0.06, 0.06, 0.08, 0.25, 0.05
            )
        base_score = (
            w_sbert * sbert_s
            + w_tfidf * tfidf_s
            + w_cite * cite_s
            + w_recency * recency_s
            + w_venue * venue_s
            + w_kw * keyword_s
            + w_author * author_s
        )
        # Multiplicative penalty: signal issues + text quality
        total = base_score * (1.0 - signal_penalty) * text_quality
        total = max(0.0, min(1.0, total))

        breakdown = {
            "sbert": round(sbert_s, 4),
            "tfidf": round(tfidf_s, 4),
            "citation": round(cite_s, 4),
            "recency": round(recency_s, 4),
            "venue": round(venue_s, 4),
            "keyword_density": round(keyword_s, 4),
            "author_prestige": round(author_s, 4),
            "has_signal": has_signal[i],
            "signal_penalty": signal_penalty,
            "text_quality": round(text_quality, 4),
        }

        out.append(
            ScoredPaper(
                paper=p,
                score_total=round(total, 4),
                score_breakdown=breakdown,
                is_relevant=sbert_s >= sbert_threshold,
                must_read=total >= must_read_threshold,
            )
        )

    out.sort(key=lambda s: -s.score_total)
    return out


def _pinned_similarity_score(
    papers: list[Paper],
    pinned_papers: list[Paper],
    sbert_sims: np.ndarray,
) -> list[float]:
    """Active Learning: boost paper yang mirip dengan paper yang sudah di-pin user."""
    if len(pinned_papers) < 2:
        return [0.0] * len(papers)

    # GABUNG pinned + candidates dalam satu panggilan _embed()
    # agar dimensi konsisten (penting untuk TF-IDF fallback yang
    # vocabulary-nya tergantung input)
    pinned_texts = [_build_text(p) for p in pinned_papers]
    all_texts = [_build_text(p) for p in papers]
    
    combined = pinned_texts + all_texts
    try:
        combined_embs = _embed(combined)
    except Exception:
        return [0.0] * len(papers)

    pinned_embs = combined_embs[:len(pinned_texts)]
    all_embs = combined_embs[len(pinned_texts):]

    avg_pinned_emb = pinned_embs.mean(axis=0, keepdims=True)
    similarities = (all_embs @ avg_pinned_emb.T).flatten()

    sim_min = similarities.min()
    sim_max = similarities.max()
    if sim_max - sim_min < 0.001:
        return [0.0] * len(papers)

    return [float((s - sim_min) / (sim_max - sim_min)) for s in similarities]


def score_papers_with_feedback(
    query: str,
    papers: Iterable[Paper],
    pinned_papers: list[Paper] | None = None,
    sbert_threshold: float = 0.45,
    must_read_threshold: float = 0.55,
) -> list[ScoredPaper]:
    """Skor batch paper DENGAN active learning dari user-pinned papers.

    Kalau user sudah pin ≥ 2 paper, signal active_learning (5%)
    ikut mempengaruhi ranking — paper yang mirip dengan yang sudah
    di-pin user dapat bonus score.

    Benchmark: ASReview LAB v2 — active learning + user feedback
    meningkatkan recall ke 95% setelah screening 38% dataset.
    """
    # ── Step 1: Score regular (7 signals) ──
    scored = score_papers(query, papers, sbert_threshold, must_read_threshold)

    # ── Step 2: Active Learning boost ──
    if pinned_papers and len(pinned_papers) >= 2:
        plist = [sp.paper for sp in scored]
        # Ambil SCORED paper yang di-pin (bukan input paper mentah)
        pinned_titles = {(p.title or "").lower() for p in pinned_papers}
        pinned_scored = [sp.paper for sp in scored
                         if (sp.paper.title or "").lower() in pinned_titles]

        if len(pinned_scored) >= 2:
            sims = _pinned_similarity_score(
                plist, pinned_scored,
                np.array([sp.score_breakdown.get("sbert", 0) for sp in scored]),
            )

            # Apply 5% active learning boost (additive)
            for i, sp in enumerate(scored):
                al_boost = sims[i] * 0.05  # max 5%
                old_total = sp.score_total
                new_total = max(0.0, min(1.0, old_total + al_boost))
                sp.score_total = round(new_total, 4)
                sp.score_breakdown["active_learning"] = round(al_boost, 4)
                sp.score_breakdown["active_learning_raw"] = round(sims[i], 4)

            # Re-sort setelah active learning boost
            scored.sort(key=lambda s: -s.score_total)
            log.info(
                "active_learning: applied with %d pinned papers, "
                "boosted %d candidates (max +0.05)",
                len(pinned_scored), sum(1 for s in scored
                                         if s.score_breakdown.get("active_learning", 0) > 0),
            )
        else:
            log.info("active_learning: skipped — pinned papers not found in candidate list")
    else:
        log.info("active_learning: skipped — need ≥ 2 pinned papers (got %d)",
                 len(pinned_papers or []))

    return scored
