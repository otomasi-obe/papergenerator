"""Human signal engine (adjuster): contractions, first person, slang, parenthetical."""

import re
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)

_CONTRACTION_RE = re.compile(r"\b\w+'\w+\b", re.I)
_FIRST_PERSON = frozenset(["i", "my", "me", "we", "our", "us", "mine", "ours"])
_SLANG = frozenset([
    "gonna", "wanna", "kinda", "sorta", "yeah", "yep", "nope",
    "stuff", "things", "a lot", "etc", "ok", "okay", "hey", "lol",
    "dunno", "gotta", "shoulda", "coulda", "woulda", "nah", "yo",
])
_FORMULAIC_TRANSITIONS = frozenset([
    "furthermore", "moreover", "consequently", "nevertheless",
    "additionally", "subsequently", "henceforth", "thus", "hence",
])
_CONNECTORS = frozenset(["firstly", "secondly", "thirdly", "finally", "lastly"])


class HumanSignalEngine(BaseEngine):
    name = "human_signal"
    weight = 0.0

    def analyze(self, ctx: TextContext) -> float:
        """Return adjustment signal in [-0.15, +0.10]. Negative = more human."""
        try:
            if ctx.word_count < 5:
                return 0.0

            tl = ctx.text_lower
            text = ctx.raw
            human = 0.0
            ai = 0.0

            contractions = len(_CONTRACTION_RE.findall(text))
            if contractions >= 2:
                human += 0.06
            elif contractions >= 1:
                human += 0.03

            first_person = sum(1 for w in ctx.words if w in _FIRST_PERSON)
            if first_person >= 3:
                human += 0.05
            elif first_person >= 1:
                human += 0.02

            slang_count = sum(1 for w in ctx.words if w in _SLANG)
            slang_count += sum(1 for s in ["a lot"] if s in tl)
            if slang_count >= 2:
                human += 0.08
            elif slang_count >= 1:
                human += 0.04

            parenth = text.count('(') + text.count(')') + text.count('\u2014')
            if parenth >= 2:
                human += 0.03

            fm_trans = sum(1 for w in ctx.words if w in _FORMULAIC_TRANSITIONS)
            if fm_trans >= 2:
                ai += 0.08
            elif fm_trans >= 1:
                ai += 0.04

            lines = text.split('\n')
            list_markers = sum(1 for l in lines if re.match(r'\s*[-*•]|\s*\d+\.', l.strip()))
            if list_markers >= 3:
                ai += 0.05

            connectors = sum(1 for w in ctx.words if w in _CONNECTORS)
            if connectors >= 2:
                ai += 0.04

            signal = min(ai, 0.10) - min(human, 0.15)
            return clamp(signal, -0.15, 0.10)
        except Exception:
            log.exception("HumanSignalEngine error")
            return 0.0
