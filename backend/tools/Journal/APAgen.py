"""
APA 7th Edition Template Generator

Generates papers in APA 7th edition format (double-spaced, author-year citations).
For psychology, social sciences, and education research.
"""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Cm

from _docx_base import (
    open_template,
    para,
    build_sectpr,
    embed_sectpr,
    setup_main_sectpr,
    append_rich_text,
    body_paragraphs,
    render_sections,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "APA.docx"
DEFAULT_OUTPUT_NAME = "APA_output.docx"


def _add_title_page(doc: Document, config: dict):
    title = config.get("title", "Untitled Paper")
    authors = config.get("authors", [])
    
    p = para(doc, style_id="Title", align=WD_ALIGN_PARAGRAPH.CENTER, sb=72)
    run = p.add_run(title)
    run.font.size = Pt(14)
    run.bold = True
    
    for author in authors:
        name = author.get("name", "")
        if name:
            p = para(doc, style_id="Author", align=WD_ALIGN_PARAGRAPH.CENTER)
            run = p.add_run(name)
            run.font.size = Pt(12)
    
    for author in authors:
        affiliation = author.get("affiliation", "")
        if affiliation:
            p = para(doc, style_id="Affiliation", align=WD_ALIGN_PARAGRAPH.CENTER)
            run = p.add_run(affiliation)
            run.font.size = Pt(12)


def _add_abstract(doc: Document, config: dict):
    abstract = config.get("abstract", "")
    if not abstract:
        return
    
    p = para(doc, style_id="AbstractHeading", align=WD_ALIGN_PARAGRAPH.CENTER, sb=12)
    run = p.add_run("Abstract")
    run.bold = True
    run.font.size = Pt(12)
    
    p = para(doc, style_id="Abstract", align=WD_ALIGN_PARAGRAPH.LEFT)
    append_rich_text(p, abstract)


def _add_keywords(doc: Document, config: dict):
    keywords = config.get("keywords", [])
    if not keywords:
        return
    
    p = para(doc, style_id="Keywords", sb=6)
    run = p.add_run("Keywords: ")
    run.italic = True
    append_rich_text(p, ", ".join(keywords))


def _add_references(doc: Document, config: dict):
    references = config.get("references", [])
    if not references:
        return
    
    h = para(doc, style_id="Heading1", align=WD_ALIGN_PARAGRAPH.CENTER, sb=18)
    run = h.add_run("References")
    run.bold = True
    
    for ref in references:
        if isinstance(ref, dict):
            ref_text = ref.get("text", "")
        else:
            ref_text = str(ref)
        
        if ref_text:
            p = para(doc, style_id="Reference", li=36, fi=-36)
            append_rich_text(p, ref_text)


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
        final_output = json_path.parent / f"{json_path.stem}_APA.docx"
    
    doc = Document()
    
    setup_main_sectpr(
        doc,
        w_pt=612.0,
        h_pt=792.0,
        top_pt=72.0,
        bottom_pt=72.0,
        left_pt=72.0,
        right_pt=72.0,
        num_cols=1,
    )
    
    _add_title_page(doc, config)
    
    para(doc, sa=12)
    
    _add_abstract(doc, config)
    _add_keywords(doc, config)
    
    para(doc, sa=12)
    
    cfg = {
        "heading1": "Heading1",
        "heading2": "Heading2",
        "body": "BodyText",
        "section_heading_format": "plain_upper",
        "figure_caption": "Caption",
        "table_head": "TableHead",
        "table_col_head": "TableColHead",
        "table_copy": "TableText",
        "equation": "Equation",
        "max_fig_width_cm": 14.0,
    }
    
    render_sections(doc, config, json_path, BASE_DIR, cfg)
    
    para(doc, sa=12)
    
    _add_references(doc, config)
    
    final_output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(final_output))
    return final_output


if __name__ == "__main__":
    import sys
    from _docx_base import run_generator
    
    run_generator(BASE_DIR, TEMPLATE_PATH, build_document)
