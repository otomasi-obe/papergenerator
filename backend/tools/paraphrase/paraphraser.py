#!/usr/bin/env python3
"""
Powerful AI Paraphraser Tool
============================
Combines multiple paraphrasing strategies:
1. AI-powered paraphrasing (via local LLM)
2. Synonym-based rewriting (NLTK/WordNet)
3. Sentence structure transformation
4. Tone adjustment (formal, casual, academic)
5. Citation-aware processing
6. Batch processing support

Based on research from: Humanizer, Paraphrasing-Tool, mytext, nlpcloud-python,
                       EssayCompanion, PhraseItUp, llm-text-compressor

Usage:
    python paraphraser.py --input "Your text here" --style academic
    python paraphraser.py --file input.txt --style formal --output output.txt
    python paraphraser.py --interactive
"""
import argparse
import sys
import os
import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared_ai_client import ai_generate, load_env

from . import PROMPT, STYLE_CONFIGS, CITATION_PATTERNS, PRESERVE_TERMS


class CitationHandler:
    """Handles citation detection and preservation."""

    def __init__(self):
        self._compiled_patterns = [re.compile(p) for p in CITATION_PATTERNS]
        self._placeholder_prefix = "\u00a7CIT\u00a7"
        self._placeholder_suffix = "\u00a7"
        self._citations: List[str] = []

    def extract_citations(self, text: str) -> Tuple[str, List[str]]:
        """Extract citations and replace with placeholders."""
        self._citations = []
        result = text

        for pattern in self._compiled_patterns:
            matches = pattern.finditer(result)
            for match in reversed(list(matches)):
                citation = match.group()
                placeholder = f"{self._placeholder_prefix}{len(self._citations)}{self._placeholder_suffix}"
                self._citations.append(citation)
                result = result[:match.start()] + placeholder + result[match.end():]

        return result, self._citations

    def restore_citations(self, text: str) -> str:
        """Restore citations from placeholders."""
        result = text
        for i, citation in enumerate(self._citations):
            placeholder = f"{self._placeholder_prefix}{i}{self._placeholder_suffix}"
            result = result.replace(placeholder, citation)
        return result

    def has_citations(self, text: str) -> bool:
        """Check if text contains citations."""
        return any(p.search(text) for p in self._compiled_patterns)


class FormattingPreserver:
    """Preserves markdown/HTML formatting during processing."""

    def __init__(self):
        self._placeholders: Dict[str, str] = {}
        self._counter = 0

    def _make_placeholder(self, prefix: str) -> str:
        self._counter += 1
        return f"\u00a7{prefix}{self._counter}\u00a7"

    def preserve_formatting(self, text: str) -> str:
        """Replace formatting elements with placeholders."""
        result = text

        patterns = [
            (r'```[\s\S]*?```', 'CODEB'),
            (r'`[^`]+`', 'CODEI'),
            (r'\$\$[\s\S]*?\$\$', 'MATHB'),
            (r'\$[^\$]+\$', 'MATHI'),
            (r'<[^>]+>', 'HTML'),
            (r'!\[([^\]]*)\]\(([^)]+)\)', 'IMG'),
            (r'\[([^\]]+)\]\(([^)]+)\)', 'LINK'),
        ]

        for pattern, prefix in patterns:
            matches = list(re.finditer(pattern, result))
            for match in reversed(matches):
                placeholder = self._make_placeholder(prefix)
                self._placeholders[placeholder] = match.group()
                result = result[:match.start()] + placeholder + result[match.end():]

        return result

    def restore_formatting(self, text: str) -> str:
        """Restore formatting elements from placeholders."""
        result = text
        for placeholder, original in self._placeholders.items():
            result = result.replace(placeholder, original)
        return result

    def reset(self):
        """Reset state for a new processing run."""
        self._placeholders = {}
        self._counter = 0


class SynonymReplacer:
    """Lightweight synonym-based paraphrasing using NLTK WordNet."""

    def __init__(self):
        self._synonyms_cache = {}
        self._stopwords = set()
        self._initialized = False
        self._preserve_terms = set(PRESERVE_TERMS)

    def _init_nltk(self):
        if self._initialized:
            return
        try:
            import nltk
            for resource in ['wordnet', 'omw-1.4', 'averaged_perceptron_tagger',
                           'punkt', 'punkt_tab', 'stopwords']:
                try:
                    nltk.data.find(f'tokenizers/{resource}' if 'punkt' in resource
                                   else f'corpora/{resource}')
                except LookupError:
                    nltk.download(resource, quiet=True)
            from nltk.corpus import wordnet, stopwords
            self._stopwords = set(stopwords.words('english'))
            self._initialized = True
        except ImportError:
            print("[WARN] NLTK not available. Synonym replacement disabled.")

    def get_synonyms(self, word: str, pos: str = None) -> list:
        self._init_nltk()
        if not self._initialized:
            return []
        from nltk.corpus import wordnet
        cache_key = f"{word}_{pos}"
        if cache_key in self._synonyms_cache:
            return self._synonyms_cache[cache_key]

        synonyms = set()
        synsets = wordnet.synsets(word, pos=pos) if pos else wordnet.synsets(word)
        for syn in synsets[:3]:
            for lemma in syn.lemmas():
                name = lemma.name().replace('_', ' ')
                if name.lower() != word.lower() and len(name) > 2:
                    synonyms.add(name)

        result = list(synonyms)[:8]
        self._synonyms_cache[cache_key] = result
        return result

    def get_contextual_synonym(self, word: str, tag: str, context: str = "") -> Optional[str]:
        """Get a context-aware synonym using WordNet POS tags and sense disambiguation."""
        self._init_nltk()
        if not self._initialized:
            return None
        from nltk.corpus import wordnet

        pos_map = {
            'NN': wordnet.NOUN, 'NNS': wordnet.NOUN, 'NNP': wordnet.NOUN,
            'VB': wordnet.VERB, 'VBD': wordnet.VERB, 'VBG': wordnet.VERB,
            'VBN': wordnet.VERB, 'VBP': wordnet.VERB, 'VBZ': wordnet.VERB,
            'JJ': wordnet.ADJ, 'JJR': wordnet.ADJ, 'JJS': wordnet.ADJ,
            'RB': wordnet.ADV, 'RBR': wordnet.ADV, 'RBS': wordnet.ADV,
        }

        wn_pos = pos_map.get(tag)
        if not wn_pos:
            return None

        synsets = wordnet.synsets(word, pos=wn_pos)
        if not synsets:
            return None

        best_syn = synsets[0]
        if context:
            context_words = set(context.lower().split()) - {word.lower()}
            best_score = 0
            for syn in synsets[:5]:
                def_words = set(w.lower() for w in syn.definition().split())
                overlap = len(context_words & def_words)
                if overlap > best_score:
                    best_score = overlap
                    best_syn = syn

        candidates = []
        for lemma in best_syn.lemmas():
            name = lemma.name().replace('_', ' ')
            if name.lower() != word.lower() and len(name) > 2:
                candidates.append(name)

        if not candidates:
            for syn in synsets[1:3]:
                for lemma in syn.lemmas():
                    name = lemma.name().replace('_', ' ')
                    if name.lower() != word.lower() and len(name) > 2:
                        candidates.append(name)
                        if len(candidates) >= 3:
                            break

        import random
        return random.choice(candidates) if candidates else None

    def replace_synonyms(self, text: str, replacement_rate: float = 0.3,
                         context_aware: bool = False) -> str:
        self._init_nltk()
        if not self._initialized:
            return text
        from nltk import word_tokenize, pos_tag
        from nltk.corpus import wordnet

        words = word_tokenize(text)
        tagged = pos_tag(words)

        pos_map = {
            'NN': wordnet.NOUN, 'NNS': wordnet.NOUN, 'NNP': wordnet.NOUN,
            'VB': wordnet.VERB, 'VBD': wordnet.VERB, 'VBG': wordnet.VERB,
            'VBN': wordnet.VERB, 'VBP': wordnet.VERB, 'VBZ': wordnet.VERB,
            'JJ': wordnet.ADJ, 'JJR': wordnet.ADJ, 'JJS': wordnet.ADJ,
            'RB': wordnet.ADV, 'RBR': wordnet.ADV, 'RBS': wordnet.ADV,
        }

        import random
        result = []
        for i, (word, tag) in enumerate(tagged):
            wn_pos = pos_map.get(tag)
            if (wn_pos
                and word.lower() not in self._stopwords
                and word not in self._preserve_terms
                and word.upper() not in self._preserve_terms
                and len(word) > 3
                and random.random() < replacement_rate):
                if context_aware:
                    context_start = max(0, i - 5)
                    context_end = min(len(tagged), i + 5)
                    context = ' '.join(w for w, _ in tagged[context_start:context_end])
                    syn = self.get_contextual_synonym(word, tag, context)
                else:
                    syns = self.get_synonyms(word, wn_pos)
                    syn = syns[0] if syns else None
                if syn:
                    if word[0].isupper():
                        syn = syn[0].upper() + syn[1:]
                    result.append(syn)
                    continue
            result.append(word)

        return ' '.join(result)


class AIParaphraser:
    """AI-powered paraphrasing using the configured LLM."""

    STYLE_PROMPTS = {
        "standard": """You are an expert paraphrasing assistant. Paraphrase the following text
using clear, balanced language suitable for general use. Maintain the original meaning
while improving clarity and readability. Use natural sentence flow and varied structure.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], [2,3], (Author, Year), doi:10.xxx
- Preserve ALL formatting: **bold**, *italic*, `code`, ## headings, lists
- Preserve technical terms and proper nouns
- Return ONLY the paraphrased text""",

        "academic": """You are an academic writing expert. Paraphrase the following text
using formal academic language, proper scholarly tone, and sophisticated vocabulary.
Maintain the original meaning while improving clarity and academic rigor. Use passive
voice where appropriate, employ hedging language (e.g., "suggests", "may", "could"),
and ensure the text follows academic writing conventions. Integrate sources smoothly.

CRITICAL RULES:
- Preserve ALL citations exactly as positioned: [1], [2,3], (Author, Year), doi:10.xxx
- Preserve ALL formatting: **bold**, *italic*, `code`, $$math$$, ## headings
- Preserve technical terms and proper nouns exactly
- Do NOT add new citations or remove existing ones
- Return ONLY the paraphrased text""",

        "formal": """You are a professional writing expert. Paraphrase the following text
using formal, professional language suitable for business or official contexts. Maintain
the original meaning while making it polished and authoritative. Use precise vocabulary
and well-structured sentences.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], (Author, Year), doi references
- Preserve ALL formatting: **bold**, *italic*, `code`, ## headings
- Preserve technical terms and proper nouns
- Return ONLY the paraphrased text""",

        "casual": """You are a writing coach. Paraphrase the following text in a casual,
conversational tone while keeping the original meaning. Make it friendly, approachable,
and easy to read. Use contractions, shorter sentences, and everyday language.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], (Author, Year)
- Preserve ALL formatting: **bold**, *italic*, `code`, links
- Preserve technical terms and proper nouns
- Return ONLY the paraphrased text""",

        "simple": """You are a simplification expert. Paraphrase the following text using
simple, clear language that anyone can understand (aim for Grade 8 reading level). Break
down complex ideas into straightforward sentences. Replace jargon with plain language.
Use short sentences and common words while preserving the original meaning.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], (Author, Year)
- Preserve ALL formatting
- Keep proper nouns unchanged
- Return ONLY the paraphrased text""",

        "creative": """You are a creative writing expert. Paraphrase the following text
using creative, engaging language with vivid word choices and varied sentence structures.
Make it compelling and interesting while keeping the core message intact. Use metaphors,
analogies, and dynamic phrasing where appropriate.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], (Author, Year)
- Preserve ALL formatting
- Preserve technical meaning and accuracy
- Return ONLY the paraphrased text""",

        "seo": """You are an SEO content expert. Paraphrase the following text to be
more engaging and search-engine friendly. Use active voice, clear structure with
subheadings, natural keyword integration, scannable formatting, and compelling hooks.
Maintain the original meaning while optimizing for readability and search.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], (Author, Year)
- Preserve ALL formatting and link structure
- Preserve key terms (potential keywords)
- Return ONLY the paraphrased text""",

        "fluency": """You are a native-level English writing expert. Paraphrase the following
text to achieve the most natural, fluent expression possible. Focus on eliminating awkward
phrasing, improving transitions between ideas, and creating a smooth, enjoyable reading
experience. Vary sentence length and rhythm naturally.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], [2,3], (Author, Year), doi references
- Preserve ALL formatting: **bold**, *italic*, `code`, ## headings
- Preserve technical terms and proper nouns
- Return ONLY the paraphrased text""",

        "concise": """You are a text compression and concision expert. Paraphrase the
following text to be more concise while preserving all key information, main arguments,
and critical details. Eliminate redundancy, remove filler words, and use precise language.
Aim for approximately 70-80% of the original word count.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], (Author, Year), doi references
- Preserve ALL formatting
- Do NOT remove any cited claims or arguments
- Preserve technical terms and proper nouns
- Return ONLY the paraphrased text""",
    }

    def __init__(self):
        self._citation_handler = CitationHandler()

    def _get_style_config(self, style: str) -> dict:
        """Get style configuration from STYLE_CONFIGS."""
        return STYLE_CONFIGS.get(style, STYLE_CONFIGS.get("standard", {}))

    def paraphrase(self, text: str, style: str = "academic",
                   preserve_citations: bool = True) -> str:
        """Paraphrase text using AI with the specified style."""
        system_prompt = self.STYLE_PROMPTS.get(style, self.STYLE_PROMPTS["standard"])

        if preserve_citations:
            system_prompt += (
                "\n\nMANDATORY: Preserve every single citation, reference number, "
                "DOI, and author-year reference EXACTLY as it appears in the original. "
                "Do not renumber, reorder, or modify any citation."
            )

        user_prompt = f"Paraphrase the following text:\n\n{text}"

        style_config = self._get_style_config(style)
        temperature = style_config.get("temperature", 0.7)

        return ai_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=min(len(text.split()) * 3, 4096),
            temperature=temperature,
        )

    def paraphrase_with_instructions(self, text: str, instructions: str) -> str:
        """Paraphrase with custom instructions."""
        system_prompt = """You are an expert paraphrasing assistant.
Follow these specific instructions when paraphrasing:
{instructions}

Always preserve the original meaning and any citations/references.
Preserve ALL formatting: **bold**, *italic*, `code`, ## headings, lists.
Preserve technical terms and proper nouns exactly.
Return ONLY the paraphrased text, no explanations or meta-commentary.""".format(
            instructions=instructions
        )

        user_prompt = f"Paraphrase the following text:\n\n{text}"

        return ai_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=min(len(text.split()) * 3, 4096),
            temperature=0.7,
        )

    def humanize(self, text: str) -> str:
        """Convert AI-generated text to more natural, human-like writing."""
        system_prompt = """You are an expert at making AI-generated text sound natural and human.
Rewrite the following text to:
1. Vary sentence length and structure naturally
2. Add subtle imperfections and natural flow
3. Use contractions and informal transitions where appropriate
4. Include occasional rhetorical questions or asides
5. Make the tone conversational yet informative
6. Avoid repetitive patterns common in AI text
7. Preserve all factual content and citations exactly as they appear
8. Preserve all formatting: **bold**, *italic*, `code`, ## headings
9. Preserve technical terms and proper nouns
10. Return ONLY the rewritten text"""

        user_prompt = f"Humanize the following text:\n\n{text}"

        return ai_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=min(len(text.split()) * 3, 4096),
            temperature=0.8,
        )

    def compress(self, text: str, target_ratio: float = 0.5) -> str:
        """Compress text while preserving key information."""
        target_words = int(len(text.split()) * target_ratio)
        system_prompt = """You are a text compression expert. Compress the following text
to approximately {target_words} words while preserving all key information,
main arguments, and important details. Maintain readability and coherence.

CRITICAL RULES:
- Preserve ALL citations exactly: [1], (Author, Year), doi references
- Preserve ALL formatting
- Preserve technical terms and proper nouns
- Return ONLY the compressed text""".format(target_words=target_words)

        user_prompt = f"Compress this text:\n\n{text}"

        return ai_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=min(target_words * 2, 4096),
            temperature=0.5,
        )


class StructureTransformer:
    """Transform sentence structures for paraphrasing."""

    @staticmethod
    def split_long_sentences(text: str, max_words: int = 35) -> str:
        """Split overly long sentences into shorter ones."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        result = []
        for sent in sentences:
            words = sent.split()
            if len(words) > max_words:
                split_points = [', and ', ', but ', '; however, ', '; therefore, ',
                                ', moreover, ', '; additionally, ', ', while ',
                                '; furthermore, ', ', although ', '; nevertheless, ']
                for sp in split_points:
                    if sp in sent:
                        parts = sent.split(sp, 1)
                        if len(parts) == 2 and all(len(p.split()) > 5 for p in parts):
                            left = parts[0].strip()
                            if not left.endswith(('.', '!', '?')):
                                left += '.'
                            result.append(left)
                            right_part = parts[1].strip()
                            right_part = right_part[0].upper() + right_part[1:]
                            result.append(right_part)
                            break
                else:
                    semicolons = sent.split(';')
                    if len(semicolons) > 1 and all(len(s.split()) > 5 for s in semicolons):
                        for s in semicolons:
                            s = s.strip()
                            if not s.endswith(('.', '!', '?')):
                                s += '.'
                            result.append(s)
                    else:
                        result.append(sent)
            else:
                result.append(sent)
        return ' '.join(result)

    @staticmethod
    def combine_short_sentences(text: str, min_words: int = 6) -> str:
        """Combine very short sentences for better flow."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        result = []
        i = 0
        while i < len(sentences):
            current = sentences[i]
            if (i + 1 < len(sentences)
                and len(current.split()) < min_words + 2
                and len(sentences[i + 1].split()) < min_words + 2):
                left = current.rstrip('.!?,;')
                right = sentences[i + 1]
                combined = left + ', and ' + right[0].lower() + right[1:]
                result.append(combined)
                i += 2
            else:
                result.append(current)
                i += 1
        return ' '.join(result)

    @staticmethod
    def change_voice(text: str, to_passive: bool = False) -> str:
        """Attempt to change between active and passive voice."""
        if to_passive:
            transformations = [
                (r'\b(\w+)s\b', r'is \1ed'),
                (r'\b(\w+)es\b', r'are \1ed'),
            ]
        else:
            transformations = [
                (r'\b(\w+)ed by\b', r'was \1ing'),
                (r'\bwas (\w+)ed\b', r'\1s'),
                (r'\bwere (\w+)ed\b', r'\1'),
                (r'\bis being (\w+)ed\b', r'\1s'),
                (r'\bare being (\w+)ed\b', r'\1'),
            ]
        result = text
        for pattern, replacement in transformations:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    @staticmethod
    def reorder_clauses(text: str) -> str:
        """Reorder dependent and independent clauses for variety."""
        pattern = r'^((?:[A-Z][^.!?,]*)),\s*((?:because|although|while|since|when|if|unless|whereas)\s+[^.]+)$'
        match = re.match(pattern, text.strip())
        if match:
            main_clause = match.group(1)
            dependent_clause = match.group(2)
            return f"{dependent_clause[0].upper()}{dependent_clause[1:]}, {main_clause[0].lower()}{main_clause[1:]}"
        return text

    @staticmethod
    def vary_openings(sentences: List[str]) -> List[str]:
        """Vary sentence beginnings to reduce repetition."""
        transition_starters = [
            "Furthermore, ", "Moreover, ", "Additionally, ",
            "In addition, ", "Consequently, ", "As a result, ",
            "Notably, ", "Importantly, ", "Significantly, ",
        ]
        result = []
        prev_starts = []
        for i, sent in enumerate(sentences):
            words = sent.split()
            if not words:
                result.append(sent)
                continue
            first_word = words[0].lower() if words else ''
            if first_word in prev_starts and i > 0:
                import random
                for starter in random.sample(transition_starters, len(transition_starters)):
                    new_sent = starter + sent[0].lower() + sent[1:]
                    if not new_sent.endswith(('.', '!', '?')):
                        new_sent += '.'
                    result.append(new_sent)
                    break
                else:
                    result.append(sent)
            else:
                result.append(sent)
            prev_starts.append(first_word)
            if len(prev_starts) > 3:
                prev_starts.pop(0)
        return result

    def transform(self, text: str, aggressive: bool = False) -> str:
        """Apply all structure transformations."""
        text = self.split_long_sentences(text)
        text = self.combine_short_sentences(text)
        if aggressive:
            text = self.change_voice(text)
        return text


class PowerParaphraser:
    """Main paraphraser combining all strategies."""

    VALID_MODES = ["ai", "synonym", "structure", "combined", "humanize", "compress"]
    VALID_STYLES = ["standard", "academic", "formal", "casual", "simple",
                    "creative", "seo", "fluency", "concise"]

    def __init__(self):
        self.ai = AIParaphraser()
        self.synonym = SynonymReplacer()
        self.transformer = StructureTransformer()
        self.citation_handler = CitationHandler()
        self.formatting_preserver = FormattingPreserver()

    def _preprocess_citations(self, text: str) -> Tuple[str, List[str]]:
        """Extract citations before processing, return cleaned text and citations."""
        return self.citation_handler.extract_citations(text)

    def _postprocess_citations(self, text: str) -> str:
        """Restore citations after processing."""
        return self.citation_handler.restore_citations(text)

    def paraphrase(self, text: str, style: str = "academic",
                   mode: str = "ai", preserve_citations: bool = True,
                   context_aware_synonyms: bool = False) -> dict:
        """
        Paraphrase text using the specified mode.

        Modes:
            - 'ai': Full AI-powered paraphrasing
            - 'synonym': Synonym replacement only
            - 'structure': Structure transformation only
            - 'combined': AI + synonym + structure (most powerful)
            - 'humanize': Make AI text sound human
            - 'compress': Compress while preserving meaning
        """
        result = {
            "original": text,
            "mode": mode,
            "style": style,
            "preserve_citations": preserve_citations,
        }

        if style not in self.VALID_STYLES:
            style = "standard"
            result["style"] = style

        if mode == "ai":
            result["paraphrased"] = self.ai.paraphrase(text, style, preserve_citations)

        elif mode == "synonym":
            if preserve_citations:
                cleaned, citations = self._preprocess_citations(text)
                paraphrased = self.synonym.replace_synonyms(
                    cleaned, context_aware=context_aware_synonyms)
                result["paraphrased"] = self._postprocess_citations(paraphrased)
            else:
                result["paraphrased"] = self.synonym.replace_synonyms(
                    text, context_aware=context_aware_synonyms)

        elif mode == "structure":
            result["paraphrased"] = self.transformer.transform(text, aggressive=False)

        elif mode == "combined":
            if preserve_citations:
                cleaned, citations = self._preprocess_citations(text)
            else:
                cleaned = text
            ai_result = self.ai.paraphrase(cleaned, style, preserve_citations=False)
            structured = self.transformer.split_long_sentences(ai_result)
            structured = self.transformer.combine_short_sentences(structured)
            final = self.synonym.replace_synonyms(structured, replacement_rate=0.15,
                                                   context_aware=context_aware_synonyms)
            if preserve_citations:
                final = self._postprocess_citations(final)
            result["paraphrased"] = final

        elif mode == "humanize":
            result["paraphrased"] = self.ai.humanize(text)

        elif mode == "compress":
            result["paraphrased"] = self.ai.compress(text)

        else:
            result["paraphrased"] = self.ai.paraphrase(text, style, preserve_citations)

        orig_words = len(text.split())
        para_words = len(result["paraphrased"].split())
        result["stats"] = {
            "original_word_count": orig_words,
            "paraphrased_word_count": para_words,
            "compression_ratio": round(para_words / orig_words, 2) if orig_words > 0 else 0,
            "word_change": para_words - orig_words,
        }

        if preserve_citations and mode != "ai":
            orig_cites = len(re.findall(r'\[\d+(?:,\s*\d+)*\]', text))
            para_cites = len(re.findall(r'\[\d+(?:,\s*\d+)*\]', result["paraphrased"]))
            result["stats"]["citations_original"] = orig_cites
            result["stats"]["citations_paraphrased"] = para_cites
            result["stats"]["citations_preserved"] = orig_cites == para_cites

        return result

    def batch_paraphrase(self, texts: List[str], style: str = "academic",
                         mode: str = "ai", preserve_citations: bool = True,
                         context_aware_synonyms: bool = False,
                         progress_callback=None) -> List[dict]:
        """Paraphrase multiple texts with optional progress callback."""
        results = []
        total = len(texts)
        for i, text in enumerate(texts):
            print(f"  [{i+1}/{total}] Paraphrasing...")
            result = self.paraphrase(text, style=style, mode=mode,
                                     preserve_citations=preserve_citations,
                                     context_aware_synonyms=context_aware_synonyms)
            results.append(result)
            if progress_callback:
                progress_callback(i + 1, total, result)
        return results

    def batch_paraphrase_streaming(self, texts: List[str], style: str = "academic",
                                    mode: str = "ai", preserve_citations: bool = True,
                                    context_aware_synonyms: bool = False):
        """Generator for batch paraphrasing with streaming results (for SSE)."""
        total = len(texts)
        for i, text in enumerate(texts):
            result = self.paraphrase(text, style=style, mode=mode,
                                     preserve_citations=preserve_citations,
                                     context_aware_synonyms=context_aware_synonyms)
            yield {
                "index": i,
                "total": total,
                "progress": round((i + 1) / total * 100, 1),
                "result": result,
            }


def interactive_mode():
    """Run paraphraser in interactive mode."""
    print("=" * 60)
    print("  PowerParaphraser - Interactive Mode")
    print("=" * 60)
    print("\nStyles: standard, academic, formal, casual, simple, creative, seo, fluency, concise")
    print("Modes: ai, synonym, structure, combined, humanize, compress")
    print("Type 'quit' to exit\n")

    p = PowerParaphraser()

    while True:
        text = input("\nEnter text to paraphrase (or 'quit'): ").strip()
        if text.lower() in ('quit', 'exit', 'q'):
            break

        style = input("Style [academic]: ").strip() or "academic"
        mode = input("Mode [ai]: ").strip() or "ai"

        print("\nParaphrasing...")
        result = p.paraphrase(text, style=style, mode=mode)

        print(f"\nResult ({result['stats']['original_word_count']} -> "
              f"{result['stats']['paraphrased_word_count']} words):")
        print("-" * 40)
        print(result["paraphrased"])
        print("-" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="PowerParaphraser - AI-powered text paraphrasing tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input "Your text here" --style academic
  %(prog)s --file paper.txt --style formal --output paraphrased.txt
  %(prog)s --input "Text" --mode combined --style academic
  %(prog)s --input "AI text" --mode humanize
  %(prog)s --file long.txt --mode compress
  %(prog)s --interactive
        """
    )

    parser.add_argument("--input", "-i", help="Input text to paraphrase")
    parser.add_argument("--file", "-f", help="Input file path")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--style", "-s", default="academic",
                       choices=PowerParaphraser.VALID_STYLES,
                       help="Paraphrasing style (default: academic)")
    parser.add_argument("--mode", "-m", default="ai",
                       choices=PowerParaphraser.VALID_MODES,
                       help="Paraphrasing mode (default: ai)")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--context-aware", action="store_true",
                       help="Use context-aware synonym replacement")
    parser.add_argument("--no-cite-preserve", action="store_true",
                       help="Disable citation preservation")

    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
        return

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.input:
        text = args.input
    else:
        if not sys.stdin.isatty():
            text = sys.stdin.read()
        else:
            parser.print_help()
            sys.exit(1)

    p = PowerParaphraser()
    result = p.paraphrase(
        text,
        style=args.style,
        mode=args.mode,
        preserve_citations=not args.no_cite_preserve,
        context_aware_synonyms=args.context_aware,
    )

    if args.json:
        output = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        output = result["paraphrased"]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Output written to {args.output}")
        print(f"   Words: {result['stats']['original_word_count']} -> "
              f"{result['stats']['paraphrased_word_count']}")
    else:
        print(output)


if __name__ == "__main__":
    main()
