"""
JTRANSIENTgen.py -- Generate a JTRANSIENT paper from JSON using the original
JTRANSIENT.docx template.

The generator keeps the original template package intact, clones paragraph
formatting from the source DOCX, preserves header/footer/section layout, and
renders the manuscript body from _PLC-MediapipeID.json.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.table import _Cell
from docx.text.paragraph import Paragraph
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "_PLC-MediapipeID.json"
TEMPLATE_PATH = BASE_DIR / "JTRANSIENT.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

BODY_FONT_NAME = "Times New Roman"
BODY_FONT_PT = 10.0
TITLE_FONT_PT = 14.0
AUTHOR_FONT_PT = 12.0
AFFILIATION_FONT_PT = 10.0
CAPTION_FONT_PT = 9.0
TABLE_FONT_NAME = "Arial Narrow"
TABLE_FONT_PT = 8.0
MAX_FIGURE_WIDTH_CM = 7.22
TABLE_TOTAL_WIDTH_TW = 4678

SECTION_SPACE_BEFORE_PT = 3.0
SECTION_SPACE_AFTER_PT = 3.0
SUBSECTION_SPACE_BEFORE_PT = 3.0
SUBSECTION_SPACE_AFTER_PT = 3.0
TABLE_TITLE_BEFORE_PT = 6.0
TABLE_TITLE_AFTER_PT = 3.0
FIGURE_TITLE_BEFORE_PT = 3.0
FIGURE_TITLE_AFTER_PT = 6.0
FIGURE_BEFORE_PT = 3.0
FIGURE_AFTER_PT = 3.0
EQUATION_BEFORE_PT = 3.0
EQUATION_AFTER_PT = 3.0

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]

_XSLT = None
_DRAWING_ID_NEXT = 1
_DOC_PR_PATTERN = re.compile(r'<wp:docPr\b[^>]*\bid="(\d+)"')


@dataclass
class RenderState:
    figure_number: int = 1
    table_number: int = 1
    equation_number: int = 1


def _wq(tag: str) -> str:
    return f"{{{NS_W}}}{tag}"


def _clone_ppr(paragraph: Paragraph) -> etree._Element | None:
    ppr = paragraph._p.find(qn("w:pPr"))
    return deepcopy(ppr) if ppr is not None else None


def _clone_run_rpr(paragraph: Paragraph, run_index: int = 0) -> etree._Element | None:
    runs = paragraph._p.findall(qn("w:r"))
    if run_index >= len(runs):
        return None
    rpr = runs[run_index].find(qn("w:rPr"))
    return deepcopy(rpr) if rpr is not None else None


def _apply_sample_ppr(paragraph: Paragraph, sample_ppr: etree._Element | None) -> None:
    current = paragraph._p.find(qn("w:pPr"))
    if current is not None:
        paragraph._p.remove(current)
    if sample_ppr is not None:
        paragraph._p.insert(0, deepcopy(sample_ppr))


def _apply_sample_rpr(run, sample_rpr: etree._Element | None) -> None:
    current = run._r.find(qn("w:rPr"))
    if current is not None:
        run._r.remove(current)
    if sample_rpr is not None:
        run._r.insert(0, deepcopy(sample_rpr))


def _set_run_font(run, font_name: str) -> None:
    run.font.name = font_name
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def _set_run_format(
    run,
    *,
    font_name: str | None = None,
    size_pt: float | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    superscript: bool | None = None,
) -> None:
    if font_name is not None:
        _set_run_font(run, font_name)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline
    if superscript is not None:
        run.font.superscript = superscript


def _append_run(
    paragraph: Paragraph,
    text: str,
    sample_rpr: etree._Element | None = None,
    *,
    font_name: str | None = None,
    size_pt: float | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    superscript: bool | None = None,
):
    run = paragraph.add_run(text)
    _apply_sample_rpr(run, sample_rpr)
    _set_run_format(
        run,
        font_name=font_name,
        size_pt=size_pt,
        bold=bold,
        italic=italic,
        underline=underline,
        superscript=superscript,
    )
    return run


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _clear_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._element
    for child in list(element):
        if child.tag != qn("w:pPr"):
            element.remove(child)


def _clear_cell(cell: _Cell) -> None:
    tc = cell._tc
    for child in list(tc):
        if child.tag != qn("w:tcPr"):
            tc.remove(child)
    tc.append(OxmlElement("w:p"))


def _new_paragraph(doc: Document, sample_ppr: etree._Element | None = None) -> Paragraph:
    paragraph = doc.add_paragraph()
    if sample_ppr is not None:
        _apply_sample_ppr(paragraph, sample_ppr)
    return paragraph


def _set_paragraph_spacing(
    paragraph: Paragraph, *, before_pt: float | None = None, after_pt: float | None = None
) -> None:
    if before_pt is not None:
        paragraph.paragraph_format.space_before = Pt(before_pt)
    if after_pt is not None:
        paragraph.paragraph_format.space_after = Pt(after_pt)


def _split_text_blocks(text: str) -> list[str]:
    normalized = text.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return parts or [normalized.strip()]


def _iter_rich_tokens(text: str):
    # Normalize newlines and convert Markdown bold/italic to toggle-escape format
    normalized = text.replace("\\n", "\n")
    normalized = re.sub(r"\*\*(.+?)\*\*", r"\\b\1\\b", normalized, flags=re.DOTALL)
    normalized = re.sub(r"\*([^*\n]+?)\*", r"\\i\1\\i", normalized)
    buffer: list[str] = []
    bold = False
    italic = False
    underline = False
    index = 0

    def flush_buffer():
        nonlocal buffer
        value = "".join(buffer)
        buffer = []
        if value:
            yield {
                "kind": "text",
                "value": value,
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
                value = normalized[index + 1 : closing]
                if value:
                    yield {"kind": "math", "value": value}
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


def _set_math_rpr_defaults(rpr: etree._Element, half_points: int = 20) -> None:
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), "Cambria Math")

    size = rpr.find(qn("w:sz"))
    if size is None:
        size = OxmlElement("w:sz")
        rpr.append(size)
    size.set(qn("w:val"), str(half_points))

    size_cs = rpr.find(qn("w:szCs"))
    if size_cs is None:
        size_cs = OxmlElement("w:szCs")
        rpr.append(size_cs)
    size_cs.set(qn("w:val"), str(half_points))


def _normalize_omml_math(omml: etree._Element, half_points: int = 20) -> etree._Element:
    for math_run in omml.findall(f".//{{{MATH_NS}}}r"):
        rpr = math_run.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            math_run.insert(0, rpr)
        _set_math_rpr_defaults(rpr, half_points=half_points)

    for ctrl_pr in omml.findall(f".//{{{MATH_NS}}}ctrlPr"):
        rpr = ctrl_pr.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            ctrl_pr.insert(0, rpr)
        _set_math_rpr_defaults(rpr, half_points=half_points)

    return omml


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


def _append_inline_math(paragraph: Paragraph, latex: str) -> bool:
    omml = _latex_to_omml(latex)
    if omml is None:
        return False
    omml = _normalize_omml_math(omml, half_points=20)
    tag = omml.tag.split("}")[-1] if "}" in omml.tag else omml.tag
    if tag in ("oMath", "oMathPara"):
        paragraph._p.append(omml)
    else:
        wrapper = etree.fromstring(f'<m:oMath xmlns:m="{MATH_NS}"/>')
        wrapper.append(omml)
        paragraph._p.append(wrapper)
    return True


def _append_rich_text(paragraph: Paragraph, text: str, sample_rpr: etree._Element | None) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            paragraph.add_run().add_break()
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                _append_run(paragraph, token["value"], sample_rpr, italic=True)
            continue
        run = _append_run(paragraph, token["value"], sample_rpr)
        if token["bold"]:
            run.bold = True
        if token["italic"]:
            run.italic = True
        if token["underline"]:
            run.underline = True


def _append_table_text(paragraph: Paragraph, text: str, *, bold_default: bool = False) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            paragraph.add_run().add_break()
            continue
        value = token.get("value", "")
        run = paragraph.add_run(value)
        _set_run_format(
            run,
            font_name=TABLE_FONT_NAME,
            size_pt=TABLE_FONT_PT,
            bold=bold_default or token.get("bold", False),
            italic=token.get("italic", False),
            underline=token.get("underline", False),
        )


def _resolve_path(path_text: str, json_path: Path) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate
    relative_to_json = json_path.parent / candidate
    if relative_to_json.exists():
        return relative_to_json
    return BASE_DIR / candidate


def _initialize_drawing_ids(doc: Document) -> None:
    global _DRAWING_ID_NEXT
    max_id = 0
    for part in doc.part.package.parts:
        part_name = str(getattr(part, "partname", ""))
        if not part_name.endswith(".xml"):
            continue
        try:
            xml_text = part.blob.decode("utf-8", errors="ignore")
        except Exception:
            continue
        for match in _DOC_PR_PATTERN.finditer(xml_text):
            max_id = max(max_id, int(match.group(1)))
    _DRAWING_ID_NEXT = max_id + 1


def _next_drawing_id() -> int:
    global _DRAWING_ID_NEXT
    drawing_id = _DRAWING_ID_NEXT
    _DRAWING_ID_NEXT += 1
    return drawing_id


def _assign_inline_drawing_id(inline) -> None:
    drawing_id = _next_drawing_id()
    inline._inline.docPr.set("id", str(drawing_id))
    for node in inline._inline.xpath(".//*[local-name()='cNvPr']"):
        node.set("id", str(drawing_id))


def _strip_markup(text: str) -> str:
    value = text.replace("\\b", "").replace("\\i", "").replace("\\u", "")
    value = value.replace("\\n", " ")
    value = re.sub(r"\$[^$]+\$", "MM", value)
    return value


def _compute_column_widths(
    headers: list[str], rows: list[list[str]], total_width_tw: int
) -> list[int]:
    count = len(headers)
    if count <= 0:
        return []
    weights: list[int] = []
    for index in range(count):
        values = [_strip_markup(headers[index])]
        for row in rows:
            values.append(_strip_markup(row[index] if index < len(row) else ""))
        width_hint = max((len(value.strip()) for value in values), default=1)
        weights.append(max(width_hint, 4))

    total_weight = sum(weights) or count
    widths = [max(420, int(total_width_tw * weight / total_weight)) for weight in weights]
    delta = total_width_tw - sum(widths)
    widths[-1] += delta
    return widths


def _set_table_widths(table, widths: list[int]) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr

    def ensure(parent, tag_name: str):
        node = parent.find(qn(tag_name))
        if node is None:
            node = OxmlElement(tag_name)
            parent.append(node)
        return node

    tbl_style = ensure(tbl_pr, "w:tblStyle")
    tbl_style.set(qn("w:val"), "Table1")

    tbl_w = ensure(tbl_pr, "w:tblW")
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")

    jc = ensure(tbl_pr, "w:jc")
    jc.set(qn("w:val"), "center")

    tbl_borders = ensure(tbl_pr, "w:tblBorders")
    border_specs = {
        "top": ("single", "4"),
        "left": ("nil", "0"),
        "bottom": ("single", "4"),
        "right": ("nil", "0"),
        "insideH": ("nil", "0"),
        "insideV": ("nil", "0"),
    }
    for edge, (value, size) in border_specs.items():
        edge_el = tbl_borders.find(qn(f"w:{edge}"))
        if edge_el is None:
            edge_el = OxmlElement(f"w:{edge}")
            tbl_borders.append(edge_el)
        edge_el.set(qn("w:val"), value)
        edge_el.set(qn("w:sz"), size)
        edge_el.set(qn("w:space"), "0")
        edge_el.set(qn("w:color"), "000000")

    tbl_layout = ensure(tbl_pr, "w:tblLayout")
    tbl_layout.set(qn("w:type"), "fixed")

    tbl_look = ensure(tbl_pr, "w:tblLook")
    tbl_look.set(qn("w:val"), "0000")

    grid = tbl.tblGrid
    if grid is None:
        grid = OxmlElement("w:tblGrid")
        tbl.insert(1, grid)
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(width))
        grid.append(grid_col)

    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")


def _load_prototypes(doc: Document) -> dict[str, etree._Element | None]:
    paragraphs = doc.paragraphs
    return {
        "blank_top_ppr": _clone_ppr(paragraphs[0]),
        "blank_center_ppr": _clone_ppr(paragraphs[3]),
        "blank_justify_ppr": _clone_ppr(paragraphs[13]),
        "title_ppr": _clone_ppr(paragraphs[1]),
        "title_rpr": _clone_run_rpr(paragraphs[1], 0),
        "authors_ppr": _clone_ppr(paragraphs[4]),
        "author_rpr": _clone_run_rpr(paragraphs[4], 0),
        "author_sup_rpr": _clone_run_rpr(paragraphs[4], 1),
        "affiliation_ppr": _clone_ppr(paragraphs[6]),
        "affiliation_rpr": _clone_run_rpr(paragraphs[6], 1),
        "affiliation_sup_rpr": _clone_run_rpr(paragraphs[6], 0),
        "corr_ppr": _clone_ppr(paragraphs[9]),
        "corr_star_rpr": _clone_run_rpr(paragraphs[9], 0),
        "corr_text_rpr": _clone_run_rpr(paragraphs[9], 1),
        "abstract_title_ppr": _clone_ppr(paragraphs[12]),
        "abstract_title_rpr": _clone_run_rpr(paragraphs[12], 0),
        "abstract_body_ppr": _clone_ppr(paragraphs[14]),
        "abstract_body_rpr": _clone_run_rpr(paragraphs[14], 0),
        "keywords_ppr": _clone_ppr(paragraphs[16]),
        "keywords_rpr": _clone_run_rpr(paragraphs[16], 0),
        "section_break_1_ppr": _clone_ppr(paragraphs[25]),
        "section_break_2_ppr": _clone_ppr(paragraphs[26]),
        "section_heading_ppr": _clone_ppr(paragraphs[27]),
        "section_heading_rpr": _clone_run_rpr(paragraphs[27], 0),
        "subsection_ppr": _clone_ppr(paragraphs[45]),
        "subsection_rpr": _clone_run_rpr(paragraphs[45], 0),
        "body_ppr": _clone_ppr(paragraphs[29]),
        "body_rpr": _clone_run_rpr(paragraphs[29], 0),
        "figure_ppr": _clone_ppr(paragraphs[59]),
        "figure_caption_ppr": _clone_ppr(paragraphs[61]),
        "figure_caption_rpr": _clone_run_rpr(paragraphs[61], 0),
        "table_caption_ppr": _clone_ppr(paragraphs[64]),
        "table_caption_rpr": _clone_run_rpr(paragraphs[64], 0),
        "equation_ppr": _clone_ppr(paragraphs[71]),
        "equation_num_rpr": _clone_run_rpr(paragraphs[71], 0),
        "references_heading_ppr": _clone_ppr(paragraphs[90]),
        "references_heading_rpr": _clone_run_rpr(paragraphs[90], 0),
        "reference_ppr": _clone_ppr(paragraphs[94]),
        "reference_rpr": _clone_run_rpr(paragraphs[94], 0),
    }


def _normalize_authors(raw_authors: Any) -> list[dict[str, str]]:
    authors: list[dict[str, str]] = []
    if isinstance(raw_authors, list):
        for raw in raw_authors:
            if isinstance(raw, dict):
                authors.append(
                    {
                        "name": str(raw.get("name", "")).strip(),
                        "affiliation": str(raw.get("affiliation", "")).strip(),
                        "location": str(raw.get("location", "")).strip(),
                        "email": str(raw.get("email", "")).strip(),
                    }
                )
    if authors:
        return authors
    return [
        {
            "name": "Nama Penulis",
            "affiliation": "Afiliasi penulis belum disediakan",
            "location": "Lokasi belum disediakan",
            "email": "email@example.com",
        }
    ]


def _build_affiliation_groups(
    authors: list[dict[str, str]]
) -> tuple[dict[tuple[str, str], int], list[tuple[int, str]]]:
    group_map: dict[tuple[str, str], int] = {}
    groups: list[tuple[int, str]] = []
    for author in authors:
        key = (author.get("affiliation", ""), author.get("location", ""))
        if key not in group_map:
            group_id = len(group_map) + 1
            group_map[key] = group_id
            label = ", ".join(part for part in key if part) or "Afiliasi belum tersedia"
            groups.append((group_id, label))
    return group_map, groups


def _fallback_text(value: str, placeholder: str) -> str:
    value = str(value or "").strip()
    return value or placeholder


def _fallback_english_abstract(config: dict[str, Any]) -> str:
    explicit = _fallback_text(config.get("abstract_en", ""), "")
    if explicit:
        return explicit
    title = _fallback_text(config.get("title", ""), "this study")
    return (
        f"This paper presents {title}. "
        "A dedicated English abstract was not provided in the source JSON, so this placeholder summary preserves the JTRANSIENT abstract format for verification."
    )


def _add_front_matter(
    doc: Document, config: dict[str, Any], proto: dict[str, etree._Element | None]
) -> None:
    authors = _normalize_authors(config.get("authors"))
    group_map, groups = _build_affiliation_groups(authors)
    corresponding = authors[0]

    _new_paragraph(doc, proto["blank_top_ppr"])

    title = _fallback_text(config.get("title", ""), "Judul Artikel")
    title_paragraph = _new_paragraph(doc, proto["title_ppr"])
    _append_run(title_paragraph, title, proto["title_rpr"])

    _new_paragraph(doc, proto["blank_center_ppr"])

    authors_paragraph = _new_paragraph(doc, proto["authors_ppr"])
    for index, author in enumerate(authors):
        if index > 0:
            separator = ", " if index < len(authors) - 1 else " dan "
            _append_run(authors_paragraph, separator, proto["author_rpr"])
        _append_run(
            authors_paragraph,
            _fallback_text(author.get("name", ""), f"Penulis {index + 1}"),
            proto["author_rpr"],
        )
        affiliation_id = group_map[(author.get("affiliation", ""), author.get("location", ""))]
        marker = f"{affiliation_id}*)" if author is corresponding else str(affiliation_id)
        _append_run(authors_paragraph, marker, proto["author_sup_rpr"])

    _new_paragraph(doc, proto["blank_center_ppr"])

    for group_id, label in groups:
        paragraph = _new_paragraph(doc, proto["affiliation_ppr"])
        _append_run(paragraph, str(group_id), proto["affiliation_sup_rpr"])
        _append_run(paragraph, label, proto["affiliation_rpr"])

    _new_paragraph(doc, proto["blank_center_ppr"])

    corr_email = _fallback_text(corresponding.get("email", ""), "email@example.com")
    corr_paragraph = _new_paragraph(doc, proto["corr_ppr"])
    _append_run(corr_paragraph, "*", proto["corr_star_rpr"])
    _append_run(
        corr_paragraph, f"Penulis korespondensi, E-mail: {corr_email}", proto["corr_text_rpr"]
    )

    _new_paragraph(doc, proto["blank_center_ppr"])
    _new_paragraph(doc, proto["blank_center_ppr"])

    abstract_title = _new_paragraph(doc, proto["abstract_title_ppr"])
    _append_run(abstract_title, "Abstrak", proto["abstract_title_rpr"])
    # Set italic + superscript di run pertama (sesuai template asli)
    for i, r in enumerate(abstract_title.runs):
        r.italic = True
        r.bold = True
        if i == 0:
            r.font.superscript = True

    _new_paragraph(doc, proto["blank_justify_ppr"])

    abstract_paragraph = _new_paragraph(doc, proto["abstract_body_ppr"])
    abstract_text = _fallback_text(
        config.get("abstract", ""),
        "Abstrak belum tersedia pada source JSON. Teks placeholder ini mempertahankan struktur JTRANSIENT untuk verifikasi format.",
    )
    _append_rich_text(abstract_paragraph, abstract_text, proto["abstract_body_rpr"])

    _new_paragraph(doc, proto["blank_justify_ppr"])

    keywords = config.get("keywords") if isinstance(config.get("keywords"), list) else []
    keywords_text = ", ".join(str(item).strip() for item in keywords if str(item).strip())
    keywords_text = keywords_text or "kata kunci belum tersedia"
    keywords_paragraph = _new_paragraph(doc, proto["keywords_ppr"])
    _append_run(keywords_paragraph, f"Kata kunci: {keywords_text}", proto["keywords_rpr"])

    _new_paragraph(doc, proto["blank_center_ppr"])
    _new_paragraph(doc, proto["blank_center_ppr"])

    abstract_en_title = _new_paragraph(doc, proto["abstract_title_ppr"])
    _append_run(abstract_en_title, "Abstract", proto["abstract_title_rpr"])

    _new_paragraph(doc, proto["blank_center_ppr"])

    abstract_en_paragraph = _new_paragraph(doc, proto["abstract_body_ppr"])
    _append_rich_text(
        abstract_en_paragraph, _fallback_english_abstract(config), proto["abstract_body_rpr"]
    )

    _new_paragraph(doc, proto["blank_justify_ppr"])

    keywords_en_paragraph = _new_paragraph(doc, proto["keywords_ppr"])
    _append_run(keywords_en_paragraph, f"Keywords: {keywords_text}", proto["keywords_rpr"])

    _new_paragraph(doc, proto["blank_justify_ppr"])
    _new_paragraph(doc, proto["section_break_1_ppr"])
    _new_paragraph(doc, proto["section_break_2_ppr"])


def _add_body_paragraph(doc: Document, text: str, proto: dict[str, etree._Element | None]) -> None:
    blocks = _split_text_blocks(text)
    for block in blocks:
        paragraph = _new_paragraph(doc, proto["body_ppr"])
        _append_rich_text(paragraph, block, proto["body_rpr"])


def _add_section_heading(
    doc: Document, number: int, title: str, proto: dict[str, etree._Element | None]
) -> None:
    paragraph = _new_paragraph(doc, proto["section_heading_ppr"])
    _set_paragraph_spacing(
        paragraph, before_pt=SECTION_SPACE_BEFORE_PT, after_pt=SECTION_SPACE_AFTER_PT
    )
    _append_run(paragraph, f"{number}. {title}", proto["section_heading_rpr"])


def _add_subsection_heading(
    doc: Document,
    section_number: int,
    subsection_number: int,
    title: str,
    proto: dict[str, etree._Element | None],
) -> None:
    paragraph = _new_paragraph(doc, proto["subsection_ppr"])
    _set_paragraph_spacing(
        paragraph, before_pt=SUBSECTION_SPACE_BEFORE_PT, after_pt=SUBSECTION_SPACE_AFTER_PT
    )
    _append_run(
        paragraph, f"{section_number}.{subsection_number}.\t{title}", proto["subsection_rpr"]
    )


def _add_figure(
    doc: Document,
    item: dict[str, Any],
    json_path: Path,
    proto: dict[str, etree._Element | None],
    state: RenderState,
) -> None:

    # AI prompt emit (warna merah). Idempotent supaya tidak double-emit.
    _ai_title = str(item.get("Title") or item.get("title") or "").strip()
    _ai_prompt_text = str(item.get("Prompt") or item.get("Description") or "").strip()
    if _ai_title:
        _ai_full = f"[PROMPT UNTUK AI GAMBAR: {_ai_title}. {_ai_prompt_text or _ai_title}]"
        from docx.enum.text import WD_ALIGN_PARAGRAPH as _WAP
        from docx.shared import RGBColor as _RGB

        _ai_para = doc.add_paragraph()
        _ai_para.alignment = _WAP.CENTER
        _ai_run = _ai_para.add_run(_ai_full)
        _ai_run.italic = True
        _ai_run.font.color.rgb = _RGB(0xFF, 0x00, 0x00)
    title = _fallback_text(item.get("Title", ""), f"Judul gambar {state.figure_number}")
    image_path = _resolve_path(str(item.get("Path", "")).strip(), json_path)

    paragraph = _new_paragraph(doc, proto["figure_ppr"])
    _set_paragraph_spacing(paragraph, before_pt=FIGURE_BEFORE_PT, after_pt=FIGURE_AFTER_PT)
    if image_path.is_file():
        inline = paragraph.add_run().add_picture(str(image_path), width=Cm(MAX_FIGURE_WIDTH_CM))
        _assign_inline_drawing_id(inline)
    else:
        _append_run(
            paragraph, str(image_path) or "[gambar belum tersedia]", proto["body_rpr"], italic=True
        )

    caption = _new_paragraph(doc, proto["figure_caption_ppr"])
    _set_paragraph_spacing(
        caption, before_pt=FIGURE_TITLE_BEFORE_PT, after_pt=FIGURE_TITLE_AFTER_PT
    )
    _append_rich_text(
        caption, f"Gambar {state.figure_number}. {title}", proto["figure_caption_rpr"]
    )
    state.figure_number += 1


def _add_table(
    doc: Document, item: dict[str, Any], proto: dict[str, etree._Element | None], state: RenderState
) -> None:
    headers = [str(value).strip() for value in item.get("Headers", []) if str(value).strip()]
    rows = [
        [str(value).strip() for value in row]
        for row in item.get("Rows", [])
        if isinstance(row, list)
    ]

    if not headers:
        headers = ["Kolom 1", "Kolom 2"]
    if not rows:
        rows = [["Data belum tersedia", "Data belum tersedia"]]

    max_cols = max(len(headers), max((len(row) for row in rows), default=0))
    if len(headers) < max_cols:
        headers.extend([f"Kolom {index}" for index in range(len(headers) + 1, max_cols + 1)])
    rows = [row + [""] * (max_cols - len(row)) for row in rows]

    title = _fallback_text(item.get("Title", ""), f"Judul tabel {state.table_number}")
    caption = _new_paragraph(doc, proto["table_caption_ppr"])
    _set_paragraph_spacing(caption, before_pt=TABLE_TITLE_BEFORE_PT, after_pt=TABLE_TITLE_AFTER_PT)
    _append_rich_text(caption, f"Tabel {state.table_number}.\t{title}", proto["table_caption_rpr"])

    table = doc.add_table(rows=len(rows) + 1, cols=max_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_table_widths(table, _compute_column_widths(headers, rows, TABLE_TOTAL_WIDTH_TW))

    for cell in table.rows[0].cells:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for column_index, header in enumerate(headers):
        cell = table.rows[0].cells[column_index]
        _clear_cell(cell)
        paragraph = cell.paragraphs[0]
        paragraph.alignment = 1
        _append_table_text(paragraph, header, bold_default=True)

    for row_index, values in enumerate(rows, start=1):
        for column_index, value in enumerate(values):
            cell = table.rows[row_index].cells[column_index]
            _clear_cell(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.alignment = 1
            _append_table_text(paragraph, value)

    state.table_number += 1


def _add_equation(
    doc: Document, item: dict[str, Any], proto: dict[str, etree._Element | None], state: RenderState
) -> None:
    formula = _fallback_text(item.get("latex", "") or item.get("text", ""), "x = y")
    number = str(state.equation_number)
    paragraph = _new_paragraph(doc, proto["equation_ppr"])
    _set_paragraph_spacing(paragraph, before_pt=EQUATION_BEFORE_PT, after_pt=EQUATION_AFTER_PT)
    if not _append_inline_math(paragraph, formula):
        _append_run(paragraph, formula, proto["body_rpr"], italic=True)
    _append_run(paragraph, f"\t\t\t\t({number})", proto["equation_num_rpr"])
    state.equation_number += 1


def _render_content_item(
    doc: Document,
    item: dict[str, Any],
    json_path: Path,
    proto: dict[str, etree._Element | None],
    state: RenderState,
) -> None:
    item_type = str(item.get("id", "")).strip().lower()
    if item_type == "text":
        text = _fallback_text(item.get("text", ""), "Konten belum tersedia pada source JSON.")
        _add_body_paragraph(doc, text, proto)
        return
    if item_type in {"gambar", "figure", "image"}:
        _add_figure(doc, item, json_path, proto, state)
        return
    if item_type in {"tabel", "table"}:
        _add_table(doc, item, proto, state)
        return
    if item_type in {"rumus", "formula", "equation"}:
        _add_equation(doc, item, proto, state)
        return
    _add_body_paragraph(
        doc, f"Konten tipe '{item_type or 'unknown'}' belum memiliki renderer khusus.", proto
    )


def _render_content(
    doc: Document,
    content: Any,
    json_path: Path,
    proto: dict[str, etree._Element | None],
    state: RenderState,
) -> None:
    if isinstance(content, str):
        if content.strip():
            _add_body_paragraph(doc, content.strip(), proto)
        return
    if not isinstance(content, list):
        return
    for item in content:
        if isinstance(item, str):
            if item.strip():
                _add_body_paragraph(doc, item.strip(), proto)
        elif isinstance(item, dict):
            _render_content_item(doc, item, json_path, proto, state)


def _section_keys(config: dict[str, Any]) -> list[tuple[int, str]]:
    keys: list[tuple[int, str]] = []
    for key in config:
        match = re.fullmatch(r"section(\d+)", key)
        if match:
            keys.append((int(match.group(1)), key))
    return sorted(keys)


def _subsection_keys(section_key: str, container: dict[str, Any]) -> list[str]:
    matches: list[tuple[str, str]] = []
    pattern = re.compile(rf"^{re.escape(section_key)}([a-z]+)$")
    for key in container:
        match = pattern.fullmatch(key)
        if match:
            matches.append((match.group(1), key))
    matches.sort(key=lambda item: item[0])
    return [key for _, key in matches]


def _render_sections(
    doc: Document,
    config: dict[str, Any],
    json_path: Path,
    proto: dict[str, etree._Element | None],
    state: RenderState,
) -> None:
    for section_number, key in _section_keys(config):
        section = config.get(key)
        if not isinstance(section, dict):
            continue
        title = _fallback_text(section.get("title", ""), f"Bagian {section_number}")
        _add_section_heading(doc, section_number, title, proto)
        _render_content(doc, section.get("content", []), json_path, proto, state)

        for subsection_index, subsection_key in enumerate(_subsection_keys(key, section), start=1):
            subsection = section.get(subsection_key)
            if not isinstance(subsection, dict):
                continue
            subsection_title = _fallback_text(
                subsection.get("title", ""), f"Subbagian {section_number}.{subsection_index}"
            )
            _add_subsection_heading(doc, section_number, subsection_index, subsection_title, proto)
            _render_content(doc, subsection.get("content", []), json_path, proto, state)


def _render_references(
    doc: Document, config: dict[str, Any], proto: dict[str, etree._Element | None]
) -> None:
    references = config.get("references") if isinstance(config.get("references"), dict) else {}
    title = _fallback_text(references.get("title", ""), "Referensi")
    content = references.get("content") if isinstance(references.get("content"), list) else []
    items = [str(item).strip() for item in content if str(item).strip()]
    if not items:
        items = ["Referensi belum tersedia pada source JSON."]

    title_paragraph = _new_paragraph(doc, proto["references_heading_ppr"])
    _append_run(title_paragraph, title, proto["references_heading_rpr"])

    for item in items:
        paragraph = _new_paragraph(doc, proto["reference_ppr"])
        _append_run(paragraph, item, proto["reference_rpr"])


def build_document(json_path: Path = JSON_PATH, output_path: Path | None = None) -> Path:
    json_path = Path(json_path)
    config = json.loads(json_path.read_text(encoding="utf-8"))

    final_output = (
        Path(output_path)
        if output_path is not None
        else json_path.parent / f"{JOURNAL_NAME}_output.docx"
    )
    final_output.parent.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(TEMPLATE_PATH, final_output)
    doc = Document(str(final_output))
    _initialize_drawing_ids(doc)
    prototypes = _load_prototypes(doc)

    _clear_document_body(doc)
    _add_front_matter(doc, config, prototypes)

    state = RenderState()
    _render_sections(doc, config, json_path, prototypes, state)

    # Inject inline section break (cols=2 continuous) sebelum references
    # untuk match struktur 4-section original (title 1col -> body 2col ->
    # refs 2col -> final 2col).
    from copy import deepcopy as _deepcopy

    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn as _qn

    # Ambil pgSz/pgMar dari final body sectPr supaya page setup match
    body_el = doc._element.body
    final_sectpr = body_el.find(_qn("w:sectPr"))

    break_para = doc.add_paragraph()
    pPr = break_para._p.get_or_add_pPr()
    sectPr = OxmlElement("w:sectPr")
    sec_type = OxmlElement("w:type")
    sec_type.set(_qn("w:val"), "continuous")
    sectPr.append(sec_type)
    if final_sectpr is not None:
        for tag in ("w:pgSz", "w:pgMar"):
            src = final_sectpr.find(_qn(tag))
            if src is not None:
                sectPr.append(_deepcopy(src))
    cols = OxmlElement("w:cols")
    cols.set(_qn("w:num"), "2")
    cols.set(_qn("w:space"), "360")
    sectPr.append(cols)
    pPr.append(sectPr)

    _render_references(doc, config, prototypes)

    doc.save(str(final_output))
    return final_output


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    json_path = Path(args[0]) if args else JSON_PATH
    output_path = Path(args[1]) if len(args) > 1 else None
    result = build_document(json_path, output_path)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
