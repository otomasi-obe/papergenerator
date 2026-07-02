"""
PGPAUDTrunojoyogen.py - Generator untuk Jurnal PG-PAUD Trunojoyo.
Template-based: preserves masthead paragraph + branding tables, rebuilds content.
TNR 12pt body, 16pt title, 10pt abstract. Supports sections + subsections.
"""
import json, copy, shutil, re, os
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "PGPAUDTrunojoyo.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "PGPAUDTrunojoyo_output.docx"

FONT = "Times New Roman"
SZ_TITLE = 16
SZ_BODY = 12
SZ_HEADING = 12
SZ_SUBHEADING = 12
SZ_ABSTRACT = 10
SZ_CAPTION = 11
SZ_REF = 12

DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

def _clean_latex(text):
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
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
    text = re.sub(r'_([0-9])', lambda m: '₀₁₂₃₄₅₆₇₈₉'[int(m.group(1))], text)
    text = re.sub(r'\^([0-9])', lambda m: '⁰¹²³⁴⁵⁶⁷⁸⁹'[int(m.group(1))], text)
    text = re.sub(r'\\;', '', text); text = re.sub(r'\\,', '', text); text = re.sub(r'\\!', '', text)
    text = re.sub(r'[{}]', '', text)
    return text.strip()

def _mk_para(doc, text, size=None, bold=None, italic=None, align="justify",
             before=0, after=0, first_indent=0, left=0):
    p = doc.add_paragraph()
    amap = {"center": WD_ALIGN_PARAGRAPH.CENTER, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "left": WD_ALIGN_PARAGRAPH.LEFT}
    p.alignment = amap.get(align, WD_ALIGN_PARAGRAPH.JUSTIFY)
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = 1.0
    pPr = p._element.get_or_add_pPr()
    ind = pPr.find(qn("w:ind")) or OxmlElement("w:ind")
    if ind not in list(pPr): pPr.append(ind)
    if first_indent: ind.set(qn("w:firstLine"), str(first_indent))
    if left: ind.set(qn("w:left"), str(left))
    run = p.add_run(text)
    if size: run.font.size = Pt(size)
    run.font.name = FONT
    if bold is not None: run.bold = bold
    if italic is not None: run.italic = italic
    return p

def _heading(doc, text):
    return _mk_para(doc, text.upper(), SZ_HEADING, bold=True, align="left", before=6, after=6, left=180)

def _subheading(doc, text):
    return _mk_para(doc, text, SZ_SUBHEADING, bold=True, align="left", before=4, after=4, left=180)

def _body(doc, text):
    return _mk_para(doc, text, SZ_BODY, align="justify", before=0, after=3, first_indent=284)

def _set_table_borders(table):
    tblPr = table._element.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr"); table._element.insert(0, tblPr)
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

def _add_table(doc, tbl):
    h = tbl.get("Headers", []); r = tbl.get("Rows", [])
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

def _fig_cap(doc, no, title):
    p = _mk_para(doc, "", SZ_CAPTION, align="center", before=3, after=6)
    p.clear()
    r1 = p.add_run(f"Gambar {no}. "); r1.font.size = Pt(SZ_CAPTION); r1.font.name = FONT
    r2 = p.add_run(title); r2.italic = True; r2.font.size = Pt(SZ_CAPTION); r2.font.name = FONT

def _add_fig(doc, fig, cnt):
    no = str(fig.get("ImageNumber", cnt))
    title = _clean_latex(str(fig.get("Title", "")))
    prompt = _clean_latex(str(fig.get("Prompt", "")))
    ip = str(fig.get("Path", ""))
    actual = None
    if ip:
        cands = [Path(ip), BASE.parent / "image" / ip]
        stem = os.path.splitext(ip)[0]
        for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            cands.append(BASE.parent / "image" / f"{stem}{ext}")
        for c in cands:
            if c.exists(): actual = c; break
    p = _mk_para(doc, "", align="center", before=12, after=8)
    if actual:
        try:
            r = p.add_run(); r.add_picture(str(actual), width=Inches(3.2))
        except Exception:
            actual = None
    if not actual:
        r = p.add_run(f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt}]")
        r.italic = True
        r.font.color.rgb = RGBColor(0xFF, 0, 0); r.font.size = Pt(SZ_CAPTION); r.font.name = FONT
    _fig_cap(doc, no, title)

def _tbl_cap(doc, no, title):
    p = _mk_para(doc, "", SZ_CAPTION, bold=True, align="center", before=10, after=4)
    p.clear()
    r1 = p.add_run(f"Tabel {no}. "); r1.bold = True; r1.font.size = Pt(SZ_CAPTION); r1.font.name = FONT
    r2 = p.add_run(title); r2.font.size = Pt(SZ_CAPTION); r2.font.name = FONT

def _format_ref(ref):
    """Build citation text from structured metadata."""
    if isinstance(ref, str):
        return ref
    if isinstance(ref, dict):
        # If it already has a 'text' key, use it
        if 'text' in ref:
            return str(ref['text'])
        authors = ref.get('authors', [])
        if isinstance(authors, list):
            authors_str = ', '.join(str(a) for a in authors)
        elif isinstance(authors, str):
            authors_str = authors
        else:
            authors_str = str(authors)

        year = str(ref.get('year', ''))
        title = str(ref.get('title', ''))
        journal = str(ref.get('journal', ''))
        vol = str(ref.get('volume', ''))
        issue = str(ref.get('issue', ''))
        pages = str(ref.get('pages', ''))
        doi = str(ref.get('doi', ''))

        parts = [authors_str]
        if year:
            parts.append(f"({year}).")
        if title:
            parts.append(f"{title}.")
        if journal:
            parts.append(f"*{journal}*")
            if vol:
                parts[-1] += f", {vol}"
            if issue:
                parts[-1] += f"({issue})"
        if pages:
            parts.append(f"{pages}.")
        if doi:
            parts.append(f"DOI: {doi}.")

        return ' '.join(parts)
    return str(ref)

def _refs(doc, data):
    refs = data.get("references", {})
    rl = refs.get("content") or refs.get("items") or [] if isinstance(refs, dict) else (refs if isinstance(refs, list) else [])
    if not rl: return
    _heading(doc, "Daftar Pustaka")
    for i, ref in enumerate(rl, 1):
        txt = _format_ref(ref)
        txt = re.sub(r'^\[\d+\]\s*', '', txt)
        p = _mk_para(doc, f"[{i}] {_clean_latex(txt)}", SZ_REF, align="justify",
                     first_indent=-284, left=284)

def _is_branding_element(child) -> bool:
    """Identify journal branding/masthead elements to preserve.
    Preserves: ARTICLE INFO masthead paragraph + table containing logo blips."""
    if child.tag == qn("w:p"):
        texts = child.findall(".//" + qn("w:t"))
        text = ' '.join(t.text or '' for t in texts)
        # The ARTICLE INFO masthead (first-page journal signature with logos)
        if "A R T I C L E" in text and "I N F O" in text:
            return True
    if child.tag == qn("w:tbl"):
        # Table with embedded images used as decorative/logo containers
        blips = child.findall(".//" + "{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
        if blips:
            return True
    return False

def _render_content_items(doc, items, counters):
    """Process a list of content items (dicts with id, text, etc.)."""
    for item in items:
        if not isinstance(item, dict): continue
        kind = str(item.get("id", "")).lower()
        if kind in ("text", "paragraf", "paragraph"):
            txt = _clean_latex(str(item.get("text", item.get("Text", ""))).strip())
            if txt: _body(doc, txt)
        elif kind in ("gambar", "image", "figure"):
            # Skip section-level gambar; rendered from top-level 'figures' key
            pass
        elif kind in ("tabel", "table"):
            counters["tbl"] += 1
            _tbl_cap(doc, str(item.get("TableNumber", counters["tbl"])),
                     _clean_latex(str(item.get("Title", ""))))
            _add_table(doc, item)
        elif kind in ("rumus", "equation", "formula", "persamaan"):
            lt = str(item.get("latex", item.get("Formula", ""))).strip()
            if lt: _mk_para(doc, lt, SZ_BODY, italic=True, align="center")

def _render_section_hierarchy(doc, data, counters):
    """Walk sections and nested subsections, rendering headings + content."""
    for i in range(1, 30):
        k = f"section{i}"
        if k not in data:
            continue
        sec = data[k]
        if not isinstance(sec, dict):
            continue

        # Section heading
        st = _clean_latex(str(sec.get("title", sec.get("Title", ""))).strip())
        if st:
            _heading(doc, st)

        # Section-level content
        ct = sec.get("content", sec.get("Content", []))
        if isinstance(ct, list):
            _render_content_items(doc, ct, counters)

        # Subsections: section2a, section2b, etc.
        sub_keys = sorted(
            [sk for sk in sec.keys() if re.match(r'^section\d+[a-z]$', sk)],
            key=lambda x: x
        )
        for sk in sub_keys:
            sub = sec[sk]
            if not isinstance(sub, dict):
                continue
            subst = _clean_latex(str(sub.get("title", sub.get("Title", ""))).strip())
            if subst:
                _subheading(doc, subst)
            sub_ct = sub.get("content", sub.get("Content", []))
            if isinstance(sub_ct, list):
                _render_content_items(doc, sub_ct, counters)

def generate():
    data = json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))
    shutil.copy2(str(TEMPLATE_DOCX), str(OUTPUT_DOCX))
    doc = Document(str(OUTPUT_DOCX))
    body = doc._element.body

    # ── Identify branding elements to preserve (masthead + logo tables) ──
    preserved = set()
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            preserved.add(child)
        elif _is_branding_element(child):
            preserved.add(child)

    # ── Clear body except preserved elements ──
    for child in list(body):
        if child in preserved:
            continue
        body.remove(child)

    # ── Title ──
    title = _clean_latex(str(data.get("title", "")).strip())
    _mk_para(doc, title, SZ_TITLE, bold=True, align="justify", before=0, after=6)

    # ── Authors ──
    authors = data.get("authors", [])
    if authors:
        names = [a["name"] if isinstance(a, dict) else str(a) for a in authors]
        _mk_para(doc, ", ".join(names), SZ_BODY, align="center", before=3, after=2)
        affs = []
        for a in authors:
            if isinstance(a, dict) and a.get("affiliation"):
                affs.append(a["affiliation"])
        for i, aff in enumerate(affs, 1):
            _mk_para(doc, f"{i}{_clean_latex(aff)}", 8, align="center")

    # ── Abstract Bahasa Indonesia ──
    abstract = _clean_latex(str(data.get("abstract", "")).strip())
    if abstract:
        _mk_para(doc, "A B S T R A K", 10, bold=True, align="center", before=6, after=3)
        _mk_para(doc, abstract, SZ_ABSTRACT, align="justify", before=0, after=6)
        kw = data.get("keywords", [])
        if kw:
            kws = ", ".join(str(k) for k in kw) if isinstance(kw, list) else str(kw)
            p = _mk_para(doc, "", SZ_ABSTRACT, align="justify", before=0, after=3)
            p.clear()
            r1 = p.add_run("Kata Kunci: "); r1.bold = True; r1.font.size = Pt(SZ_ABSTRACT); r1.font.name = FONT
            r2 = p.add_run(_clean_latex(kws)); r2.font.size = Pt(SZ_ABSTRACT); r2.font.name = FONT
        _mk_para(doc, " ", size=1)

    # ── Abstract English ──
    abstract_en = _clean_latex(str(data.get("abstract_en", "")).strip()) or abstract
    _mk_para(doc, "A B S T R A C T", 9, bold=True, align="center", before=3, after=3)
    _mk_para(doc, abstract_en, SZ_ABSTRACT, align="justify", before=0, after=3)

    # ── Sections + Subsections ──
    counters = {"fig": 0, "tbl": 0}
    _render_section_hierarchy(doc, data, counters)

    # ── Top-level figures (only those with actual image paths) ──
    figures = data.get("figures", [])
    for fig in figures:
        if not isinstance(fig, dict):
            continue
        ip = str(fig.get("Path", ""))
        if ip and ip.strip():
            counters["fig"] += 1
            _add_fig(doc, fig, counters["fig"])

    # ── References ──
    _refs(doc, data)

    # ── Ensure sectPr is last ──
    sectPr = body.find(qn("w:sectPr"))
    if sectPr is not None and sectPr.getnext() is not None:
        body.remove(sectPr)
        body.append(sectPr)

    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    print(f"[VERIFY] OK - {counters['fig']} figures, {counters['tbl']} tables")
    return str(OUTPUT_DOCX)

if __name__ == "__main__":
    generate()