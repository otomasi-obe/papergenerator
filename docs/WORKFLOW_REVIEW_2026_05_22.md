# Review Workflow Sistem PaperFull — Chat, Prompt, Tools

**Tanggal:** 2026-05-22  
**Reviewer:** Kilo AI  
**Tujuan:** Memahami workflow sistem chat, prompt system, tools, dan antisipasi pertanyaan user

---

## 1. Arsitektur Sistem — Gambaran Besar

PaperFull menggunakan **mode-based routing architecture** dengan 3 komponen utama:

### 1.1 Chat System (Backend: `chat.py`)
- **Multi-chat per paper**: Setiap paper bisa punya banyak conversation thread
- **SSE streaming**: Real-time response dengan Server-Sent Events
- **Tool execution loop**: AI bisa panggil tools sampai 10 iterasi per turn
- **Mode persistence**: Mode disimpan in-memory (`_CONV_MODE` dict), reset saat restart
- **Auto-memory extraction**: Fakta user otomatis di-extract tanpa AI harus panggil tool

### 1.2 Prompt System (Backend: `mode_prompts.py`)
**8 Mode** dengan prompt dan tools berbeda:

| Mode | Ukuran Prompt | Jumlah Tools | Use Case |
|------|---------------|--------------|----------|
| `tier0` | 158 B | 1 (RouteIntent) | First turn, klasifikasi intent |
| `discovery` | 1584 B | 12 tools | Workflow 7-step: jurusan → topik → latar belakang → literatur → metode → data → confirm |
| `slr` | 644 B | 5 tools | Literature search & review |
| `edit` | 1121 B | 11 tools | Edit paper yang sudah ada |
| `rapikan` | 616 B | 4 tools | Renumber Fig/Table/Eq references |
| `revisi` | 1574 B | 17 tools | Targeted revisions (paraphrase, grammar, translate) |
| `memory` | 287 B | 2 tools | Manage project memory |
| `casual` | 158 B | 0 tools | Casual chat tanpa tools |

**Token Efficiency:**
- Sebelum: "halo" = ~13 KB (7.4 KB prompt + 4.7 KB tools)
- Sesudah: "halo" = ~520 B (tier0 mode)
- **Penghematan: >95%** untuk turn casual

### 1.3 Tool System (Backend: `chat_tools.py`)
**37 Tools Total**, dikelompokkan per fungsi:

**Discovery & Planning (12 tools):**
- `AskQuestions` - Multi-question form dengan auto-memory
- `ProposeChips` - Render clickable option chips
- `ClassifyFile` - Klasifikasi file upload (paper_slr, paper_read, data, image, template)
- `ReviewLargeFile` - Extract sections dari paper besar
- `SetCitationStyle` - Set style (ACS, APA, Chicago, Harvard, IEEE, MLA, Vancouver)
- `SetLanguage` - Set bahasa paper (id/en)

**Literature (5 tools):**
- `RunSLR` - Systematic Literature Review (async, 2-5 menit)
- `GetLiterature` - Read existing literature items
- `SearchPapers` - Search inline (tampil di chat)
- `ListAttachedFiles` - List uploaded files
- `ReadAttachedFile` - Read file content

**Paper Generation (1 tool):**
- `GenerateFullPaper` - Generate paper lengkap (chunked, 8 sections, 3-10 menit)

**Paper Editing (9 tools):**
- `GetPaperContent` - Read full paper
- `GetPaperSection` - Read specific section
- `GetPaperNumbering` - Get Fig/Table/Eq numbering
- `GetParagraphContext` - Read paragraph context
- `ProposeTitle` - Propose title change
- `ProposeAbstract` - Propose abstract change
- `ProposeKeywords` - Propose keywords change
- `ProposeSection` - Propose section change (with diff preview)
- `ProposeReference` - Propose reference change

**Revision Tools (3 tools):**
- `Paraphrase` - Paraphrase text (paragraph/section/whole)
- `FixGrammar` - Fix grammar
- `Translate` - Translate to target language

**Advanced Editing (4 tools):**
- `ReviewPaper` - Holistic review
- `ReviseData` - Revise Section 4 data
- `AddLiterature` - Add literature by keyword
- `GenerateChart` - Generate chart dari data (line, bar, scatter, hist, box, heatmap, pie)

**Export (2 tools):**
- `ProposeJournal` - Switch journal template
- `RequestExportDocx` - Export to DOCX

**Memory (2 tools):**
- `ListMemory` - List saved memory
- `DeleteMemory` - Delete memory entry
- ~~`SaveMemory`~~ - **DIHAPUS** (sekarang auto-extract)
- ~~`GetMemory`~~ - **DIHAPUS** (memory di-inject ke prompt saat needed)

**Routing (1 tool):**
- `RouteIntent` - Classify intent → switch mode

**Utility (2 tools):**
- `WebSearch` - Search web
- `WebFetch` - Fetch URL content

---

## 2. User Journey — 4 Path Utama

### Path 1: **Discovery (Dari Nol)**
**Entry point:** User baru, belum punya apa-apa

**Flow:**
1. User klik "Mulai dari nol" chip atau ketik "mau buat paper"
2. AI masuk mode `discovery`, tanya 7 step:
   - Jurusan (key=`jurusan`)
   - Topik (key=`topik`)
   - Latar belakang (key=`latar_belakang`)
   - Literatur (key=`referensi_terpilih`) → pilih: Belum / Sudah file / Keduanya
     - Jika "Belum" → `RunSLR` (async 2-5 menit)
     - Jika "Sudah file" → `ListAttachedFiles` + `ReadAttachedFile`
   - Metode (key=`metode`)
   - Data (key=`data_asli` atau `data_estimasi`)
   - Kesimpulan target (key=`kesimpulan_target`)
   - Citation style (key=`citation_style`) → ProposeChips 7 options
   - Bahasa (key=`paper_language`) → chips id/en
   - Use review data (key=`use_review_data`) → chips yes/no
3. AI restate semua jawaban, kasih `[OPSI]` 1) Generate sekarang 2) Revisi <field> 3) Ubah <field>
4. User pilih "1" → AI panggil `GenerateFullPaper`
5. Frontend render `PaperProgressBubble` dengan progress bar + Cancel/Resume/Retry buttons
6. Paper selesai 3-10 menit, auto-load di Editor

**Auto-memory:** Semua jawaban user otomatis tersimpan tanpa AI harus panggil `SaveMemory`

### Path 2: **Upload File (Sudah Punya Literatur/Data)**
**Entry point:** User upload file PDF/CSV/XLSX/image

**Flow:**
1. User drag-drop file atau klik upload
2. Frontend kirim `[FILE_IDS=xxx,yyy] --- File terlampir ---` ke chat
3. AI detect file upload, panggil `AskQuestions` per file:
   - "Ini file apa? (filename.pdf)"
   - Options: paper_slr / paper_read / data / image / template
4. User pilih option → AI panggil `ClassifyFile(file_id, kind)`
5. Jika `kind=paper_slr` AND text >3000 words:
   - AI panggil `ReviewLargeFile(file_id)`
   - Tanya one-by-one: ambil data / methods / results / abstract / literature?
6. Jika `kind=paper_read`:
   - Skip SLR, langsung retemplating
7. Jika `kind=data`:
   - Nanti bisa dipake untuk `GenerateChart` di Section 4
8. Jika `kind=image`:
   - Masuk image queue untuk paper

**Keuntungan:** User bisa skip step literatur di discovery flow

### Path 3: **Edit Paper (Paper Sudah Ada)**
**Entry point:** User sudah punya paper, mau edit

**Flow:**
1. User ketik "revisi abstract" / "tambah section" / "ganti judul"
2. AI panggil `RouteIntent` → mode `edit` atau `revisi`
3. AI baca dulu via `GetPaperSection` atau `GetPaperContent`
4. AI panggil **exactly ONE** Propose* tool:
   - `ProposeTitle` / `ProposeAbstract` / `ProposeKeywords` / `ProposeSection` / `ProposeReference`
5. Frontend render `RevisiProposalCard` dengan diff preview (old vs new)
6. User klik **Accept** → perubahan applied
7. User klik **Reject** → perubahan dismissed

**Special case — Chart:**
1. User upload CSV/XLSX atau ketik "buat grafik untuk Section 4"
2. AI baca data via `ReadAttachedFile`
3. AI panggil `ProposeChips` dengan 7 chart kinds: line, bar, scatter, hist, box, heatmap, pie
4. User pilih kind → AI panggil `GenerateChart(data, kind, title, xlabel, ylabel)`
5. Chart di-generate, masuk Section 4

### Path 4: **Paraphrase/Grammar/Translate**
**Entry point:** User mau revisi bahasa/grammar

**Flow:**
1. User ketik "parafrase paragraf ini" / "fix grammar section 2" / "translate ke English"
2. AI panggil `RouteIntent` → mode `revisi`
3. AI baca context via `GetParagraphContext` atau `GetPaperSection`
4. AI panggil tool:
   - `Paraphrase(scope, target_text)` - scope: paragraph/section/whole
   - `FixGrammar(scope, target_text)`
   - `Translate(scope, target_text, target_language)`
5. Frontend render `RevisiProposalCard` dengan diff
6. User Accept/Reject

---

## 3. Pertanyaan User yang Mungkin Muncul

### 3.1 Tentang Memory
**Q: "Kenapa SaveMemory hilang?"**  
A: Backend sekarang auto-extract fakta dari jawaban user. AI tidak perlu panggil tool lagi. Lebih efisien dan tidak lupa.

**Q: "Gimana tau memory ke-save apa engga?"**  
A: Cek log INFO di `backend/auto_memory.py`. Frontend bisa tampilkan via `/api/papers/{id}/memory`. Ada panel "Project memory" di ChatTab sidebar dengan badge count.

**Q: "Memory hilang setelah restart?"**  
A: Memory di database tetap ada. Yang hilang adalah **mode** (in-memory `_CONV_MODE` dict). AI akan re-classify via RouteIntent di turn berikutnya.

### 3.2 Tentang Mode
**Q: "Mode `revisi` belum bisa diakses?"**  
A: User harus minta "saya mau revisi" atau AI otomatis panggil `RouteIntent` dengan mode=revisi saat detect intent revisi.

**Q: "Gimana tau AI sekarang di mode apa?"**  
A: Tidak ada UI indicator mode saat ini. Bisa ditambahkan badge kecil di header chat (tier0/discovery/slr/edit/rapikan/revisi/memory/casual).

**Q: "Bisa ganti mode manual?"**  
A: Tidak ada UI untuk switch mode manual. AI yang decide via `RouteIntent`. User bisa "pancing" dengan keyword: "kembali ke awal" → discovery, "carikan literatur" → slr, "edit section" → edit.

### 3.3 Tentang Generate Paper
**Q: "Generate paper berapa lama?"**  
A: 3-10 menit tergantung kompleksitas. Ada 8 chunks: outline → section_1..5 → references → combine.

**Q: "Bisa cancel mid-generation?"**  
A: Ya. Klik tombol **Cancel** di `PaperProgressBubble`. Partial paper tetap tersimpan.

**Q: "Resume kok regenerate dari awal?"**  
A: Cek `AiJob.result.chunks_done` array. Kalau kosong berarti checkpoint tidak jalan. Debug `checkpoint_cb` di `generate_paper_chunked.py`.

**Q: "Resume saat literatur baru ditambah?"**  
A: Ada potential inconsistency. Section 1-2 pakai literatur lama, section 3-5 pakai literatur baru. Belum ada warning di UI. Bisa ditambahkan.

### 3.4 Tentang SLR
**Q: "SLR job done tapi tabel kosong sampai 30 detik?"**  
A: Bug ini sudah fixed. `runSLR` sekarang re-arm `schedulePoll()` setelah `loadJobs()`.

**Q: "V-DEEPSEEK ditolak SLR?"**  
A: Bug ini sudah fixed. V-DEEPSEEK sekarang di-whitelist di `slr_bp.py:171` dan `chat_tools.py:515`.

**Q: "AI summary tidak jalan?"**  
A: Cek env `AIOTOMASI_API` dan `AIOTOMASI_APIKEY`. Kalau kosong, AI summary skip. Ada badge "extractive only" di LiteratureTab untuk signal ini.

### 3.5 Tentang File Upload
**Q: "Upload file tapi AI tidak respon?"**  
A: AI harus detect `[FILE_IDS=...]` pattern. Cek frontend kirim format yang benar. AI akan panggil `AskQuestions` untuk classify file.

**Q: "File PDF besar (>3000 words) gimana?"**  
A: AI panggil `ReviewLargeFile` dan tanya one-by-one section mana yang mau diambil: data/methods/results/abstract/literature.

**Q: "Upload image langsung masuk paper?"**  
A: Ya, setelah classify sebagai `kind=image`. Masuk image queue, bisa dilihat di Figures tab.

### 3.6 Tentang Tools
**Q: "Kenapa AI tidak panggil tool yang saya mau?"**  
A: Tool hanya available di mode tertentu. Contoh: `Paraphrase` hanya ada di mode `revisi`. Kalau AI di mode `discovery`, tool tidak tersedia. Solusi: pancing AI untuk switch mode dengan keyword yang jelas.

**Q: "AI panggil tool tapi error?"**  
A: Cek log backend. Error di-sanitize untuk user (tidak tampilkan SQL/traceback). Full error di `app.log`.

**Q: "Bisa panggil tool manual?"**  
A: Tidak. Tools hanya bisa dipanggil AI. User interact via natural language.

### 3.7 Tentang Diff Preview
**Q: "Diff preview tidak muncul?"**  
A: Hanya Propose* tools yang render diff: ProposeTitle, ProposeAbstract, ProposeKeywords, ProposeSection, ProposeReference, Paraphrase, FixGrammar, Translate. Tools lain (GenerateFullPaper, RunSLR, dll) tidak ada diff.

**Q: "Accept tapi perubahan tidak applied?"**  
A: Cek `paperStore.acceptProposal()` di frontend. Mungkin ada race condition atau error di `paper.js`.

### 3.8 Tentang Progress & Notification
**Q: "Generate paper di chat A, switch ke chat B, gimana tau A selesai?"**  
A: `paperJobs.js` store polling setiap 3s (active) / 10s (global). Browser Notification API akan muncul toast saat job done. Bell badge di AppHeader juga update.

**Q: "Notification permission belum muncul?"**  
A: `paperJobs.js` expose `requestNotifPermission()` tapi belum dipanggil otomatis. Frontend perlu call saat user klik "Generate Paper" pertama kali.

**Q: "Progress bar stuck di 50%?"**  
A: Cek `AiJob.result.current_stage` dan `progress_percent`. Mungkin chunk hang. Bisa retry via tombol **Retry** di bubble.

---

## 4. Pain Points & Confusion Points

### 4.1 Mode Tidak Visible
**Problem:** User tidak tau AI sekarang di mode apa.  
**Impact:** User bingung kenapa tool tertentu tidak available.  
**Solution:** Tambahkan badge mode di chat header. Contoh: `🔍 Discovery` / `✏️ Edit` / `📚 SLR`.

### 4.2 Memory Auto-Extract Tidak Transparan
**Problem:** User tidak tau fakta apa yang ke-save.  
**Impact:** User tidak percaya memory system.  
**Solution:** 
- Toast notification saat memory saved: "✓ Tersimpan: topik = Machine Learning"
- Highlight memory panel di sidebar saat ada update baru

### 4.3 File Upload Flow Panjang
**Problem:** User upload 5 file → AI tanya 5 kali "ini file apa?"  
**Impact:** Tedious, user mungkin abandon.  
**Solution:**
- Batch question: "Kamu upload 5 file. Classify semuanya sekaligus?"
- Auto-detect file type dari extension/content (PDF = paper, CSV = data, PNG = image)

### 4.4 Generate Paper Tidak Ada Preview
**Problem:** User tidak tau paper akan seperti apa sebelum generate.  
**Impact:** User takut waste 10 menit untuk hasil yang tidak sesuai.  
**Solution:**
- Tampilkan outline preview setelah step 7 discovery
- "Paper akan punya 5 section: Introduction, Literature Review, Methodology, Results, Conclusion. Lanjut generate?"

### 4.5 SLR Async Tidak Ada ETA
**Problem:** "2-5 menit" terlalu vague.  
**Impact:** User tidak tau harus tunggu berapa lama.  
**Solution:**
- Real-time progress: "Searching IEEE... 12/50 papers found"
- ETA based on query complexity: "Estimated 3 minutes remaining"

### 4.6 Mode Switch Tidak Smooth
**Problem:** User di mode `discovery`, tiba-tiba mau edit section → AI harus panggil RouteIntent → extra turn.  
**Impact:** Feels clunky.  
**Solution:**
- Allow multi-mode tools: `GetPaperSection` available di semua mode
- Smart mode detection: "edit section 2" → auto-switch ke mode `edit` tanpa extra turn

### 4.7 Diff Preview Tidak Ada Version History
**Problem:** User accept proposal, tapi mau undo → tidak bisa.  
**Impact:** User takut accept.  
**Solution:**
- Version history per section: "Section 2 (v3) ← v2 ← v1"
- Undo button: "Kembalikan ke versi sebelumnya"

### 4.8 Citation Validator Belum Ada
**Problem:** Paper punya `[L1]`, `[L2]` tapi tidak match ke LiteratureItem ID.  
**Impact:** Broken references.  
**Solution:**
- Validator di backend: parse `[Ln]` tokens, match ke literature.id
- Warning di frontend: "⚠️ 3 citations tidak ditemukan di Literature tab"

---

## 5. User Understanding Level — Segmentasi

### 5.1 Beginner (Mahasiswa S1/S2 Baru)
**Karakteristik:**
- Belum pernah buat paper akademik
- Tidak tau apa itu SLR, citation style, abstract
- Butuh guidance step-by-step

**Pertanyaan Tipikal:**
- "Apa itu SLR?"
- "Citation style itu apa? Pilih yang mana?"
- "Abstract itu apa bedanya sama introduction?"
- "Berapa halaman paper yang bagus?"

**Kebutuhan:**
- Tooltips di setiap step: "SLR = Systematic Literature Review, proses cari dan review paper relevan"
- Default recommendations: "Untuk jurnal teknik, pilih IEEE citation style"
- Examples: "Contoh abstract yang bagus: ..."

### 5.2 Intermediate (Mahasiswa S2/S3, Dosen Muda)
**Karakteristik:**
- Sudah pernah buat paper 1-3 kali
- Tau basic structure paper
- Butuh efficiency tools

**Pertanyaan Tipikal:**
- "Bisa import paper saya yang lama?"
- "Gimana cara ganti template jurnal?"
- "Bisa export ke LaTeX?"
- "Literatur bisa auto-cite?"

**Kebutuhan:**
- Bulk operations: "Import 10 papers sekaligus"
- Template library: "50+ journal templates"
- Advanced export: DOCX, LaTeX, Markdown

### 5.3 Advanced (Dosen Senior, Researcher)
**Karakteristik:**
- Sudah publish 10+ papers
- Tau semua convention
- Butuh customization & control

**Pertanyaan Tipikal:**
- "Bisa custom citation format?"
- "Bisa integrate dengan Zotero/Mendeley?"
- "Bisa batch generate 5 papers sekaligus?"
- "API access untuk automation?"

**Kebutuhan:**
- Custom templates: "Upload template jurnal sendiri"
- API endpoints: "POST /api/papers/generate dengan JSON payload"
- Batch processing: "Generate 5 papers dari 5 topik berbeda"

---

## 6. Recommendations — Improvement Prioritas

### Priority 1 (High Impact, Low Effort)
1. **Mode badge di chat header** — user tau context sekarang
2. **Memory save notification** — transparency auto-extract
3. **File type auto-detect** — reduce question count
4. **SLR progress indicator** — real-time "12/50 papers found"
5. **Citation validator** — detect broken `[Ln]` references

### Priority 2 (High Impact, Medium Effort)
6. **Outline preview sebelum generate** — reduce uncertainty
7. **Version history per section** — undo capability
8. **Tooltips untuk beginner** — explain SLR, citation style, abstract
9. **Template library** — 50+ journal templates
10. **Batch file upload** — classify 5 files sekaligus

### Priority 3 (Medium Impact, High Effort)
11. **Multi-mode tools** — GetPaperSection available di semua mode
12. **Smart mode detection** — auto-switch tanpa extra turn
13. **Custom citation format** — untuk advanced users
14. **API access** — automation untuk researchers
15. **LaTeX export** — untuk jurnal yang require LaTeX

---

## 7. Kesimpulan

### Strengths
✅ **Token efficiency** — 95% reduction untuk casual turns  
✅ **Auto-memory** — user tidak perlu eksplisit save  
✅ **Chunked generation** — resilient dengan cancel/resume  
✅ **Mode-based routing** — focused tools per context  
✅ **Diff preview** — user bisa review sebelum accept  

### Weaknesses
⚠️ **Mode tidak visible** — user tidak tau context  
⚠️ **File upload tedious** — tanya 1-by-1  
⚠️ **No preview sebelum generate** — uncertainty tinggi  
⚠️ **No version history** — tidak bisa undo  
⚠️ **Citation validator missing** — broken refs possible  

### Next Steps
1. **Manual E2E test** di paperfull.app — verify semua flow jalan
2. **User testing** dengan 3 segmen (beginner/intermediate/advanced)
3. **Implement Priority 1 improvements** — quick wins
4. **Monitor user questions** di production — adjust docs/tooltips
5. **Iterate based on feedback** — continuous improvement

---

**End of Review**
