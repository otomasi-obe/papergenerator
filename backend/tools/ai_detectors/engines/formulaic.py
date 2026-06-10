"""Formulaic engine: openers, closers, fillers, starter rep, heading-bullet."""

import re
import logging
from collections import Counter
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)

_OPENERS = [
    re.compile(r"in today's (?:rapidly )?(?:evolving|changing|digital|modern)", re.I),
    re.compile(r"when it comes to", re.I),
    re.compile(r"in the realm of", re.I),
    re.compile(r"let's (?:dive|explore|unpack)", re.I),
    re.compile(r"it is (?:important|worth|crucial|essential) to", re.I),
    re.compile(r"understanding (?:the |these )?(?:key |critical |crucial )?(?:concepts|principles|differences|factors)", re.I),
    re.compile(r"in this (?:article|post|guide|section|chapter)", re.I),
    re.compile(r"(?:as we|before we) (?:dive|explore|delve|begin)", re.I),
]

_CLOSERS = [
    re.compile(r"in conclusion", re.I),
    re.compile(r"in summary|to summarize|to sum up", re.I),
    re.compile(r"ultimately|at the end of the day", re.I),
    re.compile(r"as we (?:navigate|move forward|look ahead)", re.I),
    re.compile(r"(?:it is|it's) clear that", re.I),
    re.compile(r"by (?:understanding|leveraging|embracing)", re.I),
]

_FILLERS = [
    re.compile(r"not only.{3,60}but also", re.I | re.DOTALL),
    re.compile(r"(?:it's|it is) (?:important|worth|crucial|essential) to (?:note|remember|consider)", re.I),
    re.compile(r"first and foremost", re.I),
    re.compile(r"last but not least", re.I),
    re.compile(r"needless to say", re.I),
    re.compile(r"it goes without saying", re.I),
    re.compile(r"(?:it's|it is) worth (?:noting|mentioning)", re.I),
    re.compile(r"(?:it should|this should) be noted", re.I),
]


class FormulaicEngine(BaseEngine):
    name = "formulaic"
    weight = 0.13

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.word_count < 10:
                return 0.5
            wc = ctx.word_count
            text = ctx.raw
            score = 0.0

            first300 = text[:300]
            opener_hit = 1 if any(p.search(first300) for p in _OPENERS) else 0
            score += opener_hit * 0.20

            last400 = text[-400:] if len(text) >= 400 else text
            closer_hit = 1 if any(p.search(last400) for p in _CLOSERS) else 0
            score += closer_hit * 0.15

            filler_count = sum(len(p.findall(text)) for p in _FILLERS)
            filler_dens = (filler_count / wc) * 1000
            score += min(filler_dens / 5, 1) * 0.30

            first_words = []
            for sent in ctx.sentences:
                words = sent.split()
                if words:
                    first_words.append(words[0].lower())
            if len(first_words) >= 2:
                fw_counts = Counter(first_words)
                repeated = sum(1 for v in fw_counts.values() if v > 1)
                repeat_ratio = repeated / len(first_words)
                starter_rep = clamp((repeat_ratio - 0.55) / 0.25, 0, 1)
                score += starter_rep * 0.05

            lines = [l for l in text.split('\n') if l.strip()]
            hb_sections = 0
            for i, line in enumerate(lines):
                if re.match(r'\s*#{1,6}\s', line) or (len(line.split()) <= 6 and not line.startswith(('-','*','•'))):
                    bullets = 0
                    for j in range(i + 1, min(i + 6, len(lines))):
                        if re.match(r'\s*[-*•]', lines[j]):
                            bullets += 1
                    if bullets >= 2:
                        hb_sections += 1
            score += min(hb_sections / 3, 1) * 0.30

            return clamp(score, 0, 1)
        except Exception:
            log.exception("FormulaicEngine error")
            return 0.5
