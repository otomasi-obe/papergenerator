# HANDOFF — Wave 1 + Wave 2: Bug Fixes & New Tools

**Tanggal:** 2026-05-22 (lanjutan dari HANDOFF_2026_05_22.md)
**Branch:** `v1` (uncommitted, 50 file modified, 3 file baru, 3 file dihapus)
**Project:** `/home/sirobo/papergenerator`
**Status:** Implementation complete. 117/117 backend tests PASS, frontend build clean (5.05s). Belum di-commit, belum di-deploy.

---

## 1. Konteks Sesi

Sesi ini adalah lanjutan langsung dari `HANDOFF_2026_05_22.md`. User minta:

1. Baca `perintah2.txt` (banner error 524 di Literatur tab) dan `perintah.txt` (revisi pipeline lengkap).
2. Hapus semua sisa OpenAI di backend.
3. Hapus dead code yang tidak dipakai.
4. Pakai `/systematic-debugging` untuk debug semua workflow.
5. Kerahkan agent paralel.

Saya jalankan **5 agent analisa** dulu (read-only), kemudian **2 wave × 5 agent paralel** untuk eksekusi (10 agent total). File boundary di-pisah supaya tidak tabrakan.

---

## 2. Apa yang Dikerjakan

### Wave 0 — Analisa (5 explore agents, read-only)

5 agent analisa thorough men-scan: SLR 524 root cause, paper generation pipeline, editor revision tools, OpenAI usage, image queue + bug `getItemNumber`. Output → 5 laporan terstruktur jadi input Wave 1+2.

### Wave 1 — Fixes (5 agents paralel)

| Agent | Scope | File |
|---|---|---|
| **A** | OpenAI removal + PG safeguards | `backend/app.py`, `backend/requirements.txt` |
| **B** | Dead code purge | `backend/archive/`, `backend/generate_docx_from_json.py`, `prompt/prompt.txt` (root) |
| **C** | Pipeline integration fixes | `backend/generate_paper_chunked.py`, `backend/chat_tools.py`, `backend/mode_prompts.py` |
| **D** | SLR resilience (524 fix) | `backend/slr_bp.py`, `backend/slr_worker.py`, `backend/SLR/scoring.py`, `frontend/.../LiteratureTab.vue` |
| **E** | Frontend chat hooks + rebuild | `frontend/src/stores/chat.js`, `paper.js`, `ContentList.vue` |

### Wave 2 — New Tools & Orchestration (5 agents paralel)

| Agent | Scope | File |
|---|---|---|
| **F** | Charts blueprint | `backend/charts_bp.py` (NEW), `backend/app.py` (register only) |
| **G** | 3 new chat tools | `backend/chat_tools.py`, `backend/mode_prompts.py` |
| **H** | Prompt cleanup + slr noise | `backend/prompt/prompt.txt`, `prompt_section_only.txt`, `slr_worker.py` |
| **I** | Frontend chip kinds + post-generate | `chat.js`, `paperJobs.js`, `ChatMessage.vue`, `ChartPreviewCard.vue` (NEW), `FileReviewCard.vue` (NEW) |
| **J** | Tests | `tests/test_charts_bp.py`, `test_paragraph_context.py`, `test_review_large_file.py` (semua NEW) |

---

## 3. Perubahan Kunci per Topik

### 3.1 Banner 524 di Literatur — Fixed

Root cause: Postgres lock starvation + missing `sentence_transformers` + Cloudflare 100s timeout di poll endpoint. Fix:

- **PG session safeguards** di `app.py`: `statement_timeout=30s`, `idle_in_transaction_session_timeout=5min`, `lock_timeout=5s` (psycopg-only via SQLAlchemy `connect` event).
- **`slr_bp.list_slr_jobs`**: `defer(SlrJob.result)` untuk hemat bytes per poll, handler `OperationalError → 503 DB_BUSY`.
- **Endpoint baru `GET /api/papers/<id>/slr/jobs/wait?after=<ts>`**: long-poll 30s di bawah Cloudflare 100s threshold.
- **`scoring.py` TF-IDF fallback**: kalau `sentence_transformers` tidak terinstall, otomatis pakai `TfidfVectorizer(max_features=384)` dengan L2 normalization. Pipeline tetap jalan tanpa SBERT.
- **`slr_worker._run_job`**: DELETE+INSERT LiteratureItem dalam `db.session.begin_nested()` SAVEPOINT — kalau INSERT gagal, baris lama tidak hilang.
- **`LiteratureTab.vue`**: visibility-aware polling (5s hidden / 2.5s active / 30s idle), 3-strikes transient retry sebelum tampilkan banner, `startSLRFromPaperTopic` sekarang langsung call `runSLR()`.

**Manual cleanup yang masih perlu user lakukan** (di luar scope kode):
```sql
-- bunuh transaksi DROP TABLE yang nyangkut + idle-in-transaction > 5 menit
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname='papergenerator'
  AND (query ILIKE 'DROP TABLE literature_items%'
       OR (state='idle in transaction' AND xact_start < now() - interval '5 minutes'));

UPDATE slr_jobs SET status='error', error='Cleared after lock-storm', finished_at=now()
WHERE status='running' AND started_at < now() - interval '30 minutes';
```

### 3.2 OpenAI Removal — Done

- `backend/app.py`: hapus `from openai import OpenAI`, `OPENAI_MODEL`, `openai_client`, `get_openai_client()`. Ganti dengan `AIOTOMASI_MODEL = os.getenv("AIOTOMASI_MODEL", "VIOLAGPT")`.
- `/api/generate` endpoint port ke `_call_aiotomasi_with_fallback` (response shape preserved + tambah field `text` alias).
- `requirements.txt`: hapus `openai==1.68.0`.
- `archive/` dihapus (4.4 MB), `generate_docx_from_json.py` (24 KB) dihapus, `prompt/prompt.txt` root (52.5 KB) dihapus.

Verifikasi: `grep -rn "openai\|OPENAI" backend/ --include="*.py"` → cuma match `openaire` (OpenAIRE search service, bukan OpenAI).

### 3.3 Pipeline Integration — Bug Krusial Difix

**Bug:** `db` tidak di-import di `generate_paper_chunked.py` walaupun dipakai di `_load_full_context` line 213, 236, 274, 610. Setiap call → `NameError` ditelan `except Exception` → return string kosong → chat history & literatur tidak masuk ke prompt.

**Fix:** `from models import db, ChatMessage, LiteratureItem, PaperFile` di `_load_full_context`.

**Tambahan:**
- `_load_full_context` terima param baru `custom_prompt`. Kalau mengandung marker `[REFERENCE DOCUMENTS]`, skip injeksi file (hindari double-inject dengan path `app._run_generate_full_job:629`).
- `chat_tools._generate_full_paper`: `effective_style = style kwarg > ProjectMemory.citation_style > None` → `prompt/style/<X>.txt` benar-benar ke-load oleh chunked pipeline.
- Pre-flight validasi: `n_lit < 20 and n_must == 0` → return PROPOSAL_PREFIX `kind=validation_error error_code=NEED_MORE_LITERATURE`.
- Hapus dead helpers `_load_section_prompt()` & `_load_humanize_prose()`.

### 3.4 Discovery Q&A Chips — Added

`mode_prompts.py:DISCOVERY_PROMPT` tambah 3 langkah baru di akhir Q&A:

- **CITATION STYLE** [key=`citation_style`] — ProposeChips 7 chips: ACS, APA, Chicago, Harvard, IEEE, MLA, Vancouver → SetCitationStyle.
- **BAHASA** [key=`paper_language`] — ProposeChips 2 chips: Bahasa Indonesia (id), English (en) → SetLanguage.
- **USE REVIEW DATA** [key=`use_review_data`] — ProposeChips 2 chips: yes/no.

`MODE_TOOLS["discovery"]` tambah: `SetCitationStyle`, `SetLanguage`, `GetParagraphContext`, `ReviewLargeFile`.

### 3.5 3 Tools Chat Agent Baru

| Tool | Output | Use case |
|---|---|---|
| `GenerateChart(kind, title, data, ...)` | PROPOSAL_PREFIX `kind=chart_proposal` + image_id, url, spec | Section 4 (Results) matplotlib chart |
| `GetParagraphContext(section_index, content_index)` | JSON section_meta + target + neighbors + citations + fig_refs + constraints (~80% lebih hemat token vs `GetPaperSection`) | Sebelum Paraphrase/FixGrammar/Translate |
| `ReviewLargeFile(file_id)` | >3000 kata: PROPOSAL_PREFIX `kind=file_review` + head/tail + suggested_kinds. ≤3000: fallback ke `_read_attached_file` | File attachment terlalu panjang |

Total tools sekarang: **33** (dari 30 di handoff sebelumnya).
`MODE_TOOLS["revisi"]` sekarang **13 tools** (dari 10).

### 3.6 Image Generator — Hooks + Bug Fix

- `paper.js:addContent('gambar')` & `uploadImage()`: lazy-import `chat.js` lalu `injectAssistantMessage` tanya "itu gambar apa keterangannya?" — supaya AI bisa generate prompt format `(create image"...")`.
- `chat.js`: method baru `injectAssistantMessage(content)` — push synthetic message tanpa hit backend.
- `paperJobs.js`: post-done hook `_onJobDone(job)` collect figure prompts dari paper data, inject chat dengan list "Fig. N — title — prompt" untuk review.
- `ContentList.vue`: defensive `?.` guard di template & `badgeLabel`.
- Frontend rebuild → bundle hash baru (`PaperEditorPage-CdrxZ_LN.js` etc) → bundle stale `c5vwf3Ow` hilang. Bug `TypeError: getItemNumber is not a function` resolved.

### 3.7 Prompt Cleanup

`prompt.txt:33` ganti default IEEE `[1], [2]` → author-year style + larangan eksplisit ketik bracket di prose. `prompt_section_only.txt:53` sama. Reference list akan di-auto-number post-generation.

### 3.8 Charts Blueprint

`backend/charts_bp.py` (BARU, 122 baris):
- `POST /api/papers/<paper_id>/charts` (JWT-protected, paper-ownership check).
- Validasi `kind ∈ {line, bar, scatter, hist, box, heatmap, pie}`, `title`/`data` required.
- Pindahkan PNG dari `backend/charts/` → `backend/uploads/<paper_id>/` via `shutil.move`, register `PaperImage`, return `{image_id, filename, url}` 201.
- Error codes: `BAD_REQUEST`, `BAD_KIND`, `BAD_SPEC`, `GENERATE_ERROR`, `SAVE_ERROR`.

### 3.9 Frontend Chip Kinds

`ChatMessage.vue` render 4 kind baru:
- `chart_proposal` → `<ChartPreviewCard>` (file BARU): preview image + accept/regenerate buttons.
- `file_review` → `<FileReviewCard>` (file BARU): word_count + head/tail preview + chip pilih kinds.
- `validation_error` → banner amber + tombol "Jalankan SLR" (kalau code `NEED_MORE_LITERATURE`) atau "Coba lagi".
- `image_prompt_review` → list "Fig. N — title — prompt" dengan checkbox.

---

## 4. Test Coverage

```
backend/tests/test_auto_memory.py             38/38 PASS
backend/tests/test_mode_prompts.py            22/22 PASS
backend/tests/test_generate_paper_chunked.py   6/6  PASS
backend/tests/test_chart_generator.py         18/18 PASS
backend/tests/test_charts_bp.py               12/12 PASS  ← BARU (Wave 2)
backend/tests/test_paragraph_context.py       13/13 PASS  ← BARU (Wave 2)
backend/tests/test_review_large_file.py        8/8  PASS  ← BARU (Wave 2)
─────────────────────────────────────────────────────────
                                              117/117 PASS (3.69s)
```

Frontend: `npm run build` PASS (5.05s, 149 modules, 0 errors).

Run command:
```bash
cd /home/sirobo/papergenerator/backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_auto_memory.py tests/test_mode_prompts.py tests/test_generate_paper_chunked.py \
  tests/test_chart_generator.py tests/test_charts_bp.py tests/test_paragraph_context.py \
  tests/test_review_large_file.py -v
```

---

## 5. Issues Ditemukan di Code Review (Belum Difix)

Saat local code review pasca-eksekusi, ditemukan 7 isu yang **TIDAK** difix di sesi ini. Sesi berikutnya wajib handle:

### 5.1 [HIGH] `chat_tools._generate_chart_tool` — nested `app_context()`
Lokasi: `backend/chat_tools.py` di dalam `_generate_chart_tool`.
```python
from app import app          # circular import risk
with app.app_context():       # tool sudah dipanggil dari request context
    ...
```
**Fix:** Hapus blok `with app.app_context()` dan import. Tool sudah dijamin punya context dari chat blueprint.

### 5.2 [HIGH] `paperJobs._onJobDone` — tidak ada dedup per `job.id`
Lokasi: `frontend/src/stores/paperJobs.js`.
Setiap `fetchRecentDone()` (10s polling) akan re-inject chat message untuk semua done jobs. Chat akan banjir duplikat.
**Fix:**
```js
const _processedJobIds = new Set()
function _onJobDone(job) {
  if (!job?.id || _processedJobIds.has(job.id)) return
  _processedJobIds.add(job.id)
  // existing logic
}
```

### 5.3 [LOW] `app.py:_set_pg_session_defaults` — `commit()` tidak perlu
`SET` Postgres adalah session-level, tidak butuh commit. Lebih bersih dihapus. Logger di dalam function juga harusnya pakai module-level `logger`.

### 5.4 [MEDIUM] `slr_bp.wait_slr_jobs` — `commit()` antara probe
Untuk read-only query, lebih idiomatic pakai `db.session.rollback()` atau `expire_all()` daripada `commit()`. Saat ini tidak break tapi tidak best practice.

### 5.5 [MEDIUM] Vite circular import warning
```
chat.js is dynamically imported by paper.js but also statically imported by 
ChatTab.vue, paperJobs.js, PaperEditorPage.vue
```
`paperJobs.js` baru tambah static import `chat.js`. Defeat code-splitting. Pilih satu pola: dynamic import di paperJobs.js juga, atau static import di paper.js.

### 5.6 [MEDIUM] ChatTab.vue tidak mendengar event chart/file-review
Verifikasi di working tree: ChatTab.vue cuma punya `@chip-select="onChipSelect"`. Event `chart-accept`, `chart-regenerate`, `file-review-pick` dari ChatMessage.vue **tidak di-wire** ke handler. UI render tapi click button no-op.
**Fix:** Tambah handler di ChatTab.vue:
```vue
@chart-accept="onChartAccept"
@chart-regenerate="onChartRegenerate"
@file-review-pick="onFileReviewPick"
```
Plus implement 3 handler functions yang panggil `chatStore.sendMessage(...)` dengan instruksi spesifik.

### 5.7 [LOW] Marker `[REFERENCE DOCUMENTS]` verifikasi
`generate_paper_chunked.py` cek `if "[REFERENCE DOCUMENTS]" in custom_prompt` untuk skip file inject. `app.py:629` tulis `"[REFERENCE DOCUMENTS]\n{combined}"` — sudah verified match. Aman.

---

## 6. Yang Out-of-Scope (Tidak Dikerjakan Sesi Ini)

Item dari `perintah.txt` yang BELUM diimplement:

- **Generate grafik post-paper otomatis** di Section 4 — sekarang `GenerateChart` tool ada, tapi tidak ada flow "setelah paper jadi auto-generate chart matplotlib dari data user". Frontend perlu tanya user model grafik via chips.
- **`ReviewPaper` tool** untuk review menyeluruh (5 layer: structural, logical, numerical, style, language) — belum dibuat.
- **`ReviseData` tool** dedicated untuk Section 4 dengan tabel + chart spec — sekarang user pakai `ProposeSection` + `GenerateChart` manual.
- **Citation validator [L1]..[Ln]** — orphan citation detection belum implement.
- **Edit-after-generate version history** — RevisiProposalCard cuma diff sederhana.
- **Browser notif permission auto-prompt** saat first generate click.
- **Toast cross-paper integration** — paperJobs done event belum wire ke paperStore toast.
- **`backend/python/router_api.py`** — kemungkinan dead, butuh konfirmasi user.

---

## 7. Migration & Deploy Steps

```bash
# 1. Manual SQL cleanup di Postgres production (jika lock-storm masih ada)
psql -d papergenerator <<'EOF'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname='papergenerator'
  AND query ILIKE 'DROP TABLE literature_items%';

SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname='papergenerator'
  AND state='idle in transaction'
  AND xact_start < now() - interval '5 minutes';

UPDATE slr_jobs SET status='error', error='Cleared after lock-storm', finished_at=now()
WHERE status='running' AND started_at < now() - interval '30 minutes';
EOF

# 2. (Optional) Install sentence-transformers untuk SBERT scoring
# Kalau tidak, TF-IDF fallback otomatis jalan
# pip install sentence-transformers==3.0.1 torch==2.4.0

# 3. Backend restart (PG safeguards & charts blueprint baru)
bash server.sh restart    # or pm2 restart paper-backend

# 4. Frontend deploy + cache purge
cd frontend && npm run build
# Purge Cloudflare cache untuk paperfull.app supaya bundle hash baru ke-load
```

---

## 8. Quick Reference

### Tools registered (33 total)
```
Bash, ClassifyFile, DeleteMemory, FixGrammar, GenerateChart (NEW),
GenerateFullPaper, GetLiterature, GetPaperContent, GetPaperNumbering,
GetPaperSection, GetParagraphContext (NEW), ListAttachedFiles, ListMemory,
Paraphrase, ProposeAbstract, ProposeChips, ProposeJournal, ProposeKeywords,
ProposeReference, ProposeSection, ProposeTitle, Read, ReadAttachedFile,
RequestExportDocx, ReviewLargeFile (NEW), RouteIntent, RunSLR, SearchPapers,
SetCitationStyle, SetLanguage, Translate, WebFetch, WebSearch
```

### Modes
```
tier0       prompt=158B  tools=1
discovery   prompt=1939B tools=11   ← +2 chips, +2 tools
slr         prompt=644B  tools=5
edit        prompt=1119B tools=11   ← +2 tools
rapikan     prompt=612B  tools=4
revisi      prompt=1574B tools=13   ← +3 tools
memory      prompt=287B  tools=2
casual      prompt=158B  tools=0
```

### Routes baru
```
POST /api/papers/<paper_id>/charts            ← Wave 2 (charts_bp)
GET  /api/papers/<paper_id>/slr/jobs/wait     ← Wave 1 (long-poll, 524 fix)
```

### Environment yang dipakai
```
AIOTOMASI_API           # endpoint upstream chat completion
AIOTOMASI_APIKEY        # API key
AIOTOMASI_MODEL         # default VIOLAGPT
SLR_MAX_WORKERS=10
IEEE_API_KEY            # optional
SINTA_OFFLINE_DIR=/home/sirobo/sinta-scraping
# OPENAI_API_KEY, OPENAI_MODEL  ← TIDAK PERLU LAGI
```

### Verifikasi cepat sesi berikutnya
```bash
# Backend imports + routes
cd backend && python3 -c "
import app
from chat_tools import CHAT_TOOLS
print('tools:', len(CHAT_TOOLS))
for r in app.app.url_map.iter_rules():
    if 'charts' in str(r) or 'slr/jobs/wait' in str(r):
        print(' -', r)
"

# Tests
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_auto_memory.py tests/test_mode_prompts.py \
  tests/test_generate_paper_chunked.py tests/test_chart_generator.py \
  tests/test_charts_bp.py tests/test_paragraph_context.py \
  tests/test_review_large_file.py -v

# Frontend build
cd frontend && rm -rf node_modules/.vite dist && npm run build
```

---

## 9. Definition of Done (Sesi Ini)

- [x] Banner 524 root cause diagnosed + difix (PG safeguards + long-poll + defer + 3-strikes retry)
- [x] OpenAI removal lengkap (app.py + requirements.txt + archive/ + generate_docx_from_json.py)
- [x] `db` import bug di generate_paper_chunked.py difix (chat history + literatur + files akhirnya benar2 ter-inject)
- [x] Style sitasi flow: chips di discovery → SetCitationStyle → memory → effective_style → load `prompt/style/<X>.txt`
- [x] 20 SLR validation pre-flight `kind=validation_error` di `_generate_full_paper`
- [x] 3 tools baru: GenerateChart, GetParagraphContext, ReviewLargeFile
- [x] `charts_bp.py` blueprint + register
- [x] Frontend rebuild → `getItemNumber` TypeError hilang
- [x] Image add/upload trigger chat-ask "itu gambar apa"
- [x] Post-generate paperJobs hook → review prompt image
- [x] 33 tests baru (12+13+8) PASS, total 117/117
- [x] Frontend build clean

Pending (sesi berikutnya):
- [ ] **Fix 7 issues code review di section 5** (terutama 5.1, 5.2, 5.6 yang HIGH/MEDIUM)
- [ ] Manual SQL cleanup di production Postgres
- [ ] Push ke origin/v1 + buat PR
- [ ] E2E test di paperfull.app live
- [ ] Implement out-of-scope items (section 6) prioritas: ReviewPaper tool + auto-chart-after-generate
- [ ] Verify ChatTab.vue handler wire-up untuk event chart/file-review

---

## 10. File Change Summary

### Modified (50 backend + frontend files)
Highlights:
- `backend/app.py` (+41/-23) — OpenAI removal + PG safeguards + charts_bp register
- `backend/chat_tools.py` (+282/-3) — 3 tools baru + validation 20 SLR + style fix
- `backend/slr_bp.py` (+83/-6) — defer + 503 DB_BUSY + long-poll endpoint
- `backend/slr_worker.py` (+97/-74) — atomic SAVEPOINT + sweep noise
- `backend/SLR/scoring.py` (+42/-3) — TF-IDF fallback
- `backend/generate_paper_chunked.py` (+16/-38) — db import fix + dead helper purge
- `backend/mode_prompts.py` (+21/-6) — discovery chips + MODE_TOOLS
- `frontend/src/stores/chat.js` (+75) — injectAssistantMessage + 4 chip kinds parser
- `frontend/src/stores/paperJobs.js` (+59) — post-done hook (⚠ butuh dedup)
- `frontend/src/stores/paper.js` (+26/-1) — addContent/uploadImage chat hook
- `frontend/src/components/ChatMessage.vue` (+141/-1) — 4 kind renderer
- `frontend/src/components/LiteratureTab.vue` (+41/-9) — visibility-aware poll + 3-strikes
- `frontend/src/components/ContentList.vue` (+2/-2) — defensive guard

### New
- `backend/charts_bp.py` (122 lines)
- `backend/tests/test_charts_bp.py` (12 tests)
- `backend/tests/test_paragraph_context.py` (13 tests)
- `backend/tests/test_review_large_file.py` (8 tests)
- `frontend/src/components/ChartPreviewCard.vue`
- `frontend/src/components/FileReviewCard.vue`

### Deleted
- `backend/archive/` (4.4 MB, OpenAI legacy)
- `backend/generate_docx_from_json.py` (24 KB, dead — pakai `template/<JOURNAL>gen.py`)
- `prompt/prompt.txt` (root, 52.5 KB, dead — backend pakai `backend/prompt/prompt.txt`)

---

**End of handoff.** Semua perubahan **belum di-commit**. Sebelum commit, fix issue 5.1, 5.2, 5.6 dulu (HIGH priority).
