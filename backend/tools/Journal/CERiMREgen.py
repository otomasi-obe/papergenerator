"""CERiMREgen.py — Generator dokumen CERiMRE dari JSON.

Target:
- Menggunakan file template asli: CERiMRE.docx (header/footer/theme/styles tetap).
- Mengisi title/author/abstract/keywords/sections/subsections/figures/tables/equations/references.
- Menjaga format berdasarkan style bawaan template (keep formatting).
- Jika data JSON kosong/tidak ada, tetap menulis struktur dengan isi fallback.

Catatan:
- JSON default mengikuti permintaan: backend/output/20260331_004418_robotik.json
- Generator ini juga dipakai oleh backend via /api/export (app.py), sehingga
  build_document(json_path, output_path) wajib tersedia.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

JSON_PATH = BASE_DIR / "_template.json"
TEMPLATE_PATH = BASE_DIR / "CERiMRE.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# Template style IDs (hasil analisa template/CERiMRE.docx)
STYLE_TITLE = "TITLECERiMRE"
STYLE_AUTHOR = "AUTHORNAMECERiMRE"
STYLE_AFFILIATION = "AFFILIATIONCERiMRE"
STYLE_EMAIL = "EMAILCERiMRE"
STYLE_ABSTRACT = "ABSTRACTCERiMRE"
STYLE_KEYWORDS = "KEYWORDSCERiMRE"
STYLE_SECTION = "SECTIONCERiMRE"
STYLE_SUBSECTION = "SUB-SECTIONCERiMRE"
STYLE_BODY = "PARAGRAPHCERiMRE"
STYLE_FIGURE = "FIGURECERiMRE"
STYLE_FIGURE_CAPTION = "FIGURECAPTIONCERiMRE"
STYLE_REFERENCE = "REFERENCESCERiMRE"

TEXT_AREA_WIDTH_TW = 9360  # dari analyse: usable=9360tw (468pt)
MAX_FIGURE_WIDTH_CM = 15.5

XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
]
_XSLT = None


@dataclass
class RenderState:
    figure_count: int = 0
    table_count: int = 0
    equation_count: int = 0


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


def _set_para_style(paragraph, style_id: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    pstyle = ppr.find(qn("w:pStyle"))
    if pstyle is None:
        pstyle = OxmlElement("w:pStyle")
        ppr.insert(0, pstyle)
    pstyle.set(qn("w:val"), style_id)


def _clear_document_body(doc: Document) -> None:
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _normalize_text_commands(text: str) -> str:
    # JSON sering menyimpan newline sebagai literal "\\n"
    text = str(text).replace("\\n", "\n")
    # Convert Markdown bold/italic to \b..\b / \i..\i toggle format
    text = re.sub(r"\*\*(.+?)\*\*", r"\\b\1\\b", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+?)\*", r"\\i\1\\i", text)
    return text


def _iter_rich_tokens(text: str):
    normalized = _normalize_text_commands(text)
    buffer: list[str] = []
    bold = False
    italic = False
    underline = False
    index = 0

    def flush_buffer():
        nonlocal buffer
        content = "".join(buffer)
        buffer = []
        if content:
            yield {
                "kind": "text",
                "value": content,
                "bold": bold,
                "italic": italic,
                "underline": underline,
            }

    while index < len(normalized):
        ch = normalized[index]
        if ch == "\n":
            yield from flush_buffer()
            yield {"kind": "linebreak"}
            index += 1
            continue

        # Rich commands: \b, \i, \u, and escaping \\\
        if ch == "\\" and index + 1 < len(normalized):
            cmd = normalized[index + 1]
            if cmd == "\\":
                buffer.append("\\")
                index += 2
                continue
            if cmd == "b":
                yield from flush_buffer()
                bold = not bold
                index += 2
                continue
            if cmd == "i":
                yield from flush_buffer()
                italic = not italic
                index += 2
                continue
            if cmd == "u":
                yield from flush_buffer()
                underline = not underline
                index += 2
                continue

        # Inline math: $...$
        if ch == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                yield from flush_buffer()
                formula = normalized[index + 1 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 1
                continue

        buffer.append(ch)
        index += 1
    yield from flush_buffer()


def _get_xslt():
    global _XSLT
    if _XSLT is not None:
        return _XSLT
    for candidate in XSL_CANDIDATES:
        try:
            if candidate.exists():
                _XSLT = etree.XSLT(etree.parse(str(candidate)))
                return _XSLT
        except Exception:
            continue
    _XSLT = False
    return _XSLT


def _latex_to_omml(latex: str):
    try:
        import latex2mathml.converter
    except Exception:
        return None
    xslt = _get_xslt()
    if not xslt:
        return None
    try:
        mathml = latex2mathml.converter.convert(latex)
        root = etree.fromstring(mathml.encode("utf-8"))
        return xslt(root).getroot()
    except Exception:
        return None


def _append_inline_math(paragraph, latex: str) -> bool:
    omml = _latex_to_omml(latex)
    if omml is None:
        return False
    tag = omml.tag.split("}")[-1] if "}" in omml.tag else omml.tag
    if tag in ("oMath", "oMathPara"):
        paragraph._p.append(omml)
    else:
        wrapper = etree.fromstring(f'<m:oMath xmlns:m="{MATH_NS}"/>')
        wrapper.append(omml)
        paragraph._p.append(wrapper)
    return True


def _append_rich_text(paragraph, text: str) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            paragraph.add_run().add_break()
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                run = paragraph.add_run(token["value"])
                run.italic = True
            continue
        run = paragraph.add_run(token["value"])
        run.bold = token["bold"]
        run.italic = token["italic"]
        run.underline = token["underline"]


def _title_case_if_upper(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value
    letters = [c for c in value if c.isalpha()]
    if letters and value.upper() == value:
        words = []
        for w in value.split():
            if w.isupper() and len(w) <= 3:
                words.append(w)
            else:
                words.append(w.capitalize())
        return " ".join(words)
    return value


def _safe_title(config: dict) -> str:
    title = str(config.get("title", "")).strip()
    if title:
        return title
    return "Untitled Paper (CERiMRE)"


def _safe_authors(config: dict) -> list[dict]:
    authors = config.get("authors")
    if isinstance(authors, list) and authors:
        return [a if isinstance(a, dict) else {"name": str(a)} for a in authors]
    return [
        {
            "name": "Author Name",
            "affiliation": "Affiliation / Department",
            "location": "City, Country",
            "email": "author@example.com",
        }
    ]


def _safe_abstract(config: dict) -> str:
    abstract = str(config.get("abstract", "")).strip()
    if abstract:
        return abstract
    return (
        "This paper presents a study relevant to CERiMRE scope. "
        "The objective is to propose a method, evaluate its performance, and discuss the results "
        "in a structured manner. The findings indicate the approach is feasible and provides a basis "
        "for further research and practical deployment."
    )


def _safe_keywords(config: dict) -> list[str]:
    raw = config.get("keywords")
    if isinstance(raw, list) and [k for k in raw if str(k).strip()]:
        return [str(k).strip() for k in raw if str(k).strip()]
    return ["robotics", "control", "artificial intelligence", "navigation"]


def _section_keys(config: dict) -> list[str]:
    keys = [k for k in config.keys() if re.fullmatch(r"section\d+", str(k))]
    return sorted(keys, key=lambda k: int(str(k).replace("section", "")))


def _subsection_keys(section_key: str, section_data: dict) -> list[str]:
    pattern = re.compile(rf"^{re.escape(section_key)}[a-z]+$")
    keys = [k for k in section_data.keys() if pattern.fullmatch(str(k))]
    return sorted(keys, key=lambda k: (len(str(k)), str(k)))


def _norm_content_list(content) -> list:
    if content is None:
        return []
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return content
    return [str(content)]


def _resolve_image(path_text: str, json_path: Path) -> Path | None:
    if not path_text:
        return None
    path = Path(str(path_text))
    if path.is_absolute():
        return path if path.exists() else None
    candidates = [
        json_path.parent / path,
        ROOT_DIR / path,
        BASE_DIR / path,
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _make_placeholder_image_bytes(label: str, title: str) -> BytesIO:
    width, height = 1600, 900
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    text = f"{label}\n{title}\n\n[IMAGE FILE NOT FOUND]"
    margin = 60
    y = margin
    for line in text.split("\n"):
        draw.text((margin, y), line, fill="black", font=font)
        y += 30
    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio


def _set_table_borders_none(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")


def _set_cell_border(cell, *, top: str | None = None, bottom: str | None = None) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge, val in (("top", top), ("bottom", bottom)):
        if val is None:
            continue
        el = tc_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tc_borders.append(el)
        el.set(qn("w:val"), val)
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")


def _add_title_block(doc: Document, config: dict) -> None:
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_TITLE)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(_safe_title(config))


def _add_authors_block(doc: Document, config: dict) -> None:
    authors = _safe_authors(config)

    aff_map: dict[tuple[str, str], int] = {}
    aff_list: list[tuple[tuple[str, str], int]] = []
    for a in authors:
        aff = str(a.get("affiliation", "")).strip() or "Affiliation"
        loc = str(a.get("location", "")).strip() or "City, Country"
        key = (aff, loc)
        if key not in aff_map:
            aff_map[key] = len(aff_map) + 1
            aff_list.append((key, aff_map[key]))

    # Email letters: a, b, c ... for authors that have email (or fallback)
    letters = "abcdefghijklmnopqrstuvwxyz"
    email_letters: list[str] = []
    for idx, a in enumerate(authors):
        email = str(a.get("email", "")).strip() or f"author{idx+1}@example.com"
        a["email"] = email
        email_letters.append(letters[idx] if idx < len(letters) else "a")

    # Author line
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_AUTHOR)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def add_author(i: int, author: dict):
        name = str(author.get("name", "")).strip() or f"Author {i+1}"
        aff = str(author.get("affiliation", "")).strip() or "Affiliation"
        loc = str(author.get("location", "")).strip() or "City, Country"
        aff_no = aff_map.get((aff, loc), i + 1)
        letter = email_letters[i]

        p.add_run(name)
        r_num = p.add_run(str(aff_no))
        r_num.font.superscript = True
        r_letter = p.add_run(f",{letter}")
        r_letter.font.superscript = True

    for i, a in enumerate(authors):
        if i > 0:
            if i == len(authors) - 1:
                p.add_run(" , and ")
            else:
                p.add_run(", ")
        add_author(i, a)

    # Affiliation lines
    for (aff, loc), num in aff_list:
        p = doc.add_paragraph()
        _set_para_style(p, STYLE_AFFILIATION)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(str(num))
        r.font.superscript = True
        p.add_run(aff)
        if loc:
            p.add_run(", ")
            p.add_run(loc)

    # Email line(s)
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_EMAIL)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for i, a in enumerate(authors):
        if i > 0:
            p.add_run("; ")
        r = p.add_run(email_letters[i])
        r.font.superscript = True
        p.add_run("email ")
        p.add_run(str(a.get("email", "")).strip())


def _add_abstract_block(doc: Document, config: dict) -> None:
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_ABSTRACT)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run("Abstract.")
    r.bold = True
    p.add_run(" ")
    _append_rich_text(p, _safe_abstract(config))


def _add_keywords_block(doc: Document, config: dict) -> None:
    keywords = _safe_keywords(config)
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_KEYWORDS)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run("Keywords:")
    r.bold = True
    p.add_run(" ")
    p.add_run(", ".join(keywords))


def _split_paragraphs(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b for b in re.split(r"\n\s*\n", normalized) if b.strip()]
    return blocks or [normalized.strip()]


def _render_text_block(doc: Document, text: str, *, style_id: str = STYLE_BODY) -> None:
    for block in _split_paragraphs(text):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        bullet_lines = [ln for ln in lines if ln.startswith("-") or ln.startswith("•")]
        if bullet_lines and len(bullet_lines) == len(lines):
            for ln in bullet_lines:
                item = ln.lstrip("-• ").strip()
                p = doc.add_paragraph()
                _set_para_style(p, style_id)
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                p.add_run("• ")
                _append_rich_text(p, item)
            continue

        p = doc.add_paragraph()
        _set_para_style(p, style_id)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _append_rich_text(p, block.strip())


def _add_figure(doc: Document, item: dict, json_path: Path, state: RenderState) -> None:
    state.figure_count += 1
    fig_no = str(item.get("ImageNumber", "")).strip() or str(state.figure_count)
    title = str(item.get("Title", "")).strip() or f"Figure {fig_no}"
    path_text = str(item.get("Path", "")).strip()
    resolved = _resolve_image(path_text, json_path)

    p_img = doc.add_paragraph()
    _set_para_style(p_img, STYLE_FIGURE)
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(3)
    p_img.paragraph_format.space_after = Pt(3)
    run = p_img.add_run()
    if resolved is not None:
        try:
            run.add_picture(str(resolved), width=Cm(MAX_FIGURE_WIDTH_CM))
        except Exception:
            bio = _make_placeholder_image_bytes(f"Figure {fig_no}", title)
            run.add_picture(bio, width=Cm(MAX_FIGURE_WIDTH_CM))
    else:
        bio = _make_placeholder_image_bytes(f"Figure {fig_no}", title)
        run.add_picture(bio, width=Cm(MAX_FIGURE_WIDTH_CM))

    p_cap = doc.add_paragraph()
    _set_para_style(p_cap, STYLE_FIGURE_CAPTION)
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _append_rich_text(p_cap, title)


def _add_table(doc: Document, item: dict, state: RenderState) -> None:
    state.table_count += 1
    table_no = str(item.get("TableNumber", "")).strip() or str(state.table_count)
    title = str(item.get("Title", "")).strip() or f"Table {table_no}"
    headers = item.get("Headers") if isinstance(item.get("Headers"), list) else []
    rows = item.get("Rows") if isinstance(item.get("Rows"), list) else []

    p_cap = doc.add_paragraph()
    _set_para_style(p_cap, STYLE_BODY)
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cap.paragraph_format.space_before = Pt(6)
    r = p_cap.add_run(f"Table {table_no}")
    r.bold = True
    r2 = p_cap.add_run(".")
    r2.bold = True
    if title:
        p_cap.add_run(f" {title}")

    cols = max(len(headers), max((len(r) for r in rows), default=0))
    if cols <= 0:
        cols = 2
    if not headers:
        headers = ["Column 1", "Column 2"][:cols]
    if len(headers) < cols:
        headers = headers + [f"Column {i+1}" for i in range(len(headers), cols)]

    table = doc.add_table(rows=1 + len(rows), cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders_none(table)

    # Header row
    for c in range(cols):
        cell = table.cell(0, c)
        _set_cell_border(cell, top="single", bottom="single")
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(headers[c]))
        run.bold = True

    # Body
    for r_idx, row in enumerate(rows, start=1):
        row_vals = [str(v) for v in (row or [])]
        if len(row_vals) < cols:
            row_vals = row_vals + [""] * (cols - len(row_vals))
        for c in range(cols):
            cell = table.cell(r_idx, c)
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if c == 0 else WD_ALIGN_PARAGRAPH.CENTER
            _append_rich_text(p, row_vals[c])

    # Spacing after table
    p_after = doc.add_paragraph()
    _set_para_style(p_after, STYLE_BODY)
    p_after.paragraph_format.space_before = Pt(3)
    p_after.paragraph_format.space_after = Pt(3)


def _add_equation(doc: Document, item: dict, state: RenderState) -> None:
    state.equation_count += 1
    latex = str(item.get("latex", "")).strip() or r"E = mc^2"

    # Equation table: left = equation, right = numbering style from template
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders_none(tbl)

    left = tbl.cell(0, 0)
    right = tbl.cell(0, 1)

    left.text = ""
    right.text = ""

    p_eq = left.paragraphs[0]
    _set_para_style(p_eq, STYLE_FIGURE)  # centered spacing baseline
    p_eq.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_eq.paragraph_format.space_before = Pt(3)
    p_eq.paragraph_format.space_after = Pt(3)
    if not _append_inline_math(p_eq, latex):
        run = p_eq.add_run(latex)
        run.italic = True

    p_no = right.paragraphs[0]
    _set_para_style(p_no, "EQUATIONNUMBERCERiMRE")
    p_no.paragraph_format.space_before = Pt(3)
    p_no.paragraph_format.space_after = Pt(3)
    p_no.add_run(" ")


def _render_content(doc: Document, content_list: list, json_path: Path, state: RenderState) -> None:
    for item in content_list:
        if isinstance(item, str):
            if item.strip():
                _render_text_block(doc, item)
            continue
        if not isinstance(item, dict):
            _render_text_block(doc, str(item))
            continue

        kind = str(item.get("id", "text")).strip().lower() or "text"
        if kind == "text":
            text = item.get("text", "")
            if str(text).strip():
                _render_text_block(doc, str(text))
            continue
        if kind == "gambar":
            _add_figure(doc, item, json_path, state)
            continue
        if kind == "tabel":
            _add_table(doc, item, state)
            continue
        if kind == "rumus":
            _add_equation(doc, item, state)
            continue

        # Unknown item -> stringify
        _render_text_block(doc, json.dumps(item, ensure_ascii=False))


def _render_sections(doc: Document, config: dict, json_path: Path, state: RenderState) -> None:
    keys = _section_keys(config)
    if not keys and isinstance(config.get("sections"), list):
        # Legacy list-based format
        for sec in config.get("sections", []):
            if not isinstance(sec, dict):
                continue
            title = _title_case_if_upper(sec.get("title", "")) or "Section"
            p = doc.add_paragraph()
            _set_para_style(p, STYLE_SECTION)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.add_run(title)
            _render_content(doc, _norm_content_list(sec.get("content")), json_path, state)
            for sub in sec.get("subsections", []) or []:
                if not isinstance(sub, dict):
                    continue
                st = _title_case_if_upper(sub.get("title", "")) or "Subsection"
                ps = doc.add_paragraph()
                _set_para_style(ps, STYLE_SUBSECTION)
                ps.paragraph_format.space_before = Pt(3)
                ps.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                ps.add_run(st)
                _render_content(doc, _norm_content_list(sub.get("content")), json_path, state)
        return

    if not keys:
        # Minimal structure
        for title in ("Introduction", "Method", "Results", "Conclusion"):
            p = doc.add_paragraph()
            _set_para_style(p, STYLE_SECTION)
            p.add_run(title)
            _render_text_block(
                doc, "Content is not provided in JSON. This paragraph is auto-filled."
            )
        return

    for section_key in keys:
        data = config.get(section_key) or {}
        if not isinstance(data, dict):
            continue
        title = (
            _title_case_if_upper(data.get("title", ""))
            or f"Section {section_key.replace('section', '')}"
        )
        p = doc.add_paragraph()
        _set_para_style(p, STYLE_SECTION)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.add_run(title)

        _render_content(doc, _norm_content_list(data.get("content")), json_path, state)

        for sub_key in _subsection_keys(section_key, data):
            sub = data.get(sub_key) or {}
            if not isinstance(sub, dict):
                continue
            st = _title_case_if_upper(sub.get("title", "")) or "Subsection"
            ps = doc.add_paragraph()
            _set_para_style(ps, STYLE_SUBSECTION)
            ps.paragraph_format.space_before = Pt(3)
            ps.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            ps.add_run(st)
            _render_content(doc, _norm_content_list(sub.get("content")), json_path, state)


def _safe_ack_text(config: dict) -> str:
    ack = str(config.get("acknowledgment", "") or config.get("acknowledgement", "")).strip()
    if ack:
        return ack
    return "The authors would like to thank all parties who supported this work."


def _safe_references(config: dict) -> list[str]:
    refs = config.get("references")
    if isinstance(refs, dict) and isinstance(refs.get("content"), list):
        items = [str(x).strip() for x in refs.get("content") if str(x).strip()]
        return items
    if isinstance(refs, list):
        items: list[str] = []
        for x in refs:
            if isinstance(x, str) and x.strip():
                items.append(x.strip())
            elif isinstance(x, dict) and str(x.get("text", "")).strip():
                items.append(str(x.get("text")).strip())
        return items
    return [
        'A. Author, "Placeholder reference title," Journal Name, vol. 1, no. 1, pp. 1–5, 2026.',
        'B. Author, "Another placeholder reference," Proceedings Name, pp. 10–15, 2025.',
    ]


def _add_ack_and_references(doc: Document, config: dict) -> None:
    # Acknowledgements
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_SECTION)
    p.add_run("Acknowledgements")
    _render_text_block(doc, _safe_ack_text(config), style_id=STYLE_BODY)

    # References
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_SECTION)
    p.add_run("References")
    for ref in _safe_references(config):
        pr = doc.add_paragraph()
        _set_para_style(pr, STYLE_REFERENCE)
        pr.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _append_rich_text(pr, ref)


def verify_document(json_path: Path, docx_path: Path) -> list[str]:
    issues: list[str] = []
    if not docx_path.exists():
        return [f"DOCX tidak ditemukan: {docx_path}"]
    if not json_path.exists():
        return [f"JSON tidak ditemukan: {json_path}"]

    config = json.loads(json_path.read_text(encoding="utf-8"))
    wanted_title = _safe_title(config)
    wanted_keywords = _safe_keywords(config)
    wanted_sections = []
    for sk in _section_keys(config):
        sd = config.get(sk) or {}
        if isinstance(sd, dict):
            wanted_sections.append(_title_case_if_upper(sd.get("title", "")))

    wanted_fig_titles: list[str] = []
    wanted_tbl_titles: list[str] = []
    wanted_eq_count = 0
    for sk in _section_keys(config):
        sd = config.get(sk)
        if not isinstance(sd, dict):
            continue
        for item in _norm_content_list(sd.get("content")):
            if isinstance(item, dict) and str(item.get("id", "")).lower() == "gambar":
                wanted_fig_titles.append(str(item.get("Title", "")).strip())
            if isinstance(item, dict) and str(item.get("id", "")).lower() == "tabel":
                wanted_tbl_titles.append(str(item.get("Title", "")).strip())
            if isinstance(item, dict) and str(item.get("id", "")).lower() == "rumus":
                wanted_eq_count += 1
        for subk in _subsection_keys(sk, sd):
            subd = sd.get(subk)
            if not isinstance(subd, dict):
                continue
            for item in _norm_content_list(subd.get("content")):
                if isinstance(item, dict) and str(item.get("id", "")).lower() == "gambar":
                    wanted_fig_titles.append(str(item.get("Title", "")).strip())
                if isinstance(item, dict) and str(item.get("id", "")).lower() == "tabel":
                    wanted_tbl_titles.append(str(item.get("Title", "")).strip())
                if isinstance(item, dict) and str(item.get("id", "")).lower() == "rumus":
                    wanted_eq_count += 1

    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "m": MATH_NS,
    }
    with zipfile.ZipFile(docx_path) as zf:
        names = set(zf.namelist())
        if "word/header1.xml" not in names:
            issues.append("header1.xml hilang (header/footer template tidak terbawa)")
        else:
            header_xml = etree.fromstring(zf.read("word/header1.xml"))
            header_text = "".join(t for t in header_xml.xpath(".//w:t/text()", namespaces=ns) if t)
            if "CERiMRE" not in header_text:
                issues.append("Header tidak mengandung teks CERiMRE (cek template/header)")

        styles_xml = etree.fromstring(zf.read("word/styles.xml"))
        style_ids = set(styles_xml.xpath(".//w:style/@w:styleId", namespaces=ns))
        for sid in (
            STYLE_TITLE,
            STYLE_AUTHOR,
            STYLE_ABSTRACT,
            STYLE_KEYWORDS,
            STYLE_SECTION,
            STYLE_SUBSECTION,
            STYLE_BODY,
            STYLE_FIGURE,
            STYLE_FIGURE_CAPTION,
            STYLE_REFERENCE,
        ):
            if sid not in style_ids:
                issues.append(f"Style hilang di styles.xml: {sid}")

        doc_xml = etree.fromstring(zf.read("word/document.xml"))
        all_text = " ".join(t for t in doc_xml.xpath(".//w:t/text()", namespaces=ns) if t)

        if wanted_title[:30] and wanted_title[:30] not in all_text:
            issues.append("Title tidak terdeteksi dalam document.xml")
        for kw in wanted_keywords[:6]:
            if kw and kw not in all_text:
                issues.append(f"Keyword tidak terdeteksi: {kw}")
                break
        for st in wanted_sections[:3]:
            if st and st not in all_text:
                issues.append(f"Section title tidak terdeteksi: {st}")
                break

        for ft in [x for x in wanted_fig_titles if x][:3]:
            if ft and ft not in all_text:
                issues.append(f"Figure caption tidak terdeteksi: {ft}")
                break

        for tt in [x for x in wanted_tbl_titles if x][:3]:
            if tt and tt not in all_text:
                issues.append(f"Table title tidak terdeteksi: {tt}")
                break

        math_count = len(doc_xml.xpath(".//m:oMath | .//m:oMathPara", namespaces=ns))
        if wanted_eq_count and math_count < wanted_eq_count:
            issues.append(
                f"Jumlah equation OMML kurang: found={math_count}, expected>={wanted_eq_count}"
            )

        # Check table caption spacing: paragraphs starting with 'Table'
        table_caps = doc_xml.xpath(
            ".//w:p[.//w:t[starts-with(normalize-space(.), 'Table ')]]",
            namespaces=ns,
        )
        if table_caps:
            p0 = table_caps[0]
            sp = p0.find("w:pPr/w:spacing", namespaces=ns)
            before = (
                int(sp.get(qn("w:before"), "0")) if sp is not None and sp.get(qn("w:before")) else 0
            )
            if before < 120:
                issues.append(f"Spacing before Table caption < 6pt (tw={before})")

    return issues


def build_document(
    json_path: Path = JSON_PATH,
    output_path: Path | None = None,
    template_path: Path = TEMPLATE_PATH,
) -> Path:
    config = json.loads(Path(json_path).read_text(encoding="utf-8"))

    final_output = (
        Path(output_path) if output_path else Path(json_path).parent / f"{JOURNAL_NAME}_output.docx"
    )
    final_output.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy(str(template_path), str(final_output))
    doc = Document(str(final_output))
    _clear_document_body(doc)

    state = RenderState()

    _add_title_block(doc, config)
    _add_authors_block(doc, config)
    _add_abstract_block(doc, config)
    _add_keywords_block(doc, config)
    _render_sections(doc, config, Path(json_path), state)
    _add_ack_and_references(doc, config)

    _set_ai_prompt_color_red(doc)
    doc.save(str(final_output))
    return final_output


def main() -> None:
    json_arg = Path(sys.argv[1]) if len(sys.argv) >= 2 else JSON_PATH
    output_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
    template_arg = Path(sys.argv[3]) if len(sys.argv) >= 4 else TEMPLATE_PATH

    if not json_arg.exists():
        print(f"JSON tidak ditemukan: {json_arg}")
        sys.exit(1)
    if not template_arg.exists():
        print(f"Template tidak ditemukan: {template_arg}")
        sys.exit(1)

    out = build_document(json_arg, output_arg, template_arg)
    issues = verify_document(json_arg, out)
    if issues:
        print("[VERIFY] FAILED")
        for i in issues:
            print(f" - {i}")
        sys.exit(2)
    print(f"Generated: {out}")
    print("[VERIFY] OK")


if __name__ == "__main__":
    main()
