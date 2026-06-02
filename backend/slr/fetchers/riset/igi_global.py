"""Fetcher untuk IGI Global - https://www.igi-global.com

IGI Global specializes in information science and technology research.
Requires subscription for full access.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    IGI Global doesn't provide a public search API.
    IGI Global content may be accessible via crossref/openalex fetchers.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "igi_global fetcher skipped: no public API available. "
            "IGI Global content may be accessible via crossref/openalex fetchers."
        )
        _warned = True
    return iter([])
