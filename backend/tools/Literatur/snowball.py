"""Snowballing sitasi untuk SLR — backward references + forward citations.

Reuse classifier dari active learning (langkah 4), tidak latih model baru.

Algoritma:
  seed = included_papers
  cand = backward_refs(seed) ∪ forward_citations(seed)  # via OpenAlex/S2
  cand = dedup(cand) - already_screened
  score(c) = 0.6·clf.proba(c) + 0.4·citation_overlap(c, seed)
  → kandidat skor tinggi masuk balik ke screening (langkah 4)
  ulangi sampai tidak ada included baru (konvergen)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable
    from numpy.typing import NDArray

log = logging.getLogger(__name__)

# ── Data types ─────────────────────────────────────────────────────────────


@dataclass
class SnowballResult:
    """Hasil satu iterasi snowballing."""

    iteration: int
    new_candidates: list[dict]       # kandidat baru dari citation graph
    scored_candidates: list[dict]    # sudah diskor (score, proba, citation_overlap)
    newly_included: list[str]        # ID kandidat yang masuk
    total_included: int              # total included setelah iterasi ini
    converged: bool                  # True kalau tidak ada included baru


# ── Snowballer ─────────────────────────────────────────────────────────────


class Snowballer:
    """Snowballing search menggunakan OpenAlex + Semantic Scholar API.

    Menggabungkan:
    - Backward references (paper yang disitasi oleh seed)
    - Forward citations (paper yang mensitasi seed)
    - Citation overlap scoring (co-citation + bibliographic coupling)
    """

    def __init__(
        self,
        classifier=None,          # SVM classifier dari screening (punya predict_proba)
        embed_fn: Callable | None = None,  # SPECTER2 embed function
        openalex_email: str | None = None,
        max_backward_per_seed: int = 50,
        max_forward_per_seed: int = 50,
        max_total_candidates: int = 500,
        score_weight_classifier: float = 0.6,
        score_weight_citation: float = 0.4,
        min_score_threshold: float = 0.35,
    ):
        self.clf = classifier
        self.embed_fn = embed_fn
        self.openalex_email = openalex_email
        self.max_backward_per_seed = max_backward_per_seed
        self.max_forward_per_seed = max_forward_per_seed
        self.max_total_candidates = max_total_candidates
        self.score_w_clf = score_weight_classifier
        self.score_w_cit = score_weight_citation
        self.min_score = min_score_threshold

        self._already_screened: set[str] = set()
        self._already_snowballed: set[str] = set()

    # ── Public API ──────────────────────────────────────────────────────

    def set_screened(self, paper_ids: list[str]) -> None:
        """Tandai paper yang sudah melalui screening."""
        self._already_screened.update(paper_ids)

    def set_snowballed(self, paper_ids: list[str]) -> None:
        """Tandai paper yang sudah melalui snowballing."""
        self._already_snowballed.update(paper_ids)

    def run_iteration(
        self,
        included_papers: list[dict],
        iteration: int = 0,
    ) -> SnowballResult:
        """Jalankan satu iterasi snowballing.

        Args:
            included_papers: List dict paper dengan setidaknya 'id', 'doi', 'title'
            iteration: Nomor iterasi (untuk tracking)

        Returns:
            SnowballResult
        """
        t0 = time.time()

        # 1. Ambil backward refs + forward citations
        candidates = self._fetch_citation_graph(included_papers)

        # 2. Dedup - hapus yang sudah discreen/disnowball
        candidates = [
            c for c in candidates
            if c.get("id") not in self._already_screened
            and c.get("id") not in self._already_snowballed
        ]

        if not candidates:
            log.info("Snowball iter %d: no new candidates", iteration)
            return SnowballResult(
                iteration=iteration,
                new_candidates=[],
                scored_candidates=[],
                newly_included=[],
                total_included=len(included_papers),
                converged=True,
            )

        # 3. Hitung citation overlap dengan seed
        citation_overlaps = self._compute_citation_overlap(
            candidates, included_papers
        )

        # 4. Score dengan weighted combination
        scored = self._score_candidates(candidates, citation_overlaps)

        # 5. Filter by threshold
        scored = [c for c in scored if c.get("_score", 0) >= self.min_score]
        scored.sort(key=lambda c: c.get("_score", 0), reverse=True)

        # 6. Mark as snowballed
        for c in scored:
            self._already_snowballed.add(c.get("id", ""))

        newly_included = [c["id"] for c in scored[:50]]  # top-50
        converged = len(newly_included) == 0

        elapsed = time.time() - t0
        log.info(
            "Snowball iter %d: %d candidates → %d scored → %d included (%.1fs)%s",
            iteration, len(candidates), len(scored), len(newly_included),
            elapsed, " CONVERGED" if converged else "",
        )

        return SnowballResult(
            iteration=iteration,
            new_candidates=candidates,
            scored_candidates=scored,
            newly_included=newly_included,
            total_included=len(included_papers) + len(newly_included),
            converged=converged,
        )

    # ── Internal ───────────────────────────────────────────────────────

    def _fetch_citation_graph(
        self, seed_papers: list[dict]
    ) -> list[dict]:
        """Fetch backward refs + forward citations via OpenAlex API.

        Kalau OpenAlex gagal, coba Semantic Scholar.
        """
        candidates: list[dict] = []
        dois = [p.get("doi") for p in seed_papers if p.get("doi")]

        if dois:
            candidates = self._fetch_openalex(dois)

        # Fallback: Semantic Scholar
        if not candidates and dois:
            candidates = self._fetch_semantic_scholar(dois)

        # Dedup by ID
        seen = set()
        unique = []
        for c in candidates:
            cid = c.get("id", c.get("doi", ""))
            if cid and cid not in seen:
                seen.add(cid)
                unique.append(c)

        return unique[:self.max_total_candidates]

    def _fetch_openalex(self, dois: list[str]) -> list[dict]:
        """Fetch dari OpenAlex API."""
        import json
        import urllib.request

        candidates = []
        headers = {"User-Agent": "mailto:" + (self.openalex_email or "slr@example.com")}

        for doi in dois[:20]:  # Batasi 20 seed
            # Backward refs: /works/{id}/referenced_works
            # Forward citations: /works?filter=cites:{doi}
            try:
                # Forward citations
                url = f"https://api.openalex.org/works?filter=cites:https://doi.org/{doi}&per_page={self.max_forward_per_seed}"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                    for w in data.get("results", []):
                        candidates.append(self._parse_openalex_work(w))
            except Exception:
                continue

            # Rate limit
            time.sleep(0.1)

        return candidates

    def _fetch_semantic_scholar(self, dois: list[str]) -> list[dict]:
        """Fetch dari Semantic Scholar API (fallback)."""
        import json
        import urllib.request

        candidates = []
        for doi in dois[:10]:
            try:
                url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}/citations?limit={self.max_forward_per_seed}&fields=title,year,authors,abstract"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read())
                    for c in data.get("data", []):
                        paper = c.get("citingPaper", {})
                        if paper:
                            candidates.append({
                                "id": paper.get("paperId", ""),
                                "title": paper.get("title", ""),
                                "year": paper.get("year"),
                                "authors": [a.get("name", "") for a in paper.get("authors", [])],
                                "abstract": paper.get("abstract", ""),
                                "doi": paper.get("externalIds", {}).get("DOI", ""),
                                "source": "semantic_scholar_citation",
                            })
            except Exception:
                continue
        return candidates

    def _parse_openalex_work(self, w: dict) -> dict:
        """Parse OpenAlex work ke format standar."""
        return {
            "id": w.get("id", "").split("/")[-1] if w.get("id") else "",
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
            "title": w.get("title") or w.get("display_name", ""),
            "year": w.get("publication_year"),
            "authors": [
                a.get("author", {}).get("display_name", "")
                for a in w.get("authorships", [])
            ],
            "abstract": _reconstruct_openalex_abstract(w.get("abstract_inverted_index")),
            "citations": w.get("cited_by_count", 0),
            "source": "openalex",
        }

    def _compute_citation_overlap(
        self,
        candidates: list[dict],
        seed: list[dict],
    ) -> dict[str, float]:
        """Hitung citation overlap — simplified co-citation proxy.

        Untuk efisiensi, gunakan judul similarity sebagai proxy citation overlap.
        Paper dengan judul mirip seed cenderung disitasi bersama (co-citation).
        """
        overlaps: dict[str, float] = {}
        if not seed:
            return overlaps

        from .dedup import normalize_title, _jaro_winkler_similarity

        seed_titles = [
            normalize_title(p.get("title", ""))
            for p in seed
        ]
        seed_titles = [t for t in seed_titles if t]

        for c in candidates:
            ct = normalize_title(c.get("title", ""))
            if not ct:
                overlaps[c.get("id", "")] = 0.0
                continue

            # Rata-rata similarity dengan semua seed titles
            sims = []
            for st in seed_titles[:20]:  # Batasi untuk perf
                sims.append(_jaro_winkler_similarity(ct, st))

            # Gunakan max similarity (proxy untuk citation coupling)
            overlaps[c.get("id", "")] = max(sims) if sims else 0.0

        return overlaps

    def _score_candidates(
        self,
        candidates: list[dict],
        citation_overlaps: dict[str, float],
    ) -> list[dict]:
        """Score kandidat dengan weighted combination classifier + citation overlap."""
        for c in candidates:
            cid = c.get("id", "")

            # Classifier score
            clf_score = 0.5  # default
            if self.clf is not None and self.embed_fn is not None:
                try:
                    title = c.get("title", "") or ""
                    abstract = c.get("abstract", "") or ""
                    text = title + " " + abstract
                    emb = self.embed_fn(text)
                    if emb is not None:
                        proba = self.clf.predict_proba(emb.reshape(1, -1))
                        clf_score = float(proba[0, 1])
                except Exception:
                    pass

            # Citation overlap score
            cit_score = citation_overlaps.get(cid, 0.0)

            # Weighted combination
            score = self.score_w_clf * clf_score + self.score_w_cit * cit_score
            c["_score"] = score
            c["_clf_proba"] = clf_score
            c["_citation_overlap"] = cit_score

        scored = sorted(candidates, key=lambda x: x.get("_score", 0), reverse=True)
        return scored


def _reconstruct_openalex_abstract(inv_index: dict | None) -> str:
    """Rekonstruksi abstrak dari inverted index OpenAlex."""
    if not inv_index:
        return ""
    pos_map = {}
    for word, positions in inv_index.items():
        for p in positions:
            pos_map[p] = word
    if not pos_map:
        return ""
    max_pos = max(pos_map.keys())
    return " ".join(pos_map.get(i, "") for i in range(max_pos + 1)).strip()