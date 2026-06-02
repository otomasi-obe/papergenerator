"""Fetcher untuk ClinicalKey (Elsevier) - https://www.clinicalkey.com

ClinicalKey is a clinical search engine requiring institutional subscription.
For medical literature, use PubMed/EuropePMC as free alternatives.
"""

import logging
from typing import Iterable

from ..paper import Paper

_warned = False


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """
    ClinicalKey requires institutional subscription.
    For clinical/medical research, use pubmed or europepmc fetchers as alternatives.
    """
    global _warned
    if not _warned:
        logging.getLogger(__name__).info(
            "clinicalkey fetcher skipped: requires institutional subscription. "
            "Use pubmed/europepmc for medical literature."
        )
        _warned = True
    return iter([])
