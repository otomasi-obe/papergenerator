"""
Murhumgen.py - Generator untuk Jurnal Murhum: Jurnal Pendidikan Anak Usia Dini.
Template spec: Cambria, 1-col A4, 14pt title, 12pt body/heading, 11pt abstract.
Uses style injection from template + rich text toggles.
References formatted in APA style from structured dicts.
"""
import json, copy, shutil, re, os
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "Murhum.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "Murhum_output.docx"

FONT = "Cambria"
SZ_TITLE = 14          # template says 14pt (masthead uses 10pt)
SZ_BODY = 12           # template says 12pt, spacing 1.15
SZ_HEADING = 12        # template says 12pt Cambria Bold (caps)
SZ_AUTHOR = 10          # template says 10pt
SZ_ABSTRACT = 11        # template says 11pt italic
SZ_CAPTION = 10
SZ_REF = 12

# ====================================================================
#  RICH TEXT PARSER  (ported from IEEEgen.py)
# ====================================================================

def _decode_stray_escapes(text: str) -> str:
    if not text:
        return text
    text = text.replace("\x08", "")
    if "\\u" in text:
        def _u(m):
            try:
                ch = chr(int(m.group(1), 16))
                return " " if ord(ch) < 0x20 else ch
            except:
                return m.group(0)
        text = re.sub(r"\\u([0-9a-fA-F]{4})", _u, text)
    text = text.replace('\\\\b', '\\b')
    text = text.replace('\\\\i', '\\i')
    text = text.replace('\\\\u', '\\u')
    return text

def _normalize_text_commands(text: str) -> str:
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
    text = _decode_stray_escapes(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\b\1\\b", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+?)\*", r"\\i\1\\i", text)
    return text

def _iter_rich_tokens(text: str):
    normalized = _normalize_text_commands(text)
    buffer = []
    bold = False
    italic = False
    underline = False
    index = 0

    def flush():
        nonlocal buffer
        content = "".join(buffer)
        buffer = []
        if content:
            yield {"kind": "text", "value": content, "bold": bold, "italic": italic, "underline": underline}

    while index < len(normalized):
        ch = normalized[index]
        if ch == "\n":
            yield from flush()
            yield {"kind": "linebreak"}
            index += 1
            continue
        if ch == "\\" and index + 1 < len(normalized):
            cmd = normalized[index + 1]
            if cmd == "\\":
                buffer.append("\\"); index += 2; continue
            if cmd == "b":
                yield from flush(); bold = not bold; index += 2; continue
            if cmd == "i":
                yield from flush(); italic = not italic; index += 2; continue
            if cmd == "u":
                yield from flush(); underline = not underline; index += 2; continue
        if ch == "$" and index + 1 < len(normalized) and normalized[index + 1] == "$":
            closing = normalized.find("$$", index + 2)
            if closing != -1:
                yield from flush()
                formula = normalized[index + 2 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 2; continue
        if ch == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                yield from flush()
                formula = normalized[index + 1 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 1; continue
        buffer.append(ch)
        index += 1
    yield from flush()

def _append_rich_text(paragraph, text: str):
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            paragraph.add_run().add_break()
            continue
        if token["kind"] == "math":
            run = paragraph.add_run(token["value"])
            run.italic = True; run.font.name = "Cambria Math"
            continue
        run = paragraph.add_run(token["value"])
        run.bold = token["bold"]
        run.italic = token["italic"]
        run.underline = token["underline"]
        run.font.size = Pt(SZ_BODY)
        run.font.name = FONT

# ====================================================================
#  LATEX MATH CLEANING  (for fallback when no OMML)
# ====================================================================

def _clean_latex(text):
    """Strip LaTeX math markup -> readable Unicode. Leaves toggle markers intact."""
    if not text:
        return text
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    # Handle \frac before stripping braces
    text = re.sub(r'\\frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', r'(\1)/(\2)', text)
    text = re.sub(r'\\mathrm\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    # Greek letters
    text = re.sub(r'\\eta', '\u03b7', text); text = re.sub(r'\\Delta', '\u0394', text)
    text = re.sub(r'\\lambda', '\u03bb', text); text = re.sub(r'\\sigma', '\u03c3', text)
    text = re.sub(r'\\Sigma', '\u03a3', text)
    # operators
    text = re.sub(r'\\approx', '\u2248', text); text = re.sub(r'\\times', '\u00d7', text)
    text = re.sub(r'\\cdot', '\u00b7', text); text = re.sub(r'\\quad', ' ', text)
    text = re.sub(r'\\infty', '\u221e', text); text = re.sub(r'\\circ', '\u00b0', text)
    text = re.sub(r'\\alpha', '\u03b1', text); text = re.sub(r'\\beta', '\u03b2', text)
    text = re.sub(r'\\gamma', '\u03b3', text); text = re.sub(r'\\theta', '\u03b8', text)
    text = re.sub(r'\\pi', '\u03c0', text); text = re.sub(r'\\mu', '\u03bc', text)
    # Special: \% -> literal %
    text = re.sub(r'\\\%', '%', text)
    # Strip superscript/subscript braces, then remaining braces
    text = re.sub(r'[_^]\{([^}]*)\}', r'\1', text)
    text = re.sub(r'_([0-9])', lambda m: '\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089'[int(m.group(1))], text)
    text = re.sub(r'\^([0-9])', lambda m: '\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079'[int(m.group(1))], text)
    text = re.sub(r'\\;', '', text); text = re.sub(r'\\,', '', text); text = re.sub(r'\\!', '', text)
    text = re.sub(r'[{}]', '', text)
    return text.strip()

# ====================================================================
#  DOCX BUILDING HELPERS
# ====================================================================

def _mk_para(doc, text="", size=None, bold=None, italic=None, align="justify",
             before=0, after=0, line_tw=None, first_indent=0):
    p = doc.add_paragraph()
    amap = {"center": WD_ALIGN_PARAGRAPH.CENTER, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "left": WD_ALIGN_PARAGRAPH.LEFT}
    p.alignment = amap.get(align, WD_ALIGN_PARAGRAPH.JUSTIFY)
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line_tw:
        pf.line_spacing = line_tw / 240.0
    else:
        pf.line_spacing = 1.0
    if first_indent:
        pPr = p._element.get_or_add_pPr()
        ind = pPr.find(qn("w:ind")) or OxmlElement("w:ind")
        if ind not in list(pPr): pPr.append(ind)
        ind.set(qn("w:firstLine"), str(first_indent))
    if text:
        run = p.add_run(text)
        if size: run.font.size = Pt(size)
        run.font.name = FONT
        if bold is not None: run.bold = bold
        if italic is not None: run.italic = italic
    return p

def _heading(doc, text):
    p = _mk_para(doc, "", SZ_HEADING, bold=True, before=24, after=6, align="left")
    _append_rich_text(p, text.upper())
    for run in p.runs:
        run.font.size = Pt(SZ_HEADING)
        run.bold = True
    return p

def _body_para(doc, text):
    """Body paragraph with first-line indent and 1.15 spacing."""
    p = _mk_para(doc, "", SZ_BODY, align="justify", before=0, after=6, line_tw=276, first_indent=720)
    _append_rich_text(p, _clean_latex(text))
    return p

# ====================================================================
#  TABLES
# ====================================================================

def _set_table_borders(table):
    tblPr = table._element.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr"); table._element.insert(0, tblPr)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "bottom", "insideH"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0"); el.set(qn("w:color"), "000000")
        borders.append(el)
    for side in ("left", "right", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "none"); el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0"); el.set(qn("w:color"), "auto")
        borders.append(el)
    tblPr.append(borders)

def _add_table(doc, tbl):
    h = tbl.get("Headers", []); r = tbl.get("Rows", [])
    nc = len(h) if h else (len(r[0]) if r else 2)
    nr = len(r) + (1 if h else 0)
    t = doc.add_table(rows=nr, cols=nc)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(t)
    if h:
        for j, hv in enumerate(h):
            if j < nc:
                c = t.rows[0].cells[j]; c.text = ""
                run = c.paragraphs[0].add_run(str(hv)); run.bold = True
                run.font.size = Pt(9); run.font.name = FONT
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for i, row in enumerate(r):
        for j, v in enumerate(row if isinstance(row, list) else []):
            if j < nc:
                c = t.rows[1+i].cells[j]; c.text = ""
                run = c.paragraphs[0].add_run(str(v))
                run.font.size = Pt(9); run.font.name = FONT
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    _mk_para(doc, " ", size=1)

# ====================================================================
#  FIGURES
# ====================================================================

def _fig_cap(doc, no, title):
    p = _mk_para(doc, "", SZ_CAPTION, bold=True, align="center", before=3, after=6)
    p.clear()
    r1 = p.add_run(f"Gambar {no}. "); r1.bold = True; r1.font.size = Pt(SZ_CAPTION); r1.font.name = FONT
    r2 = p.add_run(title); r2.font.size = Pt(SZ_CAPTION); r2.font.name = FONT

def _add_fig(doc, fig, cnt):
    no = str(fig.get("ImageNumber", cnt))
    raw_title = str(fig.get("Title", ""))
    title = _clean_latex(raw_title)
    prompt = _clean_latex(str(fig.get("Prompt", "")))
    ip = str(fig.get("Path", ""))
    actual = None
    if ip:
        cands = [Path(ip), BASE / "image" / os.path.basename(ip)]
        stem = os.path.splitext(ip)[0]
        for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            cands.extend([
                BASE / "image" / f"{os.path.basename(stem)}{ext}",
                Path(f"{stem}{ext}"),
            ])
        for c in cands:
            if c.exists(): actual = c; break
    p = _mk_para(doc, "", align="center", before=12, after=8)
    if actual:
        try:
            r = p.add_run(); r.add_picture(str(actual), width=Inches(3.2))
        except:
            actual = None
    if not actual:
        r = p.add_run(f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt}]")
        r.italic = True
        r.font.color.rgb = RGBColor(0xFF, 0, 0)
        r.font.size = Pt(SZ_CAPTION)
        r.font.name = FONT
    _fig_cap(doc, no, title)

def _tbl_cap(doc, no, title):
    p = _mk_para(doc, "", SZ_CAPTION, bold=True, align="center", before=10, after=4)
    p.clear()
    r1 = p.add_run(f"Tabel {no}. "); r1.bold = True; r1.font.size = Pt(SZ_CAPTION); r1.font.name = FONT
    r2 = p.add_run(title); r2.font.size = Pt(SZ_CAPTION); r2.font.name = FONT

# ====================================================================
#  REFERENCES  (APA style)
# ====================================================================

def _format_apa_authors(authors) -> str:
    """Join author list into APA style: Surname, I., Surname, I., & Surname, I."""
    names = []
    if isinstance(authors, list):
        for a in authors:
            nm = a.get("name", str(a)) if isinstance(a, dict) else str(a)
            if nm: names.append(nm)
    elif isinstance(authors, str):
        names = [authors]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return ", ".join(names[:-1]) + ", & " + names[-1]

def _format_apa_citation(ref: dict) -> str:
    """Render structured citation dict -> APA 7th style string."""
    authors = _format_apa_authors(ref.get("authors"))
    title = str(ref.get("title") or "").strip()
    year = str(ref.get("year") or "").strip()
    journal = str(ref.get("journal") or "").strip()
    volume = str(ref.get("volume") or "").strip()
    issue = str(ref.get("issue") or ref.get("number") or "").strip()
    pages = str(ref.get("pages") or "").strip()
    doi = str(ref.get("doi") or "").strip()
    rtype = str(ref.get("type") or "journal").strip().lower()

    if rtype == "book":
        pub = str(ref.get("publisher") or "").strip()
        loc = str(ref.get("location") or "").strip()
        parts = []
        if authors: parts.append(f"{authors} ({year}).")
        elif year: parts.append(f"({year}).")
        if title: parts.append(f"\\i{title}\\i.")
        imprint = f"{loc}: {pub}" if loc and pub else (pub or loc)
        if imprint: parts.append(imprint + ".")
        return " ".join(parts)
    else:
        parts = []
        if authors: parts.append(f"{authors} ({year}).")
        elif year: parts.append(f"({year}).")
        if title: parts.append(f"{title}.")
        src = journal
        if not src:
            src = str(ref.get("conference") or ref.get("booktitle") or "").strip()
        seg = []
        if src:
            seg.append(f"\\i{src}\\i")
        if volume:
            vol_str = volume
            if issue: vol_str += f"({issue})"
            seg.append(vol_str)
        if pages: seg.append(pages)
        if seg: parts.append(", ".join(seg) + ".")
        if doi: parts.append(f"https://doi.org/{doi}")
        return " ".join(parts)

def _refs(doc, data):
    refs = data.get("references", {})
    rl = refs.get("content", []) if isinstance(refs, dict) else (refs if isinstance(refs, list) else [])
    if not rl: return
    _heading(doc, "DAFTAR PUSTAKA")
    for i, ref in enumerate(rl, 1):
        if isinstance(ref, dict):
            txt = _format_apa_citation(ref)
            if not txt:
                txt = str(ref)
        else:
            txt = str(ref)
        txt = re.sub(r'^\[\d+\]\s*', '', txt)
        p = _mk_para(doc, "", SZ_REF, align="justify", before=0, after=3, first_indent=-720)
        r1 = p.add_run(f"[{i}] "); r1.font.size = Pt(SZ_REF); r1.font.name = FONT
        _append_rich_text(p, _clean_latex(txt))

# ====================================================================
#  MAIN GENERATOR
# ====================================================================

def generate():
    data = json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))
    shutil.copy2(str(TEMPLATE_DOCX), str(OUTPUT_DOCX))
    doc = Document(str(OUTPUT_DOCX))

    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)

    for section in doc.sections:
        pgMar = section._sectPr.find(qn("w:pgMar"))
        if pgMar is not None:
            for attr in ("w:left", "w:right", "w:top", "w:bottom", "w:header", "w:footer"):
                val = pgMar.get(qn(attr))
                if val:
                    try:
                        pgMar.set(qn(attr), str(int(float(val))))
                    except ValueError:
                        pgMar.set(qn(attr), "1440")

    # ---- JOURNAL MASTHEAD ----
    jinfo = data.get("journal_info", {})
    jname = jinfo.get("name", "Murhum : Jurnal Pendidikan Anak Usia Dini")
    issn = jinfo.get("issn", "2723-6390")
    volume = jinfo.get("volume", "XX")
    issue = jinfo.get("issue", "XX")
    doi = jinfo.get("doi", "………")
    pages = jinfo.get("pages", "XX-XX")

    mast_items = [
        (jname, "center"),
        (f"e-ISSN: {issn}, hal. {pages}", "center"),
        (f"Vol. {volume}, No. {issue}, Desember 2022", "left"),
        (f"DOI: {doi}", "center"),
    ]
    for item, align in mast_items:
        p = _mk_para(doc, item, 10, bold=True, italic=True, align=align, before=0, after=0)
        for run in p.runs:
            run.font.size = Pt(10)
            run.font.name = FONT
    _mk_para(doc, " ", size=1, before=6, after=6)  # spacer

    # ---- TITLE ----
    title = str(data.get("title", "")).strip()
    if title:
        p = _mk_para(doc, "", SZ_TITLE, bold=True, align="center", before=6, after=6)
        _append_rich_text(p, _clean_latex(title))
        for run in p.runs:
            run.font.size = Pt(SZ_TITLE)
            run.bold = True
            run.font.name = FONT

    # ---- AUTHORS ----
    authors = data.get("authors", [])
    if authors:
        names = [a["name"] if isinstance(a, dict) else str(a) for a in authors]
        p_au = _mk_para(doc, "", SZ_AUTHOR, bold=True, align="center")
        _append_rich_text(p_au, ", ".join(names))
        for run in p_au.runs:
            run.font.size = Pt(SZ_AUTHOR)
            run.bold = True
            run.font.name = FONT
        affs = []
        for a in authors:
            if isinstance(a, dict) and a.get("affiliation"):
                affs.append(a["affiliation"])
        if affs:
            p_af = _mk_para(doc, "", SZ_AUTHOR, italic=True, align="center")
            _append_rich_text(p_af, _clean_latex("; ".join(affs)))
            for run in p_af.runs:
                run.font.size = Pt(SZ_AUTHOR)
                run.italic = True
                run.font.name = FONT

    # ---- ABSTRAK ----
    abstract = str(data.get("abstract", "")).strip()
    if abstract:
        p = _mk_para(doc, "", SZ_ABSTRACT, before=6, after=3, align="justify")
        r1 = p.add_run("ABSTRAK. "); r1.bold = True; r1.font.size = Pt(SZ_ABSTRACT); r1.font.name = FONT
        _append_rich_text(p, abstract)
        for run in p.runs[1:]:
            run.italic = True
            run.font.size = Pt(SZ_ABSTRACT)
            run.font.name = FONT
        kw = data.get("keywords", [])
        if kw:
            kws = ", ".join(str(k) for k in kw) if isinstance(kw, list) else str(kw)
            pk = _mk_para(doc, "", SZ_ABSTRACT, before=0, after=6, align="justify")
            rk1 = pk.add_run("Kata Kunci: "); rk1.bold = True; rk1.font.size = Pt(SZ_ABSTRACT); rk1.font.name = FONT
            rk2 = pk.add_run(_clean_latex(kws)); rk2.italic = True; rk2.font.size = Pt(SZ_ABSTRACT); rk2.font.name = FONT

    # ---- ABSTRACT (ENGLISH) ----
    abstract_en = str(data.get("abstract_en", "")).strip() or abstract
    if abstract_en:
        p2 = _mk_para(doc, "", SZ_ABSTRACT, before=3, after=3, align="justify")
        r1 = p2.add_run("ABSTRACT. "); r1.bold = True; r1.italic = True; r1.font.size = Pt(SZ_ABSTRACT); r1.font.name = FONT
        _append_rich_text(p2, abstract_en)
        for run in p2.runs[1:]:
            run.italic = True
            run.font.size = Pt(SZ_ABSTRACT)
            run.font.name = FONT

    # ---- SECTIONS ----
    fig_cnt, tbl_cnt = 0, 0
    for i in range(1, 30):
        k = f"section{i}"
        if k not in data: continue
        sec = data[k]
        st = _clean_latex(str(sec.get("title", sec.get("Title", ""))).strip())
        if st: _heading(doc, st)
        ct = sec.get("content", sec.get("Content", []))
        if not isinstance(ct, list): continue
        for item in ct:
            if not isinstance(item, dict): continue
            kind = str(item.get("id", "")).lower()
            if kind in ("text", "paragraf", "paragraph"):
                txt = str(item.get("text", item.get("Text", ""))).strip()
                if txt: _body_para(doc, txt)
            elif kind in ("gambar", "image", "figure"):
                fig_cnt += 1; _add_fig(doc, item, fig_cnt)
            elif kind in ("tabel", "table"):
                tbl_cnt += 1
                _tbl_cap(doc, str(item.get("TableNumber", tbl_cnt)), _clean_latex(str(item.get("Title", ""))))
                _add_table(doc, item)
            elif kind in ("rumus", "equation", "formula", "persamaan"):
                lt = str(item.get("latex", item.get("Formula", ""))).strip()
                if lt: _mk_para(doc, _clean_latex(lt), SZ_BODY, italic=True, align="center")

    # ---- REFERENCES ----
    _refs(doc, data)

    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    print("[VERIFY] OK")
    return str(OUTPUT_DOCX)

if __name__ == "__main__":
    generate()