# PaperFull Preview & Export Fix — 6 Juli 2026

## Ringkasan

Semua fix dari percakapan tentang perbaikan PDF preview dan export DOCX untuk PaperFull, mencakup 3 area utama: konten hilang, tabel berantakan, dan font rusak.

---

## 1. Konten Paper Hilang di PDF Preview

**Masalah:** Preview PDF dan export PDF hanya menampilkan abstrak + referensi tanpa isi section. Export DOCX normal (lengkap).

**Root Cause:** Paper JSON dari DB struktur nested `{paper_data: {paper: {section1: ...}}}`. Generator membaca `section1..N` dari top-level JSON. Export DOCX berhasil karena `_make_generate_adapter` unwrap `paper_data.paper` → flat sebelum generator membaca. Preview PDF **melewatkan** langkah unwrap ini.

**Fix:** `backend/main.py`

Unwrap `paper_data.paper` di 2 tempat:
- **`paper_pdf_preview` endpoint** (~line 2644) — sebelum normalisasi
- **`_pdf_preview_render`** (~line 2587) — safety net saat baca JSON

```python
if "paper_data" in paper:
    pd = paper["paper_data"]
    if isinstance(pd, dict):
        paper = pd.get("paper", pd)
        for key in ("figures", "tables", "equations"):
            if key in pd and key not in paper:
                paper[key] = pd[key]
```

Berlaku untuk **semua 49 journal generator** tanpa perubahan per-generator.

---

## 2. Tabel Overflow/Overlap di Preview PDF

**Masalah:** Tabel di section 2-kolom confined ke lebar 1 kolom → teks body overlap di samping tabel. Terjadi di semua journal yang punya layout 2-column.

**Root Cause:** generator `add_table()` (python-docx) otomatis mengikuti lebar section. Di section 2-col, tabel hanya selebar 1 kolom.

**Fix:** `backend/tools/Journal/JCEFgen.py`

Section break di `add_table_block()`:
```python
# Sebelum tabel: 2-col → 1-col
_emit_section_break(doc, num_cols=1, sec_type="continuous")
# ... render caption + table ...
# Setelah tabel: 1-col → 2-col
_emit_section_break(doc, num_cols=2, sec_type="continuous")
```

**Catatan:** Hanya JCEF yang butuh fix ini (2-col layout + tabel). Generator lain (IEEE, Elsevier, ACM, dll) pakai 1-col layout → tidak kena.

---

## 3. Font Rusak / Missing di PDF Preview

**Masalah:** Semua journal — tabel overlap, teks bertumpuk, layout berantakan di PDF preview (LibreOffice render). DOCX export di MS Word normal.

**Root Cause:** **LibreOffice 7.3.7 tidak punya font Microsoft** — Times New Roman, Arial, Calibri, Cambria, Palatino Linotype, dll **semua missing**. LO substitusi sembarangan → metrics beda → layout hancur.

46 dari 49 generator pakai font yang tidak ada di sistem.

**Fix:** Install font + fontconfig aliases

### Font Installed

| Font Requested | Resolved To | Sumber |
|---|---|---|
| Times New Roman | ✅ **Times New Roman** (asli) | `ttf-mscorefonts-installer` |
| Arial | ✅ **Arial** (asli) | `ttf-mscorefonts-installer` |
| Calibri | **Carlito** (metric-compatible) | `fonts-crosextra-carlito` |
| Cambria / Cambria Math | **Caladea** (metric-compatible) | `fonts-crosextra-caladea` |
| Palatino Linotype | **P052** (metric-compatible) | TeX Gyre Pagella (via `fonts-texgyre`) |
| Gadugi | **Noto Sans** | `fonts-noto` |
| Sakkal Majalla | **Noto Sans Arabic** | `fonts-noto` |
| Cordia New / Angsana New | **Noto Sans/Serif Thai** | `fonts-noto` |
| PT Serif | **Liberation Serif** | `fonts-liberation` |
| Sorts Mill Goudy | **Liberation Serif** | `fonts-liberation` |
| MS Mincho | **Noto Serif CJK JP** | `fonts-noto-cjk` |

### Fontconfig Aliases

File: `/etc/fonts/conf.d/99-paperfull-font-aliases.conf`

Mapping font proprietary MS → metric-compatible open substitutes via XML alias config, bukan rename font di generator. Ini berarti generator tetap pakai nama font asli di DOCX → MS Word render sempurna → LibreOffice pakai substitute.

---

## 4. Fix Pendukung

### 4a. JWT Auth Optional untuk Preview
**File:** `backend/main.py`

`POST /api/papers/<id>/pdf-preview` → `@jwt_required(optional=True)`. Paper_id UUID unguessable cukup sebagai auth.

### 4b. Title Kosong → 404
**File:** `backend/main.py`

Serve endpoint cek `if journal_code:` (tidak perlu `title` truthy), fallback `title or "paper"`.

### 4c. Border Tabel Full Grid
**File:** `backend/tools/Journal/JCEFgen.py`

Border 3-line horizontal → full grid: `{top, bottom, left, right, insideH, insideV}`.

### 4d. Tombol Ekspor DOCX di Preview Tab
**File:** `frontend/src/components/PreviewTab.vue`

Tombol "Download" jadi 2 tombol: **Ekspor PDF** + **Ekspor DOCX**.

---

## Commits

| Hash | Deskripsi |
|------|-----------|
| `a831ad4` | JWT optional + auth fix untuk preview |
| `740ad4..` | Unwrap `paper_data.paper` sebelum PDF render |
| `b4e96a0` | Tabel full-width dengan section break 1-col |
| `e60d83f` | Serve endpoint fallback title kosong |
| `648537f` | Border tabel full grid |
| `6ba1cea` | Tombol Ekspor DOCX di Preview tab |

Font install tidak di-commit (system-level).

---

## Cara Test

1. Hard refresh browser (`Ctrl+Shift+R`)
2. Buka paper → tab Preview
3. Cek: semua section tampil? tabel rapi? font sesuai?
4. Klik "Ekspor DOCX" → download, cek di Word
5. Ganti paper beda journal → repeat

Jika ada journal tertentu yang masih bermasalah, kirim screenshot + nama journal.
