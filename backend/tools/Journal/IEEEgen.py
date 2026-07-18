from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree

from ._docx_base import _constrain_table_width, _shrink_omml_to_column

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "ieee.json"
TEMPLATE_PATH = BASE_DIR / "IEEE.docx"
DEFAULT_OUTPUT_NAME = "Dokumen_IEEE.docx"
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
PAGE_WIDTH_PT = 595.3
BODY_MARGIN_PT = 45.35
BODY_GAP_PT = 18.0
BODY_COLUMN_WIDTH_PT = (PAGE_WIDTH_PT - (2 * BODY_MARGIN_PT) - BODY_GAP_PT) / 2
MAX_FIGURE_WIDTH_CM = 4.0  # 2-col: ~50% column width (matches AEJ)
NS_MAP = {
    b"http://purl.oclc.org/ooxml/wordprocessingml/main": b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    b"http://purl.oclc.org/ooxml/officeDocument/relationships": b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/drawingml/main": b"http://schemas.openxmlformats.org/drawingml/2006/main",
    b"http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing": b"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    b"http://purl.oclc.org/ooxml/officeDocument/math": b"http://schemas.openxmlformats.org/officeDocument/2006/math",
}
STYLE_XML_ID = {
    "Body Text": "BodyText",
    "heading 1": "Heading1",
    "heading 2": "Heading2",
    "heading 3": "Heading3",
    "paper title": "papertitle",
    "Author": "Author",
    "Abstract": "Abstract",
    "Keywords": "Keywords",
    "bullet list": "bulletlist",
    "references": "references",
    "equation": "equation",
    "figure caption": "figurecaption",
    "table head": "tablehead",
    "table col head": "tablecolhead",
    "table copy": "tablecopy",
    "Affiliation": "Affiliation",
}
XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]
_XSLT = None


def _format_reference(item) -> str:
    """Format a reference dict into a citation string."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()
    text = item.get("text") or item.get("Text") or item.get("value")
    if text:
        return str(text).strip()
    parts = []
    authors = item.get("authors", [])
    if authors:
        parts.append(", ".join(str(a) for a in authors) if isinstance(authors, list) else str(authors))
    year = item.get("year")
    if year:
        parts.append(f"({year})")
    title = item.get("title", "")
    if title:
        parts.append(f'"{title},"')
    jname = item.get("journal") or item.get("conference") or ""
    if jname:
        parts.append(str(jname) + ",")
    vol = item.get("volume", "")
    if vol:
        parts.append(f"vol. {vol},")
    issue = item.get("issue", "")
    if issue:
        parts.append(f"no. {issue},")
    pages = item.get("pages", "")
    if pages:
        parts.append(f"pp. {pages},")
    doi = item.get("doi", "")
    if doi:
        parts.append(f"doi: {doi}.")
    url = item.get("url", "")
    if url:
        accessed = item.get("accessed", "")
        parts.append(f"[Online]. Available: {url}" + (f" [Accessed: {accessed}]." if accessed else "."))
    publisher = item.get("publisher", "")
    if publisher and not jname:
        location = item.get("location", "")
        parts.append(f"{location}: {publisher}." if location else f"{publisher}.")
    result = " ".join(str(p) for p in parts if p).strip()
    result = result.replace(" , ", ", ").replace(" .", ".")
    if result.endswith(","):
        result = result[:-1] + "."
    if not result.endswith("."):
        result = result + "."
    return result

def _strict_to_trans(data: bytes) -> bytes:
    for old, new in NS_MAP.items():
        data = data.replace(old, new)
    return data


def _inject_template_styles(doc: Document, template_path: Path) -> None:
    if not template_path.exists():
        return
    try:
        with zipfile.ZipFile(template_path) as archive:
            if "word/styles.xml" not in archive.namelist():
                return
            raw = archive.read("word/styles.xml")
    except (zipfile.BadZipFile, KeyError):
        return
    tmpl_styles = etree.fromstring(_strict_to_trans(raw))
    cur = doc.part.styles._element
    for child in list(cur):
        cur.remove(child)
    for child in list(tmpl_styles):
        cur.append(child)
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    def wq(tag):
        return f"{{{ns_w}}}{tag}"
    for ppr in cur.findall(f".//{wq('pPr')}"):
        num_pr = ppr.find(wq("numPr"))
        if num_pr is None:
            continue
        num_id = num_pr.find(wq("numId"))
        if num_id is not None:
            num_id.set(wq("val"), "0")
    try:
        if hasattr(doc.part.styles, "_styles"):
            doc.part.styles._styles = None
    except Exception:
        pass


def _pt2tw(pt: float) -> int:
    return int(round(pt * 20))


def _set_para_style(paragraph, style_name: str) -> None:
    xml_id = STYLE_XML_ID.get(style_name, style_name)
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(qn("w:val"), xml_id)


def _para(
    doc: Document,
    style_id: str | None = None,
    align=None,
    sb: float | None = None,
    sa: float | None = None,
    fi: float | None = None,
    li: float | None = None,
):
    paragraph = doc.add_paragraph()
    if style_id:
        _set_para_style(paragraph, style_id)
    pf = paragraph.paragraph_format
    if align is not None:
        paragraph.alignment = align
    if sb is not None:
        pf.space_before = Pt(sb)
    if sa is not None:
        pf.space_after = Pt(sa)
    if fi is not None:
        pf.first_line_indent = Pt(fi)
    if li is not None:
        pf.left_indent = Pt(li)
    return paragraph


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _build_sectpr(
    num_cols: int,
    col_space_pt: float,
    top_pt: float,
    bottom_pt: float,
    left_pt: float,
    right_pt: float,
    section_type: str = "continuous",
    w_pt: float = 595.3,
    h_pt: float = 841.9,
    header_pt: float = 36.0,
    footer_pt: float = 36.0,
    title_pg: bool = False,
):
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    def wq(tag):
        return f"{{{ns_w}}}{tag}"
    sectpr = etree.Element(wq("sectPr"))
    sec_type = etree.SubElement(sectpr, wq("type"))
    sec_type.set(wq("val"), section_type)
    pg_sz = etree.SubElement(sectpr, wq("pgSz"))
    pg_sz.set(wq("w"), str(_pt2tw(w_pt)))
    pg_sz.set(wq("h"), str(_pt2tw(h_pt)))
    pg_mar = etree.SubElement(sectpr, wq("pgMar"))
    pg_mar.set(wq("top"), str(_pt2tw(top_pt)))
    pg_mar.set(wq("right"), str(_pt2tw(right_pt)))
    pg_mar.set(wq("bottom"), str(_pt2tw(bottom_pt)))
    pg_mar.set(wq("left"), str(_pt2tw(left_pt)))
    pg_mar.set(wq("header"), str(_pt2tw(header_pt)))
    pg_mar.set(wq("footer"), str(_pt2tw(footer_pt)))
    pg_mar.set(wq("gutter"), "0")
    cols = etree.SubElement(sectpr, wq("cols"))
    if num_cols > 1:
        cols.set(wq("num"), str(num_cols))
    cols.set(wq("space"), str(_pt2tw(col_space_pt)))
    if title_pg:
        etree.SubElement(sectpr, wq("titlePg"))
    return sectpr


def _embed_sectpr(doc: Document, sectpr_el, style_id: str | None = None):
    paragraph = _para(doc, style_id=style_id)
    ppr = paragraph._p.get_or_add_pPr()
    ppr.append(sectpr_el)
    return paragraph


def _setup_main_sectpr(doc: Document) -> None:
    body = doc.element.body
    sectpr = body.find(qn("w:sectPr"))
    if sectpr is None:
        sectpr = OxmlElement("w:sectPr")
        body.append(sectpr)
    for tag in ("w:cols", "w:pgSz", "w:pgMar", "w:type", "w:titlePg"):
        for old in sectpr.findall(qn(tag)):
            sectpr.remove(old)
    pg_sz = OxmlElement("w:pgSz")
    pg_sz.set(qn("w:w"), str(_pt2tw(595.3)))
    pg_sz.set(qn("w:h"), str(_pt2tw(841.9)))
    sectpr.append(pg_sz)
    pg_mar = OxmlElement("w:pgMar")
    pg_mar.set(qn("w:top"), str(_pt2tw(54.0)))
    pg_mar.set(qn("w:right"), str(_pt2tw(44.65)))
    pg_mar.set(qn("w:bottom"), str(_pt2tw(72.0)))
    pg_mar.set(qn("w:left"), str(_pt2tw(44.65)))
    pg_mar.set(qn("w:header"), str(_pt2tw(36.0)))
    pg_mar.set(qn("w:footer"), str(_pt2tw(36.0)))
    pg_mar.set(qn("w:gutter"), "0")
    sectpr.append(pg_mar)
    cols = OxmlElement("w:cols")
    cols.set(qn("w:space"), str(_pt2tw(36.0)))
    sectpr.append(cols)
    sec_type = OxmlElement("w:type")
    sec_type.set(qn("w:val"), "continuous")
    sectpr.append(sec_type)


def _get_xslt():
    global _XSLT
    if _XSLT is not None:
        return _XSLT
    for candidate in XSL_CANDIDATES:
        try:
            if candidate.exists():
                _XSLT = etree.XSLT(etree.parse(str(candidate)))
                return _XSLT
        except Exception:
            continue
    _XSLT = False
    return _XSLT


def _sanitize_latex(latex: str) -> str:
    """Clean LaTeX strings known to break latex2mathml.

    Replaces forbidden text/font commands with MathML-friendly equivalents
    and normalizes manual sizing/delimiter commands.
    """
    if not latex:
        return latex
    s = latex
    # Strip display-math delimiters if present (renderer handles layout)
    s = s.strip()
    if s.startswith("$$") and s.endswith("$$"):
        s = s[2:-2].strip()
    elif s.startswith("\[") and s.endswith("\]"):
        s = s[2:-2].strip()
    elif s.startswith("\(") and s.endswith("\)"):
        s = s[2:-2].strip()
    # Strip papergenerator toggle formatting (\b...\b, \i...\i, \u...\u)
    # These are DOCX bold/italic/underline toggles, not valid LaTeX.
    s = s.replace("\\b", "")
    s = s.replace("\\i", "")
    s = s.replace("\\u", "")
    s = s.replace("\\text{", "\\mathrm{")
    s = s.replace("\\textbf{", "\\mathbf{")
    s = s.replace("\\textit{", "\\mathit{")
    # \\mathbb, \\mathcal, \\mathscr, \\mathfrak are supported by latex2mathml - keep them
    s = re.sub(r"\\displaystyle\s*", "", s)
    s = s.replace("\\Big(", "\\left(").replace("\\Big)", "\\right)")
    s = s.replace("\\big(", "\\left(").replace("\\big)", "\\right)")
    s = s.replace("\\Bigl(", "\\left(").replace("\\Biggr)", "\\right)")
    # Remove \\label, \\ref, \\eqref, \\tag (not needed, numbering is automatic)
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    s = re.sub(r"\\eqref\{[^}]*\}", "", s)
    s = re.sub(r"\\ref\{[^}]*\}", "", s)
    s = re.sub(r"\\tag\{[^}]*\}", "", s)
    # Replace \\boxed with plain content
    s = re.sub(r"\\boxed\{([^}]*)\}", r"\1", s)
    # Replace \\color{...}{content} with content
    s = re.sub(r"\\color\{[^}]*\}\{([^}]*)\}", r"\1", s)
    # Convert Unicode superscript digits to LaTeX ^{N} (e.g. ⁸ → ^{8})
    _sup_map = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    sup_run = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
    parts = []
    pos = 0
    for m in sup_run.finditer(s):
        parts.append(s[pos:m.start()])
        digits = m.group().translate(_sup_map)
        parts.append("^{" + digits + "}")
        pos = m.end()
    parts.append(s[pos:])
    s = "".join(parts)
    # Convert Unicode subscript digits to LaTeX _{N} (e.g. ₁ → _{1})
    _sub_map = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    sub_run = re.compile(r"[₀₁₂₃₄₅₆₇₈₉]+")
    parts = []
    pos = 0
    for m in sub_run.finditer(s):
        parts.append(s[pos:m.start()])
        digits = m.group().translate(_sub_map)
        parts.append("_{" + digits + "}")
        pos = m.end()
    parts.append(s[pos:])
    s = "".join(parts)
    return s



def _latex_to_omml(latex: str):
    try:
        import latex2mathml.converter
    except Exception as exc:
        print(f"[IEEEgen] latex2mathml import failed: {exc}")
        return None
    xslt = _get_xslt()
    if not xslt:
        print("[IEEEgen] XSLT stylesheet not available for math conversion")
        return None
    cleaned = _sanitize_latex(latex)
    try:
        mathml = latex2mathml.converter.convert(cleaned)
        root = etree.fromstring(mathml.encode("utf-8"))
        return xslt(root).getroot()
    except Exception as exc:
        print(f"[IEEEgen] OMML conversion failed for {cleaned!r}: {exc}")
        return None


def _append_inline_math(paragraph, latex: str) -> bool:
    omml = _latex_to_omml(latex)
    if omml is None:
        run = paragraph.add_run(latex)
        run.italic = True
        run.font.name = "Cambria Math"
        return False
    tag = omml.tag.split("}")[-1] if "}" in omml.tag else omml.tag
    if tag == "oMath":
        paragraph._p.append(omml)
    elif tag == "oMathPara":
        paragraph._p.append(omml)
    else:
        wrapper = etree.fromstring(f'<m:oMath xmlns:m="{MATH_NS}"/>')
        wrapper.append(omml)
        paragraph._p.append(wrapper)
    return True


def _append_text_run(
    paragraph, text: str, bold: bool = False, italic: bool = False, underline: bool = False
):
    if not text:
        return
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    run.underline = underline


def _append_line_break(paragraph):
    paragraph.add_run().add_break()


def _decode_stray_escapes(text: str) -> str:
    """Decode literal escape sequences the AI sometimes emits as raw text.

    The model is asked to use bullets, and in some outputs it writes the six
    literal characters ``\\u2022`` instead of the real bullet ``•``. Left as-is
    these never render: in Word the ``\\u`` is even consumed as the underline
    toggle, mangling the following text. We decode any ``\\uXXXX`` (4 hex) into
    the real character BEFORE the toggle/markup parser runs, plus a couple of
    common whitespace escapes. Tabs and other control chars below U+0020 are
    converted to a space so they can't poison the document.
    """
    if not text:
        return text
    # Strip literal backspace char (U+0008) — shows as empty box in Word
    text = text.replace("\x08", "")
    if "\\u" in text:
        def _u(m):
            try:
                ch = chr(int(m.group(1), 16))
                return " " if ord(ch) < 0x20 else ch
            except Exception:
                return m.group(0)
        text = re.sub(r"\\u([0-9a-fA-F]{4})", _u, text)
    if "\\t" in text:
        # Replace literal tab escape \\t with space, but NOT when it's part of
        # a LaTeX command like \\theta, \\times, \\text, \\tan, etc.
        # Negative lookahead: only replace \\t NOT followed by a letter.
        text = re.sub(r"\\t(?![a-z])", " ", text)

    # Fix double-escaped toggle markers (AI often double-escapes in JSON)
    text = text.replace('\\\\b', '\\b')
    text = text.replace('\\\\i', '\\i')
    text = text.replace('\\\\u', '\\u')
    # Fix double-escaped math delimiters
    text = text.replace('\\\\(', '\\(')
    text = text.replace('\\\\)', '\\)')
    text = text.replace('\\\\[', '\\[')
    text = text.replace('\\\\]', '\\]')
    return text


def _clean_image_prompt(prompt: str) -> str:
    """Return the bare image prompt for the Word placeholder box.

    The schema stores prompts as ``(create an image "<desc>")``. In Word we
    want exactly ``create an image "<desc>"`` — no wrapping parentheses and no
    ``[PROMPT UNTUK AI GAMBAR: ...]`` envelope — so the user can copy it
    straight into an image generator.
    """
    s = _decode_stray_escapes(str(prompt or "")).strip()
    # Strip the internal envelope if it somehow reached here.
    m = re.match(r"^\[PROMPT UNTUK AI GAMBAR:\s*(.*)\]$", s, flags=re.DOTALL)
    if m:
        s = m.group(1).strip()
    # Strip one layer of surrounding parentheses: (create an image "...")
    if s.startswith("(") and s.endswith(")") and len(s) >= 2:
        s = s[1:-1].strip()
    # If a leading "Title. " precedes the create-an-image clause, keep only the clause.
    idx = s.lower().find("create an image")
    if idx > 0:
        s = s[idx:].strip()
    return s


def _sanitize_llm_text_artifacts(text: str) -> str:
    """Repair common LLM streaming artifacts that corrupt IEEE paper text.

    The text-generation LLM occasionally emits broken LaTeX, mangled
    punctuation, or missing spaces.  These are not valid content — they are
    transport-level corruption (token-boundary artefacts, lost whitespace,
    collapsed integral notation, etc.).  This pass runs BEFORE the toggle /
    math parser so that the downstream OMML converter receives clean input.

    Scope (deliberately conservative — only fix known corruption patterns):
      1. Collapsed integral notation:  "ntsunrisesunset" -> "\\int_{sunrise}^{sunset}"
      2. Bare inline math (Greek + subscripts without $...$ delimiters)
      3. Citation punctuation:  "[8]. [9]" -> "[8], [9]"
      4. Sentence-boundary comma corruption:  "mengajukan. memodelkan" -> "mengajukan, memodelkan"
      5. Missing spaces around slash-separated numbers:  "2,00/Wpada2010" -> "2,00/W pada 2010"
    """
    if not text:
        return text
    s = text

    # ------------------------------------------------------------------
    # 1. Restore collapsed integral / sum notation.
    #    The LLM sometimes drops the backslash and braces, producing tokens
    #    like "ntsunrisesunset" (= \\int_{sunrise}^{sunset}) or
    #    "ntsunsetsunrise" (= \\int_{sunset}^{sunrise}).
    # ------------------------------------------------------------------
    s = s.replace("ntsunrisesunset", "\\int_{sunrise}^{sunset}")
    s = s.replace("ntsunsetsunrise", "\\int_{sunset}^{sunrise}")
    s = s.replace("ntsum_", "\\sum_")
    # Generic: "nt" prefix before a known bound keyword -> "\\int_"
    s = re.sub(r"\bnt(sunrise|sunset|0|1|t)\b", r"\\int_{\1}", s)

    # ------------------------------------------------------------------
    # 2. Wrap bare inline math that the LLM emitted without $...$.
    #    Only wrap tokens that are CLEARLY math (Greek letter + subscript /
    #    caret) and are NOT already inside a $...$ or $$...$$ block.
    #    We protect existing math spans first, then patch the rest.
    # ------------------------------------------------------------------
    _MATH_PROTECT = re.compile(r"\$\$.*?\$\$|\$[^$]+?\$", re.DOTALL)
    placeholders: list[str] = []

    def _stash(m):
        placeholders.append(m.group(0))
        return f"\x00MATH{len(placeholders) - 1}\x00"

    s = _MATH_PROTECT.sub(_stash, s)

    # Map of bare tokens -> LaTeX equivalent.  Ordered so longer patterns
    # match first (e.g. "eta_(PV,STC)" before "eta_PV").
    _bare_math = [
        # Greek-letter variables with parenthesised subscripts
        (r"\bη_\(([A-Za-z0-9,_]+)\)", r"$\\eta_{\1}$"),
        (r"\bε_\(([A-Za-z0-9,_]+)\)", r"$\\epsilon_{\1}$"),
        (r"\bσ_\(([A-Za-z0-9,_]+)\)", r"$\\sigma_{\1}$"),
        (r"\bβ_\(([A-Za-z0-9,_]+)\)", r"$\\beta_{\1}$"),
        # Greek-letter variables with simple subscripts
        (r"\bη_([A-Za-z][A-Za-z0-9]*)\b", r"$\\eta_{\1}$"),
        (r"\bε_([A-Za-z][A-Za-z0-9]*)\b", r"$\\epsilon_{\1}$"),
        (r"\bσ_([A-Za-z][A-Za-z0-9]*)\b", r"$\\sigma_{\1}$"),
        (r"\bβ_([A-Za-z][A-Za-z0-9]*)\b", r"$\\beta_{\1}$"),
        # Greek-letter variables with parenthesised subscripts: E_(g,TRC)
        (r"\bE_\(([A-Za-z0-9,_]+)\)", r"$E_{\1}$"),
        (r"\bP_\(([A-Za-z0-9,_]+)\)", r"$P_{\1}$"),
        (r"\bk_\(([A-Za-z0-9,_]+)\)", r"$k_{\1}$"),
        (r"\bT_\(([A-Za-z0-9,_]+)\)", r"$T_{\1}$"),
        # Greek delta + capital letter: ΔT, ΔE
        (r"\bΔ([A-Z])\b", r"$\\Delta \1$"),
        # Simple subscripted variables: T_c, T_a, T_sky, E_g, P_TRC, E_daily
        (r"\bT_([a-z]{1,4})\b(?!\{)", r"$T_{\1}$"),
        (r"\bE_([a-z]{1,8})\b(?!\{)", r"$E_{\1}$"),
        (r"\bP_([A-Za-z]{1,8})\b(?!\{)", r"$P_{\1}$"),
        (r"\bk_([a-z]{1,8})\b(?!\{)", r"$k_{\1}$"),
    ]
    for pattern, repl in _bare_math:
        s = re.sub(pattern, repl, s)

    # Restore protected math spans
    def _unstash(m):
        idx = int(m.group(1))
        return placeholders[idx]

    s = re.sub(r"\x00MATH(\d+)\x00", _unstash, s)

    # ------------------------------------------------------------------
    # 3. Citation punctuation:  "[8]. [9]" -> "[8], [9]"
    #    The LLM sometimes ends a citation with a period then starts the
    #    next citation; IEEE style wants a comma.
    # ------------------------------------------------------------------
    s = re.sub(r"(\])\.\s+\[", r"\1, [", s)

    # ------------------------------------------------------------------
    # 4. Sentence-boundary comma corruption.
    #    Indonesian / English connectives that should be comma-separated
    #    sometimes get a period from the LLM (token-boundary artefact).
    #    Only fix when a lowercase word follows a period+space (clearly not
    #    a sentence end) and the preceding word is not an abbreviation.
    # ------------------------------------------------------------------
    _comma_after = [
        "mengajukan", "surya", "puncak", "efisiensi",
        "melainkan", "sementara", "memodelkan", "pendinginan",
        "namun", "sedangkan", "sehingga", "serta",
    ]
    for word in _comma_after:
        s = re.sub(r"\.\s+" + word + r"\b", r", " + word, s, flags=re.IGNORECASE)

    # ------------------------------------------------------------------
    # 5. Missing spaces around slash-separated numbers and units.
    #    "2,00/Wpada2010menjadi0,20/W" -> "2,00/W pada 2010 menjadi 0,20/W"
    #    Insert space between /W and a following Indonesian connective word
    #    (pada, menjadi, dari, ke, dan, atau) and between that word and a
    #    digit, then between a digit and /W.
    # ------------------------------------------------------------------
    s = re.sub(r"(/W)(pada|menjadi|dari|ke|dan|atau)(\d)", r"\1 \2 \3", s, flags=re.IGNORECASE)
    # "2010menjadi0,20" -> "2010 menjadi 0,20"
    s = re.sub(r"(\d)(menjadi|pada|dari|ke)(\d)", r"\1 \2 \3", s, flags=re.IGNORECASE)
    # Trailing digit glued to /W:  "0,20/Wpada" already handled above; also
    # handle "0,20/W" glued directly to the next word boundary.
    s = re.sub(r"(/W)([a-z]{4,})", r"\1 \2", s, flags=re.IGNORECASE)

    return s


def _normalize_text_commands(text: str) -> str:
    text = _sanitize_llm_text_artifacts(text)
    text = _decode_stray_escapes(text)
    text = re.sub(r'\\\\n(?![a-z])', '\n', text)
    # Convert Markdown bold/italic to \b..\b / \i..\i toggle format
    text = re.sub(r"\*\*(.+?)\*\*", r"\\b\1\\b", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+?)\*", r"\\i\1\\i", text)
    return text


def _iter_rich_tokens(text: str):
    normalized = _normalize_text_commands(text)
    buffer: list[str] = []
    bold = False
    italic = False
    underline = False
    index = 0

    def flush_buffer():
        nonlocal buffer
        content = "".join(buffer)
        buffer = []
        if content:
            yield {
                "kind": "text",
                "value": content,
                "bold": bold,
                "italic": italic,
                "underline": underline,
            }

    while index < len(normalized):
        char = normalized[index]
        if char == "\n":
            yield from flush_buffer()
            yield {"kind": "linebreak"}
            index += 1
            continue
        if char == "\\" and index + 1 < len(normalized):
            command = normalized[index + 1]
            if command == "\\":
                buffer.append("\\")
                index += 2
                continue
            if command == "b":
                yield from flush_buffer()
                bold = not bold
                index += 2
                continue
            if command == "i":
                yield from flush_buffer()
                italic = not italic
                index += 2
                continue
            if command == "u":
                yield from flush_buffer()
                underline = not underline
                index += 2
                continue
        # $$...$$ display math (check before $...$)
        if char == "$" and index + 1 < len(normalized) and normalized[index + 1] == "$":
            closing = normalized.find("$$", index + 2)
            if closing != -1:
                yield from flush_buffer()
                formula = normalized[index + 2 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 2
                continue
        # $...$ inline math
        if char == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                yield from flush_buffer()
                formula = normalized[index + 1 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 1
                continue
        # \(...\) inline math
        if char == "\\" and index + 1 < len(normalized) and normalized[index + 1] == "(":
            closing = normalized.find("\\)", index + 2)
            if closing != -1:
                yield from flush_buffer()
                formula = normalized[index + 2 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 2
                continue
        # \[...\] display math
        if char == "\\" and index + 1 < len(normalized) and normalized[index + 1] == "[":
            closing = normalized.find("\\]", index + 2)
            if closing != -1:
                yield from flush_buffer()
                formula = normalized[index + 2 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 2
                continue
        buffer.append(char)
        index += 1
    yield from flush_buffer()


def _append_rich_text(paragraph, text: str):
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            _append_line_break(paragraph)
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                run = paragraph.add_run(token["value"])
                run.italic = True
            continue
        _append_text_run(
            paragraph,
            token["value"],
            bold=token["bold"],
            italic=token["italic"],
            underline=token["underline"],
        )


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    parts = [part for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return parts or [""]


def _body_paragraphs(doc: Document, text: str, style_id: str = "Body Text"):
    paragraphs = []
    for block in _split_body_blocks(text):
        paragraph = _para(doc, style_id=style_id)
        _append_rich_text(paragraph, block)
        paragraphs.append(paragraph)
    return paragraphs


def _roman(number) -> str:
    try:
        value = int(str(number).strip())
    except Exception:
        return str(number).strip()
    numerals = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    result = []
    for arabic, roman in numerals:
        while value >= arabic:
            result.append(roman)
            value -= arabic
    return "".join(result)


def _subsection_letter(number_text: str) -> str:
    parts = [part for part in str(number_text).split(".") if part]
    if not parts:
        return str(number_text)
    try:
        last = int(parts[-1])
    except Exception:
        return str(number_text)
    if 1 <= last <= 26:
        return chr(ord("A") + last - 1)
    return str(number_text)


def _subsubsection_label(number_text: str) -> str:
    parts = [part for part in str(number_text).split(".") if part]
    if not parts:
        return str(number_text)
    return f"{parts[-1]})"


def _add_title(doc: Document, config: dict):
    # Support both new format (title) and legacy format (TitleBlock)
    title = config.get("title", "")
    if not title:
        title = config.get("TitleBlock", {}).get("Title", "Untitled Paper")

    paragraph = _para(doc, style_id="paper title")
    _append_rich_text(paragraph, title)
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    rpr = run._r.get_or_add_rPr()
    kern = OxmlElement("w:kern")
    kern.set(qn("w:val"), "48")
    rpr.append(kern)


def _parse_author_entries(title_block: dict) -> list[dict]:
    # Support both new format (authors array) and legacy format
    authors = title_block.get("authors", [])
    if authors:
        # New format: authors is an array of author objects
        entries = []
        for author in authors:
            name = author.get("name", "")
            affiliation = author.get("affiliation", "")
            location = author.get("location", "")
            email = author.get("email", "")

            lines = []
            if affiliation:
                lines.append(affiliation)
            if location:
                lines.append(location)
            if email:
                lines.append(f"e-mail: {email}")

            entries.append({"name": name, "lines": lines})
        return entries

    # Legacy format: AuthorLine and AddressLines
    author_line = str(title_block.get("AuthorLine") or "").strip()
    address_lines = [
        str(line).strip() for line in title_block.get("AddressLines", []) if str(line).strip()
    ]
    if not author_line and not address_lines:
        return []
    common_lines: list[str] = []
    affiliation_map: dict[str, str] = {}
    email_lines: list[str] = []
    for line in address_lines:
        if re.match(r"^\*?\s*e-?mail\s*:", line, flags=re.IGNORECASE):
            email_lines.append(line.lstrip("*"))
            continue
        match = re.match(r"^(\d+(?:\s*,\s*\d+)*)\s*(.+)$", line)
        if match:
            ids = [part.strip() for part in match.group(1).split(",")]
            content = match.group(2).strip()
            for ident in ids:
                affiliation_map[ident] = content
            continue
        common_lines.append(line)
    raw_names = [part.strip() for part in author_line.split(",") if part.strip()]
    entries = []
    for raw in raw_names:
        starred = raw.startswith("*")
        clean = raw.lstrip("*").strip()
        numbers = re.findall(r"(\d+)", clean)
        name = re.sub(r"\d+$", "", clean).strip()
        if not name:
            name = clean
        lines: list[str] = []
        for number in numbers:
            affiliation = affiliation_map.get(number)
            if affiliation and affiliation not in lines:
                lines.append(affiliation)
        for line in common_lines:
            if line not in lines:
                lines.append(line)
        if starred:
            for email in email_lines:
                if email not in lines:
                    lines.append(email)
        entries.append({"name": name, "lines": lines})
    if entries:
        return entries
    fallback_lines = []
    if author_line:
        fallback_lines.append(author_line)
    fallback_lines.extend(address_lines)
    return [{"name": "", "lines": fallback_lines}]


def _add_authors(doc: Document, config: dict):
    # Support both new and legacy formats
    entries = _parse_author_entries(config)  # config can be the whole dict or just TitleBlock
    if not entries:
        return
    for entry in entries:
        # SATU paragraf per penulis dengan style "Author"
        paragraph = _para(doc, style_id="Author")

        # Nama penulis dengan font 9pt dan tidak bold
        if entry.get("name"):
            run = paragraph.add_run(entry["name"])
            run.font.size = Pt(9)  # IEEE author name size
            # run.bold = True  # Tidak bold

        # Afiliasi dan email dengan font lebih kecil dan italic
        for line in entry.get("lines", []):
            _append_line_break(paragraph)
            run = paragraph.add_run(line)
            run.font.size = Pt(9)  # IEEE affiliation size
            # Email tidak italic, yang lain italic
            if not re.match(r"^\s*e-?mail\s*:", line, flags=re.IGNORECASE):
                run.italic = True


def _add_abstracts(doc: Document, config: dict):
    # Support both new format (abstract, keywords) and legacy format
    abstract = config.get("abstract", "")
    keywords = config.get("keywords", [])

    # If new format not found, try legacy format
    if not abstract:
        abstract_block = config.get("Abstract", {})
        abstract = str(abstract_block.get("English") or "").strip()
        if not abstract:
            abstract = str(abstract_block.get("Indonesian") or "").strip()

    if not keywords:
        abstract_block = config.get("Abstract", {})
        keywords_en = str(abstract_block.get("KeywordsEnglish") or "").strip()
        keywords_id = str(abstract_block.get("KeywordsIndonesian") or "").strip()
        if keywords_en:
            keywords = [k.strip() for k in keywords_en.split(",")]
        elif keywords_id:
            keywords = [k.strip() for k in keywords_id.split(",")]

    # Add abstract
    if abstract:
        paragraph = _para(doc, style_id="Abstract")
        paragraph.add_run("Abstract")
        paragraph.add_run("—")
        _append_rich_text(paragraph, abstract)

    # Add keywords
    if keywords:
        keywords_text = ", ".join(keywords)
        paragraph = _para(doc, style_id="Keywords")
        paragraph.add_run("Index Terms")
        paragraph.add_run("—")
        _append_rich_text(
            paragraph, keywords_text if keywords_text.endswith(".") else f"{keywords_text}."
        )


def _section_heading_text(item: dict) -> str:
    number = str(item.get("NumberiOrLetter") or "").strip()
    title = str(item.get("Text") or "").strip().upper()
    if not number:
        return title
    return f"{_roman(number)}. {title}"


def _subsection_heading_text(item: dict) -> str:
    title = str(item.get("Text") or "").strip()
    number = str(item.get("NumberiOrLetter") or "").strip()
    label = _subsection_letter(number)
    return f"{label}. {title}" if label else title


def _subsubsection_heading_text(item: dict) -> str:
    title = str(item.get("Text") or "").strip()
    number = str(item.get("NumberiOrLetter") or "").strip()
    label = _subsubsection_label(number)
    return f"{label} {title}".strip()


def _add_section_heading(doc: Document, text: str):
    paragraph = _para(doc, style_id="heading 1")
    _append_rich_text(paragraph, text)


def _add_subsection_heading(doc: Document, text: str):
    paragraph = _para(doc, style_id="heading 2")
    run = paragraph.add_run(text)
    run.italic = True


def _add_subsubsection_heading(doc: Document, text: str):
    paragraph = _para(doc, style_id="heading 3")
    _append_rich_text(paragraph, text)


def _iter_point_entries(item: dict):
    items = item.get("Items")
    if isinstance(items, list) and items:
        for entry in items:
            if isinstance(entry, str):
                text = entry
                label = None
            elif isinstance(entry, dict):
                text = entry.get("Text", "")
                label = entry.get("Label")
            else:
                text = str(entry)
                label = None
            if text:
                yield text, label
        return
    text = item.get("Text", "")
    if text:
        yield text, item.get("Label")


def _add_point_list(doc: Document, item: dict):
    list_type = str(
        item.get("ListType") or ("number" if item.get("Numbered") else "bullet")
    ).lower()
    start_at = int(item.get("StartAt", 1))
    for index, (text, custom_label) in enumerate(_iter_point_entries(item), start=start_at):
        paragraph = _para(doc, style_id="bullet list")
        prefix = custom_label
        if prefix is None:
            prefix = f"{index}) " if list_type in {"number", "numbering", "ordered"} else "• "
        paragraph.add_run(prefix)
        _append_rich_text(paragraph, text)


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative

    # Also try the image/ subdirectory next to the JSON (correct for preview: user/<username>/<paper_id>/image/)
    image_relative = json_path.parent / "image" / path
    if image_relative.exists():
        return image_relative

    # Derive paper_id correctly: json_path.parent is usually paper_dir (user/<username>/<paper_id>/)
    # But for preview/export it might be in export/ subfolder
    if json_path.parent.name == "export":
        paper_id = json_path.parent.parent.name
    else:
        paper_id = json_path.parent.name

    # Try safe_paper_image_dir for canonical user/<username>/<paper_id>/image/ location
    try:
        from tools.editor.utils import safe_paper_image_dir
        img_dir = safe_paper_image_dir(paper_id)
        if img_dir and img_dir.exists():
            # Try direct match
            candidate = img_dir / path
            if candidate.is_file():
                return candidate
            # Try with just the filename
            fname = path.name
            candidate = img_dir / fname
            if candidate.is_file():
                return candidate
            # Extension-insensitive match (JSON may say .png but disk has .jpg)
            stem = Path(fname).stem
            for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif'):
                candidate = img_dir / (stem + ext)
                if candidate.is_file():
                    return candidate
            # Glob fallback
            for match in img_dir.glob(f"{stem}.*"):
                if match.is_file():
                    return match
            # Also try img_dir/image/ subdirectory
            if img_dir.name != "image":
                img_dir2 = img_dir / "image"
                if img_dir2.is_dir():
                    candidate = img_dir2 / path
                    if candidate.is_file():
                        return candidate
                    candidate = img_dir2 / fname
                    if candidate.is_file():
                        return candidate
                    for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif'):
                        candidate = img_dir2 / (stem + ext)
                        if candidate.is_file():
                            return candidate
                    for match in img_dir2.glob(f"{stem}.*"):
                        if match.is_file():
                            return match
    except Exception:
        pass

    return BASE_DIR / path



def _set_full_cell_borders(cell):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:

        tc_borders = OxmlElement("w:tcBorders")


        tc_pr.append(tc_borders)
    border_spec = {
        "top": {"val": "single", "sz": "8", "space": "0", "color": "auto"},
        "bottom": {"val": "single", "sz": "8", "space": "0", "color": "auto"},
        "left": {"val": "single", "sz": "8", "space": "0", "color": "auto"},
        "right": {"val": "single", "sz": "8", "space": "0", "color": "auto"},
    }
    for edge, values in border_spec.items():
        el = tc_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tc_borders.append(el)
        for key, value in values.items():
            el.set(qn(f"w:{key}"), value)


def _set_horizontal_cell_borders(cell, top=False, bottom=False):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)

    border_spec = {}
    border_spec["top"] = (
        {"val": "single", "sz": "8", "space": "0", "color": "auto"} if top else {"val": "none"}
    )

    border_spec["bottom"] = (
        {"val": "single", "sz": "8", "space": "0", "color": "auto"} if bottom else {"val": "none"}
    )
    border_spec["left"] = {"val": "none"}

    border_spec["right"] = {"val": "none"}

    for edge, values in border_spec.items():
        el = tc_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tc_borders.append(el)
        for key, value in values.items():
            el.set(qn(f"w:{key}"), value)


def _add_figure(doc: Document, item: dict, json_path: Path):
    """Render figure from legacy JTM format (ID='Gambar').

    Legacy items use the same field names as content format
    (ImageNumber, Title, Prompt, Path) so delegate directly.
    """
    _add_figure_from_content(doc, item, json_path)


def _add_prompt_box(doc: Document, item: dict):
    prompt_text = str(item.get("Prompt") or "").strip()
    if not prompt_text:
        prompt_text = str(item.get("Title") or "").strip() or "Prompt gambar belum diisi."
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Normal Table"
    _set_table_borders_match_template(table)
    cell = table.cell(0, 0)
    _set_full_cell_borders(cell)
    # Enable word wrap so long prompts wrap inside the cell
    tblPr = table._tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        table._tbl.append(tblPr)
    tblLayout = OxmlElement('w:tblLayout')
    tblLayout.set(qn('w:type'), 'autofit')
    tblPr.append(tblLayout)
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcW = OxmlElement('w:tcW')
    tcW.set(qn('w:type'), 'auto')
    tcPr.append(tcW)
    vAlign = OxmlElement('w:vAlign')
    vAlign.set(qn('w:val'), 'top')
    tcPr.append(vAlign)
    paragraph = cell.paragraphs[0]
    _set_para_style(paragraph, "Body Text")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _append_rich_text(paragraph, prompt_text)
    for extra_paragraph in cell.paragraphs[1:]:
        for run in extra_paragraph.runs:
            run.clear()
    return table


def _render_item(doc: Document, item: dict, json_path: Path):
    """Render item in legacy JTM format"""
    item_id = str(item.get("ID") or "").strip()
    if item_id in {"Bab", "Bab utama"}:
        _add_section_heading(doc, _section_heading_text(item))
        return
    if item_id in {"SubBab", "Bab 1.1"}:
        _add_subsection_heading(doc, _subsection_heading_text(item))
        return
    if item_id == "SubSubBab":
        _add_subsubsection_heading(doc, _subsubsection_heading_text(item))
        return
    if item_id == "Paragraf":
        _body_paragraphs(doc, str(item.get("Text") or ""))
        return
    if item_id == "Poin":
        _add_point_list(doc, item)
        return
    if item_id == "Gambar":
        _add_figure(doc, item, json_path)
        return
    if item_id == "Tabel":
        _add_table(doc, item)
        return
    if item_id == "Rumus":
        _add_equation_group(doc, item)


def _style_cell_paragraph(paragraph, style_id: str, align=WD_ALIGN_PARAGRAPH.CENTER):
    _set_para_style(paragraph, style_id)
    paragraph.alignment = align


def _add_table(doc: Document, item: dict):
    number = str(item.get("NumberiOrLetter") or "").strip()
    title = str(item.get("Title") or "").strip()
    caption = _para(doc, style_id="table head")
    label = f"TABLE {_roman(number)}"
    text = f"{label}. {title}" if title else label
    _append_rich_text(caption, text)
    headers = list(item.get("Headers", []))
    rows = list(item.get("Rows", []))
    if not headers:
        return
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders_match_template(table)
    _constrain_table_width(table, {"columns": 2})
    for column_index, value in enumerate(headers):
        cell = table.rows[0].cells[column_index]
        _set_horizontal_cell_borders(cell, top=True, bottom=True)
        cell.text = ""
        paragraph = cell.paragraphs[0]
        _style_cell_paragraph(paragraph, "table col head")
        _append_rich_text(paragraph, str(value))
        for run in paragraph.runs:
            run.bold = True
    for row_index, row_data in enumerate(rows, start=1):
        is_last_row = row_index == len(rows)
        for column_index, value in enumerate(row_data):
            if column_index >= len(headers):
                break
            cell = table.rows[row_index].cells[column_index]
            _set_horizontal_cell_borders(cell, top=False, bottom=is_last_row)
            cell.text = ""
            paragraph = cell.paragraphs[0]
            _style_cell_paragraph(paragraph, "table copy")
            _append_rich_text(paragraph, str(value))
    _para(doc, sa=4)


def _add_equation_line(doc: Document, formula: str, number: str | None = None):
    formula = _strip_math_delimiters(formula)
    if not formula:
        return
    paragraph = _para(doc, style_id="equation")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    tab_stops = paragraph.paragraph_format.tab_stops
    tab_stops.add_tab_stop(Pt(BODY_COLUMN_WIDTH_PT / 2), WD_TAB_ALIGNMENT.CENTER)
    tab_stops.add_tab_stop(Pt(BODY_COLUMN_WIDTH_PT), WD_TAB_ALIGNMENT.RIGHT)
    paragraph.add_run("\t")
    omml = _latex_to_omml(formula)
    if omml is not None:
        # Auto-shrink font to fit column width
        _shrink_omml_to_column(omml, formula, BODY_COLUMN_WIDTH_PT)
        tag = omml.tag.split("}")[-1] if "}" in omml.tag else omml.tag
        if tag == "oMath":
            paragraph._p.append(omml)
        elif tag == "oMathPara":
            paragraph._p.append(omml)
        else:
            wrapper = etree.fromstring(f'<m:oMath xmlns:m="{MATH_NS}"/>')
            wrapper.append(omml)
            paragraph._p.append(wrapper)
        paragraph.add_run("\u200b")
    else:
        run = paragraph.add_run(formula)
        run.italic = True
    if number is not None:
        paragraph.add_run(f"\t({number})")


def _add_equation_group(doc: Document, item: dict):
    formulas = [str(line).strip() for line in item.get("Lines", []) if str(line).strip()]
    if not formulas:
        return
    number = str(item.get("NumberiOrLetter") or "").strip() or None
    for formula in formulas[:-1]:
        _add_equation_line(doc, formula)
    _add_equation_line(doc, formulas[-1], number=number)


def _reference_parts(reference_text: str, fallback_number: int):
    match = re.match(r"^\s*\[(.+?)\]\s*(.*)$", reference_text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return str(fallback_number), reference_text.strip()


def _ieee_author_name(name: str) -> str:
    """Convert "Surname, F. M." → "F. M. Surname" (IEEE style: initials first).

    Leaves names that don't match the "Surname, Initials" pattern untouched.
    """
    s = str(name).strip()
    if not s:
        return s
    if "," in s:
        surname, rest = s.split(",", 1)
        surname = surname.strip()
        rest = rest.strip()
        if surname and rest:
            return f"{rest} {surname}".strip()
    return s


def _format_ieee_authors(authors) -> str:
    """Join an author list into IEEE form: 'A. B' , 'A. B and C. D',
    'A. B, C. D, and E. F'. Accepts list[str] or list[dict{name}]."""
    names = []
    if isinstance(authors, list):
        for a in authors:
            if isinstance(a, dict):
                nm = a.get("name") or a.get("author") or ""
            else:
                nm = str(a)
            nm = _ieee_author_name(nm)
            if nm:
                names.append(nm)
    elif isinstance(authors, str):
        names = [_ieee_author_name(authors)]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _format_ieee_citation(ref: dict) -> str:
    """Render a structured citation dict into an IEEE reference string.

    Supports type: journal, conference, book, and a generic fallback.
    Recognised keys: authors, title, journal, conference, booktitle, volume,
    issue/number, pages, year, publisher, location, doi, url.
    """
    authors = _format_ieee_authors(ref.get("authors"))
    title = str(ref.get("title") or "").strip()
    year = str(ref.get("year") or "").strip()
    pages = str(ref.get("pages") or "").strip()
    volume = str(ref.get("volume") or "").strip()
    issue = str(ref.get("issue") or ref.get("number") or "").strip()
    doi = str(ref.get("doi") or "").strip()
    url = str(ref.get("url") or "").strip()
    rtype = str(ref.get("type") or "").strip().lower()

    parts = []
    if authors:
        parts.append(f"{authors},")

    if rtype == "book":
        # A. Author, Title. Location: Publisher, Year, pp. X.
        if title:
            parts.append(f"{title}.")
        loc = str(ref.get("location") or "").strip()
        pub = str(ref.get("publisher") or "").strip()
        imprint = ""
        if loc and pub:
            imprint = f"{loc}: {pub}"
        elif pub:
            imprint = pub
        elif loc:
            imprint = loc
        tail = []
        if imprint and year:
            tail.append(f"{imprint}, {year}")
        elif imprint:
            tail.append(imprint)
        elif year:
            tail.append(year)
        if pages:
            tail.append(f"pp. {pages}")
        if tail:
            parts.append(", ".join(tail) + ".")
    elif rtype == "conference":
        # A. Author, "Title," in Conf Name, Year, pp. X.
        if title:
            parts.append(f'"{title},"')
        conf = str(ref.get("conference") or ref.get("booktitle") or "").strip()
        seg = []
        if conf:
            seg.append(f"in {conf}")
        if year:
            seg.append(year)
        if pages:
            seg.append(f"pp. {pages}")
        if seg:
            parts.append(", ".join(seg) + ".")
    else:
        # journal / generic: A. Author, "Title," Journal, vol. X, no. Y, pp. Z, Year.
        if title:
            parts.append(f'"{title},"')
        journal = str(ref.get("journal") or ref.get("venue") or "").strip()
        seg = []
        if journal:
            seg.append(journal)
        if volume:
            seg.append(f"vol. {volume}")
        if issue:
            seg.append(f"no. {issue}")
        if pages:
            seg.append(f"pp. {pages}")
        if year:
            seg.append(year)
        if seg:
            parts.append(", ".join(seg) + ".")

    text = " ".join(p for p in parts if p).strip()
    if doi:
        text = f"{text} doi: {doi}.".strip()
    elif url:
        text = f"{text} [Online]. Available: {url}".strip()
    return text


def _add_references(doc: Document, config: dict):
    # Support both new format (references section) and legacy format
    references = None

    # Try new format - look for direct references key
    if "references" in config:
        ref_data = config["references"]
        if isinstance(ref_data, dict):
            for _rk in ("content", "items"):
                _rc = ref_data.get(_rk)
                if isinstance(_rc, list):
                    references = _rc
                    break
        elif isinstance(ref_data, list):
            references = ref_data
    # Also try section_references key
    elif "section_references" in config:
        ref_data = config["section_references"]
        if isinstance(ref_data, dict):
            for _rk in ("content", "items"):
                _rc = ref_data.get(_rk)
                if isinstance(_rc, list):
                    references = _rc
                    break
        elif isinstance(ref_data, list):
            references = ref_data
    # If not found, try legacy sections format
    else:
        sections = config.get("sections", [])
        for section in sections:
            if section.get("title", "").upper() == "REFERENCES":
                references = section.get("content", [])
                break

    # If still not found, try legacy format
    if not references:
        references = config.get("References", [])

    if not references:
        return

    heading = _para(doc, style_id="heading 1")
    _append_rich_text(heading, "REFERENCES")

    # Handle different reference formats
    if isinstance(references, list) and references and isinstance(references[0], dict):
        # New format: list of reference objects. Two shapes supported:
        #   (a) {id, text}            → pre-formatted reference string
        #   (b) structured citation   → {authors, title, journal/conference,
        #                                volume, issue, pages, year, doi, type}
        # Structured dicts get rendered into IEEE style here.
        for index, reference in enumerate(references, start=1):
            ref_id = reference.get("id", "")
            ref_text = reference.get("text", "")
            if not ref_text:
                # No pre-formatted text → build IEEE citation from structured fields
                ref_text = _format_ieee_citation(reference)
            if not ref_text:
                continue
            paragraph = _para(doc, style_id="references")
            ppr = paragraph._p.get_or_add_pPr()
            ind = OxmlElement("w:ind")
            ind.set(qn("w:start"), str(int(round(17.7 * 20))))
            ind.set(qn("w:hanging"), str(int(round(17.7 * 20))))
            ppr.append(ind)
            label = str(ref_id) if ref_id else str(index)
            # Strip leading [N] or [N, M] if already in ref_text (LLM double-formatting)
            ref_text_clean = re.sub(r'^\s*\[\d+(?:,\s*\d+)*\]\s*', '', ref_text)
            _append_rich_text(paragraph, f"[{label}] {ref_text_clean}".strip())
    else:
        # Legacy format: list of reference strings
        for index, reference in enumerate(references, start=1):
            ref_id, ref_text = _reference_parts(str(reference), index)
            paragraph = _para(doc, style_id="references")
            ppr = paragraph._p.get_or_add_pPr()
            ind = OxmlElement("w:ind")
            ind.set(qn("w:start"), str(int(round(17.7 * 20))))
            ind.set(qn("w:hanging"), str(int(round(17.7 * 20))))
            ppr.append(ind)
            _append_rich_text(paragraph, f"[{ref_id}] {ref_text}".strip())


def _render_content_item(doc: Document, item: dict, json_path: Path):
    """Render a single content item from the new format"""
    item_id = str(item.get("id", "")).lower()

    if item_id == "text":
        text = str(item.get("text", ""))
        if text:
            _body_paragraphs(doc, text)

    elif item_id == "gambar" or item_id == "image":
        _add_figure_from_content(doc, item, json_path)

    elif item_id == "rumus" or item_id == "formula":
        _add_equation_from_content(doc, item)

    elif item_id == "tabel" or item_id == "table":
        _add_table_from_content(doc, item)


def _add_figure_from_content(doc: Document, item: dict, json_path: Path):
    """Add figure from new content format"""
    image_number = str(item.get("ImageNumber", "")).strip()
    path_text = str(item.get("Path", "")).strip()
    prompt = str(item.get("Prompt", "")).strip()
    title = str(item.get("Title", "")).strip()

    # Use Caption if available, otherwise fall back to Title
    caption_text = item.get("Title", "").strip() or title

    image_path = _resolve_path(path_text, json_path) if path_text else None

    try:
        width_cm = float(item.get("WidthCm", MAX_FIGURE_WIDTH_CM))
    except Exception:
        width_cm = MAX_FIGURE_WIDTH_CM
    width_cm = max(1.0, min(width_cm, MAX_FIGURE_WIDTH_CM))

    if image_path is not None and image_path.is_file():
        paragraph = _para(doc, align=WD_ALIGN_PARAGRAPH.CENTER, sb=6, sa=2)
        paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
    else:
        # Image not generated yet → show ONLY the clean prompt text, e.g.
        #   create an image "A CAD model of ..."
        # NOT the internal wrapper [PROMPT UNTUK AI GAMBAR: ...]. The user
        # copies this prompt straight into an image generator.
        prompt_body = _clean_image_prompt(prompt) if prompt else f"Figure {image_number} not found"
        # Truncate long prompts to prevent overflow in DOCX
        if len(prompt_body) > 300:
            prompt_body = prompt_body[:297] + "..."
        _add_prompt_box_with_text(doc, prompt_body)

    # Add caption using title or prompt
    if image_number and caption_text:
        caption = _para(doc, style_id="figure caption", align=WD_ALIGN_PARAGRAPH.CENTER)
        _append_rich_text(caption, f"Fig. {image_number}. {caption_text}".strip())


def _strip_math_delimiters(formula: str) -> str:
    """Strip surrounding $/$$/\[...\]/\(...\) delimiters from a formula string."""
    s = formula.strip()
    if s.startswith("$$") and s.endswith("$$") and len(s) >= 4:
        s = s[2:-2].strip()
    elif s.startswith("$") and s.endswith("$") and len(s) >= 2:
        s = s[1:-1].strip()
    if s.startswith("\\[") and s.endswith("\\]") and len(s) >= 4:
        s = s[2:-2].strip()
    if s.startswith("\\(") and s.endswith("\\)") and len(s) >= 4:
        s = s[2:-2].strip()
    return s


def _add_equation_from_content(doc: Document, item: dict):
    """Add equation from new content format"""
    formula_number = str(item.get("FormulaNumber", "")).strip()
    # Support 'text', 'latex', and 'formula' keys
    raw_formula = (
        item.get("formula")
        or item.get("text")
        or item.get("latex")
        or ""
    )
    formula_text = _strip_math_delimiters(str(raw_formula))

    if formula_text:
        _add_equation_line(doc, formula_text, formula_number if formula_number else None)


def _add_table_from_content(doc: Document, item: dict):
    """Add table from new content format"""
    table_number = str(item.get("TableNumber", "")).strip()
    title = str(item.get("Title", "")).strip()
    headers = list(item.get("Headers", []))
    rows = list(item.get("Rows", []))

    if not headers:
        return

    # Add table caption
    caption = _para(doc, style_id="table head")
    label = f"TABLE {_roman(table_number)}" if table_number else "TABLE"
    text = f"{label}. {title}" if title else label
    _append_rich_text(caption, text)

    # Create table
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders_match_template(table)
    # Constrain to column width (2-col layout)
    _constrain_table_width(table, {"columns": 2})

    # Add headers
    for column_index, value in enumerate(headers):
        cell = table.rows[0].cells[column_index]
        _set_horizontal_cell_borders(cell, top=True, bottom=True)
        cell.text = ""
        paragraph = cell.paragraphs[0]
        _style_cell_paragraph(paragraph, "table col head")
        _append_rich_text(paragraph, str(value))
        for run in paragraph.runs:
            run.bold = True

    # Add rows
    for row_index, row_data in enumerate(rows, start=1):
        is_last_row = row_index == len(rows)
        for column_index, value in enumerate(row_data):
            if column_index >= len(headers):
                break
            cell = table.rows[row_index].cells[column_index]
            _set_horizontal_cell_borders(cell, top=False, bottom=is_last_row)
            cell.text = ""
            paragraph = cell.paragraphs[0]
            _style_cell_paragraph(paragraph, "table copy")
            _append_rich_text(paragraph, str(value))

    _para(doc, sa=4)


def _add_prompt_box_with_text(doc: Document, text: str):
    """Add a prompt box with custom text"""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Normal Table"
    _set_table_borders_match_template(table)
    cell = table.cell(0, 0)
    _set_full_cell_borders(cell)
    # Enable word wrap so long prompts wrap inside the cell
    tblPr = table._tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        table._tbl.append(tblPr)
    tblLayout = OxmlElement('w:tblLayout')
    tblLayout.set(qn('w:type'), 'autofit')
    tblPr.append(tblLayout)
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcW = OxmlElement('w:tcW')
    tcW.set(qn('w:type'), 'auto')
    tcPr.append(tcW)
    vAlign = OxmlElement('w:vAlign')
    vAlign.set(qn('w:val'), 'top')
    tcPr.append(vAlign)
    paragraph = cell.paragraphs[0]
    _set_para_style(paragraph, "Body Text")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _append_rich_text(paragraph, text)
    for extra_paragraph in cell.paragraphs[1:]:
        for run in extra_paragraph.runs:
            run.clear()
    return table


def _render_sections_legacy(doc: Document, config: dict, json_path: Path):
    """Render sections in the legacy sections array format"""
    sections = config.get("sections", [])

    for section in sections:
        # Add section heading
        section_number = str(section.get("number", "")).strip()
        section_title = str(section.get("title", "")).strip().upper()

        if section_number:
            heading_text = f"{_roman(section_number)}. {section_title}"
        else:
            heading_text = section_title

        _add_section_heading(doc, heading_text)

        # Add section content (handle both string and array)
        content = section.get("content", "")
        if isinstance(content, str) and content.strip():
            _body_paragraphs(doc, content.strip())
        elif isinstance(content, list):
            # Handle array of content items at section level
            for item in content:
                if isinstance(item, str):
                    _body_paragraphs(doc, item.strip())
                elif isinstance(item, dict):
                    _render_content_item(doc, item, json_path)

        # Add subsections
        subsections = section.get("subsections", [])
        for subsection in subsections:
            _render_subsection(doc, subsection, json_path)


def _render_sections(doc: Document, config: dict, json_path: Path):
    """Render sections in the new format with direct section keys"""
    # Look for direct section keys (section1, section2, etc.)
    section_keys = []
    for key in config.keys():
        if key.startswith("section") and key.replace("section", "").isdigit():
            section_keys.append(key)

    # Sort section keys numerically
    section_keys.sort(key=lambda x: int(x.replace("section", "")))

    for section_key in section_keys:
        section = config[section_key]

        # Add section heading
        section_number = str(section.get("number", "")).strip()
        # Derive section number from key when "number" field is absent (e.g. "section1" -> "1")
        if not section_number:
            num_part = section_key.replace("section", "")
            if num_part.isdigit():
                section_number = num_part
        section_title = str(section.get("title", "")).strip().upper()

        if section_number:
            heading_text = f"{_roman(section_number)}. {section_title}"
        else:
            heading_text = section_title

        _add_section_heading(doc, heading_text)

        # Add section content (handle both string and array)
        content = section.get("content", "")
        if isinstance(content, str) and content.strip():
            _body_paragraphs(doc, content.strip())
        elif isinstance(content, list):
            # Handle array of content items at section level
            for item in content:
                if isinstance(item, str):
                    _body_paragraphs(doc, item.strip())
                elif isinstance(item, dict):
                    _render_content_item(doc, item, json_path)

        # Collect subsection keys in insertion order.
        # Support old pattern: sub2a, sub3b  (starts with "sub", digits+alpha after)
        # Support new pattern: section2a, section3b  (starts with "section", ends digit+alpha)
        subsection_keys = [
            key
            for key in section.keys()
            if (key.startswith("sub") and len(key) > 3 and key[3:].isalnum())
            or re.match(r"^section\d+[a-z]+$", key)
        ]
        for key in subsection_keys:
            _render_subsection(doc, section[key], json_path, sub_key=key)


def _render_subsection(doc: Document, subsection: dict, json_path: Path, sub_key: str = ""):
    """Render a subsection with mixed content types"""
    subsection_letter = str(subsection.get("letter", "")).strip()
    # Derive letter from sub_key when "letter" field is absent.
    # Handles both old style (sub2a -> A) and new style (section2a -> A).
    if not subsection_letter and sub_key:
        m = re.match(r"^(?:sub|section)\d+([a-z]+)$", sub_key)
        if m:
            subsection_letter = m.group(1).upper()
    subsection_title = str(subsection.get("title", "")).strip()

    # Add subsection heading
    if subsection_letter and subsection_title:
        heading_text = f"{subsection_letter}. {subsection_title}"
    elif subsection_title:
        heading_text = subsection_title
    else:
        heading_text = ""

    if heading_text:
        _add_subsection_heading(doc, heading_text)

    # Render content items



    content_items = subsection.get("content", [])
    if isinstance(content_items, list):
        for item in content_items:
            _render_content_item(doc, item, json_path)
    elif isinstance(content_items, str):
        # If content is a string, treat it as text
        if content_items.strip():
            _body_paragraphs(doc, content_items.strip())


def _default_output_path(config: dict, json_path: Path) -> Path:
    return json_path.parent / f"{json_path.stem}.docx"


def build_document(
    json_path: Path = JSON_PATH,
    output_path: Path | None = None,
    template_path: Path = TEMPLATE_PATH,

) -> Path:
    config = json.loads(Path(json_path).read_text(encoding="utf-8"))
    final_output = (
        Path(output_path) if output_path else _default_output_path(config, Path(json_path))
    )
    doc = Document()
    _inject_template_styles(doc, Path(template_path))
    _clear_document_body(doc)
    _setup_main_sectpr(doc)
    _add_title(doc, config)
    _embed_sectpr(
        doc, _build_sectpr(1, 36.0, 27.0, 72.0, 44.65, 44.65, title_pg=True), style_id="Author"

    )
    _add_authors(doc, config)
    _embed_sectpr(doc, _build_sectpr(3, 36.0, 22.5, 72.0, 44.65, 44.65))

    _embed_sectpr(doc, _build_sectpr(3, 36.0, 22.5, 72.0, 44.65, 44.65))
    _add_abstracts(doc, config)

    # Detect format and render content accordingly
    # Check for new format with direct section keys (section1, section2, etc.)
    has_direct_sections = any(
        key.startswith("section") and key.replace("section", "").isdigit() for key in config.keys()
    )
    # Also check for legacy sections array format
    has_sections_array = "sections" in config and isinstance(config["sections"], list)

    if has_direct_sections:
        # New format with direct section keys
        _render_sections(doc, config, Path(json_path))
    elif has_sections_array:
        # Legacy new format with sections array
        _render_sections_legacy(doc, config, Path(json_path))
    else:
        # Legacy JTM format
        for item in config.get("Items", []):
            _render_item(doc, item, Path(json_path))

    _add_references(doc, config)
    _embed_sectpr(doc, _build_sectpr(2, 18.0, 54.0, 72.0, 45.35, 45.35))

    # Aktifkan First Page Different di section 0 supaya First Page Footer
    # unik (match template IEEE original yang punya footerReference type="first").
    # python-docx auto-create footer part + relationships ketika di-akses.
    if doc.sections:
        section0 = doc.sections[0]
        section0.different_first_page_header_footer = True
        _ = section0.first_page_footer.paragraphs  # trigger creation

    final_output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(final_output))
    return final_output


def build_pdf(json_path: Path, pdf_path: Path, template_path=None) -> Path:
    """Build a PDF for this journal template from a paper JSON.

    Calls build_document() to produce a .docx, then converts to .pdf
    via LibreOffice headless.  Final PDF is written to ``pdf_path``.
    """
    from ._render_pdf import build_pdf_from_builder
    return build_pdf_from_builder(build_document, json_path, pdf_path, template_path)

def _run_part_scripts(base_dir: Path):
    """Run all part scripts to generate JSON files"""
    import subprocess

    part_scripts = ["gen2jsonID.py", "gen2jsonEN.py"]

    print("No JSON files found. Running part scripts to generate JSON...")

    for script in part_scripts:
        script_path = base_dir / script
        if script_path.exists():
            print(f"Running {script}...")
            try:
                result = subprocess.run(
                    [sys.executable, str(script_path)],
                    cwd=str(base_dir),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                if result.returncode == 0:
                    print(f"[OK] {script} completed successfully")
                    if result.stdout.strip():
                        print(f"   Output: {result.stdout.strip()}")
                else:
                    print(f"[ERR] {script} failed: {result.stderr.strip()}")
            except Exception as e:
                print(f"[ERR] Error running {script}: {e}")
        else:
            print(f"[ERR] {script} not found")

    print()


def main():
    base_dir = Path(__file__).parent

    if len(sys.argv) >= 2:
        # Mode: generate satu file
        json_arg = Path(sys.argv[1])
        output_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
        template_arg = Path(sys.argv[3]) if len(sys.argv) >= 4 else TEMPLATE_PATH

        if not json_arg.exists():
            print(f"[ERR] File not found: {json_arg}")
            return

        result = build_document(json_arg, output_arg, template_arg)
        print(f"[OK] Generated: {result.name}")
    else:
        # Mode: generate semua JSON di folder
        print("Generating all IEEE DOCX files...")

        # Cari semua file .json di folder base
        json_files = list(base_dir.glob("*.json"))

        if not json_files:
            # Auto-run part scripts if no JSON files found
            _run_part_scripts(base_dir)

            # Check again for JSON files
            json_files = list(base_dir.glob("*.json"))

            if not json_files:
                print("[ERR] No JSON files found in directory after running part scripts")
                return

        for json_path in sorted(json_files):
            # Skip file yang bukan format JSON yang valid
            if json_path.name.lower() in ["package.json", "tsconfig.json", "settings.json"]:
                continue

            try:
                # Validasi JSON dengan membaca sedikit content
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Cek apakah JSON memiliki struktur yang diharapkan
                if not isinstance(data, dict):
                    print(f"[ERR] Skip: {json_path.name} - Invalid JSON structure")
                    continue

                # Generate DOCX dengan nama IEEE_output.docx (untuk batch_audit.sh)
                # kalau JSON-nya _template.json, output ke IEEE_output.docx
                if json_path.stem == "_template":
                    output_arg = json_path.parent / "IEEE_output.docx"
                    output_path = build_document(json_path, output_path=output_arg)
                else:
                    output_path = build_document(json_path)
                print(f"[OK] Generated: {output_path.name}")

            except json.JSONDecodeError as e:
                print(f"[ERR] Skip: {json_path.name} - Invalid JSON: {e}")
            except Exception as e:
                print(f"[ERR] Error: {json_path.name} - {e}")

        print("\nDone!")


def _set_table_borders_match_template(table) -> None:
    """Set border tabel sesuai pattern template original IEEE: PARTIAL.

    IEEE template pakai top + bottom + insideH + insideV (no left/right).
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    tbl_borders = tbl_pr.find(qn("w:tblBorders"))
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    visible_sides = {"top", "bottom", "insideH", "insideV"}
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tbl_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tbl_borders.append(el)
        if edge in visible_sides:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")
        else:
            el.set(qn("w:val"), "nil")
            el.set(qn("w:sz"), "0")


if __name__ == "__main__":
    import json
    import sys

    main()
