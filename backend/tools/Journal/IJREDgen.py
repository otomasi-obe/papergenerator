"""
IJREDgen.py — Generator DOCX untuk IJRED journal.
Template pakai custom styles: icsmauthors, icsmaddresses, icsmheading1, icsmbodytext.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "IJRED.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "IJRED_output.docx"

STYLE_TITLE = "Title"
STYLE_AUTHORS = "icsmauthors"
STYLE_ABSTRACT = "icsmbodytext"
STYLE_KEYWORDS = "icsmbodytext"
STYLE_HEAD1 = "icsmheading1"
STYLE_HEAD2 = "icsmheading1"
STYLE_BODY = "icsmbodytext"
STYLE_TBL_CAPTION = "icsmbodytext"
STYLE_FIG_CAPTION = "icsmbodytext"
STYLE_REFS = "icsmbodytext"
STYLE_AFFIL = "icsmaddresses"


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

def _clean_latex(text):
    """Strip inline LaTeX markers dari text."""
    if not isinstance(text, str) or not text.strip():
        return text if isinstance(text, str) else ""
    import re as _re
    text = _re.sub(r'\$([^$]+)\$', r'\1', text)
    text = _re.sub(r'\\mathrm\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\mathbf\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\hat\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\vec\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\overline\{([^}]*)\}', r'\1', text)
    text = _re.sub(r'\\sqrt\{([^}]*)\}', r'sqrt(\1)', text)
    text = _re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1/\2)', text)
    text = _re.sub(r'\\left[(\[{]', '(', text)
    text = _re.sub(r'\\right[)\]]', ')', text)
    text = _re.sub(r'\\begin\{cases\}', '', text)
    text = _re.sub(r'\\end\{cases\}', '', text)
    text = _re.sub(r'\\approx', chr(8776), text)
    text = _re.sub(r'\\times', chr(215), text)
    text = _re.sub(r'\\cdot', chr(183), text)
    text = _re.sub(r'\\quad', ' ', text)
    text = _re.sub(r'\\qquad', '  ', text)
    text = _re.sub(r'\\infty', chr(8734), text)
    text = _re.sub(r'\\circ', chr(176), text)
    text = _re.sub(r'\\alpha', chr(945), text)
    text = _re.sub(r'\\beta', chr(946), text)
    text = _re.sub(r'\\gamma', chr(947), text)
    text = _re.sub(r'\\theta', chr(952), text)
    text = _re.sub(r'\\lambda', chr(955), text)
    text = _re.sub(r'\\sigma', chr(963), text)
    text = _re.sub(r'\\omega', chr(969), text)
    text = _re.sub(r'\\pi', chr(960), text)
    text = _re.sub(r'\\mu', chr(956), text)
    text = _re.sub(r'\\Delta', chr(916), text)
    text = _re.sub(r'\\partial', chr(8706), text)
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
    text = _re.sub(r'_\{([^}]+)\}', _sub_braced, text)
    text = _re.sub(r'\^\{([^}]+)\}', _sup_braced, text)
    # Single-char sub/superscript: _i → ᵢ, ^2 → ²
    text = _re.sub(r'_([a-zA-Z0-9])', _sub_single, text)
    text = _re.sub(r'\^([a-zA-Z0-9])', _sup_single, text)
    text = _re.sub(r'\\[a-zA-Z]+', '', text)
    text = _re.sub(r'[{}]', '', text)
    # Strip stray single-char artifacts at edges (LLM data noise)
    if text.startswith('b') and text.endswith(' b'):
        text = text[1:].rstrip()
        text = text[:-1].rstrip()
    elif text.startswith('i ') and text.endswith(' i'):
        text = text[2:]
        text = text[:-1].rstrip()
    _mc = set('ᵢⱼₖₗₘₙₒₚᵣₛₜₓᵧ₀₁₂₃₄₅₆₇₈₉ₐₑₕⁿˣʸ⁰¹²³⁴⁵⁶⁷⁸⁹θαπσβγδελμωφψρτηζξχν')
    if any(c in _mc for c in text):
        text = re.sub(r'^[ib](?=[A-Z(θαπσβγδελμω])', '', text)
        text = re.sub(r'^[ib]\s+(?=[θαπσβγδελμω])', '', text)
        text = re.sub(r'(?<=\))[ib]$', '', text)
    return text.strip()


def _postprocess_clean_latex(doc):
    """Walk all paragraphs and clean LaTeX from run text in-place."""
    import re as _re
    for para in doc.paragraphs:
        for run in para.runs:
            if run.text and _re.search(r'\\[a-zA-Z]|[$]', run.text):
                run.text = _clean_latex(run.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        if run.text and _re.search(r'\\[a-zA-Z]|[$]', run.text):
                            run.text = _clean_latex(run.text)
def _strip_latex(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"\$([^$]*)\$", r"\1", text)
    text = re.sub(r"\\(mathrm|mathbf|mathit|text|mathsf|mathtt)\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\{([^}]*)\}", r"√(\1)", text)
    text = re.sub(r"_\{([^}]*)\}", r"_\1", text)
    text = re.sub(r"\^\{([^}]*)\}", r"^\1", text)
    replacements = {
        r"\\approx": "≈",
        r"\\times": "×",
        r"\\cdot": "·",
        r"\\leq": "≤",
        r"\\geq": "≥",
        r"\\neq": "≠",
        r"\\infty": "∞",
        r"\\pm": "±",
        r"\\circ": "°",
        r"\\alpha": "α",
        r"\\beta": "β",
        r"\\gamma": "γ",
        r"\\theta": "θ",
        r"\\lambda": "λ",
        r"\\mu": "μ",
        r"\\pi": "π",
        r"\\sigma": "σ",
        r"\\omega": "ω",
        r"\\Delta": "Δ",
        r"\\Sigma": "Σ",
        r"\\sum": "Σ",
        r"\\int": "∫",
        r"\\partial": "∂",
        r"\\quad": "  ",
        r"\\qquad": "    ",
        r"\\dots": "...",
        r"\\ldots": "...",
        r"\\left": "",
        r"\\right": "",
        r"\\overline": "",
        r"\\underline": "",
        r"\\hat": "",
        r"\\vec": "",
        r"\\bar": "",
        r"\\dot": "",
        r"\\displaystyle": "",
        r"\\,": " ",
        r"\\begin\{[^}]*\}": "",
        r"\\end\{[^}]*\}": "",
    }
    for pat, repl in replacements.items():
        text = re.sub(pat, repl, text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"[{}]", "", text)
    return text


def load_json() -> dict:
    return json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))


def clear_body_keep_sectprs(doc):
    """Hapus body content tapi PRESERVE semua sectPr (inline + final).
    Gambar di 3 paragraf + 2 tabel pertama = logo jurnal (preserve).
    Gambar setelah itu = author photos (buang).
    """
    body = doc.element.body
    preserved_inline_sectprs = []
    para_count = 0
    tbl_count = 0
    for child in list(body):
        if child.tag == qn("w:p"):
            para_count += 1
            ppr = child.find(qn("w:pPr"))
            if ppr is not None:
                sectpr_inline = ppr.find(qn("w:sectPr"))
                if sectpr_inline is not None:
                    preserved_inline_sectprs.append(child)
                    for run in child.findall(qn("w:r")):
                        child.remove(run)
                    continue
            # Preserve logo drawings (blip only) di 3 paragraf pertama saja
            # Skip shape-only drawings (textbox, lines) — bukan logo gambar
            a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
            if para_count <= 3 and child.findall(f".//{{{a_ns}}}blip"):
                # Hapus text runs, keep drawing
                for run in child.findall(qn("w:r")):
                    if not run.findall(f".//{{{a_ns}}}blip"):
                        child.remove(run)
                continue
        elif child.tag == qn("w:tbl"):
            tbl_count += 1
            # Preserve logo tables di 2 tabel pertama saja
            if tbl_count <= 2 and child.findall(".//" + qn("w:drawing")):
                continue
            body.remove(child)
            continue
        elif child.tag == qn("w:sectPr"):
            continue
        body.remove(child)
    return preserved_inline_sectprs
def insert_before_sectpr(doc, sectpr_para):
    """Helper untuk insert paragraph baru SEBELUM paragraf yang punya sectPr inline."""
    new_p = OxmlElement("w:p")
    sectpr_para.addprevious(new_p)
    return new_p


def _set_para_style(paragraph, style_name: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    for old in ppr.findall(qn("w:pStyle")):
        ppr.remove(old)
    pstyle = OxmlElement("w:pStyle")
    pstyle.set(qn("w:val"), style_name)
    ppr.insert(0, pstyle)


def _set_tight_cell_spacing(para):
    """Set paragraph spacing to tight (0 before, 0 after, single line) for table cells."""
    from docx.oxml.ns import qn as _qn
    from docx.oxml import OxmlElement as _Oxml
    ppr = para._p.get_or_add_pPr()
    sp = ppr.find(_qn("w:spacing"))
    if sp is None:
        sp = _Oxml("w:spacing")
        ppr.append(sp)
    sp.set(_qn("w:before"), "0")
    sp.set(_qn("w:after"), "0")
    sp.set(_qn("w:line"), "240")
    sp.set(_qn("w:lineRule"), "auto")


def _add_run(
    paragraph,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    superscript: bool = False,
    font: str = None,
    size_pt: float = None,
    color_rgb: str = None,
):
    run = paragraph.add_run(text)
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    if superscript:
        run.font.superscript = True
    if font:
        run.font.name = font
        rPr = run._element.get_or_add_rPr()
    if color_rgb:
        rPr = run._element.get_or_add_rPr()
        from docx.shared import RGBColor
        run.font.color.rgb = RGBColor(*[int(color_rgb[i:i+2], 16) for i in (0, 2, 4)])
    if size_pt:
        run.font.size = Pt(size_pt)
    return run


def _embed_inline_sectpr(doc, num_cols: int, col_space_tw: int = 288):
    """Embed sectPr inline (untuk transition antar section layout)."""
    p = doc.add_paragraph()
    ppr = p._p.get_or_add_pPr()
    sectpr = OxmlElement("w:sectPr")
    pgsz = OxmlElement("w:pgSz")
    pgsz.set(qn("w:w"), "11907")
    pgsz.set(qn("w:h"), "16839")
    sectpr.append(pgsz)
    pgmar = OxmlElement("w:pgMar")
    pgmar.set(qn("w:top"), "1008")
    pgmar.set(qn("w:right"), "936")
    pgmar.set(qn("w:bottom"), "1008")
    pgmar.set(qn("w:left"), "936")
    pgmar.set(qn("w:header"), "187")
    pgmar.set(qn("w:footer"), "141")
    pgmar.set(qn("w:gutter"), "0")
    sectpr.append(pgmar)
    cols = OxmlElement("w:cols")
    if num_cols > 1:
        cols.set(qn("w:num"), str(num_cols))
        cols.set(qn("w:space"), str(col_space_tw))
    else:
        cols.set(qn("w:space"), "720")
    sectpr.append(cols)
    ppr.append(sectpr)


def add_title(doc, data):
    title_text = (data.get("title") or "Paper Title Goes Here").strip()
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_TITLE)
    _add_run(p, title_text)


def add_authors(doc, data):
    authors = data.get("authors") or [
        {"name": "Author Name", "affiliation": "Department, University"}
    ]

    affil_map = {}
    for author in authors:
        affil = (author.get("affiliation") or "").strip()
        if affil and affil not in affil_map:
            affil_map[affil] = len(affil_map) + 1

    p = doc.add_paragraph()
    _set_para_style(p, STYLE_AUTHORS)
    for i, author in enumerate(authors):
        if i > 0:
            connector = ", and " if i == len(authors) - 1 else ", "
            _add_run(p, connector)
        name = (author.get("name") or "Author Name").strip()
        _add_run(p, name)
        idx = affil_map.get((author.get("affiliation") or "").strip())
        if idx:
            _add_run(p, str(idx), superscript=True)


def add_abstract(doc, data):
    abstract = (data.get("abstract") or "Abstract text goes here.").strip()
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_ABSTRACT)
    _add_run(p, "Abstract—", bold=True)
    _add_run(p, _strip_latex(abstract))


def add_keywords(doc, data):
    kw = data.get("keywords") or []
    if not kw:
        return
    text = ", ".join(kw)
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_KEYWORDS)
    _add_run(p, "Index Terms—", bold=True, italic=True)
    _add_run(p, text, italic=True)


def add_section_heading(doc, title: str):
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_HEAD1)
    _add_run(p, title.upper(), bold=True, size_pt=9)


def add_subsection_heading(doc, title: str):
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_HEAD2)
    _add_run(p, title)


def add_body_text(doc, text: str):
    cleaned = _strip_latex(text)
    bold_auto = cleaned.startswith('• ') or 'Kontribusi spesifik' in cleaned
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_BODY)
    _add_run(p, cleaned, bold=bold_auto)


def _set_table_borders(table, pattern="full"):
    tbl = table._tbl
    tbl_pr = tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    tbl_borders = OxmlElement("w:tblBorders")
    if pattern == "full":
        visible = {"top", "left", "bottom", "right", "insideH", "insideV"}
    elif pattern == "horizontal":
        visible = {"top", "bottom", "insideH"}
    else:
        visible = set()
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        if side in visible:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
        else:
            el.set(qn("w:val"), "nil")
        tbl_borders.append(el)
    tbl_pr.append(tbl_borders)


def add_table(doc, table_data: dict):
    num = str(table_data.get("TableNumber") or "1")
    title = _clean_latex(_clean_latex((table_data.get("Title") or "Table title").strip()))
    headers = table_data.get("Headers") or ["Col1", "Col2"]
    rows = table_data.get("Rows") or [["Data", "Data"]]

    cap = doc.add_paragraph()
    _set_para_style(cap, STYLE_TBL_CAPTION)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(cap, f"TABLE {num}", bold=True)
    _add_run(cap, "\n" + title)

    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(table, pattern="horizontal")

    for col_idx, header in enumerate(headers):
        cell = table.rows[0].cells[col_idx]
        cell.text = ""
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_tight_cell_spacing(para)
        _add_run(para, str(header), bold=True)

    for row_idx, row_data in enumerate(rows, start=1):
        for col_idx, value in enumerate(row_data[: len(headers)]):
            cell = table.rows[row_idx].cells[col_idx]
            cell.text = ""
            para = cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _set_tight_cell_spacing(para)
            _add_run(para, str(value))


def add_figure(doc, fig_data: dict):
    image_number = str(fig_data.get("ImageNumber") or "1").strip()
    title = (fig_data.get("Title") or "").strip()
    prompt = (fig_data.get("Prompt") or "").strip()
    path_text = (fig_data.get("Path") or "").strip()

    image_path = None
    if path_text:
        path_text_norm = path_text.replace(" ", "")
        all_cands = []
        for _pt in (path_text, path_text_norm):
            _cand = Path(_pt)
            all_cands.append(_cand)
            if not _cand.is_absolute():
                all_cands.append(BASE / _pt)
        # Scan user/*/<paper_id>/image/
        try:
            _data = load_json()
            _pid = str(_data.get("paper_id") or _data.get("id") or "").strip()
            if not _pid and isinstance(_data.get("paper_data"), dict):
                _pid = str(_data["paper_data"].get("paper_id", "")).strip()
            if _pid:
                _udir = Path(__file__).resolve().parent.parent.parent / "user"
                if _udir.is_dir():
                    for _uname in _udir.iterdir():
                        _idir = _uname / _pid / "image"
                        if _idir.is_dir():
                            all_cands.extend([_idir / path_text, _idir / path_text_norm])
                            break
        except Exception:
            pass
        for _cand in all_cands:
            if _cand.is_file():
                image_path = _cand
                break

    if image_path:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(image_path), width=Cm(7.5))
    else:
        prompt_body = prompt if prompt else f"Figure {image_number}"
        if title:
            placeholder_text = f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt_body}]"
        else:
            placeholder_text = f"[PROMPT UNTUK AI GAMBAR: {prompt_body}]"
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p, placeholder_text, italic=True, color_rgb="FF0000")

    if title:
        cap = doc.add_paragraph()
        _set_para_style(cap, STYLE_FIG_CAPTION)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(cap, f"Fig. {image_number}. ", bold=True)
        _add_run(cap, title)


def add_formula(doc, formula_data: dict):
    num = str(formula_data.get("FormulaNumber") or "").strip()
    text = (formula_data.get("text") or formula_data.get("latex") or "E = mc^2").strip()
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_BODY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _omml_done = False
    try:
        from _math_omml import append_omml_math as _omml_fn
        _lx = (formula_data.get("latex") or "")
        _omml_done = bool(str(_lx or "").strip()) and _omml_fn(p, _lx)
    except Exception:
        _omml_done = False
    if not _omml_done:
        _add_run(p, _strip_latex(text), italic=True)
    if num:
        _add_run(p, f"\t({num})")


def process_content_item(doc, item: dict):
    if not isinstance(item, dict):
        return
    item_id = (item.get("id") or "").lower()
    if item_id in ("text", ""):
        text = (item.get("text") or "").strip()
        if text:
            add_body_text(doc, text)
    elif item_id in ("gambar", "image", "figure"):
        add_figure(doc, item)
    elif item_id in ("tabel", "table"):
        add_table(doc, item)
    elif item_id in ("rumus", "formula", "equation"):
        add_formula(doc, item)


def process_section(doc, section_data: dict, top_level: bool = True):
    if not isinstance(section_data, dict):
        return
    title = (section_data.get("title") or "").strip()
    if title:
        if top_level:
            add_section_heading(doc, title)
        else:
            add_subsection_heading(doc, title)

    content = section_data.get("content")
    if isinstance(content, list):
        for item in content:
            process_content_item(doc, item)

    for key in section_data:
        if key in ("title", "content"):
            continue
        if key.startswith("section"):
            process_section(doc, section_data[key], top_level=False)


def add_references(doc, data):
    refs = data.get("references") or {}
    if isinstance(refs, list):
        refs = {"title": "REFERENCES", "content": refs}
    title = (refs.get("title") or "REFERENCES").strip()
    items = [_format_reference(r) for r in (refs.get("content") or refs.get("items") or [])]
    items = [t for t in items if t] or ["[1] Author, Title, Journal, Year."]

    p_title = doc.add_paragraph()
    _set_para_style(p_title, STYLE_HEAD1)
    _add_run(p_title, title.upper())

    for ref in items:
        rp = doc.add_paragraph()
        _set_para_style(rp, STYLE_REFS)
        _add_run(rp, str(ref))


def generate():
    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    # Preserve inline sectPrs (yang punya headerReference/footerReference dari template)
    clear_body_keep_sectprs(doc)

    data = load_json()

    # Section 0 (sebelum sectPr inline #0): Title, Authors, Abstract, Keywords
    # Masthead inject
    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    # Body content (akan masuk antara preserved sectprs atau setelah-nya)
    for i in range(1, 30):
        key = f"section{i}"
        if key in data:
            process_section(doc, data[key], top_level=True)

    # References (1-col area atau setelah sectPr inline #1)
    add_references(doc, data)

    _postprocess_clean_latex(doc)
    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)



def build_pdf(json_path: Path, pdf_path: Path, template_path=None) -> Path:
    """Build a PDF for this journal template from a paper JSON.

    Writes a temporary .docx via generate(), then converts to .pdf
    via LibreOffice headless.  Final PDF is written to ``pdf_path``.
    """
    import sys as _sys
    import tempfile as _tf

    _json_path = Path(json_path)
    _pdf_path = Path(pdf_path)
    _pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp docx path
    with _tf.NamedTemporaryFile(suffix=".docx", delete=False) as _tmp:
        _tmp_docx = Path(_tmp.name)

    _mod = _sys.modules[__name__]
    _saved_in = getattr(_mod, "TEMPLATE_JSON", None)
    _saved_out = getattr(_mod, "OUTPUT_DOCX", None)

    try:
        setattr(_mod, "TEMPLATE_JSON", _json_path)
        setattr(_mod, "OUTPUT_DOCX", _tmp_docx)
        generate()
    finally:
        if _saved_in is not None:
            setattr(_mod, "TEMPLATE_JSON", _saved_in)
        if _saved_out is not None:
            setattr(_mod, "OUTPUT_DOCX", _saved_out)

    try:
        from ._render_pdf import convert_docx_to_pdf
        return convert_docx_to_pdf(_tmp_docx, _pdf_path)
    finally:
        _tmp_docx.unlink(missing_ok=True)

if __name__ == "__main__":
    generate()
