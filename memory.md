# PaperGenerator — Memory / Peta Arsitektur

> **ATURAN WAJIB**: ketika baca file ini nanti setelah selesai kamu kerja tolong di update lagi sesuai apa yang kamu ubah menyesuaikan style dokumen ini, tolong update file ini juga ya, setelah edit2 untuk program rebuildnya pakai ./server.sh 1 tidak boleh cara lain atau matikan pm2 dengan cara lain.
> **Tujuan**: agen baru bisa langsung paham layout repo tanpa scan ulang. Cari fitur → lihat tabel → buka file.
> Convention: `path/file.py:fn()` artinya fungsi tersebut ada di file itu.

---

## 1. STACK & ENTRY POINT

| Layer    | Tech                                              | Entry                              |
|----------|---------------------------------------------------|------------------------------------|
| Backend  | Flask + SQLAlchemy + Postgres + JWT cookie + Redis | `backend/main.py`                  |
| Frontend | Vue 3 + TS + Vite + Pinia + Tailwind              | `frontend/src/main.ts` → `App.vue` |
| AI       | AIOTOMASI API (VIOLA-GENERATE / VIOLA-CHAT)       | env `AIOTOMASI_APIKEY/API`         |
| Auth     | Google OAuth + email/password (JWT httpOnly + CSRF) | `backend/utils/auth_bp/auth.py`    |
| Jobs     | Threading: image-gen 4 worker, SLR 10 worker, AiJob sweeper | `tools/*/worker.py`        |
| Storage  | `backend/user/<username>/<paper_id>/` filesystem  | `utils/core/user_storage.py`       |

Bootstrap backend di `main.py`:
- Load env (skip override di test) → set Flask config (JWT, CORS, rate limit, max upload 60MB).
- Register 15+ blueprint (lihat §3).
- Worker pools dimulai: `start_image_workers(app)`, `start_slr_workers(app)`, daemon `_sweep_stuck_jobs` (mark `pending > 15min` → error).
- Security headers + CSP via `@app.after_request`.

---

## 2. STRUKTUR FOLDER LENGKAP

### 2.1 Backend `/backend/`

```
main.py                  Flask app + route langsung: /api/generate, /api/generate-full,
                         /api/job/<id>, /api/topics, /api/styles, /api/journals,
                         /api/upload-pdfs, /api/upload-image, /api/health, /api/docs
database/
  models.py              13 model (lihat §5). Pakai `db = SQLAlchemy()`
  alembic/versions/      Migration (baseline, indexes, cascade, paused, image jobs, dll)

tools/                   Domain features
  admin/admin.py         Blueprint admin (7 route, lihat §3.8)
  ai_detectors/          AI text detection (10 engine)
  chat/chat.py           Blueprint simple_chat (7 route: CRUD conv, clear, SSE stream)
  chat/chatPrompt.txt    System prompt: paper editing via [APPLY_PAPER] tags
  chat/drafts.py         Blueprint drafts (CRUD chat drafts, @draft injection)
  chat/tools.py          [APPLY_PAPER] parsing + apply + filesystem helpers
  data/
    chart_api.py         Blueprint chart_api (6 route, CRUD chart per paper)
    chart_generator.py   Render chart pakai matplotlib/plotly
  editor/                Inti paper editing + generation
    papers.py            Blueprint papers (7 route CRUD)
    single.py            Single-shot full paper generation (`generate_paper_json_single`)
    chunked.py           Chunked generation lama (outline → section → refs)
    api_client.py        `_call_aiotomasi_with_fallback()` - hit upstream API
  File/files.py          Blueprint files (5 route) — upload, extract text only, no raw binary
  grammar/               Grammar + spell check
  humanizer/             Humanize AI-generated text
  image_generation/      Gemini-scraping image generation
    images.py            Blueprint paper_images + image_serve (6 route)
    image_jobs.py        Blueprint image_jobs (4 route - queue)
    worker.py            `_Worker` (4 thread) + `_Dispatcher` + `start_image_workers(app)`
    CreateImageGemini.py Playwright scraping Gemini
    reconcile.py         Reconcile figure images for DOCX export
    compress.py          Kompres PNG hasil
  Journal/               44 generator template DOCX
    _docx_base.py        Base builder (page setup, styles)
    _math_omml.py        LaTeX→OMML oMath converter (shared)
    IEEEgen.py, ACMgen.py, APAgen.py, ELSEVIERgen.py, ...  build_document(paper) → DOCX bytes
  Literatur/             SLR (Systematic Literature Review)
    slr_api.py           Blueprint slr_api (13 route - jobs, literature CRUD, bulk ops, pinned)
    orchestrator.py      Pilih sumber & jalankan paralel + `expand_query()` ID→EN
    pipeline.py          `run()` end-to-end: fetch → score → summarize → save
    worker.py            `start_slr_workers(app)` - 10 worker pool, FIFO via DB
    scoring.py           ScoredPaper (SBERT 0.50 + TF-IDF 0.10 + keyword_density 0.07 + author 0.05 + citation 0.10 + recency 0.08 + venue 0.10)
    fetchers/            16 sources: arxiv, core, crossref, dblp, dimensions, europepmc,
                         ieee, lens, openalex, pubmed, sciencedirect, scopus,
                         semantic_scholar, sinta, springer, taylor_francis
  paperfull/             Full-paper async pipeline
    jobs.py              Blueprint jobs (10+ route - SSE stream, cancel, resume, retry, status poll)
    paper_worker.py      Worker eksekutor
    generate_full.py     Orkestrator
    prompt/topic/*.txt   Prompt per topic (cs, biomed, dll)
    prompt/style/*.txt   Prompt per citation style (ieee, apa, harvard, dll)
  paraphrase/            AI paraphrase
  plagiarism/            Plagiarism check
  preview/               Export ke berbagai format (DOCX, PDF, LaTeX, Markdown)
    ref_normalize.py     Multi-style reference formatter (journal-agnostic)
  summarize/             Summarize text
  translator/            Translation tool

utils/
  job_core.py            `init_job_core(app, ai_model)`, job CRUD, `_log_api_usage()`
  ai_tools/
    tools_api.py         Blueprint tools_api (2 route): `/api/tools/<tool_id>`, translate config
    model_router.py      Routing model VIOLA-CHAT/GENERATE
    model_config.py      `get_primary_generate_model()`
  auth_bp/auth.py        Blueprint auth (7 route, lihat §3.1)
  core/
    global_logger.py     `init_global_logging()`, `log_access()`, `log_activity()`
    env_loader.py        Wrapper load_dotenv + numbered→base env normalization
    redis_client.py      Singleton Redis (rate-limit, SSE pubsub)
    user_storage.py      `get_username()`, `save_paper_json()`, `save_paper_json_by_id()`
    cache.py             `@cached(ttl_seconds=…)` in-memory cache
  state_bp/state.py      Per-paper UI state persistence (Blueprint)
  middleware/
    error_handler.py     `register_error_handlers(app)` - JSON error responses
    validation.py        Schema validation decorators
  monitoring/            Prometheus metrics (observability_v2.py)
  quota/quota.py         Token quota
  health/health.py       Health check (/ + /detailed)
  schemas/               Pydantic-style validators

user/                    Per-user FS: <username>/<paper_id>/{paper.json, files/, generation/}
data/                    uploads/, exports/, charts/, logs/
tests/                   integration/, performance/, helpers/ (mock_ai.py)
```

### 2.2 Frontend `/frontend/src/`

```
main.ts                  Bootstrap: createApp(App) + Pinia + Router + globalErrorHandler
App.vue                  Root: <RouterView/> + global modal/toast

api/
  index.ts               Axios client: baseURL=VITE_API_URL, withCredentials, CSRF interceptor
  charts.ts              Wrapper API chart

router/index.ts          7 route + guard: requiresAuth, requiresAdmin

stores/                  Pinia composition-API stores (lihat §6)
  auth.ts, paper.ts, paperJobs.ts, chat.ts, imageGen.ts,
  literature.ts, tools.ts, quota.ts, theme.ts, ui.ts

views/                   Halaman route-level (lihat §7)
  LandingPage.vue, LoginPage.vue, AuthCallbackPage.vue,
  DashboardPage.vue, PaperEditorPage.vue, FilesPage.vue, AdminPage.vue

components/              36+ komponen Vue (lihat §7.2)
composables/             useKeyboardShortcuts.ts, useSanitize.ts, useMathRender.ts
services/                errorHandler.ts, globalErrorHandler.ts
utils/                   logger.ts, errorMessages.ts
types/                   router.d.ts, components.ts, slr.ts
```

---

## 3. API ENDPOINTS (lengkap, dikelompokkan per blueprint)

### 3.1 Auth — `utils/auth_bp/auth.py` (prefix `/api/auth`, limit 10/min)
| Method | Path                | Fungsi                            |
|--------|---------------------|-----------------------------------|
| POST   | `/register`         | Daftar email/password             |
| POST   | `/login`            | Login → set cookie JWT            |
| GET    | `/google/login`     | Redirect OAuth                    |
| GET    | `/google/callback`  | Callback OAuth → set cookie + CSRF|
| POST   | `/refresh`          | Refresh access token              |
| GET    | `/me`               | Profil user current               |
| POST   | `/logout`           | Clear cookie                      |

### 3.2 Papers CRUD — `tools/editor/papers.py` (prefix `/api/papers`)
| Method | Path                | Fungsi                                 |
|--------|---------------------|----------------------------------------|
| GET    | `/`                 | `list_papers()` - daftar paper user    |
| POST   | `/`                 | `save_paper()` - create/upsert         |
| GET    | `/<paper_id>`       | `load_paper()` - detail                |
| PUT    | `/<paper_id>`       | `update_paper()` - replace full        |
| PATCH  | `/<paper_id>`       | `patch_paper()` - JSON-patch ops       |
| DELETE | `/<paper_id>`       | `delete_paper()`                       |
| GET    | `/<paper_id>/status`| `get_paper_status()` - lock & job state|

### 3.3 AI Generate — `main.py`
| Method | Path                  | Fungsi                                                         |
|--------|-----------------------|----------------------------------------------------------------|
| POST   | `/api/generate`       | `generate()` - 1 section, sync (limit 20/min)                 |
| POST   | `/api/generate-full`  | `generate_full()` - spawn thread (limit 10/min)               |
| GET    | `/api/job/<job_id>`   | `get_job_status()` - polling: pending/done/error               |

### 3.4 Paperfull Jobs — `tools/paperfull/jobs.py` (advanced async + SSE)
| Method | Path                                       | Fungsi                                   |
|--------|--------------------------------------------|------------------------------------------|
| POST   | `/api/papers/<paper_id>/generate`          | `enqueue_generate()` - alt entry         |
| POST   | `/api/papers/<paper_id>/generate-stream`   | `generate_stream()` - **SSE** langsung, inject user prefs + selected_drafts + literature. Auto-enqueue image jobs setelah paper done. Buat AiJob untuk bell notif. |
| GET    | `/api/papers/<paper_id>/generate-status`   | Poll progress streaming (reasoning+content) |
| GET    | `/api/jobs/<job_id>`                       | `get_job()` - status                     |
| POST   | `/api/jobs/<job_id>/cancel`                | `cancel_job()`                           |
| GET    | `/api/jobs/<job_id>/stream`                | `stream_job()` - **SSE** progress Redis  |
| GET    | `/api/papers/<paper_id>/active-jobs`       | Jobs aktif paper                         |
| POST   | `/api/ai-jobs/<job_id>/cancel`             | Cancel ai-job                            |
| POST   | `/api/ai-jobs/<job_id>/resume`             | Resume dari checkpoint                   |
| POST   | `/api/ai-jobs/<job_id>/retry-section`      | Retry 1 section                          |
| GET    | `/api/me/ai-jobs/recent`                   | Inbox notifikasi (filter orphan)         |

### 3.5 Chat — `tools/chat/chat.py`
| Method | Path                                          | Fungsi                          |
|--------|-----------------------------------------------|---------------------------------|
| GET    | `/api/papers/<paper_id>/conversations`        | `list_paper_conversations()`    |
| POST   | `/api/papers/<paper_id>/conversations`        | `create_paper_conversation()`   |
| GET    | `/api/chat/conversations/<conv_id>`           | `get_conversation()` + messages |
| PATCH  | `/api/chat/conversations/<conv_id>`           | `rename_conversation()`         |
| DELETE | `/api/chat/conversations/<conv_id>`           | `delete_conversation()`         |
| POST   | `/api/chat/conversations/<conv_id>/clear`     | `clear_conversation()`          |
| POST   | `/api/chat/conversations/<conv_id>/messages`  | `send_message()` - **SSE stream** + [APPLY_PAPER] + @slr/@draft tags |

### 3.6 Chat Drafts — `tools/chat/drafts.py`
| Method | Path                                     | Fungsi                     |
|--------|------------------------------------------|----------------------------|
| POST   | `/api/papers/<paper_id>/drafts`          | Create draft from conv     |
| GET    | `/api/papers/<paper_id>/drafts`          | List drafts                |
| GET    | `/api/papers/<paper_id>/drafts/<name>`   | Get single draft           |
| PATCH  | `/api/papers/<paper_id>/drafts/<name>`   | Update draft               |
| DELETE | `/api/papers/<paper_id>/drafts/<name>`   | Delete draft               |

### 3.7 Files — `tools/File/files.py` (prefix `/api/papers`)
| Method | Path                                              | Fungsi                                          |
|--------|---------------------------------------------------|-------------------------------------------------|
| GET    | `/<paper_id>/files`                               | List PaperFile                                  |
| POST   | `/<paper_id>/files`                               | Upload (multipart, max 10MB, text-only persist) |
| DELETE | `/<paper_id>/files/<file_id>`                     | Hapus                                           |
| GET    | `/<paper_id>/files/<file_id>/raw`                 | Download (inline, extracted text)               |
| GET    | `/<paper_id>/files/<file_id>/preview`             | Preview text                                    |

Plus `main.py`: `POST /api/upload-pdfs`, `POST /api/upload-image`

### 3.8 Images — `tools/image_generation/`
| Method | Path                                       | Fungsi                          |
|--------|--------------------------------------------|---------------------------------|
| POST   | `/api/papers/<id>/images`                  | Create image record             |
| POST   | `/api/papers/<id>/images/upload`           | Upload file                     |
| GET    | `/api/papers/<id>/images`                  | List                            |
| DELETE | `/api/papers/<id>/images/<image_id>`       | Hapus                           |
| POST   | `/api/papers/<id>/sign`                    | Signed serving URL              |
| GET    | `/api/img/<paper_id>/<filename>`           | Serve image (HMAC)              |
| POST   | `/api/image-jobs`                          | Create job (4-worker pool)      |
| GET    | `/api/image-jobs`                          | List jobs                       |
| GET    | `/api/image-jobs/<job_id>`                 | Status                          |
| POST   | `/api/image-jobs/<job_id>/cancel`          | Cancel                          |

### 3.9 Admin — `tools/admin/admin.py` (prefix `/api/admin`, requires admin)
| Method | Path                              | Fungsi                          |
|--------|-----------------------------------|---------------------------------|
| GET    | `/users`                          | List user                       |
| POST   | `/users/<user_id>/promote`        | Set role admin                  |
| PATCH  | `/users/<user_id>/quota`          | Update quota                    |
| POST   | `/users/<user_id>/reset-quota`    | Reset quota counter             |
| GET    | `/papers`                         | List semua paper                |
| GET    | `/usage`                          | ApiUsageLog query               |
| GET    | `/stats`                          | Statistik global                |

### 3.10 SLR / Literature — `tools/Literatur/slr_api.py`
| Method | Path                                                   | Fungsi                     |
|--------|--------------------------------------------------------|----------------------------|
| POST   | `/api/papers/<paper_id>/slr/jobs`                      | `create_slr_job()`         |
| GET    | `/api/papers/<paper_id>/slr/jobs`                      | `list_slr_jobs()`          |
| GET    | `/api/papers/<paper_id>/slr/jobs/wait`                 | `wait_slr_jobs()` long-poll|
| GET    | `/api/slr/jobs/<job_id>`                               | `get_slr_job()`            |
| DELETE | `/api/slr/jobs/<job_id>`                               | `cancel_slr_job()`         |
| GET    | `/api/papers/<paper_id>/literature`                    | `list_literature()`        |
| POST   | `/api/papers/<paper_id>/literature`                    | `create_literature()`      |
| PATCH  | `/api/papers/<paper_id>/literature/<item_id>`          | `update_literature()`      |
| DELETE | `/api/papers/<paper_id>/literature/<item_id>`          | `delete_literature()`      |
| POST   | `/api/papers/<paper_id>/literature/bulk-delete`        | `bulk_delete_literature()` |
| POST   | `/api/papers/<paper_id>/literature/bulk-patch`         | `bulk_patch_literature()`  |
| POST   | `/api/papers/<paper_id>/literature/from-files`         | `import_from_files()`      |
| GET    | `/api/papers/<paper_id>/literature/pinned`             | Formatted pinned items     |

### 3.11 Lainnya
| Path                        | File                              | Fungsi                                   |
|-----------------------------|-----------------------------------|------------------------------------------|
| `GET /api/topics`           | `main.py`                         | List topic (cached 1h)                   |
| `GET /api/styles`           | `main.py`                         | List citation style (cached 1h)          |
| `GET /api/journals`         | `main.py`                         | List template Journal/*gen.py            |
| `GET /api/health`           | `utils/health/health.py`          | Health check                             |
| `GET /api/quota`            | `utils/quota/quota.py`            | Token quota user                         |
| `POST /api/tools/<tool_id>` | `utils/ai_tools/tools_api.py`     | Run AI tool                              |
| `GET/POST/PUT/DELETE /api/papers/<id>/charts` | `tools/data/chart_api.py` | 6 route CRUD chart          |
| `GET /api/docs`             | `main.py`                         | Swagger UI                               |

---

## 4. ALUR FUNGSI KUNCI (call graph ringkas)

### 4.1 Generate Full Paper (SSE stream, dipakai default)
```
POST /api/papers/<id>/generate-stream                    [tools/paperfull/jobs.py:generate_stream]
  ↓ Buat AiJob (running) untuk bell notif
  ↓ Baca selected_drafts, data_files, reference_files dari FormData/JSON
  ↓ Thread: gen() — SSE generator dengan Redis snapshot + GeneratorExit handler
      ↓ _pf_snapshot() tulis Redis key paperfull:stream:<paper_id> (throttle 1.5s)
      ↓ generate_paper_json_single(judul, custom_prompt,...)   [tools/editor/single.py]
          ├─ _load_system_prompt(style, topic)
          ├─ _load_chat_history(conv_id)
          ├─ _load_literature(paper_id) + pinned literature injection
          ├─ _load_attached_files(paper_id)
          ├─ _call_v_opus() → _call_aiotomasi_with_fallback()  [editor/api_client.py]
          ├─ _parse_json_response(raw)
          └─ _normalize_paper_shape(raw) + _lift_subsections()
      ↓ _persist_paper_data() — rollback + re-query + commit (3x retry, fresh connection)
      ↓ Auto-enqueue image generation jobs (_collect_gambar_prompts)
      ↓ yield event: done dengan {paper_data, image_jobs: [ids]}

Frontend (PaperfullTab.vue):
  ↓ _startStatusPoll() poll /generate-status tiap 2s
  ↓ event: thinking → reasoningText += token
  ↓ event: content → contentText += token → tryLiveUpdateEditor (incremental JSON parser)
  ↓ event: done → finishGeneration() → editor updated
  ↓ Auto-poll image jobs jika ada
```

### 4.2 Chat (SSE streaming)
```
POST /api/chat/conversations/<conv_id>/messages    [tools/chat/chat.py:send_message]
  ↓ load Conversation, ChatMessage history
  ↓ get_paper_context(paper_id) — full Paper.data JSON (cap 30K)
  ↓ Parse tags: @slr (inject pinned literature), @draft (inject named drafts)
  ↓ Stream AI response via SSE (thinking + content, Redis snapshot incremental)
  ↓ Parse [APPLY_PAPER] tags → apply_operations() → update Paper.data
  ↓ SSE event 'paper_applied' → frontend reload paper
  ↓ Save ChatMessage (user + assistant + thinking) ke DB
  ↓ GeneratorExit handler: drain remaining + save DB before exit
```

### 4.3 SLR Pipeline
```
POST /api/papers/<id>/slr/jobs              [slr_api.py:create_slr_job]
  ↓ SlrJob row (status=queued) + enqueue_slr_job()
  ↓ worker.py picks FIFO (10 worker pool, DB retry 3x untuk SSL reconnect)
      ↓ pipeline.run(query, sources, top_k, ...)
          ├─ orchestrator.pick_sources_for_topic() + expand_query() (ID→EN)
          ├─ fetchers/* (16 sources) paralel
          ├─ scoring.py: SBERT + TF-IDF + keyword_density + author + citation + recency + venue
          ├─ summarizer.py: AI summarize per paper
          └─ save() → SlrJob.result_json + LiteratureItem rows
```

### 4.4 Image Generation
```
POST /api/image-jobs                       [image_jobs.py]
  ↓ ImageGenJob row + submit_now(job_id)   [worker.py]
  ↓ _Dispatcher pick → _Worker (4 thread, 1 per Gemini account)
      ↓ CreateImageGemini: dismiss overlays → new chat → menu → type prompt → wait download
      ↓ compress.py kompres PNG
      ↓ save ke user/<u>/<paper>/images/ + PaperImage DB row
      ↓ reconcile.py maps completed jobs back to paper.data figure Path fields
```

### 4.5 DOCX Export (44 jurnal)
```
POST /api/export (main.py:export_docx)
  ↓ reconcile_figure_images(paper_id) — match ImageGenJob done → set figure Path
  ↓ normalize_references(paper_data, style) — inject formatted text per ref
  ↓ _get_builder_for_journal() → build_document(paper) → DOCX bytes
  ↓ Setiap jurnal: refs formatted, images embedded, equations as native oMath
```

---

## 5. DATABASE MODELS (`database/models.py`)

| Model           | Tabel                | Field utama                                                   |
|-----------------|----------------------|---------------------------------------------------------------|
| `User`          | users                | id, email, password_hash, name, role, google_id, token_quota, tokens_used, created_at |
| `Paper`         | papers               | id (uuid), user_id, title, data (JSONB), updated_at, operation_lock, version (opt-in optimistic lock) |
| `PaperImage`    | paper_images         | id, paper_id, filename, url, caption, created_at              |
| `PaperFile`     | paper_files          | id, paper_id, filename, mime, size, preview_text, sha256       |
| `ApiUsageLog`   | api_usage_logs       | id, user_id, endpoint, prompt_tokens, completion_tokens, ts   |
| `Conversation`  | conversations        | id (uuid), paper_id, user_id, title, mode, paused              |
| `ChatMessage`   | chat_messages        | id, conv_id, role, content, tool_calls JSONB, thinking        |
| `ChatDraft`     | chat_drafts          | id, paper_id, user_id, conversation_id, name, content, tags   |
| `ProjectMemory` | project_memory       | id, paper_id, conv_id (FK), key, value                        |
| `AiJob`         | ai_jobs              | id, user_id, paper_id, prompt, status, stage, progress, result JSONB, error |
| `LiteratureItem`| literature_items     | id, paper_id, title, authors, year, doi, abstract, url, summary, score, pdf_url, review, gap_riset, pinned, must_read |
| `SlrJob`        | slr_jobs             | id, paper_id, query, sources, status, stage, info JSONB, result_json |
| `ImageGenJob`   | image_gen_jobs       | id, user_id, paper_id, prompt, status, result_urls JSON, error |

Status enums umum: `pending|running|done|error|cancelled`.
FK indexes pada: ai_jobs(user_id), papers(user_id), chat_messages(paper_id, user_id), literature_items(paper_id, user_id), slr_jobs(user_id).

---

## 6. PINIA STORES (`frontend/src/stores/`)

| Store                | File              | State/Actions utama                                                                       |
|----------------------|-------------------|-------------------------------------------------------------------------------------------|
| `useAuthStore`       | `auth.ts`         | `user`, `isLoggedIn`, `csrfToken`. Actions: `login`, `register`, `googleLogin`, `fetchMe`, `logout` |
| `usePaperStore`      | `paper.ts`        | `paper`, `loading`, `pendingCount`, `canUndo/canRedo`, history stack. Actions: `load`, `save`, `patch`, `undo/redo`, `exportDocx` |
| `usePaperJobsStore`  | `paperJobs.ts`    | Map `<paperId, job>`. Actions: `startGenerateFull`, `pollJob`, `cancelJob`, `resumeJob`   |
| `useChatStore`       | `chat.ts`         | `conversations`, `activeConv`, `messages`. Actions: `loadConvs`, `createConv`, `sendMessage` (SSE), resume poller after refresh |
| `useImageGenStore`   | `imageGen.ts`     | `jobs`, `results`. Actions: `requestGen`, `pollJob({onDone})`, `cancel`, `clearFinished`  |
| `useLiteratureStore` | `literature.ts`   | `slrJobs`, `literatureItems`. Actions: `startSLR`, `pollSLR`, `listItems`, `bulkPatch`    |
| `useToolsStore`      | `tools.ts`        | Tool results per tool_id. Actions: `runTool`, `cancelTool`, `dispose`                     |
| `useQuotaStore`      | `quota.ts`        | `tokensUsed`, `tokensLimit`, `quotaExceeded`. Actions: `refresh`                          |
| `useThemeStore`      | `theme.ts`        | `mode`. Actions: `toggle`, `setMode`                                                      |
| `useUiStore`         | `ui.ts`           | `modals`, `toasts`, `sidebar`. Actions: `showToast`, `openModal`, `closeAllModals`        |

---

## 7. FRONTEND HALAMAN & KOMPONEN

### 7.1 Views (route-level)

| View | Path | Auth | Fungsi |
|------|------|------|--------|
| `LandingPage.vue` | `/` | — | Public homepage + CTA |
| `LoginPage.vue` | `/login` | — | Email/password + Google OAuth |
| `AuthCallbackPage.vue` | `/auth/callback` | — | OAuth callback handler |
| `DashboardPage.vue` | `/dashboard` | ✓ | Grid paper list + quota badge |
| `PaperEditorPage.vue` | `/editor/:paperId` | ✓ | Main editor (3-panel, multi-tab) |
| `FilesPage.vue` | — | ✓ | File browser global |
| `AdminPage.vue` | `/admin` | admin | User/quota/stats management |

**PaperEditorPage** tab:
| Tab | Komponen | Fungsi |
|-----|----------|--------|
| Sections | `SectionsTab.vue` | Tree section/subsection + AI per section |
| Content | `ContentList.vue` | Rich-text items |
| Files | `FilesTab.vue` | Upload + preview (text-only) |
| Literature | `LiteratureTab.vue` + `LiteratureCard.vue` + `SLRResultsView.vue` | SLR + literature CRUD |
| Charts/Data | `ChartsTab.vue` + `DataTab.vue` | Chart generator |
| Images | `ImageTab.vue` | Image gen + upload + manage |
| Journal | `JournalTab.vue` | Pilih template DOCX (44 jurnal) |
| Preview | `PreviewTab.vue` | Render preview paper |
| Paperfull | `PaperfullTab.vue` | Full paper gen: prompt + topic/style + 2 streaming box (Reasoning + Content). Live editor update via incremental JSON parser. Auto-image-gen after done. |
| Metadata | `MetadataTab.vue` | Authors, affiliation, keywords |
| References | `ReferencesTab.vue` | Edit references (structured objects) |
| Tools | `ToolsTab.vue` + `ToolWorkspace.vue` | AI tools (paraphrase, summarize, dll) |
| Chat | `ChatTab.vue` + `ChatMessage.vue` | Chat AI tentang paper |

### 7.2 Style System
- Tailwind custom palette (`cream`, `ink`, `ash`, `navy`, `anthracite`). Dark mode `class`-based via `useThemeStore`.
- No UI component library (all custom). Markdown: `markdown-it` + `highlight.js` + DOMPurify.
- Drag-drop: `vuedraggable`. KaTeX bundled via Vite (no CDN).

---

## 8. CATATAN PENTING / GOTCHAS

| Area              | Detail                                                                                                     |
|-------------------|------------------------------------------------------------------------------------------------------------|
| **Auth**          | JWT httpOnly cookie + CSRF double-submit. Axios interceptor auto-attach `X-CSRF-TOKEN`. Session cookie OFF (persist 7 hari). |
| **CORS**          | Hanya `localhost:8000` di dev. Produksi same-origin via nginx.                                             |
| **Rate Limit**    | Default 1000/min. `/api/generate` 20/min. `/api/generate-full` 10/min. `/api/auth/*` 10/min. Redis storage. |
| **Upload**        | Max 60MB/request. Per PDF 30MB. Per PaperFile 10MB.                                                        |
| **DB Session**    | Postgres: `statement_timeout=30s`, `idle_in_transaction=5min`, `pool_pre_ping=True`, `pool_recycle=1800`.  |
| **Workers**       | Image gen: 4 (1 per Gemini account). SLR: 10 (FIFO DB). PDF extract: 20 (ThreadPool). AiJob sweeper: 60s. |
| **SSE**           | Redis pub/sub + per-paper snapshot key (TTL 1800s). Frontend EventSource + status poll fallback. GeneratorExit handler di semua SSE endpoint. |
| **User storage**  | FS: `backend/user/<username>/<paper_id>/`. Generation logs per job.                                        |
| **PM2**           | Production PM2: `PM2_HOME=/home/sirobo/.pm2 pm2 ...`. Jangan bare `pm2` (session daemon conflict).        |
| **Rebuild**       | Setelah edit: `./server.sh 1` (frontend rebuild).                                                         |
| **Test mocking**  | `AI_MOCKING=true` → intercept AI calls. `conftest.py` pakai `sqlite:///:memory:`.                         |

---

## 9. CHANGELOG RINGKAS (June 2026)

| Tanggal | Area | Ringkasan |
|---------|------|-----------|
| 06-11 | JWT | Session cookie OFF → persist 7 hari (`JWT_SESSION_COOKIE=False`) |
| 06-11 | Routing | `/` → landing (bukan dashboard), logout → `/`, catch-all → `/` |
| 06-11 | Dark mode | Audit seluruh frontend: color tokens, forced dark bg di Login/Landing, card shadows |
| 06-11 | Chat system | Full paper JSON context (cap 30K), thinking stream + save to DB, modular tools.py, auto-reload prompt |
| 06-12 | SLR overhaul | 3 fetcher baru (core/lens/dimensions = 16 total), expand_query ID→EN, enhanced scoring, @slr tag |
| 06-12 | File upload | Only extracted text persisted (no raw binary), PPTX support |
| 06-12 | Image gen | UI redesign (merged generate+upload+manage), account4 overlay dismiss fix |
| 06-12 | Bug screening | 2 rounds: 50+ bugs fixed (null guards, race conditions, path traversal, DB rollback, AbortController, reader lock) |
| 06-12 | Streaming | BodyStreamBuffer abort fix, reader.releaseLock(), incremental section parser |
| 06-13 | SSE yield | f-string data tidak di-yield (standalone expression) → gabung dalam satu yield |
| 06-13 | KaTeX | CDN → bundled import via composable |
| 06-13 | Chat reasoning | Filter fix (duplicate thinking), save thinking to DB, Redis write throttle |
| 06-13 | Bell notif | Delete buttons, orphan job filter |
| 06-13 | Auto image | Auto-enqueue image jobs after paperfull generate |
| 06-14 | Streaming polish | Timer-based sync 2s, age-based recovery, error cleanup, progress UI |
| 06-14 | References | Structured ref objects, `_formatStructuredRef()`, display helpers |
| 06-14 | Persistensi | Chat resume poller after refresh, data-jobs keep ID on error |
| 06-14 | Layout | Split-brain fix (computed via ui store), SSL save (fresh connection retry), bell AiJob creation |
| 06-14 | 2-bucket input | Data + Referensi separate drop-zones, env normalize (numbered→base) |
| 06-14 | Render | Stray `\u2022` decode, empty formula skip, image marker cleanup |
| 06-15 | Chat drafts | Export chat as named draft, @draft injection, checkbox selector di paperfull |
| 06-15 | Draft→file | Section Chat Drafts dihapus, + picker di Referensi (💬 draft/upload/dari paper), paste teks ChatTab dihapus |
| 06-15 | Bell fix | `_clickedIds` persisted to localStorage (survives refresh) |
| 06-15 | State fix | `saveState`/`_restoreBucket` preserve isDraft/isExisting flags, virtual entries not stale |
| 06-15 | Bug fixes | stopGeneration aborts SSE, _startStatusPoll clears old timer, _pushFiles replaces stale entries |
| 06-15 | Data tab cleanup | "Buat Data Variabel" button removed (tabel auto dari paperfull) |
| 06-15 | Dari Data picker | + picker di Data bucket: "Dari Data" opsi (ambil tabel/grafik/analisa dari DataTab localStorage) |
| 06-15 | Pre-extracted texts | `data_texts`/`reference_texts` dikirim via FormData (virtual entries tanpa File object) |
| 06-15 | Click-outside fix | + picker dropdown auto-close saat klik bagian lain (use `composedPath` + template refs) |
| 06-16 | hasDataAnalysis guard | "Dari Data" button hidden when no data analysis exists (computed from localStorage) |
| 06-16 | SSE error handling | `onerror` now checks job status via API → shows actual error message instead of generic "Koneksi terputus" |
| 06-15 | DOCX export | Ref rendering fix (structured → IEEE format), figure image reconcile + embed |
| 06-15 | 44 jurnal | All templates fixed: refs/gambar/rumus/grafik. Modules: `ref_normalize.py`, `_math_omml.py`, `reconcile.py` |
| 06-15 | Scalability | Silent=True pada semua get_json, 9 FK indexes, optimistic lock (opt-in), nginx conn_limit 100 |
| 06-15 | SLR UI overhaul | LiteraturTab: kolom baru (#, Judul full, Abstract full, Penulis, Tahun, Sumber/DOI/PDF gabungan, Sitasi, Skor, Review, Aksi). Full-width stretch. Sort filter buttons (tahun/skor/sitasi/judul A-Z/penulis A-Z). 🤖 Review Pinned button (AI review per-item + bulk pinned). Removed: must-read, AI summaries badge, Venue column. Review prompt: 50-word summary + 20-word research gap, language-aware (user preferred_language). |

---

## 10. ARSITEKTUR KEY PATTERNS

**Persistence hierarchy:**
- Real-time state: sessionStorage (per-paper key `paperfull_state:<paper_id>`)
- Cross-tab: Pinia → localStorage
- Durable: PostgreSQL (papers.data JSONB, ai_jobs, chat_messages)
- SSE progress: Redis snapshot (paperfull:stream:<paper_id>, TTL 1800s, throttle 1.5s)

**Error resilience patterns:**
- Semua `db.session.commit()` wrapped try/except + rollback
- SSE generators: GeneratorExit handler → save DB state before exit
- Reader lock: always `reader.releaseLock()` in finally block
- AbortError: caught locally, filtered from user-facing toasts
- Long-running DB ops: retry 3x with fresh connection (SSL reconnect pattern)

**Image generation pipeline:**
1. Paper generate → extract gambar prompts → auto-enqueue ImageGenJob
2. 4 Gemini accounts (Playwright scraping) → compress PNG → save + PaperImage row
3. DOCX export: `reconcile_figure_images()` matches done jobs → sets figure.Path → embed

**Reference system:**
- Store as structured objects (authors[], year, title, doi, type)
- `ref_normalize.py` injects formatted `text` field per style (ieee/apa/acs) at export time
- `reference_formatter.format_reference()` handles all types (journal/conference/book/website)

---

_Last update: 2026-06-15. Update progresif sesuai investigasi baru._