"""
AI Content Detector & Humanizer
===============================
Combines multiple AI detection heuristics with LLM-powered humanization.
Inspired by: Manuscript (Go), StealthHumanizer, anti-ai-detector, eames,
humanize-text, realai-check-detector, truthlens, unslop.

Features:
  - Multi-engine ensemble AI detection (17 heuristic engines)
  - Statistical AI detection (perplexity, burstiness, token distribution)
  - Pattern-based detection (repetition, filler phrases, AI vocabulary)
  - Model attribution (GPT-3.5/GPT-4/Claude/Gemini/Llama/Mistral fingerprinting)
  - Semantic coherence analysis (overly uniform semantic flow detection)
  - Human signal adjustment (contractions, first person, slang)
  - LLM-powered humanization via AIOTOMASI API
  - Multi-pass rewriting with style preservation
  - Detection scoring (0-100, higher = more AI-like)
  - Fast mode (heuristics only) and Deep mode (heuristics + LLM)
  - Hybrid mode combining heuristic + LLM for maximum accuracy

Usage:
    from ai_detectors.detector import AIDetector, AIHumanizer, PowerfulAIDetector

    detector = AIDetector()
    score, details = detector.analyze("Your text here")
    print(f"AI Score: {score}/100")

    humanizer = AIHumanizer()
    humanized = humanizer.humanize("AI-generated text here")
"""

import os
import re
import math
import json
import logging
from collections import Counter
from typing import Tuple, Dict, List, Optional
from pathlib import Path

import requests
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

log = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent

with open(_DIR / "ai_slop_words.json", encoding="utf-8") as _f:
    _SLOP_DATA = json.load(_f)

with open(_DIR / "ai_starters.json", encoding="utf-8") as _f:
    _STARTERS_DATA = json.load(_f)

_AI_SLOP_WORDS: set = set()
_AI_SLOP_WORDS.update(w.lower() for w in _SLOP_DATA.get("single_words", []))
_AI_SLOP_WORDS.update(p.lower() for p in _SLOP_DATA.get("phrases", []))

_AI_STARTERS: list = [
    r"^(" + "|".join(re.escape(s) for s in _STARTERS_DATA.get("starters", [])) + ")",
]


# ── Ensemble imports ──────────────────────────────────────────────────────────
from .engines.base import TextContext, clamp
from .engines import ALL_ENGINES


class PowerfulAIDetector:
    """Ensemble multi-engine AI detector with 17 heuristic engines.

    Returns (score_0_100, details_dict) with per-engine breakdown,
    model attribution, and human signal adjustment.

    Modes:
      - "fast": Heuristics only (no LLM). Fast, deterministic, offline.
      - "deep": Heuristics + LLM-based detection for maximum accuracy.
      - "hybrid": Combines heuristic ensemble with LLM result using weighted fusion.
    """

    def __init__(self, mode: str = "fast"):
        self._mode = mode
        self._engines = [EngineClass() for EngineClass in ALL_ENGINES]
        self._ensemble_engines = [e for e in self._engines if e.name != "human_signal"]
        self._human_signal_engine = next(e for e in self._engines if e.name == "human_signal")

    def analyze(self, text: str) -> Tuple[float, Dict]:
        """Analyze text and return (score 0-100, details dict)."""
        if not text or not text.strip():
            return 0.0, {"error": "empty text", "final_score": 0.0, "verdict": "Likely Human"}

        ctx = TextContext(text)
        details: Dict = {}
        engine_results: Dict = {}

        for engine in self._engines:
            try:
                score = engine.analyze(ctx)
                if engine.name == "human_signal":
                    score = clamp(score, -0.15, 0.10)
                else:
                    score = clamp(score, 0.0, 1.0)
            except Exception:
                log.exception(f"Engine {engine.name} failed")
                score = 0.5
            engine_results[engine.name] = {
                "score": round(score, 4),
                "weight": engine.weight,
            }

        weighted_sum = 0.0
        weight_total = 0.0
        for engine in self._ensemble_engines:
            s = engine_results[engine.name]["score"]
            w = engine.weight
            weighted_sum += s * w
            weight_total += w

        if weight_total > 0:
            weighted = weighted_sum / weight_total
        else:
            weighted = 0.5

        human_signal = engine_results.get("human_signal", {}).get("score", 0.0)
        final01 = clamp(weighted + human_signal, 0.0, 1.0)
        heuristic_score = final01 * 100

        attributed_model = getattr(ctx, '_attributed_model', 'Unknown')
        model_confidence = getattr(ctx, '_model_confidence', 0.0)
        all_model_scores = getattr(ctx, '_all_model_scores', {})

        details["engines"] = engine_results
        details["weighted_raw"] = round(weighted, 4)
        details["human_signal"] = round(human_signal, 4)
        details["attributed_model"] = attributed_model
        details["model_confidence"] = round(model_confidence, 4)
        details["all_model_scores"] = all_model_scores
        details["mode"] = self._mode

        if self._mode in ("deep", "hybrid"):
            llm_result = self._llm_detect(text)
            details["llm_result"] = llm_result
            if self._mode == "hybrid" and "pct" in llm_result:
                llm_pct = llm_result["pct"]
                fused = (heuristic_score * 0.6) + (llm_pct * 0.4)
                score = clamp(fused, 0.0, 100.0)
                details["heuristic_score"] = round(heuristic_score, 2)
                details["llm_score"] = llm_pct
                details["fusion_weights"] = {"heuristic": 0.6, "llm": 0.4}
            elif self._mode == "deep" and "pct" in llm_result:
                llm_pct = llm_result["pct"]
                score = (heuristic_score * 0.4) + (llm_pct * 0.6)
                score = clamp(score, 0.0, 100.0)
                details["heuristic_score"] = round(heuristic_score, 2)
                details["llm_score"] = llm_pct
                details["fusion_weights"] = {"heuristic": 0.4, "llm": 0.6}
            else:
                score = heuristic_score
        else:
            score = heuristic_score

        details["final_score"] = round(score, 2)
        details["verdict"] = self._verdict(score)

        self._fill_backward_compat(details, engine_results, ctx)

        return round(score, 2), details

    def _llm_detect(self, text: str) -> Dict:
        """Call LLM for AI detection via the per-index endpoint chain. Returns
        dict with pct, reasons, suggestions."""
        from . import PROMPT as _PROMPT
        from utils.ai_tools.ai_client import chat as _chain_chat

        user_prompt = _PROMPT["user_template"].format(option="Standard", text=text[:3000])

        try:
            content, _used = _chain_chat(
                [
                    {"role": "system", "content": _PROMPT["system"]},
                    {"role": "user", "content": user_prompt},
                ],
                heavy=False,
                max_tokens=1024,
                timeout=60,
            )
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(content[json_start:json_end])
                if "pct" not in parsed:
                    parsed["pct"] = 50
                return parsed
            return {"pct": 50, "reasons": ["Could not parse LLM response"], "suggestions": []}
        except RuntimeError as e:
            if "no endpoint configured" in str(e):
                return {"pct": 50, "reasons": ["LLM not configured"], "suggestions": []}
            log.error(f"LLM detection call failed: {e}")
            return {"pct": 50, "reasons": [f"LLM error: {type(e).__name__}"], "suggestions": []}
        except Exception as e:
            log.error(f"LLM detection call failed: {e}")
            return {"pct": 50, "reasons": [f"LLM error: {type(e).__name__}"], "suggestions": []}

    @staticmethod
    def _fill_backward_compat(details: Dict, engine_results: Dict, ctx: TextContext):
        """Populate old-style keys for backward compatibility (0-100 scale)."""
        def s100(name):
            return round(engine_results.get(name, {}).get("score", 0) * 100, 2)

        details["slop_density"] = s100("slop")
        details["starter_pattern"] = s100("formulaic")
        details["burstiness"] = s100("burstiness")
        details["perplexity_approx"] = s100("perplexity_proxy")
        details["repetition"] = s100("repetition")
        details["vocabulary_richness"] = s100("vocabulary")
        details["linguistic_markers"] = s100("linguistic")
        details["structural"] = s100("structural")
        details["readability_uniformity"] = s100("readability")
        details["sentiment_hedging"] = s100("sentiment")
        details["fingerprint"] = s100("fingerprint")
        details["common_words"] = s100("common_words")
        details["syntactic_uniformity"] = s100("syntactic")
        details["punctuation"] = s100("punctuation")
        details["semantic_coherence"] = s100("semantic_coherence")

    @staticmethod
    def _verdict(score: float) -> str:
        if score <= 20:
            return "Likely Human"
        elif score <= 40:
            return "Low risk"
        elif score <= 60:
            return "Suspicious/Mixed"
        elif score <= 80:
            return "Likely AI"
        else:
            return "Slop/High confidence AI"


class AIDetector:
    """Multi-heuristic AI content detector (backward compatible).

    Delegates to PowerfulAIDetector but preserves the original
    return signature (score, details) with all legacy detail keys.

    Supports mode parameter for fast/deep/hybrid detection.
    """

    def __init__(self, mode: str = "fast"):
        self._powerful = PowerfulAIDetector(mode=mode)
        self.slop_words = _AI_SLOP_WORDS
        self.starters = [re.compile(p, re.IGNORECASE) for p in _AI_STARTERS]

    @classmethod
    def reload_vocabulary(cls):
        """Reload slop words and starters from JSON files (hot-reload)."""
        global _AI_SLOP_WORDS, _AI_STARTERS, _SLOP_DATA, _STARTERS_DATA
        with open(_DIR / "ai_slop_words.json", encoding="utf-8") as _f:
            _SLOP_DATA = json.load(_f)
        with open(_DIR / "ai_starters.json", encoding="utf-8") as _f:
            _STARTERS_DATA = json.load(_f)
        _AI_SLOP_WORDS = set()
        _AI_SLOP_WORDS.update(w.lower() for w in _SLOP_DATA.get("single_words", []))
        _AI_SLOP_WORDS.update(p.lower() for p in _SLOP_DATA.get("phrases", []))
        _AI_STARTERS = [
            r"^(" + "|".join(re.escape(s) for s in _STARTERS_DATA.get("starters", [])) + ")",
        ]

    def analyze(self, text: str) -> Tuple[float, Dict]:
        """Analyze text and return (score, details).

        Score: 0-100 where 100 = almost certainly AI-generated.
        Details: dict with per-metric breakdown.
        """
        return self._powerful.analyze(text)

    def _slop_density(self, text: str) -> float:
        words = re.findall(r'\b\w+\b', text.lower())
        if not words:
            return 0.0
        slop_count = sum(1 for w in words if w in self.slop_words)
        text_lower = text.lower()
        phrase_count = sum(1 for p in self.slop_words if ' ' in p and p in text_lower)
        total_slop = slop_count + phrase_count * 2
        density = total_slop / len(words)
        return min(100.0, density * 2000)

    def _starter_pattern(self, text: str) -> float:
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return 0.0
        ai_starters = 0
        for sent in sentences:
            for pattern in self.starters:
                if pattern.match(sent):
                    ai_starters += 1
                    break
        ratio = ai_starters / len(sentences)
        return min(100.0, ratio * 300)

    def _burstiness(self, text: str) -> float:
        sentences = re.split(r'[.!?]+', text)
        lengths = [len(s.split()) for s in sentences if s.strip()]
        if len(lengths) < 3:
            return 50.0
        mean = sum(lengths) / len(lengths)
        variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
        std = math.sqrt(variance)
        cv = std / mean if mean > 0 else 0
        if cv < 0.2:
            return 90.0
        elif cv < 0.4:
            return 70.0
        elif cv < 0.6:
            return 40.0
        elif cv < 0.8:
            return 20.0
        else:
            return 10.0

    def _perplexity_approx(self, text: str) -> float:
        if len(text) < 50:
            return 50.0
        text_lower = text.lower()
        bigrams = [text_lower[i:i+2] for i in range(len(text_lower) - 1)]
        counts = Counter(bigrams)
        total = len(bigrams)
        entropy = -sum(
            (c / total) * math.log2(c / total) for c in counts.values()
        )
        if entropy < 3.0:
            return 85.0
        elif entropy < 3.5:
            return 65.0
        elif entropy < 4.0:
            return 40.0
        else:
            return 20.0

    def _repetition(self, text: str) -> float:
        words = re.findall(r'\b\w+\b', text.lower())
        if len(words) < 20:
            return 50.0
        trigrams = [' '.join(words[i:i+3]) for i in range(len(words) - 2)]
        counts = Counter(trigrams)
        repeated = sum(1 for c in counts.values() if c > 2)
        ratio = repeated / len(trigrams) if trigrams else 0
        return min(100.0, ratio * 1000)

    def _vocabulary_richness(self, text: str) -> float:
        words = re.findall(r'\b\w+\b', text.lower())
        if len(words) < 10:
            return 50.0
        unique = len(set(words))
        ttr = unique / len(words)
        if ttr < 0.3:
            return 90.0
        elif ttr < 0.4:
            return 70.0
        elif ttr < 0.5:
            return 50.0
        elif ttr < 0.6:
            return 30.0
        else:
            return 15.0

    @staticmethod
    def _verdict(score: float) -> str:
        if score >= 80:
            return "HIGH confidence: AI-generated"
        elif score >= 60:
            return "MODERATE-HIGH: Likely AI-generated"
        elif score >= 40:
            return "MODERATE: Possibly AI-generated or edited"
        elif score >= 20:
            return "LOW-MODERATE: Likely human with some AI patterns"
        else:
            return "LOW confidence: Likely human-written"


class AIHumanizer:
    """LLM-powered AI text humanizer using AIOTOMASI API.

    Multi-pass rewriting inspired by StealthHumanizer and anti-ai-detector:
      Pass 1: Structural rewrite (break patterns, vary sentence length)
      Pass 2: Vocabulary naturalization (replace AI-speak with natural language)
      Pass 3: Style injection (add personality, imperfections, authenticity)
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        from utils.ai_tools.model_config import get_primary_generate_model
        self.api_url = api_url or self._build_api_url()
        self.api_key = api_key or os.getenv("AIOTOMASI_APIKEY", "")
        self.model = model or get_primary_generate_model()

    @staticmethod
    def _build_api_url() -> str:
        base = os.getenv("AIOTOMASI_API", "").rstrip("/")
        return f"{base}/chat/completions" if base else ""

    def _call_llm(self, system: str, user: str, temperature: float = 0.8) -> str:
        """Call the LLM via the per-index endpoint chain (MODELGENERATE1..3,
        each with its own endpoint+key)."""
        from utils.ai_tools.ai_client import chat as _chain_chat
        try:
            content, _used = _chain_chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                heavy=True,
                max_tokens=4096,
                temperature=temperature,
                timeout=120,
            )
            return content
        except Exception as e:
            log.error(f"LLM call failed: {e}")
            raise

    def humanize(
        self,
        text: str,
        style: str = "academic",
        passes: int = 3,
        preserve_meaning: bool = True,
    ) -> str:
        if not text.strip():
            return text
        result = text
        for i in range(passes):
            result = self._rewrite_pass(result, style, i + 1, passes, preserve_meaning)
        return result

    def _rewrite_pass(
        self, text: str, style: str, current_pass: int, total_passes: int,
        preserve_meaning: bool,
    ) -> str:
        prompts = {
            1: {
                "system": (
                    "You are an expert academic editor. Your task is to rewrite "
                    "the given text to sound more naturally human. Focus on:\n"
                    "- Varying sentence length and structure\n"
                    "- Breaking predictable patterns\n"
                    "- Using more natural transitions\n"
                    "- Removing AI-typical phrases and filler words\n"
                    f"- Target style: {style}\n"
                    "Preserve all factual content and meaning."
                ),
                "user": f"Rewrite this text to sound more naturally human:\n\n{text}",
            },
            2: {
                "system": (
                    "You are a skilled writer specializing in natural academic prose. "
                    "Rewrite the text to:\n"
                    "- Replace formal/stiff vocabulary with natural alternatives\n"
                    "- Add subtle personality and voice\n"
                    "- Use contractions where appropriate\n"
                    "- Vary paragraph structure\n"
                    "- Remove any remaining AI-typical patterns\n"
                    f"- Target style: {style}"
                ),
                "user": f"Humanize this text further:\n\n{text}",
            },
            3: {
                "system": (
                    "You are a final-pass editor ensuring the text reads as if written "
                    "by a knowledgeable human. Make final adjustments:\n"
                    "- Ensure natural flow and rhythm\n"
                    "- Add authentic-sounding transitions\n"
                    "- Remove any remaining artificial-sounding phrases\n"
                    "- Ensure the text has natural imperfections\n"
                    f"- Target style: {style}\n"
                    "Output ONLY the rewritten text, no explanations."
                ),
                "user": f"Final humanization pass:\n\n{text}",
            },
        }
        prompt = prompts.get(current_pass, prompts[3])
        return self._call_llm(prompt["system"], prompt["user"], temperature=0.7 + current_pass * 0.1)

    def detect_and_humanize(
        self, text: str, style: str = "academic", threshold: float = 50.0
    ) -> Dict:
        detector = AIDetector()
        orig_score, details = detector.analyze(text)

        if orig_score < threshold:
            return {
                "original_score": orig_score,
                "humanized_text": text,
                "new_score": orig_score,
                "was_humanized": False,
                "details": details,
            }

        humanized = self.humanize(text, style=style)
        new_score, new_details = detector.analyze(humanized)

        return {
            "original_score": orig_score,
            "humanized_text": humanized,
            "new_score": new_score,
            "was_humanized": True,
            "score_reduction": orig_score - new_score,
            "original_details": details,
            "new_details": new_details,
        }


# ── Module-level entry point for tools_api ──────────────────────────────────

def run_detector(data: dict) -> dict:
    """tools_api-compatible entry point for the detector tool.

    Args:
        data: Request body dict with keys:
            - text (str, required)
            - option (str, optional, default 'Standard')
            - mode (str, optional, default 'fast'): 'fast' | 'deep' | 'hybrid'

    Returns:
        Dict with keys:
            - pct (int): AI likelihood score 0-100
            - reasons (list): list of detection reasons
            - suggestions (list): list of humanization suggestions
            - confidence (float): detection confidence 0-1
            - category (str): 'Human' | 'Mixed' | 'AI'
            - model_guess (str): attributed model name
            - details (dict): full detection details

    Raises:
        ValueError: when 'text' is missing or empty.
    """
    text = (data.get("text") or "").strip()
    if not text:
        raise ValueError("No text provided")

    option = (data.get("option") or "Standard").strip() or "Standard"
    mode = (data.get("mode") or "fast").strip().lower()
    if mode not in ("fast", "deep", "hybrid"):
        mode = "fast"

    detector = AIDetector(mode=mode)
    score, details = detector.analyze(text)

    attributed_model = details.get("attributed_model", "Unknown")
    verdict = details.get("verdict", "Unknown")

    if score <= 20:
        category = "Human"
    elif score <= 60:
        category = "Mixed"
    else:
        category = "AI"

    reasons = []
    suggestions = []

    if details.get("slop_density", 0) > 50:
        reasons.append("High density of AI-typical vocabulary detected")
        suggestions.append("Replace AI-speak words with simpler, more natural alternatives")

    if details.get("burstiness", 0) > 60:
        reasons.append("Sentence lengths are suspiciously uniform")
        suggestions.append("Vary sentence length — mix short punchy sentences with longer complex ones")

    if details.get("starter_pattern", 0) > 40:
        reasons.append("Multiple AI-typical sentence starters detected")
        suggestions.append("Use more varied, natural sentence openings")

    if details.get("fingerprint", 0) > 50:
        reasons.append("Known AI phrase fingerprints found in text")
        suggestions.append("Rewrite flagged phrases in your own words")

    if details.get("semantic_coherence", 0) > 60:
        reasons.append("Overly uniform semantic flow — lacks natural digressions")
        suggestions.append("Add natural tangents, abrupt topic shifts, or personal asides")

    if details.get("repetition", 0) > 40:
        reasons.append("Unusual repetition of phrases detected")
        suggestions.append("Reduce repeated phrases and vary your expressions")

    if details.get("vocabulary_richness", 0) > 60:
        reasons.append("Vocabulary is unusually uniform/predictable")
        suggestions.append("Use more specific, varied, and unexpected word choices")

    if attributed_model and attributed_model != "Unknown":
        reasons.append(f"Writing patterns consistent with {attributed_model} output")

    if not reasons:
        if score > 40:
            reasons.append("General AI-like patterns detected across multiple dimensions")
        else:
            reasons.append("Text appears to be human-written")

    if not suggestions:
        suggestions.append("Review the text for any remaining AI-typical patterns")

    confidence = min(1.0, max(0.0, score / 100.0 + 0.1))

    result = {
        "pct": int(round(score)),
        "confidence": round(confidence, 2),
        "category": category,
        "model_guess": attributed_model,
        "reasons": reasons,
        "suggestions": suggestions,
        "details": details,
    }

    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AI Detector & Humanizer")
    sub = parser.add_subparsers(dest="command")

    det = sub.add_parser("detect", help="Detect AI-generated content")
    det.add_argument("text", nargs="?", help="Text to analyze")
    det.add_argument("--file", "-f", help="File to analyze")
    det.add_argument("--json", action="store_true", help="Output as JSON")
    det.add_argument("--mode", default="fast", choices=["fast", "deep", "hybrid"],
                     help="Detection mode: fast (heuristics), deep (heuristics+LLM), hybrid (fused)")

    hum = sub.add_parser("humanize", help="Humanize AI text")
    hum.add_argument("text", nargs="?", help="Text to humanize")
    hum.add_argument("--file", "-f", help="File to humanize")
    hum.add_argument("--style", default="academic", choices=["academic", "casual", "professional", "creative"])
    hum.add_argument("--passes", type=int, default=3, choices=[1, 2, 3])

    auto = sub.add_parser("auto", help="Detect and humanize if AI-like")
    auto.add_argument("text", nargs="?", help="Text to process")
    auto.add_argument("--file", "-f", help="File to process")
    auto.add_argument("--threshold", type=float, default=50.0)
    auto.add_argument("--style", default="academic")
    auto.add_argument("--json", action="store_true")
    auto.add_argument("--mode", default="fast", choices=["fast", "deep", "hybrid"])

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    text = args.text
    if hasattr(args, "file") and args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    if not text:
        import sys
        text = sys.stdin.read()

    if args.command == "detect":
        mode = getattr(args, "mode", "fast")
        detector = AIDetector(mode=mode)
        score, details = detector.analyze(text)
        if getattr(args, "json", False):
            print(json.dumps({"score": score, "details": details}, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"  AI Detection Score: {score}/100")
            print(f"  Verdict: {details['verdict']}")
            print(f"  Mode: {mode}")
            if details.get("attributed_model"):
                print(f"  Attributed Model: {details['attributed_model']}")
            print(f"{'='*60}")
            for k, v in details.items():
                if k not in ("verdict", "final_score", "engines", "all_model_scores"):
                    print(f"  {k:.<35} {v}")

    elif args.command == "humanize":
        humanizer = AIHumanizer()
        result = humanizer.humanize(text, style=args.style, passes=args.passes)
        print(result)

    elif args.command == "auto":
        mode = getattr(args, "mode", "fast")
        humanizer = AIHumanizer()
        result = humanizer.detect_and_humanize(text, style=args.style, threshold=args.threshold)
        if getattr(args, "json", False):
            out = {k: v for k, v in result.items() if k not in ("original_details", "new_details")}
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print(f"\n{'='*60}")
            print(f"  Original AI Score: {result['original_score']}/100")
            print(f"  Humanized: {result['was_humanized']}")
            if result['was_humanized']:
                print(f"  New AI Score: {result['new_score']}/100")
                print(f"  Score Reduction: {result['score_reduction']:.1f}")
            print(f"{'='*60}\n")
            print(result['humanized_text'])


if __name__ == "__main__":
    main()
