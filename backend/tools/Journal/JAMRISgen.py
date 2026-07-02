"""
JAMRISgen.py -- Generate JAMRIS documents from JSON using the original template.

The generator keeps the source template package parts intact and writes content
with the template's own styles, numbering, and section layout.
"""

from __future__ import annotations

import json
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
from docx.shared import Cm, Pt
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "_PLC-MediapipeID.json"
TEMPLATE_PATH = BASE_DIR / "JAMRIS.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"

MATH_NS = NS_M
MAX_FIGURE_WIDTH_CM = 7.8
BODY_WIDTH_TW = 4632
EQUATION_TABLE_TOTAL_TW = 4512
EQUATION_FORMULA_TW = 3852
EQUATION_NUMBER_TW = EQUATION_TABLE_TOTAL_TW - EQUATION_FORMULA_TW

FONT_CALIBRI = "Calibri"
FONT_CAMBRIA = "Cambria"
FONT_TIMES = "Times New Roman"
FONT_CENTURY = "Century Gothic"

PAGE_W_TW = 12240
PAGE_H_TW = 15840

TITLE_TOP_TW = 1134
BODY_TOP_TW = 1247
BOTTOM_TW = 1134
LEFT_TW = 1134
RIGHT_TW = 1134
HEADER_TW = 720
FOOTER_TW = 476
COL_SPACE_TW = 708

TITLE_SECTION_INDENT_TW = 357
SUBSECTION_INDENT_TW = 425

XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]

STYLE_XML_ID = {
    "title": "JAMRISTitle",
    "authors": "JAMRISAuthors",
    "abstract_heading": "JAMRISSectionAbstract",
    "abstract": "JAMRISAbstract",
    "keywords": "JAMRISKeywords",
    "section": "JAMRISSection",
    "subsection": "JAMRISSectionSub",
    "body": "JAMRISAkapit",
    "figure": "JAMRISFigure",
    "figure_caption": "JAMRISLegendBelow",
    "references": "JAMRISBiblio",
    "author_about": "JAMRISAuthorAbout",
}

_XSLT = None


@dataclass
class RenderState:
    figure_number: int = 0
    table_number: int = 0


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

def _wq(tag: str) -> str:
    return f"{{{NS_W}}}{tag}"


def _pt_to_twips(value: float) -> int:
    return int(round(value * 20))


def _set_para_style(paragraph, style_name: str) -> None:
    xml_id = STYLE_XML_ID.get(style_name, style_name)
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(qn("w:val"), xml_id)


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


def _set_hanging_indent_twips(paragraph, *, left_tw: int, hanging_tw: int) -> None:
    paragraph.paragraph_format.left_indent = Pt(left_tw / 20)
    paragraph.paragraph_format.first_line_indent = Pt(-(hanging_tw / 20))


def _set_run_font(run, font_name: str) -> None:
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
    size_pt: float | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    font_name: str | None = None,
) -> None:
    if font_name:
        _set_run_font(run, font_name)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _embed_sectpr(
    doc: Document,
    sectpr_el,
    *,
    align=None,
    space_before_pt: float | None = None,
    space_after_pt: float | None = None,
) -> None:
    paragraph = doc.add_paragraph()
    if align is not None:
        paragraph.alignment = align
    if space_before_pt is not None:
        paragraph.paragraph_format.space_before = Pt(space_before_pt)
    if space_after_pt is not None:
        paragraph.paragraph_format.space_after = Pt(space_after_pt)
    ppr = paragraph._p.get_or_add_pPr()
    ppr.append(sectpr_el)


def _build_title_sectpr() -> etree._Element:
    sectpr = etree.Element(_wq("sectPr"))

    pgsz = etree.SubElement(sectpr, _wq("pgSz"))
    pgsz.set(_wq("w"), str(PAGE_W_TW))
    pgsz.set(_wq("h"), str(PAGE_H_TW))

    pgmar = etree.SubElement(sectpr, _wq("pgMar"))
    pgmar.set(_wq("top"), str(TITLE_TOP_TW))
    pgmar.set(_wq("bottom"), str(BOTTOM_TW))
    pgmar.set(_wq("left"), str(LEFT_TW))
    pgmar.set(_wq("right"), str(RIGHT_TW))
    pgmar.set(_wq("header"), str(HEADER_TW))
    pgmar.set(_wq("footer"), str(FOOTER_TW))
    pgmar.set(_wq("gutter"), "0")

    cols = etree.SubElement(sectpr, _wq("cols"))
    cols.set(_wq("num"), "1")
    cols.set(_wq("space"), str(COL_SPACE_TW))

    return sectpr


def _build_body_sectpr() -> etree._Element:
    sectpr = etree.Element(_wq("sectPr"))

    pgsz = etree.SubElement(sectpr, _wq("pgSz"))
    pgsz.set(_wq("w"), str(PAGE_W_TW))
    pgsz.set(_wq("h"), str(PAGE_H_TW))

    pgmar = etree.SubElement(sectpr, _wq("pgMar"))
    pgmar.set(_wq("top"), str(BODY_TOP_TW))
    pgmar.set(_wq("bottom"), str(BOTTOM_TW))
    pgmar.set(_wq("left"), str(LEFT_TW))
    pgmar.set(_wq("right"), str(RIGHT_TW))
    pgmar.set(_wq("header"), str(HEADER_TW))
    pgmar.set(_wq("footer"), str(FOOTER_TW))
    pgmar.set(_wq("gutter"), "0")

    cols = etree.SubElement(sectpr, _wq("cols"))
    cols.set(_wq("num"), "2")
    cols.set(_wq("space"), str(COL_SPACE_TW))

    stype = etree.SubElement(sectpr, _wq("type"))
    stype.set(_wq("val"), "continuous")

    return sectpr


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
    if tag in {"oMath", "oMathPara"}:
        paragraph._p.append(omml)
    else:
        wrapper = etree.fromstring(f'<m:oMath xmlns:m="{MATH_NS}"/>')
        wrapper.append(omml)
        paragraph._p.append(wrapper)
    return True


def _append_text_run(
    paragraph,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    size_pt: float | None = None,
    font_name: str | None = None,
):
    if not text:
        return None
    run = paragraph.add_run(text)
    _format_run(
        run,
        size_pt=size_pt,
        bold=bold if bold else None,
        italic=italic if italic else None,
        underline=underline if underline else None,
        font_name=font_name,
    )
    return run


def _append_line_break(paragraph) -> None:
    paragraph.add_run().add_break()


def _normalize_text_commands(text: str) -> str:
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
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
            cmd = normalized[index + 1]
            if cmd == "\\":
                buffer.append("\\")
                index += 2
                continue
            if cmd == "b":
                next_char = normalized[index + 2] if index + 2 < len(normalized) else ""
                if next_char.islower():
                    buffer.append("\\b")
                    index += 2
                    continue
                yield from flush_buffer()
                bold = not bold
                index += 2
                continue
            if cmd == "i":
                next_char = normalized[index + 2] if index + 2 < len(normalized) else ""
                if next_char.islower():
                    buffer.append("\\i")
                    index += 2
                    continue
                yield from flush_buffer()
                italic = not italic
                index += 2
                continue
            if cmd == "u":
                next_char = normalized[index + 2] if index + 2 < len(normalized) else ""
                if next_char.islower():
                    buffer.append("\\u")
                    index += 2
                    continue
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
    base_bold: bool = False,
    base_italic: bool = False,
    size_pt: float | None = None,
    font_name: str | None = None,
) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            _append_line_break(paragraph)
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                _append_text_run(
                    paragraph, token["value"], italic=True, size_pt=size_pt, font_name=font_name
                )
            continue
        _append_text_run(
            paragraph,
            token["value"],
            bold=base_bold or token["bold"],
            italic=base_italic or token["italic"],
            underline=token["underline"],
            size_pt=size_pt,
            font_name=font_name,
        )


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    blocks = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return blocks or [normalized.strip()]


ROMAN_TABLE_REFS = [
    (r'\bTabel\s+IV\b', 'Tabel 4'),
    (r'\bTabel\s+V\b', 'Tabel 5'),
    (r'\bTabel\s+VI\b', 'Tabel 6'),
    (r'\bTabel\s+VII\b', 'Tabel 7'),
    (r'\bTabel\s+VIII\b', 'Tabel 8'),
    (r'\bTabel\s+IX\b', 'Tabel 9'),
    (r'\bTabel\s+X\b', 'Tabel 10'),
    (r'\bTabel\s+III\b', 'Tabel 3'),
    (r'\bTabel\s+II\b', 'Tabel 2'),
    (r'\bTabel\s+I\b', 'Tabel 1'),
]


def _replace_roman_table_refs(text: str) -> str:
    """Replace Roman numeral table references (Tabel I→Tabel 1) with Arabic."""
    # Match longer Roman numerals first to avoid partial matches
    for pattern, replacement in ROMAN_TABLE_REFS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _body_paragraph(doc: Document, text: str) -> None:
    text = _replace_roman_table_refs(str(text))
    for block in _split_body_blocks(text):
        paragraph = doc.add_paragraph()
        _set_para_style(paragraph, "body")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        paragraph.paragraph_format.first_line_indent = Cm(0.5)
        paragraph.paragraph_format.space_after = Pt(0)
        _append_rich_text(paragraph, block, size_pt=10.0, font_name=FONT_CAMBRIA)


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative
    return BASE_DIR / path


def _clean_reference_text(text: str) -> str:
    return re.sub(r"^\s*\[\d+\]\s*", "", text).strip()


def _set_table_borders(table, *, enabled: bool) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    tbl_borders = tbl_pr.find(qn("w:tblBorders"))
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    value = "single" if enabled else "nil"
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = tbl_borders.find(qn(f"w:{edge}"))
        if border is None:
            border = OxmlElement(f"w:{edge}")
            tbl_borders.append(border)
        # Hanya top/bottom/insideH yang visible (academic style)
        side_value = value if edge in ("top", "bottom", "insideH") else "nil"
        border.set(qn("w:val"), side_value)
        border.set(qn("w:sz"), "4" if side_value == "single" else "0")
        border.set(qn("w:space"), "0")
        border.set(qn("w:color"), "000000")


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
    tbl_w.set(qn("w:type"), "dxa")
    tbl_w.set(qn("w:w"), str(total_width_tw))

    tbl_layout = tbl_pr.find(qn("w:tblLayout"))
    if tbl_layout is None:
        tbl_layout = OxmlElement("w:tblLayout")
        tbl_pr.append(tbl_layout)
    tbl_layout.set(qn("w:type"), "fixed")

    tbl_grid = tbl.tblGrid
    if tbl_grid is None:
        tbl_grid = OxmlElement("w:tblGrid")
        tbl.insert(1, tbl_grid)
    for child in list(tbl_grid):
        tbl_grid.remove(child)
    for width in column_widths_tw:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(width))
        tbl_grid.append(grid_col)

    for row in table.rows:
        for cell, width in zip(row.cells, column_widths_tw):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:type"), "dxa")
            tc_w.set(qn("w:w"), str(width))


def _set_cell_margins(cell, *, top: int, left: int, bottom: int, right: int) -> None:
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


def _fill_cell_text(
    cell, text: str, *, size_pt: float, bold: bool = False, align=WD_ALIGN_PARAGRAPH.CENTER
) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    paragraph = cell.paragraphs[0]
    _set_para_style(paragraph, "body")
    paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(0)
    _append_rich_text(paragraph, text, size_pt=size_pt, base_bold=bold)


def _fit_table_columns(headers: list[str], rows: list[list[str]]) -> list[int]:
    min_width = 420
    available = BODY_WIDTH_TW - 120
    weights: list[int] = []
    for col_idx, header in enumerate(headers):
        values = [str(header)]
        for row in rows:
            if col_idx < len(row):
                values.append(str(row[col_idx]))
        max_chars = max(len(value) for value in values) + 2
        weights.append(max(max_chars, 6))
    total_weight = sum(weights) or len(headers)
    widths = [max(min_width, int(available * weight / total_weight)) for weight in weights]
    delta = available - sum(widths)
    widths[-1] += delta
    return widths


def _parse_author_entries(config: dict) -> list[dict]:
    authors = config.get("authors", [])
    if not isinstance(authors, list):
        return []
    entries: list[dict] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = str(author.get("name", "")).strip()
        if not name:
            continue
        # New explicit fields take priority; fall back to parsing old 'affiliation' / 'location'
        department = str(author.get("department", "")).strip()
        institution = str(author.get("institution", "")).strip()
        city = str(author.get("city", "")).strip()
        zip_code = str(author.get("zip", author.get("zip_code", ""))).strip()
        country = str(author.get("country", "")).strip()
        email = str(author.get("email", "")).strip()
        is_corresponding = bool(author.get("corresponding", False))

        # If old-style 'affiliation' contains comma-separated dept+inst, parse it
        old_aff = str(author.get("affiliation", "")).strip()
        if old_aff and not (department or institution):
            parts = [p.strip() for p in old_aff.split(",", 1)]
            if len(parts) == 2:
                department, institution = parts[0], parts[1]
            else:
                institution = parts[0]
                department = ""

        # If old-style 'location' contains city and country, parse it
        old_loc = str(author.get("location", "")).strip()
        if old_loc and not (city or country):
            loc_parts = [p.strip() for p in old_loc.split(",", 1)]
            if len(loc_parts) == 2:
                city, country = loc_parts[0], loc_parts[1]
            else:
                city = loc_parts[0]

        entries.append({
            "name": name,
            "department": department,
            "institution": institution,
            "city": city,
            "zip": zip_code,
            "country": country,
            "email": email,
            "corresponding": is_corresponding,
        })

    # If no corresponding author explicitly set, default to the first author
    if entries and not any(e["corresponding"] for e in entries):
        entries[0]["corresponding"] = True

    return entries


def _add_title(doc: Document, config: dict) -> None:
    title = str(config.get("title", "")).strip()
    if not title:
        return
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "title")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _append_rich_text(paragraph, title)


def _add_authors_line(doc: Document, config: dict) -> None:
    """Add author names only (no affiliation/email) — detail goes in AUTHORS block."""
    authors = _parse_author_entries(config)
    if not authors:
        return
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "authors")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _append_text_run(paragraph, ", ".join(a["name"] for a in authors),
                     italic=True, size_pt=10.0, font_name=FONT_CAMBRIA)


def _add_abstract(doc: Document, config: dict) -> None:
    abstract = str(config.get("abstract", "")).strip()
    if not abstract:
        return
    heading = doc.add_paragraph()
    _set_para_style(heading, "abstract_heading")
    _append_text_run(heading, "Abstract:", bold=True, size_pt=12.0, font_name=FONT_CALIBRI)

    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "abstract")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _append_rich_text(
        paragraph,
        abstract,
        base_italic=True,
        size_pt=10.0,
        font_name=FONT_CALIBRI,
    )


def _add_keywords(doc: Document, config: dict) -> None:
    keywords = [str(item).strip() for item in config.get("keywords", []) if str(item).strip()]
    if not keywords:
        return
    # Capitalize first letter of each keyword
    keywords = [kw[0].upper() + kw[1:] if kw else kw for kw in keywords]
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "keywords")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _append_text_run(paragraph, "Keywords:", bold=True, size_pt=12.0, font_name=FONT_CALIBRI)
    _append_text_run(paragraph, " ", size_pt=10.0, font_name=FONT_CALIBRI)
    _append_rich_text(paragraph, ", ".join(keywords), size_pt=10.0, font_name=FONT_CALIBRI)


def _add_submission_status(doc: Document, config: dict) -> None:
    """Add 'Submitted: date; accepted: date' line before abstract."""
    submitted = str(config.get("submitted", "")).strip()
    accepted = str(config.get("accepted", "")).strip()
    if not submitted:
        submitted = "1 January XXXX"
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(6)
    parts = [f"Submitted: {submitted}"]
    if accepted:
        parts.append(f"accepted: {accepted}")
    else:
        parts.append("accepted")
    _append_text_run(paragraph, "; ".join(parts), italic=True, size_pt=10.0, font_name=FONT_CAMBRIA)


def _add_acknowledgements(doc: Document, config: dict) -> None:
    """Add Acknowledgements section before References."""
    ack_text = str(config.get("acknowledgements", "")).strip()
    if not ack_text:
        return
    heading = doc.add_paragraph()
    _set_para_style(heading, "section")
    _append_text_run(heading, "Acknowledgements", bold=True, size_pt=10.0)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.first_line_indent = Cm(0.5)
    paragraph.paragraph_format.space_after = Pt(6)
    _append_rich_text(paragraph, ack_text, size_pt=10.0, font_name=FONT_CAMBRIA)


def _add_section_heading(doc: Document, title: str) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "section")
    _set_num_pr(paragraph, num_id=3, ilvl=0)
    _set_hanging_indent_twips(
        paragraph,
        left_tw=TITLE_SECTION_INDENT_TW,
        hanging_tw=TITLE_SECTION_INDENT_TW,
    )
    _append_rich_text(paragraph, title, base_bold=True, size_pt=12.0, font_name=FONT_CALIBRI)


def _add_subsection_heading(doc: Document, title: str) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "subsection")
    _set_num_pr(paragraph, num_id=3, ilvl=1)
    _set_hanging_indent_twips(
        paragraph,
        left_tw=SUBSECTION_INDENT_TW,
        hanging_tw=SUBSECTION_INDENT_TW,
    )
    _append_rich_text(paragraph, title, base_bold=True, size_pt=12.0, font_name=FONT_CALIBRI)


def _add_figure(doc: Document, item: dict, json_path: Path, state: RenderState) -> None:

    path_text = str(item.get("Path", "")).strip()
    title = str(item.get("Title", "")).strip()
    width_cm = item.get("WidthCm")
    try:
        width_cm = float(width_cm) if width_cm is not None else MAX_FIGURE_WIDTH_CM
    except (TypeError, ValueError):
        width_cm = MAX_FIGURE_WIDTH_CM
    width_cm = min(max(width_cm, 1.0), MAX_FIGURE_WIDTH_CM)

    if path_text:
        image_path = _resolve_path(path_text, json_path)
        if image_path.is_file():
            figure_paragraph = doc.add_paragraph()
            _set_para_style(figure_paragraph, "figure")
            figure_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            figure_paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))

    if title:
        state.figure_number += 1
        caption = doc.add_paragraph()
        _set_para_style(caption, "figure_caption")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _append_text_run(caption, f"Fig. {state.figure_number}. ", bold=True)
        _append_rich_text(caption, title, base_bold=True, base_italic=True)


def _add_equation(doc: Document, item: dict) -> None:
    latex = str(item.get("latex") or item.get("text") or "").strip()
    if not latex:
        return
    number = str(item.get("FormulaNumber") or item.get("NumberiOrLetter") or "").strip()

    table = doc.add_table(rows=1, cols=2)
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_table_width_fixed(
        table, EQUATION_TABLE_TOTAL_TW, [EQUATION_FORMULA_TW, EQUATION_NUMBER_TW]
    )
    _set_table_borders(table, enabled=False)

    left_cell = table.cell(0, 0)
    right_cell = table.cell(0, 1)
    _set_cell_margins(left_cell, top=40, left=40, bottom=40, right=40)
    _set_cell_margins(right_cell, top=40, left=40, bottom=40, right=40)

    left_cell.text = ""
    left_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    left_para = left_cell.paragraphs[0]
    _set_para_style(left_para, "body")
    left_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    left_para.paragraph_format.space_after = Pt(0)
    if not _append_inline_math(left_para, latex):
        _append_text_run(left_para, latex, italic=True, font_name=FONT_CAMBRIA)

    right_cell.text = ""
    right_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    right_para = right_cell.paragraphs[0]
    _set_para_style(right_para, "body")
    right_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    right_para.paragraph_format.space_after = Pt(0)
    if number:
        # Strip ALL pipe '|' characters and any existing parentheses
        clean = number.replace("|", "").strip().strip("()").strip()
        if clean:
            _append_text_run(right_para, f"({clean})")

    doc.add_paragraph()


def _add_table(doc: Document, item: dict, state: RenderState) -> None:
    headers = [str(value) for value in (item.get("Headers", []) or item.get("headers", []))]
    rows = [list(map(str, row)) for row in (item.get("Rows", []) or item.get("rows", []))]
    if not headers:
        return

    state.table_number += 1
    title = str(item.get("Title") or item.get("title") or "").strip()

    caption = doc.add_paragraph()
    _set_para_style(caption, "figure_caption")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _append_text_run(caption, f"Table {state.table_number}. ", bold=True)
    if title:
        _append_rich_text(caption, title, base_bold=True, base_italic=True)

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_table_borders(table, enabled=True)
    column_widths = _fit_table_columns(headers, rows)
    _set_table_width_fixed(table, sum(column_widths), column_widths)

    size_pt = 8.0 if len(headers) >= 6 else 9.0

    for col_idx, header in enumerate(headers):
        _fill_cell_text(
            table.rows[0].cells[col_idx],
            header,
            size_pt=size_pt,
            bold=True,
            align=WD_ALIGN_PARAGRAPH.CENTER,
        )

    for row_idx, row_data in enumerate(rows, start=1):
        for col_idx in range(len(headers)):
            value = row_data[col_idx] if col_idx < len(row_data) else ""
            align = WD_ALIGN_PARAGRAPH.CENTER if len(value) <= 18 else WD_ALIGN_PARAGRAPH.LEFT
            _fill_cell_text(
                table.rows[row_idx].cells[col_idx],
                value,
                size_pt=size_pt,
                align=align,
            )

    doc.add_paragraph()


def _add_author_about(doc: Document, config: dict) -> None:
    authors = _parse_author_entries(config)
    if not authors:
        return

    doc.add_paragraph()

    heading = doc.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _append_text_run(heading, "AUTHORS", bold=True, size_pt=10.0)

    for author in authors:
        paragraph = doc.add_paragraph()
        _set_para_style(paragraph, "author_about")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        name_text = author["name"]
        if author["corresponding"]:
            name_text += "*"
        name_run = _append_text_run(
            paragraph,
            name_text,
            bold=True,
            size_pt=10.0,
            font_name=FONT_TIMES,
        )
        if name_run is None:
            continue

        details = []
        if author["department"]:
            details.append(author["department"])
        if author["institution"]:
            details.append(author["institution"])
        if author["city"]:
            details.append(author["city"])
        if author["country"]:
            details.append(author["country"])
        if author["email"]:
            details.append(author["email"])
        if details:
            _append_text_run(paragraph, " – ", size_pt=10.0, font_name=FONT_CENTURY)
            _append_rich_text(paragraph, ", ".join(details), size_pt=10.0, font_name=FONT_CENTURY)

    # *Corresponding author footnote
    if any(a["corresponding"] for a in authors):
        footnote = doc.add_paragraph()
        footnote.alignment = WD_ALIGN_PARAGRAPH.LEFT
        footnote.paragraph_format.space_after = Pt(6)
        _append_text_run(footnote, "*Corresponding author", italic=True,
                         size_pt=8.0, font_name=FONT_CAMBRIA)


def _add_references(doc: Document, config: dict) -> None:
    _refs_raw = config.get("references") or {}
    if isinstance(_refs_raw, list):
        references = _refs_raw
    else:
        references = list(_refs_raw.get("content") or _refs_raw.get("items") or [])
    if not references:
        return

    doc.add_paragraph()

    heading = doc.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _append_text_run(heading, "References", bold=True, size_pt=10.0)

    for index, reference in enumerate(references, start=1):
        ref_text = (
            str(reference.get("text") or reference.get("Text") or "")
            if isinstance(reference, dict)
            else str(reference)
        )
        ref_text = _clean_reference_text(ref_text)
        if not ref_text:
            continue
        paragraph = doc.add_paragraph()
        _set_para_style(paragraph, "references")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _append_text_run(paragraph, f"[{index}] ")
        _append_rich_text(paragraph, ref_text)


def _render_content_item(doc: Document, item: dict, json_path: Path, state: RenderState) -> None:
    item_id = str(item.get("id", "")).lower().strip()
    if item_id == "text":
        text = str(item.get("text", "")).strip()
        if text:
            _body_paragraph(doc, text)
    elif item_id in {"gambar", "image", "figure"}:
        _add_figure(doc, item, json_path, state)
    elif item_id in {"rumus", "formula", "equation"}:
        _add_equation(doc, item)
    elif item_id in {"tabel", "table"}:
        _add_table(doc, item, state)


def _render_subsection(
    doc: Document, subsection: dict, json_path: Path, state: RenderState
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
                _body_paragraph(doc, item)
    elif isinstance(content, str) and content.strip():
        _body_paragraph(doc, content)


def _render_sections(doc: Document, config: dict, json_path: Path, state: RenderState) -> None:
    section_keys = sorted(
        [key for key in config.keys() if re.match(r"^section\d+$", key)],
        key=lambda key: int(key[7:]),
    )

    for section_key in section_keys:
        section = config[section_key]
        title = str(section.get("title", "")).strip()
        if title:
            _add_section_heading(doc, title)

        content = section.get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    _render_content_item(doc, item, json_path, state)
                elif isinstance(item, str) and item.strip():
                    _body_paragraph(doc, item)
        elif isinstance(content, str) and content.strip():
            _body_paragraph(doc, content)

        subsection_keys = sorted(
            [
                key
                for key, value in section.items()
                if isinstance(value, dict) and key.startswith(section_key) and key != section_key
            ]
        )
        for subsection_key in subsection_keys:
            _render_subsection(doc, section[subsection_key], json_path, state)


def build_document(
    json_path: Path = JSON_PATH,
    output_path: Path | None = None,
    template_path: Path = TEMPLATE_PATH,
) -> Path:
    config = json.loads(Path(json_path).read_text(encoding="utf-8"))
    final_output = (
        Path(output_path)
        if output_path is not None
        else Path(json_path).parent / f"{JOURNAL_NAME}_output.docx"
    )
    final_output.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy(str(template_path), str(final_output))
    doc = Document(str(final_output))
    _clear_document_body(doc)

    _add_title(doc, config)
    _add_authors_line(doc, config)
    doc.add_paragraph()
    _embed_sectpr(doc, _build_title_sectpr(), align=WD_ALIGN_PARAGRAPH.CENTER)

    _add_submission_status(doc, config)
    _add_abstract(doc, config)
    _add_keywords(doc, config)

    state = RenderState()
    _render_sections(doc, config, Path(json_path), state)
    _add_acknowledgements(doc, config)
    _add_author_about(doc, config)
    _add_references(doc, config)
    _embed_sectpr(doc, _build_body_sectpr())

    doc.save(str(final_output))
    print(f"Generated: {final_output}")
    return final_output


def main() -> None:
    if len(sys.argv) >= 2:
        json_arg = Path(sys.argv[1])
        output_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
        template_arg = Path(sys.argv[3]) if len(sys.argv) >= 4 else TEMPLATE_PATH
        result = build_document(json_arg, output_arg, template_arg)
        print(f"Selesai: {result}")
        return

    json_files = sorted(
        path
        for path in BASE_DIR.glob("*.json")
        if path.name.lower() not in {"package.json", "tsconfig.json", "settings.json"}
    )
    for json_file in json_files:
        build_document(json_file)


if __name__ == "__main__":
    main()
