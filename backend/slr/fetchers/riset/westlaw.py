"""Fetcher untuk Westlaw - https://www.westlaw.com

Westlaw is a legal research database (Thomson Reuters).
Requires subscription and is focused on legal documents, not academic papers.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Westlaw is a legal research database, not an academic paper database.
    Requires subscription and API access.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "westlaw fetcher skipped: legal database, not for academic papers"
        )
        _warned = True
    return iter([])
