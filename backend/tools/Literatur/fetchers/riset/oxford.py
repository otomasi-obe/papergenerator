"""Fetcher untuk Oxford Academic - https://academic.oup.com

Oxford Academic content is indexed in Crossref and OpenAlex.
No public search API available for individual researchers.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Oxford Academic doesn't provide a public search API.
    Oxford content is accessible via crossref/openalex fetchers.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "oxford fetcher skipped: no public API available. "
            "Oxford content accessible via crossref/openalex fetchers."
        )
        _warned = True
    return iter([])
