"""
PAUDIAgen.py — Generator DOCX untuk Jurnal PAUDIA: Jurnal Penelitian dalam Bidang Pendidikan Anak Usia Dini.
Sinta 3. Template-based (preserve masthead table), TNR 11pt body, 1.5 spacing.
Supports both flat section1-N and sections[] array JSON formats.
APA references from structured data or plain text.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "PAUDIA.docx"

FONT = "Times New Roman"
SZ_TITLE = 14
SZ_BODY = 11
SZ_CAPTION = 10
SZ_REF = 11
SZ_SUBHEADING = 11


# ═══════════════════════════════════════════════════════════════════
# LaTeX cleaning
# ═══════════════════════════════════════════════════════════════════
def _clean_latex(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    text = re.sub(r'\\mathrm\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\approx', '\u2248', text)
    text = re.sub(r'\\times', '\u00d7', text)
    text = re.sub(r'\\cdot', '\u00b7', text)
    text = re.sub(r'\\quad', ' ', text)
    text = re.sub(r'\\infty', '\u221e', text)
    text = re.sub(r'\\circ', '\u00b0', text)
    text = re.sub(r'\\alpha', '\u03b1', text)
    text = re.sub(r'\\beta', '\u03b2', text)
    text = re.sub(r'\\gamma', '\u03b3', text)
    text = re.sub(r'\\theta', '\u03b8', text)
    text = re.sub(r'\\pi', '\u03c0', text)
    text = re.sub(r'\\mu', '\u03bc', text)
    # Convert subscripts to Unicode subscript characters
    _sub_map = {
        '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
        '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
        'i': 'ᵢ', 'j': 'ⱼ', 'k': 'ₖ', 'l': 'ₗ', 'm': 'ₘ',
        'n': 'ₙ', 'o': 'ₒ', 'p': 'ₚ', 'r': 'ᵣ', 's': 'ₛ',
        't': 'ₜ', 'x': 'ₓ', 'y': 'ᵧ', 'z': 'z',
        'a': 'ₐ', 'e': 'ₑ', 'h': 'ₕ',
    }
    _sup_map = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        'n': 'ⁿ', 'x': 'ˣ', 'y': 'ʸ',
    }

    def _sub_single(m):
        c = m.group(1)
        return _sub_map.get(c) or c

    def _sup_single(m):
        c = m.group(1)
        return _sup_map.get(c) or c

    def _sub_braced(m):
        s = m.group(1)
        return ''.join(_sub_map.get(c) or c for c in s)

    def _sup_braced(m):
        s = m.group(1)
        return ''.join(_sup_map.get(c) or c for c in s)

    # Braced sub/superscript: _{abc} → ₐᵦc
    text = re.sub(r'_\{([^}]+)\}', _sub_braced, text)
    text = re.sub(r'\^\{([^}]+)\}', _sup_braced, text)
    # Single-char sub/superscript: _i → ᵢ, ^2 → ²
    text = re.sub(r'_([a-zA-Z0-9])', _sub_single, text)
    text = re.sub(r'\^([a-zA-Z0-9])', _sup_single, text)
    text = re.sub(r'_([0-9])', lambda m: '\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089'[int(m.group(1))], text)
    text = re.sub(r'\^([0-9])', lambda m: '\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079'[int(m.group(1))], text)
    text = re.sub(r'\\;', '', text)
    text = re.sub(r'\\,', '', text)
    text = re.sub(r'\\!', '', text)
    text = re.sub(r'[{}]', '', text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════
# Paragraph helpers
# ═══════════════════════════════════════════════════════════════════
def _mk_para(doc, text, size=None, bold=None, italic=None, align="justify",
             before=0, after=0, line=1.0, first_indent=0, font_name=FONT):
    p = doc.add_paragraph()
    amap = {"center": WD_ALIGN_PARAGRAPH.CENTER, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "left": WD_ALIGN_PARAGRAPH.LEFT}
    p.alignment = amap.get(align, WD_ALIGN_PARAGRAPH.JUSTIFY)
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    if first_indent:
        pPr = p._element.get_or_add_pPr()
        ind = pPr.find(qn("w:ind")) or OxmlElement("w:ind")
        if ind not in list(pPr):
            pPr.append(ind)
        ind.set(qn("w:firstLine"), str(first_indent))
    run = p.add_run(text)
    if size:
        run.font.size = Pt(size)
    run.font.name = font_name
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    return p


def _heading1(doc, text):
    return _mk_para(doc, text.upper(), SZ_BODY, bold=True, align="justify", before=6, after=6, line=1.5)


def _heading2(doc, text):
    return _mk_para(doc, text, SZ_SUBHEADING, bold=True, italic=True, align="justify", before=4, after=4, line=1.5)


def _body(doc, text):
    return _mk_para(doc, text, SZ_BODY, align="justify", before=3, after=6, first_indent=720)


# ═══════════════════════════════════════════════════════════════════
# Tables
# ═══════════════════════════════════════════════════════════════════
def _set_table_borders(table):
    tblPr = table._element.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        table._element.insert(0, tblPr)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "bottom", "insideH"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0"); el.set(qn("w:color"), "000000")
        borders.append(el)
    for side in ("left", "right", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "none"); el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0"); el.set(qn("w:color"), "auto")
        borders.append(el)
    tblPr.append(borders)


def _add_table(doc, tbl_data):
    h = tbl_data.get("Headers", [])
    r = tbl_data.get("Rows", [])
    nc = len(h) if h else (len(r[0]) if r else 2)
    nr = len(r) + (1 if h else 0)
    t = doc.add_table(rows=nr, cols=nc)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t)
    if h:
        for j, hv in enumerate(h):
            if j < nc:
                c = t.rows[0].cells[j]; c.text = ""
                run = c.paragraphs[0].add_run(str(hv)); run.bold = True
                run.font.size = Pt(9); run.font.name = FONT
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for i, row in enumerate(r):
        for j, v in enumerate(row if isinstance(row, list) else []):
            if j < nc:
                c = t.rows[1+i].cells[j]; c.text = ""
                run = c.paragraphs[0].add_run(str(v))
                run.font.size = Pt(9); run.font.name = FONT
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    _mk_para(doc, " ", size=1)


def _tbl_cap(doc, no, title):
    p = _mk_para(doc, "", SZ_CAPTION, align="center", before=10, after=4)
    p.clear()
    r1 = p.add_run(f"Table {no}. "); r1.bold = True; r1.font.size = Pt(SZ_CAPTION); r1.font.name = FONT
    r2 = p.add_run(title); r2.font.size = Pt(SZ_CAPTION); r2.font.name = FONT


# ═══════════════════════════════════════════════════════════════════
# Figures
# ═══════════════════════════════════════════════════════════════════
def _add_fig_cap(doc, no, title):
    p = _mk_para(doc, "", SZ_CAPTION, align="center", before=3, after=6)
    p.clear()
    r1 = p.add_run(f"Figure {no}. "); r1.bold = True; r1.font.size = Pt(SZ_CAPTION); r1.font.name = FONT
    r2 = p.add_run(title); r2.font.size = Pt(SZ_CAPTION); r2.font.name = FONT


def _add_fig(doc, fig, cnt):
    no = str(fig.get("ImageNumber", cnt))
    title = _clean_latex(str(fig.get("Title", "")))
    prompt = _clean_latex(str(fig.get("Prompt", "")))
    ip = str(fig.get("Path", ""))
    actual = None
    if ip:
        cands = [Path(ip), BASE_DIR.parent / "image" / ip]
        stem = os.path.splitext(ip)[0]
        for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            cands.append(BASE_DIR.parent / "image" / f"{stem}{ext}")
        for c in cands:
            if c.exists():
                actual = c
                break
    p = _mk_para(doc, "", align="center", before=12, after=8)
    if actual:
        try:
            r = p.add_run(); r.add_picture(str(actual), width=Inches(3.2))
        except Exception:
            actual = None
    if not actual:
        r = p.add_run(f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt}]"); r.italic = True
        try:
            from docx.shared import RGBColor
            r.font.color.rgb = RGBColor(0xFF, 0, 0)
        except ImportError:
            pass
        r.font.size = Pt(SZ_CAPTION); r.font.name = FONT
    _add_fig_cap(doc, no, title)


# ═══════════════════════════════════════════════════════════════════
# Content rendering (shared between sections and subsections)
# ═══════════════════════════════════════════════════════════════════
def _render_content_items(doc, items, fig_cnt, tbl_cnt):
    """Render a list of content items. Returns (fig_cnt, tbl_cnt) updated."""
    if not isinstance(items, list):
        return fig_cnt, tbl_cnt
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("id", "")).lower()
        if kind in ("text", "paragraf", "paragraph"):
            txt = _clean_latex(str(item.get("text", item.get("Text", ""))).strip())
            if txt:
                _body(doc, txt)
        elif kind in ("gambar", "image", "figure"):
            fig_cnt += 1
            _add_fig(doc, item, fig_cnt)
        elif kind in ("tabel", "table"):
            tbl_cnt += 1
            tn = str(item.get("TableNumber", tbl_cnt))
            tt = _clean_latex(str(item.get("Title", "")))
            _tbl_cap(doc, tn, tt)
            _add_table(doc, item)
        elif kind in ("rumus", "equation", "formula", "persamaan"):
            lt = str(item.get("latex", item.get("Formula", ""))).strip()
            if lt:
                _mk_para(doc, lt, SZ_BODY, italic=True, align="center")
    return fig_cnt, tbl_cnt


# ═══════════════════════════════════════════════════════════════════
# Masthead table filling
# ═══════════════════════════════════════════════════════════════════
def _fill_masthead(doc, config):
    """Fill masthead table (Table 0) with actual abstract and keywords from JSON.

    Masthead structure:
      Row 0, Col 0: "Artikel Info" header (keep)
      Row 0, Col 1: "Abstract" heading + abstract text (Indonesian)
      Row 1, Col 0: "History" metadata + "Keywords: ..." + license
      Row 1, Col 1: "Abstract" heading + abstract text (English, or Indonesian if none)
    """
    if not doc.tables:
        return

    t = doc.tables[0]
    abstract = _clean_latex(str(config.get("abstract", "")).strip())
    abstract_en = _clean_latex(str(config.get("abstract_en", "")).strip())

    kw = config.get("keywords", [])
    if isinstance(kw, list):
        kws_text = "; ".join(str(k) for k in kw)
    else:
        kws_text = str(kw)
    kws_text = _clean_latex(kws_text)

    # Fill Row 0, Col 1: Indonesian abstract
    cell_01 = t.rows[0].cells[1]
    for pi, p in enumerate(cell_01.paragraphs):
        pt = p.text.strip()
        if pt.lower().startswith("abstract"):
            # Keep "Abstract" heading, but update abstract text in same or next paragraph
            if abstract:
                # Keep the heading run, clear the rest and add abstract
                runs = p.runs
                for r in runs:
                    if r.text.strip().lower() in ("abstract", "abstrak"):
                        # Keep heading run
                        continue
                    r.text = ""
                # Find or create a run for the abstract text
                # Use next paragraph for abstract text
                if pi + 1 < len(cell_01.paragraphs):
                    p_next = cell_01.paragraphs[pi + 1]
                else:
                    p_next = cell_01.add_paragraph()
                _clear_para(p_next)
                r = p_next.add_run(abstract)
                r.font.size = Pt(10)
                r.font.name = FONT
                r.italic = True
            break

    # Fill Row 1, Col 0: Keywords
    cell_10 = t.rows[1].cells[0]
    for p in cell_10.paragraphs:
        pt = p.text.strip()
        if pt.lower().startswith("keywords"):
            _clear_para(p)
            r1 = p.add_run("Keywords: ")
            r1.bold = True
            r1.font.size = Pt(10)
            r1.font.name = FONT
            r2 = p.add_run(kws_text if kws_text else "Keywords placeholder")
            r2.font.size = Pt(10)
            r2.font.name = FONT
            break

    # Fill Row 0, Col 1: English abstract (if available)
    if abstract_en:
        cell_11 = t.rows[1].cells[1]
        for pi, p in enumerate(cell_11.paragraphs):
            pt = p.text.strip()
            if pt.lower().startswith("abstract"):
                if pi + 1 < len(cell_11.paragraphs):
                    p_next = cell_11.paragraphs[pi + 1]
                else:
                    p_next = cell_11.add_paragraph()
                _clear_para(p_next)
                r = p_next.add_run(abstract_en)
                r.font.size = Pt(10)
                r.font.name = FONT
                r.italic = True
                break

    # If no English abstract but we have Indonesian, fill both with Indonesian
    if abstract and not abstract_en:
        cell_11 = t.rows[1].cells[1]
        for pi, p in enumerate(cell_11.paragraphs):
            pt = p.text.strip()
            if pt.lower().startswith("abstract"):
                if pi + 1 < len(cell_11.paragraphs):
                    p_next = cell_11.paragraphs[pi + 1]
                else:
                    p_next = cell_11.add_paragraph()
                _clear_para(p_next)
                r = p_next.add_run(abstract)
                r.font.size = Pt(10)
                r.font.name = FONT
                r.italic = True
                break


def _clear_para(p):
    """Remove all runs from a paragraph."""
    for r in list(p.runs):
        r._element.getparent().remove(r._element)


# ═══════════════════════════════════════════════════════════════════
# References — APA formatting from structured data
# ═══════════════════════════════════════════════════════════════════
def _format_structured_ref(ref: dict) -> str:
    """Format a structured reference dict as APA 7th text."""
    # Authors: "Smith, J., & Jones, T."
    authors = ref.get("authors", [])
    if isinstance(authors, list):
        if len(authors) == 1:
            author_str = authors[0]
        elif len(authors) <= 7:
            author_str = ", ".join(authors[:-1]) + ", & " + authors[-1]
        else:
            author_str = ", ".join(authors[:6]) + ", ... " + authors[-1]
    else:
        author_str = str(authors)

    year = ref.get("year", "")
    title = ref.get("title", "")
    journal = ref.get("journal", "")
    volume = ref.get("volume", "")
    issue = ref.get("issue", "")
    pages = ref.get("pages", "")
    doi = ref.get("doi", "")

    parts = [f"{author_str} ({year}).", f"{title}."]
    if journal:
        jpart = f"*{journal}*"
        if volume:
            jpart += f", *{volume}*"
            if issue:
                jpart += f"({issue})"
        if pages:
            jpart += f", {pages}"
        jpart += "."
        parts.append(jpart)
    if doi:
        parts.append(f"https://doi.org/{doi}")

    return " ".join(parts)


def _refs(doc, config):
    """Render references. Supports both {content: [{text}]} and [{authors, year, ...}] formats."""
    refs = config.get("references", [])
    rl = []

    if isinstance(refs, dict):
        # Old format: {"content": [{"text": "..."}, ...]}
        rl = refs.get("content", [])
        # Each item may be {"text": "..."} or a string
        result = []
        for ref in rl:
            if isinstance(ref, dict):
                result.append(ref.get("text", ""))
            else:
                result.append(str(ref))
        rl = result
    elif isinstance(refs, list) and refs:
        # Could be old list of {"text": "..."} or new structured format
        first = refs[0]
        if isinstance(first, dict) and "authors" in first:
            # Structured format — format as APA
            rl = []
            for ref in refs:
                try:
                    rl.append(_format_structured_ref(ref))
                except Exception:
                    rl.append(str(ref))
        elif isinstance(first, dict) and "text" in first:
            rl = [r.get("text", "") if isinstance(r, dict) else str(r) for r in refs]
        else:
            rl = [str(r) for r in refs]
    elif isinstance(refs, list):
        rl = [str(r) for r in refs]

    if not rl:
        return

    _heading1(doc, "Daftar Pustaka")
    for i, txt in enumerate(rl, 1):
        if not txt:
            continue
        txt = _clean_latex(str(txt))
        txt = re.sub(r'^\[\d+\]\s*', '', txt)
        p = _mk_para(doc, f"[{i}] {txt}", SZ_REF, align="justify", first_indent=-567)
        pPr = p._element.get_or_add_pPr()
        ind = pPr.find(qn("w:ind"))
        if ind is not None:
            ind.set(qn("w:left"), "567")


# ═══════════════════════════════════════════════════════════════════
# Section extraction — supports both formats
# ═══════════════════════════════════════════════════════════════════
def _extract_sections(config: dict) -> list:
    """Extract sections from config. Returns list of section dicts with title, content, subsections.
    
    Supports:
      1. "sections" array: [{"title": ..., "content": [...], "subsections": [...]}]
      2. "section1"..."sectionN" dict keys
    """
    if "sections" in config and isinstance(config["sections"], list):
        return config["sections"]

    # Legacy section1-sectionN format
    sections = []
    for i in range(1, 50):
        k = f"section{i}"
        if k not in config:
            continue
        sec = config[k]
        if not isinstance(sec, dict):
            continue
        # Convert to array format
        entry = {
            "title": sec.get("title", sec.get("Title", "")),
            "content": sec.get("content", sec.get("Content", [])),
            "subsections": _extract_subsections(sec),
        }
        sections.append(entry)
    return sections


def _extract_subsections(section: dict) -> list:
    """Extract subsections from a section dict (legacy subX keys)."""
    subs = section.get("subsections", [])
    if subs:
        return subs

    # Check for subX keys
    result = []
    for key in sorted(section.keys()):
        if re.match(r'^sub\d*[a-z]?$', key) or key.startswith("sub"):
            sub = section[key]
            if isinstance(sub, dict):
                result.append({
                    "title": sub.get("title", sub.get("Title", "")),
                    "content": sub.get("content", sub.get("Content", [])),
                })
    return result


# ═══════════════════════════════════════════════════════════════════
# Main builder
# ═══════════════════════════════════════════════════════════════════
def build_document(
    json_path: Path | str,
    output_path: Path | str | None = None,
    template_path: Path | str = TEMPLATE_PATH,
) -> Path:
    """Build PAUDIA DOCX from JSON config."""
    json_path = Path(json_path)
    template_path = Path(template_path)
    config = json.loads(json_path.read_text(encoding="utf-8"))

    if output_path:
        final = Path(output_path)
    else:
        final = json_path.parent / f"{json_path.stem}_PAUDIA.docx"

    # Copy template to preserve masthead and styles
    shutil.copy2(str(template_path), str(final))
    doc = Document(str(final))

    # Preserve masthead table (Table 0 with Artikel Info + Abstract)
    body = doc._element.body
    masthead = None
    for child in list(body):
        if child.tag == qn("w:tbl"):
            masthead = child
            break

    # Clear body except masthead and sectPr
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        if child is masthead:
            continue
        body.remove(child)

    # ── Title ──
    title = _clean_latex(str(config.get("title", "")).strip())
    if title:
        _mk_para(doc, title, SZ_TITLE, bold=True, align="center", before=6, after=24)

    # ── Authors ──
    authors = config.get("authors", [])
    if authors:
        names = [a["name"] if isinstance(a, dict) else str(a) for a in authors]
        _mk_para(doc, ", ".join(names), SZ_BODY, align="center")
        affs = set()
        for a in authors:
            if isinstance(a, dict) and a.get("affiliation"):
                affs.add(a["affiliation"])
        for aff in affs:
            _mk_para(doc, _clean_latex(aff), 9, align="center")
        # Add email if available
        emails = set()
        for a in authors:
            if isinstance(a, dict) and a.get("email"):
                emails.add(a["email"])
        if emails:
            _mk_para(doc, ", ".join(emails), 9, align="center")

    # ── Fill masthead with abstract + keywords ──
    _fill_masthead(doc, config)

    # ── Sections ──
    fig_cnt, tbl_cnt = 0, 0
    sections = _extract_sections(config)
    for sec in sections:
        st = _clean_latex(str(sec.get("title", "")).strip())
        if st:
            _heading1(doc, st)

        # Render section-level content
        fig_cnt, tbl_cnt = _render_content_items(doc, sec.get("content", []), fig_cnt, tbl_cnt)

        # Render subsections
        subs = sec.get("subsections", [])
        for sub in subs:
            sst = _clean_latex(str(sub.get("title", "")).strip())
            if sst:
                _heading2(doc, sst)
            fig_cnt, tbl_cnt = _render_content_items(doc, sub.get("content", []), fig_cnt, tbl_cnt)

    # ── References ──
    _refs(doc, config)

    doc.save(str(final))
    return final


if __name__ == "__main__":
    from _docx_base import run_generator
    run_generator(BASE_DIR, TEMPLATE_PATH, build_document)