"""
JTUNDIPgen.py -- Generator dokumen JTUNDIP/TEKNIK dari JSON.

Dokumen dibangun dari JTUNDIP.docx asli dengan pendekatan salin template lalu
menulis ulang body menggunakan sample XML dari template asli agar header,
footer, styles, numbering, dan section layout tetap mengikuti dokumen sumber.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "_PLC-MediapipeID.json"
TEMPLATE_PATH = BASE_DIR / "JTUNDIP.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

MAX_FIGURE_WIDTH_CM = 7.8
RIGHT_TAB_PT = 225.0
FORMULA_TAB_PT = 70.0

NS_MAP_STRICT = {
    b"http://purl.oclc.org/ooxml/wordprocessingml/main": b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    b"http://purl.oclc.org/ooxml/officeDocument/relationships": b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/drawingml/main": b"http://schemas.openxmlformats.org/drawingml/2006/main",
    b"http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing": b"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    b"http://purl.oclc.org/ooxml/officeDocument/math": b"http://schemas.openxmlformats.org/officeDocument/2006/math",
}

XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]

KEYWORD_ID_MAP = {
    "Hand Gesture Recognition": "Pengenalan Gestur Tangan",
    "PLC Control": "Kendali PLC",
    "MediaPipe": "MediaPipe",
    "Modbus TCP": "Modbus TCP",
    "Industry 4.0": "Industri 4.0",
    "Threading": "Threading",
}

DEFAULT_ID_ABSTRACT = (
    "Tuliskan abstrak berbahasa Indonesia secara ringkas yang memuat latar belakang, "
    "tujuan, metode, hasil utama, dan simpulan penelitian ini."
)

DEFAULT_EN_ABSTRACT = (
    "Shared control panels on production lines create contamination risks in food-grade and cleanroom "
    "environments. This paper presents GestPLC and evaluates whether a standard USB webcam combined with a "
    "geometric rule-based classifier can control a Schneider Modicon M221 PLC without GPU acceleration or a "
    "trained neural network. MediaPipe extracts 21 hand landmarks per frame on an Intel Core i7 CPU, and an "
    "angle-threshold engine converts the landmarks into Modbus TCP coil-write commands through FC15. Camera "
    "capture, gesture classification, and Modbus I/O run in separate Python threads so delayed network "
    "responses do not stall the vision loop. Under 300 lux illumination, the classifier achieved a macro "
    "F1-score of 95.4% and an average Modbus round-trip delay of 12.3 ms. A 24-hour endurance test recorded "
    "872,640 transactions with a 99.97% write success rate, although the observed communication MTBF was only "
    "8.2 hours. These results show that landmark geometry, rather than deep learning, is sufficient for "
    "six-gesture PLC control on commodity hardware."
)

DEFAULT_ACKNOWLEDGMENT = (
    "Penulis menyampaikan terima kasih kepada lingkungan laboratorium dan institusi afiliasi penulis atas "
    "dukungan fasilitas, perangkat komputasi, dan infrastruktur PLC yang digunakan selama pengembangan dan "
    "pengujian sistem GestPLC."
)

_XSLT = None


@dataclass
class RenderState:
    figure_number: int = 0
    table_number: int = 0
    formula_number: int = 0


def _wq(tag: str) -> str:
    return f"{{{NS_W}}}{tag}"


def _strict_to_trans(data: bytes) -> bytes:
    for old, new in NS_MAP_STRICT.items():
        data = data.replace(old, new)
    return data


def _text_of_run(run_el: etree._Element) -> str:
    texts = []
    for text_el in run_el.findall(f".//{_wq('t')}"):
        if text_el.text:
            texts.append(text_el.text)
    return "".join(texts)


def _clone(element: etree._Element | None) -> etree._Element | None:
    return deepcopy(element) if element is not None else None


def _remove_numpr(ppr: etree._Element | None) -> etree._Element | None:
    cloned = _clone(ppr)
    if cloned is None:
        return None
    num_pr = cloned.find(_wq("numPr"))
    if num_pr is not None:
        cloned.remove(num_pr)
    return cloned


def _apply_sample_ppr(paragraph, sample_ppr: etree._Element | None) -> None:
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


def _new_paragraph(doc: Document, sample_ppr: etree._Element | None = None):
    paragraph = doc.add_paragraph()
    if sample_ppr is not None:
        _apply_sample_ppr(paragraph, sample_ppr)
    return paragraph


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _set_document_final_sectpr(doc: Document, sectpr: etree._Element) -> None:
    body = doc._element.body
    current = body.find(qn("w:sectPr"))
    if current is not None:
        body.remove(current)
    body.append(deepcopy(sectpr))


def _append_front_section_break(
    doc: Document,
    sample_ppr: etree._Element | None,
    sectpr: etree._Element,
) -> None:
    paragraph = _new_paragraph(doc, sample_ppr)
    ppr = paragraph._p.get_or_add_pPr()
    old = ppr.find(qn("w:sectPr"))
    if old is not None:
        ppr.remove(old)
    ppr.append(deepcopy(sectpr))


def _set_run_font(run, font_name: str) -> None:
    run.font.name = font_name
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def _add_sample_run(
    paragraph,
    text: str,
    sample_rpr: etree._Element | None,
    *,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    superscript: bool = False,
    font_name: str | None = None,
):
    run = paragraph.add_run(text)
    _apply_sample_rpr(run, sample_rpr)
    if font_name is not None:
        _set_run_font(run, font_name)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline
    if superscript:
        run.font.superscript = True
    return run


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
                formula = normalized[index + 1 : closing]
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


def _set_math_rpr_defaults(rpr: etree._Element, half_points: int = 20) -> None:
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), "Cambria Math")

    for tag in ("sz", "szCs"):
        size_el = rpr.find(qn(f"w:{tag}"))
        if size_el is None:
            size_el = OxmlElement(f"w:{tag}")
            rpr.append(size_el)
        size_el.set(qn("w:val"), str(half_points))


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


def _append_inline_math(paragraph, latex: str) -> bool:
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


def _append_rich_text(
    paragraph,
    text: str,
    sample_rpr: etree._Element | None,
    *,
    base_bold: bool = False,
    base_italic: bool = False,
    base_underline: bool = False,
    font_name: str | None = None,
) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            paragraph.add_run().add_break()
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                _add_sample_run(
                    paragraph,
                    token["value"],
                    sample_rpr,
                    italic=True,
                    font_name=font_name,
                )
            continue
        _add_sample_run(
            paragraph,
            token["value"],
            sample_rpr,
            bold=base_bold or token["bold"],
            italic=base_italic or token["italic"],
            underline=base_underline or token["underline"],
            font_name=font_name,
        )


def _set_spacing(paragraph, before: float | None = None, after: float | None = None) -> None:
    if before is not None:
        paragraph.paragraph_format.space_before = Pt(before)
    if after is not None:
        paragraph.paragraph_format.space_after = Pt(after)


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    blocks = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return blocks or [normalized.strip()]


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative
    return BASE_DIR / path


def _smart_heading_case(text: str) -> str:
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return cleaned
    if cleaned.isupper():
        words = []
        for word in cleaned.split():
            if len(word) <= 4 and word.isupper():
                words.append(word)
            else:
                words.append(word.capitalize())
        return " ".join(words)
    return cleaned


def _parse_author_entries(config: dict) -> list[dict[str, str]]:
    authors = config.get("authors", [])
    entries: list[dict[str, str]] = []
    if isinstance(authors, list):
        for author in authors:
            if not isinstance(author, dict):
                continue
            name = str(author.get("name") or "").strip()
            if not name:
                continue
            entries.append(
                {
                    "name": name,
                    "affiliation": str(author.get("affiliation") or "").strip(),
                    "location": str(author.get("location") or "").strip(),
                    "email": str(author.get("email") or "").strip(),
                }
            )
    if entries:
        return entries
    return [
        {
            "name": "Nama Penulis",
            "affiliation": "Afiliasi Penulis",
            "location": "Kota, Indonesia",
            "email": "email@domain.ac.id",
        }
    ]


def _title_text(config: dict) -> str:
    return str(config.get("title") or "Judul Artikel").strip() or "Judul Artikel"


def _abstract_id_text(config: dict) -> str:
    for key in ("abstract_id", "abstrak", "abstract"):
        value = str(config.get(key) or "").strip()
        if value:
            return value
    return DEFAULT_ID_ABSTRACT


def _abstract_en_text(config: dict) -> str:
    for key in ("abstract_en", "abstract_english", "english_abstract", "abstrak_en"):
        value = str(config.get(key) or "").strip()
        if value:
            return value
    return DEFAULT_EN_ABSTRACT


def _keywords_en_list(config: dict) -> list[str]:
    raw = config.get("keywords", [])
    if isinstance(raw, list):
        items = [str(item).strip() for item in raw if str(item).strip()]
        if items:
            return items
    for key in ("keywords_en", "english_keywords"):
        value = config.get(key)
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                return items
    return [
        "Gesture Control",
        "Programmable Logic Controller",
        "Computer Vision",
        "Industrial Communication",
        "Automation",
    ]


def _keywords_id_list(config: dict) -> list[str]:
    for key in ("keywords_id", "kata_kunci"):
        value = config.get(key)
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                return items
    result = []
    for keyword in _keywords_en_list(config):
        result.append(KEYWORD_ID_MAP.get(keyword, keyword))
    return result


def _format_reference(item) -> str:
    """Format a reference dict (with authors, year, title, etc.) into a citation string."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()
    
    # Check if already has text field
    text = item.get("text") or item.get("Text") or item.get("value")
    if text:
        return str(text).strip()
    
    # Build from fields
    parts = []
    
    # Authors
    authors = item.get("authors", [])
    if authors:
        if isinstance(authors, list):
            parts.append(", ".join(str(a) for a in authors))
        else:
            parts.append(str(authors))
    
    # Year
    year = item.get("year")
    if year:
        parts.append(f"({year})")
    
    # Title
    title = item.get("title", "")
    if title:
        parts.append(f'"{title},"')
    
    # Journal or Conference
    jname = item.get("journal") or item.get("conference") or ""
    if jname:
        parts.append(str(jname) + ",")
    
    # Volume
    vol = item.get("volume", "")
    if vol:
        parts.append(f"vol. {vol},")
    
    # Issue
    issue = item.get("issue", "")
    if issue:
        parts.append(f"no. {issue},")
    
    # Pages
    pages = item.get("pages", "")
    if pages:
        parts.append(f"pp. {pages},")
    
    # DOI
    doi = item.get("doi", "")
    if doi:
        parts.append(f"doi: {doi}.")
    
    # URL
    url = item.get("url", "")
    if url:
        accessed = item.get("accessed", "")
        if accessed:
            parts.append(f"[Online]. Available: {url} [Accessed: {accessed}].")
        else:
            parts.append(f"[Online]. Available: {url}.")
    
    # Publisher (for books)
    publisher = item.get("publisher", "")
    if publisher and not jname:
        location = item.get("location", "")
        if location:
            parts.append(f"{location}: {publisher}.")
        else:
            parts.append(f"{publisher}.")
    
    result = " ".join(str(p) for p in parts if p).strip()
    result = result.replace(" , ", ", ").replace(" .", ".")
    if result.endswith(","):
        result = result[:-1] + "."
    if not result.endswith("."):
        result = result + "."
    
    return result


def _reference_items(config: dict) -> list[str]:
    references = config.get("references")

    # Normalize to list of entries (dicts)
    raw_entries = []
    if isinstance(references, list):
        raw_entries = references
    elif isinstance(references, dict):
        # Try multiple key names used by different JSON generators
        for key in ("content", "items", "references"):
            candidate = references.get(key)
            if isinstance(candidate, list):
                raw_entries = candidate
                break

    items = []
    for entry in raw_entries:
        text = _format_reference(entry)
        if text:
            items.append(text)
    return items


def _clean_reference_label(text: str) -> str:
    return re.sub(r"^\s*\[\d+\]\s*", "", text).strip()


def _acknowledgment_text(config: dict) -> str:
    for key in ("acknowledgment", "acknowledgement", "ucapan_terima_kasih"):
        value = str(config.get(key) or "").strip()
        if value:
            return value
    affiliations = []
    for author in _parse_author_entries(config):
        value = ", ".join(
            part for part in (author.get("affiliation", ""), author.get("location", "")) if part
        )
        if value and value not in affiliations:
            affiliations.append(value)
    if affiliations:
        joined = "; ".join(affiliations)
        return (
            f"Penulis menyampaikan terima kasih kepada {joined} atas dukungan fasilitas laboratorium, "
            "infrastruktur komputasi, dan akses perangkat PLC selama pelaksanaan penelitian ini."
        )
    return DEFAULT_ACKNOWLEDGMENT


def _load_template_samples(template_path: Path) -> dict[str, etree._Element | None]:
    with zipfile.ZipFile(template_path) as archive:
        raw = _strict_to_trans(archive.read("word/document.xml"))
    root = etree.fromstring(raw)
    body = root.find(_wq("body"))
    paragraphs = body.findall(_wq("p")) if body is not None else []
    tables = body.findall(_wq("tbl")) if body is not None else []

    def clone_ppr(index: int):
        return _clone(paragraphs[index].find(_wq("pPr")))

    def clone_rpr(index: int, run_index: int):
        runs = paragraphs[index].findall(_wq("r"))
        if run_index >= len(runs):
            return None
        return _clone(runs[run_index].find(_wq("rPr")))

    def clone_first_text_rpr(index: int):
        for run in paragraphs[index].findall(_wq("r")):
            if _text_of_run(run).strip():
                return _clone(run.find(_wq("rPr")))
        return None

    def clone_last_text_rpr(index: int):
        runs = paragraphs[index].findall(_wq("r"))
        for run in reversed(runs):
            if _text_of_run(run).strip():
                return _clone(run.find(_wq("rPr")))
        return None

    def table_para(row_index: int, cell_index: int):
        if not tables:
            return None, None
        rows = tables[0].findall(_wq("tr"))
        if row_index >= len(rows):
            return None, None
        cells = rows[row_index].findall(_wq("tc"))
        if cell_index >= len(cells):
            return None, None
        paragraph = cells[cell_index].find(_wq("p"))
        if paragraph is None:
            return None, None
        ppr = _clone(paragraph.find(_wq("pPr")))
        rpr = None
        for run in paragraph.findall(_wq("r")):
            if _text_of_run(run).strip() or run.find(_wq("rPr")) is not None:
                rpr = _clone(run.find(_wq("rPr")))
                break
        return ppr, rpr

    header_cell_ppr, header_cell_rpr = table_para(0, 0)
    body_cell_ppr, body_cell_rpr = table_para(1, 0)

    front_break_ppr = clone_ppr(22)
    front_sectpr = None
    front_break_owner_ppr = paragraphs[23].find(_wq("pPr"))
    if front_break_owner_ppr is not None:
        front_sectpr = _clone(front_break_owner_ppr.find(_wq("sectPr")))

    final_sectpr = _clone(body.find(_wq("sectPr"))) if body is not None else None

    return {
        "title_ppr": clone_ppr(0),
        "title_rpr": clone_rpr(0, 0),
        "title_gap_ppr": clone_ppr(2),
        "author_ppr": clone_ppr(4),
        "author_name_rpr": clone_rpr(4, 0),
        "author_sup_rpr": clone_rpr(4, 4),
        "author_star_rpr": clone_rpr(4, 5),
        "affiliation_ppr": clone_ppr(6),
        "affiliation_sup_rpr": clone_rpr(6, 0),
        "affiliation_text_rpr": clone_rpr(6, 1),
        "post_author_gap_ppr": clone_ppr(9),
        "abstract_title_ppr": clone_ppr(10),
        "abstract_title_rpr": clone_rpr(10, 0),
        "abstract_gap_ppr": clone_ppr(11),
        "abstract_body_ppr": clone_ppr(12),
        "abstract_body_rpr": clone_first_text_rpr(12),
        "keywords_ppr": clone_ppr(14),
        "keywords_label_rpr": clone_rpr(14, 0),
        "keywords_body_rpr": clone_rpr(14, 2),
        "post_keywords_gap_ppr": clone_ppr(15),
        "post_abstract_en_gap_ppr": clone_ppr(17),
        "post_keywords_en_gap_ppr": clone_ppr(21),
        "front_break_ppr": front_break_ppr,
        "front_sectpr": front_sectpr,
        "section_ppr": _remove_numpr(clone_ppr(24)),
        "section_rpr": clone_first_text_rpr(24),
        "body_ppr": clone_ppr(25),
        "body_rpr": clone_first_text_rpr(25),
        "subsection_ppr": _remove_numpr(clone_ppr(33)),
        "subsection_rpr": clone_first_text_rpr(54),
        "figure_caption_ppr": _remove_numpr(clone_ppr(48)),
        "figure_label_rpr": clone_rpr(48, 0),
        "figure_text_rpr": clone_rpr(48, 2),
        "table_caption_ppr": _remove_numpr(clone_ppr(50)),
        "table_label_rpr": clone_rpr(50, 0),
        "table_text_rpr": clone_rpr(50, 1),
        "equation_ppr": _remove_numpr(clone_ppr(63)),
        "equation_body_rpr": clone_first_text_rpr(25),
        "equation_num_rpr": clone_last_text_rpr(62),
        "reference_heading_ppr": _remove_numpr(clone_ppr(106)),
        "reference_heading_rpr": clone_first_text_rpr(106),
        "reference_item_ppr": clone_ppr(108),
        "reference_item_rpr": clone_first_text_rpr(108),
        "table_header_cell_ppr": header_cell_ppr,
        "table_header_cell_rpr": header_cell_rpr,
        "table_body_cell_ppr": body_cell_ppr,
        "table_body_cell_rpr": body_cell_rpr,
        "body_final_sectpr": final_sectpr,
    }


def _add_title(doc: Document, config: dict, samples: dict[str, etree._Element | None]) -> None:
    paragraph = _new_paragraph(doc, samples["title_ppr"])
    _add_sample_run(paragraph, _title_text(config), samples["title_rpr"])
    _new_paragraph(doc, samples["title_gap_ppr"])


def _add_authors(doc: Document, config: dict, samples: dict[str, etree._Element | None]) -> None:
    authors = _parse_author_entries(config)
    author_para = _new_paragraph(doc, samples["author_ppr"])

    affiliation_numbers: dict[tuple[str, str], int] = {}
    grouped_affiliations: list[dict[str, object]] = []
    author_numbers: list[int] = []

    for author in authors:
        key = (author["affiliation"], author["location"])
        number = affiliation_numbers.get(key)
        if number is None:
            number = len(grouped_affiliations) + 1
            affiliation_numbers[key] = number
            grouped_affiliations.append(
                {
                    "number": number,
                    "affiliation": author["affiliation"],
                    "location": author["location"],
                    "emails": [],
                }
            )
        author_numbers.append(number)
        if author["email"]:
            group = grouped_affiliations[number - 1]
            emails = group["emails"]
            if author["email"] not in emails:
                emails.append(author["email"])

    for index, author in enumerate(authors):
        if index:
            _add_sample_run(author_para, ", ", samples["author_name_rpr"])
        _add_sample_run(author_para, author["name"], samples["author_name_rpr"])
        _add_sample_run(
            author_para, str(author_numbers[index]), samples["author_sup_rpr"], superscript=True
        )
        if index == 0:
            star_rpr = (
                samples["author_star_rpr"]
                if samples["author_star_rpr"] is not None
                else samples["author_sup_rpr"]
            )
            _add_sample_run(author_para, "*", star_rpr, superscript=True)

    for group in grouped_affiliations:
        paragraph = _new_paragraph(doc, samples["affiliation_ppr"])
        _add_sample_run(
            paragraph, str(group["number"]), samples["affiliation_sup_rpr"], superscript=True
        )
        _add_sample_run(paragraph, " ", samples["affiliation_sup_rpr"], superscript=True)
        details = [part for part in (str(group["affiliation"]), str(group["location"])) if part]
        body_text = ", ".join(details) if details else "Afiliasi Penulis"
        emails = [str(item) for item in group["emails"] if str(item)]
        if emails:
            body_text = f"{body_text}. Email: {'; '.join(emails)}"
        _append_rich_text(paragraph, body_text, samples["affiliation_text_rpr"], base_italic=True)

    _new_paragraph(doc, samples["post_author_gap_ppr"])


def _add_abstract_block(
    doc: Document,
    title_text: str,
    abstract_text: str,
    keyword_label: str,
    keywords: list[str],
    samples: dict[str, etree._Element | None],
) -> None:
    title_paragraph = _new_paragraph(doc, samples["abstract_title_ppr"])
    _add_sample_run(title_paragraph, title_text, samples["abstract_title_rpr"], bold=True)

    _new_paragraph(doc, samples["abstract_gap_ppr"])

    abstract_paragraph = _new_paragraph(doc, samples["abstract_body_ppr"])
    _append_rich_text(
        abstract_paragraph, abstract_text, samples["abstract_body_rpr"], base_italic=True
    )

    _new_paragraph(doc, samples["post_keywords_gap_ppr"])

    keyword_paragraph = _new_paragraph(doc, samples["keywords_ppr"])
    _append_rich_text(
        keyword_paragraph, f"{keyword_label}: ", samples["keywords_label_rpr"], base_bold=True
    )
    keyword_text = "; ".join(keywords).strip()
    if keyword_text and not keyword_text.endswith("."):
        keyword_text += "."
    _append_rich_text(
        keyword_paragraph, keyword_text, samples["keywords_body_rpr"], base_italic=False
    )


def _add_front_matter(
    doc: Document, config: dict, samples: dict[str, etree._Element | None]
) -> None:
    _add_title(doc, config, samples)
    _add_authors(doc, config, samples)

    _add_abstract_block(
        doc,
        "Abstrak",
        _abstract_id_text(config),
        "Kata kunci",
        _keywords_id_list(config),
        samples,
    )

    _new_paragraph(doc, samples["post_keywords_gap_ppr"])

    _add_abstract_block(
        doc,
        "Abstract",
        _abstract_en_text(config),
        "Keywords",
        _keywords_en_list(config),
        samples,
    )

    _new_paragraph(doc, samples["post_keywords_en_gap_ppr"])


def _body_paragraph(doc: Document, text: str, samples: dict[str, etree._Element | None]) -> None:
    for block in _split_body_blocks(text):
        paragraph = _new_paragraph(doc, samples["body_ppr"])
        _append_rich_text(paragraph, block, samples["body_rpr"])


def _add_section_heading(
    doc: Document,
    number: int,
    title: str,
    samples: dict[str, etree._Element | None],
) -> None:
    paragraph = _new_paragraph(doc, samples["section_ppr"])
    _set_spacing(paragraph, before=3.0, after=3.0)
    _append_rich_text(
        paragraph,
        _smart_heading_case(title),
        samples["section_rpr"],
        base_bold=True,
    )


def _add_subsection_heading(
    doc: Document,
    section_number: int,
    subsection_number: int,
    title: str,
    samples: dict[str, etree._Element | None],
) -> None:
    paragraph = _new_paragraph(doc, samples["subsection_ppr"])
    _set_spacing(paragraph, before=3.0, after=3.0)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    subsection_rpr = (
        samples["subsection_rpr"]
        if samples["subsection_rpr"] is not None
        else samples["section_rpr"]
    )
    _append_rich_text(
        paragraph,
        _smart_heading_case(title),
        subsection_rpr,
        base_bold=True,
    )


def _add_missing_figure_notice(
    doc: Document,
    text: str,
    samples: dict[str, etree._Element | None],
) -> None:
    paragraph = _new_paragraph(doc, samples["body_ppr"])
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    _set_spacing(paragraph, before=3.0, after=3.0)
    _append_rich_text(paragraph, text, samples["body_rpr"], base_italic=True)


def _add_figure(
    doc: Document,
    item: dict,
    json_path: Path,
    samples: dict[str, etree._Element | None],
    state: RenderState,
) -> None:

    state.figure_number += 1
    number = state.figure_number
    title = str(item.get("Title") or item.get("title") or f"Judul gambar {number}").strip()
    path_text = str(item.get("Path") or item.get("path") or "").strip()
    prompt = str(item.get("Prompt") or "").strip()

    try:
        width_cm = float(item.get("WidthCm") or MAX_FIGURE_WIDTH_CM)
    except Exception:
        width_cm = MAX_FIGURE_WIDTH_CM
    width_cm = min(max(width_cm, 1.0), MAX_FIGURE_WIDTH_CM)

    image_path = _resolve_path(path_text, json_path) if path_text else None
    if image_path is not None and image_path.is_file():
        paragraph = _new_paragraph(doc, samples["body_ppr"])
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.first_line_indent = Pt(0)
        _set_spacing(paragraph, before=3.0, after=3.0)
        paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
    else:
        fallback = prompt or title or f"Gambar {number} belum tersedia."
        _add_missing_figure_notice(doc, f"[Gambar {number} belum tersedia: {fallback}]", samples)

    caption = _new_paragraph(doc, samples["figure_caption_ppr"])
    caption.alignment = WD_ALIGN_PARAGRAPH.LEFT
    caption.paragraph_format.first_line_indent = Pt(0)
    _set_spacing(caption, before=3.0, after=6.0)
    _add_sample_run(caption, f"Gambar {number}", samples["figure_label_rpr"], bold=True)
    _add_sample_run(caption, ". ", samples["figure_text_rpr"])
    _append_rich_text(caption, title, samples["figure_text_rpr"])


def _clear_cell(cell) -> None:
    tc = cell._tc
    for child in list(tc):
        if child.tag != qn("w:tcPr"):
            tc.remove(child)
    tc.append(OxmlElement("w:p"))


def _set_cell_border(cell, edge: str, attrs: dict[str, str]) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    border = tc_borders.find(qn(f"w:{edge}"))
    if border is None:
        border = OxmlElement(f"w:{edge}")
        tc_borders.append(border)
    for key, value in attrs.items():
        border.set(qn(f"w:{key}"), value)


def _set_horizontal_only_borders(cell, *, top: bool = False, bottom: bool = False) -> None:
    visible = {"val": "single", "sz": "4", "space": "0", "color": "auto"}
    hidden = {"val": "none"}
    _set_cell_border(cell, "top", visible if top else hidden)
    _set_cell_border(cell, "bottom", visible if bottom else hidden)
    _set_cell_border(cell, "left", hidden)
    _set_cell_border(cell, "right", hidden)


def _set_table_border_defaults(table) -> None:
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
        border = tbl_borders.find(qn(f"w:{edge}"))
        if border is None:
            border = OxmlElement(f"w:{edge}")
            tbl_borders.append(border)
        # Template JTUNDIP NO_BORDERS - jangan force border explicit
        border.set(qn("w:val"), "nil")


def _fill_cell_text(
    cell,
    text: str,
    sample_ppr: etree._Element | None,
    sample_rpr: etree._Element | None,
    *,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    base_bold: bool = False,
    font_size_pt: float | None = None,
) -> None:
    _clear_cell(cell)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    paragraph = cell.paragraphs[0]
    _apply_sample_ppr(paragraph, sample_ppr)
    paragraph.alignment = align
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    _append_rich_text(paragraph, text, sample_rpr, base_bold=base_bold)
    if font_size_pt is not None:
        for run in paragraph.runs:
            run.font.size = Pt(font_size_pt)


def _add_table(
    doc: Document,
    item: dict,
    samples: dict[str, etree._Element | None],
    state: RenderState,
) -> None:
    headers = [str(value) for value in (item.get("Headers") or item.get("headers") or [])]
    rows = [list(map(str, row)) for row in (item.get("Rows") or item.get("rows") or [])]
    if not headers:
        return

    state.table_number += 1
    number = state.table_number
    title = str(item.get("Title") or item.get("title") or f"Judul tabel {number}").strip()

    caption = _new_paragraph(doc, samples["table_caption_ppr"])
    caption.alignment = WD_ALIGN_PARAGRAPH.LEFT
    caption.paragraph_format.first_line_indent = Pt(0)
    _set_spacing(caption, before=6.0, after=3.0)
    _add_sample_run(caption, f"Tabel {number}", samples["table_label_rpr"], bold=True)
    _add_sample_run(caption, ". ", samples["table_text_rpr"])
    _append_rich_text(caption, title, samples["table_text_rpr"])

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_border_defaults(table)

    font_size_pt = 8.0 if len(headers) >= 6 else 9.0

    for col_index, header in enumerate(headers):
        cell = table.rows[0].cells[col_index]
        _set_horizontal_only_borders(cell, top=True, bottom=True)
        _fill_cell_text(
            cell,
            header,
            samples["table_header_cell_ppr"],
            samples["table_header_cell_rpr"],
            align=WD_ALIGN_PARAGRAPH.CENTER,
            base_bold=True,
            font_size_pt=font_size_pt,
        )

    for row_index, row_values in enumerate(rows, start=1):
        is_last_row = row_index == len(rows)
        for col_index in range(len(headers)):
            value = row_values[col_index] if col_index < len(row_values) else ""
            cell = table.rows[row_index].cells[col_index]
            _set_horizontal_only_borders(cell, bottom=is_last_row)
            align = WD_ALIGN_PARAGRAPH.CENTER if len(value) <= 18 else WD_ALIGN_PARAGRAPH.LEFT
            _fill_cell_text(
                cell,
                value,
                samples["table_body_cell_ppr"],
                samples["table_body_cell_rpr"],
                align=align,
                font_size_pt=font_size_pt,
            )

    spacer = _new_paragraph(doc, samples["body_ppr"])
    spacer.paragraph_format.first_line_indent = Pt(0)
    _set_spacing(spacer, before=0.0, after=3.0)


def _add_equation(
    doc: Document,
    item: dict,
    samples: dict[str, etree._Element | None],
    state: RenderState,
) -> None:
    formula = str(item.get("latex") or item.get("text") or "").strip()
    if not formula:
        return

    state.formula_number += 1
    number = str(item.get("FormulaNumber") or state.formula_number).strip() or str(
        state.formula_number
    )

    paragraph = _new_paragraph(doc, samples["equation_ppr"])
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(0)
    _set_spacing(paragraph, before=3.0, after=3.0)
    paragraph.paragraph_format.tab_stops.add_tab_stop(Pt(FORMULA_TAB_PT))
    paragraph.paragraph_format.tab_stops.add_tab_stop(Pt(RIGHT_TAB_PT), WD_TAB_ALIGNMENT.RIGHT)

    paragraph.add_run().add_tab()
    if not _append_inline_math(paragraph, formula):
        _add_sample_run(paragraph, formula, samples["equation_body_rpr"], italic=True)
    paragraph.add_run().add_tab()
    _add_sample_run(
        paragraph, f"({number})", samples["equation_num_rpr"] or samples["equation_body_rpr"]
    )


def _render_content_item(
    doc: Document,
    item: dict,
    json_path: Path,
    samples: dict[str, etree._Element | None],
    state: RenderState,
) -> None:
    item_id = str(item.get("id") or "").strip().lower()
    if item_id == "text":
        text = str(item.get("text") or "").strip()
        if text:
            _body_paragraph(doc, text, samples)
        return
    if item_id in {"gambar", "image", "figure"}:
        _add_figure(doc, item, json_path, samples, state)
        return
    if item_id in {"tabel", "table"}:
        _add_table(doc, item, samples, state)
        return
    if item_id in {"rumus", "formula", "equation"}:
        _add_equation(doc, item, samples, state)
        return


def _render_content_sequence(
    doc: Document,
    content,
    json_path: Path,
    samples: dict[str, etree._Element | None],
    state: RenderState,
) -> None:
    if isinstance(content, str):
        if content.strip():
            _body_paragraph(doc, content.strip(), samples)
        return
    if not isinstance(content, list):
        return
    for item in content:
        if isinstance(item, str):
            if item.strip():
                _body_paragraph(doc, item.strip(), samples)
        elif isinstance(item, dict):
            _render_content_item(doc, item, json_path, samples, state)


def _render_sections(
    doc: Document,
    config: dict,
    json_path: Path,
    samples: dict[str, etree._Element | None],
) -> int:
    state = RenderState()
    section_keys = sorted(
        [key for key in config.keys() if re.fullmatch(r"section\d+", key)],
        key=lambda key: int(key.replace("section", "")),
    )

    for section_index, section_key in enumerate(section_keys, start=1):
        section = config.get(section_key)
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or f"Bagian {section_index}").strip()
        _add_section_heading(doc, section_index, title, samples)
        _render_content_sequence(doc, section.get("content", []), json_path, samples, state)

        subsection_keys = sorted(
            [
                key
                for key, value in section.items()
                if isinstance(value, dict) and re.fullmatch(rf"{re.escape(section_key)}[a-z]+", key)
            ],
            key=lambda key: key[len(section_key) :],
        )
        for subsection_index, subsection_key in enumerate(subsection_keys, start=1):
            subsection = section[subsection_key]
            title = str(
                subsection.get("title") or f"Subbagian {section_index}.{subsection_index}"
            ).strip()
            _add_subsection_heading(doc, section_index, subsection_index, title, samples)
            _render_content_sequence(doc, subsection.get("content", []), json_path, samples, state)

    acknowledgment_number = len(section_keys) + 1
    _add_section_heading(doc, acknowledgment_number, "Ucapan Terima Kasih", samples)
    _body_paragraph(doc, _acknowledgment_text(config), samples)
    return acknowledgment_number


def _add_references(doc: Document, config: dict, samples: dict[str, etree._Element | None]) -> None:
    items = _reference_items(config)
    heading = _new_paragraph(doc, samples["reference_heading_ppr"])
    _set_spacing(heading, before=3.0, after=3.0)
    _append_rich_text(heading, "Daftar Pustaka", samples["reference_heading_rpr"], base_bold=True)

    if not items:
        placeholder = _new_paragraph(doc, samples["reference_item_ppr"])
        _append_rich_text(
            placeholder,
            "Tambahkan daftar pustaka sesuai gaya penulisan JTUNDIP/TEKNIK.",
            samples["reference_item_rpr"],
        )
        return

    for item in items:
        paragraph = _new_paragraph(doc, samples["reference_item_ppr"])
        _append_rich_text(paragraph, _clean_reference_label(item), samples["reference_item_rpr"])


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

    samples = _load_template_samples(template_path)

    shutil.copy(str(template_path), str(final_output))
    doc = Document(str(final_output))
    _clear_document_body(doc)
    if samples["body_final_sectpr"] is None:
        raise RuntimeError("Template JTUNDIP tidak memiliki final sectPr.")
    _set_document_final_sectpr(doc, samples["body_final_sectpr"])

    _add_front_matter(doc, config, samples)
    if samples["front_sectpr"] is None:
        raise RuntimeError("Template JTUNDIP tidak memiliki section break front matter.")
    _append_front_section_break(doc, samples["front_break_ppr"], samples["front_sectpr"])
    _render_sections(doc, config, Path(json_path), samples)
    # Tambahkan inline section break (cols=2) sebelum references untuk match
    # 3-section struktur original: title 1col -> body 2col -> refs 2col.
    if samples["body_final_sectpr"] is not None:
        _append_front_section_break(doc, samples["front_break_ppr"], samples["body_final_sectpr"])
    _add_references(doc, config, samples)

    doc.save(str(final_output))
    print(f"Generated: {final_output}")
    return final_output


def build_pdf(json_path: Path, pdf_path: Path, template_path=None) -> Path:
    """Build a PDF for this journal template from a paper JSON.

    Calls build_document() to produce a .docx, then converts to .pdf
    via LibreOffice headless.  Final PDF is written to ``pdf_path``.
    """
    from ._render_pdf import build_pdf_from_builder
    return build_pdf_from_builder(build_document, json_path, pdf_path, template_path)

def main() -> None:
    if len(sys.argv) >= 2:
        json_arg = Path(sys.argv[1])
        output_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
        template_arg = Path(sys.argv[3]) if len(sys.argv) >= 4 else TEMPLATE_PATH
        if not json_arg.exists():
            print(f"ERROR: file not found: {json_arg}")
            sys.exit(1)
        result = build_document(json_arg, output_arg, template_arg)
        print(f"Selesai: {result}")
        return

    json_files = sorted(
        path
        for path in BASE_DIR.glob("*.json")
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


def _set_table_borders_match_template(table) -> None:
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
        el.set(qn("w:val"), "nil")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")


if __name__ == "__main__":
    main()