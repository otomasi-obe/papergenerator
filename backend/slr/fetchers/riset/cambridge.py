"""Fetcher untuk Cambridge Core - https://www.cambridge.org/core

Cambridge Core content is indexed in Crossref and OpenAlex.
No public search API available for individual researchers.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Cambridge Core doesn't provide a public search API.
    Cambridge content is accessible via crossref/openalex fetchers.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "cambridge fetcher skipped: no public API available. "
            "Cambridge content accessible via crossref/openalex fetchers."
        )
        _warned = True
    return iter([])
