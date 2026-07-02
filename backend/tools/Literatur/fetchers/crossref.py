"""Combined Crossref fetcher.

1. search() — general Crossref search (broad coverage, any publisher)
2. search_publishers() — batch fetch from 8 member publishers + SSRN
   (Springer, Wiley, SPIE, Emerald, Oxford, ASCE, IGI Global, JSTOR, SSRN)

Both expose: search(client, query, limit, filters) -> Iterable[Paper]
"""

import logging
import os
import re
from typing import Iterable

from ..http_client import RateLimiter, fetch_json, get_random_ua, strip_html
from ..paper import Paper
from .openalex import enrich_abstract_via_doi

log = logging.getLogger(__name__)

BASE = "https://api.crossref.org/works"

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

_ALL_MEMBERS = ",".join(MEMBER_PUBLISHERS.keys())
SSRN_PREFIX = "10.2139"

SELECT_FIELDS = (
    "DOI,title,author,member,container-title,published-print,"
    "published-online,issued,created,type,URL,link,license,"
    "abstract,is-referenced-by-count,publisher,page,reference"
)

# ─── Shared helpers ──────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_jats_tags(text: str) -> str:
    """Remove JATS/HTML markup from CrossRef abstract text.

    CrossRef often returns abstracts wrapped in JATS XML tags such as
    ``<jats:p>`` or ``<jats:title>``.
    """
    return _TAG_RE.sub("", text).strip()


def _clean(text) -> str | None:
    if isinstance(text, list):
        text = " ".join(t for t in text if t)
    if not text:
        return None
    text = strip_html(str(text)) or None
    # If it still has JATS tags after strip_html, try harder
    if text and "<jats:" in text:
        text = _strip_jats_tags(text) or None
    return text


def _get_year(item: dict) -> int | None:
    """Extract year with priority: published-print > published-online > published > issued > created."""
    for dk in ("published-print", "published-online", "published", "issued", "created"):
        dp = (item.get(dk) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            try:
                return int(dp[0][0])
            except (ValueError, TypeError):
                pass
    return None


def _get_authors(item: dict) -> list[str]:
    authors = []
    for a in item.get("author", []) or []:
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{given} {family}".strip() or a.get("name", "")
        if name:
            authors.append(name)
    return authors


def _get_pdf_url(item: dict) -> tuple[str | None, bool]:
    """Return (url_or_landing, is_pdf).

    Checks both content-type AND URL ending for robust PDF detection.
    """
    for link in item.get("link", []) or []:
        ct = (link.get("content-type") or "").lower()
        url = link.get("URL", "").strip()
        if not url:
            continue
        is_pdf = ("pdf" in ct or url.lower().endswith(".pdf"))
        if is_pdf:
            return url, True

    doi = item.get("DOI")
    if doi:
        return f"https://doi.org/{doi}", False

    return item.get("URL"), False


# CrossRef type → venue_type mapping (more granular than before)
_CROSSREF_TYPE_MAP = {
    "journal-article": "journal",
    "proceedings-article": "conference",
    "book": "book",
    "book-chapter": "book-chapter",
    "monograph": "book",
    "edited-book": "book",
    "book-section": "book-chapter",
    "book-part": "book-chapter",
    "reference-book": "book",
    "posted-content": "preprint",
    "dissertation": "dissertation",
    "report": "report",
    "dataset": "dataset",
    "peer-review": "peer-review",
    "standard": "standard",
    "component": "component",
}


def _detect_venue_type(item: dict) -> str | None:
    """Map CrossRef type to venue_type using comprehensive mapping."""
    ctype = (item.get("type") or "").strip().lower()
    return _CROSSREF_TYPE_MAP.get(ctype)


def _detect_oa(item: dict) -> bool | None:
    """Detect open access from license URLs (creativecommons)."""
    if item.get("license"):
        for lic in item["license"]:
            if "creativecommons" in (lic.get("URL") or "").lower():
                return True
    return None


def _parse_page_range(item: dict) -> str | None:
    """Extract page range from the 'page' field."""
    page = (item.get("page") or "").strip()
    return page or None


def _parse_references(item: dict) -> list[str]:
    """Extract cited DOIs from a CrossRef work record.

    Only reference entries that carry a DOI field are included.
    """
    raw_refs = item.get("reference") or []
    result = []
    for entry in raw_refs:
        if not isinstance(entry, dict):
            continue
        doi = (entry.get("DOI") or "").strip()
        if doi:
            result.append(doi)
    return result


def _get_unpaywall_resolver():
    try:
        from ..unpaywall import resolve_pdf_url
        return resolve_pdf_url
    except Exception:
        return None


# ─── General search (broad, any publisher) ───────────────────────────────

def _parse_item_general(item: dict) -> Paper | None:
    title_list = item.get("title") or []
    title = title_list[0] if title_list else None
    if not title:
        return None

    doi = item.get("DOI")
    raw_url, is_pdf = _get_pdf_url(item)
    if is_pdf:
        pdf_url = raw_url
        url = raw_url
    else:
        pdf_url = None
        url = raw_url or None
    if not url and doi:
        url = f"https://doi.org/{doi}"

    # Parse references and log count
    refs = _parse_references(item)
    if refs:
        log.debug("Crossref: paper %s has %d references", doi, len(refs))

    return Paper(
        source="crossref",
        source_id=doi or "",
        title=title,
        authors=_get_authors(item),
        abstract=_clean(item.get("abstract")),
        year=_get_year(item),
        venue=_clean(item.get("container-title")),
        venue_type=_detect_venue_type(item),
        doi=doi,
        url=url,
        pdf_url=pdf_url,
        citations=item.get("is-referenced-by-count"),
        is_open_access=_detect_oa(item),
        type=item.get("type"),
        publisher=item.get("publisher"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """General Crossref search — broad coverage, any publisher."""
    rl = RateLimiter(0.25)
    per_page = min(limit, 100)
    fetched = 0
    offset = 0

    filter_parts = []
    if filters:
        for k, v in filters.items():
            filter_parts.append(f"{k}:{v}")

    while fetched < limit:
        rl.wait()
        params = {
            "query": query,
            "rows": min(per_page, limit - fetched),
            "offset": offset,
            "sort": "relevance",
            "order": "desc",
            "mailto": os.getenv("SLR_CONTACT_EMAIL") or "research@example.com",
            "select": "DOI,title,author,issued,container-title,abstract,type,publisher,URL,is-referenced-by-count,page,reference",
        }
        if filter_parts:
            params["filter"] = ",".join(filter_parts)

        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        items = ((data.get("message") or {}).get("items")) or []
        if not items:
            return
        for item in items:
            paper = _parse_item_general(item)
            if paper:
                # NOTE: OpenAlex enrichment disabled to avoid 429 rate limits
                # Enable only when OPENALEX_API_KEY is set or proxy rotation is active
                # if not paper.abstract and paper.doi:
                #     paper.abstract = enrich_abstract_via_doi(paper.doi, client)
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        offset += len(items)
        if len(items) < per_page:
            return


# ─── Batch publisher search (8 members + SSRN in 2 calls) ────────────────

def _parse_item_publisher(item: dict, source_override: str | None = None) -> Paper | None:
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

    doi = item.get("DOI")
    pdf_url, _is_pdf = _get_pdf_url(item)
    landing_url = item.get("URL") or (doi and f"https://doi.org/{doi}")
    if not _is_pdf:
        pdf_url = None

    # Parse references and log count
    refs = _parse_references(item)
    if refs:
        log.debug("Crossref: paper %s has %d references", doi, len(refs))

    return Paper(
        source=source,
        source_id=doi or "",
        title=title,
        authors=_get_authors(item),
        abstract=_clean(item.get("abstract")),
        year=_get_year(item),
        venue=_clean(item.get("container-title")),
        venue_type=_detect_venue_type(item),
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        citations=item.get("is-referenced-by-count"),
        is_open_access=_detect_oa(item),
        type=item.get("type"),
        publisher=pub_name,
    )


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
        data = fetch_json(client, BASE, params=params, headers={"User-Agent": get_random_ua()})
        if not data:
            return
        msg = data.get("message") or {}
        items = msg.get("items") or []
        if not items:
            return

        for item in items:
            paper = _parse_item_publisher(item)
            if paper:
                if resolver and not paper.pdf_url and paper.doi:
                    try:
                        pdf = resolver(paper.doi)
                        if pdf:
                            paper.pdf_url = pdf
                            paper.is_open_access = True
                    except Exception:
                        pass
                # NOTE: OpenAlex enrichment disabled to avoid 429 rate limits
                # if not paper.abstract and paper.doi:
                #     paper.abstract = enrich_abstract_via_doi(paper.doi, client)
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
        data = fetch_json(client, BASE, params=params, headers={"User-Agent": get_random_ua()})
        if not data:
            return
        msg = data.get("message") or {}
        items = msg.get("items") or []
        if not items:
            return

        for item in items:
            paper = _parse_item_publisher(item, source_override="ssrn")
            if paper:
                if resolver and not paper.pdf_url and paper.doi:
                    try:
                        pdf = resolver(paper.doi)
                        if pdf:
                            paper.pdf_url = pdf
                            paper.is_open_access = True
                    except Exception:
                        pass
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


def search_publishers(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Batch fetch from 8 member publishers + SSRN in 2 API calls.

    Each paper carries its correct source tag (springer/wiley/spie/etc).
    Sort: newest first. Includes Unpaywall PDF resolution and OpenAlex
    abstract enrichment.
    """
    yield from _fetch_members(client, query, limit, filters)
    yield from _fetch_ssrn(client, query, limit, filters)
