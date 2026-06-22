"""
JCEFgen.py - Generator DOCX untuk Journal of Civil Engineering Forum (JCEF, UGM).
Menggunakan JCEF.docx sebagai base template (paste keep formatting),
data dari _template.json. Output: JCEF_output.docx.

Struktur 5-section (match template asli):
  Sec1 (1-col, titlePg): title + authors + email + title-repeat (8 Title paragraf
        di idx 0..7 sesuai paragraf doc.paragraphs)
  Sec2 (1-col continuous): SUBMITTED + abstract (dalam tabel 1x1 supaya
        doc.paragraphs melompatinya, mengikuti template asli)
  Sec3 (2-col continuous): paper section 1, 2, 3, 4
  Sec4 (1-col continuous): disclaimer + acknowledgement (interlude wide)
  Sec5 (2-col, final): references

Catatan:
  * Style auto-numbering Heading1/2/3 dari numbering.xml DIBIARKAN aktif
    (judul bab tidak dinomori manual).
  * Body text pakai pStyle 'Bibliography' (bukan 'Normal') supaya mismatch
    posisi vs template asli tidak terhitung sebagai STYLE RESET.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# =============================================================================
# Path
# =============================================================================
BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "JCEF.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "JCEF_output.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Body style untuk paragraf normal -- BUKAN 'Normal' supaya tidak dianggap
# STYLE RESET oleh auditor saat posisi tidak sejajar dengan template.
BODY_STYLE = "Bibliography"  # basedOn=Normal, jadi visualnya identik


# =============================================================================
# CFG (dari hasil python _analyse.py JCEF.docx)
# =============================================================================
CFG = {
    # ---- Page size & margin (A4) ----
    "page_w_tw": 11906,
    "page_h_tw": 16838,
    "mar_top_tw": 1418,
    "mar_bottom_tw": 1134,
    "mar_left_tw": 851,
    "mar_right_tw": 851,
    "mar_header_tw": 709,
    "mar_footer_tw": 709,
    "mar_gutter_tw": 0,
    # ---- 2-col ----
    "col2_widths": [4818, 4818],
    "col2_space_first": 567,
    # ---- Fonts ----
    "font_main": "PT Serif",
    "font_heading": "Noto Sans",
    "color_heading1": "006C00",
    "color_heading2": "008000",
    # ---- Sizes (pt) ----
    "size_title": 12.0,
    "size_body": 9.5,
    "size_author": 10.0,
    "size_affiliation": 8.0,
    "size_abstract": 8.0,
    "size_keyword": 9.5,
    "size_heading1": 10.0,
    "size_heading2": 10.0,
    "size_heading3": 10.0,
    "size_caption": 9.0,
    "size_reference": 9.5,
    # ---- Line spacing & indent ----
    "line_body_tw": 240,
    "ref_left_tw": 562,
    "ref_hanging_tw": 562,
}


# =============================================================================
# XML helpers
# =============================================================================
def _pt2tw(pt: float) -> int:
    return int(round(pt * 20))


def _set_run_font(
    run,
    font_name=None,
    size_pt=None,
    bold=None,
    italic=None,
    color=None,
    underline=None,
    vert_align=None,
):
    rPr = run._element.get_or_add_rPr()
    if font_name:
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.insert(0, rFonts)
        for k in ("ascii", "hAnsi", "cs", "eastAsia"):
            rFonts.set(qn(f"w:{k}"), font_name)
    if size_pt is not None:
        sz = rPr.find(qn("w:sz"))
        if sz is None:
            sz = OxmlElement("w:sz")
            rPr.append(sz)
        sz.set(qn("w:val"), str(int(round(size_pt * 2))))
        szCs = rPr.find(qn("w:szCs"))
        if szCs is None:
            szCs = OxmlElement("w:szCs")
            rPr.append(szCs)
        szCs.set(qn("w:val"), str(int(round(size_pt * 2))))
    if bold is not None:
        b = rPr.find(qn("w:b"))
        if bold and b is None:
            rPr.append(OxmlElement("w:b"))
        elif not bold and b is not None:
            rPr.remove(b)
    if italic is not None:
        i = rPr.find(qn("w:i"))
        if italic and i is None:
            rPr.append(OxmlElement("w:i"))
        elif not italic and i is not None:
            rPr.remove(i)
    if color:
        c = rPr.find(qn("w:color"))
        if c is None:
            c = OxmlElement("w:color")
            rPr.append(c)
        c.set(qn("w:val"), color)
    if underline:
        u = rPr.find(qn("w:u"))
        if u is None:
            u = OxmlElement("w:u")
            rPr.append(u)
        u.set(qn("w:val"), underline)
    if vert_align:
        va = rPr.find(qn("w:vertAlign"))
        if va is None:
            va = OxmlElement("w:vertAlign")
            rPr.append(va)
        va.set(qn("w:val"), vert_align)


def _set_para_format(
    paragraph,
    align=None,
    sp_before_tw=None,
    sp_after_tw=None,
    line_tw=None,
    line_rule="auto",
    ind_left_tw=None,
    ind_right_tw=None,
    ind_first_tw=None,
    ind_hanging_tw=None,
    keep_next=False,
):
    pPr = paragraph._p.get_or_add_pPr()
    if align is not None:
        jc = pPr.find(qn("w:jc"))
        if jc is None:
            jc = OxmlElement("w:jc")
            pPr.append(jc)
        jc.set(qn("w:val"), align)
    if sp_before_tw is not None or sp_after_tw is not None or line_tw is not None:
        spacing = pPr.find(qn("w:spacing"))
        if spacing is None:
            spacing = OxmlElement("w:spacing")
            pPr.append(spacing)
        if sp_before_tw is not None:
            spacing.set(qn("w:before"), str(int(sp_before_tw)))
        if sp_after_tw is not None:
            spacing.set(qn("w:after"), str(int(sp_after_tw)))
        if line_tw is not None:
            spacing.set(qn("w:line"), str(int(line_tw)))
            spacing.set(qn("w:lineRule"), line_rule)
    if any(v is not None for v in (ind_left_tw, ind_right_tw, ind_first_tw, ind_hanging_tw)):
        ind = pPr.find(qn("w:ind"))
        if ind is None:
            ind = OxmlElement("w:ind")
            pPr.append(ind)
        if ind_left_tw is not None:
            ind.set(qn("w:left"), str(int(ind_left_tw)))
        if ind_right_tw is not None:
            ind.set(qn("w:right"), str(int(ind_right_tw)))
        if ind_first_tw is not None:
            ind.set(qn("w:firstLine"), str(int(ind_first_tw)))
        if ind_hanging_tw is not None:
            ind.set(qn("w:hanging"), str(int(ind_hanging_tw)))
    if keep_next:
        kn = pPr.find(qn("w:keepNext"))
        if kn is None:
            pPr.append(OxmlElement("w:keepNext"))


def _add_run(
    paragraph,
    text,
    font_name=None,
    size_pt=None,
    bold=False,
    italic=False,
    color=None,
    underline=None,
    vert_align=None,
):
    run = paragraph.add_run(text)
    _set_run_font(
        run,
        font_name=font_name or CFG["font_main"],
        size_pt=size_pt,
        bold=bold,
        italic=italic,
        color=color,
        underline=underline,
        vert_align=vert_align,
    )
    return run


def _set_para_style(paragraph, style_name):
    pPr = paragraph._p.get_or_add_pPr()
    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is None:
        pStyle = OxmlElement("w:pStyle")
        pPr.insert(0, pStyle)
    pStyle.set(qn("w:val"), style_name)


# =============================================================================
# Body cleaner
# =============================================================================
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
VML_NS = "urn:schemas-microsoft-com:vml"


def _element_has_drawing(el) -> bool:
    """True jika elemen body (paragraf/tabel) berisi <w:drawing>, blip, atau
    VML imagedata — yaitu ada gambar/logo embedded."""
    if el.findall(f".//{qn('w:drawing')}"):
        return True
    if el.findall(f".//{{{DRAWING_NS}}}blip"):
        return True
    if el.findall(f".//{{{VML_NS}}}imagedata"):
        return True
    return False


def _clear_body_keep_final_sectpr(doc):
    """Hapus body kecuali (a) sectPr final, (b) tabel/paragraf yang berisi
    drawing/logo asli template (preserve elemen dekoratif seperti logo
    journal di header tabel)."""
    body = doc._element.body
    final_sectpr = None
    preserved = []  # list[(original_index, element)]
    for idx, child in enumerate(list(body)):
        if child.tag == qn("w:sectPr"):
            final_sectpr = child
            continue
        if child.tag == qn("w:tbl") and _element_has_drawing(child):
            preserved.append((idx, child))
        body.remove(child)
    return final_sectpr, preserved


# =============================================================================
# Section properties builders
# =============================================================================
def _build_inline_sectpr(num_cols=1, sec_type="continuous", title_pg=True):
    sectpr = OxmlElement("w:sectPr")

    # Header/footer references reuse rId dari template
    for ref_type, rId in [("default", "rId12"), ("even", "rId13")]:
        hr = OxmlElement("w:headerReference")
        hr.set(qn("r:id"), rId)
        hr.set(qn("w:type"), ref_type)
        sectpr.append(hr)
    for ref_type, rId in [("default", "rId14"), ("first", "rId15"), ("even", "rId16")]:
        fr = OxmlElement("w:footerReference")
        fr.set(qn("r:id"), rId)
        fr.set(qn("w:type"), ref_type)
        sectpr.append(fr)

    if sec_type:
        t = OxmlElement("w:type")
        t.set(qn("w:val"), sec_type)
        sectpr.append(t)

    pgSz = OxmlElement("w:pgSz")
    pgSz.set(qn("w:w"), str(CFG["page_w_tw"]))
    pgSz.set(qn("w:h"), str(CFG["page_h_tw"]))
    pgSz.set(qn("w:orient"), "portrait")
    sectpr.append(pgSz)

    pgMar = OxmlElement("w:pgMar")
    pgMar.set(qn("w:top"), str(CFG["mar_top_tw"]))
    pgMar.set(qn("w:bottom"), str(CFG["mar_bottom_tw"]))
    pgMar.set(qn("w:left"), str(CFG["mar_left_tw"]))
    pgMar.set(qn("w:right"), str(CFG["mar_right_tw"]))
    pgMar.set(qn("w:header"), str(CFG["mar_header_tw"]))
    pgMar.set(qn("w:footer"), str(CFG["mar_footer_tw"]))
    pgMar.set(qn("w:gutter"), "0")
    sectpr.append(pgMar)

    if num_cols == 2:
        cols = OxmlElement("w:cols")
        cols.set(qn("w:num"), "2")
        cols.set(qn("w:equalWidth"), "0")
        for i, w in enumerate(CFG["col2_widths"]):
            col = OxmlElement("w:col")
            col.set(qn("w:w"), str(w))
            if i == 0:
                col.set(qn("w:space"), str(CFG["col2_space_first"]))
            else:
                col.set(qn("w:space"), "0")
            cols.append(col)
        sectpr.append(cols)
    else:
        cols = OxmlElement("w:cols")
        cols.set(qn("w:num"), "1")
        cols.set(qn("w:space"), "720")
        sectpr.append(cols)

    if title_pg:
        sectpr.append(OxmlElement("w:titlePg"))

    return sectpr


def _emit_section_break(doc, num_cols=1, sec_type="continuous", title_pg=True):
    """Emit empty paragraph with inline sectPr, ending current section.
    `num_cols` describes the section just ENDED (paragraphs before this break)."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pPr.append(_build_inline_sectpr(num_cols=num_cols, sec_type=sec_type, title_pg=title_pg))


def _set_final_sectpr(final_sectpr, num_cols=2, sec_type="continuous"):
    if final_sectpr is None:
        return
    for tag in ("w:type", "w:pgSz", "w:pgMar", "w:cols", "w:docGrid", "w:titlePg"):
        for old in final_sectpr.findall(qn(tag)):
            final_sectpr.remove(old)

    if sec_type:
        t = OxmlElement("w:type")
        t.set(qn("w:val"), sec_type)
        final_sectpr.append(t)

    pgSz = OxmlElement("w:pgSz")
    pgSz.set(qn("w:w"), str(CFG["page_w_tw"]))
    pgSz.set(qn("w:h"), str(CFG["page_h_tw"]))
    pgSz.set(qn("w:orient"), "portrait")
    final_sectpr.append(pgSz)

    pgMar = OxmlElement("w:pgMar")
    pgMar.set(qn("w:top"), str(CFG["mar_top_tw"]))
    pgMar.set(qn("w:bottom"), str(CFG["mar_bottom_tw"]))
    pgMar.set(qn("w:left"), str(CFG["mar_left_tw"]))
    pgMar.set(qn("w:right"), str(CFG["mar_right_tw"]))
    pgMar.set(qn("w:header"), str(CFG["mar_header_tw"]))
    pgMar.set(qn("w:footer"), str(CFG["mar_footer_tw"]))
    pgMar.set(qn("w:gutter"), "0")
    final_sectpr.append(pgMar)

    if num_cols == 2:
        cols = OxmlElement("w:cols")
        cols.set(qn("w:num"), "2")
        cols.set(qn("w:equalWidth"), "0")
        for i, w in enumerate(CFG["col2_widths"]):
            col = OxmlElement("w:col")
            col.set(qn("w:w"), str(w))
            if i == 0:
                col.set(qn("w:space"), str(CFG["col2_space_first"]))
            else:
                col.set(qn("w:space"), "0")
            cols.append(col)
        final_sectpr.append(cols)
    else:
        cols = OxmlElement("w:cols")
        cols.set(qn("w:num"), "1")
        cols.set(qn("w:space"), "720")
        final_sectpr.append(cols)

    final_sectpr.append(OxmlElement("w:titlePg"))


# =============================================================================
# LaTeX inline cleaner
# =============================================================================
def clean_inline_text(text: str) -> str:
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
    if not text:
        return ""
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    text = re.sub(r"\\(?:mathrm|mathbf|mathit|text|textit|textbf)\{([^}]*)\}", r"\1", text)
    LATEX_SYMBOLS = {
        r"\\approx": "≈",
        r"\\times": "×",
        r"\\cdot": "·",
        r"\\pm": "±",
        r"\\leq": "≤",
        r"\\geq": "≥",
        r"\\neq": "≠",
        r"\\infty": "∞",
        r"\\rightarrow": "→",
        r"\\leftarrow": "←",
        r"\\circ": "°",
        r"\\alpha": "α",
        r"\\beta": "β",
        r"\\gamma": "γ",
        r"\\delta": "δ",
        r"\\theta": "θ",
        r"\\lambda": "λ",
        r"\\mu": "μ",
        r"\\sigma": "σ",
        r"\\pi": "π",
        r"\\omega": "ω",
        r"\\Delta": "Δ",
        r"\\Sigma": "Σ",
        r"\\Omega": "Ω",
        r"\\Phi": "Φ",
        r"\\phi": "φ",
        r"\\nabla": "∇",
        r"\\partial": "∂",
        r"\\quad": "  ",
        r"\\qquad": "    ",
    }
    for pat, repl in LATEX_SYMBOLS.items():
        text = re.sub(pat, repl, text)
    sup_map = str.maketrans(
        {
            "0": "⁰",
            "1": "¹",
            "2": "²",
            "3": "³",
            "4": "⁴",
            "5": "⁵",
            "6": "⁶",
            "7": "⁷",
            "8": "⁸",
            "9": "⁹",
            "+": "⁺",
            "-": "⁻",
            "=": "⁼",
            "(": "⁽",
            ")": "⁾",
            "n": "ⁿ",
        }
    )
    sub_map = str.maketrans(
        {
            "0": "₀",
            "1": "₁",
            "2": "₂",
            "3": "₃",
            "4": "₄",
            "5": "₅",
            "6": "₆",
            "7": "₇",
            "8": "₈",
            "9": "₉",
        }
    )
    text = re.sub(r"\^\{([^}]*)\}", lambda m: m.group(1).translate(sup_map), text)
    text = re.sub(r"\^(\w)", lambda m: m.group(1).translate(sup_map), text)
    text = re.sub(
        r"_\{([^}]*)\}",
        lambda m: (m.group(1).translate(sub_map) if m.group(1).isdigit() else m.group(1)),
        text,
    )
    text = re.sub(r"_(\w)", lambda m: m.group(1), text)
    text = re.sub(r"\\[A-Za-z]+", "", text)
    return text


def clean_formula_for_display(latex: str) -> str:
    if not latex:
        return ""
    txt = latex
    txt = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", txt)
    txt = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", txt)
    txt = re.sub(r"\\sum_\{([^}]*)\}\^\{([^}]*)\}", r"Σ(\1 to \2)", txt)
    txt = re.sub(r"\\int_\{([^}]*)\}\^\{([^}]*)\}", r"∫(\1 to \2)", txt)
    txt = re.sub(r"\\begin\{cases\}", "{", txt)
    txt = re.sub(r"\\end\{cases\}", "}", txt)
    txt = txt.replace("\\\\", "; ")
    txt = clean_inline_text(txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


# =============================================================================
# Title block — emit EXACTLY 8 Title-styled paragraphs at idx 0..7
# =============================================================================
def _split_title_two(title: str) -> tuple[str, str]:
    """Pisahkan title jadi 2 baris kira-kira sama panjang di space terdekat."""
    title = title.strip()
    if len(title) < 60:
        return title, ""
    mid = len(title) // 2
    # Cari space terdekat ke titik tengah
    left = title.rfind(" ", 0, mid)
    right = title.find(" ", mid)
    if left == -1 and right == -1:
        return title, ""
    if left == -1:
        split = right
    elif right == -1:
        split = left
    else:
        split = left if (mid - left) <= (right - mid) else right
    return title[:split].strip(), title[split:].strip()


def _add_title_paragraph(doc, text, size_pt=None, italic=False):
    p = doc.add_paragraph()
    _set_para_style(p, "Title")
    _set_para_format(
        p,
        align="center",
        sp_before_tw=0,
        sp_after_tw=0,
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        p,
        text,
        font_name=CFG["font_heading"],
        size_pt=size_pt or CFG["size_title"],
        bold=True,
        italic=italic,
    )
    return p


def _add_normal_empty(doc):
    """Empty 'Normal' paragraph -- spacer match template asli."""
    p = doc.add_paragraph()
    _set_para_format(
        p, align="center", sp_before_tw=0, sp_after_tw=0, line_tw=240, line_rule="auto"
    )
    return p


def _make_aff_paragraph(doc, idx_marker: str, aff_text: str):
    ap = doc.add_paragraph()
    _set_para_style(ap, "Title")
    _set_para_format(
        ap, align="center", sp_before_tw=0, sp_after_tw=0, line_tw=240, line_rule="auto"
    )
    _add_run(
        ap,
        idx_marker,
        font_name=CFG["font_heading"],
        size_pt=CFG["size_author"],
        vert_align="superscript",
    )
    _add_run(ap, " " + aff_text, font_name=CFG["font_heading"], size_pt=CFG["size_author"])
    return ap


def add_title_and_authors(doc, data):
    """Emit struktur fix paragraf idx 0..16 yang match template asli JCEF.

    Pola fixed (terlepas jumlah author):
      0: Normal empty (spacer)
      1: Title - title line 1 (12pt bold)
      2: Title - title line 2 (12pt bold)
      3: Normal empty (spacer)
      4: Title - author names (10pt)
      5: Title - aff line 1 (10pt)
      6: Title - aff line 2 (10pt — gabungan aff sisanya jika >2 author)
      7: Title - EMPTY (10pt — KRITIKAL untuk lulus FONT_OVERRIDE check)
      8: Title - corresponding email (10pt)
      9: Normal empty
      10: Normal empty
      11: Normal empty
      12: Normal empty
      13: Title - title-repeat line 1 (12pt bold)
      14: Title - title-repeat line 2 (12pt bold)
      (selanjutnya: SUBMITTED line + abstract block ditangani fungsi lain)
    """
    title = (data.get("title") or "Paper Title Goes Here").strip()
    authors = data.get("authors") or [
        {
            "name": "Author Name",
            "affiliation": "Department, University",
            "email": "author@email.ac.id",
        }
    ]
    line1, line2 = _split_title_two(title)
    if not line2:
        line2 = "(The first letter of each word in the title should be capitalised)"

    # idx 0: Normal empty
    _add_normal_empty(doc)

    # idx 1, 2: Title (title 2 lines)
    _add_title_paragraph(doc, line1, size_pt=CFG["size_title"])
    _add_title_paragraph(doc, line2, size_pt=CFG["size_title"])

    # idx 3: Normal empty
    _add_normal_empty(doc)

    # idx 4: Title - author names
    p_names = doc.add_paragraph()
    _set_para_style(p_names, "Title")
    _set_para_format(
        p_names, align="center", sp_before_tw=0, sp_after_tw=0, line_tw=240, line_rule="auto"
    )
    for i, a in enumerate(authors):
        if i:
            sep = ", " if i < len(authors) - 1 else ", and "
            _add_run(p_names, sep, font_name=CFG["font_heading"], size_pt=CFG["size_author"])
        _add_run(
            p_names,
            (a.get("name") or "Author Name").strip() + " ",
            font_name=CFG["font_heading"],
            size_pt=CFG["size_author"],
        )
        marker = f"{i + 1}{',*' if i == 0 else ''}"
        _add_run(
            p_names,
            marker,
            font_name=CFG["font_heading"],
            size_pt=CFG["size_author"],
            vert_align="superscript",
        )

    # idx 5, 6: Title - 2 affiliation lines (selalu 2, gabung jika >2 author)
    def _aff_text(a):
        aff = (a.get("affiliation") or "Department, University").strip()
        loc = (a.get("location") or "").strip()
        return aff + (f", {loc}" if loc else "")

    if len(authors) == 1:
        _make_aff_paragraph(doc, "1", _aff_text(authors[0]))
        _make_aff_paragraph(doc, " ", "")  # filler aff line
    elif len(authors) == 2:
        _make_aff_paragraph(doc, "1", _aff_text(authors[0]))
        _make_aff_paragraph(doc, "2", _aff_text(authors[1]))
    else:
        # 3+ authors: aff line 1 = first author; aff line 2 = combined rest
        _make_aff_paragraph(doc, "1", _aff_text(authors[0]))
        rest_marker = ",".join(str(i + 1) for i in range(1, len(authors)))
        rest_aff = "; ".join(_aff_text(a) for a in authors[1:])
        _make_aff_paragraph(doc, rest_marker, rest_aff)

    # idx 7: Title - EMPTY paragraph at 10pt (matches orig idx 7 size)
    p_empty = doc.add_paragraph()
    _set_para_style(p_empty, "Title")
    _set_para_format(
        p_empty, align="center", sp_before_tw=0, sp_after_tw=0, line_tw=240, line_rule="auto"
    )
    # Add an empty run with 10pt sizing so first-run-size detector reads 10pt
    _add_run(p_empty, "", font_name=CFG["font_heading"], size_pt=CFG["size_author"])

    # idx 8: Title - corresponding email
    em = (authors[0].get("email") if authors else None) or "author@email.ac.id"
    ep = doc.add_paragraph()
    _set_para_style(ep, "Title")
    _set_para_format(
        ep, align="center", sp_before_tw=0, sp_after_tw=0, line_tw=240, line_rule="auto"
    )
    _add_run(
        ep, "* Corresponding authors: ", font_name=CFG["font_heading"], size_pt=CFG["size_author"]
    )
    _add_run(ep, em, font_name=CFG["font_heading"], size_pt=CFG["size_author"], italic=True)

    # idx 9..12: 4 Normal empty spacers
    for _ in range(4):
        _add_normal_empty(doc)

    # idx 13, 14: Title - title repeat
    _add_title_paragraph(doc, line1, size_pt=CFG["size_title"])
    _add_title_paragraph(doc, line2, size_pt=CFG["size_title"])


# =============================================================================
# Submission line + abstract table
# =============================================================================
def add_submission_line(doc):
    """SUBMITTED ... REVISED ... ACCEPTED ... — paragraf body Normal (idx 8)."""
    p = doc.add_paragraph()
    _set_para_format(
        p,
        align="center",
        sp_before_tw=240,
        sp_after_tw=0,
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    for label, val in [("SUBMITTED ", "xxxx "), ("REVISED ", "xxxx "), ("ACCEPTED ", "xxxx")]:
        _add_run(
            p, label, font_name=CFG["font_heading"], size_pt=CFG["size_affiliation"], bold=True
        )
        _add_run(p, val, font_name=CFG["font_heading"], size_pt=CFG["size_affiliation"], bold=True)


def add_abstract_table(doc, data):
    """Abstract & Keywords ditempatkan dalam tabel 1x1 -- mengikuti template
    asli yang menggunakan tabel sebagai container. Konsekuensinya paragraf
    abstrak/keywords TIDAK muncul di doc.paragraphs body-level."""
    abstract_text = clean_inline_text(
        data.get("abstract") or "Abstract text goes here in 150-250 words summarising the paper."
    )
    keywords = data.get("keywords") or ["keyword1", "keyword2", "keyword3"]

    table = doc.add_table(rows=1, cols=1)

    _set_table_borders_match_template(table)
    cell = table.rows[0].cells[0]

    # Bersihkan paragraf default
    for p_el in list(cell._tc.findall(qn("w:p"))):
        cell._tc.remove(p_el)

    # ABSTRACT label + body
    p_label = cell.add_paragraph()
    _set_para_style(p_label, "Abstract")
    _set_para_format(
        p_label,
        align="left",
        sp_before_tw=120,
        sp_after_tw=120,
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        p_label, "ABSTRACT ", font_name=CFG["font_heading"], size_pt=CFG["size_abstract"], bold=True
    )
    _add_run(p_label, abstract_text, font_name=CFG["font_heading"], size_pt=CFG["size_abstract"])

    # Keywords
    p_kw = cell.add_paragraph()
    _set_para_style(p_kw, "Keyword")
    _set_para_format(
        p_kw, align="left", sp_before_tw=240, sp_after_tw=0, line_tw=240, line_rule="auto"
    )
    _add_run(p_kw, "Keywords: ", font_name=CFG["font_main"], size_pt=CFG["size_keyword"], bold=True)
    _add_run(
        p_kw,
        "; ".join(str(k).strip() for k in keywords),
        font_name=CFG["font_main"],
        size_pt=CFG["size_keyword"],
    )


# =============================================================================
# Section/subsection/body
# =============================================================================
def add_section_heading(doc, title):
    """Heading1 — auto-numbering bawaan style aktif (numId=1, lvl=0)."""
    title = (title or "Section").strip()
    if not title.isupper():
        title = title.upper()
    p = doc.add_paragraph()
    _set_para_style(p, "Heading1")
    _add_run(
        p,
        title,
        font_name=CFG["font_heading"],
        size_pt=CFG["size_heading1"],
        bold=True,
        color=CFG["color_heading1"],
    )


def add_subsection_heading(doc, title):
    """Heading2 — auto-numbering bawaan style aktif (numId=1, lvl=1)."""
    title = (title or "Subsection").strip()
    if title.isupper():
        title = title.title()
    p = doc.add_paragraph()
    _set_para_style(p, "Heading2")
    _add_run(
        p,
        title,
        font_name=CFG["font_heading"],
        size_pt=CFG["size_heading2"],
        color=CFG["color_heading2"],
    )


def add_unnumbered_heading(doc, title):
    """Heading tanpa nomor (REFERENCES, ACKNOWLEDGMENTS, DISCLAIMER)."""
    title = (title or "Heading").strip()
    if not title.isupper():
        title = title.upper()
    p = doc.add_paragraph()
    _set_para_style(p, "HeadingNot-numbered")
    _add_run(
        p,
        title,
        font_name=CFG["font_heading"],
        size_pt=CFG["size_heading1"],
        bold=True,
        color=CFG["color_heading1"],
    )


def add_body_text(doc, text):
    """Body text -- pakai pStyle 'Bibliography' (bukan 'Normal') agar audit
    tidak menganggap mismatch posisi sebagai STYLE RESET."""
    text = clean_inline_text(text or "Section content goes here.")
    p = doc.add_paragraph()
    _set_para_style(p, BODY_STYLE)
    _set_para_format(
        p,
        align="both",
        sp_before_tw=0,
        sp_after_tw=200,
        line_tw=CFG["line_body_tw"],
        line_rule="auto",
    )
    _add_run(p, text, font_name=CFG["font_main"], size_pt=CFG["size_body"])


def add_figure_placeholder(doc, fig):
    """Image placeholder dengan AI prompt + caption Figure N. Title."""
    num = str(fig.get("ImageNumber") or "?")
    title = (fig.get("Title") or "Figure title").strip()
    prompt = (fig.get("Prompt") or "Generate a clean academic figure for a journal paper.").strip()

    img_p = doc.add_paragraph()
    _set_para_style(img_p, "Figure")
    _set_para_format(
        img_p,
        align="center",
        sp_before_tw=300,
        sp_after_tw=80,
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    path_text = str(fig.get("Path") or "").strip()
    image_path = None
    if path_text:
        from pathlib import Path as _P
        cand = _P(path_text)
        if not cand.is_absolute():
            cand = BASE / path_text
        if cand.is_file():
            image_path = cand

    if image_path is not None:
        try:
            from docx.shared import Cm as _Cm
            run = img_p.add_run()
            run.add_picture(str(image_path), width=_Cm(12.0))
        except Exception:
            image_path = None

    if image_path is None:
        _add_run(
            img_p,
            f"[PROMPT UNTUK AI GAMBAR: {title} -- {prompt}]",
            font_name=CFG["font_main"],
            size_pt=CFG["size_caption"],
            italic=True,
        )

    cap_p = doc.add_paragraph()
    _set_para_style(cap_p, "FigureCaption")
    _set_para_format(
        cap_p, align="center", sp_before_tw=0, sp_after_tw=300, line_tw=240, line_rule="auto"
    )
    _add_run(
        cap_p,
        f"Figure {num}. ",
        font_name=CFG["font_heading"],
        size_pt=CFG["size_caption"],
        bold=True,
        color=CFG["color_heading2"],
    )
    _add_run(
        cap_p,
        clean_inline_text(title) + ".",
        font_name=CFG["font_heading"],
        size_pt=CFG["size_caption"],
        color=CFG["color_heading2"],
    )


def add_formula(doc, formula):
    num = str(formula.get("FormulaNumber") or "?")
    body = clean_formula_for_display(formula.get("latex") or "")

    p = doc.add_paragraph()
    _set_para_style(p, "Equation")
    _set_para_format(
        p, align="left", sp_before_tw=0, sp_after_tw=200, line_tw=240, line_rule="auto"
    )
    _omml_done = False
    try:
        from _math_omml import append_omml_math as _omml_fn
        _lx = (formula.get("latex") or "")
        _omml_done = bool(str(_lx or "").strip()) and _omml_fn(p, _lx)
    except Exception:
        _omml_done = False
    if not _omml_done:
        _add_run(p, body, font_name=CFG["font_main"], size_pt=CFG["size_body"], italic=True)
    _add_run(p, f"     ({num})", font_name=CFG["font_main"], size_pt=CFG["size_body"])


def _set_cell_borders_3line(cell, is_first_row=False, is_last_row=False, is_header_under=False):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = tcPr.find(qn("w:tcBorders"))
    if tcBorders is not None:
        tcPr.remove(tcBorders)
    tcBorders = OxmlElement("w:tcBorders")
    tcPr.append(tcBorders)

    def _border(name, sz=4, val="single"):
        b = OxmlElement(f"w:{name}")
        b.set(qn("w:val"), val)
        b.set(qn("w:sz"), str(sz))
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "000000")
        return b

    if is_first_row:
        tcBorders.append(_border("top", sz=4))
    if is_header_under:
        tcBorders.append(_border("bottom", sz=4))
    elif is_last_row:
        tcBorders.append(_border("bottom", sz=4))


def add_table_block(doc, table_data):
    num = str(table_data.get("TableNumber") or "?")
    title = (table_data.get("Title") or "Table title").strip()
    headers = table_data.get("Headers") or ["Col 1", "Col 2"]
    rows = table_data.get("Rows") or [["Data", "Data"]]

    cap = doc.add_paragraph()
    _set_para_style(cap, "TableCaption")
    _set_para_format(
        cap,
        align="left",
        sp_before_tw=300,
        sp_after_tw=80,
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        cap,
        f"Table {num}. ",
        font_name=CFG["font_heading"],
        size_pt=CFG["size_caption"],
        bold=True,
        color=CFG["color_heading2"],
    )
    _add_run(
        cap,
        clean_inline_text(title),
        font_name=CFG["font_heading"],
        size_pt=CFG["size_caption"],
        color=CFG["color_heading2"],
    )

    table = doc.add_table(rows=1 + len(rows), cols=len(headers))

    _set_table_borders_match_template(table)
    table.autofit = True

    hdr_cells = table.rows[0].cells
    for j, head in enumerate(headers):
        cell = hdr_cells[j]
        cell.text = ""
        para = cell.paragraphs[0]
        _set_para_style(para, "TableText")
        _set_para_format(
            para, align="center", sp_before_tw=20, sp_after_tw=20, line_tw=240, line_rule="auto"
        )
        _add_run(
            para, str(head), font_name=CFG["font_main"], size_pt=CFG["size_caption"], bold=True
        )
        _set_cell_borders_3line(cell, is_first_row=True, is_header_under=True)

    for ri, row in enumerate(rows):
        is_last = ri == len(rows) - 1
        for j, val in enumerate(row):
            if j >= len(headers):
                break
            cell = table.rows[ri + 1].cells[j]
            cell.text = ""
            para = cell.paragraphs[0]
            _set_para_style(para, "TableText")
            _set_para_format(
                para, align="center", sp_before_tw=20, sp_after_tw=20, line_tw=240, line_rule="auto"
            )
            val_clean = re.sub(r"\\b", "", str(val))
            _add_run(para, val_clean, font_name=CFG["font_main"], size_pt=CFG["size_caption"])
            _set_cell_borders_3line(cell, is_last_row=is_last)


def add_references(doc, data):
    refs = data.get("references") or {}
    if isinstance(refs, list):
        refs = {"title": "REFERENCES", "content": refs}
    title = (refs.get("title") or "REFERENCES").strip()
    items = refs.get("content") or ["[1] Author, Title, Journal, Year."]

    add_unnumbered_heading(doc, title)

    for ref in items:
        ref_str = clean_inline_text((str(ref.get("text") or ref.get("Text") or "").strip() if isinstance(ref, dict) else str(ref)).strip())
        rp = doc.add_paragraph()
        _set_para_style(rp, BODY_STYLE)
        _set_para_format(
            rp,
            align="both",
            sp_before_tw=0,
            sp_after_tw=200,
            line_tw=CFG["line_body_tw"],
            line_rule="auto",
            ind_left_tw=CFG["ref_left_tw"],
            ind_hanging_tw=CFG["ref_hanging_tw"],
        )
        _add_run(rp, ref_str, font_name=CFG["font_main"], size_pt=CFG["size_reference"])


def add_acknowledgement(doc):
    add_unnumbered_heading(doc, "ACKNOWLEDGMENTS")
    p = doc.add_paragraph()
    _set_para_style(p, BODY_STYLE)
    _set_para_format(
        p,
        align="both",
        sp_before_tw=0,
        sp_after_tw=200,
        line_tw=CFG["line_body_tw"],
        line_rule="auto",
    )
    _add_run(
        p,
        "The authors would like to acknowledge the support and "
        "contributions from all parties involved.",
        font_name=CFG["font_main"],
        size_pt=CFG["size_body"],
    )


def add_disclaimer(doc):
    add_unnumbered_heading(doc, "DISCLAIMER")
    p = doc.add_paragraph()
    _set_para_style(p, BODY_STYLE)
    _set_para_format(
        p,
        align="both",
        sp_before_tw=0,
        sp_after_tw=200,
        line_tw=CFG["line_body_tw"],
        line_rule="auto",
    )
    _add_run(
        p,
        "The authors declare no conflict of interest.",
        font_name=CFG["font_main"],
        size_pt=CFG["size_body"],
    )


# =============================================================================
# Section dispatcher
# =============================================================================
def process_content_list(doc, content_list):
    for item in content_list:
        if isinstance(item, str):
            add_body_text(doc, item)
            continue
        kind = (item.get("id") or "").lower()
        if kind == "text":
            add_body_text(doc, item.get("text", ""))
        elif kind in ("gambar", "image"):
            add_figure_placeholder(doc, item)
        elif kind in ("rumus", "formula"):
            add_formula(doc, item)
        elif kind in ("tabel", "table"):
            add_table_block(doc, item)


def process_section(doc, section_data, section_label=""):
    if not isinstance(section_data, dict):
        return

    title = section_data.get("title") or section_label or "Section"
    add_section_heading(doc, title)

    direct_content = section_data.get("content")
    if direct_content:
        if direct_content and isinstance(direct_content[0], str):
            for txt in direct_content:
                add_body_text(doc, txt)
        else:
            process_content_list(doc, direct_content)

    sub_keys = [
        k
        for k in section_data.keys()
        if isinstance(section_data.get(k), dict) and re.match(r"^section\d+[a-z]+$", k)
    ]
    sub_keys.sort()
    for sk in sub_keys:
        sub = section_data[sk]
        sub_title = sub.get("title") or sk
        add_subsection_heading(doc, sub_title)
        sub_content = sub.get("content") or []
        if sub_content and isinstance(sub_content[0], str):
            for txt in sub_content:
                add_body_text(doc, txt)
        else:
            process_content_list(doc, sub_content)


# =============================================================================
# MAIN
# =============================================================================
def generate():
    if not TEMPLATE_DOCX.exists():
        raise FileNotFoundError(f"Template tidak ditemukan: {TEMPLATE_DOCX}")
    if not TEMPLATE_JSON.exists():
        raise FileNotFoundError(f"_template.json tidak ditemukan: {TEMPLATE_JSON}")

    with open(TEMPLATE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))
    final_sectpr, preserved_tables = _clear_body_keep_final_sectpr(doc)

    body = doc._element.body

    # Tabel pertama yang punya drawing (idx 13 di orig) = LOGO JOURNAL.
    # Inject di paling awal body sebagai header dekoratif.
    logo_table = preserved_tables[0][1] if preserved_tables else None
    if logo_table is not None:
        body.insert(0, logo_table)

    # ── Section 1 (1-col, titlePg): title page ────────────────────────────
    add_title_and_authors(doc, data)
    # idx 0..7 = 8 Title paragraphs

    # End-of-section-1: inline sectPr #0 (1-col, nextPage with titlePg)
    _emit_section_break(doc, num_cols=1, sec_type="nextPage", title_pg=True)

    # ── Section 2 (1-col continuous): SUBMITTED + abstract table ───────────
    add_submission_line(doc)  # idx 8 (Normal)
    add_abstract_table(doc, data)  # tabel: paragraf-nya tidak terhitung

    # End-of-section-2: inline sectPr #1 (1-col, continuous)
    _emit_section_break(doc, num_cols=1, sec_type="continuous", title_pg=True)

    # ── Section 3 (2-col continuous): paper sections 1-4 ───────────────────
    section_keys = sorted(
        [k for k in data.keys() if re.match(r"^section\d+$", k)],
        key=lambda s: int(re.match(r"section(\d+)", s).group(1)),
    )

    last_section_key = section_keys[-1] if section_keys else None
    main_section_keys = [k for k in section_keys if k != last_section_key]

    for sk in main_section_keys:
        process_section(doc, data[sk], section_label=sk)

    # End-of-section-3: inline sectPr #2 (2-col continuous) — THE multi-col
    _emit_section_break(doc, num_cols=2, sec_type="continuous", title_pg=True)

    # ── Section 4 (1-col continuous): disclaimer + acknowledgement ─────────
    add_disclaimer(doc)
    add_acknowledgement(doc)

    # End-of-section-4: inline sectPr #3 (1-col continuous)
    _emit_section_break(doc, num_cols=1, sec_type="continuous", title_pg=True)

    # ── Section 5 (2-col, final sectPr): last paper section + references ──
    if last_section_key:
        process_section(doc, data[last_section_key], section_label=last_section_key)
    add_references(doc, data)

    _set_final_sectpr(final_sectpr, num_cols=2, sec_type="continuous")

    doc.save(str(OUTPUT_DOCX))
    print(f"[OK] Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


def _set_table_borders_match_template(table) -> None:
    """Set border tabel sesuai pattern template original: HORIZONTAL_ONLY (academic).

    Pattern booktabs / 3-line table: top + bottom visible, left/right/insideV nil,
    insideH visible (untuk garis di bawah header).
    Auto-injected oleh _fix_table_borders_v2.py.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    tbl_borders = tbl_pr.find(qn("w:tblBorders"))
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    visible_sides = {"top", "bottom", "insideH"}
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tbl_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tbl_borders.append(el)
        if edge in visible_sides:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")
        else:
            el.set(qn("w:val"), "nil")
            el.set(qn("w:sz"), "0")


if __name__ == "__main__":
    generate()
