"""Readability uniformity engine: Flesch Reading Ease CV across chunks."""

import re
import math
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


def _count_syllables(word: str) -> int:
    word = word.lower().strip()
    if not word:
        return 0
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in 'aeiouy'
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if count == 0:
        count = 1
    if word.endswith('e') and count > 1 and not word.endswith('le'):
        count -= 1
    return max(count, 1)


def _flesch_reading_ease(words, syllable_total, sent_count) -> float:
    if sent_count == 0 or len(words) == 0:
        return 0.0
    asl = len(words) / sent_count
    asw = syllable_total / len(words) if len(words) else 0
    return 206.835 - 1.015 * asl - 84.6 * asw


def _split_chunks(text: str, n: int = 4) -> list:
    words = text.split()
    if not words:
        return []
    chunk_size = max(1, len(words) // n)
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(' '.join(words[i:i + chunk_size]))
    return chunks if len(chunks) >= 2 else []


class ReadabilityUniformityEngine(BaseEngine):
    name = "readability"
    weight = 0.07

    def analyze(self, ctx: TextContext) -> float:
        try:
            paragraphs = [p for p in ctx.paragraphs if len(p.split()) >= 15]
            if len(paragraphs) < 3:
                paragraphs = _split_chunks(ctx.raw, 4)
            if len(paragraphs) < 2:
                return 0.5

            fre_scores = []
            for para in paragraphs:
                words = para.split()
                sents = [s.strip() for s in re.split(r'[.!?]+', para) if s.strip()]
                if not sents:
                    continue
                syl_total = sum(_count_syllables(w) for w in words)
                fre = _flesch_reading_ease(words, syl_total, len(sents))
                fre_scores.append(fre)

            if len(fre_scores) < 2:
                return 0.5

            mean = sum(fre_scores) / len(fre_scores)
            if abs(mean) < 1e-9:
                return 0.5
            var = sum((x - mean) ** 2 for x in fre_scores) / len(fre_scores)
            cv = math.sqrt(var) / abs(mean)

            if cv <= 0.05:
                return 1.0
            elif cv >= 0.20:
                return 0.0
            else:
                return 1 - ((cv - 0.05) / 0.15)
        except Exception:
            log.exception("ReadabilityUniformityEngine error")
            return 0.5
