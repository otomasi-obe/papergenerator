# PaperGenerator — Memory / Peta Arsitektur

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
|          | Error codes: google_denied, email_not_allowed,       | `frontend/src/views/LoginPage.vue` |
|          | auth_failed, invalid_state, csrf_detected,           | `frontend/src/views/AuthCallbackPage.vue` |
|          | session_expired                                      | `.env` (GOOGLE_ALLOWED_EMAILS)     |
| Jobs     | Threading: image-gen 4 worker, SLR 10 worker, AiJob sweeper | `tools/*/worker.py`        |
| Storage  | `backend/user/<username>/<paper_id>/` filesystem  | `utils/core/user_storage.py`       |

Bootstrap backend di `main.py`:
- Load env (skip override di test) → set Flask config (JWT, CORS, rate limit, max upload 60MB).
- Register 15 blueprint (lihat §3).
- Worker pools dimulai: `start_image_workers(app)`, `start_slr_workers(app)`, daemon `_sweep_stuck_jobs` (mark `pending > 15min` → error).
- Security headers + CSP via `@app.after_request`.

---

## 2. STRUKTUR FOLDER LENGKAP

### 2.1 Backend `/backend/`

```
main.py                  Flask app + 4 route langsung: /api/generate, /api/generate-full,
                         /api/job/<id>, /api/topics, /api/styles, /api/journals,
                         /api/upload-pdfs, /api/upload-image, /api/health, /api/docs,
                         /api/openapi.yaml
searchPaper.py           CLI: cari paper dari API akademik (standalone)
sync_papers_to_fs.py     Sync DB paper → filesystem user/
conftest.py              Pytest fixtures (db override sqlite memory)
openapi.yaml             Spec OpenAPI 3.1 (served di /api/docs)
gunicorn.conf.py         Worker config produksi
start.sh, run_tests.sh   Runner scripts
alembic.ini              Alembic migration config

database/
  models.py              13 model (lihat §5). Pakai `db = SQLAlchemy()`
  alembic/env.py         Alembic env (autogenerate dari models)
  alembic/versions/      9 migration (baseline, indexes, cascade, paused, image jobs, dll)

tools/                   Domain features
  __init__.py
  admin/admin.py         Blueprint admin (7 route, lihat §3.8)
  ai_detectors/          AI text detection (heuristic engines)
    detector.py          Orkestrator deteksi
    engines/             burstiness, fingerprint, perplexity_proxy, model_attribution, dll (10 engine)
  chat/chat.py           Blueprint simple_chat (8 route chat & memory; SSE stream)
  data/
    chart_api.py         Blueprint chart_api (6 route, CRUD chart per paper)
    chart_generator.py   Render chart pakai matplotlib/plotly
  editor/                Inti paper editing + generation
    papers.py            Blueprint papers (7 route CRUD)
    single.py            Single-shot full paper generation (`generate_paper_json_single`)
    chunked.py           Chunked generation lama (outline → section → refs)
    api_client.py        `_call_aiotomasi_with_fallback()` - hit upstream API
    section_generator.py Generator per-section
    quality_validator.py Validasi shape paper
    utils.py             Helper editing
    workflow_integration.py Integrasi tool calls dari chat
  File/                  Upload & manage PaperFile
    files.py             Blueprint files (5 route)
    extract_pdfs.py      Extract teks PDF (PyMuPDF/pdfminer); `_EXTRACT_POOL` (20 worker)
  grammar/
    grammar_checker.py   Grammar AI-assisted
    spell_checker.py     Spell check
  humanizer/humanizer.py Humanize AI-generated text
  image_generation/      Gemini-scraping image generation
    images.py            Blueprint paper_images + image_serve (6 route)
    image_jobs.py        Blueprint image_jobs (4 route - queue)
    worker.py            `_Worker` (4 thread) + `_Dispatcher` + `start_image_workers(app)`
    CreateImageGemini.py Playwright scraping Gemini
    GeminiCookies.py     Cookie pool per akun
    open_gemini.py       Browser launcher
    compress.py          Kompres PNG hasil
  Journal/               25 generator template DOCX
    _docx_base.py        Base builder (page setup, styles)
    IEEEgen.py, ACMgen.py, APAgen.py, ELSEVIERgen.py, ...  build_document(paper) → DOCX bytes
  Literatur/             SLR (Systematic Literature Review)
    slr_api.py           Blueprint slr_api (12 route - jobs, literature CRUD, bulk ops)
    orchestrator.py      Pilih sumber & jalankan paralel
    pipeline.py          `run()` end-to-end: fetch → score → summarize → save
    worker.py            `start_slr_workers(app)` - 10 worker pool, FIFO via DB
    scoring.py           ScoredPaper (relevance, citation, recency)
    summarizer.py        AI summarize per paper
    unpaywall.py         Fetch OA PDF
    http_client.py       Retry-able HTTP
    text_cleaner.py      Normalisasi teks
    paper.py             Dataclass `Paper`
    cli.py, run_slr.py   CLI standalone
    fetchers/            arxiv, crossref, dblp, europepmc, ieee, openalex, pubmed,
                         sciencedirect, scopus, semantic_scholar, sinta, springer, taylor_francis
  paperfull/             Full-paper async pipeline
    jobs.py              Blueprint jobs (10 route - SSE stream, cancel, resume, retry)
    paper_worker.py      Worker eksekutor
    generate_full.py     Orkestrator
    prompt/topic/*.txt   Prompt per topic (cs, biomed, dll)
    prompt/style/*.txt   Prompt per citation style (ieee, apa, harvard, dll)
  paraphrase/paraphraser.py    AI paraphrase (dipakai tools_api)
  plagiarism/plagiarism_checker.py  Plagiarism check
  preview/               Export ke berbagai format
    base.py              Base exporter
    docx_exporter.py     DOCX (delegate ke Journal/*gen.py)
    pdf_exporter.py      PDF
    latex_exporter.py    LaTeX
    markdown_exporter.py Markdown
    manager.py           Router format
  summarize/             Summarize text
  translator/            Translation tool

utils/
  job_core.py            `init_job_core(app, ai_model)`, `_job_create/_get/_set_done/_set_error`,
                         `_get_current_user_id()`, `_log_api_usage()`
  job_tracker.py         In-memory job tracking helper
  ai_tools/
    tools_api.py         Blueprint tools_api (2 route): `/api/tools/<tool_id>`,
                         `/api/tools/translate/config`. Routes ke paraphrase/summarize/translate/dll
    model_router.py      Routing model VIOLA-CHAT/GENERATE
    model_config.py      `get_primary_generate_model()`
  auth/helpers.py        Helper validate user, password hash
  auth_bp/auth.py        Blueprint auth (7 route, lihat §3.1)
  config/                settings.py, security.py, extensions.py (di-import opsional)
  core/
    global_logger.py     `init_global_logging()`, `log_access()`, `log_activity()`
    env_loader.py        Wrapper load_dotenv
    retry_helper.py      Decorator retry exponential
    storage_helper.py    Helper FS path
    cache.py             `@cached(ttl_seconds=…)` in-memory cache
    redis_client.py      Singleton Redis (rate-limit, SSE pubsub)
    user_storage.py      `get_username(user_id)`, `save_paper_json(username, title, data)`,
                         `save_paper_json_by_id(username, paper_id, data)`
    s3_storage.py        Optional S3 backend
    errors.py            ErrorCode, ErrorCategory enums
    log_helper.py, hourly_log_handler.py  Logging rotation
  middleware/
    error_handler.py     `register_error_handlers(app)` - JSON error responses
    validation.py        Schema validation decorators
  monitoring/
    observability.py     Prometheus metrics dasar
    observability_v2.py  Metrics v2 (RATE_LIMIT_REQUESTS, RATE_LIMIT_BREACHES, dll)
  quota/quota.py         Blueprint quota (1 route GET /quota) + `quota_exceeded(user_id)` check
  health/health.py       Blueprint health (2 route: /, /detailed)
  logging/
    logging_api.py       Blueprint logging_api (1 route POST /api/logs/frontend)
    chat_logger.py       Log chat ke file per session
  schemas/               Pydantic-style validator (chat_schemas, papers_schemas, common_schemas)

user/                    Per-user FS: <username>/<paper_id>/{paper.json, files/, generation/}
word_addon/taskpane/     MS Word Office add-in
data/                    uploads/, exports/, charts/, logs/
tests/                   integration/, performance/, helpers/ (mock_ai.py), scripts/
```

### 2.2 Frontend `/frontend/src/`

```
main.ts                  Bootstrap: createApp(App) + Pinia + Router + globalErrorHandler
App.vue                  Root: <RouterView/> + global modal/toast
env.d.ts                 Type declarations env vite

api/
  index.ts               Axios client: baseURL=VITE_API_URL, withCredentials, CSRF interceptor
                         (baca cookie `csrf_access_token` → header `X-CSRF-TOKEN`)
  charts.ts              Wrapper API chart (getCharts, createChart, dll)

router/index.ts          7 route + guard: requiresAuth → redirect /login,
                         requiresAdmin → cek user.role === 'admin'

stores/                  Pinia composition-API stores (lihat §6)
  auth.ts                useAuthStore - user, login, register, googleLogin, logout
  paper.ts               usePaperStore - paper, sections, undo/redo, save, exportDocx
  paperJobs.ts           usePaperJobsStore - track AI jobs, polling status
  chat.ts                useChatStore - conversation, SSE message stream
  imageGen.ts            useImageGenStore - request image gen + polling
  literature.ts          useLiteratureStore - SLR jobs + literature items
  tools.ts               useToolsStore - paraphrase/summarize/translate state
  quota.ts               useQuotaStore - token quota
  theme.ts               useThemeStore - dark/light toggle
  ui.ts                  useUiStore - modal, toast, sidebar state

views/                   Halaman route-level (lihat §7)
  LandingPage.vue        Public homepage
  LoginPage.vue          Email/password + Google OAuth
  AuthCallbackPage.vue   OAuth callback handler
  DashboardPage.vue      List papers user
  PaperEditorPage.vue    Main editor (3-panel, 8 tab)
  FilesPage.vue          File global user
  AdminPage.vue          Admin panel

components/              36 komponen Vue (lihat §7.2)
composables/
  useKeyboardShortcuts.ts  Daftar shortcut (Ctrl+S save, Ctrl+Z undo, dll)
  useSanitize.ts           DOMPurify wrapper untuk render markdown chat
directives/autosize.ts   v-autosize untuk textarea
services/
  errorHandler.ts        Format error API
  globalErrorHandler.ts  Window-level error catch → log ke backend
utils/
  logger.ts              Wrapper console + post ke /api/logs/frontend
  errorMessages.ts       Map kode error → pesan ID
types/
  router.d.ts            Augment RouteMeta
  components.ts          Shared types untuk komponen
  slr.ts                 Type SLR/literature
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
| POST   | `/api/generate`       | `generate()` - 1 section, sync (limit 20/min). System prompt per section: title/abstract/introduction/methodology/results/conclusion/acknowledgment |
| POST   | `/api/generate-full`  | `generate_full()` - spawn thread `_run_generate_full_job` (limit 10/min) |
| GET    | `/api/job/<job_id>`   | `get_job_status()` - polling: pending/done/error               |

### 3.4 Paperfull Jobs — `tools/paperfull/jobs.py` (advanced async + SSE)
| Method | Path                                       | Fungsi                                   |
|--------|--------------------------------------------|------------------------------------------|
| POST   | `/api/papers/<paper_id>/generate`          | `enqueue_generate()` - alt entry generate|
| GET    | `/api/jobs/<job_id>`                       | `get_job()` - status                     |
| POST   | `/api/jobs/<job_id>/cancel`                | `cancel_job()` - set Redis cancel key    |
| GET    | `/api/papers/<paper_id>/active-jobs`       | `active_jobs()` - jobs aktif paper       |
| GET    | `/api/jobs/<job_id>/stream`                | `stream_job()` - **SSE** progress Redis  |
| GET    | `/api/papers/<paper_id>/ai-jobs/active`    | `ai_jobs_active()` - varian             |
| POST   | `/api/ai-jobs/<job_id>/cancel`             | `ai_jobs_cancel()`                       |
| POST   | `/api/ai-jobs/<job_id>/resume`             | `ai_jobs_resume()` - lanjut dari checkpoint |
| POST   | `/api/ai-jobs/<job_id>/retry-section`      | `ai_jobs_retry_section()` - retry 1 section |
| GET    | `/api/me/ai-jobs/recent`                   | `ai_jobs_recent()` - inbox notifikasi   |

### 3.5 Chat — `tools/chat/chat.py`
| Method | Path                                          | Fungsi                          |
|--------|-----------------------------------------------|---------------------------------|
| GET    | `/api/papers/<paper_id>/conversations`        | `list_paper_conversations()`    |
| POST   | `/api/papers/<paper_id>/conversations`        | `create_paper_conversation()`   |
| GET    | `/api/chat/conversations/<conv_id>`           | `get_conversation()` + messages |
| PATCH  | `/api/chat/conversations/<conv_id>`           | `rename_conversation()`         |
| DELETE | `/api/chat/conversations/<conv_id>`           | `delete_conversation()`         |
| GET    | `/api/papers/<paper_id>/memory`               | `list_memory()` (ProjectMemory) |
| DELETE | `/api/papers/<paper_id>/memory/<mem_id>`      | `delete_memory_entry()`         |
| POST   | `/api/chat/conversations/<conv_id>/messages`  | `send_message()` - **SSE stream** AI response + tool calls |

### 3.6 Files — `tools/File/files.py` (prefix `/api/papers`)
| Method | Path                                              | Fungsi                                          |
|--------|---------------------------------------------------|-------------------------------------------------|
| GET    | `/<paper_id>/files`                               | List PaperFile                                  |
| POST   | `/<paper_id>/files`                               | Upload (multipart, max 10MB/file)               |
| DELETE | `/<paper_id>/files/<file_id>`                     | Hapus                                           |
| GET    | `/<paper_id>/files/<file_id>/raw`                 | Download raw (signed URL)                       |
| GET    | `/<paper_id>/files/<file_id>/preview`             | Preview text (extracted)                        |

Plus `main.py`:
- `POST /api/upload-pdfs` - extract teks 5 PDF/DOCX (pool 20 worker, cap 5000 kata/file)
- `POST /api/upload-image` - upload image legacy

### 3.7 Images — `tools/image_generation/`
**images.py** (`paper_images` blueprint prefix `/api/papers`):
| Method | Path                                       | Fungsi                          |
|--------|--------------------------------------------|---------------------------------|
| POST   | `/<paper_id>/images`                       | Create image record (from URL)  |
| POST   | `/<paper_id>/images/upload`                | Upload file langsung            |
| GET    | `/<paper_id>/images`                       | List                            |
| DELETE | `/<paper_id>/images/<image_id>`            | Hapus                           |
| POST   | `/<paper_id>/sign`                         | Generate signed serving URL     |

**images.py** (`image_serve` blueprint prefix `/api/img`):
| GET    | `/<paper_id>/<filename>`                   | Serve image (HMAC-verified)     |

**image_jobs.py** (`image_jobs` blueprint prefix `/api/image-jobs`):
| POST   | `/`           | Create job (queue ke 4-worker pool) |
| GET    | `/`           | List job user                       |
| GET    | `/<job_id>`   | Status                              |
| POST   | `/<job_id>/cancel` | Cancel                         |

### 3.8 Admin — `tools/admin/admin.py` (prefix `/api/admin`, requires admin role)
| Method | Path                              | Fungsi                          |
|--------|-----------------------------------|---------------------------------|
| GET    | `/users`                          | List user                       |
| POST   | `/users/<user_id>/promote`        | Set role admin                  |
| PATCH  | `/users/<user_id>/quota`          | Update quota                    |
| POST   | `/users/<user_id>/reset-quota`    | Reset quota counter             |
| GET    | `/papers`                         | List semua paper                |
| GET    | `/usage`                          | ApiUsageLog query               |
| GET    | `/stats`                          | Statistik global                |

### 3.9 SLR / Literature — `tools/Literatur/slr_api.py`
| Method | Path                                                   | Fungsi                     |
|--------|--------------------------------------------------------|----------------------------|
| POST   | `/api/papers/<paper_id>/slr/jobs`                      | `create_slr_job()`         |
| GET    | `/api/papers/<paper_id>/slr/jobs`                      | `list_slr_jobs()`          |
| GET    | `/api/papers/<paper_id>/slr/jobs/wait`                 | `wait_slr_jobs()` (long-poll) |
| GET    | `/api/slr/jobs/<job_id>`                               | `get_slr_job()`            |
| DELETE | `/api/slr/jobs/<job_id>`                               | `cancel_slr_job()`         |
| GET    | `/api/papers/<paper_id>/literature`                    | `list_literature()`        |
| POST   | `/api/papers/<paper_id>/literature`                    | `create_literature()`      |
| PATCH  | `/api/papers/<paper_id>/literature/<item_id>`          | `update_literature()`      |
| DELETE | `/api/papers/<paper_id>/literature/<item_id>`          | `delete_literature()`      |
| POST   | `/api/papers/<paper_id>/literature/bulk-delete`        | `bulk_delete_literature()` |
| POST   | `/api/papers/<paper_id>/literature/bulk-patch`         | `bulk_patch_literature()`  |
| POST   | `/api/papers/<paper_id>/literature/from-files`         | `import_from_files()` (extract refs dari PDF) |
| POST   | `/api/papers/<paper_id>/slr`                           | `run_slr_legacy()` (sinkron lama) |

### 3.10 Lainnya
| Path                        | File                              | Fungsi                                   |
|-----------------------------|-----------------------------------|------------------------------------------|
| `GET /api/topics`           | `main.py`                         | List topic (cached 1h)                   |
| `GET /api/styles`           | `main.py`                         | List citation style (cached 1h)          |
| `GET /api/journals`         | `main.py`                         | List template Journal/*gen.py            |
| `GET /api/health`           | `utils/health/health.py`          | Health check                             |
| `GET /api/health/detailed`  | `utils/health/health.py`          | DB + Redis + worker status               |
| `GET /api/quota`            | `utils/quota/quota.py`            | Token quota user                         |
| `POST /api/tools/<tool_id>` | `utils/ai_tools/tools_api.py`     | Run AI tool (paraphrase/summarize/dll)   |
| `GET /api/tools/translate/config` | `utils/ai_tools/tools_api.py` | Available languages                    |
| `POST /api/logs/frontend`   | `utils/logging/logging_api.py`    | Receive frontend error log              |
| `GET /api/papers/<id>/charts` `POST /api/papers/<id>/charts` `PUT/DELETE /api/papers/<id>/charts/<chart_id>` `POST .../upload-data` | `tools/data/chart_api.py` | 6 route CRUD chart |
| `GET /api/docs`             | `main.py`                         | Swagger UI                               |
| `GET /api/openapi.yaml`     | `main.py`                         | OpenAPI spec                             |

---

## 4. ALUR FUNGSI KUNCI (call graph ringkas)

### 4.1 Generate Full Paper (single-shot, dipakai default)
```
POST /api/generate-full                                       [main.py:generate_full]
  ↓ _job_create(job_id, user_id, prompt)                       [utils/job_core.py]
  ↓ Thread(_run_generate_full_job)                             [main.py — daemon]
      ↓ _checkpoint("generating", 5) → publish_progress()      [tools/paperfull/jobs.py]
      ↓ generate_paper_json_single(judul, custom_prompt,...)   [tools/editor/single.py]
          ├─ _load_system_prompt(style, topic)                 (read tools/paperfull/prompt/*)
          ├─ _load_chat_history(conv_id)                       (ChatMessage DB)
          ├─ _load_literature(paper_id)                        (LiteratureItem DB)
          ├─ _load_attached_files(paper_id)                    (PaperFile preview text)
          ├─ _call_v_opus(messages) → _call_aiotomasi_with_fallback()  [editor/api_client.py]
          ├─ _parse_json_response(raw)                         (extract JSON dari markdown)
          └─ _normalize_paper_shape(raw) + _lift_subsections()
      ↓ _validate_paper_shape(paper_data)                      [single.py]
      ↓ save_paper_json_by_id(username, paper_id, data)        [utils/core/user_storage.py]
      ↓ Paper.data = paper_data; db.commit()                   (persistensi DB)
      ↓ _checkpoint("complete", 100) → _job_set_done()         [job_core.py]

GET /api/job/<job_id>     (polling tiap 2-3 detik dari paperJobs store)
```

### 4.2 Chunked Generation (legacy, masih ada)
```
generate_paper_json_chunked()              [tools/editor/chunked.py]
  ├─ _load_full_context(paper_id, custom_prompt)
  ├─ _generate_outline(...)                → 1 AI call (struktur paper)
  ├─ for section in outline:
  │     _generate_section(...)             → 1 AI call per section (checkpoint per section)
  ├─ _generate_references(...)             → 1 AI call (format references)
  └─ combine → return paper_data
```

### 4.3 Chat (SSE streaming)
```
POST /api/chat/conversations/<conv_id>/messages    [tools/chat/chat.py:send_message]
  ↓ load Conversation, ChatMessage history
  ↓ get_memory_context(paper_id, conv_id)          (ProjectMemory)
  ↓ load_system_prompt()
  ↓ stream AI response via SSE (_sse event/data)
  ↓ tool_calls? → utils/ai_tools/tools_api dispatch
  ↓ persist ChatMessage (user + assistant)
```

### 4.4 SLR Pipeline
```
POST /api/papers/<id>/slr/jobs              [slr_api.py:create_slr_job]
  ↓ SlrJob row (status=queued) + enqueue_slr_job()
  ↓ _pump_loop (worker.py) picks FIFO       [tools/Literatur/worker.py]
      ↓ _run_job(app, job_id)
          ↓ pipeline.run(query, sources, top_k, ...)   [pipeline.py]
              ├─ orchestrator.pick_sources_for_topic()
              ├─ fetchers/* (arxiv, crossref, dll) paralel
              ├─ scoring.py: relevance + citation + recency
              ├─ summarizer.py: AI summarize tiap paper
              └─ save() → SlrJob.result_json + LiteratureItem rows
```

### 4.5 Image Generation
```
POST /api/image-jobs                       [image_jobs.py]
  ↓ ImageGenJob row + submit_now(job_id)   [worker.py]
  ↓ _Dispatcher pick → _Worker (4 thread, 1 per Gemini account)
      ↓ CreateImageGemini scrape via Playwright
      ↓ compress.py kompres PNG
      ↓ save ke user/<u>/<paper>/images/
      ↓ update ImageGenJob.status=done + result_urls
```

---

## 5. DATABASE MODELS (`database/models.py`)

| Model           | Tabel                | Field utama                                                   |
|-----------------|----------------------|---------------------------------------------------------------|
| `User`          | users                | id, email, password_hash, name, role, google_id, token_quota, tokens_used, created_at |
| `Paper`         | papers               | id (uuid), user_id, title, data (JSONB), updated_at, operation_lock |
| `PaperImage`    | paper_images         | id, paper_id, filename, url, caption, created_at              |
| `PaperFile`     | paper_files          | id, paper_id, filename, mime, size, preview_text, sha256       |
| `ApiUsageLog`   | api_usage_logs       | id, user_id, endpoint, prompt_tokens, completion_tokens, ts   |
| `Conversation`  | conversations        | id (uuid), paper_id, user_id, title, mode, paused              |
| `ChatMessage`   | chat_messages        | id, conv_id, role (user/assistant), content, tool_calls JSONB |
| `ProjectMemory` | project_memory       | id, paper_id, conv_id (FK), key, value (memori long-term)     |
| `AiJob`         | ai_jobs              | id, user_id, paper_id, prompt, status, stage, progress, result JSONB, error, started_at, timeout |
| `LiteratureItem`| literature_items     | id, paper_id, title, authors, year, doi, abstract, url, summary, score |
| `SlrJob`        | slr_jobs             | id, paper_id, query, sources, status, stage, info JSONB, result_json |
| `ImageGenJob`   | image_gen_jobs       | id, user_id, paper_id, prompt, status, result_urls JSON, error |

Status enums umum: `pending|running|done|error|cancelled`.

---

## 6. PINIA STORES (`frontend/src/stores/`)

| Store                | File              | State/Actions utama                                                                       |
|----------------------|-------------------|-------------------------------------------------------------------------------------------|
| `useAuthStore`       | `auth.ts`         | `user`, `isLoggedIn`, `csrfToken`. Actions: `login`, `register`, `googleLogin`, `fetchMe`, `logout` |
| `usePaperStore`      | `paper.ts`        | `paper`, `loading`, `pendingCount`, `canUndo/canRedo`, history stack. Actions: `load`, `save`, `patch`, `undo/redo`, `exportDocx`, `addSection`, `deleteSection` |
| `usePaperJobsStore`  | `paperJobs.ts`    | Map `<paperId, job>`. Actions: `startGenerateFull`, `pollJob`, `cancelJob`, `resumeJob` |
| `useChatStore`       | `chat.ts`         | `conversations`, `activeConv`, `messages`. Actions: `loadConvs`, `createConv`, `sendMessage` (SSE EventSource), `deleteConv`, `renameConv` |
| `useImageGenStore`   | `imageGen.ts`     | `jobs`, `results`. Actions: `requestGen`, `pollJob`, `cancel`, `listResults`               |
| `useLiteratureStore` | `literature.ts`   | `slrJobs`, `literatureItems`. Actions: `startSLR`, `pollSLR`, `listItems`, `bulkPatch`, `bulkDelete` |
| `useToolsStore`      | `tools.ts`        | Tool results per tool_id. Actions: `runTool`                                              |
| `useQuotaStore`      | `quota.ts`        | `tokensUsed`, `tokensLimit`, `quotaExceeded`. Actions: `refresh`                          |
| `useThemeStore`      | `theme.ts`        | `mode`. Actions: `toggle`, `setMode` (persist localStorage)                               |
| `useUiStore`         | `ui.ts`           | `modals`, `toasts`, `sidebar`. Actions: `showToast`, `openModal`, `closeAllModals`         |

---

## 7. FRONTEND HALAMAN & KOMPONEN

### 7.1 Views (route-level)

#### `LandingPage.vue` — `/`
Hero public + CTA login. Tailwind statis, dark-mode aware. **State:** none.

#### `LoginPage.vue` — `/login`
Form email/password + tombol Google OAuth (redirect `/api/auth/google/login`).
**Store:** `useAuthStore`. **Tampilan:** centered card, validasi inline.

#### `AuthCallbackPage.vue` — `/auth/callback`
Handler redirect Google. Cek query params, panggil `fetchMe()`, redirect `/dashboard`.

#### `DashboardPage.vue` — `/dashboard` [requiresAuth]
Grid card list paper user.
- Komponen: `AppHeader`, card paper inline.
- Tombol "Paper Baru" → `POST /api/papers` → push `/editor/<id>`.
- Quota badge (token usage).
- **Store:** `usePaperStore` (list), `useQuotaStore`.

#### `PaperEditorPage.vue` — `/editor/:paperId` **[HALAMAN UTAMA]**
Layout 3-area:
1. **Header bar**: `AppHeader` + title editor + Save status + Undo/Redo + Export DOCX + tab switcher (Editor / Preview / Tools).
2. **Generation banner** (kondisional): progress AI job + Cancel.
3. **Main**: drag-and-drop sections (vuedraggable) + chat panel kanan.

**Tab di dalam editor** (komponen):
| Tab          | Komponen           | Fungsi                                                    |
|--------------|--------------------|-----------------------------------------------------------|
| Sections     | `SectionsTab.vue`  | Tree section/subsection + AI generate per section (AiButton) |
| Content      | `ContentList.vue`  | List rich-text item                                       |
| Files        | `FilesTab.vue`     | Upload PaperFile + preview                                |
| Literature   | `LiteratureTab.vue` + `LiteratureCard.vue` + `SLRResultsView.vue` | SLR + literature CRUD |
| Charts/Data  | `ChartsTab.vue` + `ChartPreviewCard.vue` + `DataTab.vue` | Chart generator       |
| Images       | `ImageTab.vue`     | Image gen + upload                                        |
| Journal      | `JournalTab.vue`   | Pilih template DOCX                                       |
| Preview      | `PreviewTab.vue`   | Render preview paper                                      |
| Paperfull    | `PaperfullTab.vue` | Full paper gen UI (prompt + topic + style)                |
| Metadata     | `MetadataTab.vue`  | Authors, affiliation, keywords                            |
| References   | `ReferencesTab.vue`| Edit references list                                      |
| Tools        | `ToolsTab.vue` + `ToolWorkspace.vue` + `ToolGauge.vue` | AI tools (paraphrase, summarize, dll) |
| Chat         | `ChatTab.vue` + `ChatMessage.vue` | Chat AI tentang paper                  |

**Komponen pendukung di editor:**
- `AiButton.vue` — trigger `POST /api/generate` per section
- `AiPromptBox.vue` — input prompt AI dengan auto-resize
- `ActionChips.vue` — quick-action chips di chat
- `ThinkingBlock.vue` — render AI thinking trace
- `ToolCallBlock.vue` — render tool call result
- `DiffBlock.vue` — render diff sebelum/sesudah edit
- `MultiQuestionCard.vue` — pertanyaan AI batch
- `RevisiProposalCard.vue` — usulan revisi AI
- `FileReviewCard.vue` — preview review file
- `PaperProgressBubble.vue` — progress bubble in-chat (job aktif)
- `StateView.vue` — render state JSON debug
- `AppDialog.vue` — modal generik
- `ShortcutsHelp.vue` — popup daftar shortcut
- `ErrorBoundary.vue` — wrap error per section
- `WordAddonInstallModal.vue` — install MS Word add-in

**Store yang dipakai:** `paper`, `chat`, `paperJobs`, `imageGen`, `literature`, `tools`, `ui`.
**Realtime:** EventSource ke `/api/jobs/<id>/stream` untuk progress; polling fallback.
**Autosave:** debounced PATCH `/api/papers/<id>`.

#### `FilesPage.vue` — File browser global user

#### `AdminPage.vue` — `/admin` [requiresAdmin]
Tabel user + quota override + statistics + ApiUsageLog. Hit `/api/admin/*`.

### 7.2 Style System
- **Tailwind config** (`tailwind.config.js`): custom palette (`cream-50/100/200/300/400`, `ink-50…900`, `ash-…`, `navy-500`, `anthracite-…`). Dark mode `class`-based via `useThemeStore`.
- Tidak pakai library UI komponen (semua custom).
- Markdown rendering: `markdown-it` + `highlight.js` + DOMPurify (via `useSanitize`).
- Drag-drop: `vuedraggable`.
- Icons: emoji + inline SVG (minimal lib eksternal).

---

## 8. CATATAN PENTING / GOTCHAS

| Area              | Detail                                                                                                     |
|-------------------|------------------------------------------------------------------------------------------------------------|
| **Auth**          | JWT di httpOnly cookie + CSRF double-submit. State-changing wajib `X-CSRF-TOKEN` header (Axios interceptor di `api/index.ts` baca cookie `csrf_access_token` auto). |
| **CORS**          | Hanya `localhost:8000` di dev. Produksi same-origin via nginx.                                             |
| **Rate Limit**    | Default 1000/min. `/api/generate` 20/min. `/api/generate-full` 10/min. `/api/auth/*` 10/min. Storage Redis (prod) atau memory:// (dev). |
| **Upload**        | Max 60MB per request (multipart). Per PDF 30MB. Per PaperFile 10MB.                                       |
| **DB Session**    | Postgres: `statement_timeout=30s`, `idle_in_transaction=5min`, `lock_timeout=5s`. SQLite (tests) skip pool. |
| **Workers**       | Image gen: 4 (1 per Gemini account). SLR: 10 (FIFO via `SlrJob` table). PDF extract: 20 (ThreadPool). AiJob sweeper: daemon thread 60s interval. |
| **Test mocking**  | Set env `AI_MOCKING=true` → `tests/helpers/mock_ai.py` intercept AI calls. Test setup di `conftest.py` pakai `sqlite:///:memory:`. |
| **User storage**  | FS: `backend/user/<username>/<paper_id>/`. Generation logs di `generation/<job_id>/{00_request,01_raw,02_normalized,02_parsed,02_validation}.json`. |
| **SSE**           | Channel: Redis pub/sub. Frontend pakai EventSource ke `/api/jobs/<id>/stream` & `/api/chat/.../messages`. |
| **Logging**       | Hourly rotating files di `backend/log/YYYY-MM-DD-HH/`. Global logger via `utils/core/global_logger.py`.  |
| **Sentry**        | Optional via env `GLITCHTIP_DSN`. Integrasi Flask + SQLAlchemy.                                           |
| **Monitoring**    | Prometheus metrics di `utils/monitoring/observability_v2.py` (rate limit, dll).                          |

---

## 9. ENV VARS PENTING (`.env`)

```
DATABASE_URL                postgresql://… (atau sqlite:/// untuk test)
JWT_SECRET_KEY              wajib non-default
SECRET_KEY                  wajib non-default
SIGNED_URL_SECRET           HMAC untuk signed image URL (fallback ke SECRET_KEY)
AIOTOMASI_APIKEY            API key upstream AI
AIOTOMASI_API               base URL upstream
MODELGENERATE               nama model (mis. VIOLA-GENERATE)
RATELIMIT_STORAGE_URI       redis://… (wajib produksi)
JWT_COOKIE_SECURE           true/false
SESSION_COOKIE_SECURE       true/false
SESSION_COOKIE_DOMAIN       optional, untuk subdomain
SESSION_COOKIE_SAMESITE     None / Lax
QUERY_LOGGING_ENABLED       1 untuk log semua SQL
GLITCHTIP_DSN               optional Sentry
SENTRY_RELEASE              tag rilis
FLASK_ENV                   production / development / testing
AI_MOCKING                  true (testing)
VITE_API_URL                base URL backend untuk frontend
```

---

## 10. QUICK INDEX — DI MANA NYARI?

| Cari…                                | Buka file                                                  |
|--------------------------------------|------------------------------------------------------------|
| Endpoint baru / route                | `backend/main.py` atau `backend/tools/*/` (blueprint)      |
| Add field model DB                   | `backend/database/models.py` + bikin migration alembic     |
| Logic generate paper                 | `backend/tools/editor/single.py` (default) atau `chunked.py` |
| Prompt template                      | `backend/tools/paperfull/prompt/{topic,style}/*.txt`       |
| Template DOCX baru                   | `backend/tools/Journal/<KODE>gen.py` (export `build_document`) |
| Tambah fetcher SLR                   | `backend/tools/Literatur/fetchers/<source>.py`             |
| Tambah AI tool                       | `backend/utils/ai_tools/tools_api.py` (run_tool dispatcher)|
| Halaman baru                         | `frontend/src/views/*.vue` + `router/index.ts`             |
| Komponen baru                        | `frontend/src/components/*.vue`                            |
| State baru                           | `frontend/src/stores/<name>.ts` (defineStore)              |
| Style/warna                          | `frontend/tailwind.config.js`                              |
| API client / interceptor             | `frontend/src/api/index.ts`                                |
| Error message i18n                   | `frontend/src/utils/errorMessages.ts`                      |
| Permission check (frontend)          | `frontend/src/router/index.ts` (beforeEach)                |
| Permission check (backend)           | `@jwt_required()` + cek role di handler / `tools/admin/`   |

---

_Last update: 2026-06-10. Update progresif sesuai investigasi baru._
