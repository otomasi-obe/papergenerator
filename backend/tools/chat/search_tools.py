"""
Chat search tools — lightweight wrappers around web search, arXiv, and
Semantic Scholar for use in the PaperFull chat assistant.

These are NOT the full SLR pipeline (that's in tools/Literatur/).
These are quick-lookup tools for brainstorming and light research questions.

For full SLR (systematic literature review with scoring, dedup, summarization),
the chat should offer the user to trigger the SLR job endpoint instead.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

log = logging.getLogger(__name__)

# ── Rate limiters ─────────────────────────────────────────────────────────────
_last_ddgs_call = 0.0
_last_s2_call = 0.0
_last_arxiv_call = 0.0

DDGS_MIN_INTERVAL = 2.0   # seconds between DDGS calls
S2_MIN_INTERVAL = 1.5      # seconds between S2 calls
ARXIV_MIN_INTERVAL = 4.0   # arXiv is strict


def _rate_limit(last: float, interval: float) -> float:
    """Sleep if needed, return current time."""
    now = time.monotonic()
    gap = now - last
    if gap < interval:
        time.sleep(interval - gap)
    return time.monotonic()


# ── Intent detection ──────────────────────────────────────────────────────────

# Keywords that signal the user wants research/search capabilities
INTENT_KEYWORDS = {
    "web_search": {
        # Light brainstorming / fact-checking
        "keywords": [
            "cari di internet", "search online", "google",
            "cari info", "cari informasi", "search for",
            "look up", "find online", "web search",
            "browse", "carikan di web",
        ],
        "weight": 1,
    },
    "arxiv_search": {
        # ArXiv-specific queries
        "keywords": [
            "arxiv", "preprint", "paper terbaru", "latest paper",
            "recent paper", "paper terkini",
        ],
        "weight": 1,
    },
    "academic_search": {
        # Academic paper search (semantic scholar)
        "keywords": [
            "cari paper", "search paper", "find paper",
            "cari jurnal", "search journal", "literature",
            "referensi", "citation", "sitasi",
            "previous study", "penelitian terdahulu",
            "related work", "karya terkait",
        ],
        "weight": 1,
    },
    "research_gap": {
        # Research gap analysis — offer SLR
        "keywords": [
            "research gap", "celah penelitian", "gap penelitian",
            "kesenjangan penelitian", "gap analysis",
            "what hasn't been studied", "apa yang belum diteliti",
            "novelty", "kebaruan",
        ],
        "weight": 2,
    },
    "slr": {
        # Explicit SLR request
        "keywords": [
            "slr", "systematic literature review",
            "tinjauan literatur sistematis", "literature review lengkap",
            "riset literatur mendalam", "comprehensive review",
        ],
        "weight": 3,
    },
}


def detect_intent(message: str) -> list[str]:
    """Detect search/research intents from user message.

    Returns list of intent names sorted by weight (highest first).
    Empty list means no special intent — just normal chat.
    """
    msg = f" {message.lower().strip()} "
    detected = []
    for intent, cfg in INTENT_KEYWORDS.items():
        if any(f" {kw} " in msg or kw in msg.lower() for kw in cfg["keywords"]):
            detected.append((intent, cfg["weight"]))
    if not detected:
        return []
    detected.sort(key=lambda x: -x[1])
    return [d[0] for d in detected]


# ── Web search (DuckDuckGo) ──────────────────────────────────────────────────

def web_search(query: str, limit: int = 5) -> dict[str, Any]:
    """Search the web using DuckDuckGo (no API key needed).

    Returns:
        {"success": bool, "results": [{"title", "url", "snippet"}], "error": str}
    """
    global _last_ddgs_call
    _last_ddgs_call = _rate_limit(_last_ddgs_call, DDGS_MIN_INTERVAL)

    try:
        from ddgs import DDGS
    except ImportError:
        return {"success": False, "results": [], "error": "ddgs not installed"}

    try:
        results = []
        with DDGS() as client:
            for i, hit in enumerate(client.text(query, max_results=limit)):
                if i >= limit:
                    break
                results.append({
                    "title": hit.get("title", ""),
                    "url": hit.get("href") or hit.get("url", ""),
                    "snippet": hit.get("body", ""),
                })
        log.info("web_search '%s': %d results", query[:60], len(results))
        return {"success": True, "results": results, "error": None}
    except Exception as e:
        log.warning("web_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ── ArXiv search ─────────────────────────────────────────────────────────────

def arxiv_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search arXiv for papers. Returns title, authors, abstract, year, url.

    Uses the Literatur fetcher directly for consistency with SLR pipeline.
    """
    global _last_arxiv_call
    _last_arxiv_call = _rate_limit(_last_arxiv_call, ARXIV_MIN_INTERVAL)

    try:
        from tools.Literatur.fetchers.arxiv import search as arxiv_search_fn
        from tools.Literatur.http_client import get_client

        results = []
        with get_client() as client:
            for paper in arxiv_search_fn(client, query, limit=limit):
                results.append({
                    "title": paper.title or "",
                    "authors": paper.authors[:5] if paper.authors else [],
                    "abstract": (paper.abstract or "")[:500],
                    "year": paper.year,
                    "url": paper.url or "",
                    "doi": paper.doi or "",
                    "source": "arxiv",
                })
        log.info("arxiv_search '%s': %d results", query[:60], len(results))
        return {"success": True, "results": results, "error": None}
    except Exception as e:
        log.warning("arxiv_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ── Semantic Scholar search ──────────────────────────────────────────────────

def academic_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search academic papers via OpenAlex (fast, no key needed) with
    Semantic Scholar as fallback.

    Returns title, authors, abstract, year, venue, citations, DOI.
    """
    # Try OpenAlex first (fastest, most reliable, no rate limit)
    result = _openalex_search(query, limit)
    if result["success"] and result["results"]:
        return result

    # Fallback to Semantic Scholar
    global _last_s2_call
    _last_s2_call = _rate_limit(_last_s2_call, S2_MIN_INTERVAL)

    try:
        from tools.Literatur.fetchers.semantic_scholar import search as s2_search_fn
        from tools.Literatur.http_client import get_client

        results = []
        with get_client() as client:
            for paper in s2_search_fn(client, query, limit=limit):
                results.append({
                    "title": paper.title or "",
                    "authors": paper.authors[:5] if paper.authors else [],
                    "abstract": (paper.abstract or "")[:500],
                    "year": paper.year,
                    "venue": paper.venue or "",
                    "citations": paper.citations,
                    "doi": paper.doi or "",
                    "url": paper.url or "",
                    "source": "semantic_scholar",
                    "open_access": paper.is_open_access,
                })
        log.info("academic_search (S2 fallback) '%s': %d results", query[:60], len(results))
        return {"success": True, "results": results, "error": None}
    except Exception as e:
        log.warning("academic_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


def _openalex_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Quick OpenAlex search — no API key, fast, reliable."""
    try:
        import httpx
        resp = httpx.get(
            "https://api.openalex.org/works",
            params={
                "search": query,
                "per_page": min(limit, 25),
                "select": "id,title,publication_year,cited_by_count,doi,authorships,primary_location,open_access",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            return {"success": False, "results": [], "error": f"OpenAlex HTTP {resp.status_code}"}

        data = resp.json()
        results = []
        for work in data.get("results", []):
            title = work.get("title", "")
            if not title:
                continue

            # Extract authors
            authors = []
            for auth in (work.get("authorships") or [])[:5]:
                author = auth.get("author", {})
                if author.get("display_name"):
                    authors.append(author["display_name"])

            # Extract venue
            venue = ""
            loc = work.get("primary_location") or {}
            source = loc.get("source") or {}
            venue = source.get("display_name", "")

            # Extract abstract from inverted index (OpenAlex stores it this way)
            abstract = ""
            # OpenAlex doesn't include abstract in 'select' — skip for speed

            # DOI
            doi = (work.get("doi") or "").replace("https://doi.org/", "")

            # Open access
            oa_info = work.get("open_access") or {}
            oa_url = oa_info.get("oa_url", "")

            results.append({
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "year": work.get("publication_year"),
                "venue": venue,
                "citations": work.get("cited_by_count"),
                "doi": doi,
                "url": oa_url or f"https://doi.org/{doi}" if doi else "",
                "source": "openalex",
                "open_access": bool(oa_url),
            })

        log.info("openalex_search '%s': %d results", query[:60], len(results))
        return {"success": True, "results": results, "error": None}
    except Exception as e:
        log.warning("openalex_search error: %s", e)
        return {"success": False, "results": [], "error": str(e)}


# ── Parallel multi-search ────────────────────────────────────────────────────

def execute_searches(intents: list[str], query: str, limit: int = 5) -> dict[str, Any]:
    """Execute multiple searches in parallel based on detected intents.

    Returns combined results formatted for injection into AI context.
    """
    if not intents:
        return {"context": "", "has_results": False}

    # Determine which searches to run
    searches = {}
    for intent in intents:
        if intent == "web_search":
            searches["web"] = ("Web Search (DuckDuckGo)", web_search, query, limit)
        elif intent == "arxiv_search":
            searches["arxiv"] = ("ArXiv Search", arxiv_search, query, min(limit, 10))
        elif intent == "academic_search":
            searches["academic"] = ("Semantic Scholar", academic_search, query, min(limit, 10))
        elif intent == "research_gap":
            # For research gap: run both academic + arxiv in parallel
            searches["academic"] = ("Semantic Scholar", academic_search, query, min(limit, 10))
            searches["arxiv"] = ("ArXiv Search", arxiv_search, query, min(limit, 8))
        elif intent == "slr":
            # SLR is handled separately — just set a flag
            pass

    if not searches and "slr" not in intents:
        return {"context": "", "has_results": False}

    # Execute in parallel
    results = {}
    with ThreadPoolExecutor(max_workers=min(3, len(searches))) as ex:
        futures = {}
        for key, (label, fn, q, lim) in searches.items():
            futures[ex.submit(fn, q, lim)] = (key, label)

        for fut in as_completed(futures):
            key, label = futures[fut]
            try:
                results[key] = (label, fut.result())
            except Exception as e:
                results[key] = (label, {"success": False, "results": [], "error": str(e)})

    # Build context block for injection
    parts = []
    has_results = False

    for key, (label, data) in results.items():
        if not data.get("success") or not data.get("results"):
            err = data.get("error", "no results")
            parts.append(f"### {label}\n(No results: {err})\n")
            continue

        has_results = True
        items = data["results"]
        parts.append(f"### {label} — {len(items)} hasil ditemukan\n")

        for i, item in enumerate(items, 1):
            title = item.get("title", "Untitled")
            year = item.get("year", "?")
            authors = ", ".join(item.get("authors", [])[:3])
            if len(item.get("authors", [])) > 3:
                authors += " et al."
            abstract = item.get("abstract", item.get("snippet", ""))
            if abstract and len(abstract) > 300:
                abstract = abstract[:300] + "..."
            url = item.get("url", "")
            doi = item.get("doi", "")
            venue = item.get("venue", "")
            citations = item.get("citations")
            source = item.get("source", "")

            line = f"{i}. **{title}**"
            if authors:
                line += f"\n   Authors: {authors}"
            if year:
                line += f" ({year})"
            if venue:
                line += f"\n   Venue: {venue}"
            if citations is not None:
                line += f" | Citations: {citations}"
            if doi:
                line += f"\n   DOI: {doi}"
            if url:
                line += f"\n   URL: {url}"
            if source:
                line += f" [Source: {source}]"
            if abstract:
                line += f"\n   Abstract: {abstract}"
            parts.append(line + "\n")

    context = ""
    if parts:
        context = "## HASIL PENCARIAN OTOMATIS (gunakan sebagai referensi)\n\n" + "\n".join(parts)

    return {
        "context": context,
        "has_results": has_results,
        "needs_slr_offer": "slr" in intents or "research_gap" in intents,
    }


# ── Search tag extraction from AI response ───────────────────────────────────
# AI outputs search commands as [WEBSEARCH:query], [ARXIV:query], [SCHOLAR:query]
# Backend intercepts these, executes them, and streams progress to frontend.

_SEARCH_TAG_RE = re.compile(
    r"\[(WEBSEARCH|ARXIV|SCHOLAR):([^\]]{1,300})\]",
    re.IGNORECASE,
)


def extract_search_tags(text: str) -> list[dict]:
    """Extract search commands from AI text.

    Returns list of {"type": "web"|"arxiv"|"scholar", "query": "...", "raw": "[WEBSEARCH:...]"}.
    """
    tags = []
    for m in _SEARCH_TAG_RE.finditer(text):
        tag_type = m.group(1).upper()
        query = m.group(2).strip()
        type_map = {"WEBSEARCH": "web", "ARXIV": "arxiv", "SCHOLAR": "scholar"}
        tags.append({
            "type": type_map.get(tag_type, "web"),
            "query": query,
            "raw": m.group(0),
        })
    return tags


def strip_search_tags(text: str) -> str:
    """Remove search tags from AI text."""
    return _SEARCH_TAG_RE.sub("", text).strip()


def execute_tag_search(tag: dict) -> dict[str, Any]:
    """Execute a single search tag and return results."""
    t = tag["type"]
    q = tag["query"]
    if t == "web":
        return web_search(q, limit=8)
    elif t == "arxiv":
        return arxiv_search(q, limit=8)
    elif t == "scholar":
        return academic_search(q, limit=8)
    return {"success": False, "results": [], "error": f"Unknown type: {t}"}


def format_search_results_for_ai(all_results: list[dict]) -> str:
    """Format collected search results into a context block for AI phase 2."""
    if not all_results:
        return ""

    parts = ["## HASIL PENCARIAN REAL (gunakan sebagai referensi NYATA)\n"]
    for block in all_results:
        source_type = block["type"]
        query = block["query"]
        data = block["data"]

        label_map = {"web": "Web Search", "arxiv": "ArXiv", "scholar": "OpenAlex/Scholar"}
        label = label_map.get(source_type, source_type)

        if not data.get("success") or not data.get("results"):
            err = data.get("error", "no results")
            parts.append(f"### {label} untuk \"{query}\" — Tidak ada hasil ({err})\n")
            continue

        items = data["results"]
        parts.append(f"### {label} untuk \"{query}\" — {len(items)} hasil\n")

        for i, item in enumerate(items, 1):
            title = item.get("title", "Untitled")
            year = item.get("year", "")
            authors = ", ".join(item.get("authors", [])[:3])
            if len(item.get("authors", [])) > 3:
                authors += " et al."
            url = item.get("url", "")
            doi = item.get("doi", "")
            venue = item.get("venue", "")
            citations = item.get("citations")
            snippet = item.get("snippet", item.get("abstract", ""))
            if snippet and len(snippet) > 300:
                snippet = snippet[:300] + "..."
            source = item.get("source", "")

            line = f"{i}. **{title}**"
            if authors:
                line += f"\n   Authors: {authors}"
            if year:
                line += f" ({year})"
            if venue:
                line += f"\n   Venue: {venue}"
            if citations is not None:
                line += f" | Citations: {citations}"
            if doi:
                line += f"\n   DOI: {doi}"
            if url:
                line += f"\n   URL: {url}"
            if source:
                line += f" [Source: {source}]"
            if snippet:
                line += f"\n   {snippet}"
            parts.append(line + "\n")

    parts.append(
        "\n⚠️ REFERENSI DI ATAS ADALAH DATA REAL DARI PENCARIAN. "
        "Gunakan authors, year, title, DOI yang TEPAT dari data di atas saat menyitasi. "
        "JANGAN mengarang referensi yang tidak ada di hasil pencarian.\n"
    )
    return "\n".join(parts)


def format_search_event_for_frontend(tag: dict, data: dict) -> dict:
    """Format a search result as a frontend-friendly event payload."""
    source_type = tag["type"]
    query = tag["query"]
    label_map = {"web": "web_search", "arxiv": "arxiv_search", "scholar": "scholar_search"}
    label = label_map.get(source_type, source_type)

    items = []
    if data.get("success") and data.get("results"):
        for item in data["results"]:
            items.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "year": item.get("year"),
                "authors": item.get("authors", [])[:3],
                "doi": item.get("doi", ""),
                "venue": item.get("venue", ""),
                "citations": item.get("citations"),
                "snippet": (item.get("snippet", item.get("abstract", "")) or "")[:200],
            })

    return {
        "type": label,
        "query": query,
        "icon": "🔍",
        "count": len(items),
        "results": items,
        "error": data.get("error"),
    }


# ── SLR trigger ──────────────────────────────────────────────────────────────

def trigger_slr_job(paper_id: str, user_id: int, query: str, conversation_id: str | None = None) -> dict:
    """Trigger an SLR job via the worker system.

    Returns job info dict or error.
    """
    try:
        from tools.Literatur.worker import enqueue_slr_job

        job = enqueue_slr_job(
            paper_id=paper_id,
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            sources=None,          # auto-detect by topic
            per_source=None,
            top_k=None,
            year_from=None,
            ai_summarize=True,
            ai_model="VIOLA-GENERATE",
        )
        log.info("SLR job triggered: %s for paper=%s query=%s", job.id, paper_id, query[:60])
        return {
            "success": True,
            "job_id": job.id,
            "status": job.status,
        }
    except Exception as e:
        log.exception("Failed to trigger SLR job: %s", e)
        return {"success": False, "error": str(e)}
