"""Semantic coherence analysis engine: detects overly uniform semantic flow typical of AI text.

AI-generated text tends to maintain a uniformly coherent, linear flow — each sentence
follows logically from the previous one with smooth transitions. Human writing, by
contrast, contains natural digressions, topic shifts, tangents, and abrupt changes in
direction that reflect genuine thought processes.

This engine measures several proxies for semantic flow uniformity:
  - Lexical overlap between consecutive sentences (AI: high overlap, smooth topic drift)
  - Topic shift frequency (AI: few abrupt shifts, human: more variation)
  - Transition smoothness (AI: uniform transition patterns)
  - Paragraph cohesion variance (AI: low variance, human: high variance)
"""

import re
import math
import logging
from collections import Counter
from typing import List
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)


def _word_set(text: str) -> set:
    return set(re.findall(r'\b[a-z]+\b', text.lower()))


def _bigrams(words: List[str]) -> List[str]:
    return [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def _cosine_sim(counter_a: Counter, counter_b: Counter) -> float:
    shared = set(counter_a.keys()) & set(counter_b.keys())
    dot = sum(counter_a[k] * counter_b[k] for k in shared)
    mag_a = math.sqrt(sum(v ** 2 for v in counter_a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in counter_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class SemanticCoherenceEngine(BaseEngine):
    """Detects overly uniform semantic flow patterns typical of AI text."""

    name = "semantic_coherence"
    weight = 0.06

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.sentence_count < 4 or ctx.word_count < 40:
                return 0.5

            sentences = ctx.sentences
            sent_word_sets = [_word_set(s) for s in sentences]
            sent_word_lists = [re.findall(r'\b[a-z]+\b', s.lower()) for s in sentences]

            sentence_overlaps = []
            for i in range(len(sentences) - 1):
                overlap = _jaccard(sent_word_sets[i], sent_word_sets[i + 1])
                sentence_overlaps.append(overlap)

            overlap_mean = (
                sum(sentence_overlaps) / len(sentence_overlaps)
                if sentence_overlaps else 0.5
            )
            overlap_var = (
                sum((o - overlap_mean) ** 2 for o in sentence_overlaps)
                / len(sentence_overlaps)
                if sentence_overlaps else 0.0
            )

            bigram_counters = [Counter(_bigrams(ws)) for ws in sent_word_lists if len(ws) >= 2]
            bigram_sims = []
            for i in range(len(bigram_counters) - 1):
                sim = _cosine_sim(bigram_counters[i], bigram_counters[i + 1])
                bigram_sims.append(sim)

            bigram_sim_mean = (
                sum(bigram_sims) / len(bigram_sims) if bigram_sims else 0.5
            )
            bigram_sim_var = (
                sum((s - bigram_sim_mean) ** 2 for s in bigram_sims)
                / len(bigram_sims)
                if bigram_sims else 0.0
            )

            topic_shift_count = sum(1 for o in sentence_overlaps if o < 0.05)
            topic_shift_ratio = topic_shift_count / max(len(sentence_overlaps), 1)

            paragraph_cohesions = []
            for para in ctx.paragraphs:
                para_sents = [s.strip() for s in re.split(r'[.!?]+', para) if s.strip()]
                if len(para_sents) < 2:
                    continue
                para_sets = [_word_set(s) for s in para_sents]
                para_overlaps = [
                    _jaccard(para_sets[j], para_sets[j + 1])
                    for j in range(len(para_sents) - 1)
                ]
                if para_overlaps:
                    paragraph_cohesions.append(
                        sum(para_overlaps) / len(para_overlaps)
                    )

            para_cohesion_var = 0.0
            if len(paragraph_cohesions) >= 2:
                pc_mean = sum(paragraph_cohesions) / len(paragraph_cohesions)
                para_cohesion_var = (
                    sum((c - pc_mean) ** 2 for c in paragraph_cohesions)
                    / len(paragraph_cohesions)
                )

            ai_score = 0.0
            components = 0

            if sentence_overlaps:
                if overlap_mean > 0.25:
                    ai_score += min(1.0, (overlap_mean - 0.15) / 0.35)
                else:
                    ai_score += max(0.0, 0.3 - overlap_mean)
                components += 1

            if bigram_sims:
                if bigram_sim_mean > 0.20:
                    ai_score += min(1.0, (bigram_sim_mean - 0.10) / 0.30)
                else:
                    ai_score += max(0.0, 0.3 - bigram_sim_mean)
                components += 1

            if sentence_overlaps:
                low_var_score = max(0.0, 1.0 - overlap_var * 15)
                ai_score += low_var_score
                components += 1

            if topic_shift_ratio < 0.15:
                ai_score += min(1.0, (0.15 - topic_shift_ratio) / 0.15)
                components += 1
            else:
                ai_score += max(0.0, topic_shift_ratio - 0.3)
                components += 1

            if paragraph_cohesions:
                high_para_cohesion = min(1.0, max(0.0, (sum(paragraph_cohesions) / len(paragraph_cohesions)) - 0.1) / 0.3)
                ai_score += high_para_cohesion
                low_para_var_score = max(0.0, 1.0 - para_cohesion_var * 20)
                ai_score += low_para_var_score
                components += 2

            if components == 0:
                return 0.5

            final = clamp(ai_score / components, 0.0, 1.0)
            return final

        except Exception:
            log.exception("SemanticCoherenceEngine error")
            return 0.5
