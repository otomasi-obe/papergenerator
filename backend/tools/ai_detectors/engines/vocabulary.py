"""Vocabulary richness engine: TTR, hapax ratio, Yule's K."""

import logging
from collections import Counter
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


class VocabularyRichnessEngine(BaseEngine):
    name = "vocabulary"
    weight = 0.11

    def analyze(self, ctx: TextContext) -> float:
        try:
            total = ctx.word_count
            if total < 30:
                return 0.5
            unique = ctx.unique_word_count
            freq = ctx.word_freq
            root_ttr = unique / (total ** 0.5)
            ttr_score = clamp(1 - ((root_ttr - 3.5) / 4), 0, 1)

            hapax = sum(1 for v in freq.values() if v == 1)
            hapax_ratio = hapax / unique if unique else 0
            hapax_score = clamp(1 - ((hapax_ratio - 0.3) / 0.4), 0, 1)

            m1 = total
            freq_of_freq = Counter(freq.values())
            m2 = sum(i * i * c for i, c in freq_of_freq.items())
            denom = m1 * m1
            if denom == 0:
                yules_k = 0
            else:
                yules_k = 10000 * (m2 - m1) / denom
            k_score = clamp((yules_k - 80) / 120, 0, 1)

            return ttr_score * 0.35 + hapax_score * 0.35 + k_score * 0.30
        except Exception:
            log.exception("VocabularyRichnessEngine error")
            return 0.5
