"""Fetcher untuk EBSCOhost - https://www.ebsco.com

EBSCOhost requires institutional subscription and API access.
This is a stub implementation.
"""

import logging
import os
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    EBSCOhost requires institutional subscription and API credentials.
    Set EBSCO_API_KEY and EBSCO_USER_ID if you have access.
    """
    global _warned
    api_key = os.getenv("EBSCO_API_KEY")
    if not api_key:
        if not _warned:
            logging.getLogger(__name__).info(
                "ebscohost fetcher skipped: requires institutional subscription"
            )
            _warned = True
        return iter([])

    # TODO: Implement EBSCOhost EDS API integration if credentials are available
    logging.getLogger(__name__).warning("EBSCOhost API integration not yet implemented")
    return iter([])
