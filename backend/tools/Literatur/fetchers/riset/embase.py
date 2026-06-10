"""Fetcher untuk Embase (Elsevier) - https://www.embase.com

Embase is a biomedical database requiring institutional subscription.
For medical literature, use PubMed/EuropePMC as free alternatives.
"""

import logging
import os
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    Embase requires institutional subscription and Elsevier API credentials.
    For biomedical research, use pubmed or europepmc fetchers as alternatives.
    """
    global _warned
    api_key = os.getenv("ELSEVIER_API_KEY")
    if not api_key:
        if not _warned:
            logging.getLogger(__name__).info(
                "embase fetcher skipped: requires institutional subscription. "
                "Use pubmed/europepmc for biomedical literature."
            )
            _warned = True
        return iter([])

    # TODO: Implement Embase API integration if institutional access is available
    logging.getLogger(__name__).warning("Embase API integration not yet implemented")
    return iter([])
