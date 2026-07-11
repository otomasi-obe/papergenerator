# PaperFull UI Review — Post-Login Pages

**Date:** 2026-07-11
**Reviewer:** AI (Hermes Agent)
**Scope:** Semua halaman setelah login (Dashboard, Editor, Tools, Preview, Token Modal, AI Assistant)
**Excluded:** Landing page

---

## 1. Header Bar (Global — semua halaman)

### ✅ Yang sudah bagus
- Logo dan brand placement jelas
- User menu dropdown functional
- Token meter informatif

### ⚠️ Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| Header terlalu crowded | 🔴 High | Terlalu banyak kontrol sejajar: logo, Update, token meter, Beli Token, bell, user menu |
| Token meter `0/500.000` terlihat seperti input field | 🟡 Medium | Bukan indicator, mirip text field |
| `Beli Paket Token` (hijau) lebih dominan dari `+ New Paper` (biru) | 🟡 Medium | Visual hierarchy salah — billing action > core action |
| Button styles campur | 🟡 Medium | Outlined beige, solid green, solid blue, icon-only, pill — ga unified |
| Disabled Undo/Redo terlalu pudar | 🟢 Low | Hampir invisible, contrast terlalu rendah |

### 💡 Rekomendasi
- Group billing controls (token + beli) ke satu area, kurangi visual weight
- Token meter pakai progress bar style, bukan bordered pill
- Standardisasi button styles: 1 primary (blue), 1 secondary (outlined), 1 accent (green hanya untuk billing)

---

## 2. Dashboard

### ✅ Yang sudah bagus
- Layout simple dan clear
- Paper card rounded corners, warm palette
- Action buttons (Open, Copy, Delete) discoverable

### ⚠️ Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| Tanpa max-width container | 🟡 Medium | Konten stretch full width, terasa sparse di layar lebar |
| Paper card dan `+ New Paper` ga aligned | 🟡 Medium | Card kiri, button jauh di kanan — weak relationship |
| Card surface sama warnanya dengan background | 🟡 Medium | Card ga "pop", kurang kontras dengan page background |
| Button `Open` terlalu besar vs `Copy`/`Delete` | 🟡 Medium | Proporsi ga balance di dalam card |
| `Delete` terlalu pudar (red ghost) | 🟢 Low | Destructive action harus jelas tapi ini terlalu faint |
| Metadata pills low contrast | 🟢 Low | "Updated 1m ago" dan "0 images" sulit dibaca |

### 💡 Rekomendasi
- Tambah `max-width: 960px` container dengan `margin: 0 auto`
- `+ New Paper` aligned di row yang sama dengan "My Papers" title
- Card background sedikit lebih putih dari page background (contoh: page `#faf8f5`, card `#ffffff`)
- Normalize button sizes di dalam card
- Delete button: red outlined, bukan ghost

---

## 3. Editor Page

### ✅ Yang sudah bagus
- Section structure jelas (Section I, II, III + subsections)
- Drag-to-reorder functional
- Content type buttons (+ Text, + Image, + Table, + Formula) mudah ditemukan
- Auto-save indicator

### ⚠️ Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| **Border overdose** | 🔴 High | Semua card, input, inner block pakai warna border yang sama (gold/tan) → visual noise |
| Section labels uppercase serif | 🟡 Medium | TITLE, AUTHORS, ABSTRACT pakai serif bold — inkonsisten sama sans-serif UI lainnya |
| Placeholder text low contrast | 🟡 Medium | "Paper title...", "Name", "Email" terlalu pudar |
| Card-inside-card effect | 🟡 Medium | Author block di dalam section card → visual clutter |
| Separator `\|` plain text | 🟢 Low | Antara "← Kembali ke Dashboard" dan title — looks cheap |
| Form-heavy feel | 🟡 Medium | Lebih mirip admin panel daripada paper editor |
| Image error state kurang jelas | 🟢 Low | "⚠️ Gambar gagal dimuat" — bisa lebih informatif |

### 💡 Rekomendasi
- Input border: `#d6d0c4` (subtle), card border: `#c4b89c` (sedikit lebih kuat) — buat hierarchy
- Labels: sans-serif semua, uppercase OK tapi pakai font-weight 600 bukan serif bold
- Placeholder: minimum contrast ratio 4.5:1
- Author fields: hapus inner border, pakai spacing/indent saja
- Separator: ganti dengan CSS divider atau hapus

---

## 4. Tools Panel

### ✅ Yang sudah bagus
- Grid layout 2 kolom rapi
- Card styles konsisten
- Label + icon per tool jelas

### ⚠️ Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| **Mixed icon styles** | 🔴 High | Sebagian emoji (🌐✨🧬), sebagian flat icon, sebagian outlined — ga kohesif |
| "Plagiarism Check" wrap 2 baris | 🟢 Low | Card lain 1 baris, grid ga rata |
| Banyak empty space di bawah grid | 🟢 Low | Tools grid ga fill panel height |
| Nama tool campur bahasa | 🟢 Low | "Literatur" (ID) di antara English tool names |

### 💡 Rekomendasi
- Pilih satu icon style: semua emoji ATAU semua SVG/Lucide icons
- "Plagiarism Check" → "Plagiarism" atau perkecil font sedikit
- Fill empty space dengan tool descriptions atau tips

---

## 5. Preview Tab

### ✅ Yang sudah bagus
- PDF berhasil render
- Export PDF/DOCX controls ada
- Zoom in/out functional

### ⚠️ Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| Default zoom terlalu kecil | 🟡 Medium | PDF ga readable tanpa zoom in manual |
| Ga ada fit-to-width / zoom percentage | 🟡 Medium | User ga tau zoom level saat ini |
| PDF ga centered di viewer | 🟢 Low | Terlalu banyak blank space di bawah |

### 💡 Rekomendasi
- Default: fit-to-width
- Tambah zoom percentage indicator (contoh: "75%")
- Center PDF secara horizontal dan vertikal di viewer area

---

## 6. Token Detail Modal

### ✅ Yang sudah bagus
- 3 metric cards (Sisa Token, Dibeli, Dipakai) warna-coded dan jelas
- Layout clean dengan chart area dan transaction history
- Empty state messaging ada

### ⚠️ Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| Modal terlalu tinggi | 🟡 Medium | Content bawah terpotong viewport, butuh scroll internal |
| AI Assistant button overlap modal | 🟢 Low | Floating button tetap visible di atas modal |
| Empty state terlalu plain | 🟢 Low | "Belum ada data pemakaian" — bisa pakai icon/illustration |

### 💡 Rekomendasi
- `max-height: 80vh` + `overflow-y: auto` pada modal body
- Hide floating AI Assistant saat modal open, atau z-index di bawah modal
- Empty state: tambah subtle icon

---

## 7. AI Assistant Floating Panel

### ✅ Yang sudah bagus
- Header navy gradient — solid, professional
- Suggestion chips — berguna, user ga bingung mau tanya apa
- Greeting personal — "Halo [nama]!" pakai nama user, friendly
- Input area jelas — ada attach button, send button
- Maximize/minimize functional

### ⚠️ Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| **Border terlalu neon** | 🟡 Medium | Teal/gold border + glow = looks dev/debug, bukan production |
| **Suggestion chips kebanyakan** | 🟡 Medium | 8 chips di panel kecil → cramped, text terpotong |
| **Typography campur** | 🟡 Medium | Greeting serif bold, header sans-serif, chips sans-serif |
| **"Clear" aktif di chat kosong** | 🟢 Low | Ga ada gunanya, misleading |
| **Send button terlalu pudar** | 🟢 Low | Terlihat disabled padahal cuma belum ada text |
| **Overlap editor content** | 🟡 Medium | Panel nutupin Authors/Abstract, editor ga auto-resize |
| **Floating button terlalu dominan** | 🟡 Medium | Gradient teal + glow + dashed ring animation — gimmicky |
| **"AI Assistant" vs "AI Chat" duplikasi** | 🟢 Low | Header bilang "AI Assistant", sub-header bilang "AI Chat" |

### 💡 Rekomendasi
- Border: hapus, ganti `box-shadow: 0 8px 32px rgba(0,0,0,.12)` saja
- Chips: max 4 visible, sisanya collapsible "Lainnya..."
- Typography: pure sans-serif di dalam panel
- Button pill: simpler gradient, hapus ring animation
- Editor integration: saat panel open, editor content width shrink
- Disable "Clear" dan "Export Draft" saat chat kosong
- Pilih satu nama: "AI Assistant" everywhere

---

## Ringkasan Prioritas Fix

### 🔴 High Impact (fix pertama)
1. **Unify button system** — 1 primary (blue), 1 secondary (outlined), 1 destructive (red outlined)
2. **Reduce border noise di editor** — input border subtle, card border sedikit lebih kuat
3. **Unify icon set di Tools** — pilih satu style konsisten
4. **Header declutter** — group billing controls, kurangi visual weight

### 🟡 Medium Impact
5. **Improve contrast** — placeholder text, disabled buttons, metadata pills
6. **Max-width container** — dashboard content jangan stretch full width
7. **PDF preview default zoom** — fit-to-width sebagai default
8. **AI Assistant border/shadow** — hapus neon border, pakai subtle shadow
9. **Suggestion chips** — max 4, typography konsisten
10. **Editor-Assistant integration** — editor shrink saat panel open

### 🟢 Low Impact (nice to have)
11. Separator `|` → CSS divider
12. "Plagiarism Check" wrap fix
13. Empty state improvements (icon/illustration)
14. Disable "Clear" di chat kosong
15. Nama duplikasi "AI Assistant" vs "AI Chat"

---

## Screenshots

Screenshots tersimpan di:
- Dashboard: `browser_screenshot_71988fa44a594f86b91c06ad141174a4.png`
- Editor: `browser_screenshot_3d228fc1cc854eb5baa1776a48c76a86.png`
- Tools: `browser_screenshot_6a6bed94738746a2bb4fadcd9e310c56.png`
- Preview: `browser_screenshot_86823937e57344bfba5d7f8f14b5511a.png`
- Token Modal: `browser_screenshot_2dfac14c4e6940dc89e6f24bff8a52e4.png`
- AI Assistant (Dashboard): `browser_screenshot_90f14d96e6164ecf9fc511fbe456ef66.png`
- AI Assistant (New Chat): `browser_screenshot_0268a2ae3c674896ad0347cfb92c720f.png`
- AI Assistant (Editor): `browser_screenshot_8f0c3a89f14e420ea5de84e2c7b3c78f.png`
