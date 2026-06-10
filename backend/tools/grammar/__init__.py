"""tools.grammar — public API: PROMPT, run_grammar, run_grammar_markup, GrammarChecker, CompositeSpellChecker, SpellCheckResult."""
import re
import difflib
from pathlib import Path

_PROMPT_PATH = Path(__file__).resolve().parent / "grammar_prompt.txt"
_FALLBACK = {
    "system": (
        "You are an expert academic editor. Fix all grammar, spelling, and style "
        "errors while preserving meaning and academic tone. Preserve citations, "
        "references, code, and LaTeX. Output ONLY the corrected text."
    ),
    "user_template": (
        "Proofread and correct (focus: {option} — Standard / Grammar / Spelling / "
        "Style / Clarity / Academic).\n\nTEXT:\n{text}"
    ),
}


def _load_prompt() -> dict:
    if not _PROMPT_PATH.exists():
        return _FALLBACK
    sections, current = {}, None
    for line in _PROMPT_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\[SECTION:(\w+)\]\s*$", line.strip())
        if m:
            current = m.group(1).lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    if not {"system", "user_template"} <= sections.keys():
        return _FALLBACK
    return {"system": "\n".join(sections["system"]).strip(),
            "user_template": "\n".join(sections["user_template"]).strip()}


PROMPT = _load_prompt()

try:
    from .grammar_checker import GrammarChecker  # noqa: F401
    _checker = GrammarChecker()
except Exception:
    GrammarChecker = None  # type: ignore
    _checker = None
try:
    from .spell_checker import (  # noqa: F401
        CompositeSpellChecker, SpellCheckResult,
    )
except Exception:
    CompositeSpellChecker = None  # type: ignore
    SpellCheckResult = None  # type: ignore

_MODE = {"standard": "all", "grammar": "grammar", "spelling": "spelling",
         "style": "style", "all": "all", "academic": "all",
         "clarity": "style", "indonesian": "all"}


def run_grammar(data: dict) -> dict:
    """Program-only grammar check. NO LLM. Raises ValueError on empty text."""
    text = (data.get("text") or "").strip()
    if not text:
        raise ValueError("No text provided")
    option = (data.get("option") or "all").strip().lower()
    language = (data.get("language") or "en-US").strip()
    domain = (data.get("domain") or "academic").strip()
    mode = "all" if language.lower().startswith("id") else _MODE.get(option, "all")
    if _checker is None:
        return {"text": text, "word_count": len(text.split()),
                "sentence_count": len(re.findall(r"[.!?]+", text)) + 1,
                "errors": [], "warnings": [], "suggestions": [],
                "readability": {}, "mode": mode, "language": language,
                "engine": "unavailable"}
    return _checker.check(text, mode=mode, language=language, domain=domain)


_TOKEN_RE = re.compile(r"\w+|\s+|[^\w\s]")


def _tokenize(text: str) -> list:
    return _TOKEN_RE.findall(text or "")


def _build_diff_markup(original: str, corrected: str, errors: list | None = None) -> str:
    """Build track-changes markup (<add>...</add> <del>...</del>) between original and corrected.

    Tokens are split into words, whitespace runs, and individual punctuation so the
    diff keeps spacing stable. Output is plain markup — the frontend's
    `renderGrammarOutput()` handles HTML escaping. The `errors` parameter is
    accepted for symmetry with the checker but is not required by the diff itself.
    """
    if not original and not corrected:
        return ""
    if original == corrected:
        return corrected
    a_tokens = _tokenize(original)
    b_tokens = _tokenize(corrected)
    sm = difflib.SequenceMatcher(a=a_tokens, b=b_tokens, autojunk=False)
    sm.ratio()  # touch quick_ratio / ratio
    out: list = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append("".join(a_tokens[i1:i2]))
        elif tag == "delete":
            out.append("<del>")
            out.append("".join(a_tokens[i1:i2]))
            out.append("</del>")
        elif tag == "insert":
            out.append("<add>")
            out.append("".join(b_tokens[j1:j2]))
            out.append("</add>")
        elif tag == "replace":
            out.append("<del>")
            out.append("".join(a_tokens[i1:i2]))
            out.append("</del>")
            out.append("<add>")
            out.append("".join(b_tokens[j1:j2]))
            out.append("</add>")
    return "".join(out)


def run_grammar_markup(data: dict) -> dict:
    """Same as run_grammar() but returns track-changes markup in the 'text' field.

    Compatible with tools_api.py SSE shape: {"text": "<markup>", "result": <dict>}.
    The frontend parses `outputText` (the string) through `renderGrammarOutput()`
    which converts <add>/<del> tags into green/red spans.
    """
    result = run_grammar(data)
    original = result.get("text", "")
    corrected = result.get("corrected", "")
    items = list(result.get("errors") or []) + list(result.get("warnings") or [])
    markup = _build_diff_markup(original, corrected, items)
    return {"text": markup, "result": result}


__all__ = ["PROMPT", "run_grammar", "run_grammar_markup", "_build_diff_markup",
           "GrammarChecker", "CompositeSpellChecker", "SpellCheckResult"]
