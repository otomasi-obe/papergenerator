"""Fetcher untuk JSTOR - https://about.jstor.org/whats-in-jstor/text-mining-support/

JSTOR requires institutional access for full-text and metadata access.
For research purposes, use JSTOR Data for Research (DfR) service.
This is a stub implementation - JSTOR content is better accessed via Crossref.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    JSTOR doesn't provide a public search API for individual researchers.
    JSTOR content is indexed in Crossref and OpenAlex.
    For institutional access, use JSTOR Data for Research (DfR).
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "jstor fetcher skipped: requires institutional access. "
            "JSTOR content accessible via crossref/openalex fetchers."
        )
        _warned = True
    return iter([])
