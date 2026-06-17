"""Shared LaTeX → OMML (native Word math) helper for journal generators.

Mirrors the proven conversion path in IEEEgen.py so every generator can emit
real Word equation objects (``<m:oMath>``) instead of flattened unicode text.
Pipeline: sanitize LaTeX → latex2mathml → MathML → MML2OMML.XSL → OMML element.

Usage in a generator's ``add_formula``::

    from _math_omml import append_omml_math
    if not append_omml_math(paragraph, latex):
        # fall back to the generator's existing unicode/text rendering
        ...

``append_omml_math`` returns True only when a native OMML element was inserted.
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
