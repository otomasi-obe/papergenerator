"""Citation Snowballing: forward + backward via OpenAlex & Semantic Scholar.

Mengambil top-N paper dari hasil SLR, lalu:
- Backward: cari paper yang DIRUJUK oleh seed papers (references)
- Forward: cari paper yang MERUJUK seed papers (cited-by)
- Score semua dengan similarity terhadap query → merge ke hasil utama

Benchmark: Connected Papers / Litmaps menggunakan pendekatan ini,
meningkatkan recall 15-30% untuk paper yang miss dari keyword search.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Sequence
from urllib.parse import quote, urlencode

import httpx

from .paper import Paper

log = logging.getLogger(__name__)

# ── Rate limiting ──
_snowball_lock = threading.Lock()
_snowball_delay = 0.8  # 1.25 req/s

# ── OpenAlex base ──
_OPENALEX_BASE = "https://api.openalex.org"
_OPENALEX_MAILTO = "mailto:rofiqcp@gmail.com"


def _rate_limit():
    with _snowball_lock:
        time.sleep(_snowball_delay)


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def _openalex_find_work(doi: str, title: str) -> dict | None:
    """Cari OpenAlex work by DOI + title fallback.

    OpenAlex kadang punya DOI berbeda dari yang disimpan di DB.
    Strategy: DOI dulu → kalau tidak ketemu, cari by title.
    """
    _rate_limit()

    with httpx.Client(timeout=httpx.Timeout(20)) as client:
        # Strategy 1: filter by DOI (exact match)
        if doi and doi.strip():
            params = {
                "filter": f"doi:{doi}",
                "select": "id,doi,title,referenced_works,cited_by_count",
                "mailto": _OPENALEX_MAILTO,
            }
            r = client.get(
                f"{_OPENALEX_BASE}/works",
                params=params,
                headers={"User-Agent": "Papergenerator/3.0"},
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    return results[0]

        # Strategy 2: search by title
        if title and title.strip():
            params = {
                "search": title[:200],
                "per_page": 5,
                "sort": "relevance_score:desc",
                "select": "id,doi,title,referenced_works,cited_by_count",
                "mailto": _OPENALEX_MAILTO,
            }
            r = client.get(
                f"{_OPENALEX_BASE}/works",
                params=params,
                headers={"User-Agent": "Papergenerator/3.0"},
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    # Cari yang judul paling cocok
                    norm = _normalize_title(title)
                    for w in results:
                        w_norm = _normalize_title(w.get("title", ""))
                        if norm[:30] in w_norm or w_norm[:30] in norm:
                            return w
                    # Fallback: ambil result pertama
                    return results[0]

    return None


def _openalex_references(seed_title: str, seed_doi: str, limit: int = 20) -> list[Paper]:
    """Ambil papers yang DIRUJUK oleh seed paper (backward snowball)."""
    work = _openalex_find_work(seed_doi, seed_title)
    if not work:
        return []

    ref_urls = work.get("referenced_works", [])[: limit * 2]
    if not ref_urls:
        return []

    results = []
    ref_ids = [u.split("/")[-1] for u in ref_urls[:limit]]

    # Batch fetch per 50 IDs
    for batch_start in range(0, len(ref_ids), 50):
        batch = ref_ids[batch_start:batch_start + 50]
        _rate_limit()

        with httpx.Client(timeout=httpx.Timeout(20)) as client:
            params = {
                "filter": f"openalex_id:{'|'.join(batch)}",
                "select": "id,doi,title,authorships,publication_year,"
                          "primary_location,type,open_access,publication_date",
                "per_page": min(len(batch), limit),
                "mailto": _OPENALEX_MAILTO,
            }
            r = client.get(
                f"{_OPENALEX_BASE}/works",
                params=params,
                headers={"User-Agent": "Papergenerator/3.0"},
            )
            if r.status_code == 200:
                for w in r.json().get("results", []):
                    p = _openalex_result_to_paper(w, direction="backward")
                    if p.title:
                        results.append(p)

    return results


def _openalex_cited_by(seed_title: str, seed_doi: str, limit: int = 20) -> list[Paper]:
    """Ambil papers yang MERUJUK seed paper (forward snowball)."""
    work = _openalex_find_work(seed_doi, seed_title)
    if not work:
        return []

    # OpenAlex ID untuk cites filter
    oa_id = work.get("id")
    if not oa_id:
        oa_id = quote(work.get("doi", ""), safe="")

    # Cari papers yang citing work ini
    oa_short = oa_id.split("/")[-1]
    _rate_limit()

    with httpx.Client(timeout=httpx.Timeout(20)) as client:
        params = {
            "filter": f"cites:{oa_short}",
            "select": "id,doi,title,authorships,publication_year,"
                      "primary_location,type,open_access,publication_date",
            "per_page": limit,
            "sort": "cited_by_count:desc",
            "mailto": _OPENALEX_MAILTO,
        }
        r = client.get(
            f"{_OPENALEX_BASE}/works",
            params=params,
            headers={"User-Agent": "Papergenerator/3.0"},
        )
        if r.status_code == 200:
            return [
                _openalex_result_to_paper(w, direction="forward")
                for w in r.json().get("results", [])
                if w.get("title")
            ]

    return []


def _semantic_scholar_citations(doi: str, limit: int = 20) -> list[Paper]:
    """Ambil citations + references dari Semantic Scholar."""
    _rate_limit()

    try:
        with httpx.Client(timeout=httpx.Timeout(15)) as client:
            url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi, safe='')}"
            params = {
                "fields": "citations.title,citations.authors,citations.year,"
                          "citations.abstract,citations.citationCount,"
                          "citations.externalIds,citations.url,"
                          "references.title,references.authors,references.year,"
                          "references.abstract,references.citationCount,"
                          "references.externalIds,references.url",
                "limit": limit,
            }
            r = client.get(url, params=params)
            if r.status_code != 200:
                return []

            data = r.json()
            results = []

            for cite in data.get("citations", [])[:limit]:
                eid = cite.get("externalIds") or {}
                results.append(Paper(
                    source="snowball-forward",
                    source_id=eid.get("DOI", ""),
                    title=cite.get("title", ""),
                    authors=[a.get("name", "") for a in cite.get("authors", [])],
                    year=cite.get("year"),
                    abstract=cite.get("abstract", ""),
                    citations=cite.get("citationCount", 0),
                    doi=eid.get("DOI", ""),
                    url=cite.get("url", ""),
                ))

            for ref in data.get("references", [])[:limit]:
                eid = ref.get("externalIds") or {}
                results.append(Paper(
                    source="snowball-backward",
                    source_id=eid.get("DOI", ""),
                    title=ref.get("title", ""),
                    authors=[a.get("name", "") for a in ref.get("authors", [])],
                    year=ref.get("year"),
                    abstract=ref.get("abstract", ""),
                    citations=ref.get("citationCount", 0),
                    doi=eid.get("DOI", ""),
                    url=ref.get("url", ""),
                ))

            return results
    except Exception as e:
        log.warning("snowball_s2(doi=%s): %s", doi, e)
        return []


def _openalex_result_to_paper(w: dict, direction: str = "") -> Paper:
    """Konversi OpenAlex API result → Paper."""
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    date = w.get("publication_date", "") or ""

    abstract = ""
    if inv := w.get("abstract_inverted_index"):
        word_positions = []
        for word, positions in inv.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        abstract = " ".join(w for _, w in word_positions)

    authors = []
    for a in w.get("authorships", []) or []:
        auth_info = a.get("author") or {}
        name = auth_info.get("display_name", "")
        if name:
            authors.append(name)

    doi = (w.get("doi", "") or "").replace("https://doi.org/", "")
    year = int(date[:4]) if date and len(date) >= 4 else None

    return Paper(
        title=w.get("title", ""),
        source=f"snowball-{direction}" if direction else "snowball",
        source_id=w.get("id", "").split("/")[-1] if w.get("id") else doi or "",
        authors=authors,
        year=year,
        venue=src.get("display_name", ""),
        publisher=src.get("publisher", ""),
        doi=doi,
        url=loc.get("landing_page_url", w.get("doi", "")),
        pdf_url=(loc.get("pdf_url") or ""),
        abstract=abstract,
        citations=w.get("cited_by_count") or 0,
        venue_type=w.get("type", ""),
        is_open_access=bool(w.get("open_access", {}).get("is_oa", False)),
    )


def snowball(
    seed_papers: Sequence[Paper],
    query: str,
    top_n_seeds: int = 10,
    max_per_seed: int = 10,
    max_total: int = 100,
) -> list[Paper]:
    """Forward + backward citation snowballing dari seed papers.

    Args:
        seed_papers: Top-N papers dari SLR utama (diurut relevance)
        query: Query SLR untuk scoring similarity
        top_n_seeds: Berapa seed paper yang dipakai
        max_per_seed: Max hasil per seed per arah
        max_total: Batas total snowball results

    Returns:
        List unik Paper yang ditemukan via citation chaining (sudah di-score).
    """
    seeds = list(seed_papers)[:top_n_seeds]
    if not seeds:
        return []

    log.info("snowball: starting with %d seeds, query=%s", len(seeds), query[:60])

    all_found: list[Paper] = []
    seen_titles: set[str] = set()
    seen_dois: set[str] = set()

    for s in seeds:
        if s.title:
            seen_titles.add(_normalize_title(s.title))
        if s.doi:
            seen_dois.add(s.doi.lower())

    for seed in seeds:
        if not seed.title:
            continue

        # OpenAlex: backward + forward
        refs = _openalex_references(seed.title, seed.doi or "", limit=max_per_seed)
        cites = _openalex_cited_by(seed.title, seed.doi or "", limit=max_per_seed)

        for p in refs + cites:
            norm = _normalize_title(p.title)
            doi_lower = (p.doi or "").lower()
            if norm not in seen_titles and doi_lower not in seen_dois:
                seen_titles.add(norm)
                if doi_lower:
                    seen_dois.add(doi_lower)
                all_found.append(p)

        if len(all_found) >= max_total:
            break

    # Semantic Scholar supplemental
    remaining = max_total - len(all_found)
    if remaining > 0 and seeds[0].doi:
        s2_results = _semantic_scholar_citations(seeds[0].doi, limit=min(remaining, 20))
        for p in s2_results:
            norm = _normalize_title(p.title)
            doi_lower = (p.doi or "").lower()
            if norm not in seen_titles and doi_lower not in seen_dois:
                seen_titles.add(norm)
                if doi_lower:
                    seen_dois.add(doi_lower)
                all_found.append(p)

    # Score similarity terhadap query
    try:
        from .scoring import score_papers
        scored = score_papers(query, all_found)
        all_found = [sp.paper for sp in scored]
        log.info("snowball: scored %d papers via SBERT/TF-IDF", len(all_found))
    except Exception as e:
        log.warning("snowball: scoring failed (%s), keeping raw order", e)

    log.info("snowball: found %d unique papers from %d seeds", len(all_found), len(seeds))
    return all_found[:max_total]