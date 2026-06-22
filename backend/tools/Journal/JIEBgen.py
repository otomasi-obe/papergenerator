"""
JIEBgen.py — Generator DOCX untuk Journal of Indonesian Economy and Business (JIEB)
Menggunakan dokumen asli JIEB.docx sebagai base template (paste keep formatting).
Data diambil dari _template.json.
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

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "JIEB.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "JIEB_output.docx"

CFG = {
    "page_width_tw": 11907,
    "page_height_tw": 16840,
    "margin_top_tw": 1701,
    "margin_bottom_tw": 1418,
    "margin_left_tw": 1418,
    "margin_right_tw": 1418,
    "margin_gutter_tw": 0,
    "header_distance_tw": 1077,
    "footer_distance_tw": 1134,
    "columns": 1,
    "col_space_tw": 360,
    "font_body": "Times New Roman",
    "font_title": "Times New Roman",
    "font_heading": "Times New Roman",
    "font_caption": "Times New Roman",
    "font_reference": "Times New Roman",
    "size_title": 14,
    "size_body": 11,
    "size_heading1": 11,
    "size_heading2": 11,
    "size_heading3": 11,
    "size_caption": 11,
    "size_reference": 11,
    "size_header": 10,
    "size_footer": 10,
    "section_heading_format": "arabic_dot",
    "section_heading_upper": False,
    "subsection_format": "arabic_parent_child",
    "fig_prefix": "Figure",
    "tbl_prefix": "Table",
    "tbl_number_format": "arabic",
    "table_borders": "three_line",
    "line_spacing_body": 360,
    "line_spacing_rule": "auto",
    "first_line_indent_tw": 0,
    "ref_hanging_indent_tw": 720,
    "ref_numbering": "none",
    "heading_color": (0x00, 0x70, 0xC0),
    "subheading_color": (0x2E, 0x74, 0xB5),
}

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XSL_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL"),
    BASE / "MML2OMML.XSL",
    BASE.parent / "MML2OMML.XSL",
]
_XSLT = None


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
    """
    JIEB-specific: keep form-submission pages (paragraphs containing inline
    sectPr that carry per-section header/footer references) + final sectPr.
    Only the paper-template content (after the last inline sectPr) is removed
    so the generator can rewrite it from JSON.
    """
    body = doc._element.body
    children = list(body)

    last_inline_sectpr_idx = -1
    for i, child in enumerate(children):
        if child.tag == qn("w:p"):
            p_pr = child.find(qn("w:pPr"))
            if p_pr is not None and p_pr.find(qn("w:sectPr")) is not None:
                last_inline_sectpr_idx = i

    if last_inline_sectpr_idx == -1:
        for child in children:
            if child.tag != qn("w:sectPr"):
                body.remove(child)
        return

    for i, child in enumerate(children):
        if i <= last_inline_sectpr_idx:
            continue
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def add_empty_para(doc):
    p = doc.add_paragraph()
    set_paragraph_spacing(p, before=0, after=0, line=CFG["line_spacing_body"], line_rule="auto")
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
    sz = size_pt or CFG["size_body"]
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


def add_title(doc, data):
    title = data.get("title", "Paper Title Goes Here")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=0, after=120, line=CFG["line_spacing_body"], line_rule="auto")
    run = p.add_run(title)
    set_run_font(run, font_name=CFG["font_title"], size_pt=CFG["size_title"], bold=True)


def add_authors(doc, data):
    authors = data.get("authors", [])
    if not authors:
        authors = [
            {
                "name": "Author Name",
                "affiliation": "Department, University",
                "email": "author@email.ac.id",
            }
        ]

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=120, after=0, line=CFG["line_spacing_body"], line_rule="auto")

    for i, author in enumerate(authors):
        name = author.get("name", "Author Name")
        if i > 0:
            sep = ", " if i < len(authors) - 1 else ", and "
            run = p.add_run(sep)
            set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])

        run = p.add_run(name)
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])

        run_sup = p.add_run(str(i + 1))
        set_run_font(run_sup, font_name=CFG["font_body"], size_pt=CFG["size_body"])
        run_sup.font.superscript = True
        if i == 0:
            run_star = p.add_run("*")
            set_run_font(run_star, font_name=CFG["font_body"], size_pt=CFG["size_body"])
            run_star.font.superscript = True

    for i, author in enumerate(authors):
        affiliation = author.get("affiliation", "")
        location = author.get("location", "")
        email = author.get("email", "")
        parts = [str(i + 1)] + [s for s in [affiliation, location, email] if s]
        if len(parts) > 1:
            p_aff = doc.add_paragraph()
            p_aff.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_paragraph_spacing(
                p_aff, before=0, after=0, line=CFG["line_spacing_body"], line_rule="auto"
            )
            run_sup = p_aff.add_run(parts[0])
            set_run_font(run_sup, font_name=CFG["font_body"], size_pt=CFG["size_body"])
            run_sup.font.superscript = True
            run = p_aff.add_run(" " + ", ".join(parts[1:]))
            set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], italic=True)


def add_abstract(doc, data):
    add_empty_para(doc)

    abstract_text = data.get(
        "abstract",
        "Abstract text goes here. This section should contain 150-250 words summarizing the paper.",
    )

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=120, line=CFG["line_spacing_body"], line_rule="auto")
    run = p.add_run("Abstract: ")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)
    _append_rich_text(p, abstract_text)


def add_keywords(doc, data):
    keywords = data.get("keywords", ["keyword1", "keyword2", "keyword3"])
    if isinstance(keywords, list):
        keywords_text = ", ".join(keywords)
    else:
        keywords_text = str(keywords)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=120, line=CFG["line_spacing_body"], line_rule="auto")

    run = p.add_run("Keywords: ")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True, italic=True)

    run = p.add_run(keywords_text)
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], italic=True)


def _section_number_text(section_index):
    return f"{section_index}."


def _subsection_number_text(section_index, sub_index):
    return f"{section_index}.{sub_index}."


def add_section_heading(doc, title, section_index=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=6, after=3, line=CFG["line_spacing_body"], line_rule="auto")

    if section_index is not None:
        prefix = _section_number_text(section_index) + " "
    else:
        prefix = ""

    run = p.add_run(prefix + title)
    set_run_font(
        run,
        font_name=CFG["font_heading"],
        size_pt=CFG["size_heading1"],
        bold=True,
        color=CFG["heading_color"],
    )


def add_subsection_heading(doc, title, section_index=None, sub_index=None, level=1):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=6, after=3, line=CFG["line_spacing_body"], line_rule="auto")

    if section_index is not None and sub_index is not None:
        prefix = _subsection_number_text(section_index, sub_index) + " "
    else:
        prefix = ""

    run = p.add_run(prefix + title)
    set_run_font(
        run,
        font_name=CFG["font_heading"],
        size_pt=CFG["size_heading2"],
        bold=True,
        italic=True,
        color=CFG["subheading_color"],
    )


def add_body_text(doc, text, first_paragraph=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=CFG["line_spacing_body"], line_rule="auto")
    _append_rich_text(p, text)


def add_figure(doc, fig_data):
    image_number = str(fig_data.get("ImageNumber", "1")).strip()
    title = fig_data.get("Title", "Title of the figure")
    path_text = fig_data.get("Path", "").strip()

    add_empty_para(doc)

    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_cap, before=3, after=6, line=CFG["line_spacing_body"], line_rule="auto")
    run = p_cap.add_run(f"{CFG['fig_prefix']} {image_number}. ")
    set_run_font(run, font_name=CFG["font_caption"], size_pt=CFG["size_caption"], bold=True)
    run = p_cap.add_run(title)
    set_run_font(run, font_name=CFG["font_caption"], size_pt=CFG["size_caption"])

    image_path = None
    if path_text:
        # Try direct path first (handles full/relative paths), then BASE-relative
        for cand in (Path(path_text), BASE / path_text):
            if cand.is_file():
                image_path = cand
                break

    if image_path and image_path.is_file():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p, before=3, after=3, line=CFG["line_spacing_body"], line_rule="auto")
        usable_width_cm = (
            CFG["page_width_tw"] - CFG["margin_left_tw"] - CFG["margin_right_tw"]
        ) / 567.0
        max_width = min(usable_width_cm, 14.0)
        run = p.add_run()
        run.add_picture(str(image_path), width=Cm(max_width))
    else:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p, before=3, after=3, line=CFG["line_spacing_body"], line_rule="auto")
        prompt_text = (
            f"[PROMPT UNTUK AI GAMBAR: Buatkan gambar, diagram, atau ilustrasi teknis "
            f"yang merepresentasikan '{title}'. Pastikan visualnya profesional, "
            f"hitam putih/grayscale, dan cocok untuk publikasi jurnal akademik ilmiah.]"
        )
        run = p.add_run(prompt_text)
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], italic=True)
        run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)

    p_src = doc.add_paragraph()
    p_src.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_src, before=0, after=0, line=CFG["line_spacing_body"], line_rule="auto")
    run = p_src.add_run("Source: The Authors")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])
    run.font.color.rgb = RGBColor(0x2E, 0x74, 0xB5)


def add_formula(doc, formula_data):
    # OMML via shared utility
    import sys
    from pathlib import Path as _Path
    _jdir = _Path(__file__).resolve().parent
    if str(_jdir) not in sys.path:
        sys.path.insert(0, str(_jdir))
    from _formula_omml import add_omml_formula

    latex = str(formula_data.get("latex", formula_data.get("Formula", ""))).strip()
    number = str(formula_data.get("FormulaNumber", "")).strip()
    if not latex:
        return
    add_omml_formula(doc, latex, number, CFG, before_pt=4, after_pt=4,
                     alignment="center", font_body=CFG.get("font_body", "Times New Roman"),
                     size_body=CFG.get("size_body", 10))
def add_table(doc, table_data):
    table_number = str(table_data.get("TableNumber", "1")).strip()
    title = table_data.get("Title", "Title of the table")
    headers = table_data.get("Headers", [])
    rows = table_data.get("Rows", [])

    if not headers:
        headers = ["Column 1", "Column 2"]
        rows = [["Data", "Data"]]

    add_empty_para(doc)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(
        p_title, before=6, after=3, line=CFG["line_spacing_body"], line_rule="auto"
    )
    run = p_title.add_run(f"{CFG['tbl_prefix']} {table_number}. ")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)
    run = p_title.add_run(title)
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])

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
        run = p.add_run(str(header))
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)

    for row_idx, row_data in enumerate(rows):
        for col_idx, value in enumerate(row_data):
            if col_idx >= num_cols:
                break
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _append_rich_text(p, str(value), font_name=CFG["font_body"], size_pt=CFG["size_body"])

    p_src = doc.add_paragraph()
    p_src.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p_src, before=0, after=0, line=CFG["line_spacing_body"], line_rule="auto")
    run = p_src.add_run("Source: The Authors")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])
    run.font.color.rgb = RGBColor(0x2E, 0x74, 0xB5)


def _set_table_borders_three_line(table):
    tbl = table._tbl
    tbl_pr = tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)

    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is not None:
        tbl_pr.remove(borders)
    borders = OxmlElement("w:tblBorders")

    visible_edges = ["top", "bottom", "insideH"]
    hidden_edges = ["left", "right", "insideV"]

    for edge in visible_edges:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)

    for edge in hidden_edges:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)

    tbl_pr.append(borders)


def add_references(doc, data):
    ref_data = data.get("references", {})
    ref_title = ref_data.get("title", "Reference") if isinstance(ref_data, dict) else "Reference"
    ref_content = ref_data.get("content", []) if isinstance(ref_data, dict) else []

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=6, after=3, line=CFG["line_spacing_body"], line_rule="auto")
    run = p.add_run(ref_title)
    set_run_font(
        run,
        font_name=CFG["font_heading"],
        size_pt=CFG["size_heading1"],
        bold=True,
        color=CFG["heading_color"],
    )

    if not ref_content:
        ref_content = ["[1] Author, Title, Journal, Year."]

    for ref in ref_content:
        if isinstance(ref, dict):
            ref_text = ref.get("text", "")
        else:
            ref_text = str(ref)
        if ref_text:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            set_paragraph_spacing(
                p, before=0, after=80, line=CFG["line_spacing_body"], line_rule="auto"
            )
            set_paragraph_indent(
                p, left=CFG["ref_hanging_indent_tw"], hanging=CFG["ref_hanging_indent_tw"]
            )
            _append_rich_text(
                p, ref_text, font_name=CFG["font_reference"], size_pt=CFG["size_reference"]
            )


def process_content_item(doc, item):
    item_id = str(item.get("id", "")).lower()

    if item_id == "text":
        text = item.get("text", "")
        if text:
            add_body_text(doc, text)
    elif item_id == "gambar" or item_id == "image":
        add_figure(doc, item)
    elif item_id == "rumus" or item_id == "formula":
        add_formula(doc, item)
    elif item_id == "tabel" or item_id == "table":
        add_table(doc, item)


def process_section(doc, section_data, section_key, section_index):
    if not isinstance(section_data, dict):
        return

    title = section_data.get("title", "")
    if title:
        add_section_heading(doc, title, section_index=section_index)

    content = section_data.get("content", [])
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                add_body_text(doc, item)
            elif isinstance(item, dict):
                process_content_item(doc, item)
    elif isinstance(content, str) and content.strip():
        add_body_text(doc, content)

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
        if isinstance(sub_data, dict):
            sub_title = sub_data.get("title", "")
            if sub_title:
                add_subsection_heading(
                    doc, sub_title, section_index=section_index, sub_index=sub_idx, level=1
                )

            sub_content = sub_data.get("content", [])
            if isinstance(sub_content, list):
                for item in sub_content:
                    if isinstance(item, str):
                        add_body_text(doc, item)
                    elif isinstance(item, dict):
                        process_content_item(doc, item)
            elif isinstance(sub_content, str) and sub_content.strip():
                add_body_text(doc, sub_content)


def generate():
    data = load_json()

    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    clear_body(doc)

    # Masthead inject
    _inject_masthead_content(doc, data)
    # add_title(doc, data) — replaced by inject
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
    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


if __name__ == "__main__":
    generate()
# --- Hermes patch: masthead no-op ---
def _inject_masthead_content(doc, data):
    """No-op — masthead injection not needed for this template."""
    pass
