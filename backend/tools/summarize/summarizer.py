"""Extractive summarization using TextRank algorithm with keyword extraction support.

Provides fallback summarization when LLM is unavailable, and hybrid mode
that combines extractive key sentences with abstractive LLM summarization.
"""

import logging
import re
from collections import Counter
from math import log10

log = logging.getLogger(__name__)

_DEFAULT_RATIO = 0.2
_MAX_KEYWORDS = 15
_MAX_SENTENCES = 50

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "dare", "ought", "used", "it", "its", "this", "that", "these", "those",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself",
    "she", "her", "hers", "herself", "they", "them", "their", "theirs",
    "themselves", "what", "which", "who", "whom", "when", "where", "why",
    "how", "all", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "just", "because", "if", "then", "else", "while",
    "although", "though", "after", "before", "since", "until", "unless",
    "about", "between", "through", "during", "above", "below", "up", "down",
    "out", "off", "over", "under", "again", "further", "once", "here",
    "there", "also", "into", "et", "al", "fig", "figure", "table", "ref",
    "pp", "vol", "eg", "ie", "etc", "vs", "cf",
})


class _Sentence:
    __slots__ = ("text", "token", "index", "score")

    def __init__(self, text: str, token: str, index: int):
        self.text = text
        self.token = token
        self.index = index
        self.score = 0.0


def _tokenize_sentences(text: str) -> list[str]:
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    sentences = []
    for s in raw:
        s = s.strip()
        if len(s.split()) >= 3:
            sentences.append(s)
    if not sentences and text.strip():
        sentences = [text.strip()]
    return sentences[:_MAX_SENTENCES]


def _normalize_sentence(sentence: str) -> str:
    s = re.sub(r"\[[\d,\s-]+\]", "", sentence)
    s = re.sub(r"\([^)]*\d{4}[^)]*\)", "", s)
    s = re.sub(r"[^\w\s]", "", s.lower())
    return s.strip()


def _sentence_similarity(s1: str, s2: str) -> float:
    words1 = [w for w in s1.split() if w not in _STOPWORDS and len(w) > 1]
    words2 = [w for w in s2.split() if w not in _STOPWORDS and len(w) > 1]
    if not words1 or not words2:
        return 0.0
    common = set(words1) & set(words2)
    if not common:
        return 0.0
    log1 = log10(len(words1))
    log2 = log10(len(words2))
    if log1 + log2 == 0:
        return 0.0
    return len(common) / (log1 + log2)


def _build_similarity_matrix(sentences: list[str]) -> list[list[float]]:
    n = len(sentences)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim = _sentence_similarity(sentences[i], sentences[j])
            matrix[i][j] = sim
            matrix[j][i] = sim
    return matrix


def _textrank_scores(
    matrix: list[list[float]], damping: float = 0.85, iterations: int = 100
) -> list[float]:
    n = len(matrix)
    if n == 0:
        return []
    scores = [1.0 / n] * n
    for _ in range(iterations):
        new_scores = [0.0] * n
        converged = True
        for i in range(n):
            rank = (1 - damping) / n
            for j in range(n):
                if i == j:
                    continue
                weight_sum = sum(matrix[j][k] for k in range(n) if k != j)
                if weight_sum > 0:
                    rank += damping * scores[j] * matrix[j][i] / weight_sum
            new_scores[i] = rank
            if abs(new_scores[i] - scores[i]) > 0.0001:
                converged = False
        scores = new_scores
        if converged:
            break
    return scores


def _extract_keywords_textrank(
    text: str, max_keywords: int = _MAX_KEYWORDS
) -> list[tuple[str, float]]:
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    words = [w for w in words if w not in _STOPWORDS]
    if not words:
        return []

    window_size = 5
    cooccurrence: dict[str, dict[str, int]] = {}
    for i, w in enumerate(words):
        if w not in cooccurrence:
            cooccurrence[w] = {}
        for j in range(
            max(0, i - window_size), min(len(words), i + window_size + 1)
        ):
            if i != j:
                neighbor = words[j]
                cooccurrence[w][neighbor] = cooccurrence[w].get(neighbor, 0) + 1

    scores: dict[str, float] = {w: 1.0 / len(set(words)) for w in set(words)}
    for _ in range(50):
        new_scores: dict[str, float] = {}
        for w in scores:
            rank = (1 - 0.85) / len(scores)
            if w in cooccurrence:
                for neighbor, weight in cooccurrence[w].items():
                    if neighbor in scores:
                        neighbor_sum = sum(cooccurrence.get(neighbor, {}).values())
                        if neighbor_sum > 0:
                            rank += 0.85 * scores[neighbor] * weight / neighbor_sum
            new_scores[w] = rank
        scores = new_scores

    max_score = max(scores.values()) if scores else 1.0
    if max_score > 0:
        scores = {w: s / max_score for w, s in scores.items()}

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:max_keywords]


def extractive_summarize(
    text: str, ratio: float = _DEFAULT_RATIO, max_sentences: int | None = None
) -> dict:
    """Extract top-ranked sentences using TextRank algorithm.

    Args:
        text: Input text to summarize
        ratio: Proportion of sentences to extract (0.0-1.0)
        max_sentences: Exact number of sentences to extract (overrides ratio)

    Returns:
        dict with summary text, sentences list, scores, and method
    """
    raw_sentences = _tokenize_sentences(text)
    if not raw_sentences:
        return {"summary": "", "sentences": [], "scores": [], "method": "extractive"}

    normalized = [_normalize_sentence(s) for s in raw_sentences]
    objects = [
        _Sentence(raw, norm, i)
        for i, (raw, norm) in enumerate(zip(raw_sentences, normalized))
    ]

    matrix = _build_similarity_matrix(normalized)
    scores = _textrank_scores(matrix)

    for obj, score in zip(objects, scores):
        obj.score = score

    objects.sort(key=lambda s: s.score, reverse=True)

    if max_sentences:
        count = min(max_sentences, len(objects))
    else:
        count = max(1, int(len(objects) * ratio))

    selected = objects[:count]
    selected.sort(key=lambda s: s.index)

    summary = " ".join(s.text for s in selected)
    return {
        "summary": summary,
        "sentences": [s.text for s in selected],
        "scores": [round(s.score, 4) for s in selected],
        "method": "extractive",
    }


def extract_keywords(text: str, max_keywords: int = _MAX_KEYWORDS) -> list[dict]:
    """Extract keywords using TextRank algorithm.

    Args:
        text: Input text
        max_keywords: Maximum number of keywords to return

    Returns:
        List of dicts with keyword and score
    """
    keywords = _extract_keywords_textrank(text, max_keywords)
    return [{"keyword": kw, "score": round(score, 4)} for kw, score in keywords]


def extract_key_sentences(text: str, num_sentences: int = 5) -> list[dict]:
    """Extract top N key sentences without ratio-based selection.

    Args:
        text: Input text
        num_sentences: Number of top sentences to return

    Returns:
        List of dicts with sentence text and score
    """
    raw_sentences = _tokenize_sentences(text)
    if not raw_sentences:
        return []

    normalized = [_normalize_sentence(s) for s in raw_sentences]
    objects = [
        _Sentence(raw, norm, i)
        for i, (raw, norm) in enumerate(zip(raw_sentences, normalized))
    ]

    matrix = _build_similarity_matrix(normalized)
    scores = _textrank_scores(matrix)

    for obj, score in zip(objects, scores):
        obj.score = score

    objects.sort(key=lambda s: s.score, reverse=True)
    selected = objects[: min(num_sentences, len(objects))]
    selected.sort(key=lambda s: s.index)

    return [{"sentence": s.text, "score": round(s.score, 4)} for s in selected]


def run_summarizer(data: dict) -> dict:
    """Main entry point for summarization tool runner.

    Supports modes: "ai", "extractive", "hybrid"

    Args:
        data: Request dict with keys:
            - text: Input text to summarize
            - option: Summary type (TL;DR, Abstract, Bullets, etc.)
            - mode: "ai" | "extractive" | "hybrid" (default "extractive")
            - domain: Content domain (default "academic")
            - format: Output format (default "plain")
            - ratio: Extractive ratio (0.0-1.0, default 0.2)

    Returns:
        dict with summary result
    """
    text = (data.get("text") or "").strip()
    if not text:
        raise ValueError("No text provided")

    option = (data.get("option") or "Bullets").strip()
    mode = (data.get("mode") or "extractive").strip().lower()
    domain = (data.get("domain") or "academic").strip().lower()
    ratio = float(data.get("ratio") or 0.2)
    ratio = max(0.05, min(1.0, ratio))

    if mode == "extractive":
        result = extractive_summarize(text, ratio=ratio)
        keywords = extract_keywords(text)
        result["keywords"] = keywords
        result["option"] = option
        result["domain"] = domain
        return result

    if mode == "hybrid":
        extractive_result = extractive_summarize(text, ratio=ratio)
        keywords = extract_keywords(text)
        key_sentences = extract_key_sentences(text, num_sentences=5)
        return {
            "summary": extractive_result["summary"],
            "sentences": extractive_result["sentences"],
            "scores": extractive_result["scores"],
            "keywords": keywords,
            "key_sentences": key_sentences,
            "method": "hybrid",
            "option": option,
            "domain": domain,
            "llm_prompt_hint": (
                f"Refine and improve the following extractive summary into a "
                f"{option} format for {domain} domain:\n\n"
                f"{extractive_result['summary']}"
            ),
        }

    # mode == "ai" -> return data for LLM processing by tools_api
    from tools.summarize import PROMPT

    fmt = (data.get("format") or "plain").strip().lower()
    user_prompt = PROMPT["user_template"].format(
        domain=domain, option=option, format=fmt, text=text
    )
    return {
        "method": "ai",
        "system": PROMPT["system"],
        "user_prompt": user_prompt,
        "option": option,
        "domain": domain,
        "format": fmt,
    }
