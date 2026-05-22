"""
IJIMSgen.py — Generator DOCX untuk template IJIMS (Indonesian Journal of Islam and Muslim Societies)
Menggunakan dokumen asli IJIMS.doc sebagai base template (paste keep formatting).
Data diambil dari _template.json.
"""
import json, copy, re, os
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm, Emu, Inches, RGBColor
import latex2mathml.converter
import mathml2omml

def Tw(twips):
    return Emu(twips * 914400 // 1440)
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
from lxml import etree

BASE = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE / "IJIMS.docx"
JSON_PATH = BASE / "_template.json"
OUTPUT_PATH = BASE / "IJIMS_output.docx"


OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def latex_to_omml_element(latex_src):
    mathml = latex2mathml.converter.convert(latex_src)
    omml_str = mathml2omml.convert(mathml)
    omml_str = re.sub(
        r'(<m:groupChrPr>.*?)</m:groupChr>(\s*<m:e>)',
        r'\1</m:groupChrPr>\2',
        omml_str,
    )
    if not omml_str.startswith("<m:oMath xmlns:m="):
        omml_str = omml_str.replace("<m:oMath>", f'<m:oMath xmlns:m="{OMML_NS}">', 1)
    return parse_xml(omml_str)


INLINE_MATH_RE = re.compile(r'\$([^$]+)\$')


def load_json():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_output_dir():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def set_run_font(run, font_name, size_pt, bold=False, italic=False, color=None):
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="{font_name}" w:hAnsi="{font_name}" w:cs="{font_name}"/>')
        rpr.insert(0, rfonts)
    else:
        rfonts.set(qn('w:ascii'), font_name)
        rfonts.set(qn('w:hAnsi'), font_name)
        rfonts.set(qn('w:cs'), font_name)


def set_paragraph_spacing(paragraph, before=None, after=None, line=None, line_rule=None):
    ppr = paragraph._p.get_or_add_pPr()
    spacing = ppr.find(qn('w:spacing'))
    if spacing is None:
        spacing = parse_xml(f'<w:spacing {nsdecls("w")}/>')
        ppr.append(spacing)
    if before is not None:
        spacing.set(qn('w:before'), str(before))
    if after is not None:
        spacing.set(qn('w:after'), str(after))
    if line is not None:
        spacing.set(qn('w:line'), str(line))
    if line_rule is not None:
        spacing.set(qn('w:lineRule'), line_rule)


def set_paragraph_indent(paragraph, left=None, right=None, first_line=None, hanging=None):
    ppr = paragraph._p.get_or_add_pPr()
    ind = ppr.find(qn('w:ind'))
    if ind is None:
        ind = parse_xml(f'<w:ind {nsdecls("w")}/>')
        ppr.append(ind)
    if left is not None:
        ind.set(qn('w:left'), str(left))
        ind.set(qn('w:start'), str(left))
    if right is not None:
        ind.set(qn('w:right'), str(right))
        ind.set(qn('w:end'), str(right))
    if first_line is not None:
        ind.set(qn('w:firstLine'), str(first_line))
    if hanging is not None:
        ind.set(qn('w:hanging'), str(hanging))


def set_columns(section, num_cols, space_tw=360):
    sectPr = section._sectPr
    cols = sectPr.find(qn('w:cols'))
    if cols is None:
        cols = parse_xml(f'<w:cols {nsdecls("w")}/>')
        sectPr.append(cols)
    cols.set(qn('w:num'), str(num_cols))
    cols.set(qn('w:space'), str(space_tw))


def add_even_odd_headers(doc):
    settings_el = doc.settings.element
    eoh = settings_el.find(qn('w:evenAndOddHeaders'))
    if eoh is None:
        eoh = parse_xml(f'<w:evenAndOddHeaders {nsdecls("w")}/>')
        settings_el.append(eoh)


def setup_header_even(section, data):
    header = section.even_page_header
    for p in header.paragraphs:
        p.clear()
    header.paragraphs[0].text = ""


def setup_header_odd(section, data):
    header = section.header
    for p in header.paragraphs:
        p.clear()

    p1 = header.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run1 = p1.add_run("Indonesian Journal of Islam and Muslim Societies")
    set_run_font(run1, "Arial Narrow", 8.5, italic=True)
    set_paragraph_spacing(p1, before=0, after=0, line=240, line_rule="auto")

    p2 = header.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run2 = p2.add_run("Vol. 8, no.2 (2018), pp. 173-197, doi : 10.18326/ijims.v8i2. 173-197")
    set_run_font(run2, "Arial Narrow", 8.5)
    set_paragraph_spacing(p2, before=0, after=0, line=240, line_rule="auto")


def setup_footer_even(section, data):
    footer = section.even_page_footer
    for p in footer.paragraphs:
        p.clear()
    footer.paragraphs[0].text = ""


def setup_footer_odd(section, data):
    footer = section.footer
    for p in footer.paragraphs:
        p.clear()

    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    authors_str = ", ".join([a["name"] for a in data.get("authors", [])])
    title_short = data.get("title", "Title")[:60]
    run = p.add_run(f"{title_short}... ({authors_str})")
    set_run_font(run, "Cambria", 10)
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")


def add_title(doc, data):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    run = p.add_run(data.get("title", "Title of the Paper"))
    set_run_font(run, "Cambria", 20.5, bold=True)


def add_empty_line(doc, font_name="Cambria", size=10):
    p = doc.add_paragraph()
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    run = p.add_run("")
    set_run_font(run, font_name, size)


def add_authors(doc, data):
    authors = data.get("authors", [])
    if not authors:
        authors = [{"name": "Author Name", "affiliation": "Institution", "location": "City, Country", "email": "email@mail.ac.id"}]

    p_name = doc.add_paragraph()
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_name, before=0, after=0, line=240, line_rule="auto")
    run = p_name.add_run(", ".join(a.get("name", "Author Name") for a in authors))
    set_run_font(run, "Cambria", 14, bold=True)

    p_aff = doc.add_paragraph()
    p_aff.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_aff, before=0, after=0, line=240, line_rule="auto")
    affs = []
    for a in authors:
        aff = a.get("affiliation", "Institution")
        if aff not in affs:
            affs.append(aff)
    run = p_aff.add_run("; ".join(affs))
    set_run_font(run, "Cambria", 11.5, bold=True)

    p_em = doc.add_paragraph()
    p_em.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_em, before=0, after=0, line=240, line_rule="auto")
    run = p_em.add_run(", ".join(a.get("email", "email@mail.ac.id") for a in authors))
    set_run_font(run, "Cambria", 11.5)


def add_abstract(doc, data):
    add_empty_line(doc, "Cambria", 10)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    run = p.add_run("Abstract")
    set_run_font(run, "Cambria", 12, bold=True)

    add_empty_line(doc, "Cambria", 12)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    abstract_text = data.get("abstract", "Abstract text goes here. This should be a concise summary of the paper content between 150-250 words.")
    run = p.add_run(abstract_text)
    set_run_font(run, "Cambria", 10.5)


def add_keywords(doc, data):
    add_empty_line(doc, "Cambria", 10)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
    run_label = p.add_run("Keywords: ")
    set_run_font(run_label, "Cambria", 10, bold=True)

    keywords = data.get("keywords", ["keyword one", "keyword two", "keyword three"])
    kw_text = "; ".join(keywords)
    run_kw = p.add_run(kw_text)
    set_run_font(run_kw, "Cambria", 10, italic=True)


def add_section_heading(doc, title):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=60, after=60, line=240, line_rule="atLeast")
    run = p.add_run(title)
    set_run_font(run, "Cambria", 11.5, bold=True)
    return p


def add_subsection_heading(doc, title):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_paragraph_spacing(p, before=60, after=60, line=240, line_rule="auto")
    run = p.add_run(title)
    set_run_font(run, "Cambria", 10.5, bold=True)
    return p


def _add_text_with_inline_math(p, text, font_name, size_pt, italic=False, bold=False):
    pos = 0
    for m in INLINE_MATH_RE.finditer(text):
        before = text[pos:m.start()]
        if before:
            run = p.add_run(before)
            set_run_font(run, font_name, size_pt, bold=bold, italic=italic)
        try:
            omml = latex_to_omml_element(m.group(1))
            p._p.append(omml)
        except Exception:
            run = p.add_run(m.group(0))
            set_run_font(run, font_name, size_pt, bold=bold, italic=True)
        pos = m.end()
    tail = text[pos:]
    if tail:
        run = p.add_run(tail)
        set_run_font(run, font_name, size_pt, bold=bold, italic=italic)


def add_body_text(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=276, line_rule="auto")
    set_paragraph_indent(p, first_line=720)
    _add_text_with_inline_math(p, text, "Cambria", 11)
    return p


def add_body_text_no_indent(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    set_paragraph_spacing(p, before=0, after=0, line=276, line_rule="auto")
    _add_text_with_inline_math(p, text, "Cambria", 11)
    return p


def add_figure(doc, fig_data):
    img_number = fig_data.get("ImageNumber", "1")
    title = fig_data.get("Title", "Figure Title")
    path = fig_data.get("Path", "")

    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_img, before=60, after=60, line=240, line_rule="auto")

    img_full_path = BASE / path if path else None
    if img_full_path and img_full_path.exists():
        run = p_img.add_run()
        run.add_picture(str(img_full_path), width=Cm(12))
    else:
        prompt_text = (
            f"[PROMPT UNTUK AI GAMBAR: {title}. "
            f"Gaya ilustrasi teknis-akademik, latar bersih, resolusi tinggi, "
            f"komposisi terpusat, label elemen jelas dan terbaca.]"
        )
        run = p_img.add_run(prompt_text)
        set_run_font(run, "Cambria", 10, italic=True)

    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_cap, before=60, after=120, line=240, line_rule="auto")
    run_label = p_cap.add_run(f"Figure {img_number}. ")
    set_run_font(run_label, "Cambria", 10, bold=True)
    run_title = p_cap.add_run(title)
    set_run_font(run_title, "Cambria", 10)


def add_formula(doc, formula_data):
    formula_num = formula_data.get("FormulaNumber", "1")
    latex = formula_data.get("latex", "E = mc^2")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p, before=60, after=60, line=240, line_rule="auto")

    try:
        omml = latex_to_omml_element(latex)
        p._p.append(omml)
    except Exception:
        run = p.add_run(f"  {latex}  ")
        set_run_font(run, "Cambria", 11, italic=True)

    p_num = doc.add_paragraph()
    p_num.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_paragraph_spacing(p_num, before=0, after=60, line=240, line_rule="auto")
    run_num = p_num.add_run(f"({formula_num})")
    set_run_font(run_num, "Cambria", 11)


def add_table(doc, table_data):
    tbl_number = table_data.get("TableNumber", "I")
    title = table_data.get("Title", "Table Title")
    headers = table_data.get("Headers", [])
    rows = table_data.get("Rows", [])

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_title, before=120, after=60, line=240, line_rule="auto")
    run_label = p_title.add_run(f"Table {tbl_number}. ")
    set_run_font(run_label, "Cambria", 10, bold=True)
    run_title = p_title.add_run(title)
    set_run_font(run_title, "Cambria", 10)

    num_cols = len(headers) if headers else 1
    num_rows = len(rows) + 1
    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    tbl_el = table._tbl
    tblPr = tbl_el.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = parse_xml(f'<w:tblPr {nsdecls("w")}/>')
        tbl_el.insert(0, tblPr)

    borders_xml = (
        f'<w:tblBorders {nsdecls("w")}>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '</w:tblBorders>'
    )
    tblBorders = parse_xml(borders_xml)
    tblPr.append(tblBorders)

    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")
        run = p.add_run(h)
        set_run_font(run, "Cambria", 9, bold=True)

        tcPr = cell._tc.get_or_add_tcPr()
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="auto" w:val="clear"/>')
        tcPr.append(shading)

    for ri, row in enumerate(rows):
        for ci, cell_text in enumerate(row):
            cell = table.rows[ri + 1].cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_paragraph_spacing(p, before=0, after=0, line=240, line_rule="auto")

            is_bold = "\\b" in str(cell_text)
            clean_text = str(cell_text).replace("\\b", "")
            run = p.add_run(clean_text)
            set_run_font(run, "Cambria", 9, bold=is_bold)

    p_after = doc.add_paragraph()
    set_paragraph_spacing(p_after, before=60, after=0, line=240, line_rule="auto")


def add_references(doc, data):
    refs_data = data.get("references", {})
    refs_title = refs_data.get("title", "REFERENCES")
    refs_content = refs_data.get("content", [])

    add_empty_line(doc)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_paragraph_spacing(p_title, before=120, after=60, line=240, line_rule="auto")
    run = p_title.add_run(refs_title)
    set_run_font(run, "Cambria", 11.5, bold=True)

    if not refs_content:
        refs_content = ["[1] Author, \"Title,\" Journal, vol. X, no. Y, pp. Z, Year."]

    for i, ref in enumerate(refs_content):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        set_paragraph_spacing(p, before=0, after=50, line=180, line_rule="exact")
        set_paragraph_indent(p, left=360, hanging=360)

        run_num = p.add_run(f"[{i+1}] ")
        set_run_font(run_num, "Times New Roman", 8)
        run_text = p.add_run(ref)
        set_run_font(run_text, "Times New Roman", 8)


def process_section_content(doc, content_list):
    if not content_list:
        return

    first_text = True
    for item in content_list:
        item_id = item.get("id", "")

        if item_id == "text":
            text = item.get("text", "")
            if first_text:
                add_body_text_no_indent(doc, text)
                first_text = False
            else:
                add_body_text(doc, text)

        elif item_id == "gambar":
            add_figure(doc, item)

        elif item_id == "rumus":
            add_formula(doc, item)

        elif item_id == "tabel":
            add_table(doc, item)


def process_section(doc, section_key, section_data, level=1):
    if not section_data:
        return

    title = section_data.get("title", "")

    if level == 1:
        add_section_heading(doc, title)
    else:
        add_subsection_heading(doc, title)

    content = section_data.get("content", [])
    if isinstance(content, list) and content:
        if isinstance(content[0], dict):
            process_section_content(doc, content)
        elif isinstance(content[0], str):
            for text in content:
                add_body_text(doc, text)

    for key, val in section_data.items():
        if key in ("title", "content"):
            continue
        if isinstance(val, dict) and "title" in val:
            process_section(doc, key, val, level=2)


def generate():
    data = load_json()
    ensure_output_dir()

    if TEMPLATE_PATH.exists():
        doc = Document(str(TEMPLATE_PATH))
        body = doc.element.body
        for child in list(body):
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag != "sectPr":
                body.remove(child)
    else:
        doc = Document()
        section = doc.sections[0]
        section.page_width = Tw(11906)
        section.page_height = Tw(16838)
        section.orientation = WD_ORIENT.PORTRAIT
        section.top_margin = Tw(2268)
        section.bottom_margin = Tw(1701)
        section.left_margin = Tw(1701)
        section.right_margin = Tw(1701)
        section.gutter = Tw(567)
        section.header_distance = Tw(851)
        section.footer_distance = Tw(567)
        add_even_odd_headers(doc)
        setup_header_odd(section, data)
        setup_header_even(section, data)
        setup_footer_odd(section, data)
        setup_footer_even(section, data)

    add_title(doc, data)
    add_empty_line(doc, "Cambria", 10)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    add_empty_line(doc)

    section_keys = []
    for key in data.keys():
        if key.startswith("section") and isinstance(data[key], dict):
            section_keys.append(key)

    section_keys.sort(key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)

    for sk in section_keys:
        process_section(doc, sk, data[sk], level=1)

    add_references(doc, data)

    doc.save(str(OUTPUT_PATH))
    print(f"Generated: {OUTPUT_PATH}")
    return str(OUTPUT_PATH)


if __name__ == "__main__":
    generate()
