"""Shared LaTeX → OMML (native Word math) helper for journal generators.

Mirrors the proven conversion path in IEEEgen.py so every generator can emit
real Word equation objects (``<m:oMath>``) instead of flattened unicode text.
Pipeline: sanitize LaTeX → latex2mathml → MathML → MML2OMML.XSL → OMML element.

Usage in a generator's ``add_formula``::

    from _math_omml import append_omml_math
    if not append_omml_math(paragraph, latex):
        # fall back to the generator's existing unicode/text rendering
        ...
"""
from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

_BASE = Path(__file__).resolve().parent
_XSL_CANDIDATES = [
    _BASE / "MML2OMML.XSL",
    _BASE.parent / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL"),
]
_XSLT = None


def _get_xslt():
    global _XSLT
    if _XSLT is not None:
        return _XSLT
    for cand in _XSL_CANDIDATES:
        try:
            if cand.exists():
                _XSLT = etree.XSLT(etree.parse(str(cand)))
                return _XSLT
        except Exception:
            continue
    _XSLT = False
    return _XSLT


def _sanitize_latex(latex: str) -> str:
    if not latex:
        return ""
    s = str(latex).strip()
    # strip math delimiters
    for op, cl in (("$$", "$$"), ("$", "$"), (r"\[", r"\]"), (r"\(", r"\)")):
        if s.startswith(op) and s.endswith(cl) and len(s) > len(op) + len(cl) - 1:
            s = s[len(op):-len(cl)].strip()
            break
    s = s.replace(r"\text{", r"\mathrm{")
    s = s.replace(r"\textbf{", r"\mathbf{")
    s = s.replace(r"\textit{", r"\mathit{")
    s = re.sub(r"\\displaystyle\s*", "", s)
    s = s.replace(r"\Big(", r"\left(").replace(r"\Big)", r"\right)")
    s = s.replace(r"\big(", r"\left(").replace(r"\big)", r"\right)")
    s = s.replace(r"\Bigl(", r"\left(").replace(r"\Biggr)", r"\right)")
    # drop labels/refs/tags — numbering is handled by the template
    s = re.sub(r"\\(label|ref|eqref|tag)\{[^}]*\}", "", s)
    s = re.sub(r"\\color\{[^}]*\}\{([^}]*)\}", r"\1", s)
    # Decode stray tab escapes but preserve LaTeX commands (\theta, \times, etc.)
    if "\\t" in s:
        s = re.sub(r"\\t(?![a-z])", " ", s)
    if "\\u" in s:
        def _u(m):
            try:
                ch = chr(int(m.group(1), 16))
                return " " if ord(ch) < 0x20 else ch
            except Exception:
                return m.group(0)
        s = re.sub(r"\\u([0-9a-fA-F]{4})", _u, s)
    return s.strip()


def sanitize_llm_text_artifacts(text: str) -> str:
    """Repair common LLM streaming artifacts that corrupt paper text.

    The text-generation LLM occasionally emits broken LaTeX, mangled
    punctuation, or missing spaces.  These are transport-level corruption
    (token-boundary artefacts, lost whitespace, collapsed integral notation).
    This pass runs BEFORE the toggle / math parser so the downstream OMML
    converter receives clean input.

    Conservative by design — only fixes known corruption patterns:
      1. Collapsed integral notation:  "ntsunrisesunset" -> "\\int_{sunrise}^{sunset}"
      2. Bare inline math (Greek + subscripts without $...$ delimiters)
      3. Citation punctuation:  "[8]. [9]" -> "[8], [9]"
      4. Sentence-boundary comma corruption:  "mengajukan. memodelkan" -> "mengajukan, memodelkan"
      5. Missing spaces around slash-separated numbers:  "2,00/Wpada2010" -> "2,00/W pada 2010"
    """
    if not text:
        return text
    s = text

    # 1. Restore collapsed integral / sum notation.
    s = s.replace("ntsunrisesunset", "\\int_{sunrise}^{sunset}")
    s = s.replace("ntsunsetsunrise", "\\int_{sunset}^{sunrise}")
    s = s.replace("ntsum_", "\\sum_")
    s = re.sub(r"\bnt(sunrise|sunset|0|1|t)\b", r"\\int_{\1}", s)

    # 2. Wrap bare inline math that the LLM emitted without $...$.
    #    Protect existing math spans first, then patch the rest.
    _MATH_PROTECT = re.compile(r"\$\$.*?\$\$|\$[^$]+?\$", re.DOTALL)
    placeholders: list[str] = []

    def _stash(m):
        placeholders.append(m.group(0))
        return f"\x00MATH{len(placeholders) - 1}\x00"

    s = _MATH_PROTECT.sub(_stash, s)

    _bare_math = [
        (r"\bη\(([A-Za-z0-9,_]+)\)", r"$\\eta_{\1}$"),
        (r"\bε\(([A-Za-z0-9,_]+)\)", r"$\\epsilon_{\1}$"),
        (r"\bσ\(([A-Za-z0-9,_]+)\)", r"$\\sigma_{\1}$"),
        (r"\bβ\(([A-Za-z0-9,_]+)\)", r"$\\beta_{\1}$"),
        (r"\bη_([A-Za-z][A-Za-z0-9]*)\b", r"$\\eta_{\1}$"),
        (r"\bε_([A-Za-z][A-Za-z0-9]*)\b", r"$\\epsilon_{\1}$"),
        (r"\bσ_([A-Za-z][A-Za-z0-9]*)\b", r"$\\sigma_{\1}$"),
        (r"\bβ_([A-Za-z][A-Za-z0-9]*)\b", r"$\\beta_{\1}$"),
        (r"\bE\(([A-Za-z0-9,_]+)\)", r"$E_{\1}$"),
        (r"\bP\(([A-Za-z0-9,_]+)\)", r"$P_{\1}$"),
        (r"\bk\(([A-Za-z0-9,_]+)\)", r"$k_{\1}$"),
        (r"\bT\(([A-Za-z0-9,_]+)\)", r"$T_{\1}$"),
        (r"\bΔ([A-Z])\b", r"$\\Delta \1$"),
        (r"\bT_([a-z]{1,4})\b(?!\{)", r"$T_{\1}$"),
        (r"\bE_([a-z]{1,8})\b(?!\{)", r"$E_{\1}$"),
        (r"\bP_([A-Za-z]{1,8})\b(?!\{)", r"$P_{\1}$"),
        (r"\bk_([a-z]{1,8})\b(?!\{)", r"$k_{\1}$"),
    ]
    for pattern, repl in _bare_math:
        s = re.sub(pattern, repl, s)

    def _unstash(m):
        idx = int(m.group(1))
        return placeholders[idx]

    s = re.sub(r"\x00MATH(\d+)\x00", _unstash, s)

    # 3. Citation punctuation:  "[8]. [9]" -> "[8], [9]"
    s = re.sub(r"(\])\.\s+\[", r"\1, [", s)

    # 4. Sentence-boundary comma corruption (Indonesian connectives).
    _comma_after = [
        "mengajukan", "surya", "puncak", "efisiensi",
        "melainkan", "sementara", "memodelkan", "pendinginan",
        "namun", "sedangkan", "sehingga", "serta",
    ]
    for word in _comma_after:
        s = re.sub(r"\.\s+" + word + r"\b", r", " + word, s, flags=re.IGNORECASE)

    # 5. Missing spaces around slash-separated numbers and units.
    s = re.sub(r"(/W)(pada|menjadi|dari|ke|dan|atau)(\d)", r"\1 \2 \3", s, flags=re.IGNORECASE)
    s = re.sub(r"(\d)(menjadi|pada|dari|ke)(\d)", r"\1 \2 \3", s, flags=re.IGNORECASE)
    s = re.sub(r"(/W)([a-z]{4,})", r"\1 \2", s, flags=re.IGNORECASE)

    return s


# ── LaTeX → Unicode for plain-text previews ────────────────────────────
# The DOCX generators already convert LaTeX to native OMML equations.
# Web previews need a lossy-but-readable plain-text fallback.
_LATEX_UNICODE = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ",
    r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ", r"\mu": "μ",
    r"\nu": "ν", r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ",
    r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ", r"\phi": "φ",
    r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Phi": "Φ",
    r"\Psi": "Ψ", r"\Omega": "Ω",
    r"\cdot": "·", r"\times": "×", r"\pm": "±", r"\mp": "∓",
    r"\approx": "≈", r"\equiv": "≡", r"\neq": "≠", r"\propto": "∝",
    r"\leq": "≤", r"\geq": "≥", r"\ll": "≪", r"\gg": "≫",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇", r"\int": "∫",
    r"\sum": "Σ", r"\prod": "Π", r"\sqrt": "√",
    r"\rightarrow": "→", r"\Rightarrow": "⇒", r"\leftarrow": "←",
    r"\Leftarrow": "⇐", r"\leftrightarrow": "↔", r"\mapsto": "↦",
    r"\to": "→",
    r"\sin": "sin", r"\cos": "cos", r"\tan": "tan",
    r"\exp": "exp", r"\log": "log", r"\ln": "ln",
    r"\max": "max", r"\min": "min", r"\lim": "lim",
    r"\ldots": "…", r"\cdots": "⋯", r"\vdots": "⋮", r"\ddots": "⋱",
    r"\circ": "°", r"\degree": "°", r"\angstrom": "Å",
    r"\AA": "Å", r"\textdegree": "°",
    r"\textmu": "µ", r"\textpm": "±",
    r"\upmu": "µ",
}


def clean_latex_for_preview(text: str) -> str:
    """Convert inline LaTeX to readable Unicode for plain-text preview.

    Strip $...$ delimiters, replace common commands with Unicode symbols,
    and flatten subscripts/superscripts.  This is LOSSY — it targets human
    readability in the web preview, not mathematical fidelity (which the
    DOCX export already provides via OMML).

    Examples:
        $P_{out}$          →  P_out
        $\eta_{total}$     →  η_total
        $\frac{1}{2}$      →  (1)/(2)
        $\cdot$            →  ·
        $\sin(\theta)$     →  sin(θ)
    """
    if not text:
        return text

    s = text

    # ---- 0. Extract display math blocks ($$...$$) — keep them for KaTeX ----
    _display_blocks = {}
    def _stash_display(m):
        key = f"\x00DISPLAY{len(_display_blocks)}\x00"
        _display_blocks[key] = m.group(0)  # raw $$...$$ block, we clean later
        return key
    s = re.sub(r"\$\$\s*(.+?)\s*\$\$", _stash_display, s, flags=re.DOTALL)

    # ---- 1. Strip $inline$ delimiters — render as plain Unicode text ----
    s = re.sub(r"\$([^$]+?)\$", r"\1", s)

    # 2. Flatten \frac{a}{b} → (a)/(b) (braced form)
    s = re.sub(
        r"\\frac\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        r"(\1)/(\2)", s,
    )
    # \frac12, \frac ab (two single tokens, no braces)
    s = re.sub(r"\\frac\s*(\d)(\d)\b", r"(\1)/(\2)", s)
    s = re.sub(r"\\frac\s*([a-zA-Z])([a-zA-Z])\b", r"(\1)/(\2)", s)

    # 3. Flatten \sqrt{a} → √(a)
    s = re.sub(
        r"\\sqrt\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        r"√(\1)", s,
    )

    # 4. Flatten \mathrm{text}, \mathbf{text}, \text{text} → text
    s = re.sub(
        r"\\(?:mathrm|mathbf|mathit|text|textit|textbf|mathsf|mathtt)"
        r"\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
        r"\1", s,
    )

    # 5. Remove \displaystyle, \scriptstyle, \textstyle
    s = re.sub(r"\\(?:displaystyle|scriptstyle|textstyle)\s*", "", s)

    # 6. Drop sizing/grouping: \left, \right, \big, \Big, \bigg, \Bigg
    s = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)[lrm]?\s*", "", s)

    # 7. Strip accent commands: \ddot{v}→v, \dot{x}→x, \hat{y}→y, \bar{z}→z, etc.
    s = re.sub(
        r"\\(?:ddot|dot|hat|bar|tilde|vec|breve|check|acute|grave)"
        r"\{([^{}]+)\}",
        r"\1", s,
    )

    # 8. Replace known LaTeX commands with Unicode (longest-first)
    for cmd in sorted(_LATEX_UNICODE, key=len, reverse=True):
        s = s.replace(cmd, _LATEX_UNICODE[cmd])

    # 9. Flatten subscripts: bare _x first, then _{text}.
    #    Insert space when next char is a letter: C_pv → C_p v, m_{eq}w → m_eq w.
    #    Order matters: do bare first so braced results don't get re-split.

    # 9a. Bare subscript: _x (single letter/digit, no braces)
    _bare_sub = re.compile(r"_([a-zA-Z0-9])")
    _buf, _pos = [], 0
    for m in _bare_sub.finditer(s):
        start, end = m.span()
        _buf.append(s[_pos:start])
        _buf.append(m.group(0))
        if end < len(s) and s[end].isalpha():
            _buf.append(" ")
        _pos = end
    _buf.append(s[_pos:])
    s = "".join(_buf)

    # 9b. Braced subscript: _{text} → _text
    def _flatten_sub(m):
        result = f"_{m.group(1)}"
        if m.end() < len(m.string) and m.string[m.end()].isalpha():
            result += " "
        return result
    s = re.sub(r"_\{([^{}]+)\}", _flatten_sub, s)

    # 10. Flatten superscripts: ^{text} → ^text
    s = re.sub(r"\^\{([^{}]+)\}", r"^\1", s)

    # 11. Collapse leftover braces: {text} → text
    s = re.sub(r"\{([^{}]+)\}", r"\1", s)

    # 12. Clean up remaining bare \commands — keep name, drop backslash
    s = re.sub(r"\\([a-zA-Z]+)", r"\1", s)

    # 13. Add space at script boundary: Greek→Latin, Latin→Greek
    #     \theta w → θ w, v_pθ → v_p θ
    s = re.sub(r"([α-ωΑ-Ω])([a-zA-Z])", r"\1 \2", s)
    s = re.sub(r"([a-zA-Z])([α-ωΑ-Ω])", r"\1 \2", s)

    # 14. Normalise whitespace & strip zero-width/invisible characters
    s = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad]+", "", s)
    s = re.sub(r"\s+", " ", s)

    # ---- 15. Restore display math blocks (ZWS stripped, LaTeX kept) ----
    for key, block in _display_blocks.items():
        # Extract inner content: $$ ... $$
        inner = re.sub(r"^\$\$\s*", "", block)
        inner = re.sub(r"\s*\$\$$", "", inner)
        # Strip ZWS, normalize whitespace
        inner = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad]+", "", inner)
        inner = re.sub(r"\s+", " ", inner).strip()
        s = s.replace(key, f"$${inner}$$")

    return s.strip()


def latex_to_omml_element(latex: str):
    """Return an OMML (``<m:oMath>``) lxml element for *latex*, or None."""
    try:
        import latex2mathml.converter
    except Exception:
        return None
    xslt = _get_xslt()
    if not xslt:
        return None
    cleaned = _sanitize_latex(latex)
    if not cleaned:
        return None
    try:
        mathml = latex2mathml.converter.convert(cleaned)
        root = etree.fromstring(mathml.encode("utf-8"))
        return xslt(root).getroot()
    except Exception:
        return None


def append_omml_math(paragraph, latex) -> bool:
    """Insert a native OMML equation into *paragraph*. Returns True on success."""
    el = latex_to_omml_element(latex)
    if el is None:
        return False
    try:
        paragraph._p.append(el)
        return True
    except Exception:
        return False