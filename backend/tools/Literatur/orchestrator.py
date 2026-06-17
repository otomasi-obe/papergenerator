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
import time
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
        "hospital",
        "rumah sakit",
        "surgery",
        "bedah",
        "vaccine",
        "vaksin",
        "epidemiol",
        "public health",
        "mental health",
        "nutrition",
        "gizi",
        "patolog",
        "anatomy",
        "anatomi",
        "immunol",
        "cardio",
        "jantung",
    ),
    "biology": (
        "biolog",
        "gene",
        "protein",
        "cell",
        "neuron",
        "genome",
        "genom",
        "ecosystem",
        "ekosistem",
        "species",
        "spesies",
        "evolution",
        "evolusi",
        "microbio",
        "mikroba",
        "molecular",
        "molekuler",
        "bioinform",
        "biodiversity",
        "biodiversitas",
    ),
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
        "computing",
        "cyber",
        "security",
        "keamanan",
        "blockchain",
        "cryptography",
        "kriptografi",
        "web",
        "mobile",
        "operating system",
        "sistem operasi",
        "data mining",
        "tambang data",
        "big data",
        "information system",
        "sistem informasi",
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
        "artificial intelligence",
        "generative",
        "llm",
        "large language model",
        "gpt",
        "bert",
        "chatbot",
        "natural language",
        "bahasa alami",
        "image recognition",
        "pengenalan citra",
        "speech recognition",
        "pengenalan suara",
        "autonomous",
        "otonom",
        "knowledge graph",
        "expert system",
        "sistem pakar",
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
        "renewable",
        "terbarukan",
        "solar",
        "energi",
        "energy",
        "material",
        "structural",
        "infrastruktur",
        "infrastructure",
        "manufacturing",
        "manufaktur",
        "aerospace",
        "dirgantara",
        "automotive",
        "otomotif",
    ),
    "physics": (
        "physics",
        "quantum",
        "particle",
        "astro",
        "fisika",
        "optics",
        "optik",
        "thermo",
        "relativity",
        "relativitas",
        "nuclear",
        "nuklir",
        "plasma",
        "condensed matter",
    ),
    "indonesia": (
        "indonesia",
        "sinta",
        "garuda",
        "kemdikbud",
        "lokal",
        "akreditasi sinta",
        "lokal indonesia",
        "nusantara",
        "jawa",
        "sumatera",
        "kalimantan",
        "sulawesi",
    ),
    "economics": (
        "econom",
        "ekonomi",
        "finance",
        "keuangan",
        "market",
        "pasar",
        "inflation",
        "inflasi",
        "gdp",
        "pib",
        "monetary",
        "moneter",
        "fiscal",
        "fiskal",
        "banking",
        "perbankan",
        "trade",
        "perdagangan",
        "investment",
        "investasi",
        "stock",
        "saham",
        "cryptocurrency",
        "crypto",
    ),
    "social": (
        "social",
        "sosial",
        "society",
        "masyarakat",
        "culture",
        "budaya",
        "politic",
        "politik",
        "governance",
        "tata kelola",
        "democracy",
        "demokrasi",
        "gender",
        "poverty",
        "kemiskinan",
        "inequality",
        "ketimpangan",
        "migration",
        "migrasi",
        "community",
        "komunitas",
        "psycholog",
        "psikolog",
    ),
    "education": (
        "education",
        "pendidikan",
        "learning",
        "pembelajaran",
        "teaching",
        "pengajaran",
        "curriculum",
        "kurikulum",
        "school",
        "sekolah",
        "university",
        "universitas",
        "student",
        "siswa",
        "mahasiswa",
        "pedagog",
        "e-learning",
        "pembelajaran daring",
        "assessment",
        "asesmen",
        "literacy",
        "literasi",
    ),
    "law": (
        "law",
        "hukum",
        "legal",
        "regulation",
        "regulasi",
        "policy",
        "kebijakan",
        "constitutional",
        "konstitusi",
        "criminal",
        "pidana",
        "civil",
        "perdata",
        "human rights",
        "hak asasi",
        "intellectual property",
        "hak kekayaan intelektual",
        "compliance",
        "kepatuhan",
        "justice",
        "keadilan",
    ),
    "agriculture": (
        "agriculture",
        "pertanian",
        "crop",
        "tanaman",
        "farming",
        "tani",
        "food security",
        "ketahanan pangan",
        "irrigation",
        "irigasi",
        "soil",
        "tanah",
        "pest",
        "hama",
        "fertilizer",
        "pupuk",
        "agronomy",
        "agronomi",
        "livestock",
        "peternakan",
        "fishery",
        "perikanan",
        "forestry",
        "kehutanan",
    ),
}


# Indonesian → English term mapping for query expansion
_ID_TO_EN = {
    "kecerdasan buatan": "artificial intelligence",
    "pembelajaran mesin": "machine learning",
    "pembelajaran mendalam": "deep learning",
    "jaringan saraf": "neural network",
    "pengolahan bahasa alami": "natural language processing",
    "penglihatan komputer": "computer vision",
    "sistem pakar": "expert system",
    "penambangan data": "data mining",
    "keamanan siber": "cyber security",
    "komputasi awan": "cloud computing",
    "internet segala": "internet of things",
    "pembelajaran daring": "e-learning",
    "sistem informasi": "information system",
    "rekayasa perangkat lunak": "software engineering",
    "kesehatan masyarakat": "public health",
    "ketahanan pangan": "food security",
    "energi terbarukan": "renewable energy",
    "perubahan iklim": "climate change",
    "pembangunan berkelanjutan": "sustainable development",
    "hak asasi manusia": "human rights",
    "kebijakan publik": "public policy",
}

# Common academic synonym expansion (English → additional terms)
_SYNONYMS = {
    "machine learning": "ml",
    "deep learning": "dl",
    "natural language processing": "nlp",
    "artificial intelligence": "ai",
    "internet of things": "iot",
    "cloud computing": "cloud",
    "data mining": "knowledge discovery",
    "neural network": "neural net",
    "computer vision": "image recognition",
    "reinforcement learning": "rl",
    "software engineering": "software development",
    "information retrieval": "search",
    "sentiment analysis": "opinion mining",
    "image classification": "image recognition",
    "object detection": "object recognition",
    "climate change": "global warming",
    "renewable energy": "green energy",
    "sustainable development": "sustainability",
    "public health": "epidemiology",
    "mental health": "psychological well-being",
}


def expand_query(query: str) -> str:
    """Expand a search query with Indonesian→English translations and synonyms.

    - Detects Indonesian terms and adds English equivalents.
    - Adds common synonyms for academic terms.
    - Preserves existing boolean operators (AND, OR) if user already used them.
    - Returns expanded query string suitable for academic search APIs.
    """
    if not query or not query.strip():
        return query

    q_lower = query.lower().strip()

    # If user already uses boolean operators, respect their structure
    has_booleans = bool(re.search(r'\b(AND|OR|NOT)\b', query))

    terms_added: list[str] = []

    # Indonesian → English translation
    for id_term, en_term in _ID_TO_EN.items():
        if id_term in q_lower and en_term not in q_lower:
            terms_added.append(en_term)

    # Synonym expansion
    for base_term, syn in _SYNONYMS.items():
        if base_term in q_lower and syn not in q_lower:
            terms_added.append(syn)

    # Reverse synonym lookup (if user typed the short form, add the full form)
    for base_term, syn in _SYNONYMS.items():
        if syn in q_lower and base_term not in q_lower:
            terms_added.append(base_term)

    if not terms_added:
        return query

    if has_booleans:
        # Append with OR to broaden results without breaking user's boolean logic
        expansion = " OR ".join(terms_added)
        return f"({query}) OR ({expansion})"
    else:
        # Simple space-separated append — most academic APIs treat spaces as AND
        return f"{query} {' '.join(terms_added)}"


def _detect_topics(query: str) -> set[str]:
    q = f" {(query or '').lower().strip()} "
    found: set[str] = set()
    for topic, kws in _TOPIC_KEYWORDS.items():
        if any(f" {k.strip()} " in q for k in kws):
            found.add(topic)
    # Also check partial matches for longer keywords
    q_stripped = (query or "").lower().strip()
    for topic, kws in _TOPIC_KEYWORDS.items():
        if topic in found:
            continue
        for k in kws:
            k_stripped = k.strip()
            if len(k_stripped) >= 5 and k_stripped in q_stripped:
                found.add(topic)
                break
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
    """Normalize title for dedup — same algorithm as db_cache.normalize_title."""
    s = (t or "").lower().strip()
    # Match db_cache.normalize_title: strip all non-alphanumeric
    return re.sub(r'[^a-z0-9]+', '', s)


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
    source_save_cb=None,
    use_cache: bool = True,
) -> list[Paper]:
    """Tahap 1 — DB FIRST, lalu API kalau kurang.

    Redesign (2026-06-17):
    1. Check DB cache for target papers. If enough → skip API entirely (<1s).
    2. If DB insufficient → fetch APIs in parallel with:
       - Global timeout: 15 min hard stop
       - Per-fetcher timeout: 30 s without results = skip
       - Early stop: target reached → stop fetching
    3. Dedup (round-robin across sources).

    source_save_cb: Callable[[list[Paper]], None] — called per-source after
    fetch for streaming save to DB (API path only).

    use_cache: If True, check DB first before fetching from API.
    """
    from . import db_cache

    sources = sources or pick_sources_for_topic(query)
    sources = [s for s in sources if s in ALL]
    if not sources:
        return []

    # Expand query with Indonesian→English translations and synonyms
    expanded = expand_query(query)
    if expanded != query:
        log.debug("Query expanded: %r → %r", query, expanded)

    # Target: how many papers we want for scoring (passed as max_total)
    target = max_total or limit_per_source * len(sources)
    new_papers_count = 0  # tracks API-fetched papers (0 in DB-only path)

    # ── Step 1: DB FIRST ─────────────────────────────────────────────────
    cached_papers: list[Paper] = []
    if use_cache:
        try:
            cached_papers = db_cache.search_papers(
                query=expanded,
                limit=target * 2,  # fetch extra for dedup headroom
                sources=sources,
            )
            log.info("Cache hit: %d papers from DB (target=%d)", len(cached_papers), target)
        except Exception as e:
            log.warning("DB cache lookup failed: %s", e)
            cached_papers = []

    # Enough from DB → SKIP API entirely
    if len(cached_papers) >= target:
        log.info(
            "DB has enough papers (%d >= %d), skipping API fetch",
            len(cached_papers), target,
        )
        if progress_cb:
            progress_cb("fetching", {
                "sources": sources, "started": 0, "total": len(sources),
                "from_cache": True,
            })

        all_papers = list(cached_papers)
        # DB path: no source_save_cb needed (papers already in DB cache)
        # Dedup + save_cb in pipeline still run normally
    else:
        # ── Step 2: API FETCH (DB insufficient) ──────────────────────────
        GLOBAL_TIMEOUT = 180  # 3 min hard stop
        PER_FETCHER_TIMEOUT = 30  # 30 s per source

        api_start = time.time()
        deadline = api_start + GLOBAL_TIMEOUT

        workers = min(MAX_WORKERS, max(1, len(sources)))
        all_papers = list(cached_papers)  # start with cached
        completed = 0
        new_papers_count = 0
        timed_out_sources: list[str] = []
        error_sources: list[str] = []

        if progress_cb:
            progress_cb("fetching", {
                "sources": sources, "started": 0, "total": len(sources),
            })

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(
                    fetch_from_source, name, expanded, limit_per_source, filters
                ): name
                for name in sources
            }

            try:
                while True:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        log.warning("SLR global timeout reached, stopping fetch")
                        break

                    pending = [f for f in futures if not f.done()]
                    if not pending:
                        break  # all done

                    try:
                        batch = list(as_completed(
                            pending,
                            timeout=min(remaining, PER_FETCHER_TIMEOUT),
                        ))
                    except (TimeoutError, Exception) as e:
                        # Python 3.10: concurrent.futures.TimeoutError ≠ TimeoutError
                        # Catch both to handle per-fetcher timeout
                        if "TimeoutError" not in type(e).__name__ and not isinstance(e, TimeoutError):
                            raise
                        # Per-fetcher timeout: cancel slow sources
                        still_pending = [f for f in futures if not f.done()]
                        for f in still_pending:
                            src = futures[f]
                            f.cancel()
                            timed_out_sources.append(src)
                            log.warning(
                                "SLR fetch [%s] timed out after %ds, skipping",
                                src, PER_FETCHER_TIMEOUT,
                            )
                        # BUG-6.1: continue collecting from completed futures
                        # instead of breaking out of the entire loop
                        continue

                    for fut in batch:
                        name = futures[fut]
                        try:
                            papers = fut.result(timeout=0) or []
                        except TimeoutError:
                            timed_out_sources.append(name)
                            log.warning("SLR fetch [%s] timed out, skipping", name)
                            continue
                        except Exception as e:
                            error_sources.append(name)
                            log.warning("SLR future [%s] error: %s", name, e)
                            papers = []

                        completed += 1
                        new_papers_count += len(papers)

                        if progress_cb:
                            progress_cb("source_done", {
                                "source": name,
                                "count": len(papers),
                                "completed": completed,
                                "total": len(sources),
                            })

                        if source_save_cb and papers:
                            try:
                                source_save_cb(papers)
                            except Exception as e:
                                log.warning(
                                    "slr.source_save_cb failed for %s: %s",
                                    name, e,
                                )

                        all_papers.extend(papers)

                        # Early stop: enough papers collected
                        if target and len(all_papers) >= target:
                            log.info(
                                "Early stop: %d papers >= target %d",
                                len(all_papers), target,
                            )
                            for f in futures:
                                if not f.done():
                                    f.cancel()
                            break
                    else:
                        continue  # inner for completed normally → next while iter
                    break  # inner for broke (early stop) → exit while

            except BaseException:
                for f in futures:
                    f.cancel()
                raise

        elapsed = time.time() - api_start
        log.info(
            "SLR API fetch done: %d new papers, %d completed, "
            "%d timed out, %d errors in %.1fs",
            new_papers_count, completed,
            len(timed_out_sources), len(error_sources), elapsed,
        )

    # ── Step 3: Dedup + round-robin ──────────────────────────────────────
    by_source: dict[str, list[Paper]] = {}
    for p in all_papers:
        by_source.setdefault(p.source, []).append(p)

    seen_keys: set[str] = set()
    seen_titles: set[str] = set()
    results: list[Paper] = []
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
                break
            if q:
                next_queues.append(q)
        queues = next_queues

    if progress_cb:
        progress_cb("dedup_done", {"count": len(results)})

    # ── Step 4: Save new papers to DB cache (API path only) ──────────────
    if use_cache and new_papers_count > 0:
        try:
            saved = db_cache.save_papers(results, source=None)
            log.info("Saved %d papers to DB cache", saved)
        except Exception as e:
            log.warning("Failed to save papers to DB: %s", e)

    # ── Step 5: Complete SLR job ─────────────────────────────────────────
    # job tracking removed from fetch_titles — handled by pipeline/worker

    # Post-sort by year desc (newest first) after relevance fetch
    results.sort(key=lambda p: p.year or 0, reverse=True)

    return results



# Backward-compat alias used by old call sites.
fetch_all = fetch_titles
