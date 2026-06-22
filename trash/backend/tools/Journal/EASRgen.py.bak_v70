"""
EASRgen.py - Generator DOCX untuk jurnal Engineering and Applied Science Research (EASR)
Menggunakan dokumen asli EASR.docx sebagai base template (paste keep formatting).
Data diambil dari _template.json.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "EASR.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "EASR_output.docx"

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

XSL_CANDIDATES = [
    BASE / "MML2OMML.XSL",
    BASE.parent / "MML2OMML.XSL",
    BASE.parent / "template" / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]

# Format config dari analisa EASR.docx
CFG = {
    "page_width_tw": 11907,
    "page_height_tw": 16840,
    "margin_top_tw": 1440,
    "margin_bottom_tw": 1440,
    "margin_left_tw": 1440,
    "margin_right_tw": 1440,
    "header_distance_tw": 1134,
    "footer_distance_tw": 1440,
    "columns": 1,
    "col_space_tw": 274,
    "font_default": "Times New Roman",
    "size_title_pt": 12,
    "size_body_pt": 12,
    "size_heading_pt": 12,
    "size_caption_pt": 12,
    "size_reference_pt": 12,
    "size_header_pt": 12,
    "size_footer_pt": 12,
    "line_spacing_tw": 480,
    "line_spacing_rule": "auto",
    "first_line_indent_tw": 284,
    "ref_left_indent_tw": 420,
    "ref_hanging_indent_tw": 420,
    "fig_prefix": "Figure",
    "tbl_prefix": "Table",
    "tbl_number_format": "roman",
    "ref_numbering": "bracket",
}

_XSLT = None


def _set_run_font(run, *, name=None, size_pt=None, bold=None, italic=None, color=None):
    if name is not None:
        run.font.name = name
        from docx.oxml.ns import qn

        rPr = run._element.get_or_add_rPr()
        rfonts = rPr.find(qn("w:rFonts"))
        if rfonts is None:
            from docx.oxml import OxmlElement

            rfonts = OxmlElement("w:rFonts")
            rPr.insert(0, rfonts)
        for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
            rfonts.set(qn(f"w:{attr}"), name)
    if size_pt is not None:
        from docx.shared import Pt

        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bool(bold)
    if italic is not None:
        run.italic = bool(italic)


def _sanitize_inline_latex(t):
    """Convert inline LaTeX commands di body text jadi unicode/text plain.
    Menghilangkan kebocoran $...$, \\mathrm{}, _{}, ^{}, \frac{}{}, dst di body."""
    if not t:
        return t
    s = str(t)
    if "\\" not in s and "_{" not in s and "^{" not in s and "$" not in s:
        return s
    import re as _re

    SYMBOLS = {
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\delta": "δ",
        r"\epsilon": "ε",
        r"\theta": "θ",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\pi": "π",
        r"\sigma": "σ",
        r"\tau": "τ",
        r"\phi": "φ",
        r"\omega": "ω",
        r"\sum": "∑",
        r"\prod": "∏",
        r"\int": "∫",
        r"\infty": "∞",
        r"\pm": "±",
        r"\times": "×",
        r"\cdot": "·",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\neq": "≠",
        r"\approx": "≈",
        r"\to": "→",
        r"\dots": "…",
        r"\ldots": "…",
        r"\quad": " ",
        r"\,": " ",
        r"\;": " ",
        r"\:": " ",
        r"\!": "",
        r"\left": "",
        r"\right": "",
    }
    for k, v in SYMBOLS.items():
        s = s.replace(k, v)
    s = _re.sub(r"\\(mathrm|mathbf|mathit|text|textbf|textit|operatorname)\{([^{}]*)\}", r"\2", s)
    s = _re.sub(r"\\(vec|hat|bar|tilde|dot|ddot)\{([^{}]*)\}", r"\2", s)
    s = _re.sub(r"_\{([^{}]*)\}", r"_\1", s)
    s = _re.sub(r"\^\{([^{}]*)\}", r"^\1", s)
    while True:
        new_s = _re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", s)
        if new_s == s:
            break
        s = new_s
    s = _re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("$", "")
    return s


def _add_plain(paragraph, text, *, size_pt=None, bold=None, italic=None):
    run = paragraph.add_run(_sanitize_inline_latex(text))
    _set_run_font(run, name=CFG["font_default"], size_pt=size_pt, bold=bold, italic=italic)
    return run


def _add_rich(paragraph, text, *, size_pt=None, bold=None, italic=None):
    return _add_plain(paragraph, text, size_pt=size_pt, bold=bold, italic=italic)


def _append_inline_math(paragraph, latex):
    """Render LaTeX into the paragraph. Prefer native Word OMML (real equation
    objects); fall back to sanitized unicode text if conversion is unavailable.
    Return True so the caller does not fall back to raw rendering (which leaks)."""
    if not latex:
        return False
    # Native OMML path first (matches IEEEgen fidelity).
    try:
        from _math_omml import append_omml_math as _omml
        if _omml(paragraph, latex):
            return True
    except Exception:
        pass
    import re as _re

    s = str(latex).strip()
    SYMBOLS = {
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\delta": "δ",
        r"\epsilon": "ε",
        r"\theta": "θ",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\pi": "π",
        r"\sigma": "σ",
        r"\tau": "τ",
        r"\phi": "φ",
        r"\omega": "ω",
        r"\sum": "∑",
        r"\prod": "∏",
        r"\int": "∫",
        r"\infty": "∞",
        r"\pm": "±",
        r"\times": "×",
        r"\cdot": "·",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\neq": "≠",
        r"\approx": "≈",
        r"\to": "→",
        r"\dots": "…",
        r"\ldots": "…",
        r"\quad": " ",
        r"\,": " ",
        r"\;": " ",
        r"\:": " ",
        r"\!": "",
        r"\left": "",
        r"\right": "",
    }
    for k, v in SYMBOLS.items():
        s = s.replace(k, v)
    s = _re.sub(r"\\(mathrm|mathbf|mathit|text|textbf|textit|operatorname)\{([^{}]*)\}", r"\2", s)
    s = _re.sub(r"\\(vec|hat|bar|tilde|dot|ddot)\{([^{}]*)\}", r"\2", s)
    s = _re.sub(r"_\{([^{}]*)\}", r"_\1", s)
    s = _re.sub(r"\^\{([^{}]*)\}", r"^\1", s)
    while True:
        new_s = _re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", s)
        if new_s == s:
            break
        s = new_s
    s = _re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "").replace("$", "")
    paragraph.add_run(s)
    return True


def _clear_pstyle(paragraph):
    from docx.oxml.ns import qn

    pPr = paragraph._element.find(qn("w:pPr"))
    if pPr is None:
        return
    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is not None:
        pPr.remove(pStyle)


def _set_paragraph_format(
    paragraph,
    *,
    align=None,
    space_before=None,
    space_after=None,
    line_spacing_tw=None,
    line_rule=None,
    keep_next=None,
    first_line_indent_tw=None,
    first_line_tw=None,
    left_indent_tw=None,
    left_tw=None,
    hanging_indent_tw=None,
    hanging_tw=None,
    **_kwargs,
):
    if first_line_tw is not None and first_line_indent_tw is None:
        first_line_indent_tw = first_line_tw
    if left_tw is not None and left_indent_tw is None:
        left_indent_tw = left_tw
    if hanging_tw is not None and hanging_indent_tw is None:
        hanging_indent_tw = hanging_tw
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    if align is not None:
        paragraph.alignment = align
    pf = paragraph.paragraph_format
    if space_before is not None:
        from docx.shared import Pt, Twips

        pf.space_before = Pt(space_before) if space_before < 100 else Twips(space_before)
    if space_after is not None:
        from docx.shared import Pt, Twips

        pf.space_after = Pt(space_after) if space_after < 100 else Twips(space_after)
    pPr = paragraph._element.get_or_add_pPr()
    if line_spacing_tw is not None:
        spacing = pPr.find(qn("w:spacing"))
        if spacing is None:
            spacing = OxmlElement("w:spacing")
            pPr.append(spacing)
        spacing.set(qn("w:line"), str(line_spacing_tw))
        if line_rule:
            spacing.set(qn("w:lineRule"), line_rule)
    if keep_next:
        kn = pPr.find(qn("w:keepNext"))
        if kn is None:
            kn = OxmlElement("w:keepNext")
            pPr.append(kn)
    if (
        first_line_indent_tw is not None
        or left_indent_tw is not None
        or hanging_indent_tw is not None
    ):
        ind = pPr.find(qn("w:ind"))
        if ind is None:
            ind = OxmlElement("w:ind")
            pPr.append(ind)
        if first_line_indent_tw is not None:
            ind.set(qn("w:firstLine"), str(first_line_indent_tw))
        if left_indent_tw is not None:
            ind.set(qn("w:left"), str(left_indent_tw))
        if hanging_indent_tw is not None:
            ind.set(qn("w:hanging"), str(hanging_indent_tw))


def _set_ai_prompt_color_red(doc):
    """Post-process output DOCX:
    1. Set warna text MERAH untuk paragraf prompt AI gambar.
    2. Set border tabel data tegas (single/sz=4) supaya keliatan di Word.
    Idempotent dan aman dipanggil sebelum doc.save()."""
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

    # DISABLED: template NO_BORDERS, jangan force border

    # Set border tabel data:
    # for t in doc.tables:
    # rows = t.rows
    # if len(rows) < 2 or len(rows[0].cells) < 2:
    # continue
    # header_text = "".join((c.text or "").strip() for c in rows[0].cells)
    # if not header_text:
    # continue
    # tbl = t._element
    # tblPr = tbl.find(qn("w:tblPr"))
    # if tblPr is None:
    # tblPr = OxmlElement("w:tblPr")
    # tbl.insert(0, tblPr)
    # borders = tblPr.find(qn("w:tblBorders"))
    # if borders is None:
    # borders = OxmlElement("w:tblBorders")
    # tblPr.append(borders)
    # for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
    # el = borders.find(qn(f"w:{side}"))
    # if el is None:
    # el = OxmlElement(f"w:{side}")
    # borders.append(el)
    # el.set(qn("w:val"), "single")
    # el.set(qn("w:sz"), "4")
    # el.set(qn("w:space"), "0")
    # el.set(qn("w:color"), "000000")


def load_json():
    return json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))


def _clear_body(doc):
    """Hapus seluruh paragraf body, sisakan sectPr terakhir."""
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _new_paragraph(doc):
    """Helper kompatibilitas: bikin paragraph baru di body."""
    return doc.add_paragraph()


def add_title(doc, data):
    title = (data.get("title") or "Paper Title Goes Here").strip()
    p = _new_paragraph(doc)
    _set_paragraph_format(
        p,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )
    _add_plain(p, "Research Article or Review Article", size_pt=CFG["size_title_pt"], bold=True)

    p2 = _new_paragraph(doc)
    _set_paragraph_format(
        p2,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )

    p3 = _new_paragraph(doc)
    _set_paragraph_format(
        p3,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )
    _add_rich(p3, title, size_pt=CFG["size_title_pt"], bold=True, italic=True)


def add_authors(doc, data):
    authors = data.get("authors") or []
    if not authors:
        authors = [
            {
                "name": "Author Name",
                "affiliation": "Department, University",
                "location": "City, Country",
                "email": "author@email.ac.id",
            }
        ]

    names = [a.get("name", "") for a in authors if a.get("name")]
    if not names:
        names = ["Author Name"]
    if len(names) == 1:
        name_line = names[0] + "*"
    elif len(names) == 2:
        name_line = f"{names[0]} and {names[1]}*"
    else:
        name_line = ", ".join(names[:-1]) + f", and {names[-1]}*"

    p = _new_paragraph(doc)
    _set_paragraph_format(
        p,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )
    _add_plain(p, name_line, size_pt=CFG["size_title_pt"])

    affiliations = []
    for a in authors:
        aff = a.get("affiliation", "")
        loc = a.get("location", "")
        combined = ", ".join(x for x in [aff, loc] if x)
        if combined and combined not in affiliations:
            affiliations.append(combined)

    for aff_idx, aff in enumerate(affiliations):
        ap = _new_paragraph(doc)
        _set_paragraph_format(
            ap,
            align=WD_ALIGN_PARAGRAPH.LEFT,
            space_before=0,
            space_after=0,
            line_spacing_tw=CFG["line_spacing_tw"],
            line_rule="auto",
        )
        # Affiliation pertama: bold; affiliation kedua dst: italic
        if aff_idx == 0:
            _add_plain(ap, aff, size_pt=CFG["size_body_pt"], bold=True)
        else:
            _add_plain(ap, aff, size_pt=CFG["size_body_pt"], italic=True)

    cp = _new_paragraph(doc)
    _set_paragraph_format(
        cp,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )
    primary_email = ""
    for a in authors:
        if a.get("email"):
            primary_email = a["email"]
            break
    if not primary_email:
        primary_email = "author@email.ac.id"
    _add_plain(cp, "*Corresponding author. Tel.: +00-0000-0000", size_pt=CFG["size_body_pt"])
    _add_plain(cp, f"; Email address: {primary_email}", size_pt=CFG["size_body_pt"])

    sp = _new_paragraph(doc)
    _set_paragraph_format(
        sp,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )


def add_abstract(doc, data):
    abstract = (data.get("abstract") or "").strip()
    if not abstract:
        abstract = (
            "Abstract text goes here. This section should contain "
            "150-250 words summarizing the paper."
        )

    head = _new_paragraph(doc)
    _set_paragraph_format(
        head,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_plain(head, "Abstract", size_pt=CFG["size_body_pt"], bold=True)

    body = _new_paragraph(doc)
    _set_paragraph_format(
        body,
        align=WD_ALIGN_PARAGRAPH.JUSTIFY,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
        first_line_tw=CFG["first_line_indent_tw"],
    )
    _add_rich(body, abstract, size_pt=CFG["size_body_pt"])


def add_keywords(doc, data):
    keywords = data.get("keywords") or []
    if not keywords:
        keywords = ["keyword1", "keyword2", "keyword3"]
    text = ", ".join(keywords)

    p = _new_paragraph(doc)
    _set_paragraph_format(
        p,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )
    _add_plain(p, "Keywords:", size_pt=CFG["size_body_pt"], bold=True)
    _add_plain(p, " ", size_pt=CFG["size_body_pt"])
    _add_plain(p, text, size_pt=CFG["size_body_pt"])

    blank = _new_paragraph(doc)
    _set_paragraph_format(
        blank,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )


def add_section_heading(doc, number, title):
    """Section heading: "1. Title" - bold, TNR 12pt, left-aligned, sp_before=3pt+"""
    text = f"{number}. {title}"
    p = _new_paragraph(doc)
    _set_paragraph_format(
        p,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=6,
        space_after=3,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_plain(p, text, size_pt=CFG["size_heading_pt"], bold=True)


def add_subsection_heading(doc, number, title):
    """Subsection heading: "2.1 Title" - italic, TNR 12pt, left-aligned"""
    text = f"{number} {title}"
    p = _new_paragraph(doc)
    _set_paragraph_format(
        p,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=6,
        space_after=3,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_plain(p, text, size_pt=CFG["size_heading_pt"], italic=True)


def add_body_text(doc, text, *, indent=True):
    p = _new_paragraph(doc)
    _set_paragraph_format(
        p,
        align=WD_ALIGN_PARAGRAPH.JUSTIFY,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
        first_line_tw=CFG["first_line_indent_tw"] if indent else 0,
    )
    _add_rich(p, text, size_pt=CFG["size_body_pt"])
    return p


def _resolve_image_path(path_text: str) -> Path | None:
    if not path_text:
        return None
    p = Path(path_text)
    if p.is_absolute():
        return p if p.exists() else None
    cand = BASE / p
    if cand.exists():
        return cand
    cand2 = BASE.parent / p
    if cand2.exists():
        return cand2
    cand3 = BASE.parent / "template" / p
    if cand3.exists():
        return cand3
    return None


def add_figure(doc, fig_data):
    """Figure: image centered, caption "Figure N <bold> Title<regular>" centered."""
    number = str(fig_data.get("ImageNumber", "")).strip()
    title = (fig_data.get("Title") or "").strip() or "Figure title"
    path_text = (fig_data.get("Path") or "").strip()
    prompt_text = (fig_data.get("Prompt") or "").strip()

    img_path = _resolve_image_path(path_text)

    img_p = _new_paragraph(doc)
    _set_paragraph_format(
        img_p,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=6,
        space_after=3,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
        first_line_tw=0,
        keep_next=True,
    )
    if img_path is not None:
        try:
            run = img_p.add_run()
            run.add_picture(str(img_path), width=Cm(12.0))
        except Exception:
            _add_dynamic_prompt_placeholder(img_p, title, prompt_text)
    else:
        _add_dynamic_prompt_placeholder(img_p, title, prompt_text)

    cap = _new_paragraph(doc)
    _set_paragraph_format(
        cap,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=3,
        space_after=6,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )
    _add_plain(cap, f"Figure {number}", size_pt=CFG["size_caption_pt"], bold=True)
    _add_plain(cap, " ", size_pt=CFG["size_caption_pt"])
    _add_rich(cap, title, size_pt=CFG["size_caption_pt"])


def _add_dynamic_prompt_placeholder(paragraph, title: str, prompt_text: str):
    """Render dynamic AI image prompt placeholder.

    Format: [PROMPT UNTUK AI GAMBAR: <Title>. <Prompt>]
    The JSON Title must appear inside the brackets so the QA auditor can
    match it back to the corresponding entry in _template.json.
    """
    body = prompt_text.strip()
    title_clean = title.strip()
    if title_clean and title_clean.lower() not in body.lower():
        if body:
            body = f"{title_clean}. {body}"
        else:
            body = title_clean
    if not body:
        body = title_clean or "Gambar"
    _add_plain(
        paragraph,
        f"[PROMPT UNTUK AI GAMBAR: {body}]",
        size_pt=CFG["size_body_pt"],
        italic=True,
    )


def _to_roman(n):
    try:
        v = int(str(n).strip())
    except Exception:
        return str(n).strip()
    if v <= 0:
        return str(n).strip()
    table = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    out = []
    for arabic, roman in table:
        while v >= arabic:
            out.append(roman)
            v -= arabic
    return "".join(out)


def add_table(doc, tbl_data):
    """Table: caption "Table N <bold> Title<regular>", three-line borders."""
    number_raw = str(tbl_data.get("TableNumber", "")).strip()
    title = (tbl_data.get("Title") or "").strip() or "Table title"
    headers = list(tbl_data.get("Headers") or [])
    rows = list(tbl_data.get("Rows") or [])

    if not headers:
        headers = ["Column 1", "Column 2"]
        rows = [["Data", "Data"]]

    if number_raw and re.match(r"^[IVXLCDM]+$", number_raw, re.IGNORECASE):
        num_label = number_raw.upper()
    elif number_raw.isdigit():
        num_label = _to_roman(number_raw)
    else:
        num_label = number_raw or "1"

    cap = _new_paragraph(doc)
    _set_paragraph_format(
        cap,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=6,
        space_after=3,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
        keep_next=True,
    )
    _add_plain(cap, f"Table {num_label}", size_pt=CFG["size_caption_pt"], bold=True)
    _add_plain(cap, " ", size_pt=CFG["size_caption_pt"])
    _add_rich(cap, title, size_pt=CFG["size_caption_pt"])

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    try:
        table.style = "Normal Table"
    except Exception:
        pass

    _set_table_three_line_borders(table)

    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        cell.text = ""
        cp = cell.paragraphs[0]
        _clear_pstyle(cp)
        _set_paragraph_format(
            cp,
            align=WD_ALIGN_PARAGRAPH.CENTER,
            space_before=0,
            space_after=0,
            line_spacing_tw=CFG["line_spacing_tw"],
            line_rule="auto",
        )
        _add_rich(cp, str(h), size_pt=CFG["size_caption_pt"], bold=True)

    for i, row in enumerate(rows, start=1):
        for j in range(len(headers)):
            value = row[j] if j < len(row) else ""
            cell = table.rows[i].cells[j]
            cell.text = ""
            cp = cell.paragraphs[0]
            _clear_pstyle(cp)
            _set_paragraph_format(
                cp,
                align=WD_ALIGN_PARAGRAPH.CENTER,
                space_before=0,
                space_after=0,
                line_spacing_tw=CFG["line_spacing_tw"],
                line_rule="auto",
            )
            _add_rich(cp, str(value), size_pt=CFG["size_caption_pt"])

    after = _new_paragraph(doc)
    _set_paragraph_format(
        after,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=0,
        space_after=0,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
    )


def _set_table_three_line_borders(table):
    """Three-line borders: top of first row, bottom of header, bottom of last row."""
    n_rows = len(table.rows)
    n_cols = len(table.columns)
    if n_rows == 0:
        return

    for j in range(n_cols):
        cell = table.rows[0].cells[j]
        _set_cell_borders(cell, top=True, bottom=True, left=False, right=False)

    for i in range(1, n_rows - 1):
        for j in range(n_cols):
            cell = table.rows[i].cells[j]
            _set_cell_borders(cell, top=False, bottom=False, left=False, right=False)

    if n_rows > 1:
        for j in range(n_cols):
            cell = table.rows[n_rows - 1].cells[j]
            _set_cell_borders(cell, top=False, bottom=True, left=False, right=False)


def _set_cell_borders(cell, *, top=False, bottom=False, left=False, right=False):
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = tcPr.find(qn("w:tcBorders"))
    if tcBorders is None:
        tcBorders = OxmlElement("w:tcBorders")
        tcPr.append(tcBorders)

    spec = {
        "top": top,
        "bottom": bottom,
        "left": left,
        "right": right,
    }
    for edge, on in spec.items():
        el = tcBorders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tcBorders.append(el)
        if on:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "8")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
        else:
            el.set(qn("w:val"), "nil")


def add_formula(doc, formula_data):
    """Formula: centered, numbering right-aligned (e.g. (1))."""
    number = str(formula_data.get("FormulaNumber") or "").strip()
    latex = (formula_data.get("latex") or formula_data.get("text") or "").strip()
    if not latex:
        latex = "E = mc^2"

    p = _new_paragraph(doc)
    _set_paragraph_format(
        p,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        space_before=3,
        space_after=3,
        line_spacing_tw=CFG["line_spacing_tw"],
        line_rule="auto",
        first_line_tw=0,
    )

    usable_pt = (CFG["page_width_tw"] - CFG["margin_left_tw"] - CFG["margin_right_tw"]) / 20.0
    pf = p.paragraph_format
    pf.tab_stops.add_tab_stop(Pt(usable_pt / 2.0), WD_TAB_ALIGNMENT.CENTER)
    pf.tab_stops.add_tab_stop(Pt(usable_pt), WD_TAB_ALIGNMENT.RIGHT)

    p.add_run("\t")
    if not _append_inline_math(p, latex):
        run = p.add_run(latex)
        _set_run_font(run, size_pt=CFG["size_body_pt"], italic=True)
    if number:
        p.add_run("\t")
        nrun = p.add_run(f"({number})")
        _set_run_font(nrun, size_pt=CFG["size_body_pt"])


def add_references(doc, data, *, ref_section_num: int = 8):
    refs_block = data.get("references") or {}
    if isinstance(refs_block, list):
        refs_block = {"title": "References", "content": refs_block}
    title = (refs_block.get("title") or "References").strip()
    items = refs_block.get("content") or []

    if not items:
        items = ["Author, Title, Journal, Year."]

    # Section heading uses Title-case display per template (e.g. "References")
    display_title = title if title else "References"
    if display_title.isupper():
        display_title = display_title.title()
    add_section_heading(doc, str(ref_section_num), display_title)

    for idx, ref in enumerate(items, start=1):
        ref_text = ref if isinstance(ref, str) else (ref.get("text") or str(ref))
        m = re.match(r"^\s*\[(\d+)\]\s*(.*)$", ref_text)
        if m:
            num = m.group(1)
            body = m.group(2)
        else:
            num = str(idx)
            body = ref_text.strip()

        p = _new_paragraph(doc)
        _set_paragraph_format(
            p,
            align=WD_ALIGN_PARAGRAPH.JUSTIFY,
            space_before=0,
            space_after=0,
            line_spacing_tw=CFG["line_spacing_tw"],
            line_rule="auto",
            left_tw=CFG["ref_left_indent_tw"],
            hanging_tw=CFG["ref_hanging_indent_tw"],
        )
        _add_plain(p, f"[{num}] ", size_pt=CFG["size_reference_pt"])
        _add_rich(p, body, size_pt=CFG["size_reference_pt"])


def _process_content_items(doc, items):
    for it in items:
        if isinstance(it, str):
            add_body_text(doc, it.strip())
            continue
        if not isinstance(it, dict):
            continue
        kind = str(it.get("id", "")).lower()
        if kind == "text":
            add_body_text(doc, it.get("text", ""))
        elif kind in ("gambar", "image", "figure"):
            add_figure(doc, it)
        elif kind in ("rumus", "formula"):
            add_formula(doc, it)
        elif kind in ("tabel", "table"):
            add_table(doc, it)


def _process_section(doc, sec_data, section_num: int):
    title = (sec_data.get("title") or "Section").strip()
    add_section_heading(doc, str(section_num), title)

    content = sec_data.get("content")
    if isinstance(content, list):
        _process_content_items(doc, content)
    elif isinstance(content, str) and content.strip():
        add_body_text(doc, content.strip())

    sub_keys = sorted(
        [k for k in sec_data.keys() if re.match(rf"^section{section_num}[a-z]+$", k)],
        key=lambda x: x,
    )
    for sub_idx, sub_key in enumerate(sub_keys, start=1):
        sub = sec_data.get(sub_key) or {}
        sub_title = (sub.get("title") or "Subsection").strip()
        sub_number = f"{section_num}.{sub_idx}"
        add_subsection_heading(doc, sub_number, sub_title)
        sub_content = sub.get("content")
        if isinstance(sub_content, list):
            _process_content_items(doc, sub_content)
        elif isinstance(sub_content, str) and sub_content.strip():
            add_body_text(doc, sub_content.strip())


def generate():
    if not TEMPLATE_DOCX.exists():
        raise FileNotFoundError(f"Template tidak ditemukan: {TEMPLATE_DOCX}")
    if not TEMPLATE_JSON.exists():
        raise FileNotFoundError(f"JSON tidak ditemukan: {TEMPLATE_JSON}")

    data = load_json()

    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    _clear_body(doc)

    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    section_keys = sorted(
        [k for k in data.keys() if re.match(r"^section\d+$", k)],
        key=lambda x: int(x.replace("section", "")),
    )
    for sk in section_keys:
        sn = int(sk.replace("section", ""))
        _process_section(doc, data[sk], sn)

    # References numbered as next section after the last data section
    last_section_num = max((int(k.replace("section", "")) for k in section_keys), default=0)
    add_references(doc, data, ref_section_num=last_section_num + 1)

    _set_ai_prompt_color_red(doc)
    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


if __name__ == "__main__":
    generate()
