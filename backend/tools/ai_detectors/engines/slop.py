"""Slop word engine: density of AI slop words/phrases from JSON + internal dict."""

import json
import logging
from pathlib import Path
from collections import Counter
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent.parent

_SEVERITY_INTERNAL = {
    "high": ["delve", "tapestry", "multifaceted", "ever-evolving", "leverage",
             "paradigm", "synergy", "holistic", "groundbreaking", "game-changer",
             "cutting-edge", "revolutionize", "foster", "navigate", "underscore"],
    "medium": ["robust", "comprehensive", "pivotal", "nuanced", "cornerstone",
               "streamline", "optimize", "empower", "transformative", "ecosystem",
               "seamless", "seamlessly", "framework", "methodology"],
    "low": ["enhance", "dynamic", "innovative", "stakeholder", "actionable",
            "furthermore", "moreover", "consequently", "however"],
}


class SlopWordEngine(BaseEngine):
    name = "slop"
    weight = 0.07

    def __init__(self):
        self._slop_set = set()
        self._phrases = []
        try:
            with open(_DIR / "ai_slop_words.json", encoding="utf-8") as f:
                data = json.load(f)
            for w in data.get("single_words", []):
                self._slop_set.add(w.lower())
            for p in data.get("phrases", []):
                p_lower = p.lower()
                self._slop_set.add(p_lower)
                if ' ' in p_lower:
                    self._phrases.append(p_lower)
        except Exception:
            log.warning("Could not load ai_slop_words.json, using internal dict only")
        for severity_words in _SEVERITY_INTERNAL.values():
            self._slop_set.update(w.lower() for w in severity_words)

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.word_count < 5:
                return 0.5
            wc = ctx.word_count
            tl = ctx.text_lower
            found = sum(1 for w in ctx.words if w in self._slop_set)
            found += sum(1 for p in self._phrases if p in tl)
            density = (found / wc) * 1000
            return clamp(density / 6.67, 0, 1)
        except Exception:
            log.exception("SlopWordEngine error")
            return 0.5
