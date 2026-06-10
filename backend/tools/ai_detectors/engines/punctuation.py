"""Punctuation engine: em-dash, oxford comma, semicolon, colon density."""

import re
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


class PunctuationEngine(BaseEngine):
    name = "punctuation"
    weight = 0.01

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.word_count < 10:
                return 0.5
            wc = ctx.word_count
            text = ctx.raw

            em_count = text.count('\u2014') + text.count('--')
            em_dens = (em_count / wc) * 1000
            em_score = clamp(em_dens / 10, 0, 1)

            oxford_matches = re.findall(r',\s+\w+\s*,\s+\w+\s+and\b', text)
            oxford_matches2 = re.findall(r',\s+\w+\s*,\s+\w+\s+or\b', text)
            oxford_rate = ((len(oxford_matches) + len(oxford_matches2)) / max(ctx.sentence_count, 1)) * 100
            oxford_score = clamp(oxford_rate / 30, 0, 1)

            semi_count = text.count(';')
            semi_dens = (semi_count / wc) * 1000
            semi_score = clamp(semi_dens / 5, 0, 1)

            colon_count = text.count(':')
            colon_dens = (colon_count / wc) * 1000
            colon_score = clamp(colon_dens / 15, 0, 1)

            avg = (em_score + oxford_score + semi_score + colon_score) / 4
            return clamp(avg, 0, 1)
        except Exception:
            log.exception("PunctuationEngine error")
            return 0.5
