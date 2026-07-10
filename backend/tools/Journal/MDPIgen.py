"""
MDPI Journal Template Generator

Generates papers in MDPI (Multidisciplinary Digital Publishing Institute) format.
Open access journal format with single-column layout.

Supports 148+ individual MDPI journals with journal-specific logos, headers, and footers.
Set "journal" in JSON config to "MDPI_acoustics", "MDPI_ijms", etc.

Supports two JSON formats:
1. "sections" array format (preferred) — nested arrays with subsections
2. "section1"/"section2" legacy format — flat numbered keys
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Inches, RGBColor

from _docx_base import (
    para,
    setup_main_sectpr,
    append_rich_text,
    render_sections,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "MDPI.docx"
LOGOS_DIR = BASE_DIR / "logos"

# MDPI style mapping
MD_STYLES = {
    "article_type": "MDPI_1.1_article_type",
    "title": "MDPI_1.2_title",
    "author_names": "MDPI_1.3_authornames",
    "affiliation": "MDPI_1.6_affiliation",
    "abstract": "MDPI_1.7_abstract",
    "keywords": "MDPI_1.8_keywords",
    "line": "MDPI_1.9_line",
    "heading1": "MDPI_2.1_heading1",
    "heading2": "MDPI_2.2_heading2",
    "heading3": "MDPI_2.3_heading3",
    "body_text": "MDPI_3.1_text",
    "text_no_indent": "MDPI_3.2_text_no_indent",
    "text_before_list": "MDPI_3.5_text_before_list",
    "itemize": "MDPI_3.7_itemize",
    "bullet": "MDPI_3.8_bullet",
    "equation": "MDPI_3.9_equation",
    "table_caption": "MDPI_4.1_table_caption",
    "table_body": "MDPI_4.2_table_body",
    "table_footer": "MDPI_4.3_table_footer",
    "figure_caption": "MDPI_5.1_figure_caption",
    "figure": "MDPI_5.2_figure",
    "back_matter": "MDPI_6.2_back_matter",
    "notes": "MDPI_6.3_notes",
    "references": "MDPI_8.1_references",
    "theorem": "MDPI_8.2_theorem",
    "proof": "MDPI_8.3_proof",
}


def _format_reference(item) -> str:
    """Format a reference dict into a citation string."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()
    text = item.get("text") or item.get("Text") or item.get("value")
    if text:
        return str(text).strip()
    parts = []
    authors = item.get("authors", [])
    if authors:
        parts.append(", ".join(str(a) for a in authors) if isinstance(authors, list) else str(authors))
    year = item.get("year")
    if year:
        parts.append(f"({year})")
    title = item.get("title", "")
    if title:
        parts.append(f'"{title},"')
    jname = item.get("journal") or item.get("conference") or ""
    if jname:
        parts.append(str(jname) + ",")
    vol = item.get("volume", "")
    if vol:
        parts.append(f"vol. {vol},")
    issue = item.get("issue", "")
    if issue:
        parts.append(f"no. {issue},")
    pages = item.get("pages", "")
    if pages:
        parts.append(f"pp. {pages},")
    doi = item.get("doi", "")
    if doi:
        parts.append(f"doi: {doi}.")
    url = item.get("url", "")
    if url:
        accessed = item.get("accessed", "")
        parts.append(f"[Online]. Available: {url}" + (f" [Accessed: {accessed}]." if accessed else "."))
    publisher = item.get("publisher", "")
    if publisher and not jname:
        location = item.get("location", "")
        parts.append(f"{location}: {publisher}." if location else f"{publisher}.")
    result = " ".join(str(p) for p in parts if p).strip()
    result = result.replace(" , ", ", ").replace(" .", ".")
    if result.endswith(","):
        result = result[:-1] + "."
    if not result.endswith("."):
        result = result + "."
    return result

def _normalize_config(config: dict) -> dict:
    """Convert 'sections' array format into section1/section2... keyed format.

    Input:
      {"sections": [{"title": "Intro", "content": [...], "subsections": [...]}, ...]}

    Output:
      {"section1": {"title": "Intro", "number": "1", "content": [...]}, "section2": {...}}
    """
    if "sections" in config and isinstance(config["sections"], list):
        normalized = {k: v for k, v in config.items() if k != "sections"}
        for idx, sec in enumerate(config["sections"], start=1):
            key = f"section{idx}"
            normalized_section = _normalize_section(sec, idx)
            normalized[key] = normalized_section
        return normalized
    return config


def _normalize_section(section: dict, sec_num: int, prefix: str = "") -> dict:
    """Recursively convert a section with 'subsections' into flat keyed format.

    section1 content remains as-is (list with id='text'/'gambar'/'tabel' items).
    subsections become sub{num}{letter} keys.
    Nested subsections become subsub{num}{letter}{letter} keys.
    """
    out = {
        "title": section.get("title", ""),
        "number": str(sec_num),
        "content": section.get("content", []),
    }

    subsections = section.get("subsections", [])
    for i, sub in enumerate(subsections):
        letter = chr(ord("a") + i)  # a, b, c, ...
        sub_key = f"sub{sec_num}{letter}"
        out[sub_key] = _normalize_section(sub, sec_num, prefix + letter)

        # Handle nested subsections (subsubsections)
        nested = sub.get("subsections", [])
        for j, nested_sub in enumerate(nested):
            nested_letter = chr(ord("a") + j)
            nested_key = f"sub{sec_num}{letter}{nested_letter}"
            out[nested_key] = _normalize_section(nested_sub, sec_num, prefix + letter + nested_letter)

    return out


# ── Template & layout helpers ──


def _get_journal_config(config: dict) -> dict | None:
    from template_registry import get_mdpi_journal_info, resolve_template_journal
    journal_code = config.get("journal", "")
    base_code, sub_key = resolve_template_journal(journal_code)
    if sub_key:
        return get_mdpi_journal_info(sub_key)
    return None


def _read_template_margins(doc: Document) -> dict:
    section = doc.sections[0]
    return {
        "top_tw": round(section.top_margin / 635),
        "bottom_tw": round(section.bottom_margin / 635),
        "left_tw": round(section.left_margin / 635),
        "right_tw": round(section.right_margin / 635),
        "header_tw": round(section.header_distance / 635),
        "footer_tw": round(section.footer_distance / 635),
    }


def _clear_body_keep_sectpr(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _preserve_template_logos(doc: Document, template_path: Path) -> None:
    from lxml import etree
    DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
    R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    tmpl_doc = Document(str(template_path))
    tmpl_body = tmpl_doc._element.body

    logo_elements = []
    for child in tmpl_body.iterchildren():
        if child.tag == qn("w:sectPr"):
            continue
        for blip in child.findall(f".//{{{DRAWING_NS}}}blip"):
            rid = blip.get(f"{{{R_NS}}}embed")
            if rid in ("rId3", "rId4"):
                logo_elements.append(etree.fromstring(etree.tostring(child)))
                break

    if not logo_elements:
        return

    body = doc._element.body
    sectpr = body.find(qn("w:sectPr"))
    for elem in reversed(logo_elements):
        if sectpr is not None:
            sectpr.addprevious(elem)
        else:
            body.append(elem)


def _fix_decimal_margins(doc: Document) -> None:
    for section in doc.sections:
        pgMar = section._sectPr.find(qn("w:pgMar"))
        if pgMar is None:
            continue
        for attr in ("w:left", "w:right", "w:top", "w:bottom", "w:header", "w:footer"):
            val = pgMar.get(qn(attr))
            if val:
                try:
                    pgMar.set(qn(attr), str(int(float(val))))
                except ValueError:
                    pass


def _patch_header_footer_text(doc: Document, jconf: dict | None):
    if not jconf:
        return

    short_name = jconf.get("short_name", "")
    year = str(jconf.get("year", 2025))
    volume = str(jconf.get("volume", 1))
    section = doc.sections[0]

    for header in [section.header, section.first_page_header]:
        for p in header.paragraphs:
            text = p.text
            if "FOR PEER REVIEW" not in text and "https://doi.org" not in text:
                continue
            for r in p.runs:
                t = r.text
                if t in ("Acoustics", "MDPI") and r.font.italic:
                    r.text = short_name
                    break

    for p in section.footer.paragraphs:
        for r in p.runs:
            t = r.text
            if "https://doi.org" in t:
                r.text = f"{short_name} {year}, {volume}, x https://doi.org/10.3390/xxxxx"
            elif "Acoustics" in t:
                r.text = short_name

    for p in section.first_page_footer.paragraphs:
        for r in p.runs:
            t = r.text
            if "https://doi.org" in t:
                r.text = f"{short_name} {year}, {volume}, x https://doi.org/10.3390/xxxxx"


def _add_journal_logo(doc: Document, jconf: dict | None):
    if not jconf:
        return
    logo_path = LOGOS_DIR / f"{jconf.get('key', '')}.png"
    if not logo_path.exists():
        return

    section = doc.sections[0]
    if not section.different_first_page_header_footer:
        return
    first_header = section.first_page_header

    for p in first_header.paragraphs:
        for run in p.runs:
            drawings = run._r.findall(qn("w:drawing"))
            if drawings:
                for d in drawings:
                    run._r.remove(d)
                try:
                    run.add_picture(str(logo_path), width=Inches(2.5))
                except Exception:
                    pass
                return

    for table in first_header.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for run in p.runs:
                        drawings = run._r.findall(qn("w:drawing"))
                        if drawings:
                            for d in drawings:
                                run._r.remove(d)
                            try:
                                run.add_picture(str(logo_path), width=Inches(2.5))
                            except Exception:
                                pass
                            return


# ── Content builders ──


def _add_title(doc: Document, config: dict):
    title = config.get("title", "Untitled Paper")
    p = para(doc, style_id=MD_STYLES["title"], align=WD_ALIGN_PARAGRAPH.LEFT)
    run = p.add_run(title)
    run.font.size = Pt(20)
    run.bold = True


def _add_authors(doc: Document, config: dict):
    authors = config.get("authors", [])
    if not authors:
        return

    author_names = []
    author_superscripts = []
    for idx, author in enumerate(authors, start=1):
        name = author.get("name", "")
        if name:
            author_names.append(name)
            author_superscripts.append(idx)

    if author_names:
        p = para(doc, style_id=MD_STYLES["author_names"], align=WD_ALIGN_PARAGRAPH.LEFT)
        for i, (name, idx) in enumerate(zip(author_names, author_superscripts)):
            if i > 0:
                run = p.add_run(", ")
                run.font.size = Pt(11)
            run = p.add_run(name)
            run.font.size = Pt(11)
            # Add superscript affiliation number
            sup_run = p.add_run(str(idx))
            sup_run.font.size = Pt(8)
            sup_run.font.superscript = True

    for idx, author in enumerate(authors, start=1):
        affiliation = author.get("affiliation", "")
        email = author.get("email", "")

        if affiliation:
            p = para(doc, style_id=MD_STYLES["affiliation"], align=WD_ALIGN_PARAGRAPH.LEFT)
            run = p.add_run(f"{idx} {affiliation}")
            run.font.size = Pt(9)

        if email:
            p = para(doc, style_id=MD_STYLES["affiliation"], align=WD_ALIGN_PARAGRAPH.LEFT)
            run = p.add_run(f"* Correspondence: {email}")
            run.font.size = Pt(9)
            run.italic = True


def _add_abstract(doc: Document, config: dict):
    abstract = config.get("abstract", "")
    if not abstract:
        return

    p = para(doc, style_id=MD_STYLES["abstract"], sb=6)
    run = p.add_run("Abstract: ")
    run.bold = True
    run.font.size = Pt(10)
    append_rich_text(p, abstract)


def _add_keywords(doc: Document, config: dict):
    keywords = config.get("keywords", [])
    if not keywords:
        return

    p = para(doc, style_id=MD_STYLES["keywords"], sb=6)
    run = p.add_run("Keywords: ")
    run.bold = True
    append_rich_text(p, "; ".join(keywords))

    # Add separator line
    para(doc, style_id=MD_STYLES["line"])


def _add_references(doc: Document, config: dict):
    references = config.get("references", [])
    if isinstance(references, dict):
        references = references.get("content") or references.get("items") or []

    # Also check for 'referensi' key
    if not references:
        references = config.get("referensi", [])

    if not references:
        return

    h = para(doc, style_id=MD_STYLES["heading1"], sb=18)
    h.add_run("References")

    for idx, ref in enumerate(references, start=1):
        if isinstance(ref, dict):
            # Build APA-style reference from structured data
            ref_text = _format_apa_reference(ref)
        else:
            ref_text = str(ref)

        if ref_text.strip():
            p = para(doc, style_id=MD_STYLES["references"], li=36, fi=-36)
            append_rich_text(p, f"{idx}. {ref_text}")


def _format_apa_reference(ref: dict) -> str:
    """Format a reference dict into APA-style text."""
    authors = ref.get("authors", ref.get("author", ""))
    year = ref.get("year", "")
    title = ref.get("title", "")
    journal = ref.get("journal", ref.get("venue", ""))
    volume = ref.get("volume", "")
    number = ref.get("number", "")
    pages = ref.get("pages", "")
    doi = ref.get("doi", "")

    text = ""
    if authors:
        text += f"{authors} "
    if year:
        text += f"({year}). "
    if title:
        text += f"{title}. "
    if journal:
        text += f"*{journal}*"
        if volume:
            text += f", *{volume}*"
            if number:
                text += f"({number})"
        if pages:
            text += f", {pages}"
        text += ". "
    if doi:
        text += f"https://doi.org/{doi}"

    return text.strip()


def _add_back_matter(doc: Document, config: dict):
    """Add mandatory back matter sections if present in config."""
    back_items = config.get("back_matter", config.get("backmatter", []))

    if not back_items:
        # Default MDPI back matter items
        back_items = [
            {
                "label": "Supplementary Materials",
                "text": "The following supporting information can be downloaded at: [URL]."
            },
            {
                "label": "Author Contributions",
                "text": "Conceptualization, methodology, investigation, writing, all authors."
            },
            {
                "label": "Funding",
                "text": "This research received no external funding."
            },
            {
                "label": "Data Availability Statement",
                "text": "Data available on request from the corresponding author."
            },
            {
                "label": "Acknowledgments",
                "text": "Acknowledgments to all parties who supported this research."
            },
            {
                "label": "Conflicts of Interest",
                "text": "The authors declare no conflicts of interest."
            },
        ]

    for item in back_items:
        label = item.get("label", "")
        text = item.get("text", "")
        p = para(doc, style_id=MD_STYLES["back_matter"])
        run = p.add_run(f"{label}: ")
        run.bold = True
        append_rich_text(p, text or "To be added.")


def _add_disclaimer(doc: Document):
    """Add MDPI disclaimer/publisher's note."""
    p = para(doc, style_id=MD_STYLES["notes"])
    run = p.add_run("Disclaimer/Publisher's Note: ")
    run.bold = True
    append_rich_text(
        p,
        "The statements, opinions and data contained in all publications are solely those "
        "of the individual author(s) and contributor(s) and not of MDPI and/or the editor(s). "
        "MDPI and/or the editor(s) disclaim responsibility for any injury to people or property "
        "resulting from any ideas, methods, instructions or products referred to in the content.",
    )


# ── AI Prompt Coloring ──


def _set_ai_prompt_color_red(doc: Document):
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

    for t in doc.tables:
        rows = t.rows
        if len(rows) < 2 or len(rows[0].cells) < 2:
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


# ── Main build ──


def build_document(
    json_path: Path | str,
    output_path: Path | str | None = None,
    template_path: Path | str = TEMPLATE_PATH,

) -> Path:
    json_path = Path(json_path)
    config_original = json.loads(json_path.read_text(encoding="utf-8"))

    # Normalize sections array format to section1/section2 keyed format
    config = _normalize_config(config_original)

    tp = Path(template_path)
    if output_path:
        final_output = Path(output_path)
    else:
        final_output = json_path.parent / f"{json_path.stem}_MDPI.docx"

    final_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(tp), str(final_output))

    doc = Document(str(final_output))
    _fix_decimal_margins(doc)
    margins = _read_template_margins(doc)
    _clear_body_keep_sectpr(doc)
    _preserve_template_logos(doc, tp)

    setup_main_sectpr(
        doc,
        w_pt=595.3,
        h_pt=841.9,
        top_pt=margins["top_tw"] / 20,
        bottom_pt=margins["bottom_tw"] / 20,
        left_pt=margins["left_tw"] / 20,
        right_pt=margins["right_tw"] / 20,
        header_pt=margins["header_tw"] / 20,
        footer_pt=margins["footer_tw"] / 20,
        num_cols=1,
    )

    jconf = _get_journal_config(config)
    _patch_header_footer_text(doc, jconf)
    _add_journal_logo(doc, jconf)

    # ── Article type (optional) ──
    article_type = config.get("article_type", "")
    if article_type:
        p = para(doc, style_id=MD_STYLES["article_type"])
        p.add_run(article_type)

    # ── Front matter ──
    _add_title(doc, config)
    _add_authors(doc, config)
    _add_abstract(doc, config)
    _add_keywords(doc, config)

    # ── Sections ──
    # MDPI-specific cfg for render_sections
    cfg = {
        "heading1": MD_STYLES["heading1"],
        "heading2": MD_STYLES["heading2"],
        "body": MD_STYLES["body_text"],
        "section_heading_format": "arabic",
        "figure_caption": MD_STYLES["figure_caption"],
        "table_head": MD_STYLES["table_caption"],
        "table_col_head": MD_STYLES["table_caption"],
        "table_copy": MD_STYLES["table_body"],
        "equation": MD_STYLES["equation"],
        "max_fig_width_cm": 14.0,
    }

    render_sections(doc, config, json_path, BASE_DIR, cfg)

    # ── Back matter ──
    _add_back_matter(doc, config)
    _add_references(doc, config)
    _add_disclaimer(doc)

    _set_ai_prompt_color_red(doc)

    doc.save(str(final_output))
    return final_output


def build_pdf(json_path: Path, pdf_path: Path, template_path=None) -> Path:
    """Build a PDF for this journal template from a paper JSON.

    Calls build_document() to produce a .docx, then converts to .pdf
    via LibreOffice headless.  Final PDF is written to ``pdf_path``.
    """
    from ._render_pdf import build_pdf_from_builder
    return build_pdf_from_builder(build_document, json_path, pdf_path, template_path)

if __name__ == "__main__":
    import sys

    from _docx_base import run_generator

    run_generator(BASE_DIR, TEMPLATE_PATH, build_document)