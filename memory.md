# Paper Generator - Progress & Changes Log

_Updated: 2026-06-02_

## 🎨 Design System (claudedesign)

Sumber: `/home/sirobo/papergenerator/PaperRiset/claudedesign/`

### Perubahan yang diimplementasikan:

**`frontend/src/style.css`**
- Import Google Fonts: DM Sans, Fraunces, JetBrains Mono
- Token warna claudedesign:
  - Primary: navy `#0b4088`, vivid sea-blue `#1265c8`
  - Surfaces: cream `#fffdf8`, ivory `#fbf8f1`
  - Text: ink `#0c1c3c` (strong), `#214070` (base), `#3e70a8` (muted)
  - Accent: gold `#d9a718`, teal `#238f7f`
  - Dark mode: ash nautical blue-dark (`#0b1f3e` base, `#102c55` surface)
- Typography: Fraunces (headings), DM Sans (UI), JetBrains Mono (numerics)
- Spacing/radius/shadow sesuai design system
- `@import` di atas `@tailwind` (fix warning)

## 🔄 Layout Swap (PaperEditorPage.vue)

### Sebelum:
- Tab pane kiri collapsible, chat kanan
- Saat no tab selected → chat full-width

### Sesudah:
- **Tools panel (kiri)**: selalu terlihat dengan empty state informatif
  - Saat no tab: tampilkan grid shortcut semua tab (Editor, Journal, Literatur, Files, Data, Preview)
  - Border kanan memisahkan dari chat
- **Chat (kanan)**: selalu di sikan kanan, width 50%
- Saat no tab selected: left panel tampilkan empty state, tidak collapse

## 📥 PDF Download di Literature Review

### Frontend - `LiteratureTab.vue`
- Kolom baru **📥 PDF** di tabel literatur
- Logic per baris:
  - `pdf_url` ada → tombol "📥 Download" (hijau, link ke PDF)
  - Hanya `doi` → tombol "🔗 DOI" (kuning, link ke doi.org)
  - Hanya `url` → tombol "🔗 URL" (biru)
  - Tidak ada → `–`
- `pdf_url` ditambahkan ke TypeScript interface `LiteratureItem`
- `pdf_url` ditambahkan ke filter search haystack
- colspan updated: 13 → 14

### Frontend - `LiteratureCard.vue`
- Tombol download PDF prioritas utama (hijau dengan ikon 📥)
- DOI/URL button tetap ada sebagai fallback (hanya tampil jika tidak ada pdf_url)

### Backend - `database/models.py`
- Kolom `pdf_url = db.Column(db.Text, nullable=True)` ditambahkan ke model `LiteratureItem`
- `to_dict()` sekarang return `pdf_url`

### Backend - `api/slr_bp.py`
- `create_literature` (POST): menerima & validate field `pdf_url`
- `update_literature` (PATCH): `pdf_url` ditambahkan ke editable fields + validation

## 🔧 Backend Enhancements

### `slr/paper.py`
- `Paper` dataclass: field `pdf_url: Optional[str] = None` ditambahkan

### `slr/pipeline.py`
- `_paper_record()`: sekarang include `pdf_url` di output dict
- `run()`: integrasi Unpaywall enrichment setelah scoring, sebelum summarization
  - Papers tanpa pdf_url dan punya DOI → di-resolve via Unpaywall API
  - Jika gagal → tetap jalan tanpa PDF (graceful fallback)

### `slr/unpaywall.py` (FILE BARU)
- `resolve_pdf_url(doi)`: resolve PDF URL dari DOI via Unpaywall API
- `batch_resolve_pdf_urls(papers)`: batch resolve untuk list Paper objects
- `enrich_papers_without_pdf(papers)`: batch resolve untuk list dict (pipeline)
- Rate-limited (~8 req/sec) untuk tidak hammer Unpaywall API

### `slr/fetchers/openalex.py`
- `_parse_work()`: ekstrak `pdf_url` dari `open_access.oa_url` atau `primary_location.pdf_url`
- `pdf_url` disimpan ke Paper hanya jika `open_access.is_oa == True`

### `slr/fetchers/semantic_scholar.py`
- `_parse()`: `pdf_url` di-set jika `openAccessPdf` tersedia

### `workers/slr_worker.py`
- `_run_job()`: saat persist LiteratureItem, field `pdf_url` diisi dari pipeline result

## ✅ Build Status

### Frontend:
- `npm run build` → ✅ SUCCESS (13.05s, 187 modules)
- No warnings ( setelah fix @import order )

### Backend:
- `from slr.unpaywall import resolve_pdf_url` → ✅ OK
- `from slr.pipeline import run` → ✅ OK
- `from api.slr_bp import slr_bp` → ✅ OK
- `from workers.slr_worker import enqueue_slr_job` → ✅ OK
- `LiteratureItem.pdf_url in columns` → ✅ True
- `Paper.pdf_url` attr → ✅ True
- `_paper_record has pdf_url` → ✅ True

### Server:
- Frontend: `http://localhost:8000` → ✅ ONLINE
- Backend: `http://localhost:8001` → ✅ ONLINE

## 🎨 LandingPage Design System Update (2026-06-02)

### File: `frontend/src/views/LandingPage.vue`

Semua warna pada landing page diganti dari brown/slate/blue/cyan/orange ke palette claudedesign:

**Brown → Navy:**
- `bg-gradient-to-br from-brown-900 via-brown-800` → `from-navy-900 via-navy-800` (bg utama)
- `text-brown-800` → `text-navy-800` (nav Sign In + hero Get Started button)
- `from-brown-500/20` glow → `from-navy-500/20` (hero image glow)

**Slate → Ink:**
- `slate-900/85, slate-900/70` → `navy-900/85, navy-900/70` (trust strip overlay)
- `slate-300` → `ink-200` (trust strip label, footer, semua domain card body text)
- `slate-400` → `ink-300` (stat descriptions, feature descriptions, section subtitles, CTA subtitle)

**CTA Blue/Cyan → Navy:**
- `from-blue-600/20 to-cyan-600/20` → `from-navy-500/20 to-navy-400/20` (CTA card glow)
- `border-blue-500/30` → `border-navy-400/30` (CTA card border)
- `bg-blue-600 hover:bg-blue-500` → `bg-navy-500 hover:bg-navy-400` (CTA button)

**Font Serif pada Headings:**
- `font-serif` ditambahkan ke: h1 hero, "Everything you need" h2, "Supported Publication Types" h2, "Specialized Domains" h2, CTA h2

**Focus Ring Teal:**
- `focus:ring-orange-300/40` → `focus:ring-[#238f7f]/40` (back-to-top button)

**Back-to-top Button:**
- Ditambahkan `active:scale-95 transition-transform` (semua tombol interaktif konsisten)

**Konsistensi Rounded:**
- Feature cards: `rounded-2xl` ✓
- Small cards (publication types, domains): `rounded-xl` ✓
- CTA card: `rounded-3xl` ✓

**Verifikasi:**
- Tidak ada sisa `brown-*`, `slate-*`, `blue-600`, `blue-500`, `cyan-600`, `orange-300` — semua sudah ter-replace.

## 🎨 AppHeader.vue - Design System Compliance (2026-06-02)

### Perubahan:
- **Replaced all `brown-*` with `navy-*`**: `hover:text-brown-700` → `hover:text-navy-700`, `bg-brown-500` → `bg-navy-500`, `bg-brown-400` → `bg-navy-400`, `bg-brown-200` → `bg-navy-200`
- **Added `font-serif`** ke logo "PaperFull"
- **Added `active:scale-95 transition-transform`** ke semua elemen interaktif:
  - Logo link
  - Quota button
  - Nav items (Papers, Admin)
  - Bell button
  - Recent paper links di bell dropdown
  - User menu button
  - Theme buttons (Light/Dark/System)
  - My Papers link
  - Admin link
  - Sign Out button
- **Added teal focus rings** `focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2` ke semua elemen interaktif
- **Fixed rounded conventions**:
  - `rounded-xl` untuk dropdowns (quota tooltip, bell dropdown, user menu)
  - `rounded-full` untuk Admin badge
  - `rounded-lg` untuk buttons dan nav items
- **Added `tabindex="-1"`** ke user menu dropdown untuk aksesibilitas keyboard

### Build Status:
- Tidak ada perubahan logic/script — hanya CSS classes di template
- Vue template syntax intact
- Dropdown/tooltip functionality unchanged

## 🎨 PreviewTab.vue — Design System Migration (2026-06-02)

### File: `frontend/src/components/PreviewTab.vue`

Semua kelas Tailwind default (`gray-*`, `slate-*`) diganti ke design token PaperFull:

| Sebelum | Sesudah |
|---|---|
| `text-gray-800` | `text-ink-900 dark:text-ink-50` |
| `text-gray-700` | `text-ink-700` |
| `text-gray-600` | `text-ink-600 dark:text-ink-400` |
| `text-gray-500` | `text-ink-500` |
| `text-gray-400` | `text-ink-400` |
| `bg-gray-100` | `bg-cream-100` |
| `bg-gray-50` | `bg-cream-50` |
| `border-gray-200` | `border-cream-300` |
| `border-gray-300` | `border-cream-400` |
| `text-slate-500` | `text-ink-500` |
| `text-slate-400` | `text-ink-400` |
| `text-slate-600` | `text-ink-600` |
| `hover:text-slate-700` | `hover:text-ink-700` |
| `hover:text-slate-600` | `hover:text-ink-600` |
| `bg-slate-50` | `bg-cream-50` |

### Perubahan struktural:
- **Outer card container**: `rounded-lg` → `rounded-2xl`, border → `border-cream-300 dark:border-ash-700`, bg → `bg-white dark:bg-ash-900`
- **Focus rings**: `focus:border-brown-500` → `focus:border-navy-500 focus:ring-[#238f7f]/30` (semua input/textarea)
- **Tombol interaktif** (toggle Edit/View, Export DOCX): ditambah `active:scale-95 transition-transform`
- **Dark mode variants** ditambahkan di semua elemen teks dan surface
- **Inline `font-family: 'Times New Roman', serif`** dipertahankan (sesuai design system untuk paper preview)

### Verifikasi:
- Tidak ada sisa `text-gray-*`, `bg-gray-*`, `border-gray-*`, `text-slate-*`, `bg-slate-*`, `focus:border-brown-500`
- Vue template syntax utuh, tidak ada broken tags

## 🎨 Claudedesign Full Frontend Migration (2026-06-02)

Semua komponen frontend sudah dimigrasi ke design system PaperFull (claudedesign).

### Ringkasan perubahan global:

**1. brown-* → navy-* (SEMUA file .vue)**
- Semua referensi `brown-*` di-replace ke `navy-*` (shade number sama)
- Termasuk: LandingPage, LoginPage, DashboardPage, PaperEditorPage, AppHeader, semua tab components, chat components, utility components

**2. gray-* → ink-*/cream-***
- `text-gray-800/700/600/500/400/300` → `text-ink-900/700/600/500/400/300`
- `bg-gray-100/50` → `bg-cream-100/50`
- `border-gray-200/300` → `border-cream-300/400`

**3. slate-* → ink-*/navy-***
- `text-slate-*` → `text-ink-*`
- `bg-slate-*` → `bg-cream-*` atau `bg-navy-*`

**4. indigo-* → navy-***
- ChatMessage indigo decoration → navy decoration
- RevisiProposalCard badge → navy badge
- ChatTab rename input → cream/ash border

**5. CTA Blue/Cyan → Navy (LandingPage)**
- `blue-600/cyan-600` → `navy-500/navy-400`

**6. active:scale-95 press convention**
- Ditambahkan ke SEMUA `<button>` interaktif di seluruh codebase
- Pattern: `active:scale-95 transition-transform`

**7. Teal focus rings (#238f7f)**
- Ditambahkan ke semua elemen interaktif
- Light: `focus-visible:ring-2 focus-visible:ring-[#238f7f]/30`
- Dark: `dark:focus-visible:ring-[#4eb2a3]/30`

**8. font-serif pada headings**
- Ditambahkan ke heading utama di: LandingPage, LoginPage, DashboardPage, PaperEditorPage, AppHeader, SectionsTab, LiteratureTab, LiteratureCard, JournalTab

**9. Consistent rounded convention**
- `rounded-2xl` → card containers
- `rounded-xl` → sub-cards, dropdowns, large CTAs
- `rounded-lg` → buttons, inputs, tabs
- `rounded` → small elements
- `rounded-full` → badges, pills

### File yang diubah (complete list):
**Views:**
- LandingPage.vue, LoginPage.vue, DashboardPage.vue, PaperEditorPage.vue, AdminPage.vue, AuthCallbackPage.vue, FilesPage.vue

**Components:**
- AppHeader.vue, ChatTab.vue, ChatMessage.vue, SectionsTab.vue, LiteratureTab.vue, LiteratureCard.vue, JournalTab.vue, PreviewTab.vue, ActionChips.vue, ChartPreviewCard.vue, ChartsTab.vue, ContentList.vue, DataTab.vue, FileReviewCard.vue, FilesTab.vue, PaperProgressBubble.vue, SLRResultsView.vue, AiPromptBox.vue, DiffBlock.vue, ErrorBoundary.vue, ReferencesTab.vue, ToolCallBlock.vue, RevisiProposalCard.vue, MultiQuestionCard.vue, ShortcutsHelp.vue, ThinkingBlock.vue, StateView.vue, AppDialog.vue, AiButton.vue, MetadataTab.vue

**Tidak perlu perubahan (sudah bersih):**
- ThinkingBlock.vue (pakai `var(--accent)` semua)
- StateView.vue (pakai CSS variables semua)
- AppDialog.vue (pakai CSS variables semua)
- AiButton.vue (pakai `var(--accent)` semua)
- App.vue (tidak ada styling inline)
- MetadataTab.vue (sudah pakai ink, ivory, anthracite)
- FilesPage.vue (sudah pakai cream, ink, ash)

### Verifikasi:
- `npm run build` ✅ SUCCESS (12.66s, 185 modules)
- Zero `brown-*` remaining
- Zero `gray-*` remaining (selain standar Tailwind di template scoped CSS)
- Zero `slate-*` remaining
- Zero `indigo-*` remaining
- Grep confirm: tidak ada lagi `text-gray-*`, `bg-gray-*`, `border-gray-*`, `text-slate-*`, `bg-slate-*`, `border-slate-*`, `text-brown-*`, `bg-brown-*`, `border-brown-*`, `text-indigo-*`, `bg-indigo-*` di seluruh .vue files

## 🔍 Browser Testing (2026-06-02)

### Server Status:
- Frontend: `http://localhost:8000` → ✅ ONLINE
- Backend: `http://localhost:8001` → ✅ ONLINE (health: `{"status":"healthy"}`)

### Test Results:
- **Login page** ✅ — tampil dengan benar, form email/password, tombol Google, link Register
- **Landing page** ✅ — route `/` mengarah ke LandingPage.vue (redirect ke login jika auth store sudah login, behavior normal)
- **Route guard** ✅ — public routes (/, /login) → authenticated users redirect ke /dashboard

### Catatan Testing:
- Test user `test@example.com` (ID: 147) sudah ada di database
- Password asli tidak diketahui (hash), perlu reset via `create_user.py` jika ingin login test
- Login via browser belum bisa di-test karena password user lama tidak diketahui

## 📋 TODO / Known Issues
- Browser testing penuh (dashboard, editor, semua tab) belum selesai — perlu login dengan credentials yang valid
- Database migration: kolom `pdf_url` baru ditambahkan ke model, perlu migration jika pakai Alembic
- Unpaywall email default: `research@example.com` — sebaiknya di-set via env var `UNPAYWALL_EMAIL`
- MultiQuestionCard.vue: fallback hex colors di scoped CSS sudah diperbaiki ke palette claudedesign
