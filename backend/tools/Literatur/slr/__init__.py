"""SLR Toolkit — Systematic Literature Review dengan Active Learning.

Modul-modul:
- screening:   SPECTER2 + SVM active learning loop, stopping rule, WSS@95
- dedup:       DOI exact + Jaro-Winkler fuzzy deduplication
- snowball:    Citation graph snowballing (backward refs + forward citations)
- extraction:  Anti-hallucination data extraction + Crossref verification
- llm_review:  LLM-assisted title-abstract review (opsional, VIOLA-CHAT)

Semua modul bisa dipakai standalone atau diintegrasikan via slr_api.py.
"""

from .screening import (
    ScreeningState,
    ScreeningResult,
    ActiveScreener,
    StoppingRule,
    compute_wss95,
)
from .dedup import Deduplicator, deduplicate
from .snowball import Snowballer, SnowballResult
from .extraction import DataExtractor, ExtractionResult, verify_reference

__all__ = [
    # screening
    "ScreeningState",
    "ScreeningResult",
    "ActiveScreener",
    "StoppingRule",
    "compute_wss95",
    # dedup
    "Deduplicator",
    "deduplicate",
    # snowball
    "Snowballer",
    "SnowballResult",
    # extraction
    "DataExtractor",
    "ExtractionResult",
    "verify_reference",
]