"""
IJITEEgen.py — Generator DOCX untuk IJITEE journal.
Template pakai custom styles: Title, Authors, Abstract, Heading1, Heading2, Text.
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
TEMPLATE_DOCX = BASE / "IJITEE.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "IJITEE_output.docx"

STYLE_TITLE = "Title"
STYLE_AUTHORS = "Authors"
STYLE_ABSTRACT = "Abstract"
STYLE_KEYWORDS = "IndexTerms"
STYLE_HEAD1 = "Heading1"
STYLE_HEAD2 = "Heading2"
STYLE_BODY = "Text"
STYLE_TBL_CAPTION = "TableCaption"
STYLE_FIG_CAPTION = "FigureCaption"
STYLE_REFS = "References"


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


def clear_body_keep_sectprs(doc):
    """Hapus body content tapi PRESERVE semua sectPr (inline + final).
    SectPr inline ada di pPr dari paragraf - kita keep paragraf yang
    punya sectPr saja.
    """
    body = doc.element.body
    preserved_inline_sectprs = []
    for child in list(body):
        if child.tag == qn("w:p"):
            ppr = child.find(qn("w:pPr"))
            if ppr is not None:
                sectpr_inline = ppr.find(qn("w:sectPr"))
                if sectpr_inline is not None:
                    # Preserve sectPr inline (extract dari pPr, simpan sebagai
                    # paragraf kosong dengan pPr yang punya sectPr)
                    preserved_inline_sectprs.append(child)
                    # Hapus runs dari paragraf ini, keep pPr+sectPr
                    for run in child.findall(qn("w:r")):
                        child.remove(run)
                    continue
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)
    return preserved_inline_sectprs


def insert_before_sectpr(doc, sectpr_para):
    """Helper untuk insert paragraph baru SEBELUM paragraf yang punya sectPr inline."""
    new_p = OxmlElement("w:p")
    sectpr_para.addprevious(new_p)
    return new_p


def _set_para_style(paragraph, style_name: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    for old in ppr.findall(qn("w:pStyle")):
        ppr.remove(old)
    pstyle = OxmlElement("w:pStyle")
    pstyle.set(qn("w:val"), style_name)
    ppr.insert(0, pstyle)


def _add_run(
    paragraph,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    superscript: bool = False,
    font: str = None,
    size_pt: float = None,
):
    run = paragraph.add_run(text)
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    if superscript:
        run.font.superscript = True
    if font:
        run.font.name = font
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        rFonts.set(qn("w:ascii"), font)
        rFonts.set(qn("w:hAnsi"), font)
        rFonts.set(qn("w:cs"), font)
    if size_pt:
        run.font.size = Pt(size_pt)
    return run


def _embed_inline_sectpr(doc, num_cols: int, col_space_tw: int = 288):
    """Embed sectPr inline (untuk transition antar section layout)."""
    p = doc.add_paragraph()
    ppr = p._p.get_or_add_pPr()
    sectpr = OxmlElement("w:sectPr")
    pgsz = OxmlElement("w:pgSz")
    pgsz.set(qn("w:w"), "11907")
    pgsz.set(qn("w:h"), "16839")
    sectpr.append(pgsz)
    pgmar = OxmlElement("w:pgMar")
    pgmar.set(qn("w:top"), "1008")
    pgmar.set(qn("w:right"), "936")
    pgmar.set(qn("w:bottom"), "1008")
    pgmar.set(qn("w:left"), "936")
    pgmar.set(qn("w:header"), "187")
    pgmar.set(qn("w:footer"), "141")
    pgmar.set(qn("w:gutter"), "0")
    sectpr.append(pgmar)
    cols = OxmlElement("w:cols")
    if num_cols > 1:
        cols.set(qn("w:num"), str(num_cols))
        cols.set(qn("w:space"), str(col_space_tw))
    else:
        cols.set(qn("w:space"), "720")
    sectpr.append(cols)
    ppr.append(sectpr)


def add_title(doc, data):
    title_text = (data.get("title") or "Paper Title Goes Here").strip()
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_TITLE)
    _add_run(p, title_text)


def add_authors(doc, data):
    authors = data.get("authors") or [
        {"name": "Author Name", "affiliation": "Department, University"}
    ]

    affil_map = {}
    for author in authors:
        affil = (author.get("affiliation") or "").strip()
        if affil and affil not in affil_map:
            affil_map[affil] = len(affil_map) + 1

    p = doc.add_paragraph()
    _set_para_style(p, STYLE_AUTHORS)
    for i, author in enumerate(authors):
        if i > 0:
            connector = ", and " if i == len(authors) - 1 else ", "
            _add_run(p, connector)
        name = (author.get("name") or "Author Name").strip()
        _add_run(p, name)
        idx = affil_map.get((author.get("affiliation") or "").strip())
        if idx:
            _add_run(p, str(idx), superscript=True)


def add_abstract(doc, data):
    abstract = (data.get("abstract") or "Abstract text goes here.").strip()
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_ABSTRACT)
    _add_run(p, "Abstract—", bold=True)
    _add_run(p, _strip_latex(abstract))


def add_keywords(doc, data):
    kw = data.get("keywords") or []
    if not kw:
        return
    text = ", ".join(kw)
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_KEYWORDS)
    _add_run(p, "Index Terms—", bold=True, italic=True)
    _add_run(p, text, italic=True)


def add_section_heading(doc, title: str):
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_HEAD1)
    _add_run(p, title.upper())


def add_subsection_heading(doc, title: str):
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_HEAD2)
    _add_run(p, title)


def add_body_text(doc, text: str):
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_BODY)
    _add_run(p, _strip_latex(text))


def _set_table_borders(table, pattern="full"):
    tbl = table._tbl
    tbl_pr = tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    tbl_borders = OxmlElement("w:tblBorders")
    if pattern == "full":
        visible = {"top", "left", "bottom", "right", "insideH", "insideV"}
    elif pattern == "horizontal":
        visible = {"top", "bottom", "insideH"}
    else:
        visible = set()
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        if side in visible:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
        else:
            el.set(qn("w:val"), "nil")
        tbl_borders.append(el)
    tbl_pr.append(tbl_borders)


def add_table(doc, table_data: dict):
    num = str(table_data.get("TableNumber") or "1")
    title = (table_data.get("Title") or "Table title").strip()
    headers = table_data.get("Headers") or ["Col1", "Col2"]
    rows = table_data.get("Rows") or [["Data", "Data"]]

    cap = doc.add_paragraph()
    _set_para_style(cap, STYLE_TBL_CAPTION)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(cap, f"TABLE {num}", bold=True)
    _add_run(cap, "\n" + title)

    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(table, pattern="full")

    for col_idx, header in enumerate(headers):
        cell = table.rows[0].cells[col_idx]
        cell.text = ""
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(para, str(header), bold=True)

    for row_idx, row_data in enumerate(rows, start=1):
        for col_idx, value in enumerate(row_data[: len(headers)]):
            cell = table.rows[row_idx].cells[col_idx]
            cell.text = ""
            para = cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_run(para, str(value))


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
        p.add_run().add_picture(str(image_path), width=Cm(7.5))
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
        _add_run(para, placeholder_text, italic=True)

    if title:
        cap = doc.add_paragraph()
        _set_para_style(cap, STYLE_FIG_CAPTION)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(cap, f"Fig. {image_number}. ", bold=True)
        _add_run(cap, title)


def add_formula(doc, formula_data: dict):
    num = str(formula_data.get("FormulaNumber") or "").strip()
    text = (formula_data.get("text") or formula_data.get("latex") or "E = mc^2").strip()
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_BODY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _omml_done = False
    try:
        from _math_omml import append_omml_math as _omml_fn
        _lx = (formula_data.get("latex") or "")
        _omml_done = bool(str(_lx or "").strip()) and _omml_fn(p, _lx)
    except Exception:
        _omml_done = False
    if not _omml_done:
        _add_run(p, _strip_latex(text), italic=True)
    if num:
        _add_run(p, f"\t({num})")


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
    if isinstance(refs, list):
        refs = {"title": "REFERENCES", "content": refs}
    title = (refs.get("title") or "REFERENCES").strip()
    items = [((r.get("text") or r.get("Text") or "").strip() if isinstance(r, dict) else str(r)) for r in (refs.get("content") or [])]
    items = [t for t in items if t] or ["[1] Author, Title, Journal, Year."]

    p_title = doc.add_paragraph()
    _set_para_style(p_title, STYLE_HEAD1)
    _add_run(p_title, title.upper())

    for ref in items:
        rp = doc.add_paragraph()
        _set_para_style(rp, STYLE_REFS)
        _add_run(rp, str(ref))


def generate():
    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    # Preserve inline sectPrs (yang punya headerReference/footerReference dari template)
    clear_body_keep_sectprs(doc)

    data = load_json()

    # Section 0 (sebelum sectPr inline #0): Title, Authors, Abstract, Keywords
    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    # Body content (akan masuk antara preserved sectprs atau setelah-nya)
    for i in range(1, 30):
        key = f"section{i}"
        if key in data:
            process_section(doc, data[key], top_level=True)

    # References (1-col area atau setelah sectPr inline #1)
    add_references(doc, data)

    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


if __name__ == "__main__":
    generate()
