"""Sentiment hedging engine: hedging, balance, vague positivity, qualifiers."""

import re
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)

_HEDGING = [
    "it's worth noting", "it is worth noting", "it's important to note",
    "it should be noted", "one might argue", "studies suggest",
    "research indicates", "that said", "having said that", "that being said",
]

_VAGUE_POSITIVITY = [
    "incredibly important", "extremely valuable", "truly remarkable",
    "game-changing", "world-class", "powerful tool", "valuable resource",
    "positive impact", "meaningful change",
]

_QUALIFIERS = [
    "perhaps", "possibly", "arguably", "relatively", "somewhat",
    "fairly", "rather", "quite", "generally", "typically",
    "usually", "often",
]

_BALANCE_PATTERNS = [
    re.compile(r"on (?:the )?other hand", re.I),
    re.compile(r"while .{3,40}, .{3,40}", re.I),
    re.compile(r"however,? .{3,40}", re.I),
    re.compile(r"(?:although|though|even though) .{3,40}", re.I),
    re.compile(r"(?:it |one )?could argue", re.I),
    re.compile(r"some .{3,30} (?:while|whereas|but) .{3,30}", re.I),
]

_THIS_THESE = [
    re.compile(r"\bthis (?:approach|method|strategy|technique|framework|model|process|concept|idea|principle)\b", re.I),
    re.compile(r"\bthese (?:approaches|methods|strategies|techniques|frameworks|models|processes|concepts|ideas|principles)\b", re.I),
]


class SentimentHedgingEngine(BaseEngine):
    name = "sentiment"
    weight = 0.07

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.word_count < 10:
                return 0.5
            wc = ctx.word_count
            tl = ctx.text_lower
            score = 0.0

            hedge_count = sum(1 for h in _HEDGING if h in tl)
            hd = (hedge_count / wc) * 1000
            score += min(hd / 4, 1) * 0.30

            balance_count = sum(len(p.findall(ctx.raw)) for p in _BALANCE_PATTERNS)
            score += min(balance_count / 3, 1) * 0.15

            vp_count = sum(1 for vp in _VAGUE_POSITIVITY if vp in tl)
            vp_dens = (vp_count / wc) * 1000
            score += min(vp_dens / 3, 1) * 0.20

            q_count = sum(1 for w in ctx.words if w in _QUALIFIERS)
            q_dens = (q_count / wc) * 1000
            score += clamp((q_dens - 8) / 15, 0, 1) * 0.15

            tt_count = sum(len(p.findall(ctx.raw)) for p in _THIS_THESE)
            score += min(tt_count / 4, 1) * 0.20

            return clamp(score, 0, 1)
        except Exception:
            log.exception("SentimentHedgingEngine error")
            return 0.5
