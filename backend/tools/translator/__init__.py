"""tools.translator — public API: PROMPT, ENGINE_LIST, LANGUAGE_LIST, DOMAIN_LIST, run_translator."""

import json
import os
import re
import sys
from pathlib import Path
from typing import Generator

_PROMPT_PATH = Path(__file__).resolve().parent / "translator_prompt.txt"

_FALLBACK_SYSTEM = (
    "You are an expert professional translator with deep knowledge of linguistics, "
    "cultural nuances, and domain-specific terminology.\n\n"
    "CORE RULES:\n"
    "- Output ONLY the translated text. Never add explanations, notes, or commentary.\n"
    "- Preserve ALL formatting: line breaks, paragraph structure, indentation, bullet points, numbered lists.\n"
    "- Preserve ALL markdown (headers, bold, italic, links, code blocks), LaTeX commands, HTML tags, and code formatting verbatim.\n"
    "- Preserve ALL citations and references exactly as written (e.g., [Author, Year], (Smith et al., 2020), [1], footnote markers).\n"
    "- Preserve ALL technical terms, proper nouns, brand names, acronyms, and abbreviations without translation unless a standard translation exists in the target language.\n"
    "- Preserve ALL numbers, equations, formulas, units, and mathematical expressions exactly.\n"
    "- Preserve ALL __GLOSSARY_N__ placeholders unchanged.\n"
    "- Adapt idioms, metaphors, and cultural references to feel natural and native in the target language.\n"
    "- Maintain the original meaning, tone, register, and style with high fidelity.\n"
    "- For ambiguous terms, prefer the meaning most appropriate to the given domain context."
)

_FALLBACK_USER_TEMPLATE = (
    "Translate the following text into {option}.\n\n"
    "TEXT:\n{text}"
)


def _load_prompt() -> dict:
    if not _PROMPT_PATH.exists():
        return {"system": _FALLBACK_SYSTEM, "user_template": _FALLBACK_USER_TEMPLATE}
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in _PROMPT_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\[SECTION:(\w+)\]$", line.strip())
        if m:
            current = m.group(1)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    system = "\n".join(sections.get("SYSTEM", [])).strip()
    user_template = "\n".join(sections.get("USER_TEMPLATE", [])).strip()
    if not system or not user_template:
        return {"system": _FALLBACK_SYSTEM, "user_template": _FALLBACK_USER_TEMPLATE}
    return {"system": system, "user_template": user_template}


PROMPT = _load_prompt()

ENGINE_LIST: list[str] = ["ai", "google", "mymemory", "deepl", "libre", "argos", "lingvanex"]

LANGUAGE_LIST: list[str] = [
    "Afrikaans", "Albanian", "Amharic", "Arabic", "Armenian", "Azerbaijani",
    "Basque", "Belarusian", "Bengali", "Bosnian", "Bulgarian", "Burmese",
    "Catalan", "Chinese (Simplified)", "Chinese (Traditional)", "Croatian",
    "Czech", "Danish", "Dutch", "English", "Estonian", "Finnish", "French",
    "Galician", "Georgian", "German", "Greek", "Gujarati", "Hebrew", "Hindi",
    "Hungarian", "Icelandic", "Indonesian", "Irish", "Italian", "Japanese",
    "Kannada", "Kazakh", "Korean", "Latvian", "Lithuanian", "Macedonian",
    "Malay", "Malayalam", "Marathi", "Mongolian", "Nepali", "Norwegian",
    "Persian", "Polish", "Portuguese", "Punjabi", "Romanian", "Russian",
    "Serbian", "Slovak", "Slovenian", "Somali", "Spanish", "Swahili", "Swedish",
    "Tamil", "Telugu", "Thai", "Turkish", "Ukrainian", "Urdu", "Uzbek",
    "Vietnamese", "Welsh", "Xhosa", "Yoruba", "Zulu",
]

DOMAIN_LIST: list[str] = ["general", "academic", "technical", "casual", "legal", "medical"]

_DOMAIN_INSTRUCTIONS: dict[str, str] = {
    "academic": (
        "Translate using formal academic register appropriate for scholarly publications. "
        "Preserve all citations (APA, MLA, Chicago, IEEE, etc.) and references verbatim. "
        "Maintain scholarly terminology with precision — do not simplify or paraphrase technical terms. "
        "Preserve section headings, figure/table references, and footnote markers. "
        "Keep Latin terms (e.g., 'in vivo', 'et al.', 'ibid.') in their original form."
    ),
    "technical": (
        "Translate with strict technical accuracy. Preserve ALL code snippets, variable names, "
        "function signatures, API endpoints, and configuration keys verbatim. "
        "Do not translate proper nouns, brand names, product names, or SDK/framework names. "
        "Keep the tone professional and precise. Use the standard technical vocabulary "
        "of the target language's tech community where applicable."
    ),
    "casual": (
        "Translate in a natural, conversational tone appropriate for everyday communication. "
        "Freely adapt idioms, slang, and cultural references to feel native in the target language. "
        "Keep it friendly and approachable while preserving the original intent."
    ),
    "legal": (
        "Translate with legal precision. Preserve the exact meaning of all clauses, definitions, "
        "obligations, and conditions. Use formal legal register appropriate for the target jurisdiction. "
        "Do not paraphrase — maintain exact legal equivalence. "
        "Preserve article/section numbering, party names, and statutory references. "
        "Use standard legal terminology of the target language's legal system."
    ),
    "medical": (
        "Translate using standard medical and clinical terminology. Preserve Latin and Greek "
        "anatomical/medical terms in their internationally recognized form. "
        "Maintain clinical precision — do not paraphrase diagnoses, drug names, or procedures. "
        "Use WHO International Nomenclature where applicable. "
        "Preserve measurement units, dosages, and lab values exactly."
    ),
    "general": (
        "Translate naturally and accurately. Preserve the original meaning, tone, and style. "
        "Adapt idioms and cultural references where needed for readability."
    ),
}

def _stream_ai(system_prompt: str, user_prompt: str) -> Generator[dict, None, None]:
    """Stream AI response via the per-index endpoint chain, yielding dicts
    with a 'text' key."""
    import requests
    from utils.ai_tools.ai_client import stream_chat as _chain_stream
    from utils.ai_tools.model_config import get_primary_chat_model

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        for delta in _chain_stream(messages, heavy=False, max_tokens=4096, timeout=120):
            if delta:
                yield {"text": delta}
        return
    except RuntimeError as e:
        if "no endpoint configured" in str(e):
            yield {"error": "AI service not configured"}
        else:
            yield {"error": str(e)}
        return
    except requests.exceptions.Timeout:
        yield {"error": "AI service timeout"}
    except Exception as e:
        yield {"error": str(e)}


def _call_engine(engine: str, text: str, target_lang: str, source_lang: str, domain: str) -> Generator[dict, None, None]:
    """Call a non-AI translation engine, yielding text and metadata."""
    try:
        from .engines import get_engine, TranslationResult
        eng = get_engine(engine)
        result = eng.translate(text, source=source_lang, target=target_lang)
        if isinstance(result, TranslationResult):
            if result.success:
                yield {"text": result.text}
                if result.quality_score > 0:
                    yield {"quality_score": round(result.quality_score, 2)}
                if result.latency_ms > 0:
                    yield {"latency_ms": round(result.latency_ms)}
            else:
                yield {"error": result.error or f"Translation failed with {engine}"}
        elif isinstance(result, str):
            yield {"text": result}
        else:
            yield {"text": str(result)}
    except ImportError:
        yield {"error": f"Engine '{engine}' not available: engines.py not found"}
    except Exception as e:
        yield {"error": f"Engine '{engine}' failed: {e}"}


def _apply_glossary(text: str, glossary: dict) -> tuple[str, dict]:
    """Replace glossary terms with placeholders before translation."""
    placeholder_map = {}
    modified = text
    for idx, (src_term, tgt_term) in enumerate(glossary.items()):
        placeholder = f"__GLOSSARY_{idx}__"
        if src_term in modified:
            placeholder_map[placeholder] = tgt_term
            modified = modified.replace(src_term, placeholder)
    return modified, placeholder_map


def _restore_glossary(text: str, placeholder_map: dict) -> str:
    """Restore glossary placeholders with their target terms."""
    result = text
    for placeholder, term in placeholder_map.items():
        result = result.replace(placeholder, term)
    return result


def _compare_engines(text: str, source_lang: str, target_lang: str, engines: list[str]) -> Generator[dict, None, None]:
    """Run multiple engines and yield the best result based on quality score."""
    try:
        from .engines import compare_engines as _compare, resolve_lang_code
        src_code = resolve_lang_code(source_lang)
        tgt_code = resolve_lang_code(target_lang)
        results = _compare(text, src_code, tgt_code, engines)
        successful = [r for r in results if r.success and r.text]
        if not successful:
            errors = "; ".join(f"{r.engine}: {r.error}" for r in results if r.error)
            yield {"error": f"All engines failed. {errors}"}
            return
        best = successful[0]
        yield {"text": best.text}
        yield {"quality_score": round(best.quality_score, 2)}
        yield {"latency_ms": round(best.latency_ms)}
        comparisons = [
            {
                "engine": r.engine,
                "success": r.success,
                "quality_score": round(r.quality_score, 2),
                "latency_ms": round(r.latency_ms),
                "preview": r.text[:120] + "..." if len(r.text) > 120 else r.text,
                "error": r.error,
            }
            for r in results
        ]
        yield {"comparisons": comparisons}
    except Exception as e:
        yield {"error": f"Compare mode failed: {e}"}


def run_translator(data: dict) -> Generator[dict, None, None]:
    """Translate text using the specified engine, yielding SSE-ready dicts.

    Expected data keys:
        text (str): Source text to translate.
        option (str): Target language name (e.g., 'French', 'Indonesian').
        source_language (str): Source language or 'auto' (default: 'auto').
        engine (str): Translation engine — 'ai', 'google', 'mymemory', 'deepl', 'libre', 'argos', 'lingvanex' (default: 'ai').
        domain (str): Translation domain — 'general', 'academic', 'technical', 'casual', 'legal', 'medical' (default: 'general').
        glossary (dict): Optional {source_term: target_term} for consistent translation.
        compare (bool): If True, run multiple engines and pick the best result.

    Yields:
        dict: {'text': chunk} for streaming chunks.
        dict: {'engine_used': name, 'source_detected': lang} at the end.
        dict: {'quality_score': float} when available.
        dict: {'latency_ms': int} when available.
        dict: {'comparisons': [...]} in compare mode.
        dict: {'error': message} on failure.
    """
    text = (data.get("text") or "").strip()
    if not text:
        yield {"error": "No text provided"}
        return

    option = (data.get("option") or "").strip()
    if not option:
        yield {"error": "No target language provided (option)"}
        return

    source_language = (data.get("source_language") or "auto").strip()
    engine = (data.get("engine") or "ai").strip().lower()
    domain = (data.get("domain") or "general").strip().lower()
    glossary = data.get("glossary") or {}
    compare_mode = bool(data.get("compare"))

    if engine not in ENGINE_LIST and engine != "compare":
        yield {"error": f"Unsupported engine: {engine}. Choose from: {ENGINE_LIST}"}
        return

    if domain not in DOMAIN_LIST:
        yield {"error": f"Unsupported domain: {domain}. Choose from: {DOMAIN_LIST}"}
        return

    # Detect source language
    source_detected = source_language
    if source_language.lower() == "auto":
        try:
            from .engines import detect_language as _detect_lang, resolve_lang_name
            detected_code = _detect_lang(text)
            if detected_code and detected_code != "auto":
                source_detected = resolve_lang_name(detected_code)
            else:
                sys.path.append(str(Path(__file__).resolve().parent.parent))
                from shared_ai_client import ai_generate
                detect_system = (
                    "You are a language detection expert. Respond with ONLY the full "
                    "English name of the language (e.g., 'English', 'French', 'Japanese'). "
                    "Do not add any explanation or punctuation."
                )
                detect_prompt = f"What language is the following text written in?\n\n{text[:500]}"
                source_detected = ai_generate(detect_prompt, detect_system, max_tokens=50, temperature=0.0).strip().rstrip(".")
        except Exception:
            source_detected = "unknown"

    # Apply glossary placeholders
    placeholder_map = {}
    if glossary and isinstance(glossary, dict):
        text, placeholder_map = _apply_glossary(text, glossary)

    # Compare mode: run multiple engines
    if compare_mode or engine == "compare":
        compare_list = data.get("compare_engines") or ["google", "deepl", "mymemory", "lingvanex"]
        for chunk in _compare_engines(text, source_detected, option, compare_list):
            if "text" in chunk and placeholder_map:
                chunk["text"] = _restore_glossary(chunk["text"], placeholder_map)
            yield chunk
            if "error" in chunk:
                return
        yield {"engine_used": "compare", "source_detected": source_detected}
        return

    # Single engine mode
    if engine == "ai":
        domain_instruction = _DOMAIN_INSTRUCTIONS.get(domain, _DOMAIN_INSTRUCTIONS["general"])
        system = (
            f"{PROMPT['system']}\n\n"
            f"Domain: {domain}. {domain_instruction}\n"
            f"Translate from {source_detected} to {option}."
        )
        user_prompt = f"Translate the following text from {source_detected} to {option}:\n\n{text}"

        for chunk in _stream_ai(system, user_prompt):
            if "text" in chunk and placeholder_map:
                chunk["text"] = _restore_glossary(chunk["text"], placeholder_map)
            yield chunk
            if "error" in chunk:
                return

        yield {"engine_used": "ai", "source_detected": source_detected}
    else:
        for chunk in _call_engine(engine, text, option, source_detected, domain):
            # Restore glossary in text chunks
            if "text" in chunk and placeholder_map:
                chunk["text"] = _restore_glossary(chunk["text"], placeholder_map)
            yield chunk
            if "error" in chunk:
                return

        yield {"engine_used": engine, "source_detected": source_detected}


__all__ = [
    "PROMPT",
    "ENGINE_LIST",
    "LANGUAGE_LIST",
    "DOMAIN_LIST",
    "run_translator",
]
