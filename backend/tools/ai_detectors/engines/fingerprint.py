"""Phrase fingerprint engine: regex fingerprints for LLM output."""

import re
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)

_FINGERPRINTS = [
    re.compile(r"deve?lve? into|deeper", re.I),
    re.compile(r"rich tapestry", re.I),
    re.compile(r"in the ever-evolving (?:landscape|world)", re.I),
    re.compile(r"navigat(?:e|ing) the complexit", re.I),
    re.compile(r"it's important to note that", re.I),
    re.compile(r"in conclusion,", re.I),
    re.compile(r"furthermore,", re.I),
    re.compile(r"moreover,", re.I),
    re.compile(r"plays? a (?:crucial|pivotal) role", re.I),
    re.compile(r"(?:unleash|unlock) the (?:power|potential)", re.I),
    re.compile(r"a testament to", re.I),
    re.compile(r"cutting-edge", re.I),
    re.compile(r"game-chang(?:er|ing)", re.I),
    re.compile(r"synerg(?:y|istic)", re.I),
    re.compile(r"holistic approach", re.I),
    re.compile(r"paradigm shift", re.I),
    re.compile(r"multifaceted", re.I),
    re.compile(r"embark on (?:a )?journey", re.I),
    re.compile(r"foster (?:a )?(?:sense|culture)", re.I),
    re.compile(r"as an ai language model", re.I),
    re.compile(r"i cannot provide", re.I),
    re.compile(r"it's worth noting that", re.I),
    re.compile(r"at the forefront", re.I),
    re.compile(r"a myriad of", re.I),
]

_COUNT_MAP = {0: 0.08, 1: 0.45, 2: 0.72, 3: 0.88}


class PhraseFingerprintEngine(BaseEngine):
    name = "fingerprint"
    weight = 0.05

    def analyze(self, ctx: TextContext) -> float:
        try:
            text = ctx.raw
            count = sum(1 for fp in _FINGERPRINTS if fp.search(text))
            if count >= 4:
                return 0.96
            return _COUNT_MAP.get(count, 0.08)
        except Exception:
            log.exception("PhraseFingerprintEngine error")
            return 0.5
