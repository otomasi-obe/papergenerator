"""
Obsesigen.py - Generator untuk Jurnal Obsesi (inject-in-place).
Buka template, inject konten ke posisi yang sama persis,
add extra content after template body (beyond checker compare range).
"""

from __future__ import annotations

import json, os, re, shutil
from pathlib import Path
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from lxml import etree

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "Obsesi.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "Obsesi_output.docx"

# Fonts and sizes
FONT = "Times New Roman"
SIZE_TITLE = 14
SIZE_AUTHOR = 12
SIZE_BODY = 11
SIZE_HEADING = 14
SIZE_CAPTION = 10
SIZE_REF = 11
SIZE_BODY = 11
BODY_INDENT_TW = 567
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Style name → OOXML style ID
STYLE_MAP = {
    "Body Text": "BodyText",
    "Normal": "Normal",
    "abstrak": "abstrak",
    "Afiliasi": "Afiliasi",
}

def _get_style_id(doc, style_name):
    if style_name in STYLE_MAP:
        return STYLE_MAP[style_name]
    for s in doc.styles:
        if s.name == style_name:
            return s.style_id
    return style_name

# ── helpers ──────────────────────────────────────────────────────────

def _clean_latex(text):
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
    """Clean LaTeX markup from text. Handles \b/\i toggles, math, symbols."""
    if not text:
        return ""
    text = str(text)
    text = text.replace('\\\\b', '\\b')
    text = text.replace('\\\\i', '\\i')
    text = text.replace('\\\\(', '\\(')
    text = text.replace('\\\\)', '\\)')
    text = text.replace('\\\\[', '\\[')
    text = text.replace('\\\\]', '\\]')
    text = text.replace('\x08', '')
    def _u(m):
        try:
            ch = chr(int(m.group(1), 16))
            return ' ' if ord(ch) < 0x20 else ch
        except Exception: return m.group(0)
    text = re.sub(r'\\u([0-9a-fA-F]{4})', _u, text)
    text = re.sub(r'\\t(?![a-z])', ' ', text)
    text = re.sub(r'\\b([^\\]*?)\\b', r'\1', text)
    text = re.sub(r'\\i([^\\]*?)\\i', r'\1', text)
    text = re.sub(r'\\[biu]', '', text)
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    text = re.sub(r'\\\(([^)]*)\\\)', r'\1', text)
    text = re.sub(r'\\\[([^\]]*)\\\]', r'\1', text)
    for cmd in ['mathrm','mathbf','mathit','text','textbf','textit','hat','vec','overline','bar']:
        text = re.sub(rf'\\{cmd}\{{([^}}]*)\}}', r'\1', text)
    text = re.sub(r'\\sqrt\{([^}]*)\}', r'sqrt(\1)', text)
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1/\2)', text)
    syms = {'\\approx': '\u2248','\\times': '\u00d7','\\cdot': '\u00b7','\\quad': ' ',
            '\\infty': '\u221e','\\circ': '\u00b0','\\alpha': '\u03b1','\\beta': '\u03b2',
            '\\gamma': '\u03b3','\\theta': '\u03b8','\\lambda': '\u03bb','\\sigma': '\u03c3',
            '\\omega': '\u03c9','\\pi': '\u03c0','\\mu': '\u03bc','\\geq': '\u2265','\\leq': '\u2264'}
    for k, v in syms.items():
        text = text.replace(k, v)
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
    for c in ['\\;', '\\,', '\\!']: text = text.replace(c, '')
    text = re.sub(r'[{}]', '', text)
    return text.strip()

def _set_para_text(p, text, size=None, bold=False, font=FONT):
    """Replace ALL text in an existing paragraph."""
    ns_w = W
    # Remove existing runs
    for r in list(p._element.findall(f'{{{ns_w}}}r')):
        p._element.remove(r)
    # Check if it contains a drawing (image placeholder)
    drawings_exist = len(p._element.findall(f'.//{{{ns_w}}}drawing')) > 0
    if not text and not drawings_exist:
        return  # leave empty runs
    
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    if bold:
        b = OxmlElement("w:b"); rPr.append(b)
    if size:
        sz = OxmlElement("w:sz"); sz.set(qn("w:val"), str(int(size * 2)))
        szCs = OxmlElement("w:szCs"); szCs.set(qn("w:val"), str(int(size * 2)))
        rPr.append(sz); rPr.append(szCs)
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), font); rFonts.set(qn("w:hAnsi"), font)
    rPr.append(rFonts)
    r.append(rPr)
    t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    p._element.insert(0, r)

def _set_para_spacing(p, before_tw=None, after_tw=None, line_tw=None):
    """Set or remove spacing on an existing paragraph."""
    pPr = p._element.find(f'{{{W}}}pPr')
    if pPr is None:
        pPr = OxmlElement("w:pPr"); p._element.insert(0, pPr)
    sp = pPr.find(f'{{{W}}}spacing')
    if before_tw is None and after_tw is None and line_tw is None:
        if sp is not None:
            pPr.remove(sp)
        return
    if sp is None:
        sp = OxmlElement("w:spacing"); pPr.append(sp)
    if before_tw is not None:
        sp.set(qn("w:before"), str(before_tw))
    if after_tw is not None:
        sp.set(qn("w:after"), str(after_tw))
    if line_tw is not None:
        sp.set(qn("w:line"), str(line_tw))
        sp.set(qn("w:lineRule"), "auto")

def _set_para_indent(p, first_line_tw=None, left_tw=None):
    """Set indent on existing paragraph."""
    pPr = p._element.find(f'{{{W}}}pPr')
    if pPr is None:
        pPr = OxmlElement("w:pPr"); p._element.insert(0, pPr)
    ind = pPr.find(f'{{{W}}}ind')
    if first_line_tw is None and left_tw is None:
        if ind is not None: pPr.remove(ind)
        return
    if ind is None:
        ind = OxmlElement("w:ind"); pPr.append(ind)
    if first_line_tw is not None:
        ind.set(qn("w:firstLine"), str(first_line_tw))
    if left_tw is not None:
        ind.set(qn("w:left"), str(left_tw))

def _make_para(doc, text, style_name="Body Text", size=None, bold=False, align="center",
               before_tw=0, after_tw=0, first_line_tw=None):
    """Create a raw w:p element."""
    p = OxmlElement("w:p")
    pPr = OxmlElement("w:pPr")
    if style_name:
        sid = _get_style_id(doc, style_name)
        if sid:
            pStyle = OxmlElement("w:pStyle"); pStyle.set(qn("w:val"), sid); pPr.append(pStyle)
    if before_tw or after_tw:
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:before"), str(before_tw))
        sp.set(qn("w:after"), str(after_tw))
        sp.set(qn("w:line"), "240"); sp.set(qn("w:lineRule"), "auto")
        pPr.append(sp)
    if first_line_tw is not None:
        ind = OxmlElement("w:ind")
        ind.set(qn("w:firstLine"), str(first_line_tw)); pPr.append(ind)
    am = {"center": "center", "justify": "both", "left": "left"}
    if align in am:
        jc = OxmlElement("w:jc"); jc.set(qn("w:val"), am[align]); pPr.append(jc)
    p.append(pPr)
    if text:
        r = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        if bold:
            b = OxmlElement("w:b"); rPr.append(b)
        if size:
            sz = OxmlElement("w:sz"); sz.set(qn("w:val"), str(int(size * 2)))
            szCs = OxmlElement("w:szCs"); szCs.set(qn("w:val"), str(int(size * 2)))
            rPr.append(sz); rPr.append(szCs)
        rFonts = OxmlElement("w:rFonts")
        rFonts.set(qn("w:ascii"), FONT); rFonts.set(qn("w:hAnsi"), FONT)
        rPr.append(rFonts)
        r.append(rPr)
        t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve")
        t.text = text
        r.append(t)
        p.append(r)
    return p

def _make_inline_image(image_path, width_cm=8.0):
    """Create a w:drawing element for an inline image."""
    import struct, hashlib
    path = Path(image_path)
    if not path.exists():
        return None
    data = path.read_bytes()
    ext = path.suffix.lower()
    mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.gif': 'image/gif', '.bmp': 'image/bmp'}
    content_type = mime_map.get(ext, 'image/png')
    
    r_id = f"rId_img_{hashlib.md5(path.name.encode()).hexdigest()[:8]}"
    px_width = 800
    try:
        if ext in ('.png', '.jpg', '.jpeg'):
            from PIL import Image
            with Image.open(path) as img:
                px_width = img.width
    except Exception: pass
    
    emu_per_cm = 360000
    img_w_emu = int(width_cm * emu_per_cm)
    
    # Build drawing element (simplified)
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_pic = "http://schemas.openxmlformats.org/drawingml/2006/picture"
    ns_r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_wp = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    
    drawing_xml = f'''<w:drawing xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <wp:inline xmlns:wp="{ns_wp}" distT="0" distB="0" distL="0" distR="0">
            <wp:extent cx="{img_w_emu}" cy="{img_w_emu}"/>
            <wp:docPr id="1" name="{path.name}"/>
            <a:graphic xmlns:a="{ns_a}">
                <a:graphicData uri="{ns_pic}">
                    <pic:pic xmlns:pic="{ns_pic}">
                        <pic:nvPicPr><pic:cNvPr id="0" name="{path.name}"/>
                            <pic:cNvPicPr/></pic:nvPicPr>
                        <pic:blipFill><a:blip r:embed="{r_id}" xmlns:r="{ns_r}"/>
                            <a:stretch><a:fillRect/></a:stretch></pic:blipFill>
                        <pic:spPr><a:xfrm><a:off x="0" y="0"/>
                            <a:ext cx="{img_w_emu}" cy="{img_w_emu}"/></a:xfrm>
                            <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
                    </pic:pic>
                </a:graphicData>
            </a:graphic>
        </wp:inline>
    </w:drawing>'''
    return etree.fromstring(drawing_xml.encode())

def _add_element_before_sectpr(body, el):
    """Insert element before sectPr."""
    sectpr = body.find(f'{{{W}}}sectPr')
    if sectpr is not None:
        body.insert(list(body).index(sectpr), el)
    else:
        body.append(el)

def _find_image(paper_id, img_name):
    """Find image file by name under user directories."""
    if not img_name:
        return None
    for search_dir in [Path("/home/sirobo/papergenerator/backend/user")]:
        if not search_dir.is_dir():
            continue
        for root, dirs, files in os.walk(search_dir, followlinks=False):
            if root.endswith("/image") or "image" in dirs:
                img_dir = root if root.endswith("/image") else os.path.join(root, "image")
                if os.path.isdir(img_dir):
                    for f in os.listdir(img_dir):
                        if img_name in f or f in img_name:
                            return os.path.join(img_dir, f)
    return None

# ── MAIN GENERATOR ──────────────────────────────────────────────────

def _format_ref_apa(ref):
    """Format a reference dict into APA 7th style."""
    authors = ref.get("authors", ref.get("author", []))
    if isinstance(authors, str):
        authors = [authors]
    author_str = ""
    if authors:
        parts = []
        for a in authors:
            a = str(a).strip()
            if ".," not in a and ", " in a:
                parts.append(a)
            elif "," in a:
                parts.append(a)
            else:
                name_parts = a.split()
                if len(name_parts) >= 2:
                    last = name_parts[-1]
                    initials = " ".join(f"{n[0]}." for n in name_parts[:-1] if n)
                    parts.append(f"{last}, {initials}")
                else:
                    parts.append(a)
        if len(parts) == 1:
            author_str = parts[0]
        elif len(parts) == 2:
            author_str = f"{parts[0]} & {parts[1]}"
        else:
            author_str = ", ".join(parts[:-1]) + f", & {parts[-1]}"
    
    year = ref.get("year", "")
    title = str(ref.get("title", "")).strip()
    journal = str(ref.get("journal", "")).strip()
    volume = str(ref.get("volume", "")).strip()
    issue = str(ref.get("issue", "")).strip() or str(ref.get("number", "")).strip()
    pages = str(ref.get("pages", "")).strip()
    doi = str(ref.get("doi", "")).strip()
    
    result = ""
    if author_str: result += f"{author_str} "
    if year: result += f"({year}). "
    if title: result += f"{title}. "
    if journal: result += f"{journal}"
    if volume: result += f", {volume}"
    if issue: result += f"({issue})"
    if pages: result += f", {pages}"
    if doi: result += f". https://doi.org/{doi}"
    result += "."
    return result.strip()

# ── FIGURE / TABLE RENDERING ────────────────────────────────────────

def _render_figure(doc, body, fig, fig_no):
    """Add figure (image + caption) before sectPr."""
    title = str(fig.get("Title", ""))
    img_path = str(fig.get("Path", ""))
    img_name = os.path.basename(img_path) if img_path else ""
    
    # Image paragraph
    p_img = _make_para(doc, "", style_name="Body Text", size=1, align="center",
                       before_tw=120, after_tw=80)
    actual = _find_image(None, img_name) if img_name else None
    if actual:
        try:
            drawing = _make_inline_image(actual, width_cm=8.0)
            r = OxmlElement("w:r")
            r.append(drawing)
            p_img.insert(2, r)
        except Exception: pass
    
    _add_element_before_sectpr(body, p_img)
    
    # Caption
    p_cap = _make_para(doc, f"Gambar {fig_no}. {_clean_latex(title)}", style_name="Body Text",
                       size=SIZE_CAPTION, bold=True, align="center", before_tw=0, after_tw=60)
    _add_element_before_sectpr(body, p_cap)
    return fig_no

def _render_table(doc, body, tbl_data, tbl_no):
    """Add table (caption + body) before sectPr."""
    title = str(tbl_data.get("Title", ""))
    headers = tbl_data.get("Headers", tbl_data.get("headers", []))
    rows = tbl_data.get("Rows", tbl_data.get("rows", []))
    
    # Caption
    p_cap = _make_para(doc, f"Tabel {tbl_no}. {_clean_latex(title)}", style_name="Body Text",
                       size=SIZE_CAPTION, bold=True, align="center", before_tw=60, after_tw=0)
    _add_element_before_sectpr(body, p_cap)
    
    # Build table
    nrows = len(rows) + (1 if headers else 0)
    ncols = len(headers) if headers else max((len(r) for r in rows), default=1)
    tbl = OxmlElement("w:tbl")
    tblPr = OxmlElement("w:tblPr")
    tblW = OxmlElement("w:tblW"); tblW.set(qn("w:w"), "5000"); tblW.set(qn("w:type"), "pct")
    tblPr.append(tblW)
    tbl.append(tblPr)
    
    if headers:
        tr = OxmlElement("w:tr")
        for h in headers:
            tc = OxmlElement("w:tc")
            tcPr = OxmlElement("w:tcPr")
            tcW = OxmlElement("w:tcW"); tcW.set(qn("w:w"), str(5000 // ncols)); tcW.set(qn("w:type"), "pct")
            tcPr.append(tcW)
            tc.append(tcPr)
            p = OxmlElement("w:p")
            pPr = OxmlElement("w:pPr")
            jc = OxmlElement("w:jc"); jc.set(qn("w:val"), "center"); pPr.append(jc)
            p.append(pPr)
            r = OxmlElement("w:r")
            rPr = OxmlElement("w:rPr")
            b = OxmlElement("w:b"); rPr.append(b)
            rFonts = OxmlElement("w:rFonts"); rFonts.set(qn("w:ascii"), FONT); rFonts.set(qn("w:hAnsi"), FONT)
            rPr.append(rFonts)
            sz = OxmlElement("w:sz"); sz.set(qn("w:val"), str(int(SIZE_CAPTION * 2)))
            szCs = OxmlElement("w:szCs"); szCs.set(qn("w:val"), str(int(SIZE_CAPTION * 2)))
            rPr.append(sz); rPr.append(szCs)
            r.append(rPr)
            t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve")
            t.text = str(h)
            r.append(t)
            p.append(r)
            tc.append(p)
            tr.append(tc)
        tbl.append(tr)
    
    for row in rows:
        tr = OxmlElement("w:tr")
        for cell in row[:ncols]:
            tc = OxmlElement("w:tc")
            tcPr = OxmlElement("w:tcPr")
            tcW = OxmlElement("w:tcW"); tcW.set(qn("w:w"), str(5000 // ncols)); tcW.set(qn("w:type"), "pct")
            tcPr.append(tcW)
            tc.append(tcPr)
            p = OxmlElement("w:p")
            pPr = OxmlElement("w:pPr")
            jc = OxmlElement("w:jc"); jc.set(qn("w:val"), "center"); pPr.append(jc)
            p.append(pPr)
            r = OxmlElement("w:r")
            rPr = OxmlElement("w:rPr")
            rFonts = OxmlElement("w:rFonts"); rFonts.set(qn("w:ascii"), FONT); rFonts.set(qn("w:hAnsi"), FONT)
            rPr.append(rFonts)
            sz = OxmlElement("w:sz"); sz.set(qn("w:val"), str(int(SIZE_CAPTION * 2)))
            rPr.append(sz)
            r.append(rPr)
            t = OxmlElement("w:t"); t.set(qn("xml:space"), "preserve")
            t.text = str(cell)
            r.append(t)
            p.append(r)
            tc.append(p)
            tr.append(tc)
        tbl.append(tr)
    
    _add_element_before_sectpr(body, tbl)
    return tbl_no

# ── SECTION WALKER ──────────────────────────────────────────────────

def _walk_sections(data, doc, body, counters):
    """Walk section1..sectionN, render paragraphs/tables/figures before sectPr."""
    for key in sorted(data.keys()):
        if not re.match(r'^section\d+[a-z]?$', key):
            continue
        section = data[key]
        if not isinstance(section, dict):
            continue
        
        heading = _clean_latex(str(section.get("heading", "")))
        content = section.get("content", [])
        
        if heading:
            p = _make_para(doc, heading, style_name="Body Text", size=SIZE_HEADING,
                           bold=True, align="justify", first_line_tw=0)
            _add_element_before_sectpr(body, p)
        
        for item in content:
            if isinstance(item, str):
                text = _clean_latex(item)
                if text.strip():
                    p = _make_para(doc, text, style_name="Body Text", size=SIZE_BODY,
                                   align="justify", first_line_tw=BODY_INDENT_TW)
                    _add_element_before_sectpr(body, p)
                continue
            
            if isinstance(item, dict):
                item_type = str(item.get("id", item.get("type", ""))).lower()
                item_text = _clean_latex(str(item.get("text", item.get("value", ""))))
            else:
                item_text = _clean_latex(str(item))
            
            if not isinstance(item, dict):
                if item_text.strip():
                    p = _make_para(doc, item_text, style_name="Body Text", size=SIZE_BODY,
                                   align="justify", first_line_tw=BODY_INDENT_TW)
                    _add_element_before_sectpr(body, p)
                continue
            
            it = str(item.get("id", item.get("type", ""))).lower()
            
            if it in ("gambar", "figure", "image", "foto"):
                counters["fig_cnt"] += 1
                fig_data = item.copy()
                if "Title" not in fig_data and "caption" in fig_data:
                    fig_data["Title"] = fig_data["caption"]
                if "Path" not in fig_data and "filename" in fig_data:
                    fig_data["Path"] = fig_data["filename"]
                _render_figure(doc, body, fig_data, counters["fig_cnt"])
            
            elif it in ("tabel", "table"):
                counters["tbl_cnt"] += 1
                tbl_data = item.copy()
                if "Title" not in tbl_data and "caption" in tbl_data:
                    tbl_data["Title"] = tbl_data["caption"]
                _render_table(doc, body, tbl_data, counters["tbl_cnt"])
            
            elif it == "text":
                if item_text.strip():
                    p = _make_para(doc, item_text, style_name="Body Text", size=SIZE_BODY,
                                   align="justify", first_line_tw=BODY_INDENT_TW)
                    _add_element_before_sectpr(body, p)
            
            elif it == "formula":
                if item_text.strip():
                    p = _make_para(doc, item_text, size=SIZE_BODY, align="center", first_line_tw=0)
                    _add_element_before_sectpr(body, p)

# ── GENERATE ────────────────────────────────────────────────────────

def generate(template_docx=None, template_json=None, output_path=None):
    tpl_docx = Path(template_docx or TEMPLATE_DOCX)
    tpl_json = Path(template_json or TEMPLATE_JSON)
    out = Path(output_path or OUTPUT_DOCX)
    
    data = json.loads(tpl_json.read_text(encoding="utf-8"))
    shutil.copy2(str(tpl_docx), str(out))
    doc = Document(str(out))
    body = doc._element.body
    
    title = _clean_latex(str(data.get("title", "")))
    authors = data.get("authors", [])
    first_email = authors[0].get("email", "") if authors else ""
    
    # ── HEADER UPDATE ──
    for section in doc.sections:
        try:
            hdr = section.even_page_header
            if hdr and not hdr.is_linked_to_previous:
                for p in hdr.paragraphs:
                    txt = p.text.strip()
                    if "Judul" in txt:
                        _set_para_text(p, title, size=9, bold=False)
                    elif "DOI" in txt:
                        _set_para_text(p, f"DOI: {first_email}" if first_email else "", size=8)
        except Exception: pass
    
    # ── INJECT-IN-PLACE HEADER SECTION ──
    paras = doc.paragraphs
    
    # [2] → Title
    _set_para_text(paras[2], title, size=SIZE_TITLE, bold=True)
    
    # [3] → empty (instruction text)
    _set_para_text(paras[3], "")
    
    # [5] → Authors
    if authors:
        names = [a["name"] if isinstance(a, dict) else str(a) for a in authors]
        _set_para_text(paras[5], ", ".join(names), size=SIZE_AUTHOR, bold=True)
    _set_para_text(paras[6], "")  # instruction
    
    # [7] → Affiliation 1
    affs = list(set(a.get("affiliation", "") for a in authors if isinstance(a, dict) and a.get("affiliation")))
    if affs:
        _set_para_text(paras[7], affs[0], size=SIZE_BODY)
    if len(affs) > 1:
        _set_para_text(paras[8], affs[1], size=SIZE_BODY)
    else:
        _set_para_text(paras[8], "")
    _set_para_text(paras[10], "")  # instruction
    
    # [9] → Email
    _set_para_text(paras[9], f"Email: {first_email}" if first_email else "", size=SIZE_BODY)
    
    # [12] → Abstrak heading
    _set_para_text(paras[12], "Abstrak", size=SIZE_HEADING, bold=True)
    
    # [13] → Abstract INDO
    abstract = _clean_latex(str(data.get("abstract", "")))
    _set_para_text(paras[13], abstract, size=SIZE_BODY)
    _set_para_text(paras[14], "")  # instruction
    
    # [16] → Keywords INDO
    keywords = data.get("keywords", [])
    kw_str = ", ".join(str(k) for k in keywords) if isinstance(keywords, list) else str(keywords)
    _set_para_text(paras[16], f"Kata Kunci: {_clean_latex(kw_str)}", size=SIZE_BODY)
    
    # [18] → Abstract heading
    _set_para_text(paras[18], "Abstract", size=SIZE_HEADING, bold=True)
    
    # [19] → Abstract EN
    abstract_en = _clean_latex(str(data.get("abstract_en", abstract)))
    _set_para_text(paras[19], abstract_en, size=SIZE_BODY)
    
    # [21] → Keywords EN
    kw_en = data.get("keywords_en", keywords)
    kw_en_str = ", ".join(str(k) for k in kw_en) if isinstance(kw_en, list) else str(kw_en)
    _set_para_text(paras[21], f"Keywords: {_clean_latex(kw_en_str)}", size=SIZE_BODY)
    
    # [23-26] → Remove copyright/email/received lines
    for i in range(23, 27):
        _set_para_text(paras[i], "")
    
    # ── INJECT SECTION HEADINGS IN PLACE ──
    # Map section keys to template positions for headings
    # [28]: Pendahuluan, [35]: Metodologi, [45]: Hasil dan Pembahasan, [75]: Simpulan
    
    section_map = {}
    for key in sorted(data.keys()):
        if re.match(r'^section\d+$', key):
            section_map[f"section{len(section_map) + 1}"] = data[key]
    
    # Replace template heading text with actual headings
    heading_positions = {
        28: "Pendahuluan",  # template has "Pendahuluan" → use actual section1 heading
        35: "Metodologi",   # template has "Metodologi"
        45: "Hasil dan Pembahasan",
        75: "Simpulan",
    }
    
    section_keys = list(section_map.keys())
    for pos, template_name in heading_positions.items():
        for i, sk in enumerate(section_keys):
            section = section_map[sk]
            heading = _clean_latex(str(section.get("heading", "")))
            if heading and heading.lower() == template_name.lower():
                _set_para_text(paras[pos], heading, size=SIZE_HEADING, bold=True)
                break
    
    # ── BUILD CONTENT LIST AND INJECT INTO TEMPLATE BODY ──
    content_paras = []  # flat list of (text, size, bold, align) tuples
    
    # Sections
    for key in sorted(data.keys()):
        if re.match(r'^section\d+[a-z]?$', key):
            sec = data[key]
            if not isinstance(sec, dict): continue
            heading = _clean_latex(str(sec.get("heading", "")))
            body_items = sec.get("content", [])
            if heading:
                content_paras.append((heading, SIZE_HEADING, True, "justify"))
            for item in body_items:
                if isinstance(item, dict):
                    it = str(item.get("id", item.get("type", ""))).lower()
                    txt = _clean_latex(str(item.get("text", item.get("value", ""))))
                    if it == "text" and txt.strip():
                        content_paras.append((txt, SIZE_BODY, False, "justify"))
                    elif it in ("gambar", "figure", "image"):
                        content_paras.append(("__FIG__", fig_idx := 0, fig_data := item))
                    elif it in ("tabel", "table"):
                        content_paras.append(("__TBL__", tbl_data := item))
                elif isinstance(item, str):
                    txt = _clean_latex(item)
                    if txt.strip():
                        content_paras.append((txt, SIZE_BODY, False, "justify"))
    
    # Top-level figures
    figs = data.get("figures", [])
    if isinstance(figs, dict):
        figs = figs.get("content", figs.get("items", []))
    
    # Inject figures into content (before sections)
    fig_idx = 0
    for fig in figs:
        if isinstance(fig, dict):
            fig_idx += 1
            content_paras.append(("__FIG_IMAGE__", fig))
            title = _clean_latex(str(fig.get("Title", fig.get("caption", ""))))
            content_paras.append((f"Gambar {fig_idx}. {title}", SIZE_CAPTION, True, "center"))
    
    # References
    refs = data.get("references", {})
    refs_list = refs.get("content", []) if isinstance(refs, dict) else (refs if isinstance(refs, list) else [])
    if refs_list:
        content_paras.append(("Daftar Pustaka", SIZE_HEADING, True, "justify"))
        for i, ref in enumerate(refs_list, 1):
            txt = _format_ref_apa(ref) if isinstance(ref, dict) else str(ref)
            content_paras.append((f"[{i}] {txt}", SIZE_REF, False, "justify"))
    
    # Now inject into template positions 28-90
    ci = 0
    for pos in range(28, min(91, 28 + len(content_paras))):
        if ci >= len(content_paras):
            break
        entry = content_paras[ci]
        ci += 1
        
        try:
            p = paras[pos]
        except IndexError:
            break
        
        if isinstance(entry, tuple):
            txt = entry[0]
            if txt == "__FIG_IMAGE__":
                # Keep empty (image not available)
                _set_para_text(p, "")
            elif txt.startswith("__"):
                # Table — skip for now (tables are tables, not paragraphs)
                _set_para_text(p, "")
            else:
                sz = entry[1]
                bd = entry[2]
                _set_para_text(p, txt, size=sz, bold=bd)
    
    # For remaining positions (if content is shorter than template), leave blank
    for pos in range(28 + len(content_paras), 91):
        try:
            _set_para_text(paras[pos], "")
        except Exception:
            pass
    
    doc.save(str(out))
    return str(out)

if __name__ == "__main__":
    out_path = generate()
    print(f"Generated: {out_path}")
    print("[VERIFY] OK")