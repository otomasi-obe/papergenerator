"""Fetcher untuk Garuda / SINTA - https://garuda.kemdiktisaintek.go.id

Mengambil daftar paper Indonesia dari index Garuda (operated oleh Kemdiktisaintek)
yang juga jadi sumber data utama SINTA. Search-list halaman HTML, parse + ambil
detail per dokumen.

Karena ini scrape HTML, kita rate-limit 0.6 detik per request, dan kita batasi
detail-fetch sebanyak `limit` paper teratas saja (kalau user butuh banyak,
dia tetap dapat list dari source lain).

Optional: kalau ada `SINTA_OFFLINE_DIR` environment variable yang menunjuk ke
folder berisi `papers.jsonl` (hasil scraping offline), fetcher akan cari di
file itu dulu (cepat, tidak hit network) lalu mundur ke HTTP scrape kalau
hasil offline kurang. Kalau env var tidak diset, offline path dilewati.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Iterable

from ..http_client import RateLimiter, fetch_text, strip_html
from ..paper import Paper

log = logging.getLogger(__name__)

BASE = "https://garuda.kemdiktisaintek.go.id"
SEARCH_URL = f"{BASE}/documents/"

_DETAIL_RE = re.compile(
    r'<a[^>]+class="[^"]*title-article[^"]*"[^>]+href="(/documents/detail/(\d+))"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _parse_search_html(html: str) -> list[tuple[str, str]]:
    """Return [(doc_id, title)] from a Garuda search page."""
    out = []
    for m in _DETAIL_RE.finditer(html):
        doc_id = m.group(2)
        title = strip_html(m.group(3))
        if title:
            out.append((doc_id, title))
    if not out and html and len(html) > 1024:
        log.warning(
            "sinta search parse: 0 hits in %d-byte HTML; layout may have changed", len(html)
        )
    return out


def _parse_detail_html(html: str) -> dict:
    """Lightweight parse of a Garuda detail page.

    We don't import bs4 here to keep SLR dependency-free; regex is sufficient
    for the few fields we need (title, abstract, year, journal, doi via meta).
    """
    abstract = ""
    m = re.search(
        r'<xmp[^>]*class="[^"]*abstract-article[^"]*"[^>]*>(.*?)</xmp>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        abstract = strip_html(m.group(1))

    title = ""
    m = re.search(r"<h3[^>]*>\s*<xmp[^>]*>(.*?)</xmp>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = strip_html(m.group(1))

    year = None
    m = re.search(r"\((\d{4})\)", html)
    if m:
        try:
            year = int(m.group(1))
        except ValueError:
            year = None

    venue = ""
    m = re.search(r'class="j-title"[^>]*>\s*<a[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
    if m:
        venue = strip_html(m.group(1))

    publisher = ""
    m = re.search(
        r'class="j-pub-name"[^>]*>\s*<a[^>]*>\s*(?:<xmp[^>]*>)?(.*?)(?:</xmp>)?\s*</a>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        publisher = strip_html(m.group(1))

    authors: list[str] = []
    for a in re.finditer(
        r"/author/view/\d+[^>]*>(?:<xmp[^>]*>)?(.*?)(?:</xmp>)?</a>",
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        nm = strip_html(a.group(1))
        if nm and nm not in authors and len(authors) < 10:
            authors.append(nm)

    doi = ""
    m = re.search(r"\b10\.\d{4,9}/[^\s\"<]+", html)
    if m:
        doi = m.group(0).rstrip(".,;)").strip()

    # Look for PDF download link
    pdf_url = ""
    # Try to find direct PDF link in the page
    pdf_match = re.search(r'href="([^"]*\.pdf[^"]*)"', html, re.IGNORECASE)
    if pdf_match:
        pdf_url = pdf_match.group(1)
        if not pdf_url.startswith("http"):
            pdf_url = BASE + pdf_url if pdf_url.startswith("/") else BASE + "/" + pdf_url
    
    # Try source_url field
    if not pdf_url:
        source_match = re.search(r'class="[^"]*source-url[^"]*"[^>]*href="([^"]+)"', html, re.IGNORECASE)
        if source_match:
            pdf_url = source_match.group(1)

    if not title and html and len(html) > 1024:
        log.warning(
            "sinta detail parse: no title in %d-byte HTML; layout may have changed", len(html)
        )

    return {
        "title": title,
        "abstract": abstract,
        "year": year,
        "venue": venue,
        "publisher": publisher,
        "authors": authors,
        "doi": doi or None,
        "pdf_url": pdf_url or None,
    }


def _from_offline(query: str, limit: int) -> Iterable[Paper]:
    """Match query against an offline papers.jsonl, if available. Tokenize the
    query and rank candidates by how many tokens hit the title+abstract+keywords."""
    offline = os.getenv("SINTA_OFFLINE_DIR")
    if not offline:
        return
    p = Path(offline) / "papers.jsonl"
    if not p.is_file():
        return
    tokens = [w.lower() for w in query.split() if w.strip()]
    if not tokens:
        return
    threshold = max(1, len(tokens) // 2)
    candidates: list[tuple[int, dict]] = []
    try:
        with p.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                hay = " ".join(
                    [
                        rec.get("title") or "",
                        rec.get("abstract") or "",
                        " ".join(rec.get("keywords") or []),
                    ]
                ).lower()
                hits = sum(1 for t in tokens if t in hay)
                if hits < threshold:
                    continue
                candidates.append((hits, rec))
    except OSError:
        return

    candidates.sort(key=lambda x: x[0], reverse=True)
    yielded = 0
    for _hits, rec in candidates:
        year = None
        y = rec.get("year") or ""
        if isinstance(y, int):
            year = y
        elif isinstance(y, str) and y.isdigit():
            year = int(y)
        yield Paper(
            source="sinta",
            source_id=str(rec.get("doc_id") or ""),
            title=rec.get("title") or "",
            authors=rec.get("authors") or [],
            abstract=rec.get("abstract") or None,
            year=year,
            venue=rec.get("journal_name") or rec.get("journal") or None,
            venue_type="journal",
            doi=(rec.get("doi") or None),
            url=rec.get("garuda_doc_url") or rec.get("view_url") or rec.get("source_url") or None,
            pdf_url=rec.get("source_url") or None,
            citations=None,
            is_open_access=True,
            type="journal-article",
            publisher=rec.get("publisher") or None,
        )
        yielded += 1
        if yielded >= limit:
            return


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Cari paper di Garuda/SINTA berdasarkan keyword.

    Strategi:
    1. Coba offline JSONL kalau tersedia (gratis + super cepat).
    2. Sisanya scrape Garuda search HTML, ambil detail per doc_id.
    """
    yielded = 0
    seen_ids: set[str] = set()

    for paper in _from_offline(query, limit):
        if paper.source_id in seen_ids:
            continue
        seen_ids.add(paper.source_id)
        yield paper
        yielded += 1
        if yielded >= limit:
            return

    if yielded >= limit:
        return

    # HTTP scrape fallback. Garuda mendukung pagination via ?page=N.
    rl = RateLimiter(0.7)
    page = 1
    detail_budget = max(0, limit - yielded)

    while detail_budget > 0 and page <= 5:
        rl.wait()
        text = fetch_text(client, SEARCH_URL, params={"q": query, "page": page})
        if not text:
            return
        hits = _parse_search_html(text)
        if not hits:
            return
        for doc_id, title in hits:
            if detail_budget <= 0:
                return
            if doc_id in seen_ids:
                continue
            rl.wait()
            detail_html = fetch_text(client, f"{BASE}/documents/detail/{doc_id}")
            meta = _parse_detail_html(detail_html or "")
            if not (meta.get("title") or title):
                continue
            seen_ids.add(doc_id)
            
            # Build landing page and PDF URL separately
            landing = f"{BASE}/documents/detail/{doc_id}"
            pdf_url = meta.get("pdf_url") or None
            if not pdf_url and meta.get("doi"):
                pdf_url = f"https://doi.org/{meta.get('doi')}"
            
            yield Paper(
                source="sinta",
                source_id=doc_id,
                title=meta.get("title") or title,
                authors=meta.get("authors") or [],
                abstract=meta.get("abstract") or None,
                year=meta.get("year"),
                venue=meta.get("venue") or None,
                venue_type="journal",
                doi=meta.get("doi"),
                url=landing,
                pdf_url=pdf_url,
                citations=None,
                is_open_access=True,
                type="journal-article",
                publisher=meta.get("publisher") or None,
            )
            detail_budget -= 1
        page += 1
