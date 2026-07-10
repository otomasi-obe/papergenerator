"""
auto_checker.py - Deep Structural QA Auditor untuk DOCX jurnal akademik.

Membandingkan template original dengan dokumen hasil generate menggunakan
inspeksi struktural mendalam berbasis python-docx + lxml. Menghasilkan
laporan audit_<NAMA>.txt yang lengkap dengan:
  * Skor kecocokan di paling atas
  * Rincian pemotongan poin
  * Detail per-section (default/first/even) untuk header & footer
  * Detail per-properti untuk page setup
  * Prompt perbaikan otomatis siap copy

Modul validasi:
  [1] Deep Header/Footer Audit  (multi-section, default/first/even, FATAL -15)
  [2] Paragraph Style Validity  (style jurnal vs Normal,            MAYOR -10)
  [3] Page Setup & Multi-Column (size, margin, kolom,               MAYOR -10)
  [4] Strict Image / AI Prompt  (A + B == C dari _template.json,    MINOR  -5)
  [5] Kebocoran LaTeX / Simbol  (per-paragraf,                       MINOR  -2)

Usage:
    python auto_checker.py <template.docx> <output.docx>
"""

from __future__ import annotations

import difflib
import json
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.oxml.ns import qn
from lxml import etree


# =============================================================================
# Strict OOXML -> Transitional OOXML normalisasi (untuk DOCX format Strict)
# =============================================================================
STRICT_TO_TRANS_NS = {
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
    b"http://purl.oclc.org/ooxml/schemas/relationships/officeDocument":
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument":
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
}


def _strict_pt_to_twip(data: bytes) -> bytes:
    pattern = re.compile(rb'="(-?\d+(?:\.\d+)?)pt"')

    def _conv(m):
        v = float(m.group(1))
        return b'="' + str(int(round(v * 20))).encode("ascii") + b'"'

    return pattern.sub(_conv, data)


def open_docx(path: Path):
    """Buka DOCX dengan fallback otomatis ke konversi Strict -> Transitional."""
    try:
        return Document(str(path))
    except Exception:
        tmp = Path(tempfile.mkstemp(suffix=".docx")[1])
        with zipfile.ZipFile(path, "r") as zin:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    data = zin.read(info.filename)
                    if info.filename.endswith((".xml", ".rels")):
                        for old, new in STRICT_TO_TRANS_NS.items():
                            data = data.replace(old, new)
                        data = _strict_pt_to_twip(data)
                    zout.writestr(info, data)
        return Document(str(tmp))


# =============================================================================
# Konstanta penalti & threshold
# =============================================================================
BASE_SCORE = 100
PENALTY_HEADER_FOOTER_FATAL = 15   # FATAL: per (section, part_type) yang rusak
PENALTY_STYLE_RESET = 10           # MAYOR: sekali, jika ada style direset ke Normal
PENALTY_PAGE_SETUP = 10            # MAYOR: sekali, jika layout meleset
PENALTY_IMAGE_MINOR = 5            # MINOR: per kejadian placeholder/missing/invalid
PENALTY_LATEX_LEAK = 2             # per kebocoran LaTeX
PENALTY_MULTICOL_FATAL = 25        # FATAL: multi-kolom hancur (XPath cek w:cols/@w:num)
PENALTY_HEADER_SHAPE_FATAL = 20    # FATAL: textbox/shape/drawing di header hilang
PENALTY_TABLE_COUNT = 5            # MINOR: per tabel hilang/extra (di luar toleransi)
PENALTY_SECTPR_FLUSH = 15          # MAYOR: sekali, jika trailing sectPr cluster terdeteksi
PENALTY_SECTPR_DISTRIBUTION = 10   # MAYOR: sekali, jika urutan sectPr divergen jauh
PENALTY_EMPTY_SECTION = 10         # MAYOR: per section yang berkonten di orig tapi kosong di output (blank page)
PENALTY_CONTENT_CONCENTRATION = 10 # MAYOR: sekali, jika konten body menumpuk di satu section
PENALTY_STYLE_MISMATCH = 5         # per style mismatch non-Normal (selain reset ke Normal)
PENALTY_FIGURE_POSITION = 3        # per figure yang muncul sebelum referensi
PENALTY_HEADER_CONTENT = 5         # per header/footer dengan text mismatch
PENALTY_NUMBERING_MISMATCH = 3     # per heading numbering inconsistency
PENALTY_RUN_FORMATTING = 2         # per run formatting mismatch (color/underline/etc)
PENALTY_TABLE_DENSITY = 3          # per tabel dengan cell density rendah
PENALTY_TABLE_BORDER = 5           # MINOR: per tabel data tanpa border tegas/visible
PENALTY_TABLE_BORDER_THIN = 3      # MINOR: per tabel dengan border terlalu tipis (sz < 4)
PENALTY_FONT_FAMILY = 3            # per font family mismatch di STRICT zone
PENALTY_DOUBLE_NUMBERING = 5       # per heading dengan double numbering (numPr + prefix manual)
PENALTY_REF_DOUBLE_NUM = 3          # per referensi dengan double numbering ([1] [1])
PENALTY_IMAGE_SIZE_MISMATCH = 10    # MAYOR: gambar melebihi atau terlalu kecil vs lebar kolom
PENALTY_ELEMENT_SPACING = 3         # MINOR: spacing before/after figure/table/formula tidak konsisten
PENALTY_EMPTY_FORMULA = 10          # MAYOR: formula OMML kosong atau rusak
PENALTY_PLACEHOLDER_IMAGE = 5      # MINOR: per gambar placeholder/blank terdeteksi
PENALTY_LOGO_MISSING = 10          # MAYOR: per logo jurnal yang hilang dari top paragraphs
PENALTY_LOGO_SECTION_MISMATCH = 15  # MAYOR: per drawing dekoratif yg pindah ke section beda kolom
PENALTY_ANCHOR_POSITION = 5         # MINOR: per anchor position mismatch (wp:anchor offset/relativeFrom)
PENALTY_CONTAINER_CONTEXT = 5       # MINOR: per drawing dekoratif yg pindah container (paragraf/tabel cell)
PENALTY_BLANK_PAGE = 10             # MAYOR: per halaman kosong berlebih (sectPr page-breaking + konten kosong)
PENALTY_SECTPR_WASTE = 3            # MINOR: per section break tidak perlu (continuous di ekor tanpa konten)
PENALTY_CHAR_ANOMALY = 2            # MINOR: per karakter aneh/mojibake/garbled text (encoding rusak)
PENALTY_LINE_SPACING = 2            # MINOR: per paragraph dengan line spacing mismatch vs template
PENALTY_TABLE_WIDTH = 10            # MAYOR: tabel overflow kolom
PENALTY_TABLE_SPACING = 3           # MINOR: caption/spacing tabel terlalu rapat
PENALTY_FORMULA_WIDTH = 10          # MAYOR: formula OMML overflow kolom
PENALTY_FORMULA_ALIGNMENT = 3      # MINOR: per formula paragraph dengan alignment salah
PENALTY_FIGURE_CAPTION = 3          # MINOR: figure caption style mismatch (label bold/text normal)
PENALTY_PARAGRAPH_SPACING = 2       # MINOR: per paragraf dengan spacing mismatch vs template
PENALTY_EMPTY_PARAGRAPH = 3         # MINOR: per kelompok paragraf kosong beruntun (≥ 3 consecutive)
PENALTY_FIRST_LINE_INDENT = 2       # MINOR: per paragraf body dengan first_line_indent tidak sesuai
PENALTY_FONT_SIZE = 3              # MINOR: per font size mismatch di STRICT zone
PENALTY_SECTION_NUM_FORMAT = 3     # MINOR: per section numbering format mismatch

LAYOUT_TOLERANCE_TWIP = 10         # toleransi 0.5pt untuk noise pembulatan
PARAGRAPH_STYLE_CHECK_COUNT = 20   # 20 paragraf pertama
PASS_SCORE_THRESHOLD = 95          # < 95 -> STATUS REJECTED untuk FATAL XML check
TABLE_COUNT_TOLERANCE = 3          # selisih sampai 3 tabel masih wajar (template-specific)
SECTPR_FLUSH_THRESHOLD = 2         # >= N sectPr inline berturut-turut di akhir = flush (lowered from 5 to catch blank page issues)
SECTPR_DISTRIBUTION_THRESHOLD = 0.4  # cosine similarity gap maks 40%
EMPTY_SECTION_MIN_ORIG_PARAS = 2   # section orig dianggap "berkonten" jika punya >= N paragraf bertext
CONTENT_CONCENTRATION_RATIO = 0.85  # jika >= 85% paragraf bertext numpuk di 1 section = blank page issue
ANCHOR_OFFSET_TOLERANCE_EMU = 72000  # toleransi 72000 EMU (~2mm) untuk anchor offset perbedaan
CONTAINER_INDEX_TOLERANCE = 2        # toleransi perbedaan index container (paragraf/tabel)


# =============================================================================
# Regex konten
# =============================================================================
LATEX_PATTERNS = [
    r'\\mathrm\b', r'\\mathbf\b', r'\\frac\b', r'\\sum\b', r'\\int\b',
    r'\\sqrt\b', r'\\left\b', r'\\right\b', r'\\begin\b', r'\\end\b',
    r'\\vec\b', r'\\hat\b', r'\\dot\b', r'\\overline\b', r'\\underline\b',
    r'\\circ\b', r'\\approx\b', r'\\times\b', r'\\cdot\b', r'\\infty\b',
    r'\\alpha\b', r'\\beta\b', r'\\gamma\b', r'\\theta\b', r'\\lambda\b',
    r'\\sigma\b', r'\\omega\b', r'\\pi\b', r'\\mu\b', r'\\Delta\b',
    r'\\partial\b', r'_\{', r'\^\{', r'\\quad\b', r'\\qquad\b',
    r'\\text\b', r'\\displaystyle\b',
    # Inline math delimiters & bare sub/superscript
    r'\$',                # $...$ inline math delimiter
    r'_[0-9]',             # X_1 bare subscript digit (bukan _{...})
    r'\^[0-9]',           # x^2 bare superscript digit
]
LATEX_REGEX = re.compile('|'.join(LATEX_PATTERNS))

# ── Mojibake / garbled text detection ──────────────────────────────────────
# C1 control characters (U+0080 - U+009F) yang muncul di text adalah
# tanda pasti double-decoding UTF-8: byte asli 0x80-0x9F di-decode sebagai
# latin-1, menghasilkan karakter kontrol yang tidak valid dalam teks normal.
# Pattern: deteksi karakter U+0080-U+009F (kecuali U+0085 NEL & U+009A SCI
# yang kadang sah di docx)
MOJIBAKE_C1_REGEX = re.compile('[\x80-\x84\x86-\x99\x9b-\x9f]')
# Double-encoding signature: Ã (U+00C3) + C1 char = versi rusak dari 2-byte UTF-8
# â (U+00E2) + C1 char = versi rusak dari 3-byte UTF-8
MOJIBAKE_DOUBLE_ENC_REGEX = re.compile('[\u00c2-\u00e3][\x80-\xbf]')
# Replacement character U+FFFD = decoder error marker
MOJIBAKE_REPLACEMENT_REGEX = re.compile('\ufffd')
# Gabungan pattern untuk highlight
MOJIBAKE_ANY_REGEX = re.compile(
    '([\x80-\x84\x86-\x99\x9b-\x9f]|\ufffd|[\u00c2-\u00e3][\x80-\xbf])'
)

PLACEHOLDER_LEGACY_REGEX = re.compile(r'\[image\s+placeholder\b[^\]]*\]', re.IGNORECASE)
PROMPT_AI_REGEX = re.compile(r'\[PROMPT UNTUK AI GAMBAR:\s*(.*?)\]', re.DOTALL)

# Placeholder markers di header/footer template (orig content yang seharusnya di-replace)
HF_PLACEHOLDER_PATTERNS = [
    # English placeholders
    r'\bFirst Author\b',
    r'\bPaper Title\b',
    r'\bAuthor Name\b',
    r'\bAuthors? Name\b',
    r'\b\d+\s*words?\s+continued\b',
    # Indonesian placeholders
    r'\bPenulis Pertama\b',
    r'\bJudul Paper\b',
    r'\bEmpat kata\b',
    r'\b\d+\s*kata\b',
    r'\bdisambung titik-titik\b',
    r'\bdots\s*\(',
    # Volume/issue metadata placeholder
    r'Volume\s+\w+\s+Nomor\s+\w+\s+\w+\s+\d{4}',
    r'Volume\s+\d+\s+No\.\s*\d+',
    r'Vol\.\s*\d+,?\s*No\.\s*\d+',
    # Generic dummy text
    r'\(…\)',  # (…)
    r'\(\.{3}\)',   # (...)
    r'\bxxxx\b',
    r'\bXX\b',
    # Dummy paper title (template asli yang harus di-replace dengan title user)
    # Pattern: 3+ word judul yang generic + dummy author list (3+ nama)
    r'\bSistem\s+\w+\s+\w+\s+dan\s+\w+\b',
    # Topik penelitian dummy (CCTV, IoT, dll yang spesifik di template asli)
    r'CCTV\s+Image\s+Processing',
]
HF_PLACEHOLDER_REGEX = re.compile('|'.join(HF_PLACEHOLDER_PATTERNS), re.IGNORECASE | re.MULTILINE)


def _has_placeholder_marker(text: str) -> bool:
    """Cek apakah text mengandung placeholder marker (template original yang
    seharusnya diisi konten real)."""
    if not text:
        return False
    return bool(HF_PLACEHOLDER_REGEX.search(text))


# =============================================================================
# Result containers
# =============================================================================
@dataclass
class AuditResult:
    errors: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)


@dataclass
class Penalty:
    category: str
    count: int
    unit: int
    total: int


# =============================================================================
# Helpers
# =============================================================================
def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _twip(length) -> int:
    """python-docx Length (EMU) -> twip integer."""
    if length is None:
        return 0
    try:
        return int(round(length.pt * 20))
    except Exception:
        return 0


def _collect_part_text(part) -> str:
    if part is None:
        return ""
    chunks: list[str] = []
    try:
        for para in part.paragraphs:
            t = para.text.strip()
            if t:
                chunks.append(t)
        for table in part.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        t = para.text.strip()
                        if t:
                            chunks.append(t)
    except (AttributeError, KeyError):
        # python-docx kadang gagal parse header/footer Part dari template
        # Strict OOXML atau yang punya namespace non-standar. Skip silently.
        pass
    return "\n".join(chunks)


def _count_part_drawings(part) -> int:
    if part is None:
        return 0
    el = part._element
    return (
        len(el.findall(f".//{qn('w:drawing')}"))
        + len(el.findall(f".//{qn('w:pict')}"))
    )


def _count_body_drawings(doc) -> int:
    body = doc._element.body
    return (
        len(body.findall(f".//{qn('w:drawing')}"))
        + len(body.findall(f".//{qn('w:pict')}"))
    )


def load_image_titles_from_json(base_dir: Path, json_path: Path | None = None) -> list[str]:
    """Load image titles from JSON. If json_path is provided, use it directly."""
    if json_path is None:
        json_path = base_dir / "_template.json"
    if not json_path.exists():
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    titles: list[str] = []
    _extract_image_titles(data, titles)
    return titles


def _extract_image_titles(obj, titles: list[str]) -> None:
    if isinstance(obj, dict):
        if str(obj.get("id", "")).lower() in ("gambar", "image"):
            title = (obj.get("Title") or "").strip()
            if title:
                titles.append(title)
        for v in obj.values():
            _extract_image_titles(v, titles)
    elif isinstance(obj, list):
        for item in obj:
            _extract_image_titles(item, titles)


# B8: Hitung expected counts dari JSON untuk dipakai sebagai baseline audit
def load_expected_counts_from_json(base_dir: Path, json_path: Path | None = None) -> dict:
    """Hitung jumlah elemen yang DIHARAPKAN di output berdasarkan JSON.

    If json_path is provided, use it directly. Otherwise use _template.json in base_dir.

    Return: {"figures": N, "tables": N, "equations": N}
    """
    if json_path is None:
        json_path = base_dir / "_template.json"
    counts = {"figures": 0, "tables": 0, "equations": 0}
    if not json_path.exists():
        return counts

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return counts

    def _walk(obj):
        if isinstance(obj, dict):
            kind = str(obj.get("id", "")).lower() if isinstance(obj.get("id"), str) else ""
            if kind in ("gambar", "image"):
                counts["figures"] += 1
            elif kind in ("tabel", "table"):
                counts["tables"] += 1
            elif kind in ("rumus", "persamaan", "equation", "formula"):
                counts["equations"] += 1
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data)
    return counts


# =============================================================================
# [1] Deep Header / Footer Audit
# =============================================================================
HF_PART_LABEL = {
    "header": "Default Header",
    "first_page_header": "First Page Header",
    "even_page_header": "Even Page Header",
    "footer": "Default Footer",
    "first_page_footer": "First Page Footer",
    "even_page_footer": "Even Page Footer",
}

HF_PART_ATTRS = list(HF_PART_LABEL.keys())


def _hf_snapshot(part) -> dict | None:
    if part is None:
        return None
    return {
        "linked": bool(getattr(part, "is_linked_to_previous", False)),
        "text": _collect_part_text(part),
        "img_count": _count_part_drawings(part),
    }


def audit_headers_footers(doc_orig, doc_out) -> AuditResult:
    res = AuditResult()
    detail_breaks: list[tuple[str, str]] = []
    content_diffs: list[dict] = []

    orig_sections = doc_orig.sections
    out_sections = doc_out.sections
    n_sections = max(len(orig_sections), len(out_sections))

    for s_idx in range(n_sections):
        orig_sec = orig_sections[s_idx] if s_idx < len(orig_sections) else None
        out_sec = out_sections[s_idx] if s_idx < len(out_sections) else None

        for part_attr in HF_PART_ATTRS:
            orig_part = getattr(orig_sec, part_attr, None) if orig_sec else None
            out_part = getattr(out_sec, part_attr, None) if out_sec else None

            orig_snap = _hf_snapshot(orig_part)
            out_snap = _hf_snapshot(out_part)

            # Lewati slot yang di original memang kosong / di-link ke section sebelumnya.
            orig_has_content = (
                orig_snap is not None
                and not orig_snap["linked"]
                and (orig_snap["text"] or orig_snap["img_count"] > 0)
            )
            if not orig_has_content:
                continue

            label = HF_PART_LABEL.get(part_attr, part_attr)
            section_label = f"Section {s_idx + 1} ({label})"

            if out_snap is None:
                res.errors.append(
                    f"HEADER/FOOTER FATAL: {section_label} hilang total di output "
                    f"(section index {s_idx + 1} tidak ada di dokumen output)."
                )
                detail_breaks.append((section_label, "MISSING_SECTION"))
                continue

            if out_snap["linked"]:
                res.errors.append(
                    f"HEADER/FOOTER FATAL: {section_label} di output di-link ke "
                    f"section sebelumnya, padahal template original mendefinisikan "
                    f"part ini secara unik. Konfigurasi 'First Page Different' / "
                    f"'Odd-Even Pages' template hilang."
                )
                detail_breaks.append((section_label, "LINKED_LOST"))
                continue

            text_changed = (
                _normalize_ws(orig_snap["text"]) != _normalize_ws(out_snap["text"])
            )
            missing_imgs = orig_snap["img_count"] - out_snap["img_count"]

            # Text changes -> MINOR penalty (content diff)
            # SKIP jika orig adalah placeholder template (e.g. "First Author: Paper Title")
            # yang valid di-replace dengan konten real
            if text_changed:
                orig_has_placeholder = _has_placeholder_marker(orig_snap["text"])
                out_has_placeholder = _has_placeholder_marker(out_snap["text"])

                # B1 advanced: hitung apakah output mengandung placeholder TAPI
                # tidak ada di orig (artinya generator tidak ganti placeholder)
                # Kalau orig has placeholder & output tidak (sudah replaced), skip
                # Kalau output STILL has placeholder & orig juga has, flag (leak)
                if orig_has_placeholder and not out_has_placeholder:
                    # Placeholder valid di-replace - tidak perlu penalty
                    pass
                elif out_has_placeholder and orig_has_placeholder:
                    # Output masih punya marker - leak!
                    out_text = out_snap["text"][:100]
                    content_diffs.append({
                        "section_label": section_label,
                        "out_text": out_text,
                        "issue": "placeholder_leak",
                    })
                    res.errors.append(
                        f"HEADER/FOOTER PLACEHOLDER LEAK: {section_label} masih mengandung "
                        f"placeholder template di output. "
                        f"Out: \"{out_text}...\""
                    )
                else:
                    orig_text = orig_snap["text"][:100]
                    out_text = out_snap["text"][:100]
                    content_diffs.append({
                        "section_label": section_label,
                        "orig_text": orig_text,
                        "out_text": out_text,
                        "orig_len": len(orig_snap["text"]),
                        "out_len": len(out_snap["text"]),
                        "issue": "content_diff",
                    })
                    res.errors.append(
                        f"HEADER/FOOTER CONTENT: Teks pada {section_label} berubah "
                        f"(Original {len(orig_snap['text'])} char, "
                        f"Output {len(out_snap['text'])} char). "
                        f"Orig: \"{orig_text}...\" | Out: \"{out_text}...\""
                    )

            # Missing images -> FATAL
            if missing_imgs > 0:
                res.errors.append(
                    f"HEADER/FOOTER FATAL: {section_label} kehilangan {missing_imgs} "
                    f"objek gambar/logo "
                    f"(Original: {orig_snap['img_count']}, Output: {out_snap['img_count']})."
                )
                detail_breaks.append((section_label, f"IMG_LOST_{missing_imgs}"))

    res.info = {
        "broken_count": len(detail_breaks),
        "content_diffs": len(content_diffs),
        "details": detail_breaks,
        "content_diff_details": content_diffs,
        "n_sections_orig": len(orig_sections),
        "n_sections_out": len(out_sections),
    }
    return res


# =============================================================================
# [2] Paragraph Style Validity
# =============================================================================
# B7: Locale-specific style patterns (style leftover dari template original
# dalam bahasa lokal yang seharusnya di-remap)
LOCALE_STYLE_PATTERNS = [
    (re.compile(r'WP_標準|^標準$|和文|本文'), "japanese"),
    (re.compile(r'표준$|^본문|기본'), "korean"),
    (re.compile(r'正文|^标准$|^宋体'), "chinese"),
]


def _detect_locale_style(style_name: str) -> str | None:
    """Return locale code if style is locale-specific, else None."""
    if not style_name:
        return None
    for pat, locale in LOCALE_STYLE_PATTERNS:
        if pat.search(style_name):
            return locale
    return None


def audit_paragraph_styles(doc_orig, doc_out, n_check: int = PARAGRAPH_STYLE_CHECK_COUNT) -> AuditResult:
    res = AuditResult()

    orig_paras = [p for p in doc_orig.paragraphs if p.text.strip()][:n_check]
    out_paras = [p for p in doc_out.paragraphs if p.text.strip()][:n_check]

    # Gunakan sequence alignment untuk mencocokkan paragraf yang sama
    # (menghindari false positive akibat shift struktur)
    pairs = _align_paragraph_pairs(orig_paras, out_paras)

    diffs: list[dict] = []
    style_reset_count = 0
    other_diffs = 0

    for orig_idx, out_idx in pairs:
        orig_style = (orig_paras[orig_idx].style.name if orig_paras[orig_idx].style else "Normal") or "Normal"
        out_style = (out_paras[out_idx].style.name if out_paras[out_idx].style else "Normal") or "Normal"

        if orig_style == out_style:
            continue

        # Guard: skip jika konten paragraf sangat berbeda (likely beda paragraf
        # struktural). Tanpa guard ini, audit pair-kan section heading original
        # dengan body paragraph output yang shift karena dummy text orig vs
        # konten user di output.
        orig_text_norm = (orig_paras[orig_idx].text or "").lower().strip()
        out_text_norm = (out_paras[out_idx].text or "").lower().strip()
        if len(orig_text_norm) >= 4 and len(out_text_norm) >= 4:
            orig_words = set(re.findall(r"\b\w{3,}\b", orig_text_norm))
            out_words = set(re.findall(r"\b\w{3,}\b", out_text_norm))
            if orig_words and out_words:
                overlap = len(orig_words & out_words)
                union = len(orig_words | out_words)
                jaccard = overlap / union if union else 0
                if jaccard < 0.25:
                    continue

        snippet = orig_paras[orig_idx].text.strip()[:60]
        # B7: Klasifikasi mismatch
        orig_locale = _detect_locale_style(orig_style)
        out_locale = _detect_locale_style(out_style)
        category = "general"
        hint = ""

        # NEW: Detect case-only mismatches first (e.g., 'normal' vs 'Normal')
        if orig_style.lower() == out_style.lower() and orig_style != out_style:
            category = "case_mismatch"
            hint = f" [CRITICAL: Style case berbeda ('{orig_style}' vs '{out_style}') - menyebabkan font/spacing berbeda!]"
        elif out_style.lower() == "normal" and orig_style.lower() != "normal":
            category = "reset_to_normal"
        elif orig_style.lower() == "normal" and out_style.lower() != "normal":
            category = "add_new_style"
            hint = " [HINT: generator menambah style baru padahal orig pakai Normal - cek apakah perlu pakai style template asli]"
        elif out_locale:
            category = f"locale_{out_locale}"
            hint = f" [HINT: style '{out_style}' adalah leftover {out_locale} - perlu remap ke style standard]"
        elif orig_locale and not out_locale:
            category = f"locale_remap_ok_{orig_locale}"

        diffs.append({
            "orig_index": orig_idx,
            "out_index": out_idx,
            "orig_style": orig_style,
            "out_style": out_style,
            "snippet": snippet,
            "category": category,
            "hint": hint,
        })

        if category == "reset_to_normal":
            style_reset_count += 1
        elif category == "case_mismatch":
            # Treat case mismatches as resets since they cause visual differences
            style_reset_count += 1
        else:
            other_diffs += 1

    if style_reset_count > 0:
        res.errors.append(
            f"STYLE RUSAK: {style_reset_count} paragraf berubah menjadi 'Normal', "
            f"format jurnal hilang."
        )
        for d in diffs:
            if d["category"] == "reset_to_normal":
                res.errors.append(
                    f"  -> Paragraf orig#{d['orig_index']} vs out#{d['out_index']} (\"{d['snippet']}\"): "
                    f"style '{d['orig_style']}' -> 'Normal'."
                )

    # Tambah penalti untuk style mismatch non-Normal
    if other_diffs > 0:
        res.errors.append(
            f"STYLE MISMATCH: {other_diffs} paragraf dengan style berbeda (non-Normal)."
        )
        for d in diffs:
            if d["category"] != "reset_to_normal":
                res.errors.append(
                    f"  -> Paragraf orig#{d['orig_index']} vs out#{d['out_index']} (\"{d['snippet']}\"): "
                    f"'{d['orig_style']}' -> '{d['out_style']}'.{d.get('hint', '')}"
                )

    res.info = {
        "checked_pairs": len(pairs),
        "total_orig": len(orig_paras),
        "total_out": len(out_paras),
        "diffs": diffs,
        "style_reset_count": style_reset_count,
        "other_style_diffs": other_diffs,
    }
    return res


# =============================================================================
# [3] Page Setup & Multi-Column Layout
# =============================================================================
_PAGE_FIELDS = [
    ("page_width", "Page Width"),
    ("page_height", "Page Height"),
    ("margin_top", "Margin Top"),
    ("margin_bottom", "Margin Bottom"),
    ("margin_left", "Margin Left"),
    ("margin_right", "Margin Right"),
    ("margin_header", "Header Distance"),
    ("margin_footer", "Footer Distance"),
]


def _section_columns(section) -> int:
    try:
        sect_pr = section._sectPr
    except Exception:
        return 1
    cols = sect_pr.find(qn("w:cols"))
    if cols is None:
        return 1
    return int(cols.get(qn("w:num"), "1") or "1")


def _section_props(section) -> dict:
    return {
        "page_width": _twip(section.page_width),
        "page_height": _twip(section.page_height),
        "margin_top": _twip(section.top_margin),
        "margin_bottom": _twip(section.bottom_margin),
        "margin_left": _twip(section.left_margin),
        "margin_right": _twip(section.right_margin),
        "margin_header": _twip(section.header_distance),
        "margin_footer": _twip(section.footer_distance),
        "columns": _section_columns(section),
    }


def _section_signature(section) -> dict:
    """Ekstrak signature lengkap section untuk B4 dump.

    Return: {orientation, page_w, page_h, columns, has_titlePg, sec_type}
    """
    try:
        sect_pr = section._sectPr
    except Exception:
        return {}

    sig = {
        "page_w": int(getattr(section, "page_width", 0) or 0),
        "page_h": int(getattr(section, "page_height", 0) or 0),
        "columns": _section_columns(section),
        "orientation": "landscape" if int(getattr(section, "page_width", 0) or 0) > int(getattr(section, "page_height", 0) or 0) else "portrait",
    }

    # titlePg
    title_pg = sect_pr.find(qn("w:titlePg"))
    sig["has_titlePg"] = title_pg is not None

    # sec_type (continuous, nextPage, etc)
    sec_type_el = sect_pr.find(qn("w:type"))
    sig["sec_type"] = (
        sec_type_el.get(qn("w:val")) if sec_type_el is not None else "default"
    )

    return sig


def audit_page_setup(doc_orig, doc_out) -> AuditResult:
    res = AuditResult()
    diffs: list[tuple] = []

    orig_sections = doc_orig.sections
    out_sections = doc_out.sections

    if len(orig_sections) != len(out_sections):
        res.errors.append(
            f"PAGE SETUP MELESET: jumlah section berbeda "
            f"(Original: {len(orig_sections)}, Output: {len(out_sections)})."
        )

    n = min(len(orig_sections), len(out_sections))
    for i in range(n):
        op = _section_props(orig_sections[i])
        np_ = _section_props(out_sections[i])

        for field_key, label in _PAGE_FIELDS:
            ov, nv = op[field_key], np_[field_key]
            if abs(ov - nv) > LAYOUT_TOLERANCE_TWIP:
                res.errors.append(
                    f"PAGE SETUP MELESET: Section {i + 1} {label} -- "
                    f"Original {ov}tw, Output {nv}tw (selisih {abs(ov - nv)}tw)."
                )
                diffs.append((i + 1, field_key, ov, nv))

        if op["columns"] != np_["columns"]:
            res.errors.append(
                f"PAGE SETUP MELESET: Section {i + 1} jumlah kolom berubah "
                f"(Original {op['columns']} kolom, Output {np_['columns']} kolom). "
                f"Tata letak multi-column template hilang."
            )
            diffs.append((i + 1, "columns", op["columns"], np_["columns"]))

    # B4: Dump signature per section yang hilang (kalau output kurang section)
    section_signatures: list[dict] = []
    if len(out_sections) < len(orig_sections):
        for i in range(len(orig_sections)):
            sig = _section_signature(orig_sections[i])
            sig["section_idx"] = i + 1
            sig["status"] = "present" if i < len(out_sections) else "MISSING"
            section_signatures.append(sig)

    res.info = {
        "diffs": diffs,
        "n_orig": len(orig_sections),
        "n_out": len(out_sections),
        "section_signatures": section_signatures,
    }
    return res


# =============================================================================
# [4] Strict Image / Placeholder / AI Prompt
# =============================================================================
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
VML_NS = "urn:schemas-microsoft-com:vml"


def _extract_blip_rids(element) -> set[str]:
    """Kumpulkan semua rId dari <a:blip r:embed="rIdXX"> (DrawingML)
    DAN <v:imagedata r:id="rIdXX"> (VML) dalam elemen."""
    rids: set[str] = set()
    # Cari semua blip element dengan namespace drawingml
    for blip in element.findall(f".//{{{DRAWING_NS}}}blip"):
        rid = blip.get(f"{{{R_NS}}}embed")
        if rid:
            rids.add(rid)
    # Juga cek via w:drawing -> a:graphic -> a:graphicData -> pic:blip
    for drawing in element.findall(f".//{qn('w:drawing')}"):
        for blip in drawing.findall(f".//{{{DRAWING_NS}}}blip"):
            rid = blip.get(f"{{{R_NS}}}embed")
            if rid:
                rids.add(rid)
    # Cari VML <v:imagedata r:id="rIdXX"> - format legacy OLE/WordArt
    # yang sering dipakai logo jurnal di header/footer.
    for imagedata in element.findall(f".//{{{VML_NS}}}imagedata"):
        rid = imagedata.get(f"{{{R_NS}}}id")
        if rid:
            rids.add(rid)
    return rids


def _get_template_decorative_rids(doc_orig) -> set[str]:
    """Identifikasi rId gambar dekoratif (logo jurnal) dari template original.

    Heuristik:
    - Tabel di 5 tabel pertama yang mengandung drawing/blip TAPI bukan tabel
      konten (banyak rows > 3 atau banyak drawings > 2 = kemungkinan konten).
      Tabel logo/header biasanya 1-3 rows dengan 1-2 drawings.
    - Paragraf di 5 paragraf pertama yang punya drawing = logo dekoratif.
    - SEMUA gambar di headers/footers (semua sections, semua part types) = logo jurnal.
    """
    body = doc_orig._element.body
    decorative_rids: set[str] = set()

    # Cek 5 paragraf paling awal di body untuk drawing
    paragraphs_checked = 0
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            paragraphs_checked += 1
            if paragraphs_checked > 5:
                break
            rids = _extract_blip_rids(child)
            if rids:
                decorative_rids.update(rids)
        elif child.tag == qn("w:tbl"):
            break

    # Cari tabel-tabel di body (sampai 5 tabel pertama)
    tables_checked = 0
    for child in body.iterchildren():
        if child.tag != qn("w:tbl"):
            continue
        tables_checked += 1
        if tables_checked > 5:
            break

        rids = _extract_blip_rids(child)
        if not rids:
            continue

        # Filter: tabel dengan banyak rows (>3) atau banyak unique drawings (>2)
        # kemungkinan adalah tabel konten (subfigure, biography), bukan logo
        n_rows = len(child.findall(qn("w:tr")))
        n_unique_drawings = len(child.findall(f".//{qn('w:drawing')}"))

        if n_rows > 3 or n_unique_drawings > 2:
            continue

        decorative_rids.update(rids)

    # Scan SEMUA headers/footers di SEMUA sections - ini tempat paling umum untuk logo jurnal
    for section in doc_orig.sections:
        for part_attr in HF_PART_ATTRS:
            part = getattr(section, part_attr, None)
            if part is None:
                continue
            try:
                rids = _extract_blip_rids(part._element)
                if rids:
                    decorative_rids.update(rids)
            except (AttributeError, KeyError):
                # Part bisa None atau tidak punya _element - skip
                continue

    return decorative_rids


def _count_decorative_shape_drawings(doc) -> int:
    """Hitung drawing dekoratif SHAPE-ONLY (tanpa <a:blip>, mis. garis/box
    masthead atau textbox di header jurnal) di region dekoratif (5 paragraf
    awal + 5 tabel awal, sama seperti _get_template_decorative_rids).

    Drawing shape-only ini tidak punya rId blip sehingga lolos dari classifier
    berbasis blip dan keliru terhitung sebagai gambar KONTEN. Region & batasnya
    sengaja disamakan dengan _get_template_decorative_rids agar konsisten.
    """
    body = doc._element.body

    def shape_only_count(element) -> int:
        n = 0
        for drawing in element.findall(f".//{qn('w:drawing')}"):
            has_blip = any(
                blip.get(f"{{{R_NS}}}embed")
                for blip in drawing.findall(f".//{{{DRAWING_NS}}}blip")
            )
            if not has_blip:
                n += 1
        return n

    count = 0

    # 5 paragraf paling awal (stop saat ketemu tabel)
    paragraphs_checked = 0
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            paragraphs_checked += 1
            if paragraphs_checked > 5:
                break
            count += shape_only_count(child)
        elif child.tag == qn("w:tbl"):
            break

    # 5 tabel paling awal (header jurnal / container dekoratif)
    tables_checked = 0
    for child in body.iterchildren():
        if child.tag != qn("w:tbl"):
            continue
        tables_checked += 1
        if tables_checked > 5:
            break
        count += shape_only_count(child)

    return count


def audit_images(doc_orig, doc_out, json_titles: list[str]) -> AuditResult:
    res = AuditResult()
    legacy_hits: list[dict] = []
    prompt_hits: list[dict] = []
    wrong_color_prompts: list[dict] = []

    # Walk paragraf body + paragraf di dalam cell tabel (banyak template
    # mem-wrap figure dalam tabel container 1-row sebagai layout).
    all_paras = list(doc_out.paragraphs)
    for tbl in doc_out.tables:
        for row in tbl.rows:
            for cell in row.cells:
                all_paras.extend(cell.paragraphs)

    for i, para in enumerate(all_paras):
        text = para.text
        if not text:
            continue
        for m in PLACEHOLDER_LEGACY_REGEX.finditer(text):
            legacy_hits.append({"para_index": i, "match": m.group(0)})
        for m in PROMPT_AI_REGEX.finditer(text):
            prompt_hits.append({"para_index": i, "content": m.group(1).strip()})

            # Check color of AI prompt text
            for run in para.runs:
                if "[PROMPT UNTUK AI GAMBAR:" in run.text:
                    # Check if color is set and if it's RED (0xFF, 0x00, 0x00)
                    has_wrong_color = False
                    if run.font.color.rgb:
                        r, g, b = run.font.color.rgb
                        if not (r == 0xFF and g == 0x00 and b == 0x00):
                            has_wrong_color = True
                    else:
                        # No color set means default (black) - wrong color
                        has_wrong_color = True

                    if has_wrong_color:
                        wrong_color_prompts.append({
                            "para_index": i,
                            "content": m.group(1).strip()[:100]
                        })
                    break  # Only check first occurrence in paragraph

    a_count = _count_body_drawings(doc_out)
    b_count = len(prompt_hits)
    c_count = len(json_titles)

    # === Drawing Classifier: bedakan dekoratif vs konten ===
    decorative_rids = _get_template_decorative_rids(doc_orig)
    output_rids = _extract_blip_rids(doc_out._element.body)
    preserved_decorative = decorative_rids & output_rids

    # Juga exclude gambar yang rId-nya sama dengan template original
    # (gambar template yang ke-preserve, bukan konten baru)
    orig_rids = _extract_blip_rids(doc_orig._element.body)
    preserved_template_rids = output_rids & orig_rids

    # Hitung BERAPA INSTANCE drawing yang punya rId decorative ATAU preserved template
    excluded_rids = decorative_rids | orig_rids
    decorative_count = 0
    for blip in doc_out._element.body.findall(f".//{{{DRAWING_NS}}}blip"):
        rid = blip.get(f"{{{R_NS}}}embed")
        if rid and rid in excluded_rids:
            decorative_count += 1
    # Drawing dekoratif SHAPE-ONLY (tanpa blip, mis. garis/box/textbox masthead)
    # tidak punya rId sehingga tidak tertangkap classifier blip di atas. Hitung
    # di region dekoratif (header jurnal) dan kreditkan, di-cap dengan jumlah di
    # template original via min() supaya tidak over-credit / regresi template lain.
    shape_decorative_out = _count_decorative_shape_drawings(doc_out)
    shape_decorative_orig = _count_decorative_shape_drawings(doc_orig)
    decorative_count += min(shape_decorative_out, shape_decorative_orig)
    # Gambar konten = total drawing - drawing dekoratif yang terpreservasi
    content_drawings = max(0, a_count - decorative_count)

    valid_prompts: list[dict] = []
    invalid_prompts: list[dict] = []
    for pm in prompt_hits:
        content_low = pm["content"].lower()
        matched = next((t for t in json_titles if t.lower() in content_low), None)
        if matched:
            valid_prompts.append({**pm, "title": matched})
        else:
            # Title mismatch - logged but NOT penalized (checker adaptif:
            # output bisa punya gambar beda dari JSON, yang penting ada promptnya)
            invalid_prompts.append(pm)

    # Aturan 1: '[Image placeholder]' DILARANG.
    for hit in legacy_hits:
        res.errors.append(
            f"PLACEHOLDER USANG: Paragraf #{hit['para_index']} masih berisi "
            f"'[Image placeholder]' (match: \"{hit['match']}\"). "
            f"Wajib diganti menjadi `[PROMPT UNTUK AI GAMBAR: ...]`."
        )

    # Aturan 2: gambar konten + prompt HARUS >= C (count dari JSON).
    # Extra (melebihi C) = OK, tidak dipenalty.
    # Invalid prompt (title mismatch) = OK, hanya info.
    total_content = content_drawings + b_count
    if c_count > 0:
        if total_content < c_count:
            missing = c_count - total_content
            res.errors.append(
                f"GAMBAR KURANG: JSON mendefinisikan {c_count} gambar. "
                f"Output hanya punya {content_drawings} gambar konten + {b_count} prompt AI = "
                f"{total_content}. Kurang {missing} elemen."
            )
        elif total_content > c_count:
            extra = total_content - c_count
            # Extra = bukan error, hanya info warning (tidak dipenalty)
            res.errors.append(
                f"INFO: Output memiliki {total_content} elemen konten "
                f"(gambar konten + prompt) - lebih banyak dari JSON ({c_count}). "
                f"Kelebihan {extra} elemen (TIDAK DIPENALTY - adaptif)."
            )

    # Aturan 3: prompt AI harus referensi judul JSON.
    for ip in invalid_prompts:
        res.errors.append(
            f"PROMPT TIDAK COCOK: Paragraf #{ip['para_index']} berisi prompt AI gambar, "
            f"tetapi judulnya tidak match data JSON. "
            f"Konten: \"{ip['content'][:100]}\""
        )

    # Aturan 4: prompt AI harus berwarna MERAH (RGB 0xFF, 0x00, 0x00).
    for wc in wrong_color_prompts:
        res.errors.append(
            f"WARNA PROMPT SALAH: Paragraf #{wc['para_index']} berisi prompt AI gambar "
            f"dengan warna yang salah (harus MERAH RGB 255,0,0). "
            f"Konten: \"{wc['content']}\""
        )

    res.info = {
        "a_drawings": a_count,
        "b_prompts": b_count,
        "c_expected": c_count,
        "legacy_count": len(legacy_hits),
        "valid_prompts": len(valid_prompts),
        "invalid_prompts": len(invalid_prompts),
        "wrong_color_prompts": len(wrong_color_prompts),
        "missing": max(0, c_count - total_content) if c_count > 0 else 0,
        "extra": max(0, total_content - c_count) if c_count > 0 else 0,
        "original_drawings": _count_body_drawings(doc_orig),
        "decorative_rids": list(decorative_rids),
        "preserved_decorative_count": decorative_count,
        "preserved_template_rids": list(preserved_template_rids),
        "content_drawings": content_drawings,
    }
    return res


# =============================================================================
# [5] LaTeX leak audit
# =============================================================================
def audit_latex_leaks(doc_out) -> list[dict]:
    leaks: list[dict] = []
    total_occurrences = 0
    for i, para in enumerate(doc_out.paragraphs):
        text = para.text
        if not text:
            continue
        matches = LATEX_REGEX.findall(text)
        if matches:
            uniq = list(set(matches))
            total_occurrences += len(matches)
            snippet = text[:120] + ("..." if len(text) > 120 else "")
            leaks.append({
                "para_index": i, "tags": uniq, "snippet": snippet,
                "count": len(matches),
            })
    # Store total occurrences as first element's special key (hack for backward compat)
    if leaks:
        leaks[0]["_total_occurrences"] = total_occurrences
    return leaks


# =============================================================================
# [5a] Text Quality / Mojibake Detection (MINOR -2 per karakter aneh)
# =============================================================================
# Deteksi karakter encoding rusak: double-decoded UTF-8, C1 control chars,
# replacement chars, dan garbled text. Pattern asal: AMORI_2025 (latin-1
# decode pada UTF-8 bytes dari API).
#
# Tiga signature utama:
#   1. C1 control characters (U+0080-U+009F) - tidak pernah muncul di
#      teks valid bahasa Indonesia/Inggris
#   2. Double-encoding pairs Â“ / Ã” - UTF-8 byte yang di-decode sebagai
#      latin-1 menghasilkan dua karakter: prefix Ã/A + C1 char
#   3. Unicode replacement character U+FFFD - decoder error byte invalid
def audit_text_quality(doc_out) -> list[dict]:
    """Deteksi karakter garbled/mojibake di semua paragraf.

    Returns list of dicts: [{para_index, category, chars, snippet}, ...]
    category: C1_CONTROL, DOUBLE_ENC, REPLACEMENT, atau MIXED
    """
    anomalies: list[dict] = []
    for i, para in enumerate(doc_out.paragraphs):
        text = para.text
        if not text:
            continue

        # Kategori deteksi
        c1_matches = MOJIBAKE_C1_REGEX.findall(text)
        double_matches = MOJIBAKE_DOUBLE_ENC_REGEX.findall(text)
        repl_matches = MOJIBAKE_REPLACEMENT_REGEX.findall(text)

        any_matches = MOJIBAKE_ANY_REGEX.findall(text)
        if not any_matches:
            continue

        # Tentukan kategori dominan
        categories = []
        if c1_matches:
            categories.append("C1_CONTROL")
        if double_matches:
            categories.append("DOUBLE_ENC")
        if repl_matches:
            categories.append("REPLACEMENT")
        if not categories:
            categories.append("UNKNOWN")

        category = "+".join(categories) if len(categories) <= 2 else "MIXED"

        # Highlight karakter aneh dengan repr()
        highlighted_chars = []
        for ch in text:
            if MOJIBAKE_ANY_REGEX.match(ch):
                highlighted_chars.append(f"U+{ord(ch):04X}({repr(ch)[1:-1]})")
        # Deduplicate
        uniq_chars = list(dict.fromkeys(highlighted_chars))[:10]

        snippet = text[:150] + ("..." if len(text) > 150 else "")
        anomalies.append({
            "para_index": i,
            "category": category,
            "chars": uniq_chars,
            "count": len(any_matches),
            "snippet": snippet,
        })
    return anomalies


# =============================================================================
# [5b] Image Position Cross-Check (MINOR -3 per figure di posisi salah)
# =============================================================================
# Validasi bahwa gambar muncul SETELAH referensi teks pertama.
# Contoh: "seperti ditunjukkan pada Gambar 1" harus muncul SEBELUM gambar.

FIGURE_REF_REGEX = re.compile(
    r"\b(?:Gambar|Gbr\.?|Figure|Fig\.?|Tabel|Table|Tab\.?)\s*(\d+)",
    re.IGNORECASE
)


def _find_figure_references(paragraphs) -> dict[str, int]:
    """Mapping figure_number -> first paragraph index where referenced.

    Returns dict like {"1": 5, "2": 12} meaning "Figure 1" first appears at para 5.
    """
    refs: dict[str, int] = {}
    for i, para in enumerate(paragraphs):
        text = para.text
        if not text:
            continue
        for m in FIGURE_REF_REGEX.finditer(text):
            fig_num = m.group(1)
            key = fig_num
            if key not in refs:
                refs[key] = i
    return refs


def _get_drawing_positions(doc, decorative_rids: set[str] | None = None) -> dict[int, int]:
    """Mapping drawing_index -> paragraph_index where it appears.

    Skip drawing yang rId-nya match decorative_rids (logo).
    Returns dict like {0: 8, 1: 15} meaning drawing 0 is at para 8.
    """
    positions: dict[int, int] = {}
    drawing_idx = 0
    decorative_rids = decorative_rids or set()

    def _drawing_rids(drawing_el) -> set[str]:
        rids: set[str] = set()
        for blip in drawing_el.findall(f".//{{{DRAWING_NS}}}blip"):
            rid = blip.get(f"{{{R_NS}}}embed")
            if rid:
                rids.add(rid)
        return rids

    # Iterasi semua paragraf di body
    for i, para in enumerate(doc.paragraphs):
        drawings = para._element.findall(f".//{qn('w:drawing')}")
        for d in drawings:
            d_rids = _drawing_rids(d)
            # Skip drawing yang termasuk decorative (logo)
            if d_rids and d_rids.issubset(decorative_rids):
                continue
            positions[drawing_idx] = i
            drawing_idx += 1

    # Juga cek tabel di body (skip decorative)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    drawings = para._element.findall(f".//{qn('w:drawing')}")
                    for d in drawings:
                        d_rids = _drawing_rids(d)
                        if d_rids and d_rids.issubset(decorative_rids):
                            continue
                        positions[drawing_idx] = i
                        drawing_idx += 1

    return positions


def audit_figure_position(doc_out, doc_orig=None) -> AuditResult:
    """Validasi posisi gambar relatif terhadap referensi teks.

    Aturan:
    - Gambar harus muncul SETELAH (atau di paragraf yang sama dengan)
      referensi pertama, ATAU
    - Caption-first layout VALID: drawing -> caption -> reference dalam jarak <=3 paragraf.

    Penalty hanya jika gambar muncul JAUH SEBELUM referensi (gap > 3).
    Logo decorative (rId match template original) di-skip.
    """
    res = AuditResult()

    paragraphs = list(doc_out.paragraphs)
    refs = _find_figure_references(paragraphs)

    decorative_rids = set()
    if doc_orig is not None:
        decorative_rids = _get_template_decorative_rids(doc_orig)
    drawing_positions = _get_drawing_positions(doc_out, decorative_rids)

    CAPTION_FIRST_GAP = 3  # toleransi caption-first layout

    violations: list[dict] = []
    caption_first_count = 0

    for draw_idx, para_idx in drawing_positions.items():
        fig_num = str(draw_idx + 1)

        if fig_num in refs:
            ref_para_idx = refs[fig_num]
            if para_idx < ref_para_idx:
                gap = ref_para_idx - para_idx
                if gap <= CAPTION_FIRST_GAP:
                    # Caption-first layout - VALID, drawing-caption-reference berdekatan
                    caption_first_count += 1
                    continue
                # Gambar muncul JAUH sebelum referensi -> violation
                snippet = paragraphs[para_idx].text[:60] if para_idx < len(paragraphs) else ""
                violations.append({
                    "figure_num": fig_num,
                    "drawing_idx": draw_idx,
                    "drawing_para": para_idx,
                    "ref_para": ref_para_idx,
                    "gap": gap,
                    "snippet": snippet,
                })

    if violations:
        for v in violations:
            res.errors.append(
                f"FIGURE POSITION: Gambar {v['figure_num']} muncul di paragraf #{v['drawing_para']} "
                f"JAUH SEBELUM referensi pertama di paragraf #{v['ref_para']} (gap {v['gap']} paragraf, "
                f"toleransi caption-first <= {CAPTION_FIRST_GAP}). "
                f"Snippet: \"{v['snippet']}...\""
            )

    res.info = {
        "violations": len(violations),
        "caption_first_layout": caption_first_count,
        "total_drawings": len(drawing_positions),
        "figures_with_refs": len(refs),
    }
    return res


# =============================================================================
# [5c] Heading Auto-Numbering Render Check (MINOR -3 per inkonsistensi)
# =============================================================================
# Parse numbering.xml untuk simulasi nomor heading yang akan dirender Word.
# Validasi: 1, 2, 3... berurutan tanpa skip atau duplikat.

def _parse_numbering_xml(doc) -> dict:
    """Parse word/numbering.xml -> mapping numId -> abstractNumId -> level format.

    Return: {numId: {level: format_str}} atau {} jika tidak ada numbering.
    """
    try:
        numbering_part = doc.part.numbering_part
        if numbering_part is None:
            return {}
        numbering_elem = numbering_part.element
    except (AttributeError, KeyError, NotImplementedError):
        return {}

    # Build abstractNumId -> {level: format}
    abstract_map: dict[str, dict[int, str]] = {}
    for abs_num in numbering_elem.findall(qn("w:abstractNum")):
        abs_id = abs_num.get(qn("w:abstractNumId"))
        if abs_id is None:
            continue
        levels: dict[int, str] = {}
        for lvl in abs_num.findall(qn("w:lvl")):
            ilvl = lvl.get(qn("w:ilvl"))
            if ilvl is None:
                continue
            num_fmt = lvl.find(qn("w:numFmt"))
            fmt = num_fmt.get(qn("w:val")) if num_fmt is not None else "decimal"
            try:
                levels[int(ilvl)] = fmt
            except (ValueError, TypeError):
                continue
        abstract_map[abs_id] = levels

    # Build numId -> abstractNumId -> levels
    num_map: dict[str, dict[int, str]] = {}
    for num in numbering_elem.findall(qn("w:num")):
        num_id = num.get(qn("w:numId"))
        if num_id is None:
            continue
        abs_ref = num.find(qn("w:abstractNumId"))
        if abs_ref is None:
            continue
        abs_id = abs_ref.get(qn("w:val"))
        if abs_id in abstract_map:
            num_map[num_id] = abstract_map[abs_id]

    return num_map


def _get_numid_to_abstractid(doc) -> dict[str, str]:
    """Mapping numId -> abstractNumId. Untuk B2: compare abstract bukan raw numId."""
    try:
        numbering_part = doc.part.numbering_part
        if numbering_part is None:
            return {}
        numbering_elem = numbering_part.element
    except (AttributeError, KeyError, NotImplementedError):
        return {}

    mapping: dict[str, str] = {}
    for num in numbering_elem.findall(qn("w:num")):
        num_id = num.get(qn("w:numId"))
        abs_ref = num.find(qn("w:abstractNumId"))
        if num_id is not None and abs_ref is not None:
            abs_id = abs_ref.get(qn("w:val"))
            if abs_id is not None:
                mapping[num_id] = abs_id
    return mapping


def _get_paragraph_numbering(para) -> tuple[str | None, int]:
    """Extract numId dan ilvl dari paragraf. Return (numId, ilvl) atau (None, 0)."""
    pPr = para._element.find(qn("w:pPr"))
    if pPr is None:
        return None, 0
    numPr = pPr.find(qn("w:numPr"))
    if numPr is None:
        return None, 0
    numId_elem = numPr.find(qn("w:numId"))
    ilvl_elem = numPr.find(qn("w:ilvl"))
    num_id = numId_elem.get(qn("w:val")) if numId_elem is not None else None
    try:
        ilvl = int(ilvl_elem.get(qn("w:val"))) if ilvl_elem is not None else 0
    except (ValueError, TypeError):
        ilvl = 0
    return num_id, ilvl


def audit_heading_numbering(doc_orig, doc_out) -> AuditResult:
    """Validasi konsistensi heading numbering.

    Cek (B2 update):
    - Setiap numId di output: ekstrak abstractNumId target
    - Jika abstractNumId tsb ada di template original -> valid (clone abstract)
    - Jika abstractNumId baru -> flag sebagai abstract_numid_new
    """
    res = AuditResult()

    orig_num_map = _parse_numbering_xml(doc_orig)
    out_num_map = _parse_numbering_xml(doc_out)

    # B2: mapping numId -> abstractNumId untuk perbandingan abstract
    orig_numid_to_abs = _get_numid_to_abstractid(doc_orig)
    out_numid_to_abs = _get_numid_to_abstractid(doc_out)
    orig_abstract_ids = set(orig_numid_to_abs.values())

    # Kumpulkan paragraf heading yang punya numbering
    out_headings: list[dict] = []
    for i, para in enumerate(doc_out.paragraphs):
        num_id, ilvl = _get_paragraph_numbering(para)
        if num_id is not None:
            style_name = (para.style.name if para.style else "Normal") or "Normal"
            if "heading" in style_name.lower() or "judul" in style_name.lower():
                out_headings.append({
                    "para_index": i,
                    "num_id": num_id,
                    "ilvl": ilvl,
                    "style": style_name,
                    "text": para.text[:60],
                })

    # B2: Cek format match via abstractNumId, bukan raw numId
    format_mismatches: list[dict] = []
    for h in out_headings:
        # Skip numId=0 (no numbering) - itu valid edge case (e.g. REFERENCES)
        if h["num_id"] == "0":
            continue
        if h["num_id"] in orig_num_map:
            # numId match langsung -> valid
            continue
        # numId tidak ada di orig -> cek abstractNumId target
        abs_id = out_numid_to_abs.get(h["num_id"])
        if abs_id is not None and abs_id in orig_abstract_ids:
            # Generator clone abstractNumId yang ada di template -> valid
            continue
        # numId baru DAN abstractNumId baru -> mismatch real
        if orig_num_map:
            format_mismatches.append({
                "para_index": h["para_index"],
                "issue": "abstract_numid_new" if abs_id else "unknown_numid",
                "num_id": h["num_id"],
                "abstract_id": abs_id,
                "text": h["text"],
            })

    # Cek sequence: untuk level 0 (top-level heading), nomor harus berurutan
    level_0_count = sum(1 for h in out_headings if h["ilvl"] == 0)

    if format_mismatches:
        for fm in format_mismatches:
            abs_info = f", absId={fm['abstract_id']}" if fm["abstract_id"] else ""
            res.errors.append(
                f"NUMBERING MISMATCH: Paragraf #{fm['para_index']} ({fm['issue']}, "
                f"numId={fm['num_id']}{abs_info}). Snippet: \"{fm['text']}\""
            )

    res.info = {
        "total_headings": len(out_headings),
        "level_0_count": level_0_count,
        "format_mismatches": len(format_mismatches),
        "orig_num_count": len(orig_num_map),
        "out_num_count": len(out_num_map),
        "orig_abstract_count": len(orig_abstract_ids),
        "out_abstract_count": len(set(out_numid_to_abs.values())),
    }
    return res


# =============================================================================
# [5c.2] Section Numbering Format Audit (MINOR -3 per mismatch)
# =============================================================================
# Validasi bahwa format numbering section (decimal/roman/letter) di output
# konsisten dengan template original. Tidak cuma cek numPr abstractNumId,
# tapi cek actual rendered number di teks heading.
#
# Contoh mismatch:
#   Template pakai decimal (1., 1.1, 2.), tapi output pakai roman (I., II.)
#   atau letter (A., B.) untuk level yang sama.
#
# Pattern asal: PERTANIKA 2025 (run 2026-06-19).

SECTION_NUM_DECIMAL = re.compile(r"^(\d+(?:\.\d+)*)[\.\)\s]")
SECTION_NUM_UPPER_ROMAN = re.compile(r"^([IVXLCDM]+)[\.\)\s]")
SECTION_NUM_LOWER_ROMAN = re.compile(r"^([ivxlcdm]+)[\.\)\s]")
SECTION_NUM_UPPER_LETTER = re.compile(r"^([A-Z])[\.\)\s]")
SECTION_NUM_LOWER_LETTER = re.compile(r"^([a-z])[\.\)\s]")


def _classify_number_format(text: str) -> str | None:
    """Tentukan format numbering dari prefix teks heading.

    Returns: 'decimal', 'upper_roman', 'lower_roman', 'upper_letter',
             'lower_letter', atau None.
    """
    if not text:
        return None
    if SECTION_NUM_DECIMAL.match(text):
        return "decimal"
    if SECTION_NUM_UPPER_ROMAN.match(text):
        return "upper_roman"
    if SECTION_NUM_LOWER_ROMAN.match(text):
        return "lower_roman"
    if SECTION_NUM_UPPER_LETTER.match(text):
        return "upper_letter"
    if SECTION_NUM_LOWER_LETTER.match(text):
        return "lower_letter"
    return None


def _extract_number_prefix(text: str) -> str | None:
    """Extract numbering prefix dari awal teks heading."""
    if not text:
        return None
    for pat in [SECTION_NUM_DECIMAL, SECTION_NUM_UPPER_ROMAN,
                SECTION_NUM_LOWER_ROMAN, SECTION_NUM_UPPER_LETTER,
                SECTION_NUM_LOWER_LETTER]:
        m = pat.match(text)
        if m:
            return m.group(0).rstrip()
    return None


def audit_section_numbering_format(doc_orig, doc_out) -> AuditResult:
    """Validasi konsistensi format numbering section (decimal/roman/letter).

    Mengumpulkan heading di kedua dokumen, mengelompokkan berdasarkan ilvl
    (level nesting), lalu membandingkan format numbering per level.
    Flag mismatch jika format di output berbeda dari template untuk level yg sama.
    """
    res = AuditResult()

    def _get_heading_numbering(doc):
        """Return list of {para_index, ilvl, text, format, prefix, style}."""
        headings: list[dict] = []
        for i, para in enumerate(doc.paragraphs):
            style_name = (para.style.name if para.style else "Normal") or "Normal"
            if "heading" not in style_name.lower() and "judul" not in style_name.lower():
                continue
            num_id, ilvl = _get_paragraph_numbering(para)
            text = para.text.strip()
            if not text:
                continue
            fmt = _classify_number_format(text)
            prefix = _extract_number_prefix(text)
            headings.append({
                "para_index": i,
                "ilvl": ilvl if ilvl is not None else 0,
                "text": text[:60],
                "format": fmt,
                "prefix": prefix,
                "style": style_name,
                "num_id": num_id,
            })
        return headings

    orig_headings = _get_heading_numbering(doc_orig)
    out_headings = _get_heading_numbering(doc_out)

    # Kelompokkan berdasarkan ilvl, cari format dominan per level
    def _dominant_format(headings: list[dict], ilvl: int) -> str | None:
        formats = [h["format"] for h in headings if h["ilvl"] == ilvl and h["format"]]
        if not formats:
            return None
        # Return format yang paling sering muncul untuk level ini
        from collections import Counter
        return Counter(formats).most_common(1)[0][0]

    mismatches: list[dict] = []
    # Dapatkan semua ilvl yang muncul
    all_ilvls = sorted(set(
        h["ilvl"] for h in orig_headings + out_headings
    ))

    for ilvl in all_ilvls:
        orig_fmt = _dominant_format(orig_headings, ilvl)
        out_fmt = _dominant_format(out_headings, ilvl)

        # Jika salah satu tidak punya heading di level ini, skip
        if orig_fmt is None or out_fmt is None:
            continue

        if orig_fmt != out_fmt:
            # Flag semua heading di level ini yang formatnya beda
            orig_level_headings = [h for h in orig_headings if h["ilvl"] == ilvl]
            out_level_headings = [h for h in out_headings if h["ilvl"] == ilvl]

            # Flag heading output yang formatnya tidak match template
            for h in out_level_headings:
                if h["format"] != orig_fmt:
                    mismatches.append({
                        "para_index": h["para_index"],
                        "ilvl": ilvl,
                        "template_format": orig_fmt,
                        "output_format": h["format"],
                        "text": h["text"],
                    })

    if mismatches:
        for m in mismatches[:10]:
            res.errors.append(
                f"SECTION NUM FORMAT MISMATCH: level={m['ilvl']} "
                f"template={m['template_format']} vs "
                f"output={m['output_format']}. "
                f"\"{m['text']}\""
            )

    # Hitung statistik per level
    format_stats: dict[int, dict] = {}
    for ilvl in all_ilvls:
        orig_fmt = _dominant_format(orig_headings, ilvl)
        out_fmt = _dominant_format(out_headings, ilvl)
        orig_count = sum(1 for h in orig_headings if h["ilvl"] == ilvl)
        out_count = sum(1 for h in out_headings if h["ilvl"] == ilvl)
        format_stats[ilvl] = {
            "orig_format": orig_fmt,
            "out_format": out_fmt,
            "orig_count": orig_count,
            "out_count": out_count,
        }

    res.info = {
        "orig_heading_count": len(orig_headings),
        "out_heading_count": len(out_headings),
        "levels_checked": len(all_ilvls),
        "format_mismatches": len(mismatches),
        "per_level": format_stats,
    }
    return res


# =============================================================================
# [5d] Run Formatting Audit (MINOR -2 per mismatch)
# =============================================================================
# Cek color, underline, vertAlign, bold, italic pada sample paragraf.

def _extract_run_formatting(run) -> dict:
    """Extract formatting info dari run: color, underline, vertAlign, bold, italic, font."""
    fmt: dict = {
        "color": None,
        "underline": None,
        "vertAlign": None,
        "bold": None,
        "italic": None,
        "font_name": None,
        "size": None,
    }
    rPr = run._element.find(qn("w:rPr"))
    if rPr is None:
        return fmt

    color = rPr.find(qn("w:color"))
    if color is not None:
        fmt["color"] = color.get(qn("w:val"))

    u = rPr.find(qn("w:u"))
    if u is not None:
        fmt["underline"] = u.get(qn("w:val"), "single")

    va = rPr.find(qn("w:vertAlign"))
    if va is not None:
        fmt["vertAlign"] = va.get(qn("w:val"))

    b = rPr.find(qn("w:b"))
    if b is not None:
        val = b.get(qn("w:val"), "1")
        fmt["bold"] = val not in ("0", "false")

    i = rPr.find(qn("w:i"))
    if i is not None:
        val = i.get(qn("w:val"), "1")
        fmt["italic"] = val not in ("0", "false")

    rfonts = rPr.find(qn("w:rFonts"))
    if rfonts is not None:
        fmt["font_name"] = (
            rfonts.get(qn("w:ascii"))
            or rfonts.get(qn("w:hAnsi"))
            or rfonts.get(qn("w:cs"))
        )

    sz = rPr.find(qn("w:sz"))
    if sz is not None:
        try:
            fmt["size"] = int(sz.get(qn("w:val")))
        except (ValueError, TypeError):
            pass

    return fmt


# =============================================================================
# [5g] Double Numbering Detection (B9)
# =============================================================================
# Deteksi heading yang punya BOTH:
# - numPr (auto-numbering dari template Word style)
# - prefix angka manual di awal teks (misal "1. PENDAHULUAN", "I. METODE", "A. ...")
# Ini menyebabkan output Word menampilkan "1. 1. PENDAHULUAN" (double numbering).

# Pattern prefix angka manual yang sering muncul:
# - "1. ", "1.1 ", "10. " (decimal)
# - "I. ", "II. ", "IV. " (uppercase roman)
# - "i. ", "ii. ", "iv. " (lowercase roman)
# - "A. ", "B. ", "AA. " (uppercase letter)
# - "a. ", "b. " (lowercase letter)
MANUAL_PREFIX_REGEX = re.compile(
    r"^\s*("
    r"\d+(?:\.\d+)*[\.\)]\s+|"      # decimal: 1. , 1.1 , 1.1.1 , 1)
    r"[IVXLCDM]+[\.\)]\s+|"          # upper roman: I. II. III.
    r"[ivxlcdm]+[\.\)]\s+|"          # lower roman: i. ii.
    r"[A-Z]{1,2}[\.\)]\s+|"          # upper letter: A. B. AA.
    r"[a-z][\.\)]\s+"                # lower letter: a. b.
    r")"
)

# Pattern double numbering di referensi: [1] [1], [1] 1., dsb
REF_DOUBLE_NUM_REGEX = re.compile(
    r"^\s*"                          # optional leading whitespace
    r"\[(\d+)\]"                     # [N] - first bracketed number
    r"\s*"                           # optional space
    r"("
    r"\[(\d+)\]"                     # [M] - second bracketed (same or different)
    r"|"
    r"(\d+)\.?"                      # M. - plain number with optional dot
    r"|"
    r"\[(\d+)\]\s*\[(\d+)\]"         # [N][M] - no space between brackets
    r")"
    r"\s+"
)


def _style_has_numpr(doc, style_name: str) -> bool:
    """Cek apakah style di styles.xml inherit numPr (auto-numbering)."""
    if not style_name:
        return False
    try:
        style_elem = doc.styles.element
    except AttributeError:
        return False
    # Normalize style name lookup (Word uses styleId, often without space)
    target = style_name.lower().replace(" ", "")
    for style in style_elem.findall(qn("w:style")):
        sid = style.get(qn("w:styleId"))
        if not sid:
            continue
        if sid.lower().replace(" ", "") != target:
            continue
        pPr = style.find(qn("w:pPr"))
        if pPr is None:
            return False
        numPr = pPr.find(qn("w:numPr"))
        if numPr is None:
            return False
        numId_el = numPr.find(qn("w:numId"))
        if numId_el is None:
            return False
        numId_val = numId_el.get(qn("w:val"))
        # numId=0 berarti no numbering, jadi false
        return numId_val is not None and numId_val != "0"
    return False


def audit_double_numbering(doc_out) -> AuditResult:
    """Deteksi heading dengan double numbering (numPr aktif + prefix manual).

    Aturan:
    - Cek paragraph yang punya numPr (numId != 0)
    - Style HARUS heading (bukan reference, body, dll - reference list valid
      pakai pattern "C. Lugaresi" sebagai author initial)
    - Cek apakah teks paragraph diawali prefix angka manual
    - Single uppercase letter (A.) hanya di-flag kalau diikuti ALL CAPS atau
      style explicitly heading (bukan author name initial)
    """
    res = AuditResult()
    violations: list[dict] = []

    # Style yang DI-SKIP - bukan heading, jadi bukan double numbering issue
    SKIP_STYLE_PATTERNS = [
        "reference", "bibliograph", "citation",
        "body", "normal", "caption", "footnote",
        "list paragraph", "bullet", "table",
        "author", "abstract", "keywords",
    ]

    for i, para in enumerate(doc_out.paragraphs):
        text = (para.text or "").strip()
        if not text or len(text) < 3:
            continue

        # Cek numPr di paragraf (eksplisit) - kalau numId=0, override style ke "no numbering"
        num_id, ilvl = _get_paragraph_numbering(para)
        para_overrides_to_zero = num_id == "0"
        para_has_num = num_id is not None and num_id != "0"

        # Cek style: kalau style heading-related, juga cek style-inherited numPr
        style_name = (para.style.name if para.style else "") or ""
        style_lower = style_name.lower()

        # Skip kalau style bukan heading dan bukan candidate
        if any(skip in style_lower for skip in SKIP_STYLE_PATTERNS):
            continue

        # Cek style inheritance numPr
        style_has_num = _style_has_numpr(doc_out, style_name)

        # Effective auto_num: paragraf eksplisit punya numPr non-zero ATAU
        # (style punya numPr DAN paragraf tidak override ke zero)
        has_auto_num = para_has_num or (style_has_num and not para_overrides_to_zero)

        # Hanya proses kalau ada auto_num (paragraf atau style-inherited)
        if not has_auto_num:
            continue

        # Cek prefix manual
        m = MANUAL_PREFIX_REGEX.match(text)
        if not m:
            continue
        prefix = m.group(1).strip()

        # Skip kalau prefix single letter (A./B./C.) yang diikuti pattern nama
        # author (capital + lowercase) - bukan heading
        rest = text[m.end():].strip()
        if re.fullmatch(r"[A-Z][\.\)]", prefix):
            # Single uppercase letter prefix
            # Skip kalau rest mulai dengan capital + lowercase (likely author name)
            if rest and re.match(r"^[A-Z][a-z]", rest):
                continue
            # Skip kalau rest tidak ALL CAPS (kemungkinan bukan heading)
            if rest and not rest[:20].isupper() and not any(
                "heading" in style_lower or "judul" in style_lower
                for _ in [None]
            ):
                continue

        # Skip kalau lower letter prefix (a./b.) tanpa konteks heading style
        if re.fullmatch(r"[a-z][\.\)]", prefix):
            if "heading" not in style_lower and "judul" not in style_lower:
                continue

        violations.append({
            "para_index": i,
            "prefix": prefix,
            "style": style_name,
            "text": text[:60],
        })

    if violations:
        for v in violations:
            res.errors.append(
                f"DOUBLE NUMBERING: Paragraf #{v['para_index']} (style '{v['style']}') "
                f"punya auto-numbering DAN prefix manual '{v['prefix']}'. "
                f"Hasil render Word: prefix akan double. "
                f"Snippet: \"{v['text']}\""
            )

    res.info = {
        "violations": len(violations),
        "details": violations,
    }
    return res


# =============================================================================
# [5g.2] Reference Double Numbering (MINOR -3 per violation)
# =============================================================================
# Deteksi manual double numbering di daftar referensi:
#   [1] [1] Kadir... - prefix generator + nomor dalam teks
#   [1] 1. Smith... - bracketed + dot numbering
def audit_reference_double_numbering(doc_out) -> AuditResult:
    """Deteksi paragraf referensi dengan double numbering manual."""
    res = AuditResult()
    violations: list[dict] = []
    in_refs = False

    for i, para in enumerate(doc_out.paragraphs):
        text = (para.text or "").strip()
        if not text:
            continue

        style_name = (para.style.name if para.style else "") or ""
        style_lower = style_name.lower()

        # Detect start/end of reference section
        if re.match(r"^(?:REFERENCES?|DAFTAR\s+PUSTAKA|BIBLIOGRAPHY)\s*$",
                    text, re.IGNORECASE):
            in_refs = True
            continue

        # End of references: next section heading
        if in_refs and text and len(text) < 30 and (text.isupper() or
                re.match(r"^[A-Z][a-z].{0,25}$", text)):
            if not re.match(r"^\[\d+\]", text):
                in_refs = False
                continue

        if not in_refs:
            continue

        # Skip if already detected by audit_double_numbering (has numPr)
        num_id, _ = _get_paragraph_numbering(para)
        if num_id is not None and num_id != "0":
            continue  # handled by audit_double_numbering

        # Check for manual double numbering: [N] [M] or [N] M.
        m = REF_DOUBLE_NUM_REGEX.match(text)
        if not m:
            continue

        first_num = m.group(1)
        # Determine type
        if m.group(3):  # [N] [M] with space
            second_num = m.group(3)
            vtype = "bracket_bracket"
            snippet = text[:80]
        elif m.group(4):  # [N] M.
            second_num = m.group(4)
            vtype = "bracket_dot"
            snippet = text[:80]
        elif m.group(5):  # [N][M] no space
            second_num = m.group(5)  # Actually group 5 is first of [N][M]
            vtype = "bracket_bracket_nows"
            snippet = text[:80]
        else:
            continue

        violations.append({
            "para_index": i,
            "type": vtype,
            "first_num": first_num,
            "second_num": second_num,
            "snippet": snippet,
        })

    for v in violations:
        res.errors.append(
            f"DOUBLE NUM REF: Paragraf #{v['para_index']} [{v['type']}] "
            f"[{v['first_num']}] [{v['second_num']}] - \"{v['snippet']}\""
        )
    res.count = len(violations)
    res.details = {"violations": violations}
    return res


def audit_run_formatting(doc_orig, doc_out, n_check: int = 10) -> AuditResult:
    """Bandingkan formatting first-run dari sample paragraf.

    Memakai paragraph alignment untuk pasangan yang valid.
    Hanya flag perbedaan SUBSTANTIF: skip "explicit default vs implicit default"
    (misal orig bold=False vs out bold=None - keduanya non-bold).
    """
    res = AuditResult()

    orig_paras = [p for p in doc_orig.paragraphs if p.text.strip()][:n_check * 2]
    out_paras = [p for p in doc_out.paragraphs if p.text.strip()][:n_check * 2]
    pairs = _align_paragraph_pairs(orig_paras, out_paras)[:n_check]

    # Default values per field (None == default == aman jika nilai non-default tidak hilang)
    DEFAULT_VALUES = {
        "color": ("000000", "auto", None),  # hitam = default
        "underline": ("none", None),         # tanpa underline
        "vertAlign": ("baseline", None),     # baseline
        "bold": (False, None),
        "italic": (False, None),
    }

    def _is_substantive_diff(field, orig_val, out_val) -> bool:
        """True jika perbedaan benar-benar mengubah rendering.

        Hanya flag jika ORIG punya nilai explicit non-default yang HILANG di output.
        Output yang menambah formatting eksplisit (sementara orig pakai style inheritance)
        tidak di-flag karena tidak menyebabkan visual regression.
        """
        if orig_val == out_val:
            return False
        defaults = DEFAULT_VALUES.get(field, (None,))
        orig_is_default = orig_val in defaults
        out_is_default = out_val in defaults
        # Keduanya default -> tidak substantif
        if orig_is_default and out_is_default:
            return False
        # Orig default, out punya nilai eksplisit -> output ADD formatting (skip)
        # Ini bukan visual regression; output cuma jadi lebih eksplisit
        if orig_is_default and not out_is_default:
            return False
        # Orig punya nilai eksplisit, out kehilangannya -> visual regression
        return True

    # B6: Authors line detection patterns
    # Authors line biasanya: "Name1*1, Name2*2" or "Name1, Name2, Name3" with affiliation numbers
    AUTHORS_LINE_PATTERNS = [
        # Multi-author dengan affiliation numbers: "Name1, Name2,..." atau "Name1*, Name2"
        re.compile(r'^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3}\s*[\d*]+\s*[,*]', re.MULTILINE),
        # 3+ author names dengan koma
        re.compile(r'\b[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+,\s*[A-Z][a-zA-Z]+\s+[A-Z][a-zA-Z]+'),
        # Affiliation line ("1 Department of...", "1Faculty of...")
        re.compile(r'^\s*\d+\s*[A-Z][a-z]+\s+(?:of\s+)?(?:Department|Faculty|School|Engineering|Automation|Mechanical|Electrical|University|Institute|College)', re.MULTILINE),
        # Email line dengan affiliation marker
        re.compile(r'\bEmail:.*\d+\s*[a-zA-Z]+@'),
    ]

    def _is_authors_line(text: str) -> bool:
        if not text:
            return False
        for pat in AUTHORS_LINE_PATTERNS:
            if pat.search(text):
                return True
        return False

    mismatches: list[dict] = []
    for orig_idx, out_idx in pairs:
        orig_p = orig_paras[orig_idx]
        out_p = out_paras[out_idx]
        if not orig_p.runs or not out_p.runs:
            continue

        # Guard: skip jika text content sangat berbeda (likely beda paragraf
        # struktural). Run formatting check hanya valid kalau paragraf-nya
        # serupa secara konten atau peran (mis. authors line, abstract label).
        orig_text_norm = (orig_p.text or "").lower().strip()
        out_text_norm = (out_p.text or "").lower().strip()
        # Skip jika konten sangat berbeda (paragraf tidak align secara semantik).
        # Threshold diturunkan dari 20 ke 8 char karena banyak heading section
        # original pendek ("Abstract", "Method", dll) tapi tidak match dengan
        # body content output - ini false positive untuk bold/italic check.
        if len(orig_text_norm) >= 8 and len(out_text_norm) >= 8:
            orig_words = set(re.findall(r"\b\w{3,}\b", orig_text_norm))
            out_words = set(re.findall(r"\b\w{3,}\b", out_text_norm))
            # Skip kalau Jaccard similarity < 0.25 (paragraf benar-benar beda)
            if orig_words and out_words:
                overlap = len(orig_words & out_words)
                union = len(orig_words | out_words)
                jaccard = overlap / union if union else 0
                if jaccard < 0.25:
                    continue

        orig_fmt = _extract_run_formatting(orig_p.runs[0])
        out_fmt = _extract_run_formatting(out_p.runs[0])
        out_text = out_p.text or ""
        is_authors = _is_authors_line(out_text)

        for key in ("color", "underline", "vertAlign", "bold", "italic"):
            orig_val = orig_fmt.get(key)
            out_val = out_fmt.get(key)
            if _is_substantive_diff(key, orig_val, out_val):
                hint = ""
                # B6: Hint khusus untuk vertAlign superscript di authors line
                if is_authors and key == "vertAlign" and orig_val == "superscript":
                    hint = " [HINT: ini di authors line, affiliation numbers butuh superscript]"
                mismatches.append({
                    "para_index": out_idx,
                    "field": key,
                    "orig": orig_val,
                    "out": out_val,
                    "snippet": out_p.text[:50],
                    "hint": hint,
                })

    if mismatches:
        for m in mismatches[:10]:
            res.errors.append(
                f"RUN FORMAT MISMATCH: Paragraf #{m['para_index']} field '{m['field']}' "
                f"berbeda (orig={m['orig']}, out={m['out']}).{m.get('hint', '')} "
                f"\"{m['snippet']}\""
            )

    res.info = {
        "checked": len(pairs),
        "mismatches": len(mismatches),
    }
    return res


# =============================================================================
# [5e] Table Content Validation (MINOR -3 per tabel kosong)
# =============================================================================
def _table_cell_density(table) -> float:
    """Hitung rasio cell yang non-kosong vs total cell."""
    total_cells = 0
    non_empty = 0
    for row in table.rows:
        for cell in row.cells:
            total_cells += 1
            text = "".join(p.text for p in cell.paragraphs).strip()
            if text:
                non_empty += 1
    if total_cells == 0:
        return 1.0  # tabel kosong total -> abaikan
    return non_empty / total_cells


def audit_table_content(doc_out, density_threshold: float = 0.5, doc_orig=None) -> AuditResult:
    """Flag tabel di output yang density-nya di bawah threshold (placeholder).

    Jika doc_orig disediakan dan tabel pada index sama di original juga punya
    density rendah, skip flag (itu memang tabel layout/cover dari template).
    """
    res = AuditResult()

    # Pre-compute density tabel original (untuk filter false positive layout cover)
    orig_densities: dict[int, float] = {}
    if doc_orig is not None:
        for i, t in enumerate(doc_orig.tables):
            try:
                orig_densities[i] = _table_cell_density(t)
            except Exception:
                orig_densities[i] = 1.0

    low_density_tables: list[dict] = []
    for i, table in enumerate(doc_out.tables):
        # Skip tabel yang punya drawing (logo) - bukan tabel konten
        has_drawing = False
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    if para._element.findall(f".//{qn('w:drawing')}"):
                        has_drawing = True
                        break
                if has_drawing:
                    break
            if has_drawing:
                break
        if has_drawing:
            continue

        # Skip tabel ukuran 1x1 (biasanya structural, bukan konten)
        n_rows = len(table.rows)
        n_cols = len(table.rows[0].cells) if n_rows > 0 else 0
        if n_rows < 2 or n_cols < 2:
            continue

        density = _table_cell_density(table)
        if density < density_threshold:
            # Skip jika original tabel pada posisi sama juga low density
            # (itu memang tabel layout cover, bukan placeholder kosong yang error).
            orig_dens = orig_densities.get(i)
            if orig_dens is not None and orig_dens < density_threshold:
                continue
            low_density_tables.append({
                "table_index": i,
                "density": density,
                "n_rows": n_rows,
                "n_cols": n_cols,
            })

    if low_density_tables:
        for t in low_density_tables:
            res.errors.append(
                f"TABLE LOW DENSITY: Tabel #{t['table_index']} "
                f"({t['n_rows']}x{t['n_cols']}) density={t['density']:.0%} "
                f"< {density_threshold:.0%}. Indikasi tabel placeholder kosong."
            )

    res.info = {
        "total_tables": len(doc_out.tables),
        "low_density_count": len(low_density_tables),
        "details": low_density_tables,
    }
    return res


# =============================================================================
# [5e2] Table Border Visibility (MINOR -5 per invisible, -3 per thin/mismatch)
# =============================================================================
def _classify_border_pattern(t) -> str:
    """Klasifikasi pattern border tabel ke salah satu kategori.

    Kategori:
    - FULL_GRID: semua side ada border ATAU pakai tblStyle 'TableGrid' (built-in)
    - HORIZONTAL_ONLY: top + bottom (+ insideH) ada, left/right/insideV kosong
                       (academic style umum di journal IEEE, ASEAN, dll)
    - TOP_ONLY: cuma top yang ada
    - BOTTOM_ONLY: cuma bottom yang ada
    - CUSTOM_STYLE: pakai custom tblStyle (Table1, Table2, dll) -- pattern
                    aktualnya define di styles.xml, dianggap "any" untuk
                    perbandingan supaya tidak false-positive mismatch.
    - NO_BORDERS: tidak ada tblBorders sama sekali (rely on tblStyle)
    - INVISIBLE: ada tblBorders tapi semua val='none'/'nil'
    - PARTIAL: pattern lain (mixed)
    """
    from docx.oxml.ns import qn as _qn
    tblPr = t._element.find(_qn("w:tblPr"))
    borders = tblPr.find(_qn("w:tblBorders")) if tblPr is not None else None

    # Cek tblStyle dulu
    if tblPr is not None:
        tbl_style = tblPr.find(_qn("w:tblStyle"))
        if tbl_style is not None:
            style_val = tbl_style.get(_qn("w:val")) or ""
            # "TableGrid" / "Table Grid" adalah built-in Word style dengan full grid
            if style_val in ("TableGrid", "Table Grid"):
                return "FULL_GRID"
            # Custom style (Table1, MyStyle, dll) - rendering tergantung styles.xml
            # Treat sebagai "wildcard" -- tidak bisa di-classify tanpa parse styles
            if style_val:
                return "CUSTOM_STYLE"

    if borders is None:
        return "NO_BORDERS"

    sides = {}
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(_qn(f"w:{side}"))
        if el is not None:
            val = el.get(_qn("w:val")) or "none"
            sides[side] = val not in ("none", "nil")
        else:
            sides[side] = None  # absent (inherit from style)

    visible_sides = {k: v for k, v in sides.items() if v is True}
    invisible_sides = {k: v for k, v in sides.items() if v is False}

    # Tidak ada side yang visible
    if not visible_sides:
        return "INVISIBLE"

    has_top = sides.get("top") is True
    has_bottom = sides.get("bottom") is True
    has_left = sides.get("left") is True
    has_right = sides.get("right") is True
    has_insideH = sides.get("insideH") is True
    has_insideV = sides.get("insideV") is True

    if has_top and has_bottom and has_left and has_right and has_insideH and has_insideV:
        return "FULL_GRID"
    if has_top and has_bottom and not has_left and not has_right and not has_insideV:
        return "HORIZONTAL_ONLY"
    if has_top and not has_bottom and not has_left and not has_right:
        return "TOP_ONLY"
    if has_bottom and not has_top and not has_left and not has_right:
        return "BOTTOM_ONLY"
    return "PARTIAL"


def _get_template_patterns(doc) -> set[str]:
    """Dapatkan SEMUA pattern border yang muncul di doc.

    Hanya hitung tabel data (rows>=2, cols>=2, ada header text).
    Return set kosong kalau tidak ada tabel data.

    Beda dari _get_dominant_pattern: ini return semua variant sehingga output
    pattern bisa di-validate terhadap "set sah" template (bukan hanya dominant).
    """
    patterns = set()
    for t in doc.tables:
        rows = len(t.rows)
        cols = len(t.rows[0].cells) if rows > 0 else 0
        if rows < 2 or cols < 2:
            continue
        header_text = "".join((c.text or "").strip() for c in t.rows[0].cells)
        if not header_text:
            continue
        patterns.add(_classify_border_pattern(t))
    return patterns


def _get_dominant_pattern(doc) -> str | None:
    """Dapatkan pattern border yang paling sering muncul di doc.

    Hanya hitung tabel data (rows>=2, cols>=2, ada header text).
    Return None kalau tidak ada tabel data.
    """
    from collections import Counter
    patterns = []
    for t in doc.tables:
        rows = len(t.rows)
        cols = len(t.rows[0].cells) if rows > 0 else 0
        if rows < 2 or cols < 2:
            continue
        header_text = "".join((c.text or "").strip() for c in t.rows[0].cells)
        if not header_text:
            continue
        patterns.append(_classify_border_pattern(t))
    if not patterns:
        return None
    counter = Counter(patterns)
    return counter.most_common(1)[0][0]


def _get_all_table_patterns(doc) -> set[str]:
    """Get ALL table patterns including layout tables (no header filter).

    Berbeda dengan _get_template_patterns yang skip layout table (rows<2 atau
    no-header). Ini ambil semua untuk fallback ketika template tidak punya
    data tables. Useful sebagai reference style template "spirit".
    """
    patterns = set()
    for t in doc.tables:
        rows = len(t.rows)
        if rows < 1:
            continue
        cols = len(t.rows[0].cells) if rows > 0 else 0
        if cols < 1:
            continue
        patterns.add(_classify_border_pattern(t))
    return patterns


# =============================================================================
# Helper: baca expected table border style dari gen.py CFG
# =============================================================================
# Map gen.py config "table_borders" values ke border pattern
_GEN_BORDER_MAP = {
    "all": "FULL_GRID",
    "full": "FULL_GRID",
    "three_line": "HORIZONTAL_ONLY",
    "three_line_double_top": "HORIZONTAL_DOUBLE",
    "top_bottom": "TOP_BOTTOM",
    "none": "NO_BORDERS",
}


def _get_expected_border_from_gen_config(doc_orig_path: str) -> str | None:
    """Baca table_borders config dari *gen.py file corresponding ke template.

    Args:
        doc_orig_path: path ke original template .docx file

    Returns:
        Expected border pattern string, atau None jika tidak bisa dideteksi.
    """
    import os, re
    tmpl_dir = os.path.dirname(doc_orig_path)
    tmpl_name = os.path.splitext(os.path.basename(doc_orig_path))[0]
    gen_path = os.path.join(tmpl_dir, f"{tmpl_name}gen.py")
    if not os.path.isfile(gen_path):
        return None
    try:
        with open(gen_path, "r", encoding="utf-8") as f:
            gen_code = f.read()
        m = re.search(r'"table_borders"\s*:\s*"([^"]*)"', gen_code)
        if m:
            cfg_val = m.group(1)
            return _GEN_BORDER_MAP.get(cfg_val, cfg_val.upper())
    except Exception:
        pass
    return None


def audit_table_borders(doc_out, doc_orig=None, template_path=None) -> AuditResult:
    """Cek apakah tabel data di output punya border tegas/keliatan DAN match
    dengan pattern template original.

    Heuristic tabel data: rows>=2 AND cols>=2 AND ada text di header row.
    Border 'tidak tegas' = tblBorders absent ATAU semua side val='none'/'nil'.
    Border 'tipis' = ada border tapi sz < 4 (kurang dari 0.5pt, sulit dilihat).
    Border 'mismatch' = pattern output beda dengan dominant pattern di template
                       (mis. template academic style tapi output full grid).

    Returns:
        AuditResult dengan info:
        - invisible_count: tabel tanpa border sama sekali
        - thin_count: tabel dengan border terlalu tipis (sz < 4)
        - mismatch_count: tabel dengan pattern beda dari template
        - orig_pattern: dominant pattern di template (kalau doc_orig disediakan)
    """
    from docx.oxml.ns import qn as _qn
    res = AuditResult()
    invisible_tables = []
    thin_tables = []
    mismatch_tables = []

    # Detect dominant pattern + ALL valid patterns di template original
    orig_pattern = _get_dominant_pattern(doc_orig) if doc_orig is not None else None
    orig_patterns = _get_template_patterns(doc_orig) if doc_orig is not None else set()

    # Fallback: kalau template tidak punya data tables (orig_patterns kosong),
    # ambil pattern dari SEMUA tables di template (termasuk layout tables) sebagai
    # heuristik "spirit" template. Ini handle case template yang isinya layout-only.
    no_data_table_in_orig = False
    fallback_patterns: set[str] = set()
    if doc_orig is not None and not orig_patterns:
        no_data_table_in_orig = True
        fallback_patterns = _get_all_table_patterns(doc_orig)

    for i, t in enumerate(doc_out.tables):
        rows = len(t.rows)
        cols = len(t.rows[0].cells) if rows > 0 else 0
        if rows < 2 or cols < 2:
            continue
        header_text = "".join((c.text or "").strip() for c in t.rows[0].cells)
        if not header_text:
            continue

        out_pattern = _classify_border_pattern(t)

        # Cek invisible
        if out_pattern in ("INVISIBLE", "NO_BORDERS"):
            # STRICT RULE: Data tables (rows>=2, cols>=2, has header) MUST have visible borders
            # for readability, regardless of whether template original has data tables or not.
            # Template original may only have layout tables (1-row containers), but output
            # data tables still need borders.
            # Exception: Allow NO_BORDERS/INVISIBLE if template has NO_BORDERS or INVISIBLE pattern.
            # NO_BORDERS and INVISIBLE are visually equivalent (no visible borders).
            template_allows_no_border = (
                orig_pattern in ("NO_BORDERS", "INVISIBLE") or
                "NO_BORDERS" in orig_patterns or "INVISIBLE" in orig_patterns or
                "NO_BORDERS" in fallback_patterns or "INVISIBLE" in fallback_patterns
            )
            if not template_allows_no_border:
                # Template doesn't allow no-border, so output with no-border is problematic
                invisible_tables.append({"index": i, "rows": rows, "cols": cols})
            # else: template allows no-border, so output with no-border is OK (pass)
            continue

        # Cek thin
        tblPr = t._element.find(_qn("w:tblPr"))
        borders = tblPr.find(_qn("w:tblBorders")) if tblPr is not None else None
        min_sz = float('inf')
        if borders is not None:
            for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                el = borders.find(_qn(f"w:{side}"))
                if el is not None:
                    val = el.get(_qn("w:val")) or "none"
                    if val not in ("none", "nil"):
                        sz_str = el.get(_qn("w:sz"))
                        if sz_str:
                            try:
                                sz = int(sz_str)
                                min_sz = min(min_sz, sz)
                            except (ValueError, TypeError):
                                pass
        if min_sz < 4:
            thin_tables.append({"index": i, "rows": rows, "cols": cols, "min_sz": min_sz})

        # Cek mismatch: output pattern tidak ada di set pattern template original
        # Kalau template TIDAK punya pattern ini sama sekali, berarti output bikin
        # style yang tidak konsisten dengan template (mis. full grid vs academic).
        # CUSTOM_STYLE adalah wildcard - render-nya tergantung styles.xml, anggap
        # any output pattern OK kalau template (atau output) pakai custom style.
        # NO_BORDERS dan INVISIBLE secara visual sama (tidak ada border), treat compatible.
        NO_BORDER_GROUP = {"NO_BORDERS", "INVISIBLE"}
        out_in_no_border = out_pattern in NO_BORDER_GROUP
        orig_has_no_border = bool(orig_patterns & NO_BORDER_GROUP)

        # Pilih reference patterns: orig_patterns kalau ada, atau fallback_patterns
        # (dari layout tables) kalau template tidak punya data tables sama sekali.
        ref_patterns = orig_patterns if orig_patterns else fallback_patterns

        if "CUSTOM_STYLE" in ref_patterns or out_pattern == "CUSTOM_STYLE":
            pass  # Skip mismatch check - custom style render-nya unknown tanpa parse styles
        elif out_in_no_border and (orig_has_no_border or "NO_BORDERS" in fallback_patterns):
            pass  # Keduanya no-border-group, visually compatible
        elif (no_data_table_in_orig or orig_has_no_border) and out_pattern not in NO_BORDER_GROUP:
            # Template tidak punya data tables, tapi output punya visible borders.
            # Cek gen.py config untuk expected border style.
            gen_expected = None
            if template_path is not None:
                gen_expected = _get_expected_border_from_gen_config(str(template_path))
            if gen_expected and out_pattern != gen_expected:
                # Gen config expects different pattern (e.g. HORIZONTAL_ONLY)
                # but output uses something else (e.g. FULL_GRID) → MISMATCH
                mismatch_tables.append({
                    "index": i, "rows": rows, "cols": cols,
                    "out_pattern": out_pattern,
                    "orig_patterns": [gen_expected],
                    "orig_dominant": gen_expected,
                    "from_gen_config": True,
                })
            # else: no gen config or matches expected → OK (pass)
        elif ref_patterns and out_pattern not in ref_patterns:
            mismatch_tables.append({
                "index": i, "rows": rows, "cols": cols,
                "out_pattern": out_pattern,
                "orig_patterns": sorted(ref_patterns),
                "orig_dominant": orig_pattern,
                "from_fallback": no_data_table_in_orig,
            })

    res.info = {
        "total_data_tables": len([
            t for t in doc_out.tables
            if len(t.rows) >= 2 and len(t.rows[0].cells) >= 2
        ]),
        "invisible_count": len(invisible_tables),
        "invisible_indices": [x["index"] for x in invisible_tables],
        "thin_count": len(thin_tables),
        "thin_indices": [x["index"] for x in thin_tables],
        "mismatch_count": len(mismatch_tables),
        "mismatch_details": mismatch_tables,
        "orig_pattern": orig_pattern,
        "no_data_table_in_orig": no_data_table_in_orig,
        "fallback_patterns": sorted(fallback_patterns),
        "gen_expected": _get_expected_border_from_gen_config(str(template_path)) if template_path is not None else None,
    }

    # Add error messages
    for mt in mismatch_tables:
        source = "gen.py config" if mt.get("from_gen_config") else (
            "fallback layout tables" if mt.get("from_fallback") else "template tables"
        )
        res.errors.append(
            f"BORDER MISMATCH: Table {mt['index']} ({mt['rows']}x{mt['cols']}) "
            f"output={mt['out_pattern']}, "
            f"expected={mt['orig_patterns']} (from {source})"
        )
    for inv in invisible_tables:
        res.errors.append(
            f"BORDER MISSING: Table {inv['index']} ({inv['rows']}x{inv['cols']}) "
            f"tidak punya border visible"
        )
    for th in thin_tables:
        res.errors.append(
            f"BORDER THIN: Table {th['index']} ({th['rows']}x{th['cols']}) "
            f"border terlalu tipis (sz={th['min_sz']})"
        )
    return res


# =============================================================================
# [5j] Image Sizing (MAYOR -10 per image di luar range lebar kolom)
# =============================================================================
# Deteksi gambar embedded yang dimensinya tidak sesuai template kolom:
# - 1-column: target = 50% lebar area teks (page - margins)
# - 2-column: target = 70% lebar kolom
# Toleransi ±20%. Gambar di luar range → MAYOR -10 per image.

def audit_image_sizing(doc_out, doc_orig=None) -> AuditResult:
    """Cek dimensi gambar embedded vs target lebar kolom template.
    
    Skip decorative/template images (logo, header graphics) — only flags
    content images (figures from JSON data).
    """
    from docx.oxml.ns import qn
    import re as _re
    res = AuditResult()
    
    # Get template decorative rIds
    decorative_rids = set()
    if doc_orig is not None:
        decorative_rids = _get_template_decorative_rids(doc_orig)
    
    # Get page layout info
    try:
        section = doc_out.sections[0]
        page_w_emu = section.page_width
        margin_l = section.left_margin
        margin_r = section.right_margin
    except Exception:
        res.info = {"error": "Cannot read section properties"}
        return res
    
    page_w_cm = page_w_emu / 360000
    margin_l_cm = margin_l / 360000
    margin_r_cm = margin_r / 360000
    text_w_cm = page_w_cm - margin_l_cm - margin_r_cm
    
    try:
        sect_pr = doc_out._element.body.find(qn('w:sectPr'))
        cols_elem = sect_pr.find(qn('w:cols')) if sect_pr is not None else None
        num_cols = int(cols_elem.get(qn('w:num'), '1')) if cols_elem is not None else 1
    except Exception:
        num_cols = 1
    
    if num_cols > 1:
        target_cm = (text_w_cm / num_cols) * 0.70
        layout_type = "2-col"
    else:
        target_cm = text_w_cm * 0.50
        layout_type = "1-col"
    
    tolerance = 0.20
    min_cm = target_cm * (1 - tolerance)
    max_cm = target_cm * (1 + tolerance)
    
    images = []
    for shape in doc_out.inline_shapes:
        try:
            # Skip decorative images
            drawing_elem = shape._inline.getparent()
            if drawing_elem is not None:
                blip = drawing_elem.find(".//{%s}blip" % "http://schemas.openxmlformats.org/drawingml/2006/main")
                if blip is not None:
                    rid = blip.get("{%s}embed" % "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
                    if rid and rid in decorative_rids:
                        continue
            
            width_emu = shape.width
            width_cm = width_emu / 360000
            
            if width_cm < min_cm or width_cm > max_cm:
                images.append({
                    "width_cm": round(width_cm, 1),
                    "target_cm": round(target_cm, 1),
                    "layout": layout_type,
                })
        except Exception:
            continue
    
    for img in images:
        res.errors.append(
            "UKURAN GAMBAR: %s layout - gambar %.1fcm (target %.1fcm, range %.1f-%.1fcm)" % (
                img['layout'], img['width_cm'], img['target_cm'], min_cm, max_cm
            )
        )
    
    res.info = {
        "total_images": len(doc_out.inline_shapes),
        "decorative_skip": len(decorative_rids),
        "mismatch_count": len(images),
        "oversize_count": sum(1 for img in images if img["width_cm"] > target_cm),
        "target_cm": round(target_cm, 1),
        "layout": layout_type,
        "text_w_cm": round(text_w_cm, 1),
        "num_cols": num_cols,
    }
    return res


def audit_paragraph_spacing(doc_out, doc_orig=None) -> AuditResult:
    """Cek space_before dan space_after antar paragraf body text.

    Bandingkan output vs template. Jika beda > 5pt per paragraf: flag.
    Body text = paragraf non-empty dengan style Normal/Body/jurnal text.
    """
    res = AuditResult()
    TOLERANCE_PT = 5.0  # toleransi 5pt
    TOL_EMU = int(TOLERANCE_PT * 6350)  # 1pt = 6350 EMU
    MAX_CHECK = 50  # max paragraf body yang dicek

    # Kumpulkan body text paragraphs dari output
    out_body_paras = [
        p for p in doc_out.paragraphs
        if p.text.strip() and not p.style.name.startswith("Heading")
    ][:MAX_CHECK]

    # Kumpulkan body text paragraphs dari template (reference)
    orig_body_paras = []
    if doc_orig is not None:
        orig_body_paras = [
            p for p in doc_orig.paragraphs
            if p.text.strip() and not p.style.name.startswith("Heading")
        ][:MAX_CHECK]

    def _get_spacing(para):
        """Return (before_emu, after_emu) — None jika tidak di-set."""
        pf = para.paragraph_format
        before = pf.space_before  # Emu or None
        after = pf.space_after    # Emu or None
        return before, after

    def _emu_to_pt(emu):
        if emu is None:
            return 0.0
        return round(emu / 12700, 1)

    violations = []

    if orig_body_paras:
        # Mode: bandingkan output vs template
        for i, out_para in enumerate(out_body_paras):
            if i >= len(orig_body_paras):
                break
            # Skip paragraf pendek (< 30 chars) — spacing-nya sering legitimate
            if len(out_para.text.strip()) < 30:
                continue
            orig_para = orig_body_paras[i]

            out_before, out_after = _get_spacing(out_para)
            orig_before, orig_after = _get_spacing(orig_para)

            # Hitung delta (None = 0)
            ob = out_before or 0
            oa = out_after or 0
            rb = orig_before or 0
            ra = orig_after or 0

            delta_before = abs(ob - rb)
            delta_after = abs(oa - ra)

            if delta_before > TOL_EMU or delta_after > TOL_EMU:
                violations.append({
                    "para_index": i,
                    "out_before_pt": _emu_to_pt(out_before),
                    "out_after_pt": _emu_to_pt(out_after),
                    "orig_before_pt": _emu_to_pt(orig_before),
                    "orig_after_pt": _emu_to_pt(orig_after),
                    "delta_before_pt": round(delta_before / 12700, 1),
                    "delta_after_pt": round(delta_after / 12700, 1),
                    "snippet": out_para.text.strip()[:60],
                    "style": out_para.style.name,
                })
    else:
        # Mode: hanya output, cek paragraf body tanpa spacing (before=0, after=0)
        for i, para in enumerate(out_body_paras):
            # Skip paragraf pendek (< 30 chars) — spacing-nya sering legitimate
            if len(para.text.strip()) < 30:
                continue
            before, after = _get_spacing(para)
            if (before is None or before == 0) and (after is None or after == 0):
                violations.append({
                    "para_index": i,
                    "out_before_pt": 0.0,
                    "out_after_pt": 0.0,
                    "orig_before_pt": None,
                    "orig_after_pt": None,
                    "delta_before_pt": None,
                    "delta_after_pt": None,
                    "snippet": para.text.strip()[:60],
                    "style": para.style.name,
                })

    for v in violations:
        if v["delta_before_pt"] is not None:
            msg = (
                f"PARA SPACING MISMATCH #{v['para_index']} [{v['style']}]: "
                f"before={v['out_before_pt']}pt (orig={v['orig_before_pt']}pt, "
                f"delta={v['delta_before_pt']}pt) "
                f"after={v['out_after_pt']}pt (orig={v['orig_after_pt']}pt, "
                f"delta={v['delta_after_pt']}pt) "
                f"— \"{v['snippet']}\""
            )
        else:
            msg = (
                f"PARA SPACING MISSING #{v['para_index']} [{v['style']}]: "
                f"no space_before/space_after set — \"{v['snippet']}\""
            )
        res.errors.append(msg)

    res.info = {
        "checked": len(out_body_paras),
        "violations": len(violations),
        "details": violations[:10],  # max 10 for report
    }
    return res


def audit_element_spacing(doc_out) -> AuditResult:
    """Cek konsistensi spacing before/after figure dan table caption.
    
    Hanya flag caption asli (Fig. N / Table N) dengan before=0pt atau >24pt.
    Deskripsi body text seperti "Gambar 1 menunjukkan..." tidak diflag.
    """
    import re
    res = AuditResult()
    violations = []
    
    # Pattern untuk caption asli: Fig. N, Figure N, Table N/I/1
    FIG_CAPTION_RE = re.compile(r"^(?:Fig\.|Figure)\s+\d+", re.IGNORECASE)
    TBL_CAPTION_RE = re.compile(r"^(?:Table|Tabel)\s+[IVXLCDM\d]", re.IGNORECASE)
    
    for i, para in enumerate(doc_out.paragraphs):
        text = para.text.strip() if para.text else ""
        if not text:
            continue
        
        is_fig = bool(FIG_CAPTION_RE.match(text))
        is_tbl = bool(TBL_CAPTION_RE.match(text))
        
        if not (is_fig or is_tbl):
            continue
        
        pf = para.paragraph_format
        try:
            before_pt = pf.space_before / 12700 if pf.space_before else 0
            after_pt = pf.space_after / 12700 if pf.space_after else 0
        except Exception:
            continue
        
        # Only flag extreme spacing: zero (missing) or excessive (>24pt)
        if before_pt == 0 or before_pt > 24:
            elem_type = "Figure" if is_fig else "Table"
            violations.append({
                "index": i, "type": elem_type,
                "before_pt": round(before_pt, 1),
                "after_pt": round(after_pt, 1),
                "snippet": text[:60],
            })
    
    for v in violations:
        msg = "SPACING: {} caption #{} before={}pt (expected 3-24pt) - {}".format(
            v['type'], v['index'], v['before_pt'], v['snippet'][:60]
        )
        res.errors.append(msg)
    
    res.info = {"violations": len(violations), "details": violations}
    return res
def audit_formula_omml(doc_out) -> AuditResult:
    """Deteksi formula OMML yang kosong atau rusak."""
    from docx.oxml.ns import qn
    res = AuditResult()
    empty_count = 0
    total_checked = 0
    
    M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    
    for i, para in enumerate(doc_out._element.body):
        p_tag = para.tag.split("}")[-1] if "}" in para.tag else para.tag
        if p_tag != "p":
            continue
        
        omaths = para.findall("{%s}oMath" % M_NS) + para.findall("{%s}oMathPara" % M_NS)
        for om in omaths:
            total_checked += 1
            math_text = "".join(om.itertext()).strip()
            if not math_text and len(math_text.strip()) == 0:
                empty_count += 1
                res.errors.append(
                    "FORMULA KOSONG: Paragraf #%d - OMML tanpa konten matematika valid" % i
                )
    
    res.info = {"empty_count": empty_count, "total_checked": total_checked}
    return res


# =============================================================================
# [5m] Table Width (MAYOR -10 per tabel yang melebihi lebar kolom)
# =============================================================================
# 1-col: 50% text area | 2-col: 70% column width


def audit_table_width(doc_out, doc_orig=None):
    """Deteksi tabel terlalu lebar vs lebar kolom (overflow hazard seperti pada gambar)."""
    res = AuditResult(errors=[], info={})
    from docx.oxml.ns import qn as _qn

    body = doc_out._element.body
    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    sect_prs = body.findall("{%s}sectPr" % W_NS)
    tbls = body.findall("{%s}tbl" % W_NS)

    if not sect_prs:
        return res

    # Get page geometry from first sectPr
    first_sp = sect_prs[0]
    pgSz = first_sp.find("{%s}pgSz" % W_NS)
    pgMar = first_sp.find("{%s}pgMar" % W_NS)
    pw = int(pgSz.get("{%s}w" % W_NS, '11906')) if pgSz is not None else 11906
    ml = int(pgMar.get("{%s}left" % W_NS, '1440')) if pgMar is not None else 1440
    mr = int(pgMar.get("{%s}right" % W_NS, '1440')) if pgMar is not None else 1440
    text_w_cm = (pw - ml - mr) / 567.0

    # Collect section column layouts
    section_cols = []
    for sp in sect_prs:
        cols_elem = sp.find("{%s}cols" % W_NS)
        num = 1
        if cols_elem is not None:
            num_attr = cols_elem.get("{%s}num" % W_NS)
            if num_attr is not None:
                num = int(num_attr)
        section_cols.append(num)

    # Walk body, track section
    section_idx = 0
    mismatches = []

    for child in body:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

        if tag == 'sectPr':
            section_idx = min(section_idx + 1, len(section_cols) - 1)
            continue

        if tag != 'tbl':
            continue

        cols = section_cols[section_idx] if section_idx < len(section_cols) else 1
        if cols <= 0:
            cols = 1

        col_w_cm = text_w_cm / cols if cols > 1 else text_w_cm

        # Get table width from tblPr/tblW
        tbl_pr = child.find("{%s}tblPr" % W_NS)
        if tbl_pr is None:
            continue

        tbl_w = tbl_pr.find("{%s}tblW" % W_NS)
        w_type = tbl_w.get("{%s}type" % W_NS, 'auto') if tbl_w is not None else 'auto'
        w_val = tbl_w.get("{%s}w" % W_NS, '0') if tbl_w is not None else '0'

        if w_type == 'dxa':
            actual_cm = float(w_val) / 567.0
        elif w_type == 'pct':
            actual_cm = (float(w_val) / 5000.0) * text_w_cm
        else:
            # auto width — designed to fill column, NOT overflow
            # Skip: auto-width tables correctly fit the column
            continue

        # Target: tabel harus fit dalam kolom (100%), bukan 70% seperti gambar
        target_cm = col_w_cm  # 100% column width (table fills column)
        layout = "2-col" if cols == 2 else "1-col"

        # Flag if > 120% of target (generous tolerance for fixed-width tables)
        if actual_cm > target_cm * 1.20:
            mismatches.append({
                "actual_cm": round(actual_cm, 1),
                "target_cm": round(target_cm, 1),
                "col_w_cm": round(col_w_cm, 1),
                "layout": layout,
            })

    for mm in mismatches:
        res.errors.append(
            "Tabel overflow: %.1fcm > target %.1fcm (kolom %.1fcm, %s)" % (
                mm['actual_cm'], mm['target_cm'], mm['col_w_cm'], mm['layout']
            )
        )

    res.info["table_count"] = len(tbls)
    res.info["mismatch_count"] = len(mismatches)
    res.info["target_cm"] = [round(text_w_cm / max(c, 1) * (0.7 if c > 1 else 0.5), 1) for c in section_cols]

    return res


# =============================================================================
# [5o2] First Line Indent (MINOR -2 per paragraf body dengan indent tidak sesuai)
# =============================================================================


def audit_first_line_indent(doc_out, doc_orig=None):
    """Deteksi paragraf body text dengan first_line_indent yang tidak sesuai template.

    Skip heading dan caption. Bandingkan first_line_indent output vs template.
    Toleransi: 0.3 cm.

    Parameters
    ----------
    doc_out : Document
        Dokumen output yang diaudit.
    doc_orig : Document, optional
        Dokumen original (template) — untuk perbandingan indent.

    Returns
    -------
    AuditResult
        errors: daftar pesan per paragraf dengan indent tidak sesuai.
        info: {checked, mismatch_count, expected_cm}
    """
    res = AuditResult(errors=[], info={})

    # --- Collect template indent values (first_line_indent in cm) for body paragraphs ---
    # Only collect positive indents (>0.05cm) to find the body-text indent mode.
    # Skips zero-indent headings, negative-indent references, and DOI lines.
    template_indents = []
    if doc_orig is not None:
        for para in doc_orig.paragraphs:
            style_name = (para.style.name or "").lower()
            text = para.text.strip()
            if not text:
                continue
            if "heading" in style_name or "judul" in style_name:
                continue
            if text.startswith(("Table ", "Tabel ", "TABLE ", "Figure ", "Gambar ", "FIGURE ")):
                continue
            # Skip DOI / reference lines (often have hanging/negative indents)
            if "dx.doi.org" in text or "doi.org" in text:
                continue
            indent_emu = para.paragraph_format.first_line_indent
            if indent_emu is not None:
                cm_val = indent_emu / 360000.0
                if cm_val > 0.05:  # only positive body-text indents
                    template_indents.append(cm_val)

    # Determine expected indent from template — mode (most frequent) of positive indents
    expected_cm = None
    if template_indents:
        from collections import Counter
        counter = Counter(round(v, 2) for v in template_indents)
        expected_cm = counter.most_common(1)[0][0]

    checked = 0
    mismatch = 0
    tolerance_cm = 0.3

    for i, para in enumerate(doc_out.paragraphs):
        style_name = (para.style.name or "").lower()
        text = para.text.strip()
        if not text:
            continue
        if "heading" in style_name or "judul" in style_name:
            continue
        if text.startswith(("Table ", "Tabel ", "TABLE ", "Figure ", "Gambar ", "FIGURE ", "Fig. ", "FIG. ")):
            continue
        # Skip all-caps short text (likely section headings)
        if text.isupper() and len(text) < 80:
            continue
        # Skip reference entries (often have hanging/negative indents)
        if text.startswith("[") or "et al" in text.lower() or text.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
            continue
        # Skip title-case short text (likely section headings with Normal style)
        import re
        words = text.split()
        if len(words) >= 2 and all(w[0].isupper() or w[0].isdigit() for w in words if len(w) > 1) and len(text) < 100:
            continue
        if len(text) < 20:
            continue

        checked += 1
        indent_emu = para.paragraph_format.first_line_indent

        if expected_cm is not None:
            actual_cm = (indent_emu / 360000.0) if indent_emu is not None else 0.0
            diff = abs(actual_cm - expected_cm)
            if diff > tolerance_cm:
                mismatch += 1
                res.errors.append(
                    f"Paragraf #{i}: first_line_indent={actual_cm:.2f}cm, "
                    f"expected={expected_cm:.2f}cm (diff={diff:.2f}cm)"
                )

    res.info["checked"] = checked
    res.info["mismatch_count"] = mismatch
    res.info["expected_cm"] = expected_cm
    return res


# =============================================================================
# [5n] Table Spacing (MINOR -3 per caption tabel dengan spacing terlalu rapat)
# =============================================================================


def audit_table_spacing(doc_out, doc_orig=None):
    """Deteksi spacing caption tabel yang terlalu rapat (before_pt < 3)."""
    res = AuditResult(errors=[], info={})

    for i, para in enumerate(doc_out.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        # Check for table captions: starts with "Table " or "Tabel "
        if not (text.startswith("Table ") or text.startswith("Tabel ") or text.startswith("TABLE ")):
            continue

        pf = para.paragraph_format
        before_pt = (pf.space_before or 0) / 12700.0
        after_pt = (pf.space_after or 0) / 12700.0

        if before_pt < 3 and before_pt >= 0:
            res.errors.append(
                "Spacing caption tabel #%d terlalu rapat: %.0fpt before (min 3pt)" % (i, before_pt)
            )

    caption_count = sum(1 for p in doc_out.paragraphs
                        if p.text.strip().startswith(("Table ", "Tabel ", "TABLE ")))
    res.info["table_caption_count"] = caption_count

    # Also check: text paragraph immediately AFTER a table should have spacing
    # Walk body elements to find table→paragraph boundaries
    body = doc_out._element.body
    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    elements = list(body)
    for idx, child in enumerate(elements):
        if 'tbl' not in child.tag:
            continue
        # Find next paragraph after this table
        for j in range(idx + 1, len(elements)):
            next_child = elements[j]
            if 'p' in next_child.tag:
                ppr = next_child.find("{%s}pPr" % W_NS)
                if ppr is not None:
                    spacing = ppr.find("{%s}spacing" % W_NS)
                    if spacing is not None:
                        before_dxa = int(spacing.get("{%s}before" % W_NS, '0'))
                        before_pt = before_dxa / 20.0
                        text_preview = ''.join(next_child.itertext()).strip()[:40]
                        if before_pt < 3:
                            res.errors.append(
                                'Teks setelah tabel spacing terlalu rapat: %.0fpt before (min 3pt) - "%s..."' % (before_pt, text_preview)
                            )
                break

    return res



# =============================================================================
# [5o] Figure Caption Style (MINOR -3 per caption dengan style mismatch)
# =============================================================================
# Aturan: label ("Fig." / "Figure" / "Gambar" + nomor) harus bold,
# sisanya (teks deskripsi) harus normal (non-bold).
# Jika doc_orig diberikan, bandingkan juga format output vs template.


def audit_figure_caption_style(doc_out, doc_orig=None):
    """Cek style figure caption: label bold, teks deskripsi normal.

    Label = prefix "Fig." / "Figure" / "Gambar" (opsional spasi + nomor + titik/titik-dua).
    Mismatch = label tidak bold ATAU deskripsi malah bold (kecuali seluruh caption 1 run).
    Jika doc_orig disediakan, bandingkan pola bold output vs template per caption.
    """
    import re as _re

    res = AuditResult(errors=[], info={})

    _FIG_LABEL_RE = _re.compile(
        r'^(Fig\.|Figure|Gambar)\s*\d*[\.:;]?\s*', _re.IGNORECASE
    )

    def _collect_caption_paras(doc):
        """Return list of (para_index, paragraph) yang text-nya start dgn figure label."""
        result = []
        for idx, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if not text:
                continue
            if _FIG_LABEL_RE.match(text):
                result.append((idx, para))
        return result

    def _check_caption_style(para):
        """Cek 1 caption paragraph. Return (label_bold_ok, desc_bold_ok, label_text, detail)."""
        text = para.text
        m = _FIG_LABEL_RE.match(text.strip())
        if not m:
            return True, True, "", ""

        label_text = m.group(0)
        label_end_pos = len(label_text)

        # Build list of (start, end, bold) per run
        runs_info = []
        pos = 0
        for run in para.runs:
            rlen = len(run.text)
            bold = bool(run.bold)
            runs_info.append((pos, pos + rlen, bold))
            pos += rlen

        if not runs_info:
            return True, True, label_text, "no runs"

        # Check label region (0 .. label_end_pos): should have at least one bold run
        label_has_bold = False
        label_has_nonbold = False
        desc_has_bold = False

        for (start, end, bold) in runs_info:
            # Determine overlap with label region
            if start < label_end_pos:
                if bold:
                    label_has_bold = True
                else:
                    label_has_nonbold = True
            # Determine overlap with description region
            if end > label_end_pos:
                if bold:
                    desc_has_bold = True

        label_bold_ok = label_has_bold  # label region must contain bold
        desc_bold_ok = not desc_has_bold  # description should NOT be bold

        detail_parts = []
        if not label_bold_ok:
            detail_parts.append("label not bold")
        if not desc_bold_ok:
            detail_parts.append("description has bold")

        return label_bold_ok, desc_bold_ok, label_text.strip(), "; ".join(detail_parts)

    # --- Scan output ---
    out_captions = _collect_caption_paras(doc_out)
    res.info["caption_count"] = len(out_captions)

    # --- Early exit: template has no figure captions → can't compare ---
    if doc_orig is not None:
        orig_captions = _collect_caption_paras(doc_orig)
        if not orig_captions:
            res.info["skipped"] = "template has no figure captions"
            return res

    mismatches = 0

    for idx, para in out_captions:
        lbl_ok, desc_ok, label_text, detail = _check_caption_style(para)
        if not lbl_ok or not desc_ok:
            mismatches += 1
            snippet = para.text.strip()[:80]
            res.errors.append(
                "Figure caption style mismatch (para #%d): %s -- \"%s\""
                % (idx, detail, snippet)
            )

    # --- Cross-check vs template ---
    if doc_orig is not None:
        res.info["orig_caption_count"] = len(orig_captions)

        # Compare per-caption bold pattern between output and template
        for i, ((orig_idx, orig_para), (out_idx, out_para)) in enumerate(
            zip(orig_captions, out_captions)
        ):
            orig_bold_runs = [bool(r.bold) for r in orig_para.runs]
            out_bold_runs = [bool(r.bold) for r in out_para.runs]
            if orig_bold_runs != out_bold_runs:
                mismatches += 1
                res.errors.append(
                    "Figure caption #%d bold pattern mismatch: "
                    "template=%s output=%s"
                    % (i, orig_bold_runs[:5], out_bold_runs[:5])
                )

    res.info["mismatches"] = mismatches
    return res



# =============================================================================
# [5p] Formula OMML Width (MAYOR -10 per formula overflow kolom)
# =============================================================================
# 1-col: 50% text area | 2-col: 70% column width
# Estimasi lebar: char_count * font_size_pt * 0.55 / 28.35 (cm)
# Toleransi: ±15% dari target


def audit_formula_width(doc_out, doc_orig=None):
    """Deteksi formula OMML yang overflow dari kolom (seperti gambar)."""
    res = AuditResult(errors=[], info={})
    from docx.oxml.ns import qn as _qn

    body = doc_out._element.body
    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

    sect_prs = body.findall("{%s}sectPr" % W_NS)
    if not sect_prs:
        return res

    # Get page geometry
    first_sp = sect_prs[0]
    pgSz = first_sp.find("{%s}pgSz" % W_NS)
    pgMar = first_sp.find("{%s}pgMar" % W_NS)
    pw = int(pgSz.get("{%s}w" % W_NS, '11906')) if pgSz is not None else 11906
    ml = int(pgMar.get("{%s}left" % W_NS, '1440')) if pgMar is not None else 1440
    mr = int(pgMar.get("{%s}right" % W_NS, '1440')) if pgMar is not None else 1440
    text_w_cm = (pw - ml - mr) / 567.0

    # Section column layouts
    section_cols = []
    for sp in sect_prs:
        cols_elem = sp.find("{%s}cols" % W_NS)
        num = 1
        if cols_elem is not None:
            num_attr = cols_elem.get("{%s}num" % W_NS)
            if num_attr is not None:
                num = int(num_attr)
        section_cols.append(num)

    # Walk body elements to determine which section each formula belongs to
    section_idx = 0
    formulas = []  # (section_idx, element, text, len)

    for child in body:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

        if tag == 'sectPr':
            section_idx = min(section_idx + 1, len(section_cols) - 1)
            continue

        # Find OMML formulas inside paragraphs
        if tag == 'p':
            omath_list = child.findall(".//{%s}oMath" % M_NS)
            omathpara_list = child.findall(".//{%s}oMathPara" % M_NS)
            for f_elem in omath_list + omathpara_list:
                # Get font size: check run rPr first, fallback to paragraph rPr
                r_elems = f_elem.findall(".//{%s}r" % M_NS)
                sz_pt = None
                for re in r_elems:
                    rPr = re.find("{%s}rPr" % W_NS)
                    if rPr is not None:
                        sz = rPr.find("{%s}sz" % W_NS)
                        if sz is not None:
                            sz_pt = int(sz.get("{%s}val" % W_NS, '20')) / 2.0
                            break  # use first run's size

                # Fallback: paragraph-level default rPr
                if sz_pt is None:
                    para_rPr = child.find("{%s}pPr/{%s}rPr" % (W_NS, W_NS))
                    if para_rPr is not None:
                        sz = para_rPr.find("{%s}sz" % W_NS)
                        if sz is not None:
                            sz_pt = int(sz.get("{%s}val" % W_NS, '20')) / 2.0

                # Final fallback
                if sz_pt is None:
                    sz_pt = 10.0

                # Count chars
                t_elems = f_elem.findall(".//{%s}t" % M_NS)
                char_count = sum(len(t.text or '') for t in t_elems)

                if char_count > 0:
                    formulas.append((section_idx, f_elem, char_count, sz_pt))

    mismatches = []
    for sec_idx, f_elem, char_count, sz_pt in formulas:
        cols = section_cols[sec_idx] if sec_idx < len(section_cols) else 1
        if cols <= 0:
            cols = 1

        col_w_cm = text_w_cm / cols if cols > 1 else text_w_cm
        target_cm = col_w_cm * 0.90  # 90% column width for 2-col formulas

        # Estimate rendered width
        est_cm = char_count * sz_pt * 0.38 / 28.35

        if est_cm > target_cm * 1.15:
            mismatches.append({
                "est_cm": round(est_cm, 1),
                "target_cm": round(target_cm, 1),
                "cols": cols,
                "chars": char_count,
                "sz_pt": sz_pt,
            })

    for mm in mismatches:
        res.errors.append(
            "Formula overflow: ~%.1fcm > target %.1fcm (%d chars @ %.0fpt, %d-col)" % (
                mm['est_cm'], mm['target_cm'], mm['chars'], mm['sz_pt'], mm['cols']
            )
        )

    res.info["formula_count"] = len(formulas)
    res.info["mismatch_count"] = len(mismatches)

    return res


# =============================================================================
# [5q] Formula Alignment (MINOR -3 per formula paragraph dengan alignment salah)
# =============================================================================
# Formula harus CENTER-aligned; nomor formula (di kanan) harus RIGHT-aligned
# via tab stop. Bandingkan alignment output vs template jika doc_orig tersedia.


def _get_para_alignment(para_elem) -> str | None:
    """Return alignment of a paragraph element as string: 'center', 'left', 'right',
    'both', or None (inherited/default)."""
    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    pPr = para_elem.find("{%s}pPr" % W_NS)
    if pPr is None:
        return None
    jc = pPr.find("{%s}jc" % W_NS)
    if jc is None:
        return None
    return jc.get("{%s}val" % W_NS)


def _has_right_tab_stop(para_elem) -> bool:
    """Check if paragraph has a right-aligned tab stop (used for formula numbers)."""
    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    pPr = para_elem.find("{%s}pPr" % W_NS)
    if pPr is None:
        return False
    tabs = pPr.find("{%s}tabs" % W_NS)
    if tabs is None:
        return False
    for tab in tabs.findall("{%s}tab" % W_NS):
        val = tab.get("{%s}val" % W_NS, "")
        if val in ("right", "end"):
            return True
    return False


def _para_has_omml(para_elem) -> bool:
    """Check if paragraph element contains any OMML formula (oMath or oMathPara)."""
    M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    return (
        bool(para_elem.findall(".//{%s}oMath" % M_NS))
        or bool(para_elem.findall(".//{%s}oMathPara" % M_NS))
    )


def _para_has_formula_number(para_elem) -> bool:
    """Heuristic: formula paragraph has a number if it has oMath AND text outside
    the math zone that looks like a formula number (e.g., (1), (2.3), etc.)."""
    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    # Collect text from runs that are NOT inside oMath
    omath_elements = set(
        id(e) for e in para_elem.findall(".//{%s}oMath" % M_NS)
    )
    omath_elements |= set(
        id(e) for e in para_elem.findall(".//{%s}oMathPara" % M_NS)
    )
    # Check for tab character + number pattern in text outside math zones
    all_text = "".join(para_elem.itertext())
    # Pattern: formula number like (1), (2), (1.3)
    import re as _re
    if _re.search(r'\(\d+\.?\d*\)', all_text):
        return True
    return False


def audit_formula_alignment(doc_out, doc_orig=None) -> AuditResult:
    """Audit alignment of paragraphs containing OMML formulas.

    Rules:
    - Formula paragraphs should be CENTER-aligned
    - If the formula has a number (e.g., (1)), the paragraph should use a
      right-aligned tab stop to push the number to the right margin
    - If doc_orig is provided, compare alignment of corresponding formula
      paragraphs (matched by order) against the template

    Returns AuditResult with:
      info: total_formula_paras, center_violations, tab_violations,
            alignment_mismatches (vs template)
      errors: list of descriptive error strings
    """
    res = AuditResult()
    W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    total_formula_paras = 0
    center_violations = 0
    tab_violations = 0
    alignment_mismatches = 0

    # Collect formula paragraphs from output
    out_formula_paras = []
    body = doc_out._element.body
    para_idx = 0
    for child in body:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag == 'p':
            if _para_has_omml(child):
                alignment = _get_para_alignment(child)
                has_number = _para_has_formula_number(child)
                has_right_tab = _has_right_tab_stop(child)
                out_formula_paras.append({
                    "index": para_idx,
                    "alignment": alignment,
                    "has_number": has_number,
                    "has_right_tab": has_right_tab,
                    "element": child,
                })
            para_idx += 1

    total_formula_paras = len(out_formula_paras)

    # Check alignment rules on output
    for fp in out_formula_paras:
        alignment = fp["alignment"]
        idx = fp["index"]

        # Rule 1: Formula paragraphs should be CENTER-aligned (toleransi 'left')
        if alignment not in ("center", "left"):
            # 'both' (justify) is also wrong for formula
            # None means inherited — could be OK if style default is center,
            # but we flag it as potentially wrong
            center_violations += 1
            snippet_text = "".join(fp["element"].itertext()).strip()[:60]
            res.errors.append(
                f"FORMULA ALIGNMENT: Paragraf #{idx} alignment={alignment!r} "
                f"(expected 'center'). Formula: \"{snippet_text}\""
            )

        # Rule 2: If formula has number, check right tab stop
        if fp["has_number"] and not fp["has_right_tab"]:
            tab_violations += 1
            res.errors.append(
                f"FORMULA NUMBER TAB: Paragraf #{idx} punya nomor formula tapi "
                f"tidak ada right-aligned tab stop — nomor mungkin tidak rata kanan"
            )

    # Compare alignment against template (doc_orig) if available
    if doc_orig is not None:
        orig_formula_paras = []
        orig_body = doc_orig._element.body
        orig_para_idx = 0
        for child in orig_body:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if tag == 'p':
                if _para_has_omml(child):
                    alignment = _get_para_alignment(child)
                    orig_formula_paras.append({
                        "index": orig_para_idx,
                        "alignment": alignment,
                    })
                orig_para_idx += 1

        # Skip audit if template has no OMML formulas
        if orig_formula_paras:
            # Match by order: compare first N pairs
            pairs = min(len(out_formula_paras), len(orig_formula_paras))
            for i in range(pairs):
                orig_align = orig_formula_paras[i]["alignment"]
                out_align = out_formula_paras[i]["alignment"]
                # Only flag if alignment changed AND output is not center
                if orig_align != out_align and out_align != "center":
                    alignment_mismatches += 1
                    res.errors.append(
                        f"FORMULA ALIGNMENT MISMATCH: Formula #{i+1} "
                        f"template={orig_align!r} vs output={out_align!r}"
                    )

    violations = center_violations + tab_violations + alignment_mismatches
    res.info = {
        "total_formula_paras": total_formula_paras,
        "center_violations": center_violations,
        "tab_violations": tab_violations,
        "alignment_mismatches": alignment_mismatches,
        "violations": violations,
    }
    return res


def _normalize_font_name(font_name: str | None) -> str | None:
    """Normalize font names to handle PostScript vs standard names.

    Examples:
    - ArialMT -> Arial
    - TimesNewRomanPSMT -> Times New Roman
    - Calibri-Light -> Calibri
    - Type3 (9 0 R) -> Open Sans (corrupted PDF font reference)
    - NimbusRomNo9L -> NimbusSanL (Nimbus font family variants)
    """
    if not font_name:
        return font_name

    # Font normalization map (PostScript names -> Standard names)
    FONT_NORMALIZE = {
        # Standard PostScript fonts
        "ArialMT": "Arial",
        "Arial-BoldMT": "Arial",
        "Arial-ItalicMT": "Arial",
        "Arial-BoldItalicMT": "Arial",
        "TimesNewRomanPSMT": "Times New Roman",
        "TimesNewRomanPS-BoldMT": "Times New Roman",
        "TimesNewRomanPS-ItalicMT": "Times New Roman",
        "TimesNewRomanPS-BoldItalicMT": "Times New Roman",
        "CourierNewPSMT": "Courier New",
        "CourierNewPS-BoldMT": "Courier New",
        "Calibri-Light": "Calibri",
        "Calibri-Bold": "Calibri",

        # Corrupted PDF font references (from PDF conversion)
        "Type3 (9 0 R)": "Open Sans",
        "Type3 (10 0 R)": "Open Sans",
        "Type3 (11 0 R)": "Open Sans",

        # Nimbus font family (treat Roman and Sans as equivalent for audit purposes)
        # Note: These are actually different fonts (serif vs sans), but templates
        # converted from PDF often have inconsistent font detection
        "NimbusRomNo9L": "NimbusSanL",
        "NimbusRomNo9L-Regu": "NimbusSanL",
        "NimbusRomNo9L-Medi": "NimbusSanL",
    }

    return FONT_NORMALIZE.get(font_name, font_name)


def audit_font_family(doc_orig, doc_out, n_check: int = 10) -> AuditResult:
    """Bandingkan font family di N paragraf pertama (STRICT zone)."""
    res = AuditResult()

    orig_paras = [p for p in doc_orig.paragraphs if p.text.strip()][:n_check * 2]
    out_paras = [p for p in doc_out.paragraphs if p.text.strip()][:n_check * 2]
    pairs = _align_paragraph_pairs(orig_paras, out_paras)[:n_check]

    mismatches: list[dict] = []
    for orig_idx, out_idx in pairs:
        orig_p = orig_paras[orig_idx]
        out_p = out_paras[out_idx]
        if not orig_p.runs or not out_p.runs:
            continue
        orig_fmt = _extract_run_formatting(orig_p.runs[0])
        out_fmt = _extract_run_formatting(out_p.runs[0])

        orig_font = orig_fmt.get("font_name")
        out_font = out_fmt.get("font_name")

        # Normalize font names to handle PostScript vs standard names
        orig_font_normalized = _normalize_font_name(orig_font)
        out_font_normalized = _normalize_font_name(out_font)

        if orig_font_normalized and out_font_normalized and orig_font_normalized != out_font_normalized:
            mismatches.append({
                "para_index": out_idx,
                "orig_font": orig_font,
                "out_font": out_font,
                "snippet": out_p.text[:50],
            })

    if mismatches:
        for m in mismatches[:10]:
            res.errors.append(
                f"FONT FAMILY MISMATCH: Paragraf #{m['para_index']} "
                f"orig='{m['orig_font']}' vs out='{m['out_font']}'. \"{m['snippet']}\""
            )

    res.info = {
        "checked": len(pairs),
        "mismatches": len(mismatches),
    }
    return res


# =============================================================================
# [5f.1b] Full Paragraph Font Audit — ALL paragraphs, per-run comparison
# =============================================================================
# K罗德: teman bilang "font tidak identik" tapi checker lama hanya cek 10 paragraf.
# Audit ini scan SEMUA paragraf, bandingkan per-run font attributes satu-per-satu.
# Greek char detection: template pakai Symbol font untuk αβθμ, output harus sama.
# Penalty: -3 per mismatch (MAJOR zone) / -2 per mismatch (body zone).
#
# FIXED 2026-07-03: sebelumnya hanya cek 10 paragraf pertama (blind spot).
# Root cause mismatch: Greek Unicode chars (α,θ,μ) tidak dilindungi LaTeX
# sehingga lewat add_runs_with_inline() sebagai plain text → font_serif bukan Symbol.

_GREEK_CHAR_SET = frozenset(
    "αβγδεζηθικλμνξοπρστυφχψω"
    "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"
    "ϵϕϱςτωψζξνμλκιθηδγβα"  # variants
)


def _extract_all_run_fonts(para):
    """Extract per-run font info: {run_index: {w:ascii, w:hAnsi, w:cs, w:eastAsia}}."""
    result = []
    for run in para.runs:
        rPr = run._element.find(qn("w:rPr"))
        fonts = {}
        if rPr is not None:
            rFonts = rPr.find(qn("w:rFonts"))
            if rFonts is not None:
                for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                    val = rFonts.get(qn(attr))
                    if val:
                        fonts[attr.split(":")[1]] = val
        result.append({"text": run.text, "fonts": fonts})
    return result


def _has_greek(text: str) -> bool:
    return any(c in _GREEK_CHAR_SET for c in text)


def _run_fonts_match(orig_fonts: dict, out_fonts: dict, out_text: str) -> tuple[bool, str]:
    """Return (match, reason). Special handling for Greek chars."""
    # Normalize for comparison — strip eastAsia if template lacks it
    def _norm(f: dict) -> set:
        return set((k, _normalize_font_name(v) or "") for k, v in f.items())

    # If template has no font info at all, skip (inherits from style)
    if not orig_fonts:
        return True, ""

    # Strip eastAsia from comparison if template doesn't specify it
    orig_stripped = {k: v for k, v in orig_fonts.items() if k != "eastAsia"}
    out_stripped = {k: v for k, v in out_fonts.items() if "eastAsia" not in orig_fonts or k != "eastAsia"}
    if "eastAsia" not in orig_fonts:
        out_stripped = {k: v for k, v in out_fonts.items() if k != "eastAsia"}

    orig_set = _norm(orig_stripped)
    out_set = _norm(out_stripped)

    # Check if fonts match (after stripping eastAsia)
    if orig_set == out_set:
        return True, ""

    # Special case: Greek chars should use Symbol font
    if _has_greek(out_text):
        out_sym = out_fonts.get("ascii") or out_fonts.get("hAnsi") or ""
        out_sym_norm = _normalize_font_name(out_sym)
        orig_sym = orig_fonts.get("ascii") or orig_fonts.get("hAnsi") or ""
        orig_sym_norm = _normalize_font_name(orig_sym)
        if "Symbol" in (out_sym_norm or "") or "MT Extra" in (out_sym_norm or ""):
            if "Symbol" not in (out_sym_norm or "") and "MT Extra" not in (out_sym_norm or ""):
                return False, f"GREEK_CHAR_MISMATCH: text='{out_text[:20]}...' template uses '{orig_sym}' but output uses '{out_sym}'"
        if "Symbol" not in (orig_sym_norm or "") and "Times" not in (orig_sym_norm or "") and "serif" not in (orig_sym_norm or ""):
            if "Symbol" in (out_sym_norm or "") or "MT Extra" in (out_sym_norm or ""):
                return False, f"GREEK_UNEXPECTED_FONT: text='{out_text[:20]}...' template='{orig_sym}' but output uses '{out_sym}'"

    return False, f"FONT_MISMATCH"


def audit_font_full(doc_orig, doc_out) -> AuditResult:
    """Scan ALL paragraphs and compare per-run fonts between template and output."""
    res = AuditResult()

    orig_paras = [p for p in doc_orig.paragraphs if p.text.strip()]
    out_paras = [p for p in doc_out.paragraphs if p.text.strip()]

    # Pair by text similarity (fallback: index alignment)
    from difflib import SequenceMatcher

    def best_match(orig_list, out_list):
        pairs = []
        used_out = set()
        for oi, op in enumerate(orig_list):
            best_score = 0.0
            best_oi = None
            best_oj = None
            for oj, ojp in enumerate(out_list):
                if oj in used_out:
                    continue
                ratio = SequenceMatcher(None, op.text, ojp.text).ratio()
                if ratio > best_score:
                    best_score = ratio
                    best_oi = oi
                    best_oj = oj
            if best_oi is not None and best_score >= 0.6:  # 0.6 to avoid false para matches
                pairs.append((best_oi, best_oj))
                used_out.add(best_oj)
        return pairs

    pairs = best_match(orig_paras, out_paras)

    mismatches = []
    for orig_idx, out_idx in pairs:
        orig_p = orig_paras[orig_idx]
        out_p = out_paras[out_idx]
        orig_runs = _extract_all_run_fonts(orig_p)
        out_runs = _extract_all_run_fonts(out_p)

        # Compare each run pair by text similarity
        out_text = out_p.text
        for ri, orig_run in enumerate(orig_runs):
            if not orig_run["text"]:
                continue
            # Find best matching out run
            best_ratio = 0.0
            best_out_run = None
            for oj, out_run in enumerate(out_runs):
                r = SequenceMatcher(None, orig_run["text"], out_run["text"]).ratio()
                if r > best_ratio:
                    best_ratio = r
                    best_out_run = out_run
            if best_out_run is None or best_ratio < 0.4:
                continue
            matched, reason = _run_fonts_match(orig_run["fonts"], best_out_run["fonts"], best_out_run["text"])
            if not matched:
                mismatches.append({
                    "para_idx": out_idx,
                    "run_idx": ri,
                    "orig": orig_run["fonts"],
                    "out": best_out_run["fonts"],
                    "text": best_out_run["text"][:50],
                    "reason": reason,
                })

    # Deduplicate by para_idx (show first mismatch per paragraph)
    seen_para = {}
    for m in mismatches:
        pid = m["para_idx"]
        if pid not in seen_para:
            seen_para[pid] = m

    if seen_para:
        for m in list(seen_para.values())[:15]:
            if "GREEK" in m["reason"]:
                res.errors.append(
                    f"[FONT] {m['reason']} | orig={m['orig']} out={m['out']}"
                )
            else:
                res.errors.append(
                    f"[FONT] Para #{m['para_idx']} run #{m['run_idx']}: "
                    f"orig={m['orig']} out={m['out']} | \"{m['text']}\""
                )

    res.info["font_full_mismatches"] = len(seen_para)

    return res


# =============================================================================
# [5f.2] Font Size Consistency Audit (MINOR -3 per mismatch)
# =============================================================================
# Bandingkan ukuran font (w:sz) run pertama di N paragraf STRICT zone.
# Output harus mempertahankan ukuran font yang sama dengan template original.
# Pattern asal: CERiMRE (run 2026-06-19). Generator kadang mengubah font size
# menjadi default (e.g. Calibri 11pt) alih-alih ukuran jurnal.

def audit_font_size_consistency(doc_orig, doc_out, n_check: int = 10) -> AuditResult:
    """Bandingkan font size (w:sz) di N paragraf pertama (STRICT zone).

    Hanya flag jika ORIG memiliki ukuran font eksplisit (bukan 0/None) dan
    OUTPUT berbeda secara substantif (selisih ≥ 1 half-point).
    """
    res = AuditResult()

    orig_paras = [p for p in doc_orig.paragraphs if p.text.strip()][:n_check * 2]
    out_paras = [p for p in doc_out.paragraphs if p.text.strip()][:n_check * 2]
    pairs = _align_paragraph_pairs(orig_paras, out_paras)[:n_check]

    mismatches: list[dict] = []
    for orig_idx, out_idx in pairs:
        orig_p = orig_paras[orig_idx]
        out_p = out_paras[out_idx]
        if not orig_p.runs or not out_p.runs:
            continue
        orig_fmt = _extract_run_formatting(orig_p.runs[0])
        out_fmt = _extract_run_formatting(out_p.runs[0])

        orig_sz = orig_fmt.get("size")
        out_sz = out_fmt.get("size")

        # Skip jika orig tidak punya ukuran eksplisit (default via style)
        if orig_sz is None or orig_sz == 0:
            continue
        # Skip jika output juga tidak punya (pakai style default)
        if out_sz is None or out_sz == 0:
            continue

        # Toleransi 1 half-point (~0.5pt) untuk noise konversi
        if abs(orig_sz - out_sz) > 1:
            mismatches.append({
                "para_index": out_idx,
                "orig_size_halfpt": orig_sz,
                "out_size_halfpt": out_sz,
                "orig_pt": round(orig_sz / 2, 1),
                "out_pt": round(out_sz / 2, 1),
                "snippet": out_p.text[:50],
            })

    if mismatches:
        for m in mismatches[:10]:
            res.errors.append(
                f"FONT SIZE MISMATCH: Paragraf #{m['para_index']} "
                f"orig={m['orig_pt']}pt vs out={m['out_pt']}pt. "
                f"\"{m['snippet']}\""
            )

    res.info = {
        "checked": len(pairs),
        "mismatches": len(mismatches),
    }
    return res


# =============================================================================
# [5i] Embedded Image vs AI Prompt Audit (MAYOR -10 per gambar tidak embedded)
# =============================================================================
# Deteksi: JSON punya N figure titles, tapi DOCX hanya punya teks prompt AI
# tanpa gambar beneran embedded. Ini berarti pipeline export gagal menyisipkan
# gambar dari web ke DOCX - prompt AI adalah fallback, bukan hasil final.
#
# Berbeda dengan audit_images yg menghitung prompt sebagai "konten valid",
# audit ini secara eksplisit membedakan gambar embedded vs prompt teks.

def audit_embedded_vs_prompts(doc_orig, doc_out, json_titles: list[str]) -> AuditResult:
    """Validasi bahwa figure di JSON punya gambar embedded di DOCX.

    Aturan:
    - Setiap figure title di JSON harus punya gambar embedded di DOCX.
    - Jika DOCX hanya punya prompt teks (tanpa gambar), flag sebagai
      IMAGE NOT EMBEDDED (MAYOR -10 per gambar).
    - Prompts tanpa gambar embedded = pipeline export belum final.
    """
    res = AuditResult()

    # 1) Count content drawings di output (sama dengan logic audit_images)
    a_count = _count_body_drawings(doc_out)
    decorative_rids = _get_template_decorative_rids(doc_orig)

    decorative_count = 0
    for blip in doc_out._element.body.findall(f".//{{{DRAWING_NS}}}blip"):
        rid = blip.get(f"{{{R_NS}}}embed")
        if rid and rid in decorative_rids:
            decorative_count += 1
    shape_decorative_out = _count_decorative_shape_drawings(doc_out)
    shape_decorative_orig = _count_decorative_shape_drawings(doc_orig)
    decorative_count += min(shape_decorative_out, shape_decorative_orig)

    content_drawings = max(0, a_count - decorative_count)

    # 2) Count AI prompts di body
    all_paras = list(doc_out.paragraphs)
    for tbl in doc_out.tables:
        for row in tbl.rows:
            for cell in row.cells:
                all_paras.extend(cell.paragraphs)

    prompt_count = 0
    for para in all_paras:
        if PROMPT_AI_REGEX.search(para.text):
            prompt_count += 1

    # 3) Expected dari JSON
    expected = len(json_titles)
    embedded_count = content_drawings

    # 4) Jika expected > 0 tapi embedded < expected DAN ada prompts,
    #    berarti gambar gagal di-embed → flag
    if expected > 0 and embedded_count < expected:
        missing_images = expected - embedded_count
        # Hanya flag jika prompts menggantikan gambar
        # (prompts = fallback, bukan hasil final)
        if prompt_count > 0:
            for i in range(missing_images):
                title_hint = json_titles[i] if i < len(json_titles) else f"figure_{i+1}"
                res.errors.append(
                    f"GAMBAR TIDAK EMBEDDED: Figure '{title_hint[:60]}' - "
                    f"JSON expect {expected} gambar, DOCX hanya punya "
                    f"{embedded_count} embedded image(s) + {prompt_count} "
                    f"teks prompt AI. Pipeline export belum menyisipkan "
                    f"gambar asli ke DOCX."
                )
        elif embedded_count == 0:
            # Tidak ada gambar embedded sama sekali - semua prompt
            for i in range(expected):
                title_hint = json_titles[i] if i < len(json_titles) else f"figure_{i+1}"
                res.errors.append(
                    f"GAMBAR TIDAK EMBEDDED: Figure '{title_hint[:60]}' - "
                    f"DOCX tidak memiliki embedded image (hanya teks prompt). "
                    f"Pipeline export perlu menyisipkan gambar asli."
                )

    res.info = {
        "json_expected": expected,
        "embedded_content_images": embedded_count,
        "ai_prompts": prompt_count,
        "decorative_excluded": decorative_count,
    }
    return res


# =============================================================================
# [5h] Placeholder/Blank Image Detection (MINOR -5 per placeholder)
# =============================================================================
# Deteksi gambar yang merupakan placeholder kosong (putih/uniform) bukan konten
# real. Generator yang salah bisa insert gambar putih PIL alih-alih prompt AI.
# Pattern asal: template CERiMRE (run 2026-05-25)

def _extract_embedded_images(doc) -> list[dict]:
    """Extract info embedded images dari DOCX package.

    Return list of {rId, content_type, size_bytes, part_name}.
    """
    images = []
    try:
        for rel in doc.part.rels.values():
            if "image" in (rel.reltype or "").lower():
                try:
                    blob = rel.target_part.blob
                    images.append({
                        "rId": rel.rId,
                        "content_type": getattr(rel.target_part, "content_type", ""),
                        "size_bytes": len(blob) if blob else 0,
                        "part_name": str(getattr(rel.target_part, "partname", "")),
                        "blob": blob,
                    })
                except Exception:
                    continue
    except Exception:
        pass
    return images


def _is_placeholder_image(blob: bytes, size_bytes: int) -> tuple[bool, str]:
    """Heuristik deteksi placeholder image.

    Return (is_placeholder, reason).
    Strategi:
    1. Coba buka dengan PIL dan cek apakah >95% pixel putih/uniform
    2. Fallback: cek file size vs dimensions ratio (placeholder sangat kecil)
    """
    try:
        from PIL import Image as PILImage
        from io import BytesIO as _BytesIO

        img = PILImage.open(_BytesIO(blob))
        width, height = img.size

        # Skip gambar kecil (icon/logo) - bukan figure konten
        if width < 200 or height < 200:
            return False, ""

        # Sample pixels untuk cek uniformity
        img_rgb = img.convert("RGB")
        total_pixels = width * height
        # Sample max 10000 pixels untuk performa
        step = max(1, int((total_pixels / 10000) ** 0.5))
        white_count = 0
        sample_count = 0
        for y in range(0, height, step):
            for x in range(0, width, step):
                r, g, b = img_rgb.getpixel((x, y))
                sample_count += 1
                if r > 240 and g > 240 and b > 240:
                    white_count += 1

        if sample_count == 0:
            return False, ""

        white_ratio = white_count / sample_count
        if white_ratio > 0.95:
            return True, f"white_ratio={white_ratio:.1%} (>{95}% putih, {width}x{height}px)"

    except ImportError:
        # PIL tidak tersedia - fallback ke size heuristic
        # Gambar putih 1600x900 PNG compress ke ~2-5KB
        # Gambar real biasanya >20KB untuk ukuran serupa
        if size_bytes < 8000:
            return True, f"size_heuristic (size={size_bytes}B, terlalu kecil untuk gambar konten)"
    except Exception:
        pass

    return False, ""


def audit_placeholder_images(doc_out, doc_orig=None) -> AuditResult:
    """Deteksi gambar placeholder/blank di output.

    Gambar yang >95% putih/uniform dianggap placeholder yang seharusnya
    diganti dengan [PROMPT UNTUK AI GAMBAR: ...].

    Skip gambar yang juga ada di template original (logo/dekoratif).
    """
    res = AuditResult()

    # Get decorative rIds dari template original (logo, dsb)
    decorative_rids: set[str] = set()
    if doc_orig is not None:
        decorative_rids = _get_template_decorative_rids(doc_orig)

    # Extract semua embedded images dari output
    images = _extract_embedded_images(doc_out)

    # Get rIds yang dipakai di body (bukan header/footer)
    body_rids = _extract_blip_rids(doc_out._element.body)

    placeholders: list[dict] = []
    for img_info in images:
        rid = img_info["rId"]

        # Skip kalau bukan di body
        if rid not in body_rids:
            continue

        # Skip kalau decorative (logo template)
        if rid in decorative_rids:
            continue

        blob = img_info.get("blob")
        if not blob:
            continue

        is_ph, reason = _is_placeholder_image(blob, img_info["size_bytes"])
        if is_ph:
            placeholders.append({
                "rId": rid,
                "part_name": img_info["part_name"],
                "size_bytes": img_info["size_bytes"],
                "reason": reason,
            })

    if placeholders:
        for ph in placeholders:
            res.errors.append(
                f"PLACEHOLDER IMAGE: Gambar '{ph['part_name']}' (rId={ph['rId']}, "
                f"{ph['size_bytes']}B) terdeteksi sebagai placeholder kosong/putih. "
                f"Reason: {ph['reason']}. "
                f"Seharusnya diganti dengan [PROMPT UNTUK AI GAMBAR: ...]."
            )

    res.info = {
        "total_body_images": len([i for i in images if i["rId"] in body_rids and i["rId"] not in decorative_rids]),
        "placeholder_count": len(placeholders),
        "details": placeholders,
    }
    return res


# =============================================================================
# [5i] Logo Preservation Audit (MAYOR -10 per logo missing)
# =============================================================================
def audit_logo_preservation(doc_orig, doc_out) -> AuditResult:
    """Validasi bahwa logo jurnal (images di first 5 paragraphs body + headers/footers)
    dipreservasi di output.

    Context: gen_factory.py clear_body() function sekarang preserve images di
    first 5 paragraphs sebagai logo jurnal (branding). Audit ini memastikan
    logo tersebut tidak hilang saat generation.

    Aturan:
    - Logo = images (drawing/blip) di first 5 paragraphs body + SEMUA headers/footers
    - Logo harus preserved di output (rId match)
    - Content images (figures) boleh di-replace dengan AI prompts (expected)
    - Penalty hanya untuk logo yang hilang (branding loss)
    """
    res = AuditResult()

    # Identify logo rIds dari template original (body top + headers/footers)
    orig_logo_rids = _get_template_decorative_rids(doc_orig)

    # Get all rIds di output body
    output_body_rids = _extract_blip_rids(doc_out._element.body)

    # Get all rIds di output headers/footers
    output_hf_rids: set[str] = set()
    for section in doc_out.sections:
        for part_attr in HF_PART_ATTRS:
            part = getattr(section, part_attr, None)
            if part is None:
                continue
            try:
                rids = _extract_blip_rids(part._element)
                output_hf_rids.update(rids)
            except (AttributeError, KeyError):
                continue

    # Combine body + header/footer rIds for output
    output_all_rids = output_body_rids | output_hf_rids

    # Check preservation: berapa logo original yang masih ada di output
    preserved_rids = orig_logo_rids & output_all_rids
    missing_rids = orig_logo_rids - output_all_rids

    # Count logo instances di original (body + headers/footers)
    orig_logo_count_body = 0
    orig_logo_count_hf = 0
    body_orig = doc_orig._element.body

    # Count in body: first 5 paragraphs
    para_count = 0
    for child in body_orig.iterchildren():
        if child.tag == qn("w:p"):
            para_count += 1
            if para_count > 5:
                break
            for blip in child.findall(f".//{{{DRAWING_NS}}}blip"):
                rid = blip.get(f"{{{R_NS}}}embed")
                if rid and rid in orig_logo_rids:
                    orig_logo_count_body += 1
            # VML imagedata
            for imagedata in child.findall(f".//{{{VML_NS}}}imagedata"):
                rid = imagedata.get(f"{{{R_NS}}}id")
                if rid and rid in orig_logo_rids:
                    orig_logo_count_body += 1

    # Count in body: first 5 tables
    table_count = 0
    for child in body_orig.iterchildren():
        if child.tag == qn("w:tbl"):
            table_count += 1
            if table_count > 5:
                break
            for blip in child.findall(f".//{{{DRAWING_NS}}}blip"):
                rid = blip.get(f"{{{R_NS}}}embed")
                if rid and rid in orig_logo_rids:
                    orig_logo_count_body += 1
            # VML imagedata
            for imagedata in child.findall(f".//{{{VML_NS}}}imagedata"):
                rid = imagedata.get(f"{{{R_NS}}}id")
                if rid and rid in orig_logo_rids:
                    orig_logo_count_body += 1

    # Count in headers/footers
    for section in doc_orig.sections:
        for part_attr in HF_PART_ATTRS:
            part = getattr(section, part_attr, None)
            if part is None:
                continue
            try:
                el = part._element
                for blip in el.findall(f".//{{{DRAWING_NS}}}blip"):
                    rid = blip.get(f"{{{R_NS}}}embed")
                    if rid and rid in orig_logo_rids:
                        orig_logo_count_hf += 1
                # VML imagedata
                for imagedata in el.findall(f".//{{{VML_NS}}}imagedata"):
                    rid = imagedata.get(f"{{{R_NS}}}id")
                    if rid and rid in orig_logo_rids:
                        orig_logo_count_hf += 1
            except (AttributeError, KeyError):
                continue

    # Count logo instances di output (body + headers/footers)
    out_logo_count_body = 0
    out_logo_count_hf = 0
    body_out = doc_out._element.body

    # Count in body: first 5 paragraphs
    para_count = 0
    for child in body_out.iterchildren():
        if child.tag == qn("w:p"):
            para_count += 1
            if para_count > 5:
                break
            for blip in child.findall(f".//{{{DRAWING_NS}}}blip"):
                rid = blip.get(f"{{{R_NS}}}embed")
                if rid and rid in preserved_rids:
                    out_logo_count_body += 1
            # VML imagedata
            for imagedata in child.findall(f".//{{{VML_NS}}}imagedata"):
                rid = imagedata.get(f"{{{R_NS}}}id")
                if rid and rid in preserved_rids:
                    out_logo_count_body += 1

    # Count in body: first 5 tables
    table_count = 0
    for child in body_out.iterchildren():
        if child.tag == qn("w:tbl"):
            table_count += 1
            if table_count > 5:
                break
            for blip in child.findall(f".//{{{DRAWING_NS}}}blip"):
                rid = blip.get(f"{{{R_NS}}}embed")
                if rid and rid in preserved_rids:
                    out_logo_count_body += 1
            # VML imagedata
            for imagedata in child.findall(f".//{{{VML_NS}}}imagedata"):
                rid = imagedata.get(f"{{{R_NS}}}id")
                if rid and rid in preserved_rids:
                    out_logo_count_body += 1

    # Count in headers/footers
    for section in doc_out.sections:
        for part_attr in HF_PART_ATTRS:
            part = getattr(section, part_attr, None)
            if part is None:
                continue
            try:
                el = part._element
                for blip in el.findall(f".//{{{DRAWING_NS}}}blip"):
                    rid = blip.get(f"{{{R_NS}}}embed")
                    if rid and rid in preserved_rids:
                        out_logo_count_hf += 1
                # VML imagedata
                for imagedata in el.findall(f".//{{{VML_NS}}}imagedata"):
                    rid = imagedata.get(f"{{{R_NS}}}id")
                    if rid and rid in preserved_rids:
                        out_logo_count_hf += 1
            except (AttributeError, KeyError):
                continue

    # Total counts
    orig_logo_count = orig_logo_count_body + orig_logo_count_hf
    out_logo_count = out_logo_count_body + out_logo_count_hf

    # Report missing logos
    if missing_rids:
        res.errors.append(
            f"LOGO MISSING: {len(missing_rids)} logo jurnal hilang dari output. "
            f"Logo adalah branding jurnal yang harus dipertahankan. "
            f"Original: {orig_logo_count} total ({orig_logo_count_body} body + {orig_logo_count_hf} header/footer), "
            f"Output: {out_logo_count} total ({out_logo_count_body} body + {out_logo_count_hf} header/footer). "
            f"Missing rIds: {sorted(missing_rids)}"
        )

    res.info = {
        "orig_logo_rids": sorted(orig_logo_rids),
        "preserved_rids": sorted(preserved_rids),
        "missing_rids": sorted(missing_rids),
        "orig_logo_count": orig_logo_count,
        "orig_logo_count_body": orig_logo_count_body,
        "orig_logo_count_hf": orig_logo_count_hf,
        "out_logo_count": out_logo_count,
        "out_logo_count_body": out_logo_count_body,
        "out_logo_count_hf": out_logo_count_hf,
        "preservation_rate": (len(preserved_rids) / len(orig_logo_rids) * 100) if orig_logo_rids else 100.0,
    }
    return res


# =============================================================================
# [6] Multi-Column XPath Audit (FATAL -25)
# =============================================================================
# Mendeteksi kasus original 2-kolom -> output 1-kolom yang tidak tertangkap oleh
# audit_page_setup() jika section count berbeda atau cols-element absen.
#
# Catatan teknis: BaseOxmlElement python-docx punya .xpath() builtin dengan
# namespace registry yang sudah memuat w/r/a/m (tanpa kwarg namespaces=).
# Untuk VML (v:) yang tidak terdaftar, kita raw-parse via lxml etree.
def _lxml_xpath(el, expr, ns):
    """Raw lxml xpath dengan namespace map kustom (untuk v:, dst.)."""
    try:
        raw = etree.fromstring(etree.tostring(el))
    except Exception:
        return []
    try:
        return raw.xpath(expr, namespaces=ns)
    except Exception:
        return []


def _xpath_cols_num(sectpr):
    """Ambil w:num attribute dari w:cols dalam sebuah sectPr.
    Return integer (default 1 jika tidak ada w:cols atau atribut hilang)."""
    if sectpr is None:
        return 1
    cols_list = sectpr.xpath("./w:cols")
    if not cols_list:
        return 1
    cols = cols_list[0]
    num = cols.get(qn("w:num"))
    if num is None:
        return 1
    try:
        return int(num)
    except (ValueError, TypeError):
        return 1


def _doc_section_sectprs(doc):
    """Kumpulkan SEMUA sectPr dokumen: inline sectPr di pPr paragraf + final body sectPr.
    Urutan mengikuti urutan munculnya di body."""
    body = doc._element.body
    sectprs = []
    # Inline sectPr (di dalam pPr)
    for p in body.iter(qn("w:p")):
        for sp in p.findall(f".//{qn('w:sectPr')}"):
            sectprs.append(sp)
    # Final body sectPr
    final = body.find(qn("w:sectPr"))
    if final is not None:
        sectprs.append(final)
    return sectprs


def audit_multicolumn_xpath(doc_orig, doc_out) -> AuditResult:
    """Strict XPath check: setiap section dengan w:num >= 2 di original
    HARUS punya w:num >= 2 yang sama di output pada index yang sesuai."""
    res = AuditResult()

    orig_sps = _doc_section_sectprs(doc_orig)
    out_sps = _doc_section_sectprs(doc_out)

    n = min(len(orig_sps), len(out_sps))
    broken = []

    for i in range(n):
        orig_num = _xpath_cols_num(orig_sps[i])
        out_num = _xpath_cols_num(out_sps[i])
        if orig_num >= 2 and out_num < orig_num:
            res.errors.append(
                f"[LAYOUT ERROR] Format multi-kolom hancur. "
                f"Section {i + 1}: Original memiliki {orig_num} kolom, "
                f"Output menjadi {out_num} kolom."
            )
            broken.append((i + 1, orig_num, out_num))

    # Section count mismatch yang berdampak pada layout multi-kolom
    if len(orig_sps) > len(out_sps):
        # Cek apakah section yang hilang di output adalah multi-kolom
        for i in range(len(out_sps), len(orig_sps)):
            orig_num = _xpath_cols_num(orig_sps[i])
            if orig_num >= 2:
                res.errors.append(
                    f"[LAYOUT ERROR] Format multi-kolom hancur. "
                    f"Section {i + 1} hilang di output "
                    f"(Original: {orig_num} kolom, Output: section tidak ada)."
                )
                broken.append((i + 1, orig_num, 0))

    res.info = {
        "n_orig_sections": len(orig_sps),
        "n_out_sections": len(out_sps),
        "broken": broken,
    }
    return res


# =============================================================================
# [7] Header Shapes / TextBox XPath Audit (FATAL -20)
# =============================================================================
SHAPE_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "v": "urn:schemas-microsoft-com:vml",
}


def _count_header_shapes(part):
    """Hitung gabungan w:drawing + w:pict + v:shape + w:txbxContent
    di part header (atau footer). Robust terhadap part None."""
    if part is None:
        return {"drawing": 0, "pict": 0, "vshape": 0, "txbx": 0}
    try:
        el = part._element
        counts = {
            "drawing": len(el.xpath(".//w:drawing", namespaces=SHAPE_NS)),
            "pict": len(el.xpath(".//w:pict", namespaces=SHAPE_NS)),
            "vshape": len(_lxml_xpath(el, ".//v:shape", SHAPE_NS)),
            "txbx": len(el.xpath(".//w:txbxContent", namespaces=SHAPE_NS)),
        }
        return counts
    except (AttributeError, Exception):
        return {"drawing": 0, "pict": 0, "vshape": 0, "txbx": 0}


def _shape_total(counts):
    return sum(counts.values()) if isinstance(counts, dict) else 0


def audit_header_shapes_xpath(doc_orig, doc_out) -> AuditResult:
    """Cek apakah objek visual (drawing/pict/v:shape/textbox) di header original
    masih utuh di output."""
    res = AuditResult()

    orig_sections = doc_orig.sections
    out_sections = doc_out.sections
    n = min(len(orig_sections), len(out_sections))

    breakdown = []  # list of dict
    fatal_hits = 0

    for i in range(n):
        for part_attr in HF_PART_ATTRS:
            orig_part = getattr(orig_sections[i], part_attr, None)
            out_part = getattr(out_sections[i], part_attr, None)

            orig_counts = _count_header_shapes(orig_part) if orig_part else {}
            out_counts = _count_header_shapes(out_part) if out_part else {}

            orig_total = _shape_total(orig_counts)
            out_total = _shape_total(out_counts)

            if orig_total <= 0:
                continue  # Original memang tidak punya shape; skip.

            label = HF_PART_LABEL.get(part_attr, part_attr)
            section_label = f"Section {i + 1} ({label})"

            if out_total < orig_total:
                missing = orig_total - out_total
                res.errors.append(
                    f"[HEADER ERROR] Objek visual/TextBox pada header hilang "
                    f"saat konversi. {section_label}: "
                    f"Original {orig_total} objek, Output {out_total} "
                    f"(hilang {missing}). "
                    f"Detail original: {orig_counts}"
                )
                fatal_hits += 1

            breakdown.append({
                "section": i + 1,
                "part": label,
                "orig": orig_counts,
                "out": out_counts,
            })

    res.info = {"breakdown": breakdown, "fatal_hits": fatal_hits}
    return res


# =============================================================================
# [7b] Body Table Count Audit (MINOR -5 per selisih)
# =============================================================================
def _count_body_tables(doc) -> int:
    """Hitung tabel body, skip:
    - Tabel layout equation (1 row, 2-3 cols dengan equation number atau kosong/sangat sparse).
    - Tabel 1x1 (prompt box / single cell layout).
    - Tabel 1x2 (side-by-side figure layout containers).
    - Tabel 2x2 dengan konten minimal (layout containers).
    Equation tables dan prompt boxes adalah konten layout/math, bukan data table.
    """
    body = doc._element.body
    tables = body.findall(qn("w:tbl"))
    count = 0
    import re as _re
    eq_pattern = _re.compile(r"\(\d+[a-zA-Z.\d]*\)")
    for tbl in tables:
        rows = tbl.findall(qn("w:tr"))
        if len(rows) == 1:
            cells = rows[0].findall(qn("w:tc"))
            # Skip tabel 1x1 (prompt box / single cell layout)
            if len(cells) == 1:
                continue
            # Skip tabel 1x2: almost always layout containers for side-by-side figures
            if len(cells) == 2:
                continue
            # Skip tabel single-row 3 cols: equation/layout container
            if len(cells) == 3:
                # Cek apakah salah satu cell adalah equation number
                cell_texts = []
                for cell in cells:
                    cell_text = "".join(
                        (t.text or "") for t in cell.findall(f".//{qn('w:t')}")
                    ).strip()
                    cell_texts.append(cell_text)
                # Skip jika ada equation number ATAU semua cell text pendek/empty
                # (layout container template equation yang konten-nya tidak ter-render text)
                has_eq_num = any(eq_pattern.fullmatch(ct) for ct in cell_texts)
                all_short = all(len(ct) < 80 for ct in cell_texts)
                no_data_marker = not any(
                    word in ct.lower() for ct in cell_texts
                    for word in ("table", "tabel", "header", "no.", "value", "data")
                )
                if has_eq_num or (all_short and no_data_marker):
                    continue
        elif len(rows) == 2:
            cells = rows[0].findall(qn("w:tc"))
            # Skip tabel 2x2 dengan konten minimal (layout containers)
            if len(cells) == 2:
                total_text = 0
                for row in rows:
                    for cell in row.findall(qn("w:tc")):
                        cell_text = "".join(
                            (t.text or "") for t in cell.findall(f".//{qn('w:t')}")
                        ).strip()
                        total_text += len(cell_text)
                # Skip if total text < 200 chars (likely layout container)
                if total_text < 200:
                    continue
        count += 1
    return count


def audit_table_count(doc_orig, doc_out, json_expected: int | None = None) -> AuditResult:
    """Bandingkan jumlah tabel body original vs output (B3 classifier + B8 JSON-based).

    B8: Jika json_expected diberikan, baseline-nya adalah orig + json_expected
    (tabel template + tabel content user). Jika tidak, fallback ke orig saja.

    Klasifikasi:
    - extra_empty: output > expected DAN tabel tambahan low density (placeholder kosong)
    - extra_filled: output > expected DAN tabel tambahan punya konten
    - missing: output < expected (layout container hilang)
    """
    res = AuditResult()
    n_orig = _count_body_tables(doc_orig)
    n_out = _count_body_tables(doc_out)

    # B8: Adjust expected count based on JSON content
    # Generator uses clear_body() approach: clears all body content and regenerates from JSON.
    # When json_expected is provided, it means the generator will create exactly that many tables.
    # The template's original tables (including example content) are cleared, so we should
    # expect json_expected tables in the output, not max(orig, json_expected).
    if json_expected is not None and json_expected > 0:
        # Expected count is json_expected (what generator will create)
        n_expected = json_expected
    else:
        # No JSON data, expect template structure to be preserved
        n_expected = n_orig

    diff = abs(n_expected - n_out)
    n_extra = max(0, n_out - n_expected)
    n_missing = max(0, n_expected - n_out)

    # Klasifikasi extra: berapa tabel di output yang low density
    extra_empty_count = 0
    extra_filled_count = 0
    if n_extra > 0:
        body_tables = doc_out.tables
        for i, tbl in enumerate(body_tables):
            has_drawing = False
            for row in tbl.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        if para._element.findall(f".//{qn('w:drawing')}"):
                            has_drawing = True
                            break
                    if has_drawing:
                        break
                if has_drawing:
                    break
            if has_drawing:
                continue
            n_rows = len(tbl.rows)
            n_cols = len(tbl.rows[0].cells) if n_rows > 0 else 0
            if n_rows < 2 or n_cols < 2:
                continue
            density = _table_cell_density(tbl)
            if density < 0.5:
                extra_empty_count += 1
            else:
                extra_filled_count += 1

        if extra_empty_count + extra_filled_count > n_extra:
            ratio = n_extra / (extra_empty_count + extra_filled_count)
            extra_empty_count = int(extra_empty_count * ratio)
            extra_filled_count = n_extra - extra_empty_count

    # Adjust expected: jika JSON punya tabel, output boleh memiliki orig + json
    # tabel (tabel layout original tetap + konten user dari JSON). Audit tidak
    # boleh penalize generator yang mempertahankan struktur dan menambah konten.
    if json_expected is not None and json_expected > 0:
        n_expected = max(n_orig, json_expected, n_orig + json_expected - n_orig)
        # Allow output up to n_orig + json_expected tanpa flag extra
        n_expected_max = n_orig + json_expected
    else:
        n_expected_max = n_expected

    if diff > TABLE_COUNT_TOLERANCE:
        if n_missing > 0:
            res.errors.append(
                f"TABLE MISSING: Output kekurangan {n_missing} tabel "
                f"(Expected: {n_expected}, Output: {n_out}). Tabel layout container "
                f"template (mis. figure side-by-side) kemungkinan hilang."
            )
        if n_extra > 0 and n_out > n_expected_max + TABLE_COUNT_TOLERANCE:
            if extra_empty_count > 0:
                res.errors.append(
                    f"TABLE EXTRA EMPTY: Output kelebihan {extra_empty_count} tabel "
                    f"placeholder kosong (low density). Generator menambahkan tabel "
                    f"scaffold yang tidak ada di template original."
                )
            if extra_filled_count > 0:
                res.errors.append(
                    f"TABLE EXTRA FILLED: Output kelebihan {extra_filled_count} tabel "
                    f"berkonten (Expected: {n_expected}, Output: {n_out}). "
                    f"Generator menambahkan tabel data yang tidak ada di JSON."
                )

    res.info = {
        "n_orig": n_orig,
        "n_out": n_out,
        "n_expected": n_expected,
        "json_expected": json_expected,
        "diff": diff,
        "n_missing": n_missing,
        "n_extra": n_extra,
        "extra_empty": extra_empty_count,
        "extra_filled": extra_filled_count,
    }
    return res


# =============================================================================
# [7c] SectPr Distribution Audit (MAYOR)
# =============================================================================
# Mendeteksi pola "flush-at-end": generator emit semua sectPr inline di akhir
# body sebagai paragraf empty trailer, bukan menyebarkannya di antara konten.
# Distribusi total kolom akan terlihat sama dengan original (sehingga
# audit_page_setup lulus), tapi visual layout multi-section hancur.
def _ordered_inline_sectprs(doc):
    """Urut sectPr inline (TIDAK termasuk final body sectPr) sesuai
    posisi paragraf parent-nya di body. Return list of (para_index, sectpr_el)."""
    body = doc._element.body
    out = []
    for idx, child in enumerate(body.iterchildren()):
        if child.tag != qn("w:p"):
            continue
        sps = child.findall(f".//{qn('w:sectPr')}")
        for sp in sps:
            out.append((idx, sp))
    return out


def _has_text_content(p_el):
    """True bila paragraf punya text non-kosong (bukan empty trailer)."""
    txts = p_el.findall(f".//{qn('w:t')}")
    for t in txts:
        if (t.text or "").strip():
            return True
    return False


def _inline_sectpr_is_page_breaking(child):
    """True bila paragraf membawa inline sectPr bertipe page-breaking
    (nextPage/evenPage/oddPage/default). sectPr CONTINUOUS -> False:
    section continuous tidak memulai halaman baru, jadi paragraf empty
    bersectPr continuous di ekor TIDAK menghasilkan halaman kosong dan
    tak terlihat (invisible) di Word."""
    sps = child.findall(f".//{qn('w:sectPr')}")
    if not sps:
        return False
    sp = sps[0]
    t = sp.find(qn("w:type"))
    tval = t.get(qn("w:val")) if t is not None else None
    return tval in PAGE_BREAKING_SEC_TYPES


def _count_trailing_empty_sectpr_run(doc, page_breaking_only=False):
    """Hitung berapa paragraf empty bersectPr yang dijejer di EKOR body
    tanpa diselingi konten bertext. Indikator pola flush-at-end.

    page_breaking_only=True: HANYA hitung yang sectPr-nya page-breaking
    (nextPage/even/odd/default). Trailing empty continuous tidak dihitung
    karena invisible & tidak bikin blank page. Dipakai untuk penalti
    flush-at-end supaya tidak false-positive pada template yang ekornya
    memang continuous (mis. AEJ: body 2-kolom continuous + boilerplate
    1-kolom continuous yang sengaja dibiarkan kosong)."""
    body = doc._element.body
    children = list(body.iterchildren())
    run = 0
    for child in reversed(children):
        if child.tag == qn("w:sectPr"):
            continue  # final body sectPr, lewati
        if child.tag != qn("w:p"):
            break
        sps = child.findall(f".//{qn('w:sectPr')}")
        if sps and not _has_text_content(child):
            if page_breaking_only and not _inline_sectpr_is_page_breaking(child):
                # Continuous trailing empty -> invisible, lewati (jangan stop:
                # bisa ada page-breaking empty di belakangnya).
                continue
            run += 1
            continue
        # paragraf bertext atau tabel di-encounter -> stop
        break
    return run


def _sectpr_distribution_signature(sectprs, n_buckets=None):
    """Bagi list sectPr ke n_buckets posisi proporsional, hitung jumlah
    multi-kolom (num >= 2) per bucket. Return list panjang n_buckets.

    Jika n_buckets=None, hitung dinamis: max(5, len(sectprs)//2).
    """
    n = len(sectprs)
    if n_buckets is None:
        n_buckets = max(5, n // 2)
    if n == 0:
        return [0] * n_buckets
    bucket_counts = [0] * n_buckets
    for i, (_, sp) in enumerate(sectprs):
        bucket = min(int(i / n * n_buckets), n_buckets - 1)
        cols = sp.find(qn("w:cols"))
        if cols is not None:
            num = cols.get(qn("w:num"), "1")
            try:
                if int(num) >= 2:
                    bucket_counts[bucket] += 1
            except (ValueError, TypeError):
                pass
    return bucket_counts


def _sectpr_multifeature_signature(sectprs, n_buckets=None):
    """Multi-feature signature: bucketize sectPr dan ekstrak fitur:
    - col_count (jumlah kolom)
    - has_titlePg (apakah punya titlePg / first page different)
    - sec_type (continuous/nextPage/etc)

    Return: list of tuples [(col_buckets, titlepg_buckets, type_buckets)]
    """
    n = len(sectprs)
    if n_buckets is None:
        n_buckets = max(5, n // 2)
    if n == 0:
        return [0] * n_buckets, [0] * n_buckets, [0] * n_buckets

    col_buckets = [0] * n_buckets
    titlepg_buckets = [0] * n_buckets
    type_buckets = [0] * n_buckets  # count nextPage section breaks

    for i, (_, sp) in enumerate(sectprs):
        bucket = min(int(i / n * n_buckets), n_buckets - 1)
        # col_count >= 2
        cols = sp.find(qn("w:cols"))
        if cols is not None:
            num = cols.get(qn("w:num"), "1")
            try:
                if int(num) >= 2:
                    col_buckets[bucket] += 1
            except (ValueError, TypeError):
                pass
        # titlePg
        title_pg = sp.find(qn("w:titlePg"))
        if title_pg is not None:
            titlepg_buckets[bucket] += 1
        # sec_type (nextPage/continuous/etc)
        sec_type = sp.find(qn("w:type"))
        if sec_type is not None:
            type_val = sec_type.get(qn("w:val"), "")
            if type_val == "nextPage":
                type_buckets[bucket] += 1

    return col_buckets, titlepg_buckets, type_buckets


def _cosine_similarity(a, b):
    """Cosine similarity antara dua vector. Return 0-1."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        # Vektor nol -> match jika keduanya nol
        return 1.0 if (norm_a == 0 and norm_b == 0) else 0.0
    return dot / (norm_a * norm_b)


def _l1_normalized_diff(a, b):
    """L1 distance dinormalisasi vs total. 0 = identik, 1 = jauh berbeda."""
    sa = sum(a) or 1
    sb = sum(b) or 1
    pa = [x / sa for x in a]
    pb = [x / sb for x in b]
    return sum(abs(x - y) for x, y in zip(pa, pb)) / 2


def audit_sectpr_distribution(doc_orig, doc_out) -> AuditResult:
    """Dua sub-check:
    (1) Trailing sectPr cluster: bila >= SECTPR_FLUSH_THRESHOLD paragraf empty
        bersectPr menempel di ekor body, generator dianggap melakukan
        flush-at-end. Penalti MAYOR.
    (2) Distribusi multi-kolom per bucket posisi: kalau bucketization
        original vs output berbeda > SECTPR_DISTRIBUTION_THRESHOLD (L1 norm),
        artinya sectPr inline "menumpuk" di tempat yang salah. Penalti MAYOR."""
    res = AuditResult()

    # Hitung HANYA trailing empty sectPr yang page-breaking (nextPage/even/odd/
    # default) untuk penalti flush. Trailing empty CONTINUOUS = invisible & tidak
    # bikin blank page -> tidak boleh kena penalti (false positive yg dulu memaksa
    # AEJ mendistribusi body & merusak layout kolom).
    out_trailing = _count_trailing_empty_sectpr_run(doc_out, page_breaking_only=True)
    orig_trailing = _count_trailing_empty_sectpr_run(doc_orig, page_breaking_only=True)
    # Total (semua tipe) untuk info/diagnostik saja, tidak dipakai scoring.
    out_trailing_all = _count_trailing_empty_sectpr_run(doc_out)
    orig_trailing_all = _count_trailing_empty_sectpr_run(doc_orig)

    # Detect flush-at-end pattern OR blank page issue
    # Pattern 1: Severe flush (>= threshold AND significantly more than original)
    # Pattern 2: Blank page issue (original clean but output has trailing empty sectPr)
    flush_detected = (
        (out_trailing >= SECTPR_FLUSH_THRESHOLD and out_trailing > orig_trailing + 1) or
        (orig_trailing == 0 and out_trailing >= 1)
    )
    if flush_detected:
        res.errors.append(
            f"SECTPR FLUSH-AT-END: Output memiliki {out_trailing} paragraf empty "
            f"bersectPr PAGE-BREAKING menumpuk di akhir body (Original: {orig_trailing}). "
            f"Pola ini memecah layout multi-section template -- section break "
            f"page-breaking ter-emit di akhir, bukan di antara konten, sehingga "
            f"berpotensi menghasilkan halaman kosong."
        )

    orig_inline = _ordered_inline_sectprs(doc_orig)
    out_inline = _ordered_inline_sectprs(doc_out)

    # Dynamic bucket count: max(5, n_sectprs // 2)
    n_buckets = max(5, max(len(orig_inline), len(out_inline)) // 2)

    sig_orig = _sectpr_distribution_signature(orig_inline, n_buckets=n_buckets)
    sig_out = _sectpr_distribution_signature(out_inline, n_buckets=n_buckets)
    div = _l1_normalized_diff(sig_orig, sig_out)

    # Multi-feature cosine similarity (col + titlePg + sec_type)
    col_orig, tp_orig, type_orig = _sectpr_multifeature_signature(orig_inline, n_buckets=n_buckets)
    col_out, tp_out, type_out = _sectpr_multifeature_signature(out_inline, n_buckets=n_buckets)

    # Concat semua fitur jadi 1 vector
    feat_orig = col_orig + tp_orig + type_orig
    feat_out = col_out + tp_out + type_out
    cos_sim = _cosine_similarity(feat_orig, feat_out)

    distribution_diverged = div > SECTPR_DISTRIBUTION_THRESHOLD
    if distribution_diverged:
        res.errors.append(
            f"SECTPR DISTRIBUTION DIVERGED: Distribusi posisi sectPr multi-kolom "
            f"output menyimpang signifikan dari original "
            f"(L1 norm divergence={div:.2f} > {SECTPR_DISTRIBUTION_THRESHOLD}, "
            f"cosine sim={cos_sim:.2f}). "
            f"Bucket original: {sig_orig}, Output: {sig_out}. "
            f"Indikasi: section break tidak menyebar di antara konten dengan benar."
        )

    res.info = {
        "out_trailing_empty_sectpr": out_trailing,
        "orig_trailing_empty_sectpr": orig_trailing,
        "out_trailing_empty_sectpr_all": out_trailing_all,
        "orig_trailing_empty_sectpr_all": orig_trailing_all,
        "flush_detected": flush_detected,
        "sig_orig": sig_orig,
        "sig_out": sig_out,
        "n_buckets": n_buckets,
        "cosine_similarity": cos_sim,
        "divergence": div,
        "distribution_diverged": distribution_diverged,
    }
    return res


# =============================================================================
# [7d] Empty Section / Blank Page Audit (MAYOR)
# =============================================================================
# Mendeteksi pola "blank page": generator menumpuk SEMUA konten body ke satu
# section, menyisakan section-section lain (yang di template original berisi
# konten) hanya berisi paragraf kosong. Section kosong yang dibatasi section
# break page-breaking (nextPage/evenPage/oddPage) akan dirender Word sebagai
# HALAMAN KOSONG.
#
# Blind spot yang ditutup: audit_page_setup hanya cek jumlah section &
# dimensi (lulus karena section count match), audit_sectpr_distribution cek
# trailing cluster & distribusi multi-kolom (lulus karena sectPr tidak numpuk
# di ekor). Tidak ada yang cek "apakah konten tersebar ke section yang benar".
#
# Pattern asal: template PERTANIKA 2025 (run 2026-05-30) -- 18 section, semua
# 129 paragraf body menumpuk di section 16, section 1-15 jadi blank page.
# Pola identik dengan bug AEJ (body_insert_before = sectpr_paras[-1]).

# Section break type yang memulai halaman baru (bukan continuous).
PAGE_BREAKING_SEC_TYPES = {"nextPage", "evenPage", "oddPage", None}

def _segment_body_sections(doc) -> list[dict]:
    """Bagi body menjadi segmen-segmen section berdasarkan inline sectPr.

    Setiap segmen = sekumpulan body children sampai (termasuk) paragraf yang
    membawa inline sectPr; segmen terakhir ditutup oleh final body sectPr.

    Return list of dict per section:
      {nonempty, empty, tables, drawings, sec_type, cols}
    sec_type diambil dari w:type pada sectPr yang menutup section tsb
    (None == default == nextPage).
    """
    body = doc._element.body
    segments: list[dict] = []
    cur = {"nonempty": 0, "empty": 0, "tables": 0, "drawings": 0}

    def _sectpr_meta(sectpr):
        if sectpr is None:
            return None, 1
        t = sectpr.find(qn("w:type"))
        tval = t.get(qn("w:val")) if t is not None else None
        cols = sectpr.find(qn("w:cols"))
        cnum = 1
        if cols is not None:
            try:
                cnum = int(cols.get(qn("w:num"), "1") or "1")
            except (ValueError, TypeError):
                cnum = 1
        return tval, cnum

    def _flush(sectpr):
        tval, cnum = _sectpr_meta(sectpr)
        cur["sec_type"] = tval
        cur["cols"] = cnum
        segments.append(dict(cur))
        for k in ("nonempty", "empty", "tables", "drawings"):
            cur[k] = 0

    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            txt = "".join(
                t.text or "" for t in child.findall(f".//{qn('w:t')}")
            ).strip()
            n_draw = len(child.findall(f".//{qn('w:drawing')}"))
            cur["drawings"] += n_draw
            if txt:
                cur["nonempty"] += 1
            else:
                cur["empty"] += 1
            pPr = child.find(qn("w:pPr"))
            inline_sp = pPr.find(qn("w:sectPr")) if pPr is not None else None
            if inline_sp is not None:
                _flush(inline_sp)
        elif child.tag == qn("w:tbl"):
            cur["tables"] += 1
            cur["drawings"] += len(child.findall(f".//{qn('w:drawing')}"))

    # Segmen terakhir ditutup oleh final body sectPr (bukan inline)
    final_sp = body.find(qn("w:sectPr"))
    if cur["nonempty"] or cur["empty"] or cur["tables"] or final_sp is not None:
        _flush(final_sp)

    return segments


def _section_has_content(seg: dict) -> bool:
    """True jika section punya konten visual (text/table/drawing)."""
    return (
        seg.get("nonempty", 0) > 0
        or seg.get("tables", 0) > 0
        or seg.get("drawings", 0) > 0
    )


def audit_empty_sections(doc_orig, doc_out) -> AuditResult:
    """Deteksi blank page akibat konten body menumpuk di satu section.

    Dua sub-check:
    (1) Empty-section regression: section yang di ORIGINAL berisi konten
        (>= EMPTY_SECTION_MIN_ORIG_PARAS paragraf bertext, atau ada tabel/
        gambar) TAPI di OUTPUT kosong total, DAN section break-nya
        page-breaking (nextPage/evenPage/oddPage/default) -> render blank page.
        Penalty MAYOR per section.
    (2) Content concentration: bila output punya >= 4 section dan
        >= CONTENT_CONCENTRATION_RATIO (85%) seluruh paragraf bertext numpuk
        di SATU section, sedangkan original menyebar konten ke banyak section.
        Penalty MAYOR sekali.
    """
    res = AuditResult()

    orig_segs = _segment_body_sections(doc_orig)
    out_segs = _segment_body_sections(doc_out)

    # (1) Empty-section regression
    blank_page_sections: list[dict] = []
    n = min(len(orig_segs), len(out_segs))
    for i in range(n):
        o = orig_segs[i]
        x = out_segs[i]
        orig_has = (
            o.get("nonempty", 0) >= EMPTY_SECTION_MIN_ORIG_PARAS
            or o.get("tables", 0) > 0
            or o.get("drawings", 0) > 0
        )
        out_empty = not _section_has_content(x)
        page_breaking = x.get("sec_type") in PAGE_BREAKING_SEC_TYPES
        if orig_has and out_empty and page_breaking:
            blank_page_sections.append({
                "section_idx": i,
                "orig_nonempty": o.get("nonempty", 0),
                "orig_tables": o.get("tables", 0),
                "sec_type": x.get("sec_type") or "default(nextPage)",
            })

    # (2) Content concentration
    out_nonempty_list = [s.get("nonempty", 0) for s in out_segs]
    total_nonempty = sum(out_nonempty_list)
    max_nonempty = max(out_nonempty_list) if out_nonempty_list else 0
    concentration = (max_nonempty / total_nonempty) if total_nonempty else 0.0
    orig_content_sections = sum(1 for s in orig_segs if _section_has_content(s))
    # PENTING: konsentrasi konten HANYA dianggap masalah kalau ia benar-benar
    # menghasilkan blank page (>=1 section kosong page-breaking). Tanpa gating
    # ini, banyak template sah (body 1-section + section title/header kecil)
    # ter-flag false-positive. Pattern asal: regression run 2026-05-30 di mana
    # IEEE/JNTETI/ULTIMACOMP/JDMLM ter-flag padahal 0 blank page.
    concentration_detected = (
        len(blank_page_sections) > 0
        and len(out_segs) >= 4
        and total_nonempty >= 10
        and concentration >= CONTENT_CONCENTRATION_RATIO
        and orig_content_sections >= 3
    )

    for bp in blank_page_sections:
        res.errors.append(
            f"BLANK PAGE: Section {bp['section_idx'] + 1} kosong total di output "
            f"(tipe break '{bp['sec_type']}' = halaman baru), padahal di template "
            f"original berisi konten ({bp['orig_nonempty']} paragraf bertext, "
            f"{bp['orig_tables']} tabel). Section ini akan dirender sebagai HALAMAN "
            f"KOSONG di Word."
        )

    if concentration_detected:
        max_idx = out_nonempty_list.index(max_nonempty)
        res.errors.append(
            f"KONTEN MENUMPUK: {concentration:.0%} paragraf body output ({max_nonempty}/"
            f"{total_nonempty}) menumpuk di Section {max_idx + 1} saja, sedangkan "
            f"template original menyebar konten ke {orig_content_sections} section. "
            f"Generator kemungkinan menyisipkan seluruh body ke satu titik "
            f"(mis. sectpr_paras[-1]) alih-alih menyebarkannya antar section."
        )

    res.info = {
        "n_orig_sections": len(orig_segs),
        "n_out_sections": len(out_segs),
        "blank_page_count": len(blank_page_sections),
        "blank_page_details": blank_page_sections,
        "content_concentration": round(concentration, 3),
        "concentration_detected": concentration_detected,
        "orig_content_sections": orig_content_sections,
        "out_nonempty_per_section": out_nonempty_list,
    }
    return res


# =============================================================================
# [7h] Blank Page & Section Break Waste Audit
# =============================================================================
# Mendeteksi:
# (1) Blank page: section dengan sectPr page-breaking (nextPage/even/odd/default)
#     yang TIDAK memiliki konten visual (no text, no tables, no drawings).
# (2) Section break waste: empty paragraph dengan sectPr di ekor body tanpa konten.

def _get_section_content_map(doc) -> list[dict]:
    """Bagi body per section (berdasarkan sectPr), return list of content flags.

    Each element: {has_text, has_table, has_drawing}
    """
    body = doc._element.body
    segments = []
    cur = {"has_text": False, "has_table": False, "has_drawing": False}

    for child in body.iterchildren():
        if child.tag == qn("w:sectPr"):
            segments.append(dict(cur))
            cur = {"has_text": False, "has_table": False, "has_drawing": False}
            continue
        if child.tag == qn("w:p"):
            txt = "".join(t.text or "" for t in child.findall(f".//{qn('w:t')}")).strip()
            if txt:
                cur["has_text"] = True
            if child.findall(f".//{qn('w:drawing')}"):
                cur["has_drawing"] = True
        elif child.tag == qn("w:tbl"):
            cur["has_table"] = True
            if child.findall(f".//{qn('w:drawing')}"):
                cur["has_drawing"] = True

    # Final segment
    segments.append(dict(cur))
    return segments


def _count_trailing_empty_sectpr_paras(doc) -> list[dict]:
    """Hitung paragraf kosong bersectPr yang dijejer di EKOR body.

    Return list of {child_idx, sectpr_type, has_text}.
    """
    body = doc._element.body
    children = list(body.iterchildren())
    result = []

    for child in reversed(children):
        if child.tag == qn("w:sectPr"):
            continue
        if child.tag != qn("w:p"):
            break
        pPr = child.find(qn("w:pPr"))
        if pPr is None:
            break
        sp = pPr.find(qn("w:sectPr"))
        if sp is None:
            break
        txt = "".join(t.text or "" for t in child.findall(f".//{qn('w:t')}")).strip()
        t = sp.find(qn("w:type"))
        tval = t.get(qn("w:val")) if t is not None else "default"
        result.append({
            "child_idx": list(body).index(child),
            "sectpr_type": tval,
            "has_text": bool(txt),
        })

    result.reverse()
    return result


def audit_blank_pages(doc_orig, doc_out) -> AuditResult:
    """Audit [7h]: Detect blank pages dan section break waste.

    (1) Blank page: section kosong total (no text/table/drawing) di output
        yang lebih banyak dari original.
    (2) Trailing sectPr waste: paragraf kosong bersectPr yang tidak perlu di ekor.
    """
    res = AuditResult()

    # (1) Blank pages
    out_segs = _get_section_content_map(doc_out)
    orig_segs = _get_section_content_map(doc_orig)

    out_empty = sum(1 for s in out_segs if not any(s.values()))
    orig_empty = sum(1 for s in orig_segs if not any(s.values()))
    extra_empty = max(0, out_empty - orig_empty)

    blank_page_errors = []
    if extra_empty > 0:
        for i, s in enumerate(out_segs):
            if not any(s.values()):
                blank_page_errors.append(
                    f"BLANK PAGE: Section {i + 1} kosong total di output "
                    f"(tidak ada text, tabel, atau gambar). "
                    f"Halaman ini berpotensi menjadi HALAMAN KOSONG di Word."
                )
        # Only report extra (not already in orig)
        for err in blank_page_errors[:extra_empty]:
            res.errors.append(err)

    # (2) Trailing sectPr waste - only flag EMPTY sectPr paras (has_text=False).
    # A sectPr para with text content is a legitimate section boundary.
    out_waste = _count_trailing_empty_sectpr_paras(doc_out)
    orig_waste = _count_trailing_empty_sectpr_paras(doc_orig)
    out_waste_empty = [w for w in out_waste if not w["has_text"]]
    orig_waste_empty = [w for w in orig_waste if not w["has_text"]]

    extra_waste = max(0, len(out_waste_empty) - len(orig_waste_empty))
    if extra_waste > 0:
        for wd in out_waste_empty[:extra_waste]:
            res.errors.append(
                f"SECTPR WASTE: Paragraf kosong dengan section break tidak perlu "
                f"di ekor body (sectPr type={wd['sectpr_type']}, "
                f"child_idx={wd['child_idx']}). "
                f"Ini waste space/structure tanpa menghasilkan konten."
            )

    res.info = {
        "out_empty_sections": out_empty,
        "orig_empty_sections": orig_empty,
        "extra_empty": extra_empty,
        "out_trailing_waste": len(out_waste_empty),
        "orig_trailing_waste": len(orig_waste_empty),
        "extra_waste": extra_waste,
    }
    return res


# =============================================================================
# [7e] Level 1: Structural Position Audit (MAYOR -15 per mismatch)
# =============================================================================
# Deteksi drawing dekoratif (logo/masthead) yang di ORIGINAL berada di section
# N-kolom tertentu TAPI di OUTPUT pindah ke section dengan jumlah kolom berbeda.
# Ini menangkap bug destruktif: masthead di section 1-kolom pindah ke section
# 2-kolom -> masthead gepeng, atau body content di section 2-kolom pindah ke
# section 1-kolom -> render 1 kolom (padahal harusnya 2).
#
# Strategi: scan SEMUA body children, catat section-index dan cols untuk setiap
# drawing (blip ber-rId dekoratif ATAU shape-only di region dekoratif).
# Bandingkan mapping orig vs output.

def _map_drawings_to_sections(doc) -> list[dict]:
    """Peta setiap drawing di body ke (section_idx, cols, child_idx).

    Return list of dict:
      {drawing_idx, section_idx, cols, child_idx, has_blip, rids, is_shape_only}
    section_idx = index segmen section (0-based) tempat drawing berada.
    child_idx = index child di body (0-based) untuk identifikasi posisi.
    """
    body = doc._element.body
    results = []
    section_idx = 0
    drawing_idx = 0

    def _process_element(el, child_idx, section_idx, drawing_idx):
        drawings = el.findall(f".//{qn('w:drawing')}")
        for d in drawings:
            rids = set()
            for blip in d.findall(f".//{{{DRAWING_NS}}}blip"):
                rid = blip.get(f"{{{R_NS}}}embed")
                if rid:
                    rids.add(rid)
            has_blip = bool(rids)
            is_shape_only = not has_blip

            cols = 1
            sp = None
            pPr = el.find(qn("w:pPr")) if el.tag == qn("w:p") else None
            if pPr is not None:
                sp = pPr.find(qn("w:sectPr"))
            if sp is not None:
                cols_el = sp.find(qn("w:cols"))
                if cols_el is not None:
                    try:
                        cols = int(cols_el.get(qn("w:num"), "1") or "1")
                    except (ValueError, TypeError):
                        pass

            results.append({
                "drawing_idx": drawing_idx,
                "section_idx": section_idx,
                "cols": cols,
                "child_idx": child_idx,
                "has_blip": has_blip,
                "rids": rids,
                "is_shape_only": is_shape_only,
            })
            drawing_idx += 1
        return drawing_idx

    final_sectPr = body.find(qn("w:sectPr"))

    for child_idx, child in enumerate(body.iterchildren()):
        if child.tag == qn("w:sectPr"):
            continue

        if child.tag == qn("w:p"):
            drawing_idx = _process_element(child, child_idx, section_idx, drawing_idx)
            pPr = child.find(qn("w:pPr"))
            if pPr is not None and pPr.find(qn("w:sectPr")) is not None:
                section_idx += 1
        elif child.tag == qn("w:tbl"):
            drawing_idx = _process_element(child, child_idx, section_idx, drawing_idx)

    return results


def _get_section_cols_map(doc) -> list[int]:
    """Return list cols per section: [1, 2, 2, 1, ...] dari sectPr inline + final."""
    body = doc._element.body
    cols_map = []

    def _cols_from_sectpr(sp):
        if sp is None:
            return 1
        c = sp.find(qn("w:cols"))
        if c is None:
            return 1
        try:
            return int(c.get(qn("w:num"), "1") or "1")
        except (ValueError, TypeError):
            return 1

    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            pPr = child.find(qn("w:pPr"))
            if pPr is not None:
                sp = pPr.find(qn("w:sectPr"))
                if sp is not None:
                    cols_map.append(_cols_from_sectpr(sp))

    final_sp = body.find(qn("w:sectPr"))
    cols_map.append(_cols_from_sectpr(final_sp))

    return cols_map


def audit_structural_position(doc_orig, doc_out) -> AuditResult:
    """Level 1: Cek drawing dekoratif (logo/masthead) di section yang benar.

    Aturan:
    - Drawing dekoratif di original section N-cols HARUS berada di output
      section dengan jumlah kolom YANG SAMA.
    - Jika logo di original section 1-kolom, tapi di output ada di section
      2-kolom -> MAYOR penalty (masthead gepeng / konten salah layout).
    - Juga cek konten body: jika original punya drawing konten (non-dekoratif)
      di section 2-kolom, tapi output ada di section 1-kolom -> MAYOR penalty
      (body ter-render 1 kolom).

    Matching: gunakan decorative_rIds untuk klasifikasi dekoratif vs konten.
    Shape-only drawings di region dekoratif (5 paragraf + 5 tabel pertama)
    juga dianggap dekoratif.
    """
    res = AuditResult()

    orig_section_cols = _get_section_cols_map(doc_orig)
    out_section_cols = _get_section_cols_map(doc_out)
    decorative_rids = _get_template_decorative_rids(doc_orig)

    orig_drawings = _map_drawings_to_sections(doc_orig)
    out_drawings = _map_drawings_to_sections(doc_out)

    shape_decorative_orig = _count_decorative_shape_drawings(doc_orig)

    def _is_decorative(d):
        if d["rids"] & decorative_rids:
            return True
        if d["is_shape_only"] and d["child_idx"] <= 5:
            return True
        return False

    # --- Cek 1: Dekoratif (logo) di section dengan kolom beda ---
    # Kumpulkan semua drawing dekoratif di original, catat section cols-nya.
    orig_deco_by_cols = {}
    for d in orig_drawings:
        if _is_decorative(d):
            cols = d["cols"]
            if cols not in orig_deco_by_cols:
                orig_deco_by_cols[cols] = []
            orig_deco_by_cols[cols].append(d)

    # Kumpulkan drawing dekoratif di output
    out_deco_by_cols = {}
    for d in out_drawings:
        if _is_decorative(d):
            cols = d["cols"]
            if cols not in out_deco_by_cols:
                out_deco_by_cols[cols] = []
            out_deco_by_cols[cols].append(d)

    deco_mismatches = []
    orig_deco_cols_set = set(orig_deco_by_cols.keys())
    out_deco_cols_set = set(out_deco_by_cols.keys())

    # Jika original punya dekoratif di section N-kolom tapi output TIDAK punya
    # dekoratif di section N-kolom (dan output punya di section lain) -> mismatch
    for cols_key in orig_deco_cols_set:
        if cols_key not in out_deco_cols_set and out_deco_cols_set:
            orig_count = len(orig_deco_by_cols[cols_key])
            out_other_sections = {k: len(v) for k, v in out_deco_by_cols.items() if k != cols_key}
            deco_mismatches.append({
                "kind": "decorative_cols_mismatch",
                "orig_cols": cols_key,
                "orig_count": orig_count,
                "out_other_sections": out_other_sections,
            })

    # --- Cek 2: Konten (non-dekoratif) di section dengan kolom beda ---
    orig_content_by_cols = {}
    for d in orig_drawings:
        if not _is_decorative(d):
            cols = d["cols"]
            if cols not in orig_content_by_cols:
                orig_content_by_cols[cols] = []
            orig_content_by_cols[cols].append(d)

    out_content_by_cols = {}
    for d in out_drawings:
        if not _is_decorative(d):
            cols = d["cols"]
            if cols not in out_content_by_cols:
                out_content_by_cols[cols] = []
            out_content_by_cols[cols].append(d)

    content_mismatches = []
    orig_content_cols_set = set(orig_content_by_cols.keys())
    out_content_cols_set = set(out_content_by_cols.keys())

    for cols_key in orig_content_cols_set:
        if cols_key not in out_content_cols_set and out_content_cols_set:
            orig_count = len(orig_content_by_cols[cols_key])
            out_other_sections = {k: len(v) for k, v in out_content_by_cols.items() if k != cols_key}
            content_mismatches.append({
                "kind": "content_cols_mismatch",
                "orig_cols": cols_key,
                "orig_count": orig_count,
                "out_other_sections": out_other_sections,
            })

    # --- Cek 3: Drawing dekoratif di section index berbeda secara signifikan ---
    # Jika original punya dekoratif hanya di section idx 0, tapi output punya
    # dekoratif di section idx >= 2 -> kemungkinan pindah section
    orig_deco_sections = sorted(set(
        d["section_idx"] for d in orig_drawings if _is_decorative(d)
    ))
    out_deco_sections = sorted(set(
        d["section_idx"] for d in out_drawings if _is_decorative(d)
    ))

    section_shift_violations = []
    if orig_deco_sections and out_deco_sections:
        orig_min_sec = min(orig_deco_sections)
        orig_max_sec = max(orig_deco_sections)
        out_min_sec = min(out_deco_sections)
        out_max_sec = max(out_deco_sections)

        if orig_max_sec <= 1 and out_max_sec > orig_max_sec + 1:
            section_shift_violations.append({
                "kind": "decorative_section_shift",
                "detail": f"Dekoratif original di section 0-{orig_max_sec}, output di section 0-{out_max_sec}",
                "orig_range": (orig_min_sec, orig_max_sec),
                "out_range": (out_min_sec, out_max_sec),
            })

    # --- Build errors ---
    for mm in deco_mismatches:
        out_info = ", ".join(f"{k}-kolom: {v}" for k, v in mm["out_other_sections"].items())
        res.errors.append(
            f"LOGO SECTION MISMATCH: {mm['orig_count']} drawing dekoratif (logo/masthead) "
            f"di original berada di section {mm['orig_cols']}-kolom, tapi di output "
            f"tidak ada dekoratif di section {mm['orig_cols']}-kolom. "
            f"Output dekoratif berada di: {out_info}. "
            f"Masthead/logo mungkin pindah ke section dengan layout kolom berbeda."
        )

    for mm in content_mismatches:
        out_info = ", ".join(f"{k}-kolom: {v}" for k, v in mm["out_other_sections"].items())
        res.errors.append(
            f"CONTENT SECTION MISMATCH: {mm['orig_count']} drawing konten "
            f"di original berada di section {mm['orig_cols']}-kolom, tapi di output "
            f"tidak ada konten di section {mm['orig_cols']}-kolom. "
            f"Output konten berada di: {out_info}. "
            f"Gambar konten mungkin ter-render di section dengan layout kolom berbeda."
        )

    for sv in section_shift_violations:
        res.errors.append(
            f"DECORATIVE SECTION SHIFT: Drawing dekoratif (logo/masthead) bergeser "
            f"ke section yang lebih jauh dari original. {sv['detail']}. "
            f"Kemungkinan masthead pindah ke zona body 2-kolom."
        )

    res.info = {
        "orig_section_cols": orig_section_cols,
        "out_section_cols": out_section_cols,
        "orig_total_drawings": len(orig_drawings),
        "out_total_drawings": len(out_drawings),
        "orig_deco_by_cols": {k: len(v) for k, v in orig_deco_by_cols.items()},
        "out_deco_by_cols": {k: len(v) for k, v in out_deco_by_cols.items()},
        "orig_content_by_cols": {k: len(v) for k, v in orig_content_by_cols.items()},
        "out_content_by_cols": {k: len(v) for k, v in out_content_by_cols.items()},
        "deco_mismatches": len(deco_mismatches),
        "content_mismatches": len(content_mismatches),
        "section_shift_violations": len(section_shift_violations),
    }
    return res


# =============================================================================
# [7f] Level 2: Anchor Position Audit (MINOR -5 per mismatch)
# =============================================================================
# Baca property anchor dari wp:anchor di dalam w:drawing:
#   - wp:positionH (relativeFrom + offset)
#   - wp:positionV (relativeFrom + offset)
#   - wp:extent (cx, cy dalam EMU)
#   - wp:effectExtent
# Bandingkan original vs output. Perbedaan offset melampaui toleransi = penalty.

WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def _extract_anchor_props(drawing_el) -> dict | None:
    """Ekstrak property anchor dari <wp:anchor> di dalam <w:drawing>.

    Return dict dengan keys:
      {horiz_relative, horiz_offset, vert_relative, vert_offset,
       extent_cx, extent_cy, simplePos_x, simplePos_y}
    atau None jika drawing menggunakan inline (wp:inline) bukan anchor.
    """
    anchor = drawing_el.find(f"{{{WP_NS}}}anchor")
    if anchor is None:
        inline = drawing_el.find(f"{{{WP_NS}}}inline")
        if inline is not None:
            return {"mode": "inline"}
        return None

    props = {"mode": "anchor"}

    pos_h = anchor.find(f"{{{WP_NS}}}positionH")
    if pos_h is not None:
        rel = pos_h.get("relativeFrom")
        props["horiz_relative"] = rel
        off_el = pos_h.find(f"{{{WP_NS}}}posOffset")
        if off_el is not None and off_el.text:
            try:
                props["horiz_offset"] = int(off_el.text)
            except (ValueError, TypeError):
                pass

    pos_v = anchor.find(f"{{{WP_NS}}}positionV")
    if pos_v is not None:
        rel = pos_v.get("relativeFrom")
        props["vert_relative"] = rel
        off_el = pos_v.find(f"{{{WP_NS}}}posOffset")
        if off_el is not None and off_el.text:
            try:
                props["vert_offset"] = int(off_el.text)
            except (ValueError, TypeError):
                pass

    extent = anchor.find(f"{{{WP_NS}}}extent")
    if extent is not None:
        try:
            props["extent_cx"] = int(extent.get("cx", "0"))
        except (ValueError, TypeError):
            pass
        try:
            props["extent_cy"] = int(extent.get("cy", "0"))
        except (ValueError, TypeError):
            pass

    simple_pos = anchor.find(f"{{{WP_NS}}}simplePos")
    if simple_pos is not None:
        x_el = simple_pos.find(f"{{{WP_NS}}}x")
        y_el = simple_pos.find(f"{{{WP_NS}}}y")
        if x_el is not None and x_el.text:
            try:
                props["simplePos_x"] = int(x_el.text)
            except (ValueError, TypeError):
                pass
        if y_el is not None and y_el.text:
            try:
                props["simplePos_y"] = int(y_el.text)
            except (ValueError, TypeError):
                pass

    return props


def _collect_drawing_anchors(doc) -> list[dict]:
    """Kumpulkan anchor info untuk semua drawing di body.

    Return list of {child_idx, drawing_idx, anchor_props, rids, is_shape_only}.
    """
    body = doc._element.body
    results = []
    drawing_idx = 0

    for child_idx, child in enumerate(body.iterchildren()):
        if child.tag not in (qn("w:p"), qn("w:tbl")):
            continue

        for d in child.findall(f".//{qn('w:drawing')}"):
            rids = set()
            for blip in d.findall(f".//{{{DRAWING_NS}}}blip"):
                rid = blip.get(f"{{{R_NS}}}embed")
                if rid:
                    rids.add(rid)

            anchor_props = _extract_anchor_props(d)

            results.append({
                "child_idx": child_idx,
                "drawing_idx": drawing_idx,
                "anchor_props": anchor_props,
                "rids": rids,
                "is_shape_only": not bool(rids),
            })
            drawing_idx += 1

    return results


def audit_anchor_position(doc_orig, doc_out) -> AuditResult:
    """Level 2: Bandingkan anchor position drawing dekoratif orig vs output.

    Hanya membandingkan drawing dekoratif (logo/masthead) yang bisa di-identify
    via rId match antara original dan output. Drawing tanpa blip (shape-only)
    di-match berdasarkan urutan relatif di region dekoratif.

    Perbedaan yang di-cek:
    - horiz_relative / vert_relative berbeda (margin vs page vs column dll)
    - horiz_offset / vert_offset meleset melampaui toleransi EMU
    - extent_cx / extent_cy meleset melampaui toleransi EMU
    - Mode berbeda (anchor vs inline)
    """
    res = AuditResult()

    decorative_rids = _get_template_decorative_rids(doc_orig)
    orig_anchors = _collect_drawing_anchors(doc_orig)
    out_anchors = _collect_drawing_anchors(doc_out)

    # Filter hanya dekoratif
    orig_deco = [a for a in orig_anchors if a["rids"] & decorative_rids or
                 (a["is_shape_only"] and a["child_idx"] <= 5)]
    out_deco = [a for a in out_anchors if a["rids"] & decorative_rids or
                (a["is_shape_only"] and a["child_idx"] <= 5)]

    # Match by rId untuk drawing ber-blip
    rid_mismatches = []
    for oa in orig_deco:
        if not oa["rids"]:
            continue
        matching_out = [ma for ma in out_deco if ma["rids"] & oa["rids"]]
        for ma in matching_out:
            orig_props = oa["anchor_props"]
            out_props = ma["anchor_props"]
            if orig_props is None or out_props is None:
                continue

            issues = []

            if orig_props.get("mode") != out_props.get("mode"):
                issues.append(f"mode: {orig_props.get('mode')} -> {out_props.get('mode')}")

            if orig_props.get("horiz_relative") != out_props.get("horiz_relative"):
                issues.append(
                    f"horiz_relativeFrom: {orig_props.get('horiz_relative')} -> "
                    f"{out_props.get('horiz_relative')}"
                )

            if orig_props.get("vert_relative") != out_props.get("vert_relative"):
                issues.append(
                    f"vert_relativeFrom: {orig_props.get('vert_relative')} -> "
                    f"{out_props.get('vert_relative')}"
                )

            for offset_key in ("horiz_offset", "vert_offset"):
                ov = orig_props.get(offset_key)
                nv = out_props.get(offset_key)
                if ov is not None and nv is not None:
                    if abs(ov - nv) > ANCHOR_OFFSET_TOLERANCE_EMU:
                        issues.append(f"{offset_key}: {ov} -> {nv} (diff={abs(ov-nv)} EMU)")

            for size_key in ("extent_cx", "extent_cy"):
                ov = orig_props.get(size_key)
                nv = out_props.get(size_key)
                if ov is not None and nv is not None:
                    if abs(ov - nv) > ANCHOR_OFFSET_TOLERANCE_EMU:
                        issues.append(f"{size_key}: {ov} -> {nv} (diff={abs(ov-nv)} EMU)")

            if issues:
                rid_mismatches.append({
                    "rId": sorted(oa["rids"] & decorative_rids),
                    "orig_child_idx": oa["child_idx"],
                    "out_child_idx": ma["child_idx"],
                    "issues": issues,
                })

    # Match by index untuk shape-only (tanpa rId)
    shape_mismatches = []
    orig_shape_only = [a for a in orig_deco if a["is_shape_only"]]
    out_shape_only = [a for a in out_deco if a["is_shape_only"]]
    for i in range(min(len(orig_shape_only), len(out_shape_only))):
        orig_props = orig_shape_only[i]["anchor_props"]
        out_props = out_shape_only[i]["anchor_props"]
        if orig_props is None or out_props is None:
            continue

        issues = []

        if orig_props.get("mode") != out_props.get("mode"):
            issues.append(f"mode: {orig_props.get('mode')} -> {out_props.get('mode')}")

        for key in ("horiz_relative", "vert_relative"):
            if orig_props.get(key) != out_props.get(key):
                issues.append(f"{key}: {orig_props.get(key)} -> {out_props.get(key)}")

        for offset_key in ("horiz_offset", "vert_offset"):
            ov = orig_props.get(offset_key)
            nv = out_props.get(offset_key)
            if ov is not None and nv is not None:
                if abs(ov - nv) > ANCHOR_OFFSET_TOLERANCE_EMU:
                    issues.append(f"{offset_key}: {ov} -> {nv} (diff={abs(ov-nv)} EMU)")

        for size_key in ("extent_cx", "extent_cy"):
            ov = orig_props.get(size_key)
            nv = out_props.get(size_key)
            if ov is not None and nv is not None:
                if abs(ov - nv) > ANCHOR_OFFSET_TOLERANCE_EMU:
                    issues.append(f"{size_key}: {ov} -> {nv} (diff={abs(ov-nv)} EMU)")

        if issues:
            shape_mismatches.append({
                "shape_idx": i,
                "orig_child_idx": orig_shape_only[i]["child_idx"],
                "out_child_idx": out_shape_only[i]["child_idx"],
                "issues": issues,
            })

    # Build errors
    for mm in rid_mismatches:
        issues_str = "; ".join(mm["issues"])
        res.errors.append(
            f"ANCHOR POSITION MISMATCH: Drawing rId {mm['rId']} anchor berubah. "
            f"Orig child#{mm['orig_child_idx']} vs Out child#{mm['out_child_idx']}. "
            f"Issues: {issues_str}"
        )

    for mm in shape_mismatches:
        issues_str = "; ".join(mm["issues"])
        res.errors.append(
            f"ANCHOR POSITION MISMATCH: Shape-only #{mm['shape_idx']} anchor berubah. "
            f"Orig child#{mm['orig_child_idx']} vs Out child#{mm['out_child_idx']}. "
            f"Issues: {issues_str}"
        )

    res.info = {
        "orig_deco_count": len(orig_deco),
        "out_deco_count": len(out_deco),
        "rid_mismatches": len(rid_mismatches),
        "shape_mismatches": len(shape_mismatches),
        "tolerance_emu": ANCHOR_OFFSET_TOLERANCE_EMU,
    }
    return res


# =============================================================================
# [7g] Level 3: Container Context Audit (MINOR -5 per mismatch)
# =============================================================================
# Cek bahwa drawing dekoratif (logo/masthead) berada di CONTAINER yang sama
# relatif terhadap template original. Container = paragraf index atau
# tabel (table_index, row, col). Jika logo di original di paragraf #2 tapi
# di output di paragraf #20 -> kemungkinan pindah posisi.

def _map_drawings_to_containers(doc, decorative_rids: set[str] | None = None) -> list[dict]:
    """Peta setiap drawing ke container-nya di body.

    Container types:
    - "paragraph": drawing di paragraf langsung di body, container = para_idx
    - "table_cell": drawing di dalam tabel, container = (table_idx, row, col)

    Return list of {drawing_idx, container_type, container_key, rids,
                    is_shape_only, child_idx}
    """
    body = doc._element.body
    decorative_rids = decorative_rids or set()
    results = []
    drawing_idx = 0
    para_idx = 0
    table_idx = 0

    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            drawings = child.findall(f".//{qn('w:drawing')}")
            for d in drawings:
                rids = set()
                for blip in d.findall(f".//{{{DRAWING_NS}}}blip"):
                    rid = blip.get(f"{{{R_NS}}}embed")
                    if rid:
                        rids.add(rid)
                results.append({
                    "drawing_idx": drawing_idx,
                    "container_type": "paragraph",
                    "container_key": para_idx,
                    "rids": rids,
                    "is_shape_only": not bool(rids),
                    "child_idx": para_idx,
                })
                drawing_idx += 1
            para_idx += 1

        elif child.tag == qn("w:tbl"):
            for ri, row in enumerate(child.findall(qn("w:tr"))):
                for ci, cell in enumerate(row.findall(qn("w:tc"))):
                    for para in cell.findall(f".//{qn('w:p')}"):
                        drawings = para.findall(f".//{qn('w:drawing')}")
                        for d in drawings:
                            rids = set()
                            for blip in d.findall(f".//{{{DRAWING_NS}}}blip"):
                                rid = blip.get(f"{{{R_NS}}}embed")
                                if rid:
                                    rids.add(rid)
                            results.append({
                                "drawing_idx": drawing_idx,
                                "container_type": "table_cell",
                                "container_key": (table_idx, ri, ci),
                                "rids": rids,
                                "is_shape_only": not bool(rids),
                                "child_idx": para_idx,
                            })
                            drawing_idx += 1
            table_idx += 1

    return results


def audit_container_context(doc_orig, doc_out) -> AuditResult:
    """Level 3: Cek drawing dekoratif di container yang sama.

    Aturan:
    - Drawing dekoratif ber-blip: match via rId, cek container_type sama
      dan container_index berdekatan (toleransi <= CONTAINER_INDEX_TOLERANCE).
    - Drawing dekoratif shape-only: match via urutan relatif di region
      dekoratif, cek container_type dan index berdekatan.

    Perbedaan container_type (paragraph vs table_cell) = otomatis mismatch.
    Perbedaan index melampaui toleransi = position drift.
    """
    res = AuditResult()

    decorative_rids = _get_template_decorative_rids(doc_orig)
    orig_map = _map_drawings_to_containers(doc_orig, decorative_rids)
    out_map = _map_drawings_to_containers(doc_out, decorative_rids)

    # Filter dekoratif
    def _is_deco(d):
        if d["rids"] & decorative_rids:
            return True
        if d["is_shape_only"] and d["child_idx"] <= 5:
            return True
        return False

    orig_deco = [d for d in orig_map if _is_deco(d)]
    out_deco = [d for d in out_map if _is_deco(d)]

    # --- Cek 1: rId-based matching ---
    rid_violations = []
    for od in orig_deco:
        if not od["rids"]:
            continue
        matching = [md for md in out_deco if md["rids"] & od["rids"]]
        for md in matching:
            if od["container_type"] != md["container_type"]:
                rid_violations.append({
                    "rId": sorted(od["rids"] & decorative_rids),
                    "issue": "container_type_changed",
                    "orig_type": od["container_type"],
                    "out_type": md["container_type"],
                    "orig_key": od["container_key"],
                    "out_key": md["container_key"],
                })
            elif od["container_type"] == "paragraph":
                diff = abs(od["container_key"] - md["container_key"])
                if diff > CONTAINER_INDEX_TOLERANCE:
                    rid_violations.append({
                        "rId": sorted(od["rids"] & decorative_rids),
                        "issue": "paragraph_index_drift",
                        "orig_idx": od["container_key"],
                        "out_idx": md["container_key"],
                        "diff": diff,
                    })
            elif od["container_type"] == "table_cell":
                orig_t, orig_r, orig_c = od["container_key"]
                out_t, out_r, out_c = md["container_key"]
                if orig_t != out_t:
                    rid_violations.append({
                        "rId": sorted(od["rids"] & decorative_rids),
                        "issue": "table_index_changed",
                        "orig_table": orig_t,
                        "out_table": out_t,
                    })

    # --- Cek 2: Shape-only order matching ---
    shape_violations = []
    orig_shape = [d for d in orig_deco if d["is_shape_only"]]
    out_shape = [d for d in out_deco if d["is_shape_only"]]
    for i in range(min(len(orig_shape), len(out_shape))):
        od = orig_shape[i]
        md = out_shape[i]
        if od["container_type"] != md["container_type"]:
            shape_violations.append({
                "shape_idx": i,
                "issue": "container_type_changed",
                "orig_type": od["container_type"],
                "out_type": md["container_type"],
            })
        elif od["container_type"] == "paragraph":
            diff = abs(od["container_key"] - md["container_key"])
            if diff > CONTAINER_INDEX_TOLERANCE:
                shape_violations.append({
                    "shape_idx": i,
                    "issue": "paragraph_index_drift",
                    "orig_idx": od["container_key"],
                    "out_idx": md["container_key"],
                    "diff": diff,
                })

    # Build errors
    for v in rid_violations:
        issue = v["issue"]
        if issue == "container_type_changed":
            res.errors.append(
                f"CONTAINER CONTEXT: Drawing rId {v['rId']} pindah container. "
                f"Original: {v['orig_type']} (key={v['orig_key']}), "
                f"Output: {v['out_type']} (key={v['out_key']}). "
                f"Logo/masthead tidak lagi di tempat yang sama."
            )
        elif issue == "paragraph_index_drift":
            res.errors.append(
                f"CONTAINER DRIFT: Drawing rId {v['rId']} bergeser paragraf. "
                f"Original para#{v['orig_idx']} -> Output para#{v['out_idx']} "
                f"(diff={v['diff']}, tolerance={CONTAINER_INDEX_TOLERANCE}). "
                f"Posisi logo/masthead mungkin bergeser visual."
            )
        elif issue == "table_index_changed":
            res.errors.append(
                f"CONTAINER TABLE CHANGE: Drawing rId {v['rId']} pindah tabel. "
                f"Original table#{v['orig_table']} -> Output table#{v['out_table']}. "
                f"Logo tidak lagi di tabel yang sama."
            )

    for v in shape_violations:
        issue = v["issue"]
        if issue == "container_type_changed":
            res.errors.append(
                f"CONTAINER CONTEXT: Shape-only #{v['shape_idx']} pindah container. "
                f"Original: {v['orig_type']}, Output: {v['out_type']}."
            )
        elif issue == "paragraph_index_drift":
            res.errors.append(
                f"CONTAINER DRIFT: Shape-only #{v['shape_idx']} bergeser paragraf. "
                f"Original para#{v['orig_idx']} -> Output para#{v['out_idx']} "
                f"(diff={v['diff']}, tolerance={CONTAINER_INDEX_TOLERANCE})."
            )

    res.info = {
        "orig_deco_count": len(orig_deco),
        "out_deco_count": len(out_deco),
        "rid_violations": len(rid_violations),
        "shape_violations": len(shape_violations),
        "container_index_tolerance": CONTAINER_INDEX_TOLERANCE,
    }
    return res


# =============================================================================
# [8] Anomaly Detector (Heuristik visual, NON-SCORING)
# =============================================================================
# Catatan filosofi: deteksi anomali ini berjalan TERPISAH dari kalkulasi skor.
# Tujuannya menangkap kejanggalan visual yang lolos dari audit struktural -
# misal style "Heading 1" tiba-tiba jadi "Normal", muncul auto-numbering
# (numPr) tak diundang, atau font size yang di-hardcode di template direset.
ANOMALY_PARA_CHECK_COUNT = 30
STRICT_STYLE_FIRST_N = 10  # Strict style/font check pada 10 paragraf pertama


def _para_style_name(para):
    try:
        return (para.style.name if para.style else "Normal") or "Normal"
    except Exception:
        return "Normal"


def _para_has_numpr(para):
    """True jika paragraf punya <w:pPr><w:numPr> auto-numbering."""
    try:
        return bool(para._p.xpath("./w:pPr/w:numPr"))
    except Exception:
        return False


# ---- Double-numbering detection ---------------------------------------------
# Pola prefix angka manual yang umum di heading: '1. ', '1.1 ', '2.1.', dll.
MANUAL_NUMBER_PREFIX_REGEX = re.compile(r"^\s*\d+(?:\.\d+){0,3}\.?\s+\S")


def _styles_with_active_numpr(doc) -> set[str]:
    """Pindai styles.xml: kembalikan styleId yang MENGAKTIFKAN numbering
    (mengandung <w:numPr> dengan w:numId != '0' di pPr-nya).

    Style dengan numId='0' secara semantik OOXML berarti 'no numbering'
    (override eksplisit untuk mematikan inheritance), jadi tidak dianggap
    aktif."""
    active: set[str] = set()
    try:
        styles_part = doc.part.styles_element
    except Exception:
        try:
            styles_part = doc.styles.element
        except Exception:
            return active
    if styles_part is None:
        return active

    for st in styles_part.findall(qn("w:style")):
        style_id = st.get(qn("w:styleId"))
        if not style_id:
            continue
        numpr_list = st.findall(f".//{qn('w:pPr')}/{qn('w:numPr')}")
        for npr in numpr_list:
            num_id_el = npr.find(qn("w:numId"))
            if num_id_el is None:
                continue
            num_id_val = num_id_el.get(qn("w:val"))
            if num_id_val and num_id_val != "0":
                active.add(style_id)
                break
    return active


def _para_explicit_numpr_active(para) -> bool | None:
    """Periksa numPr EKSPLISIT di pPr paragraf:
       True  -> aktif (numId != 0),
       False -> dimatikan eksplisit (numId == 0),
       None  -> tidak ada numPr eksplisit (pakai inheritance dari style)."""
    try:
        npr_list = para._p.xpath("./w:pPr/w:numPr")
    except Exception:
        return None
    if not npr_list:
        return None
    npr = npr_list[0]
    num_id_el = npr.find(qn("w:numId"))
    if num_id_el is None:
        return True  # numPr ada tapi tanpa numId -> anggap aktif
    val = num_id_el.get(qn("w:val"))
    return bool(val) and val != "0"


def _para_style_id(para) -> str | None:
    """Ambil w:val dari <w:pPr><w:pStyle> paragraf (styleId, bukan display name)."""
    try:
        ps = para._p.xpath("./w:pPr/w:pStyle")
    except Exception:
        return None
    if not ps:
        return None
    return ps[0].get(qn("w:val"))


def _para_numbering_active(para, styles_with_numpr: set[str]) -> bool:
    """True jika paragraf akan render auto-numbering ketika dibuka di Word.

    Override eksplisit (numId=0 di pPr) > inheritance dari style."""
    explicit = _para_explicit_numpr_active(para)
    if explicit is True:
        return True
    if explicit is False:
        return False  # eksplisit dimatikan -> tidak akan render numbering
    style_id = _para_style_id(para)
    if style_id and style_id in styles_with_numpr:
        return True
    return False
# -----------------------------------------------------------------------------


def _para_first_run_size_hpt(para):
    """Ambil w:sz (half-points) dari run pertama yang punya rPr/sz.
    Return None jika tidak ada hardcoded size."""
    try:
        runs = para._p.xpath("./w:r")
    except Exception:
        return None
    for r in runs:
        sz_list = r.xpath("./w:rPr/w:sz")
        if sz_list:
            val = sz_list[0].get(qn("w:val"))
            try:
                return int(val)
            except (ValueError, TypeError):
                continue
    return None


def _para_snippet(para, n=70):
    txt = (para.text or "").strip()
    return txt[:n] + ("..." if len(txt) > n else "")


def _align_paragraph_pairs(orig_paras, out_paras):
    """Susun pasangan (orig_idx, out_idx) yang dianggap "paragraf yang sama"
    via sequence alignment pada nama style.

    Motif: gen.py mungkin meng-skip section instruksional template (mis.
    NOMENCLATURE / EXAMPLE / "Subdivision - numbered sections") karena
    paper user tidak punya konten tersebut. Kalau kita bandingkan paragraf
    by-index naif, mismatch di satu titik akan menggeser SEMUA paragraf
    sesudahnya dan memunculkan anomali palsu.

    Strategi: pakai difflib.SequenceMatcher pada urutan nama style untuk
    cari blok yang match (equal). Untuk blok 'replace' yang panjang
    SAMA di kedua sisi, kita tetap pasangkan - itulah skenario style
    benar-benar berubah. Blok 'insert' / 'delete' / 'replace asimetris'
    di-skip karena artinya struktur dokumen memang beda di lokasi itu.

    Return: list of (orig_idx, out_idx)."""
    a = [_para_style_name(p) for p in orig_paras]
    b = [_para_style_name(p) for p in out_paras]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    pairs: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                pairs.append((i1 + k, j1 + k))
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                pairs.append((i1 + k, j1 + k))
        # insert/delete/uneven replace -> skip; structural mismatch
    return pairs


def detect_anomalies(doc_original, doc_output,
                     n_check=ANOMALY_PARA_CHECK_COUNT,
                     n_strict=STRICT_STYLE_FIRST_N):
    """Bandingkan paragraf pertama original vs output untuk empat heuristik:
       (a) Perubahan nama style (strict pada n_strict pertama).
       (b) Auto-numbering (w:numPr) muncul di output padahal original tidak.
       (c) Font size hardcoded original berubah/hilang di output.
       (d) Double numbering: paragraf punya numbering aktif (eksplisit atau
           diwarisi dari style) DAN sekaligus prefix angka manual di teks
           (mis. style Heading1 yang berisi numPr -> render '1.', tapi teks
           juga mulai dengan '1.    INTRODUCTION' -> Word menampilkan
           '1. 1.    INTRODUCTION').

    Pasangan paragraf orig<->out di-align via difflib.SequenceMatcher pada
    style-sequence, supaya skip section instruksional (NOMENCLATURE,
    "Subdivision - numbered sections", dst.) yang ada di template asli
    tetapi tidak relevan di paper user - tidak menggeser idx pasangan
    sesudahnya.

    Return: list of dict berisi temuan kejanggalan."""
    anomalies = []

    orig_paras = list(doc_original.paragraphs)[:n_check]
    out_paras = list(doc_output.paragraphs)[:n_check]

    # Cache styles yang aktif numbering - sekali per dokumen, dipakai di loop.
    out_active_styles = _styles_with_active_numpr(doc_output)

    pairs = _align_paragraph_pairs(orig_paras, out_paras)

    # Untuk DOUBLE_NUMBERING (check d) kita scan SEMUA paragraf output dalam
    # window n_check - tidak butuh pasangan ke original karena itu masalah
    # internal output (numPr aktif + prefix manual).
    flagged_double = set()
    for j, np_ in enumerate(out_paras):
        text_out = (np_.text or "").strip()
        if not text_out:
            continue
        if not _para_numbering_active(np_, out_active_styles):
            continue
        if MANUAL_NUMBER_PREFIX_REGEX.match(text_out):
            s_out = _para_style_name(np_)
            anomalies.append({
                "kind": "DOUBLE_NUMBERING",
                "severity": "STRICT",
                "para_index": j,
                "orig_style": "(n/a)",
                "out_style": s_out,
                "snippet": _para_snippet(np_),
                "message": (
                    f"Paragraf {j}: numbering ganda. Teks sudah "
                    f"mengandung prefix angka manual (\"{text_out[:30]}\"), "
                    f"tetapi paragraf juga akan auto-render nomor "
                    f"karena <w:numPr> aktif (eksplisit atau diwarisi "
                    f"dari style '{s_out}'). Word akan menampilkan "
                    f"angka dobel."
                ),
            })
            flagged_double.add(j)

    for orig_idx, out_idx in pairs:
        op = orig_paras[orig_idx]
        np_ = out_paras[out_idx]

        s_orig = _para_style_name(op)
        s_out = _para_style_name(np_)

        # (a) Style mismatch - strict di n_strict pertama, longgar setelahnya.
        #     Index referensi: pakai out_idx supaya laporan menunjuk paragraf
        #     yang user lihat di file output mereka.
        if s_orig != s_out:
            severity = "STRICT" if out_idx < n_strict else "INFO"
            anomalies.append({
                "kind": "STYLE_MISMATCH",
                "severity": severity,
                "para_index": out_idx,
                "orig_style": s_orig,
                "out_style": s_out,
                "snippet": _para_snippet(np_),
                "message": (
                    f"Paragraf {out_idx}: Style hilang/berubah dari "
                    f"'{s_orig}' menjadi '{s_out}'. "
                    f"Ini menyebabkan font dan spasi berantakan."
                ),
            })

        # (b) Spurious auto-numbering: output punya numPr, original tidak.
        if _para_has_numpr(np_) and not _para_has_numpr(op):
            anomalies.append({
                "kind": "SPURIOUS_NUMBERING",
                "severity": "STRICT",
                "para_index": out_idx,
                "orig_style": s_orig,
                "out_style": s_out,
                "snippet": _para_snippet(np_),
                "message": (
                    f"Paragraf {out_idx}: muncul tag <w:numPr> auto-numbering "
                    f"yang tidak ada di template asli."
                ),
            })

        # (c) Font size override - strict di n_strict pertama, supaya tidak
        #     ribut pada body biasa yang tidak hardcode size.
        if out_idx < n_strict:
            # Guard: skip jika konten paragraf sangat berbeda (likely beda paragraf
            # struktural yang ter-align salah). Tanpa guard ini, detect_anomalies
            # membandingkan font size antara paragraf yang tidak related (misal:
            # template journal header 8pt vs output paper title 14pt → false positive).
            orig_text_norm = (op.text or "").lower().strip()
            out_text_norm = (np_.text or "").lower().strip()

            skip_font_check = False
            if len(orig_text_norm) >= 4 and len(out_text_norm) >= 4:
                orig_words = set(re.findall(r"\b\w{3,}\b", orig_text_norm))
                out_words = set(re.findall(r"\b\w{3,}\b", out_text_norm))
                if orig_words and out_words:
                    overlap = len(orig_words & out_words)
                    union = len(orig_words | out_words)
                    jaccard = overlap / union if union else 0
                    if jaccard < 0.25:
                        # Content too different - skip font size comparison
                        skip_font_check = True

            if not skip_font_check:
                sz_orig = _para_first_run_size_hpt(op)
                sz_out = _para_first_run_size_hpt(np_)
                if sz_orig is not None and sz_out != sz_orig:
                    # Distinguish between empty paragraph (no runs) and 0pt font size
                    if sz_out is None or sz_out == 0:
                        # Check if paragraph has any runs
                        has_runs = len(np_.runs) > 0 if hasattr(np_, 'runs') else False
                        if not has_runs:
                            message = (
                                f"Paragraf {out_idx}: paragraf kosong (tidak ada runs). "
                                f"Template memiliki konten dengan font {sz_orig / 2:.1f}pt. "
                                f"Generator tidak mengisi konten paragraf ini."
                            )
                        else:
                            message = (
                                f"Paragraf {out_idx}: font size hardcoded berubah "
                                f"({sz_orig / 2:.1f}pt -> 0.0pt). "
                                f"Text menjadi invisible atau runs tidak punya font size."
                            )
                    else:
                        message = (
                            f"Paragraf {out_idx}: font size hardcoded berubah "
                            f"({sz_orig / 2:.1f}pt -> {sz_out / 2:.1f}pt). "
                            f"Override visual hilang."
                        )

                    anomalies.append({
                        "kind": "FONT_OVERRIDE",
                        "severity": "STRICT",
                        "para_index": out_idx,
                        "orig_style": s_orig,
                        "out_style": s_out,
                        "orig_sz_hpt": sz_orig,
                        "out_sz_hpt": sz_out,
                        "snippet": _para_snippet(np_),
                        "message": message,
                    })

    # Sort untuk laporan yang stabil & enak dibaca: by para_index, lalu kind.
    anomalies.sort(key=lambda a: (a["para_index"], a["kind"]))
    return anomalies


# -----------------------------------------------------------------------------
# Master Prompt builder: gabung temuan scoring + anomaly + template solusi
# -----------------------------------------------------------------------------
def _categorize_errors(multicol_res: AuditResult,
                       header_shape_res: AuditResult,
                       table_res: AuditResult,
                       sectpr_dist_res: AuditResult,
                       border_res: AuditResult,
                       anomalies: list[dict]) -> dict:
    """Kelompokkan temuan ke 6 kategori untuk pemetaan solusi gen.py:
       ERROR_KOLOM, ERROR_HEADER, ERROR_STYLE, ERROR_TABLE, ERROR_TABLE_BORDER, ERROR_SECTPR_DIST."""
    cats = {
        "ERROR_KOLOM": {"triggered": False, "details": []},
        "ERROR_HEADER": {"triggered": False, "details": []},
        "ERROR_STYLE": {"triggered": False, "details": []},
        "ERROR_TABLE": {"triggered": False, "details": []},
        "ERROR_TABLE_BORDER": {"triggered": False, "details": []},
        "ERROR_SECTPR_DIST": {"triggered": False, "details": []},
    }

    # ERROR_KOLOM: dari audit_multicolumn_xpath (FATAL XML)
    multicol_broken = multicol_res.info.get("broken", [])
    if multicol_broken:
        cats["ERROR_KOLOM"]["triggered"] = True
        for sec_idx, orig_n, out_n in multicol_broken:
            cats["ERROR_KOLOM"]["details"].append(
                f"Section {sec_idx}: {orig_n} kolom -> {out_n} kolom"
            )

    # ERROR_HEADER: dari audit_header_shapes_xpath (FATAL XML)
    if header_shape_res.info.get("fatal_hits", 0) > 0:
        cats["ERROR_HEADER"]["triggered"] = True
        for err in header_shape_res.errors:
            cats["ERROR_HEADER"]["details"].append(err)

    # ERROR_STYLE: dari anomaly detector
    style_kinds = {"STYLE_MISMATCH", "FONT_OVERRIDE",
                   "SPURIOUS_NUMBERING", "DOUBLE_NUMBERING"}
    style_anomalies = [a for a in anomalies if a["kind"] in style_kinds]
    if style_anomalies:
        cats["ERROR_STYLE"]["triggered"] = True
        for a in style_anomalies:
            cats["ERROR_STYLE"]["details"].append(a["message"])

    # ERROR_TABLE: dari audit_table_count
    if table_res.errors:
        cats["ERROR_TABLE"]["triggered"] = True
        for err in table_res.errors:
            cats["ERROR_TABLE"]["details"].append(err)

    # ERROR_TABLE_BORDER: dari audit_table_borders
    invisible_count = border_res.info.get("invisible_count", 0)
    thin_count = border_res.info.get("thin_count", 0)
    if invisible_count > 0 or thin_count > 0:
        cats["ERROR_TABLE_BORDER"]["triggered"] = True
        if invisible_count > 0:
            cats["ERROR_TABLE_BORDER"]["details"].append(
                f"{invisible_count} tabel data tanpa border visible. "
                f"Indices: {border_res.info.get('invisible_indices', [])}"
            )
        if thin_count > 0:
            cats["ERROR_TABLE_BORDER"]["details"].append(
                f"{thin_count} tabel data dengan border terlalu tipis (sz < 4). "
                f"Indices: {border_res.info.get('thin_indices', [])}"
            )

    # ERROR_SECTPR_DIST: dari audit_sectpr_distribution
    if sectpr_dist_res.errors:
        cats["ERROR_SECTPR_DIST"]["triggered"] = True
        for err in sectpr_dist_res.errors:
            cats["ERROR_SECTPR_DIST"]["details"].append(err)

    return cats


# Template solusi per kategori. Placeholder `{gen_name}` akan di-resolve
# saat runtime dengan nama generator spesifik (mis. `DJLITgen.py`,
# `SAGEgen.py`) supaya prompt yang ditulis ke audit-unik_<NAMA>.txt
# menunjuk file yang benar -- bukan "gen.py" generik.
SOLUTION_TEMPLATES = {
    "ERROR_KOLOM": (
        "[SOLUSI UNTUK {gen_name} - LAYOUT KOLOM]\n"
        "Skrip `{gen_name}` saat ini merusak format multi-kolom karena "
        "menghapus Section Break. Tolong modifikasi `{gen_name}` agar "
        "memaksakan injeksi XML `<w:cols w:num='2'>` pada section artikel "
        "utama sebelum dokumen disave."
    ),
    "ERROR_HEADER": (
        "[SOLUSI UNTUK {gen_name} - HEADER SHAPES]\n"
        "Skrip `{gen_name}` saat ini tidak sengaja menimpa atau menghapus "
        "objek shape/textbox di Header. Tolong modifikasi `{gen_name}` agar "
        "operasi text-replacement HANYA menargetkan `doc.paragraphs` di "
        "Body, dan JANGAN menyentuh elemen di dalam "
        "`doc.sections[x].header`."
    ),
    "ERROR_STYLE": (
        "[SOLUSI UNTUK {gen_name} - STYLE PRESERVATION]\n"
        "Skrip `{gen_name}` saat ini mereset custom style (seperti judul) "
        "menjadi Normal. Tolong modifikasi `{gen_name}` agar saat melakukan "
        "`paragraph.text = new_text`, skrip harus MEMPERTAHANKAN "
        "`paragraph.style` dan meng-copy properti font dari `run` sebelumnya."
    ),
    "ERROR_TABLE": (
        "[SOLUSI UNTUK {gen_name} - TABLE LAYOUT CONTAINER]\n"
        "Jumlah tabel body output `{gen_name}` tidak match template "
        "original. Banyak template jurnal (mis. SAGE) menggunakan `<w:tbl>` "
        "sebagai container layout untuk figure/diagram side-by-side, kotak "
        "rules, atau highlight box -- bukan hanya tabel data. Tolong "
        "modifikasi `{gen_name}` supaya setiap blok figure/diagram fullwidth "
        "di-wrap dalam tabel 1-row container, dan blok rules/highlight juga "
        "pakai tabel mini, agar jumlah tabel body match template asli."
    ),
    "ERROR_TABLE_BORDER": (
        "[SOLUSI UNTUK {gen_name} - TABLE BORDER VISIBILITY]\n"
        "Tabel data di output `{gen_name}` tidak memiliki border yang tegas/visible, "
        "atau border-nya terlalu tipis sehingga sulit dilihat di Word. "
        "Tolong modifikasi `{gen_name}` agar setiap tabel data yang di-generate "
        "memiliki tblBorders dengan properti:\n"
        "  - val='single' (garis solid)\n"
        "  - sz='4' atau lebih (4 = 0.5pt, 8 = 1pt, 12 = 1.5pt)\n"
        "  - color='000000' (hitam) atau sesuai template\n"
        "Contoh kode python-docx:\n"
        "  from docx.oxml import OxmlElement\n"
        "  from docx.oxml.ns import qn\n"
        "  tbl = doc.add_table(rows=N, cols=M)\n"
        "  tblPr = tbl._element.find(qn('w:tblPr'))\n"
        "  if tblPr is None:\n"
        "      tblPr = OxmlElement('w:tblPr')\n"
        "      tbl._element.insert(0, tblPr)\n"
        "  tblBorders = OxmlElement('w:tblBorders')\n"
        "  for side in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:\n"
        "      border = OxmlElement(f'w:{{side}}')\n"
        "      border.set(qn('w:val'), 'single')\n"
        "      border.set(qn('w:sz'), '4')  # 0.5pt\n"
        "      border.set(qn('w:color'), '000000')\n"
        "      tblBorders.append(border)\n"
        "  tblPr.append(tblBorders)"
    ),
    "ERROR_SECTPR_DIST": (
        "[SOLUSI UNTUK {gen_name} - SECTPR DISTRIBUTION]\n"
        "Generator `{gen_name}` emit semua sectPr inline (section break) "
        "sebagai paragraf empty trailer di akhir body (pola flush-at-end). "
        "Distribusi total kolom terlihat sama dengan original sehingga "
        "audit_page_setup lulus, tapi visual layout multi-section hancur. "
        "Tolong modifikasi `{gen_name}` supaya sectPr inline DISEBARKAN di "
        "antara konten -- setiap kali konten beralih dari 2-kolom (body) ke "
        "1-kolom (figure/table fullwidth) dan kembali, attach sectPr inline "
        "ke pPr paragraf transisi yang sesuai. Jangan emit sectPr sebagai "
        "trailer empty."
    ),
}


def _resolve_gen_name(doc_name: str) -> str:
    """Resolve nama file generator spesifik untuk template ini.

    Konvensi: `<DOC_NAME>gen.py` di folder yang sama dengan auto_checker.
    Bila file tidak ditemukan, fallback ke konvensi nama tanpa verifikasi
    file system supaya prompt tetap ter-generate (auditor bisa jalan di
    direktori manapun)."""
    base_dir = Path(__file__).resolve().parent
    candidate = base_dir / f"{doc_name}gen.py"
    if candidate.exists():
        return candidate.name
    # Fallback: pakai konvensi <DOC_NAME>gen.py walau filenya belum ada.
    return f"{doc_name}gen.py"


def build_master_prompt(doc_name, template_name, output_name,
                        anomalies, multicol_res, header_shape_res,
                        table_res, border_res, sectpr_dist_res):
    """Susun konten audit-unik_<name>.txt: ringkasan kejanggalan +
    template solusi spesifik untuk generator per kategori error.

    Nama file generator (mis. `DJLITgen.py`, `SAGEgen.py`) di-resolve via
    `_resolve_gen_name(doc_name)` dan di-inject ke setiap SOLUTION_TEMPLATE
    sehingga prompt yang dihasilkan menunjuk file yang benar -- bukan
    "gen.py" generik."""
    bar = "=" * 60
    L = []
    add = L.append

    cats = _categorize_errors(multicol_res, header_shape_res,
                              table_res, sectpr_dist_res, border_res, anomalies)
    triggered = [k for k, v in cats.items() if v["triggered"]]
    gen_name = _resolve_gen_name(doc_name)

    # ── Banner judul ──
    add(bar)
    add(f"  MASTER PROMPT PERBAIKAN {gen_name.upper()} UNTUK TEMPLATE {doc_name.upper()}")
    add(bar)
    add(f"Template       : {template_name}")
    add(f"Output         : {output_name}")
    add(f"Generator      : {gen_name}")
    add(f"Total anomali  : {len(anomalies)}")
    add(f"Kategori error : {', '.join(triggered) if triggered else '(none)'}")
    add(f"Catatan        : Skor utama BISA tetap tinggi -- sebagian temuan")
    add(f"                 di sini adalah anomali heuristik visual yang")
    add(f"                 tidak merusak struktur XML.")
    add("")

    # ── Bagian 1: Rincian temuan ──
    add(bar)
    add("  RINCIAN TEMUAN")
    add(bar)

    label_map = {
        "ERROR_KOLOM": "[KOLOM]",
        "ERROR_HEADER": "[HEADER]",
        "ERROR_STYLE": "[STYLE]",
        "ERROR_TABLE": "[TABLE]",
        "ERROR_TABLE_BORDER": "[TABLE-BORDER]",
        "ERROR_SECTPR_DIST": "[SECTPR-DIST]",
    }
    for cat, lab in label_map.items():
        if cats[cat]["triggered"]:
            add("")
            add(f"{lab} {len(cats[cat]['details'])} masalah")
            for d in cats[cat]["details"]:
                add(f"    - {d}")

    if not triggered:
        add("")
        add("    (Tidak ada error/anomali terdeteksi.)")

    # ── Bagian 2: Template solusi per kategori ──
    add("")
    add(bar)
    add(f"  PROMPT SOLUSI PER KATEGORI (copy ke AI yang akan benerin {gen_name})")
    add(bar)

    for cat in label_map.keys():
        if cats[cat]["triggered"]:
            add("")
            add(SOLUTION_TEMPLATES[cat].format(gen_name=gen_name))

    if not triggered:
        add("")
        add("(Tidak perlu prompt perbaikan -- generator sudah sesuai.)")

    # ── Bagian 3: Master prompt akhir (siap copy-paste) ──
    add("")
    add(bar)
    add("  MASTER PROMPT PERBAIKAN (gabungan, siap copy-paste)")
    add(bar)
    add("")
    add(f"Sistem QA mendeteksi masalah pada hasil generator `{gen_name}` "
        f"untuk template `{template_name}`. Tolong perbaiki `{gen_name}` "
        f"mengatasi semua masalah berikut sekaligus, tanpa mengubah logika "
        f"lain yang sudah benar:")
    add("")
    cat_titles = {
        "ERROR_KOLOM": "KATEGORI 1: LAYOUT KOLOM",
        "ERROR_HEADER": "KATEGORI 2: HEADER SHAPES",
        "ERROR_STYLE": "KATEGORI 3: STYLE & FONT",
        "ERROR_TABLE": "KATEGORI 4: TABLE LAYOUT CONTAINER",
        "ERROR_SECTPR_DIST": "KATEGORI 5: SECTPR DISTRIBUTION",
    }
    for cat, title in cat_titles.items():
        if cats[cat]["triggered"]:
            add(title)
            for d in cats[cat]["details"][:10]:
                add(f"  - {d}")
            add("")
            add(SOLUTION_TEMPLATES[cat].format(gen_name=gen_name))
            add("")
    add(bar)

    # ── Bagian 4: Prompt upgrade auto_checker.py (meta-improvement) ──
    add("")
    add(bar)
    add("  PROMPT UPGRADE auto_checker.py (META-IMPROVEMENT)")
    add(bar)
    add("")
    add(f"Selain memperbaiki `{gen_name}`, gunakan temuan di atas sebagai "
        f"masukan untuk meng-upgrade `auto_checker.py` supaya checker jauh "
        f"lebih spesifik, valid, dan tahan terhadap pola anomali baru di "
        f"template lain. Tolong analisis temuan ini dan perbarui checker "
        f"sesuai panduan di bawah:")
    add("")
    add("LANGKAH 1 -- Analisis temuan baru")
    add(f"  Untuk template `{doc_name}`, temuan berikut muncul:")
    for cat, title in cat_titles.items():
        if cats[cat]["triggered"]:
            add(f"    - {title}: {len(cats[cat]['details'])} masalah")
    if not triggered:
        add("    (Run ini bersih -- skip langkah ini.)")
    add("")
    add("  Pertanyaan kunci yang harus dijawab sebelum mengubah checker:")
    add("    a. Apakah pola anomali ini SUDAH ditangkap oleh audit existing,")
    add("       hanya saja threshold-nya kurang tepat? (=> tune threshold)")
    add("    b. Apakah pola ini BENAR-BENAR baru, belum ada audit-nya?")
    add("       (=> tambah audit function baru)")
    add("    c. Apakah finding ini false-positive untuk template-style ini?")
    add("       (=> tambah whitelist/exclusion, JANGAN hapus check global)")
    add("")
    add("LANGKAH 2 -- Pilih strategi upgrade (urut dari paling aman)")
    add("  [A] Tune threshold existing")
    add("      Contoh: TABLE_COUNT_TOLERANCE, SECTPR_DISTRIBUTION_THRESHOLD,")
    add("      PARAGRAPH_STYLE_CHECK_COUNT. Ubah hanya bila pola yang")
    add("      terdeteksi konsisten muncul di >=2 template berbeda.")
    add("")
    add("  [B] Tambah sub-check di audit existing")
    add("      Bila finding-nya varian dari kategori existing (mis. table")
    add("      count meleset karena pattern figure-wrapper), tambahkan")
    add("      cabang khusus di `audit_table_count()` atau sejenisnya")
    add("      sehingga pesan error lebih spesifik (sebut pattern-nya).")
    add("")
    add("  [C] Tambah audit function baru")
    add("      Bila pola benar-benar di luar 7 kategori existing, buat")
    add("      `audit_<nama>()` baru yang return `AuditResult`, daftarkan")
    add("      di `main()`, dan tambahkan render-nya di `render_report()`.")
    add("      Konvensi: MAYOR untuk struktural, MINOR untuk visual.")
    add("")
    add("LANGKAH 3 -- Validasi sebelum commit")
    add("  - Run checker terhadap SEMUA file output existing (DJLIT, SAGE,")
    add("    JCEF, dll) untuk pastikan tidak ada regresi false-positive.")
    add("  - Untuk template yang sebelumnya 'Lulus', skornya harus tetap")
    add("    >= skor sebelumnya. Bila ada penurunan, threshold/check baru")
    add("    terlalu agresif -- mundur atau perlonggar.")
    add("  - Tambahkan komentar di check baru yang menyebut template")
    add(f"    sumber pola: '# Pattern asal: template {doc_name} (run YYYY-MM-DD)'")
    add("    supaya jejak rule traceable di git history.")
    add("")
    add("LANGKAH 4 -- Hindari over-fitting")
    add("  - JANGAN bikin rule yang hanya men-deteksi kasus persis di")
    add(f"    `{doc_name}` (mis. hard-code nilai twip atau nama style).")
    add("    Generalisasi ke pola struktural (rasio, range, signature XML).")
    add("  - JANGAN hapus/loosen check existing hanya supaya template ini")
    add("    'lulus'. Kalau check existing salah, perbaiki rumusnya, bukan")
    add("    matikan check-nya.")
    add("  - Determinisme dijaga: checker tetap pure-function (tidak baca")
    add("    state run sebelumnya, tidak ada randomness).")
    add("")
    add(f"Output yang diharapkan: patch `auto_checker.py` + ringkasan singkat")
    add(f"alasan setiap perubahan, sehingga reviewer bisa verifikasi cepat.")
    add("")
    add(bar)

    return "\n".join(L)


def write_anomaly_file(audit_dir, doc_name, content):
    out_path = audit_dir / f"audit-unik_{doc_name}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path


# =============================================================================
# Skoring & status
# =============================================================================
def status_label(score: int, has_xml_fatal: bool = False) -> str:
    """Status berdasarkan skor + flag FATAL XML check.
    Bila FATAL XML (multi-col atau header shape) terpicu, status maksimum
    adalah REJECTED walau skor numerik masih tinggi.
    Batas EXCELLENT = 100. Batas LULUS minimum = 95."""
    if has_xml_fatal:
        return "REJECTED (FATAL XML CHECK)"
    if score == 100:
        return "EXCELLENT"
    if score >= PASS_SCORE_THRESHOLD:
        return "REVISI MINOR"
    if score >= 60:
        return "REVISI DIBUTUHKAN"
    if score > 0:
        return "REVISI MAYOR"
    return "GAGAL TOTAL"


def calculate_score(penalties: Iterable[Penalty]) -> tuple[int, int]:
    total = sum(p.total for p in penalties)
    return max(0, BASE_SCORE - total), total


def build_repair_prompt(doc_name: str, errors: list[str]) -> str:
    gen_name = _resolve_gen_name(doc_name)
    lines = [
        "[FAIL] AUDIT GAGAL! Ditemukan ketidaksesuaian.",
        "[COPY TEKS DI BAWAH INI UNTUK PROMPT PERBAIKAN]",
        "-" * 50,
        f"Sistem QA mendeteksi kegagalan pada skrip generator `{gen_name}`. "
        f"Tolong perbaiki kodingan `{gen_name}` untuk mengatasi "
        f"masalah berikut secara spesifik, tanpa mengubah logika lain "
        f"yang sudah benar:",
        "",
    ]
    for err in errors:
        lines.append(f"- {err}")
    lines.append("-" * 50)
    return "\n".join(lines)


# =============================================================================
# [5q] Empty Paragraphs (MINOR -3 per kelompok ≥ 3 consecutive empty paragraphs)
# =============================================================================
def audit_empty_paragraphs(doc_out, doc_orig=None) -> AuditResult:
    """Deteksi paragraf kosong beruntun (≥ 3 consecutive empty paragraphs).

    Paragraf kosong = text.strip() == "" dan tidak mengandung drawing/image.
    Setiap kelompok ≥ 3 paragraf kosong berturut-turut di-flag sebagai 1
    pelanggaran.

    Parameters
    ----------
    doc_out : Document
        Dokumen output yang diaudit.
    doc_orig : Document, optional
        Dokumen original (template) — untuk perbandingan toleransi bila perlu.

    Returns
    -------
    AuditResult
        errors: daftar pesan per kelompok paragraf kosong beruntun.
        info: {groups, details (list of dict), total_empty_paras, total_paragraphs}
    """
    res = AuditResult()
    paras = doc_out.paragraphs
    total_paras = len(paras)
    groups: list[dict] = []
    consecutive_empty: list[int] = []

    def _has_drawing_or_image(para) -> bool:
        """Cek apakah paragraf mengandung drawing/image (inline atau anchor)."""
        try:
            xml = para._element.xml
            # w:drawing, wp:inline, wp:anchor, mc:AlternateContent berisi gambar
            if "w:drawing" in xml or "wp:inline" in xml or "wp:anchor" in xml:
                return True
            # Legacy v:shape / w:pict
            if "w:pict" in xml or "v:shape" in xml or "v:imagedata" in xml:
                return True
            # OLE object
            if "o:OLEObject" in xml:
                return True
        except Exception:
            pass
        return False

    def _flush_run():
        """Jika run paragraf kosong ≥ 3, catat sebagai 1 kelompok."""
        if len(consecutive_empty) >= 3:
            group = {
                "start_index": consecutive_empty[0],
                "end_index": consecutive_empty[-1],
                "count": len(consecutive_empty),
                "indices": list(consecutive_empty),
            }
            groups.append(group)

    for i, para in enumerate(paras):
        text = (para.text or "").strip()
        has_media = _has_drawing_or_image(para)

        if text == "" and not has_media:
            consecutive_empty.append(i)
        else:
            _flush_run()
            consecutive_empty = []

    # Flush sisa run di akhir dokumen
    _flush_run()

    total_empty_paras = sum(g["count"] for g in groups)

    for g in groups:
        res.errors.append(
            "EMPTY PARAGRAPHS: {} paragraf kosong beruntun "
            "(index {}–{})".format(
                g["count"], g["start_index"], g["end_index"]
            )
        )

    res.info = {
        "groups": len(groups),
        "details": groups,
        "total_empty_paras": total_empty_paras,
        "total_paragraphs": total_paras,
    }
    return res


# =============================================================================
# Report rendering
# =============================================================================
def _bar(width: int = 60, char: str = "=") -> str:
    return char * width


def render_report(
    template_path: Path,
    output_path: Path,
    score: int,
    total_penalty: int,
    label: str,
    penalties: list[Penalty],
    hf_res: AuditResult,
    style_res: AuditResult,
    page_res: AuditResult,
    img_res: AuditResult,
    latex_leaks: list[dict],
    fig_pos_res: AuditResult,
    numbering_res: AuditResult,
    double_num_res: AuditResult,
    run_fmt_res: AuditResult,
    table_content_res: AuditResult,
    font_res: AuditResult,
    multicol_res: AuditResult,
    header_shape_res: AuditResult,
    table_res: AuditResult,
    sectpr_dist_res: AuditResult,
    all_errors: list[str],
    doc_name: str,
    border_res: AuditResult | None = None,
    placeholder_img_res: AuditResult | None = None,
    logo_res: AuditResult | None = None,
    empty_sec_res: AuditResult | None = None,
    structural_pos_res: AuditResult | None = None,
    anchor_pos_res: AuditResult | None = None,
    container_ctx_res: AuditResult | None = None,
    blank_page_res: AuditResult | None = None,
    char_anomalies: list[dict] | None = None,
    empty_paragraph_res: AuditResult | None = None,
    fc_res: AuditResult | None = None,
    line_sp_res: AuditResult | None = None,
    fli_res: AuditResult | None = None,
    para_spacing_res: AuditResult | None = None,
    font_size_res: AuditResult | None = None,
    section_num_fmt_res: AuditResult | None = None,
    formula_align_res: AuditResult | None = None,
) -> str:
    out: list[str] = []
    L = out.append

    # --- Banner skor di atas ---------------------------------------------------
    L(_bar())
    L(f"[SKOR KECOCOKAN: {score}%] -> STATUS: {label}")
    L(f"  Base Score: {BASE_SCORE} | Penalty: -{total_penalty} | Final: {score}%")
    L(_bar())
    L(f"[AUDIT] Scanning: {template_path.name} vs {output_path.name}")
    L(_bar())

    # --- [1] Header / Footer ---------------------------------------------------
    L("")
    L("[1] Deep Header/Footer Audit (multi-section, default/first/even)...")
    L(f"  Sections -- Original: {hf_res.info['n_sections_orig']}, "
      f"Output: {hf_res.info['n_sections_out']}")
    L(f"  Total elemen header/footer rusak (FATAL): {hf_res.info['broken_count']} | "
      f"Content diff (MINOR): {hf_res.info.get('content_diffs', 0)}")
    if hf_res.errors:
        for err in hf_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Semua header/footer (default/first/even) di setiap section terjaga.")

    # --- [2] Paragraph Style ---------------------------------------------------
    L("")
    L("[2] Paragraph Style Validity (20 paragraf pertama)...")
    L(f"  Pasangan ter-alignment: {style_res.info['checked_pairs']} | "
      f"Original: {style_res.info['total_orig']}, Output: {style_res.info['total_out']} | "
      f"Reset ke Normal: {style_res.info['style_reset_count']} | "
      f"Style berbeda lainnya: {style_res.info['other_style_diffs']}")
    if style_res.errors:
        for err in style_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Style paragraf jurnal terjaga.")

    # --- [3] Page Setup --------------------------------------------------------
    L("")
    L("[3] Page Setup & Multi-Column Layout...")
    L(f"  Section count -- Original: {page_res.info['n_orig']}, "
      f"Output: {page_res.info['n_out']}")
    if page_res.errors:
        for err in page_res.errors:
            L(f"  [!] {err}")
        # B4: Dump section signatures jika section count beda
        sigs = page_res.info.get("section_signatures", [])
        if sigs:
            L(f"  [INFO] Section dump (B4):")
            for sig in sigs:
                marker = "*MISSING*" if sig.get("status") == "MISSING" else "ok"
                L(f"    Section {sig.get('section_idx')}: "
                  f"{sig.get('orientation', '?')} "
                  f"{sig.get('page_w', 0)}x{sig.get('page_h', 0)}tw, "
                  f"{sig.get('columns', 1)}col, "
                  f"titlePg={sig.get('has_titlePg', False)}, "
                  f"type={sig.get('sec_type', '?')} [{marker}]")
    else:
        L("  [OK] Ukuran halaman, margin, dan jumlah kolom presisi di semua section.")

    # --- [4] Image / Placeholder ----------------------------------------------
    L("")
    L("[4] Strict Placeholder & AI Prompt Validation...")
    L(f"  [A] Gambar fisik (drawing) di Output : {img_res.info['a_drawings']}")
    L(f"  [B] Prompt AI gambar di Output       : {img_res.info['b_prompts']} "
      f"(valid: {img_res.info['valid_prompts']}, mismatch: {img_res.info['invalid_prompts']} [no penalty])")
    L(f"  [C] Ekspektasi dari _template.json   : {img_res.info['c_expected']}")
    L(f"  Placeholder usang '[Image placeholder]': {img_res.info['legacy_count']}")
    L(f"  Selisih -> missing: {img_res.info['missing']}, extra: {img_res.info['extra']}")
    L(f"  Gambar fisik di Original (referensi)  : {img_res.info['original_drawings']}")
    if img_res.errors:
        for err in img_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Semua gambar/prompt sesuai JSON, tidak ada placeholder usang.")

    # --- [5] LaTeX -------------------------------------------------------------
    L("")
    L("[5] Kebocoran LaTeX/Simbol...")
    if latex_leaks:
        for leak in latex_leaks:
            tags_str = ", ".join(leak["tags"][:5])
            L(f"  [!] Paragraf #{leak['para_index']}: `{tags_str}` -- \"{leak['snippet']}\"")
    else:
        L("  [OK] Tidak ada kebocoran LaTeX terdeteksi.")

    # --- [5a] Text Quality / Mojibake ---------------------------------------------
    if char_anomalies is not None:
        L("")
        L("[5a] Text Quality / Mojibake Detection...")
        total_anomalies = sum(a["count"] for a in char_anomalies)
        L(f"  Paragraf dengan karakter aneh: {len(char_anomalies)} | "
          f"Total karakter mencurigakan: {total_anomalies}")
        for anom in char_anomalies[:10]:
            chars_desc = ", ".join(anom["chars"][:5])
            L(f"  [!] Paragraf #{anom['para_index']} "
              f"[{anom['category']}]: {anom['count']} karakter "
              f"[{chars_desc}] - \"{anom['snippet'][:80]}\"")
        if len(char_anomalies) > 10:
            L(f"  ... dan {len(char_anomalies) - 10} paragraf lainnya.")
    elif char_anomalies is None:
        L("")
        L("[5a] Text Quality / Mojibake Detection... (skipped - empty pass)")

    # --- [5b] Figure Position --------------------------------------------------
    L("")
    L("[5b] Figure Position Cross-Check...")
    L(f"  Total drawings: {fig_pos_res.info['total_drawings']} | "
      f"Figures dengan referensi: {fig_pos_res.info['figures_with_refs']} | "
      f"Caption-first valid: {fig_pos_res.info.get('caption_first_layout', 0)} | "
      f"Violations: {fig_pos_res.info['violations']}")
    if fig_pos_res.errors:
        for err in fig_pos_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Semua gambar muncul setelah referensi teks.")

    # --- [5c] Heading Numbering ------------------------------------------------
    L("")
    L("[5c] Heading Auto-Numbering Render Check...")
    L(f"  Total headings: {numbering_res.info['total_headings']} | "
      f"Level-0: {numbering_res.info['level_0_count']} | "
      f"Format mismatches: {numbering_res.info['format_mismatches']} | "
      f"NumIds: orig={numbering_res.info['orig_num_count']} out={numbering_res.info['out_num_count']} | "
      f"AbstractIds: orig={numbering_res.info.get('orig_abstract_count', 0)} out={numbering_res.info.get('out_abstract_count', 0)}")
    if numbering_res.errors:
        for err in numbering_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Heading numbering konsisten.")

    # --- [5c.2] Section Numbering Format ----------------------------------------
    if section_num_fmt_res is not None:
        L("")
        L("[5c.2] Section Numbering Format (decimal/roman/letter)...")
        info = section_num_fmt_res.info
        L(f"  Original headings: {info['orig_heading_count']} | "
          f"Output headings: {info['out_heading_count']} | "
          f"Levels checked: {info['levels_checked']} | "
          f"Format mismatches: {info['format_mismatches']}")
        per_level = info.get("per_level", {})
        if per_level:
            for ilvl in sorted(per_level.keys()):
                stats = per_level[ilvl]
                match_marker = "[OK]" if stats["orig_format"] == stats["out_format"] else "[!]"
                L(f"  Level {ilvl}: {match_marker} "
                  f"template={stats['orig_format']} ({stats['orig_count']} headings) → "
                  f"output={stats['out_format']} ({stats['out_count']} headings)")
        if section_num_fmt_res.errors:
            for err in section_num_fmt_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Format numbering section konsisten dengan template.")

    # --- [5g] Double Numbering Detection ---------------------------------------
    L("")
    L("[5g] Double Numbering Detection (numPr + manual prefix)...")
    L(f"  Violations: {double_num_res.info['violations']}")
    if double_num_res.errors:
        for err in double_num_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Tidak ada double numbering terdeteksi.")

    # --- [5d] Run Formatting ---------------------------------------------------
    L("")
    L("[5d] Run Formatting Audit (color/underline/vertAlign/bold/italic)...")
    L(f"  Pasangan diperiksa: {run_fmt_res.info['checked']} | "
      f"Mismatches: {run_fmt_res.info['mismatches']}")
    if run_fmt_res.errors:
        for err in run_fmt_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Run formatting konsisten.")

    # --- [5e] Table Content Validation -----------------------------------------
    L("")
    L("[5e] Table Content Validation...")
    L(f"  Total tables: {table_content_res.info['total_tables']} | "
      f"Low density: {table_content_res.info['low_density_count']}")
    if table_content_res.errors:
        for err in table_content_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Tidak ada tabel placeholder kosong.")

    # --- [5e2] Table Border Visibility (info-only feedback ke generator) ----
    if border_res is not None:
        L("")
        L("[5e2] Table Border Visibility...")
        info = border_res.info
        total = info.get('total_data_tables', 0)
        invisible = info.get('invisible_count', 0)
        thin = info.get('thin_count', 0)
        mismatch = info.get('mismatch_count', 0)
        orig_pattern = info.get('orig_pattern')
        good = total - invisible - thin - mismatch
        L(f"  Tabel data: {total} | "
          f"OK: {good} | "
          f"Tanpa border: {invisible} | "
          f"Border tipis: {thin} | "
          f"Pattern mismatch: {mismatch}")
        if orig_pattern:
            L(f"  Template original pattern: {orig_pattern}")
        if invisible > 0:
            L(f"  [!] {invisible} tabel data tanpa border yang jelas. "
              f"Indices: {info.get('invisible_indices', [])}")
            L(f"  [!] [HINT] Generator perlu set tblBorders sesuai pattern template.")
        if thin > 0:
            L(f"  [!] {thin} tabel data dengan border terlalu tipis (sz < 4). "
              f"Indices: {info.get('thin_indices', [])}")
        if mismatch > 0:
            L(f"  [!] {mismatch} tabel data dengan pattern beda dari template:")
            for d in info.get('mismatch_details', [])[:5]:
                orig_pats = d.get('orig_patterns') or [d.get('orig_dominant', '?')]
                L(f"     - Tabel #{d['index']}: output={d['out_pattern']}, "
                  f"template patterns={orig_pats}")
            L(f"  [!] [HINT] Sesuaikan helper border generator dengan pattern template "
              f"({orig_pattern}).")
        if invisible == 0 and thin == 0 and mismatch == 0:
            L("  [OK] Semua tabel data punya border match dengan template.")

    # --- [5o] Figure Caption Style ---------------------------------------------
    if fc_res is not None:
        L("")
        L("[5o] Figure Caption Style Audit (label bold, deskripsi normal)...")
        info = fc_res.info
        L(f"  Caption terdeteksi: {info.get('caption_count', 0)} (output) | "
          f"{info.get('orig_caption_count', 0)} (template) | "
          f"Mismatches: {info.get('mismatches', 0)}")
        if fc_res.errors:
            for err in fc_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Semua figure caption mengikuti pola label-bold + deskripsi-normal.")

    # --- [5f] Font Family ------------------------------------------------------
    L("")
    L("[5f] Font Family Mismatch...")
    L(f"  Pasangan diperiksa: {font_res.info['checked']} | "
      f"Mismatches: {font_res.info['mismatches']}")
    if font_res.errors:
        for err in font_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Font family konsisten.")

    # --- [5f.2] Font Size Consistency ------------------------------------------
    if font_size_res is not None:
        L("")
        L("[5f.2] Font Size Consistency...")
        L(f"  Pasangan diperiksa: {font_size_res.info['checked']} | "
          f"Mismatches: {font_size_res.info['mismatches']}")
        if font_size_res.errors:
            for err in font_size_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Font size konsisten dengan template.")

    # --- [5h] Placeholder Image Detection -------------------------------------
    if placeholder_img_res is not None:
        L("")
        L("[5h] Placeholder/Blank Image Detection...")
        info = placeholder_img_res.info
        L(f"  Body images (non-decorative): {info.get('total_body_images', 0)} | "
          f"Placeholder terdeteksi: {info.get('placeholder_count', 0)}")
        if placeholder_img_res.errors:
            for err in placeholder_img_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Tidak ada gambar placeholder/blank terdeteksi.")

    # --- [5i] Logo Preservation Audit ------------------------------------------
    if logo_res is not None:
        L("")
        L("[5i] Logo Preservation Audit (logo jurnal di body top + headers/footers)...")
        info = logo_res.info
        orig_count = info.get('orig_logo_count', 0)
        orig_body = info.get('orig_logo_count_body', 0)
        orig_hf = info.get('orig_logo_count_hf', 0)
        out_count = info.get('out_logo_count', 0)
        out_body = info.get('out_logo_count_body', 0)
        out_hf = info.get('out_logo_count_hf', 0)
        preservation_rate = info.get('preservation_rate', 100.0)
        missing_count = len(info.get('missing_rids', []))
        L(f"  Logo original: {orig_count} total ({orig_body} body + {orig_hf} header/footer) | "
          f"Logo output: {out_count} total ({out_body} body + {out_hf} header/footer)")
        L(f"  Preservation rate: {preservation_rate:.1f}% | Missing: {missing_count}")
        if orig_count > 0:
            L(f"  Original logo rIds: {info.get('orig_logo_rids', [])}")
            L(f"  Preserved rIds: {info.get('preserved_rids', [])}")
            if missing_count > 0:
                L(f"  Missing rIds: {info.get('missing_rids', [])}")
        if logo_res.errors:
            for err in logo_res.errors:
                L(f"  [!] {err}")
        else:
            if orig_count > 0:
                L("  [OK] Semua logo jurnal (branding) dipertahankan di output.")
            else:
                L("  [OK] Template tidak memiliki logo di body top/headers/footers (skip check).")

    # --- [5k.3] Paragraph Spacing ---------------------------------------------
    if para_spacing_res is not None:
        L("")
        L("[5k.3] Paragraph Spacing (space_before/space_after body text)...")
        info = para_spacing_res.info
        L(f"  Paragraf body dicek: {info.get('checked', 0)} | "
          f"Violations: {info.get('violations', 0)}")
        if para_spacing_res.errors:
            for err in para_spacing_res.errors[:10]:
                L(f"  [!] {err}")
            if info.get('violations', 0) > 10:
                L(f"  ... dan {info['violations'] - 10} paragraf lainnya.")
        else:
            L("  [OK] Paragraph spacing (before/after) sesuai template.")

    # --- [6] Multi-Column XPath ------------------------------------------------
    L("")
    L("[6] Multi-Column XPath Audit (FATAL XML)...")
    L(f"  Section sectPrs -- Original: {multicol_res.info.get('n_orig_sections', 0)}, "
      f"Output: {multicol_res.info.get('n_out_sections', 0)}")
    broken = multicol_res.info.get("broken", [])
    L(f"  Section dengan multi-kolom hancur: {len(broken)}")
    if multicol_res.errors:
        for err in multicol_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Semua section multi-kolom utuh (w:cols/@w:num match).")

    # --- [7] Header Shapes XPath ----------------------------------------------
    L("")
    L("[7] Header Shapes/TextBox XPath Audit (FATAL XML)...")
    L(f"  Total kerusakan FATAL header shape: {header_shape_res.info.get('fatal_hits', 0)}")
    if header_shape_res.errors:
        for err in header_shape_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Tidak ada drawing/pict/v:shape/textbox header yang hilang.")

    # --- [7b] Body Table Count -------------------------------------------------
    L("")
    L("[7b] Body Table Count Audit...")
    L(f"  Tabel body -- Original: {table_res.info.get('n_orig', 0)}, "
      f"Output: {table_res.info.get('n_out', 0)}, "
      f"Expected (orig + JSON): {table_res.info.get('n_expected', 0)} "
      f"(JSON tables: {table_res.info.get('json_expected', 0)}, toleransi: {TABLE_COUNT_TOLERANCE}) | "
      f"Missing: {table_res.info.get('n_missing', 0)} | "
      f"Extra empty: {table_res.info.get('extra_empty', 0)} | "
      f"Extra filled: {table_res.info.get('extra_filled', 0)}")
    if table_res.errors:
        for err in table_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Jumlah tabel body sesuai (dalam toleransi).")

    # --- [7c] SectPr Distribution ----------------------------------------------
    L("")
    L("[7c] SectPr Distribution Audit (MAYOR)...")
    L(f"  Trailing empty sectPr -- Original: {sectpr_dist_res.info.get('orig_trailing_empty_sectpr', 0)}, "
      f"Output: {sectpr_dist_res.info.get('out_trailing_empty_sectpr', 0)} "
      f"(threshold: {SECTPR_FLUSH_THRESHOLD})")
    L(f"  Bucket multi-col -- Original: {sectpr_dist_res.info.get('sig_orig')}, "
      f"Output: {sectpr_dist_res.info.get('sig_out')} "
      f"(L1 div: {sectpr_dist_res.info.get('divergence', 0):.2f}, "
      f"threshold: {SECTPR_DISTRIBUTION_THRESHOLD})")
    if sectpr_dist_res.errors:
        for err in sectpr_dist_res.errors:
            L(f"  [!] {err}")
    else:
        L("  [OK] Distribusi sectPr inline match dengan template original.")

    # --- [7d] Empty Section / Blank Page ---------------------------------------
    if empty_sec_res is not None:
        L("")
        L("[7d] Empty Section / Blank Page Audit (MAYOR)...")
        info = empty_sec_res.info
        L(f"  Section -- Original: {info.get('n_orig_sections', 0)}, "
          f"Output: {info.get('n_out_sections', 0)} | "
          f"Original berkonten: {info.get('orig_content_sections', 0)} section")
        L(f"  Blank page (section kosong page-breaking): {info.get('blank_page_count', 0)} | "
          f"Konsentrasi konten: {info.get('content_concentration', 0):.0%} "
          f"(threshold: {CONTENT_CONCENTRATION_RATIO:.0%})")
        if empty_sec_res.errors:
            for err in empty_sec_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Konten body tersebar benar antar section, tidak ada blank page.")

    # --- [7e] Structural Position Audit (Level 1) ------------------------------
    if structural_pos_res is not None:
        L("")
        L("[7e] Structural Position Audit - Level 1 (MAYOR)...")
        info = structural_pos_res.info
        L(f"  Section cols -- Original: {info.get('orig_section_cols', [])}, "
          f"Output: {info.get('out_section_cols', [])}")
        L(f"  Drawings -- Original: {info.get('orig_total_drawings', 0)}, "
          f"Output: {info.get('out_total_drawings', 0)}")
        L(f"  Dekoratif by cols -- Original: {info.get('orig_deco_by_cols', {})}, "
          f"Output: {info.get('out_deco_by_cols', {})}")
        L(f"  Konten by cols -- Original: {info.get('orig_content_by_cols', {})}, "
          f"Output: {info.get('out_content_by_cols', {})}")
        L(f"  Mismatches -- Deco: {info.get('deco_mismatches', 0)}, "
          f"Content: {info.get('content_mismatches', 0)}, "
          f"Section shift: {info.get('section_shift_violations', 0)}")
        if structural_pos_res.errors:
            for err in structural_pos_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Semua drawing dekoratif & konten di section layout kolom yang benar.")

    # --- [7f] Anchor Position Audit (Level 2) ----------------------------------
    if anchor_pos_res is not None:
        L("")
        L("[7f] Anchor Position Audit - Level 2 (MINOR)...")
        info = anchor_pos_res.info
        L(f"  Dekoratif drawings -- Original: {info.get('orig_deco_count', 0)}, "
          f"Output: {info.get('out_deco_count', 0)}")
        L(f"  Anchor mismatches -- rId-based: {info.get('rid_mismatches', 0)}, "
          f"Shape-only: {info.get('shape_mismatches', 0)} | "
          f"Tolerance: {info.get('tolerance_emu', 0)} EMU")
        if anchor_pos_res.errors:
            for err in anchor_pos_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Semua anchor position drawing dekoratif konsisten dengan original.")

    # --- [7g] Container Context Audit (Level 3) --------------------------------
    if container_ctx_res is not None:
        L("")
        L("[7g] Container Context Audit - Level 3 (MINOR)...")
        info = container_ctx_res.info
        L(f"  Dekoratif drawings -- Original: {info.get('orig_deco_count', 0)}, "
          f"Output: {info.get('out_deco_count', 0)}")
        L(f"  Container violations -- rId-based: {info.get('rid_violations', 0)}, "
          f"Shape-only: {info.get('shape_violations', 0)} | "
          f"Index tolerance: {info.get('container_index_tolerance', 0)}")
        if container_ctx_res.errors:
            for err in container_ctx_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Semua drawing dekoratif di container yang sama dengan original.")

    # --- [7h] Blank Page & Section Break Waste --------------------------------
    if blank_page_res is not None:
        L("")
        L("[7h] Blank Page & Section Break Waste Audit...")
        info = blank_page_res.info
        L(f"  Empty sections -- Original: {info.get('orig_empty_sections', 0)}, "
          f"Output: {info.get('out_empty_sections', 0)} | "
          f"Extra: {info.get('extra_empty', 0)}")
        L(f"  Trailing sectPr waste -- Original: {info.get('orig_trailing_waste', 0)}, "
          f"Output: {info.get('out_trailing_waste', 0)} | "
          f"Extra: {info.get('extra_waste', 0)}")
        if blank_page_res.errors:
            for err in blank_page_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Tidak ada halaman kosong berlebih atau section break waste.")

    # --- [5q] Empty Paragraphs (consecutive) ----------------------------------
    if empty_paragraph_res is not None:
        L("")
        L("[5q] Empty Paragraphs (consecutive blank paragraphs)...")
        info = empty_paragraph_res.info
        L(f"  Total paragraf: {info.get('total_paragraphs', 0)} | "
          f"Kelompok paragraf kosong beruntun (≥ 3): {info.get('groups', 0)} | "
          f"Total paragraf kosong di semua kelompok: {info.get('total_empty_paras', 0)}")
        if empty_paragraph_res.errors:
            for err in empty_paragraph_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Tidak ada paragraf kosong beruntun terdeteksi.")

    # --- [7i] Formula Alignment Audit -----------------------------------------
    if formula_align_res is not None:
        L("")
        L("[7i] Formula Alignment Audit (MINOR)...")
        info = formula_align_res.info
        L(f"  Total formula paragraphs: {info.get('total_formula_paras', 0)} | "
          f"Center violations: {info.get('center_violations', 0)} | "
          f"Tab violations: {info.get('tab_violations', 0)} | "
          f"Alignment mismatches (vs template): {info.get('alignment_mismatches', 0)}")
        if formula_align_res.errors:
            for err in formula_align_res.errors:
                L(f"  [!] {err}")
        else:
            L("  [OK] Semua formula paragraph center-aligned dengan benar.")

    # --- [5o2] First Line Indent ------------------------------------------------
    if fli_res is not None:
        L("")
        L("[5o2] First Line Indent Audit...")
        L(f"  Paragraf body diperiksa: {fli_res.info.get('checked', 0)} | "
          f"Mismatch: {fli_res.info.get('mismatch_count', 0)} | "
          f"Expected indent: {fli_res.info.get('expected_cm', 'N/A')} cm")
        if fli_res.errors:
            for err in fli_res.errors[:10]:
                L(f"  [!] {err}")
            if len(fli_res.errors) > 10:
                L(f"  ... dan {len(fli_res.errors) - 10} paragraf lainnya.")
        else:
            L("  [OK] First line indent semua paragraf body sesuai template.")

    # --- [7j] Line Spacing Body Text -------------------------------------------
    if line_sp_res is not None:
        L("")
        L("[7j] Line Spacing Body Text (MINOR)...")
        info = line_sp_res.info
        L(f"  Paragraf diperiksa: {info.get('checked_count', 0)} | "
          f"Mismatch: {info.get('mismatch_count', 0)}")
        if line_sp_res.errors:
            for err in line_sp_res.errors[:15]:
                L(f"  [!] {err}")
            if len(line_sp_res.errors) > 15:
                L(f"  ... dan {len(line_sp_res.errors) - 15} paragraf lainnya.")
        else:
            L("  [OK] Semua line spacing body text sesuai template.")

    # --- Final block -----------------------------------------------------------
    L("")
    L(_bar())
    if not all_errors:
        L("[PASS] AUDIT LULUS: dokumen output presisi terhadap template original.")
    else:
        L(build_repair_prompt(doc_name, all_errors))

    L("")
    L(f"[SKOR KECOCOKAN: {score}%] -> STATUS: {label}")
    if penalties:
        L("Rincian Pemotongan Poin:")
        L(f"  Base Score: {BASE_SCORE}")
        for p in penalties:
            if p.count > 1:
                L(f"  - {p.category}: -{p.unit} x {p.count} = -{p.total}")
            else:
                L(f"  - {p.category}: -{p.total}")
        L(f"  Total Penalty: -{total_penalty}")
        L(f"  Skor Akhir: {score}%")

    return "\n".join(out)


def render_terminal_summary(
    score: int, label: str, total_penalty: int, penalties: list[Penalty],
    placeholder_penalty: int = 0,
) -> str:
    patterns_for_placeholder = [
        "Placeholder", "prompt gambar", "image prompt", "img placeholder", "label salah",
    ]
    ph_total = 0
    for p in penalties:
        for kw in patterns_for_placeholder:
            if kw.lower() in p.category.lower():
                ph_total += p.total
                break
    structural = min(100, score + ph_total)
    lines = [_bar()]
    lines.append(f"[SKOR KECOCOKAN: {score}%] -> STATUS: {label}")
    lines.append(f"  Base: {BASE_SCORE} | Penalty: -{total_penalty} | Akhir: {score}%")
    if structural > score:
        lines.append(f"  📊 **Skor Struktural (excl. placeholder): {structural}%**")
    if penalties:
        for p in penalties:
            if p.count > 1:
                lines.append(f"   - {p.category}: -{p.unit} x {p.count} = -{p.total}")
            else:
                lines.append(f"   - {p.category}: -{p.total}")
    lines.append(_bar())
    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================
def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python auto_checker.py <template.docx> <output.docx> [--json <paper.json>]")
        print("  (urutan otomatis terdeteksi dari nama file yang mengandung '_output')")
        print("  --json: gunakan paper.json spesifik (bukan _template.json default)")
        sys.exit(1)

    # Parse --json flag
    custom_json_path = None
    args = sys.argv[1:]
    if "--json" in args:
        idx = args.index("--json")
        if idx + 1 < len(args):
            custom_json_path = Path(args[idx + 1])
            if not custom_json_path.exists():
                print(f"[ERROR] JSON file tidak ditemukan: {custom_json_path}")
                sys.exit(1)
            args = args[:idx] + args[idx + 2:]
        else:
            print("[ERROR] --json harus diikuti path ke file JSON")
            sys.exit(1)

    if len(args) < 2:
        print("[ERROR] Butuh 2 argumen (template.docx dan output.docx)")
        sys.exit(1)

    arg1 = Path(args[0])
    arg2 = Path(args[1])

    if not arg1.exists():
        print(f"[ERROR] File tidak ditemukan: {arg1}")
        sys.exit(1)
    if not arg2.exists():
        print(f"[ERROR] File tidak ditemukan: {arg2}")
        sys.exit(1)

    # Auto-detect: file dengan '_output' di nama = output, sisanya = template
    if "_output" in arg1.name and "_output" not in arg2.name:
        template_path = arg2
        output_path = arg1
        print("[INFO] Auto-detect: arg1=output, arg2=template (swapped)")
    elif "_output" in arg2.name and "_output" not in arg1.name:
        template_path = arg1
        output_path = arg2
    elif "_output" in arg1.name and "_output" in arg2.name:
        # Both have _output - use file with larger size as template
        if arg1.stat().st_size > arg2.stat().st_size:
            template_path, output_path = arg1, arg2
        else:
            template_path, output_path = arg2, arg1
        print(f"[INFO] Auto-detect by size: template={template_path.name} ({template_path.stat().st_size/1024:.0f}KB) > output={output_path.name} ({output_path.stat().st_size/1024:.0f}KB)")
    else:
        # Neither has _output - assume standard order
        template_path = arg1
        output_path = arg2

    doc_name = output_path.stem.replace("_output", "")
    audit_filename = f"audit_{output_path.stem}.txt"
    audit_path = Path(__file__).resolve().parent / audit_filename

    try:
        doc_orig = open_docx(template_path)
    except Exception as e:
        print(f"[ERROR] Gagal membuka template: {e}")
        sys.exit(1)
    try:
        doc_out = open_docx(output_path)
    except Exception as e:
        print(f"[ERROR] Gagal membuka output: {e}")
        sys.exit(1)

    json_titles = load_image_titles_from_json(Path(__file__).resolve().parent, custom_json_path)
    json_expected = load_expected_counts_from_json(Path(__file__).resolve().parent, custom_json_path)
    if custom_json_path:
        print(f"[INFO] Menggunakan JSON: {custom_json_path}")
        print(f"  - Image titles di JSON: {len(json_titles)}")
        print(f"  - Expected counts: {json_expected}")
    else:
        print(f"[INFO] Menggunakan _template.json default ({Path(__file__).resolve().parent / '_template.json'})")

    # -------------------------------------------------------------------------
    # Jalankan semua audit
    # -------------------------------------------------------------------------
    all_errors: list[str] = []
    penalties: list[Penalty] = []

    # [1] Header / Footer (FATAL -15 per kerusakan struktural, MINOR -5 per content diff)
    hf_res = audit_headers_footers(doc_orig, doc_out)
    all_errors.extend(hf_res.errors)
    if hf_res.info["broken_count"] > 0:
        n = hf_res.info["broken_count"]
        penalties.append(Penalty(
            category="Header/Footer Rusak (FATAL)",
            count=n,
            unit=PENALTY_HEADER_FOOTER_FATAL,
            total=PENALTY_HEADER_FOOTER_FATAL * n,
        ))
    if hf_res.info.get("content_diffs", 0) > 0:
        n = hf_res.info["content_diffs"]
        penalties.append(Penalty(
            category="Header/Footer Content Diff (MINOR)",
            count=n,
            unit=PENALTY_HEADER_CONTENT,
            total=PENALTY_HEADER_CONTENT * n,
        ))

    # [2] Paragraph Style (MAYOR -10 untuk reset, MINOR -5 per mismatch lainnya)
    style_res = audit_paragraph_styles(doc_orig, doc_out)
    all_errors.extend(style_res.errors)
    if style_res.info["style_reset_count"] > 0:
        penalties.append(Penalty(
            category="Style Jurnal Reset ke Normal (MAYOR)",
            count=1,
            unit=PENALTY_STYLE_RESET,
            total=PENALTY_STYLE_RESET,
        ))
    if style_res.info["other_style_diffs"] > 0:
        penalties.append(Penalty(
            category="Style Mismatch Non-Normal (MINOR)",
            count=style_res.info["other_style_diffs"],
            unit=PENALTY_STYLE_MISMATCH,
            total=PENALTY_STYLE_MISMATCH * style_res.info["other_style_diffs"],
        ))

    # [3] Page Setup (MAYOR -10 sekali kalau ada diff apapun)
    page_res = audit_page_setup(doc_orig, doc_out)
    all_errors.extend(page_res.errors)
    if page_res.errors:
        penalties.append(Penalty(
            category="Page Setup / Margin / Kolom Meleset (MAYOR)",
            count=1,
            unit=PENALTY_PAGE_SETUP,
            total=PENALTY_PAGE_SETUP,
        ))

    # [4] Image / Placeholder / Prompt (MINOR -5 per kejadian)
    img_res = audit_images(doc_orig, doc_out, json_titles)
    all_errors.extend(img_res.errors)
    img_minor_count = (
        img_res.info["legacy_count"]
        + img_res.info["missing"]
        + img_res.info["wrong_color_prompts"]
    )
    if img_minor_count > 0:
        penalties.append(Penalty(
            category="Placeholder/Prompt Gambar Salah (MINOR)",
            count=img_minor_count,
            unit=PENALTY_IMAGE_MINOR,
            total=PENALTY_IMAGE_MINOR * img_minor_count,
        ))

    # [4b] Embedded Image vs AI Prompt (MAYOR -10 per gambar tidak embedded)
    embed_res = audit_embedded_vs_prompts(doc_orig, doc_out, json_titles)
    all_errors.extend(embed_res.errors)
    embed_missing = len(embed_res.errors)
    if embed_missing > 0:
        penalties.append(Penalty(
            category="Gambar Tidak Embedded / Prompt AI (MAYOR)",
            count=embed_missing,
            unit=PENALTY_EMPTY_SECTION,
            total=PENALTY_EMPTY_SECTION * embed_missing,
        ))

    # [5] LaTeX leak (-2 per leak)
    latex_leaks = audit_latex_leaks(doc_out)
    if latex_leaks:
        for leak in latex_leaks:
            tags_str = ", ".join(leak["tags"][:5])
            all_errors.append(
                f"LATEX BOCOR: Paragraf #{leak['para_index']} ({leak.get('count', 1)} pattern) "
                f"tag: `{tags_str}`. Snippet: \"{leak['snippet']}\""
            )
        total_occ = latex_leaks[0].get('_total_occurrences', len(latex_leaks)) if latex_leaks else 0
        penalties.append(Penalty(
            category="Kebocoran LaTeX/Simbol",
            count=total_occ,
            unit=PENALTY_LATEX_LEAK,
            total=PENALTY_LATEX_LEAK * total_occ,
        ))

    # [5a] Text Quality / Mojibake (-2 per paragraf dengan karakter aneh)
    char_anomalies = audit_text_quality(doc_out)
    if char_anomalies:
        for anom in char_anomalies:
            chars_desc = ", ".join(anom["chars"][:5])
            all_errors.append(
                f"CHAR ANOMALY ({anom['category']}): Paragraf #{anom['para_index']} "
                f"mengandung {anom['count']} karakter mencurigakan "
                f"[{chars_desc}]. Snippet: \"{anom['snippet']}\""
            )
        total_char_anomalies = sum(a["count"] for a in char_anomalies)
        penalties.append(Penalty(
            category="Karakter Aneh/Mojibake (MINOR)",
            count=total_char_anomalies,
            unit=PENALTY_CHAR_ANOMALY,
            total=PENALTY_CHAR_ANOMALY * total_char_anomalies,
        ))

    # [5b] Figure Position Cross-Check (-3 per figure di posisi salah)
    fig_pos_res = audit_figure_position(doc_out, doc_orig)
    all_errors.extend(fig_pos_res.errors)
    if fig_pos_res.info["violations"] > 0:
        penalties.append(Penalty(
            category="Figure Position Salah (MINOR)",
            count=fig_pos_res.info["violations"],
            unit=PENALTY_FIGURE_POSITION,
            total=PENALTY_FIGURE_POSITION * fig_pos_res.info["violations"],
        ))

    # [5c] Heading Auto-Numbering (-3 per inkonsistensi)
    numbering_res = audit_heading_numbering(doc_orig, doc_out)
    all_errors.extend(numbering_res.errors)
    if numbering_res.info["format_mismatches"] > 0:
        penalties.append(Penalty(
            category="Heading Numbering Mismatch (MINOR)",
            count=numbering_res.info["format_mismatches"],
            unit=PENALTY_NUMBERING_MISMATCH,
            total=PENALTY_NUMBERING_MISMATCH * numbering_res.info["format_mismatches"],
        ))

    # [5c.2] Section Numbering Format (-3 per mismatch)
    section_num_fmt_res = audit_section_numbering_format(doc_orig, doc_out)
    all_errors.extend(section_num_fmt_res.errors)
    if section_num_fmt_res.info["format_mismatches"] > 0:
        penalties.append(Penalty(
            category="Section Numbering Format Mismatch (MINOR)",
            count=section_num_fmt_res.info["format_mismatches"],
            unit=PENALTY_SECTION_NUM_FORMAT,
            total=PENALTY_SECTION_NUM_FORMAT * section_num_fmt_res.info["format_mismatches"],
        ))

    # [5g] Double Numbering Detection (-5 per heading double-numbered)
    double_num_res = audit_double_numbering(doc_out)
    all_errors.extend(double_num_res.errors)
    if double_num_res.info["violations"] > 0:
        penalties.append(Penalty(
            category="Double Numbering Heading (MINOR)",
            count=double_num_res.info["violations"],
            unit=PENALTY_DOUBLE_NUMBERING,
            total=PENALTY_DOUBLE_NUMBERING * double_num_res.info["violations"],
        ))

    # [5g.2] Reference Double Numbering (-3 per [1] [1])
    ref_double_num_res = audit_reference_double_numbering(doc_out)
    all_errors.extend(ref_double_num_res.errors)
    if ref_double_num_res.count:
        penalties.append(Penalty(
            category="Referensi Double Numbering (MINOR)",
            count=ref_double_num_res.count,
            unit=PENALTY_REF_DOUBLE_NUM,
            total=PENALTY_REF_DOUBLE_NUM * ref_double_num_res.count,
        ))

    # [5d] Run Formatting (-2 per mismatch)
    run_fmt_res = audit_run_formatting(doc_orig, doc_out)
    all_errors.extend(run_fmt_res.errors)
    if run_fmt_res.info["mismatches"] > 0:
        penalties.append(Penalty(
            category="Run Formatting Mismatch (MINOR)",
            count=run_fmt_res.info["mismatches"],
            unit=PENALTY_RUN_FORMATTING,
            total=PENALTY_RUN_FORMATTING * run_fmt_res.info["mismatches"],
        ))

    # [5e] Table Content Validation (-3 per low density table)
    table_content_res = audit_table_content(doc_out, doc_orig=doc_orig)
    all_errors.extend(table_content_res.errors)
    if table_content_res.info["low_density_count"] > 0:
        penalties.append(Penalty(
            category="Table Low Density (MINOR)",
            count=table_content_res.info["low_density_count"],
            unit=PENALTY_TABLE_DENSITY,
            total=PENALTY_TABLE_DENSITY * table_content_res.info["low_density_count"],
        ))

    # [5e2] Table Border Visibility (MINOR -5 per invisible, -3 per thin/mismatch)
    # Border check berbeda dengan density check: density = isi cell (content),
    # border = garis tabel (formatting). Keduanya harus dicek terpisah.
    # Mismatch: output pakai pattern beda dari template (mis. full grid vs academic).
    border_res = audit_table_borders(doc_out, doc_orig=doc_orig, template_path=template_path)
    all_errors.extend(border_res.errors)
    if border_res.info.get("invisible_count", 0) > 0:
        penalties.append(Penalty(
            category="Table Border Missing (MINOR)",
            count=border_res.info["invisible_count"],
            unit=PENALTY_TABLE_BORDER,
            total=PENALTY_TABLE_BORDER * border_res.info["invisible_count"],
        ))
    if border_res.info.get("mismatch_count", 0) > 0:
        penalties.append(Penalty(
            category="Table Border Pattern Mismatch (MINOR)",
            count=border_res.info["mismatch_count"],
            unit=PENALTY_TABLE_BORDER_THIN,
            total=PENALTY_TABLE_BORDER_THIN * border_res.info["mismatch_count"],
        ))
    if border_res.info.get("thin_count", 0) > 0:
        penalties.append(Penalty(
            category="Table Border Thin (MINOR)",
            count=border_res.info["thin_count"],
            unit=PENALTY_TABLE_BORDER_THIN,
            total=PENALTY_TABLE_BORDER_THIN * border_res.info["thin_count"],
        ))

    # [5f] Font Family Mismatch (-3 per mismatch)
    font_res = audit_font_family(doc_orig, doc_out)
    all_errors.extend(font_res.errors)
    if font_res.info["mismatches"] > 0:
        penalties.append(Penalty(
            category="Font Family Mismatch (MINOR)",
            count=font_res.info["mismatches"],
            unit=PENALTY_FONT_FAMILY,
            total=PENALTY_FONT_FAMILY * font_res.info["mismatches"],
        ))

    # [5f.1b] Full Font Audit — ALL paragraphs, per-run comparison
    font_full_res = audit_font_full(doc_orig, doc_out)
    all_errors.extend(font_full_res.errors)
    if font_full_res.info.get("font_full_mismatches", 0) > 0:
        n_mm = font_full_res.info["font_full_mismatches"]
        penalties.append(Penalty(
            category="Font Full Audit Mismatch (MINOR)",
            count=n_mm,
            unit=PENALTY_FONT_FAMILY,
            total=PENALTY_FONT_FAMILY * n_mm,
        ))

    # [5f.2] Font Size Consistency (-3 per mismatch)
    font_size_res = audit_font_size_consistency(doc_orig, doc_out)
    all_errors.extend(font_size_res.errors)
    if font_size_res.info["mismatches"] > 0:
        penalties.append(Penalty(
            category="Font Size Mismatch (MINOR)",
            count=font_size_res.info["mismatches"],
            unit=PENALTY_FONT_SIZE,
            total=PENALTY_FONT_SIZE * font_size_res.info["mismatches"],
        ))

    # [5h] Placeholder/Blank Image Detection (-5 per placeholder)
    placeholder_img_res = audit_placeholder_images(doc_out, doc_orig=doc_orig)
    all_errors.extend(placeholder_img_res.errors)
    if placeholder_img_res.info["placeholder_count"] > 0:
        penalties.append(Penalty(
            category="Placeholder Image Kosong/Putih (MINOR)",
            count=placeholder_img_res.info["placeholder_count"],
            unit=PENALTY_PLACEHOLDER_IMAGE,
            total=PENALTY_PLACEHOLDER_IMAGE * placeholder_img_res.info["placeholder_count"],
        ))

    # [5i] Logo Preservation Audit (MAYOR -10 per logo missing)
    logo_res = audit_logo_preservation(doc_orig, doc_out)
    all_errors.extend(logo_res.errors)
    if len(logo_res.info.get("missing_rids", [])) > 0:
        penalties.append(Penalty(
            category="Logo Jurnal Hilang (MAYOR)",
            count=len(logo_res.info["missing_rids"]),
            unit=PENALTY_LOGO_MISSING,
            total=PENALTY_LOGO_MISSING * len(logo_res.info["missing_rids"]),
        ))

    # [5j] Image Sizing — penalti hanya untuk gambar OVERSIZE (> target)
    img_size_res = audit_image_sizing(doc_out, doc_orig=doc_orig)
    oversize_count = img_size_res.info.get("oversize_count", 0)
    info_count = img_size_res.info.get("mismatch_count", 0) - oversize_count
    if oversize_count > 0:
        all_errors.append(
            "UKURAN GAMBAR OVERSIZE: %d gambar > target %.1fcm (%s layout) — "
            "resiko overflow kolom" % (
                oversize_count,
                img_size_res.info.get("target_cm", 0),
                img_size_res.info.get("layout", "1-col"),
            )
        )
        penalties.append(Penalty(
            category="Ukuran Gambar OVERSIZE (MAYOR)",
            count=oversize_count,
            unit=PENALTY_IMAGE_SIZE_MISMATCH,
            total=PENALTY_IMAGE_SIZE_MISMATCH * oversize_count,
        ))
    if info_count > 0:
        all_errors.append(
            "INFO: %d gambar di bawah target %.1fcm (%s layout) — "
            "mungkin gambar test/placeholder" % (
                info_count,
                img_size_res.info.get("target_cm", 0),
                img_size_res.info.get("layout", "1-col"),
            )
        )

    # [5k] Element Spacing (MINOR -3 per spacing violation)
    spacing_res = audit_element_spacing(doc_out)
    all_errors.extend(spacing_res.errors)
    if spacing_res.info.get("violations", 0) > 0:
        penalties.append(Penalty(
            category="Spacing Element Tidak Konsisten (MINOR)",
            count=spacing_res.info["violations"],
            unit=PENALTY_ELEMENT_SPACING,
            total=PENALTY_ELEMENT_SPACING * spacing_res.info["violations"],
        ))

    # [5k.2] Line Spacing (MINOR -2 per paragraph dengan spacing mismatch)
    line_sp_res = audit_line_spacing(doc_out, doc_orig=doc_orig)
    if line_sp_res.info.get("mismatch_count", 0) > 0:
        all_errors.append(
            "LINE SPACING MISMATCH: %s paragraphs differ from template" % 
            line_sp_res.info["mismatch_count"]
        )
        penalties.append(Penalty(
            category="Line Spacing Body Text (MINOR)",
            count=line_sp_res.info["mismatch_count"],
            unit=PENALTY_LINE_SPACING,
            total=PENALTY_LINE_SPACING * line_sp_res.info["mismatch_count"],
        ))

    # [5k.3] Paragraph Spacing (MINOR -2 per paragraf dengan space_before/after mismatch)
    para_spacing_res = audit_paragraph_spacing(doc_out, doc_orig=doc_orig)
    all_errors.extend(para_spacing_res.errors)
    if para_spacing_res.info.get("violations", 0) > 0:
        penalties.append(Penalty(
            category="Paragraph Spacing Mismatch (MINOR)",
            count=para_spacing_res.info["violations"],
            unit=PENALTY_PARAGRAPH_SPACING,
            total=PENALTY_PARAGRAPH_SPACING * para_spacing_res.info["violations"],
        ))

    # [5q] Empty Paragraphs (MINOR -3 per kelompok paragraf kosong beruntun)
    empty_paragraph_res = audit_empty_paragraphs(doc_out, doc_orig=doc_orig)
    all_errors.extend(empty_paragraph_res.errors)
    if empty_paragraph_res.info.get("groups", 0) > 0:
        penalties.append(Penalty(
            category="Paragraf Kosong Beruntun (MINOR)",
            count=empty_paragraph_res.info["groups"],
            unit=PENALTY_EMPTY_PARAGRAPH,
            total=PENALTY_EMPTY_PARAGRAPH * empty_paragraph_res.info["groups"],
        ))

    # [5l] Formula OMML (MAYOR -10 per formula OMML kosong)
    formula_res = audit_formula_omml(doc_out)
    all_errors.extend(formula_res.errors)
    if formula_res.info.get("empty_count", 0) > 0:
        penalties.append(Penalty(
            category="Formula OMML Kosong/Rusak (MAYOR)",
            count=formula_res.info["empty_count"],
            unit=PENALTY_EMPTY_FORMULA,
            total=PENALTY_EMPTY_FORMULA * formula_res.info["empty_count"],
        ))

    # [5m] Table Width (MAYOR -10 per tabel overflow kolom)
    tw_res = audit_table_width(doc_out)
    all_errors.extend(tw_res.errors)
    if tw_res.info.get("mismatch_count", 0) > 0:
        penalties.append(Penalty(
            category="Tabel Overflow Kolom (MAYOR)",
            count=tw_res.info["mismatch_count"],
            unit=PENALTY_TABLE_WIDTH,
            total=PENALTY_TABLE_WIDTH * tw_res.info["mismatch_count"],
        ))

    # [5n] Table Spacing (MINOR -3 per caption/spacing rapat)
    ts_res = audit_table_spacing(doc_out)
    all_errors.extend(ts_res.errors)
    if ts_res.info.get("table_caption_count", 0) > 0 and len(ts_res.errors) > 0:
        penalties.append(Penalty(
            category="Caption/Table Spacing Rapat (MINOR)",
            count=len(ts_res.errors),
            unit=PENALTY_TABLE_SPACING,
            total=PENALTY_TABLE_SPACING * len(ts_res.errors),
        ))

    # [5o] Figure Caption Style (MINOR -3 per caption style mismatch)
    fc_res = audit_figure_caption_style(doc_out, doc_orig)
    all_errors.extend(fc_res.errors)
    if fc_res.info.get("mismatches", 0) > 0:
        penalties.append(Penalty(
            category="Figure Caption Style Mismatch (MINOR)",
            count=fc_res.info["mismatches"],
            unit=PENALTY_FIGURE_CAPTION,
            total=PENALTY_FIGURE_CAPTION * fc_res.info["mismatches"],
        ))

    # [5o2] First Line Indent (MINOR -2 per paragraf body indent tidak sesuai)
    fli_res = audit_first_line_indent(doc_out, doc_orig)
    all_errors.extend(fli_res.errors)
    if fli_res.info.get("mismatch_count", 0) > 0:
        penalties.append(Penalty(
            category="First Line Indent Tidak Sesuai (MINOR)",
            count=fli_res.info["mismatch_count"],
            unit=PENALTY_FIRST_LINE_INDENT,
            total=PENALTY_FIRST_LINE_INDENT * fli_res.info["mismatch_count"],
        ))

    # [5p] Formula OMML Width (MAYOR -10 per formula overflow kolom)
    fw_res = audit_formula_width(doc_out)
    all_errors.extend(fw_res.errors)
    if fw_res.info.get("mismatch_count", 0) > 0:
        penalties.append(Penalty(
            category="Formula OMML Overflow Kolom (MAYOR)",
            count=fw_res.info["mismatch_count"],
            unit=PENALTY_FORMULA_WIDTH,
            total=PENALTY_FORMULA_WIDTH * fw_res.info["mismatch_count"],
        ))

    # [6] Multi-Column XPath audit (FATAL -25 per section yang multi-col-nya hancur)
    multicol_res = audit_multicolumn_xpath(doc_orig, doc_out)
    all_errors.extend(multicol_res.errors)
    multicol_broken = len(multicol_res.info.get("broken", []))
    if multicol_broken > 0:
        penalties.append(Penalty(
            category="Multi-Kolom Hancur (FATAL XML)",
            count=multicol_broken,
            unit=PENALTY_MULTICOL_FATAL,
            total=PENALTY_MULTICOL_FATAL * multicol_broken,
        ))

    # [7] Header Shapes/TextBox XPath audit (FATAL -20 per section yang shape-nya hilang)
    header_shape_res = audit_header_shapes_xpath(doc_orig, doc_out)
    all_errors.extend(header_shape_res.errors)
    shape_hits = header_shape_res.info.get("fatal_hits", 0)
    if shape_hits > 0:
        penalties.append(Penalty(
            category="Header Shapes/TextBox Hilang (FATAL XML)",
            count=shape_hits,
            unit=PENALTY_HEADER_SHAPE_FATAL,
            total=PENALTY_HEADER_SHAPE_FATAL * shape_hits,
        ))

    # [7b] Body Table Count audit (B3 classifier: extra_empty vs missing)
    table_res = audit_table_count(doc_orig, doc_out, json_expected=json_expected.get("tables", 0))
    all_errors.extend(table_res.errors)
    table_diff = max(0, table_res.info.get("diff", 0) - TABLE_COUNT_TOLERANCE)
    if table_diff > 0:
        # Pakai info dari classifier untuk distribute penalti
        n_missing = table_res.info.get("n_missing", 0)
        extra_empty = table_res.info.get("extra_empty", 0)
        extra_filled = table_res.info.get("extra_filled", 0)

        # Apply tolerance proporsional
        # Missing tables -> PENALTY_TABLE_COUNT (5) per tabel
        if n_missing > TABLE_COUNT_TOLERANCE:
            n_missing_penalized = n_missing - TABLE_COUNT_TOLERANCE
            penalties.append(Penalty(
                category="Tabel Body Hilang (MINOR)",
                count=n_missing_penalized,
                unit=PENALTY_TABLE_COUNT,
                total=PENALTY_TABLE_COUNT * n_missing_penalized,
            ))
        # Extra empty -> PENALTY_TABLE_EXTRA_EMPTY (3) per tabel
        if extra_empty > 0:
            penalties.append(Penalty(
                category="Tabel Extra Kosong/Placeholder (MINOR)",
                count=extra_empty,
                unit=PENALTY_TABLE_DENSITY,
                total=PENALTY_TABLE_DENSITY * extra_empty,
            ))
        # Extra filled (kalau total extra > tolerance) -> PENALTY_TABLE_COUNT
        # JSON tables adalah konten user yang sah; jangan penalize generator
        # yang menambahkan tabel data dari JSON.
        n_extra_total = extra_empty + extra_filled
        json_allowance = table_res.info.get("json_expected", 0) or 0
        # Jika output extra masih dalam batas (orig + JSON tables + tolerance),
        # itu bukan extra "tidak sah" - generator memang menambah konten user.
        n_orig_t = table_res.info.get("n_orig", 0)
        n_out_t = table_res.info.get("n_out", 0)
        if n_extra_total > TABLE_COUNT_TOLERANCE and extra_filled > 0 and \
           n_out_t > n_orig_t + json_allowance + TABLE_COUNT_TOLERANCE:
            extra_filled_penalized = max(0, extra_filled - max(0, TABLE_COUNT_TOLERANCE - extra_empty))
            if extra_filled_penalized > 0:
                penalties.append(Penalty(
                    category="Tabel Extra Berkonten (MINOR)",
                    count=extra_filled_penalized,
                    unit=PENALTY_TABLE_COUNT,
                    total=PENALTY_TABLE_COUNT * extra_filled_penalized,
                ))

    # [7c] SectPr Distribution audit (MAYOR)
    sectpr_dist_res = audit_sectpr_distribution(doc_orig, doc_out)
    all_errors.extend(sectpr_dist_res.errors)
    if sectpr_dist_res.info.get("flush_detected"):
        penalties.append(Penalty(
            category="SectPr Flush-at-End (MAYOR)",
            count=1,
            unit=PENALTY_SECTPR_FLUSH,
            total=PENALTY_SECTPR_FLUSH,
        ))
    if sectpr_dist_res.info.get("distribution_diverged"):
        penalties.append(Penalty(
            category="SectPr Distribution Diverged (MAYOR)",
            count=1,
            unit=PENALTY_SECTPR_DISTRIBUTION,
            total=PENALTY_SECTPR_DISTRIBUTION,
        ))

    # [7d] Empty Section / Blank Page audit (MAYOR -10 per blank page section,
    # MAYOR -10 sekali untuk konsentrasi konten). Pattern asal: PERTANIKA 2025.
    empty_sec_res = audit_empty_sections(doc_orig, doc_out)
    all_errors.extend(empty_sec_res.errors)
    blank_page_count = empty_sec_res.info.get("blank_page_count", 0)
    if blank_page_count > 0:
        penalties.append(Penalty(
            category="Blank Page / Section Kosong (MAYOR)",
            count=blank_page_count,
            unit=PENALTY_EMPTY_SECTION,
            total=PENALTY_EMPTY_SECTION * blank_page_count,
        ))
    if empty_sec_res.info.get("concentration_detected"):
        penalties.append(Penalty(
            category="Konten Body Menumpuk di 1 Section (MAYOR)",
            count=1,
            unit=PENALTY_CONTENT_CONCENTRATION,
            total=PENALTY_CONTENT_CONCENTRATION,
        ))

    # [7e] Level 1: Structural Position Audit (MAYOR -15 per mismatch)
    # Drawing dekoratif (logo/masthead) yang pindah ke section dengan kolom beda.
    structural_pos_res = audit_structural_position(doc_orig, doc_out)
    all_errors.extend(structural_pos_res.errors)
    structural_mismatch_count = (
        structural_pos_res.info.get("deco_mismatches", 0)
        + structural_pos_res.info.get("content_mismatches", 0)
        + structural_pos_res.info.get("section_shift_violations", 0)
    )
    if structural_mismatch_count > 0:
        penalties.append(Penalty(
            category="Logo/Content Section Mismatch (MAYOR)",
            count=structural_mismatch_count,
            unit=PENALTY_LOGO_SECTION_MISMATCH,
            total=PENALTY_LOGO_SECTION_MISMATCH * structural_mismatch_count,
        ))

    # [7f] Level 2: Anchor Position Audit (MINOR -5 per mismatch)
    anchor_pos_res = audit_anchor_position(doc_orig, doc_out)
    all_errors.extend(anchor_pos_res.errors)
    anchor_mismatch_count = (
        anchor_pos_res.info.get("rid_mismatches", 0)
        + anchor_pos_res.info.get("shape_mismatches", 0)
    )
    if anchor_mismatch_count > 0:
        penalties.append(Penalty(
            category="Anchor Position Mismatch (MINOR)",
            count=anchor_mismatch_count,
            unit=PENALTY_ANCHOR_POSITION,
            total=PENALTY_ANCHOR_POSITION * anchor_mismatch_count,
        ))

    # [7g] Level 3: Container Context Audit (MINOR -5 per mismatch)
    container_ctx_res = audit_container_context(doc_orig, doc_out)
    all_errors.extend(container_ctx_res.errors)
    container_violation_count = (
        container_ctx_res.info.get("rid_violations", 0)
        + container_ctx_res.info.get("shape_violations", 0)
    )
    if container_violation_count > 0:
        penalties.append(Penalty(
            category="Container Context Mismatch (MINOR)",
            count=container_violation_count,
            unit=PENALTY_CONTAINER_CONTEXT,
            total=PENALTY_CONTAINER_CONTEXT * container_violation_count,
        ))

    # [7h] Blank Page & Section Break Waste Audit
    blank_page_res = audit_blank_pages(doc_orig, doc_out)
    all_errors.extend(blank_page_res.errors)
    blank_page_extra = blank_page_res.info.get("extra_empty", 0)
    if blank_page_extra > 0:
        penalties.append(Penalty(
            category="Blank Page Berlebih (MAYOR)",
            count=blank_page_extra,
            unit=PENALTY_BLANK_PAGE,
            total=PENALTY_BLANK_PAGE * blank_page_extra,
        ))
    sectpr_waste_extra = blank_page_res.info.get("extra_waste", 0)
    if sectpr_waste_extra > 0:
        penalties.append(Penalty(
            category="Section Break Waste (MINOR)",
            count=sectpr_waste_extra,
            unit=PENALTY_SECTPR_WASTE,
            total=PENALTY_SECTPR_WASTE * sectpr_waste_extra,
        ))

    # [7i] Formula Alignment Audit (MINOR -3 per alignment violation)
    formula_align_res = audit_formula_alignment(doc_out, doc_orig=doc_orig)
    all_errors.extend(formula_align_res.errors)
    formula_align_violations = formula_align_res.info.get("violations", 0)
    if formula_align_violations > 0:
        penalties.append(Penalty(
            category="Formula Alignment Salah (MINOR)",
            count=formula_align_violations,
            unit=PENALTY_FORMULA_ALIGNMENT,
            total=PENALTY_FORMULA_ALIGNMENT * formula_align_violations,
        ))

    score, total_penalty = calculate_score(penalties)
    has_xml_fatal = (multicol_broken > 0) or (shape_hits > 0)
    label = status_label(score, has_xml_fatal=has_xml_fatal)

    # -------------------------------------------------------------------------
    # [8] Anomaly Detection + Master Prompt Builder (NON-SCORING)
    #
    # File audit-unik_<doc>.txt ditulis bila ada salah satu dari:
    #   - anomali heuristik (STYLE_MISMATCH / FONT_OVERRIDE / SPURIOUS_NUMBERING)
    #   - FATAL XML KOLOM (multicol_broken)
    #   - FATAL XML HEADER SHAPE (shape_hits)
    #   - selisih jumlah tabel body di luar toleransi
    #   - sectPr distribution divergen / flush-at-end
    # -------------------------------------------------------------------------
    anomalies = detect_anomalies(doc_orig, doc_out)
    has_unik_findings = (
        bool(anomalies)
        or multicol_broken > 0
        or shape_hits > 0
        or bool(table_res.errors)
        or bool(sectpr_dist_res.errors)
        or border_res.info.get("invisible_count", 0) > 0
        or border_res.info.get("thin_count", 0) > 0
        or bool(empty_sec_res.errors)
        or bool(blank_page_res.errors)
    )
    anomaly_path = None
    if has_unik_findings:
        master_content = build_master_prompt(
            doc_name=doc_name,
            template_name=template_path.name,
            output_name=output_path.name,
            anomalies=anomalies,
            multicol_res=multicol_res,
            header_shape_res=header_shape_res,
            table_res=table_res,
            border_res=border_res,
            sectpr_dist_res=sectpr_dist_res,
        )
        anomaly_path = write_anomaly_file(
            Path(__file__).resolve().parent, doc_name, master_content
        )

    # -------------------------------------------------------------------------
    # Tulis laporan TXT
    # -------------------------------------------------------------------------
    report = render_report(
        template_path=template_path,
        output_path=output_path,
        score=score,
        total_penalty=total_penalty,
        label=label,
        penalties=penalties,
        hf_res=hf_res,
        style_res=style_res,
        page_res=page_res,
        img_res=img_res,
        latex_leaks=latex_leaks,
        fig_pos_res=fig_pos_res,
        numbering_res=numbering_res,
        double_num_res=double_num_res,
        run_fmt_res=run_fmt_res,
        table_content_res=table_content_res,
        font_res=font_res,
        multicol_res=multicol_res,
        header_shape_res=header_shape_res,
        table_res=table_res,
        sectpr_dist_res=sectpr_dist_res,
        border_res=border_res,
        all_errors=all_errors,
        doc_name=doc_name,
        placeholder_img_res=placeholder_img_res,
        logo_res=logo_res,
        empty_sec_res=empty_sec_res,
        structural_pos_res=structural_pos_res,
        anchor_pos_res=anchor_pos_res,
        container_ctx_res=container_ctx_res,
        blank_page_res=blank_page_res,
        char_anomalies=char_anomalies,
        fc_res=fc_res,
        formula_align_res=formula_align_res,
        line_sp_res=line_sp_res,
        para_spacing_res=para_spacing_res,
        font_size_res=font_size_res,
        section_num_fmt_res=section_num_fmt_res,
    )

    with open(audit_path, "w", encoding="utf-8") as f:
        f.write(report)

    # -------------------------------------------------------------------------
    # Ringkasan terminal
    # -------------------------------------------------------------------------
    print(render_terminal_summary(score, label, total_penalty, penalties))
    if anomalies:
        print(
            f"[INFO] WARNING: Skor {score}% tapi ditemukan {len(anomalies)} "
            f"kejanggalan visual."
        )
    if has_unik_findings and anomaly_path is not None:
        print(f"[INFO] Master prompt perbaikan ditulis: {anomaly_path.name}")
    elif not has_unik_findings:
        stale_unik = Path(__file__).resolve().parent / f"audit-unik_{doc_name}.txt"
        if stale_unik.exists():
            try:
                stale_unik.unlink()
                print(
                    f"[INFO] Run ini bersih, file audit-unik lama dihapus: "
                    f"{stale_unik.name}"
                )
            except OSError as e:
                print(
                    f"[WARN] Gagal menghapus file audit-unik lama "
                    f"{stale_unik.name}: {e}"
                )
    print(f"Audit selesai. Detail tersimpan: {audit_filename}")


def audit_line_spacing(doc_out, doc_orig=None) -> AuditResult:
    """Cek line spacing setiap paragraf body text. Bandingkan output vs template."""
    import re
    res = AuditResult()

    if doc_orig is None:
        res.info = {"checked_count": 0, "mismatch_count": 0}
        return res

    FIG_RE = re.compile(r"^(?:Fig\.|Figure|Gambar)\s+\d+", re.IGNORECASE)
    TBL_RE = re.compile(r"^(?:Table|Tabel)\s+[IVXLCDM\d]", re.IGNORECASE)
    HEAD_RE = re.compile(r"^heading\s*\d*$", re.IGNORECASE)

    def _is_body(p):
        t = (p.text or "").strip()
        if not t:
            return False
        sn = (p.style.name or "") if p.style else ""
        if HEAD_RE.match(sn):
            return False
        if FIG_RE.match(t) or TBL_RE.match(t):
            return False
        return True

    def _get_ls(p):
        ls_val = p.paragraph_format.line_spacing
        if ls_val is None:
            return None, None
        if isinstance(ls_val, (int, float)):
            return (float(ls_val), True) if ls_val < 10 else (float(ls_val) / 12700, False)
        try:
            return float(ls_val) / 12700, False
        except Exception:
            return None, None

    orig_bdy = [p for p in doc_orig.paragraphs if _is_body(p)]
    out_bdy = [p for p in doc_out.paragraphs if _is_body(p)]

    checked = mismatch = 0
    n = min(len(orig_bdy), len(out_bdy), 50)

    for i in range(n):
        ols, orel = _get_ls(orig_bdy[i])
        pls, prel = _get_ls(out_bdy[i])
        if ols is None or pls is None:
            continue
        checked += 1
        if orel and prel:
            if abs(ols - pls) > 0.05:
                mismatch += 1
        elif not orel and not prel:
            if abs(ols - pls) > 0.1:
                mismatch += 1
        else:
            mismatch += 1

    res.info = {"checked_count": checked, "mismatch_count": mismatch,
                "orig_body_count": len(orig_bdy), "out_body_count": len(out_bdy)}
    return res


if __name__ == "__main__":
    main()
