"""Model attribution engine: fingerprint GPT-3.5/GPT-4/Claude/Gemini/Llama/Mistral via feature ranges."""

import re
import logging
from .base import BaseEngine, TextContext, clamp

log = logging.getLogger(__name__)

_MODELS = {
    "GPT-4": {
        "avgSentenceLength": (20, 30),
        "hedgingRate": (3, 8),
        "passiveVoiceRate": (0.15, 0.35),
        "contractionRate": (0.5, 2),
        "parentheticalRate": (0, 2),
        "aiPhraseDensity": (5, 15),
        "listUsageRate": (0.05, 0.20),
        "avgWordLength": (4.8, 5.5),
    },
    "GPT-3.5": {
        "avgSentenceLength": (15, 24),
        "hedgingRate": (2, 7),
        "passiveVoiceRate": (0.10, 0.30),
        "contractionRate": (1, 4),
        "parentheticalRate": (0, 1),
        "aiPhraseDensity": (4, 12),
        "listUsageRate": (0.10, 0.30),
        "avgWordLength": (4.5, 5.2),
    },
    "Claude": {
        "avgSentenceLength": (15, 25),
        "hedgingRate": (2, 6),
        "passiveVoiceRate": (0.10, 0.25),
        "contractionRate": (2, 5),
        "parentheticalRate": (2, 6),
        "aiPhraseDensity": (3, 10),
        "listUsageRate": (0.05, 0.15),
        "avgWordLength": (4.6, 5.3),
    },
    "Gemini": {
        "avgSentenceLength": (18, 28),
        "hedgingRate": (2, 7),
        "passiveVoiceRate": (0.20, 0.40),
        "contractionRate": (0, 1.5),
        "parentheticalRate": (0, 1),
        "aiPhraseDensity": (8, 20),
        "listUsageRate": (0.08, 0.25),
        "avgWordLength": (4.7, 5.4),
    },
    "Llama": {
        "avgSentenceLength": (12, 22),
        "hedgingRate": (1, 4),
        "passiveVoiceRate": (0.05, 0.20),
        "contractionRate": (3, 7),
        "parentheticalRate": (0, 3),
        "aiPhraseDensity": (2, 8),
        "listUsageRate": (0.02, 0.12),
        "avgWordLength": (4.3, 5.0),
    },
    "Mistral": {
        "avgSentenceLength": (14, 23),
        "hedgingRate": (1, 5),
        "passiveVoiceRate": (0.08, 0.22),
        "contractionRate": (2, 6),
        "parentheticalRate": (1, 4),
        "aiPhraseDensity": (3, 9),
        "listUsageRate": (0.03, 0.15),
        "avgWordLength": (4.4, 5.1),
    },
}

_PASSIVE_PATTERNS = [
    re.compile(r'\b\w+ed\s+by\b', re.I),
    re.compile(r'\b(?:is|are|was|were|be|been|being)\s+\w+ed\b', re.I),
]

_AI_PHRASES = [
    "furthermore", "moreover", "consequently", "nevertheless",
    "in conclusion", "it is important to note", "delve",
    "leverage", "holistic", "robust", "paradigm", "synergy",
    "multifaceted", "pivotal", "comprehensive", "navigate",
    "facilitate", "groundbreaking", "cutting-edge",
]

_HEDGING_WORDS = [
    "perhaps", "possibly", "arguably", "relatively", "somewhat",
    "might", "could", "may", "seem", "appear",
]

_CONTRACTIONS = re.compile(r"\b\w+'\w+\b", re.I)


class ModelAttributionEngine(BaseEngine):
    name = "model_attribution"
    weight = 0.01

    def analyze(self, ctx: TextContext) -> float:
        try:
            if ctx.word_count < 30:
                return 0.5

            slens = [l for l in ctx.sentence_lengths if l > 0]
            avg_sent_len = sum(slens) / len(slens) if slens else 0

            hedge_count = sum(1 for w in ctx.words if w in _HEDGING_WORDS)
            hedging_rate = (hedge_count / ctx.word_count) * 1000

            passive_count = sum(
                len(p.search(ctx.raw.lower()) and p.findall(ctx.raw.lower()) or [])
                for p in _PASSIVE_PATTERNS
            )
            passive_rate = passive_count / max(ctx.sentence_count, 1)

            contraction_count = len(_CONTRACTIONS.findall(ctx.raw))
            contraction_rate = (contraction_count / ctx.word_count) * 100

            parenthetical_count = ctx.raw.count('(') + ctx.raw.count('\u2014')
            parenthetical_rate = (parenthetical_count / ctx.word_count) * 1000

            tl = ctx.text_lower
            ai_phrase_count = sum(1 for p in _AI_PHRASES if p in tl)
            ai_phrase_density = (ai_phrase_count / ctx.word_count) * 1000

            list_lines = sum(
                1 for l in ctx.raw.split('\n')
                if re.match(r'\s*[-*•]|\s*\d+\.', l.strip())
            )
            list_usage_rate = list_lines / max(ctx.sentence_count, 1)

            avg_word_len = (
                sum(len(w) for w in ctx.words) / ctx.word_count
                if ctx.word_count > 0 else 0
            )

            features = {
                "avgSentenceLength": avg_sent_len,
                "hedgingRate": hedging_rate,
                "passiveVoiceRate": passive_rate,
                "contractionRate": contraction_rate,
                "parentheticalRate": parenthetical_rate,
                "aiPhraseDensity": ai_phrase_density,
                "listUsageRate": list_usage_rate,
                "avgWordLength": avg_word_len,
            }

            best_model = "Unknown"
            best_conf = 0.0
            all_model_scores = {}

            for model_name, ranges in _MODELS.items():
                scores = []
                for feat_name, (lo, hi) in ranges.items():
                    v = features.get(feat_name, 0)
                    mid = (lo + hi) / 2
                    half_w = (hi - lo) / 2
                    if half_w == 0:
                        fs = 1.0 if v == mid else 0.0
                    else:
                        fs = max(0, 1 - abs(v - mid) / (half_w * 3))
                    scores.append(fs)
                conf = sum(scores) / len(scores) if scores else 0
                all_model_scores[model_name] = round(conf, 4)
                if conf > best_conf:
                    best_conf = conf
                    best_model = model_name

            ctx._attributed_model = best_model
            ctx._model_confidence = best_conf
            ctx._all_model_scores = all_model_scores
            return clamp(best_conf, 0, 1)
        except Exception:
            log.exception("ModelAttributionEngine error")
            return 0.5
