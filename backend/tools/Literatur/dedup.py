"""Deduplikasi SLR: ID priority chain + title fuzzy fallback + canonical merge.

Priority chain (spec dosen section 7):
1. DOI (normalized)
2. PMID
3. PMC ID
4. arXiv ID
5. Semantic Scholar Paper ID
6. OpenAlex ID
7. Crossref ID
8. Normalized title (fuzzy ≥ 0.95 = auto dup, 0.90-0.95 = check author+year)

Canonical merge: duplicate paper's sources/source_ranks merged into canonical record.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

log = logging.getLogger(__name__)

# ── DOI normalization ──────────────────────────────────────────────────────

def normalize_doi(doi: str | None) -> str | None:
    """Normalisasi DOI ke bentuk lowercase, strip prefix URL."""
    if not doi or not isinstance(doi, str):
        return None
    doi = doi.strip()
    doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
    doi = doi.strip().lower()
    return doi if doi else None


# ── Title normalization ────────────────────────────────────────────────────

def normalize_title(title: str | None) -> str | None:
    """Normalisasi judul: lowercase, strip punctuation, normalize unicode, collapse whitespace."""
    if not title:
        return None
    t = unicodedata.normalize("NFKD", title.lower().strip())
    t = re.sub(r'[^\w\s-]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    t = re.sub(r'^(the|a|an)\s+', '', t)
    return t if t else None


# ── External ID extraction ─────────────────────────────────────────────────

def extract_ids(paper: dict | Any) -> dict[str, str | None]:
    """Extract all external IDs from a paper dict or Paper object."""
    if hasattr(paper, '__dict__'):
        d = {k: getattr(paper, k, None) for k in
             ('doi', 'pmid', 'pmcid', 'arxiv_id', 's2_id', 'openalex_id', 'crossref_id',
              'source', 'source_id')}
    else:
        d = {
            'doi': paper.get('doi'),
            'pmid': paper.get('pmid'),
            'pmcid': paper.get('pmcid'),
            'arxiv_id': paper.get('arxiv_id'),
            's2_id': paper.get('s2_id'),
            'openalex_id': paper.get('openalex_id'),
            'crossref_id': paper.get('crossref_id'),
            'source': paper.get('source'),
            'source_id': paper.get('source_id'),
        }

    # Auto-extract from source/source_id if fetcher-specific
    source = (d.get('source') or '').lower()
    source_id = d.get('source_id') or ''

    if source == 'semantic_scholar' and not d.get('s2_id'):
        d['s2_id'] = source_id
    elif source == 'openalex' and not d.get('openalex_id'):
        d['openalex_id'] = source_id
    elif source == 'crossref' and not d.get('crossref_id'):
        d['crossref_id'] = source_id
    elif source == 'arxiv' and not d.get('arxiv_id'):
        d['arxiv_id'] = source_id
    elif source == 'pubmed' and not d.get('pmid'):
        d['pmid'] = source_id
    elif source == 'pmc' and not d.get('pmcid'):
        d['pmcid'] = source_id

    return d


# ID priority chain — order matters
_ID_FIELDS = ['doi', 'pmid', 'pmcid', 'arxiv_id', 's2_id', 'openalex_id', 'crossref_id']


def _id_key(field: str, value: str | None) -> str | None:
    """Normalize an external ID value for exact matching."""
    if not value:
        return None
    v = str(value).strip().lower()
    if field == 'doi':
        return normalize_doi(v)
    if field == 'pmcid' and not v.startswith('pmc'):
        v = f'pmc{v}'
    return v if v else None


# ── Deduplication ──────────────────────────────────────────────────────────

class Deduplicator:
    """ID priority chain dedup + title fuzzy fallback + canonical merge.

    Usage:
        dedup = Deduplicator()
        unique, duplicates = dedup.deduplicate(papers)
        # Each unique paper has merged sources/source_ranks from duplicates.
    """

    def __init__(
        self,
        auto_dup_threshold: float = 0.95,
        review_dup_threshold: float = 0.90,
    ):
        self.auto_dup_threshold = auto_dup_threshold
        self.review_dup_threshold = review_dup_threshold
        self._id_index: dict[str, dict[str, int]] = {}  # field -> {id_value: paper_index}
        self._seen_titles: list[tuple[str, int]] = []  # (normalized_title, paper_index)
        self._papers: list[dict] = []

    def reset(self) -> None:
        self._id_index.clear()
        self._seen_titles.clear()
        self._papers.clear()

    def _find_by_id(self, ids: dict[str, str | None]) -> int | None:
        """Find existing paper index by any ID in priority chain."""
        for field in _ID_FIELDS:
            val = _id_key(field, ids.get(field))
            if val and field in self._id_index and val in self._id_index[field]:
                return self._id_index[field][val]
        return None

    def _index_ids(self, idx: int, ids: dict[str, str | None]) -> None:
        """Add paper's IDs to index."""
        for field in _ID_FIELDS:
            val = _id_key(field, ids.get(field))
            if val:
                self._id_index.setdefault(field, {})[val] = idx

    def _find_by_title(self, title: str | None, year: int | None, authors: list[str], unique: list[dict] | None = None) -> tuple[int | None, str | None]:
        """Find existing paper by fuzzy title match.

        Returns (paper_index, reason) or (None, None).
        """
        title_norm = normalize_title(title)
        if not title_norm:
            return None, None

        search_list = unique if unique is not None else self._papers

        for existing_title, idx in self._seen_titles:
            sim = _jaro_winkler_similarity(title_norm, existing_title)
            if sim >= self.auto_dup_threshold:
                return idx, f"title_auto:{sim:.3f}"
            if sim >= self.review_dup_threshold:
                if not search_list or idx >= len(search_list):
                    continue
                existing = search_list[idx]
                if year and existing.get('year') and year == existing.get('year'):
                    return idx, f"title_year:{sim:.3f}"
                if authors and existing.get('authors'):
                    a1 = (authors[0] or '').lower().strip()
                    a2 = (existing['authors'][0] or '').lower().strip()
                    if a1 and a2 and a1 == a2:
                        return idx, f"title_author:{sim:.3f}"
        return None, None

    def _merge_sources(self, canonical: dict, duplicate: dict) -> None:
        """Merge duplicate's source info into canonical record."""
        dup_source = duplicate.get('source', '')
        if dup_source and dup_source not in canonical.get('sources', []):
            canonical.setdefault('sources', []).append(dup_source)

        # Merge source_ranks
        dup_rank = duplicate.get('source_rank')
        if dup_source and dup_rank is not None:
            canonical.setdefault('source_ranks', {})[dup_source] = dup_rank

    def deduplicate(
        self,
        papers: list[dict[str, Any]],
        id_key: str = "id",
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Deduplicate papers using ID priority chain + title fuzzy.

        Returns (unique_papers, duplicate_papers).
        Unique papers have merged sources/source_ranks from all duplicates.
        """
        self.reset()
        unique: list[dict] = []
        duplicates: list[dict] = []

        for i, paper in enumerate(papers):
            ids = extract_ids(paper)
            title = paper.get('title')
            year = paper.get('year')
            authors = paper.get('authors', [])

            # Stage 1: ID exact match (priority chain)
            match_idx = self._find_by_id(ids)

            # Stage 2: Title fuzzy fallback
            if match_idx is None:
                match_idx, reason = self._find_by_title(title, year, authors, unique)
            else:
                reason = f"id_match:{ids.get('doi') or ids.get('pmid') or 'id'}"

            if match_idx is not None:
                # Duplicate — merge into canonical
                paper_copy = dict(paper)
                paper_copy["_dup_reason"] = reason or "id_match"
                duplicates.append(paper_copy)
                self._merge_sources(unique[match_idx], paper)
                log.debug("Duplicate: %s → %s", paper.get(id_key, str(i)), reason)
            else:
                # Unique — add to index
                idx = len(unique)
                unique.append(paper)
                self._index_ids(idx, ids)
                title_norm = normalize_title(title)
                if title_norm:
                    self._seen_titles.append((title_norm, idx))

        log.info(
            "Dedup: %d total → %d unique, %d duplicates (%.1f%% removed)",
            len(papers), len(unique), len(duplicates),
            len(duplicates) / max(len(papers), 1) * 100,
        )
        return unique, duplicates


def deduplicate(
    papers: list[dict[str, Any]],
    id_key: str = "id",
    auto_dup_threshold: float = 0.95,
    review_dup_threshold: float = 0.90,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Shortcut function."""
    dedup = Deduplicator(auto_dup_threshold=auto_dup_threshold, review_dup_threshold=review_dup_threshold)
    return dedup.deduplicate(papers, id_key=id_key)


# ── PRISMA statistics ──────────────────────────────────────────────────────

class PRISMAStats:
    """Collect PRISMA flow numbers throughout the SLR pipeline."""

    def __init__(self):
        self.records_identified = 0           # total raw fetched
        self.duplicates_removed = 0           # after dedup
        self.records_screened = 0             # after dedup, before relevance filter
        self.records_excluded_title = 0       # filtered by relevance/keyword
        self.abstracts_assessed = 0           # papers with abstracts sent to LLM
        self.abstracts_excluded = 0           # LLM rejected
        self.full_texts_sought = 0            # papers with pdf_url
        self.full_texts_not_retrieved = 0     # pdf_url but not accessible
        self.full_texts_assessed = 0
        self.full_texts_excluded = 0
        self.studies_included = 0             # final selected

    def to_dict(self) -> dict:
        return {
            "records_identified": self.records_identified,
            "duplicates_removed": self.duplicates_removed,
            "records_screened": self.records_screened,
            "records_excluded_by_title": self.records_excluded_title,
            "abstracts_assessed": self.abstracts_assessed,
            "abstracts_excluded": self.abstracts_excluded,
            "full_texts_sought": self.full_texts_sought,
            "full_texts_not_retrieved": self.full_texts_not_retrieved,
            "full_texts_assessed": self.full_texts_assessed,
            "full_texts_excluded": self.full_texts_excluded,
            "studies_included": self.studies_included,
        }


# ── Jaro-Winkler via rapidfuzz ─────────────────────────────────────────────

def _jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity via rapidfuzz, fallback ke pure Python."""
    try:
        from rapidfuzz.distance import JaroWinkler
        return JaroWinkler.normalized_similarity(s1, s2)  # type: ignore[no-any-return]
    except ImportError:
        return _jaro_winkler_pure(s1, s2)


def _jaro_winkler_pure(s1: str, s2: str) -> float:
    """Pure Python Jaro-Winkler implementation — fallback."""
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

    prefix = 0
    for i in range(min(4, len_s1, len_s2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * 0.1 * (1.0 - jaro)


# ── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test DOI normalization
    assert normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
    assert normalize_doi("10.1234/XYZ") == "10.1234/xyz"
    assert normalize_doi(None) is None

    # Test title normalization
    assert normalize_title("The Great Paper") == "great paper"
    assert normalize_title("  A Study of ML  ") == "study of ml"

    # Test ID priority chain
    papers = [
        {"id": "1", "doi": "10.1000/abc", "title": "Machine Learning for SLR", "source": "openalex", "source_id": "W123", "openalex_id": "W123", "year": 2023, "authors": ["Alice"]},
        {"id": "2", "doi": "10.1000/abc", "title": "Machine Learning for SLR", "source": "crossref", "source_id": "CR456", "crossref_id": "CR456", "year": 2023, "authors": ["Alice"]},  # DOI dup
        {"id": "3", "doi": "10.1000/xyz", "title": "Machine Learning for SLR", "source": "semantic_scholar", "source_id": "S789", "s2_id": "S789", "year": 2023, "authors": ["Alice"]},  # Title dup
        {"id": "4", "doi": None, "title": "Machine Learning for Systematic Lit Review", "source": "pubmed", "source_id": "PM1", "pmid": "PM1", "year": 2023, "authors": ["Bob"]},  # Similar title
        {"id": "5", "doi": "10.1000/new", "title": "Completely Different Topic", "source": "arxiv", "source_id": "2401.001", "arxiv_id": "2401.001", "year": 2024, "authors": ["Charlie"]},  # Unique
    ]

    dedup = Deduplicator()
    unique, dups = dedup.deduplicate(papers)

    print(f"Unique: {len(unique)}")
    for p in unique:
        print(f"  {p['id']}: {p['title'][:50]}  sources={p.get('sources', [])}")
    print(f"\nDuplicates: {len(dups)}")
    for p in dups:
        print(f"  {p['id']}: {p.get('_dup_reason', '?')}")

    assert len(unique) == 2, f"Expected 2 unique, got {len(unique)}"
    assert len(dups) == 3, f"Expected 3 duplicates, got {len(dups)}"
    # Canonical paper should have merged sources
    assert "crossref" in unique[0].get("sources", []), f"Canonical missing crossref source: {unique[0].get('sources')}"
    assert "semantic_scholar" in unique[0].get("sources", []), f"Canonical missing S2 source: {unique[0].get('sources')}"
    assert "pubmed" in unique[0].get("sources", []), f"Canonical missing pubmed source: {unique[0].get('sources')}"

    # Test PRISMA
    prisma = PRISMAStats()
    prisma.records_identified = 500
    prisma.duplicates_removed = 100
    prisma.records_screened = 400
    prisma.studies_included = 50
    d = prisma.to_dict()
    assert d["records_identified"] == 500
    assert d["studies_included"] == 50

    print("\n✓ All dedup + canonical + PRISMA tests passed")
