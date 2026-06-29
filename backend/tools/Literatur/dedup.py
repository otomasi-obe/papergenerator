"""Deduplikasi untuk SLR: DOI exact match + Jaro-Winkler fuzzy pada judul.

Dua lapis dedup:
1. DOI exact match — paling akurat, tidak ada false positive
2. Jaro-Winkler similarity (threshold 0.90) pada title_normalized —
   tangkap duplikat tanpa DOI atau DOI berbeda (preprint vs published)

Gunakan rapidfuzz (lebih cepat dari python-Levenshtein murni).
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# ── DOI normalization ──────────────────────────────────────────────────────

def normalize_doi(doi: str | None) -> str | None:
    """Normalisasi DOI ke bentuk lowercase, strip prefix URL.

    "https://doi.org/10.1234/abc" → "10.1234/abc"
    "10.1234/ABC" → "10.1234/abc"
    """
    if not doi or not isinstance(doi, str):
        return None
    doi = doi.strip()
    # Remove URL prefix
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
    # Remove whitespace
    doi = doi.strip().lower()
    return doi if doi else None


# ── Title normalization ────────────────────────────────────────────────────


def normalize_title(title: str | None) -> str | None:
    """Normalisasi judul untuk perbandingan fuzzy.

    - Lowercase
    - Hapus punctuation (kecuali hyphen dalam kata)
    - Collapse whitespace
    - Hapus leading/trailing articles (the, a, an)
    """
    if not title:
        return None
    t = title.lower().strip()
    # Hapus karakter non-alphanumeric (kecuali spasi dan hyphen dalam kata)
    t = re.sub(r'[^\w\s-]', '', t)
    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    # Hapus leading articles
    t = re.sub(r'^(the|a|an)\s+', '', t)
    return t if t else None


# ── Deduplication ──────────────────────────────────────────────────────────


class Deduplicator:
    """Deduplikasi dua tahap: DOI exact → Jaro-Winkler fuzzy.

    Usage:
        dedup = Deduplicator()
        unique, duplicates = dedup.deduplicate(papers)
        # papers: list of dicts with 'doi', 'title', 'id'
    """

    def __init__(
        self,
        jw_threshold: float = 0.90,
        jw_title_threshold: float = 0.92,
    ):
        """
        Args:
            jw_threshold: Jaro-Winkler similarity minimum (default 0.90)
            jw_title_threshold: Threshold lebih tinggi untuk judul pendek (<30 chars)
        """
        self.jw_threshold = jw_threshold
        self.jw_title_threshold = jw_title_threshold
        self._seen_dois: set[str] = set()
        self._seen_titles: list[tuple[str, str]] = []  # (normalized_title, paper_id)

    def reset(self) -> None:
        """Reset state untuk batch baru."""
        self._seen_dois.clear()
        self._seen_titles.clear()

    def is_duplicate(self, doi: str | None, title: str | None, paper_id: str = "") -> tuple[bool, str | None]:
        """Cek apakah satu paper duplikat dari yang sudah ada.

        Args:
            doi: DOI paper (bisa None)
            title: Judul paper (bisa None)
            paper_id: ID untuk logging

        Returns:
            (is_duplicate, reason)
            reason: "doi_match:X" atau "title_similar:X (0.XXX)"
        """
        # Stage 1: DOI exact match
        doi_norm = normalize_doi(doi)
        if doi_norm and doi_norm in self._seen_dois:
            return True, f"doi_match:{doi_norm}"

        # Stage 2: Jaro-Winkler title similarity
        title_norm = normalize_title(title)
        if title_norm:
            threshold = (
                self.jw_title_threshold
                if len(title_norm) < 30
                else self.jw_threshold
            )
            for existing_title, existing_id in self._seen_titles:
                sim = _jaro_winkler_similarity(title_norm, existing_title)
                if sim >= threshold:
                    return True, f"title_similar:{existing_id} ({sim:.3f})"

        return False, None

    def add(self, doi: str | None, title: str | None, paper_id: str) -> None:
        """Tambah paper ke set yang sudah dilihat."""
        doi_norm = normalize_doi(doi)
        if doi_norm:
            self._seen_dois.add(doi_norm)

        title_norm = normalize_title(title)
        if title_norm:
            self._seen_titles.append((title_norm, paper_id))

    def deduplicate(
        self,
        papers: list[dict[str, Any]],
        id_key: str = "id",
        doi_key: str = "doi",
        title_key: str = "title",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Deduplicate list of paper dicts.

        Args:
            papers: List paper dict
            id_key: Key untuk ID
            doi_key: Key untuk DOI
            title_key: Key untuk judul

        Returns:
            (unique_papers, duplicate_papers)
            Setiap duplicate punya field `_dup_reason` yang menjelaskan kenapa.
        """
        self.reset()
        unique: list[dict] = []
        duplicates: list[dict] = []

        for i, paper in enumerate(papers):
            pid = paper.get(id_key, str(i))
            doi = paper.get(doi_key)
            title = paper.get(title_key)

            is_dup, reason = self.is_duplicate(doi, title, pid)
            if is_dup:
                paper_copy = dict(paper)
                paper_copy["_dup_reason"] = reason
                duplicates.append(paper_copy)
                log.debug("Duplicate: %s → %s", pid, reason)
            else:
                self.add(doi, title, pid)
                unique.append(paper)

        log.info(
            "Dedup: %d total → %d unique, %d duplicates (%.1f%% removed)",
            len(papers), len(unique), len(duplicates),
            len(duplicates) / max(len(papers), 1) * 100,
        )
        return unique, duplicates


def deduplicate(
    papers: list[dict[str, Any]],
    id_key: str = "id",
    doi_key: str = "doi",
    title_key: str = "title",
    jw_threshold: float = 0.90,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Shortcut function untuk deduplikasi."""
    dedup = Deduplicator(jw_threshold=jw_threshold)
    return dedup.deduplicate(papers, id_key, doi_key, title_key)


# ── Jaro-Winkler via rapidfuzz ─────────────────────────────────────────────


def _jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity via rapidfuzz, fallback ke pure Python."""
    try:
        from rapidfuzz.distance import JaroWinkler

        return JaroWinkler.normalized_similarity(s1, s2)  # type: ignore[no-any-return]
    except ImportError:
        # Pure Python fallback
        return _jaro_winkler_pure(s1, s2)


def _jaro_winkler_pure(s1: str, s2: str) -> float:
    """Pure Python Jaro-Winkler implementation — fallback."""
    # Jaro similarity
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len_s1, len_s2 = len(s1), len(s2)
    match_distance = max(len_s1, len_s2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len_s1
    s2_matches = [False] * len_s2
    matches = 0

    for i in range(len_s1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len_s2)
        for j in range(start, end):
            if not s2_matches[j] and s1[i] == s2[j]:
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

    if matches == 0:
        return 0.0

    # Transpositions
    transpositions = 0
    k = 0
    for i in range(len_s1):
        if s1_matches[i]:
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1

    jaro = (
        matches / len_s1
        + matches / len_s2
        + (matches - transpositions / 2) / matches
    ) / 3.0

    # Winkler boost
    prefix = 0
    for i in range(min(4, len_s1, len_s2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * 0.1 * (1.0 - jaro)


# ── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test normalization
    assert normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
    assert normalize_doi("10.1234/XYZ") == "10.1234/xyz"
    assert normalize_doi(None) is None
    assert normalize_doi("") is None

    assert normalize_title("The Great Paper") == "great paper"
    assert normalize_title("  A Study of ML  ") == "study of ml"

    # Test dedup
    papers = [
        {"id": "1", "doi": "10.1000/abc", "title": "Machine Learning for SLR"},
        {"id": "2", "doi": "10.1000/abc", "title": "Machine Learning for SLR"},  # DOI dup
        {"id": "3", "doi": "10.1000/xyz", "title": "Machine Learning for SLR"},  # Title dup
        {"id": "4", "doi": None, "title": "Machine Learning for Systematic Lit Review"},  # Similar
        {"id": "5", "doi": "10.1000/new", "title": "Completely Different Topic"},  # Unique
    ]

    dedup = Deduplicator()
    unique, dups = dedup.deduplicate(papers)

    print(f"Unique: {len(unique)}")
    for p in unique:
        print(f"  {p['id']}: {p['title'][:50]}")
    print(f"\nDuplicates: {len(dups)}")
    for p in dups:
        print(f"  {p['id']}: {p.get('_dup_reason', '?')}")

    assert len(unique) == 2, f"Expected 2 unique, got {len(unique)}"
    assert len(dups) == 3, f"Expected 3 duplicates, got {len(dups)}"
    print("\n✓ All dedup tests passed")