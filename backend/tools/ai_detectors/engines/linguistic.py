"""Linguistic marker engine: weighted AI-buzzword density."""

import re
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)

_MARKERS_W3 = [
    "delve", "tapestry", "multifaceted", "ever-evolving", "thought-provoking",
    "it's important to note", "it's worth noting",
    "in today's digital age", "let's dive in",
]

_MARKERS_W2 = [
    "landscape", "navigate", "leverage", "foster", "pivotal", "nuanced",
    "robust", "holistic", "synergy", "paradigm", "encompass", "intricate",
    "comprehensive", "underscores", "underscore", "realm", "cornerstone",
    "facilitating", "harnessing", "revolutionize", "groundbreaking",
    "cutting-edge", "game-changer",
    "deep dive", "at the forefront", "at its core", "in the realm of",
    "it is crucial", "it is essential",
    "plays a crucial role", "a testament to", "a myriad of", "plethora",
]

_MARKERS_W1 = [
    "crucial", "enhance", "dynamic", "innovative", "streamline", "optimize",
    "elevate", "empower", "stakeholder", "ecosystem", "actionable",
    "seamless", "seamlessly", "furthermore", "moreover", "consequently",
    "nevertheless",
    "in conclusion", "ultimately", "in essence", "not only", "but also",
    "on the other hand", "resonate", "aligns with", "bolster", "catalyst",
    "testament", "arguably", "notably", "specifically", "essentially",
    "fundamentally", "inherently",
]


class LinguisticMarkerEngine(BaseEngine):
    name = "linguistic"
    weight = 0.16

    def __init__(self):
        self._patterns = []
        for marker in _MARKERS_W3:
            self._patterns.append((re.compile(r'\b' + re.escape(marker) + r'\b', re.IGNORECASE), 3))
        for marker in _MARKERS_W2:
            self._patterns.append((re.compile(r'\b' + re.escape(marker) + r'\b', re.IGNORECASE), 2))
        for marker in _MARKERS_W1:
            self._patterns.append((re.compile(r'\b' + re.escape(marker) + r'\b', re.IGNORECASE), 1))

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.word_count < 5:
                return 0.5
            total_weight = 0
            for pat, w in self._patterns:
                count = len(pat.findall(ctx.text_lower))
                if count:
                    total_weight += count * w
            density = (total_weight / ctx.word_count) * 1000
            return clamp(density / 15, 0, 1)
        except Exception:
            log.exception("LinguisticMarkerEngine error")
            return 0.5
