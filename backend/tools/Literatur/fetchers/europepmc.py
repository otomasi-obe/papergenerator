"""Fetcher untuk Europe PMC - https://www.ebi.ac.uk/europepmc/webservices/rest"""

from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def _parse(item: dict) -> Paper | None:
    title = item.get("title")
    if not title:
        return None
    title = title.rstrip(".").strip()

    authors = []
    author_str = item.get("authorString")
    if author_str:
        authors = [a.strip() for a in author_str.split(",") if a.strip()]

    year = None
    if item.get("pubYear"):
        try:
            year = int(item["pubYear"])
        except (ValueError, TypeError):
            pass

    # Build PDF URL: prioritize full text links
    pdf_url = None
    doi = item.get("doi")
    pmcid = item.get("pmcid")
    pmid = item.get("pmid")
    landing_url = None

    # Landing page
    if pmid:
        landing_url = f"https://europepmc.org/article/{item.get('source', '')}/{item.get('id', '')}"
    elif doi:
        landing_url = f"https://doi.org/{doi}"

    # Check for full text links
    full_text_urls = item.get("fullTextUrlList", {}).get("fullTextUrl", [])
    for ft in full_text_urls:
        if ft.get("documentStyle") == "pdf" or ft.get("availabilityCode") == "OA":
            pdf_url = ft.get("url")
            break
    
    # Fallback: PMC PDF if available
    if not pdf_url and pmcid:
        pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"
    
    # Fallback: DOI
    if not pdf_url and doi:
        pdf_url = f"https://doi.org/{doi}"

    # Fallback: use landing_url as pdf_url if nothing else available
    if not pdf_url:
        pdf_url = landing_url

    return Paper(
        source="europepmc",
        source_id=item.get("id", ""),
        title=title,
        authors=authors,
        abstract=item.get("abstractText"),
        year=year,
        venue=item.get("journalTitle"),
        venue_type="journal" if item.get("journalTitle") else None,
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        citations=item.get("citedByCount"),
        is_open_access=item.get("isOpenAccess") == "Y",
        type=item.get("pubType"),
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    rl = RateLimiter(0.3)
    per_page = min(limit, 100)
    fetched = 0
    cursor = "*"

    full_query = query
    if filters:
        if filters.get("open_access"):
            full_query += " AND OPEN_ACCESS:Y"
        if filters.get("has_abstract"):
            full_query += " AND HAS_ABSTRACT:Y"
    # Always request HAS_ABSTRACT to avoid empty abstract records
    full_query += " AND HAS_ABSTRACT:Y"

    while fetched < limit:
        rl.wait()
        params = {
            "query": full_query,
            "format": "json",
            "resultType": "core",  # includes abstractText
            "pageSize": min(per_page, limit - fetched),
            "cursorMark": cursor,
        }
        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        results = ((data.get("resultList") or {}).get("result")) or []
        if not results:
            return
        for r in results:
            paper = _parse(r)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        next_cursor = data.get("nextCursorMark")
        if not next_cursor or next_cursor == cursor:
            return
        cursor = next_cursor
