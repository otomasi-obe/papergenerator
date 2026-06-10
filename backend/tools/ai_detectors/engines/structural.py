"""Structural engine: em-dash, uniformity, lists, paragraphs, formatting, colons."""

import re
import math
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


class StructuralEngine(BaseEngine):
    name = "structural"
    weight = 0.13

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.word_count < 10:
                return 0.5
            wc = ctx.word_count
            text = ctx.raw
            tl = ctx.text_lower
            score = 0.0

            em_matches = re.findall(r'\w\u2014\w', text)
            em_rate = (len(em_matches) / wc) * 1000
            score += min(em_rate / 6, 1) * 0.08

            slens = [l for l in ctx.sentence_lengths if l >= 3]
            if len(slens) >= 3:
                mean = sum(slens) / len(slens)
                if mean > 0:
                    var = sum((x - mean) ** 2 for x in slens) / len(slens)
                    cv = math.sqrt(var) / mean
                    score += max(0, 1 - cv / 0.6) * 0.08
            else:
                score += 0.04 * 0.08

            lines = text.split('\n')
            list_lines = sum(1 for l in lines if re.match(r'\s*[-*•]|\s*\d+\.', l.strip()))
            list_dens = (list_lines / wc) * 1000
            score += min(list_dens / 30, 1) * 0.12

            plens = [len(p.split()) for p in ctx.paragraphs if len(p.split()) >= 3]
            if len(plens) >= 2:
                pmean = sum(plens) / len(plens)
                if pmean > 0:
                    pvar = sum((x - pmean) ** 2 for x in plens) / len(plens)
                    pcv = math.sqrt(pvar) / pmean
                    score += max(0, 1 - pcv / 0.5) * 0.07
            else:
                score += 0.35 * 0.07

            bold_count = len(re.findall(r'\*\*[^*]+\*\*', text))
            heading_count = sum(1 for l in lines if re.match(r'\s*#+\s', l))
            fmt_dens = ((bold_count + heading_count) / wc) * 1000
            score += min(fmt_dens / 10, 1) * 0.05

            colon_count = tl.count(':')
            colon_dens = (colon_count / wc) * 1000
            score += min(max(colon_dens - 8, 0) / 15, 1) * 0.30

            col_defs = sum(1 for l in lines if re.match(r'\s*\w[\w\s]*:\s+[A-Z(]', l))
            score += min(col_defs / 3, 1) * 0.30

            return clamp(score, 0, 1)
        except Exception:
            log.exception("StructuralEngine error")
            return 0.5
