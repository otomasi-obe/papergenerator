"""
SLR (Systematic Literature Review) blueprint — searches multiple OA paper
indexes in parallel, deduplicates by DOI/title, ranks by citation count and
recency, returns up to 30 candidates. Cached per (paper_id, topic) into
project_memory so the same chat doesn't re-fetch.

Endpoints
---------
POST /api/papers/<paper_id>/slr
    body: {topic: str, limit: int=30, refresh: bool=false}
    Returns: {results: [...], sources_used: [...], sources_failed: [...], cached: bool}

Sources (graceful skip on failure):
- OpenAlex      — https://api.openalex.org/works
- DOAJ          — https://doaj.org/api/search/articles/
- Crossref      — https://api.crossref.org/works
- Semantic Schl — https://api.semanticscholar.org/graph/v1/paper/search

SSRF hardening: every outbound request goes through ALLOWED_HOSTS allowlist.
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from models import Paper, ProjectMemory, db
from paper_utils import PAPER_ID_RE


log = logging.getLogger(__name__)
slr_bp = Blueprint("slr", __name__, url_prefix="/api/papers")


# ── SSRF allowlist (only these hosts get outbound HTTP from SLR) ────────────
ALLOWED_HOSTS = {
    "api.openalex.org",
    "doaj.org",
    "api.crossref.org",
    "api.semanticscholar.org",
}


def _safe_get(url: str, *, params: dict | None = None, timeout: int = 15) -> dict | None:
    """Outbound GET that refuses any host outside ALLOWED_HOSTS and any
    non-https scheme (cheap defense-in-depth)."""
    try:
        u = urlparse(url)
        if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
            log.warning("slr.refuse_url", extra={"url": url})
            return None
        r = requests.get(
            url, params=params, timeout=timeout,
            headers={"User-Agent": "PaperFull-SLR/1.0 (mailto:admin@paperfull.app)"},
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        log.info("slr.fetch_failed", extra={"url": url, "err": str(e)})
        return None


# ── Per-source adapters: each returns list[dict] with normalized shape ──────
def _norm(*, title, authors, year, doi, url, abstract, citations, source, venue=""):
    return {
        "title": (title or "").strip(),
        "authors": authors or [],
        "year": int(year) if year else None,
        "doi": (doi or "").strip().lower() or None,
        "url": url or "",
        "abstract": (abstract or "")[:1500],
        "citations": int(citations or 0),
        "source": source,
        "venue": (venue or "")[:240],
    }


def fetch_openalex(topic: str, limit: int = 25):
    data = _safe_get(
        "https://api.openalex.org/works",
        params={"search": topic, "per-page": limit, "sort": "relevance_score:desc"},
    )
    if not data:
        return []
    out = []
    for w in (data.get("results") or [])[:limit]:
        title = w.get("title") or w.get("display_name")
        doi = (w.get("doi") or "").replace("https://doi.org/", "")
        url = (w.get("doi") and f"https://doi.org/{doi}") or w.get("id") or ""
        abstract_inv = w.get("abstract_inverted_index") or {}
        abstract = ""
        if abstract_inv:
            # Reverse the inverted index (OpenAlex format) to a plain string.
            positions = []
            for word, idxs in abstract_inv.items():
                for i in idxs:
                    positions.append((i, word))
            positions.sort()
            abstract = " ".join(w for _, w in positions[:300])
        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])
        ][:8]
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
        out.append(_norm(
            title=title, authors=authors, year=w.get("publication_year"),
            doi=doi, url=url, abstract=abstract,
            citations=w.get("cited_by_count", 0),
            source="openalex", venue=venue,
        ))
    return out


def fetch_doaj(topic: str, limit: int = 20):
    safe_topic = requests.utils.quote(topic, safe="")
    data = _safe_get(
        f"https://doaj.org/api/search/articles/{safe_topic}",
        params={"pageSize": min(limit, 50)},
    )
    if not data:
        return []
    out = []
    for item in (data.get("results") or [])[:limit]:
        b = item.get("bibjson") or {}
        title = b.get("title")
        year = b.get("year")
        doi = ""
        url = ""
        for ident in (b.get("identifier") or []):
            if (ident.get("type") or "").lower() == "doi":
                doi = ident.get("id", "")
        for link in (b.get("link") or []):
            if (link.get("type") or "").lower() == "fulltext":
                url = link.get("url", "")
                break
        venue = (b.get("journal") or {}).get("title", "")
        authors = [a.get("name", "") for a in (b.get("author") or [])][:8]
        out.append(_norm(
            title=title, authors=authors, year=year,
            doi=doi, url=url or (doi and f"https://doi.org/{doi}") or "",
            abstract=b.get("abstract", ""),
            citations=0, source="doaj", venue=venue,
        ))
    return out


def fetch_crossref(topic: str, limit: int = 20):
    data = _safe_get(
        "https://api.crossref.org/works",
        params={"query": topic, "rows": limit, "select": "title,author,issued,DOI,URL,container-title,abstract,is-referenced-by-count"},
    )
    if not data:
        return []
    out = []
    for it in ((data.get("message") or {}).get("items") or [])[:limit]:
        title = (it.get("title") or [""])[0]
        authors = [
            f"{(a.get('given') or '').strip()} {(a.get('family') or '').strip()}".strip()
            for a in (it.get("author") or [])
        ][:8]
        issued = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
        year = issued[0] if issued else None
        venue = (it.get("container-title") or [""])[0]
        out.append(_norm(
            title=title, authors=authors, year=year,
            doi=it.get("DOI"), url=it.get("URL"),
            abstract=re.sub(r"<[^>]+>", " ", it.get("abstract") or ""),
            citations=it.get("is-referenced-by-count", 0),
            source="crossref", venue=venue,
        ))
    return out


def fetch_semantic_scholar(topic: str, limit: int = 20):
    data = _safe_get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": topic, "limit": min(limit, 50),
            "fields": "title,authors,year,externalIds,abstract,citationCount,venue,url",
        },
    )
    if not data:
        return []
    out = []
    for w in (data.get("data") or [])[:limit]:
        ext = w.get("externalIds") or {}
        doi = ext.get("DOI") or ""
        out.append(_norm(
            title=w.get("title"),
            authors=[a.get("name", "") for a in (w.get("authors") or [])][:8],
            year=w.get("year"),
            doi=doi,
            url=w.get("url") or (doi and f"https://doi.org/{doi}") or "",
            abstract=w.get("abstract") or "",
            citations=w.get("citationCount", 0),
            source="semantic_scholar", venue=w.get("venue", ""),
        ))
    return out


SOURCES = [
    ("openalex", fetch_openalex),
    ("doaj", fetch_doaj),
    ("crossref", fetch_crossref),
    ("semantic_scholar", fetch_semantic_scholar),
]


def _dedupe_and_rank(buckets: list[list[dict]], limit: int) -> list[dict]:
    seen_doi: dict[str, dict] = {}
    seen_title: dict[str, dict] = {}
    flat: list[dict] = []
    for bucket in buckets:
        flat.extend(bucket or [])

    for it in flat:
        if not it.get("title"):
            continue
        key_doi = (it.get("doi") or "").lower()
        key_title = re.sub(r"\s+", " ", it["title"].lower()).strip()[:120]
        if key_doi and key_doi in seen_doi:
            existing = seen_doi[key_doi]
            if it["citations"] > existing["citations"]:
                seen_doi[key_doi] = it
            continue
        if key_title in seen_title:
            existing = seen_title[key_title]
            if it["citations"] > existing["citations"]:
                seen_title[key_title] = it
            continue
        if key_doi:
            seen_doi[key_doi] = it
        seen_title[key_title] = it

    merged = list({id(v): v for v in [*seen_doi.values(), *seen_title.values()]}.values())
    # Score = citations + recency boost.
    current_year = datetime.now(timezone.utc).year
    def score(it):
        c = int(it.get("citations") or 0)
        y = int(it.get("year") or 1900)
        recency = max(0, 5 - (current_year - y))  # +5..+0 for last 5 years
        return c + recency * 2
    merged.sort(key=score, reverse=True)
    return merged[:limit]


# ── Endpoint ────────────────────────────────────────────────────────────────


@slr_bp.route("/<paper_id>/slr", methods=["POST"])
@jwt_required()
def run_slr(paper_id: str):
    if not PAPER_ID_RE.match(paper_id):
        return jsonify({"error": "Invalid paper id"}), 400
    user_id = int(get_jwt_identity())
    paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    body = request.get_json(silent=True) or {}
    topic = (body.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "topic required"}), 400
    try:
        limit = max(5, min(int(body.get("limit", 30)), 50))
    except (TypeError, ValueError):
        limit = 30
    refresh = bool(body.get("refresh", False))

    cache_key = f"slr:{topic.lower()[:100]}"

    if not refresh:
        cached = ProjectMemory.query.filter_by(paper_id=paper_id, key=cache_key).first()
        if cached:
            try:
                payload = json.loads(cached.value)
                if isinstance(payload, dict) and payload.get("results"):
                    return jsonify({**payload, "cached": True})
            except Exception:
                pass

    # Run sources in parallel, capture which succeeded.
    sources_used: list[str] = []
    sources_failed: list[str] = []
    buckets: list[list[dict]] = []
    per_source_limit = max(8, limit // 2)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fn, topic, per_source_limit): name for name, fn in SOURCES}
        for fut in as_completed(futures, timeout=30):
            name = futures[fut]
            try:
                results = fut.result(timeout=20) or []
                if results:
                    buckets.append(results)
                    sources_used.append(name)
                else:
                    sources_failed.append(name)
            except Exception as e:
                log.info("slr.source_failed", extra={"source": name, "err": str(e)})
                sources_failed.append(name)

    final = _dedupe_and_rank(buckets, limit)
    payload = {
        "results": final,
        "sources_used": sources_used,
        "sources_failed": sources_failed,
        "topic": topic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache (overwrite if exists)
    mem = ProjectMemory.query.filter_by(paper_id=paper_id, key=cache_key).first()
    if mem:
        mem.value = json.dumps(payload, ensure_ascii=False)
        mem.kind = "slr_cache"
        mem.updated_at = datetime.now(timezone.utc)
    else:
        mem = ProjectMemory(
            paper_id=paper_id, user_id=user_id,
            key=cache_key, value=json.dumps(payload, ensure_ascii=False),
            kind="slr_cache",
        )
        db.session.add(mem)
    db.session.commit()

    return jsonify({**payload, "cached": False})
