"""Unpaywall PDF resolver.

Uses the Unpaywall API (https://unpaywall.org/products/api) to find
open-access PDF URLs for papers by DOI. Free for non-commercial use;
requires only an email in the request.

Also provides a batch resolution function that enriches Paper objects
with pdf_url when they have a DOI but no pdf_url yet.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterable

from .http_client import fetch_json, get_client
from .paper import Paper

log = logging.getLogger(__name__)

UNPAYWALL_BASE = "https://api.unpaywall.org/v2/{doi}"
_UNPAYWALL_EMAIL = os.getenv("SLR_CONTACT_EMAIL") or os.getenv("UNPAYWALL_EMAIL") or "research@example.com"
_BATCH_DELAY = 0.12


def resolve_pdf_url(doi: str) -> str | None:
    """Resolve the best OA PDF URL for a DOI via Unpaywall.

    Returns the direct PDF URL or None if not found.
    """
    if not doi:
        return None
    clean = doi.strip()
    if clean.startswith("https://doi.org/"):
        clean = clean[len("https://doi.org/"):]
    if clean.startswith("http://doi.org/"):
        clean = clean[len("http://doi.org/"):]

    url = UNPAYWALL_BASE.format(doi=clean)
    try:
        with get_client() as client:
            data = fetch_json(client, url, params={"email": _UNPAYWALL_EMAIL})
    except Exception as e:
        log.debug("unpaywall resolve error doi=%s: %s", clean[:40], e)
        return None

    if not data:
        return None

    best = data.get("best_oa_location")
    if best:
        pdf = best.get("url_for_pdf") or best.get("url")
        if pdf and pdf.endswith(".pdf"):
            return pdf

    for loc in data.get("oa_locations", []):
        pdf = loc.get("url_for_pdf")
        if pdf:
            return pdf

    for loc in data.get("oa_locations", []):
        url_val = loc.get("url", "")
        if url_val and ".pdf" in url_val.lower():
            return url_val

    return None


def batch_resolve_pdf_urls(papers: list[Paper], delay: float = _BATCH_DELAY) -> int:
    """Enrich papers with pdf_url from Unpaywall where missing.

    Only papers that have a doi but no pdf_url are looked up.
    Returns the number of papers that got a pdf_url resolved.

    Rate-limited to avoid hammering the Unpaywall API:
    ~8 requests/second max with default delay.
    """
    resolved = 0
    targets = [p for p in papers if p.doi and not p.pdf_url]
    if not targets:
        return 0

    log.info("unpaywall.batch_resolve: %d papers to look up", len(targets))
    for paper in targets:
        try:
            pdf = resolve_pdf_url(paper.doi)
            if pdf:
                paper.pdf_url = pdf
                resolved += 1
        except Exception as e:
            log.debug("unpaywall.batch error doi=%s: %s", (paper.doi or "")[:40], e)
        time.sleep(delay)

    log.info("unpaywall.batch_resolve: resolved %d/%d pdf urls", resolved, len(targets))
    return resolved


def enrich_papers_without_pdf(papers: list[dict]) -> int:
    """Enrich raw paper dicts with pdf_url via Unpaywall.

    For use after the SLR pipeline produces its top_k list but before
    persisting to the DB. Only resolves papers that have a 'doi' but
    no 'pdf_url' or an empty 'pdf_url'.
    """
    targets = [p for p in papers if p.get("doi") and not p.get("pdf_url")]
    if not targets:
        return 0

    resolved = 0
    for rec in targets:
        try:
            pdf = resolve_pdf_url(rec["doi"])
            if pdf:
                rec["pdf_url"] = pdf
                resolved += 1
        except Exception:
            pass
        time.sleep(_BATCH_DELAY)

    return resolved
