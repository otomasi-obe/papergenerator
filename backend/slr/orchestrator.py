"""Orchestrator multi-source SLR.

Strategi baru sesuai brief:

1. Tahap 1 — `fetch_titles()` panggil semua source (max 10 worker pool) hanya
   untuk dapat metadata ringan: title, authors, year, doi, source, venue,
   citations, abstract (kalau gratis di-include source langsung). Maks 60 hasil
   per source, lalu dedup global by DOI/title-normalized.
2. Topic-aware source selection: kalau topic terdeteksi medical → europepmc
   diprioritaskan, kalau IT/CS → ieee/dblp/arxiv. Source yang tidak match topic
   tetap dipanggil tapi dengan limit lebih kecil (signal pelengkap).
3. Hasil siap dirank di pipeline.py dengan kombinasi citation+recency+SBERT
   tanpa perlu fetch detail tambahan dulu.

Modul ini cuma menangani fetching + dedup. Ranking + summarization tetap di
pipeline.py / scoring.py / summarizer.py.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from .fetchers import ALL, SOURCE_TOPICS
from .http_client import get_client
from .paper import Paper

log = logging.getLogger(__name__)

PREDATORY_PUBLISHERS = {
    "omics",
    "scirp",
    "scientific research publishing",
    "academic journals",
    "david publishing",
    "academic and scientific publishing",
    "bentham science",
}

MAX_WORKERS = 10
DEFAULT_LIMIT_PER_SOURCE = 60


_TOPIC_KEYWORDS = {
    "medical": (
        "medic",
        "medis",
        "clinic",
        "klinis",
        "patient",
        "covid",
        "cancer",
        "drug",
        "obat",
        "pharma",
        "therapy",
        "disease",
        "penyakit",
        "diagnosis",
        "kesehatan",
        "kedokteran",
    ),
    "biology": ("biolog", "gene", "protein", "cell", "neuron"),
    "cs": (
        "software",
        "algorit",
        "programming",
        "compiler",
        "database",
        "system",
        "network",
        "cloud",
        "distributed",
        "kernel",
        "komputer",
        "informatika",
    ),
    "ai": (
        "machine learning",
        "deep learning",
        "neural",
        "ml",
        "ai",
        "lstm",
        "transformer",
        "nlp",
        "computer vision",
        "agent",
        "reinforcement",
        "kecerdasan buatan",
        "pembelajaran mesin",
        "pembelajaran mendalam",
    ),
    "engineering": (
        "engineering",
        "control",
        "robot",
        "iot",
        "embedded",
        "signal",
        "circuit",
        "rangkaian",
        "teknik elektro",
        "teknik",
        "rekayasa",
        "elektronika",
        "mesin",
    ),
    "physics": ("physics", "quantum", "particle", "astro"),
    "indonesia": (
        "indonesia",
        "sinta",
        "garuda",
        "kemdikbud",
        "lokal",
        "akreditasi sinta",
        "lokal indonesia",
    ),
}


def _detect_topics(query: str) -> set[str]:
    q = f" {(query or '').lower().strip()} "
    found: set[str] = set()
    for topic, kws in _TOPIC_KEYWORDS.items():
        if any(f" {k.strip()} " in q for k in kws):
            found.add(topic)
    if not found:
        found.add("any")
    return found


def pick_sources_for_topic(query: str, explicit: list[str] | None = None) -> list[str]:
    """Pilih sumber yang relevan utk query. Kalau caller spesifik
    (`explicit=[…]`), dipakai apa adanya (subset dari ALL)."""
    if explicit:
        return [s for s in explicit if s in ALL]
    topics = _detect_topics(query)
    chosen = []
    for src, src_topics in SOURCE_TOPICS.items():
        if src_topics & topics or "any" in src_topics:
            chosen.append(src)
    if not chosen:
        chosen = list(ALL.keys())
    return chosen


def is_predatory(paper: Paper) -> bool:
    if not paper.publisher:
        return False
    p = paper.publisher.lower()
    return any(bad in p for bad in PREDATORY_PUBLISHERS)


_PUNCT_RE = re.compile(r"[^\w\s]")


def _norm_title(t: str | None) -> str:
    s = (t or "").lower().strip()
    s = _PUNCT_RE.sub(" ", s)
    return " ".join(s.split())


def fetch_from_source(name: str, query: str, limit: int, filters: dict | None) -> list[Paper]:
    module = ALL[name]
    with get_client() as client:
        try:
            return list(module.search(client, query, limit=limit, filters=filters))
        except Exception as e:
            log.warning("SLR fetch [%s] error: %s", name, e)
            return []


def fetch_titles(
    query: str,
    sources: list[str] | None = None,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
    filters: dict | None = None,
    max_total: int | None = None,
    skip_predatory: bool = True,
    progress_cb=None,
) -> list[Paper]:
    """Tahap 1 — panggil semua source paralel, dedup, return list[Paper].

    Sesuai algoritma user: SEARCH semua API (judul saja). Walaupun fetcher
    biasanya kembalikan abstract juga (gratis), kita simpan apa adanya — tahap
    ranking di pipeline.py akan memanfaatkannya kalau ada.
    """
    sources = sources or pick_sources_for_topic(query)
    sources = [s for s in sources if s in ALL]
    if not sources:
        return []

    workers = min(MAX_WORKERS, max(1, len(sources)))
    all_papers: list[Paper] = []

    if progress_cb:
        progress_cb("fetching", {"sources": sources, "started": 0, "total": len(sources)})

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(fetch_from_source, name, query, limit_per_source, filters): name
            for name in sources
        }
        try:
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    papers = fut.result() or []
                except Exception as e:
                    log.warning("SLR future [%s] error: %s", name, e)
                    papers = []
                completed += 1
                # progress_cb may raise to signal cancellation (e.g. slr_worker's
                # WorkerCancelled). We let it propagate so pending fetches can
                # be cancelled in the except branch below.
                if progress_cb:
                    progress_cb(
                        "source_done",
                        {
                            "source": name,
                            "count": len(papers),
                            "completed": completed,
                            "total": len(sources),
                        },
                    )
                all_papers.extend(papers)
        except BaseException:
            # Cancel any still-pending fetches before re-raising so we don't
            # leak threads stuck on slow upstream HTTP calls.
            for f in futures:
                f.cancel()
            raise

    # Round-robin per source so output isn't dominated by one fast index.
    by_source: dict[str, list[Paper]] = {}
    for p in all_papers:
        by_source.setdefault(p.source, []).append(p)

    seen_keys: set[str] = set()
    seen_titles: set[str] = set()
    results: list[Paper] = []
    # Sort sources alphabetically so round-robin merge order is deterministic
    # across runs regardless of which fetcher finished first.
    queues = [list(reversed(by_source[name])) for name in sorted(by_source.keys())]

    while queues:
        next_queues = []
        for q in queues:
            if not q:
                continue
            p = q.pop()
            key = p.dedup_key()
            title_key = _norm_title(p.title)
            if key in seen_keys:
                if q:
                    next_queues.append(q)
                continue
            if title_key and title_key in seen_titles:
                if q:
                    next_queues.append(q)
                continue
            if skip_predatory and is_predatory(p):
                if q:
                    next_queues.append(q)
                continue
            seen_keys.add(key)
            if title_key:
                seen_titles.add(title_key)
            results.append(p)
            if max_total and len(results) >= max_total:
                return results
            if q:
                next_queues.append(q)
        queues = next_queues

    if progress_cb:
        progress_cb("dedup_done", {"count": len(results)})
    return results


# Backward-compat alias used by old call sites.
fetch_all = fetch_titles
