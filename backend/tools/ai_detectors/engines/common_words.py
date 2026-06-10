"""Common word engine: ratio of top-67 common English words."""

import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)

_COMMON_67 = frozenset([
    "the", "of", "and", "to", "a", "in", "is", "it", "that", "was",
    "he", "for", "on", "are", "with", "as", "i", "his", "they", "be",
    "at", "one", "have", "this", "from", "or", "had", "by", "hot", "but",
    "what", "some", "we", "can", "out", "other", "were", "all", "there",
    "when", "up", "use", "your", "how", "said", "an", "each", "she",
    "which", "do", "their", "time", "if", "will", "way", "about", "many",
    "then", "them", "write", "would", "like", "so", "these", "her", "long",
    "make", "thing", "see", "him", "two", "has", "look",
])


class CommonWordEngine(BaseEngine):
    name = "common_words"
    weight = 0.03

    def analyze(self, ctx: TextContext) -> float:
        try:
            total = ctx.word_count
            if total < 5:
                return 0.5
            count = sum(1 for w in ctx.words if w in _COMMON_67)
            ratio = count / total
            if ratio < 0.40:
                return 0.10
            elif ratio < 0.50:
                return 0.30
            elif ratio < 0.58:
                return 0.55
            elif ratio < 0.66:
                return 0.78
            else:
                return 0.90
        except Exception:
            log.exception("CommonWordEngine error")
            return 0.5
