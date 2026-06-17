"""
AMORIgen.py — Generator dokumen AMORI dari JSON.

Menggunakan AMORI.docx sebagai template asli agar header, footer,
numbering, styles, dan package parts tetap mengikuti dokumen sumber.
Semua konten diambil dari _PLC-MediapipeID.json.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "_PLC-MediapipeID.json"
TEMPLATE_PATH = BASE_DIR / "AMORI.docx"
OUTPUT_DOCX = BASE_DIR / "AMORI_output.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MAX_FIGURE_WIDTH_CM = 14.5
LEFT_TAB_PT = 171.0
RIGHT_TAB_PT = 468.0
BODY_FONT = "Times New Roman"

NS_MAP_STRICT = {
    b"http://purl.oclc.org/ooxml/wordprocessingml/main":
        b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    b"http://purl.oclc.org/ooxml/officeDocument/relationships":
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/drawingml/main":
        b"http://schemas.openxmlformats.org/drawingml/2006/main",
    b"http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing":
        b"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    b"http://purl.oclc.org/ooxml/officeDocument/math":
        b"http://schemas.openxmlformats.org/officeDocument/2006/math",
}

XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]

STYLE_XML_ID = {
    "body": "WP",
    "heading1": "Heading1",
    "figurecaption": "figurecaption",
    "tableheading": "TableHeading",
}

_XSLT = None


@dataclass
class RenderState:
    table_number: int = 0
    figure_number: int = 0


def _strict_to_trans(data: bytes) -> bytes:
    for old, new in NS_MAP_STRICT.items():
        data = data.replace(old, new)
    return data


def _pt_to_twips(value: float) -> int:
    return int(round(value * 20))


def _set_para_style(paragraph, style_name: str) -> None:
    xml_id = STYLE_XML_ID.get(style_name.lower(), style_name)
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(qn("w:val"), xml_id)


def _set_run_font(run, font_name: str = BODY_FONT) -> None:
    run.font.name = font_name
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def _format_run(run, *, size_pt: float, bold: bool | None = None,
                italic: bool | None = None, underline: bool | None = None,
                superscript: bool = False, font_name: str = BODY_FONT) -> None:
    _set_run_font(run, font_name=font_name)
    run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline
    if superscript:
        run.font.superscript = True


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


def _set_para_run_defaults(paragraph, *, size_pt: float,
                           bold: bool = False, lang: str | None = None) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    rpr = ppr.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        ppr.append(rpr)
    if bold:
        b = rpr.find(qn("w:b"))
        if b is None:
            b = OxmlElement("w:b")
            rpr.append(b)
    sz = rpr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rpr.append(sz)
    sz.set(qn("w:val"), str(int(round(size_pt * 2))))
    sz_cs = rpr.find(qn("w:szCs"))
    if sz_cs is None:
        sz_cs = OxmlElement("w:szCs")
        rpr.append(sz_cs)
    sz_cs.set(qn("w:val"), str(int(round(size_pt * 2))))
    if lang:
        lang_el = rpr.find(qn("w:lang"))
        if lang_el is None:
            lang_el = OxmlElement("w:lang")
            rpr.append(lang_el)
        lang_el.set(qn("w:val"), lang)


def _add_left_tab(paragraph, position_pt: float = LEFT_TAB_PT) -> None:
    paragraph.paragraph_format.tab_stops.add_tab_stop(Pt(position_pt))


def _add_right_tab(paragraph, position_pt: float = RIGHT_TAB_PT) -> None:
    paragraph.paragraph_format.tab_stops.add_tab_stop(
        Pt(position_pt), WD_TAB_ALIGNMENT.RIGHT
    )


def _set_paragraph_spacing(paragraph, *, before: float | None = None,
                           after: float | None = None) -> None:
    if before is not None:
        paragraph.paragraph_format.space_before = Pt(before)
    if after is not None:
        paragraph.paragraph_format.space_after = Pt(after)


def _set_hanging_indent(paragraph, *, left_pt: float, hanging_pt: float) -> None:
    paragraph.paragraph_format.left_indent = Pt(left_pt)
    paragraph.paragraph_format.first_line_indent = Pt(-hanging_pt)


def _set_hanging_indent_twips(paragraph, *, left_tw: int, hanging_tw: int) -> None:
    paragraph.paragraph_format.left_indent = Pt(left_tw / 20)
    paragraph.paragraph_format.first_line_indent = Pt(-(hanging_tw / 20))


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _extract_inline_sectpr(doc: Document):
    for paragraph in doc.paragraphs:
        ppr = paragraph._p.pPr
        if ppr is None:
            continue
        sectpr = ppr.find(qn("w:sectPr"))
        if sectpr is not None:
            return copy.deepcopy(sectpr)
    return None


def _append_section_break(doc: Document, sectpr) -> None:
    paragraph = doc.add_paragraph()
    ppr = paragraph._p.get_or_add_pPr()
    # sectpr is already a deep copy from _extract_inline_sectpr, don't copy again
    # Use insert to ensure proper placement in pPr
    if sectpr is not None:
        # Remove sectpr from its current parent if any
        parent = sectpr.getparent()
        if parent is not None:
            parent.remove(sectpr)
        ppr.append(sectpr)


def _copy_headers_from_template(template_path: Path, output_path: Path) -> None:
    """Copy headers and footers from template to output document to preserve them."""
    template_doc = Document(str(template_path))
    output_doc = Document(str(output_path))

    # Copy headers from each template section to corresponding output section
    for template_section, output_section in zip(template_doc.sections, output_doc.sections):
        # Copy header content
        template_header_element = template_section.header._element
        output_header_element = output_section.header._element

        # Clear output header content (keep the element, just clear children)
        for child in list(output_header_element):
            output_header_element.remove(child)

        # Copy all children from template header to output header
        for child in template_header_element:
            output_header_element.append(copy.deepcopy(child))

        # Copy footer content
        template_footer_element = template_section.footer._element
        output_footer_element = output_section.footer._element

        # Clear output footer content
        for child in list(output_footer_element):
            output_footer_element.remove(child)

        # Copy all children from template footer to output footer
        for child in template_footer_element:
            output_footer_element.append(copy.deepcopy(child))

    output_doc.save(str(output_path))


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


def _append_text_run(paragraph, text: str, *, size_pt: float,
                     bold: bool = False, italic: bool = False,
                     underline: bool = False) -> None:
    if not text:
        return
    run = paragraph.add_run(text)
    _format_run(run, size_pt=size_pt, bold=bold, italic=italic, underline=underline)


def _append_line_break(paragraph) -> None:
    paragraph.add_run().add_break()


def _normalize_text_commands(text: str) -> str:
    # Replace literal \n → newline, but ONLY when not followed by a-z
    # (LaTeX commands like \nu, \nabla, \neg, \notin must be preserved).
    text = re.sub(r'\\n(?![a-z])', '\n', text)
    # Same for \t — preserve \tau, \theta, \times, \tan, \text etc.
    text = re.sub(r'\\t(?![a-z])', '\t', text)
    # Convert Markdown bold/italic to \b..\b / \i..\i toggle format
    text = re.sub(r'\*\*(.+?)\*\*', r'\\b\1\\b', text, flags=re.DOTALL)
    text = re.sub(r'\*([^*\n]+?)\*', r'\\i\1\\i', text)
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
        if char == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                yield from flush_buffer()
                formula = normalized[index + 1:closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 1
                continue
        buffer.append(char)
        index += 1

    yield from flush_buffer()


def _append_rich_text(paragraph, text: str, *, size_pt: float,
                      bold: bool = False, italic: bool = False,
                      underline: bool = False) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            _append_line_break(paragraph)
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                _append_text_run(paragraph, token["value"], size_pt=size_pt, italic=True)
            continue
        _append_text_run(
            paragraph,
            token["value"],
            size_pt=size_pt,
            bold=bold or token["bold"],
            italic=italic or token["italic"],
            underline=underline or token["underline"],
        )


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    blocks = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return blocks or [normalized.strip()]


def _add_symbol_separator(paragraph) -> None:
    run = paragraph.add_run()
    _format_run(run, size_pt=11.0, bold=True, italic=True)
    sym = OxmlElement("w:sym")
    sym.set(qn("w:font"), "Symbol")
    sym.set(qn("w:char"), "F0BE")
    run._r.append(sym)


def _add_title(doc: Document, config: dict) -> None:
    paragraph = doc.add_paragraph()
    _add_left_tab(paragraph)
    _set_para_run_defaults(paragraph, size_pt=10.0, lang="id-ID")
    title = str(config.get("title", "")).strip()
    run = paragraph.add_run(title)
    _format_run(run, size_pt=24.0)


def _parse_author_entries(config: dict) -> list[dict]:
    authors = config.get("authors", [])
    if not isinstance(authors, list):
        return []
    entries = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        entries.append({
            "name": str(author.get("name", "")).strip(),
            "affiliation": str(author.get("affiliation", "")).strip(),
            "location": str(author.get("location", "")).strip(),
            "email": str(author.get("email", "")).strip(),
        })
    return [entry for entry in entries if entry["name"]]


def _add_authors(doc: Document, config: dict) -> None:
    entries = _parse_author_entries(config)
    if not entries:
        return

    doc.add_paragraph()

    author_para = doc.add_paragraph()
    _set_para_run_defaults(author_para, size_pt=11.0, lang="id-ID")
    for index, entry in enumerate(entries, start=1):
        if index > 1:
            _append_text_run(author_para, ", ", size_pt=11.0)
        _append_text_run(author_para, entry["name"], size_pt=11.0)
        sup = author_para.add_run(str(index))
        _format_run(sup, size_pt=11.0, superscript=True)
        if index == 1:
            marker = author_para.add_run("*")
            _format_run(marker, size_pt=11.0, superscript=True)

    doc.add_paragraph()

    for index, entry in enumerate(entries, start=1):
        paragraph = doc.add_paragraph()
        _set_para_run_defaults(paragraph, size_pt=11.0, lang="id-ID")
        _append_text_run(paragraph, f"[{index}] ", size_pt=11.0)
        details = [part for part in (entry["affiliation"], entry["location"]) if part]
        text = ", ".join(details)
        if entry["email"]:
            if text:
                text = f"{text}. E-mail: {entry['email']}"
            else:
                text = f"E-mail: {entry['email']}"
        _append_text_run(paragraph, text, size_pt=11.0)

    first_email = next((entry["email"] for entry in entries if entry["email"]), "")
    if first_email:
        doc.add_paragraph()
        paragraph = doc.add_paragraph()
        _set_para_run_defaults(paragraph, size_pt=11.0)
        _append_text_run(paragraph, f"Email of corresponding: {first_email}", size_pt=11.0)


def _add_submission_metadata(doc: Document) -> None:
    doc.add_paragraph()

    paragraph = doc.add_paragraph()
    _set_para_run_defaults(paragraph, size_pt=11.0)
    _append_text_run(paragraph, "Present Address:", size_pt=11.0)

    paragraph = doc.add_paragraph()
    _set_para_run_defaults(paragraph, size_pt=11.0)
    _append_text_run(
        paragraph,
        "Magister Tower, Jl Informatika No. 10, Surabaya 60111, Indonesia",
        size_pt=11.0,
    )

    doc.add_paragraph()

    paragraph = doc.add_paragraph()
    _set_para_run_defaults(paragraph, size_pt=11.0)
    _append_text_run(paragraph, "Received: xx Month xxxx", size_pt=11.0)
    paragraph.add_run().add_tab()
    _append_text_run(paragraph, "Revised: xx Month xxxx", size_pt=11.0)
    paragraph.add_run().add_tab()
    _append_text_run(paragraph, "Accepted: xx Month xxxx", size_pt=11.0)


def _add_abstract(doc: Document, config: dict) -> None:
    abstract = str(config.get("abstract", "")).strip()
    if not abstract:
        return

    doc.add_paragraph()
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _add_left_tab(paragraph)
    _set_para_run_defaults(paragraph, size_pt=11.0, bold=True)
    _append_text_run(paragraph, "Abstract", size_pt=11.0, bold=True)
    _add_symbol_separator(paragraph)
    _append_text_run(paragraph, " ", size_pt=11.0, bold=True)
    _append_rich_text(paragraph, abstract, size_pt=11.0, bold=True)


def _add_keywords(doc: Document, config: dict) -> None:
    keywords = [str(item).strip() for item in config.get("keywords", []) if str(item).strip()]
    if not keywords:
        return

    doc.add_paragraph()
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _add_left_tab(paragraph)
    _set_para_run_defaults(paragraph, size_pt=11.0, bold=True)
    _append_text_run(paragraph, "Keywords", size_pt=11.0, bold=True)
    _add_symbol_separator(paragraph)
    _append_rich_text(paragraph, ", ".join(keywords), size_pt=11.0)


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative
    return BASE_DIR / path


def _body_paragraph(doc: Document, text: str) -> None:
    for block in _split_body_blocks(text):
        paragraph = doc.add_paragraph()
        _set_para_style(paragraph, "body")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _set_paragraph_spacing(paragraph, after=3.0)
        _append_rich_text(paragraph, block, size_pt=11.0)


def _add_section_heading(doc: Document, title: str) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "heading1")
    _set_num_pr(paragraph, num_id=38, ilvl=0)
    _set_hanging_indent(paragraph, left_pt=18.0, hanging_pt=18.0)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _append_text_run(paragraph, title.upper(), size_pt=11.0)


def _add_subsection_heading(doc: Document, title: str) -> None:
    paragraph = doc.add_paragraph()
    _set_num_pr(paragraph, num_id=38, ilvl=1)
    _set_hanging_indent(paragraph, left_pt=36.0, hanging_pt=18.0)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _set_paragraph_spacing(paragraph, before=6.0, after=3.0)
    _append_text_run(paragraph, title, size_pt=11.0)


def _set_table_full_borders(table) -> None:
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
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")


def _format_cell_paragraph(paragraph, *, size_pt: float, bold: bool = False,
                           italic: bool = False,
                           align=WD_ALIGN_PARAGRAPH.CENTER) -> None:
    paragraph.alignment = align
    _set_paragraph_spacing(paragraph, after=0.0)
    for run in paragraph.runs:
        _format_run(run, size_pt=size_pt, bold=bold, italic=italic)


def _fill_cell_text(cell, text: str, *, size_pt: float, bold: bool = False,
                    italic: bool = False,
                    align=WD_ALIGN_PARAGRAPH.CENTER) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    _append_rich_text(paragraph, text, size_pt=size_pt, bold=bold, italic=italic)


def _add_figure(doc: Document, item: dict, json_path: Path,
                state: RenderState) -> None:
    path_text = str(item.get("Path", "")).strip()
    title = str(item.get("Title", "")).strip()
    prompt = str(item.get("Prompt", "")).strip()
    width_cm = item.get("WidthCm")
    try:
        width_cm = float(width_cm) if width_cm is not None else MAX_FIGURE_WIDTH_CM
    except (TypeError, ValueError):
        width_cm = MAX_FIGURE_WIDTH_CM
    width_cm = min(max(width_cm, 1.0), MAX_FIGURE_WIDTH_CM)

    image_added = False
    if path_text:
        image_path = _resolve_path(path_text, json_path)
        if image_path.is_file():
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _set_paragraph_spacing(paragraph, before=3.0, after=1.5)
            paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
            image_added = True

    # ALWAYS insert AI prompt if available (unconditional)
    if prompt:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_paragraph_spacing(paragraph, before=3.0, after=1.5)
        # Include title in prompt for audit validation
        prompt_text = f"{title} - {prompt}" if title else prompt
        run = paragraph.add_run(f"[PROMPT UNTUK AI GAMBAR: {prompt_text}]")
        _format_run(run, size_pt=10.0, italic=True)
        run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)

    if title:
        state.figure_number += 1
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _append_text_run(paragraph, f"Figure {state.figure_number}. ", size_pt=11.0, bold=True)
        _append_rich_text(paragraph, title, size_pt=11.0)


def _add_equation(doc: Document, item: dict) -> None:
    latex = str(item.get("latex") or item.get("text") or "").strip()
    if not latex:
        return
    number = str(item.get("FormulaNumber") or item.get("NumberiOrLetter") or "").strip()

    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "body")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_paragraph_spacing(paragraph, after=3.0)
    _add_right_tab(paragraph)
    if not _append_inline_math(paragraph, latex):
        _append_text_run(paragraph, latex, size_pt=11.0, italic=True)
    _append_text_run(paragraph, " ", size_pt=11.0)
    paragraph.add_run().add_tab()
    if number:
        _append_text_run(paragraph, f"({number})", size_pt=11.0)


def _add_table(doc: Document, item: dict, state: RenderState) -> None:
    headers = list(item.get("Headers", []) or item.get("headers", []))
    rows = list(item.get("Rows", []) or item.get("rows", []))
    if not headers:
        return

    state.table_number += 1
    title = str(item.get("Title") or item.get("title") or "").strip()
    caption = doc.add_paragraph()
    _set_para_style(caption, "tableheading")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption_text = f"Table {state.table_number}. {title}" if title else f"Table {state.table_number}."
    _append_text_run(caption, caption_text, size_pt=10.0, bold=True, italic=True)

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_full_borders(table)

    for col_idx, header in enumerate(headers):
        _fill_cell_text(
            table.rows[0].cells[col_idx],
            str(header),
            size_pt=10.0,
            bold=True,
            align=WD_ALIGN_PARAGRAPH.CENTER,
        )

    for row_idx, row_data in enumerate(rows, start=1):
        for col_idx in range(len(headers)):
            value = ""
            if col_idx < len(row_data):
                value = str(row_data[col_idx])
            _fill_cell_text(
                table.rows[row_idx].cells[col_idx],
                value,
                size_pt=10.0,
                align=WD_ALIGN_PARAGRAPH.CENTER,
            )

    doc.add_paragraph()


def _clean_reference_text(text: str) -> str:
    return re.sub(r"^\s*\[\d+\]\s*", "", text).strip()


def _add_references(doc: Document, config: dict) -> None:
    references = list((config.get("references") or {}).get("content", []))
    if not references:
        return

    paragraph = doc.add_paragraph()
    _append_text_run(paragraph, "REFERENCES", size_pt=11.0)

    for index, ref in enumerate(references, start=1):
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _set_hanging_indent_twips(paragraph, left_tw=568, hanging_tw=568)
        _set_paragraph_spacing(paragraph, after=0.0)
        _append_text_run(paragraph, f"[{index}]", size_pt=11.0)
        paragraph.add_run().add_tab()
        ref_text = ""
        if isinstance(ref, dict):
            ref_text = str(ref.get("text") or ref.get("Text") or "")
        else:
            ref_text = str(ref)
        _append_rich_text(paragraph, _clean_reference_text(ref_text), size_pt=11.0)


def _render_content_item(doc: Document, item: dict, json_path: Path,
                         state: RenderState) -> None:
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


def _render_subsection(doc: Document, subsection: dict, json_path: Path,
                       state: RenderState) -> None:
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


def _render_sections(doc: Document, config: dict, json_path: Path,
                     state: RenderState) -> None:
    section_keys = sorted(
        [key for key in config.keys() if key.startswith("section") and key[7:].isdigit()],
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
                key for key, value in section.items()
                if isinstance(value, dict) and key.startswith(section_key) and key != section_key
            ]
        )
        for subsection_key in subsection_keys:
            _render_subsection(doc, section[subsection_key], json_path, state)


def build_document(json_path: Path = JSON_PATH,
                   output_path: Path | None = None,
                   template_path: Path = TEMPLATE_PATH) -> Path:
    config = json.loads(Path(json_path).read_text(encoding="utf-8"))
    final_output = (
        Path(output_path)
        if output_path is not None
        else OUTPUT_DOCX
    )
    final_output.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy(str(template_path), str(final_output))
    doc = Document(str(final_output))
    inline_sectpr = _extract_inline_sectpr(doc)
    if inline_sectpr is None:
        raise RuntimeError("Template AMORI tidak memiliki inline sectPr untuk page/header break.")

    _clear_document_body(doc)

    _add_title(doc, config)
    _add_authors(doc, config)
    _add_submission_metadata(doc)
    _add_abstract(doc, config)
    _add_keywords(doc, config)
    doc.add_paragraph()
    _append_section_break(doc, inline_sectpr)

    state = RenderState()
    _render_sections(doc, config, Path(json_path), state)
    _add_references(doc, config)

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

    # Default: generate single output from default JSON
    result = build_document()
    print(f"Selesai: {result}")


if __name__ == "__main__":
    main()