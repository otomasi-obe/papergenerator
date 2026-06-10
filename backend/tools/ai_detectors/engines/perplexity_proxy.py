"""Perplexity proxy engine: character bigram entropy."""

import math
import logging
from collections import Counter
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


class PerplexityProxyEngine(BaseEngine):
    name = "perplexity_proxy"
    weight = 0.02

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.char_count < 50:
                return 0.5
            tl = ctx.text_lower
            bigrams = [tl[i:i + 2] for i in range(len(tl) - 1)]
            if not bigrams:
                return 0.5
            counts = Counter(bigrams)
            total = len(bigrams)
            entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
            if entropy < 3.0:
                return 0.85
            elif entropy < 3.5:
                return 0.65
            elif entropy < 4.0:
                return 0.40
            else:
                return 0.20
        except Exception:
            log.exception("PerplexityProxyEngine error")
            return 0.5
