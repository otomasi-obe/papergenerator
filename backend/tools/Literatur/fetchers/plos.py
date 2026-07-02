"""Fetcher untuk PLOS - Public Library of Science.

http://api.plos.org/solr/search-fields/

Keyless Solr-backed search API across all PLOS open-access journals
(PLOS ONE, Biology, Medicine, Genetics, Computational Biology, etc.).
Endpoint: https://api.plos.org/search?q=...&wt=json
All PLOS articles are open access (CC-BY).
"""

import logging
from typing import Iterable

from ..http_client import RateLimiter, fetch_json, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://api.plos.org/search"

FL = "id,title,author,abstract,publication_date,journal,article_type"


def _clean(text) -> str | None:
    if isinstance(text, list):
        text = " ".join(t for t in text if t)
    if not text:
        return None
    return strip_html(str(text)) or None


def _parse(doc: dict) -> Paper | None:
    title = _clean(doc.get("title"))
    if not title:
        return None

    authors = []
    raw = doc.get("author") or []
    if isinstance(raw, str):
        raw = [raw]
    for a in raw:
        if a:
            authors.append(a.strip())

    year = None
    pub_date = doc.get("publication_date")
    if pub_date:
        try:
            year = int(str(pub_date)[:4])
        except (ValueError, TypeError):
            pass

    # PLOS id is the DOI
    doi = doc.get("id")
    # PLOS article PDF pattern
    pdf_url = None
    landing_url = None
    if doi and doi.startswith("10.1371/"):
        landing_url = f"https://journals.plos.org/plosone/article?id={doi}"
        pdf_url = (
            f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable"
        )
    elif doi:
        landing_url = f"https://doi.org/{doi}"

    return Paper(
        source="plos",
        source_id=doi or "",
        title=title,
        authors=authors,
        abstract=_clean(doc.get("abstract")),
        year=year,
        venue=_clean(doc.get("journal")),
        venue_type="journal",
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        is_open_access=True,  # PLOS is fully open access
        type=_clean(doc.get("article_type")) or "journal-article",
        publisher="PLOS",
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search PLOS open-access journals. No API key required."""
    rl = RateLimiter(0.5)
    per_page = min(limit, 100)
    fetched = 0
    start = 0

    # Simplified query — avoid doc_type:full which can cause empty results
    # Use q=everything:"..." for broad search across all fields
    terms = query.strip()
    # If multi-word, quote to boost phrase relevance but allow partial matches
    q = f'everything:({terms}) AND !article_type:"Issue Image" AND !article_type:"Correction"'

    while fetched < limit:
        rl.wait()
        params = {
            "q": q,
            "start": start,
            "rows": min(per_page, limit - fetched),
            "wt": "json",
            "fl": FL,
            "sort": "score desc",
        }
        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        resp = data.get("response") or {}
        docs = resp.get("docs") or []
        if not docs:
            return
        for doc in docs:
            paper = _parse(doc)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        total = resp.get("numFound", 0)
        start += len(docs)
        if start >= total:
            return
