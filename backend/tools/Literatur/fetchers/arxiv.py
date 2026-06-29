"""Fetcher untuk arXiv - http://export.arxiv.org/api/query"""

import re
import xml.etree.ElementTree as _ET  # type hints only
from defusedxml.ElementTree import fromstring
from typing import Iterable

from ..http_client import RateLimiter, fetch_text
from ..paper import Paper

BASE = "https://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _parse_entry(entry: _ET.Element) -> Paper | None:
    title_el = entry.find("atom:title", NS)
    title = (title_el.text or "").strip() if title_el is not None else None
    if not title:
        return None
    title = re.sub(r"\s+", " ", title)

    summary_el = entry.find("atom:summary", NS)
    abstract = (summary_el.text or "").strip() if summary_el is not None else None
    if abstract:
        abstract = re.sub(r"\s+", " ", abstract)

    authors = []
    for a in entry.findall("atom:author", NS):
        name_el = a.find("atom:name", NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    arxiv_id = None
    id_el = entry.find("atom:id", NS)
    if id_el is not None and id_el.text:
        arxiv_id = id_el.text.rsplit("/", 1)[-1]

    year = None
    pub_el = entry.find("atom:published", NS)
    if pub_el is not None and pub_el.text:
        try:
            year = int(pub_el.text[:4])
        except ValueError:
            pass

    doi = None
    doi_el = entry.find("arxiv:doi", NS)
    if doi_el is not None:
        doi = (doi_el.text or "").strip() or None

    venue = None
    jr_el = entry.find("arxiv:journal_ref", NS)
    if jr_el is not None:
        venue = (jr_el.text or "").strip() or None

    # Landing page and PDF download link
    landing_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else None

    return Paper(
        source="arxiv",
        source_id=arxiv_id or "",
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=venue,
        venue_type="repository",
        doi=doi,
        url=landing_url,
        pdf_url=pdf_url,
        is_open_access=True,
        type="preprint",
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    # arXiv rate limit: very strict, use 10 seconds to avoid 429
    # They recommend 3 seconds but we've seen 429s, so being extra conservative
    rl = RateLimiter(10.0)
    per_page = min(limit, 100)
    start = 0

    search_query = f"all:{query}"
    if filters and "category" in filters:
        search_query = f"({search_query}) AND cat:{filters['category']}"

    while start < limit:
        rl.wait()
        params = {
            "search_query": search_query,
            "start": start,
            "max_results": min(per_page, limit - start),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        text = fetch_text(client, BASE, params=params)
        if not text:
            return
        try:
            root = fromstring(text)
        except _ET.ParseError as e:
            import logging

            logging.getLogger(__name__).warning("arxiv parse error at start=%d: %s", start, e)
            return

        entries = root.findall("atom:entry", NS)
        if not entries:
            return

        count = 0
        for entry in entries:
            paper = _parse_entry(entry)
            if paper:
                yield paper
                count += 1
        if count == 0:
            return
        start += len(entries)
        if len(entries) < per_page:
            return
