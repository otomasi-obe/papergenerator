"""
ICONIEgen.py — Generator DOCX untuk International Conference of Islamic Education (ICONIE).
Template pakai default style (style=''), formatting di-set per-paragraph.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "ICONIE.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "ICONIE_output.docx"

# Format constants
FONT_DEFAULT = "Times New Roman"
SIZE_TITLE = 14
SIZE_AUTHOR = 11
SIZE_AFFIL = 10
SIZE_ABSTRACT = 10
SIZE_BODY = 11
SIZE_HEADING = 11
SIZE_CAPTION = 10


def _strip_latex(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"\$([^$]*)\$", r"\1", text)
    text = re.sub(r"\\(mathrm|mathbf|mathit|text|mathsf|mathtt)\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\{([^}]*)\}", r"√(\1)", text)
    text = re.sub(r"_\{([^}]*)\}", r"_\1", text)
    text = re.sub(r"\^\{([^}]*)\}", r"^\1", text)
    replacements = {
        r"\\approx": "≈",
        r"\\times": "×",
        r"\\cdot": "·",
        r"\\leq": "≤",
        r"\\geq": "≥",
        r"\\neq": "≠",
        r"\\infty": "∞",
        r"\\pm": "±",
        r"\\circ": "°",
        r"\\alpha": "α",
        r"\\beta": "β",
        r"\\gamma": "γ",
        r"\\theta": "θ",
        r"\\lambda": "λ",
        r"\\mu": "μ",
        r"\\pi": "π",
        r"\\sigma": "σ",
        r"\\omega": "ω",
        r"\\Delta": "Δ",
        r"\\Sigma": "Σ",
        r"\\sum": "Σ",
        r"\\int": "∫",
        r"\\partial": "∂",
        r"\\quad": "  ",
        r"\\qquad": "    ",
        r"\\dots": "...",
        r"\\ldots": "...",
        r"\\left": "",
        r"\\right": "",
        r"\\overline": "",
        r"\\underline": "",
        r"\\hat": "",
        r"\\vec": "",
        r"\\bar": "",
        r"\\dot": "",
        r"\\displaystyle": "",
        r"\\,": " ",
        r"\\begin\{[^}]*\}": "",
        r"\\end\{[^}]*\}": "",
    }
    for pat, repl in replacements.items():
        text = re.sub(pat, repl, text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"[{}]", "", text)
    return text


def load_json() -> dict:
    return json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))


def clear_body(doc):
    body = doc.element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def _set_run_font(
    run,
    font: str = FONT_DEFAULT,
    size_pt: float = SIZE_BODY,
    bold: bool = False,
    italic: bool = False,
    superscript: bool = False,
):
    run.font.name = font
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), font)
    rFonts.set(qn("w:hAnsi"), font)
    rFonts.set(qn("w:cs"), font)
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    if superscript:
        run.font.superscript = True


def _set_para_spacing(
    paragraph,
    *,
    before_pt: float = None,
    after_pt: float = None,
    line_tw: int = None,
    line_rule: str = "auto",
    first_line_tw: int = None,
    left_tw: int = None,
    right_tw: int = None,
):
    pf = paragraph.paragraph_format
    if before_pt is not None:
        pf.space_before = Pt(before_pt)
    if after_pt is not None:
        pf.space_after = Pt(after_pt)
    if line_tw is not None:
        ppr = paragraph._p.get_or_add_pPr()
        spacing = ppr.find(qn("w:spacing"))
        if spacing is None:
            spacing = OxmlElement("w:spacing")
            ppr.append(spacing)
        spacing.set(qn("w:line"), str(line_tw))
        spacing.set(qn("w:lineRule"), line_rule)
    ppr = paragraph._p.get_or_add_pPr()
    if first_line_tw is not None:
        ind = ppr.find(qn("w:ind"))
        if ind is None:
            ind = OxmlElement("w:ind")
            ppr.append(ind)
        ind.set(qn("w:firstLine"), str(first_line_tw))
    if left_tw is not None:
        ind = ppr.find(qn("w:ind"))
        if ind is None:
            ind = OxmlElement("w:ind")
            ppr.append(ind)
        ind.set(qn("w:left"), str(left_tw))
    if right_tw is not None:
        ind = ppr.find(qn("w:ind"))
        if ind is None:
            ind = OxmlElement("w:ind")
            ppr.append(ind)
        ind.set(qn("w:right"), str(right_tw))


def add_title(doc, data):
    title_text = (data.get("title") or "Paper Title Goes Here").strip()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_para_spacing(p, before_pt=0, after_pt=6)
    run = p.add_run(title_text.upper())
    _set_run_font(run, size_pt=SIZE_TITLE, bold=True)


def add_authors(doc, data):
    authors = data.get("authors") or [
        {
            "name": "Author Name",
            "affiliation": "Department, University",
            "email": "author@email.ac.id",
        }
    ]

    affil_map = {}
    for author in authors:
        affil = (author.get("affiliation") or "").strip()
        if affil and affil not in affil_map:
            affil_map[affil] = len(affil_map) + 1

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_para_spacing(p, before_pt=0, after_pt=3)
    for i, author in enumerate(authors):
        if i > 0:
            r = p.add_run(", ")
            _set_run_font(r, size_pt=SIZE_AUTHOR)
        name = (author.get("name") or "Author Name").strip()
        r = p.add_run(name)
        _set_run_font(r, size_pt=SIZE_AUTHOR)
        affil = (author.get("affiliation") or "").strip()
        idx = affil_map.get(affil)
        if idx:
            sup = p.add_run(str(idx))
            _set_run_font(sup, size_pt=SIZE_AUTHOR, superscript=True)

    for affil, idx in affil_map.items():
        ap = doc.add_paragraph()
        ap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_para_spacing(ap, before_pt=0, after_pt=2)
        sup = ap.add_run(str(idx))
        _set_run_font(sup, size_pt=SIZE_AFFIL, italic=True, superscript=True)
        r = ap.add_run(affil)
        _set_run_font(r, size_pt=SIZE_AFFIL, italic=True)

    # Email
    for author in authors:
        email = (author.get("email") or "").strip()
        if not email:
            continue
        ep = doc.add_paragraph()
        ep.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_para_spacing(ep, before_pt=0, after_pt=2)
        r = ep.add_run(email)
        _set_run_font(r, size_pt=SIZE_AFFIL, italic=True)


def add_abstract(doc, data):
    abstract = (data.get("abstract") or "Abstract text goes here.").strip()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_para_spacing(p, before_pt=6, after_pt=3, line_tw=276, left_tw=284, right_tw=140)
    r = p.add_run("Abstract: ")
    _set_run_font(r, size_pt=SIZE_ABSTRACT, bold=True, italic=True)
    r = p.add_run(_strip_latex(abstract))
    _set_run_font(r, size_pt=SIZE_ABSTRACT, italic=True)


def add_keywords(doc, data):
    kw = data.get("keywords") or []
    if not kw:
        return
    text = ", ".join(kw)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_para_spacing(p, before_pt=3, after_pt=6, line_tw=276, left_tw=284, right_tw=140)
    r = p.add_run("Keywords: ")
    _set_run_font(r, size_pt=SIZE_ABSTRACT, bold=True, italic=True)
    r = p.add_run(text)
    _set_run_font(r, size_pt=SIZE_ABSTRACT, italic=True)


def add_section_heading(doc, title: str):
    p = doc.add_paragraph()
    _set_para_spacing(p, before_pt=6, after_pt=6, line_tw=360)
    r = p.add_run(title.upper())
    _set_run_font(r, size_pt=SIZE_HEADING, bold=True)


def add_subsection_heading(doc, title: str):
    p = doc.add_paragraph()
    _set_para_spacing(p, before_pt=4, after_pt=4, line_tw=360)
    r = p.add_run(title)
    _set_run_font(r, size_pt=SIZE_HEADING, bold=True, italic=True)


def add_body_text(doc, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_para_spacing(p, before_pt=0, after_pt=0, line_tw=360, first_line_tw=567)
    r = p.add_run(_strip_latex(text))
    _set_run_font(r, size_pt=SIZE_BODY)


def add_table(doc, table_data: dict):
    num = str(table_data.get("TableNumber") or "1")
    title = (table_data.get("Title") or "Table title").strip()
    headers = table_data.get("Headers") or ["Col1", "Col2"]
    rows = table_data.get("Rows") or [["Data", "Data"]]

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_para_spacing(cap, before_pt=6, after_pt=3)
    r = cap.add_run(f"Table {num}. ")
    _set_run_font(r, size_pt=SIZE_CAPTION, bold=True)
    r = cap.add_run(title)
    _set_run_font(r, size_pt=SIZE_CAPTION)

    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Set HORIZONTAL_ONLY borders (3-line academic style)
    tbl = table._tbl
    tbl_pr = tbl.tblPr or tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    tbl_borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        if side in ("top", "bottom", "insideH"):
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
        else:
            el.set(qn("w:val"), "nil")
        tbl_borders.append(el)
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    tbl_pr.append(tbl_borders)

    for col_idx, header in enumerate(headers):
        cell = table.rows[0].cells[col_idx]
        cell.text = ""
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = para.add_run(str(header))
        _set_run_font(r, size_pt=SIZE_CAPTION, bold=True)

    for row_idx, row_data in enumerate(rows, start=1):
        for col_idx, value in enumerate(row_data[: len(headers)]):
            cell = table.rows[row_idx].cells[col_idx]
            cell.text = ""
            para = cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = para.add_run(str(value))
            _set_run_font(r, size_pt=SIZE_CAPTION)


def add_figure(doc, fig_data: dict):
    image_number = str(fig_data.get("ImageNumber") or "1").strip()
    title = (fig_data.get("Title") or "").strip()
    prompt = (fig_data.get("Prompt") or "").strip()
    path_text = (fig_data.get("Path") or "").strip()

    image_path = None
    if path_text:
        cand = Path(path_text)
        if not cand.is_absolute():
            cand = BASE / path_text
        if cand.is_file():
            image_path = cand

    if image_path:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_para_spacing(p, before_pt=6, after_pt=3)
        p.add_run().add_picture(str(image_path), width=Cm(10))
    else:
        prompt_body = prompt if prompt else f"Figure {image_number}"
        if title:
            placeholder_text = f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt_body}]"
        else:
            placeholder_text = f"[PROMPT UNTUK AI GAMBAR: {prompt_body}]"
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = table.cell(0, 0)
        cell.text = ""
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = para.add_run(placeholder_text)
        _set_run_font(r, size_pt=SIZE_CAPTION, italic=True)

    if title:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_para_spacing(cap, before_pt=3, after_pt=6)
        r = cap.add_run(f"Figure {image_number}. ")
        _set_run_font(r, size_pt=SIZE_CAPTION, bold=True)
        r = cap.add_run(title)
        _set_run_font(r, size_pt=SIZE_CAPTION)


def add_formula(doc, formula_data: dict):
    num = str(formula_data.get("FormulaNumber") or "").strip()
    text = (formula_data.get("text") or formula_data.get("latex") or "E = mc^2").strip()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_para_spacing(p, before_pt=3, after_pt=3)
    r = p.add_run(_strip_latex(text))
    _set_run_font(r, size_pt=SIZE_BODY, italic=True)
    if num:
        r = p.add_run(f"\t({num})")
        _set_run_font(r, size_pt=SIZE_BODY)


def process_content_item(doc, item: dict):
    if not isinstance(item, dict):
        return
    item_id = (item.get("id") or "").lower()
    if item_id in ("text", ""):
        text = (item.get("text") or "").strip()
        if text:
            add_body_text(doc, text)
    elif item_id in ("gambar", "image", "figure"):
        add_figure(doc, item)
    elif item_id in ("tabel", "table"):
        add_table(doc, item)
    elif item_id in ("rumus", "formula", "equation"):
        add_formula(doc, item)


def process_section(doc, section_data: dict, top_level: bool = True):
    if not isinstance(section_data, dict):
        return
    title = (section_data.get("title") or "").strip()
    if title:
        if top_level:
            add_section_heading(doc, title)
        else:
            add_subsection_heading(doc, title)

    content = section_data.get("content")
    if isinstance(content, list):
        for item in content:
            process_content_item(doc, item)

    for key in section_data:
        if key in ("title", "content"):
            continue
        if key.startswith("section"):
            process_section(doc, section_data[key], top_level=False)


def add_references(doc, data):
    refs = data.get("references") or {}
    title = (refs.get("title") or "REFERENCES").strip()
    items = refs.get("content") or ["[1] Author, Title, Journal, Year."]

    p_title = doc.add_paragraph()
    _set_para_spacing(p_title, before_pt=12, after_pt=6, line_tw=360)
    r = p_title.add_run(title.upper())
    _set_run_font(r, size_pt=SIZE_HEADING, bold=True)

    for ref in items:
        rp = doc.add_paragraph()
        rp.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _set_para_spacing(rp, before_pt=0, after_pt=3, line_tw=276, first_line_tw=-360, left_tw=360)
        r = rp.add_run(str(ref))
        _set_run_font(r, size_pt=SIZE_CAPTION)


def generate():
    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))
    clear_body(doc)

    data = load_json()

    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    for i in range(1, 30):
        key = f"section{i}"
        if key in data:
            process_section(doc, data[key], top_level=True)

    add_references(doc, data)

    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


if __name__ == "__main__":
    generate()
