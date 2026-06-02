"""Fetcher untuk ProQuest - https://www.proquest.com

ProQuest requires institutional subscription and API access.
This is a stub implementation.
"""

import logging
import os
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    ProQuest requires institutional subscription and API credentials.
    Set PROQUEST_API_KEY and PROQUEST_API_SECRET if you have access.
    Most ProQuest content is also available via crossref/openalex.
    """
    global _warned
    api_key = os.getenv("PROQUEST_API_KEY")
    if not api_key:
        if not _warned:
            logging.getLogger(__name__).info(
                "proquest fetcher skipped: requires institutional subscription. "
                "ProQuest content may be accessible via crossref/openalex fetchers."
            )
            _warned = True
        return iter([])

    # TODO: Implement ProQuest API integration if credentials are available
    logging.getLogger(__name__).warning("ProQuest API integration not yet implemented")
    return iter([])
