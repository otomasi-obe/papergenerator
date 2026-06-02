"""Fetcher untuk McGraw Hill - https://www.mheducation.com

McGraw Hill is primarily an educational publisher.
No public search API available.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    McGraw Hill doesn't provide a public search API for academic papers.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "mcgrawhill fetcher skipped: no public API available for academic papers"
        )
        _warned = True
    return iter([])
