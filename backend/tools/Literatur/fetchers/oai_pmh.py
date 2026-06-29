"""DOAB & OAPEN OAI-PMH fetcher — keduanya Dublin Core.

DOAB (Directory of Open Access Books): 90,000+ peer-reviewed OA academic books.
OAPEN Library: OA monographs, strong in humanities & social science.
"""

import logging
import re
from typing import Iterable

from ..http_client import RateLimiter, fetch_text, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

_RECORD_RE = re.compile(
    r"<record>\s*<header[^>]*>.*?</header>\s*<metadata>\s*"
    r"<oai_dc:dc[^>]*>(.*?)</oai_dc:dc>",
    re.DOTALL,
)
_TOKEN_RE = re.compile(r"<resumptionToken[^>]*>(.*?)</resumptionToken>")
_DC_FIELD = re.compile(r"<(dc:\w+)[^>]*>(.*?)</\1>", re.DOTALL)
_YEAR_RE = re.compile(r"(\d{4})")


def _parse_oai_fields(rec_text: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for m in _DC_FIELD.finditer(rec_text):
        key = m.group(1).split(":")[1]
        fields.setdefault(key, []).append(strip_html(m.group(2)))
    return fields


def _parse_oai_paper(fields: dict, source: str) -> Paper | None:
    title = (fields.get("title") or [None])[0]
    if not title:
        return None

    year = None
    for d in fields.get("date") or []:
        m = _YEAR_RE.search(d)
        if m:
            year = int(m.group(1))
            break

    doi = None
    link = None
    for ident in fields.get("identifier") or []:
        if ident.startswith("10.") and "/" in ident:
            doi = ident.split()[0].rstrip(".,;")
        elif ident.startswith("http"):
            link = ident.split()[0]
    if not link and doi:
        link = f"https://doi.org/{doi}"

    return Paper(
        source=source,
        source_id=doi or link or title,
        title=title,
        authors=fields.get("creator") or [],
        abstract=(fields.get("description") or [None])[0],
        year=year,
        venue=None,
        venue_type="book",
        doi=doi,
        url=link,
        pdf_url=link,
        citations=None,
        is_open_access=True,
        type="book",
        publisher=(fields.get("publisher") or [None])[0],
    )


def search_oai(
    client, source: str, oai_url: str, query: str,
    limit: int = 25, extra_params: dict | None = None,
) -> Iterable[Paper]:
    """Generic OAI-PMH fetcher with client-side query filtering."""
    rl = RateLimiter(0.5)
    fetched = 0
    cursor = None

    while fetched < limit:
        rl.wait()
        if cursor:
            params = {"verb": "ListRecords", "resumptionToken": cursor}
        else:
            params = {
                "verb": "ListRecords",
                "metadataPrefix": "oai_dc",
            }
        if extra_params:
            params.update(extra_params)

        text = fetch_text(client, oai_url, params=params)
        if not text:
            return

        records = _RECORD_RE.findall(text)
        if not records and cursor:
            return

        for rec_text in records:
            fields = _parse_oai_fields(rec_text)
            paper = _parse_oai_paper(fields, source)
            if not paper:
                continue

            # client-side query filter
            query_terms = query.lower().split()
            haystack = f"{paper.title} {paper.abstract or ''}".lower()
            if all(t in haystack for t in query_terms):
                yield paper
                fetched += 1
                if fetched >= limit:
                    return

        m = _TOKEN_RE.search(text)
        if m and m.group(1):
            cursor = m.group(1)
        else:
            return


# ── DOAB & OAPEN concrete search functions ────────────────────────────

DOAB_OAI = "https://directory.doabooks.org/oai/request"
OAPEN_OAI = "https://library.oapen.org/oai/request"


def search_doab(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """DOAB (Directory of Open Access Books) — buku akademik OA."""
    return search_oai(
        client, "doab", DOAB_OAI, query, limit,
        extra_params={"set": "DOABBooks"},
    )


def search_oapen(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """OAPEN Library — monograf Open Access, kuat di humanities & social science."""
    return search_oai(client, "oapen", OAPEN_OAI, query, limit)
