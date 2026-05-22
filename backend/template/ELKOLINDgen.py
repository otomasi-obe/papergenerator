"""
ELKOLINDgen.py -- Generator DOCX ELKOLIND dari JSON.

Dokumen dibangun dari ELKOLIND.docx asli dengan pendekatan paste keep formatting:
  - file template asli disalin lebih dulu,
  - blok judul/penulis dan tabel front-matter diperbarui di dokumen asli,
  - body contoh setelah tabel front-matter dihapus,
  - isi paper dirender dari _PLC-MediapipeID.json,
  - header/footer/styles/numbering/theme/sectPr template tetap dipertahankan.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.table import _Cell
from docx.text.paragraph import Paragraph
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "_PLC-MediapipeID.json"
TEMPLATE_PATH = BASE_DIR / "ELKOLIND.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

MAX_FIGURE_WIDTH_CM = 15.5
TABLE_FONT_PT = 9.0
TABLE_FONT_NAME = "Gadugi"
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

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
_XSLT = None
_DRAWING_ID_NEXT = 1
_DOC_PR_PATTERN = re.compile(r'<wp:docPr\b[^>]*\bid="(\d+)"')


def _wq(tag: str) -> str:
    return f"{{{NS_W}}}{tag}"


def _strict_to_trans(data: bytes) -> bytes:
    for old, new in NS_MAP_STRICT.items():
        data = data.replace(old, new)
    return data


def _clone_run_rpr(paragraph: Paragraph, run_index: int = 0):
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


def _insert_paragraph_before(reference_paragraph: Paragraph, sample_ppr: etree._Element | None = None) -> Paragraph:
    paragraph_el = OxmlElement("w:p")
    reference_paragraph._p.addprevious(paragraph_el)
    paragraph = Paragraph(paragraph_el, reference_paragraph._parent)
    if sample_ppr is not None:
        _apply_sample_ppr(paragraph, sample_ppr)
    return paragraph


def _add_sample_run(
    paragraph: Paragraph,
    text: str,
    sample_rpr: etree._Element | None,
    *,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
):
    run = paragraph.add_run(text)
    _apply_sample_rpr(run, sample_rpr)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline
    return run


def _set_run_font_name(run, font_name: str) -> None:
    run.font.name = font_name
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def _set_table_run_format(run, *, bold: bool = False, italic: bool = False) -> None:
    _set_run_font_name(run, TABLE_FONT_NAME)
    run.font.size = Pt(TABLE_FONT_PT)
    run.bold = bold
    run.italic = italic


def _set_cell_border(cell: _Cell, edge: str, value: str, size: str = "4", color: str = "000000") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    border = tc_borders.find(qn(f"w:{edge}"))
    if border is None:
        border = OxmlElement(f"w:{edge}")
        tc_borders.append(border)
    border.set(qn("w:val"), value)
    border.set(qn("w:sz"), size)
    border.set(qn("w:space"), "0")
    border.set(qn("w:color"), color)


def _set_full_cell_borders(cell: _Cell) -> None:
    for edge in ("top", "left", "bottom", "right"):
        _set_cell_border(cell, edge, "single")


def _set_row_repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = tr_pr.find(qn("w:tblHeader"))
    if tbl_header is None:
        tbl_header = OxmlElement("w:tblHeader")
        tbl_header.set(qn("w:val"), "true")
        tr_pr.append(tbl_header)


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


def _set_rpr_math_defaults(rpr: etree._Element, half_points: int = 20) -> None:
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), "Cambria Math")

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


def _normalize_omml_math(omml: etree._Element, half_points: int = 20) -> etree._Element:
    for math_run in omml.findall(f".//{{{MATH_NS}}}r"):
        rpr = math_run.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            math_run.insert(0, rpr)
        _set_rpr_math_defaults(rpr, half_points=half_points)

    for ctrl_pr in omml.findall(f".//{{{MATH_NS}}}ctrlPr"):
        rpr = ctrl_pr.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            ctrl_pr.insert(0, rpr)
        _set_rpr_math_defaults(rpr, half_points=half_points)

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


def _normalize_text_commands(text: str) -> str:
    text = text.replace("\\n", "\n")
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


def _append_rich_text(paragraph: Paragraph, text: str, sample_rpr: etree._Element | None) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            paragraph.add_run().add_break()
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                run = _add_sample_run(paragraph, token["value"], sample_rpr)
                run.italic = True
            continue
        _add_sample_run(
            paragraph,
            token["value"],
            sample_rpr,
            bold=True if token["bold"] else None,
            italic=True if token["italic"] else None,
            underline=True if token["underline"] else None,
        )


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    parts = [part for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return parts or [""]


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative
    return BASE_DIR / path


def _title_text(config: dict) -> str:
    return str(config.get("title") or config.get("TitleBlock", {}).get("Title", "")).strip()


def _abstract_text_id(config: dict) -> str:
    for key in ("abstractID", "abstrak", "abstract"):
        value = str(config.get(key, "")).strip()
        if value:
            return value
    return ""


def _abstract_text_en(config: dict) -> str:
    for key in ("abstractEN", "abstractEnglish"):
        value = str(config.get(key, "")).strip()
        if value:
            return value
    return _abstract_text_id(config)


def _keyword_list(config: dict) -> list[str]:
    keywords = config.get("keywords", [])
    if isinstance(keywords, list) and keywords:
        return [str(item).strip() for item in keywords if str(item).strip()]
    raw = str(config.get("Keywords") or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _author_entries(config: dict) -> list[dict]:
    authors = config.get("authors", [])
    if not isinstance(authors, list):
        return []
    result = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        result.append(
            {
                "name": str(author.get("name", "")).strip(),
                "affiliation": str(author.get("affiliation", "")).strip(),
                "location": str(author.get("location", "")).strip(),
                "email": str(author.get("email", "")).strip(),
                "phone": str(author.get("phone") or author.get("wa") or author.get("whatsapp") or "").strip(),
                "corresponding": bool(author.get("corresponding", False)),
            }
        )
    return result


def _corresponding_author(config: dict) -> dict:
    authors = _author_entries(config)
    for author in authors:
        if author.get("corresponding"):
            return author
    return authors[0] if authors else {}


def _article_history_lines(config: dict) -> tuple[str, str, str]:
    info = config.get("articleInfo", {}) if isinstance(config.get("articleInfo"), dict) else {}
    received = str(info.get("received") or config.get("received") or "-").strip() or "-"
    revised = str(info.get("revised") or config.get("revised") or "-").strip() or "-"
    published = str(
        info.get("published")
        or info.get("accepted")
        or config.get("published")
        or config.get("accepted")
        or "-"
    ).strip() or "-"
    return received, revised, published


def _reference_texts(config: dict) -> list[str]:
    if "references" in config and isinstance(config["references"], dict):
        content = config["references"].get("content", [])
        if isinstance(content, list):
            return [str(item) for item in content if str(item).strip()]
    if "References" in config and isinstance(config["References"], list):
        return [str(item) for item in config["References"] if str(item).strip()]
    return []


def _strip_reference_label(text: str) -> str:
    return re.sub(r"^\s*\[(\d+)\]\s*", "", text).strip()


def _footer_short_text(config: dict) -> str:
    authors = _author_entries(config)
    title = _title_text(config)
    surname = authors[0]["name"].split()[-1] if authors and authors[0].get("name") else "Author"
    author_text = f"{surname} et al." if len(authors) > 1 else surname
    words = re.findall(r"\S+", title)
    short_title = " ".join(words[:4]) if words else "Untitled"
    if len(words) > 4:
        short_title += "..."
    return f"{author_text}: {short_title}".strip()


def _capture_paragraph_samples(doc: Document) -> dict[str, etree._Element | None]:
    paragraphs = doc.paragraphs

    def clone_ppr(index: int):
        return deepcopy(paragraphs[index]._p.find(qn("w:pPr")))

    def clone_rpr(index: int, run_index: int = 0):
        return _clone_run_rpr(paragraphs[index], run_index)

    return {
        "title_rpr": clone_rpr(0, 0),
        "author_name_rpr": clone_rpr(1, 0),
        "author_sup_rpr": clone_rpr(1, 1),
        "email_rpr": clone_rpr(2, 0),
        "affiliation_first_ppr": clone_ppr(3),
        "affiliation_other_ppr": clone_ppr(4),
        "affiliation_sup_rpr": clone_rpr(3, 0),
        "affiliation_text_rpr": clone_rpr(3, 1),
        "blank_pre_table_ppr": clone_ppr(5),
        "blank_after_table_ppr": clone_ppr(6),
        "section_ppr": clone_ppr(7),
        "section_rpr": clone_rpr(7, 0),
        "body_ppr": clone_ppr(8),
        "body_rpr": clone_rpr(8, 0),
        "subsection_ppr": clone_ppr(14),
        "subsection_rpr": clone_rpr(14, 0),
        "figure_ppr": clone_ppr(29),
        "figure_caption_ppr": clone_ppr(30),
        "figure_caption_rpr": clone_rpr(30, 0),
        "table_caption_ppr": clone_ppr(19),
        "table_caption_rpr": clone_rpr(19, 0),
        "equation_ppr": clone_ppr(48),
        "equation_num_rpr": clone_rpr(48, 0),
        "reference_heading_ppr": clone_ppr(58),
        "reference_heading_rpr": clone_rpr(58, 0),
        "reference_item_ppr": clone_ppr(61),
        "reference_item_rpr": clone_rpr(61, 0),
    }


def _capture_front_table_samples(table) -> dict[str, etree._Element | None]:
    info_heading = table.rows[0].cells[0].paragraphs[0]
    history_cell = table.rows[1].cells[0]
    keywords_id_cell = table.rows[2].cells[0]
    abstract_heading = table.rows[0].cells[2].paragraphs[0]
    abstract_body = table.rows[1].cells[2].paragraphs[0]
    abstract_en_heading = table.rows[3].cells[2].paragraphs[0]
    abstract_en_body = table.rows[4].cells[2].paragraphs[0]
    keywords_en_cell = table.rows[4].cells[0]
    corresponding_cell = table.rows[5].cells[0]

    corr_email_body_rpr = _clone_run_rpr(corresponding_cell.paragraphs[5], 1)
    if corr_email_body_rpr is None:
        corr_email_body_rpr = _clone_run_rpr(corresponding_cell.paragraphs[1], 0)

    return {
        "info_heading_ppr": deepcopy(info_heading._p.find(qn("w:pPr"))),
        "info_heading_rpr": _clone_run_rpr(info_heading, 0),
        "history_heading_ppr": deepcopy(history_cell.paragraphs[0]._p.find(qn("w:pPr"))),
        "history_heading_rpr": _clone_run_rpr(history_cell.paragraphs[0], 0),
        "history_body_ppr": deepcopy(history_cell.paragraphs[1]._p.find(qn("w:pPr"))),
        "history_body_rpr": _clone_run_rpr(history_cell.paragraphs[1], 0),
        "keywords_id_heading_ppr": deepcopy(keywords_id_cell.paragraphs[0]._p.find(qn("w:pPr"))),
        "keywords_id_heading_rpr": _clone_run_rpr(keywords_id_cell.paragraphs[0], 0),
        "keywords_id_body_ppr": deepcopy(keywords_id_cell.paragraphs[2]._p.find(qn("w:pPr"))),
        "keywords_id_body_rpr": _clone_run_rpr(keywords_id_cell.paragraphs[2], 0),
        "abstract_heading_ppr": deepcopy(abstract_heading._p.find(qn("w:pPr"))),
        "abstract_heading_rpr": _clone_run_rpr(abstract_heading, 0),
        "abstract_body_ppr": deepcopy(abstract_body._p.find(qn("w:pPr"))),
        "abstract_body_rpr": _clone_run_rpr(abstract_body, 0),
        "keywords_en_heading_ppr": deepcopy(keywords_en_cell.paragraphs[0]._p.find(qn("w:pPr"))),
        "keywords_en_heading_rpr": _clone_run_rpr(keywords_en_cell.paragraphs[0], 0),
        "keywords_en_body_ppr": deepcopy(keywords_en_cell.paragraphs[1]._p.find(qn("w:pPr"))),
        "keywords_en_body_rpr": _clone_run_rpr(keywords_en_cell.paragraphs[1], 0),
        "corr_heading_ppr": deepcopy(corresponding_cell.paragraphs[0]._p.find(qn("w:pPr"))),
        "corr_heading_rpr": _clone_run_rpr(corresponding_cell.paragraphs[0], 0),
        "corr_body_ppr": deepcopy(corresponding_cell.paragraphs[1]._p.find(qn("w:pPr"))),
        "corr_body_rpr": _clone_run_rpr(corresponding_cell.paragraphs[1], 0),
        "corr_email_ppr": deepcopy(corresponding_cell.paragraphs[5]._p.find(qn("w:pPr"))),
        "corr_email_label_rpr": _clone_run_rpr(corresponding_cell.paragraphs[5], 0),
        "corr_email_body_rpr": corr_email_body_rpr,
        "abstract_en_heading_ppr": deepcopy(abstract_en_heading._p.find(qn("w:pPr"))),
        "abstract_en_heading_rpr": _clone_run_rpr(abstract_en_heading, 0),
        "abstract_en_body_ppr": deepcopy(abstract_en_body._p.find(qn("w:pPr"))),
        "abstract_en_body_rpr": _clone_run_rpr(abstract_en_body, 0),
    }


def _history_line(label: str, value: str) -> str:
    if not value or value == "-":
        return f"{label} -"
    if value.lower().startswith(label.lower()):
        return value
    return f"{label} {value}"


def _group_affiliations(authors: list[dict]) -> list[tuple[str, str]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for index, author in enumerate(authors, start=1):
        key = (author.get("affiliation", ""), author.get("location", ""))
        grouped.setdefault(key, []).append(str(index))

    lines: list[tuple[str, str]] = []
    for (affiliation, location), numbers in grouped.items():
        text_parts = [part for part in (affiliation, location) if part]
        lines.append((",".join(numbers), ", ".join(text_parts)))
    return lines


def _update_title_paragraph(paragraph: Paragraph, config: dict, samples: dict) -> None:
    _clear_paragraph(paragraph)
    title = _title_text(config)
    if title:
        _add_sample_run(paragraph, title, samples["title_rpr"])


def _update_author_paragraph(paragraph: Paragraph, config: dict, samples: dict) -> None:
    _clear_paragraph(paragraph)
    authors = _author_entries(config)
    if not authors:
        return
    for index, author in enumerate(authors, start=1):
        if index > 1:
            _add_sample_run(paragraph, ", ", samples["author_name_rpr"])
        _add_sample_run(paragraph, author.get("name", ""), samples["author_name_rpr"])
        _add_sample_run(paragraph, str(index), samples["author_sup_rpr"])


def _update_email_paragraph(paragraph: Paragraph, config: dict, samples: dict) -> None:
    _clear_paragraph(paragraph)
    authors = _author_entries(config)
    emails = [author.get("email", "") for author in authors if author.get("email")]
    email_text = ", ".join(dict.fromkeys(emails))
    if not email_text:
        return
    _add_sample_run(paragraph, f"e-mail: {email_text}", samples["email_rpr"])


def _update_affiliation_paragraphs(doc: Document, blank_paragraph: Paragraph, config: dict, samples: dict) -> None:
    authors = _author_entries(config)
    affiliations = _group_affiliations(authors)

    first_para = doc.paragraphs[3]
    second_para = doc.paragraphs[4]
    target_paragraphs = [first_para, second_para]

    while len(target_paragraphs) < len(affiliations):
        target_paragraphs.append(_insert_paragraph_before(blank_paragraph, samples["affiliation_other_ppr"]))

    for index, paragraph in enumerate(target_paragraphs):
        _clear_paragraph(paragraph)
        sample_ppr = samples["affiliation_first_ppr"] if index == 0 else samples["affiliation_other_ppr"]
        _apply_sample_ppr(paragraph, sample_ppr)
        if index < len(affiliations):
            label, text = affiliations[index]
            _add_sample_run(paragraph, label, samples["affiliation_sup_rpr"])
            _add_sample_run(paragraph, " ", samples["affiliation_sup_rpr"])
            _add_sample_run(paragraph, text, samples["affiliation_text_rpr"])


def _append_cell_paragraph(cell: _Cell, sample_ppr: etree._Element | None) -> Paragraph:
    paragraph = cell.add_paragraph()
    _apply_sample_ppr(paragraph, sample_ppr)
    return paragraph


def _update_front_table(table, config: dict, samples: dict) -> None:
    received, revised, published = _article_history_lines(config)
    keywords = _keyword_list(config)
    abstract_id = _abstract_text_id(config)
    abstract_en = _abstract_text_en(config)
    corresponding = _corresponding_author(config)

    info_heading_cell = table.rows[0].cells[0]
    _clear_cell(info_heading_cell)
    p = info_heading_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["info_heading_ppr"])
    _add_sample_run(p, "Informasi Artikel", samples["info_heading_rpr"], bold=True)

    history_cell = table.rows[1].cells[0]
    _clear_cell(history_cell)
    p = history_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["history_heading_ppr"])
    _add_sample_run(p, "Riwayat Artikel", samples["history_heading_rpr"], bold=True, italic=True)
    for line in (
        _history_line("Diterima", received),
        _history_line("Direvisi", revised),
        _history_line("Diterbitkan", published),
    ):
        p = _append_cell_paragraph(history_cell, samples["history_body_ppr"])
        _add_sample_run(p, line, samples["history_body_rpr"])
    _append_cell_paragraph(history_cell, samples["history_body_ppr"])
    history_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    keywords_id_cell = table.rows[2].cells[0]
    _clear_cell(keywords_id_cell)
    p = keywords_id_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["keywords_id_heading_ppr"])
    _add_sample_run(p, "Kata kunci:", samples["keywords_id_heading_rpr"], bold=True)
    _append_cell_paragraph(keywords_id_cell, samples["keywords_id_body_ppr"])
    for keyword in keywords:
        p = _append_cell_paragraph(keywords_id_cell, samples["keywords_id_body_ppr"])
        _add_sample_run(p, keyword, samples["keywords_id_body_rpr"])
    _append_cell_paragraph(keywords_id_cell, samples["keywords_id_body_ppr"])
    keywords_id_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    abstract_heading_cell = table.rows[0].cells[2]
    _clear_cell(abstract_heading_cell)
    p = abstract_heading_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["abstract_heading_ppr"])
    _add_sample_run(p, "ABSTRAK", samples["abstract_heading_rpr"], bold=True)

    abstract_body_cell = table.rows[1].cells[2]
    _clear_cell(abstract_body_cell)
    p = abstract_body_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["abstract_body_ppr"])
    if abstract_id:
        _append_rich_text(p, abstract_id, samples["abstract_body_rpr"])
    _append_cell_paragraph(abstract_body_cell, samples["abstract_body_ppr"])
    abstract_body_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    abstract_en_heading_cell = table.rows[3].cells[2]
    _clear_cell(abstract_en_heading_cell)
    p = abstract_en_heading_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["abstract_en_heading_ppr"])
    _add_sample_run(p, "ABSTRACT", samples["abstract_en_heading_rpr"], bold=True)

    keywords_en_cell = table.rows[4].cells[0]
    _clear_cell(keywords_en_cell)
    p = keywords_en_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["keywords_en_heading_ppr"])
    _add_sample_run(p, "Keywords:", samples["keywords_en_heading_rpr"], bold=True, italic=True)
    for keyword in keywords:
        p = _append_cell_paragraph(keywords_en_cell, samples["keywords_en_body_ppr"])
        _add_sample_run(p, keyword, samples["keywords_en_body_rpr"])
    _append_cell_paragraph(keywords_en_cell, samples["keywords_en_body_ppr"])
    keywords_en_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    abstract_en_body_cell = table.rows[4].cells[2]
    _clear_cell(abstract_en_body_cell)
    p = abstract_en_body_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["abstract_en_body_ppr"])
    if abstract_en:
        _append_rich_text(p, abstract_en, samples["abstract_en_body_rpr"])
    abstract_en_body_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    corresponding_cell = table.rows[5].cells[0]
    _clear_cell(corresponding_cell)
    p = corresponding_cell.paragraphs[0]
    _apply_sample_ppr(p, samples["corr_heading_ppr"])
    _add_sample_run(p, "Penulis Korespondensi:", samples["corr_heading_rpr"], bold=True, italic=True)

    name = corresponding.get("name", "")
    if name:
        p = _append_cell_paragraph(corresponding_cell, samples["corr_body_ppr"])
        _add_sample_run(p, name, samples["corr_body_rpr"])

    affiliation = corresponding.get("affiliation", "")
    location = corresponding.get("location", "")
    for line in (affiliation, location):
        if line:
            p = _append_cell_paragraph(corresponding_cell, samples["corr_body_ppr"])
            _add_sample_run(p, line, samples["corr_body_rpr"])

    email = corresponding.get("email", "")
    if email:
        p = _append_cell_paragraph(corresponding_cell, samples["corr_email_ppr"])
        _add_sample_run(p, "Email: ", samples["corr_email_label_rpr"])
        _add_sample_run(p, email, samples["corr_email_body_rpr"])

    phone = corresponding.get("phone", "")
    if phone:
        p = _append_cell_paragraph(corresponding_cell, samples["corr_body_ppr"])
        _add_sample_run(p, f"Nomor HP/WA aktif: {phone}", samples["corr_body_rpr"])

    corresponding_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP


def _trim_template_body(doc: Document, first_table) -> None:
    body = doc._element.body
    remove = False
    for child in list(body):
        if child is first_table._tbl:
            remove = True
            continue
        if remove and child.tag != qn("w:sectPr"):
            body.remove(child)


def _body_paragraphs(doc: Document, text: str, samples: dict) -> None:
    for block in _split_body_blocks(text):
        paragraph = _new_paragraph(doc, samples["body_ppr"])
        _append_rich_text(paragraph, block, samples["body_rpr"])


def _add_section_heading(doc: Document, title: str, samples: dict) -> None:
    paragraph = _new_paragraph(doc, samples["section_ppr"])
    _add_sample_run(paragraph, title.upper(), samples["section_rpr"], bold=True)


def _add_subsection_heading(doc: Document, section_index: int, sub_index: int, title: str, samples: dict) -> None:
    paragraph = _new_paragraph(doc, samples["subsection_ppr"])
    _add_sample_run(paragraph, f"{section_index}.{sub_index}   {title}", samples["subsection_rpr"], bold=True)


def _add_prompt_box(doc: Document, text: str, samples: dict) -> None:
    table = doc.add_table(rows=1, cols=1)
    _set_table_full_borders(table)
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    _set_full_cell_borders(cell)
    paragraph = cell.paragraphs[0]
    _apply_sample_ppr(paragraph, samples["body_ppr"])
    _append_rich_text(paragraph, text, samples["body_rpr"])


def _add_figure(doc: Document, item: dict, json_path: Path, samples: dict) -> None:

    # AI prompt emit (warna merah). Idempotent supaya tidak double-emit.
    _ai_title = str(item.get("Title") or item.get("title") or "").strip()
    _ai_prompt_text = str(item.get("Prompt") or item.get("Description") or "").strip()
    if _ai_title:
        _ai_full = f"[PROMPT UNTUK AI GAMBAR: {_ai_title}. {_ai_prompt_text or _ai_title}]"
        from docx.shared import RGBColor as _RGB
        from docx.enum.text import WD_ALIGN_PARAGRAPH as _WAP
        _ai_para = doc.add_paragraph()
        _ai_para.alignment = _WAP.CENTER
        _ai_run = _ai_para.add_run(_ai_full)
        _ai_run.italic = True
        _ai_run.font.color.rgb = _RGB(0xFF, 0x00, 0x00)
    path_text = str(item.get("Path") or item.get("path") or "").strip()
    title = str(item.get("Title") or item.get("title") or "").strip()
    number = str(item.get("ImageNumber") or item.get("number") or "").strip()

    try:
        width_cm = float(item.get("WidthCm", MAX_FIGURE_WIDTH_CM))
    except Exception:
        width_cm = MAX_FIGURE_WIDTH_CM
    width_cm = max(1.0, min(width_cm, MAX_FIGURE_WIDTH_CM))

    image_path = _resolve_path(path_text, json_path) if path_text else None
    paragraph = _new_paragraph(doc, samples["figure_ppr"])
    if image_path is not None and image_path.is_file():
        inline = paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
        _assign_inline_drawing_id(inline)
    else:
        fallback = str(item.get("Prompt") or title or path_text or "[missing figure]").strip()
        _add_prompt_box(doc, fallback, samples)
        return

    caption = _new_paragraph(doc, samples["figure_caption_ppr"])
    if number:
        _add_sample_run(caption, f"Gambar {number}: ", samples["figure_caption_rpr"])
    if title:
        _append_rich_text(caption, title, samples["figure_caption_rpr"])


def _add_table_caption(doc: Document, number: str, title: str, samples: dict) -> None:
    caption = _new_paragraph(doc, samples["table_caption_ppr"])
    label = f"TABEL {number} : " if number else "TABEL : "
    _add_sample_run(caption, label, samples["table_caption_rpr"])
    if title:
        _append_rich_text(caption, title, samples["table_caption_rpr"])


def _add_table(doc: Document, item: dict, samples: dict) -> None:
    number = str(item.get("TableNumber") or item.get("NumberiOrLetter") or "").strip()
    title = str(item.get("Title") or item.get("title") or "").strip()
    headers = list(item.get("Headers") or item.get("headers") or [])
    rows = list(item.get("Rows") or item.get("rows") or [])
    if not headers:
        return

    if number or title:
        _add_table_caption(doc, number, title, samples)

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))

    _set_table_full_borders(table)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_row_repeat_header(table.rows[0])

    for row in table.rows:
        for cell in row.cells:
            _set_full_cell_borders(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    for col_index, value in enumerate(headers):
        cell = table.rows[0].cells[col_index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(str(value))
        _set_table_run_format(run, bold=True)

    for row_index, row_data in enumerate(rows, start=1):
        for col_index in range(len(headers)):
            value = str(row_data[col_index]) if col_index < len(row_data) else ""
            cell = table.rows[row_index].cells[col_index]
            cell.text = ""
            paragraph = cell.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for block_index, block in enumerate(_split_body_blocks(value)):
                target = paragraph if block_index == 0 else cell.add_paragraph()
                if block_index > 0:
                    target.alignment = WD_ALIGN_PARAGRAPH.LEFT
                run = target.add_run(block)
                _set_table_run_format(run)

    _new_paragraph(doc, samples["blank_after_table_ppr"])


def _add_equation_group(doc: Document, item: dict, samples: dict) -> None:
    formulas = [str(value).strip() for value in item.get("Lines", []) if str(value).strip()]
    single = str(item.get("latex") or item.get("text") or "").strip()
    if not formulas and single:
        formulas = [single]
    if not formulas:
        return

    number = str(item.get("FormulaNumber") or item.get("NumberiOrLetter") or "").strip() or None
    for index, formula in enumerate(formulas):
        paragraph = _new_paragraph(doc, samples["equation_ppr"])
        if not _append_inline_math(paragraph, formula):
            fallback = _add_sample_run(paragraph, formula, samples["body_rpr"])
            fallback.italic = True
        if index == len(formulas) - 1 and number is not None:
            paragraph.add_run().add_tab()
            _add_sample_run(paragraph, f"({number})", samples["equation_num_rpr"])


def _render_content_item(doc: Document, item: dict, json_path: Path, samples: dict) -> None:
    item_id = str(item.get("id", "")).strip().lower()
    if item_id == "text":
        text = str(item.get("text", "")).strip()
        if text:
            _body_paragraphs(doc, text, samples)
        return
    if item_id in {"gambar", "image", "figure"}:
        _add_figure(doc, item, json_path, samples)
        return
    if item_id in {"tabel", "table"}:
        _add_table(doc, item, samples)
        return
    if item_id in {"rumus", "formula", "equation"}:
        _add_equation_group(doc, item, samples)


def _render_content(doc: Document, content, json_path: Path, samples: dict) -> None:
    if isinstance(content, str):
        if content.strip():
            _body_paragraphs(doc, content.strip(), samples)
        return
    if not isinstance(content, list):
        return
    for item in content:
        if isinstance(item, str):
            if item.strip():
                _body_paragraphs(doc, item.strip(), samples)
        elif isinstance(item, dict):
            _render_content_item(doc, item, json_path, samples)


def _sorted_child_section_keys(container: dict, prefix: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(prefix)}[a-z]+$")
    return sorted([key for key in container if pattern.match(key)])


def _render_subsections(
    doc: Document,
    section: dict,
    json_path: Path,
    samples: dict,
    section_key: str,
    section_index: int,
) -> None:
    child_keys = _sorted_child_section_keys(section, section_key)
    for sub_index, child_key in enumerate(child_keys, start=1):
        child = section.get(child_key)
        if not isinstance(child, dict):
            continue
        title = str(child.get("title", "")).strip()
        if title:
            _add_subsection_heading(doc, section_index, sub_index, title, samples)
        _render_content(doc, child.get("content", []), json_path, samples)


def _render_sections(doc: Document, config: dict, json_path: Path, samples: dict) -> None:
    section_keys = sorted(
        [key for key in config if re.fullmatch(r"section\d+", key)],
        key=lambda value: int(value.replace("section", "")),
    )
    for section_index, section_key in enumerate(section_keys, start=1):
        section = config.get(section_key)
        if not isinstance(section, dict):
            continue
        title = str(section.get("title", "")).strip()
        if title:
            _add_section_heading(doc, title, samples)
        _render_content(doc, section.get("content", []), json_path, samples)
        _render_subsections(doc, section, json_path, samples, section_key, section_index)


def _add_references(doc: Document, config: dict, samples: dict) -> None:
    references = _reference_texts(config)
    if not references:
        return

    title = "DAFTAR PUSTAKA"
    if isinstance(config.get("references"), dict):
        title = str(config["references"].get("title") or title).strip() or title

    heading = _new_paragraph(doc, samples["reference_heading_ppr"])
    _add_sample_run(heading, title.upper(), samples["reference_heading_rpr"], bold=True)

    for reference in references:
        paragraph = _new_paragraph(doc, samples["reference_item_ppr"])
        _append_rich_text(paragraph, _strip_reference_label(reference), samples["reference_item_rpr"])


def _replace_footer_placeholders(xml_bytes: bytes, replacement_text: str) -> bytes:
    root = etree.fromstring(xml_bytes)
    ns = {"w": NS_W}
    for paragraph in root.findall(".//w:p", ns):
        seen_tab = False
        blank_tail = False
        for child in paragraph:
            if child.tag == _wq("r"):
                if child.find(_wq("tab")) is not None:
                    seen_tab = True
                for text_node in child.findall(".//w:t", ns):
                    text = text_node.text or ""
                    if "First Author:" in text or "Penulis Pertama:" in text:
                        text_node.text = replacement_text
                        blank_tail = seen_tab
                    elif blank_tail and text:
                        text_node.text = ""
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def _patch_footer_placeholders(docx_path: Path, replacement_text: str) -> None:
    temp_path = docx_path.with_suffix(docx_path.suffix + ".tmp")
    with zipfile.ZipFile(docx_path, "r") as src, zipfile.ZipFile(temp_path, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.startswith("word/footer") and item.filename.endswith(".xml"):
                data = _replace_footer_placeholders(data, replacement_text)
            dst.writestr(item, data)
    temp_path.replace(docx_path)


def build_document(
    json_path: Path = JSON_PATH,
    output_path: Path | None = None,
    template_path: Path = TEMPLATE_PATH,
) -> Path:
    config = json.loads(Path(json_path).read_text(encoding="utf-8"))
    final_output = Path(output_path) if output_path else Path(json_path).parent / f"{JOURNAL_NAME}_output.docx"
    final_output.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy(str(template_path), str(final_output))
    doc = Document(str(final_output))
    _initialize_drawing_ids(doc)

    paragraph_samples = _capture_paragraph_samples(doc)
    front_table_samples = _capture_front_table_samples(doc.tables[0])

    blank_pre_table = doc.paragraphs[5]
    _update_title_paragraph(doc.paragraphs[0], config, paragraph_samples)
    _update_author_paragraph(doc.paragraphs[1], config, paragraph_samples)
    _update_email_paragraph(doc.paragraphs[2], config, paragraph_samples)
    _update_affiliation_paragraphs(doc, blank_pre_table, config, paragraph_samples)
    _clear_paragraph(blank_pre_table)
    _update_front_table(doc.tables[0], config, front_table_samples)

    first_table = doc.tables[0]
    _trim_template_body(doc, first_table)

    _new_paragraph(doc, paragraph_samples["blank_after_table_ppr"])
    _render_sections(doc, config, Path(json_path), paragraph_samples)
    _add_references(doc, config, paragraph_samples)

    doc.save(str(final_output))
    _patch_footer_placeholders(final_output, _footer_short_text(config))
    return final_output


def main() -> None:
    if len(sys.argv) >= 2:
        json_arg = Path(sys.argv[1])
        output_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
        template_arg = Path(sys.argv[3]) if len(sys.argv) >= 4 else TEMPLATE_PATH
        if not json_arg.exists():
            print(f"ERROR: file not found: {json_arg}")
            sys.exit(1)
        result = build_document(json_arg, output_arg, template_arg)
        print(f"Generated: {result}")
        return

    json_files = sorted(
        path for path in BASE_DIR.glob("*.json")
        if path.name.lower() not in {"package.json", "tsconfig.json", "settings.json"}
    )
    if not json_files:
        print("ERROR: no JSON files found")
        return

    ok = 0
    err = 0
    for json_file in json_files:
        try:
            result = build_document(json_file)
            print(f"Generated: {result.name}")
            ok += 1
        except Exception as exc:
            print(f"ERROR: {json_file.name}: {exc}")
            err += 1
    print(f"Done: {ok} OK, {err} errors")




def _set_table_full_borders(table) -> None:
    """Pastikan tabel punya border tegas/visible (val=single, sz=4 = 0.5pt).

    Dipanggil setelah doc.add_table() supaya tabel data keliatan di Word.
    Auto-injected oleh _fix_table_borders.py untuk lulus audit border check.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
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


if __name__ == "__main__":
    main()