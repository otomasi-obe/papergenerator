import requests
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)

# ── Retry & Rate Limiting ──────────────────────────────────────────────────────

_RATE_LIMIT_STATE: dict[str, float] = {}

_RATE_LIMIT_INTERVALS: dict[str, float] = {
    "google": 0.5,
    "mymemory": 1.0,
    "deepl": 0.3,
    "libre": 1.0,
    "argos": 0.0,
    "lingvanex": 1.0,
}


def _retry(fn: Callable, max_retries: int = 3, base_delay: float = 1.0, engine_name: str = "") -> Any:
    """Retry a callable with exponential backoff."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            _enforce_rate_limit(engine_name)
            return fn()
        except requests.exceptions.HTTPError as e:
            last_exc = e
            status = e.response.status_code if e.response is not None else 0
            if status == 429:
                retry_after = float(e.response.headers.get("Retry-After", base_delay * (2 ** attempt)))
                logger.warning("%s rate-limited (429), waiting %.1fs", engine_name, retry_after)
                time.sleep(retry_after)
                continue
            if status >= 500:
                delay = base_delay * (2 ** attempt)
                logger.warning("%s server error %d, retry %d/%d in %.1fs", engine_name, status, attempt + 1, max_retries, delay)
                time.sleep(delay)
                continue
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            delay = base_delay * (2 ** attempt)
            logger.warning("%s connection error, retry %d/%d in %.1fs", engine_name, attempt + 1, max_retries, delay)
            time.sleep(delay)
            continue
    raise last_exc


def _enforce_rate_limit(engine_name: str) -> None:
    """Sleep if needed to respect per-engine rate limit."""
    interval = _RATE_LIMIT_INTERVALS.get(engine_name, 0.5)
    if interval <= 0:
        return
    last = _RATE_LIMIT_STATE.get(engine_name, 0.0)
    now = time.monotonic()
    wait = interval - (now - last)
    if wait > 0:
        time.sleep(wait)
    _RATE_LIMIT_STATE[engine_name] = time.monotonic()

LANGUAGE_CODES = {
    "afrikaans": "af",
    "albanian": "sq",
    "amharic": "am",
    "arabic": "ar",
    "armenian": "hy",
    "azerbaijani": "az",
    "basque": "eu",
    "belarusian": "be",
    "bengali": "bn",
    "bosnian": "bs",
    "bulgarian": "bg",
    "burmese": "my",
    "catalan": "ca",
    "chinese (simplified)": "zh-CN",
    "chinese (traditional)": "zh-TW",
    "chinese": "zh",
    "croatian": "hr",
    "czech": "cs",
    "danish": "da",
    "dutch": "nl",
    "english": "en",
    "estonian": "et",
    "finnish": "fi",
    "french": "fr",
    "galician": "gl",
    "georgian": "ka",
    "german": "de",
    "greek": "el",
    "gujarati": "gu",
    "hebrew": "he",
    "hindi": "hi",
    "hungarian": "hu",
    "icelandic": "is",
    "indonesian": "id",
    "irish": "ga",
    "italian": "it",
    "japanese": "ja",
    "javanese": "jv",
    "kannada": "kn",
    "kazakh": "kk",
    "khmer": "km",
    "korean": "ko",
    "kurdish": "ku",
    "lao": "lo",
    "latin": "la",
    "latvian": "lv",
    "lithuanian": "lt",
    "macedonian": "mk",
    "malay": "ms",
    "malayalam": "ml",
    "maltese": "mt",
    "marathi": "mr",
    "mongolian": "mn",
    "nepali": "ne",
    "norwegian": "no",
    "pashto": "ps",
    "persian": "fa",
    "polish": "pl",
    "portuguese": "pt",
    "punjabi": "pa",
    "romanian": "ro",
    "russian": "ru",
    "serbian": "sr",
    "sinhala": "si",
    "slovak": "sk",
    "slovenian": "sl",
    "somali": "so",
    "spanish": "es",
    "sundanese": "su",
    "swahili": "sw",
    "swedish": "sv",
    "tajik": "tg",
    "tamil": "ta",
    "telugu": "te",
    "thai": "th",
    "turkish": "tr",
    "ukrainian": "uk",
    "urdu": "ur",
    "uzbek": "uz",
    "vietnamese": "vi",
    "welsh": "cy",
    "xhosa": "xh",
    "yiddish": "yi",
    "yoruba": "yo",
    "zulu": "zu",
}

REVERSE_LANG_CODES = {v: k.title() for k, v in LANGUAGE_CODES.items()}


@dataclass
class TranslationResult:
    text: str
    engine: str
    source_language: str
    target_language: str
    success: bool
    error: Optional[str] = None
    quality_score: float = 0.0
    latency_ms: float = 0.0


def resolve_lang_code(name: str) -> str:
    if not name or name.lower() == "auto":
        return "auto"
    lower = name.lower().strip()
    if lower in LANGUAGE_CODES:
        return LANGUAGE_CODES[lower]
    if lower in LANGUAGE_CODES.values():
        return lower
    for k, v in LANGUAGE_CODES.items():
        if lower in k or k in lower:
            return v
    return lower


def resolve_lang_name(code: str) -> str:
    if not code or code == "auto":
        return "Auto"
    return REVERSE_LANG_CODES.get(code, code.upper())


def detect_language(text: str) -> str:
    """Detect language using langdetect with Unicode-range fallback."""
    if not text or not text.strip():
        return "auto"
    try:
        from langdetect import detect
        code = detect(text[:1000])
        return code
    except Exception:
        pass
    # Fallback: heuristic based on Unicode character ranges
    sample = text[:1000]
    ranges = [
        (r'[\u3040-\u309f\u30a0-\u30ff]', "ja"),   # Hiragana + Katakana
        (r'[\uac00-\ud7af]', "ko"),                   # Korean Hangul
        (r'[\u4e00-\u9fff]', "zh"),                   # CJK Unified (Chinese)
        (r'[\u0e00-\u0e7f]', "th"),                   # Thai
        (r'[\u0900-\u097f]', "hi"),                   # Devanagari (Hindi)
        (r'[\u0980-\u09ff]', "bn"),                   # Bengali
        (r'[\u0a00-\u0a7f]', "pa"),                   # Gurmukhi (Punjabi)
        (r'[\u0b00-\u0b7f]', "ta"),                   # Tamil
        (r'[\u0b80-\u0bff]', "te"),                   # Telugu
        (r'[\u0c00-\u0c7f]', "kn"),                   # Kannada
        (r'[\u0c80-\u0cff]', "ml"),                   # Malayalam
        (r'[\u0600-\u06ff]', "ar"),                   # Arabic
        (r'[\u0750-\u077f]', "ar"),                   # Arabic Supplement
        (r'[\u0590-\u05ff]', "he"),                   # Hebrew
        (r'[\u0400-\u04ff]', "ru"),                   # Cyrillic
        (r'[\u1000-\u109f]', "my"),                   # Myanmar/Burmese
        (r'[\u1780-\u17ff]', "km"),                   # Khmer
        (r'[\u0f00-\u0fff]', "bo"),                   # Tibetan
    ]
    for pattern, code in ranges:
        if re.search(pattern, sample):
            return code
    # Latin-script detection: check for common diacritics
    if re.search(r'[àâäéèêëïîôùûüÿçœæ]', sample, re.IGNORECASE):
        return "fr"
    if re.search(r'[äöüß]', sample, re.IGNORECASE):
        return "de"
    if re.search(r'[áéíóúñ¿¡]', sample, re.IGNORECASE):
        return "es"
    if re.search(r'[àèìòù]', sample, re.IGNORECASE):
        return "it"
    if re.search(r'[ãõç]', sample, re.IGNORECASE):
        return "pt"
    return "auto"


def estimate_quality(text: str, source: str, target: str, engine: str) -> float:
    """Heuristic quality score (0.0–1.0) based on translation artifacts."""
    if not text:
        return 0.0
    score = 1.0
    # Penalize if translation is identical to source (likely untranslated)
    if text.strip().lower() == (source or "").strip().lower():
        score -= 0.5
    # Penalize very short output relative to input
    ratio = len(text) / max(len(source), 1)
    if ratio < 0.2:
        score -= 0.3
    elif ratio > 3.0:
        score -= 0.2
    # Penalize leftover placeholder artifacts
    if re.search(r'__[A-Z]+_\d+__', text):
        score -= 0.1
    # Reward engines with known higher quality
    engine_bonus = {"deepl": 0.1, "google": 0.05, "lingvanex": 0.05}
    score += engine_bonus.get(engine, 0.0)
    return max(0.0, min(1.0, score))


def _split_text(text: str, max_chars: int):
    """Split text into chunks at sentence/paragraph boundaries, never mid-word."""
    if len(text) <= max_chars:
        return [text]
    paragraphs = text.split("\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if not para.strip():
            # Preserve blank lines
            if current:
                current += "\n"
            continue
        if len(para) > max_chars:
            # Long paragraph: split at sentence boundaries
            sentences = re.split(r'(?<=[.!?。！？])\s+', para)
            for sent in sentences:
                if len(sent) > max_chars:
                    # Still too long: split at clause/semicolon boundaries
                    clauses = re.split(r'(?<=[;；,，])\s*', sent)
                    for clause in clauses:
                        if len(current) + len(clause) + 2 > max_chars and current:
                            chunks.append(current.rstrip())
                            current = clause
                        else:
                            current = (current + " " + clause) if current else clause
                elif len(current) + len(sent) + 1 > max_chars:
                    if current:
                        chunks.append(current.rstrip())
                    current = sent
                else:
                    current = (current + " " + sent) if current else sent
        else:
            if len(current) + len(para) + 1 > max_chars:
                if current:
                    chunks.append(current.rstrip())
                current = para
            else:
                current = (current + "\n" + para) if current else para
    if current and current.strip():
        chunks.append(current.rstrip())
    return chunks


class GoogleEngine:
    BASE_URL = "https://translate.googleapis.com/translate_a/single"
    MAX_CHARS = 4500

    def translate(self, text: str, source: str = "auto", target: str = "en") -> TranslationResult:
        src = resolve_lang_code(source)
        tgt = resolve_lang_code(target)
        t0 = time.monotonic()
        try:
            chunks = _split_text(text, self.MAX_CHARS) if len(text) > self.MAX_CHARS else [text]
            results = []
            detected_src = src
            for chunk in chunks:
                def _do_request(c=chunk):
                    params = {
                        "client": "gtx",
                        "sl": src,
                        "tl": tgt,
                        "dt": "t",
                        "q": c,
                    }
                    resp = requests.get(self.BASE_URL, params=params, timeout=15)
                    resp.raise_for_status()
                    return resp.json()
                data = _retry(_do_request, max_retries=3, base_delay=1.0, engine_name="google")
                parts = [seg[0] for seg in data[0] if seg[0]]
                results.append("".join(parts))
                if src == "auto" and data[2]:
                    detected_src = data[2]
            elapsed = (time.monotonic() - t0) * 1000
            result_text = "\n".join(results)
            return TranslationResult(
                text=result_text,
                engine="google",
                source_language=detected_src,
                target_language=tgt,
                success=True,
                quality_score=estimate_quality(result_text, text, tgt, "google"),
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("GoogleEngine error: %s", e)
            return TranslationResult(
                text="",
                engine="google",
                source_language=src,
                target_language=tgt,
                success=False,
                error=str(e),
                latency_ms=elapsed,
            )


class MyMemoryEngine:
    BASE_URL = "http://api.mymemory.translated.net/get"
    MAX_CHARS = 450

    def translate(self, text: str, source: str = "auto", target: str = "en") -> TranslationResult:
        src = resolve_lang_code(source)
        tgt = resolve_lang_code(target)
        if src == "auto":
            detected = detect_language(text)
            src = detected if detected != "auto" else "en"
        t0 = time.monotonic()
        try:
            chunks = _split_text(text, self.MAX_CHARS) if len(text) > self.MAX_CHARS else [text]
            results = []
            for chunk in chunks:
                def _do_request(c=chunk):
                    params = {"q": c, "langpair": f"{src}|{tgt}"}
                    resp = requests.get(self.BASE_URL, params=params, timeout=15)
                    resp.raise_for_status()
                    return resp.json()
                data = _retry(_do_request, max_retries=3, base_delay=1.5, engine_name="mymemory")
                translated = data.get("responseData", {}).get("translatedText", "")
                if not translated:
                    matches = data.get("matches", [])
                    if matches:
                        translated = matches[0].get("translation", "")
                results.append(translated)
            elapsed = (time.monotonic() - t0) * 1000
            result_text = "\n".join(results)
            return TranslationResult(
                text=result_text,
                engine="mymemory",
                source_language=src,
                target_language=tgt,
                success=True,
                quality_score=estimate_quality(result_text, text, tgt, "mymemory"),
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("MyMemoryEngine error: %s", e)
            return TranslationResult(
                text="",
                engine="mymemory",
                source_language=src,
                target_language=tgt,
                success=False,
                error=str(e),
                latency_ms=elapsed,
            )


class DeepLEngine:
    BASE_URL_FREE = "https://api-free.deepl.com/v2/translate"

    def translate(self, text: str, source: str = "auto", target: str = "en") -> TranslationResult:
        src = resolve_lang_code(source)
        tgt = resolve_lang_code(target)
        api_key = os.getenv("DEEPL_API_KEY")
        if not api_key:
            return TranslationResult(
                text="", engine="deepl", source_language=src, target_language=tgt,
                success=False, error="DEEPL_API_KEY not set",
            )
        t0 = time.monotonic()
        try:
            def _do_request():
                payload = {"auth_key": api_key, "text": text, "target_lang": tgt.upper()}
                if src != "auto":
                    payload["source_lang"] = src.upper()
                resp = requests.post(self.BASE_URL_FREE, json=payload, timeout=15)
                resp.raise_for_status()
                return resp.json()
            data = _retry(_do_request, max_retries=3, base_delay=1.0, engine_name="deepl")
            translated = data["translations"][0]["text"]
            detected = data["translations"][0].get("detected_source_language", src).lower()
            elapsed = (time.monotonic() - t0) * 1000
            return TranslationResult(
                text=translated, engine="deepl", source_language=detected, target_language=tgt,
                success=True,
                quality_score=estimate_quality(translated, text, tgt, "deepl"),
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("DeepLEngine error: %s", e)
            return TranslationResult(
                text="", engine="deepl", source_language=src, target_language=tgt,
                success=False, error=str(e), latency_ms=elapsed,
            )


class LibreEngine:
    def translate(self, text: str, source: str = "auto", target: str = "en") -> TranslationResult:
        src = resolve_lang_code(source)
        tgt = resolve_lang_code(target)
        base_url = os.getenv("LIBRE_TRANSLATE_URL", "https://libretranslate.com")
        api_key = os.getenv("LIBRE_API_KEY", "")
        t0 = time.monotonic()
        try:
            def _do_request():
                payload = {"q": text, "source": src, "target": tgt, "format": "text"}
                if api_key:
                    payload["api_key"] = api_key
                resp = requests.post(f"{base_url}/translate", json=payload, timeout=30)
                resp.raise_for_status()
                return resp.json()
            data = _retry(_do_request, max_retries=3, base_delay=2.0, engine_name="libre")
            translated = data.get("translatedText", "")
            elapsed = (time.monotonic() - t0) * 1000
            return TranslationResult(
                text=translated, engine="libre", source_language=src, target_language=tgt,
                success=True,
                quality_score=estimate_quality(translated, text, tgt, "libre"),
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("LibreEngine error: %s", e)
            return TranslationResult(
                text="", engine="libre", source_language=src, target_language=tgt,
                success=False, error=str(e), latency_ms=elapsed,
            )


class ArgosEngine:
    def translate(self, text: str, source: str = "auto", target: str = "en") -> TranslationResult:
        src = resolve_lang_code(source)
        tgt = resolve_lang_code(target)
        t0 = time.monotonic()
        try:
            import argostranslate.translate as tr
            translated = tr.translate(text, src, tgt)
            elapsed = (time.monotonic() - t0) * 1000
            return TranslationResult(
                text=translated, engine="argos", source_language=src, target_language=tgt,
                success=True,
                quality_score=estimate_quality(translated, text, tgt, "argos"),
                latency_ms=elapsed,
            )
        except ImportError:
            elapsed = (time.monotonic() - t0) * 1000
            return TranslationResult(
                text="", engine="argos", source_language=src, target_language=tgt,
                success=False, error="argos-translate not installed", latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("ArgosEngine error: %s", e)
            return TranslationResult(
                text="", engine="argos", source_language=src, target_language=tgt,
                success=False, error=str(e), latency_ms=elapsed,
            )


class LingvanexEngine:
    """Lingvanex free translation API (https://api-b2b.backenster.com)."""
    BASE_URL = "https://api-b2b.backenster.com/api/v3/translate"

    def translate(self, text: str, source: str = "auto", target: str = "en") -> TranslationResult:
        src = resolve_lang_code(source)
        tgt = resolve_lang_code(target)
        api_key = os.getenv("LINGVANEX_API_KEY", "")
        if not api_key:
            return TranslationResult(
                text="", engine="lingvanex", source_language=src, target_language=tgt,
                success=False, error="LINGVANEX_API_KEY not set",
            )
        t0 = time.monotonic()
        try:
            def _do_request():
                payload = {
                    "from": src if src != "auto" else "auto",
                    "to": tgt,
                    "data": text,
                    "platform": "api",
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(self.BASE_URL, json=payload, headers=headers, timeout=15)
                resp.raise_for_status()
                return resp.json()
            data = _retry(_do_request, max_retries=3, base_delay=1.5, engine_name="lingvanex")
            translated = data.get("result", data.get("translatedText", ""))
            detected = data.get("from", src)
            elapsed = (time.monotonic() - t0) * 1000
            return TranslationResult(
                text=translated, engine="lingvanex", source_language=detected, target_language=tgt,
                success=True,
                quality_score=estimate_quality(translated, text, tgt, "lingvanex"),
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("LingvanexEngine error: %s", e)
            return TranslationResult(
                text="", engine="lingvanex", source_language=src, target_language=tgt,
                success=False, error=str(e), latency_ms=elapsed,
            )


ENGINES = {
    "google": GoogleEngine,
    "mymemory": MyMemoryEngine,
    "deepl": DeepLEngine,
    "libre": LibreEngine,
    "argos": ArgosEngine,
    "lingvanex": LingvanexEngine,
}


def get_engine(name: str):
    cls = ENGINES.get(name.lower())
    if cls:
        return cls()
    raise ValueError(f"Unknown engine: {name}. Available: {', '.join(ENGINES.keys())}")


def translate_with_fallback(text: str, primary_engine: str, source: str, target: str, fallback_engines=None):
    engine = get_engine(primary_engine)
    result = engine.translate(text, source, target)
    if result.success:
        return result
    if fallback_engines:
        for fb_name in fallback_engines:
            try:
                fb_engine = get_engine(fb_name)
                fb_result = fb_engine.translate(text, source, target)
                if fb_result.success:
                    return fb_result
            except Exception:
                continue
    return result


def compare_engines(text: str, source: str, target: str, engines: list[str] | None = None) -> list[TranslationResult]:
    """Run translation on multiple engines and return sorted results by quality_score."""
    if engines is None:
        engines = ["google", "mymemory", "deepl", "libre", "lingvanex"]
    results = []
    for eng_name in engines:
        try:
            eng = get_engine(eng_name)
            result = eng.translate(text, source, target)
            results.append(result)
        except Exception as e:
            logger.warning("compare_engines: %s failed: %s", eng_name, e)
            results.append(TranslationResult(
                text="", engine=eng_name, source_language=source, target_language=target,
                success=False, error=str(e),
            ))
    results.sort(key=lambda r: r.quality_score if r.success else -1, reverse=True)
    return results


def stream_translate(text: str, engine_name: str, source: str, target: str):
    yield {"status": "translating", "engine": engine_name}
    try:
        engine = get_engine(engine_name)
        result = engine.translate(text, source, target)
        if result.success:
            yield {
                "text": result.text,
                "engine_used": result.engine,
                "source_detected": result.source_language,
            }
        else:
            yield {"error": result.error}
    except Exception as e:
        yield {"error": str(e)}
