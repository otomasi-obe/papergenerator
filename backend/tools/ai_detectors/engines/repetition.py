"""Repetition engine: bigram and trigram repetition analysis."""

import logging
from collections import Counter
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


class RepetitionEngine(BaseEngine):
    name = "repetition"
    weight = 0.03

    def analyze(self, ctx: TextContext) -> float:
        try:
            words = ctx.words
            n = len(words)
            if n < 20:
                return 0.5

            bigrams = [' '.join(words[i:i + 2]) for i in range(n - 1)]
            bigram_counts = Counter(bigrams)
            bi_repeats = sum(v - 1 for v in bigram_counts.values() if v > 1)
            bi_ratio = bi_repeats / (n - 1) if n > 1 else 0

            if bi_ratio < 0.02:
                bi_score = 0.65
            elif bi_ratio < 0.06:
                bi_score = 0.30
            elif bi_ratio < 0.12:
                bi_score = 0.55
            else:
                bi_score = 0.78

            trigrams = [' '.join(words[i:i + 3]) for i in range(n - 2)]
            tri_counts = Counter(trigrams)
            tri_repeats = sum(v - 1 for v in tri_counts.values() if v > 2)
            tri_ratio = tri_repeats / len(trigrams) if trigrams else 0
            tri_score = clamp(tri_ratio * 1000, 0, 1)

            return (bi_score + tri_score) / 2
        except Exception:
            log.exception("RepetitionEngine error")
            return 0.5
