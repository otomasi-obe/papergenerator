"""
Post-processing cleaner for AI-generated paper text.
Fixes mojibake (UTF-8 decoded as Latin-1/CP1252), LaTeX notation, and math delimiters.
"""
import re

_SUP = '⁰¹²³⁴⁵⁶⁷⁸⁹'
_SUB = '₀₁₂₃₄₅₆₇₈₉'

_LATEX_PATTERNS = [
    # Degree symbol variants
    (r'\^\{\\circ\}', '°'),
    (r'\^\\circ', '°'),
    (r'\\degree\b', '°'),
    (r'\\circ\b', '°'),
    # Common math symbols (operators only — NOT Greek letters or formatting)
    (r'\\times\b', '×'),
    (r'\\div\b', '÷'),
    (r'\\pm\b', '±'),
    (r'\\leq\b', '≤'),
    (r'\\geq\b', '≥'),
    (r'\\neq\b', '≠'),
    (r'\\approx\b', '≈'),
    (r'\\infty\b', '∞'),
    # Greek letters (match even when next char is a letter → \etasolar → ηsolar)
    (r'\\alpha', 'α'),   (r'\\Alpha', 'Α'),
    (r'\\beta', 'β'),    (r'\\Beta', 'Β'),
    (r'\\gamma', 'γ'),   (r'\\Gamma', 'Γ'),
    (r'\\delta', 'δ'),   (r'\\Delta', 'Δ'),
    (r'\\epsilon', 'ε'), (r'\\varepsilon', 'ε'),
    (r'\\zeta', 'ζ'),    (r'\\Zeta', 'Ζ'),
    (r'\\eta', 'η'),     (r'\\Eta', 'Η'),
    (r'\\theta', 'θ'),   (r'\\vartheta', 'ϑ'), (r'\\Theta', 'Θ'),
    (r'\\iota', 'ι'),    (r'\\Iota', 'Ι'),
    (r'\\kappa', 'κ'),   (r'\\Kappa', 'Κ'),
    (r'\\lambda', 'λ'),  (r'\\Lambda', 'Λ'),
    (r'\\mu', 'μ'),      (r'\\Mu', 'Μ'),
    (r'\\nu', 'ν'),      (r'\\Nu', 'Ν'),
    (r'\\xi', 'ξ'),      (r'\\Xi', 'Ξ'),
    (r'\\pi', 'π'),      (r'\\varpi', 'ϖ'), (r'\\Pi', 'Π'),
    (r'\\rho', 'ρ'),     (r'\\varrho', 'ϱ'), (r'\\Rho', 'Ρ'),
    (r'\\sigma', 'σ'),   (r'\\varsigma', 'ς'), (r'\\Sigma', 'Σ'),
    (r'\\tau', 'τ'),     (r'\\Tau', 'Τ'),
    (r'\\upsilon', 'υ'), (r'\\Upsilon', 'Υ'),
    (r'\\phi', 'φ'),     (r'\\varphi', 'ϕ'), (r'\\Phi', 'Φ'),
    (r'\\chi', 'χ'),     (r'\\Chi', 'Χ'),
    (r'\\psi', 'ψ'),     (r'\\Psi', 'Ψ'),
    (r'\\omega', 'ω'),   (r'\\Omega', 'Ω'),
    (r'\\rightarrow\b', '→'),
    (r'\\leftarrow\b', '←'),
    (r'\\Rightarrow\b', '⇒'),
    (r'\\Leftarrow\b', '⇐'),
    (r'---', '—'),
    (r'--', '–'),
    # LaTeX spacing → remove
    (r'\\[,;:!.]\s*', ''),
    (r'\\quad\b\s*', ' '),
    (r'\\qquad\b\s*', '  '),
    (r'\\hspace\{[^}]*\}\s*', ''),
    (r'\\vspace\{[^}]*\}\s*', ''),
    # Quotes
    (r'``', '"'),
    (r"''", '"'),
    # Strip invisible/zero-width characters
    ('\u200b', ''),   # ZERO WIDTH SPACE
    ('\u200c', ''),   # ZERO WIDTH NON-JOINER
    ('\u200d', ''),   # ZERO WIDTH JOINER
    ('\ufeff', ''),   # ZERO WIDTH NO-BREAK SPACE / BOM
    # Collapse single newlines (LLM tokenizer splits formulas across lines)
    # Only single \n, not paragraph breaks (\n\n). Replace with space.
    (r'(?<!\n)\n(?!\n)', ' '),
]

# Regex to match LaTeX math delimiters ($$ before $, \[\] before \(\))
_MATH_PATTERN = re.compile(
    r'(\$\$.*?\$\$|'
    r'\$[^$]+?\$|'
    r'\\\[.*?\\\]|'
    r'\\\(.*?\\\))',
    re.DOTALL
)


def _fix_mojibake(text: str) -> str:
    """Recover UTF-8 bytes incorrectly decoded as Latin-1/CP1252.

    Uses targeted repair: finds runs of high-byte chars (U+00C0-U+00FF +
    U+0080-U+00BF) and tries to decode them. Works even when the string
    contains non-Latin-1 characters (Greek, math symbols, etc.).
    """
    if not isinstance(text, str):
        return text

    # Try whole-string fix first (fast path, works for clean text)
    for enc in ('latin-1', 'cp1252'):
        try:
            return text.encode(enc).decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
            continue

    # Fallback: targeted repair of mojibake runs
    # Mojibake run: sequence of chars in U+00C0-U+00FF (start bytes) and
    # U+0080-U+00BF (continuation bytes), terminated by ASCII or non-Latin-1
    result = []
    run = []
    for ch in text:
        cp = ord(ch)
        if 0x0080 <= cp <= 0x00FF:
            run.append(ch)
        else:
            if run:
                result.append(_try_mojibake_run(''.join(run)))
                run.clear()
            result.append(ch)
    if run:
        result.append(_try_mojibake_run(''.join(run)))
    return ''.join(result)


def _try_mojibake_run(run: str) -> str:
    """Try to decode a run of high-byte characters as UTF-8 mojibake."""
    for enc in ('latin-1', 'cp1252'):
        try:
            decoded = run.encode(enc).decode('utf-8')
            # Only accept if decoding produced fewer chars (valid UTF-8 sequences)
            if len(decoded) < len(run):
                return decoded
        except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
            continue
    return run


def _convert_match(text, pattern, bold_open, bold_close):
    """Convert braced formatting commands to toggle format, outside math regions."""
    result = []
    i = 0
    in_math = False
    while i < len(text):
        if text[i] == '$':
            in_math = not in_math
            result.append(text[i])
            i += 1
        else:
            m = pattern.match(text, i)
            if m and not in_math:
                result.append(bold_open)
                result.append(m.group(1))
                result.append(bold_close)
                i = m.end()
            else:
                result.append(text[i])
                i += 1
    return ''.join(result)


def _convert_formatting_to_toggles(text: str) -> str:
    """Convert LaTeX formatting commands to paper toggle format BEFORE stripping.

    \\textbf{...} → \\b...\\b   (bold toggle)
    \\textit{...} → \\i...\\i   (italic toggle)
    \\underline{...} → \\u...\\u (underline toggle)
    \\mathrm{...} → \\b...\\b   (preserves emphasis via bold)
    \\mathbf{...} → \\b...\\b   (bold)
    \\mathit{...} → \\i...\\i   (italic)
    \\emph{...} → \\i...\\i     (italic)

    Only converts outside $...$ math regions to preserve LaTeX math.
    """
    # Process inner commands first to handle nesting correctly:
    #   \textbf{\textit{inner}} → \b\iinner\i\b (not \bnested \iinner\b\i)
    text = _convert_match(text, re.compile(r'\\underline\{([^}]*)\}', re.DOTALL), '\\u', '\\u')
    text = _convert_match(text, re.compile(r'\\textit\{([^}]*)\}', re.DOTALL), '\\i', '\\i')
    text = _convert_match(text, re.compile(r'\\emph\{([^}]*)\}', re.DOTALL), '\\i', '\\i')
    text = _convert_match(text, re.compile(r'\\mathit\{([^}]*)\}', re.DOTALL), '\\i', '\\i')
    text = _convert_match(text, re.compile(r'\\textbf\{([^}]*)\}', re.DOTALL), '\\b', '\\b')
    text = _convert_match(text, re.compile(r'\\mathrm\{([^}]*)\}', re.DOTALL), '\\b', '\\b')
    text = _convert_match(text, re.compile(r'\\mathbf\{([^}]*)\}', re.DOTALL), '\\b', '\\b')

    # Strip remaining broken commands (without braces)
    text = re.sub(r'\\(?:textit|textbf|emph|underline|mathrm|mathbf|mathit)\s+', '', text)
    return text


def _clean_latex_notation(text: str) -> str:
    """Convert LaTeX notation in text to plain Unicode, preserving math-mode regions."""
    if not isinstance(text, str):
        return text

    # 1. Extract and protect math-mode regions ($$, $, \[...\], \(...\))
    math_regions = {}
    counter = [0]

    def _save_math(m):
        placeholder = f'\x00MATH{counter[0]}\x00'
        math_regions[placeholder] = m.group(0)
        counter[0] += 1
        return placeholder

    text = _MATH_PATTERN.sub(_save_math, text)

    # 2. Convert LaTeX formatting commands to toggle format (\b, \i, \u)
    #    This MUST happen before applying _LATEX_PATTERNS to prevent stripping.
    text = _convert_formatting_to_toggles(text)

    # 3. Apply LaTeX patterns only to non-math text
    for pattern, repl in _LATEX_PATTERNS:
        text = re.sub(pattern, repl, text)

    # Digit subscript/superscript with braces: _{3} → ₃, ^{2} → ²
    text = re.sub(r'\^{(\d+)}', lambda m: ''.join(_SUP[int(c)] for c in m.group(1)), text)
    text = re.sub(r'_{(\d+)}', lambda m: ''.join(_SUB[int(c)] for c in m.group(1)), text)

    # Text subscript/superscript with braces → extract content (non-digit)
    text = re.sub(r'_{([a-zA-Z][a-zA-Z0-9]*?)}', r'\1', text)
    text = re.sub(r'\^{([a-zA-Z][a-zA-Z0-9]*?)}', r'\1', text)
    # Catch-all: any remaining braces content (e.g. ^{1.5})
    text = re.sub(r'_{([^}]+)}', r'\1', text)
    text = re.sub(r'\^{([^}]+)}', r'\1', text)

    # 4. Restore math-mode regions intact (raw LaTeX for KaTeX)
    for placeholder, original in math_regions.items():
        text = text.replace(placeholder, original)

    return text


# ── Indonesian punctuation fixes ──────────────────────────────────
# Common conjunctions that should be preceded by comma, not period.
# Only matches lowercase conjunctions (capitalized = likely new sentence).
_ID_CONJUNCTIONS = (
    'sementara', 'tetapi', 'namun', 'sedangkan', 'sehingga',
    'meskipun', 'walaupun', 'karena', 'jika', 'bila', 'walau',
    'melainkan', 'padahal', 'andaikan', 'sekalipun', 'kendati',
    'adapun', 'serta', 'lagi', 'pula', 'pun',
    'dan', 'atau', 'yang', 'ia', 'akan', 'dapat', 'bisa',
    'maka', 'lalu', 'kemudian', 'bahkan', 'apalagi',
    'yakni', 'yaitu', 'ialah', 'contohnya', 'misalnya',
    'baik', 'juga', 'hanya', 'saja',
)


def _fix_id_punctuation(text: str) -> str:
    """Fix common Indonesian punctuation errors in generated text.

    ''. conjunction'' → '', conjunction'' (comma before conjunctions)
    ''[N]. [M]'' → ''[N], [M]'' (citation list)
    """
    if not isinstance(text, str):
        return text
    # Pattern: period + space + lowercase conjunction → comma + space + conjunction
    conj_pattern = r'\. (' + '|'.join(_ID_CONJUNCTIONS) + r')\b'
    text = re.sub(conj_pattern, r', \1', text)

    # Pattern: citation [N]. [M] → [N], [M]
    text = re.sub(r'(\]\s*)\.\s*(\[)', r'\1, \2', text)

    # Pattern: multiple spaces → single space
    text = re.sub(r' {2,}', ' ', text)

    # Pattern: space before comma/period
    text = re.sub(r' ,', ',', text)
    text = re.sub(r' \.', '.', text)

    return text


def clean_paper_text(text: str) -> str:
    """Clean a single text string: strip invisible chars, fix mojibake, then LaTeX notation."""
    if not isinstance(text, str):
        return text
    # Strip invisible/zero-width chars FIRST — they block latin-1 encode for mojibake fix
    text = text.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '')
    text = _fix_mojibake(text)
    text = _clean_latex_notation(text)
    text = _fix_id_punctuation(text)
    return text


def clean_paper_data(data):
    """Recursively clean all string values in a paper data dict/list."""
    if data is None:
        return None
    if isinstance(data, dict):
        return {k: clean_paper_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_paper_data(item) for item in data]
    elif isinstance(data, str):
        return clean_paper_text(data)
    return data