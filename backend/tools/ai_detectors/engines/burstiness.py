"""Burstiness engine: sentence length coefficient of variation."""

import math
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


class BurstinessEngine(BaseEngine):
    name = "burstiness"
    weight = 0.09

    def analyze(self, ctx: TextContext) -> float:
        try:
            slens = ctx.sentence_lengths
            if len(slens) < 3:
                return 0.5
            mean = sum(slens) / len(slens)
            if mean == 0:
                return 0.5
            var = sum((x - mean) ** 2 for x in slens) / len(slens)
            cv = math.sqrt(var) / mean
            if cv < 0.2:
                return 0.9
            elif cv < 0.4:
                return 0.7
            elif cv < 0.6:
                return 0.4
            elif cv < 0.8:
                return 0.2
            else:
                return 0.1
        except Exception:
            log.exception("BurstinessEngine error")
            return 0.5
