"""Shared helper: enrich paper abstracts via DOI cross-reference to OpenAlex.

OpenAlex exposes abstract_inverted_index which can be reconstructed into
plain text. This is a lightweight fallback for fetchers that have DOIs but
no abstracts (DBLP, Scopus Search, SSRN via Crossref, CrossRef records
where the publisher didn't deposit abstracts).

Usage:
    from ._abstract_enrich import enrich_abstract_via_doi
    abstract = enrich_abstract_via_doi(doi, client)  # returns str or None

    or use the batch version (lightweight, no extra HTTP if no DOI):
    from ._abstract_enrich import enrich_abstracts
    enrich_abstracts(papers, client)  # mutates papers in-place
"""

import logging
import re
from typing import Iterable

from ..http_client import fetch_json
from ..paper import Paper

log = logging.getLogger(__name__)

OPENALEX_WORK = "https://api.openalex.org/works/"
_TAG_RE = re.compile(r"<[^>]+>")


def _reconstruct_abstract(inv_index: dict | None) -> str | None:
    """Reconstruct abstract text from OpenAlex abstract_inverted_index."""
    if not inv_index:
        return None
    pos_map = {}
    for word, positions in inv_index.items():
        for p in positions:
            pos_map[p] = word
    if not pos_map:
        return None
    max_pos = max(pos_map.keys())
    return " ".join(pos_map.get(i, "") for i in range(max_pos + 1)).strip()


def enrich_abstract_via_doi(doi: str, client) -> str | None:
    """Query OpenAlex by DOI and return reconstructed abstract, or None."""
    if not doi:
        return None
    # Normalize: strip prefix
    doi_clean = doi
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if doi_clean.startswith(prefix):
            doi_clean = doi_clean[len(prefix):]
            break
    if not doi_clean:
        return None

    url = f"{OPENALEX_WORK}doi:{doi_clean}"
    try:
        data = fetch_json(client, url)
        if not data:
            return None
        inv = data.get("abstract_inverted_index")
        abstract = _reconstruct_abstract(inv)
        if abstract:
            # Strip any HTML/XML tags (rare but possible)
            abstract = _TAG_RE.sub(" ", abstract)
            abstract = " ".join(abstract.split()).strip()
        return abstract or None
    except Exception as e:
        log.debug("Abstract enrichment failed for DOI %s: %s", doi_clean, e)
        return None


def enrich_abstracts(papers: Iterable[Paper], client) -> int:
    """Enrich papers with missing abstracts via DOI → OpenAlex.

    Mutates papers in-place. Returns number of papers enriched.
    """
    count = 0
    for paper in papers:
        if not paper.abstract and paper.doi:
            abstract = enrich_abstract_via_doi(paper.doi, client)
            if abstract:
                paper.abstract = abstract
                count += 1
    return count