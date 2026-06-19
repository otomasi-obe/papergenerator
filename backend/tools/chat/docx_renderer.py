"""
Chat DOCX Renderer — render JSON spec to .docx file.

Supports: heading, paragraph (bold/italic/underline), LaTeX formula (via OMML),
          table, questionnaire.

The JSON spec format:

{
  "title": "Dokumen Kuesioner",
  "orientation": "portrait",   // optional, default portrait
  "content": [
    {"type": "heading", "text": "I. Pendahuluan", "level": 1},
    {"type": "paragraph", "text": "Teks biasa dengan \\\\b...\\\\b (bold),
     \\\\i...\\\\i (italic), \\\\u...\\\\u (underline)."},
    {"type": "formula", "latex": "x = \\\\frac{-b \\\\pm \\\\sqrt{b^2 - 4ac}}{2a}", "label": "(1)"},
    {"type": "table", "caption": "Tabel 1. Contoh",
     "headers": ["No", "Nama", "Nilai"],
     "rows": [["1", "Alice", "90"], ["2", "Bob", "85"]]},
    {"type": "questionnaire", "title": "Kuesioner Kepuasan",
     "instructions": "Petunjuk pengisian...",
     "variables": [
       {"variable": "X1", "indicator": "Kualitas Sistem",
        "items": ["Kemudahan penggunaan", "Navigasi intuitif"],
        "scale": "Likert 1-5"}
     ]},
    {"type": "answer_sheet", "title": "Lembar Jawaban",
     "variables": [...same structure...]}
  ]
}
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, Emu, Inches
from lxml import etree

log = logging.getLogger(__name__)

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
DEFAULT_FONT = "Times New Roman"
DEFAULT_FONT_SIZE = Pt(11)
HEADING_SIZES = {1: Pt(14), 2: Pt(13), 3: Pt(12)}

# ── Math conversion cache ──────────────────────────────────────────────
_MML2OMML_XSL_PATH = Path(__file__).resolve().parent.parent / "Journal" / "MML2OMML.XSL"
_XSLT = None


def _get_xslt():
    global _XSLT
    if _XSLT is not None:
        return _XSLT
    path = _MML2OMML_XSL_PATH
    if path.exists():
        try:
            _XSLT = etree.XSLT(etree.parse(str(path)))
            return _XSLT
        except Exception:
            pass
    _XSLT = False
    return _XSLT


def _sanitize_latex(latex: str) -> str:
    """Clean LaTeX before conversion."""
    if not latex:
        return latex
    s = latex.strip()
    # Strip display delimiters
    if s.startswith("$$") and s.endswith("$$"):
        s = s[2:-2].strip()
    elif s.startswith("\\[") and s.endswith("\\]"):
        s = s[2:-2].strip()
    elif s.startswith("\\(") and s.endswith("\\)"):
        s = s[2:-2].strip()
    # Text commands → math equivalents
    s = s.replace("\\text{", "\\mathrm{")
    s = s.replace("\\textbf{", "\\mathbf{")
    s = s.replace("\\textit{", "\\mathit{")
    # Strip formatting
    s = re.sub(r"\\displaystyle\s*", "", s)
    s = re.sub(r"\\label\{[^}]*\}", "", s)
    s = re.sub(r"\\ref\{[^}]*\}", "", s)
    s = re.sub(r"\\eqref\{[^}]*\}", "", s)
    s = re.sub(r"\\tag\{[^}]*\}", "", s)
    s = re.sub(r"\\boxed\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\color\{[^}]*\}\{([^}]*)\}", r"\1", s)
    # Big delimiters
    s = s.replace("\\Big(", "\\left(").replace("\\Big)", "\\right)")
    s = s.replace("\\big(", "\\left(").replace("\\big)", "\\right)")
    s = s.replace("\\Bigl(", "\\left(").replace("\\Biggr)", "\\right)")
    return s


def _latex_to_omml(latex: str):
    """Convert LaTeX to Office Math Markup Language (OMML)."""
    try:
        import latex2mathml.converter
    except ImportError:
        log.warning("latex2mathml not available")
        return None
    xslt = _get_xslt()
    if not xslt:
        log.warning("MML2OMML.XSL not found")
        return None
    cleaned = _sanitize_latex(latex)
    if not cleaned:
        return None
    try:
        mathml = latex2mathml.converter.convert(cleaned)
        root = etree.fromstring(mathml.encode("utf-8"))
        omml_root = xslt(root).getroot()
        return omml_root
    except Exception as e:
        log.warning("OMML conversion failed for %r: %s", cleaned[:60], e)
        return None


def _append_inline_math(paragraph, latex: str) -> bool:
    """Append LaTeX as OMML math to paragraph. Returns True on success."""
    omml = _latex_to_omml(latex)
    if omml is None:
        run = paragraph.add_run(latex)
        run.italic = True
        run.font.name = DEFAULT_FONT
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


# ── Text formatting ────────────────────────────────────────────────────

# Format markers (same as chatPrompt.txt / IEEEgen.py convention):
#   \\b...\\b = bold
#   \\i...\\i = italic
#   \\u...\\u = underline
_RICH_RE = re.compile(
    r"\\\\(b|i|u)\\{(.+?)\\\\(b|i|u)\\}|"  # matched bracket form: \\b{text}\\b
    r"\\(b|i|u)\\b\\s+(.+?)\\s+\\\\(b|i|u)\\b",  # space-delimited: \\b text \\b
    re.DOTALL,
)

# Simpler pattern: \\b{text}\\b, \\i{text}\\i, \\u{text}\\u
_SIMPLE_RICH_RE = re.compile(r"\\(b|i|u)\{(.+?)\}\\(b|i|u)")


def _append_rich_text(paragraph, text: str, font_name: str = DEFAULT_FONT,
                      font_size: Pt = DEFAULT_FONT_SIZE):
    """Append text with \\b{...}\\b bold, \\i{...}\\i italic, \\u{...}\\u underline."""
    if not text:
        return
    # Decode stray escapes first
    text = _decode_stray_escapes(text)
    # Also support the older \\b...\\b format without braces
    text = _normalize_rich_tags(text)
    # Parse and render
    _render_rich_segments(paragraph, text, font_name, font_size)


def _normalize_rich_tags(text: str) -> str:
    """No-op: the \b{text}\b format is handled directly in _render_rich_segments."""
    return text


def _render_rich_segments(paragraph, text: str, font_name: str, font_size: Pt):
    """Parse and render text with inline formatting tags."""
    pattern = re.compile(
        r'\\(b|i|u)\{(.*?)\}\\(b|i|u)', re.DOTALL
    )
    pos = 0
    for m in pattern.finditer(text):
        # Plain text before this match
        prefix = text[pos:m.start()]
        if prefix:
            _add_run(paragraph, prefix, font_name, font_size)
        # Check that open/close tags match
        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
        if open_tag == close_tag:
            bold = (open_tag == 'b')
            italic = (open_tag == 'i')
            underline = (open_tag == 'u')
            _add_run(paragraph, inner, font_name, font_size,
                     bold=bold, italic=italic, underline=underline)
        else:
            # Mismatched tags → treat as plain text including the tags
            _add_run(paragraph, m.group(0), font_name, font_size)
        pos = m.end()
    # Remaining text
    tail = text[pos:]
    if tail:
        _add_run(paragraph, tail, font_name, font_size)


def _add_run(paragraph, text: str, font_name: str = DEFAULT_FONT,
             font_size: Pt = DEFAULT_FONT_SIZE,
             bold: bool = False, italic: bool = False, underline: bool = False):
    """Add a single run with formatting."""
    if not text:
        return
    run = paragraph.add_run(text)
    run.bold = bold
    run.italic = italic
    run.underline = underline
    run.font.name = font_name
    run.font.size = font_size


def _decode_stray_escapes(text: str) -> str:
    """Decode literal \\uXXXX escape sequences."""
    if not text or "\\u" not in text:
        return text
    text = text.replace("\x08", "")

    def _u(m):
        try:
            ch = chr(int(m.group(1), 16))
            return " " if ord(ch) < 0x20 else ch
        except Exception:
            return m.group(0)
    return re.sub(r"\\u([0-9a-fA-F]{4})", _u, text)


# ── Table helpers ──────────────────────────────────────────────────────

def _set_table_borders(table) -> None:
    """Set clean table borders: top + bottom + insideH + insideV."""
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    tbl_borders = tbl_pr.find(qn("w:tblBorders"))
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    visible = {"top", "bottom", "insideH", "insideV"}
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tbl_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tbl_borders.append(el)
        if edge in visible:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")
        else:
            el.set(qn("w:val"), "nil")
            el.set(qn("w:sz"), "0")


def _shade_cell(cell, color: str = "D9E2F3"):
    """Add background shading to a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color)
    shading.set(qn("w:val"), "clear")
    tc_pr.append(shading)


# ── Document structure ─────────────────────────────────────────────────

def _add_heading(doc: Document, item: dict):
    """Add a heading paragraph."""
    text = item.get("text", "")
    level = item.get("level", 1)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf = p.paragraph_format
    pf.space_before = Pt(12)
    pf.space_after = Pt(6)
    size = HEADING_SIZES.get(level, Pt(12))
    _add_run(p, text, font_size=size, bold=True)


def _add_paragraph(doc: Document, item: dict):
    """Add a rich-text paragraph."""
    text = item.get("text", "")
    align = item.get("align", "justify")
    p = doc.add_paragraph()
    align_map = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    p.alignment = align_map.get(align, WD_ALIGN_PARAGRAPH.JUSTIFY)
    pf = p.paragraph_format
    pf.space_after = Pt(6)
    pf.first_line_indent = Cm(0.75) if align != "center" else None
    _append_rich_text(p, text)


def _add_formula(doc: Document, item: dict):
    """Add a LaTeX formula as centered OMML equation."""
    latex = item.get("latex", "")
    label = item.get("label", "")
    if not latex:
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(6)
    ok = _append_inline_math(p, latex)
    if not ok:
        # Fallback: already rendered as italic text by _append_inline_math
        pass
    if label:
        _add_run(p, f"  {label}")


def _add_table(doc: Document, item: dict):
    """Add a formatted table."""
    caption = item.get("caption", "")
    headers = item.get("headers", [])
    rows = item.get("rows", [])
    if not headers:
        return
    # Caption
    if caption:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf = p.paragraph_format
        pf.space_after = Pt(4)
        _add_run(p, caption, font_size=Pt(10), bold=True)

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders(table)

    # Header row
    for ci, val in enumerate(headers):
        cell = table.rows[0].cells[ci]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p, str(val), font_size=Pt(10), bold=True)
        _shade_cell(cell, "D9E2F3")

    # Data rows
    for ri, row_data in enumerate(rows):
        for ci, val in enumerate(row_data):
            if ci >= len(headers):
                break
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _append_rich_text(p, str(val), font_size=Pt(10))

    # Spacing after table
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)


def _add_questionnaire(doc: Document, item: dict):
    """Add a questionnaire section with variable-indicator structure."""
    title = item.get("title", "KUESIONER")
    instructions = item.get("instructions", "")
    variables = item.get("variables", [])

    # Title
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(12)
    pf.space_after = Pt(6)
    _add_run(p, title, font_size=Pt(14), bold=True)

    # Instructions
    if instructions:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pf = p.paragraph_format
        pf.space_after = Pt(8)
        _add_run(p, instructions, font_size=Pt(10))

    if not variables:
        return

    # Variable definition table
    # Columns: No | Variabel | Indikator | Item Pertanyaan | Skala
    headers = ["No", "Variabel", "Indikator", "Item Pertanyaan", "Skala"]
    # Count total rows needed (variables with items)
    total_rows = sum(max(len(v.get("items", [])), 1) for v in variables)

    table = doc.add_table(rows=total_rows + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders(table)

    # Header
    for ci, val in enumerate(headers):
        cell = table.rows[0].cells[ci]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p, val, font_size=Pt(9), bold=True)
        _shade_cell(cell, "D9E2F3")

    # Data rows — one row per variable-item pair
    row_idx = 1
    item_no = 0
    for var in variables:
        var_name = var.get("variable", "")
        indicator = var.get("indicator", "")
        items = var.get("items", [""])
        scale = var.get("scale", "Likert 1-5")
        var_row_start = row_idx
        for itm in items:
            item_no += 1
            cell_no = table.rows[row_idx].cells[0]
            cell_no.text = ""
            p = cell_no.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_run(p, str(item_no), font_size=Pt(9))

            cell_var = table.rows[row_idx].cells[1]
            cell_var.text = ""
            p = cell_var.paragraphs[0]
            _add_run(p, var_name if itm == items[0] else "", font_size=Pt(9))

            cell_ind = table.rows[row_idx].cells[2]
            cell_ind.text = ""
            p = cell_ind.paragraphs[0]
            _add_run(p, indicator if itm == items[0] else "", font_size=Pt(9))

            cell_item = table.rows[row_idx].cells[3]
            cell_item.text = ""
            p = cell_item.paragraphs[0]
            _add_run(p, itm, font_size=Pt(9))

            cell_scale = table.rows[row_idx].cells[4]
            cell_scale.text = ""
            p = cell_scale.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_run(p, scale if itm == items[0] else "", font_size=Pt(9))

            row_idx += 1

        # Merge variable/indicator/scale cells if multiple items
        var_item_count = len(items)
        if var_item_count > 1:
            _merge_cells_vertical(table, var_row_start, 1, var_item_count)  # variable
            _merge_cells_vertical(table, var_row_start, 2, var_item_count)  # indicator
            _merge_cells_vertical(table, var_row_start, 4, var_item_count)  # scale

    # Set column widths
    _set_col_widths(table, [Cm(0.8), Cm(2.0), Cm(2.5), Cm(7.0), Cm(2.0)])

    # Spacing
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(6)


def _add_answer_sheet(doc: Document, item: dict):
    """Add an answer sheet with empty fillable table."""
    title = item.get("title", "LEMBAR JAWABAN")
    instructions = item.get("instructions", "Berilah tanda centang (✓) pada kolom yang sesuai.")
    variables = item.get("variables", [])
    scale_labels = item.get("scale_labels", ["STS", "TS", "N", "S", "SS"])

    # Title
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(18)
    pf.space_after = Pt(6)
    _add_run(p, title, font_size=Pt(14), bold=True)

    # Instructions
    if instructions:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pf = p.paragraph_format
        pf.space_after = Pt(8)
        _add_run(p, instructions, font_size=Pt(10))

    # Collect all items
    all_items = []
    for var in variables:
        for itm in var.get("items", []):
            all_items.append(itm)

    if not all_items:
        return

    # Table: No | Pernyataan | STS | TS | N | S | SS
    headers = ["No", "Pernyataan"] + scale_labels
    table = doc.add_table(rows=len(all_items) + 1, cols=len(headers))
    table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders(table)

    # Header
    for ci, val in enumerate(headers):
        cell = table.rows[0].cells[ci]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p, val, font_size=Pt(9), bold=True)
        _shade_cell(cell, "D9E2F3")

    # Rows
    for ri, itm in enumerate(all_items):
        # No
        cell_no = table.rows[ri + 1].cells[0]
        cell_no.text = ""
        p = cell_no.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p, str(ri + 1), font_size=Pt(9))

        # Statement
        cell_stmt = table.rows[ri + 1].cells[1]
        cell_stmt.text = ""
        p = cell_stmt.paragraphs[0]
        _add_run(p, itm, font_size=Pt(9))

        # Scale columns (empty for filling)
        for si in range(len(scale_labels)):
            cell = table.rows[ri + 1].cells[2 + si]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # Leave empty — user fills in

    # Column widths: No narrow, Pernyataan wide, scale columns narrow
    widths = [Cm(0.8), Cm(8.0)] + [Cm(1.5)] * len(scale_labels)
    _set_col_widths(table, widths)

    # Spacing
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(6)


def _merge_cells_vertical(table, start_row: int, col: int, count: int):
    """Merge cells vertically in a column."""
    if count <= 1:
        return
    try:
        cell_start = table.rows[start_row].cells[col]
        cell_end = table.rows[start_row + count - 1].cells[col]
        cell_start.merge(cell_end)
        # Re-center merged content
        p = cell_start.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception as e:
        log.warning("Cell merge failed: %s", e)


def _set_col_widths(table, widths_cm: list):
    """Set explicit column widths."""
    for ri, row in enumerate(table.rows):
        for ci, cell in enumerate(row.cells):
            if ci < len(widths_cm):
                cell.width = widths_cm[ci]


# ── Main renderer ──────────────────────────────────────────────────────

_ENABLED_TYPES = {
    "heading": _add_heading,
    "paragraph": _add_paragraph,
    "formula": _add_formula,
    "table": _add_table,
    "questionnaire": _add_questionnaire,
    "answer_sheet": _add_answer_sheet,
}


def render_docx(spec: dict, output_path: Optional[Path] = None) -> Path:
    """Render a JSON spec into a .docx file.

    Args:
        spec: The JSON document specification.
        output_path: Target .docx path. If None, creates a temp file.

    Returns:
        Path to the generated .docx file.
    """
    doc = Document()

    # Page setup
    section = doc.sections[0]
    orientation = spec.get("orientation", "portrait")
    if orientation == "landscape":
        section.orientation = 1  # WD_ORIENT.LANDSCAPE
        section.page_width = Cm(29.7)
        section.page_height = Cm(21.0)
    else:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.54)
    section.right_margin = Cm(2.54)

    # Default font
    style = doc.styles["Normal"]
    style.font.name = DEFAULT_FONT
    style.font.size = DEFAULT_FONT_SIZE
    style.paragraph_format.space_after = Pt(6)

    # Title
    title = spec.get("title", "")
    if title:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf = p.paragraph_format
        pf.space_after = Pt(12)
        _add_run(p, title, font_size=Pt(16), bold=True)

    # Content items
    content = spec.get("content", [])
    for item in content:
        item_type = item.get("type", "paragraph")
        handler = _ENABLED_TYPES.get(item_type)
        if handler:
            try:
                handler(doc, item)
            except Exception as e:
                log.warning("Failed to render %s item: %s", item_type, e)
                # Add error placeholder
                p = doc.add_paragraph()
                _add_run(p, f"[Error rendering {item_type}]", italic=True)
        else:
            # Unknown type: render as plain paragraph
            text = item.get("text", json.dumps(item, ensure_ascii=False))
            p = doc.add_paragraph()
            _append_rich_text(p, text)

    # Save
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".docx", prefix="chat_docx_")
        os.close(fd)
        output_path = Path(output_path)

    doc.save(str(output_path))
    log.info("DOCX rendered: %s (%d items)", output_path, len(content))
    return output_path


def render_docx_from_json_string(json_str: str, output_path: Optional[Path] = None) -> Path:
    """Parse JSON string and render to .docx."""
    spec = json.loads(json_str)
    return render_docx(spec, output_path)


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, os

    test_spec = {
        "title": "Kuesioner Kepuasan Pengguna Sistem PaperFull",
        "orientation": "portrait",
        "content": [
            {
                "type": "heading",
                "text": "I. Identitas Responden",
                "level": 1,
            },
            {
                "type": "paragraph",
                "text": "Kuesioner ini bertujuan untuk mengukur tingkat kepuasan pengguna "
                        "terhadap sistem PaperFull. Jawablah dengan jujur sesuai pengalaman Anda.",
            },
            {
                "type": "heading",
                "text": "II. Variabel dan Indikator",
                "level": 2,
            },
            {
                "type": "table",
                "caption": "Tabel 1. Definisi Operasional Variabel",
                "headers": ["Variabel", "Definisi", "Indikator", "Skala"],
                "rows": [
                    ["Kualitas Sistem\n(X1)", "Tingkat kualitas teknis sistem informasi",
                     "Kemudahan, kecepatan, keandalan", "Likert 1-5"],
                    ["Kualitas Informasi\n(X2)", "Kualitas output informasi yang dihasilkan",
                     "Akurasi, relevansi, kelengkapan", "Likert 1-5"],
                ],
            },
            {
                "type": "formula",
                "latex": "Y = \\beta_0 + \\beta_1 X_1 + \\beta_2 X_2 + \\epsilon",
                "label": "(1)",
            },
            {
                "type": "paragraph",
                "text": "Keterangan: \\\\b{Y}\\b = Kepuasan Pengguna, \\\\b{X1}\\b = Kualitas Sistem, "
                        "\\\\b{X2}\\b = Kualitas Informasi, \\\\b{\\epsilon}\\b = error term.",
            },
            {
                "type": "questionnaire",
                "title": "KUESIONER PENELITIAN",
                "instructions": "Petunjuk: Berilah jawaban pada kolom yang tersedia "
                                "sesuai dengan pendapat Anda.",
                "variables": [
                    {
                        "variable": "X1",
                        "indicator": "Kualitas Sistem",
                        "items": [
                            "Sistem PaperFull mudah digunakan",
                            "Navigasi antar fitur berjalan lancar",
                            "Waktu loading halaman cepat",
                            "Sistem jarang mengalami error",
                        ],
                        "scale": "Likert 1-5",
                    },
                    {
                        "variable": "X2",
                        "indicator": "Kualitas Informasi",
                        "items": [
                            "Informasi yang dihasilkan akurat",
                            "Output paper sesuai dengan format yang diharapkan",
                            "Referensi yang digunakan relevan",
                        ],
                        "scale": "Likert 1-5",
                    },
                ],
            },
            {
                "type": "answer_sheet",
                "title": "LEMBAR JAWABAN",
                "instructions": "Berilah tanda centang (✓) pada kolom yang sesuai.\n"
                                "STS=Sangat Tidak Setuju, TS=Tidak Setuju, "
                                "N=Netral, S=Setuju, SS=Sangat Setuju",
                "variables": [
                    {
                        "variable": "X1",
                        "indicator": "Kualitas Sistem",
                        "items": [
                            "Sistem PaperFull mudah digunakan",
                            "Navigasi antar fitur berjalan lancar",
                            "Waktu loading halaman cepat",
                            "Sistem jarang mengalami error",
                        ],
                    },
                    {
                        "variable": "X2",
                        "indicator": "Kualitas Informasi",
                        "items": [
                            "Informasi yang dihasilkan akurat",
                            "Output paper sesuai dengan format yang diharapkan",
                            "Referensi yang digunakan relevan",
                        ],
                    },
                ],
                "scale_labels": ["STS", "TS", "N", "S", "SS"],
            },
        ],
    }

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/test_chat_docx.docx")
    result = render_docx(test_spec, out)
    print(f"Generated: {result} ({result.stat().st_size} bytes)")