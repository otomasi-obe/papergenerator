"""
PSTgen.py - Generator DOCX untuk jurnal Plant Science Today (PST).
Menggunakan dokumen asli PST.docx sebagai base template.
Data diambil dari paper_data (web) atau _template.json (standalone).
PST: single column, Vancouver style, Times New Roman 12pt.
"""
import json
import copy
import shutil
import re
import os
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm, Inches, Twips, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml, OxmlElement

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "PST.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "PST_output.docx"

CFG = {
    "font_body": "Times New Roman",
    "font_title": "Times New Roman",
    "font_heading": "Times New Roman",
    "size_body": 12,
    "size_title": 14,
    "size_heading1": 12,
    "size_heading2": 12,
    "size_caption": 10,
    "size_reference": 11,
    "columns": 1,
    "col_width_cm": 17.0,
    "first_line_indent_tw": 0,
    "table_borders": "three_line",
    "fig_prefix": "Fig.",
    "tbl_prefix": "Table",
    "section_heading_upper": True,
}


def load_json():
    with open(TEMPLATE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def set_run_font(run, font_name=None, size_pt=None, bold=None, italic=None, color=None):
    if font_name:
        run.font.name = font_name
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.insert(0, rFonts)
        rFonts.set(qn("w:ascii"), font_name)
        rFonts.set(qn("w:hAnsi"), font_name)
        rFonts.set(qn("w:cs"), font_name)
    if size_pt:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)


def set_para_spacing(para, before_pt=None, after_pt=None, line_tw=None, line_spacing=1.0):
    pf = para.paragraph_format
    if before_pt is not None:
        pf.space_before = Pt(before_pt)
    if after_pt is not None:
        pf.space_after = Pt(after_pt)
    if line_spacing is not None:
        pf.line_spacing = line_spacing
    if line_tw is not None:
        pPr = para._element.get_or_add_pPr()
        spacing = pPr.find(qn("w:spacing"))
        if spacing is None:
            spacing = OxmlElement("w:spacing")
            pPr.append(spacing)
        spacing.set(qn("w:line"), str(line_tw))
        spacing.set(qn("w:lineRule"), "auto")


def set_para_indent(para, first_line_tw=None, left_tw=None, hanging_tw=None):
    pPr = para._element.get_or_add_pPr()
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        pPr.append(ind)
    if first_line_tw is not None:
        ind.set(qn("w:firstLine"), str(first_line_tw))
    if left_tw is not None:
        ind.set(qn("w:left"), str(left_tw))
    if hanging_tw is not None:
        ind.set(qn("w:hanging"), str(hanging_tw))
        if ind.get(qn("w:firstLine")):
            del ind.attrib[qn("w:firstLine")]


def set_table_borders(table, style="three_line"):
    if style == "skip":
        return
    tblPr = table._element.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        table._element.insert(0, tblPr)
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is not None:
        tblPr.remove(borders)
    borders = OxmlElement("w:tblBorders")

    if style == "three_line":
        for side in ("top", "bottom", "insideH"):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")
            borders.append(el)
        for side in ("left", "right", "insideV"):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "none")
            el.set(qn("w:sz"), "0")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
            borders.append(el)
    elif style == "full":
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")
            borders.append(el)
    elif style == "partial":
        for side in ("top", "bottom", "insideH", "insideV"):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
            borders.append(el)
    elif style == "none":
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "none")
            el.set(qn("w:sz"), "0")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
            borders.append(el)

    tblPr.append(borders)


def clear_body(doc):
    """Clear body content but keep logo paragraphs (images in first 3 paragraphs)."""
    body = doc._element.body
    sectpr_paras = []
    logo_paras = []
    logo_tables = []

    # Identify logo paragraphs (images in first 3 paragraphs)
    para_count = 0
    for child in body:
        if child.tag == qn("w:p"):
            para_count += 1
            if para_count <= 3:
                has_image = False
                for run in child.findall(qn("w:r")):
                    if run.findall(qn("w:drawing")):
                        has_image = True
                        break
                if has_image:
                    logo_paras.append(child)

    # Identify logo tables
    table_count = 0
    for child in body:
        if child.tag == qn("w:tbl"):
            table_count += 1
            if table_count <= 3:
                has_drawing = len(child.findall(f".//{qn('w:drawing')}")) > 0
                if has_drawing:
                    logo_tables.append(child)

    # Clear body but preserve logos and section breaks
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        if child in logo_paras:
            continue
        if child in logo_tables:
            continue
        if child.tag == qn("w:p"):
            pPr = child.find(qn("w:pPr"))
            if pPr is not None and pPr.find(qn("w:sectPr")) is not None:
                for run in child.findall(qn("w:r")):
                    child.remove(run)
                sectpr_paras.append(child)
                continue
        body.remove(child)
    return sectpr_paras


def insert_column_break(doc, num_cols):
    """Insert continuous section break inline (attach to last paragraph)."""
    if CFG["columns"] <= 1:
        return
    body = doc._element.body
    final_sectpr = body.find(qn("w:sectPr"))

    last_para = None
    for child in reversed(list(body)):
        if child.tag == qn("w:sectPr"):
            continue
        if child.tag == qn("w:p"):
            pPr = child.find(qn("w:pPr"))
            if pPr is not None and pPr.find(qn("w:sectPr")) is not None:
                continue
            last_para = child
            break

    if last_para is None:
        return

    pPr = last_para.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        last_para.insert(0, pPr)

    sp = OxmlElement("w:sectPr")
    sec_type = OxmlElement("w:type")
    sec_type.set(qn("w:val"), "continuous")
    sp.append(sec_type)
    if final_sectpr is not None:
        for prop_tag in ("w:pgSz", "w:pgMar"):
            orig = final_sectpr.find(qn(prop_tag))
            if orig is not None:
                sp.append(copy.deepcopy(orig))
    cols_el = OxmlElement("w:cols")
    cols_el.set(qn("w:num"), str(num_cols))
    sp.append(cols_el)
    pPr.append(sp)


def remove_trailing_empty_sectpr_paras(doc):
    """Remove empty paragraphs with sectPr at the end of body."""
    body = doc._element.body
    trailing_empty_sectprs = []
    last_content_para = None

    for child in reversed(list(body)):
        if child.tag == qn("w:sectPr"):
            continue
        if child.tag == qn("w:p"):
            pPr = child.find(qn("w:pPr"))
            has_sectpr = pPr is not None and pPr.find(qn("w:sectPr")) is not None

            has_content = False
            for run in child.findall(qn("w:r")):
                t_elem = run.find(qn("w:t"))
                if t_elem is not None and t_elem.text and t_elem.text.strip():
                    has_content = True
                    break

            if has_content:
                last_content_para = child
                break
            elif has_sectpr:
                trailing_empty_sectprs.append(child)
        elif child.tag == qn("w:tbl"):
            break

    if last_content_para is not None and trailing_empty_sectprs:
        pPr = last_content_para.find(qn("w:pPr"))
        if pPr is None:
            pPr = OxmlElement("w:pPr")
            last_content_para.insert(0, pPr)

        first_trailing = trailing_empty_sectprs[-1]
        trailing_pPr = first_trailing.find(qn("w:pPr"))
        if trailing_pPr is not None:
            trailing_sectpr = trailing_pPr.find(qn("w:sectPr"))
            if trailing_sectpr is not None:
                existing_sectpr = pPr.find(qn("w:sectPr"))
                if existing_sectpr is not None:
                    pPr.remove(existing_sectpr)
                pPr.append(copy.deepcopy(trailing_sectpr))

        for child in trailing_empty_sectprs:
            body.remove(child)
        return len(trailing_empty_sectprs)
    return 0


def add_title(doc, data):
    """Add article title using PST Article title style."""
    title = str(data.get("title", "Paper Title")).strip()
    p = doc.add_paragraph()
    p.style = "Article title"
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para_spacing(p, before_pt=0, after_pt=6, line_spacing=1.5)
    run = p.add_run(title)
    set_run_font(run, CFG["font_title"], CFG["size_title"], bold=True)


def add_authors(doc, data):
    """Add author names and affiliations."""
    authors = data.get("authors", [])
    if not authors:
        return
    names = [a["name"] if isinstance(a, dict) else str(a) for a in authors]
    p = doc.add_paragraph()
    p.style = "Author names"
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para_spacing(p, before_pt=6, after_pt=3, line_spacing=1.5)
    run = p.add_run(", ".join(names))
    set_run_font(run, CFG["font_title"], CFG["size_body"])

    affiliations = set()
    for a in authors:
        if isinstance(a, dict) and a.get("affiliation"):
            affiliations.add(a["affiliation"])
    if affiliations:
        p2 = doc.add_paragraph()
        p2.style = "Affiliation"
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_para_spacing(p2, before_pt=0, after_pt=3, line_spacing=1.5)
        run2 = p2.add_run("; ".join(affiliations))
        set_run_font(run2, CFG["font_title"], CFG["size_body"] - 1, italic=True)

    emails = [a.get("email", "") for a in authors if isinstance(a, dict) and a.get("email")]
    if emails:
        p3 = doc.add_paragraph()
        p3.style = "Correspondence details"
        p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_para_spacing(p3, before_pt=0, after_pt=6, line_spacing=1.5)
        run3 = p3.add_run(", ".join(emails))
        set_run_font(run3, CFG["font_title"], CFG["size_body"] - 1, italic=True)


def add_abstract(doc, data):
    """Add abstract using PST Abstract style."""
    abstract = str(data.get("abstract", "")).strip()
    if not abstract:
        return
    # Label
    p_label = doc.add_paragraph()
    p_label.style = "Abstract"
    p_label.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_para_spacing(p_label, before_pt=6, after_pt=3, line_spacing=1.5)
    run_label = p_label.add_run("Abstract")
    set_run_font(run_label, CFG["font_body"], CFG["size_body"], bold=True)
    # Content
    p = doc.add_paragraph()
    p.style = "Abstract"
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_para_spacing(p, before_pt=0, after_pt=6, line_spacing=1.5)
    run = p.add_run(_clean_latex(abstract))
    set_run_font(run, CFG["font_body"], CFG["size_body"])


def add_keywords(doc, data):
    """Add keywords using PST Keywords style."""
    keywords = data.get("keywords", [])
    if not keywords:
        return
    if isinstance(keywords, list):
        kw_text = "; ".join(str(k) for k in keywords)
    else:
        kw_text = str(keywords)
    p = doc.add_paragraph()
    p.style = "Keywords"
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_para_spacing(p, before_pt=0, after_pt=6, line_spacing=1.5)
    run_label = p.add_run("Keywords: ")
    set_run_font(run_label, CFG["font_body"], CFG["size_body"], bold=True)
    run_kw = p.add_run(kw_text)
    set_run_font(run_kw, CFG["font_body"], CFG["size_body"])


def add_section_heading(doc, title):
    """Add section heading (bold, justified)."""
    p = doc.add_paragraph()
    p.style = "New paragraph"
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_para_spacing(p, before_pt=6, after_pt=3, line_spacing=1.5)
    display = title.upper() if CFG["section_heading_upper"] else title
    run = p.add_run(display)
    set_run_font(run, CFG["font_heading"], CFG["size_heading1"], bold=True)


def add_subsection_heading(doc, title):
    """Add subsection heading (bold)."""
    p = doc.add_paragraph()
    p.style = "Normal"
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_para_spacing(p, before_pt=3, after_pt=3, line_spacing=1.5)
    run = p.add_run(title)
    set_run_font(run, CFG["font_heading"], CFG["size_heading2"], bold=True)


def _clean_latex(text):
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
    """Strip inline LaTeX markers dari body text supaya tidak bocor ke output."""
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    text = re.sub(r'\\mathrm\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\hat\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\vec\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\overline\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\sqrt\{([^}]*)\}', r'sqrt(\1)', text)
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1/\2)', text)
    text = re.sub(r'\\left[(\[{]', '(', text)
    text = re.sub(r'\\right[)\]}]', ')', text)
    text = re.sub(r'\\begin\{cases\}', '', text)
    text = re.sub(r'\\end\{cases\}', '', text)
    text = re.sub(r'\\approx', chr(8776), text)
    text = re.sub(r'\\times', chr(215), text)
    text = re.sub(r'\\cdot', chr(183), text)
    text = re.sub(r'\\quad', ' ', text)
    text = re.sub(r'\\qquad', '  ', text)
    text = re.sub(r'\\infty', chr(8734), text)
    text = re.sub(r'\\circ', chr(176), text)
    text = re.sub(r'\\alpha', chr(945), text)
    text = re.sub(r'\\beta', chr(946), text)
    text = re.sub(r'\\gamma', chr(947), text)
    text = re.sub(r'\\theta', chr(952), text)
    text = re.sub(r'\\lambda', chr(955), text)
    text = re.sub(r'\\sigma', chr(963), text)
    text = re.sub(r'\\omega', chr(969), text)
    text = re.sub(r'\\pi', chr(960), text)
    text = re.sub(r'\\mu', chr(956), text)
    text = re.sub(r'\\Delta', chr(916), text)
    text = re.sub(r'\\partial', chr(8706), text)
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
    # Convert bare subscript/superscript to Unicode
    text = re.sub(r'_([0-9])', lambda m: '₀₁₂₃₄₅₆₇₈₉'[int(m.group(1))], text)
    text = re.sub(r'\^([0-9])', lambda m: '⁰¹²³⁴⁵⁶⁷⁸⁹'[int(m.group(1))], text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    text = re.sub(r'[{}]', '', text)
    # Strip any remaining stray $ (unmatched math delimiters)
    text = re.sub(r'\$', '', text)
    return text.strip()


def add_body_text(doc, text):
    """Add body paragraph using PST New paragraph style."""
    cleaned = _clean_latex(text)
    p = doc.add_paragraph()
    p.style = "New paragraph"
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_para_spacing(p, before_pt=0, after_pt=0, line_spacing=1.5)
    if CFG["first_line_indent_tw"] > 0:
        set_para_indent(p, first_line_tw=CFG["first_line_indent_tw"])
    run = p.add_run(cleaned)
    set_run_font(run, CFG["font_body"], CFG["size_body"])


def add_figure(doc, fig_data, fig_counter):
    """Add figure with caption."""
    fig_no = str(fig_data.get("ImageNumber", fig_counter)).strip()
    title = _clean_latex(str(fig_data.get("Title", f"Figure {fig_no}")).strip())
    prompt_hint = _clean_latex(str(fig_data.get("Prompt", "")).strip())

    image_path_str = str(fig_data.get("Path", "")).strip()
    image_url = str(fig_data.get("url", "")).strip()
    has_image = fig_data.get("hasImage", False)

    actual_image = None
    if image_path_str or image_url:
        candidates = []

        if image_path_str and os.path.isabs(image_path_str):
            candidates.append(Path(image_path_str))

        try:
            json_dir = Path(str(TEMPLATE_JSON)).parent
            paper_dir = json_dir.parent
            image_dir = paper_dir / "image"
            if image_dir.is_dir() and image_path_str:
                candidates.append(image_dir / image_path_str)
                stem = os.path.splitext(image_path_str)[0]
                if stem:
                    for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                        candidates.append(image_dir / f"{stem}{ext}")
        except Exception:
            pass

        if image_path_str:
            candidates.append(Path(image_path_str))

        for cand in candidates:
            if cand.exists() and cand.is_file():
                actual_image = cand
                break

    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para_spacing(p_img, before_pt=3, after_pt=3, line_spacing=1.5)

    if actual_image:
        try:
            run_img = p_img.add_run()
            # Dynamic image sizing based on column layout
            columns = CFG.get("columns", 1)
            col_w = CFG.get("col_width_cm", 16.0)
            if columns == 2:
                max_w_cm = (col_w / 2) * 0.5  # 2-col: 50% of each column
            else:
                max_w_cm = col_w * 0.5  # 1-col: 50% of text area
            run_img.add_picture(str(actual_image), width=Inches(max_w_cm / 2.54))
        except Exception:
            actual_image = None

    if not actual_image:
        dyn_prompt = prompt_hint or (
            f"Buatkan gambar/diagram/ilustrasi teknis yang merepresentasikan "
            f"'{title}'. Pastikan visualnya profesional dan cocok untuk jurnal akademik."
        )
        prompt_text = f"[PROMPT UNTUK AI GAMBAR: {title}. {dyn_prompt}]"
        run = p_img.add_run(prompt_text)
        set_run_font(run, CFG["font_body"], CFG["size_body"], italic=True, color=(0xFF, 0x00, 0x00))

    p_cap = doc.add_paragraph()
    p_cap.style = "Figure caption"
    p_cap.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_para_spacing(p_cap, before_pt=3, after_pt=6, line_spacing=1.5)
    run_label = p_cap.add_run(f"{CFG['fig_prefix']} {fig_no}. ")
    set_run_font(run_label, CFG["font_body"], CFG["size_caption"], bold=True)
    run_title = p_cap.add_run(title)
    set_run_font(run_title, CFG["font_body"], CFG["size_caption"])


def add_table_element(doc, tbl_data, tbl_counter):
    """Add table with title above."""
    tbl_no = str(tbl_data.get("TableNumber", tbl_counter)).strip()
    title = _clean_latex(str(tbl_data.get("Title", f"Table {tbl_no}")).strip())
    headers = tbl_data.get("Headers", [])
    rows = tbl_data.get("Rows", [])

    p_title = doc.add_paragraph()
    p_title.style = "Table title"
    p_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_para_spacing(p_title, before_pt=6, after_pt=3, line_spacing=1.5)
    run_label = p_title.add_run(f"{CFG['tbl_prefix']} {tbl_no}. ")
    set_run_font(run_label, CFG["font_body"], CFG["size_caption"], bold=True)
    run_title = p_title.add_run(title)
    set_run_font(run_title, CFG["font_body"], CFG["size_caption"])

    if not headers and not rows:
        if CFG["columns"] > 1:
            insert_column_break(doc, CFG["columns"])
        return

    n_cols = len(headers) if headers else (len(rows[0]) if rows else 2)
    n_rows = len(rows) + (1 if headers else 0)
    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, CFG["table_borders"])

    if headers:
        for j, h in enumerate(headers):
            if j < n_cols:
                cell = table.rows[0].cells[j]
                cell.text = ""
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(_clean_latex(str(h)))
                set_run_font(run, CFG["font_body"], CFG["size_caption"], bold=True)

    start_row = 1 if headers else 0
    for i, row_data in enumerate(rows):
        if not isinstance(row_data, list):
            continue
        row_idx = start_row + i
        if row_idx >= n_rows:
            break
        for j, val in enumerate(row_data):
            if j < n_cols:
                cell = table.rows[row_idx].cells[j]
                cell.text = ""
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(_clean_latex(str(val)))
                set_run_font(run, CFG["font_body"], CFG["size_caption"])

    # Spacer after table ensures text below has breathing room
    p_spacer = doc.add_paragraph()
    set_para_spacing(p_spacer, before_pt=6, after_pt=6)
    run_s = p_spacer.add_run(" ")
    set_run_font(run_s, CFG["font_body"], 1)


def add_formula(doc, formula_data):
    # OMML via shared utility
    import sys
    from pathlib import Path as _Path
    _jdir = _Path(__file__).resolve().parent
    if str(_jdir) not in sys.path:
        sys.path.insert(0, str(_jdir))
    from _formula_omml import add_omml_formula

    latex = str(formula_data.get("latex", formula_data.get("Formula", ""))).strip()
    number = str(formula_data.get("FormulaNumber", "")).strip()
    if not latex:
        return
        # Calculate max formula width (same rules as images)
    columns = CFG.get("columns", 1)
    col_w = CFG.get("col_width_cm", 16.0)
    max_fw = (col_w / 2) * 0.7 if columns == 2 else col_w * 0.7
    add_omml_formula(doc, latex, number, CFG, before_pt=4, after_pt=4,
                     alignment="center", font_body=CFG.get("font_body", "Times New Roman"),
                     size_body=CFG.get("size_body", 10), max_width_cm=max_fw)
def add_references(doc, data):
    """Add references section with Vancouver style."""
    refs_data = data.get("references", {})
    if isinstance(refs_data, dict):
        refs_list = refs_data.get("content", [])
    elif isinstance(refs_data, list):
        refs_list = refs_data
    else:
        refs_list = []

    if not refs_list:
        return

    # Heading
    add_section_heading(doc, "References")

    # Items
    for i, ref in enumerate(refs_list, 1):
        ref_text = str(ref.get("text", ref) if isinstance(ref, dict) else ref).strip()
        if not ref_text:
            continue
        # Strip existing bracket number prefix to avoid [1] [1] double numbering
        ref_text = re.sub(r'^\[\d+\]\s*', '', ref_text)
        p = doc.add_paragraph()
        p.style = "References"
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        set_para_spacing(p, before_pt=0, after_pt=0, line_spacing=1.5)
        set_para_indent(p, left_tw=360, hanging_tw=360)
        run = p.add_run(f"[{i}] {ref_text}")
        set_run_font(run, CFG["font_body"], CFG["size_reference"])


def process_content_items(doc, content_list, fig_counter, tbl_counter):
    """Process a list of content items (text, gambar, rumus, tabel)."""
    if not isinstance(content_list, list):
        return fig_counter, tbl_counter

    for item in content_list:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("id", "")).lower()

        if kind in ("text", "paragraf", "paragraph"):
            text = str(item.get("text", item.get("Text", ""))).strip()
            if text:
                add_body_text(doc, text)

        elif kind in ("gambar", "image", "figure"):
            fig_counter += 1
            add_figure(doc, item, fig_counter)

        elif kind in ("tabel", "table"):
            tbl_counter += 1
            add_table_element(doc, item, tbl_counter)

        elif kind in ("rumus", "equation", "formula", "persamaan"):
            add_formula(doc, item)

    return fig_counter, tbl_counter


def process_section(doc, section_data, fig_counter, tbl_counter):
    """Process a section (and its subsections) recursively."""
    if not isinstance(section_data, dict):
        return fig_counter, tbl_counter

    title = str(section_data.get("title", section_data.get("Title", ""))).strip()
    if title:
        add_section_heading(doc, title)

    content = section_data.get("content", section_data.get("Content", []))
    fig_counter, tbl_counter = process_content_items(doc, content, fig_counter, tbl_counter)

    for key in sorted(section_data.keys()):
        if key in ("title", "Title", "content", "Content", "id"):
            continue
        val = section_data[key]
        if isinstance(val, dict) and ("title" in val or "Title" in val or "content" in val or "Content" in val):
            sub_title = str(val.get("title", val.get("Title", ""))).strip()
            if sub_title:
                add_subsection_heading(doc, sub_title)
            sub_content = val.get("content", val.get("Content", []))
            fig_counter, tbl_counter = process_content_items(doc, sub_content, fig_counter, tbl_counter)

            for subkey in sorted(val.keys()):
                if subkey in ("title", "Title", "content", "Content", "id"):
                    continue
                subval = val[subkey]
                if isinstance(subval, dict) and ("title" in subval or "Title" in subval or "content" in subval or "Content" in subval):
                    ssub_title = str(subval.get("title", subval.get("Title", ""))).strip()
                    if ssub_title:
                        add_subsection_heading(doc, ssub_title)
                    ssub_content = subval.get("content", subval.get("Content", []))
                    fig_counter, tbl_counter = process_content_items(doc, ssub_content, fig_counter, tbl_counter)

    return fig_counter, tbl_counter


def generate(paper_data=None):
    """Generate PST-formatted DOCX from paper_data or _template.json."""
    if paper_data is None:
        data = load_json()
    else:
        data = paper_data

    # Copy template as base (preserves headers/footers/styles/numbering)
    shutil.copy2(str(TEMPLATE_DOCX), str(OUTPUT_DOCX))
    doc = Document(str(OUTPUT_DOCX))

    # Clear body but keep section break paragraphs in place
    sectpr_paras = clear_body(doc)
    body = doc._element.body

    # Find insertion point: before first sectPr paragraph (or final sectPr)
    if sectpr_paras:
        insert_before = sectpr_paras[0]
    else:
        insert_before = body.find(qn("w:sectPr"))

    # Generate title block
    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    # Move title block paragraphs to before first section break
    if insert_before is not None:
        new_paras = []
        for child in list(body):
            if child.tag == qn("w:sectPr"):
                continue
            if child.tag == qn("w:p"):
                pPr = child.find(qn("w:pPr"))
                if pPr is not None and pPr.find(qn("w:sectPr")) is not None:
                    continue
            if list(body).index(child) > list(body).index(insert_before):
                new_paras.append(child)
        for p in new_paras:
            body.remove(p)
            body.insert(list(body).index(insert_before), p)

    # Determine where body content goes
    if sectpr_paras:
        body_insert_before = sectpr_paras[-1]
    else:
        body_insert_before = body.find(qn("w:sectPr"))

    # Generate body content
    fig_counter = 0
    tbl_counter = 0
    for i in range(1, 30):
        key = f"section{i}"
        if key in data:
            fig_counter, tbl_counter = process_section(doc, data[key], fig_counter, tbl_counter)

    # References
    add_references(doc, data)

    # Move body content to before the target insertion point
    if body_insert_before is not None and sectpr_paras:
        new_elements = []
        for child in list(body):
            if child.tag == qn("w:sectPr"):
                continue
            if child.tag == qn("w:p"):
                pPr = child.find(qn("w:pPr"))
                if pPr is not None and pPr.find(qn("w:sectPr")) is not None:
                    continue
            try:
                if list(body).index(child) >= list(body).index(body_insert_before):
                    if child != body_insert_before:
                        new_elements.append(child)
            except ValueError:
                pass
        for el in new_elements:
            body.remove(el)
            body.insert(list(body).index(body_insert_before), el)

    # Remove trailing empty sectPr paragraphs
    remove_trailing_empty_sectpr_paras(doc)

    # Save
    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    print("[VERIFY] OK")
    return str(OUTPUT_DOCX)


if __name__ == "__main__":
    generate()
