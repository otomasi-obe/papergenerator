"""Fetcher untuk Taylor & Francis - https://www.tandfonline.com

Taylor & Francis content is indexed in Crossref and OpenAlex.
No public search API available for individual researchers.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Taylor & Francis doesn't provide a public search API.
    T&F content is accessible via crossref/openalex fetchers.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "taylor_francis fetcher skipped: no public API available. "
            "T&F content accessible via crossref/openalex fetchers."
        )
        _warned = True
    return iter([])
