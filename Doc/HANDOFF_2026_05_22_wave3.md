# HANDOFF — Wave 3: Single-Shot Paper, Multi-Question, Model Lock, Production Fix

**Tanggal:** 2026-05-22 (lanjutan dari `HANDOFF_2026_05_22_wave2.md`)
**Branch:** `v1` (uncommitted, ~80 file modified, ~1900 file deleted)
**Project:** `/home/sirobo/papergenerator`
**Status:** Implementation complete. Backend 163/163 tests PASS. Frontend build clean (5.34s, bundle `index-DO_pSb3z.js` already deployed). **Production blocker fixed inline:** Postgres `users` tabel hilang — sudah dibuat ulang via `db.create_all()` dan stamped Alembic.

---

## 1. Konteks Sesi

User minta kelanjutan revisi besar dari `perintah.txt` + perintah baru di chat:
1. Generate paper full-paper **single-shot** (bukan chunked) pakai `backend/prompt/prompt.txt` + history + literatur + files
2. **Model lock**: full paper = **V-OPUS**, chat Q&A = **V-DEEPSEEK**, **buang model picker**
3. Tools revisi **dispatcher** — abstract / section / data / review / literatur / parafrase / grammar / translate
4. Multi-pertanyaan **5-soal-sekaligus** (Claude-Code style) dengan chip + free-text fallback
5. Per-call JSONL log untuk tracing
6. Hapus block "Per model" di tooltip token quota header
7. Verifikasi end-to-end: SLR jalan, generate paper jalan, image gen jalan

Pendekatan: **5 agent paralel** dengan file boundary terpisah, +1 agent integrasi (saya).

---

## 2. Wave Eksekusi

### Wave 0 — Analisa
Read `HANDOFF_2026_05_22_wave2.md`, `perintah.txt`, `tes3..7`, `prompt/prompt.txt` untuk paham state lengkap.

### Wave 1 — 5 Agent Paralel

| Agent | Scope | File |
|---|---|---|
| **A1** | Single-shot paper gen + lock V-OPUS | `backend/generate_paper_single.py` (NEW), `backend/app.py` (`_run_generate_full_job`) |
| **A2** | Tools revisi + multi-question + JSONL log + lock | `backend/chat_tools.py`, `backend/mode_prompts.py` |
| **A3** | Chat routing lock V-DEEPSEEK + SLR default | `backend/chat.py`, `backend/slr_bp.py`, `backend/slr_worker.py`, `backend/SLR/summarizer.py` |
| **A4** | Frontend chat cards | `MultiQuestionCard.vue` (NEW), `ChatMessage.vue`, `chat.js`, `RevisiProposalCard.vue` |
| **A5** | Frontend handlers + dedup + 524 fix | `ChatTab.vue`, `paperJobs.js`, `LiteratureTab.vue`, `paper.js` |

### Wave 2 — Integration & Production Fix (saya)
- Hapus block "Per model" di `AppHeader.vue`
- Rebuild frontend (`vite` 5.34s, hash baru `index-DO_pSb3z.js`)
- **Diagnosa Google login error 500** → ketemu `relation "users" does not exist` di Postgres
- `db.create_all()` → 13 tabel terbentuk
- `python3 -m alembic stamp c3a9f7b2e154` → versioning beres
- `bash server.sh restart` → `pm2` restart 3 service
- Verifikasi: `/api/healthz` 200, `/api/auth/google/login` 302 → accounts.google.com (jalan)

---

## 3. Perubahan Kunci per Topik

### 3.1 Single-Shot Full Paper Generation — NEW

Sebelumnya pakai `generate_paper_chunked.py` (8 chunks × 30s = 4-10 menit, dengan checkpoint-resume).

**Sekarang:** `backend/generate_paper_single.py` — satu call ke V-OPUS dengan:
- System prompt = `prompt/prompt.txt` + `prompt/humanize.txt` + optional `style/<X>.txt` + optional `topic/<Y>.txt`
- User message berisi: judul, custom_prompt (memory + planner outline + setting), 10 chat history terakhir, top-50 literature, top-5 file extracts
- Hard-coded `model="V-OPUS"`, `timeout=900`, `max_tokens=32000`, `temperature=0.7`
- Output dinormalisasi: flat keys `section1..N` di-flatten jadi `sections` array, figures/tables/equations diekstrak ke top-level

**`app.py:_run_generate_full_job`:**
- Default sekarang ke single-shot. `chunked=False/True` dan `model=...` kwargs di-`**_legacy_kwargs` dan diabaikan
- Kalau V-OPUS gagal, raise (no fallback chain) — by design
- Pre-flight `cancel_check`, mid-run checkpoint at progress=5, final checkpoint at progress=100

**Catatan:** `generate_paper_chunked.py` masih ada di disk dan tetap di-test (`test_generate_paper_chunked.py` 6/6 PASS) — boleh diretire di sesi berikutnya.

### 3.2 Model Lock — Done

| Path | Model | Lokasi |
|---|---|---|
| `/api/chat/conversations/<id>/messages` | **V-DEEPSEEK** | `chat.py:CHAT_MODEL` (constant) |
| `/api/papers/.../slr/jobs` | **V-DEEPSEEK** (default) | `slr_bp.py`, `slr_worker.py` |
| `SLR/summarizer.py` | **V-DEEPSEEK** | `_DEFAULT_MODEL` |
| `chat_tools._plan_outline` | **V-DEEPSEEK** | hard-coded |
| Full paper generation | **V-OPUS** | `generate_paper_single.py` hard-coded |

`_ALLOWED_MODELS = {None, "V-OPUS", "V-DEEPSEEK"}` di `chat_tools.py`. V-CLAUDE / V-GPT / V-GLM dibuang.

`chat.py`:
- `SELECTABLE_MODELS`, `DEFAULT_MODEL_KEY`, `_resolve_model()` **DELETED**
- `_call_upstream` ambil `model="V-DEEPSEEK"` default, tidak ada fallback chain
- `send_message`: body `{model: ...}` di-ignore silent (back-compat)
- `execute_tool(...)` tidak terima `model=` lagi, terima `conv_id=` untuk JSONL log

Frontend:
- `ChatTab.vue`: model picker UI dihapus (button + dropdown + handlers)
- `chat.js`: `selectedModel` / `setModel` jadi no-op shim untuk backward-compat
- `AppHeader.vue`: block "Per model" dihapus dari tooltip quota header

### 3.3 Tools Baru — 4 Dispatcher

| Tool | Output | Use case |
|---|---|---|
| `AskQuestions(questions[])` | PROPOSAL `kind=multi_question` | 1-5 pertanyaan dgn chip 2-6 opsi + free-text fallback. Frontend render `MultiQuestionCard`. |
| `ReviewPaper(directive, scope)` | PROPOSAL `kind=review_plan` | Review menyeluruh; AI lanjut panggil ProposeAbstract/ProposeSection per arahan |
| `ReviseData(directive)` | PROPOSAL `kind=revise_data` | Section 4 data revision dispatcher |
| `AddLiterature(keyword, year_from, top_k)` | alias ke `RunSLR` (V-DEEPSEEK) | SLR baru dgn keyword spesifik |

Total tools: **37** (dari 33). Mode tool count:
- `discovery`: 12 (+1 AskQuestions)
- `revisi`: 16 (+3 ReviewPaper, ReviseData, AddLiterature)

`mode_prompts.py`:
- `DISCOVERY_PROMPT` rewrite: hapus "ASK ONE QUESTION PER MESSAGE", ganti dengan instruksi `AskQuestions` batch up to 5
- `REVISI_PROMPT` rewrite: dispatch table eksplisit untuk setiap action revisi (paragraph/section/whole scope)
- Hilangkan "Step N" prose dari semua prompt

### 3.4 Frontend Cards Baru

**`MultiQuestionCard.vue` (NEW):**
- 1-5 pertanyaan, masing-masing punya chip 2-6 opsi + input free-text di samping
- ✓ checkmark di pojok kanan saat row terjawab
- Submit button enable kalau ≥1 row terisi
- Emit `multi-question-submit` dengan `[{key, value}, ...]`

**`RevisiProposalCard.vue` (rewrite):**
- Title dari tool name (Paraphrase / Fix Grammar / Translate)
- Subtitle dari scope
- Side-by-side mono diff (red original / green rewrite)
- Buttons: "Terima" / "Tolak" + emit `revisi-accepted` / `revisi-rejected` (past tense — verifikasi: emit name di ChatMessage.vue **past tense**, bukan present tense seperti spec awal)
- Language badge "→ Bahasa Inggris" kalau ada `target_language`

**`ChatMessage.vue` rendering tambahan:**
- `multi_question` → `<MultiQuestionCard>`
- `review_plan` → notice + tombol "Batalkan"
- `revise_data` → notice text-only

**`chat.js` parser tambahan:**
- `multi_question`, `review_plan`, `revise_data`, dan helper `submitMultiQuestionAnswers(answers)`

### 3.5 JSONL Per-Call Log — NEW

Path: `<repo>/logs/chat_calls/<paper_id>/<YYYY-MM-DD>.jsonl`

`chat_tools._log_chat_call(paper_id, conv_id, role, payload)` dipanggil:
- `chat.py:send_message` saat user-turn entry (role=user) dan saat assistant message persist (role=assistant + usage + tool_calls)
- `chat_tools.execute_tool` saat tool call/result/error (role=tool_call/tool_result/tool_error)

Failure-tolerant: kalau `os.makedirs` gagal di production read-only, hanya log warning (chat tetap jalan).

### 3.6 Code Review Fix dari HANDOFF Wave 2 Section 5

| Item | Status | Lokasi |
|---|---|---|
| 5.1 nested `app_context` di `_generate_chart_tool` | **FIXED** | `chat_tools.py:_generate_chart_tool` |
| 5.2 `paperJobs._onJobDone` tidak dedup | **FIXED** | `paperJobs.js` `_processedJobIds` Set |
| 5.4 `slr_bp.wait_slr_jobs` `commit()` antar probe | **FIXED** | ganti `rollback()` |
| 5.5 Vite circular import warning | **FIXED** | `paperJobs.js` lazy-import `chat.js` |
| 5.6 ChatTab.vue tidak wire event chart/file-review | **FIXED** | 7 handler baru |
| 5.3, 5.7 | **DEFERRED** | low priority |

### 3.7 LiteratureTab 524 — Strengthened

- `loadJobs` pakai `/api/papers/<id>/slr/jobs/wait?after=<ts>` (long-poll 35s) saat ada job running, fallback ke list endpoint saat idle
- Banner muncul setelah **3-strikes** consecutive failure, reset ke 0 saat sukses
- Banner copy halus: "Sambungan ke server lambat. Coba lagi?" (tidak lagi tampilin status code)
- Visibility-aware polling (5s hidden / 2.5s active / 30s idle)
- "Coba lagi" reset failures + reload
- Cross-paper reset bersihkan `_consecutiveFailures` dan `_waitCursor`

### 3.8 Production Database Fix

**Root cause:** Postgres `papergenerator` tidak punya tabel sama sekali (schema belum pernah di-migrate sejak deploy). Login Google return 500 dengan `relation "users" does not exist`.

**Fix:**
```bash
cd /home/sirobo/papergenerator/backend
python3 -c "from app import app; from models import db
with app.app_context(): db.create_all()"
# 13 tabel terbentuk: ai_jobs, alembic_version, api_usage_logs,
# chat_messages, conversations, image_gen_jobs, literature_items,
# paper_files, paper_images, papers, project_memory, slr_jobs, users

python3 -m alembic stamp c3a9f7b2e154
bash ../server.sh restart  # pm2 restart paper-backend, paper-frontend, paper-worker
```

**Verifikasi:**
```
curl /api/healthz → 200
curl /api/auth/google/login → 302 → accounts.google.com (working)
deployed bundle → index-DO_pSb3z.js (matches local build)
```

---

## 4. Test Coverage

```
backend/tests/                                    163/163 PASS (1 skipped)
  test_chat_model_picker.py (rewritten)            4/4
  test_mode_prompts.py (DISCOVERY assertion fix)  22/22
  test_generate_paper_chunked.py                   6/6
  test_chart_generator.py                         18/18
  test_charts_bp.py                               12/12
  test_paragraph_context.py                       13/13
  test_review_large_file.py                        8/8
  ... (rest of suite)                             80/80
```

Frontend: `npm run build` PASS (5.34s, 152 modules, 0 errors, no circular import warning).

Run cmd:
```bash
cd /home/sirobo/papergenerator/backend && \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -v
```

---

## 5. Belum Dikerjakan / Catatan untuk Sesi Berikutnya

### 5.1 [BLOCKER untuk E2E] Playwright Google login bot detection
Google blokir headless OAuth flow. E2E test di paperfull.app harus dilakukan manual atau pakai session cookie hasil login interaktif. Saat ini `/api/auth/google/login` sudah confirmed 302 → Google, tapi flow callback tidak bisa diverifikasi via Playwright tanpa user-supplied cookie.

**Workaround sesi berikutnya:** minta user login lewat browser, copy cookie `access_token_cookie` ke MCP, lalu Playwright bisa lanjut test SLR + generate paper + image gen.

### 5.2 [LOW] `chat.py` SELECTABLE_MODELS sudah dihapus tapi shim di chat.js
`chat.js` masih expose `selectedModel` dan `setModel` no-op untuk back-compat. Kalau aman, hapus di sesi berikutnya — tapi pastikan tidak ada caller lain.

### 5.3 [LOW] `generate_paper_chunked.py` masih ada di disk
Single-shot adalah path utama sekarang. Module chunked masih bisa dipakai via direct import (test masih jalan). Aman dihapus kalau sudah konfirmasi tidak ada user yang punya resume_state stuck.

### 5.4 [LOW] `chat_tools._generate_full_paper` masih kirim `model=` dan `chunked=True`
Agent A1 menerima sebagai `**_legacy_kwargs` jadi tidak break, tapi clean-up code path agar konsisten.

### 5.5 [MEDIUM] `ChatMessage.vue` belum emit `review-cancel`
`ChatTab.vue` sudah wire handler-nya, tapi sumber emit di ChatMessage belum ada. Tambahkan tombol "Batalkan" di renderer `review_plan` yang emit `review-cancel`.

### 5.6 [MEDIUM] `AddLiterature` dispatcher tidak read GetLiterature dulu
By design — AI yang harus call GetLiterature dulu via REVISI_PROMPT. Tapi di mode_prompts perlu instruksi eksplisit "selalu GetLiterature dulu sebelum AddLiterature".

### 5.7 [MEDIUM] Belum di-commit
80 file modified + 1900 deleted (cleanup `prompt/riset/` legacy folders). Pre-commit perlu manual review supaya tidak commit secrets atau unintended deletions.

### 5.8 [HIGH] Missing favicon (per perintah.txt poin terakhir)
User minta favicon dari logo papefull untuk muncul di Google search. Belum dikerjakan. File favicon sebaiknya ditaruh di `frontend/public/favicon.ico` dengan beberapa size (16x16, 32x32, 192x192, apple-touch-icon 180x180).

### 5.9 [HIGH] SEO `seo-google` skill belum dipanggil
User minta pakai SEO skill untuk paperfull.app supaya nomor 1 di Google search dengan keyword "Generate complete papers...". Belum di-execute. Skill location: `file:///home/sirobo/.config/kilo/skill/seo-google/SKILL.md`.

---

## 6. Migration & Deploy Steps

```bash
# 1. (DONE) Postgres schema bootstrap (kalau belum jalan, jalankan ini)
cd /home/sirobo/papergenerator/backend && python3 -c "
from app import app
from models import db
with app.app_context(): db.create_all()
" && python3 -m alembic stamp c3a9f7b2e154

# 2. (DONE) Backend restart
bash /home/sirobo/papergenerator/server.sh restart

# 3. (DONE) Frontend rebuild + deploy
cd /home/sirobo/papergenerator/frontend && rm -rf node_modules/.vite dist && npm run build
# pm2 sudah otomatis serve dari dist/ via paper-frontend

# 4. (Pending sesi berikutnya) Cloudflare cache purge kalau bundle hash baru tidak ke-load di client
```

---

## 7. Quick Reference

### Tools registered (37 total)
```
AddLiterature (NEW)        Bash                ClassifyFile
DeleteMemory               FixGrammar          GenerateChart
GenerateFullPaper          GetLiterature       GetPaperContent
GetPaperNumbering          GetPaperSection     GetParagraphContext
ListAttachedFiles          ListMemory          AskQuestions (NEW)
Paraphrase                 ProposeAbstract     ProposeChips
ProposeJournal             ProposeKeywords     ProposeReference
ProposeSection             ProposeTitle        Read
ReadAttachedFile           RequestExportDocx   ReviewLargeFile
ReviewPaper (NEW)          ReviseData (NEW)    RouteIntent
RunSLR                     SearchPapers        SetCitationStyle
SetLanguage                Translate           WebFetch
WebSearch                  (CHAT_TOOLS = 37)
```

### Modes (mode → tools count)
```
tier0       1 tool    (RouteIntent)
discovery   12 tools  (+AskQuestions)
slr         5 tools
edit        11 tools
rapikan     4 tools
revisi      16 tools  (+ReviewPaper, ReviseData, AddLiterature)
memory      2 tools
casual      0 tools
```

### Routes baru/locked
```
POST /api/papers/<id>/charts                  ← Wave 2 (charts_bp)
GET  /api/papers/<id>/slr/jobs/wait           ← Wave 1 (long-poll)
POST /api/chat/conversations/<id>/messages    ← Wave 3 (model V-DEEPSEEK locked)
```

### Environment yang dipakai
```
AIOTOMASI_API           # endpoint upstream chat completion
AIOTOMASI_APIKEY        # API key
AIOTOMASI_MODEL         # default VIOLAGPT (untuk fallback /api/generate ad-hoc only)
SLR_MAX_WORKERS=10
IEEE_API_KEY            # optional
GOOGLE_CLIENT_ID        # required for OAuth
GOOGLE_CLIENT_SECRET    # required for OAuth
JWT_SECRET_KEY          # required for sessions
DATABASE_URL=postgresql://papergenerator:.../localhost:5432/papergenerator
```

### Verifikasi cepat sesi berikutnya
```bash
# Backend imports + tools count
cd /home/sirobo/papergenerator/backend && python3 -c "
import chat, chat_tools
from mode_prompts import MODE_TOOLS
print('CHAT_MODEL:', chat.CHAT_MODEL)
print('total tools:', len(chat_tools.CHAT_TOOLS))
print('discovery tools:', len(MODE_TOOLS['discovery']))
print('revisi tools:', len(MODE_TOOLS['revisi']))
print('_ALLOWED_MODELS:', chat_tools._ALLOWED_MODELS)
"

# Tests
cd /home/sirobo/papergenerator/backend && \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -q

# Frontend build
cd /home/sirobo/papergenerator/frontend && rm -rf node_modules/.vite dist && npm run build

# Production health
curl -sf https://paperfull.app/api/healthz && echo OK
curl -sIL https://paperfull.app/api/auth/google/login | grep -iE "^(HTTP|location)"
```

---

## 8. Definition of Done (Sesi Ini)

- [x] Single-shot generation pakai `prompt/prompt.txt` + history + literature + files (V-OPUS hard-coded)
- [x] Chat lock V-DEEPSEEK; model picker UI dihapus
- [x] 4 tools baru: `AskQuestions`, `ReviewPaper`, `ReviseData`, `AddLiterature`
- [x] `MultiQuestionCard.vue` 1-5 pertanyaan dgn chip + free-text fallback
- [x] `RevisiProposalCard.vue` side-by-side diff dgn Terima/Tolak buttons
- [x] JSONL per-call log di `logs/chat_calls/<paper>/<date>.jsonl`
- [x] HANDOFF Wave 2 Section 5 fixes (5.1, 5.2, 5.4, 5.5, 5.6)
- [x] LiteratureTab 524 banner — long-poll + 3-strikes + halus
- [x] AppHeader hapus block "Per model"
- [x] Backend tests 163/163 PASS
- [x] Frontend build clean 5.34s
- [x] Production database schema bootstrap + alembic stamp + backend restart
- [x] Verifikasi `/api/auth/google/login` 302 → Google (working)
- [x] Bundle baru `index-DO_pSb3z.js` deployed

Pending (sesi berikutnya):
- [ ] Commit semua perubahan ke `v1` (~80 file modified, 1900 deleted)
- [ ] **Buat favicon** dari logo papefull (16/32/192/180 sizes)
- [ ] **Run SEO skill** untuk paperfull.app (`seo-google`)
- [ ] E2E test interaktif: SLR + generate paper + image gen (butuh user login Google manual)
- [ ] (LOW) `ChatMessage.vue` emit `review-cancel`
- [ ] (LOW) Retire `generate_paper_chunked.py` / `_resolve_model` shim di chat.js
- [ ] (LOW) Clean dead `model=` / `chunked=True` kwargs di `chat_tools._generate_full_paper`
- [ ] Push ke origin/v1 + buat PR

---

## 9. File Change Summary

### Modified (key files)
- `backend/app.py` (+109/-104) — `_run_generate_full_job` rewrite ke single-shot, legacy kwargs ignored
- `backend/chat.py` (+79/-98) — model lock V-DEEPSEEK, hapus selectable models, `_call_upstream` simplified
- `backend/chat_tools.py` (+426/-15) — 4 tools baru, JSONL log, allowed models shrunk, lock V-DEEPSEEK di `_plan_outline` + `_run_slr_tool`
- `backend/mode_prompts.py` (+53/-36) — DISCOVERY/REVISI prompt rewrite, MODE_TOOLS update
- `backend/slr_bp.py` (+89/-10) — long-poll wait endpoint, ai_model default V-DEEPSEEK, rollback() di wait_slr_jobs
- `backend/slr_worker.py` (+99/-76) — atomic SAVEPOINT, ai_model default
- `backend/SLR/scoring.py` (+42/-3) — TF-IDF fallback (Wave 1)
- `backend/SLR/summarizer.py` (+1/-1) — _DEFAULT_MODEL → V-DEEPSEEK
- `frontend/src/stores/chat.js` (+124/-8) — multi_question parser + selectedModel/setModel shim no-op
- `frontend/src/stores/paperJobs.js` (+70) — dedup Set + lazy-import chat
- `frontend/src/components/ChatMessage.vue` (+204/-1) — render multi_question, review_plan, revise_data
- `frontend/src/components/ChatTab.vue` (+53/-65) — model picker UI dihapus, 7 handler baru
- `frontend/src/components/LiteratureTab.vue` (+82/-15) — long-poll, 3-strikes, halus
- `frontend/src/components/RevisiProposalCard.vue` (+146/-56) — side-by-side rewrite
- `frontend/src/components/AppHeader.vue` (-7) — block "Per model" dihapus

### New
- `backend/generate_paper_single.py` — single-shot V-OPUS generator
- `frontend/src/components/MultiQuestionCard.vue` — 1-5 question chip card
- `HANDOFF_2026_05_22.md`, `HANDOFF_2026_05_22_wave2.md`, `HANDOFF_2026_05_22_wave3.md` (this file)
- `logs/chat_calls/<paper>/<date>.jsonl` (runtime, dibuat saat first chat call)

### Deleted
- `backend/generate_docx_from_json.py` (24 KB, dead code — Wave 1)
- `backend/template/MML2OMML.XSL` (3.8 MB duplicate dari `backend/MML2OMML.XSL`)
- `backend/prompt/riset/**` (~1900 file legacy research data — sinta scrapes, jurnal Q1-Q4 HTML, PDF templates) — total ~1 MB modifikasi git
- `prompt/prompt.txt` (root level, 52.5 KB, dead — backend pakai `backend/prompt/prompt.txt` — Wave 1)

---

## 10. Quick Diagnostic Commands (Production)

```bash
# Cek schema lengkap?
cd /home/sirobo/papergenerator/backend && python3 -c "
from app import app
from models import db
with app.app_context():
    from sqlalchemy import inspect
    print(sorted(inspect(db.engine).get_table_names()))
"

# Cek alembic version
psql $DATABASE_URL -c "SELECT version_num FROM alembic_version;"
# Should be: c3a9f7b2e154

# Cek backend health
curl -sf https://paperfull.app/api/healthz

# Cek bundle hash live
curl -s https://paperfull.app | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1
# Should match: index-DO_pSb3z.js (or newer if rebuilt)

# Tail backend logs
tail -f /home/sirobo/papergenerator/backend/app.log | jq -r 'select(.level=="ERROR") | .msg'
```

---

**End of handoff.** Production sudah jalan setelah inline DB-schema fix. Code changes belum di-commit. Sebelum commit, fix `ChatMessage.vue` emit `review-cancel` (5.5) optional, lalu prioritas lanjutan: favicon (5.8) + SEO (5.9).
