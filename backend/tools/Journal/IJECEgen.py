"""
IJECEgen.py - Generator DOCX gaya International Journal of Electrical
and Computer Engineering (IJECE) berdasarkan template IJECE.docx.

Pakai dokumen asli IJECE.docx sebagai base (paste keep formatting):
- Copy template -> output
- Kosongkan body (paragraf + tabel) tapi pertahankan sectPr, headers,
  footers, styles, numbering, theme, fontTable.
- Generate ulang isi dari _template.json mengikuti format hasil
  _analyse.py.

Format ringkas (hasil analisa _analyse.py terhadap IJECE.docx):
- Page A4 11907x16840 tw, 1 kolom, col_space=720tw
- Margin top=1418 bot=1418 left=1701 right=1418, header=1134 footer=1134
- titlePg=YES (header first/even/default berbeda)
- Body universal Times New Roman walau theme major=Cambria minor=Calibri
- Title: 16pt bold center
- Authors: 10pt bold center + superscript affiliation
- Affiliations: 8pt center + superscript number
- Abstract block: heading "Abstract" 10pt bold + isi 9pt italic justify
- Keywords block: 9pt italic justify
- Section heading: "1. INTRODUCTION (10 PT)" bold uppercase arabic+dot 10pt
- Subsection heading: "3.1.  Sub section" bold 10pt
- SubSubsection heading: "3.2.1. Subsub section" italic 10pt
- Body: TNR 10pt justify, ind_firstLine=720tw
- Figure caption: center "Figure N. <judul>"
- Table caption: center "Table N. <judul>" DI ATAS tabel
- Table borders: top double + bottom single (three-line variant)
- Equation: center, label "(N)" rata kanan
- References: "REFERENCES" bold + list 8pt
"""

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from lxml import etree

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "IJECE.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "IJECE_output.docx"

# ============================================================
# KONFIG FORMAT (hasil _analyse.py)
# ============================================================
CFG = {
    # Page A4 portrait
    "page_width_tw": 11907,
    "page_height_tw": 16840,
    "margin_top_tw": 1418,
    "margin_bottom_tw": 1418,
    "margin_left_tw": 1701,
    "margin_right_tw": 1418,
    "margin_gutter_tw": 0,
    "header_distance_tw": 1134,
    "footer_distance_tw": 1134,
    "columns": 1,
    "col_width_cm": 15.5,
    "col_space_tw": 720,
    # Fonts: IJECE menggunakan Times New Roman di body
    "font_body": "Times New Roman",
    "font_title": "Times New Roman",
    "font_heading": "Times New Roman",
    "font_caption": "Times New Roman",
    "font_reference": "Times New Roman",
    # Sizes (pt)
    "size_title": 16,  # Paper's title
    "size_body": 10,  # IJECE body 10pt
    "size_author": 10,  # Author names
    "size_affil": 8,  # Affiliation
    "size_abstract_label": 10,
    "size_abstract": 9,
    "size_keywords": 9,
    "size_heading1": 10,  # Section heading
    "size_heading2": 10,  # Subsection
    "size_heading3": 10,  # Subsubsection
    "size_caption": 9,
    "size_reference": 8,
    "size_header": 9,
    "size_footer": 9,
    # Heading numbering: arabic dot ("1.", "2.")
    "section_heading_format": "arabic_dot",
    "section_heading_upper": True,
    # Figure / Table prefix English
    "fig_prefix": "Figure",
    "tbl_prefix": "Table",
    # Tabel border = three-line (top double + bottom single)
    "table_borders": "three_line_double_top",
    # Line spacing body
    "line_spacing_body": 240,
    "line_spacing_rule": "auto",
    # Indent body
    "first_line_indent_tw": 720,
    # Reference
    "ref_left_indent_tw": 426,
    "ref_hanging_indent_tw": 426,
    "ref_after_pt": 0,
}

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XSL_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL"),
    BASE / "MML2OMML.XSL",
    BASE.parent / "MML2OMML.XSL",
    BASE.parent / "template" / "MML2OMML.XSL",
]
_XSLT = None

def _clean_latex(text):
    """Strip inline LaTeX markers dari text."""
    if not isinstance(text, str) or not text.strip():
        return text if isinstance(text, str) else ""
    import re as _re
    text = _re.sub(r'\$([^$]+)\$', r'\1', text)
    text = _re.sub(r'\\mathrm\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\mathbf\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\hat\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\vec\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\overline\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\sqrt\{([^}]*)\}', r'sqrt(\1)', text)
    text = _re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1/\2)', text)
    text = _re.sub(r'\\left[(\[{]', '(', text)
    text = _re.sub(r'\\right[)\]]', ')', text)
    text = _re.sub(r'\\begin\{cases\}', '', text)
    text = _re.sub(r'\\end\{cases\}', '', text)
    text = _re.sub(r'\\approx', chr(8776), text)
    text = _re.sub(r'\\times', chr(215), text)
    text = _re.sub(r'\\cdot', chr(183), text)
    text = _re.sub(r'\\quad', ' ', text)
    text = _re.sub(r'\\qquad', '  ', text)
    text = _re.sub(r'\\infty', chr(8734), text)
    text = _re.sub(r'\\circ', chr(176), text)
    text = _re.sub(r'\\alpha', chr(945), text)
    text = _re.sub(r'\\beta', chr(946), text)
    text = _re.sub(r'\\gamma', chr(947), text)
    text = _re.sub(r'\\theta', chr(952), text)
    text = _re.sub(r'\\lambda', chr(955), text)
    text = _re.sub(r'\\sigma', chr(963), text)
    text = _re.sub(r'\\omega', chr(969), text)
    text = _re.sub(r'\\pi', chr(960), text)
    text = _re.sub(r'\\mu', chr(956), text)
    text = _re.sub(r'\\Delta', chr(916), text)
    text = _re.sub(r'\\partial', chr(8706), text)
    text = _re.sub(r'[_^]\{([^}]*)\}', r'\1', text)
    # Convert bare subscript/superscript to Unicode
    text = re.sub(r'_([0-9])', lambda m: '₀₁₂₃₄₅₆₇₈₉'[int(m.group(1))], text)
    text = re.sub(r'\^([0-9])', lambda m: '⁰¹²³⁴⁵⁶⁷⁸⁹'[int(m.group(1))], text)
    # LaTeX spacing → remove or space
    text = re.sub(r'\\;', '', text)
    text = re.sub(r'\\,', '', text)
    text = re.sub(r'\\:', '', text)
    text = re.sub(r'\\!', '', text)
    # Math function names → preserve content
    text = re.sub(r'\\cos\^\{(-?\d+)\}', r'cos\1', text)
    text = re.sub(r'\\cos\^(-?\d+)', r'cos\1', text)
    text = re.sub(r'\\cos\\b', 'cos', text)
    text = re.sub(r'\\sin\^\{(-?\d+)\}', r'sin\1', text)
    text = re.sub(r'\\sin\^(-?\d+)', r'sin\1', text)
    text = re.sub(r'\\sin\\b', 'sin', text)
    text = re.sub(r'\\tan\^\{(-?\d+)\}', r'tan\1', text)
    text = re.sub(r'\\tan\^(-?\d+)', r'tan\1', text)
    text = re.sub(r'\\tan\\b', 'tan', text)
    text = re.sub(r'\\log\^\{(-?\d+)\}', r'log\1', text)
    text = re.sub(r'\\log\^(-?\d+)', r'log\1', text)
    text = re.sub(r'\\log\\b', 'log', text)
    text = re.sub(r'\\exp\^\{(-?\d+)\}', r'exp\1', text)
    text = re.sub(r'\\exp\\b', 'exp', text)
    text = re.sub(r'\\max\\b', 'max', text)
    text = re.sub(r'\\min\\b', 'min', text)
    text = re.sub(r'\\lim\\b', 'lim', text)
    text = re.sub(r'\\det\\b', 'det', text)
    text = re.sub(r'\\operatorname\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\[a-zA-Z]+', '', text)
    text = re.sub(r'[{}]', '', text)
    # Strip any remaining stray $ (unmatched math delimiters)
    text = re.sub(r'\$', '', text)
    return text.strip()

def _postprocess_clean_latex(doc):
    """Walk all paragraphs and clean LaTeX from run text in-place."""
    import re as _re
    for para in doc.paragraphs:
        for run in para.runs:
            if run.text and _re.search(r'\\[a-zA-Z]|[$]', run.text):
                run.text = _clean_latex(run.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        if run.text and _re.search(r'\\[a-zA-Z]|[$]', run.text):
                            run.text = _clean_latex(run.text)
def _append_inline_math(paragraph, latex):
    """Render LaTeX into the paragraph. Prefer native Word OMML (real equation
    objects); fall back to sanitized unicode text if conversion is unavailable.
    Return True so the caller does not fall back to raw rendering (which leaks)."""
    if not latex:
        return False
    # Native OMML path first (matches IEEEgen fidelity).
    try:
        from _math_omml import append_omml_math as _omml
        if _omml(paragraph, latex):
            return True
    except Exception:
        pass
    import re as _re

    s = str(latex).strip()
    SYMBOLS = {
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\delta": "δ",
        r"\epsilon": "ε",
        r"\theta": "θ",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\pi": "π",
        r"\sigma": "σ",
        r"\tau": "τ",
        r"\phi": "φ",
        r"\omega": "ω",
        r"\sum": "∑",
        r"\prod": "∏",
        r"\int": "∫",
        r"\infty": "∞",
        r"\pm": "±",
        r"\times": "×",
        r"\cdot": "·",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\neq": "≠",
        r"\approx": "≈",
        r"\to": "→",
        r"\dots": "…",
        r"\ldots": "…",
        r"\quad": " ",
        r"\,": " ",
        r"\;": " ",
        r"\:": " ",
        r"\!": "",
        r"\left": "",
        r"\right": "",
    }
    for k, v in SYMBOLS.items():
        s = s.replace(k, v)
    s = _re.sub(r"\\(mathrm|mathbf|mathit|text|textbf|textit|operatorname)\{([^{}]*)\}", r"\2", s)
    s = _re.sub(r"\\(vec|hat|bar|tilde|dot|ddot)\{([^{}]*)\}", r"\2", s)
    s = _re.sub(r"_\{([^{}]*)\}", r"_\1", s)
    s = _re.sub(r"\^\{([^{}]*)\}", r"^\1", s)
    while True:
        new_s = _re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", s)
        if new_s == s:
            break
        s = new_s
    s = _re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "").replace("$", "")
    paragraph.add_run(s)
    return True

def _set_ai_prompt_color_red(doc):
    """Post-process output DOCX:
    1. Set warna text MERAH untuk paragraf prompt AI gambar.
    2. Set border tabel data tegas (single/sz=4) supaya keliatan di Word.
    Idempotent dan aman dipanggil sebelum doc.save()."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import RGBColor

    RED = RGBColor(0xFF, 0x00, 0x00)

    def _color_prompt(p):
        text = p.text or ""
        if "[PROMPT UNTUK AI GAMBAR" in text or "[PROMPT AI GAMBAR" in text:
            for r in p.runs:
                try:
                    r.font.color.rgb = RED
                except Exception:
                    pass

    for p in doc.paragraphs:
        _color_prompt(p)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _color_prompt(p)

    # Set border tabel data (skip layout 1x1, 1xN equation)
    for t in doc.tables:
        rows = t.rows
        if len(rows) < 2 or len(rows[0].cells) < 2:
            continue
        header_text = "".join((c.text or "").strip() for c in rows[0].cells)
        if not header_text:
            continue
        tbl = t._element
        tblPr = tbl.find(qn("w:tblPr"))
        if tblPr is None:
            tblPr = OxmlElement("w:tblPr")
            tbl.insert(0, tblPr)
        borders = tblPr.find(qn("w:tblBorders"))
        if borders is None:
            borders = OxmlElement("w:tblBorders")
            tblPr.append(borders)
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = borders.find(qn(f"w:{side}"))
            if el is None:
                el = OxmlElement(f"w:{side}")
                borders.append(el)
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")

def load_json():
    with open(TEMPLATE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def set_run_font(run, font_name=None, size_pt=None, bold=None, italic=None, color=None):
    if font_name:
        run.font.name = font_name
        rpr = run._r.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.insert(0, rfonts)
        rfonts.set(qn("w:ascii"), font_name)
        rfonts.set(qn("w:hAnsi"), font_name)
        rfonts.set(qn("w:eastAsia"), font_name)
        rfonts.set(qn("w:cs"), font_name)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
        rpr = run._r.get_or_add_rPr()
        szcs = rpr.find(qn("w:szCs"))
        if szcs is None:
            szcs = OxmlElement("w:szCs")
            rpr.append(szcs)
        szcs.set(qn("w:val"), str(int(size_pt * 2)))
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor(*color) if isinstance(color, tuple) else color

def set_paragraph_spacing(paragraph, before=None, after=None, line=None, line_rule=None):
    pf = paragraph.paragraph_format
    if before is not None:
        pf.space_before = Pt(before)
    if after is not None:
        pf.space_after = Pt(after)
    if line is not None:
        ppr = paragraph._p.get_or_add_pPr()
        spacing = ppr.find(qn("w:spacing"))
        if spacing is None:
            spacing = OxmlElement("w:spacing")
            ppr.append(spacing)
        spacing.set(qn("w:line"), str(line))
        if line_rule:
            spacing.set(qn("w:lineRule"), line_rule)

def set_paragraph_indent(paragraph, left=None, right=None, first_line=None, hanging=None):
    ppr = paragraph._p.get_or_add_pPr()
    ind = ppr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        ppr.append(ind)
    if left is not None:
        ind.set(qn("w:left"), str(left))
    if right is not None:
        ind.set(qn("w:right"), str(right))
    if first_line is not None:
        ind.set(qn("w:firstLine"), str(first_line))
    if hanging is not None:
        ind.set(qn("w:hanging"), str(hanging))

def clear_body(doc):
    """Hapus seluruh paragraf & tabel pada body, sisakan sectPr akhir."""
    body = doc._element.body
    for child in list(body):
        if child.tag in (qn("w:p"), qn("w:tbl")):
            body.remove(child)

def add_empty_para(doc, line=240):
    p = doc.add_paragraph()
    set_paragraph_spacing(p, before=0, after=0, line=line, line_rule="auto")
    return p

def _normalize_text(text: str) -> str:
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
    text = re.sub(r'\\\\n(?![a-z])', '\n', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\b\1\\b", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+?)\*", r"\\i\1\\i", text)
    return text

def _append_rich_text(
    paragraph, text: str, font_name=None, size_pt=None, base_bold=False, base_italic=False
):
    fn = font_name or CFG["font_body"]
    sz = size_pt if size_pt is not None else CFG["size_body"]
    normalized = _normalize_text(text)
    bold = base_bold
    italic = base_italic
    buffer = []
    index = 0

    def flush():
        nonlocal buffer
        content = "".join(buffer)
        buffer = []
        if content:
            run = paragraph.add_run(content)
            set_run_font(run, font_name=fn, size_pt=sz, bold=bold, italic=italic)

    while index < len(normalized):
        char = normalized[index]
        if char == "\n":
            flush()
            run = paragraph.add_run()
            run.add_break()
            index += 1
            continue
        if char == "\\" and index + 1 < len(normalized):
            cmd = normalized[index + 1]
            if cmd == "\\":
                buffer.append("\\")
                index += 2
                continue
            if cmd == "b":
                flush()
                bold = not bold
                index += 2
                continue
            if cmd == "i":
                flush()
                italic = not italic
                index += 2
                continue
        if char == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                flush()
                formula = normalized[index + 1 : closing]
                if formula:
                    if not _append_inline_math(paragraph, formula):
                        run = paragraph.add_run(formula)
                        set_run_font(run, font_name=fn, size_pt=sz, italic=True)
                index = closing + 1
                continue
        buffer.append(char)
        index += 1
    flush()

# ============================================================
# CONTENT GENERATORS
# ============================================================

def add_title(doc, data):
    title_text = data.get("title", "Paper Title Goes Here")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=0, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(title_text)
    set_run_font(run, font_name=CFG["font_title"], size_pt=CFG["size_title"], bold=True)

def add_authors(doc, data):
    authors = data.get("authors", [])
    if not authors:
        authors = [
            {
                "name": "Author Name",
                "affiliation": "Department, University",
                "location": "City, Country",
                "email": "author@email.ac.id",
            }
        ]

    # Baris nama gabungan, semua bold + superscript afiliasi
    p_names = doc.add_paragraph()
    p_names.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_names, before=12, after=0, line=240, line_rule="auto")
    set_paragraph_indent(p_names, first_line=0)

    for i, author in enumerate(authors):
        name = author.get("name", "Author Name")
        if i > 0:
            sep = ", " if i < len(authors) - 1 else ", "
            r = p_names.add_run(sep)
            set_run_font(r, font_name=CFG["font_body"], size_pt=CFG["size_author"], bold=True)
        run = p_names.add_run(name)
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_author"], bold=True)
        run_sup = p_names.add_run(str(i + 1))
        set_run_font(run_sup, font_name=CFG["font_body"], size_pt=CFG["size_author"], bold=True)
        run_sup.font.superscript = True

    # Afiliasi tiap author (8pt, superscript number, italic agak halus)
    for i, author in enumerate(authors):
        affiliation = author.get("affiliation", "")
        location = author.get("location", "")
        email = author.get("email", "")
        parts = [s for s in [affiliation, location] if s]
        if not parts and not email:
            continue
        p_aff = doc.add_paragraph()
        p_aff.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p_aff, before=0, after=0, line=240, line_rule="auto")
        set_paragraph_indent(p_aff, first_line=0)
        r_sup = p_aff.add_run(str(i + 1))
        set_run_font(r_sup, font_name=CFG["font_body"], size_pt=CFG["size_affil"])
        r_sup.font.superscript = True
        aff_text = ", ".join(parts)
        r_aff = p_aff.add_run(aff_text)
        set_run_font(r_aff, font_name=CFG["font_body"], size_pt=CFG["size_affil"])
        if email:
            r_email = p_aff.add_run(f" (email: {email})")
            set_run_font(
                r_email, font_name=CFG["font_body"], size_pt=CFG["size_affil"], italic=True
            )

def add_abstract(doc, data):
    add_empty_para(doc)

    # Heading "Abstract"
    p_label = doc.add_paragraph()
    p_label.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p_label, before=12, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p_label, first_line=0)
    run = p_label.add_run("ABSTRACT")
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_abstract_label"], bold=True)

    # Isi abstract: TNR 9pt italic justify
    abstract_text = data.get(
        "abstract",
        "Abstract text goes here. This section should contain 150-250 words.",
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    _append_rich_text(
        p, abstract_text, font_name=CFG["font_body"], size_pt=CFG["size_abstract"], base_italic=True
    )

def add_keywords(doc, data):
    keywords = data.get("keywords", ["keyword1", "keyword2", "keyword3"])
    if isinstance(keywords, list):
        keywords_text = "; ".join(keywords)
    else:
        keywords_text = str(keywords)

    # Label "Keywords:" bold
    p_label = doc.add_paragraph()
    p_label.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p_label, before=6, after=3, line=240, line_rule="auto")
    set_paragraph_indent(p_label, first_line=0)
    run = p_label.add_run("Keywords:")
    set_run_font(
        run, font_name=CFG["font_body"], size_pt=CFG["size_keywords"], bold=True, italic=True
    )

    # Isi keywords
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=0, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(keywords_text)
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_keywords"])

def add_section_heading(doc, title, section_index):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=12, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    title_text = title.upper() if CFG["section_heading_upper"] else title
    run = p.add_run(f"{section_index}. {title_text}")
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading1"], bold=True)

def add_subsection_heading(doc, title, section_index, sub_index):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=8, after=4, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(f"{section_index}.{sub_index}.  {title}")
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading2"], bold=True)

def add_subsubsection_heading(doc, title, section_index, sub_index, subsub_index):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=6, after=3, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(f"{section_index}.{sub_index}.{subsub_index}. {title}")
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading3"], italic=True)

def add_body_text(doc, text, first_paragraph=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=CFG["line_spacing_body"], line_rule="auto")
    set_paragraph_indent(p, first_line=CFG["first_line_indent_tw"])
    _append_rich_text(p, text, font_name=CFG["font_body"], size_pt=CFG["size_body"])

def _add_dynamic_prompt_placeholder(doc, title, prompt_text):
    """Tambahkan teks placeholder format Prompt AI Dinamis."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=6, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    placeholder = f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt_text}]"
    run = p.add_run(placeholder)
    set_run_font(
        run,
        font_name=CFG["font_body"],
        size_pt=CFG["size_body"],
        italic=True,
        color=(0xFF, 0x00, 0x00),
    )

def add_figure(doc, fig_data):
    image_number = str(fig_data.get("ImageNumber", "1")).strip()
    title = fig_data.get("Title", "Title of the figure")
    path_text = fig_data.get("Path", "").strip()
    prompt_hint = fig_data.get("Prompt", "")

    image_path = None
    if path_text:
        for cand in (Path(path_text), BASE / path_text):
            if cand.is_file():
                image_path = cand
                break

    if image_path and image_path.is_file():
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p_img, before=6, after=3, line=240, line_rule="auto")
        set_paragraph_indent(p_img, first_line=0)
        usable_tw = CFG["page_width_tw"] - CFG["margin_left_tw"] - CFG["margin_right_tw"]
        usable_cm = usable_tw / 567.0
        max_width = min(usable_cm, 14.0)  # Cap prevent overflow
        columns = CFG.get("columns", 1)
        if columns == 2:
            max_width = min((usable_cm / 2) * 0.7, 14.0)
        else:
            max_width = min(usable_cm * 0.5, 14.0)
        run = p_img.add_run()
        run.add_picture(str(image_path), width=Cm(max_width))
    else:
        _add_dynamic_prompt_placeholder(doc, title, prompt_hint)

    # Caption: "Figure N. <judul>" center
    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_cap, before=3, after=8, line=240, line_rule="auto")
    set_paragraph_indent(p_cap, first_line=0)
    r_lbl = p_cap.add_run(f"{CFG['fig_prefix']} {image_number}. ")
    set_run_font(r_lbl, font_name=CFG["font_caption"], size_pt=CFG["size_caption"])
    r_ttl = p_cap.add_run(title)
    set_run_font(r_ttl, font_name=CFG["font_caption"], size_pt=CFG["size_caption"])

def add_formula(doc, formula_data):
    formula_number = str(formula_data.get("FormulaNumber", "")).strip()
    latex = formula_data.get("latex", "E = mc^2").strip()

    cleaned = re.sub(r'\$([^$]+)\$', r'\1', latex)
    cleaned = cleaned.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

    try:
        from latex2mathml.converter import convert as latex2mathml
        from mathml2omml import convert as mathml2omml

        mathml_str = latex2mathml(cleaned)
        omml_str = mathml2omml(mathml_str)

        # Fix mathml2omml bug: groupChrPr incorrectly closed by </m:groupChr>
        omml_str = re.sub(r'(<m:groupChrPr>.*?</m:)groupChr>', r'\1groupChrPr>', omml_str)

        MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
        omml_wrapped = f'<m:oMathPara xmlns:m="{MATH_NS}">{omml_str}</m:oMathPara>'
        oMathPara = etree.fromstring(omml_wrapped)

        body = doc._element.body
        final_sectpr = body.find(qn("w:sectPr"))

        p_elem = etree.Element(qn("w:p"))
        pPr = etree.SubElement(p_elem, qn("w:pPr"))
        jc = etree.SubElement(pPr, qn("w:jc"))
        jc.set(qn("w:val"), "center")
        spacing = etree.SubElement(pPr, qn("w:spacing"))
        spacing.set(qn("w:before"), "120")
        spacing.set(qn("w:after"), "120")
        spacing.set(qn("w:line"), "240")
        spacing.set(qn("w:lineRule"), "auto")
        p_elem.append(oMathPara)

        if formula_number:
            run = etree.SubElement(p_elem, qn("w:r"))
            rPr = etree.SubElement(run, qn("w:rPr"))
            rFonts = etree.SubElement(rPr, qn("w:rFonts"))
            rFonts.set(qn("w:ascii"), "Times New Roman")
            sz = etree.SubElement(rPr, qn("w:sz"))
            sz.set(qn("w:val"), "20")
            t = etree.SubElement(run, qn("w:t"))
            t.set(qn("xml:space"), "preserve")
            t.text = f"    ({formula_number})"

        if final_sectpr is not None:
            final_sectpr.addprevious(p_elem)
        else:
            body.append(p_elem)

    except Exception:
        # Fallback: plain text
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p, before=6, after=6, line=240, line_rule="auto")
        display = cleaned
        if formula_number:
            display = f"{cleaned}    ({formula_number})"
        run = p.add_run(display)
        set_run_font(run, "Cambria Math", CFG["size_body"], italic=True)

def _set_table_borders_three_line(table):
    """Three-line: top double + bottom single + insideH single (header)."""
    tbl = table._tbl
    tbl_pr = tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)

    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is not None:
        tbl_pr.remove(borders)
    borders = OxmlElement("w:tblBorders")

    # top double, bottom single, insideH single
    edge_specs = [
        ("top", "double", "12"),
        ("bottom", "single", "12"),
        ("insideH", "single", "4"),
    ]
    for edge, val, sz in edge_specs:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), val)
        el.set(qn("w:sz"), sz)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)

    for edge in ["left", "right", "insideV"]:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)

    tbl_pr.append(borders)

def add_table(doc, table_data):
    table_number = str(table_data.get("TableNumber", "1")).strip()
    title = table_data.get("Title", "Title of the table")
    headers = table_data.get("Headers", [])
    rows = table_data.get("Rows", [])

    if not headers:
        headers = ["Column 1", "Column 2"]
        rows = [["Data", "Data"]]

    # Title (DI ATAS tabel)
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_title, before=8, after=3, line=240, line_rule="auto")
    set_paragraph_indent(p_title, first_line=0)
    r_lbl = p_title.add_run(f"{CFG['tbl_prefix']} {table_number}. ")
    set_run_font(r_lbl, font_name=CFG["font_caption"], size_pt=CFG["size_caption"])
    r_ttl = p_title.add_run(title)
    set_run_font(r_ttl, font_name=CFG["font_caption"], size_pt=CFG["size_caption"])

    num_cols = len(headers)
    num_rows = len(rows) + 1
    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders_three_line(table)

    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
        set_paragraph_indent(p, first_line=0)
        run = p.add_run(str(header))
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_caption"], bold=True)

    for row_idx, row_data in enumerate(rows):
        for col_idx, value in enumerate(row_data):
            if col_idx >= num_cols:
                break
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
            set_paragraph_indent(p, first_line=0)
            run = p.add_run(_clean_latex(str(value)))
            set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_caption"])

    p_spacer = doc.add_paragraph()
    set_paragraph_spacing(p_spacer, before=0, after=0, line=240, line_rule="auto")
    set_paragraph_indent(p_spacer, first_line=0

)
    # Spacer after table
    p_spacer = doc.add_paragraph()
    set_paragraph_spacing(p_spacer, before=6, after=6)
    p_spacer.add_run(" ").font.size = Pt(1)

def add_references(doc, data):
    ref_data = data.get("references", {})
    if isinstance(ref_data, dict):
        ref_title = ref_data.get("title", "References")
        ref_content = ref_data.get("content", [])
    else:
        ref_title = "References"
        ref_content = list(ref_data) if isinstance(ref_data, list) else []

    # Heading "REFERENCES"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=12, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(ref_title.upper())
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading1"], bold=True)

    if not ref_content:
        ref_content = ["[1] Author, Title, Journal, Year."]

    for ref in ref_content:
        ref_text = ref.get("text", "") if isinstance(ref, dict) else str(ref)
        if not ref_text:
            continue
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        set_paragraph_spacing(p, before=0, after=CFG["ref_after_pt"], line=240, line_rule="auto")
        set_paragraph_indent(
            p, left=CFG["ref_left_indent_tw"], hanging=CFG["ref_hanging_indent_tw"], first_line=None
        )
        _append_rich_text(
            p, ref_text, font_name=CFG["font_reference"], size_pt=CFG["size_reference"]
        )

def process_content_item(doc, item, first_paragraph=False):
    item_id = str(item.get("id", "")).lower()
    if item_id == "text":
        text = item.get("text", "")
        if text:
            add_body_text(doc, text, first_paragraph=first_paragraph)
    elif item_id in ("gambar", "image"):
        add_figure(doc, item)
    elif item_id in ("rumus", "formula"):
        add_formula(doc, item)
    elif item_id in ("tabel", "table"):
        add_table(doc, item)

def process_section(doc, section_data, section_key, section_index):
    if not isinstance(section_data, dict):
        return

    title = section_data.get("title", "")
    if title:
        add_section_heading(doc, title, section_index=section_index)

    content = section_data.get("content", [])
    first_done = False
    if isinstance(content, list):
        for item in content:
            is_first = not first_done
            if isinstance(item, str):
                add_body_text(doc, item, first_paragraph=is_first)
                first_done = True
            elif isinstance(item, dict):
                if str(item.get("id", "")).lower() == "text":
                    process_content_item(doc, item, first_paragraph=is_first)
                    first_done = True
                else:
                    process_content_item(doc, item)
    elif isinstance(content, str) and content.strip():
        add_body_text(doc, content, first_paragraph=True)

    # Subsections (section1a, section2b, dst.)
    subsection_keys = []
    for key in section_data.keys():
        if (
            key.startswith(section_key)
            and len(key) > len(section_key)
            and key[len(section_key) :].isalpha()
        ):
            subsection_keys.append(key)
    subsection_keys.sort()

    for sub_idx, sub_key in enumerate(subsection_keys, start=1):
        sub_data = section_data[sub_key]
        if not isinstance(sub_data, dict):
            continue
        sub_title = sub_data.get("title", "")
        if sub_title:
            add_subsection_heading(doc, sub_title, section_index=section_index, sub_index=sub_idx)

        sub_content = sub_data.get("content", [])
        sub_first_done = False
        if isinstance(sub_content, list):
            for item in sub_content:
                is_first = not sub_first_done
                if isinstance(item, str):
                    add_body_text(doc, item, first_paragraph=is_first)
                    sub_first_done = True
                elif isinstance(item, dict):
                    if str(item.get("id", "")).lower() == "text":
                        process_content_item(doc, item, first_paragraph=is_first)
                        sub_first_done = True
                    else:
                        process_content_item(doc, item)
        elif isinstance(sub_content, str) and sub_content.strip():
            add_body_text(doc, sub_content, first_paragraph=True)

        # Sub-subsections (section3a1, section3a2, dst.)
        subsub_keys = []
        for key in sub_data.keys():
            if (
                key.startswith(sub_key)
                and len(key) > len(sub_key)
                and key[len(sub_key) :].isdigit()
            ):
                subsub_keys.append(key)
        subsub_keys.sort()

        for ss_idx, ss_key in enumerate(subsub_keys, start=1):
            ss_data = sub_data[ss_key]
            if not isinstance(ss_data, dict):
                continue
            ss_title = ss_data.get("title", "")
            if ss_title:
                add_subsubsection_heading(
                    doc,
                    ss_title,
                    section_index=section_index,
                    sub_index=sub_idx,
                    subsub_index=ss_idx,
                )
            ss_content = ss_data.get("content", [])
            ss_first_done = False
            if isinstance(ss_content, list):
                for item in ss_content:
                    is_first = not ss_first_done
                    if isinstance(item, str):
                        add_body_text(doc, item, first_paragraph=is_first)
                        ss_first_done = True
                    elif isinstance(item, dict):
                        if str(item.get("id", "")).lower() == "text":
                            process_content_item(doc, item, first_paragraph=is_first)
                            ss_first_done = True
                        else:
                            process_content_item(doc, item)
            elif isinstance(ss_content, str) and ss_content.strip():
                add_body_text(doc, ss_content, first_paragraph=True)

def ensure_sectpr(doc):
    """Pastikan sectPr akhir punya page-size & margins sesuai analisa."""
    body = doc._element.body
    sectpr = body.find(qn("w:sectPr"))
    if sectpr is None:
        return
    pgsz = sectpr.find(qn("w:pgSz"))
    if pgsz is None:
        pgsz = OxmlElement("w:pgSz")
        sectpr.append(pgsz)
    pgsz.set(qn("w:w"), str(CFG["page_width_tw"]))
    pgsz.set(qn("w:h"), str(CFG["page_height_tw"]))
    pgsz.set(qn("w:orient"), "portrait")

    pgmar = sectpr.find(qn("w:pgMar"))
    if pgmar is None:
        pgmar = OxmlElement("w:pgMar")
        sectpr.append(pgmar)
    pgmar.set(qn("w:top"), str(CFG["margin_top_tw"]))
    pgmar.set(qn("w:right"), str(CFG["margin_right_tw"]))
    pgmar.set(qn("w:bottom"), str(CFG["margin_bottom_tw"]))
    pgmar.set(qn("w:left"), str(CFG["margin_left_tw"]))
    pgmar.set(qn("w:header"), str(CFG["header_distance_tw"]))
    pgmar.set(qn("w:footer"), str(CFG["footer_distance_tw"]))
    pgmar.set(qn("w:gutter"), str(CFG["margin_gutter_tw"]))

# ============================================================
# MAIN
# ============================================================

def generate():
    data = load_json()

    # Copy template asli -> output (paste keep formatting)
    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    # Hapus body content (pertahankan sectPr, headers, footers, styles)
    clear_body(doc)
    ensure_sectpr(doc)

    # Generate content
    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    section_index = 0
    for i in range(1, 20):
        key = f"section{i}"
        if key in data:
            section_index += 1
            process_section(doc, data[key], key, section_index)

    add_references(doc, data)

    _set_ai_prompt_color_red(doc)
    _postprocess_clean_latex(doc)
    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)

if __name__ == "__main__":
    generate()
