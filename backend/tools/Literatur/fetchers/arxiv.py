"""Fetcher untuk arXiv - https://export.arxiv.org/api/query

Keyless. Rate limit ketipis dengan retry + backoff + proxy rotation.
Sesuai format Paper dataclass.
"""

import re
import time
import logging
import xml.etree.ElementTree as _ET
from typing import Iterable

from defusedxml.ElementTree import fromstring

from ..http_client import RateLimiter, fetch_text, get_client, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# ── Category mapping ─────────────────────────────────────────────────────

_ARXIV_CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "cs.AI": ("Artificial Intelligence", "cs.AI"),
    "cs.CL": ("Computation and Language", "cs.CL"),
    "cs.CV": ("Computer Vision", "cs.CV"),
    "cs.LG": ("Machine Learning", "cs.LG"),
    "cs.RO": ("Robotics", "cs.RO"),
    "cs.NE": ("Neural and Evolutionary Computing", "cs.NE"),
    "cs.AS": ("Audio and Speech Processing", "cs.AS"),
    "cs.CR": ("Cryptography and Security", "cs.CR"),
    "cs.DS": ("Data Structures and Algorithms", "cs.DS"),
    "cs.SE": ("Software Engineering", "cs.SE"),
    "cs.SY": ("Systems and Control", "cs.SY"),
    "cs.IR": ("Information Retrieval", "cs.IR"),
    "cs.HC": ("Human-Computer Interaction", "cs.HC"),
    "cs.MA": ("Multiagent Systems", "cs.MA"),
    "cs.GT": ("Computer Science and Game Theory", "cs.GT"),
    "cs.DL": ("Digital Libraries", "cs.DL"),
    "stat.ML": ("Machine Learning (Stats)", "stat.ML"),
    "stat.ME": ("Methodology (Stats)", "stat.ME"),
    "math.OC": ("Optimization and Control", "math.OC"),
    "physics.comp-ph": ("Computational Physics", "physics.comp-ph"),
    "quant-ph": ("Quantum Physics", "quant-ph"),
    "eess.SP": ("Signal Processing", "eess.SP"),
    "eess.IV": ("Image and Video Processing", "eess.IV"),
}


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_links(entry: _ET.Element) -> tuple[str | None, str | None]:
    landing_url: str | None = None
    pdf_url: str | None = None
    for link_el in entry.findall("atom:link", NS):
        rel = link_el.get("rel", "")
        title = link_el.get("title", "")
        href = link_el.get("href", "")
        if not href:
            continue
        if rel == "alternate" and landing_url is None:
            landing_url = href
        elif title == "pdf" and pdf_url is None:
            pdf_url = href
    return landing_url, pdf_url


def _parse_categories(entry: _ET.Element) -> tuple[list[str] | None, list[str] | None]:
    fields_of_study: set[str] = set()
    subjects: set[str] = set()
    for cat_el in entry.findall("atom:category", NS):
        term = (cat_el.get("term") or "").strip()
        if not term or term not in _ARXIV_CATEGORY_MAP:
            continue
        field, subject = _ARXIV_CATEGORY_MAP[term]
        fields_of_study.add(field)
        subjects.add(subject)
    return (
        sorted(fields_of_study) if fields_of_study else None,
        sorted(subjects) if subjects else None,
    )


def _parse_affiliations(entry: _ET.Element) -> list[str] | None:
    affiliations: list[str] = []
    for author_el in entry.findall("atom:author", NS):
        for aff_el in author_el.findall("arxiv:affiliation", NS):
            aff = (aff_el.text or "").strip()
            if aff and aff not in affiliations:
                affiliations.append(aff)
    return affiliations or None


def _parse_entry(entry: _ET.Element) -> Paper | None:
    title_el = entry.find("atom:title", NS)
    title_raw = (title_el.text or "") if title_el is not None else ""
    if not title_raw.strip():
        return None
    title = _normalize_ws(title_raw)

    summary_el = entry.find("atom:summary", NS)
    abstract_raw = (summary_el.text or "") if summary_el is not None else None
    abstract = _normalize_ws(abstract_raw) if abstract_raw else None

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

    landing_url, pdf_url = _parse_links(entry)
    if not landing_url and arxiv_id:
        landing_url = f"https://arxiv.org/abs/{arxiv_id}"
    if not pdf_url and arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    comment = None
    comment_el = entry.find("arxiv:comment", NS)
    if comment_el is not None:
        comment = (comment_el.text or "").strip() or None

    fields_of_study, subjects = _parse_categories(entry)
    affiliations = _parse_affiliations(entry)

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
        comment=comment,
        fields_of_study=fields_of_study,
        subjects=subjects,
        affiliations=affiliations,
    )


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search arXiv API. Keyless. Rate limit 5s + retry 7x + backoff.

    Args:
        client: httpx.Client (supports proxy rotation).
        limit: Max results (capped at 30000 via MAX_PAGES).
        filters: Optional dict with keys:
            - category (str): arxiv category code (e.g. "cs.AI")
            - submitted_date_from / submitted_date_to (date or str)
    """
    # arXiv recommends 3s, we use 5s to be safe with shared IP
    rl = RateLimiter(5.0)
    per_page = min(limit, 200)
    start = 0
    empty_streak = 0
    MAX_PAGES = 150  # 150 * 200 = 30000 max
    CONSEC_EMPTY = 10

    search_query = f"all:{query}"
    if filters and "category" in filters:
        search_query = f"({search_query}) AND cat:{filters['category']}"

    if filters:
        date_from = filters.get("submitted_date_from")
        date_to = filters.get("submitted_date_to")
        if date_from or date_to:
            from_str = _format_submitted_date(date_from) if date_from else "199101010000"
            to_str = _format_submitted_date(date_to) if date_to else "999912312359"
            date_filter = f"submittedDate:[{from_str} TO {to_str}]"
            search_query = f"({search_query}) AND {date_filter}"

    while start < limit:
        rl.wait()
        page = start // per_page
        page_size = min(per_page, limit - start)

        params = {
            "search_query": search_query,
            "start": start,
            "max_results": page_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        text = None
        for attempt in range(7):
            try:
                text = fetch_text(client, BASE, params=params)
                if text:
                    break
            except Exception as e:
                wait = min(15 * (2 ** attempt), 120)
                log.warning("arxiv fetch err [attempt %d/7]: %s | wait %ds", attempt + 1, e, wait)
                time.sleep(wait)

        if not text:
            log.warning("arxiv: FAILED at start=%d, skip", start)
            break

        try:
            root = fromstring(text)
        except _ET.ParseError as e:
            log.warning("arxiv parse error at start=%d: %s", start, e)
            break

        entries = root.findall("atom:entry", NS)
        if not entries:
            empty_streak += 1
            if empty_streak >= CONSEC_EMPTY:
                log.info("arxiv: %d consecutive empty pages → stop", CONSEC_EMPTY)
                break
            start += per_page
            continue

        empty_streak = 0
        count = 0
        for entry in entries:
            paper = _parse_entry(entry)
            if paper:
                yield paper
                count += 1

        start += len(entries)
        if len(entries) < per_page:
            break
        if page + 1 >= MAX_PAGES:
            log.info("arxiv: max pages (%d) reached", MAX_PAGES)
            break


def _format_submitted_date(value) -> str:
    if isinstance(value, str):
        return value.replace("-", "") + "0000"
    return value.strftime("%Y%m%d") + "0000"
