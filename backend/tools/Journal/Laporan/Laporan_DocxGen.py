#!/usr/bin/env python3
"""Laporan_DocxGen.py — Template-based DOCX generator untuk Laporan KP/Skripsi.

Menggunakan DOCX asli sebagai template: salin file, lalu ganti konten teks
dari JSON sambil mempertahankan SEMUA formatting (numbering, header/footer,
styles, page layout, dll) secara identik.

Contoh:
    python Laporan_DocxGen.py bagas.json
    python Laporan_DocxGen.py bagas.json output.docx
"""
from __future__ import annotations
import copy, json, os, shutil, sys, tempfile, zipfile, zlib, struct, binascii
from pathlib import Path
from lxml import etree

# ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = BASE_DIR / "master.docx"

# ─────────────────────────────────────────────────────────────────
NS_W  = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R  = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_A  = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
NS_PKG= "http://schemas.openxmlformats.org/package/2006/relationships"
WQ = lambda t: f"{{{NS_W}}}{t}"
AQ = lambda t: f"{{{NS_A}}}{t}"

# Strict→Transitional namespace map
_NS_STRICT = {
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

def _fix_ns(data: bytes) -> bytes:
    for old, new in _NS_STRICT.items():
        data = data.replace(old, new)
    return data

# ─────────────────────────────────────────────────────────────────
# XML helpers — operate on lxml elements
# ─────────────────────────────────────────────────────────────────
def _get_text(el) -> str:
    return "".join(t.text or "" for t in el.iter(WQ("t")))

def _get_style(p) -> str:
    ppr = p.find(WQ("pPr"))
    if ppr is not None:
        ps = ppr.find(WQ("pStyle"))
        if ps is not None:
            return ps.get(WQ("val"), "")
    return ""

def _has_image(p) -> bool:
    return any(p.iter(AQ("blip")))

def _get_image_rid(p) -> str:
    blip = next(p.iter(AQ("blip")), None)
    if blip is not None:
        return blip.get(f"{{{NS_R}}}embed", "")
    return ""

def _set_para_text(p, new_text: str) -> bool:
    """Replace text of a paragraph, preserving run formatting and drawings.
    Returns True if text was actually changed."""
    runs = p.findall(WQ("r"))
    if not runs:
        r = etree.SubElement(p, WQ("r"))
        t = etree.SubElement(r, WQ("t"))
        t.text = new_text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return True

    current_text = _get_text(p)
    if current_text == new_text:
        return False

    first_r = runs[0]
    has_drawing = first_r.find(WQ("drawing")) is not None

    if has_drawing and len(runs) > 1:
        target_r = runs[1]
    elif has_drawing:
        r = etree.SubElement(p, WQ("r"))
        rpr_src = first_r.find(WQ("rPr"))
        if rpr_src is not None:
            r.append(copy.deepcopy(rpr_src))
        t = etree.SubElement(r, WQ("t"))
        t.text = new_text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return True
    else:
        target_r = first_r

    t_elems = list(target_r.iter(WQ("t")))
    if t_elems:
        t_elems[0].text = new_text
        t_elems[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        for extra_t in t_elems[1:]:
            extra_t.getparent().remove(extra_t)
    else:
        t = etree.SubElement(target_r, WQ("t"))
        t.text = new_text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    for r in (runs[2:] if has_drawing else runs[1:]):
        if r.find(WQ("drawing")) is None:
            p.remove(r)

    return True


def _set_cell_text(tc, new_text: str) -> bool:
    """Replace text in a table cell, preserving tcPr and formatting."""
    paras = tc.findall(WQ("p"))
    if not paras:
        p = etree.SubElement(tc, WQ("p"))
        t = etree.SubElement(p, WQ("t"))
        t.text = new_text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return True

    first_p = paras[0]
    current = _get_text(first_p)
    if current == new_text:
        return False

    runs = first_p.findall(WQ("r"))
    if runs:
        t_elems = list(runs[0].iter(WQ("t")))
        if t_elems:
            t_elems[0].text = new_text
            t_elems[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            for extra_t in t_elems[1:]:
                extra_t.getparent().remove(extra_t)
        else:
            t = etree.SubElement(runs[0], WQ("t"))
            t.text = new_text
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        for r in runs[1:]:
            first_p.remove(r)
    else:
        r = etree.SubElement(first_p, WQ("r"))
        t = etree.SubElement(r, WQ("t"))
        t.text = new_text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    for extra_p in paras[1:]:
        tc.remove(extra_p)

    return True


# ─────────────────────────────────────────────────────────────────
# Find content boundaries in document body
# ─────────────────────────────────────────────────────────────────
def _find_section_indices(paras, heading_text: str, heading_style: str = "Heading1"):
    """Find start/end of a section by its heading text."""
    target = heading_text.strip().upper()
    for i, p in enumerate(paras):
        style = _get_style(p)
        text = _get_text(p).strip()
        if text.upper() == target and (style == heading_style or style == heading_style.replace(" ", "")):
            for j in range(i + 1, len(paras)):
                if _get_style(paras[j]) in ("Heading1",) and j > i + 1:
                    return i, j
            return i, len(paras)
    return None, None


def _find_paras_between(paras, start_idx, end_idx, style_filter=None):
    """Get paragraph indices between start and end, optionally filtered by style."""
    result = []
    for i in range(start_idx, min(end_idx, len(paras))):
        style = _get_style(paras[i])
        text = _get_text(paras[i]).strip()
        if style_filter:
            if style in style_filter:
                result.append(i)
        else:
            if text and style not in ("Heading1", "Heading2"):
                result.append(i)
    return result


# ─────────────────────────────────────────────────────────────────
# Replace image in media folder
# ─────────────────────────────────────────────────────────────────
def _replace_media_image(work_dir: Path, rid: str, new_image_path: Path,
                          rels_tree) -> None:
    """Replace an image file referenced by rid."""
    root = rels_tree.getroot()
    for rel in root:
        if rel.get("Id") == rid:
            target = rel.get("Target", "")
            if target.startswith("/"):
                target = target[1:]
            img_path = work_dir / "word" / target
            if not img_path.is_absolute():
                img_path = work_dir / target
            if new_image_path.exists():
                shutil.copy2(new_image_path, img_path)
            return


# ─────────────────────────────────────────────────────────────────
# Serialize document.xml back to bytes, preserving original format
# ─────────────────────────────────────────────────────────────────
def _serialize_docxml(tree) -> bytes:
    """Serialize lxml tree back to document.xml bytes matching original format."""
    rt = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
    # Fix lxml roundtrip differences:
    # 1. XML declaration uses single quotes → original uses double quotes
    rt = rt.replace(
        b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n",
        b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n"
    )
    # 2. lxml uses decimal &#10; instead of hex &#xA;
    rt = rt.replace(b"&#10;", b"&#xA;")
    # 3. Original uses \r\n line endings throughout
    rt = rt.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return bytes(rt)


# ─────────────────────────────────────────────────────────────────
# Main generator
# ─────────────────────────────────────────────────────────────────
def generate(json_path: str | Path, template_path: str | Path = None,
             output_path: str | Path = None) -> None:
    """Generate DOCX from JSON using template-based approach."""

    json_path = Path(json_path)
    if template_path is None:
        template_path = DEFAULT_TEMPLATE
    template_path = Path(template_path)
    if output_path is None:
        output_path = json_path.with_suffix(".docx")
    output_path = Path(output_path)

    # Load JSON
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Copy template to output
    shutil.copy2(template_path, output_path)

    # Extract DOCX to temp directory
    work_dir = Path(tempfile.mkdtemp(prefix="docx_gen_"))
    with zipfile.ZipFile(output_path) as z:
        z.extractall(work_dir)

    # Parse document.xml
    doc_path = work_dir / "word" / "document.xml"
    with open(doc_path, "rb") as f:
        raw_xml = f.read()

    fixed_xml = _fix_ns(raw_xml)
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.fromstring(fixed_xml, parser)
    body = tree.find(WQ("body"))
    paras = list(body.findall(WQ("p")))
    tables = list(body.findall(WQ("tbl")))

    # Parse rels
    rels_path = work_dir / "word" / "_rels" / "document.xml.rels"
    rels_tree = etree.parse(str(rels_path))

    # Build rId -> image target map
    rid_map = {}
    for rel in rels_tree.getroot():
        rid = rel.get("Id", "")
        target = rel.get("Target", "")
        rtype = rel.get("Type", "").split("/")[-1]
        if rtype == "image":
            rid_map[rid] = target

    # ── Get data from JSON ──
    title = data.get("title", "")
    authors = data.get("authors", [])
    author = authors[0] if authors else {}
    author_name = author.get("name", "")
    author_nim = author.get("nim", "")
    affiliation = author.get("affiliation", "")
    year = data.get("year", "2026")
    sections = data.get("sections", [])
    figures = data.get("figures", [])
    tables_data = data.get("tables", [])
    references = data.get("references", [])

    # Parse affiliation
    aff_parts = [p.strip() for p in affiliation.split(",")] if affiliation else []
    prog_studi = aff_parts[0] if len(aff_parts) > 0 else ""
    fakultas = aff_parts[1] if len(aff_parts) > 1 else ""
    univ = aff_parts[2] if len(aff_parts) > 2 else ""

    # Custom sections from JSON
    pengesahan = data.get("pengesahan", {})
    kata_pengantar = data.get("kata_pengantar", {})
    biodata = data.get("biodata", {})
    lampiran_items = data.get("lampiran", [])

    dosen_pembimbing = pengesahan.get("dosen_pembimbing", "")
    ketua_departemen = pengesahan.get("ketua_departemen", "")
    pembimbing_lapangan = pengesahan.get("pembimbing_lapangan", "")
    tanggal_pengesahan = pengesahan.get("tanggal", "")
    lokasi_pengesahan = pengesahan.get("lokasi", "")
    tanggal_mulai = pengesahan.get("tanggal_mulai", "")
    tanggal_selesai = pengesahan.get("tanggal_selesai", "")

    # ── 1. COVER PAGE (paras 0-17) ──
    if "UNIVERSITAS DIPONEGORO":
        _set_para_text(paras[2], "UNIVERSITAS DIPONEGORO")
    if title:
        _set_para_text(paras[4], title.upper())
    if True:
        _set_para_text(paras[6], "LAPORAN KERJA PRAKTIK")
        _set_para_text(paras[7], "PT PERTAMINA PATRA NIAGA RU IV CILACAP")
    if author_name:
        _set_para_text(paras[10], author_name.upper())
    if author_nim:
        _set_para_text(paras[11], author_nim)
    if prog_studi:
        _set_para_text(paras[14], prog_studi.upper())
    if fakultas:
        _set_para_text(paras[15], fakultas.upper())
    if univ:
        _set_para_text(paras[16], univ.upper())
    if year:
        _set_para_text(paras[17], f"TAHUN {year}")

    # ── 2. SECOND COVER (paras 19-35) ──
    if True:
        _set_para_text(paras[20], "UNIVERSITAS DIPONEGORO")
    if title:
        _set_para_text(paras[22], title.upper())
        _set_para_text(paras[23], "")
        _set_para_text(paras[24], "LAPORAN KERJA PRAKTIK")
        _set_para_text(paras[25], "PT PERTAMINA PATRA NIAGA RU IV CILACAP")
    if author_name:        _set_para_text(paras[29], author_name.upper())
    if author_nim:
        _set_para_text(paras[30], author_nim)
    if prog_studi:
        _set_para_text(paras[32], prog_studi.upper())
    if fakultas:
        _set_para_text(paras[33], fakultas.upper())
    if univ:
        _set_para_text(paras[34], univ.upper())
    if year:
        _set_para_text(paras[35], f"TAHUN {year}")

    # ── 3. LEMBAR PENGESAHAN #1 (paras 38-58) ──
    if True:
        _set_para_text(paras[40], "LAPORAN KERJA PRAKTIK")
        _set_para_text(paras[41], "PT PERTAMINA PATRA NIAGA RU IV CILACAP")
    if title:
        _set_para_text(paras[45], title)
    if author_name:
        _set_para_text(paras[48], author_name)
    if author_nim:
        _set_para_text(paras[49], author_nim)
    if lokasi_pengesahan:
        _set_para_text(paras[51], lokasi_pengesahan)
    if tanggal_mulai and tanggal_selesai:
        _set_para_text(paras[52], f"{tanggal_mulai} s/d {tanggal_selesai}")
    if tanggal_pengesahan:
        _set_para_text(paras[55], tanggal_pengesahan)

    # ── 4. LEMBAR PENGESAHAN #2 (paras 60-79) ──
    if True:
        _set_para_text(paras[62], "LAPORAN KERJA PRAKTIK")
        _set_para_text(paras[63], "PT PERTAMINA PATRA NIAGA RU IV CILACAP")
    if title:
        _set_para_text(paras[66], title)
    if author_name:
        _set_para_text(paras[69], author_name)
    if author_nim:
        _set_para_text(paras[70], author_nim)
    if lokasi_pengesahan:
        _set_para_text(paras[72], lokasi_pengesahan)
    if tanggal_mulai and tanggal_selesai:
        _set_para_text(paras[73], f"{tanggal_mulai} s/d {tanggal_selesai}")
    if tanggal_pengesahan:
        _set_para_text(paras[76], tanggal_pengesahan)

    # ── 5. TABLE[0] = Ketua Dept & Dosen Pembimbing ──
    if dosen_pembimbing and len(tables) > 0:
        rows = tables[0].findall(WQ("tr"))
        if rows:
            cells = rows[0].findall(WQ("tc"))
            if len(cells) > 1 and ketua_departemen:
                _set_cell_text(cells[0], f"Ketua Departemen Teknik Elektro\nUniversitas Diponegoro\n\n\n{ketua_departemen}")
            if len(cells) > 1 and dosen_pembimbing:
                _set_cell_text(cells[1], f"Dosen Pembimbing Kerja Praktik\n\n\n\n{dosen_pembimbing}")

    # ── 6. TABLE[1] = Pembimbing Lapangan & Pjs Lead ──
    if pembimbing_lapangan and len(tables) > 1:
        rows = tables[1].findall(WQ("tr"))
        if rows:
            cells = rows[0].findall(WQ("tc"))
            if len(cells) > 0:
                _set_cell_text(cells[0], f"Pembimbing Lapangan\nKerja Praktik\n\n\n{pembimbing_lapangan}")

    # ── 7. KATA PENGANTAR (paras 81-113) ──
    kp_paragraphs = kata_pengantar.get("paragraphs", [])
    kp_bullets = kata_pengantar.get("bullets", [])
    kp_closing = kata_pengantar.get("closing", {})
    kp_semarang = kp_closing.get("semarang", "")
    kp_tanggal = kp_closing.get("tanggal", "")

    kp_para_start = 84
    for idx, text in enumerate(kp_paragraphs):
        p_idx = kp_para_start + idx
        if p_idx < len(paras):
            _set_para_text(paras[p_idx], text)

    bullet_start = kp_para_start + len(kp_paragraphs)
    for idx, text in enumerate(kp_bullets):
        p_idx = bullet_start + idx
        if p_idx < len(paras):
            _set_para_text(paras[p_idx], text)

    closing_idx = bullet_start + len(kp_bullets) + 1
    if kp_semarang and closing_idx < len(paras):
        _set_para_text(paras[closing_idx], kp_semarang)
    if kp_tanggal and closing_idx + 1 < len(paras):
        _set_para_text(paras[closing_idx + 1], kp_tanggal)

    # ── 8. BAB SECTIONS ──
    for section in sections:
        sec_title = section.get("title", "")

        # Skip LAMPIRAN — handled separately in step 13
        if sec_title.strip().upper() == "LAMPIRAN":
            continue

        content = section.get("content", [])
        subsections = section.get("subsections", [])

        heading_idx = None
        for i, p in enumerate(paras):
            text = _get_text(p).strip()
            style = _get_style(p)
            if text.upper() == sec_title.upper() and style == "Heading1":
                heading_idx = i
                break

        if heading_idx is None:
            continue

        content_paras = []
        for i in range(heading_idx + 1, len(paras)):
            style = _get_style(paras[i])
            text = _get_text(paras[i]).strip()
            if style == "Heading1":
                break
            if style == "Heading2":
                break
            if text or _has_image(paras[i]):
                content_paras.append(i)

        text_items = [item for item in content if item.get("id") == "text"]
        for idx, item in enumerate(text_items):
            if idx < len(content_paras):
                _set_para_text(paras[content_paras[idx]], item.get("text", ""))

        img_items = [item for item in content if item.get("id") == "gambar"]
        img_idx = 0
        for item in img_items:
            img_path = item.get("Path", "")
            if not img_path:
                continue
            for p_idx in content_paras:
                if _has_image(paras[p_idx]):
                    full_img_path = BASE_DIR / img_path
                    if full_img_path.exists():
                        rid = _get_image_rid(paras[p_idx])
                        if rid:
                            _replace_media_image(work_dir, rid, full_img_path, rels_tree)
                    content_paras = [x for x in content_paras if x != p_idx]
                    break

        for sub in subsections:
            sub_title = sub.get("title", "")
            sub_content = sub.get("content", [])

            sub_heading_idx = None
            for i in range(heading_idx + 1, len(paras)):
                text = _get_text(paras[i]).strip()
                style = _get_style(paras[i])
                if text.upper() == sub_title.upper() and style == "Heading2":
                    sub_heading_idx = i
                    break

            if sub_heading_idx is None:
                continue

            sub_content_paras = []
            for i in range(sub_heading_idx + 1, len(paras)):
                style = _get_style(paras[i])
                text = _get_text(paras[i]).strip()
                if style in ("Heading1", "Heading2"):
                    break
                if text or _has_image(paras[i]):
                    sub_content_paras.append(i)

            sub_text_items = [item for item in sub_content if item.get("id") == "text"]
            for idx, item in enumerate(sub_text_items):
                if idx < len(sub_content_paras):
                    _set_para_text(paras[sub_content_paras[idx]], item.get("text", ""))

            sub_img_items = [item for item in sub_content if item.get("id") == "gambar"]
            for item in sub_img_items:
                img_path = item.get("Path", "")
                if not img_path:
                    continue
                for p_idx in sub_content_paras:
                    if _has_image(paras[p_idx]):
                        full_img_path = BASE_DIR / img_path
                        if full_img_path.exists():
                            rid = _get_image_rid(paras[p_idx])
                            if rid:
                                _replace_media_image(work_dir, rid, full_img_path, rels_tree)
                        sub_content_paras = [x for x in sub_content_paras if x != p_idx]
                        break

    # ── 9. DAFTAR ISI — handled by Word TOC fields, no replacement needed ──

    # ── 10. DAFTAR PUSTAKA ──
    if references:
        dp_start, dp_end = _find_section_indices(paras, "DAFTAR PUSTAKA")
        if dp_start is not None:
            dp_paras = _find_paras_between(paras, dp_start + 1, dp_end)
            for idx, ref in enumerate(references):
                if idx < len(dp_paras):
                    _set_para_text(paras[dp_paras[idx]], ref)

    # ── 11. ABSTRAK (Indonesian) ──
    abstract_id = data.get("abstract", "")
    abstract_en_text = data.get("abstract_en", "")
    # Only replace ABSTRAK if we have BOTH abstract and abstract_en
    # (so we can distinguish Indonesian from English)
    if abstract_id and abstract_en_text and abstract_id != abstract_en_text:
        ab_start, ab_end = _find_section_indices(paras, "ABSTRAK")
        if ab_start is not None:
            ab_paras = _find_paras_between(paras, ab_start + 1, ab_end)
            if ab_paras:
                _set_para_text(paras[ab_paras[0]], abstract_id)

    # ── 12. ABSTRACT (English) ──
    if abstract_en_text:
        ae_start, ae_end = _find_section_indices(paras, "ABSTRACT")
        if ae_start is not None:
            ae_paras = _find_paras_between(paras, ae_start + 1, ae_end)
            if ae_paras:
                _set_para_text(paras[ae_paras[0]], abstract_en_text)

    # ── 13. LAMPIRAN ──
    lampiran_start_idx, lampiran_end_idx = _find_section_indices(paras, "LAMPIRAN")
    if lampiran_start_idx is not None and lampiran_items:
        lam_paras = _find_paras_between(paras, lampiran_start_idx + 1, lampiran_end_idx)
        lam_content_paras = list(lam_paras)
        for item in lampiran_items:
            item_id = item.get("id", "")
            if item_id == "text" and lam_content_paras:
                p_idx = lam_content_paras.pop(0)
                _set_para_text(paras[p_idx], item.get("text", ""))
            elif item_id == "gambar":
                img_path = item.get("Path", "")
                if img_path:
                    for p_idx in lam_content_paras:
                        if _has_image(paras[p_idx]):
                            full_img_path = BASE_DIR / img_path
                            if full_img_path.exists():
                                rid = _get_image_rid(paras[p_idx])
                                if rid:
                                    _replace_media_image(work_dir, rid, full_img_path, rels_tree)
                            lam_content_paras.remove(p_idx)
                            break

    # ── 14. BIODATA ──
    biodata_start_idx, biodata_end_idx = _find_section_indices(paras, "BIODATA")
    if biodata_start_idx is not None and biodata:
        bio_paras = _find_paras_between(paras, biodata_start_idx + 1, biodata_end_idx)

        photo_path = biodata.get("photo")
        if photo_path:
            for p_idx in bio_paras:
                if _has_image(paras[p_idx]):
                    full_photo = BASE_DIR / photo_path
                    if full_photo.exists():
                        rid = _get_image_rid(paras[p_idx])
                        if rid:
                            _replace_media_image(work_dir, rid, full_photo, rels_tree)
                    break

        bio_fields = [
            ("name", biodata.get("name", "")),
            ("nim", biodata.get("nim", "")),
            ("program", biodata.get("program", "")),
            ("faculty", biodata.get("faculty", "")),
            ("university", biodata.get("university", "")),
            ("email", biodata.get("email", "")),
        ]
        field_idx = 0
        for p_idx in bio_paras:
            if field_idx >= len(bio_fields):
                break
            text = _get_text(paras[p_idx]).strip()
            if text and not _has_image(paras[p_idx]):
                _set_para_text(paras[p_idx], bio_fields[field_idx][1])
                field_idx += 1

        education = biodata.get("education", [])
        if education:
            edu_tbl_idx = None
            for ti, tbl in enumerate(tables):
                rows = tbl.findall(WQ("tr"))
                if rows:
                    first_cell = rows[0].findall(WQ("tc"))
                    if first_cell:
                        cell_text = _get_text(first_cell[0]).strip()
                        if "Tingkat" in cell_text:
                            edu_tbl_idx = ti
                            break

            if edu_tbl_idx is not None:
                tbl = tables[edu_tbl_idx]
                rows = tbl.findall(WQ("tr"))
                for ri, edu in enumerate(education):
                    if ri + 1 < len(rows):
                        cells = rows[ri + 1].findall(WQ("tc"))
                        if len(cells) > 2:
                            _set_cell_text(cells[0], edu.get("tingkat", ""))
                            _set_cell_text(cells[1], edu.get("institusi", ""))
                            _set_cell_text(cells[2], edu.get("tahun", ""))

    # ── SAVE ──
    new_xml_bytes = _serialize_docxml(tree)
    with open(doc_path, "wb") as f:
        f.write(new_xml_bytes)

    # Repackage as ZIP (DOCX)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for root_dir, dirs, files in os.walk(work_dir):
            for fname in files:
                fpath = Path(root_dir) / fname
                arcname = str(fpath.relative_to(work_dir))
                zout.write(fpath, arcname)

    # Cleanup
    shutil.rmtree(work_dir, ignore_errors=True)
    print(f"[OK] Generated: {output_path}")


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Laporan_DocxGen.py <data.json> [template.docx] [output.docx]")
        sys.exit(1)

    json_file = sys.argv[1]
    template_file = sys.argv[2] if len(sys.argv) > 2 else str(DEFAULT_TEMPLATE)
    output_file = sys.argv[3] if len(sys.argv) > 3 else None

    generate(json_file, template_file, output_file)
