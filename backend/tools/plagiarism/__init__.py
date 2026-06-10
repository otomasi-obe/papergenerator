import os
import json
import re
from pathlib import Path

_PROMPT_FILE = Path(__file__).parent / "plagiarism_prompt.txt"

def _load_prompt() -> dict:
    if _PROMPT_FILE.exists():
        raw = _PROMPT_FILE.read_text(encoding="utf-8")
        sections = {}
        current = None
        for line in raw.splitlines():
            m = re.match(r"^\[SECTION:(\w+)\]$", line.strip())
            if m:
                current = m.group(1)
                sections.setdefault(current, [])
            elif current is not None:
                sections[current].append(line)
        return {
            "system": "\n".join(sections.get("SYSTEM", [])).strip(),
            "user_template": "\n".join(sections.get("USER_TEMPLATE", [])).strip(),
        }
    return {
        "system": (
            "You are an expert plagiarism detection analyst with deep knowledge of academic integrity, "
            "citation practices, and content originality assessment. Your task is to analyze the given "
            "text and provide a thorough plagiarism assessment.\n\n"
            "Analyze the text for:\n"
            "1. VERBATIM MATCHES: Exact or near-exact copying of phrases, sentences, or passages "
            "from known sources (textbooks, papers, websites, common phrases)\n"
            "2. PARAPHRASED MATCHES: Content that closely paraphrases known sources — same structure "
            "and ideas with minor word changes, synonym substitution, or sentence restructuring\n"
            "3. IDEA MATCHES: Arguments, thesis statements, unique findings, or specific data that "
            "appear to originate from identifiable sources without attribution\n"
            "4. SELF-PLAGIARISM: Reuse of the author's own previously published content\n"
            "5. COMMON KNOWLEDGE: Widely known facts that do not require citation (do not flag these)\n\n"
            "For each flagged passage, determine:\n"
            "- The type of match (verbatim | paraphrased | idea)\n"
            "- Severity (low | moderate | high) based on length and centrality to the argument\n"
            "- Whether it could be common knowledge or requires citation\n\n"
            "Respond with ONLY a valid JSON object (no markdown, no code fences):\n"
            "{\n"
            '  "pct": <int 0-100>,\n'
            '  "breakdown": {\n'
            '    "verbatim_pct": <int 0-100>,\n'
            '    "paraphrased_pct": <int 0-100>,\n'
            '    "idea_pct": <int 0-100>\n'
            "  },\n"
            '  "reasons": ["string", ...],\n'
            '  "suggestions": ["string", ...],\n'
            '  "highlighted_sentences": [\n'
            '    {\n'
            '      "text": "the flagged passage",\n'
            '      "issue": "verbatim match | paraphrased content | unattributed idea | self-plagiarism",\n'
            '      "severity": "low | moderate | high",\n'
            '      "note": "brief explanation of why this is flagged",\n'
            '      "context_before": "preceding sentence or phrase for context",\n'
            '      "context_after": "following sentence or phrase for context"\n'
            "    }\n"
            "  ],\n"
            '  "sources": [\n'
            '    {\n'
            '      "url": "source URL if identifiable",\n'
            '      "title": "source title",\n'
            '      "match_pct": <int 0-100>,\n'
            '      "credibility": "high | medium | low",\n'
            '      "type": "academic | web | textbook | unknown"\n'
            "    }\n"
            "  ]\n"
            "}"
        ),
        "user_template": (
            "Analyze the following text for plagiarism.\n"
            "Analysis mode: {option}\n"
            "Text length: approximately {word_count} words\n\n"
            "TEXT:\n{text}\n\n"
            "Provide your assessment as a JSON object."
        ),
    }

PROMPT = _load_prompt()


def run_plagiarism(data: dict) -> dict:
    from tools.plagiarism.plagiarism_checker import (
        run_offline_check,
        run_web_search_check,
        run_ai_check,
        run_full_scan,
    )

    text = (data.get("text") or "").strip()
    option = (data.get("option") or "AI Check").strip()

    if not text:
        return {"error": "No text provided", "pct": 0}

    option_lower = option.lower()

    if option_lower == "offline" or option == "Offline":
        return run_offline_check(text)
    elif option_lower in ("web", "web search", "web_search") or option == "Web Search":
        return run_web_search_check(text)
    elif option_lower in ("full", "full scan", "full_scan") or option == "Full Scan":
        return run_full_scan(text, PROMPT)
    elif option_lower == "ai" or option == "AI Check":
        return run_ai_check(text, PROMPT, option)
    else:
        return run_ai_check(text, PROMPT, option)
