"""Syntactic uniformity engine: unique sentence-starters ratio."""

import re
import logging
from collections import Counter
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


class SyntacticUniformityEngine(BaseEngine):
    name = "syntactic"
    weight = 0.03

    def analyze(self, ctx: TextContext) -> float:
        try:
            first_words = []
            for sent in ctx.sentences:
                words = sent.split()
                if words:
                    fw = words[0].lower().rstrip(',;:')
                    first_words.append(fw)
            total = len(first_words)
            if total < 2:
                return 0.5
            unique = len(set(first_words))
            ratio = unique / total
            if ratio > 0.85:
                return 0.10
            elif ratio > 0.70:
                return 0.30
            elif ratio > 0.55:
                return 0.55
            else:
                return 0.80
        except Exception:
            log.exception("SyntacticUniformityEngine error")
            return 0.5
