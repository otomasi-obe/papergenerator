"""
AI Detector runner — sentence-level highlighting + engine breakdown.

Returns structured result for frontend:
  - pct: overall AI score (0-100)
  - verdict: human-readable label
  - sentences: per-sentence analysis with severity + reasons
  - engines: per-engine score breakdown
  - model: attributed LLM model + confidence
  - stats: word/sentence/paragraph counts
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, Any

from .detector import PowerfulAIDetector

log = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent

# Load slop words & starters for per-sentence analysis
with open(_DIR / "ai_slop_words.json", encoding="utf-8") as _f:
    _SLOP_DATA = json.load(_f)

with open(_DIR / "ai_starters.json", encoding="utf-8") as _f:
    _STARTERS_DATA = json.load(_f)

_SLOP_SET = set()
_SLOP_SET.update(w.lower() for w in _SLOP_DATA.get("single_words", []))
_SLOP_SET.update(p.lower() for p in _SLOP_DATA.get("phrases", []))
_SLOP_PHRASES = [p.lower() for p in _SLOP_DATA.get("phrases", []) if " " in p]

_STARTER_PATTERNS = [
    re.compile(r"^(" + "|".join(re.escape(s) for s in _STARTERS_DATA.get("starters", [])) + r")", re.I)
]

_FINGERPRINT_PATTERNS = [
    re.compile(r"delve\s+into", re.I),
    re.compile(r"rich\s+tapestry", re.I),
    re.compile(r"ever-evolving", re.I),
    re.compile(r"it\s+is\s+(?:important|worth|crucial|essential)\s+to", re.I),
    re.compile(r"plays?\s+a\s+(?:crucial|pivotal|vital)\s+role", re.I),
    re.compile(r"(?:unleash|unlock)\s+the\s+(?:power|potential)", re.I),
    re.compile(r"a\s+testament\s+to", re.I),
    re.compile(r"embark\s+on", re.I),
    re.compile(r"foster\s+(?:a\s+)?(?:sense|culture)", re.I),
    re.compile(r"at\s+the\s+forefront", re.I),
    re.compile(r"a\s+myriad\s+of", re.I),
    re.compile(r"navigat(?:e|ing)\s+the\s+complexit", re.I),
    re.compile(r"cutting-edge", re.I),
    re.compile(r"game-chang(?:er|ing)", re.I),
]

_FORMULAIC_PATTERNS = [
    re.compile(r"in\s+(?:today's|the\s+realm|this\s+(?:article|section|chapter))", re.I),
    re.compile(r"when\s+it\s+comes\s+to", re.I),
    re.compile(r"not\s+only.{3,60}but\s+also", re.I | re.DOTALL),
    re.compile(r"first\s+and\s+foremost", re.I),
    re.compile(r"last\s+but\s+not\s+least", re.I),
    re.compile(r"it's?\s+worth\s+(?:noting|mentioning)", re.I),
    re.compile(r"(?:this|it)\s+should\s+be\s+noted", re.I),
]

_HEDGING_WORDS = {
    "perhaps", "possibly", "arguably", "relatively", "somewhat",
    "might", "could", "may", "seem", "appear", "allegedly",
}

_ENGINE_LABELS = {
    "slop": ("AI Slop Words", "Kepadatan kata/frase khas AI"),
    "formulaic": ("Formulaic Patterns", "Pembuka, penutup, dan pengisi formulaik"),
    "burstiness": ("Burstiness", "Variasi panjang kalimat"),
    "perplexity_proxy": ("Perplexity", "Prediktabilitas teks"),
    "repetition": ("Repetition", "Pengulangan frasa"),
    "vocabulary": ("Vocabulary", "Kekayaan kosakata"),
    "linguistic": ("Linguistic Markers", "Penanda linguistik khas AI"),
    "structural": ("Structural", "Keteraturan struktur paragraf"),
    "readability": ("Readability", "Keseragaman keterbacaan"),
    "sentiment": ("Sentiment Hedging", "Keraguan dan kualifikasi"),
    "fingerprint": ("Phrase Fingerprint", "Sidik jari frase LLM"),
    "common_words": ("Common Words", "Kata paling umum"),
    "syntactic": ("Syntactic Uniformity", "Keseragaman sintaksis"),
    "punctuation": ("Punctuation", "Pola tanda baca"),
    "semantic_coherence": ("Semantic Coherence", "Koherensi semantik"),
    "model_attribution": ("Model Attribution", "Atribusi model"),
    "human_signal": ("Human Signal", "Sinyal penulisan manusia"),
}


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences preserving original text."""
    raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in raw_sentences if s.strip() and len(s.strip()) > 3]


def _analyze_sentence(sentence: str) -> Dict[str, Any]:
    """Analyze a single sentence for AI-likeness. Returns score 0-1 + reasons."""
    score = 0.0
    reasons = []
    s_lower = sentence.lower()
    words = re.findall(r'\b[a-z]+\b', s_lower)
    wc = len(words)

    if wc < 3:
        return {"score": 0.0, "reasons": [], "severity": "none"}

    # 1. Slop words
    slop_hits = [w for w in words if w in _SLOP_SET]
    slop_phrases = [p for p in _SLOP_PHRASES if p in s_lower]
    slop_count = len(slop_hits) + len(slop_phrases) * 2
    if slop_count > 0:
        slop_density = min(slop_count / wc * 15, 1.0)
        score += slop_density * 0.35
        if slop_hits:
            reasons.append(f"Slop words: {', '.join(sorted(set(slop_hits))[:5])}")
        if slop_phrases:
            reasons.append(f"AI phrases: {', '.join(slop_phrases[:3])}")

    # 2. Fingerprint matches
    fp_hits = [p.pattern for p in _FINGERPRINT_PATTERNS if p.search(sentence)]
    if fp_hits:
        score += min(len(fp_hits) * 0.15, 0.4)
        reasons.append(f"LLM fingerprints: {len(fp_hits)}")

    # 3. Formulaic patterns
    formulaic_hits = [p.pattern for p in _FORMULAIC_PATTERNS if p.search(sentence)]
    if formulaic_hits:
        score += min(len(formulaic_hits) * 0.12, 0.35)
        reasons.append("Formulaic pattern detected")

    # 4. Starter pattern
    for pat in _STARTER_PATTERNS:
        if pat.match(sentence.strip()):
            score += 0.10
            reasons.append("AI-typical sentence opener")
            break

    # 5. Hedging density
    hedge_count = sum(1 for w in words if w in _HEDGING_WORDS)
    if hedge_count > 0:
        hedge_score = min(hedge_count / wc * 20, 0.2)
        score += hedge_score
        if hedge_count >= 2:
            reasons.append(f"Hedging words ({hedge_count}x)")

    # 6. Sentence too uniform (long + formal)
    if wc > 30:
        score += 0.08
        reasons.append("Unusually long, uniform sentence")

    # 7. Passive voice
    passive = re.findall(r'\b(?:is|are|was|were|be|been|being)\s+\w+ed\b', s_lower)
    if len(passive) >= 2:
        score += 0.08
        reasons.append("Heavy passive voice")

    score = min(score, 1.0)

    if score >= 0.55:
        severity = "high"
    elif score >= 0.30:
        severity = "moderate"
    elif score >= 0.15:
        severity = "low"
    else:
        severity = "none"

    return {
        "score": round(score, 3),
        "reasons": reasons[:4],
        "severity": severity,
    }


def run_detector(data: Dict[str, Any]) -> Dict[str, Any]:
    """Main runner. data must have 'text'. Optional 'mode': fast/deep/hybrid."""
    text = (data.get("text") or "").strip()
    mode = (data.get("option") or data.get("mode") or "fast").strip().lower()
    if mode not in ("fast", "deep", "hybrid"):
        mode = "fast"

    if not text:
        return {"pct": 0, "verdict": "Empty text", "sentences": [], "engines": {}, "stats": {}}

    # 1. Overall analysis
    detector = PowerfulAIDetector(mode=mode)
    overall_score, details = detector.analyze(text)

    # 2. Per-sentence analysis
    sentences = _split_sentences(text)
    sentence_results = []
    for sent in sentences:
        analysis = _analyze_sentence(sent)
        sentence_results.append({
            "text": sent,
            **analysis,
        })

    # 3. Engine breakdown
    engines_raw = details.get("engines", {})
    engine_breakdown = []
    for eng_name, eng_data in engines_raw.items():
        label, desc = _ENGINE_LABELS.get(eng_name, (eng_name, ""))
        eng_score = round(eng_data.get("score", 0) * 100, 1)
        weight = eng_data.get("weight", 0)
        engine_breakdown.append({
            "id": eng_name,
            "label": label,
            "desc": desc,
            "score": eng_score,
            "weight": weight,
        })
    engine_breakdown.sort(key=lambda x: x["score"], reverse=True)

    # 4. Model attribution
    model_info = {
        "attributed": details.get("attributed_model", "Unknown"),
        "confidence": round(details.get("model_confidence", 0) * 100, 1),
        "all_scores": details.get("all_model_scores", {}),
    }

    # 5. Stats
    words = re.findall(r'\b\w+\b', text)
    stats = {
        "words": len(words),
        "sentences": len(sentences),
        "paragraphs": len([p for p in text.split('\n\n') if p.strip()]),
        "flagged_sentences": sum(1 for s in sentence_results if s["severity"] != "none"),
    }

    # 6. LLM result (if deep/hybrid)
    llm_result = None
    if "llm_result" in details:
        llm = details["llm_result"]
        llm_result = {
            "pct": llm.get("pct"),
            "reasons": llm.get("reasons", []),
            "suggestions": llm.get("suggestions", []),
        }

    result = {
        "pct": round(overall_score, 1),
        "verdict": details.get("verdict", ""),
        "sentences": sentence_results,
        "engines": engine_breakdown,
        "model": model_info,
        "stats": stats,
        "mode": mode,
    }
    if llm_result:
        result["llm"] = llm_result

    return result
