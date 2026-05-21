"""Scoring + ranking paper tanpa LLM (gratis penuh).

Mengkombinasi 5 sinyal yang diekstrak dari kode 10 repo SLR rujukan:

1. SBERT cosine similarity terhadap topik query        (PROMPTHEUS A2)
2. TF-IDF cosine sebagai sinyal pelengkap (no-embedding fallback)
3. Citation impact (log-normalized)                    (paper-qa enrichment)
4. Recency (sigmoid 5-tahun)                           (gpt-researcher sort)
5. Source / venue quality bonus                        (paper-qa retraction
   pattern + dblp venue typing)

Output:
    score_total    -> 0..1
    score_breakdown -> dict per komponen
    must_read       -> bool (>= 0.55)
    is_relevant     -> bool (>= 0.40, threshold PROMPTHEUS default)

Tidak menggunakan API berbayar. Embedding dipakai pakai
`all-MiniLM-L6-v2` (model lokal, 80 MB, ~3 ms/abstract di CPU).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .paper import Paper
from .text_cleaner import clean_abstract, clean_title

_SBERT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_SBERT = None  # lazy

_HIGH_QUALITY_VENUE_TOKENS = (
    "ieee", "acm", "springer", "elsevier", "nature", "science",
    "transactions", "proceedings", "annals", "communications",
)


def _get_sbert():
    global _SBERT
    if _SBERT is None:
        from sentence_transformers import SentenceTransformer
        _SBERT = SentenceTransformer(_SBERT_MODEL)
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
    now = datetime.utcnow().year
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


def _has_signal(p: Paper) -> bool:
    if not (p.abstract and len(p.abstract.strip()) > 80):
        return False
    return bool(p.title and p.title.strip())


def _embed(texts: Sequence[str]) -> np.ndarray:
    sbert = _get_sbert()
    return sbert.encode(list(texts), batch_size=32, show_progress_bar=False,
                         convert_to_numpy=True, normalize_embeddings=True)


def score_papers(query: str, papers: Iterable[Paper],
                 sbert_threshold: float = 0.40,
                 must_read_threshold: float = 0.55) -> list[ScoredPaper]:
    """Skor batch paper. Paper tanpa abstract tetap di-skor pakai title-only +
    penalti pada score_breakdown.has_signal."""
    plist = list(papers)
    if not plist:
        return []

    texts = [_build_text(p) for p in plist]
    has_signal = [_has_signal(p) for p in plist]

    # Strategi A2 PROMPTHEUS: SBERT cosine.
    embs = _embed([query] + texts)
    q_emb, doc_emb = embs[0:1], embs[1:]
    sbert_sims = (doc_emb @ q_emb.T).flatten()

    # Sinyal pelengkap: TF-IDF cosine. Bekerja walau abstract pendek.
    try:
        vec = TfidfVectorizer(stop_words="english", max_df=0.9, min_df=1,
                              ngram_range=(1, 2))
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
        signal_penalty = 0.0 if has_signal[i] else 0.15

        total = (
            0.45 * sbert_s
            + 0.15 * tfidf_s
            + 0.15 * cite_s
            + 0.10 * recency_s
            + 0.15 * venue_s
        ) - signal_penalty
        total = max(0.0, min(1.0, total))

        breakdown = {
            "sbert": round(sbert_s, 4),
            "tfidf": round(tfidf_s, 4),
            "citation": round(cite_s, 4),
            "recency": round(recency_s, 4),
            "venue": round(venue_s, 4),
            "has_signal": has_signal[i],
            "signal_penalty": signal_penalty,
        }

        out.append(ScoredPaper(
            paper=p,
            score_total=round(total, 4),
            score_breakdown=breakdown,
            is_relevant=sbert_s >= sbert_threshold,
            must_read=total >= must_read_threshold,
        ))

    out.sort(key=lambda s: -s.score_total)
    return out
