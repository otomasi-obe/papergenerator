"""
IJBgen.py — Generator DOCX untuk Gadjah Mada International Journal of Business (IJB).
Menggunakan dokumen asli IJB.docx sebagai base template (paste keep formatting).
Data diambil dari _template.json.

Format ringkas (hasil analisa _analyse.py terhadap IJB.docx):
- Page A4, margin 1" semua sisi, header=709tw, footer=709tw, kolom tunggal.
- Title: Heading1 (Times New Roman 18pt bold), centered.
- Author/affiliation: Times New Roman 12pt centered.
- Abstract label: Heading3 12pt bold; isi: NoSpacing (TNR 12pt italic justify).
- Keywords label+isi: Heading3 12pt; sectionnya tanpa numbering (template tak pakai).
- Section heading: Heading2 (TNR 14pt bold) — tanpa nomor (preserve case JSON).
- Subsection heading: Heading5 (TNR 12pt bold) — tanpa nomor.
- Body text: Heading4 (TNR 12pt, justify, line=360/1.5x, sp_before/after=120tw).
- Figure caption: TNR 12pt centered, "Gbr. N." bold + judul regular.
- Table title: TNR 12pt centered, "Tabel N." bold + judul regular.
- Tabel: three-line border (top, bottom, insideH).
- Rumus: TNR/Cambria Math centered + numbering (N) rata kanan.
- Reference list: TNR 12pt justify, ind_left=720 hanging=720, sp_after=160.
- Footer: page number rata kanan (sudah ada pada template asli).
"""
import json
import shutil
import re
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "IJB.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "IJB_output.docx"

# ══════════════════════════════════════════════════════════════
# KONFIGURASI FORMAT (hasil analisa _analyse.py)
# ══════════════════════════════════════════════════════════════
CFG = {
    # Page setup (A4 portrait)
    "page_width_tw": 11906,
    "page_height_tw": 16838,
    "margin_top_tw": 1440,
    "margin_bottom_tw": 1440,
    "margin_left_tw": 1440,
    "margin_right_tw": 1440,
    "margin_gutter_tw": 0,
    "header_distance_tw": 709,
    "footer_distance_tw": 709,
    "columns": 1,
    "col_space_tw": 708,

    # Fonts (IJB universally Times New Roman)
    "font_body": "Times New Roman",
    "font_title": "Times New Roman",
    "font_heading": "Times New Roman",
    "font_caption": "Times New Roman",
    "font_reference": "Times New Roman",

    # Sizes (pt) — diambil dari styles.xml IJB
    "size_title": 18,        # Heading1
    "size_body": 12,         # Heading4 / NoSpacing / docBody
    "size_heading1": 14,     # Heading2 (Section)
    "size_heading2": 12,     # Heading5 (Subsection)
    "size_caption": 12,
    "size_reference": 12,
    "size_header": 10,
    "size_footer": 10,
    "size_abstract_label": 12,

    # Heading numbering — IJB pakai plain (tanpa nomor)
    "section_heading_format": "plain",
    "section_heading_upper": False,
    "subsection_format": "plain",

    # Figure / Table prefix — JSON pakai bahasa Indonesia
    "fig_prefix": "Gbr.",
    "tbl_prefix": "Tabel",
    "tbl_number_format": "roman",  # data JSON sudah memakai I/II/III

    # Tabel border
    "table_borders": "three_line",

    # Line spacing body 1.5 (Heading4 line=360 lineRule=auto)
    "line_spacing_body": 360,
    "line_spacing_rule": "auto",

    # Indent body
    "first_line_indent_tw": 360,

    # Reference indent
    "ref_left_indent_tw": 720,
    "ref_hanging_indent_tw": 720,
    "ref_after_tw_pt": 8,  # ~160tw → 8pt
}

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XSL_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL"),
    BASE / "MML2OMML.XSL",
    BASE.parent / "MML2OMML.XSL",
]
_XSLT = None


def _append_inline_math(paragraph, latex):
    """Sanitize LaTeX commands jadi text plain dan emit ke paragraph.
    Return True supaya caller tidak fallback ke render mentah (yang bocor)."""
    if not latex:
        return False
    import re as _re
    s = str(latex).strip()
    SYMBOLS = {
        r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
        r"\epsilon": "ε", r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ",
        r"\pi": "π", r"\sigma": "σ", r"\tau": "τ", r"\phi": "φ",
        r"\omega": "ω", r"\sum": "∑", r"\prod": "∏", r"\int": "∫",
        r"\infty": "∞", r"\pm": "±", r"\times": "×", r"\cdot": "·",
        r"\leq": "≤", r"\geq": "≥", r"\neq": "≠", r"\approx": "≈",
        r"\to": "→", r"\dots": "…", r"\ldots": "…",
        r"\quad": " ", r"\,": " ", r"\;": " ", r"\:": " ", r"\!": "",
        r"\left": "", r"\right": "",
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


def _set_ai_prompt_color_red(doc):
    """Post-process output DOCX:
    1. Set warna text MERAH untuk paragraf prompt AI gambar.
    2. Set border tabel data tegas (single/sz=4) supaya keliatan di Word.
    Idempotent dan aman dipanggil sebelum doc.save()."""
    from docx.shared import RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
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
            el.set(qn("w:val"), "single" if side in ("top", "bottom", "insideH") else "nil" if side in ("top", "bottom", "insideH") else "nil" if side in ("top", "bottom", "insideH") else "nil" if side in ("top", "bottom", "insideH") else "nil" if side in ("top", "bottom", "insideH") else "nil" if side in ("top", "bottom", "insideH") else "nil")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")

def load_json():
    with open(TEMPLATE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def set_run_font(run, font_name=None, size_pt=None, bold=None, italic=None, color=None):
    if font_name:
        run.font.name = font_name
        rpr = run._r.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.insert(0, rfonts)
        rfonts.set(qn("w:ascii"), font_name)
        rfonts.set(qn("w:hAnsi"), font_name)
        rfonts.set(qn("w:eastAsia"), font_name)
        rfonts.set(qn("w:cs"), font_name)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
        rpr = run._r.get_or_add_rPr()
        szcs = rpr.find(qn("w:szCs"))
        if szcs is None:
            szcs = OxmlElement("w:szCs")
            rpr.append(szcs)
        szcs.set(qn("w:val"), str(int(size_pt * 2)))
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor(*color) if isinstance(color, tuple) else color


def set_paragraph_spacing(paragraph, before=None, after=None, line=None, line_rule=None):
    pf = paragraph.paragraph_format
    if before is not None:
        pf.space_before = Pt(before)
    if after is not None:
        pf.space_after = Pt(after)
    if line is not None:
        ppr = paragraph._p.get_or_add_pPr()
        spacing = ppr.find(qn("w:spacing"))
        if spacing is None:
            spacing = OxmlElement("w:spacing")
            ppr.append(spacing)
        spacing.set(qn("w:line"), str(line))
        if line_rule:
            spacing.set(qn("w:lineRule"), line_rule)


def set_paragraph_indent(paragraph, left=None, right=None, first_line=None, hanging=None):
    ppr = paragraph._p.get_or_add_pPr()
    ind = ppr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        ppr.append(ind)
    if left is not None:
        ind.set(qn("w:left"), str(left))
    if right is not None:
        ind.set(qn("w:right"), str(right))
    if first_line is not None:
        ind.set(qn("w:firstLine"), str(first_line))
    if hanging is not None:
        ind.set(qn("w:hanging"), str(hanging))


def apply_style(paragraph, style_name):
    """Terapkan built-in style dari template dengan menulis pStyle XML."""
    ppr = paragraph._p.get_or_add_pPr()
    p_style = ppr.find(qn("w:pStyle"))
    if p_style is None:
        p_style = OxmlElement("w:pStyle")
        ppr.insert(0, p_style)
    p_style.set(qn("w:val"), style_name)


def clear_body(doc):
    """Hapus seluruh paragraf & tabel pada body, sisakan sectPr akhir."""
    body = doc._element.body
    for child in list(body):
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)


def add_empty_para(doc):
    p = doc.add_paragraph()
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    return p


def _normalize_text(text: str) -> str:
    text = text.replace("\\n", "\n")
    text = re.sub(r'\*\*(.+?)\*\*', r'\\b\1\\b', text, flags=re.DOTALL)
    text = re.sub(r'\*([^*\n]+?)\*', r'\\i\1\\i', text)
    return text


def _append_rich_text(paragraph, text: str, font_name=None, size_pt=None,
                      base_bold=False, base_italic=False):
    fn = font_name or CFG["font_body"]
    sz = size_pt or CFG["size_body"]
    normalized = _normalize_text(text)
    bold = base_bold
    italic = base_italic
    buffer = []
    index = 0

    def flush():
        nonlocal buffer
        content = "".join(buffer)
        buffer = []
        if content:
            run = paragraph.add_run(content)
            set_run_font(run, font_name=fn, size_pt=sz, bold=bold, italic=italic)

    while index < len(normalized):
        char = normalized[index]
        if char == "\n":
            flush()
            run = paragraph.add_run()
            run.add_break()
            index += 1
            continue
        if char == "\\" and index + 1 < len(normalized):
            cmd = normalized[index + 1]
            if cmd == "\\":
                buffer.append("\\")
                index += 2
                continue
            if cmd == "b":
                flush()
                bold = not bold
                index += 2
                continue
            if cmd == "i":
                flush()
                italic = not italic
                index += 2
                continue
        if char == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                flush()
                formula = normalized[index + 1:closing]
                if formula:
                    if not _append_inline_math(paragraph, formula):
                        run = paragraph.add_run(formula)
                        set_run_font(run, font_name=fn, size_pt=sz, italic=True)
                index = closing + 1
                continue
        buffer.append(char)
        index += 1
    flush()


# ══════════════════════════════════════════════════════════════
# CONTENT GENERATORS
# ══════════════════════════════════════════════════════════════

def add_title(doc, data):
    title_text = data.get("title", "Paper Title Goes Here")
    p = doc.add_paragraph()
    apply_style(p, "Heading1")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=0, after=12, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(title_text)
    set_run_font(run, font_name=CFG["font_title"], size_pt=CFG["size_title"], bold=True)


def add_authors(doc, data):
    authors = data.get("authors", [])
    if not authors:
        authors = [{
            "name": "Author Name",
            "affiliation": "Department, University",
            "location": "City, Country",
            "email": "author@email.ac.id",
        }]

    # Baris nama gabungan
    p_names = doc.add_paragraph()
    p_names.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_names, before=12, after=0, line=240, line_rule="auto")
    set_paragraph_indent(p_names, first_line=0)

    for i, author in enumerate(authors):
        name = author.get("name", "Author Name")
        if i > 0:
            sep = ", " if i < len(authors) - 1 else ", and "
            r = p_names.add_run(sep)
            set_run_font(r, font_name=CFG["font_body"], size_pt=CFG["size_body"])
        run = p_names.add_run(name)
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)
        run_sup = p_names.add_run(str(i + 1))
        set_run_font(run_sup, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)
        run_sup.font.superscript = True
        if i == 0:
            r_star = p_names.add_run("*")
            set_run_font(r_star, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)
            r_star.font.superscript = True

    # Afiliasi tiap author
    for i, author in enumerate(authors):
        affiliation = author.get("affiliation", "")
        location = author.get("location", "")
        email = author.get("email", "")
        parts = [s for s in [affiliation, location, email] if s]
        if not parts:
            continue
        p_aff = doc.add_paragraph()
        p_aff.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p_aff, before=0, after=0, line=240, line_rule="auto")
        set_paragraph_indent(p_aff, first_line=0)
        r_sup = p_aff.add_run(str(i + 1))
        set_run_font(r_sup, font_name=CFG["font_body"], size_pt=CFG["size_body"])
        r_sup.font.superscript = True
        r_aff = p_aff.add_run(" " + ", ".join(parts))
        set_run_font(r_aff, font_name=CFG["font_body"], size_pt=CFG["size_body"], italic=True)


def add_abstract(doc, data):
    add_empty_para(doc)

    # Heading "Abstract"
    p_label = doc.add_paragraph()
    apply_style(p_label, "Heading2")
    p_label.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_label, before=12, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p_label, first_line=0)
    run = p_label.add_run("Abstract")
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading1"], bold=True)

    # Isi abstract
    abstract_text = data.get(
        "abstract",
        "Abstract text goes here. This section should contain 150-250 words summarizing the paper.",
    )
    p = doc.add_paragraph()
    apply_style(p, "NoSpacing")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=6, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    _append_rich_text(p, abstract_text, font_name=CFG["font_body"],
                      size_pt=CFG["size_body"], base_italic=True)


def add_keywords(doc, data):
    keywords = data.get("keywords", ["keyword1", "keyword2", "keyword3"])
    if isinstance(keywords, list):
        keywords_text = ", ".join(keywords)
    else:
        keywords_text = str(keywords)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=6, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)

    run = p.add_run("Keywords: ")
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], bold=True)
    run = p.add_run(keywords_text)
    set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"], italic=True)


def add_section_heading(doc, title, section_index=None):
    p = doc.add_paragraph()
    apply_style(p, "Heading2")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=18, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(title)
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading1"], bold=True)


def add_subsection_heading(doc, title, section_index=None, sub_index=None):
    p = doc.add_paragraph()
    apply_style(p, "Heading5")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=12, after=6, line=CFG["line_spacing_body"], line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(title)
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading2"], bold=True)


def add_body_text(doc, text, first_paragraph=False):
    p = doc.add_paragraph()
    apply_style(p, "Heading4")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=6, after=6, line=CFG["line_spacing_body"], line_rule="auto")
    set_paragraph_indent(p, first_line=CFG["first_line_indent_tw"] if not first_paragraph else 0)
    _append_rich_text(p, text, font_name=CFG["font_body"], size_pt=CFG["size_body"])


def add_figure(doc, fig_data):
    image_number = str(fig_data.get("ImageNumber", "1")).strip()
    title = fig_data.get("Title", "Title of the figure")
    path_text = fig_data.get("Path", "").strip()
    prompt_hint = (fig_data.get("Prompt", "") or "").strip()

    image_path = None
    if path_text:
        candidate = BASE / path_text
        if candidate.is_file():
            image_path = candidate

    # Image area: gambar fisik bila ada, jika tidak fallback ke placeholder
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_img, before=6, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p_img, first_line=0)
    if image_path and image_path.is_file():
        usable_cm = (CFG["page_width_tw"] - CFG["margin_left_tw"] - CFG["margin_right_tw"]) / 567.0
        max_width = min(usable_cm, 13.0)
        run = p_img.add_run()
        run.add_picture(str(image_path), width=Cm(max_width))
    else:
        # File gambar tidak ada → render Prompt AI Dinamis sesuai format QA
        # standar: [PROMPT UNTUK AI GAMBAR: <Title>. <Prompt>]
        dyn_prompt = prompt_hint or (
            f"Buatkan gambar/diagram/ilustrasi teknis yang merepresentasikan "
            f"'{title}'. Pastikan visualnya profesional, jelas, dan cocok untuk "
            f"publikasi jurnal akademik IJB."
        )
        placeholder = f"[PROMPT UNTUK AI GAMBAR: {title}. {dyn_prompt}]"
        run = p_img.add_run(placeholder)
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"],
                     italic=True, color=(0xFF, 0x00, 0x00))

    # Caption: "Gbr. N. <judul>"
    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_cap, before=3, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p_cap, first_line=0)
    r_lbl = p_cap.add_run(f"{CFG['fig_prefix']} {image_number}. ")
    set_run_font(r_lbl, font_name=CFG["font_caption"], size_pt=CFG["size_caption"], bold=True)
    r_ttl = p_cap.add_run(title)
    set_run_font(r_ttl, font_name=CFG["font_caption"], size_pt=CFG["size_caption"])
    # Catatan: prompt AI sudah di-emit sebagai p_img placeholder (kalau image
    # tidak ada). Tidak perlu emit ulang sebagai block terpisah supaya tidak
    # double-count di audit.


def add_formula(doc, formula_data):
    formula_number = str(formula_data.get("FormulaNumber", "")).strip()
    latex = formula_data.get("latex", "E = mc^2").strip()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=6, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)

    if not _append_inline_math(p, latex):
        run = p.add_run(latex)
        set_run_font(run, font_name="Cambria Math", size_pt=CFG["size_body"], italic=True)

    if formula_number:
        run = p.add_run(f"     ({formula_number})")
        set_run_font(run, font_name=CFG["font_body"], size_pt=CFG["size_body"])


def add_table(doc, table_data):
    table_number = str(table_data.get("TableNumber", "1")).strip()
    title = table_data.get("Title", "Title of the table")
    headers = table_data.get("Headers", [])
    rows = table_data.get("Rows", [])

    if not headers:
        headers = ["Column 1", "Column 2"]
        rows = [["Data", "Data"]]

    # Title (DI ATAS tabel)
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_title, before=12, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p_title, first_line=0)
    r_lbl = p_title.add_run(f"{CFG['tbl_prefix']} {table_number}. ")
    set_run_font(r_lbl, font_name=CFG["font_caption"], size_pt=CFG["size_caption"], bold=True)
    r_ttl = p_title.add_run(title)
    set_run_font(r_ttl, font_name=CFG["font_caption"], size_pt=CFG["size_caption"])

    num_cols = len(headers)
    num_rows = len(rows) + 1
    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders_three_line(table)

    # Header row
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
        set_paragraph_indent(p, first_line=0)
        run = p.add_run(str(header))
        set_run_font(run, font_name=CFG["font_body"], size_pt=11, bold=True)

    # Data rows
    for row_idx, row_data in enumerate(rows):
        for col_idx, value in enumerate(row_data):
            if col_idx >= num_cols:
                break
            cell = table.rows[row_idx + 1].cells[col_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
            set_paragraph_indent(p, first_line=0)
            _append_rich_text(p, str(value), font_name=CFG["font_body"], size_pt=11)

    # Spacer setelah tabel agar tidak nempel ke paragraf berikutnya
    p_spacer = doc.add_paragraph()
    set_paragraph_spacing(p_spacer, before=0, after=0, line=240, line_rule="auto")
    set_paragraph_indent(p_spacer, first_line=0)


def _set_table_borders_three_line(table):
    tbl = table._tbl
    tbl_pr = tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)

    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is not None:
        tbl_pr.remove(borders)
    borders = OxmlElement("w:tblBorders")

    visible_edges = [("top", "12"), ("bottom", "12"), ("insideH", "4")]
    hidden_edges = ["left", "right", "insideV"]

    for edge, sz in visible_edges:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), sz)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)

    for edge in hidden_edges:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)

    tbl_pr.append(borders)


def add_references(doc, data):
    ref_data = data.get("references", {})
    if isinstance(ref_data, dict):
        ref_title = ref_data.get("title", "References")
        ref_content = ref_data.get("content", [])
    else:
        ref_title = "References"
        ref_content = list(ref_data) if isinstance(ref_data, list) else []

    p = doc.add_paragraph()
    apply_style(p, "Heading2")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=18, after=6, line=240, line_rule="auto")
    set_paragraph_indent(p, first_line=0)
    run = p.add_run(ref_title)
    set_run_font(run, font_name=CFG["font_heading"], size_pt=CFG["size_heading1"], bold=True)

    if not ref_content:
        ref_content = ["[1] Author, Title, Journal, Year."]

    for ref in ref_content:
        ref_text = ref.get("text", "") if isinstance(ref, dict) else str(ref)
        if not ref_text:
            continue
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        set_paragraph_spacing(p, before=0, after=CFG["ref_after_tw_pt"],
                              line=240, line_rule="auto")
        set_paragraph_indent(p,
                             left=CFG["ref_left_indent_tw"],
                             hanging=CFG["ref_hanging_indent_tw"],
                             first_line=None)
        _append_rich_text(p, ref_text,
                          font_name=CFG["font_reference"],
                          size_pt=CFG["size_reference"])


def process_content_item(doc, item, first_paragraph=False):
    item_id = str(item.get("id", "")).lower()
    if item_id == "text":
        text = item.get("text", "")
        if text:
            add_body_text(doc, text, first_paragraph=first_paragraph)
    elif item_id in ("gambar", "image"):
        add_figure(doc, item)
    elif item_id in ("rumus", "formula"):
        add_formula(doc, item)
    elif item_id in ("tabel", "table"):
        add_table(doc, item)


def process_section(doc, section_data, section_key, section_index):
    if not isinstance(section_data, dict):
        return

    title = section_data.get("title", "")
    if title:
        add_section_heading(doc, title, section_index=section_index)

    content = section_data.get("content", [])
    first_done = False
    if isinstance(content, list):
        for item in content:
            is_first = not first_done
            if isinstance(item, str):
                add_body_text(doc, item, first_paragraph=is_first)
                first_done = True
            elif isinstance(item, dict):
                if str(item.get("id", "")).lower() == "text":
                    process_content_item(doc, item, first_paragraph=is_first)
                    first_done = True
                else:
                    process_content_item(doc, item)
    elif isinstance(content, str) and content.strip():
        add_body_text(doc, content, first_paragraph=True)

    # Subsections (section1a, section2b, dst.)
    subsection_keys = []
    for key in section_data.keys():
        if (
            key.startswith(section_key)
            and len(key) > len(section_key)
            and key[len(section_key):].isalpha()
        ):
            subsection_keys.append(key)
    subsection_keys.sort()

    for sub_idx, sub_key in enumerate(subsection_keys, start=1):
        sub_data = section_data[sub_key]
        if not isinstance(sub_data, dict):
            continue
        sub_title = sub_data.get("title", "")
        if sub_title:
            add_subsection_heading(doc, sub_title,
                                   section_index=section_index, sub_index=sub_idx)

        sub_content = sub_data.get("content", [])
        sub_first_done = False
        if isinstance(sub_content, list):
            for item in sub_content:
                is_first = not sub_first_done
                if isinstance(item, str):
                    add_body_text(doc, item, first_paragraph=is_first)
                    sub_first_done = True
                elif isinstance(item, dict):
                    if str(item.get("id", "")).lower() == "text":
                        process_content_item(doc, item, first_paragraph=is_first)
                        sub_first_done = True
                    else:
                        process_content_item(doc, item)
        elif isinstance(sub_content, str) and sub_content.strip():
            add_body_text(doc, sub_content, first_paragraph=True)


def ensure_sectpr(doc):
    """Pastikan sectPr akhir punya page-size & margins sesuai analisa."""
    body = doc._element.body
    sectpr = body.find(qn("w:sectPr"))
    if sectpr is None:
        return
    # pgSz
    pgsz = sectpr.find(qn("w:pgSz"))
    if pgsz is None:
        pgsz = OxmlElement("w:pgSz")
        sectpr.append(pgsz)
    pgsz.set(qn("w:w"), str(CFG["page_width_tw"]))
    pgsz.set(qn("w:h"), str(CFG["page_height_tw"]))
    # pgMar
    pgmar = sectpr.find(qn("w:pgMar"))
    if pgmar is None:
        pgmar = OxmlElement("w:pgMar")
        sectpr.append(pgmar)
    pgmar.set(qn("w:top"), str(CFG["margin_top_tw"]))
    pgmar.set(qn("w:right"), str(CFG["margin_right_tw"]))
    pgmar.set(qn("w:bottom"), str(CFG["margin_bottom_tw"]))
    pgmar.set(qn("w:left"), str(CFG["margin_left_tw"]))
    pgmar.set(qn("w:header"), str(CFG["header_distance_tw"]))
    pgmar.set(qn("w:footer"), str(CFG["footer_distance_tw"]))
    pgmar.set(qn("w:gutter"), str(CFG["margin_gutter_tw"]))


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def generate():
    data = load_json()

    # Copy template asli → output (paste keep formatting)
    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    # Hapus body content (pertahankan sectPr, headers, footers, styles, numbering)
    clear_body(doc)
    ensure_sectpr(doc)

    # Generate content
    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    section_index = 0
    for i in range(1, 20):
        key = f"section{i}"
        if key in data:
            section_index += 1
            process_section(doc, data[key], key, section_index)

    add_references(doc, data)

    _set_ai_prompt_color_red(doc)
    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


if __name__ == "__main__":
    generate()
