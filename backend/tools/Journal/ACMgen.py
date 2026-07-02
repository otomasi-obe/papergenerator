"""
ACM Conference Proceedings Template Generator

Generates papers in ACM SIGCONF format (two-column, numbered references).
Based on ACM Master Article Template.
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
    roman,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "ACM.docx"
DEFAULT_OUTPUT_NAME = "ACM_output.docx"


def _add_title(doc: Document, config: dict):
    title = config.get("title", "Untitled Paper")
    p = para(doc, style_id="Title", align=WD_ALIGN_PARAGRAPH.LEFT)
    append_rich_text(p, title)


def _add_authors(doc: Document, config: dict):
    authors = config.get("authors", [])
    if not authors:
        return
    
    for author in authors:
        name = author.get("name", "")
        affiliation = author.get("affiliation", "")
        email = author.get("email", "")
        
        if name:
            p = para(doc, style_id="Author", align=WD_ALIGN_PARAGRAPH.LEFT)
            run = p.add_run(name)
            run.font.size = Pt(12)
        
        if affiliation:
            p = para(doc, style_id="Affiliation", align=WD_ALIGN_PARAGRAPH.LEFT)
            run = p.add_run(affiliation)
            run.font.size = Pt(10)
            run.italic = True
        
        if email:
            p = para(doc, style_id="Affiliation", align=WD_ALIGN_PARAGRAPH.LEFT)
            run = p.add_run(email)
            run.font.size = Pt(10)


def _add_abstract(doc: Document, config: dict):
    abstract = config.get("abstract", "")
    if not abstract:
        return
    
    p = para(doc, style_id="AbstractHeading")
    p.add_run("ABSTRACT")
    
    p = para(doc, style_id="Abstract")
    append_rich_text(p, abstract)


def _add_keywords(doc: Document, config: dict):
    keywords = config.get("keywords", [])
    if not keywords:
        return
    
    p = para(doc, style_id="Keywords")
    p.add_run("Keywords: ")
    append_rich_text(p, ", ".join(keywords))


def _format_ref(item):
    """Format a reference dict into a citation string."""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return str(item)
    # Already has text
    text = item.get("text") or item.get("Text") or item.get("value")
    if text:
        return str(text).strip()
    # Build from fields
    parts = []
    authors = item.get("authors", [])
    if authors:
        parts.append(", ".join(authors))
    year = item.get("year")
    if year:
        parts.append(f"({year})")
    title = item.get("title", "")
    if title:
        parts.append(f'"{title},"')
    jname = item.get("journal") or item.get("conference") or ""
    if jname:
        parts.append(f"{jname},")
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
        parts.append(f"[Online]. Available: {url}" + (f" [Accessed: {accessed}]" if accessed else ""))
    result = " ".join(parts).strip()
    # Clean trailing comma
    if result.endswith(","):
        result = result[:-1] + "."
    return result

def _add_references(doc: Document, config: dict):
    references = config.get("references", [])
    raw_entries = []
    if isinstance(references, list):
        raw_entries = references
    elif isinstance(references, dict):
        for key in ("content", "items", "references"):
            candidate = references.get(key)
            if isinstance(candidate, list):
                raw_entries = candidate
                break
    if not raw_entries:
        return
    
    h = para(doc, style_id="Heading1")
    h.add_run("REFERENCES")
    
    for idx, ref in enumerate(raw_entries, start=1):
        ref_text = _format_ref(ref)
        if ref_text:
            p = para(doc, style_id="Reference")
            append_rich_text(p, f"[{idx}] {ref_text}")


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
        final_output = json_path.parent / f"{json_path.stem}_ACM.docx"
    
    doc = Document()
    
    setup_main_sectpr(
        doc,
        w_pt=595.3,
        h_pt=841.9,
        top_pt=54.0,
        bottom_pt=54.0,
        left_pt=54.0,
        right_pt=54.0,
        col_space_pt=12.0,
        num_cols=1,
    )
    
    _add_title(doc, config)
    
    embed_sectpr(doc, build_sectpr(1, 12.0, 54.0, 54.0, 54.0, 54.0))
    
    _add_authors(doc, config)
    
    embed_sectpr(doc, build_sectpr(2, 12.0, 54.0, 54.0, 54.0, 54.0))
    
    _add_abstract(doc, config)
    _add_keywords(doc, config)
    
    cfg = {
        "heading1": "Heading1",
        "heading2": "Heading2",
        "body": "BodyText",
        "section_heading_format": "arabic",
        "figure_caption": "Caption",
        "table_head": "TableHead",
        "table_col_head": "TableColHead",
        "table_copy": "TableText",
        "equation": "Equation",
        "max_fig_width_cm": 8.0,
    }
    
    render_sections(doc, config, json_path, BASE_DIR, cfg)
    
    _add_references(doc, config)
    
    final_output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(final_output))
    return final_output


if __name__ == "__main__":
    import sys
    from _docx_base import run_generator
    
    run_generator(BASE_DIR, TEMPLATE_PATH, build_document)
