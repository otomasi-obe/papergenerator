"""Base classes and helpers for AI detection engines."""

import re
import math
import logging
from collections import Counter
from typing import List

log = logging.getLogger(__name__)


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, value)))


class TextContext:
    """Pre-computed text properties shared across engines."""

    def __init__(self, text: str):
        self.raw = text
        self.text_lower = text.lower()
        self.words: List[str] = re.findall(r'\b[a-z]+\b', self.text_lower)
        self.word_count = len(self.words)
        self.char_list: List[str] = list(self.text_lower)
        self.char_count = len(self.char_list)
        self.sentences: List[str] = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        self.sentence_count = len(self.sentences)
        self.sentence_lengths: List[int] = [len(s.split()) for s in self.sentences]
        self.paragraphs: List[str] = [p.strip() for p in text.split('\n\n') if p.strip()]
        if not self.paragraphs:
            self.paragraphs = [text.strip()] if text.strip() else []
        self.paragraph_count = len(self.paragraphs)
        self.word_freq = Counter(self.words)
        self.unique_word_count = len(self.word_freq)


class BaseEngine:
    """Abstract base for a detection engine."""

    name: str = "base"
    weight: float = 0.0

    def analyze(self, ctx: TextContext) -> float:
        """Return score 0..1 (higher = more AI-like). Must not throw."""
        raise NotImplementedError
