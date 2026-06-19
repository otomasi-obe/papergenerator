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
    (r'\\[,;:!]\s*', ''),
    (r'\\quad\b\s*', ' '),
    (r'\\qquad\b\s*', '  '),
    (r'\\hspace\{[^}]*\}\s*', ''),
    (r'\\vspace\{[^}]*\}\s*', ''),
    # Quotes
    (r'``', '"'),
    (r"''", '"'),
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
    """Recover UTF-8 bytes incorrectly decoded as Latin-1/CP1252."""
    if not isinstance(text, str):
        return text
    for enc in ('latin-1', 'cp1252'):
        try:
            return text.encode(enc).decode('utf-8')
        except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
            continue
    return text


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
    global _SUP, _SUB, _MATH_PATTERN

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


def clean_paper_text(text: str) -> str:
    """Clean a single text string: fix mojibake then LaTeX notation."""
    return _clean_latex_notation(_fix_mojibake(text))


def clean_paper_data(data):
    """Recursively clean all string values in a paper data dict/list."""
    if isinstance(data, dict):
        return {k: clean_paper_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_paper_data(item) for item in data]
    elif isinstance(data, str):
        return clean_paper_text(data)
    return data