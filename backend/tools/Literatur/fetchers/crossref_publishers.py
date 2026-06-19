"""Combined Crossref publisher fetchers.

Replaces 9 individual publisher wrappers (springer, wiley, spie, emerald,
oxford, asce, igi_global, jstor + ssrn) with 2 HTTP calls instead of 9.

1. search_crossref_publishers() — batch fetch from 8 member-based publishers
   in a single Crossref API call. Each paper is tagged with the correct
   source name based on member ID.

2. search_ssrn() — separate call for SSRN (uses DOI prefix 10.2139, not
   member ID, because SSRN shares member 78 with all Elsevier content).

Sort: newest first (sort=published, order=desc).
"""

import logging
import os
import re
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper
from ._abstract_enrich import enrich_abstract_via_doi

log = logging.getLogger(__name__)

BASE = "https://api.crossref.org/works"
USER_AGENT = "MonitoringVokasi/1.0 (mailto:research@example.com)"
_TAG_RE = re.compile(r"<[^>]+>")

# Crossref member ID → (source_name, display_name)
MEMBER_PUBLISHERS = {
    "297": ("springer", "Springer Nature"),
    "311": ("wiley", "Wiley"),
    "189": ("spie", "SPIE"),
    "140": ("emerald", "Emerald"),
    "286": ("oxford", "Oxford University Press"),
    "30": ("asce", "ASCE"),
    "2432": ("igi_global", "IGI Global"),
    "1121": ("jstor", "JSTOR"),
}

# Comma-separated member filter for batch query
_ALL_MEMBERS = ",".join(MEMBER_PUBLISHERS.keys())

# SSRN uses DOI prefix (member 78 = all Elsevier, too broad)
SSRN_PREFIX = "10.2139"

# SELECT fields to minimize response size
SELECT_FIELDS = (
    "DOI,title,author,member,container-title,published-print,"
    "published-online,issued,created,type,URL,link,license,"
    "abstract,is-referenced-by-count,publisher"
)


# ─── Parsing ─────────────────────────────────────────────────────────────


def _clean(text) -> str | None:
    if isinstance(text, list):
        text = " ".join(t for t in text if t)
    if not text:
        return None
    text = _TAG_RE.sub(" ", str(text))
    return " ".join(text.split()).strip() or None


def _parse(item: dict, source_override: str | None = None) -> Paper | None:
    title = _clean(item.get("title"))
    if not title:
        return None

    member_id = item.get("member")
    if source_override:
        source = source_override
    elif member_id and member_id in MEMBER_PUBLISHERS:
        source = MEMBER_PUBLISHERS[member_id][0]
    else:
        source = "crossref_publishers"

    pub_name = None
    if member_id and member_id in MEMBER_PUBLISHERS:
        pub_name = MEMBER_PUBLISHERS[member_id][1]
    else:
        pub_name = item.get("publisher") or source

    authors = []
    for a in item.get("author", []) or []:
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{given} {family}".strip() or a.get("name", "")
        if name:
            authors.append(name)

    year = None
    for dk in ("published-print", "published-online", "issued", "created"):
        dp = (item.get(dk) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            try:
                year = int(dp[0][0])
                break
            except (ValueError, TypeError):
                pass

    doi = item.get("DOI")
    venue = _clean(item.get("container-title"))

    ctype = item.get("type", "")
    venue_type = None
    if "journal" in ctype:
        venue_type = "journal"
    elif "proceedings" in ctype or "conference" in ctype:
        venue_type = "conference"
    elif "book" in ctype:
        venue_type = "book"
    elif "posted-content" in ctype:
        venue_type = "preprint"

    pdf_url = None
    for link in item.get("link", []) or []:
        ct = (link.get("content-type") or "").lower()
        url = link.get("URL")
        if url and ("pdf" in ct or url.lower().endswith(".pdf")):
            pdf_url = url
            break

    landing_url = item.get("URL") or (doi and f"https://doi.org/{doi}")

    is_oa = None
    if item.get("license"):
        for lic in item["license"]:
            if "creativecommons" in (lic.get("URL") or "").lower():
                is_oa = True
                break

    abstract = _clean(item.get("abstract"))

    return Paper(
        source=source,
        source_id=doi or "",
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=venue,
        venue_type=venue_type,
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        citations=item.get("is-referenced-by-count"),
        is_open_access=is_oa,
        type=ctype or None,
        publisher=pub_name,
    )


# ─── Batch fetch (8 publishers, 1 call) ──────────────────────────────────


def search(
    client,
    query: str,
    limit: int = 25,
    filters: dict | None = None,
) -> Iterable[Paper]:
    """Entry point called by orchestrator. Fetches from all 8 Crossref-member
    publishers in 1 API call, plus SSRN in a 2nd call.

    Each paper carries its correct source tag (springer/wiley/spie/etc).
    Sort: newest first.
    """
    # Part 1: batch fetch 8 member publishers
    yield from _fetch_members(client, query, limit, filters)

    # Part 2: SSRN via prefix
    yield from _fetch_ssrn(client, query, limit, filters)


def _fetch_members(
    client,
    query: str,
    limit: int,
    filters: dict | None,
) -> Iterable[Paper]:
    rl = RateLimiter(0.5)
    per_page = min(limit, 100)
    fetched = 0
    cursor = "*"

    full_filter = f"member:{_ALL_MEMBERS}"
    if filters and filters.get("year_from"):
        full_filter += f",from-pub-date:{filters['year_from']}-01-01"

    resolver = _get_unpaywall_resolver()

    while fetched < limit:
        rl.wait()
        params = {
            "query": query,
            "filter": full_filter,
            "rows": min(per_page, limit - fetched),
            "cursor": cursor,
            "sort": "relevance",
            "order": "desc",
            "select": SELECT_FIELDS,
            "mailto": os.getenv("SLR_CONTACT_EMAIL") or "research@example.com",
        }
        data = fetch_json(client, BASE, params=params, headers={"User-Agent": USER_AGENT})
        if not data:
            return
        msg = data.get("message") or {}
        items = msg.get("items") or []
        if not items:
            return

        for item in items:
            paper = _parse(item)
            if paper:
                if resolver and not paper.pdf_url and paper.doi:
                    try:
                        pdf = resolver(paper.doi)
                        if pdf:
                            paper.pdf_url = pdf
                            paper.is_open_access = True
                    except Exception:
                        pass
                # Enrich abstract via DOI → OpenAlex fallback
                if not paper.abstract and paper.doi:
                    paper.abstract = enrich_abstract_via_doi(paper.doi, client)
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        next_cursor = msg.get("next-cursor")
        if not next_cursor or next_cursor == cursor:
            return
        cursor = next_cursor


def _fetch_ssrn(
    client,
    query: str,
    limit: int,
    filters: dict | None,
) -> Iterable[Paper]:
    rl = RateLimiter(0.5)
    per_page = min(limit, 100)
    fetched = 0
    cursor = "*"

    full_filter = f"prefix:{SSRN_PREFIX}"
    if filters and filters.get("year_from"):
        full_filter += f",from-pub-date:{filters['year_from']}-01-01"

    resolver = _get_unpaywall_resolver()

    while fetched < limit:
        rl.wait()
        params = {
            "query": query,
            "filter": full_filter,
            "rows": min(per_page, limit - fetched),
            "cursor": cursor,
            "sort": "relevance",
            "order": "desc",
            "select": SELECT_FIELDS,
            "mailto": os.getenv("SLR_CONTACT_EMAIL") or "research@example.com",
        }
        data = fetch_json(client, BASE, params=params, headers={"User-Agent": USER_AGENT})
        if not data:
            return
        msg = data.get("message") or {}
        items = msg.get("items") or []
        if not items:
            return

        for item in items:
            paper = _parse(item, source_override="ssrn")
            if paper:
                if resolver and not paper.pdf_url and paper.doi:
                    try:
                        pdf = resolver(paper.doi)
                        if pdf:
                            paper.pdf_url = pdf
                            paper.is_open_access = True
                    except Exception as _e:
                        print(f"[crossref_publishers] unpaywall resolve failed for DOI {paper.doi}: {_e}")
                # Enrich abstract via DOI → OpenAlex fallback
                if not paper.abstract and paper.doi:
                    paper.abstract = enrich_abstract_via_doi(paper.doi, client)
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        next_cursor = msg.get("next-cursor")
        if not next_cursor or next_cursor == cursor:
            return
        cursor = next_cursor


def _get_unpaywall_resolver():
    try:
        from ..unpaywall import resolve_pdf_url
        return resolve_pdf_url
    except Exception as _e:
        print(f"[crossref_publishers] unpaywall module not available: {_e}")
        return None
