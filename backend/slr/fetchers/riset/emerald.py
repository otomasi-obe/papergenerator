"""Fetcher untuk Emerald Insight - https://www.emerald.com/insight/

Emerald content is indexed in Crossref and OpenAlex.
No public search API available for individual researchers.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Emerald doesn't provide a public search API.
    Emerald content is accessible via crossref/openalex fetchers.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "emerald fetcher skipped: no public API available. "
            "Emerald content accessible via crossref/openalex fetchers."
        )
        _warned = True
    return iter([])
