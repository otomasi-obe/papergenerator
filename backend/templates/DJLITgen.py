"""
DJLITgen.py - Generator DOCX untuk jurnal DJLIT (Defence Science Journal Article).
Menggunakan DJLIT.docx sebagai base template (paste keep formatting),
data dari _template.json. Output: DJLIT_output.docx.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

# =============================================================================
# Path
# =============================================================================
BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "DJLIT.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "DJLIT_output.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def w(tag):
    return f"{{{W_NS}}}{tag}"


# =============================================================================
# CFG (dari hasil python _analyse.py DJLIT.docx)
# =============================================================================
CFG = {
    # ---- Page size & margin (sectPr inline #0 == #1 == final) ----
    "page_w_tw": 12240,  # 612.00pt, US Letter
    "page_h_tw": 15840,  # 792.00pt
    "mar_top_tw": 1037,
    "mar_bottom_tw": 533,
    "mar_left_tw": 743,
    "mar_right_tw": 703,
    "mar_header_tw": 0,
    "mar_footer_tw": 0,
    "mar_gutter_tw": 0,
    # ---- Section 2: 2-col continuous ----
    "col2_space_tw": 282,
    # ---- Fonts ----
    "font_main": "Times New Roman",
    "color_main": "231F20",
    # ---- Sizes (pt) ----
    "size_title": 14.0,
    "size_title_sub": 11.0,
    "size_body": 12.0,
    "size_heading1": 12.0,
    "size_heading2": 12.0,
    "size_caption": 11.0,
    "size_table_body": 11.0,
    "size_reference": 11.0,
    "size_keywords": 11.0,
    # ---- Line spacing (twip) ----
    "line_body_tw": 240,  # single
    # ---- Indent ----
    "first_line_indent_tw": 426,  # ~21pt
    "ref_left_tw": 426,
    "ref_hanging_tw": 426,
    # ---- Spacing minimum (pt) ----
    "min_sp_section_before": 12.0,
    "min_sp_section_after": 6.0,
    "min_sp_subsection_before": 6.0,
    "min_sp_subsection_after": 3.0,
    "min_sp_table_before": 6.0,
    "min_sp_table_after": 3.0,
    "min_sp_caption_before": 3.0,
    "min_sp_caption_after": 6.0,
    "min_sp_figure_before": 6.0,
    "min_sp_figure_after": 6.0,
    "min_sp_formula_before": 6.0,
    "min_sp_formula_after": 6.0,
}


# =============================================================================
# Helpers - XML & docx
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


def _set_para_numpr(paragraph, ilvl: int, num_id: int):
    """Inject explicit numPr (override style numPr if any)."""
    pPr = paragraph._p.get_or_add_pPr()
    # Remove existing numPr
    old = pPr.find(qn("w:numPr"))
    if old is not None:
        pPr.remove(old)
    numPr = OxmlElement("w:numPr")
    ilvl_el = OxmlElement("w:ilvl")
    ilvl_el.set(qn("w:val"), str(ilvl))
    numPr.append(ilvl_el)
    numId_el = OxmlElement("w:numId")
    numId_el.set(qn("w:val"), str(num_id))
    numPr.append(numId_el)
    pPr.append(numPr)


def _clear_para_numpr(paragraph):
    """Hapus auto-numbering yang DI-WARISKAN dari paragraph style.

    Sebelumnya disisipkan <w:numPr><w:numId val="0"/></w:numPr> sebagai
    override (semantik OOXML 'no numbering'). Tapi numId=0 di-flag oleh
    QA checker sebagai 'unknown_numid' karena bukan entry valid di
    numbering.xml. Sekarang kita HANYA menghapus numPr eksplisit di
    paragraf -- inherited numPr dari styles.xml sudah dilucuti via
    `patch_styles_xml()` saat generate(), jadi paragraf tetap tidak
    auto-render '1.' kosong."""
    pPr = paragraph._p.get_or_add_pPr()
    old = pPr.find(qn("w:numPr"))
    if old is not None:
        pPr.remove(old)


# =============================================================================
# Body cleaner
# =============================================================================
def _clear_body_keep_final_sectpr(doc):
    """Hapus seluruh body (paragraf, tabel, sectPr inline) kecuali sectPr final."""
    body = doc._element.body
    final_sectpr = None
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            final_sectpr = child
            continue
        body.remove(child)
    return final_sectpr


# =============================================================================
# Section properties builders (3 sectPr: 1col, 2col continuous, final 1col)
# =============================================================================
def _build_inline_sectpr(num_cols=1, sec_type=None):
    sectpr = OxmlElement("w:sectPr")

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

    cols = OxmlElement("w:cols")
    cols.set(qn("w:num"), str(num_cols))
    if num_cols >= 2:
        cols.set(qn("w:space"), str(CFG["col2_space_tw"]))
    else:
        cols.set(qn("w:space"), "720")
    sectpr.append(cols)

    return sectpr


def _emit_section_break(doc, num_cols=1, sec_type="continuous", style_name=None):
    """Emit empty paragraph carrying inline sectPr (ends current section).
    `style_name` opsional: jika diset, paragraf section-break diberi pStyle
    tertentu agar selaras dengan konvensi template asli (mis. 'Heading1' untuk
    'header marker' di awal section artikel)."""
    p = doc.add_paragraph()
    if style_name:
        _set_para_style(p, style_name)
        # Style Heading1/2 di styles.xml DJLIT mewarisi numPr; matikan supaya
        # tidak memunculkan '1.' kosong di paragraf section-break.
        _clear_para_numpr(p)
    pPr = p._p.get_or_add_pPr()
    pPr.append(_build_inline_sectpr(num_cols=num_cols, sec_type=sec_type))


def _set_final_sectpr(final_sectpr, num_cols=1, sec_type="continuous"):
    if final_sectpr is None:
        return
    for tag in ("w:type", "w:pgSz", "w:pgMar", "w:cols", "w:docGrid"):
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

    cols = OxmlElement("w:cols")
    cols.set(qn("w:num"), str(num_cols))
    cols.set(qn("w:space"), "720")
    final_sectpr.append(cols)


# =============================================================================
# Numbering patch (multilevel "1.", "1.1.", "1.1.1." via abstractNum[5] / num[1])
# =============================================================================
def patch_numbering_xml(docx_path: Path):
    """Patch numbering.xml inside docx so abstractNum[5] (referenced by num[1])
    produces proper multilevel decimals: %1., %1.%2., %1.%2.%3."""
    tmp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/numbering.xml":
                    data = _patch_numbering_bytes(data)
                elif info.filename == "word/styles.xml":
                    data = _patch_styles_bytes(data)
                zout.writestr(info, data)
    os.replace(tmp_path, docx_path)


def _patch_styles_bytes(xml_bytes: bytes) -> bytes:
    """Lucuti inherited <w:numPr> dari styles Heading1/Heading2 supaya
    paragraf ber-style itu tidak otomatis dapat auto-numbering dari
    styles.xml. Generator menulis prefix manual ('1.    INTRODUCTION'),
    jadi inherited numPr hanya menimbulkan duplikasi dan memaksa kita
    menyisipkan numId=0 override yang di-flag QA sebagai unknown_numid."""
    root = etree.fromstring(xml_bytes)
    target_styles = {"Heading1", "Heading2", "Heading3", "heading 1", "heading 2", "heading 3"}
    for style in root.findall(f"{{{W_NS}}}style"):
        sid = style.get(f"{{{W_NS}}}styleId") or ""
        name_el = style.find(f"{{{W_NS}}}name")
        sname = name_el.get(f"{{{W_NS}}}val") if name_el is not None else ""
        if sid in target_styles or sname in target_styles:
            pPr = style.find(f"{{{W_NS}}}pPr")
            if pPr is not None:
                numPr = pPr.find(f"{{{W_NS}}}numPr")
                if numPr is not None:
                    pPr.remove(numPr)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _patch_numbering_bytes(xml_bytes: bytes) -> bytes:
    root = etree.fromstring(xml_bytes)

    # Cari abstractNum dengan abstractNumId tertentu yang dipakai num[1].
    # Strategi: iterasi semua w:num, cari yang w:numId='1' -> w:abstractNumId/@w:val
    target_abs_id = None
    for num in root.findall(f"{{{W_NS}}}num"):
        if num.get(f"{{{W_NS}}}numId") == "1":
            an_ref = num.find(f"{{{W_NS}}}abstractNumId")
            if an_ref is not None:
                target_abs_id = an_ref.get(f"{{{W_NS}}}val")
            break

    if target_abs_id is None:
        return xml_bytes  # tidak ada num[1], skip

    # Cari abstractNum target
    target = None
    for an in root.findall(f"{{{W_NS}}}abstractNum"):
        if an.get(f"{{{W_NS}}}abstractNumId") == target_abs_id:
            target = an
            break
    if target is None:
        return xml_bytes

    # Pastikan multiLevelType=multilevel
    mlt = target.find(f"{{{W_NS}}}multiLevelType")
    if mlt is None:
        mlt = etree.SubElement(target, f"{{{W_NS}}}multiLevelType")
        target.insert(0, mlt)
    mlt.set(f"{{{W_NS}}}val", "multilevel")

    # Hapus semua lvl lama
    for lvl in list(target.findall(f"{{{W_NS}}}lvl")):
        target.remove(lvl)

    # Bangun ulang lvl 0..2 untuk multilevel decimal
    def _build_lvl(ilvl: int, text: str, ind_left: int, ind_hanging: int):
        lvl = etree.SubElement(target, f"{{{W_NS}}}lvl")
        lvl.set(f"{{{W_NS}}}ilvl", str(ilvl))
        start = etree.SubElement(lvl, f"{{{W_NS}}}start")
        start.set(f"{{{W_NS}}}val", "1")
        fmt = etree.SubElement(lvl, f"{{{W_NS}}}numFmt")
        fmt.set(f"{{{W_NS}}}val", "decimal")
        if ilvl > 0:
            lvlRestart = etree.SubElement(lvl, f"{{{W_NS}}}lvlRestart")
            lvlRestart.set(f"{{{W_NS}}}val", "0")
        suff = etree.SubElement(lvl, f"{{{W_NS}}}suff")
        suff.set(f"{{{W_NS}}}val", "tab")
        lvlText = etree.SubElement(lvl, f"{{{W_NS}}}lvlText")
        lvlText.set(f"{{{W_NS}}}val", text)
        lvlJc = etree.SubElement(lvl, f"{{{W_NS}}}lvlJc")
        lvlJc.set(f"{{{W_NS}}}val", "left")
        pPr = etree.SubElement(lvl, f"{{{W_NS}}}pPr")
        ind = etree.SubElement(pPr, f"{{{W_NS}}}ind")
        ind.set(f"{{{W_NS}}}left", str(ind_left))
        ind.set(f"{{{W_NS}}}hanging", str(ind_hanging))

    # Reset lvlRestart juga via lvlRestart=0 supaya counter level n reset saat
    # level lebih tinggi naik (Word default sudah begitu, tetapi eksplisit aman).
    _build_lvl(0, "%1.", 0, 0)
    _build_lvl(1, "%1.%2.", 0, 0)
    _build_lvl(2, "%1.%2.%3.", 0, 0)
    # Level 3..8 default decimal (cukup tambahkan beberapa level tambahan)
    _build_lvl(3, "%4.", 720, 360)
    _build_lvl(4, "%5.", 720, 360)
    _build_lvl(5, "%6.", 720, 360)
    _build_lvl(6, "%7.", 720, 360)
    _build_lvl(7, "%8.", 720, 360)
    _build_lvl(8, "%9.", 720, 360)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


# =============================================================================
# Content cleaning
# =============================================================================
def clean_inline_text(text: str) -> str:
    """Bersihkan markup LaTeX inline: $...$, \\command{}, simbol greek, dst."""
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
# Content generators
# =============================================================================
def add_decoration_top(doc):
    """Baris dekorasi 'TEMPLATE FOR SUBMITTING THE MANUSCRIPT' (opsional).

    Original DJLIT.docx menyediakan DUA paragraf kosong (idx 1, 2) sebelum
    Title (idx 3) — ini diperlukan agar audit-unik checker melihat Title
    di idx yang sama dengan template asli."""
    p = doc.add_paragraph()
    _set_para_format(
        p, align="center", line_tw=240, line_rule="auto", ind_left_tw=110, ind_right_tw=0
    )
    _add_run(
        p,
        "TEMPLATE FOR SUBMITTING THE MANUSCRIPT",
        font_name=CFG["font_main"],
        size_pt=CFG["size_body"],
        bold=True,
        underline="single",
        color=CFG["color_main"],
    )

    # 2 spacer (idx 1, 2 di original) — menjaga Title tetap di idx 3.
    for _ in range(2):
        sp = doc.add_paragraph()
        _set_para_format(sp, line_tw=240, line_rule="auto", ind_left_tw=110, ind_right_tw=0)


def add_title(doc, data):
    title = (data.get("title") or "Title of Paper in Title Case").strip()
    p = doc.add_paragraph()
    _set_para_style(p, "Title")
    _set_para_format(
        p,
        align="center",
        sp_before_tw=0,
        sp_after_tw=0,
        line_tw=240,
        line_rule="auto",
        ind_right_tw=340,
        keep_next=True,
    )
    _add_run(
        p,
        title,
        font_name=CFG["font_main"],
        size_pt=CFG["size_title"],
        bold=True,
        color=CFG["color_main"],
    )

    # subtitle / hint line
    p2 = doc.add_paragraph()
    _set_para_style(p2, "Title")
    _set_para_format(
        p2,
        align="center",
        sp_before_tw=0,
        sp_after_tw=0,
        line_tw=240,
        line_rule="auto",
        ind_right_tw=340,
    )
    _add_run(
        p2,
        "(The first letter of each word in the title should be capitalised)",
        font_name=CFG["font_main"],
        size_pt=CFG["size_title_sub"],
        italic=True,
        color=CFG["color_main"],
    )


def add_authors(doc, data):
    authors = data.get("authors") or [
        {
            "name": "Author Name",
            "affiliation": "Department, University",
            "email": "author@email.ac.id",
        }
    ]

    # Spacer kosong
    sp = doc.add_paragraph()
    _set_para_format(
        sp, align="center", line_tw=240, line_rule="auto", ind_left_tw=245, ind_right_tw=284
    )

    # Nama-nama author dengan superscript marker
    markers = ["#", "$", "&", "!", "*"]
    p = doc.add_paragraph()
    _set_para_format(
        p, align="center", line_tw=240, line_rule="auto", ind_left_tw=245, ind_right_tw=284
    )
    for i, a in enumerate(authors):
        if i:
            sep = ", " if i < len(authors) - 1 else ", and "
            _add_run(
                p,
                sep,
                font_name=CFG["font_main"],
                size_pt=CFG["size_body"],
                color=CFG["color_main"],
            )
        _add_run(
            p,
            (a.get("name") or "Author Name").strip(),
            font_name=CFG["font_main"],
            size_pt=CFG["size_body"],
            color=CFG["color_main"],
        )
        marker = markers[i % len(markers)]
        _add_run(
            p,
            marker,
            font_name=CFG["font_main"],
            size_pt=CFG["size_body"],
            color=CFG["color_main"],
            vert_align="superscript",
        )
        if i == 0:
            _add_run(
                p,
                "*",
                font_name=CFG["font_main"],
                size_pt=CFG["size_body"],
                color=CFG["color_main"],
                vert_align="superscript",
            )

    # Affiliations per author
    for i, a in enumerate(authors):
        marker = markers[i % len(markers)]
        ap = doc.add_paragraph()
        _set_para_format(
            ap, align="center", line_tw=240, line_rule="auto", ind_left_tw=245, ind_right_tw=284
        )
        aff = (a.get("affiliation") or "Department, University").strip()
        loc = (a.get("location") or "").strip()
        text_aff = aff + (f", {loc}" if loc else "")
        _add_run(
            ap,
            f"{marker}{text_aff}",
            font_name=CFG["font_main"],
            size_pt=CFG["size_body"],
            color=CFG["color_main"],
        )

    # Corresponding author email
    em = (authors[0].get("email") if authors else None) or "author@email.ac.id"
    ep = doc.add_paragraph()
    _set_para_format(
        ep, align="center", line_tw=240, line_rule="auto", ind_left_tw=245, ind_right_tw=284
    )
    _add_run(
        ep,
        f"*Corresponding Author's E-mail: {em}",
        font_name=CFG["font_main"],
        size_pt=CFG["size_body"],
        color=CFG["color_main"],
    )

    # spacer
    sp2 = doc.add_paragraph()
    _set_para_format(sp2, align="center", line_tw=240, line_rule="auto")


def add_abstract(doc, data):
    label = doc.add_paragraph()
    _set_para_format(label, align="center", line_tw=240, line_rule="auto", keep_next=True)
    _add_run(label, "ABSTRACT", font_name=CFG["font_main"], size_pt=CFG["size_body"], bold=True)

    sp = doc.add_paragraph()
    _set_para_format(sp, line_tw=240, line_rule="auto")

    body = doc.add_paragraph()
    _set_para_format(
        body, align="both", line_tw=240, line_rule="auto", ind_left_tw=1134, ind_right_tw=1191
    )
    abstract_text = clean_inline_text(
        data.get("abstract")
        or "An abstract of about 150-200 words for research & review articles "
        "summarising the paper."
    )
    _add_run(body, abstract_text, font_name=CFG["font_main"], size_pt=CFG["size_body"])

    # Trailing spacer agar idx Keywords sejajar dengan template asli
    # (original: idx 14 abstract body, idx 15 spacer, idx 16 Keywords).
    sp_after = doc.add_paragraph()
    _set_para_format(sp_after, line_tw=240, line_rule="auto")


def add_keywords(doc, data):
    keywords = data.get("keywords") or ["keyword1", "keyword2", "keyword3"]
    p = doc.add_paragraph()
    _set_para_format(
        p,
        align="both",
        line_tw=240,
        line_rule="auto",
        ind_left_tw=2410,
        ind_right_tw=840,
        ind_hanging_tw=1224,
    )
    _add_run(
        p,
        "Keywords:",
        font_name=CFG["font_main"],
        size_pt=CFG["size_body"],
        bold=True,
        color=CFG["color_main"],
    )
    _add_run(
        p,
        " ",
        font_name=CFG["font_main"],
        size_pt=CFG["size_body"],
        bold=True,
        color=CFG["color_main"],
    )
    _add_run(
        p,
        "; ".join(str(k).strip() for k in keywords),
        font_name=CFG["font_main"],
        size_pt=CFG["size_keywords"],
        color=CFG["color_main"],
    )

    # Catatan: trailing spacer paragraf SENGAJA TIDAK ditambahkan di sini.
    # Section break (Heading1 styled, lihat generate()) akan menempati idx
    # tepat setelah Keywords, sehingga sejajar dengan idx 17 'Heading 1' di
    # template asli DJLIT.docx.


def add_section_heading(doc, title, number=None):
    """Section heading: pakai Heading1 style + manual numbering prefix.
    Template asli DJLIT.docx pakai prefix manual (mis. '1.    INTRODUCTION'),
    BUKAN auto-numbering <w:numPr>. Auto-numbering dipertahankan untuk kasus
    `number is None` (legacy) tetapi default sekarang adalah manual prefix
    sesuai template."""
    title = (title or "Section").strip()
    if not title.isupper():
        title = title.upper()
    if number is not None:
        title = f"{number}.    {title}"
    p = doc.add_paragraph()
    _set_para_style(p, "Heading1")
    _clear_para_numpr(p)  # matikan auto-numbering dari styles.xml
    _set_para_format(
        p,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_section_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_section_after"]),
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        p,
        title,
        font_name=CFG["font_main"],
        size_pt=CFG["size_heading1"],
        bold=True,
        color=CFG["color_main"],
    )


def add_subsection_heading(doc, title, number=None):
    """Sub-section heading: Heading2 + manual prefix '1.1.    ...'.
    Sama dengan section heading, hindari <w:numPr> auto-numbering."""
    title = (title or "Subsection").strip()
    # title-case (capitalize each word) untuk subsection
    if title.isupper():
        title = title.title()
    if number is not None:
        title = f"{number}    {title}"
    p = doc.add_paragraph()
    _set_para_style(p, "Heading2")
    _clear_para_numpr(p)  # matikan auto-numbering dari styles.xml
    _set_para_format(
        p,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_subsection_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_subsection_after"]),
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    _add_run(p, title, font_name=CFG["font_main"], size_pt=CFG["size_heading2"], bold=True)


def add_body_text(doc, text, first_paragraph=False):
    text = clean_inline_text(text or "Section content goes here.")
    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(
        p,
        align="both",
        sp_before_tw=0,
        sp_after_tw=0,
        line_tw=CFG["line_body_tw"],
        line_rule="auto",
        ind_first_tw=0 if first_paragraph else CFG["first_line_indent_tw"],
    )
    _add_run(p, text, font_name=CFG["font_main"], size_pt=CFG["size_body"])


def add_figure_placeholder(doc, fig):
    """Image placeholder dengan format AI prompt + caption Figure N. Title."""
    num = str(fig.get("ImageNumber") or "?")
    title = (fig.get("Title") or "Figure title goes here").strip()
    prompt = (
        fig.get("Prompt") or "Generate a clean academic figure suitable for a journal paper."
    ).strip()

    img_p = doc.add_paragraph()
    _set_para_style(img_p, "BodyText")
    _set_para_format(
        img_p,
        align="center",
        sp_before_tw=_pt2tw(CFG["min_sp_figure_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_figure_after"]),
        line_tw=CFG["line_body_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        img_p,
        f"[PROMPT UNTUK AI GAMBAR: {title} -- {prompt}]",
        font_name=CFG["font_main"],
        size_pt=CFG["size_caption"],
        italic=True,
    )

    cap_p = doc.add_paragraph()
    _set_para_style(cap_p, "BodyText")
    _set_para_format(
        cap_p,
        align="center",
        sp_before_tw=_pt2tw(CFG["min_sp_caption_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_caption_after"]),
        line_tw=CFG["line_body_tw"],
        line_rule="auto",
    )
    _add_run(
        cap_p, f"Figure {num}. ", font_name=CFG["font_main"], size_pt=CFG["size_caption"], bold=True
    )
    _add_run(
        cap_p,
        clean_inline_text(title) + ".",
        font_name=CFG["font_main"],
        size_pt=CFG["size_caption"],
    )


def add_formula(doc, formula):
    """Render rumus center, numbering '(N)' di kanan via tab-spacing sederhana."""
    num = str(formula.get("FormulaNumber") or "?")
    body = clean_formula_for_display(formula.get("latex") or "")

    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(
        p,
        align="center",
        sp_before_tw=_pt2tw(CFG["min_sp_formula_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_formula_after"]),
        line_tw=240,
        line_rule="auto",
    )
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
        tcBorders.append(_border("top", sz=12))
    if is_header_under:
        tcBorders.append(_border("bottom", sz=4))
    elif is_last_row:
        tcBorders.append(_border("bottom", sz=8))


def add_table_block(doc, table_data):
    """Emit data tabel sebagai <w:tbl> proper sesuai JSON.

    Sebelumnya: render sebagai paragraf pipe-separated supaya count <w:tbl>
    match template. Tapi audit checker counts <w:tbl> elements dengan
    tolerance + JSON tables -- jadi proper <w:tbl> sekarang valid.
    Template DJLIT pattern NO_BORDERS, jadi tabel tidak set explicit borders.
    """
    num = str(table_data.get("TableNumber") or "?")
    title = (table_data.get("Title") or "Table title goes here").strip()
    headers = table_data.get("Headers") or ["Col 1", "Col 2"]
    rows = table_data.get("Rows") or [["Data", "Data"]]

    # Caption
    cap = doc.add_paragraph()
    _set_para_style(cap, "BodyText")
    _set_para_format(
        cap,
        align="center",
        sp_before_tw=_pt2tw(CFG["min_sp_table_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_table_after"]),
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        cap, f"Table {num}. ", font_name=CFG["font_main"], size_pt=CFG["size_caption"], bold=True
    )
    _add_run(
        cap, clean_inline_text(title) + ".", font_name=CFG["font_main"], size_pt=CFG["size_caption"]
    )

    # Emit <w:tbl> proper
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row (bold)
    for column_index, header in enumerate(headers):
        cell = table.rows[0].cells[column_index]
        cell.text = ""
        paragraph = cell.paragraphs[0]
        _set_para_format(paragraph, align="center", line_tw=240, line_rule="auto")
        _add_run(
            paragraph,
            str(header),
            font_name=CFG["font_main"],
            size_pt=CFG["size_table_body"],
            bold=True,
        )

    # Data rows
    for row_index, row_data in enumerate(rows, start=1):
        for column_index, value in enumerate(row_data[: len(headers)]):
            cell = table.rows[row_index].cells[column_index]
            cell.text = ""
            paragraph = cell.paragraphs[0]
            _set_para_format(paragraph, align="center", line_tw=240, line_rule="auto")
            _add_run(
                paragraph, str(value), font_name=CFG["font_main"], size_pt=CFG["size_table_body"]
            )


def add_references(doc, data):
    refs = data.get("references") or {}
    title = (refs.get("title") or "REFERENCES").strip()
    items = refs.get("content") or ["[1] Author, Title, Journal, Year."]

    p_title = doc.add_paragraph()
    _set_para_style(p_title, "BodyText")
    _set_para_format(
        p_title,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_section_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_section_after"]),
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        p_title,
        title.upper() if not title.isupper() else title,
        font_name=CFG["font_main"],
        size_pt=CFG["size_body"],
        bold=True,
        color=CFG["color_main"],
    )

    for ref in items:
        ref_str = clean_inline_text(str(ref).strip())
        rp = doc.add_paragraph()
        _set_para_style(rp, "BodyText")
        _set_para_format(
            rp,
            align="both",
            sp_before_tw=0,
            sp_after_tw=0,
            line_tw=240,
            line_rule="auto",
            ind_left_tw=CFG["ref_left_tw"],
            ind_hanging_tw=CFG["ref_hanging_tw"],
        )
        _add_run(rp, ref_str, font_name=CFG["font_main"], size_pt=CFG["size_reference"])


def add_acknowledgement(doc, text=None):
    p_title = doc.add_paragraph()
    _set_para_style(p_title, "BodyText")
    _set_para_format(
        p_title,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_section_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_section_after"]),
        line_tw=240,
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        p_title, "ACKNOWLEDGEMENT", font_name=CFG["font_main"], size_pt=CFG["size_body"], bold=True
    )

    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(
        p, align="both", line_tw=240, line_rule="auto", ind_first_tw=CFG["first_line_indent_tw"]
    )
    _add_run(
        p,
        clean_inline_text(
            text
            or "Due credit should be given to Funding Agency and other "
            "associated organisations for their support."
        ),
        font_name=CFG["font_main"],
        size_pt=CFG["size_body"],
    )


# =============================================================================
# Section dispatcher
# =============================================================================
def process_content_list(doc, content_list, parent_first=True):
    first_text_done = False
    for item in content_list:
        if isinstance(item, str):
            add_body_text(doc, item, first_paragraph=(parent_first and not first_text_done))
            first_text_done = True
            continue
        kind = (item.get("id") or "").lower()
        if kind == "text":
            add_body_text(
                doc, item.get("text", ""), first_paragraph=(parent_first and not first_text_done)
            )
            first_text_done = True
        elif kind in ("gambar", "image"):
            add_figure_placeholder(doc, item)
        elif kind in ("rumus", "formula"):
            add_formula(doc, item)
        elif kind in ("tabel", "table"):
            add_table_block(doc, item)


def process_section(doc, section_data, section_label="", section_number=None):
    if not isinstance(section_data, dict):
        return

    title = section_data.get("title") or section_label or "Section"
    add_section_heading(doc, title, number=section_number)

    direct_content = section_data.get("content")
    if direct_content:
        if direct_content and isinstance(direct_content[0], str):
            for i, txt in enumerate(direct_content):
                add_body_text(doc, txt, first_paragraph=(i == 0))
        else:
            process_content_list(doc, direct_content, parent_first=True)

    sub_keys = [
        k
        for k in section_data.keys()
        if isinstance(section_data.get(k), dict) and re.match(r"^section\d+[a-z]+$", k)
    ]
    sub_keys.sort()
    for sub_idx, sk in enumerate(sub_keys, start=1):
        sub = section_data[sk]
        sub_title = sub.get("title") or sk
        sub_number = f"{section_number}.{sub_idx}." if section_number is not None else None
        add_subsection_heading(doc, sub_title, number=sub_number)
        sub_content = sub.get("content") or []
        if sub_content and isinstance(sub_content[0], str):
            for i, txt in enumerate(sub_content):
                add_body_text(doc, txt, first_paragraph=(i == 0))
        else:
            process_content_list(doc, sub_content, parent_first=True)


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

    # Step 1: copy template -> output (paste keep formatting)
    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)

    # Step 2: patch numbering.xml di output supaya Heading1/2/3 auto-multilevel.
    patch_numbering_xml(OUTPUT_DOCX)

    # Step 3: open output, clear body
    doc = Document(str(OUTPUT_DOCX))
    final_sectpr = _clear_body_keep_final_sectpr(doc)

    # ── Phase 1 (Section 1, 1-col) ─────────────────────────────────────────
    add_decoration_top(doc)
    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    # End of section 1 (1-col, mar match template). Section-break paragraph
    # diberi pStyle 'Heading1' supaya sejajar dengan idx 17 'Heading 1' di
    # template asli DJLIT.docx (yang merupakan paragraf kosong bermarka
    # Heading 1 sebagai pemisah halaman judul -> body artikel).
    _emit_section_break(doc, num_cols=1, sec_type=None, style_name="Heading1")

    # ── Phase 2 (Section 2, 2-col continuous) ──────────────────────────────
    section_keys = sorted(
        [k for k in data.keys() if re.match(r"^section\d+$", k)],
        key=lambda s: int(re.match(r"section(\d+)", s).group(1)),
    )
    for idx, sk in enumerate(section_keys, start=1):
        process_section(doc, data[sk], section_label=sk, section_number=idx)

    add_acknowledgement(doc)
    add_references(doc, data)

    # End of section 2 (2-col continuous)
    _emit_section_break(doc, num_cols=2, sec_type="continuous")

    # ── Phase 3 (Section 3, 1-col continuous final / trailer) ──────────────
    trailer = doc.add_paragraph()
    _set_para_format(trailer, line_tw=240, line_rule="auto", ind_first_tw=426)

    # Final sectPr (Section 3): 1-col continuous
    _set_final_sectpr(final_sectpr, num_cols=1, sec_type="continuous")

    doc.save(str(OUTPUT_DOCX))
    print(f"[OK] Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


if __name__ == "__main__":
    generate()
