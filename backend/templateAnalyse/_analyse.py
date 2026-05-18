"""
_analyse.py  —  Analisa lengkap semua file template DOCX/DOC di folder Template.
Mencakup: format, package parts, metadata, rels, settings, theme, fontTable,
styles (docDefaults + semua tipe), numbering, header/footer, dan body
(sectPr lengkap + semua paragraf + tabel).
ULTIMACOMP.doc dideteksi sebagai Office Theme dan dianalisa isinya.
"""
import zipfile, sys, io, json
from pathlib import Path
from lxml import etree

BASE = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────
# Namespace helpers
# ─────────────────────────────────────────────────────────────────
NS_MAP_STRICT = {
    b"http://purl.oclc.org/ooxml/wordprocessingml/main":
        b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    b"http://purl.oclc.org/ooxml/officeDocument/relationships":
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/drawingml/main":
        b"http://schemas.openxmlformats.org/drawingml/2006/main",
    b"http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing":
        b"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    b"http://purl.oclc.org/ooxml/officeDocument/math":
        b"http://schemas.openxmlformats.org/officeDocument/2006/math",
}

NS_W   = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R   = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_A   = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_CORE= "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS_DC  = "http://purl.org/dc/elements/1.1/"
NS_DCTERMS = "http://purl.org/dc/terms/"
NS_APP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
NS_CT  = "http://schemas.openxmlformats.org/package/2006/content-types"

wq  = lambda tag: f"{{{NS_W}}}{tag}"
aq  = lambda tag: f"{{{NS_A}}}{tag}"
rq  = lambda tag: f"{{{NS_R}}}{tag}"
pkq = lambda tag: f"{{{NS_PKG}}}{tag}"

def strict_to_trans(data: bytes) -> bytes:
    for old, new in NS_MAP_STRICT.items():
        data = data.replace(old, new)
    return data

# ─────────────────────────────────────────────────────────────────
# Unit helpers
# ─────────────────────────────────────────────────────────────────
def norm_tw(v) -> str:
    """Normalize dimension value to twips (integer string)."""
    if v is None:
        return "—"
    s = str(v).strip()
    if s.lower().endswith("pt"):
        s = s[:-2].strip()
        try:
            return str(int(round(float(s) * 20)))
        except ValueError:
            return v
    if "." in s:
        try:
            return str(int(round(float(s))))
        except ValueError:
            return s
    return s

def tw_pt(v) -> str:
    """Display: '1440tw (72.0pt)'"""
    if v is None:
        return "—"
    tw = norm_tw(v)
    try:
        return f"{tw}tw ({int(tw)/20:.2f}pt)"
    except Exception:
        return str(v)

def half_pt(v) -> str:
    """Display half-point value as pt: '24hpt (12pt)'"""
    if v is None:
        return "—"
    try:
        return f"{v}hpt ({int(v)/2:.1f}pt)"
    except Exception:
        return str(v)

def tw_int(v) -> int | None:
    """Return twips as int when possible."""
    if v is None:
        return None
    try:
        return int(norm_tw(v))
    except Exception:
        return None

def fmt_tw(v: int | float | None) -> str:
    """Display a twips value as tw + pt, keeping decimals when needed."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}tw ({v/20:.2f}pt)"
    return f"{v}tw ({v/20:.2f}pt)"

def _column_layout_details(sp) -> list[str]:
    """Compute effective text-area width and derived column widths from sectPr."""
    lines = []
    pgsz  = sp.find(wq("pgSz"))
    pgmar = sp.find(wq("pgMar"))
    cols  = sp.find(wq("cols"))
    if pgsz is None or pgmar is None:
        return lines

    page_w_tw = tw_int(pgsz.get(wq("w")))
    left_tw   = tw_int(pgmar.get(wq("left"))) or 0
    right_tw  = tw_int(pgmar.get(wq("right"))) or 0
    gutter_tw = tw_int(pgmar.get(wq("gutter"))) or 0
    if page_w_tw is None:
        return lines

    text_area_tw = page_w_tw - left_tw - right_tw - gutter_tw
    lines.append(f"    textArea: pageWidth={fmt_tw(page_w_tw)}  usable={fmt_tw(text_area_tw)}")

    if cols is None:
        lines.append(f"    derivedCols: [single={fmt_tw(text_area_tw)}]")
        return lines

    num = cols.get(wq("num"), "1")
    try:
        num_i = int(num)
    except Exception:
        num_i = 1
    gap_tw = tw_int(cols.get(wq("space"))) or 0
    gap_total_tw = max(num_i - 1, 0) * gap_tw
    equal_width = cols.get(wq("equalWidth"))
    child_col_els = cols.findall(wq("col"))
    col_defs = [tw_int(cd.get(wq("w"))) for cd in child_col_els]
    col_defs = [value for value in col_defs if value is not None]
    child_spaces = [tw_int(cd.get(wq("space"))) for cd in child_col_els]
    child_spaces = [value for value in child_spaces if value is not None]

    lines.append(f"    colsSpaceTotal: {fmt_tw(gap_total_tw)}")
    if child_spaces:
        child_spaces_s = ", ".join(fmt_tw(value) for value in child_spaces)
        lines.append(f"    childColSpaces: [{child_spaces_s}]  total={fmt_tw(sum(child_spaces))}")
    effective_gap_total_tw = sum(child_spaces) if child_spaces else gap_total_tw
    lines.append(f"    effectiveGapTotal: {fmt_tw(effective_gap_total_tw)}")
    if num_i > 0:
        text_area_based = (text_area_tw - effective_gap_total_tw) / num_i
        widths_s = ", ".join(fmt_tw(text_area_based) for _ in range(num_i))
        lines.append(f"    textAreaBasedCols: [{widths_s}]")

    if col_defs:
        widths_s = ", ".join(fmt_tw(value) for value in col_defs)
        declared_total_tw = sum(col_defs)
        delta_tw = text_area_tw - declared_total_tw - effective_gap_total_tw
        lines.append(f"    declaredCols: [{widths_s}]  total={fmt_tw(declared_total_tw)}")
        lines.append(f"    cols+effectiveGap delta vs textArea: {fmt_tw(delta_tw)}")
        if delta_tw != 0:
            direction = "under" if delta_tw > 0 else "over"
            lines.append(f"    note: declared column layout is {direction} textArea by {fmt_tw(abs(delta_tw))}; compare this delta against the original template")
        return lines

    if num_i <= 0:
        return lines

    effective_width_tw = (text_area_tw - effective_gap_total_tw) / num_i
    widths_s = ", ".join(fmt_tw(effective_width_tw) for _ in range(num_i))
    lines.append(f"    derivedCols: equalWidth={equal_width}  [{widths_s}]")
    return lines

# ─────────────────────────────────────────────────────────────────
# Low-level XML reader
# ─────────────────────────────────────────────────────────────────
def read_xml(z: zipfile.ZipFile, inner: str, fix_strict: bool = True) -> etree._Element | None:
    names = z.namelist()
    if inner not in names:
        return None
    raw = z.read(inner)
    if fix_strict:
        raw = strict_to_trans(raw)
    return etree.fromstring(raw)

# ─────────────────────────────────────────────────────────────────
# Format detection
# ─────────────────────────────────────────────────────────────────
def detect_format(zf: zipfile.ZipFile) -> str:
    names = zf.namelist()
    if "word/document.xml" not in names:
        if any("theme" in n for n in names):
            return "OFFICE THEME (no document.xml)"
        return "UNKNOWN"
    raw = zf.read("word/document.xml")
    if b"purl.oclc.org/ooxml" in raw:
        return "OOXML STRICT"
    return "OOXML TRANSITIONAL"

# ─────────────────────────────────────────────────────────────────
# § 1  Package parts ([Content_Types].xml)
# ─────────────────────────────────────────────────────────────────
def analyse_content_types(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    names = sorted(zf.namelist())
    lines.append(f"  Total parts: {len(names)}")
    for n in names:
        size = zf.getinfo(n).file_size
        lines.append(f"    {n}  ({size:,} bytes)")
    return lines

# ─────────────────────────────────────────────────────────────────
# § 2  Core & App properties
# ─────────────────────────────────────────────────────────────────
def analyse_core_props(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    root = read_xml(zf, "docProps/core.xml", fix_strict=False)
    if root is None:
        lines.append("  (tidak ada core.xml)")
        return lines
    fields = [
        (f"{{{NS_DC}}}creator",       "Creator"),
        (f"{{{NS_DC}}}title",         "Title"),
        (f"{{{NS_DC}}}subject",       "Subject"),
        (f"{{{NS_DC}}}description",   "Description"),
        (f"{{{NS_DCTERMS}}}created",  "Created"),
        (f"{{{NS_DCTERMS}}}modified", "Modified"),
        (f"{{{NS_CORE}}}lastModifiedBy",  "LastModifiedBy"),
        (f"{{{NS_CORE}}}revision",    "Revision"),
        (f"{{{NS_CORE}}}keywords",    "Keywords"),
    ]
    for tag, label in fields:
        el = root.find(tag)
        if el is not None and el.text:
            lines.append(f"  {label}: {el.text.strip()}")
    app = read_xml(zf, "docProps/app.xml", fix_strict=False)
    if app is not None:
        ns_app = f"{{{NS_APP}}}"
        for tag in ("Application", "AppVersion", "Pages", "Words", "Characters", "DocSecurity", "Template"):
            el = app.find(f"{ns_app}{tag}")
            if el is not None and el.text:
                lines.append(f"  {tag}: {el.text.strip()}")
    return lines

# ─────────────────────────────────────────────────────────────────
# § 3  Relationships (word/_rels/document.xml.rels)
# ─────────────────────────────────────────────────────────────────
def analyse_rels(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    root = read_xml(zf, "word/_rels/document.xml.rels", fix_strict=False)
    if root is None:
        lines.append("  (tidak ada document.xml.rels)")
        return lines
    for rel in root:
        rid    = rel.get("Id", "")
        rtype  = rel.get("Type", "").split("/")[-1]
        target = rel.get("Target", "")
        lines.append(f"  {rid:6s}  {rtype:25s}  → {target}")
    return lines

# ─────────────────────────────────────────────────────────────────
# § 4  Settings (word/settings.xml)
# ─────────────────────────────────────────────────────────────────
def analyse_settings(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    root = read_xml(zf, "word/settings.xml")
    if root is None:
        lines.append("  (tidak ada settings.xml)")
        return lines

    # Interesting top-level elements
    interested = {
        "zoom":                     lambda e: f"zoom {e.get(wq('percent'), e.get('percent','?'))}%",
        "defaultTabStop":           lambda e: f"defaultTabStop {tw_pt(e.get(wq('val')))}",
        "characterSpacingControl":  lambda e: f"characterSpacingControl={e.get(wq('val'),'?')}",
        "evenAndOddHeaders":        lambda e: "evenAndOddHeaders=ON",
        "titlePg":                  lambda e: "titlePg (first-page header) declared",
        "themeFontLang":            lambda e: f"themeFontLang={e.get(wq('val'),'?')}",
        "decimalSymbol":            lambda e: f"decimalSymbol={e.get(wq('val'),'?')}",
        "listSeparator":            lambda e: f"listSeparator={e.get(wq('val'),'?')}",
        "docId":                    lambda e: f"docId={e.get(wq('val') or 'val','?')}",
        "mathPr":                   lambda e: "mathPr (Math properties present)",
    }
    for child in root:
        tag = child.tag.split("}")[-1]
        if tag in interested:
            try:
                lines.append(f"  {interested[tag](child)}")
            except Exception:
                lines.append(f"  {tag}")
        elif tag == "compat":
            compat_settings = []
            for cc in child:
                ctag = cc.tag.split("}")[-1]
                cval = cc.get(wq("val"), "")
                compat_settings.append(f"{ctag}={cval}" if cval else ctag)
            if compat_settings:
                lines.append(f"  compat: {', '.join(compat_settings)}")
        elif tag == "footnotePr":
            pos = child.find(wq("pos"))
            fmt = child.find(wq("numFmt"))
            parts = []
            if pos is not None: parts.append(f"pos={pos.get(wq('val'),'?')}")
            if fmt is not None: parts.append(f"numFmt={fmt.get(wq('val'),'?')}")
            if parts:
                lines.append(f"  footnotePr: {', '.join(parts)}")
    return lines

# ─────────────────────────────────────────────────────────────────
# § 5  Theme (word/theme/theme1.xml)
# ─────────────────────────────────────────────────────────────────
def analyse_theme(zf: zipfile.ZipFile, inner_path: str = "word/theme/theme1.xml") -> list[str]:
    lines = []
    root = read_xml(zf, inner_path, fix_strict=False)
    if root is None:
        lines.append("  (tidak ada theme1.xml)")
        return lines

    theme_name = root.get("name", "—")
    lines.append(f"  Nama theme: {theme_name}")

    # Color scheme
    cs = root.find(f".//{aq('clrScheme')}")
    if cs is not None:
        cs_name = cs.get("name", "—")
        lines.append(f"  Color scheme: {cs_name}")
        # dk1, lt1, dk2, lt2, accent1-6, hyperlink, folHlink
        for slot in ("dk1","lt1","dk2","lt2",
                     "accent1","accent2","accent3","accent4","accent5","accent6",
                     "hlink","folHlink"):
            el = cs.find(aq(slot))
            if el is None:
                continue
            color = "?"
            for child in el:
                tag = child.tag.split("}")[-1]
                if tag == "srgbClr":
                    color = f"#{child.get('val','?')}"
                elif tag == "sysClr":
                    color = f"sys:{child.get('lastClr','?')}"
                elif tag == "lumMod":
                    color = f"lumMod:{child.get('val','?')}"
            lines.append(f"    {slot:10s}: {color}")

    # Font scheme
    fs = root.find(f".//{aq('fontScheme')}")
    if fs is not None:
        fs_name = fs.get("name", "—")
        lines.append(f"  Font scheme: {fs_name}")
        for region in ("majorFont", "minorFont"):
            fe = fs.find(aq(region))
            if fe is None:
                continue
            lat = fe.find(aq("latin"))
            ea  = fe.find(aq("ea"))
            cs2 = fe.find(aq("cs"))
            lat_val = lat.get("typeface", "—") if lat is not None else "—"
            ea_val  = ea.get("typeface", "—")  if ea  is not None else "—"
            cs_val  = cs2.get("typeface", "—") if cs2 is not None else "—"
            lines.append(f"    {region}: latin={lat_val}  ea={ea_val}  cs={cs_val}")

    return lines

# ─────────────────────────────────────────────────────────────────
# § 6  Font table (word/fontTable.xml)
# ─────────────────────────────────────────────────────────────────
def analyse_font_table(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    root = read_xml(zf, "word/fontTable.xml")
    if root is None:
        lines.append("  (tidak ada fontTable.xml)")
        return lines
    fonts = []
    for f in root.findall(wq("font")):
        fname = f.get(wq("name"), "?")
        charset = f.find(wq("charset"))
        family  = f.find(wq("family"))
        pitch   = f.find(wq("pitch"))
        info_parts = [fname]
        if family  is not None: info_parts.append(family.get(wq("val"),"?"))
        if pitch   is not None: info_parts.append(f"pitch={pitch.get(wq('val'),'?')}")
        if charset is not None: info_parts.append(f"charset={charset.get(wq('val'),'?')}")
        fonts.append("  ".join(info_parts))
    lines.append(f"  Total font deklarasi: {len(fonts)}")
    for fn in fonts:
        lines.append(f"    {fn}")
    return lines

# ─────────────────────────────────────────────────────────────────
# § 7  Styles (word/styles.xml)
# ─────────────────────────────────────────────────────────────────
def _fmt_rpr(rpr) -> str:
    if rpr is None:
        return ""
    parts = []
    rfonts = rpr.find(wq("rFonts"))
    if rfonts is not None:
        for a in ("ascii","hAnsi","eastAsia","cs"):
            v = rfonts.get(wq(a))
            if v: parts.append(f"font_{a}={v}")
    sz   = rpr.find(wq("sz"))
    szcs = rpr.find(wq("szCs"))
    if sz   is not None: parts.append(f"sz={half_pt(sz.get(wq('val')))}")
    if szcs is not None: parts.append(f"szCs={half_pt(szcs.get(wq('val')))}")
    b  = rpr.find(wq("b"))
    i  = rpr.find(wq("i"))
    u  = rpr.find(wq("u"))
    color = rpr.find(wq("color"))
    va = rpr.find(wq("vertAlign"))
    if va is not None:
        vav = va.get(wq("val"), "?")
        parts.append(f"vertAlign={vav}")
    if b     is not None:
        bv = b.get(wq("val"), "true")
        if bv not in ("false","0"): parts.append("bold")
    if i     is not None:
        iv = i.get(wq("val"), "true")
        if iv not in ("false","0"): parts.append("italic")
    if u     is not None: parts.append(f"underline={u.get(wq('val'),'single')}")
    if color is not None:
        cv = color.get(wq("val"),"")
        if cv and cv != "auto": parts.append(f"color=#{cv}")
    lang = rpr.find(wq("lang"))
    if lang is not None:
        lv = lang.get(wq("val"), lang.get(wq("bidi"), ""))
        if lv: parts.append(f"lang={lv}")
    return "  ".join(parts)

def _fmt_ppr(ppr) -> str:
    if ppr is None:
        return ""
    parts = []
    jc = ppr.find(wq("jc"))
    if jc is not None: parts.append(f"align={jc.get(wq('val'),'?')}")
    spacing = ppr.find(wq("spacing"))
    if spacing is not None:
        for a in ("before","after","line","lineRule"):
            v = spacing.get(wq(a))
            if v is not None: parts.append(f"sp_{a}={v}")
    ind = ppr.find(wq("ind"))
    if ind is not None:
        for a in ("left","right","firstLine","hanging","start","end"):
            v = ind.get(wq(a))
            if v is not None: parts.append(f"ind_{a}={v}")
    numpr = ppr.find(wq("numPr"))
    if numpr is not None:
        ilvl = numpr.find(wq("ilvl"))
        numid= numpr.find(wq("numId"))
        il = ilvl.get(wq("val"),"?") if ilvl is not None else "?"
        ni = numid.get(wq("val"),"?") if numid is not None else "?"
        parts.append(f"numPr(ilvl={il},numId={ni})")
    keepnext = ppr.find(wq("keepNext"))
    pagebreak= ppr.find(wq("pageBreakBefore"))
    if keepnext  is not None: parts.append("keepNext")
    if pagebreak is not None: parts.append("pageBreakBefore")
    return "  ".join(parts)

def analyse_styles(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    root = read_xml(zf, "word/styles.xml")
    if root is None:
        lines.append("  (tidak ada styles.xml)")
        return lines

    # docDefaults
    dd = root.find(wq("docDefaults"))
    if dd is not None:
        lines.append("  [docDefaults]")
        rprdef = dd.find(f".//{wq('rPrDefault')}")
        pprdef = dd.find(f".//{wq('pPrDefault')}")
        if rprdef is not None:
            rpr = rprdef.find(wq("rPr"))
            if rpr is not None:
                lines.append(f"    rPr: {_fmt_rpr(rpr) or '(kosong)'}")
        if pprdef is not None:
            ppr = pprdef.find(wq("pPr"))
            if ppr is not None:
                lines.append(f"    pPr: {_fmt_ppr(ppr) or '(kosong)'}")

    # Categorize styles
    by_type: dict[str, list] = {"paragraph": [], "character": [], "table": [], "numbering": [], "other": []}
    for style_el in root.findall(wq("style")):
        sid   = style_el.get(wq("styleId"), "")
        stype = style_el.get(wq("type"), "other")
        sdef  = style_el.get(wq("default"), "0")
        name_el = style_el.find(wq("name"))
        sname = name_el.get(wq("val"), "") if name_el is not None else ""
        based = style_el.find(wq("basedOn"))
        based_v = based.get(wq("val"), "") if based is not None else ""
        link = style_el.find(wq("link"))
        link_v = link.get(wq("val"), "") if link is not None else ""

        ppr = style_el.find(wq("pPr"))
        rpr = style_el.find(wq("rPr"))
        ppr_s = _fmt_ppr(ppr)
        rpr_s = _fmt_rpr(rpr)

        entry = {
            "id": sid, "name": sname, "default": sdef == "1",
            "basedOn": based_v, "link": link_v,
            "pPr": ppr_s, "rPr": rpr_s,
        }
        # table style — tblPr / tcPr
        if stype == "table":
            tblpr = style_el.find(wq("tblPr"))
            if tblpr is not None:
                entry["tblPr"] = etree.tostring(tblpr, encoding="unicode")[:120]
        cat = stype if stype in by_type else "other"
        by_type[cat].append(entry)

    for stype, items in by_type.items():
        if not items:
            continue
        lines.append(f"\n  [{stype.upper()} STYLES] ({len(items)} buah)")
        for e in items:
            def_marker = " [DEFAULT]" if e["default"] else ""
            based_s = f"  basedOn={e['basedOn']}" if e["basedOn"] else ""
            link_s  = f"  link={e['link']}"       if e["link"]    else ""
            lines.append(f"    {e['id']:30s} \"{e['name']}\"{def_marker}{based_s}{link_s}")
            if e["rPr"]: lines.append(f"      rPr: {e['rPr']}")
            if e["pPr"]: lines.append(f"      pPr: {e['pPr']}")
            if e.get("tblPr"): lines.append(f"      tblPr: {e['tblPr'][:100]}")

    return lines

# ─────────────────────────────────────────────────────────────────
# § 8  Numbering (word/numbering.xml)
# ─────────────────────────────────────────────────────────────────
def analyse_numbering(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    root = read_xml(zf, "word/numbering.xml")
    if root is None:
        lines.append("  (tidak ada numbering.xml)")
        return lines

    abs_nums = root.findall(wq("abstractNum"))
    nums     = root.findall(wq("num"))
    lines.append(f"  abstractNum: {len(abs_nums)}, num: {len(nums)}")

    for an in abs_nums:
        anid = an.get(wq("abstractNumId"), "?")
        name_el = an.find(wq("name"))
        aname = name_el.get(wq("val"), "") if name_el is not None else ""
        style_link = an.find(wq("numStyleLink"))
        multilevel = an.find(wq("multiLevelType"))
        mt = multilevel.get(wq("val"), "?") if multilevel is not None else "?"
        lines.append(f"\n    abstractNum[{anid}] name={aname!r} multiLevelType={mt}")
        for lvl in an.findall(wq("lvl")):
            ilvl   = lvl.get(wq("ilvl"), "?")
            numfmt = lvl.find(wq("numFmt"))
            lvltext= lvl.find(wq("lvlText"))
            jc     = lvl.find(wq("lvlJc"))
            start  = lvl.find(wq("start"))
            rpr    = lvl.find(wq("rPr"))
            ppr    = lvl.find(wq("pPr"))
            fmt_s  = numfmt.get(wq("val"),"?")  if numfmt  is not None else "?"
            text_s = lvltext.get(wq("val"),"?") if lvltext is not None else "?"
            jc_s   = jc.get(wq("val"),"?")      if jc      is not None else "?"
            start_s= start.get(wq("val"),"?")   if start   is not None else "?"
            rpr_s  = _fmt_rpr(rpr)
            ppr_s  = _fmt_ppr(ppr)
            line = (f"      lvl[{ilvl}] fmt={fmt_s} text={text_s!r} "
                    f"jc={jc_s} start={start_s}")
            if rpr_s: line += f"\n        rPr: {rpr_s}"
            if ppr_s: line += f"\n        pPr: {ppr_s}"
            lines.append(line)

    for num in nums:
        numid  = num.get(wq("numId"), "?")
        abref  = num.find(wq("abstractNumId"))
        abval  = abref.get(wq("val"), "?") if abref is not None else "?"
        overrides = num.findall(wq("lvlOverride"))
        ov_s = f"  overrides: {len(overrides)}" if overrides else ""
        lines.append(f"    num[{numid}] → abstractNum[{abval}]{ov_s}")

    return lines

# ─────────────────────────────────────────────────────────────────
# § 9  Header / Footer content
# ─────────────────────────────────────────────────────────────────
def _extract_text_from_body(root) -> str:
    texts = []
    for t in root.iter(wq("t")):
        if t.text:
            texts.append(t.text)
    return "".join(texts)[:200]

def analyse_headers_footers(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    names = zf.namelist()
    hf_files = sorted(
        [n for n in names if n.startswith("word/") and
         (("/header" in n or "/footer" in n) and n.endswith(".xml"))]
    )
    if not hf_files:
        lines.append("  (tidak ada header/footer)")
        return lines
    for hf in hf_files:
        root = read_xml(zf, hf)
        if root is None:
            lines.append(f"  {hf}: (gagal dibaca)")
            continue
        body_paras = root.findall(wq("p"))
        text = _extract_text_from_body(root)
        lines.append(f"  {hf}: {len(body_paras)} paragraf, text='{text}'")
        for i, para in enumerate(body_paras):
            ppr = para.find(wq("pPr"))
            style = ""
            align = ""
            if ppr is not None:
                ps = ppr.find(wq("pStyle"))
                if ps is not None: style = ps.get(wq("val"), "")
                jc = ppr.find(wq("jc"))
                if jc is not None: align = jc.get(wq("val"), "")
            runs = []
            for r in para.findall(wq("r")):
                rpr_el = r.find(wq("rPr"))
                rpr_s  = _fmt_rpr(rpr_el)
                rt_parts = [t.text for t in r.findall(wq("t")) if t.text]
                rt = "".join(rt_parts)[:60]
                run_line = f"      text='{rt}'"
                if rpr_s: run_line += f"  {rpr_s}"
                if rt or rpr_s:
                    runs.append(run_line)
            # Check for fields (page number etc.)
            flds = list(para.iter(wq("fldChar"))) + list(para.iter(wq("instrText")))
            fld_texts = [f.text for f in para.iter(wq("instrText")) if f.text]
            align_s = f"  align={align}" if align else ""
            style_s = f"  style={style}" if style else ""
            fld_s   = f"  fields={fld_texts}" if fld_texts else ""
            lines.append(f"    para[{i}]{style_s}{align_s}{fld_s}")
            for rl in runs:
                lines.append(rl)
    return lines

# ─────────────────────────────────────────────────────────────────
# § 10  sectPr detail (dari body maupun pPr inline)
# ─────────────────────────────────────────────────────────────────
def _parse_sectpr_full(sp, label: str) -> list[str]:
    lines = [f"  ── sectPr [{label}] ──"]
    pgsz  = sp.find(wq("pgSz"))
    pgmar = sp.find(wq("pgMar"))
    cols  = sp.find(wq("cols"))
    stype = sp.find(wq("type"))
    pgnum = sp.find(wq("pgNumType"))
    titlePg = sp.find(wq("titlePg"))

    if pgsz is not None:
        w = tw_pt(pgsz.get(wq("w")))
        h = tw_pt(pgsz.get(wq("h")))
        orient = pgsz.get(wq("orient"), "portrait")
        lines.append(f"    pgSz: w={w}  h={h}  orient={orient}")

    if pgmar is not None:
        attrs = {}
        for a in ("top","bottom","left","right","header","footer","gutter"):
            v = pgmar.get(wq(a))
            if v is not None:
                attrs[a] = tw_pt(v)
        lines.append(f"    pgMar: {attrs}")

    if cols is not None:
        num    = cols.get(wq("num"), "1")
        space  = tw_pt(cols.get(wq("space"))) if cols.get(wq("space")) else "—"
        eq     = cols.get(wq("equalWidth"))
        # Individual col definitions
        col_defs = cols.findall(wq("col"))
        cdesc = ""
        if col_defs:
            cwds = [tw_pt(cd.get(wq("w"))) for cd in col_defs]
            cspaces = [tw_pt(cd.get(wq("space"))) for cd in col_defs if cd.get(wq("space")) is not None]
            cdesc = f"  col widths=[{', '.join(cwds)}]"
            if cspaces:
                cdesc += f"  child spaces=[{', '.join(cspaces)}]"
        lines.append(f"    cols: num={num}  space={space}  equalWidth={eq}{cdesc}")
        lines.extend(_column_layout_details(sp))
    else:
        lines.extend(_column_layout_details(sp))

    if stype is not None:
        lines.append(f"    type: {stype.get(wq('val'), '?')}")
    else:
        lines.append(f"    type: (tidak ada — default nextPage)")

    if titlePg is not None:
        lines.append(f"    titlePg: YES (first-page header berbeda)")

    if pgnum is not None:
        fmt = pgnum.get(wq("fmt"), "")
        start= pgnum.get(wq("start"), "")
        lines.append(f"    pgNumType: fmt={fmt} start={start}")

    # headerReference / footerReference
    for ref_type in ("headerReference", "footerReference"):
        for ref in sp.findall(wq(ref_type)):
            rtype = ref.get(wq("type"), "")
            rid   = ref.get(f"{{{NS_R}}}id", "")
            lines.append(f"    {ref_type}: type={rtype}  rId={rid}")

    return lines

# ─────────────────────────────────────────────────────────────────
# § 11  Body structure (semua paragraf, tabel, sectPr)
# ─────────────────────────────────────────────────────────────────
def analyse_body(zf: zipfile.ZipFile) -> list[str]:
    lines = []
    root = read_xml(zf, "word/document.xml")
    if root is None:
        lines.append("  (tidak ada document.xml)")
        return lines
    body = root.find(wq("body"))
    if body is None:
        lines.append("  (tidak ada body)")
        return lines

    body_children = list(body)
    lines.append(f"  Total elemen body: {len(body_children)}")

    # Count elements
    n_para = sum(1 for c in body_children if c.tag == wq("p"))
    n_tbl  = sum(1 for c in body_children if c.tag == wq("tbl"))
    n_sect_final = sum(1 for c in body_children if c.tag == wq("sectPr"))
    n_sect_inline = 0
    for c in body_children:
        if c.tag == wq("p"):
            ppr = c.find(wq("pPr"))
            if ppr is not None and ppr.find(wq("sectPr")) is not None:
                n_sect_inline += 1
    total_sect = n_sect_final + n_sect_inline
    lines.append(f"  Paragraf: {n_para}  Tabel: {n_tbl}  sectPr: {total_sect} ({n_sect_inline} inline + {n_sect_final} final)")

    # ── Semua sectPr dengan detail ──
    lines.append("\n  ── SECTION PROPERTIES ──")
    sect_idx = 0
    para_idx = 0
    for child in body_children:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            ppr = child.find(wq("pPr"))
            if ppr is not None:
                sp = ppr.find(wq("sectPr"))
                if sp is not None:
                    texts = []
                    for t in child.iter(wq("t")):
                        if t.text: texts.append(t.text)
                    preview = "".join(texts)[:50]
                    label = f"inline #{sect_idx}  in para[{para_idx}] '{preview}'"
                    lines.extend(_parse_sectpr_full(sp, label))
                    sect_idx += 1
            para_idx += 1
        elif tag == "tbl":
            para_idx += 1
        elif tag == "sectPr":
            lines.extend(_parse_sectpr_full(child, f"final #{sect_idx}"))
            sect_idx += 1

    # ── Body paragraf dan tabel ──
    lines.append("\n  ── BODY CONTENT ──")
    idx = 0
    for child in body_children:
        tag = child.tag.split("}")[-1]
        if tag == "p":
            ppr = child.find(wq("pPr"))
            style = ""
            has_sect = False
            ppr_s = ""
            if ppr is not None:
                ps = ppr.find(wq("pStyle"))
                if ps is not None: style = ps.get(wq("val"), "")
                has_sect = ppr.find(wq("sectPr")) is not None
                ppr_s = _fmt_ppr(ppr)

            # Runs
            run_infos = []
            for r in child.findall(wq("r")):
                rpr_el = r.find(wq("rPr"))
                rpr_s  = _fmt_rpr(rpr_el)
                t_parts = [t.text for t in r.findall(wq("t")) if t.text]
                t_text  = "".join(t_parts)[:60]
                run_infos.append((rpr_s, t_text))

            # fldChar / instrText (page fields, etc.)
            fld_texts = [f.text for f in child.iter(wq("instrText")) if f.text]

            sect_marker = "  [SECTPR]" if has_sect else ""
            p_line = f"  [{idx:03d}] P  style={style!r}{sect_marker}"
            if ppr_s: p_line += f"\n         pPr: {ppr_s}"
            for (rs, rt) in run_infos:
                run_line = f"         run: '{rt}'"
                if rs: run_line += f"  [{rs}]"
                p_line += f"\n{run_line}"
            if fld_texts:
                p_line += f"\n         fields: {fld_texts}"
            lines.append(p_line)

        elif tag == "tbl":
            rows = child.findall(wq("tr"))
            # Count max cells
            max_cells = max((len(r.findall(wq("tc"))) for r in rows), default=0)
            lines.append(f"  [{idx:03d}] TABLE  {len(rows)} baris × {max_cells} kolom")
            # tblBorders (table-level borders)
            tblpr = child.find(wq("tblPr"))
            if tblpr is not None:
                tblborders = tblpr.find(wq("tblBorders"))
                if tblborders is not None:
                    border_parts = []
                    for b in tblborders:
                        btag  = b.tag.split("}")[-1]
                        bval  = b.get(wq("val"), "")
                        bsz   = b.get(wq("sz"), "")
                        bclr  = b.get(wq("color"), "")
                        border_parts.append(f"{btag}(val={bval},sz={bsz},clr={bclr})")
                    lines.append(f"         tblBorders: {' | '.join(border_parts)}")
                else:
                    lines.append(f"         tblBorders: (none)")
            # tcBorders of first data cell (to capture per-cell border style)
            if rows:
                first_cells = rows[0].findall(wq("tc"))
                if first_cells:
                    tc0pr = first_cells[0].find(wq("tcPr"))
                    if tc0pr is not None:
                        tcb = tc0pr.find(wq("tcBorders"))
                        if tcb is not None:
                            tp = []
                            for b in tcb:
                                btag = b.tag.split("}")[-1]
                                bval = b.get(wq("val"), "")
                                bsz  = b.get(wq("sz"), "")
                                tp.append(f"{btag}(val={bval},sz={bsz})")
                            lines.append(f"         tcBorders[0]: {' | '.join(tp)}")
            for ri, row in enumerate(rows):
                cells = row.findall(wq("tc"))
                cell_texts = []
                for tc in cells:
                    ct_parts = [t.text for t in tc.iter(wq("t")) if t.text]
                    cell_texts.append("".join(ct_parts)[:30])
                lines.append(f"         baris[{ri}]: {cell_texts}")

        elif tag == "sectPr":
            lines.append(f"  [{idx:03d}] FINAL-SECTPR")

        idx += 1

    return lines

# ─────────────────────────────────────────────────────────────────
# § SPECIAL — Office Theme-only file (ULTIMACOMP.doc dll)
# ─────────────────────────────────────────────────────────────────
def analyse_theme_only(zf: zipfile.ZipFile, fname: str) -> list[str]:
    lines = []
    lines.append(f"  FORMAT: Office Theme File (bukan Word document)")
    lines.append(f"  Berisi font scheme & color scheme untuk MS Office.")
    lines.append("")

    # Content types
    ct_root = read_xml(zf, "[Content_Types].xml", fix_strict=False)
    if ct_root is not None:
        lines.append("  [Content Types]")
        ns_ct = "http://schemas.openxmlformats.org/package/2006/content-types"
        for ov in ct_root.findall(f"{{{ns_ct}}}Override"):
            lines.append(f"    {ov.get('PartName','')} → {ov.get('ContentType','')}")

    # Theme
    theme_paths = [n for n in zf.namelist() if "theme" in n and n.endswith(".xml") and "theme1" in n]
    for tp in theme_paths:
        lines.append(f"\n  [Theme: {tp}]")
        lines.extend(analyse_theme(zf, tp))

    return lines

# ─────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────
TEMPLATES = [
    "AMORI.docx", "ELCTRICES.docx", "ELKOLIND.docx", "ENERGIUPM.docx",
    "IEEE.docx", "IJEECS.docx", "JAMRIS.docx", "JEEMECS.docx",
    "JMEM.docx", "JMEV.docx", "JNTETI.docx", "JOKI.docx",
    "JRC.docx",
    "JTMM.docx", "JTRANSIENT.docx", "JTUNDIP.docx", "ROTASI.docx",
    # Legacy doc files
    "JMEM.doc",
    # Theme files
    "ULTIMACOMP.doc",
]

# ─────────────────────────────────────────────────────────────────
# § GEN-CODE AUDIT  (source audit semua *gen.py)
# ─────────────────────────────────────────────────────────────────
import ast as _ast
import re as _re_gen

def _parse_gen_source_cfg(gen_path: Path):
    """Extract CFG dict from generator source using ast.literal_eval."""
    text = gen_path.read_text(encoding="utf-8")
    m = _re_gen.search(r"CFG\s*=\s*\{", text)
    if not m:
        return None, text
    start = m.end() - 1
    depth = 0
    end = None
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return None, text
    block = text[start:end]
    try:
        return _ast.literal_eval(block), text
    except Exception:
        return None, text


def analyse_gen_code() -> list[str]:
    """Audit all *gen.py files for key CFG flags and detect common issues."""
    lines = []
    gens = sorted(BASE.glob("*gen.py"))
    if not gens:
        lines.append("  (tidak ada *gen.py ditemukan)")
        return lines
    for gen in gens:
        cfg, text = _parse_gen_source_cfg(gen)
        flags = []
        if "subsection_no_prefix" in text:  flags.append("sub_no_prefix")
        if "subsection_bare_run" in text:   flags.append("sub_bare_run")
        if "table_auto_label" in text:      flags.append("tbl_auto")
        if "figure_auto_label" in text:     flags.append("fig_auto")
        if "custom_refs_fn" in text or "def _add_references" in text:
            flags.append("custom_refs")
        if "def _add_abstract" in text:     flags.append("custom_abstract")
        if "def _add_authors" in text:      flags.append("custom_authors")
        if "def _add_title" in text:        flags.append("custom_title")

        shf    = cfg.get("section_heading_format", "?") if cfg else "?"
        fb     = cfg.get("full_borders", "?") if cfg else "?"
        h1     = cfg.get("heading1", "-") if cfg else "-"
        h2     = cfg.get("heading2", "-") if cfg else "-"
        fig_s  = cfg.get("figure_caption", "-") if cfg else "-"
        tbl_s  = cfg.get("table_head", "-") if cfg else "-"
        refs_s = cfg.get("references", "-") if cfg else "-"
        body_s = cfg.get("body", "-") if cfg else "-"
        pfx    = cfg.get("fig_prefix", "-") if cfg else "-"
        col_w  = cfg.get("col_width_pt", "-") if cfg else "-"

        lines.append(f"\n  === {gen.name} ===")
        lines.append(f"    section_heading_format : {shf}")
        lines.append(f"    full_borders           : {fb}")
        lines.append(f"    col_width_pt           : {col_w}")
        lines.append(f"    heading1 style         : {h1}")
        lines.append(f"    heading2 style         : {h2}")
        lines.append(f"    body style             : {body_s}")
        lines.append(f"    figure_caption style   : {fig_s}")
        lines.append(f"    table_head style       : {tbl_s}")
        lines.append(f"    references style       : {refs_s}")
        lines.append(f"    fig_prefix             : {pfx}")
        if flags:
            lines.append(f"    custom flags           : {', '.join(flags)}")

        # Detect potential issues
        issues = []
        if h1 == h2 == body_s:
            issues.append(f"heading1/heading2/body all use same style '{h1}' — OK only if template designed that way")
        if cfg is None:
            issues.append("CFG dict not found or not parseable")
        if shf not in ("plain", "plain_upper", "arabic_dot", "roman_dot", "roman_upper", "?"):
            issues.append(f"Unknown section_heading_format: {shf!r}")
        if issues:
            for iss in issues:
                lines.append(f"    [!] {iss}")
    return lines

SEP  = "=" * 76
SEP2 = "-" * 60

def section(title: str, lines: list[str]):
    print(f"\n  {SEP2}")
    print(f"  § {title}")
    print(f"  {SEP2}")
    for ln in lines:
        print(ln)


def _iter_target_files(args: list[str]) -> list[Path]:
    if not args:
        return [BASE / fname for fname in TEMPLATES]

    targets: list[Path] = []
    seen: set[Path] = set()
    for raw in args:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = (BASE / candidate).resolve()
        if candidate.is_dir():
            for child in sorted(candidate.iterdir()):
                if child.suffix.lower() not in {".docx", ".doc"}:
                    continue
                if child not in seen:
                    targets.append(child)
                    seen.add(child)
            continue
        if candidate not in seen:
            targets.append(candidate)
            seen.add(candidate)
    return targets

def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    target_files = _iter_target_files(sys.argv[1:])

    # ── § GEN-CODE AUDIT ──────────────────────────────────────────
    print(f"\n{SEP}")
    print(f"§ GEN-CODE AUDIT — semua *gen.py di folder Template")
    print(SEP)
    for ln in analyse_gen_code():
        print(ln)

    # ── Template DOCX/DOC analysis ────────────────────────────────
    for fpath in target_files:
        fname = fpath.name
        if not fpath.exists():
            print(f"\n{SEP}")
            print(f"FILE: {fname}  [ TIDAK DITEMUKAN ]")
            print(SEP)
            continue

        size_bytes = fpath.stat().st_size

        print(f"\n{SEP}")
        print(f"FILE: {fname}  ({size_bytes:,} bytes)")
        print(SEP)

        try:
            with zipfile.ZipFile(fpath) as zf:
                fmt = detect_format(zf)
                print(f"FORMAT: {fmt}")

                # ── Theme-only (ULTIMACOMP.doc, etc.) ──
                if "OFFICE THEME" in fmt:
                    section("OFFICE THEME CONTENT", analyse_theme_only(zf, fname))
                    continue

                # ── Full DOCX analysis ──
                section("1. PACKAGE PARTS", analyse_content_types(zf))
                section("2. CORE & APP PROPERTIES", analyse_core_props(zf))
                section("3. DOCUMENT RELATIONSHIPS", analyse_rels(zf))
                section("4. SETTINGS", analyse_settings(zf))
                section("5. THEME", analyse_theme(zf))
                section("6. FONT TABLE", analyse_font_table(zf))
                section("7. STYLES", analyse_styles(zf))
                section("8. NUMBERING", analyse_numbering(zf))
                section("9. HEADER / FOOTER", analyse_headers_footers(zf))
                section("10. BODY (SECTPR + CONTENT)", analyse_body(zf))

        except zipfile.BadZipFile:
            print(f"  ERROR: Bukan file ZIP yang valid (mungkin binary .doc lama)")
        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()

    print(f"\n{SEP}")
    print("SELESAI")
    print(SEP)


if __name__ == "__main__":
    main()
