"""
ENERGIUPMgen.py - Generator dokumen ENERGIUPM dari JSON.

Menggunakan ENERGIUPM.docx sebagai template asli agar header, footer,
theme, numbering, dan package parts tetap mengikuti dokumen sumber.
Semua konten diambil dari _PLC-MediapipeID.json.

Format yang dipertahankan dari hasil analisa template:
- halaman 1-kolom dengan margin/header/footer asli template
- title 14pt Palatino Linotype
- body 11pt Palatino Linotype
- caption 11pt Palatino Linotype, center
- heading section/subsection memakai numbering template (numId=1)
- tabel data memakai gaya tabel jurnal sederhana tanpa grid penuh
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "_PLC-MediapipeID.json"
TEMPLATE_PATH = BASE_DIR / "ENERGIUPM.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
BODY_FONT = "Palatino Linotype"
BODY_SIZE_PT = 11.0
BODY_TABLE_SIZE_PT = 10.0
TITLE_SIZE_PT = 14.0
EMAIL_SIZE_PT = 9.0
MAX_FIGURE_WIDTH_CM = 9.95

AUTHOR_TABLE_WIDTH_TW = 9067
AUTHOR_TABLE_COLS_TW = [562, 2977, 3260, 2268]
CONTENT_TABLE_WIDTH_TW = 7797
EQUATION_TABLE_WIDTH_TW = 9073
EQUATION_COLS_TW = [8073, 1000]

SECTION_INDENT_TW = 288
SUBSECTION_INDENT_TW = 426
REFERENCE_INDENT_TW = 426
BORDER_SIZE = "4"
BORDER_COLOR = "auto"
BORDER_DASH = "dashSmallGap"

XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]
_XSLT = None


@dataclass
class RenderState:
    figure_count: int = 0
    table_count: int = 0


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


def _pt_to_twips(value: float) -> int:
    return int(round(value * 20))


def _set_para_style(paragraph, style_id: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(qn("w:val"), style_id)


def _set_num_pr(paragraph, *, num_id: int, ilvl: int) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    num_pr = ppr.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        ppr.append(num_pr)
    ilvl_el = num_pr.find(qn("w:ilvl"))
    if ilvl_el is None:
        ilvl_el = OxmlElement("w:ilvl")
        num_pr.append(ilvl_el)
    ilvl_el.set(qn("w:val"), str(ilvl))
    num_id_el = num_pr.find(qn("w:numId"))
    if num_id_el is None:
        num_id_el = OxmlElement("w:numId")
        num_pr.append(num_id_el)
    num_id_el.set(qn("w:val"), str(num_id))


def _set_run_font(run, font_name: str = BODY_FONT) -> None:
    run.font.name = font_name
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def _format_run(
    run,
    *,
    size_pt: float,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    superscript: bool = False,
    font_name: str = BODY_FONT,
) -> None:
    _set_run_font(run, font_name=font_name)
    run.font.size = Pt(size_pt)
    run.font.color.rgb = RGBColor(0, 0, 0)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline
    if superscript:
        run.font.superscript = True


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


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


def _latex_to_omml(latex: str):
    try:
        import latex2mathml.converter
    except Exception:
        return None
    xslt = _get_xslt()
    if not xslt:
        return None
    try:
        mathml = latex2mathml.converter.convert(latex)
        root = etree.fromstring(mathml.encode("utf-8"))
        return xslt(root).getroot()
    except Exception:
        return None


def _append_inline_math(paragraph, latex: str) -> bool:
    omml = _latex_to_omml(latex)
    if omml is None:
        return False
    tag = omml.tag.split("}")[-1] if "}" in omml.tag else omml.tag
    if tag in ("oMath", "oMathPara"):
        paragraph._p.append(omml)
    else:
        wrapper = etree.fromstring(f'<m:oMath xmlns:m="{MATH_NS}"/>')
        wrapper.append(omml)
        paragraph._p.append(wrapper)
    return True


def _append_line_break(paragraph) -> None:
    paragraph.add_run().add_break()


def _normalize_text_commands(text: str) -> str:
    text = text.replace("\\n", "\n")
    # Convert Markdown bold/italic to \b..\b / \i..\i toggle format
    text = re.sub(r"\*\*(.+?)\*\*", r"\\b\1\\b", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+?)\*", r"\\i\1\\i", text)
    return text


def _iter_rich_tokens(text: str):
    normalized = _normalize_text_commands(text)
    buffer: list[str] = []
    bold = italic = underline = False
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
            cmd = normalized[index + 1]
            if cmd == "\\":
                buffer.append("\\")
                index += 2
                continue
            if cmd == "b":
                yield from flush_buffer()
                bold = not bold
                index += 2
                continue
            if cmd == "i":
                yield from flush_buffer()
                italic = not italic
                index += 2
                continue
            if cmd == "u":
                yield from flush_buffer()
                underline = not underline
                index += 2
                continue
        if char == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                yield from flush_buffer()
                formula = normalized[index + 1 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 1
                continue
        buffer.append(char)
        index += 1
    yield from flush_buffer()


def _append_rich_text(
    paragraph,
    text: str,
    *,
    size_pt: float = BODY_SIZE_PT,
    font_name: str = BODY_FONT,
) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            _append_line_break(paragraph)
        elif token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                run = paragraph.add_run(token["value"])
                _format_run(run, size_pt=size_pt, italic=True, font_name=font_name)
        else:
            run = paragraph.add_run(token["value"])
            _format_run(
                run,
                size_pt=size_pt,
                bold=token["bold"],
                italic=token["italic"],
                underline=token["underline"],
                font_name=font_name,
            )


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    parts = [part for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return parts or [""]


def _body_paragraphs(
    doc: Document,
    text: str,
    *,
    first_line: bool = True,
    space_after_pt: float | None = None,
) -> None:
    for block in _split_body_blocks(text):
        paragraph = doc.add_paragraph()
        _set_para_style(paragraph, "Normal")
        if not first_line:
            paragraph.paragraph_format.first_line_indent = Pt(0)
        if space_after_pt is not None:
            paragraph.paragraph_format.space_after = Pt(space_after_pt)
        _append_rich_text(paragraph, block)


def _set_table_width_fixed(table, total_width_tw: int, column_widths_tw: list[int]) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)

    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total_width_tw))
    tbl_w.set(qn("w:type"), "dxa")

    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")

    tbl_grid = tbl.find(qn("w:tblGrid"))
    if tbl_grid is None:
        tbl_grid = OxmlElement("w:tblGrid")
        tbl.insert(1, tbl_grid)
    for child in list(tbl_grid):
        tbl_grid.remove(child)
    for width in column_widths_tw:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(width))
        tbl_grid.append(grid_col)


def _set_cell_width(cell, width_tw: int) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(width_tw))
    tc_w.set(qn("w:type"), "dxa")


def _set_cell_margins(cell, top=72, left=72, bottom=72, right=72) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for edge, value in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = tc_mar.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tc_mar.append(el)
        el.set(qn("w:w"), str(value))
        el.set(qn("w:type"), "dxa")


def _set_cell_border(
    cell,
    *,
    top: str | None = None,
    bottom: str | None = None,
    left: str | None = None,
    right: str | None = None,
) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)

    for edge, value in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        if value is None:
            continue
        el = tc_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tc_borders.append(el)
        el.set(qn("w:val"), value)
        el.set(qn("w:sz"), BORDER_SIZE)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), BORDER_COLOR)


def _clear_all_borders(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    tbl_borders = tbl_pr.find(qn("w:tblBorders"))
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tbl_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tbl_borders.append(el)
        el.set(qn("w:val"), "nil")


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative
    return BASE_DIR / path


def _table_number_text(item: dict, state: RenderState) -> str:
    raw = str(item.get("TableNumber", "")).strip()
    if raw:
        return raw
    state.table_count += 1
    return str(state.table_count)


def _figure_number_text(item: dict, state: RenderState) -> str:
    raw = str(item.get("ImageNumber", "")).strip()
    if raw:
        return raw
    state.figure_count += 1
    return str(state.figure_count)


def _guess_column_widths(headers: list[str], rows: list[list[str]]) -> list[int]:
    cols = len(headers)
    if cols <= 0:
        return []
    if cols == 2:
        return [
            int(CONTENT_TABLE_WIDTH_TW * 0.38),
            CONTENT_TABLE_WIDTH_TW - int(CONTENT_TABLE_WIDTH_TW * 0.38),
        ]

    weights = []
    min_chars = 8
    max_chars = 36
    for col_index in range(cols):
        values = [str(headers[col_index])]
        for row in rows:
            if col_index < len(row):
                values.append(str(row[col_index]))
        longest = max((len(value.strip()) for value in values), default=min_chars)
        longest = max(min_chars, min(longest, max_chars))
        weights.append(math.sqrt(longest))

    total_weight = sum(weights) or cols
    widths = [max(600, int(CONTENT_TABLE_WIDTH_TW * (weight / total_weight))) for weight in weights]
    delta = CONTENT_TABLE_WIDTH_TW - sum(widths)
    widths[-1] += delta
    return widths


def _looks_numeric(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    if len(cleaned) <= 6 and " " not in cleaned:
        return True
    return bool(re.fullmatch(r"[\d,.;:%()=+\-xX/]+", cleaned))


def _add_title(doc: Document, config: dict) -> None:
    title = str(config.get("title", "")).strip()
    if not title:
        return
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "Heading1")
    paragraph.paragraph_format.first_line_indent = Pt(0)
    _append_rich_text(paragraph, title, size_pt=TITLE_SIZE_PT)


def _parse_author_entries(config: dict) -> list[dict]:
    authors = config.get("authors", [])
    if not isinstance(authors, list):
        return []
    entries = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        entries.append(
            {
                "name": str(author.get("name", "")).strip(),
                "affiliation": str(author.get("affiliation", "")).strip(),
                "location": str(author.get("location", "")).strip(),
                "email": str(author.get("email", "")).strip(),
                "orcid": str(author.get("orcid", "")).strip(),
            }
        )
    return entries


def _add_author_table(doc: Document, entries: list[dict]) -> None:
    if not entries:
        return
    table = doc.add_table(rows=len(entries) + 1, cols=4)
    table.style = "Table Grid"
    table.autofit = False
    _set_table_width_fixed(table, AUTHOR_TABLE_WIDTH_TW, AUTHOR_TABLE_COLS_TW)

    headers = ["No", "Full name ", "email", "Orcid (if any)"]
    for col_index, header in enumerate(headers):
        cell = table.cell(0, col_index)
        _set_cell_width(cell, AUTHOR_TABLE_COLS_TW[col_index])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.text = header

    for row_index, entry in enumerate(entries, start=1):
        values = [
            str(row_index),
            entry["name"],
            entry["email"],
            entry["orcid"],
        ]
        for col_index, value in enumerate(values):
            cell = table.cell(row_index, col_index)
            _set_cell_width(cell, AUTHOR_TABLE_COLS_TW[col_index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.text = value
            if col_index == 0:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT


def _add_email_line(doc: Document, entries: list[dict]) -> None:
    email = next((entry["email"] for entry in entries if entry["email"]), "")
    if not email:
        return
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "Normal")
    paragraph.paragraph_format.first_line_indent = Pt(0)
    run = paragraph.add_run("Email: ")
    _format_run(run, size_pt=EMAIL_SIZE_PT)
    run = paragraph.add_run(email)
    _format_run(run, size_pt=EMAIL_SIZE_PT)


def _add_affiliations(doc: Document, entries: list[dict]) -> None:
    for index, entry in enumerate(entries, start=1):
        paragraph = doc.add_paragraph()
        _set_para_style(paragraph, "Normal")
        paragraph.paragraph_format.first_line_indent = Pt(0)

        run = paragraph.add_run(str(index))
        _format_run(run, size_pt=BODY_SIZE_PT, superscript=True)

        parts = [part for part in (entry["affiliation"], entry["location"]) if part]
        if parts:
            text = ", ".join(parts)
            _append_rich_text(paragraph, text, size_pt=BODY_SIZE_PT)


def _add_abstract(doc: Document, config: dict) -> None:
    abstract = str(config.get("abstract", "")).strip()
    if not abstract:
        return
    heading = doc.add_paragraph()
    _set_para_style(heading, "Heading1")
    heading.paragraph_format.first_line_indent = Pt(0)
    _append_rich_text(heading, "Abstract", size_pt=BODY_SIZE_PT)

    _body_paragraphs(doc, abstract, first_line=True, space_after_pt=6.0)


def _add_keywords(doc: Document, config: dict) -> None:
    keywords = config.get("keywords", [])
    if not isinstance(keywords, list) or not keywords:
        return
    text = "; ".join(str(keyword).strip() for keyword in keywords if str(keyword).strip())
    if not text:
        return
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "Normal")
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_after = Pt(6.0)
    _append_rich_text(paragraph, f"Keywords: {text}")


def _normalize_heading_case(text: str) -> str:
    """Normalize heading: kalau seluruhnya UPPERCASE, ubah ke Title Case
    supaya konsisten dengan template (Heading 1 numbering pakai Title Case)."""
    if not text:
        return text
    s = str(text).strip()
    # Kalau sudah ada huruf kecil, biarkan apa adanya
    if any(c.islower() for c in s):
        return s
    # Semua huruf besar -> ubah ke title case (kata-kata pendek tetap kapital)
    return s.title()


def _set_paragraph_rpr_size(paragraph, half_points: int) -> None:
    """Set rPr di pPr untuk override ukuran auto-numbering marker.
    Style 'Heading1' di template ENERGIUPM punya sz=40 (20pt) yang bikin
    angka '1.' render terlalu besar. Override ke half_points (11pt = 22)
    supaya angka match body text size."""
    pPr = paragraph._p.get_or_add_pPr()
    # rPr di dalam pPr controls paragraph mark + auto-numbering label
    rpr = pPr.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        pPr.append(rpr)
    # Set size
    sz = rpr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rpr.append(sz)
    sz.set(qn("w:val"), str(half_points))
    szcs = rpr.find(qn("w:szCs"))
    if szcs is None:
        szcs = OxmlElement("w:szCs")
        rpr.append(szcs)
    szcs.set(qn("w:val"), str(half_points))
    # Set font ke body font (Palatino Linotype) supaya konsisten
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), BODY_FONT)


def _add_section_heading(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "Heading1")
    _set_num_pr(paragraph, num_id=1, ilvl=0)
    _set_paragraph_rpr_size(paragraph, _pt_to_twips(BODY_SIZE_PT) // 10)
    paragraph.paragraph_format.left_indent = Pt(SECTION_INDENT_TW / 20)
    paragraph.paragraph_format.first_line_indent = Pt(-(SECTION_INDENT_TW / 20))
    _append_rich_text(paragraph, _normalize_heading_case(text), size_pt=BODY_SIZE_PT)


def _add_subsection_heading(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "Heading3")
    _set_num_pr(paragraph, num_id=1, ilvl=1)
    _set_paragraph_rpr_size(paragraph, _pt_to_twips(BODY_SIZE_PT) // 10)
    paragraph.paragraph_format.left_indent = Pt(SUBSECTION_INDENT_TW / 20)
    paragraph.paragraph_format.first_line_indent = Pt(-(SUBSECTION_INDENT_TW / 20))
    _append_rich_text(paragraph, text, size_pt=BODY_SIZE_PT)


def _add_subsubsection_heading(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "Heading3")
    _set_num_pr(paragraph, num_id=1, ilvl=2)
    paragraph.paragraph_format.left_indent = Pt(28.0)
    paragraph.paragraph_format.first_line_indent = Pt(-28.0)
    _append_rich_text(paragraph, text, size_pt=BODY_SIZE_PT)


def _add_figure(doc: Document, item: dict, json_path: Path, state: RenderState) -> None:

    path_text = str(item.get("Path", "")).strip()
    title = str(item.get("Title", "")).strip()
    number = _figure_number_text(item, state)
    image_path = _resolve_path(path_text, json_path) if path_text else None

    try:
        width_cm = float(item.get("WidthCm", MAX_FIGURE_WIDTH_CM))
    except (TypeError, ValueError):
        width_cm = MAX_FIGURE_WIDTH_CM
    width_cm = max(1.0, min(width_cm, MAX_FIGURE_WIDTH_CM))

    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if image_path is not None and image_path.is_file():
        paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
    else:
        _append_rich_text(paragraph, f"[IMAGE MISSING: {path_text}]", size_pt=BODY_SIZE_PT)

    if title:
        caption = doc.add_paragraph()
        _set_para_style(caption, "Caption")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _append_rich_text(caption, f"Figure {number}. {title}", size_pt=BODY_SIZE_PT)


def _add_table(doc: Document, item: dict, state: RenderState) -> None:
    headers = list(item.get("Headers", []) or item.get("headers", []))
    rows = list(item.get("Rows", []) or item.get("rows", []))
    title = str(item.get("Title") or item.get("title", "")).strip()
    if not headers:
        return

    number = _table_number_text(item, state)
    if title:
        caption = doc.add_paragraph()
        _set_para_style(caption, "Caption")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _append_rich_text(caption, f"Table {number}. {title}", size_pt=BODY_SIZE_PT)

    column_widths = _guess_column_widths([str(value) for value in headers], rows)
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_table_width_fixed(table, CONTENT_TABLE_WIDTH_TW, column_widths)
    _clear_all_borders(table)

    for row in table.rows:
        for cell_index, cell in enumerate(row.cells):
            _set_cell_width(cell, column_widths[cell_index])
            _set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    for col_index, value in enumerate(headers):
        cell = table.rows[0].cells[col_index]
        _set_cell_border(cell, top=BORDER_DASH, bottom=BORDER_DASH)
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.text = ""
        _append_rich_text(paragraph, str(value), size_pt=BODY_TABLE_SIZE_PT)
        for run in paragraph.runs:
            _format_run(run, size_pt=BODY_TABLE_SIZE_PT, bold=True)

    for row_index, row_data in enumerate(rows, start=1):
        for col_index in range(len(headers)):
            value = str(row_data[col_index]) if col_index < len(row_data) else ""
            cell = table.rows[row_index].cells[col_index]
            paragraph = cell.paragraphs[0]
            paragraph.text = ""
            paragraph.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER if _looks_numeric(value) else WD_ALIGN_PARAGRAPH.LEFT
            )
            _append_rich_text(paragraph, value, size_pt=BODY_TABLE_SIZE_PT)
        if row_index == len(rows):
            for cell in table.rows[row_index].cells:
                _set_cell_border(cell, bottom=BORDER_DASH)


def _add_equation_line(doc: Document, formula: str, number: str | None) -> None:
    table = doc.add_table(rows=1, cols=2)
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_table_width_fixed(table, EQUATION_TABLE_WIDTH_TW, EQUATION_COLS_TW)
    _clear_all_borders(table)

    left_cell = table.cell(0, 0)
    right_cell = table.cell(0, 1)
    _set_cell_width(left_cell, EQUATION_COLS_TW[0])
    _set_cell_width(right_cell, EQUATION_COLS_TW[1])
    _set_cell_margins(left_cell, 0, 0, 0, 0)
    _set_cell_margins(right_cell, 0, 0, 0, 0)
    left_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    right_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    left_para = left_cell.paragraphs[0]
    left_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    left_para.paragraph_format.first_line_indent = Pt(0)
    if not _append_inline_math(left_para, formula):
        _append_rich_text(left_para, formula, size_pt=BODY_SIZE_PT)

    right_para = right_cell.paragraphs[0]
    right_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    right_para.paragraph_format.first_line_indent = Pt(0)
    if number:
        _append_rich_text(right_para, f"({number})", size_pt=BODY_SIZE_PT)


def _add_equation_group(doc: Document, item: dict) -> None:
    formulas = [str(value).strip() for value in item.get("Lines", []) if str(value).strip()]
    single = str(item.get("latex", "") or item.get("text", "")).strip()
    if not formulas and single:
        formulas = [single]
    if not formulas:
        return
    number = str(item.get("FormulaNumber", "")).strip() or None
    for formula in formulas[:-1]:
        _add_equation_line(doc, formula, None)
    _add_equation_line(doc, formulas[-1], number)


def _render_content_item(doc: Document, item: dict, json_path: Path, state: RenderState) -> None:
    item_id = str(item.get("id", "")).lower().strip()
    if item_id == "text":
        text = str(item.get("text", "")).strip()
        if text:
            _body_paragraphs(doc, text)
    elif item_id in ("gambar", "image", "figure"):
        _add_figure(doc, item, json_path, state)
    elif item_id in ("tabel", "table"):
        _add_table(doc, item, state)
    elif item_id in ("rumus", "formula", "equation"):
        _add_equation_group(doc, item)


def _render_subsubsection(
    doc: Document, subsubsection: dict, json_path: Path, state: RenderState
) -> None:
    title = str(subsubsection.get("title", "")).strip()
    if title:
        _add_subsubsection_heading(doc, title)
    content = subsubsection.get("content", [])
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                _render_content_item(doc, item, json_path, state)
            elif isinstance(item, str) and item.strip():
                _body_paragraphs(doc, item.strip())


def _render_subsection(
    doc: Document, subsection: dict, json_path: Path, state: RenderState, sub_key: str
) -> None:
    title = str(subsection.get("title", "")).strip()
    if title:
        _add_subsection_heading(doc, title)

    content = subsection.get("content", [])
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                _render_content_item(doc, item, json_path, state)
            elif isinstance(item, str) and item.strip():
                _body_paragraphs(doc, item.strip())
    elif isinstance(content, str) and content.strip():
        _body_paragraphs(doc, content.strip())

    nested_keys = sorted(
        [key for key in subsection.keys() if re.fullmatch(rf"{re.escape(sub_key)}[a-z]+", key)]
    )
    for nested_key in nested_keys:
        nested_value = subsection[nested_key]
        if isinstance(nested_value, dict):
            _render_subsubsection(doc, nested_value, json_path, state)


def _render_sections(doc: Document, config: dict, json_path: Path, state: RenderState) -> None:
    section_keys = sorted(
        [key for key in config.keys() if re.fullmatch(r"section\d+", key)],
        key=lambda value: int(value.replace("section", "")),
    )

    for section_key in section_keys:
        section = config.get(section_key, {})
        if not isinstance(section, dict):
            continue
        section_number = section_key.replace("section", "")
        title = str(section.get("title", "")).strip()
        if title:
            _add_section_heading(doc, title)

        content = section.get("content", [])
        if isinstance(content, str) and content.strip():
            _body_paragraphs(doc, content.strip())
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    _render_content_item(doc, item, json_path, state)
                elif isinstance(item, str) and item.strip():
                    _body_paragraphs(doc, item.strip())

        subsection_keys = sorted(
            [key for key in section.keys() if re.fullmatch(rf"section{section_number}[a-z]+", key)]
        )
        for subsection_key in subsection_keys:
            subsection = section[subsection_key]
            if isinstance(subsection, dict):
                _render_subsection(doc, subsection, json_path, state, subsection_key)


def _add_references(doc: Document, config: dict) -> None:
    references = config.get("references", {})
    if not isinstance(references, dict):
        return
    items = references.get("content", [])
    if not isinstance(items, list) or not items:
        return

    title = str(references.get("title", "References")).strip() or "References"
    if title.upper() == "REFERENCES":
        title = "References"
    _add_section_heading(doc, title)

    for index, value in enumerate(items, start=1):
        ref_text = (str(value.get("text") or value.get("Text") or "").strip() if isinstance(value, dict) else str(value)).strip()
        if not ref_text:
            continue
        paragraph = doc.add_paragraph()
        _set_para_style(paragraph, "Normal")
        paragraph.paragraph_format.left_indent = Pt(REFERENCE_INDENT_TW / 20)
        paragraph.paragraph_format.first_line_indent = Pt(-(REFERENCE_INDENT_TW / 20))
        paragraph.paragraph_format.space_after = Pt(6.0)
        prefix = paragraph.add_run(f"[{index}] ")
        _format_run(prefix, size_pt=BODY_SIZE_PT)
        _append_rich_text(paragraph, ref_text, size_pt=BODY_SIZE_PT)


def build_document(
    json_path: Path = JSON_PATH,
    output_path: Path | None = None,
    template_path: Path = TEMPLATE_PATH,
) -> Path:
    config = json.loads(Path(json_path).read_text(encoding="utf-8"))
    final_output = (
        Path(output_path) if output_path else Path(json_path).parent / f"{JOURNAL_NAME}_output.docx"
    )
    final_output.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy(str(template_path), str(final_output))
    doc = Document(str(final_output))
    _clear_document_body(doc)

    state = RenderState()
    authors = _parse_author_entries(config)

    _add_title(doc, config)
    _add_author_table(doc, authors)
    _add_email_line(doc, authors)
    _add_affiliations(doc, authors)
    doc.add_paragraph()

    _add_abstract(doc, config)
    _add_keywords(doc, config)
    doc.add_paragraph()

    _render_sections(doc, config, Path(json_path), state)
    _add_references(doc, config)

    _set_ai_prompt_color_red(doc)
    doc.save(str(final_output))
    print(f"Generated: {final_output}")
    return final_output


def main() -> None:
    if len(sys.argv) >= 2:
        json_arg = Path(sys.argv[1])
        output_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
        template_arg = Path(sys.argv[3]) if len(sys.argv) >= 4 else TEMPLATE_PATH

        if not json_arg.exists():
            print(f"File tidak ditemukan: {json_arg}")
            sys.exit(1)
        if not template_arg.exists():
            print(f"Template tidak ditemukan: {template_arg}")
            sys.exit(1)

        build_document(json_arg, output_arg, template_arg)
        return

    build_document(JSON_PATH)


if __name__ == "__main__":
    main()
