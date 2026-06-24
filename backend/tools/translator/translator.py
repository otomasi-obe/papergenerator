#!/usr/bin/env python3
"""
Comprehensive AI-Powered Translation Tool
=========================================

Features:
  1. AI-powered translation via local LLM (primary method)
  2. Support for 50+ languages
  3. Auto-detect source language
  4. Batch translation (file-based)
  5. Context preservation
  6. Domain-specific translation (academic, technical, casual)
  7. Back-translation for quality checking
  8. Translation comparison (multiple outputs)
  9. Glossary / terminology support (preserve specific terms)
  10. Export translated documents (.txt, .md, .json)

Usage:
  python translator.py --text "Hello world" --target French
  python translator.py --file input.txt --target Japanese --domain academic
  python translator.py --file input.txt --target German --back-translate
  python translator.py --file input.txt --target Spanish --compare
  python translator.py --file input.txt --target Chinese --glossary glossary.json
  python translator.py --file input.txt --target Korean --output result.md --format md

Author: PaperRiset Translation Tools
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime

# ── shared AI client ──────────────────────────────────────────────────────────
sys.path.append(str(Path(__file__).resolve().parent.parent))
from shared_ai_client import ai_generate

# ── Constants ──────────────────────────────────────────────────────────────────

SUPPORTED_LANGUAGES = {
    "afrikaans": "Afrikaans", "albanian": "Albanian", "amharic": "Amharic",
    "arabic": "Arabic", "armenian": "Armenian", "azerbaijani": "Azerbaijani",
    "basque": "Basque", "belarusian": "Belarusian", "bengali": "Bengali",
    "bosnian": "Bosnian", "bulgarian": "Bulgarian", "burmese": "Burmese",
    "catalan": "Catalan", "chinese": "Chinese", "croatian": "Croatian",
    "czech": "Czech", "danish": "Danish", "dutch": "Dutch",
    "english": "English", "estonian": "Estonian", "finnish": "Finnish",
    "french": "French", "galician": "Galician", "georgian": "Georgian",
    "german": "German", "greek": "Greek", "gujarati": "Gujarati",
    "hebrew": "Hebrew", "hindi": "Hindi", "hungarian": "Hungarian",
    "icelandic": "Icelandic", "indonesian": "Indonesian", "irish": "Irish",
    "italian": "Italian", "japanese": "Japanese", "kannada": "Kannada",
    "kazakh": "Kazakh", "korean": "Korean", "latvian": "Latvian",
    "lithuanian": "Lithuanian", "macedonian": "Macedonian", "malay": "Malay",
    "malayalam": "Malayalam", "marathi": "Marathi", "mongolian": "Mongolian",
    "nepali": "Nepali", "norwegian": "Norwegian", "persian": "Persian",
    "polish": "Polish", "portuguese": "Portuguese", "punjabi": "Punjabi",
    "romanian": "Romanian", "russian": "Russian", "serbian": "Serbian",
    "slovak": "Slovak", "slovenian": "Slovenian", "somali": "Somali",
    "spanish": "Spanish", "swahili": "Swahili", "swedish": "Swedish",
    "tamil": "Tamil", "telugu": "Telugu", "thai": "Thai",
    "turkish": "Turkish", "ukrainian": "Ukrainian", "urdu": "Urdu",
    "uzbek": "Uzbek", "vietnamese": "Vietnamese", "welsh": "Welsh",
    "xhosa": "Xhosa", "yoruba": "Yoruba", "zulu": "Zulu",
}

DOMAINS = {
    "academic": {
        "label": "Academic",
        "instruction": (
            "Translate using formal academic register. Preserve citations, "
            "references, and scholarly terminology. Maintain the original "
            "academic tone and precision. Do not simplify technical terms."
        ),
    },
    "technical": {
        "label": "Technical",
        "instruction": (
            "Translate with technical accuracy. Preserve code snippets, "
            "variable names, and domain-specific jargon. Keep the tone "
            "professional and precise. Do not translate proper nouns or "
            "brand names."
        ),
    },
    "casual": {
        "label": "Casual",
        "instruction": (
            "Translate in a natural, conversational tone. Adapt idioms and "
            "cultural references to feel native in the target language. "
            "Keep it friendly and approachable."
        ),
    },
    "legal": {
        "label": "Legal",
        "instruction": (
            "Translate with legal precision. Preserve the exact meaning of "
            "all clauses and terms. Use formal legal register. Do not "
            "paraphrase — maintain exact legal equivalence."
        ),
    },
    "medical": {
        "label": "Medical",
        "instruction": (
            "Translate using standard medical terminology. Preserve Latin "
            "terms and anatomical names. Maintain clinical precision and "
            "formality."
        ),
    },
    "general": {
        "label": "General",
        "instruction": (
            "Translate naturally and accurately. Preserve the original "
            "meaning, tone, and style. Adapt idioms where needed."
        ),
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_language(name: str) -> str:
    """Resolve a language name (case-insensitive) to its canonical form."""
    key = name.strip().lower()
    if key in SUPPORTED_LANGUAGES:
        return SUPPORTED_LANGUAGES[key]
    # Try reverse lookup by value
    for v in SUPPORTED_LANGUAGES.values():
        if v.lower() == key:
            return v
    raise ValueError(
        f"Unsupported language: '{name}'. "
        f"Use --list-languages to see all {len(SUPPORTED_LANGUAGES)} supported languages."
    )


def _load_glossary(path: str) -> dict:
    """Load a glossary JSON file mapping source terms → target terms."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Glossary file not found: {path}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Glossary file must be a JSON object {source_term: target_term}")
    return data


def _apply_glossary(text: str, glossary: dict, reverse: bool = False) -> tuple:
    """
    Replace glossary terms with placeholders before translation.
    Returns (modified_text, placeholder_map).
    """
    placeholder_map = {}
    modified = text
    for idx, (src, tgt) in enumerate(glossary.items()):
        if reverse:
            term = tgt
        else:
            term = src
        placeholder = f"__GLOSSARY_{idx}__"
        if term in modified:
            placeholder_map[placeholder] = tgt if not reverse else src
            modified = modified.replace(term, placeholder)
    return modified, placeholder_map


def _restore_glossary(text: str, placeholder_map: dict) -> str:
    """Restore glossary placeholders with their target terms."""
    result = text
    for placeholder, term in placeholder_map.items():
        result = result.replace(placeholder, term)
    return result


def _chunk_text(text: str, max_chars: int = 3000) -> list:
    """Split text into chunks at paragraph/sentence boundaries, never mid-word."""
    if len(text) <= max_chars:
        return [text]
    paragraphs = text.split("\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if not para.strip():
            if current:
                current += "\n"
            continue
        if len(para) > max_chars:
            sentences = re.split(r'(?<=[.!?。！？])\s+', para)
            for sent in sentences:
                if len(sent) > max_chars:
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


# ── Core Translation Functions ─────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """Auto-detect the source language of the given text."""
    system = (
        "You are a language detection expert. Respond with ONLY the full "
        "English name of the language (e.g., 'English', 'French', 'Japanese'). "
        "Do not add any explanation or punctuation."
    )
    prompt = f"What language is the following text written in?\n\n{text[:500]}"
    result = ai_generate(prompt, system_prompt=system, max_tokens=50, temperature=0.0)
    return result.strip().rstrip(".")


def translate_text(
    text: str,
    target_language: str,
    source_language: str = "auto",
    domain: str = "general",
    glossary: dict = None,
    context: str = "",
    temperature: float = 0.3,
) -> str:
    """
    Translate text to the target language.

    Args:
        text:            Source text to translate.
        target_language: Target language name (e.g., 'French').
        source_language: Source language or 'auto' for detection.
        domain:          Translation domain (academic/technical/casual/legal/medical/general).
        glossary:        Optional dict of {source_term: target_term} to preserve.
        context:         Additional context to guide translation.
        temperature:     LLM temperature (lower = more deterministic).

    Returns:
        Translated text string.
    """
    target = _resolve_language(target_language)

    # Auto-detect source language
    if source_language.lower() == "auto":
        source = detect_language(text)
        print(f"  [auto-detect] Source language: {source}")
    else:
        source = _resolve_language(source_language)

    if source.lower() == target.lower():
        print(f"  [info] Source and target are both '{source}'. Returning original text.")
        return text

    # Apply glossary placeholders
    placeholder_map = {}
    if glossary:
        text, placeholder_map = _apply_glossary(text, glossary)

    # Build domain instruction
    domain_info = DOMAINS.get(domain, DOMAINS["general"])
    domain_instruction = domain_info["instruction"]

    # Build context instruction
    context_instruction = ""
    if context:
        context_instruction = (
            f"\n\nAdditional context for translation:\n{context}\n"
            "Use this context to ensure accurate and consistent translation."
        )

    # Translate in chunks if needed
    chunks = _chunk_text(text)
    translated_chunks = []

    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"  [chunk {i+1}/{len(chunks)}] Translating...")

        system = (
            f"You are a professional translator. Translate from {source} to {target}.\n"
            f"Domain: {domain_info['label']}. {domain_instruction}\n"
            "Rules:\n"
            "- Output ONLY the translated text. Do NOT add explanations.\n"
            "- Preserve formatting, line breaks, and paragraph structure.\n"
            "- Keep placeholders like __GLOSSARY_N__ unchanged.\n"
            "- Preserve any markdown, LaTeX, or code formatting."
            f"{context_instruction}"
        )

        prompt = f"Translate the following {source} text to {target}:\n\n{chunk}"

        translated = ai_generate(
            prompt, system_prompt=system, max_tokens=4096, temperature=temperature
        )
        translated_chunks.append(translated)

    result = "\n".join(translated_chunks)

    # Restore glossary terms
    if placeholder_map:
        result = _restore_glossary(result, placeholder_map)

    return result


def back_translate(text: str, target_language: str, source_language: str = "auto",
                   domain: str = "general") -> dict:
    """
    Translate text to target language and back to source for quality checking.

    Returns a dict with keys: original, translated, back_translated, similarity_note
    """
    target = _resolve_language(target_language)

    # Forward translation
    print("  [1/2] Forward translation...")
    translated = translate_text(text, target, source_language=source_language, domain=domain)

    # Determine source for back-translation
    if source_language.lower() == "auto":
        source = detect_language(text)
    else:
        source = _resolve_language(source_language)

    # Back translation
    print("  [2/2] Back translation...")
    back_translated = translate_text(translated, source, source_language=target, domain=domain)

    # Ask LLM to assess quality
    system = (
        "You are a translation quality assessor. Compare the original text with "
        "the back-translated text and rate the translation quality. "
        "Respond with a brief assessment (1-3 sentences) noting any meaning drift, "
        "omissions, or additions."
    )
    prompt = (
        f"Original ({source}):\n{text[:1000]}\n\n"
        f"Back-translated ({source}):\n{back_translated[:1000]}\n\n"
        "Assess the translation quality:"
    )
    assessment = ai_generate(prompt, system_prompt=system, max_tokens=200, temperature=0.3)

    return {
        "original": text,
        "translated": translated,
        "back_translated": back_translated,
        "source_language": source,
        "target_language": target,
        "quality_assessment": assessment,
    }


def _estimate_quality(original: str, translated: str, source_lang: str, target_lang: str) -> dict:
    """Estimate translation quality using heuristics and LLM assessment."""
    import re as _re

    scores = {}

    # Length ratio check
    ratio = len(translated) / max(len(original), 1)
    scores["length_ratio"] = round(ratio, 2)
    if 0.3 <= ratio <= 3.0:
        scores["length_score"] = 1.0
    elif 0.2 <= ratio <= 5.0:
        scores["length_score"] = 0.6
    else:
        scores["length_score"] = 0.2

    # Untranslated check (same text)
    if translated.strip().lower() == original.strip().lower():
        scores["untranslated_penalty"] = True
    else:
        scores["untranslated_penalty"] = False

    # Placeholder preservation
    placeholders_original = set(_re.findall(r'__\w+_\d+__', original))
    placeholders_translated = set(_re.findall(r'__\w+_\d+__', translated))
    if placeholders_original:
        preserved = len(placeholders_original & placeholders_translated)
        scores["placeholder_preservation"] = round(preserved / len(placeholders_original), 2)
    else:
        scores["placeholder_preservation"] = 1.0

    # Citation preservation (simple check for [Author, Year] patterns)
    citations_orig = set(_re.findall(r'\[[\w\s,.\d]+\]', original))
    citations_trans = set(_re.findall(r'\[[\w\s,.\d]+\]', translated))
    if citations_orig:
        preserved_cit = len(citations_orig & citations_trans)
        scores["citation_preservation"] = round(preserved_cit / len(citations_orig), 2)
    else:
        scores["citation_preservation"] = 1.0

    # Overall score
    overall = (
        scores.get("length_score", 0.5) * 0.2
        + scores.get("placeholder_preservation", 1.0) * 0.3
        + scores.get("citation_preservation", 1.0) * 0.3
        + (0.0 if scores.get("untranslated_penalty") else 0.2)
    )
    scores["overall"] = round(overall, 2)
    return scores


def compare_translations(text: str, target_language: str, source_language: str = "auto",
                         domain: str = "general", engines: list = None) -> dict:
    """
    Generate multiple translation variants and compare them.

    Args:
        text:            Source text.
        target_language: Target language.
        source_language: Source language or 'auto'.
        domain:          Translation domain.
        engines:         Optional list of engine names to use for comparison.
                         If None, uses AI with different temperatures.

    Returns a dict with keys: original, variants (list), comparison, best_variant
    """
    target = _resolve_language(target_language)
    source = _resolve_language(source_language) if source_language.lower() != "auto" else detect_language(text)

    variants = []

    if engines:
        # Engine-based comparison
        from .engines import get_engine, TranslationResult
        for eng_name in engines:
            print(f"  [{eng_name}] Translating...")
            try:
                eng = get_engine(eng_name)
                result = eng.translate(text, source=source, target=target)
                if isinstance(result, TranslationResult) and result.success:
                    quality = _estimate_quality(text, result.text, source, target)
                    variants.append({
                        "label": eng_name,
                        "engine": eng_name,
                        "text": result.text,
                        "quality_score": result.quality_score,
                        "latency_ms": round(result.latency_ms),
                        "quality_assessment": quality,
                    })
                else:
                    err = result.error if isinstance(result, TranslationResult) else "Unknown error"
                    variants.append({
                        "label": eng_name,
                        "engine": eng_name,
                        "text": "",
                        "error": err,
                    })
            except Exception as e:
                variants.append({
                    "label": eng_name,
                    "engine": eng_name,
                    "text": "",
                    "error": str(e),
                })
    else:
        # AI temperature-based comparison (original behavior)
        temperatures = [0.1, 0.4, 0.7]
        labels = ["Conservative", "Balanced", "Creative"]
        for temp, label in zip(temperatures, labels):
            print(f"  [{label}] Generating variant (temp={temp})...")
            domain_info = DOMAINS.get(domain, DOMAINS["general"])
            system = (
                f"You are a professional translator. Translate from {source} to {target}.\n"
                f"Domain: {domain_info['label']}. {domain_info['instruction']}\n"
                "Output ONLY the translated text. Preserve formatting."
            )
            prompt = f"Translate the following {source} text to {target}:\n\n{text}"
            result = ai_generate(prompt, system_prompt=system, max_tokens=4096, temperature=temp)
            quality = _estimate_quality(text, result, source, target)
            variants.append({
                "label": label,
                "temperature": temp,
                "text": result,
                "quality_assessment": quality,
            })

    # Filter successful variants
    successful = [v for v in variants if v.get("text") and not v.get("error")]

    # Determine best variant
    best_variant = None
    if successful:
        best_variant = max(successful, key=lambda v: v.get("quality_assessment", {}).get("overall", 0))

    # LLM comparison analysis
    comparison = ""
    if len(successful) >= 2:
        system = (
            "You are a translation expert. Compare the following translation variants "
            "and provide a brief analysis of differences, strengths, and weaknesses of each. "
            "Recommend the best variant and explain why."
        )
        comparison_text = f"Original ({source}):\n{text[:500]}\n\n"
        for v in successful:
            comparison_text += f"--- {v['label']} ---\n{v['text'][:500]}\n\n"
        comparison_text += "Analysis:"
        comparison = ai_generate(comparison_text, system_prompt=system, max_tokens=500, temperature=0.3)

    return {
        "original": text,
        "source_language": source,
        "target_language": target,
        "variants": variants,
        "best_variant": best_variant["label"] if best_variant else None,
        "comparison": comparison,
    }


def batch_translate(input_path: str, target_language: str, source_language: str = "auto",
                    domain: str = "general", glossary: dict = None,
                    output_path: str = None, output_format: str = "txt") -> str:
    """
    Translate an entire file.

    Args:
        input_path:      Path to the input file.
        target_language: Target language.
        source_language: Source language or 'auto'.
        domain:          Translation domain.
        glossary:        Optional glossary dict.
        output_path:     Output file path (auto-generated if None).
        output_format:   Output format: txt, md, json.

    Returns:
        Path to the output file.
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with open(input_file, "r", encoding="utf-8") as f:
        text = f.read()

    print(f"  Reading: {input_file} ({len(text)} chars)")

    translated = translate_text(
        text, target_language,
        source_language=source_language,
        domain=domain,
        glossary=glossary,
    )

    # Determine output path
    if output_path is None:
        stem = input_file.stem
        target_tag = target_language.lower().replace(" ", "_")
        output_path = str(input_file.parent / f"{stem}_{target_tag}.{output_format}")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        data = {
            "source_file": str(input_file),
            "source_language": source_language,
            "target_language": _resolve_language(target_language),
            "domain": domain,
            "translated_at": datetime.now().isoformat(),
            "original_text": text,
            "translated_text": translated,
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    elif output_format == "md":
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# Translation: {input_file.name}\n\n")
            f.write(f"- **Source:** {source_language}\n")
            f.write(f"- **Target:** {_resolve_language(target_language)}\n")
            f.write(f"- **Domain:** {domain}\n")
            f.write(f"- **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            f.write(translated)
    else:  # txt
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(translated)

    print(f"  Output: {output_file}")
    return str(output_file)


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="translator.py",
        description="Comprehensive AI-Powered Translation Tool — 50+ languages, "
                    "domain-specific, glossary support, back-translation, comparison, batch.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s --text "Hello, how are you?" --target French
  %(prog)s --file paper.txt --target Japanese --domain academic
  %(prog)s --file notes.txt --target German --back-translate
  %(prog)s --file article.txt --target Spanish --compare
  %(prog)s --file doc.txt --target Chinese --glossary terms.json
  %(prog)s --file report.txt --target Korean --output report_ko.md --format md
  %(prog)s --list-languages
  %(prog)s --list-domains
        """,
    )

    # Input group
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--text", "-t", type=str, help="Text string to translate.")
    input_group.add_argument("--file", "-f", type=str, help="Path to input file for batch translation.")

    # Language options
    parser.add_argument("--target", type=str, help="Target language (e.g., French, Japanese).")
    parser.add_argument("--source", type=str, default="auto",
                        help="Source language (default: auto-detect).")
    parser.add_argument("--list-languages", action="store_true",
                        help="List all supported languages and exit.")
    parser.add_argument("--list-domains", action="store_true",
                        help="List all translation domains and exit.")

    # Translation options
    parser.add_argument("--domain", "-d", type=str, default="general",
                        choices=list(DOMAINS.keys()),
                        help="Translation domain (default: general).")
    parser.add_argument("--glossary", "-g", type=str,
                        help="Path to glossary JSON file {source_term: target_term}.")
    parser.add_argument("--context", "-c", type=str, default="",
                        help="Additional context to guide translation.")
    parser.add_argument("--temperature", type=float, default=0.3,
                        help="LLM temperature 0.0-1.0 (default: 0.3).")

    # Advanced features
    parser.add_argument("--back-translate", action="store_true",
                        help="Translate and back-translate for quality checking.")
    parser.add_argument("--compare", action="store_true",
                        help="Generate multiple translation variants and compare.")
    parser.add_argument("--engines", type=str, nargs="+",
                        help="Engines to use for --compare mode (e.g., google deepl lingvanex).")

    # Output options
    parser.add_argument("--output", "-o", type=str,
                        help="Output file path (for batch/file mode).")
    parser.add_argument("--format", type=str, default="txt",
                        choices=["txt", "md", "json"],
                        help="Output format (default: txt).")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── List modes ─────────────────────────────────────────────────────────
    if args.list_languages:
        print(f"\n  Supported Languages ({len(SUPPORTED_LANGUAGES)}):\n")
        cols = 3
        langs = sorted(SUPPORTED_LANGUAGES.values())
        for i in range(0, len(langs), cols):
            row = langs[i:i + cols]
            print("    " + "".join(f"{l:<22}" for l in row))
        print()
        return

    if args.list_domains:
        print("\n  Translation Domains:\n")
        for key, info in DOMAINS.items():
            print(f"    {key:<12} — {info['label']}")
            print(f"                 {info['instruction'][:80]}...")
        print()
        return

    # ── Validate required args ──────────────────────────────────────────────
    if not args.text and not args.file:
        parser.error("Provide --text or --file for translation.")
    if not args.target:
        parser.error("--target language is required.")

    # ── Load glossary ───────────────────────────────────────────────────────
    glossary = None
    if args.glossary:
        glossary = _load_glossary(args.glossary)
        print(f"  Loaded glossary: {len(glossary)} terms")

    # ── Execute ─────────────────────────────────────────────────────────────
    start_time = time.time()

    if args.back_translate:
        # Back-translation mode
        if args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            text = args.text

        result = back_translate(text, args.target, args.source, args.domain)

        print(f"\n{'='*60}")
        print(f"  BACK-TRANSLATION RESULT")
        print(f"{'='*60}")
        print(f"\n  Source: {result['source_language']}")
        print(f"  Target: {result['target_language']}")
        print(f"\n--- Original ---\n{result['original'][:500]}")
        print(f"\n--- Translated ---\n{result['translated'][:500]}")
        print(f"\n--- Back-Translated ---\n{result['back_translated'][:500]}")
        print(f"\n--- Quality Assessment ---\n{result['quality_assessment']}")

        if args.output:
            data = {**result, "domain": args.domain, "timestamp": datetime.now().isoformat()}
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n  Saved to: {args.output}")

    elif args.compare:
        # Comparison mode
        if args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            text = args.text

        result = compare_translations(text, args.target, args.source, args.domain,
                                      engines=args.engines)

        print(f"\n{'='*60}")
        print(f"  TRANSLATION COMPARISON")
        print(f"{'='*60}")
        for v in result["variants"]:
            label = v['label']
            if v.get("error"):
                print(f"\n--- {label} [FAILED] ---\n  Error: {v['error']}")
            else:
                quality = v.get("quality_assessment", {}).get("overall", "?")
                latency = v.get("latency_ms", "")
                suffix = f" (quality={quality}, {latency}ms)" if latency else ""
                print(f"\n--- {label}{suffix} ---\n{v['text'][:400]}")
        if result.get("best_variant"):
            print(f"\n  Best variant: {result['best_variant']}")
        if result.get("comparison"):
            print(f"\n--- Comparison ---\n{result['comparison']}")

        if args.output:
            data = {**result, "domain": args.domain, "timestamp": datetime.now().isoformat()}
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n  Saved to: {args.output}")

    elif args.file:
        # Batch file translation
        output = batch_translate(
            args.file, args.target,
            source_language=args.source,
            domain=args.domain,
            glossary=glossary,
            output_path=args.output,
            output_format=args.format,
        )
        print(f"\n  Translation saved to: {output}")

    elif args.text:
        # Single text translation
        result = translate_text(
            args.text, args.target,
            source_language=args.source,
            domain=args.domain,
            glossary=glossary,
            context=args.context,
            temperature=args.temperature,
        )
        print(f"\n{'='*60}")
        print(f"  TRANSLATION RESULT")
        print(f"{'='*60}")
        print(f"\n{result}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"\n  Saved to: {args.output}")

    elapsed = time.time() - start_time
    print(f"\n  ⏱  Completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
