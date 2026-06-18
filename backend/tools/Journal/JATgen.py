"""
JATgen.py — Generator DOCX untuk Journal of Al-Tamaddun (JAT)
Menggunakan dokumen asli JAT.docx sebagai base template (paste keep formatting).
Data diambil dari _template.json.

Chicago 18th Edition Notes-Bibliography style:
- In-text citations as Word footnotes (superscript numbers)
- Bibliography alphabetical, unnumbered, hanging indent
"""

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from lxml import etree

# ─── Chicago 18th helpers ────────────────────────────────────────────
_FOOTNOTE_COUNTER = 0  # global footnote counter
_FOOTNOTES_INITIALIZED = False  # only clear template footnotes once


def _init_footnotes(doc: Document):
    """Clear template footnotes and ensure fresh footnotes part."""
    global _FOOTNOTE_COUNTER, _FOOTNOTES_INITIALIZED
    if _FOOTNOTES_INITIALIZED:
        return True
    _FOOTNOTE_COUNTER = 0
    _FOOTNOTES_INITIALIZED = True

    FOOTNOTES_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    footnotes_part = None
    for rel in doc.part.rels.values():
        if rel.reltype.endswith("/footnotes"):
            footnotes_part = rel.target_part
            break

    if footnotes_part is not None:
        # Clear existing user footnotes (keep separator/continuationSeparator)
        xml_bytes = footnotes_part.blob
        root = etree.fromstring(xml_bytes)
        to_remove = []
        for fn in root.findall(f"{{{FOOTNOTES_NS}}}footnote"):
            fn_id_str = fn.get(f"{{{FOOTNOTES_NS}}}id", "")
            try:
                fn_id = int(fn_id_str)
            except (ValueError, TypeError):
                fn_id = -999
            if fn_id > 0:
                to_remove.append(fn)
        for fn in to_remove:
            root.remove(fn)
        footnotes_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        return True

    # No footnotes part — create fresh one
    package = doc.part.package
    from docx.opc.part import Part
    from docx.opc.packuri import PackURI

    footnotes_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<w:footnote w:type="separator" w:id="-1">'
        '<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
        '<w:r><w:separator/></w:r></w:p></w:footnote>'
        '<w:footnote w:type="continuationSeparator" w:id="0">'
        '<w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
        '<w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
        '</w:footnotes>'
    )

    part_name = PackURI("/word/footnotes.xml")
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
    part = Part(part_name, content_type, footnotes_xml.encode("utf-8"), package)

    rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
    doc.part.relate_to(part, rel_type)
    return True


def _add_footnote(doc: Document, paragraph, footnote_text: str) -> int:
    """Add a real Word footnote at the paragraph, return the footnote ID."""
    global _FOOTNOTE_COUNTER
    _FOOTNOTE_COUNTER += 1
    fn_id = _FOOTNOTE_COUNTER

    FOOTNOTES_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    # Add footnoteref mark in body paragraph
    run_elem = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    rstyle = OxmlElement("w:rStyle")
    rstyle.set(qn("w:val"), "FootnoteReference")
    rpr.append(rstyle)
    run_elem.append(rpr)

    fn_ref = OxmlElement("w:footnoteReference")
    fn_ref.set(qn("w:id"), str(fn_id))
    run_elem.append(fn_ref)
    paragraph._p.append(run_elem)

    # Get or create footnotes part XML
    footnotes_part = None
    for rel in doc.part.rels.values():
        if rel.reltype.endswith("/footnotes"):
            footnotes_part = rel.target_part
            break

    if footnotes_part is None:
        _init_footnotes(doc)
        for rel in doc.part.rels.values():
            if rel.reltype.endswith("/footnotes"):
                footnotes_part = rel.target_part
                break

    if footnotes_part is None:
        return fn_id

    # Append footnote content to footnotes.xml
    xml_bytes = footnotes_part.blob
    root = etree.fromstring(xml_bytes)

    nsmap = {"w": FOOTNOTES_NS}

    fn_elem = etree.SubElement(root, f"{{{FOOTNOTES_NS}}}footnote")
    fn_elem.set(f"{{{FOOTNOTES_NS}}}id", str(fn_id))

    p_elem = etree.SubElement(fn_elem, f"{{{FOOTNOTES_NS}}}p")
    pPr = etree.SubElement(p_elem, f"{{{FOOTNOTES_NS}}}pPr")
    pStyle = etree.SubElement(pPr, f"{{{FOOTNOTES_NS}}}pStyle")
    pStyle.set(f"{{{FOOTNOTES_NS}}}val", "FootnoteText")
    spacing = etree.SubElement(pPr, f"{{{FOOTNOTES_NS}}}spacing")
    spacing.set(f"{{{FOOTNOTES_NS}}}after", "0")
    spacing.set(f"{{{FOOTNOTES_NS}}}line", "240")
    spacing.set(f"{{{FOOTNOTES_NS}}}lineRule", "auto")

    run_elem = etree.SubElement(p_elem, f"{{{FOOTNOTES_NS}}}r")
    rPr = etree.SubElement(run_elem, f"{{{FOOTNOTES_NS}}}rPr")
    rFont = etree.SubElement(rPr, f"{{{FOOTNOTES_NS}}}rFonts")
    rFont.set(f"{{{FOOTNOTES_NS}}}ascii", CFG["font_body"])
    rFont.set(f"{{{FOOTNOTES_NS}}}hAnsi", CFG["font_body"])
    sz = etree.SubElement(rPr, f"{{{FOOTNOTES_NS}}}sz")
    sz.set(f"{{{FOOTNOTES_NS}}}val", str(CFG["size_reference"] * 2))

    t_elem = etree.SubElement(run_elem, f"{{{FOOTNOTES_NS}}}t")
    t_elem.text = footnote_text

    footnotes_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return fn_id


# Roman → Arabic table reference conversion (same pattern as JAMRISgen)
ROMAN_TABLE_REFS = [
    (r'\b[Tt]able\s+IV\b', 'Table 4'),
    (r'\b[Tt]able\s+V\b', 'Table 5'),
    (r'\b[Tt]able\s+VI\b', 'Table 6'),
    (r'\b[Tt]able\s+VII\b', 'Table 7'),
    (r'\b[Tt]able\s+VIII\b', 'Table 8'),
    (r'\b[Tt]able\s+IX\b', 'Table 9'),
    (r'\b[Tt]able\s+X\b', 'Table 10'),
    (r'\b[Tt]able\s+III\b', 'Table 3'),
    (r'\b[Tt]able\s+II\b', 'Table 2'),
    (r'\b[Tt]able\s+I\b', 'Table 1'),
]


def _replace_roman_table_refs(text: str) -> str:
    for pattern, replacement in ROMAN_TABLE_REFS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ─── End Chicago helpers ─────────────────────────────────────────────

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "JAT.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "JAT_output.docx"

CFG = {
    "page_width_tw": 12240,
    "page_height_tw": 15840,
    "margin_top_tw": 1009,
    "margin_bottom_tw": 1009,
    "margin_left_tw": 1440,
    "margin_right_tw": 1440,
    "margin_gutter_tw": 0,
    "header_distance_tw": 720,
    "footer_distance_tw": 720,
    "columns": 1,
    "col_space_tw": 0,
    "font_body": "Times New Roman",
    "font_title": "Times New Roman",
    "font_heading": "Times New Roman",
    "font_caption": "Times New Roman",
    "font_reference": "Times New Roman",
    "size_title": 12,
    "size_body": 12,
    "size_heading1": 12,
    "size_heading2": 12,
    "size_heading3": 12,
    "size_caption": 12,
    "size_reference": 12,
    "size_header": 10,
    "size_footer": 9,
    "section_heading_format": "plain",
    "section_heading_upper": False,
    "subsection_format": "plain",
    "fig_prefix": "Figure",
    "tbl_prefix": "Table",
    "tbl_number_format": "arabic",
    "table_borders": "full",
    "line_spacing_body": 240,
    "line_spacing_rule": "auto",
    "first_line_indent_tw": 0,
    "ref_hanging_indent_tw": 0,
    "ref_numbering": "none",
}

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XSL_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL"),
    BASE / "MML2OMML.XSL",
    BASE.parent / "MML2OMML.XSL",
]
_XSLT = None


def _append_inline_math(paragraph, latex):
    """Render LaTeX into the paragraph. Prefer native Word OMML (real equation
    objects); fall back to sanitized unicode text if conversion is unavailable.
    Return True so the caller does not fall back to raw rendering (which leaks)."""
    if not latex:
        return False
    # Native OMML path first (matches IEEEgen fidelity).
    try:
        from _math_omml import append_omml_math as _omml
        if _omml(paragraph, latex):
            return True
    except Exception:
        pass
    import re as _re

    s = str(latex).strip()
    SYMBOLS = {
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\delta": "δ",
        r"\epsilon": "ε",
        r"\theta": "θ",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\pi": "π",
        r"\sigma": "σ",
        r"\tau": "τ",
        r"\phi": "φ",
        r"\omega": "ω",
        r"\sum": "∑",
        r"\prod": "∏",
        r"\int": "∫",
        r"\infty": "∞",
        r"\pm": "±",
        r"\times": "×",
        r"\cdot": "·",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\neq": "≠",
        r"\approx": "≈",
        r"\to": "→",
        r"\dots": "…",
        r"\ldots": "…",
        r"\quad": " ",
        r"\,": " ",
        r"\;": " ",
        r"\:": " ",
        r"\!": "",
        r"\left": "",
        r"\right": "",
    }
    for k, v in SYMBOLS.items():
        s = s.replace(k, v)
    s = _re.sub(r"\\(mathrm|mathbf|mathit|text|textbf|textit|operatorname)\{([^{}]*)\}", r"\2", s)
    s = _re.sub(r"\\(vec|hat|bar|tilde|dot|ddot)\{([^{}]*)\}", r"\2", s)
    s = _re.sub(r"_\{([^{}]*)\}", r"_\1", s)
    s = _re.sub(r"\^\{([^{}]*)\}", r"^\1", s)
    while True:
        new_s = _re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", s)
        if new_s == s:
            break
        s = new_s
    s = _re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "").replace("$", "")
    paragraph.add_run(s)
    return True


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


def load_json():
    with open(TEMPLATE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def set_run_font(run, font_name=None, size_pt=None, bold=None, italic=None, color=None):
    if font_name:
        run.font.name = font_name
        rpr = run._r.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.insert(0, rfonts)
        rfonts.set(qn("w:ascii"), font_name)
        rfonts.set(qn("w:hAnsi"), font_name)
        rfonts.set(qn("w:eastAsia"), font_name)
        rfonts.set(qn("w:cs"), font_name)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor(*color) if isinstance(color, tuple) else color


def set_paragraph_spacing(paragraph, before=None, after=None, line=None, line_rule=None):
    pf = paragraph.paragraph_format
    if before is not None:
        pf.space_before = Pt(before)
    if after is not None:
        pf.space_after = Pt(after)
    if line is not None:
        ppr = paragraph._p.get_or_add_pPr()
        spacing = ppr.find(qn("w:spacing"))
        if spacing is None:
            spacing = OxmlElement("w:spacing")
            ppr.append(spacing)
        spacing.set(qn("w:line"), str(line))
        if line_rule:
            spacing.set(qn("w:lineRule"), line_rule)


def set_paragraph_indent(paragraph, left=None, right=None, first_line=None, hanging=None):
    ppr = paragraph._p.get_or_add_pPr()
    ind = ppr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        ppr.append(ind)
    if left is not None:
        ind.set(qn("w:left"), str(left))
    if right is not None:
        ind.set(qn("w:right"), str(right))
    if first_line is not None:
        ind.set(qn("w:firstLine"), str(first_line))
    if hanging is not None:
        ind.set(qn("w:hanging"), str(hanging))


def clear_body(doc):
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def add_paragraph(
    doc,
    text="",
    alignment=None,
    bold=None,
    italic=None,
    font_name=None,
    size_pt=None,
    space_before=None,
    space_after=None,
    line_spacing=None,
    line_rule=None,
):
    p = doc.add_paragraph()
    if alignment is not None:
        p.alignment = alignment
    set_paragraph_spacing(
        p, before=space_before, after=space_after, line=line_spacing, line_rule=line_rule
    )
    if text:
        run = p.add_run(text)
        set_run_font(
            run,
            font_name=font_name or CFG["font_body"],
            size_pt=size_pt or CFG["size_body"],
            bold=bold,
            italic=italic,
        )
    return p


def _normalize_text(text: str) -> str:
    text = re.sub(r'\\\\n(?![a-z])', '\n', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\b\1\\b", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+?)\*", r"\\i\1\\i", text)
    return text


def _append_rich_text(
    paragraph, text: str, font_name=None, size_pt=None, base_bold=False, base_italic=False
):
    fn = font_name or CFG["font_body"]
    sz = size_pt or CFG["size_body"]
    normalized = _normalize_text(text)
    bold = base_bold
    italic = base_italic
    buffer = []
    index = 0

    def flush():
        nonlocal buffer
        content = "".join(buffer)
        buffer = []
        if content:
            run = paragraph.add_run(content)
            set_run_font(run, font_name=fn, size_pt=sz, bold=bold, italic=italic)

    while index < len(normalized):
        char = normalized[index]
        if char == "\n":
            flush()
            run = paragraph.add_run()
            run.add_break()
            index += 1
            continue
        if char == "\\" and index + 1 < len(normalized):
            cmd = normalized[index + 1]
            if cmd == "\\":
                buffer.append("\\")
                index += 2
                continue
            if cmd == "b":
                flush()
                bold = not bold
                index += 2
                continue
            if cmd == "i":
                flush()
                italic = not italic
                index += 2
                continue
        if char == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                flush()
                formula = normalized[index + 1 : closing]
                if formula:
                    if not _append_inline_math(paragraph, formula):
                        run = paragraph.add_run(formula)
                        set_run_font(run, font_name=fn, size_pt=sz, italic=True)
                index = closing + 1
                continue
        buffer.append(char)
        index += 1
    flush()


def add_title(doc, data):
    title = data.get("title", "Paper Title Goes Here")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    run = p.add_run(title)
    set_run_font(run, font_name=CFG["font_title"], size_pt=CFG["size_title"], bold=True)


def add_title_english(doc, data):
    title_en = data.get("title_english", "")
    if not title_en:
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    run = p.add_run(f"({title_en})")
    set_run_font(
        run, font_name=CFG["font_title"], size_pt=CFG["size_title"], bold=True, italic=True
    )


def add_empty_para(doc):
    p = doc.add_paragraph()
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    return p


def add_authors(doc, data):
    authors = data.get("authors", [])
    if not authors:
        authors = [
            {
                "name": "Author Name",
                "affiliation": "Department, University",
                "email": "author@email.ac.id",
            }
        ]

    add_empty_para(doc)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")

    for i, author in enumerate(authors):
        name = author.get("name", "Author Name")
        if i > 0:
            if i == len(authors) - 1:
                run = p.add_run(" & ")
            else:
                run = p.add_run(", ")
            set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)

        run = p.add_run(name)
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)

        marker = "*" * (i + 1)
        run_sup = p.add_run(marker)
        set_run_font(run_sup, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)
        run_sup.font.superscript = True


def add_abstract(doc, data):
    add_empty_para(doc)

    p_label = doc.add_paragraph()
    p_label.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_label, before=0, after=0, line=240, line_rule="auto")
    run = p_label.add_run("Abstract")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True, italic=True)

    add_empty_para(doc)

    abstract_text = data.get(
        "abstract",
        "Abstract text goes here. This section should contain 150-250 words summarizing the paper.",
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    _append_rich_text(p, abstract_text)


def add_keywords(doc, data):
    add_empty_para(doc)

    keywords = data.get("keywords", ["keyword1", "keyword2", "keyword3"])
    if isinstance(keywords, list):
        # Limit to 5 keywords max (JAT template rule)
        keywords = keywords[:5]
        keywords_text = ", ".join(keywords)
    else:
        keywords_text = str(keywords)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")

    run = p.add_run("Keywords: ")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)

    run = p.add_run(keywords_text)
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])


def add_section_heading(doc, title):
    add_empty_para(doc)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=3, after=3, line=240, line_rule="auto")
    run = p.add_run(title)
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading1"], bold=True)


def add_subsection_heading(doc, title, level=1):
    add_empty_para(doc)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=3, after=3, line=240, line_rule="auto")

    if level == 1:
        run = p.add_run(title)
        set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading2"], bold=True)
    elif level == 2:
        run = p.add_run(title)
        set_run_font(
            run, font_name=CFG["font_heading"], size_pt=CFG["size_heading2"], bold=True, italic=True
        )
    elif level == 3:
        run = p.add_run(title)
        set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading3"], italic=True)


def add_body_text(doc, text, first_paragraph=False):
    text = _replace_roman_table_refs(str(text))
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")

    # Parse IEEE [N] citations → Word footnotes
    # Handle [1], [ 1 ], [1 ], [ 1] — spaces inside brackets are common in NN output
    parts = re.split(r'\[\s*(\d+)\s*\]', text)
    if len(parts) > 1:
        _init_footnotes(doc)
        for i, segment in enumerate(parts):
            if i % 2 == 0:
                # Text segment — trim trailing space if followed by punctuation
                if segment:
                    _append_rich_text(p, segment)
            else:
                ref_idx = int(segment)
                _add_footnote(doc, p, f"See reference [{ref_idx}] in bibliography.")
    else:
        _append_rich_text(p, text)


def add_block_quote(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    set_paragraph_indent(p, left=567, right=567, first_line=0)
    _append_rich_text(p, text)


def add_figure(doc, fig_data):
    image_number = str(fig_data.get("ImageNumber", "1")).strip()
    title = fig_data.get("Title", "Description of the Figure")
    path_text = fig_data.get("Path", "").strip()

    add_empty_para(doc)

    image_path = None
    if path_text:
        candidate = BASE / path_text
        if candidate.is_file():
            image_path = candidate

    if image_path and image_path.is_file():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p, before=3, after=3, line=240, line_rule="auto")
        usable_width_cm = (
            CFG["page_width_tw"] - CFG["margin_left_tw"] - CFG["margin_right_tw"]
        ) / 567.0
        max_width = min(usable_width_cm, 14.0)
        run = p.add_run()
        run.add_picture(str(image_path), width=Cm(max_width))
    else:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p, before=3, after=3, line=240, line_rule="auto")
        prompt_text = (
            f"[PROMPT UNTUK AI GAMBAR: Buatkan gambar, diagram, atau ilustrasi teknis "
            f"yang merepresentasikan '{title}'. Pastikan visualnya profesional, "
            f"hitam putih/grayscale, dan cocok untuk publikasi jurnal akademik ilmiah.]"
        )
        run = p.add_run(prompt_text)
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], italic=True)
        run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)

    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_cap, before=3, after=6, line=240, line_rule="auto")
    run = p_cap.add_run(f"{CFG['fig_prefix']} {image_number}: ")
    set_run_font(run, font_name=CFG["font_caption"], size_pt=CFG["size_caption"], bold=True)
    run = p_cap.add_run(title)
    set_run_font(run, font_name=CFG["font_caption"], size_pt=CFG["size_caption"], bold=True)

    p_src = doc.add_paragraph()
    p_src.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_src, before=0, after=0, line=240, line_rule="auto")
    run = p_src.add_run("Source: The Authors")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])


def add_formula(doc, formula_data):
    formula_number = str(formula_data.get("FormulaNumber", "")).strip()
    latex = formula_data.get("latex", "E = mc^2").strip()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=3, after=3, line=240, line_rule="auto")

    if not _append_inline_math(p, latex):
        run = p.add_run(latex)
        set_run_font(run, font_name="Cambria Math", size_pt=CFG["size_body"], italic=True)

    if formula_number:
        run = p.add_run(f"   ({formula_number})")
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])


def _roman_to_arabic(s: str) -> str:
    """Convert Roman numeral to Arabic. Returns original if not Roman."""
    roman_map = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
                 "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
                 "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15}
    upper = s.strip().upper()
    if upper in roman_map:
        return str(roman_map[upper])
    return s


def add_table(doc, table_data):
    table_number = _roman_to_arabic(str(table_data.get("TableNumber", "1")).strip())
    title = table_data.get("Title", "Description of the Table")
    headers = table_data.get("Headers", [])
    rows = table_data.get("Rows", [])

    if not headers:
        headers = ["Column 1", "Column 2"]
        rows = [["Data", "Data"]]

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_title, before=6, after=3, line=240, line_rule="auto")
    run = p_title.add_run(f"{CFG['tbl_prefix']} {table_number}: {title}")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)

    num_cols = len(headers)
    num_rows = len(rows) + 1
    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    _set_table_borders_full(table)

    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(header))
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)

    for row_idx, row_data in enumerate(rows):
        for col_idx, value in enumerate(row_data):
            if col_idx >= num_cols:
                break
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _append_rich_text(p, str(value), font_name=CFG["font_body"], size_pt=CFG["size_body"])

    p_src = doc.add_paragraph()
    p_src.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_src, before=0, after=0, line=240, line_rule="auto")
    run = p_src.add_run("Source: The Authors")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])


def _set_table_borders_full(table):
    tbl = table._tbl
    tbl_pr = tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)

    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is not None:
        tbl_pr.remove(borders)
    borders = OxmlElement("w:tblBorders")

    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)

    tbl_pr.append(borders)


def add_references(doc, data):
    ref_data = data.get("references", {})
    if isinstance(ref_data, dict):
        ref_title = ref_data.get("title", "References")
        ref_content = ref_data.get("content", [])
    else:
        ref_title = "References"
        ref_content = ref_data if isinstance(ref_data, list) else []

    add_section_heading(doc, ref_title)
    add_empty_para(doc)

    # Chicago 18th Edition notes-bibliography style
    # Extract reference text from entries
    refs = []
    for ref in ref_content:
        if isinstance(ref, dict):
            t = ref.get("text", "").strip()
        elif isinstance(ref, str):
            t = ref.strip()
        else:
            t = ""
        # Strip leading [N] or [ N ] numbering if present
        t = re.sub(r'^\[\s*\d+\s*\]\s*', '', t).strip()
        if t:
            refs.append(t)

    # Remove duplicates and sort alphabetically (Chicago style)
    seen = set()
    unique_refs = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            unique_refs.append(r)
    unique_refs.sort(key=lambda s: s.lower())

    if not unique_refs:
        unique_refs = ["Author Last, First. \"Title.\" Journal Name Volume, no. Issue (Year): Pages. https://doi.org/xxx."]

    for ref_text in unique_refs:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
        # Hanging indent per Chicago style
        p.paragraph_format.first_line_indent = Cm(-1.27)
        p.paragraph_format.left_indent = Cm(1.27)
        _append_rich_text(p, ref_text)


def process_content_item(doc, item):
    item_id = str(item.get("id", "")).lower()

    if item_id == "text":
        text = item.get("text", "")
        if text:
            add_body_text(doc, text)
    elif item_id == "gambar" or item_id == "image":
        add_figure(doc, item)
    elif item_id == "rumus" or item_id == "formula":
        add_formula(doc, item)
    elif item_id == "tabel" or item_id == "table":
        add_table(doc, item)


def process_section(doc, section_data, section_key):
    if not isinstance(section_data, dict):
        return

    title = section_data.get("title", "")
    if title:
        add_section_heading(doc, title)

    content = section_data.get("content", [])
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                add_body_text(doc, item)
            elif isinstance(item, dict):
                process_content_item(doc, item)
    elif isinstance(content, str) and content.strip():
        add_body_text(doc, content)

    subsection_keys = []
    for key in section_data.keys():
        if (
            key.startswith(section_key)
            and len(key) > len(section_key)
            and key[len(section_key) :].isalpha()
        ):
            subsection_keys.append(key)

    subsection_keys.sort()

    for sub_key in subsection_keys:
        sub_data = section_data[sub_key]
        if isinstance(sub_data, dict):
            sub_title = sub_data.get("title", "")
            if sub_title:
                add_subsection_heading(doc, sub_title, level=1)

            sub_content = sub_data.get("content", [])
            if isinstance(sub_content, list):
                for item in sub_content:
                    if isinstance(item, str):
                        add_body_text(doc, item)
                    elif isinstance(item, dict):
                        process_content_item(doc, item)
            elif isinstance(sub_content, str) and sub_content.strip():
                add_body_text(doc, sub_content)


def add_acknowledgements(doc, data):
    ack_text = data.get("acknowledgements", "").strip()
    if not ack_text:
        return

    add_section_heading(doc, "Acknowledgement")
    add_empty_para(doc)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    _append_rich_text(p, ack_text)


def generate():
    global _FOOTNOTE_COUNTER, _FOOTNOTES_INITIALIZED
    _FOOTNOTE_COUNTER = 0
    _FOOTNOTES_INITIALIZED = False

    data = load_json()

    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    clear_body(doc)

    add_title(doc, data)
    add_title_english(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    for i in range(1, 20):
        key = f"section{i}"
        if key in data:
            process_section(doc, data[key], key)

    add_acknowledgements(doc, data)
    add_references(doc, data)

    _set_ai_prompt_color_red(doc)
    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


if __name__ == "__main__":
    generate()
