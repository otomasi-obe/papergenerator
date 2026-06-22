"""
El-Usrahgen.py — Generator DOCX untuk jurnal El-Usrah: Jurnal Hukum Keluarga
Menggunakan dokumen asli El-Usrah.docx sebagai base template (paste keep formatting).
Data diambil dari _template.json.
"""

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor, Twips

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "El-Usrah.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "El-Usrah_output.docx"

FONT_NAME = "Times New Roman"
FONT_SIZE_BODY = Pt(12)
FONT_SIZE_HEADER = Pt(10)
FONT_SIZE_FOOTER = Pt(12)

PAGE_WIDTH_TW = 9979
PAGE_HEIGHT_TW = 14181
MARGIN_TW = 1134

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XSL_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL"),
    BASE / "MML2OMML.XSL",
    BASE.parent / "MML2OMML.XSL",
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
    text = _re.sub(r'[_^]([a-zA-Z0-9])', r'\1', text)
    text = _re.sub(r'\\[a-zA-Z]+', '', text)
    text = _re.sub(r'[{}]', '', text)
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
            el.set(
                qn("w:val"),
                (
                    "single"
                    if side in ("top", "bottom", "insideH")
                    else (
                        "nil"
                        if side in ("top", "bottom", "insideH")
                        else (
                            "nil"
                            if side in ("top", "bottom", "insideH")
                            else (
                                "nil"
                                if side in ("top", "bottom", "insideH")
                                else (
                                    "nil"
                                    if side in ("top", "bottom", "insideH")
                                    else "nil" if side in ("top", "bottom", "insideH") else "nil"
                                )
                            )
                        )
                    )
                ),
            )
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")


def load_json():
    with open(TEMPLATE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def set_run_font(run, size=FONT_SIZE_BODY, bold=False, italic=False, color=None, superscript=False):
    run.font.name = FONT_NAME
    run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    r = run._element
    rPr = r.find(qn("w:rPr"))
    if rPr is None:
        rPr = parse_xml(f'<w:rPr {nsdecls("w")}></w:rPr>')
        r.insert(0, rPr)
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = parse_xml(
            f'<w:rFonts {nsdecls("w")} w:ascii="{FONT_NAME}" w:hAnsi="{FONT_NAME}" w:eastAsia="{FONT_NAME}" w:cs="{FONT_NAME}"/>'
        )
        rPr.insert(0, rFonts)
    else:
        rFonts.set(qn("w:ascii"), FONT_NAME)
        rFonts.set(qn("w:hAnsi"), FONT_NAME)
        rFonts.set(qn("w:eastAsia"), FONT_NAME)
        rFonts.set(qn("w:cs"), FONT_NAME)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if superscript:
        run.font.superscript = True


def set_paragraph_format(
    para,
    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
    space_before=0,
    space_after=0,
    line_spacing=1.0,
    first_line_indent=None,
    left_indent=None,
    hanging_indent=None,
):
    pf = para.paragraph_format
    pf.alignment = alignment
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line_spacing
    if first_line_indent is not None:
        pf.first_line_indent = Twips(first_line_indent)
    if left_indent is not None:
        pf.left_indent = Twips(left_indent)
    if hanging_indent is not None:
        pf.first_line_indent = Twips(-hanging_indent)
        if left_indent is None:
            pf.left_indent = Twips(hanging_indent)


def add_empty_para(doc, space_after=0):
    p = doc.add_paragraph()
    set_paragraph_format(p, space_after=space_after, line_spacing=1.0)
    run = p.add_run("")
    set_run_font(run)
    return p


def clear_body(doc):
    body = doc.element.body
    children_to_remove = []
    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag in ("p", "tbl"):
            children_to_remove.append(child)
    for child in children_to_remove:
        body.remove(child)


def setup_header_first_page(doc, data):
    section = doc.sections[0]
    section.different_first_page_header_footer = True
    header = section.first_page_header
    for p in header.paragraphs:
        pass


def setup_header_default(doc, data):
    section = doc.sections[0]
    header = section.header
    for p in header.paragraphs:
        pass


def setup_footer_first_page(doc):
    section = doc.sections[0]
    footer = section.first_page_footer
    for p in footer.paragraphs:
        pass


def setup_footer_default(doc):
    section = doc.sections[0]
    footer = section.footer
    for p in footer.paragraphs:
        pass


def add_title(doc, data):
    p = doc.add_paragraph()
    set_paragraph_format(
        p, alignment=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=0, line_spacing=1.0
    )
    run = p.add_run(data.get("title", "Title"))
    set_run_font(run, size=FONT_SIZE_BODY, bold=True)


def add_authors(doc, data):
    authors = data.get("authors", [])
    if not authors:
        return

    affiliations = {}
    aff_counter = 0
    for author in authors:
        aff = author.get("affiliation", "") + ", " + author.get("location", "")
        if aff not in affiliations:
            aff_counter += 1
            affiliations[aff] = str(aff_counter)

    p = doc.add_paragraph()
    set_paragraph_format(
        p, alignment=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=0, line_spacing=1.0
    )
    for i, author in enumerate(authors):
        aff = author.get("affiliation", "") + ", " + author.get("location", "")
        aff_num = affiliations[aff]
        name = author.get("name", "")
        if i > 0:
            run = p.add_run(" ")
            set_run_font(run)
        run = p.add_run(name + ",")
        set_run_font(run)
        run = p.add_run(aff_num)
        set_run_font(run, superscript=True)
        if i < len(authors) - 1:
            pass

    for aff, num in affiliations.items():
        p = doc.add_paragraph()
        set_paragraph_format(
            p, alignment=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=0, line_spacing=1.0
        )
        run = p.add_run(num)
        set_run_font(run, superscript=True)
        run = p.add_run(" " + aff)
        set_run_font(run)

    emails = [a.get("email", "") for a in authors if a.get("email")]
    if emails:
        p = doc.add_paragraph()
        set_paragraph_format(
            p, alignment=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=0, line_spacing=1.0
        )
        run = p.add_run("Email: ")
        set_run_font(run, italic=True)
        run = p.add_run(", ".join(emails))
        set_run_font(run, italic=True)


def add_abstract(doc, data):
    add_empty_para(doc)

    p = doc.add_paragraph()
    set_paragraph_format(
        p, alignment=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=0, line_spacing=1.0
    )
    run = p.add_run("Abstract")
    set_run_font(run, bold=True, italic=True)

    p = doc.add_paragraph()
    set_paragraph_format(
        p, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=0, space_after=0, line_spacing=1.0
    )
    abstract_text = data.get("abstract", "Abstract text goes here.")
    run = p.add_run(abstract_text)
    set_run_font(run, italic=True)


def add_keywords(doc, data):
    keywords = data.get("keywords", [])
    p = doc.add_paragraph()
    set_paragraph_format(
        p, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=0, space_after=0, line_spacing=1.0
    )
    run = p.add_run("Keywords: ")
    set_run_font(run, bold=True, italic=True)
    run = p.add_run(", ".join(keywords) if keywords else "keyword1, keyword2, keyword3")
    set_run_font(run, bold=True, italic=True)


def add_section_heading(doc, title, space_before=3, space_after=3):
    p = doc.add_paragraph()
    set_paragraph_format(
        p,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        space_before=space_before,
        space_after=space_after,
        line_spacing=1.0,
    )
    run = p.add_run(title)
    set_run_font(run, bold=True, italic=True)
    return p


def add_subsection_heading(doc, title, space_before=3, space_after=3):
    p = doc.add_paragraph()
    set_paragraph_format(
        p,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        space_before=space_before,
        space_after=space_after,
        line_spacing=1.0,
    )
    run = p.add_run(title)
    set_run_font(run, bold=True)
    return p


def add_body_text(doc, text, first_line_indent=720):
    p = doc.add_paragraph()
    set_paragraph_format(
        p,
        alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
        space_before=0,
        space_after=0,
        line_spacing=1.0,
        first_line_indent=first_line_indent,
    )
    _append_rich_body_text(p, text)
    return p


def _append_rich_body_text(paragraph, text):
    parts = re.split(r"(\$[^$]+\$)", text)
    for part in parts:
        if part.startswith("$") and part.endswith("$") and len(part) > 2:
            latex = part[1:-1]
            if not _append_inline_math(paragraph, latex):
                run = paragraph.add_run(latex)
                set_run_font(run, italic=True)
        else:
            if part:
                run = paragraph.add_run(part)
                set_run_font(run)


def add_figure(doc, fig_data, space_before=3, space_after=3):
    img_path = BASE / fig_data.get("Path", "")
    fig_num = fig_data.get("ImageNumber", "")
    fig_title = fig_data.get("Title", "")

    p_img = doc.add_paragraph()
    set_paragraph_format(
        p_img,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=space_before,
        space_after=0,
        line_spacing=1.0,
    )

    if img_path.exists() and img_path.is_file():
        run = p_img.add_run()
        set_run_font(run)
        run.add_picture(str(img_path), width=Cm(8))
    else:
        title_text = str(fig_data.get("Title", "")).strip()
        prompt_text = str(fig_data.get("Prompt", "")).strip()
        body_parts = []
        if title_text:
            body_parts.append(title_text)
        if prompt_text and prompt_text.lower() not in (title_text or "").lower():
            body_parts.append(prompt_text)
        body = ". ".join(body_parts) if body_parts else f"Image: {fig_data.get('Path', '')}"
        run = p_img.add_run(f"[PROMPT UNTUK AI GAMBAR: {body}]")
        set_run_font(run, italic=True)

    p_cap = doc.add_paragraph()
    set_paragraph_format(
        p_cap,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=0,
        space_after=space_after,
        line_spacing=1.0,
    )
    run = p_cap.add_run(f"Gbr. {fig_num}. ")
    set_run_font(run, bold=True)
    run = p_cap.add_run(fig_title)
    set_run_font(run)


def add_formula(doc, formula_data, space_before=3, space_after=3):
    formula_num = formula_data.get("FormulaNumber", "")
    latex = formula_data.get("latex", "")

    p = doc.add_paragraph()
    set_paragraph_format(
        p,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=space_before,
        space_after=space_after,
        line_spacing=1.0,
    )

    if not _append_inline_math(p, latex):
        run = p.add_run(latex)
        set_run_font(run, italic=True)

    if formula_num:
        run = p.add_run(f"   ({formula_num})")
        set_run_font(run)


def add_table(doc, table_data, space_before=6, space_after=3):
    tbl_num = table_data.get("TableNumber", "")
    tbl_title = table_data.get("Title", "")
    headers = table_data.get("Headers", [])
    rows = table_data.get("Rows", [])

    p_title = doc.add_paragraph()
    set_paragraph_format(
        p_title,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=space_before,
        space_after=space_after,
        line_spacing=1.0,
    )
    run = p_title.add_run(f"Tabel {tbl_num}. ")
    set_run_font(run, bold=True)
    run = p_title.add_run(tbl_title)
    set_run_font(run)

    num_cols = len(headers)
    num_rows = len(rows) + 1
    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    tbl_el = table._tbl
    tblPr = tbl_el.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = parse_xml(f'<w:tblPr {nsdecls("w")}></w:tblPr>')
        tbl_el.insert(0, tblPr)
    borders_xml = (
        f'<w:tblBorders {nsdecls("w")}>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        "</w:tblBorders>"
    )
    tblPr.append(parse_xml(borders_xml))

    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        set_paragraph_format(
            p, alignment=WD_ALIGN_PARAGRAPH.CENTER, space_before=0, space_after=0, line_spacing=1.0
        )
        run = p.add_run(h)
        set_run_font(run, bold=True)

    for ri, row in enumerate(rows):
        for ci, cell_text in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            set_paragraph_format(
                p,
                alignment=WD_ALIGN_PARAGRAPH.CENTER,
                space_before=0,
                space_after=0,
                line_spacing=1.0,
            )
            clean_text = cell_text.replace("\\b", "")
            is_bold = "\\b" in cell_text
            run = p.add_run(clean_text)
            set_run_font(run, bold=is_bold)


def add_references(doc, data):
    refs_data = data.get("references", {})
    if isinstance(refs_data, list):
        refs_data = {"title": "REFERENCES", "content": refs_data}
    refs_title = refs_data.get("title", "REFERENCES")
    refs_content = refs_data.get("content", [])

    add_empty_para(doc)
    p = doc.add_paragraph()
    set_paragraph_format(
        p, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_before=3, space_after=3, line_spacing=1.0
    )
    run = p.add_run(refs_title)
    set_run_font(run, bold=True)

    for ref in refs_content:
        # Normalize ref to string
        if isinstance(ref, dict):
            ref_id = ref.get("id", "")
            ref_text = ref.get("text", "")
            ref_str = f"[{ref_id}] {ref_text}" if ref_id else ref_text
        else:
            ref_str = str(ref)
        
        p = doc.add_paragraph()
        set_paragraph_format(
            p,
            alignment=WD_ALIGN_PARAGRAPH.JUSTIFY,
            space_before=0,
            space_after=0,
            line_spacing=1.0,
            left_indent=567,
            hanging_indent=567,
        )
        parts = re.split(r"(\"[^\"]+\")", ref_str)
        for part in parts:
            if part.startswith('"') and part.endswith('"'):
                run = p.add_run(part)
                set_run_font(run, color="000000")
            else:
                re.search(r",\s*([^,]+(?:,\s*(?:ed\.|vol\.|no\.)[^,]*)*)\s*,", part)
                run = p.add_run(part)
                set_run_font(run, color="000000")


def process_section_content(doc, content_list):
    if not content_list:
        return
    for item in content_list:
        if isinstance(item, str):
            add_body_text(doc, item)
            continue
        item_id = item.get("id", "")
        if item_id == "text":
            add_body_text(doc, item.get("text", ""))
        elif item_id == "gambar":
            add_figure(doc, item, space_before=3, space_after=6)
        elif item_id == "rumus":
            add_formula(doc, item, space_before=3, space_after=3)
        elif item_id == "tabel":
            add_table(doc, item, space_before=6, space_after=3)


def process_section(doc, section_data, section_num, is_top_level=True):
    title = section_data.get("title", "")
    content = section_data.get("content", [])

    if is_top_level:
        add_section_heading(doc, title, space_before=3, space_after=3)
    else:
        add_subsection_heading(doc, title, space_before=3, space_after=3)

    if content:
        process_section_content(doc, content)

    sub_keys = sorted(
        [
            k
            for k in section_data.keys()
            if k.startswith(f"section{section_num}") and k != "title" and k != "content"
        ]
    )
    for sk in sub_keys:
        sub_data = section_data[sk]
        if isinstance(sub_data, dict) and "title" in sub_data:
            process_section(doc, sub_data, section_num, is_top_level=False)


def generate():
    data = load_json()

    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    clear_body(doc)

    section = doc.sections[0]
    section.page_width = Twips(PAGE_WIDTH_TW)
    section.page_height = Twips(PAGE_HEIGHT_TW)
    section.top_margin = Twips(MARGIN_TW)
    section.bottom_margin = Twips(MARGIN_TW)
    section.left_margin = Twips(MARGIN_TW)
    section.right_margin = Twips(MARGIN_TW)
    section.header_distance = Twips(709)
    section.footer_distance = Twips(709)

    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    add_empty_para(doc)

    for i in range(1, 10):
        key = f"section{i}"
        if key in data:
            section_data = data[key]
            process_section(doc, section_data, i, is_top_level=True)

    add_references(doc, data)

    _set_ai_prompt_color_red(doc)
    _postprocess_clean_latex(doc)
    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return OUTPUT_DOCX


if __name__ == "__main__":
    generate()
