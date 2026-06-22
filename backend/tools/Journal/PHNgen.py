"""
PHN (Public Health Nutrition) Journal Template Generator

Generates papers in PHN format — Cambridge University Press style.
Title page exactly matches PHN.docx template, followed by full paper body.

Template analysis (from PHN.docx):
  - Page: Letter (8.5" x 11"), margins 1" all sides
  - Font: Times New Roman 12pt (sz=24) on ALL runs
  - docDefaults: sz=22 (11pt), spacing after=160 (8pt), lineRule=auto
  - Normal style: inherits from docDefaults (no explicit overrides)
  - PlainText style: Calibri, spacing after=0 (used for title page)
  - Title: centered, bold
  - Authors: centered, PlainText style, no bold
  - "Corresponding author:" / "Short title:" labels: bold
  - Disclosure statements: italic body
  - All other labels: no bold, no italic
  - Empty paragraphs: follow style of PREVIOUS paragraph

Structure:
  1. Title Page (matching PHN.docx exactly)
  2. Abstract page (if abstract present)
  3. Keywords
  4. Body sections
  5. Acknowledgements
  6. Financial Support
  7. Conflict of Interest
  8. Authorship
  9. Ethical Standards Disclosure
  10. References
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
TEMPLATE_PATH = BASE_DIR / "PHN.docx"
DEFAULT_OUTPUT_NAME = "PHN_output.docx"

_FONT_NAME = "Times New Roman"
_FONT_SIZE = Pt(12)  # sz=24 in half-points = 12pt
_WML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# ── helpers ─────────────────────────────────────────────────────────────


def _set_doc_defaults(doc: Document):
    """Set document-level defaults: Times New Roman 12pt, justified."""
    style = doc.styles["Normal"]
    style.font.name = _FONT_NAME
    style.font.size = _FONT_SIZE
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    style.paragraph_format.space_after = Pt(8)
    style.paragraph_format.space_before = Pt(0)


def _phn_make_run(p, text: str = "", bold: bool = False, italic: bool = False,
                  superscript: bool = False, clear: bool = True):
    """Add a clean run with Times New Roman 12pt. No false formatting elements."""
    r = p.add_run(text)
    r.font.name = _FONT_NAME
    r.font.size = _FONT_SIZE
    if bold:
        r.bold = True
    if italic:
        r.italic = True
    if superscript:
        r.font.superscript = True
    if clear:
        _strip_false_formatting(r)
    return r


def _strip_false_formatting(run):
    """Remove OOXML elements that explicitly set formatting to false/default."""
    rpr = run._element.find(f"{{{_WML_NS}}}rPr")
    if rpr is None:
        return
    for tag, false_vals in [("b", ("0", "false")), ("i", ("0", "false")), ("u", ("none",))]:
        for el in rpr.findall(f"{{{_WML_NS}}}{tag}"):
            if (el.get(f"{{{_WML_NS}}}val") or "").lower() in false_vals:
                rpr.remove(el)


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


def _ensure_font(p):
    """Ensure all runs have PHN font + size. Strip false formatting."""
    for r in p.runs:
        if not r.font.name:
            r.font.name = _FONT_NAME
        if not r.font.size:
            r.font.size = _FONT_SIZE
        _strip_false_formatting(r)


def _set_plaintext_style(paragraph):
    """Set paragraph to PlainText style (spacing after=0, Calibri font)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    ppr = paragraph._p.get_or_add_pPr()
    pStyle = ppr.find(qn("w:pStyle"))
    if pStyle is None:
        pStyle = OxmlElement("w:pStyle")
        ppr.insert(0, pStyle)
    pStyle.set(qn("w:val"), "PlainText")


def _phn_empty_line(doc, plaintext: bool = True):
    """Empty paragraph for spacing.

    Template pattern: empty paragraphs follow the style of the PREVIOUS paragraph.
    Set plaintext=True when the preceding content paragraph uses PlainText style.
    Empty paragraphs in Normal-style sections must use plaintext=False.
    """
    p = para(doc)
    if plaintext:
        _set_plaintext_style(p)
    return p


# ── title page ─────────────────────────────────────────────────────────


def _add_title_page(doc: Document, config: dict):
    """Generate PHN title page exactly matching PHN.docx template structure.

    Para mapping (from PHN.docx):
      [00] Title — jc=center, BOLD (Normal style)
      [01] Authors — jc=center, PlainText, no bold
      [02] Affiliations — PlainText, superscript numbers
      [03] empty (PlainText — follows PlainText [02])
      [04] Corresponding author — PlainText, label BOLD
      [05] empty (PlainText — follows PlainText [04])
      [06] Short title — Normal, label BOLD
      [07] empty (Normal — follows Normal [06])
      [08] Disclosure statements — Normal, ITALIC body
      [09] empty (Normal — follows Normal [08])
      [10] Acknowledgements — Normal
      [11] empty (Normal — follows Normal [10])
      [12] Financial Support — Normal
      [13] empty (Normal — follows Normal [12])
      [14] Conflict of Interest — Normal
      [15] empty (Normal — follows Normal [14])
      [16] Authorship — Normal
      [17] empty (Normal — follows Normal [16])
      [18] Ethical Standards Disclosure — Normal
    """
    # ── [00] Title — centered, bold ──
    title = str(config.get("title", "")).strip()
    if not title:
        title = "[Manuscript Title]"
    p_title = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
    _phn_make_run(p_title, title, bold=True)

    # ── [01] Authors — centered, PlainText ──
    authors = config.get("authors", [])
    author_names = []
    for author in authors:
        name = str(author.get("name", "")).strip()
        if name:
            author_names.append(name)
    author_line = ", ".join(author_names) if author_names else (
        "[Authors' names, given without titles or degrees]"
    )
    p_auth = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
    _set_plaintext_style(p_auth)
    _phn_make_run(p_auth, author_line)

    # ── [02] Affiliations — PlainText, with superscript numbers ──
    aff_map = {}
    for author in authors:
        dept = str(author.get("department", "")).strip()
        inst = str(author.get("institution", "")).strip()
        city = str(author.get("city", "")).strip()
        country = str(author.get("country", "")).strip()
        aff_str = ", ".join(p for p in [dept, inst, city, country] if p)
        if not aff_str:
            aff_str = author.get("affiliation", "")
        if aff_str and aff_str not in aff_map:
            aff_map[aff_str] = len(aff_map) + 1

    if not aff_map:
        aff_map["[Name and address of department(s) and institution(s) to which "
                "the work should be attributed for each author, with each "
                "affiliation indicated by a superscript number]"] = 1

    p_aff = para(doc)
    _set_plaintext_style(p_aff)
    for i, (aff_str, num) in enumerate(sorted(aff_map.items(), key=lambda x: x[1])):
        if i > 0:
            _phn_make_run(p_aff, "; ")
        _phn_make_run(p_aff, str(num), superscript=True)
        _phn_make_run(p_aff, aff_str)

    # ── [03] empty (PlainText — follows PlainText [02]) ──
    _phn_empty_line(doc, plaintext=True)

    # ── [04] Corresponding author — PlainText, label BOLD ──
    corr_author = config.get("corresponding_author", "")
    corr_email = config.get("corresponding_email", "")
    if not corr_author:
        for author in authors:
            if author.get("corresponding"):
                corr_author = author.get("name", "")
                corr_email = author.get("email", "")
                break
    if not corr_author:
        corr_author = "[Name, mailing address, email address, telephone and fax numbers]"
    p_corr = para(doc)
    _set_plaintext_style(p_corr)
    _phn_make_run(p_corr, "Corresponding author: ", bold=True)
    corr_body = corr_author
    if corr_email:
        corr_body = f"{corr_author}, {corr_email}"
    _phn_make_run(p_corr, corr_body)

    # ── [05] empty (PlainText — follows PlainText [04]) ──
    _phn_empty_line(doc, plaintext=True)

    # ── [06] Short title — Normal, label BOLD ──
    short_title = str(config.get("short_title", "")).strip()
    if not short_title:
        short_title = title[:45] if len(title) > 45 else title
        if not short_title:
            short_title = "[not exceeding 45 characters]"
    p_st = para(doc)
    _phn_make_run(p_st, "Short title: ", bold=True)
    _phn_make_run(p_st, short_title[:45])

    # ── [07] empty (Normal — follows Normal [06]) ──
    _phn_empty_line(doc, plaintext=False)

    # ── [08] Disclosure statements — Normal, ITALIC body, normal brackets ──
    disclaimers = []
    for key in ["disclosure", "disclosures", "disclosure_statements"]:
        val = str(config.get(key, "")).strip()
        if val:
            disclaimers.append(val)
            break
    if not disclaimers:
        disclaimers = [
            "Disclosure statements, as outlined below. These must be included "
            "on the title page and not in the manuscript file, to enable "
            "double-blind reviewing. If any are not applicable, please state this."
        ]
    p_disc = para(doc)
    # Template pattern: [ (normal) + italic body + ] (normal)
    # When using config data, render as: [body] all italic for simplicity
    body_text = disclaimers[0]
    # Check if already bracketed
    if body_text.startswith("[") and body_text.endswith("]"):
        _phn_make_run(p_disc, "[", bold=False, italic=False)
        _phn_make_run(p_disc, body_text[1:-1], italic=True)
        _phn_make_run(p_disc, "]", bold=False, italic=False)
    else:
        _phn_make_run(p_disc, body_text, italic=True)

    # ── [09] empty (Normal — follows Normal [08]) ──
    _phn_empty_line(doc, plaintext=False)


def _add_post_title_sections(doc: Document, config: dict):
    """Add sections that appear on title page after disclosures.

    All paragraphs use Normal style. Empty lines follow Normal (plaintext=False).
    """
    # ── [10] Acknowledgements ──
    ack = str(config.get("acknowledgements", "")).strip()
    p_ack = para(doc)
    _phn_make_run(p_ack, "Acknowledgements: ")
    _phn_make_run(p_ack, ack if ack else (
        "[Here you may acknowledge individuals or organizations that "
        "provided advice and/or support (non-financial)]"
    ))
    _phn_empty_line(doc, plaintext=False)  # [11]

    # ── [12] Financial Support ──
    fin = str(config.get("financial_support", "")).strip()
    p_fin = para(doc)
    _phn_make_run(p_fin, "Financial Support: ")
    _phn_make_run(p_fin, fin if fin else (
        "[Please provide details of the sources of financial support "
        "for all authors, including grant numbers]"
    ))
    _phn_empty_line(doc, plaintext=False)  # [13]

    # ── [14] Conflict of Interest ──
    coi = str(config.get("conflict_of_interest", "")).strip()
    p_coi = para(doc)
    _phn_make_run(p_coi, "Conflict of Interest:  ")
    _phn_make_run(p_coi, coi if coi else (
        "[Please provide details of all known financial and non-financial "
        "(professional and personal) relationships]"
    ))
    _phn_empty_line(doc, plaintext=False)  # [15]

    # ── [16] Authorship ──
    authorship = str(config.get("authorship", "")).strip()
    p_auth2 = para(doc)
    _phn_make_run(p_auth2, "Authorship: ")
    _phn_make_run(p_auth2, authorship if authorship else (
        "[Please provide a very brief description of the "
        "contribution of each author]"
    ))
    _phn_empty_line(doc, plaintext=False)  # [17]

    # ── [18] Ethical Standards Disclosure ──
    ethics = str(config.get("ethical_standards", "")).strip()
    p_eth = para(doc)
    _phn_make_run(p_eth, "Ethical Standards Disclosure: ")
    _phn_make_run(p_eth, ethics if ethics else (
        "[Manuscripts describing research involving human participants "
        "must include the following statements]"
    ))
    _phn_empty_line(doc, plaintext=False)  # spacer before abstract/body


# ── abstract ───────────────────────────────────────────────────────────


def _add_abstract(doc: Document, config: dict):
    """Add abstract section after title page."""
    abstract = str(config.get("abstract", "")).strip()
    if not abstract:
        return

    # Abstract heading
    p_head = para(doc)
    _phn_make_run(p_head, "Abstract")

    # Abstract body
    for bp in body_paragraphs(doc, abstract, style_id="Normal"):
        _ensure_font(bp)

    # Keywords
    keywords = config.get("keywords", "")
    if isinstance(keywords, list):
        keywords = "; ".join(kw.strip() for kw in keywords if kw.strip())
    if keywords:
        p_kw = para(doc)
        _phn_make_run(p_kw, "Keywords: ")
        _phn_make_run(p_kw, str(keywords))


# ── body sections ──────────────────────────────────────────────────────


def _phn_render_content_item(doc: Document, item: dict, json_path: Path):
    """Render a single content item (image/table/formula/text)."""
    from _docx_base import (
        _resolve_path, _add_prompt_box_with_text, _strip_math_delimiters,
        _add_equation_line, _set_table_borders,
    )

    item_id = str(item.get("id", "")).lower()

    if item_id == "text":
        text = str(item.get("text", ""))
        if text:
            for bp in body_paragraphs(doc, text, style_id="Normal"):
                _ensure_font(bp)

    elif item_id in ("gambar", "image"):
        image_number = str(item.get("ImageNumber", "")).strip()
        path_text = str(item.get("Path", "")).strip()
        prompt = str(item.get("Prompt", "")).strip()
        title = str(item.get("Title", "")).strip()
        max_fig_width = 14.0

        image_path = _resolve_path(path_text, json_path) if path_text else None
        try:
            width_cm = float(item.get("WidthCm", max_fig_width))
        except Exception:
            width_cm = max_fig_width
        width_cm = max(1.0, min(width_cm, max_fig_width))

        if image_path is not None and image_path.is_file():
            paragraph = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER, sb=6, sa=2)
            paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
        else:
            fallback = f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt}]" if title \
                else f"[PROMPT UNTUK AI GAMBAR: {prompt}]"
            _add_prompt_box_with_text(doc, fallback)

        if image_number and title:
            cap = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
            _phn_make_run(cap, f"Figure {image_number}. {title}")

    elif item_id in ("tabel", "table"):
        table_number = str(item.get("TableNumber", "")).strip()
        title = str(item.get("Title", "")).strip()
        headers = list(item.get("Headers", []))
        rows = list(item.get("Rows", []))

        if not headers:
            return

        # Caption centered
        cap = para(doc, align=WD_ALIGN_PARAGRAPH.CENTER)
        label = f"Table {table_number}" if table_number else "Table"
        cap_text = f"{label}. {title}" if title else label
        _phn_make_run(cap, cap_text)

        table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
        table.style = "Normal Table"
        from docx.enum.table import WD_TABLE_ALIGNMENT
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True
        _set_table_borders(table)

        # Header row
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
        formula_text = str(
            item.get("latex", "") or item.get("text", "") or item.get("formula", "")
        ).strip()
        if formula_text:
            formula_text = _strip_math_delimiters(formula_text)
            _add_equation_line(
                doc, formula_text,
                formula_number if formula_number else None,
                style_id="Normal",
            )


def _phn_render_sections(doc: Document, config: dict, json_path: Path):
    """Render all body sections with content items."""
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

        # Section heading — bold
        heading_text = (
            f"{section_number}. {section_title}"
            if section_number else section_title
        )
        hp = para(doc)
        _phn_make_run(hp, heading_text, bold=True)

        # Body content
        content = section.get("content", "")
        if isinstance(content, str) and content.strip():
            for bp in body_paragraphs(doc, content.strip(), style_id="Normal"):
                _ensure_font(bp)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    for bp in body_paragraphs(doc, item.strip(), style_id="Normal"):
                        _ensure_font(bp)
                elif isinstance(item, dict):
                    _phn_render_content_item(doc, item, json_path)

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
                _phn_make_run(hp, heading_text)

            content_items = subsection.get("content", [])
            if isinstance(content_items, list):
                for item in content_items:
                    if isinstance(item, str):
                        for bp in body_paragraphs(doc, item.strip(), style_id="Normal"):
                            _ensure_font(bp)
                    elif isinstance(item, dict):
                        _phn_render_content_item(doc, item, json_path)
            elif isinstance(content_items, str):
                if content_items.strip():
                    for bp in body_paragraphs(doc, content_items.strip(), style_id="Normal"):
                        _ensure_font(bp)


# ── references ─────────────────────────────────────────────────────────


def _add_references(doc: Document, config: dict):
    """Add reference list."""
    refs = normalize_references(config)
    if not refs:
        return

    # References heading
    hp = para(doc)
    _phn_make_run(hp, "References", bold=True)

    for ref in refs:
        rp = para(doc)
        ref_id = ref.get("id", "")
        ref_text = ref.get("text", "")
        if ref_id:
            _phn_make_run(rp, f"{ref_id}. ")
        if ref_text:
            append_rich_text(rp, ref_text)
        _ensure_font(rp)


# ── build_document ─────────────────────────────────────────────────────


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
        final_output = json_path.parent / f"{json_path.stem}_PHN.docx"

    doc = Document()

    # Page setup — Letter (8.5" x 11"), 1" margins
    setup_main_sectpr(
        doc,
        w_pt=612.0,       # 8.5 inches
        h_pt=792.0,       # 11 inches
        top_pt=72.0,      # 1 inch
        bottom_pt=72.0,
        left_pt=72.0,
        right_pt=72.0,
        num_cols=1,
    )

    _set_doc_defaults(doc)

    # ── Title page ──
    _add_title_page(doc, config)
    _add_post_title_sections(doc, config)

    # ── Abstract + Keywords ──
    _add_abstract(doc, config)

    # ── Body sections ──
    _phn_render_sections(doc, config, json_path)

    # ── References ──
    _add_references(doc, config)

    # Global cleanup
    _strip_doc_false_formatting(doc)

    final_output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(final_output))
    return final_output


if __name__ == "__main__":
    import sys
    from _docx_base import run_generator

    run_generator(BASE_DIR, TEMPLATE_PATH, build_document)