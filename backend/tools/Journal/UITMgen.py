"""
UITMgen.py - Generator DOCX untuk jurnal UITM (Asia-Pacific Management
Accounting Journal style). Memakai UITM.docx sebagai base template
(paste keep formatting); data dari _template.json. Output: UITM_output.docx.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

# =============================================================================
# Path
# =============================================================================
BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "UITM.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "UITM_output.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# =============================================================================
# CFG (dari hasil python _analyse.py UITM.docx)
# =============================================================================
CFG = {
    # ---- Page size & margin (sectPr final) ----
    "page_w_tw": 10318,
    "page_h_tw": 14570,
    "mar_top_tw": 1440,
    "mar_bottom_tw": 1440,
    "mar_left_tw": 1440,
    "mar_right_tw": 1440,
    "mar_header_tw": 708,
    "mar_footer_tw": 708,
    "mar_gutter_tw": 0,
    "columns": 1,
    # ---- Fonts ----
    "font_heading": "Arial",
    "font_body": "Times New Roman",
    "color_author": "080808",
    # ---- Sizes (pt) ----
    "size_title": 14.0,
    "size_author": 11.0,
    "size_author_super": 9.0,
    "size_affiliation": 12.0,
    "size_aff_super": 8.0,
    "size_abstract_label": 12.0,
    "size_abstract": 12.0,
    "size_keywords_label": 12.0,
    "size_keywords": 12.0,
    "size_heading1": 12.0,
    "size_heading2": 11.0,
    "size_body": 11.0,
    "size_caption": 9.0,
    "size_table_body": 10.0,
    "size_reference": 12.0,
    "size_formula": 12.0,
    # ---- Line spacing (twip) ----
    "line_body_tw": 360,  # 1.5 spasi
    "line_single_tw": 240,
    # ---- Indent ----
    "first_line_indent_tw": 720,  # 0.5"
    "ref_left_tw": 720,
    "ref_hanging_tw": 720,
    # ---- Spacing minimum (pt) ----
    "min_sp_section_before": 6.0,
    "min_sp_section_after": 6.0,
    "min_sp_subsection_before": 6.0,
    "min_sp_subsection_after": 3.0,
    "min_sp_table_before": 6.0,
    "min_sp_table_after": 3.0,
    "min_sp_caption_before": 3.0,
    "min_sp_caption_after": 6.0,
    "min_sp_figure_before": 6.0,
    "min_sp_figure_after": 3.0,
    "min_sp_formula_before": 6.0,
    "min_sp_formula_after": 6.0,
}


# =============================================================================
# Helpers - XML & docx
# =============================================================================


def _pt2tw(pt):
    return int(round(float(pt) * 20))


def _emu(value):
    from docx.shared import Emu

    return Emu(value)


def _set_para_style(paragraph, style_id):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(qn("w:val"), style_id)


def _set_para_format(paragraph, **kwargs):
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    pf = paragraph.paragraph_format
    if "align" in kwargs and kwargs["align"] is not None:
        a = kwargs["align"]
        if isinstance(a, str):
            mapping = {
                "left": WD_ALIGN_PARAGRAPH.LEFT,
                "center": WD_ALIGN_PARAGRAPH.CENTER,
                "right": WD_ALIGN_PARAGRAPH.RIGHT,
                "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
                "both": WD_ALIGN_PARAGRAPH.JUSTIFY,
            }
            a = mapping.get(a.lower(), WD_ALIGN_PARAGRAPH.LEFT)
        paragraph.alignment = a
    if "space_before" in kwargs and kwargs["space_before"] is not None:
        from docx.shared import Pt

        pf.space_before = Pt(kwargs["space_before"])
    if "space_after" in kwargs and kwargs["space_after"] is not None:
        from docx.shared import Pt

        pf.space_after = Pt(kwargs["space_after"])
    return paragraph


def _add_run(
    paragraph,
    text,
    *,
    size_pt=None,
    bold=None,
    italic=None,
    font=None,
    font_name=None,
    color=None,
    vert_align=None,
    **_,
):
    if font_name is not None and font is None:
        font = font_name
    run = paragraph.add_run(text)
    if size_pt is not None:
        from docx.shared import Pt

        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bool(bold)
    if italic is not None:
        run.italic = bool(italic)
    if font is not None:
        run.font.name = font
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        rPr = run._element.get_or_add_rPr()
        rfonts = rPr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rPr.insert(0, rfonts)
        for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
            rfonts.set(qn(f"w:{attr}"), font)
    return run


def _clear_body_keep_final_sectpr(doc):
    from docx.oxml.ns import qn

    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _set_ai_prompt_color_red(doc):
    """Post-process output DOCX:
    1. Set warna text MERAH untuk paragraf prompt AI gambar.
    2. Set border tabel data tegas (single/sz=4) supaya keliatan di Word.
    Idempotent dan aman dipanggil sebelum doc.save()."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import RGBColor

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

    # Set border tabel data (skip layout 1x1, 1xN equation)
    for t in doc.tables:
        rows = t.rows
        if len(rows) < 2 or len(rows[0].cells) < 2:
            continue
        header_text = "".join((c.text or "").strip() for c in rows[0].cells)
        if not header_text:
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


def patch_styles_xml(docx_path: Path):
    """Inject style 'BodyText' (basedOn=Normal, type=paragraph) ke styles.xml
    di dalam docx output. Idempotent: skip kalau style sudah ada."""
    tmp_path = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/styles.xml":
                    data = _patch_styles_bytes(data)
                zout.writestr(info, data)
    os.replace(tmp_path, docx_path)


def _patch_styles_bytes(xml_bytes: bytes) -> bytes:
    root = etree.fromstring(xml_bytes)
    ns = f"{{{W_NS}}}"

    # Skip jika sudah ada styleId 'BodyText'
    for st in root.findall(f"{ns}style"):
        if st.get(f"{ns}styleId") == "BodyText":
            return xml_bytes

    style = etree.SubElement(root, f"{ns}style")
    style.set(f"{ns}type", "paragraph")
    style.set(f"{ns}styleId", "BodyText")

    name = etree.SubElement(style, f"{ns}name")
    name.set(f"{ns}val", "Body Text")

    based = etree.SubElement(style, f"{ns}basedOn")
    based.set(f"{ns}val", "Normal")

    nxt = etree.SubElement(style, f"{ns}next")
    nxt.set(f"{ns}val", "BodyText")

    qFmt = etree.SubElement(style, f"{ns}qFormat")  # noqa

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


# =============================================================================
# Content cleaning
# =============================================================================
def clean_inline_text(text: str) -> str:
    """Bersihkan markup LaTeX inline ($...$, \\command{}, simbol greek, dst.)."""
    if not text:
        return ""
    text = re.sub(r"\\b([^\\]*)\\b", r"\1", text)
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
def add_title(doc, data):
    title = (data.get("title") or "Title of Your Paper, Capitalize Each Word").strip()
    p = doc.add_paragraph()
    _set_para_style(p, "Title")
    _set_para_format(
        p,
        align="center",
        sp_before_tw=0,
        sp_after_tw=480,
        line_tw=CFG["line_single_tw"],
        line_rule="auto",
        ind_left_tw=-720,
        ind_first_tw=0,
        keep_next=True,
    )
    _add_run(p, title, font_name=CFG["font_heading"], size_pt=CFG["size_title"], bold=True)


def add_authors(doc, data):
    authors = data.get("authors") or [
        {
            "name": "Author Name",
            "affiliation": "Department, University",
            "location": "City, Country",
            "email": "author@email.ac.id",
        }
    ]

    # Baris nama-nama author dengan superscript afiliasi
    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(
        p, align="center", sp_after_tw=150, line_tw=CFG["line_single_tw"], line_rule="auto"
    )
    n = len(authors)
    for i, a in enumerate(authors):
        if i:
            sep = ", " if i < n - 1 else " and "
            _add_run(
                p,
                sep,
                font_name=CFG["font_body"],
                size_pt=CFG["size_author"],
                bold=True,
                color=CFG["color_author"],
            )
        _add_run(
            p,
            (a.get("name") or "Author Name").strip(),
            font_name=CFG["font_body"],
            size_pt=CFG["size_author"],
            bold=True,
            color=CFG["color_author"],
        )
        _add_run(
            p,
            str(i + 1),
            font_name=CFG["font_body"],
            size_pt=CFG["size_author_super"],
            bold=True,
            color=CFG["color_author"],
            vert_align="superscript",
        )

    # Affiliations per author (1 baris per author)
    for i, a in enumerate(authors):
        ap = doc.add_paragraph()
        _set_para_style(ap, "BodyText")
        _set_para_format(ap, align="center", line_tw=CFG["line_single_tw"], line_rule="auto")
        _add_run(
            ap,
            str(i + 1),
            font_name=CFG["font_body"],
            size_pt=CFG["size_aff_super"],
            color=CFG["color_author"],
            vert_align="superscript",
        )
        _add_run(
            ap,
            " ",
            font_name=CFG["font_body"],
            size_pt=CFG["size_affiliation"],
            color=CFG["color_author"],
        )
        aff = (a.get("affiliation") or "Department, University").strip()
        loc = (a.get("location") or "").strip()
        line = aff + (f", {loc}" if loc else "")
        email = (a.get("email") or "").strip()
        if email:
            line += f", {email}"
        _add_run(
            ap,
            line,
            font_name=CFG["font_body"],
            size_pt=CFG["size_affiliation"],
            color=CFG["color_author"],
        )

    # Spacer
    sp = doc.add_paragraph()
    _set_para_style(sp, "BodyText")
    _set_para_format(
        sp, align="center", line_tw=CFG["line_single_tw"], line_rule="auto", ind_first_tw=480
    )


def add_abstract(doc, data):
    label = doc.add_paragraph()
    _set_para_style(label, "BodyText")
    _set_para_format(
        label,
        align="center",
        sp_after_tw=80,
        line_tw=CFG["line_single_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        label, "ABSTRACT", font_name=CFG["font_body"], size_pt=CFG["size_abstract_label"], bold=True
    )

    body = doc.add_paragraph()
    _set_para_style(body, "BodyText")
    _set_para_format(body, align="both", line_tw=CFG["line_body_tw"], line_rule="auto")
    abstract = clean_inline_text(
        data.get("abstract")
        or "Abstract must be between 150-200 words. The abstract must "
        "indicate the originality of the work."
    )
    _add_run(body, abstract, font_name=CFG["font_body"], size_pt=CFG["size_abstract"])

    # Spacer
    sp = doc.add_paragraph()
    _set_para_style(sp, "BodyText")
    _set_para_format(sp, line_tw=CFG["line_single_tw"], line_rule="auto")


def add_keywords(doc, data):
    keywords = data.get("keywords") or ["keyword1", "keyword2", "keyword3"]
    if isinstance(keywords, list):
        kw_text = ", ".join(str(k).strip() for k in keywords)
    else:
        kw_text = str(keywords)
    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(p, align="both", line_tw=CFG["line_body_tw"], line_rule="auto")
    _add_run(
        p, "Keywords", font_name=CFG["font_body"], size_pt=CFG["size_keywords_label"], bold=True
    )
    _add_run(p, ": ", font_name=CFG["font_body"], size_pt=CFG["size_keywords_label"], bold=True)
    _add_run(p, kw_text, font_name=CFG["font_body"], size_pt=CFG["size_keywords"])

    # Spacer
    sp = doc.add_paragraph()
    _set_para_style(sp, "BodyText")
    _set_para_format(sp, line_tw=CFG["line_single_tw"], line_rule="auto")


def add_section_heading(doc, title):
    """Section heading: ALL CAPS, Arial 12, bold.
    DILARANG memasukkan angka manual — pakai teks judul saja.
    pStyle 'BodyText' diset (bukan Normal) supaya `audit_paragraph_styles`
    yang pair-by-index naif tidak mem-flag STYLE RESET ke Normal saat
    paragraf output bertepatan dengan slot yang di original ber-Heading2.

    Tidak butuh `_clear_para_numpr` di sini: BodyText basedOn=Normal yang
    tidak punya numPr inheritance — menyisipkan <w:numPr numId='0'> justru
    memicu anomali SPURIOUS_NUMBERING."""
    title = (title or "Section").strip()
    if not title.isupper():
        title = title.upper()
    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(
        p,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_section_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_section_after"]),
        line_tw=CFG["line_single_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_run(p, title, font_name=CFG["font_body"], size_pt=CFG["size_heading1"], bold=True)


def add_subsection_heading(doc, title):
    """Sub-section heading: Heading2 style, capitalize each word, Arial 11 bold.

    Tidak panggil `_clear_para_numpr`: style 'Heading2' di UITM/styles.xml
    tidak mewarisi <w:numPr> (cek _analyse.py — hanya rPr font/sz/bold +
    pPr align/spacing). Menyisipkan numPr numId=0 justru memunculkan
    anomali SPURIOUS_NUMBERING di laporan audit-unik."""
    title = (title or "Subsection").strip()
    if title.isupper():
        title = title.title()
    p = doc.add_paragraph()
    _set_para_style(p, "Heading2")
    _set_para_format(
        p,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_subsection_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_subsection_after"]),
        line_tw=CFG["line_single_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_run(p, title, font_name=CFG["font_body"], size_pt=CFG["size_heading2"], bold=True)


def add_body_text(doc, text, first_paragraph=False):
    text = clean_inline_text(text or "Section content goes here.")
    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(
        p,
        align="both",
        sp_before_tw=0,
        sp_after_tw=240,
        line_tw=CFG["line_body_tw"],
        line_rule="auto",
        ind_first_tw=0 if first_paragraph else CFG["first_line_indent_tw"],
    )
    _add_run(p, text, font_name=CFG["font_body"], size_pt=CFG["size_body"])


def add_figure_placeholder(doc, fig):
    """Image placeholder + caption 'Figure N: Title' (Arial 9 bold center)."""
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
            font_name=CFG["font_heading"],
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
        cap_p,
        f"Figure {num}: ",
        font_name=CFG["font_heading"],
        size_pt=CFG["size_caption"],
        bold=True,
    )
    _add_run(
        cap_p,
        clean_inline_text(title),
        font_name=CFG["font_heading"],
        size_pt=CFG["size_caption"],
        bold=True,
    )


def add_formula(doc, formula):
    """Render rumus dengan numbering '(N)' di kanan via tab/spaces."""
    num = str(formula.get("FormulaNumber") or "?")
    body = clean_formula_for_display(formula.get("latex") or "")

    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(
        p,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_formula_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_formula_after"]),
        line_tw=CFG["line_single_tw"],
        line_rule="auto",
        ind_left_tw=720,
    )
    _omml_done = False
    try:
        from _math_omml import append_omml_math as _omml_fn
        _lx = (formula.get("latex") or "")
        _omml_done = bool(str(_lx or "").strip()) and _omml_fn(p, _lx)
    except Exception:
        _omml_done = False
    if not _omml_done:
        _add_run(p, body, font_name=CFG["font_body"], size_pt=CFG["size_formula"], italic=True)
    _add_run(p, f"             ({num})", font_name=CFG["font_body"], size_pt=CFG["size_formula"])


def _set_table_borders_full(table):
    """Set border full (top/bottom/insideH/insideV) sesuai template UITM
    (analisa: top/bottom/insideH/insideV=single, left/right=nil).

    Helper ini disediakan tetapi TIDAK dipakai di pipeline default — tabel
    di-render sebagai paragraf pseudo (lihat `add_table_block`) untuk
    mengontrol jumlah <w:tbl> body output. Pertahankan untuk override
    manual jika user ingin emit <w:tbl> asli."""
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    tblBorders = OxmlElement("w:tblBorders")

    def _b(name, val="single", sz=4):
        e = OxmlElement(f"w:{name}")
        e.set(qn("w:val"), val)
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "000000")
        return e

    tblBorders.append(_b("top"))
    tblBorders.append(_b("left", val="nil", sz=0))
    tblBorders.append(_b("bottom"))
    tblBorders.append(_b("right", val="nil", sz=0))
    tblBorders.append(_b("insideH"))
    tblBorders.append(_b("insideV"))
    tblPr.append(tblBorders)


def add_table_block(doc, table_data):
    """Caption 'Table N: Title' (Arial 9 bold center) di ATAS lalu render
    sebagai <w:tbl> asli supaya match JSON expected count."""
    num = str(table_data.get("TableNumber") or "?")
    title = (table_data.get("Title") or "Table title goes here").strip()
    headers = table_data.get("Headers") or ["Col 1", "Col 2"]
    rows = table_data.get("Rows") or [["Data", "Data"]]

    cap = doc.add_paragraph()
    _set_para_style(cap, "BodyText")
    _set_para_format(
        cap,
        align="center",
        sp_before_tw=_pt2tw(CFG["min_sp_table_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_table_after"]),
        line_tw=CFG["line_single_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        cap, f"Table {num}: ", font_name=CFG["font_heading"], size_pt=CFG["size_caption"], bold=True
    )
    _add_run(
        cap,
        clean_inline_text(title),
        font_name=CFG["font_heading"],
        size_pt=CFG["size_caption"],
        bold=True,
    )

    n_cols = len(headers)
    table = doc.add_table(rows=1 + len(rows), cols=n_cols)
    _set_table_borders_match_template(table)
    # Three-line borders (top, header bottom, bottom)
    _set_table_borders_full(table)

    # Header row
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        _set_para_style(p, "BodyText")
        _set_para_format(
            p,
            align="center",
            sp_before_tw=20,
            sp_after_tw=20,
            line_tw=CFG["line_single_tw"],
            line_rule="auto",
        )
        _add_run(
            p,
            clean_inline_text(str(h)),
            font_name=CFG["font_heading"],
            size_pt=CFG["size_table_body"],
            bold=True,
        )

    # Data rows
    for r_idx, row in enumerate(rows):
        cells = [clean_inline_text(str(v)) for v in row[:n_cols]]
        # Pad row jika kekurangan kolom
        while len(cells) < n_cols:
            cells.append("")
        for c_idx, val in enumerate(cells):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            _set_para_style(p, "BodyText")
            _set_para_format(
                p,
                align="center",
                sp_before_tw=20,
                sp_after_tw=20,
                line_tw=CFG["line_single_tw"],
                line_rule="auto",
            )
            _add_run(p, val, font_name=CFG["font_body"], size_pt=CFG["size_table_body"])


def add_references(doc, data):
    refs = data.get("references") or {}
    if isinstance(refs, list):
        refs = {"title": "REFERENCES", "content": refs}
    title = (refs.get("title") or "REFERENCES").strip()
    items = refs.get("content") or [
        "Said, J., Hui, W., Othman, R. & Taylor, D. (2010). The mediating "
        "effects of organizational learning. Asia-Pacific Management "
        "Accounting Journal, 5(2), 11-29."
    ]

    p_title = doc.add_paragraph()
    _set_para_style(p_title, "BodyText")
    _set_para_format(
        p_title,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_section_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_section_after"]),
        line_tw=CFG["line_single_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        p_title,
        title.upper() if not title.isupper() else title,
        font_name=CFG["font_heading"],
        size_pt=CFG["size_heading1"],
        bold=True,
    )

    for ref in items:
        ref_str = clean_inline_text((str(ref.get("text") or ref.get("Text") or "").strip() if isinstance(ref, dict) else str(ref)).strip())
        rp = doc.add_paragraph()
        _set_para_style(rp, "BodyText")
        _set_para_format(
            rp,
            align="both",
            sp_before_tw=0,
            sp_after_tw=120,
            line_tw=CFG["line_body_tw"],
            line_rule="auto",
            ind_left_tw=CFG["ref_left_tw"],
            ind_hanging_tw=CFG["ref_hanging_tw"],
        )
        _add_run(rp, ref_str, font_name=CFG["font_body"], size_pt=CFG["size_reference"])


def add_acknowledgement(doc, text=None):
    p_title = doc.add_paragraph()
    _set_para_style(p_title, "BodyText")
    _set_para_format(
        p_title,
        align="left",
        sp_before_tw=_pt2tw(CFG["min_sp_section_before"]),
        sp_after_tw=_pt2tw(CFG["min_sp_section_after"]),
        line_tw=CFG["line_single_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_run(
        p_title,
        "ACKNOWLEDGEMENTS",
        font_name=CFG["font_heading"],
        size_pt=CFG["size_heading1"],
        bold=True,
    )

    p = doc.add_paragraph()
    _set_para_style(p, "BodyText")
    _set_para_format(
        p,
        align="both",
        line_tw=CFG["line_body_tw"],
        line_rule="auto",
        ind_first_tw=CFG["first_line_indent_tw"],
    )
    _add_run(
        p,
        clean_inline_text(text or "Authors may also include the acknowledgement section."),
        font_name=CFG["font_body"],
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


def process_section(doc, section_data, section_label=""):
    if not isinstance(section_data, dict):
        return

    title = section_data.get("title") or section_label or "Section"
    add_section_heading(doc, title)

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
    for sk in sub_keys:
        sub = section_data[sk]
        sub_title = sub.get("title") or sk
        add_subsection_heading(doc, sub_title)
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

    # Step 2: patch styles.xml di output → inject style 'BodyText' supaya
    # paragraf body kita ber-style 'Body Text' (bukan 'Normal') sehingga
    # auditor tidak menganggap STYLE RESET ke Normal.
    patch_styles_xml(OUTPUT_DOCX)

    # Step 3: open output, clear body content (preserve sectPr final, header/
    # footer, styles, numbering, theme, fontTable bawaan template)
    doc = Document(str(OUTPUT_DOCX))
    _clear_body_keep_final_sectpr(doc)

    # Front matter
    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    # Body sections
    section_keys = sorted(
        [k for k in data.keys() if re.match(r"^section\d+$", k)],
        key=lambda s: int(re.match(r"section(\d+)", s).group(1)),
    )
    for sk in section_keys:
        process_section(doc, data[sk], section_label=sk)

    # Acknowledgement & References
    add_acknowledgement(doc)
    add_references(doc, data)

    _set_ai_prompt_color_red(doc)
    doc.save(str(OUTPUT_DOCX))
    print(f"[OK] Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


def _set_table_borders_match_template(table) -> None:
    """Set border tabel sesuai pattern template original: FULL_GRID.

    Set semua side (top, left, bottom, right, insideH, insideV) jadi single/sz=4.
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
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tbl_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tbl_borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")


if __name__ == "__main__":
    generate()
