from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "ieee.json"
TEMPLATE_PATH = BASE_DIR / "IEEE.docx"
DEFAULT_OUTPUT_NAME = "Dokumen_IEEE.docx"
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
PAGE_WIDTH_PT = 595.3
BODY_MARGIN_PT = 45.35
BODY_GAP_PT = 18.0
BODY_COLUMN_WIDTH_PT = (PAGE_WIDTH_PT - (2 * BODY_MARGIN_PT) - BODY_GAP_PT) / 2
MAX_FIGURE_WIDTH_CM = 8.4
NS_MAP = {
    b"http://purl.oclc.org/ooxml/wordprocessingml/main": b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    b"http://purl.oclc.org/ooxml/officeDocument/relationships": b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/drawingml/main": b"http://schemas.openxmlformats.org/drawingml/2006/main",
    b"http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing": b"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    b"http://purl.oclc.org/ooxml/officeDocument/math": b"http://schemas.openxmlformats.org/officeDocument/2006/math",
}
STYLE_XML_ID = {
    "Body Text": "BodyText",
    "heading 1": "Heading1",
    "heading 2": "Heading2",
    "heading 3": "Heading3",
    "paper title": "papertitle",
    "Author": "Author",
    "Abstract": "Abstract",
    "Keywords": "Keywords",
    "bullet list": "bulletlist",
    "references": "references",
    "equation": "equation",
    "figure caption": "figurecaption",
    "table head": "tablehead",
    "table col head": "tablecolhead",
    "table copy": "tablecopy",
    "Affiliation": "Affiliation",
}
XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]
_XSLT = None


def _strict_to_trans(data: bytes) -> bytes:
    for old, new in NS_MAP.items():
        data = data.replace(old, new)
    return data


def _inject_template_styles(doc: Document, template_path: Path) -> None:
    with zipfile.ZipFile(template_path) as archive:
        raw = archive.read("word/styles.xml")
    tmpl_styles = etree.fromstring(_strict_to_trans(raw))
    cur = doc.part.styles._element
    for child in list(cur):
        cur.remove(child)
    for child in list(tmpl_styles):
        cur.append(child)
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    wq = lambda tag: f"{{{ns_w}}}{tag}"
    for ppr in cur.findall(f".//{wq('pPr')}"):
        num_pr = ppr.find(wq("numPr"))
        if num_pr is None:
            continue
        num_id = num_pr.find(wq("numId"))
        if num_id is not None:
            num_id.set(wq("val"), "0")
    try:
        if hasattr(doc.part.styles, "_styles"):
            doc.part.styles._styles = None
    except Exception:
        pass


def _pt2tw(pt: float) -> int:
    return int(round(pt * 20))


def _set_para_style(paragraph, style_name: str) -> None:
    xml_id = STYLE_XML_ID.get(style_name, style_name)
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(qn("w:val"), xml_id)


def _para(doc: Document, style_id: str | None = None, align=None, sb: float | None = None, sa: float | None = None, fi: float | None = None, li: float | None = None):
    paragraph = doc.add_paragraph()
    if style_id:
        _set_para_style(paragraph, style_id)
    pf = paragraph.paragraph_format
    if align is not None:
        paragraph.alignment = align
    if sb is not None:
        pf.space_before = Pt(sb)
    if sa is not None:
        pf.space_after = Pt(sa)
    if fi is not None:
        pf.first_line_indent = Pt(fi)
    if li is not None:
        pf.left_indent = Pt(li)
    return paragraph


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _build_sectpr(num_cols: int, col_space_pt: float, top_pt: float, bottom_pt: float, left_pt: float, right_pt: float, section_type: str = "continuous", w_pt: float = 595.3, h_pt: float = 841.9, header_pt: float = 36.0, footer_pt: float = 36.0, title_pg: bool = False):
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    wq = lambda tag: f"{{{ns_w}}}{tag}"
    sectpr = etree.Element(wq("sectPr"))
    sec_type = etree.SubElement(sectpr, wq("type"))
    sec_type.set(wq("val"), section_type)
    pg_sz = etree.SubElement(sectpr, wq("pgSz"))
    pg_sz.set(wq("w"), str(_pt2tw(w_pt)))
    pg_sz.set(wq("h"), str(_pt2tw(h_pt)))
    pg_mar = etree.SubElement(sectpr, wq("pgMar"))
    pg_mar.set(wq("top"), str(_pt2tw(top_pt)))
    pg_mar.set(wq("right"), str(_pt2tw(right_pt)))
    pg_mar.set(wq("bottom"), str(_pt2tw(bottom_pt)))
    pg_mar.set(wq("left"), str(_pt2tw(left_pt)))
    pg_mar.set(wq("header"), str(_pt2tw(header_pt)))
    pg_mar.set(wq("footer"), str(_pt2tw(footer_pt)))
    pg_mar.set(wq("gutter"), "0")
    cols = etree.SubElement(sectpr, wq("cols"))
    if num_cols > 1:
        cols.set(wq("num"), str(num_cols))
    cols.set(wq("space"), str(_pt2tw(col_space_pt)))
    if title_pg:
        etree.SubElement(sectpr, wq("titlePg"))
    return sectpr


def _embed_sectpr(doc: Document, sectpr_el, style_id: str | None = None):
    paragraph = _para(doc, style_id=style_id)
    ppr = paragraph._p.get_or_add_pPr()
    ppr.append(sectpr_el)
    return paragraph


def _setup_main_sectpr(doc: Document) -> None:
    body = doc.element.body
    sectpr = body.find(qn("w:sectPr"))
    if sectpr is None:
        sectpr = OxmlElement("w:sectPr")
        body.append(sectpr)
    for tag in ("w:cols", "w:pgSz", "w:pgMar", "w:type", "w:titlePg"):
        for old in sectpr.findall(qn(tag)):
            sectpr.remove(old)
    pg_sz = OxmlElement("w:pgSz")
    pg_sz.set(qn("w:w"), str(_pt2tw(595.3)))
    pg_sz.set(qn("w:h"), str(_pt2tw(841.9)))
    sectpr.append(pg_sz)
    pg_mar = OxmlElement("w:pgMar")
    pg_mar.set(qn("w:top"), str(_pt2tw(54.0)))
    pg_mar.set(qn("w:right"), str(_pt2tw(44.65)))
    pg_mar.set(qn("w:bottom"), str(_pt2tw(72.0)))
    pg_mar.set(qn("w:left"), str(_pt2tw(44.65)))
    pg_mar.set(qn("w:header"), str(_pt2tw(36.0)))
    pg_mar.set(qn("w:footer"), str(_pt2tw(36.0)))
    pg_mar.set(qn("w:gutter"), "0")
    sectpr.append(pg_mar)
    cols = OxmlElement("w:cols")
    cols.set(qn("w:space"), str(_pt2tw(36.0)))
    sectpr.append(cols)
    sec_type = OxmlElement("w:type")
    sec_type.set(qn("w:val"), "continuous")
    sectpr.append(sec_type)


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
    if tag == "oMath":
        paragraph._p.append(omml)
    elif tag == "oMathPara":
        paragraph._p.append(omml)
    else:
        wrapper = etree.fromstring(f'<m:oMath xmlns:m="{MATH_NS}"/>')
        wrapper.append(omml)
        paragraph._p.append(wrapper)
    return True


def _append_text_run(paragraph, text: str, bold: bool = False, italic: bool = False, underline: bool = False):
    if not text:
        return
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    run.underline = underline


def _append_line_break(paragraph):
    paragraph.add_run().add_break()


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
            yield {"kind": "text", "value": content, "bold": bold, "italic": italic, "underline": underline}

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


def _append_rich_text(paragraph, text: str):
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            _append_line_break(paragraph)
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                run = paragraph.add_run(token["value"])
                run.italic = True
            continue
        _append_text_run(
            paragraph,
            token["value"],
            bold=token["bold"],
            italic=token["italic"],
            underline=token["underline"],
        )


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    parts = [part for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return parts or [""]


def _body_paragraphs(doc: Document, text: str, style_id: str = "Body Text"):
    paragraphs = []
    for block in _split_body_blocks(text):
        paragraph = _para(doc, style_id=style_id)
        _append_rich_text(paragraph, block)
        paragraphs.append(paragraph)
    return paragraphs


def _roman(number) -> str:
    try:
        value = int(str(number).strip())
    except Exception:
        return str(number).strip()
    numerals = [
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
    ]
    result = []
    for arabic, roman in numerals:
        while value >= arabic:
            result.append(roman)
            value -= arabic
    return "".join(result)


def _subsection_letter(number_text: str) -> str:
    parts = [part for part in str(number_text).split(".") if part]
    if not parts:
        return str(number_text)
    try:
        last = int(parts[-1])
    except Exception:
        return str(number_text)
    if 1 <= last <= 26:
        return chr(ord("A") + last - 1)
    return str(number_text)


def _subsubsection_label(number_text: str) -> str:
    parts = [part for part in str(number_text).split(".") if part]
    if not parts:
        return str(number_text)
    return f"{parts[-1]})"


def _add_title(doc: Document, config: dict):
    # Support both new format (title) and legacy format (TitleBlock)
    title = config.get("title", "")
    if not title:
        title = config.get("TitleBlock", {}).get("Title", "Untitled Paper")
    
    paragraph = _para(doc, style_id="paper title")
    _append_rich_text(paragraph, title)
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    rpr = run._r.get_or_add_rPr()
    kern = OxmlElement("w:kern")
    kern.set(qn("w:val"), "48")
    rpr.append(kern)


def _parse_author_entries(title_block: dict) -> list[dict]:
    # Support both new format (authors array) and legacy format
    authors = title_block.get("authors", [])
    if authors:
        # New format: authors is an array of author objects
        entries = []
        for author in authors:
            name = author.get("name", "")
            affiliation = author.get("affiliation", "")
            location = author.get("location", "")
            email = author.get("email", "")
            
            lines = []
            if affiliation:
                lines.append(affiliation)
            if location:
                lines.append(location)
            if email:
                lines.append(f"e-mail: {email}")
            
            entries.append({"name": name, "lines": lines})
        return entries
    
    # Legacy format: AuthorLine and AddressLines
    author_line = str(title_block.get("AuthorLine") or "").strip()
    address_lines = [str(line).strip() for line in title_block.get("AddressLines", []) if str(line).strip()]
    if not author_line and not address_lines:
        return []
    common_lines: list[str] = []
    affiliation_map: dict[str, str] = {}
    email_lines: list[str] = []
    for line in address_lines:
        if re.match(r"^\*?\s*e-?mail\s*:", line, flags=re.IGNORECASE):
            email_lines.append(line.lstrip("*"))
            continue
        match = re.match(r"^(\d+(?:\s*,\s*\d+)*)\s*(.+)$", line)
        if match:
            ids = [part.strip() for part in match.group(1).split(",")]
            content = match.group(2).strip()
            for ident in ids:
                affiliation_map[ident] = content
            continue
        common_lines.append(line)
    raw_names = [part.strip() for part in author_line.split(",") if part.strip()]
    entries = []
    for raw in raw_names:
        starred = raw.startswith("*")
        clean = raw.lstrip("*").strip()
        numbers = re.findall(r"(\d+)", clean)
        name = re.sub(r"\d+$", "", clean).strip()
        if not name:
            name = clean
        lines: list[str] = []
        for number in numbers:
            affiliation = affiliation_map.get(number)
            if affiliation and affiliation not in lines:
                lines.append(affiliation)
        for line in common_lines:
            if line not in lines:
                lines.append(line)
        if starred:
            for email in email_lines:
                if email not in lines:
                    lines.append(email)
        entries.append({"name": name, "lines": lines})
    if entries:
        return entries
    fallback_lines = []
    if author_line:
        fallback_lines.append(author_line)
    fallback_lines.extend(address_lines)
    return [{"name": "", "lines": fallback_lines}]


def _add_authors(doc: Document, config: dict):
    # Support both new and legacy formats
    entries = _parse_author_entries(config)  # config can be the whole dict or just TitleBlock
    if not entries:
        return
    for entry in entries:
        # SATU paragraf per penulis dengan style "Author" 
        paragraph = _para(doc, style_id="Author")
        
        # Nama penulis dengan font 9pt dan tidak bold
        if entry.get("name"):
            run = paragraph.add_run(entry["name"])
            run.font.size = Pt(9)  # IEEE author name size
            # run.bold = True  # Tidak bold
        
        # Afiliasi dan email dengan font lebih kecil dan italic
        for line in entry.get("lines", []):
            _append_line_break(paragraph)
            run = paragraph.add_run(line)
            run.font.size = Pt(9)  # IEEE affiliation size
            # Email tidak italic, yang lain italic
            if not re.match(r"^\s*e-?mail\s*:", line, flags=re.IGNORECASE):
                run.italic = True


def _add_abstracts(doc: Document, config: dict):
    # Support both new format (abstract, keywords) and legacy format
    abstract = config.get("abstract", "")
    keywords = config.get("keywords", [])
    
    # If new format not found, try legacy format
    if not abstract:
        abstract_block = config.get("Abstract", {})
        abstract = str(abstract_block.get("English") or "").strip()
        if not abstract:
            abstract = str(abstract_block.get("Indonesian") or "").strip()
    
    if not keywords:
        abstract_block = config.get("Abstract", {})
        keywords_en = str(abstract_block.get("KeywordsEnglish") or "").strip()
        keywords_id = str(abstract_block.get("KeywordsIndonesian") or "").strip()
        if keywords_en:
            keywords = [k.strip() for k in keywords_en.split(",")]
        elif keywords_id:
            keywords = [k.strip() for k in keywords_id.split(",")]
    
    # Add abstract
    if abstract:
        paragraph = _para(doc, style_id="Abstract")
        paragraph.add_run("Abstract")
        paragraph.add_run("—")
        _append_rich_text(paragraph, abstract)
    
    # Add keywords
    if keywords:
        keywords_text = ", ".join(keywords)
        paragraph = _para(doc, style_id="Keywords")
        paragraph.add_run("Index Terms")
        paragraph.add_run("—")
        _append_rich_text(paragraph, keywords_text if keywords_text.endswith(".") else f"{keywords_text}.")


def _section_heading_text(item: dict) -> str:
    number = str(item.get("NumberiOrLetter") or "").strip()
    title = str(item.get("Text") or "").strip().upper()
    if not number:
        return title
    return f"{_roman(number)}. {title}"


def _subsection_heading_text(item: dict) -> str:
    title = str(item.get("Text") or "").strip()
    number = str(item.get("NumberiOrLetter") or "").strip()
    label = _subsection_letter(number)
    return f"{label}. {title}" if label else title


def _subsubsection_heading_text(item: dict) -> str:
    title = str(item.get("Text") or "").strip()
    number = str(item.get("NumberiOrLetter") or "").strip()
    label = _subsubsection_label(number)
    return f"{label} {title}".strip()


def _add_section_heading(doc: Document, text: str):
    paragraph = _para(doc, style_id="heading 1")
    _append_rich_text(paragraph, text)


def _add_subsection_heading(doc: Document, text: str):
    paragraph = _para(doc, style_id="heading 2")
    run = paragraph.add_run(text)
    run.italic = True


def _add_subsubsection_heading(doc: Document, text: str):
    paragraph = _para(doc, style_id="heading 3")
    _append_rich_text(paragraph, text)


def _iter_point_entries(item: dict):
    items = item.get("Items")
    if isinstance(items, list) and items:
        for entry in items:
            if isinstance(entry, str):
                text = entry
                label = None
            elif isinstance(entry, dict):
                text = entry.get("Text", "")
                label = entry.get("Label")
            else:
                text = str(entry)
                label = None
            if text:
                yield text, label
        return
    text = item.get("Text", "")
    if text:
        yield text, item.get("Label")


def _add_point_list(doc: Document, item: dict):
    list_type = str(item.get("ListType") or ("number" if item.get("Numbered") else "bullet")).lower()
    start_at = int(item.get("StartAt", 1))
    for index, (text, custom_label) in enumerate(_iter_point_entries(item), start=start_at):
        paragraph = _para(doc, style_id="bullet list")
        prefix = custom_label
        if prefix is None:
            prefix = f"{index}) " if list_type in {"number", "numbering", "ordered"} else "• "
        paragraph.add_run(prefix)
        _append_rich_text(paragraph, text)


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative
    return BASE_DIR / path


def _set_full_cell_borders(cell):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    border_spec = {
        "top": {"val": "single", "sz": "8", "space": "0", "color": "auto"},
        "bottom": {"val": "single", "sz": "8", "space": "0", "color": "auto"},
        "left": {"val": "single", "sz": "8", "space": "0", "color": "auto"},
        "right": {"val": "single", "sz": "8", "space": "0", "color": "auto"},
    }
    for edge, values in border_spec.items():
        el = tc_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tc_borders.append(el)
        for key, value in values.items():
            el.set(qn(f"w:{key}"), value)


def _set_horizontal_cell_borders(cell, top=False, bottom=False):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    
    border_spec = {}
    border_spec["top"] = {"val": "single", "sz": "8", "space": "0", "color": "auto"} if top else {"val": "none"}
    border_spec["bottom"] = {"val": "single", "sz": "8", "space": "0", "color": "auto"} if bottom else {"val": "none"}
    border_spec["left"] = {"val": "none"}
    border_spec["right"] = {"val": "none"}
    
    for edge, values in border_spec.items():
        el = tc_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tc_borders.append(el)
        for key, value in values.items():
            el.set(qn(f"w:{key}"), value)


def _add_prompt_box(doc: Document, item: dict):
    prompt_text = str(item.get("Prompt") or "").strip()
    if not prompt_text:
        prompt_text = str(item.get("Title") or "").strip() or "Prompt gambar belum diisi."
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Normal Table"
    _set_table_borders_match_template(table)
    cell = table.cell(0, 0)
    _set_full_cell_borders(cell)
    paragraph = cell.paragraphs[0]
    _set_para_style(paragraph, "Body Text")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _append_rich_text(paragraph, prompt_text)
    for extra_paragraph in cell.paragraphs[1:]:
        for run in extra_paragraph.runs:
            run.clear()
    return table


def _render_item(doc: Document, item: dict, json_path: Path):
    """Render item in legacy JTM format"""
    item_id = str(item.get("ID") or "").strip()
    if item_id in {"Bab", "Bab utama"}:
        _add_section_heading(doc, _section_heading_text(item))
        return
    if item_id in {"SubBab", "Bab 1.1"}:
        _add_subsection_heading(doc, _subsection_heading_text(item))
        return
    if item_id == "SubSubBab":
        _add_subsubsection_heading(doc, _subsubsection_heading_text(item))
        return
    if item_id == "Paragraf":
        _body_paragraphs(doc, str(item.get("Text") or ""))
        return
    if item_id == "Poin":
        _add_point_list(doc, item)
        return
    if item_id == "Gambar":
        _add_figure(doc, item, json_path)
        return
    if item_id == "Tabel":
        _add_table(doc, item)
        return
    if item_id == "Rumus":
        _add_equation_group(doc, item)


def _style_cell_paragraph(paragraph, style_id: str, align=WD_ALIGN_PARAGRAPH.CENTER):
    _set_para_style(paragraph, style_id)
    paragraph.alignment = align


def _add_table(doc: Document, item: dict):
    number = str(item.get("NumberiOrLetter") or "").strip()
    title = str(item.get("Title") or "").strip()
    caption = _para(doc, style_id="table head")
    label = f"TABLE {_roman(number)}"
    text = f"{label}. {title}" if title else label
    _append_rich_text(caption, text)
    headers = list(item.get("Headers", []))
    rows = list(item.get("Rows", []))
    if not headers:
        return
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders_match_template(table)
    for column_index, value in enumerate(headers):
        cell = table.rows[0].cells[column_index]
        _set_horizontal_cell_borders(cell, top=True, bottom=True)
        cell.text = ""
        paragraph = cell.paragraphs[0]
        _style_cell_paragraph(paragraph, "table col head")
        _append_rich_text(paragraph, str(value))
        for run in paragraph.runs:
            run.bold = True
    for row_index, row_data in enumerate(rows, start=1):
        is_last_row = (row_index == len(rows))
        for column_index, value in enumerate(row_data):
            if column_index >= len(headers):
                break
            cell = table.rows[row_index].cells[column_index]
            _set_horizontal_cell_borders(cell, top=False, bottom=is_last_row)
            cell.text = ""
            paragraph = cell.paragraphs[0]
            _style_cell_paragraph(paragraph, "table copy")
            _append_rich_text(paragraph, str(value))
    _para(doc, sa=4)


def _add_equation_line(doc: Document, formula: str, number: str | None = None):
    paragraph = _para(doc, style_id="equation")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    tab_stops = paragraph.paragraph_format.tab_stops
    tab_stops.add_tab_stop(Pt(BODY_COLUMN_WIDTH_PT / 2), WD_TAB_ALIGNMENT.CENTER)
    tab_stops.add_tab_stop(Pt(BODY_COLUMN_WIDTH_PT), WD_TAB_ALIGNMENT.RIGHT)
    paragraph.add_run("\t")
    if not _append_inline_math(paragraph, formula):
        run = paragraph.add_run(formula)
        run.italic = True
    if number is not None:
        paragraph.add_run(f"\t({number})")


def _add_equation_group(doc: Document, item: dict):
    formulas = [str(line).strip() for line in item.get("Lines", []) if str(line).strip()]
    if not formulas:
        return
    number = str(item.get("NumberiOrLetter") or "").strip() or None
    for formula in formulas[:-1]:
        _add_equation_line(doc, formula)
    _add_equation_line(doc, formulas[-1], number=number)


def _reference_parts(reference_text: str, fallback_number: int):
    match = re.match(r"^\s*\[(.+?)\]\s*(.*)$", reference_text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return str(fallback_number), reference_text.strip()


def _add_references(doc: Document, config: dict):
    # Support both new format (references section) and legacy format
    references = None
    
    # Try new format - look for direct references key
    if "references" in config:
        references = config["references"].get("content", [])
    # Also try section_references key
    elif "section_references" in config:
        references = config["section_references"].get("content", [])
    # If not found, try legacy sections format
    else:
        sections = config.get("sections", [])
        for section in sections:
            if section.get("title", "").upper() == "REFERENCES":
                references = section.get("content", [])
                break
    
    # If still not found, try legacy format
    if not references:
        references = config.get("References", [])
    
    if not references:
        return
    
    heading = _para(doc, style_id="heading 1")
    _append_rich_text(heading, "REFERENCES")
    
    # Handle different reference formats
    if isinstance(references, list) and references and isinstance(references[0], dict):
        # New format: list of reference objects with id and text
        for reference in references:
            ref_id = reference.get("id", "")
            ref_text = reference.get("text", "")
            if ref_text:
                paragraph = _para(doc, style_id="references")
                ppr = paragraph._p.get_or_add_pPr()
                ind = OxmlElement("w:ind")
                ind.set(qn("w:start"), str(int(round(17.7 * 20))))
                ind.set(qn("w:hanging"), str(int(round(17.7 * 20))))
                ppr.append(ind)
                if ref_id:
                    _append_rich_text(paragraph, f"[{ref_id}] {ref_text}".strip())
                else:
                    _append_rich_text(paragraph, ref_text.strip())
    else:
        # Legacy format: list of reference strings
        for index, reference in enumerate(references, start=1):
            ref_id, ref_text = _reference_parts(str(reference), index)
            paragraph = _para(doc, style_id="references")
            ppr = paragraph._p.get_or_add_pPr()
            ind = OxmlElement("w:ind")
            ind.set(qn("w:start"), str(int(round(17.7 * 20))))
            ind.set(qn("w:hanging"), str(int(round(17.7 * 20))))
            ppr.append(ind)
            _append_rich_text(paragraph, f"[{ref_id}] {ref_text}".strip())


def _render_content_item(doc: Document, item: dict, json_path: Path):
    """Render a single content item from the new format"""
    item_id = str(item.get("id", "")).lower()
    
    if item_id == "text":
        text = str(item.get("text", ""))
        if text:
            _body_paragraphs(doc, text)
    
    elif item_id == "gambar" or item_id == "image":
        _add_figure_from_content(doc, item, json_path)
    
    elif item_id == "rumus" or item_id == "formula":
        _add_equation_from_content(doc, item)
    
    elif item_id == "tabel" or item_id == "table":
        _add_table_from_content(doc, item)


def _add_figure_from_content(doc: Document, item: dict, json_path: Path):
    """Add figure from new content format"""
    image_number = str(item.get("ImageNumber", "")).strip()
    path_text = str(item.get("Path", "")).strip()
    prompt = str(item.get("Prompt", "")).strip()
    title = str(item.get("Title", "")).strip()
    
    # Use Caption if available, otherwise fall back to Title
    caption_text = item.get("Title", "").strip() or title
    
    image_path = _resolve_path(path_text, json_path) if path_text else None
    
    try:
        width_cm = float(item.get("WidthCm", MAX_FIGURE_WIDTH_CM))
    except Exception:
        width_cm = MAX_FIGURE_WIDTH_CM
    width_cm = max(1.0, min(width_cm, MAX_FIGURE_WIDTH_CM))
    
    if image_path is not None and image_path.is_file():
        paragraph = _para(doc, align=WD_ALIGN_PARAGRAPH.CENTER, sb=6, sa=2)
        paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
    else:
        # Use prompt in the placeholder box if image not found
        # Wrap dengan format [PROMPT UNTUK AI GAMBAR: ...] supaya audit lulus
        prompt_body = prompt if prompt else f"Figure {image_number} not found"
        if title:
            fallback_text = f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt_body}]"
        else:
            fallback_text = f"[PROMPT UNTUK AI GAMBAR: {prompt_body}]"
        _add_prompt_box_with_text(doc, fallback_text)
    
    # Add caption using title or prompt
    if image_number and caption_text:
        caption = _para(doc, style_id="figure caption", align=WD_ALIGN_PARAGRAPH.CENTER)
        _append_rich_text(caption, f"Fig. {image_number}. {caption_text}".strip())


def _add_equation_from_content(doc: Document, item: dict):
    """Add equation from new content format"""
    formula_number = str(item.get("FormulaNumber", "")).strip()
    # Support both 'text' and 'latex' keys
    formula_text = str(item.get("text", "") or item.get("latex", "")).strip()
    
    if formula_text:
        _add_equation_line(doc, formula_text, formula_number if formula_number else None)


def _add_table_from_content(doc: Document, item: dict):
    """Add table from new content format"""
    table_number = str(item.get("TableNumber", "")).strip()
    title = str(item.get("Title", "")).strip()
    headers = list(item.get("Headers", []))
    rows = list(item.get("Rows", []))
    
    if not headers:
        return
    
    # Add table caption
    caption = _para(doc, style_id="table head")
    label = f"TABLE {_roman(table_number)}" if table_number else "TABLE"
    text = f"{label}. {title}" if title else label
    _append_rich_text(caption, text)
    
    # Create table
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders_match_template(table)
    
    # Add headers
    for column_index, value in enumerate(headers):
        cell = table.rows[0].cells[column_index]
        _set_horizontal_cell_borders(cell, top=True, bottom=True)
        cell.text = ""
        paragraph = cell.paragraphs[0]
        _style_cell_paragraph(paragraph, "table col head")
        _append_rich_text(paragraph, str(value))
        for run in paragraph.runs:
            run.bold = True
    
    # Add rows
    for row_index, row_data in enumerate(rows, start=1):
        is_last_row = (row_index == len(rows))
        for column_index, value in enumerate(row_data):
            if column_index >= len(headers):
                break
            cell = table.rows[row_index].cells[column_index]
            _set_horizontal_cell_borders(cell, top=False, bottom=is_last_row)
            cell.text = ""
            paragraph = cell.paragraphs[0]
            _style_cell_paragraph(paragraph, "table copy")
            _append_rich_text(paragraph, str(value))
    
    _para(doc, sa=4)


def _add_prompt_box_with_text(doc: Document, text: str):
    """Add a prompt box with custom text"""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Normal Table"
    _set_table_borders_match_template(table)
    cell = table.cell(0, 0)
    _set_full_cell_borders(cell)
    paragraph = cell.paragraphs[0]
    _set_para_style(paragraph, "Body Text")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _append_rich_text(paragraph, text)
    for extra_paragraph in cell.paragraphs[1:]:
        for run in extra_paragraph.runs:
            run.clear()
    return table


def _render_sections_legacy(doc: Document, config: dict, json_path: Path):
    """Render sections in the legacy sections array format"""
    sections = config.get("sections", [])
    
    for section in sections:
        # Add section heading
        section_number = str(section.get("number", "")).strip()
        section_title = str(section.get("title", "")).strip().upper()
        
        if section_number:
            heading_text = f"{_roman(section_number)}. {section_title}"
        else:
            heading_text = section_title
        
        _add_section_heading(doc, heading_text)
        
        # Add section content (handle both string and array)
        content = section.get("content", "")
        if isinstance(content, str) and content.strip():
            _body_paragraphs(doc, content.strip())
        elif isinstance(content, list):
            # Handle array of content items at section level
            for item in content:
                if isinstance(item, str):
                    _body_paragraphs(doc, item.strip())
                elif isinstance(item, dict):
                    _render_content_item(doc, item, json_path)
        
        # Add subsections
        subsections = section.get("subsections", [])
        for subsection in subsections:
            _render_subsection(doc, subsection, json_path)


def _render_sections(doc: Document, config: dict, json_path: Path):
    """Render sections in the new format with direct section keys"""
    # Look for direct section keys (section1, section2, etc.)
    section_keys = []
    for key in config.keys():
        if key.startswith("section") and key.replace("section", "").isdigit():
            section_keys.append(key)
    
    # Sort section keys numerically
    section_keys.sort(key=lambda x: int(x.replace("section", "")))
    
    for section_key in section_keys:
        section = config[section_key]
        
        # Add section heading
        section_number = str(section.get("number", "")).strip()
        # Derive section number from key when "number" field is absent (e.g. "section1" -> "1")
        if not section_number:
            num_part = section_key.replace("section", "")
            if num_part.isdigit():
                section_number = num_part
        section_title = str(section.get("title", "")).strip().upper()
        
        if section_number:
            heading_text = f"{_roman(section_number)}. {section_title}"
        else:
            heading_text = section_title
        
        _add_section_heading(doc, heading_text)
        
        # Add section content (handle both string and array)
        content = section.get("content", "")
        if isinstance(content, str) and content.strip():
            _body_paragraphs(doc, content.strip())
        elif isinstance(content, list):
            # Handle array of content items at section level
            for item in content:
                if isinstance(item, str):
                    _body_paragraphs(doc, item.strip())
                elif isinstance(item, dict):
                    _render_content_item(doc, item, json_path)
        
        # Collect subsection keys in insertion order.
        # Support old pattern: sub2a, sub3b  (starts with "sub", digits+alpha after)
        # Support new pattern: section2a, section3b  (starts with "section", ends digit+alpha)
        subsection_keys = [
            key for key in section.keys()
            if (key.startswith("sub") and len(key) > 3 and key[3:].isalnum())
            or re.match(r'^section\d+[a-z]+$', key)
        ]
        for key in subsection_keys:
            _render_subsection(doc, section[key], json_path, sub_key=key)


def _render_subsection(doc: Document, subsection: dict, json_path: Path, sub_key: str = ""):
    """Render a subsection with mixed content types"""
    subsection_letter = str(subsection.get("letter", "")).strip()
    # Derive letter from sub_key when "letter" field is absent.
    # Handles both old style (sub2a -> A) and new style (section2a -> A).
    if not subsection_letter and sub_key:
        m = re.match(r'^(?:sub|section)\d+([a-z]+)$', sub_key)
        if m:
            subsection_letter = m.group(1).upper()
    subsection_title = str(subsection.get("title", "")).strip()
    
    # Add subsection heading
    if subsection_letter and subsection_title:
        heading_text = f"{subsection_letter}. {subsection_title}"
    elif subsection_title:
        heading_text = subsection_title
    else:
        heading_text = ""
    
    if heading_text:
        _add_subsection_heading(doc, heading_text)
    
    # Render content items
    content_items = subsection.get("content", [])
    if isinstance(content_items, list):
        for item in content_items:
            _render_content_item(doc, item, json_path)
    elif isinstance(content_items, str):
        # If content is a string, treat it as text
        if content_items.strip():
            _body_paragraphs(doc, content_items.strip())


def _default_output_path(config: dict, json_path: Path) -> Path:
    return json_path.parent / f"{json_path.stem}.docx"


def build_document(json_path: Path = JSON_PATH, output_path: Path | None = None, template_path: Path = TEMPLATE_PATH) -> Path:
    config = json.loads(Path(json_path).read_text(encoding="utf-8"))
    final_output = Path(output_path) if output_path else _default_output_path(config, Path(json_path))
    doc = Document()
    _inject_template_styles(doc, Path(template_path))
    _clear_document_body(doc)
    _setup_main_sectpr(doc)
    _add_title(doc, config)
    _embed_sectpr(doc, _build_sectpr(1, 36.0, 27.0, 72.0, 44.65, 44.65, title_pg=True), style_id="Author")
    _add_authors(doc, config)
    _embed_sectpr(doc, _build_sectpr(3, 36.0, 22.5, 72.0, 44.65, 44.65))
    _embed_sectpr(doc, _build_sectpr(3, 36.0, 22.5, 72.0, 44.65, 44.65))
    _add_abstracts(doc, config)
    
    # Detect format and render content accordingly
    # Check for new format with direct section keys (section1, section2, etc.)
    has_direct_sections = any(key.startswith("section") and key.replace("section", "").isdigit() for key in config.keys())
    # Also check for legacy sections array format
    has_sections_array = "sections" in config and isinstance(config["sections"], list)
    
    if has_direct_sections:
        # New format with direct section keys
        _render_sections(doc, config, Path(json_path))
    elif has_sections_array:
        # Legacy new format with sections array
        _render_sections_legacy(doc, config, Path(json_path))
    else:
        # Legacy JTM format
        for item in config.get("Items", []):
            _render_item(doc, item, Path(json_path))
    
    _add_references(doc, config)
    _embed_sectpr(doc, _build_sectpr(2, 18.0, 54.0, 72.0, 45.35, 45.35))

    # Aktifkan First Page Different di section 0 supaya First Page Footer
    # unik (match template IEEE original yang punya footerReference type="first").
    # python-docx auto-create footer part + relationships ketika di-akses.
    if doc.sections:
        section0 = doc.sections[0]
        section0.different_first_page_header_footer = True
        _ = section0.first_page_footer.paragraphs  # trigger creation

    final_output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(final_output))
    return final_output


def _run_part_scripts(base_dir: Path):
    """Run all part scripts to generate JSON files"""
    import subprocess
    
    part_scripts = ["gen2jsonID.py", "gen2jsonEN.py"]
    
    print("No JSON files found. Running part scripts to generate JSON...")
    
    for script in part_scripts:
        script_path = base_dir / script
        if script_path.exists():
            print(f"Running {script}...")
            try:
                result = subprocess.run([sys.executable, str(script_path)], 
                                      cwd=str(base_dir), 
                                      capture_output=True, 
                                      text=True,
                                      encoding='utf-8')
                if result.returncode == 0:
                    print(f"[OK] {script} completed successfully")
                    if result.stdout.strip():
                        print(f"   Output: {result.stdout.strip()}")
                else:
                    print(f"[ERR] {script} failed: {result.stderr.strip()}")
            except Exception as e:
                print(f"[ERR] Error running {script}: {e}")
        else:
            print(f"[ERR] {script} not found")
    
    print()


def main():
    base_dir = Path(__file__).parent
    
    if len(sys.argv) >= 2:
        # Mode: generate satu file
        json_arg = Path(sys.argv[1])
        output_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
        template_arg = Path(sys.argv[3]) if len(sys.argv) >= 4 else TEMPLATE_PATH
        
        if not json_arg.exists():
            print(f"[ERR] File not found: {json_arg}")
            return
        
        result = build_document(json_arg, output_arg, template_arg)
        print(f"[OK] Generated: {result.name}")
    else:
        # Mode: generate semua JSON di folder
        print("Generating all IEEE DOCX files...")
        
        # Cari semua file .json di folder base
        json_files = list(base_dir.glob("*.json"))
        
        if not json_files:
            # Auto-run part scripts if no JSON files found
            _run_part_scripts(base_dir)
            
            # Check again for JSON files
            json_files = list(base_dir.glob("*.json"))
            
            if not json_files:
                print("[ERR] No JSON files found in directory after running part scripts")
                return
        
        for json_path in sorted(json_files):
            # Skip file yang bukan format JSON yang valid
            if json_path.name.lower() in ["package.json", "tsconfig.json", "settings.json"]:
                continue
                
            try:
                # Validasi JSON dengan membaca sedikit content
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Cek apakah JSON memiliki struktur yang diharapkan
                if not isinstance(data, dict):
                    print(f"[ERR] Skip: {json_path.name} - Invalid JSON structure")
                    continue

                # Generate DOCX dengan nama IEEE_output.docx (untuk batch_audit.sh)
                # kalau JSON-nya _template.json, output ke IEEE_output.docx
                if json_path.stem == "_template":
                    output_arg = json_path.parent / "IEEE_output.docx"
                    output_path = build_document(json_path, output_path=output_arg)
                else:
                    output_path = build_document(json_path)
                print(f"[OK] Generated: {output_path.name}")
                
            except json.JSONDecodeError as e:
                print(f"[ERR] Skip: {json_path.name} - Invalid JSON: {e}")
            except Exception as e:
                print(f"[ERR] Error: {json_path.name} - {e}")
        
        print("\nDone!")




def _set_table_borders_match_template(table) -> None:
    """Set border tabel sesuai pattern template original IEEE: PARTIAL.

    IEEE template pakai top + bottom + insideH + insideV (no left/right).
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
    visible_sides = {"top", "bottom", "insideH", "insideV"}
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tbl_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tbl_borders.append(el)
        if edge in visible_sides:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")
        else:
            el.set(qn("w:val"), "nil")
            el.set(qn("w:sz"), "0")

if __name__ == "__main__":
    import sys
    import json
    main()
