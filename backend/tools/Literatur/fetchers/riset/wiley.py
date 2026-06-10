"""Fetcher untuk Wiley Online Library - https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining

Wiley doesn't have a public search API. This fetcher uses web scraping as fallback.
For production use, consider institutional access or Crossref/OpenAlex as alternatives.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Wiley doesn't provide a public search API.
    Wiley content is available through Crossref and OpenAlex fetchers.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "wiley fetcher skipped: no public API available. "
            "Wiley content accessible via crossref/openalex fetchers."
        )
        _warned = True
    return iter([])
