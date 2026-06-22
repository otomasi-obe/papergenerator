"""
SJMR Journal Template Generator

Generates papers in SJMR format — simple single-column layout.
All paragraphs use Normal style (Times New Roman 12pt, justified).
No bold, no center alignment (except figure/table captions).
Section headings are title-case (not uppercase).

Structure:
  - Paper Type (optional header)
  - Title — justified, not bold
  - Authors with superscript affiliation numbers + * for corresponding
  - Numbered affiliation list — justified
  - *Correspondence: email — justified
  - Abstract: ... — justified
  - Keywords: k1; k2; k3 — justified
  - Body sections (1. Title, 2. Title, ...) — justified, title case
  - Subsections (3.1. Title, 3.1.1. Title) — justified, title case
  - Figure/Table captions — centered, "Figure N. caption" / "Table N. caption"
  - Acknowledgments: ... — justified
  - Author Contributions: ... — justified
  - References — justified, numbered "N.\t..."
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Cm

from _docx_base import (
    para,
    setup_main_sectpr,
    append_rich_text,
    body_paragraphs,
    normalize_references,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "SJMR.docx"
DEFAULT_OUTPUT_NAME = "SJMR_output.docx"

_FONT_NAME = "Times New Roman"
_FONT_SIZE = Pt(12)  # 12pt — matches docDefaults in SJMR.docx
_WML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# ── helpers ─────────────────────────────────────────────────────────────

def _set_doc_defaults(doc: Document):
    """Set document-level defaults: Times New Roman 12pt, justified.

    SJMR.docx docDefaults: space_after=160 twips (8pt), line=278 (1.158),
    sz=24 (12pt), theme font minorHAnsi → Times New Roman.
    No explicit spacing on individual paragraphs — uniform flow.
    """
    style = doc.styles["Normal"]
    style.font.name = _FONT_NAME
    style.font.size = _FONT_SIZE
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    style.paragraph_format.space_after = Pt(8)   # match docDefaults 160 twips
    style.paragraph_format.space_before = Pt(0)


def _sj_make_run(p, text: str = "", superscript: bool = False, clear: bool = True):
    """Add a clean run — no explicit bold/italic/underline elements.
    
    `clear=True` removes extraneous formatting elements that python-docx
    adds even when setting to False (e.g. <w:b w:val="0"/>).
    """
    r = p.add_run(text)
    r.font.name = _FONT_NAME
    r.font.size = _FONT_SIZE
    if superscript:
        r.font.superscript = True
    if clear:
        _strip_false_formatting(r)
    return r


def _sj_labeled_paragraph(doc: Document, label: str, body: str, sp_after: float | None = None):
    """Paragraph with label prefix + normal body. NO bold — match template.

    SJMR template uses no bold anywhere. Labels like "Abstract:", "Keywords:"
    are distinguished only by the colon separator.

    Pass `sp_after` as a plain float (points) to override spacing.
    Default None lets Normal style (8pt from docDefaults) control spacing.
    """
    p = para(doc, sa=sp_after)
    r_label = p.add_run(label)
    r_label.font.name = _FONT_NAME
    r_label.font.size = _FONT_SIZE
    if body:
        append_rich_text(p, body)
    return p


def _strip_false_formatting(run):
    """Remove OOXML elements that explicitly set formatting to false/default.
    
    python-docx creates <w:b w:val="0"/>, <w:i w:val="0"/>, <w:u w:val="none"/>
    when setting properties to False/None. The template doesn't have these.
    """
    rpr = run._element.find(f"{{{_WML_NS}}}rPr")
    if rpr is None:
        return
    # Remove false-bold: <w:b w:val="0"/> or <w:b w:val="false"/>
    for b in rpr.findall(f"{{{_WML_NS}}}b"):
        val = (b.get(f"{{{_WML_NS}}}val") or "").lower()
        if val in ("0", "false"):
            rpr.remove(b)
    # Remove false-italic
    for i in rpr.findall(f"{{{_WML_NS}}}i"):
        val = (i.get(f"{{{_WML_NS}}}val") or "").lower()
        if val in ("0", "false"):
            rpr.remove(i)
    # Remove false-underline
    for u in rpr.findall(f"{{{_WML_NS}}}u"):
        val = (u.get(f"{{{_WML_NS}}}val") or "").lower()
        if val == "none":
            rpr.remove(u)


def _strip_doc_false_formatting(doc: Document):
    """Strip explicit false formatting from ALL runs in the document."""
    for p in doc.paragraphs:
        for r in p.runs:
            _strip_false_formatting(r)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        _strip_false_formatting(r)


def _ensure_font_sjmr(p):
    """Ensure all runs have SJMR font + size. Also strip false formatting."""
    for r in p.runs:
        if not r.font.name:
            r.font.name = _FONT_NAME
        if not r.font.size:
            r.font.size = _FONT_SIZE
        _strip_false_formatting(r)


# ── sections ────────────────────────────────────────────────────────────

def _add_paper_type(doc: Document, config: dict):
    pt = config.get("paper_type", "")
    if not pt:
        return
    p = para(doc)
    _sj_make_run(p, pt)


def _add_title(doc: Document, config: dict):
    title = config.get("title", "Untitled Paper")
    p = para(doc)
    _sj_make_run(p, title)


def _add_authors(doc: Document, config: dict):
    authors = config.get("authors", [])
    if not authors:
        return

    aff_map: dict[str, int] = {}
    aff_list: list[str] = []
    for author in authors:
        dept = author.get("department", "")
        inst = author.get("institution", "")
        city = author.get("city", "")
        country = author.get("country", "")
        parts = [p for p in [dept, inst, city, country] if p]
        aff_str = ", ".join(parts) if parts else ""
        if aff_str and aff_str not in aff_map:
            aff_num = len(aff_list) + 1
            aff_map[aff_str] = aff_num
            aff_list.append(aff_str)
    if not aff_list:
        for i, author in enumerate(authors, 1):
            aff = author.get("affiliation", "")
            if aff and aff not in aff_map:
                aff_map[aff] = i
                aff_list.append(aff)

    p = para(doc)
    for i, author in enumerate(authors):
        name = author.get("name", "")
        if not name:
            continue
        if i > 0:
            _sj_make_run(p, ", ")

        _sj_make_run(p, name)

        dept = author.get("department", "")
        inst = author.get("institution", "")
        city = author.get("city", "")
        country = author.get("country", "")
        parts = [x for x in [dept, inst, city, country] if x]
        aff_str = ", ".join(parts) if parts else author.get("affiliation", "")
        if aff_str and aff_str in aff_map:
            _sj_make_run(p, str(aff_map[aff_str]), superscript=True)
        if author.get("corresponding"):
            _sj_make_run(p, ",*", superscript=True)

    for aff_str, num in sorted(aff_map.items(), key=lambda x: x[1]):
        ap = para(doc)
        _sj_make_run(ap, f"{num} {aff_str}")

    corr_email = ""
    for author in authors:
        if author.get("corresponding"):
            corr_email = author.get("email", "")
            break
    if not corr_email and authors:
        corr_email = authors[0].get("email", "")
    if corr_email:
        cp = para(doc)
        _sj_make_run(cp, f"*Correspondence: {corr_email}")


def _add_abstract(doc: Document, config: dict):
    abstract = config.get("abstract", "")
    if not abstract:
        return
    p = _sj_labeled_paragraph(doc, "Abstract: ", abstract)
    _ensure_font_sjmr(p)


def _add_keywords(doc: Document, config: dict):
    keywords = config.get("keywords", [])
    if not keywords:
        return
    kw_text = "; ".join(keywords)
    p = _sj_labeled_paragraph(doc, "Keywords: ", kw_text)
    _ensure_font_sjmr(p)


def _add_acknowledgments(doc: Document, config: dict):
    ack = config.get("acknowledgments", config.get("acknowledgements", ""))
    if not ack:
        return
    p = _sj_labeled_paragraph(doc, "Acknowledgments: ", ack)
    _ensure_font_sjmr(p)


def _add_author_contributions(doc: Document, config: dict):
    contrib = config.get("author_contributions", "")
    if not contrib:
        return
    p = _sj_labeled_paragraph(doc, "Author Contributions: ", contrib)
    _ensure_font_sjmr(p)


def _add_references(doc: Document, config: dict):
    refs = normalize_references(config)
    if not refs:
        return
    p = para(doc)
    r = p.add_run("References")
    r.font.name = _FONT_NAME
    r.font.size = _FONT_SIZE

    for ref in refs:
        ref_id = ref.get("id", "")
        ref_text = ref.get("text", "")
        if not ref_text:
            continue
        rp = para(doc)
        _sj_make_run(rp, f"{ref_id}.\t")
        append_rich_text(rp, ref_text)
        _ensure_font_sjmr(rp)


# ── custom content rendering for SJMR ───────────────────────────────────

def _sjmr_render_content_item(doc: Document, item: dict, json_path: Path):
    """SJMR-specific content item renderer — no bold, table captions centered."""
    from _docx_base import _resolve_path, _add_prompt_box_with_text, _strip_math_delimiters
    from _docx_base import _add_equation_line, _set_table_borders, _style_cell_paragraph, _normalize_text_commands

    item_id = str(item.get("id", "")).lower()

    if item_id == "text":
        text = str(item.get("text", ""))
        if text:
            for bp in body_paragraphs(doc, text, style_id="Normal"):
                _ensure_font_sjmr(bp)

    elif item_id in ("gambar", "image"):
        image_number = str(item.get("ImageNumber", "")).strip()
        path_text = str(item.get("Path", "")).strip()
        prompt = str(item.get("Prompt", "")).strip()
        title = str(item.get("Title", "")).strip()
        max_fig_width = 14.0

        image_path = _resolve_path(path_text, json_path) if path_text else None
        width_cm = max_fig_width
        try:
            width_cm = float(item.get("WidthCm", max_fig_width))
        except Exception:
            pass
        width_cm = max(1.0, min(width_cm, max_fig_width))

        if image_path is not None and image_path.is_file():
            paragraph = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER, sb=6, sa=2)
            paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
        else:
            fallback_text = f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt}]" if title else f"[PROMPT UNTUK AI GAMBAR: {prompt}]"
            _add_prompt_box_with_text(doc, fallback_text)

        if image_number and title:
            cap = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
            _sj_make_run(cap, f"Figure {image_number}. {title}")

    elif item_id in ("tabel", "table"):
        table_number = str(item.get("TableNumber", "")).strip()
        title = str(item.get("Title", "")).strip()
        headers = list(item.get("Headers", []))
        rows = list(item.get("Rows", []))

        if not headers:
            return

        # Caption centered (SJMR style)
        cap = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
        label = f"Table {table_number}" if table_number else "Table"
        cap_text = f"{label}. {title}" if title else label
        _sj_make_run(cap, cap_text)

        table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
        table.style = "Normal Table"
        from docx.enum.table import WD_TABLE_ALIGNMENT
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True
        _set_table_borders(table)

        # Header row — NO bold (SJMR style)
        for ci, value in enumerate(headers):
            cell = table.rows[0].cells[ci]
            cell.text = ""
            p_cell = cell.paragraphs[0]
            r = p_cell.add_run(str(value))
            r.font.name = _FONT_NAME
            r.font.size = _FONT_SIZE
            _strip_false_formatting(r)

        # Data rows
        for ri, row_data in enumerate(rows, start=1):
            for ci, value in enumerate(row_data):
                if ci >= len(headers):
                    break
                cell = table.rows[ri].cells[ci]
                cell.text = ""
                p_cell = cell.paragraphs[0]
                r = p_cell.add_run(str(value))
                r.font.name = _FONT_NAME
                r.font.size = _FONT_SIZE
                _strip_false_formatting(r)

        para(doc, sa=4)

    elif item_id in ("rumus", "formula"):
        formula_number = str(item.get("FormulaNumber", "")).strip()
        formula_text = str(item.get("latex", "") or item.get("text", "") or item.get("formula", "")).strip()
        if formula_text:
            formula_text = _strip_math_delimiters(formula_text)
            _add_equation_line(doc, formula_text, formula_number if formula_number else None, style_id="Normal")


# ── section rendering ──────────────────────────────────────────────────

def _sjmr_render_sections(doc: Document, config: dict, json_path: Path):
    section_keys = []
    for key in config.keys():
        if key.startswith("section") and key.replace("section", "").isdigit():
            section_keys.append(key)
    section_keys.sort(key=lambda x: int(x.replace("section", "")))

    for section_key in section_keys:
        section = config[section_key]
        section_number = str(section.get("number", "")).strip()
        if not section_number:
            num_part = section_key.replace("section", "")
            if num_part.isdigit():
                section_number = num_part
        section_title = str(section.get("title", "")).strip()

        heading_text = f"{section_number}. {section_title}" if section_number else section_title

        hp = para(doc)
        _sj_make_run(hp, heading_text)

        # Body content
        content = section.get("content", "")
        if isinstance(content, str) and content.strip():
            for bp in body_paragraphs(doc, content.strip(), style_id="Normal"):
                _ensure_font_sjmr(bp)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    for bp in body_paragraphs(doc, item.strip(), style_id="Normal"):
                        _ensure_font_sjmr(bp)
                elif isinstance(item, dict):
                    _sjmr_render_content_item(doc, item, json_path)

        # Subsections
        subsection_keys = []
        for key in section.keys():
            if (key.startswith("sub") and len(key) > 3 and key[3:].isalnum()) or \
               re.match(r"^section\d+[a-z]+$", key):
                subsection_keys.append(key)
        for key in sorted(subsection_keys):
            subsection = section[key]
            subsection_letter = str(subsection.get("letter", "")).strip()
            if not subsection_letter:
                m = re.match(r"^(?:sub|section)\d+([a-z]+)$", key)
                if m:
                    subsection_letter = m.group(1).upper()
            subsection_title = str(subsection.get("title", "")).strip()

            if subsection_letter and subsection_title:
                heading_text = f"{subsection_letter}. {subsection_title}"
            elif subsection_title:
                heading_text = subsection_title
            else:
                heading_text = ""

            if heading_text:
                hp = para(doc)
                _sj_make_run(hp, heading_text)

            content_items = subsection.get("content", [])
            if isinstance(content_items, list):
                for item in content_items:
                    if isinstance(item, str):
                        for bp in body_paragraphs(doc, item.strip(), style_id="Normal"):
                            _ensure_font_sjmr(bp)
                    elif isinstance(item, dict):
                        _sjmr_render_content_item(doc, item, json_path)
            elif isinstance(content_items, str):
                if content_items.strip():
                    for bp in body_paragraphs(doc, content_items.strip(), style_id="Normal"):
                        _ensure_font_sjmr(bp)


# ── post-process ───────────────────────────────────────────────────────

# Caption prefix fix: already handled in _sjmr_render_content_item
# (Figure N. / Table N. format used directly, no conversion needed)


# ── build_document ──────────────────────────────────────────────────────

def build_document(
    json_path: Path | str,
    output_path: Path | str | None = None,
    template_path: Path | str = TEMPLATE_PATH,
) -> Path:
    json_path = Path(json_path)
    config = json.loads(json_path.read_text(encoding="utf-8"))

    if output_path:
        final_output = Path(output_path)
    else:
        final_output = json_path.parent / f"{json_path.stem}_SJMR.docx"

    doc = Document()

    setup_main_sectpr(
        doc,
        w_pt=595.3,
        h_pt=841.9,
        top_pt=56.69,      # 2cm — matches SJMR.docx
        bottom_pt=56.69,
        left_pt=56.69,
        right_pt=56.69,
        num_cols=1,
    )

    _set_doc_defaults(doc)

    _add_paper_type(doc, config)
    _add_title(doc, config)
    _add_authors(doc, config)
    _add_abstract(doc, config)
    _add_keywords(doc, config)

    _sjmr_render_sections(doc, config, json_path)

    _add_acknowledgments(doc, config)
    _add_author_contributions(doc, config)
    _add_references(doc, config)

    # Global cleanup: strip false formatting from all runs
    _strip_doc_false_formatting(doc)

    final_output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(final_output))
    return final_output


if __name__ == "__main__":
    import sys
    from _docx_base import run_generator

    run_generator(BASE_DIR, TEMPLATE_PATH, build_document)