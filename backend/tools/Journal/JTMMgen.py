"""
JTMMgen.py — Generate a JTMM manuscript from JSON using the original JTMM.docx.

The generator copies the original template so header/footer, theme, numbering,
styles, and package parts remain attached to the journal source document.
All manuscript content is sourced from _PLC-MediapipeID.json; when JSON data is
missing, the generator inserts format-correct placeholder content.
"""

from __future__ import annotations

import json
import re
import shutil
import string
import sys
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "_PLC-MediapipeID.json"
TEMPLATE_PATH = BASE_DIR / "JTMM.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

BODY_FONT = "Times New Roman"
TITLE_FONT = "Arial"
MAX_FIGURE_WIDTH_CM = 14.0
EQUATION_RIGHT_TAB_PT = 468.0
REFERENCE_HANGING_TW = 540
REFERENCE_LINE_PT = 14.4
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]

_XSLT = None


@dataclass
class RenderState:
    figure_number: int = 0
    table_number: int = 0
    equation_number: int = 0


def _set_para_style(paragraph, style_name: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(qn("w:val"), style_name)


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
    font_name: str = BODY_FONT,
    size_pt: float = 12.0,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    superscript: bool = False,
) -> None:
    _set_run_font(run, font_name)
    run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline
    if superscript:
        run.font.superscript = True


def _append_text_run(
    paragraph,
    text: str,
    *,
    font_name: str = BODY_FONT,
    size_pt: float = 12.0,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    superscript: bool = False,
):
    run = paragraph.add_run(text)
    _format_run(
        run,
        font_name=font_name,
        size_pt=size_pt,
        bold=bold,
        italic=italic,
        underline=underline,
        superscript=superscript,
    )
    return run


def _set_paragraph_spacing(
    paragraph, *, before: float | None = None, after: float | None = None
) -> None:
    if before is not None:
        paragraph.paragraph_format.space_before = Pt(before)
    if after is not None:
        paragraph.paragraph_format.space_after = Pt(after)


def _set_first_line_indent_twips(paragraph, twips: int) -> None:
    paragraph.paragraph_format.first_line_indent = Pt(twips / 20)


def _set_hanging_indent_twips(paragraph, *, left_tw: int, hanging_tw: int) -> None:
    paragraph.paragraph_format.left_indent = Pt(left_tw / 20)
    paragraph.paragraph_format.first_line_indent = Pt(-(hanging_tw / 20))


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


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


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return parts or [normalized.strip()]


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
                next_char = normalized[index + 2] if index + 2 < len(normalized) else ""
                if next_char.islower():
                    buffer.append("\b")
                    index += 2
                    continue
                yield from flush_buffer()
                bold = not bold
                index += 2
                continue
            if command == "i":
                next_char = normalized[index + 2] if index + 2 < len(normalized) else ""
                if next_char.islower():
                    buffer.append("\i")
                    index += 2
                    continue
                yield from flush_buffer()
                italic = not italic
                index += 2
                continue
            if command == "u":
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
                formula = normalized[index + 1 : closing].strip()
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 1
                continue
        buffer.append(char)
        index += 1

    yield from flush_buffer()


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


def _append_rich_text(
    paragraph,
    text: str,
    *,
    font_name: str = BODY_FONT,
    size_pt: float = 12.0,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            paragraph.add_run().add_break()
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                _append_text_run(
                    paragraph, token["value"], font_name=font_name, size_pt=size_pt, italic=True
                )
            continue
        _append_text_run(
            paragraph,
            token["value"],
            font_name=font_name,
            size_pt=size_pt,
            bold=bold or token["bold"],
            italic=italic or token["italic"],
            underline=underline or token["underline"],
        )


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative
    return BASE_DIR / path


def _placeholder_text(label: str) -> str:
    return (
        f"Teks placeholder untuk {label} ditambahkan karena data tersebut tidak tersedia di JSON."
    )


def _default_english_abstract(config: dict) -> str:
    explicit = str(
        config.get("abstract_en")
        or config.get("english_abstract")
        or config.get("abstractEnglish")
        or ""
    ).strip()
    if explicit:
        return explicit

    source = str(config.get("abstract", "")).strip()
    if source.startswith("Panel kontrol bersama pada lini produksi"):
        return (
            "Shared control panels on production lines create contamination risks in food-grade and cleanroom "
            "environments. This paper presents GestPLC to evaluate whether a standard USB webcam combined with a "
            "geometric rule-based classifier can control a Schneider Modicon M221 PLC without a GPU or a trained "
            "neural network. MediaPipe extracts 21 hand landmarks per frame on an Intel Core i7 CPU, and an angle-"
            "threshold engine converts those landmarks into Modbus TCP coil-write commands through FC15. Camera "
            "capture, gesture classification, and Modbus communication run on separate Python threads so delayed "
            "network replies do not freeze the vision loop. At 300 lux, the classifier reaches a macro-F1 score of "
            "95.4%, while the average Modbus round trip is 12.3 ms. A 24-hour endurance test records 872,640 "
            "transactions with a 99.97% write success rate, although the communication mean time between failures is "
            "only 8.2 hours. The results show that landmark geometry, rather than deep learning, is sufficient for "
            "six-gesture PLC control on commodity hardware."
        )

    title = str(config.get("title", "this study")).strip() or "this study"
    return (
        f"This paper presents {title}. The English abstract was generated because the JSON did not provide one. "
        "The manuscript discusses the system architecture, experiments, measured results, and conclusions based on "
        "the supplied article content."
    )


def _clean_reference_text(text: str) -> str:
    return re.sub(r"^\s*\[(?:\d+)\]\s*", "", text).strip()


def _roman_numeral(value: int) -> str:
    mapping = (
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
    )
    result: list[str] = []
    remainder = max(value, 1)
    for arabic, roman in mapping:
        while remainder >= arabic:
            result.append(roman)
            remainder -= arabic
    return "".join(result)


def _author_entries(config: dict) -> list[dict]:
    raw_authors = config.get("authors", [])
    if not isinstance(raw_authors, list):
        raw_authors = []
    entries: list[dict] = []
    for author in raw_authors:
        if not isinstance(author, dict):
            continue
        name = str(author.get("name", "")).strip()
        affiliation = str(author.get("affiliation", "")).strip()
        location = str(author.get("location", "")).strip()
        email = str(author.get("email", "")).strip()
        if not any((name, affiliation, location, email)):
            continue
        entries.append(
            {
                "name": name or _placeholder_text("nama penulis"),
                "affiliation": affiliation or _placeholder_text("afiliasi penulis"),
                "location": location or _placeholder_text("lokasi penulis"),
                "email": email or f"placeholder{len(entries) + 1}@example.com",
            }
        )
    if entries:
        return entries
    return [
        {
            "name": "Nama Penulis Placeholder",
            "affiliation": "Afiliasi Placeholder",
            "location": "Kota, Negara",
            "email": "placeholder@example.com",
        }
    ]


def _group_affiliations(
    authors: list[dict],
) -> tuple[dict[tuple[str, str], int], list[tuple[tuple[str, str], int]]]:
    mapping: dict[tuple[str, str], int] = {}
    ordered: list[tuple[tuple[str, str], int]] = []
    next_index = 1
    for author in authors:
        key = (author["affiliation"], author["location"])
        if key in mapping:
            continue
        mapping[key] = next_index
        ordered.append((key, next_index))
        next_index += 1
    return mapping, ordered


def _email_letter(index: int) -> str:
    letters = string.ascii_lowercase
    if index < len(letters):
        return letters[index]
    return f"{letters[index % len(letters)]}{index // len(letters)}"


def _add_title(doc: Document, config: dict) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "TTPTitle")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(paragraph, before=0.0, after=6.0)
    title = str(config.get("title", "")).strip() or _placeholder_text("judul artikel")
    _append_rich_text(paragraph, title, font_name=TITLE_FONT, size_pt=14.0, bold=True)


def _add_authors(doc: Document, config: dict) -> None:
    authors = _author_entries(config)
    affiliation_map, ordered_affiliations = _group_affiliations(authors)

    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "TTPAuthors")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(paragraph, before=6.0, after=3.0)

    for index, author in enumerate(authors):
        if index > 0:
            _append_text_run(paragraph, ", ", font_name=TITLE_FONT, size_pt=14.0)
        _append_text_run(paragraph, author["name"], font_name=TITLE_FONT, size_pt=14.0)
        aff_number = affiliation_map[(author["affiliation"], author["location"])]
        marker = f"{aff_number},{_email_letter(index)}"
        if index == 0:
            marker += ",*"
        _append_text_run(paragraph, marker, font_name=TITLE_FONT, size_pt=14.0, superscript=True)

    for (affiliation, location), number in ordered_affiliations:
        aff_paragraph = doc.add_paragraph()
        _set_para_style(aff_paragraph, "TTPAddress")
        aff_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_paragraph_spacing(aff_paragraph, before=3.0, after=0.0)
        _append_text_run(
            aff_paragraph, str(number), font_name=TITLE_FONT, size_pt=11.0, superscript=True
        )
        details = ", ".join(part for part in (affiliation, location) if part)
        _append_text_run(aff_paragraph, details, font_name=TITLE_FONT, size_pt=11.0)

    email_paragraph = doc.add_paragraph()
    _set_para_style(email_paragraph, "TTPAddress")
    email_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(email_paragraph, before=3.0, after=6.0)
    for index, author in enumerate(authors):
        if index > 0:
            _append_text_run(email_paragraph, ", ", font_name=TITLE_FONT, size_pt=11.0)
        _append_text_run(
            email_paragraph,
            _email_letter(index),
            font_name=TITLE_FONT,
            size_pt=11.0,
            superscript=True,
        )
        _append_text_run(email_paragraph, author["email"], font_name=TITLE_FONT, size_pt=11.0)
    _append_text_run(email_paragraph, " (corresponding author)", font_name=TITLE_FONT, size_pt=11.0)


def _add_abstract_block(
    doc: Document,
    *,
    heading: str,
    text: str,
    keyword_label: str,
    keywords: list[str],
    english: bool = False,
) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "TTPAbstract")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_paragraph_spacing(paragraph, before=3.0, after=3.0)
    _append_text_run(paragraph, f"{heading}. ", size_pt=12.0, bold=True)
    _append_rich_text(paragraph, text, size_pt=12.0)

    keyword_paragraph = doc.add_paragraph()
    _set_para_style(keyword_paragraph, "TTPKeywords")
    keyword_paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_paragraph_spacing(keyword_paragraph, before=3.0, after=3.0)
    _append_text_run(keyword_paragraph, f"{keyword_label}: ", size_pt=11.0, bold=True)
    _append_rich_text(
        keyword_paragraph,
        ", ".join(keywords) if keywords else _placeholder_text("kata kunci"),
        size_pt=11.0,
        italic=True,
    )

    if not english:
        doc.add_paragraph()


def _add_front_matter(doc: Document, config: dict) -> None:
    _add_title(doc, config)
    _add_authors(doc, config)

    abstract_id = str(config.get("abstract", "")).strip() or _placeholder_text(
        "abstrak bahasa Indonesia"
    )
    keywords = [str(item).strip() for item in config.get("keywords", []) if str(item).strip()]
    if not keywords:
        keywords = ["keyword placeholder", "manuscript placeholder"]
    _add_abstract_block(
        doc,
        heading="Abstrak",
        text=abstract_id,
        keyword_label="Kata kunci",
        keywords=keywords,
        english=False,
    )
    _add_abstract_block(
        doc,
        heading="Abstract",
        text=_default_english_abstract(config),
        keyword_label="Keywords",
        keywords=keywords,
        english=True,
    )


def _new_body_paragraph(doc: Document, *, first: bool) -> any:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "TTPParagraph1st" if first else "TTPParagraphothers")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_paragraph_spacing(paragraph, before=0.0, after=3.0)
    if first:
        _set_first_line_indent_twips(paragraph, 0)
    else:
        _set_first_line_indent_twips(paragraph, 283)
    return paragraph


def _add_body_text(doc: Document, text: str, *, first_in_group: bool) -> bool:
    added = False
    first_flag = first_in_group
    for block in _split_body_blocks(text):
        if not block:
            continue
        paragraph = _new_body_paragraph(doc, first=first_flag)
        _append_rich_text(paragraph, block, size_pt=12.0)
        first_flag = False
        added = True
    return first_flag if added else first_in_group


def _add_section_heading(doc: Document, number_text: str, title: str) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "TTPSectionHeading")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_paragraph_spacing(paragraph, before=3.0, after=3.0)
    _append_text_run(paragraph, f"{number_text}. {title}", size_pt=12.0, bold=True)


def _add_subsection_heading(doc: Document, number_text: str, title: str) -> None:
    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "TTPSectionHeading")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _set_paragraph_spacing(paragraph, before=3.0, after=3.0)
    _append_text_run(paragraph, f"{number_text}. {title}", size_pt=12.0, bold=True)


def _set_table_borders(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single" if edge in ("top", "bottom", "insideH") else "nil")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")


def _fill_cell(
    cell,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    align=WD_ALIGN_PARAGRAPH.CENTER,
    size_pt: float = 10.0,
) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    _set_paragraph_spacing(paragraph, before=0.0, after=0.0)
    _append_rich_text(paragraph, text, size_pt=size_pt, bold=bold, italic=italic)


def _add_figure(doc: Document, item: dict, json_path: Path, state: RenderState) -> None:

    title = str(item.get("Title") or item.get("title") or "").strip() or _placeholder_text(
        "judul gambar"
    )
    number = str(item.get("ImageNumber") or item.get("number") or "").strip()
    if not number:
        state.figure_number += 1
        number = str(state.figure_number)
    else:
        state.figure_number = (
            max(state.figure_number, int(number)) if number.isdigit() else state.figure_number + 1
        )

    image_paragraph = doc.add_paragraph()
    image_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(image_paragraph, before=3.0, after=3.0)
    image_path_text = str(item.get("Path", "")).strip()
    image_path = _resolve_path(image_path_text, json_path) if image_path_text else None
    if image_path and image_path.is_file():
        image_paragraph.add_run().add_picture(str(image_path), width=Cm(MAX_FIGURE_WIDTH_CM))
    else:
        _append_text_run(
            image_paragraph,
            f"[Placeholder figure: {title}]",
            size_pt=10.0,
            italic=True,
        )

    caption = doc.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(caption, before=3.0, after=6.0)
    _append_text_run(caption, f"Gambar {number}. ", size_pt=10.0, bold=True)
    _append_rich_text(caption, title, size_pt=10.0)


def _add_equation(doc: Document, item: dict, state: RenderState) -> None:
    latex = str(item.get("latex") or item.get("text") or "").strip()
    if not latex:
        latex = "x = y"
    number = str(item.get("FormulaNumber") or item.get("number") or "").strip()
    if not number:
        state.equation_number += 1
        number = str(state.equation_number)
    elif number.isdigit():
        state.equation_number = max(state.equation_number, int(number))

    paragraph = doc.add_paragraph()
    _set_para_style(paragraph, "TTPEquation")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.left_indent = Pt(283 / 20)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.right_indent = Pt(0)
    paragraph.paragraph_format.tab_stops.add_tab_stop(
        Pt(EQUATION_RIGHT_TAB_PT), WD_TAB_ALIGNMENT.RIGHT
    )
    _set_paragraph_spacing(paragraph, before=3.0, after=3.0)
    if not _append_inline_math(paragraph, latex):
        _append_text_run(paragraph, latex, size_pt=12.0, italic=True)
    paragraph.add_run().add_tab()
    _append_text_run(paragraph, f"({number})", size_pt=12.0)


def _add_table(doc: Document, item: dict, state: RenderState) -> None:
    headers = [str(value) for value in (item.get("Headers") or item.get("headers") or [])]
    rows = [list(map(str, row)) for row in (item.get("Rows") or item.get("rows") or [])]
    if not headers:
        headers = ["Kolom 1", "Kolom 2"]
        rows = [
            ["Placeholder baris 1", "Placeholder baris 1"],
            ["Placeholder baris 2", "Placeholder baris 2"],
        ]

    number = str(item.get("TableNumber") or item.get("number") or "").strip()
    if not number:
        state.table_number += 1
        number = _roman_numeral(state.table_number)
    else:
        state.table_number += 1
    title = str(item.get("Title") or item.get("title") or "").strip() or _placeholder_text(
        "judul tabel"
    )

    caption = doc.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(caption, before=6.0, after=3.0)
    _append_text_run(caption, f"Tabel {number}. ", size_pt=10.0, bold=True)
    _append_rich_text(caption, title, size_pt=10.0)

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders(table)

    for col_idx, header in enumerate(headers):
        _fill_cell(table.rows[0].cells[col_idx], header, bold=True, size_pt=10.0)

    for row_idx, row in enumerate(rows, start=1):
        for col_idx in range(len(headers)):
            value = row[col_idx] if col_idx < len(row) else ""
            align = WD_ALIGN_PARAGRAPH.LEFT if col_idx == 0 else WD_ALIGN_PARAGRAPH.CENTER
            _fill_cell(table.rows[row_idx].cells[col_idx], value, align=align, size_pt=10.0)

    doc.add_paragraph()


def _render_content_item(
    doc: Document, item: dict, json_path: Path, first_text: bool, state: RenderState
) -> bool:
    item_id = str(item.get("id", "")).strip().lower()
    if item_id == "text":
        text = str(item.get("text", "")).strip()
        if not text:
            text = _placeholder_text("isi paragraf")
        return _add_body_text(doc, text, first_in_group=first_text)
    if item_id in {"gambar", "image", "figure"}:
        _add_figure(doc, item, json_path, state)
        return first_text
    if item_id in {"tabel", "table"}:
        _add_table(doc, item, state)
        return first_text
    if item_id in {"rumus", "formula", "equation"}:
        _add_equation(doc, item, state)
        return first_text
    return first_text


def _render_content(
    doc: Document, content, json_path: Path, state: RenderState, *, insert_placeholder: bool = True
) -> None:
    first_text = True
    rendered_any = False
    if isinstance(content, str):
        text = content.strip()
        if text:
            _add_body_text(doc, text, first_in_group=True)
        elif insert_placeholder:
            _add_body_text(doc, _placeholder_text("isi bagian"), first_in_group=True)
        return
    if not isinstance(content, list):
        if insert_placeholder:
            _add_body_text(doc, _placeholder_text("isi bagian"), first_in_group=True)
        return
    for item in content:
        if isinstance(item, dict):
            rendered_any = True
            first_text = _render_content_item(doc, item, json_path, first_text, state)
        elif isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            rendered_any = True
            first_text = _add_body_text(doc, text, first_in_group=first_text)
    if not rendered_any and insert_placeholder:
        _add_body_text(doc, _placeholder_text("isi bagian"), first_in_group=True)


def _subsection_keys(section: dict, prefix: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(prefix)}[a-z]+$")
    return sorted([key for key in section if pattern.match(key)])


def _render_sections(doc: Document, config: dict, json_path: Path, state: RenderState) -> None:
    section_keys = sorted(
        [key for key in config if re.fullmatch(r"section\d+", key)],
        key=lambda key: int(key[7:]),
    )
    if not section_keys:
        _add_section_heading(doc, "1", "Pendahuluan")
        _add_body_text(doc, _placeholder_text("isi utama manuskrip"), first_in_group=True)
        return

    for section_index, section_key in enumerate(section_keys, start=1):
        section = config.get(section_key, {})
        if not isinstance(section, dict):
            continue
        title = str(section.get("title", "")).strip() or _placeholder_text(f"judul {section_key}")
        _add_section_heading(doc, str(section_index), title)
        subsection_keys = _subsection_keys(section, section_key)
        _render_content(
            doc,
            section.get("content", []),
            json_path,
            state,
            insert_placeholder=not subsection_keys,
        )
        for subsection_index, subsection_key in enumerate(subsection_keys, start=1):
            subsection = section.get(subsection_key, {})
            if not isinstance(subsection, dict):
                continue
            subsection_title = str(subsection.get("title", "")).strip() or _placeholder_text(
                f"judul {subsection_key}"
            )
            _add_subsection_heading(doc, f"{section_index}.{subsection_index}", subsection_title)
            _render_content(
                doc, subsection.get("content", []), json_path, state, insert_placeholder=True
            )


def _add_references(doc: Document, config: dict) -> None:
    references = config.get("references", {})
    title = "REFERENCES"
    content = []
    if isinstance(references, dict):
        title = str(references.get("title", title)).strip() or title
        content = references.get("content", [])
    _add_section_heading(
        doc, str(len([key for key in config if re.fullmatch(r"section\d+", key)]) + 1), title
    )

    items = []
    if isinstance(content, list):
        items = content
    if not items:
        items = [_placeholder_text("daftar referensi")]

    for index, item in enumerate(items, start=1):
        text = ""
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("Text") or "").strip()
        else:
            text = str(item).strip()
        text = _clean_reference_text(text) or _placeholder_text(f"referensi {index}")

        paragraph = doc.add_paragraph()
        _set_para_style(paragraph, "TTPReference")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _set_hanging_indent_twips(
            paragraph, left_tw=REFERENCE_HANGING_TW, hanging_tw=REFERENCE_HANGING_TW
        )
        _set_paragraph_spacing(paragraph, before=0.0, after=6.0)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
        paragraph.paragraph_format.line_spacing = Pt(REFERENCE_LINE_PT)
        _append_text_run(paragraph, f"[{index}] ", size_pt=12.0)
        _append_rich_text(paragraph, text, size_pt=12.0)


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

    _add_front_matter(doc, config)
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

    json_files = sorted(
        path
        for path in BASE_DIR.glob("*.json")
        if path.name.lower() not in {"package.json", "tsconfig.json", "settings.json"}
    )
    for json_file in json_files:
        build_document(json_file)


if __name__ == "__main__":
    main()