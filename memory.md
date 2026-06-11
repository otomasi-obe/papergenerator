# PaperGenerator — Memory / Peta Arsitektur

> **ATURAN WAJIB**: ketika baca file ini nanti setelah selesai kamu kerja tolong di update lagi sesuai apa yang kamu ubah meynesuaikan style dokumen ini..
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
  chat/chat.py           Blueprint simple_chat (7 route: CRUD conv, clear, SSE stream; no memory)
  chat/chatPrompt.txt    System prompt: paper editing via [APPLY_PAPER] tags
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
    slr_api.py           Blueprint slr_api (13 route - jobs, literature CRUD, bulk ops, pinned)
    orchestrator.py      Pilih sumber & jalankan paralel + `expand_query()` ID→EN
    pipeline.py          `run()` end-to-end: fetch → score → summarize → save
    worker.py            `start_slr_workers(app)` - 10 worker pool, FIFO via DB
    scoring.py           ScoredPaper (SBERT 0.50 + TF-IDF 0.10 + keyword_density 0.07 + author 0.05 + citation 0.10 + recency 0.08 + venue 0.10)
    summarizer.py        AI summarize per paper
    unpaywall.py         Fetch OA PDF
    http_client.py       Retry-able HTTP + `fetch_post_json()` for POST requests
    text_cleaner.py      Normalisasi teks
    paper.py             Dataclass `Paper`
    cli.py, run_slr.py   CLI standalone
    fetchers/            16 sources: arxiv, core, crossref, dblp, dimensions,
                         europepmc, ieee, lens, openalex, pubmed,
                         sciencedirect, scopus, semantic_scholar, sinta,
                         springer, taylor_francis
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
| POST   | `/api/chat/conversations/<conv_id>/clear`     | `clear_conversation()` — hapus semua pesan, keep conv |
| POST   | `/api/chat/conversations/<conv_id>/messages`  | `send_message()` - **SSE stream** AI response + [APPLY_PAPER] parsing |

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
| GET    | `/api/papers/<paper_id>/literature/pinned`             | `get_pinned_literature()` — formatted pinned items for chat/paperfull |
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
  ↓ get_paper_context(paper_id)                     (Paper.data JSON summary)
  ↓ load_system_prompt()
  ↓ stream AI response via SSE (_sse event/data)
  ↓ parse [APPLY_PAPER] tags → _apply_paper_operations() → update Paper.data
  ↓ SSE event 'paper_applied' → frontend reload paper
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
| `useChatStore`       | `chat.ts`         | `conversations`, `activeConv`, `messages`. Actions: `loadConvs`, `createConv`, `sendMessage` (SSE), `deleteConv`, `renameConv`, `clearCurrentChat` |
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

_Last update: 2026-06-11. Update progresif sesuai investigasi baru._

## 10. FRONTEND DARK MODE & UI POLISH (2026-06-11)

Seluruh frontend telah diaudit dan difiks untuk dark mode contrast + konsistensi visual.

### Color Token Map (Dark Mode)

| Light | Dark | Usage |
|-------|------|-------|
| `text-ink-900` | `dark:text-anthracite-50` | Primary text / headings |
| `text-ink-700` | `dark:text-anthracite-100` | Secondary text |
| `text-ink-600` | `dark:text-anthracite-200` | Metadata |
| `text-ink-500` | `dark:text-anthracite-200` | Muted text, labels |
| `text-ink-400` | `dark:text-anthracite-300` | Placeholder/subtle |
| `text-ink-300` | `dark:text-anthracite-300` | Drag handles |
| `text-blue-600` | `dark:text-blue-400` | Links |
| `text-red-400` | `dark:text-red-300` | Delete/remove buttons |
| `text-red-300` | `dark:text-red-400` | Subtle error |
| `hover:text-red-600` | `dark:hover:text-red-200` | Red hover states |
| `bg-white` | `dark:bg-anthracite-700` | Card bg |
| `bg-cream-50` | `dark:bg-ash-850` | App bg |
| `border-cream-300` | `dark:border-ash-600` | Borders |
| `border-cream-400` | `dark:border-ash-500` | Strong borders |

### Files Changed

- **PaperEditorPage.vue** — move buttons, reference numbers, drag handles, section delete → dark variants + better card shadows + focus rings
- **LiteratureTab.vue** — table row numbers, DOI links, empty states, edit button → dark variants
- **SectionsTab.vue** — delete buttons → dark red hover
- **PreviewTab.vue** — status text, resolved changes → dark variants
- **ContentList.vue** — red delete/lepas buttons → dark variants
- **DataTab.vue** — delete text → dark variants
- **FilesTab.vue** — lepas gambar button → dark variants
- **ReferencesTab.vue** — delete button → dark variants
- **ChartsTab.vue** — delete button → dark variants
- **LoginPage.vue** — error message → dark red
- **DashboardPage.vue** — border color fix
- **style.css** — `.paper-preview` dark bg fix, `.card` improved shadows + hover, input focus rings improved, transitions added

### Key Fix: paper-preview bg putih di dark mode

CSS `.paper-preview` hardcoded `background: #ffffff`. Sekarang `.dark .paper-preview` punya `background: #0b1f3e` (ash-850).

### Key Fix: LoginPage & LandingPage forced dark background

LoginPage dan LandingPage pakai `bg-gradient-to-br from-navy-900` (always dark) tapi button masih pakai `dark:` variants. User di light mode system akan lihat button low contrast. **Fix:** hapus semua `dark:bg-*` dan `dark:text-*` dari button di halaman ini, forced light button (bg-cream-50/text-navy-800) untuk kontras tinggi di background gelap.

- LoginPage.vue: "Sign In" button + "Continue with Google" → `bg-cream-50 text-navy-800` (hapus dark variants)
- LandingPage.vue: "Sign In" + "Get Started" button → `bg-cream-50 text-navy-800` (hapus dark variants)

### Global Polish

- Card shadows enhanced dengan hover effect
- Input focus rings pakai accent color (`#238f7f` light / `#4eb2a3` dark)
- Placeholder opacity dikurangi (0.6→0.55)
- Transitions added ke input dan card elements
- LiteratureTab.vue: placeholder-ivory-500 → tambah `dark:placeholder-anthracite-200` (2 tempat)

## 11. JWT SESSION COOKIE FIX (2026-06-11)

User harus login ulang setiap tutup browser padahal JWT refresh token valid 7 hari.

**Root cause:** JWT refresh token expires di server = 7 hari, tapi cookie-nya session cookie (hilang saat browser ditutup) karena `JWT_SESSION_COOKIE` default `True`.

**Fix:** tambah `app.config["JWT_SESSION_COOKIE"] = False` di:
- `backend/main.py` line 138
- `backend/utils/config/settings.py` line 75

Sekarang JWT cookies persist sampai expires (7 hari). User hanya perlu login ulang setelah 7 hari atau kalau manual logout.

**Session timeline:**
- Access token: 1 jam (auto-refresh via `/api/auth/refresh`)
- Refresh token: 7 hari (cookie persist di browser)
- Frontend sudah implement auto-refresh di `frontend/src/api/index.ts`

## 12. ROUTING & BUTTON CONTRAST FIX (2026-06-11)

**Google button contrast issue:**
- LoginPage.vue: `bg-white text-ink-900` → `bg-white text-navy-900 hover:bg-cream-100`
- Sebelumnya text-ink-900 di-override oleh parent `text-cream-50`, sekarang text-navy-900 lebih spesifik

**Routing fixes:**
- `/` (root) → landing page (bukan dashboard)
- 404 catch-all → redirect ke `/` (landing) bukan `/dashboard`
- Logout → redirect ke `/` (landing page) via `window.location.href = '/'`
- Login page → sudah ada link "← Back to home" ke landing page

**Files changed:**
- `frontend/src/views/LoginPage.vue` — Google button text-navy-900 + hover:bg-cream-100
- `frontend/src/router/index.ts` — catch-all redirect: `/dashboard` → `/`
- `frontend/src/stores/auth.ts` — logout redirect ke `/`

## 13. CHAT SYSTEM IMPROVEMENTS — FULL PAPER CONTEXT AND THINKING STREAM (2026-06-11)

### Problem
- System prompt hanya kirim summary truncated (abstract 2000 char, section 500 char, 10 ref max)
- AI tidak punya konteks lengkap paper → tidak bisa edit dengan akurat via [APPLY_PAPER]
- Thinking/reasoning dari AI tidak disimpan ke filesystem (hanya completion)
- Parsing [APPLY_PAPER] dan apply operations tersebar di chat.py

### Solution
**1. Full Paper JSON di System Prompt**
- `get_paper_context()` rewrite: dump **full JSON** dari `Paper.data` (cap 30K char safety)
- System prompt sekarang: `chatPrompt.txt` + ```json {full_paper_json} ```
- Setiap user kirim pesan → JSON terbaru dari DB otomatis dikirim ke AI

**2. Thinking Stream and Filesystem Save**
- Stream loop collect `thinking_content` dari delta["thinking"]
- SSE event "thinking" dikirim ke frontend (bisa di-expand/collapse nanti)
- Thinking disave ke filesystem recv.json sebagai field "thinking"

**3. Modular Tools (`tools/chat/tools.py`)**
Fungsi baru:
- `parse_completion(text)` → extract [APPLY_PAPER] blocks + return cleaned text
- `apply_operations(paper_id, ops)` → apply ke Paper.data + return results/errors
- `save_thinking_to_fs()` → save thinking ke filesystem
- `append_completion_to_recv()` → save completion + operations ke recv.json

**4. Auto-reload System Prompt**
- `load_system_prompt()` sekarang cek mtime `chatPrompt.txt`
- Kalau file berubah → auto-reload tanpa restart backend

### Files Changed
- `backend/tools/chat/chat.py` — integrate tools.py, collect thinking, use full JSON context
- `backend/tools/chat/tools.py` — NEW: parsing + apply + filesystem helpers
- `backend/tools/chat/chatPrompt.txt` — update deskripsi Paper Context = full JSON

### Flow Sekarang
```
User message → get_paper_context() → Paper.query.get() → json.dumps(full_data, cap 30K)
→ System prompt: chatPrompt.txt + ```json {paper} ```
→ AI stream: delta.content (text) + delta.thinking (reasoning)
→ Collect thinking → stream "thinking" event → save ke recv.json
→ Parse [APPLY_PAPER] via tools.parse_completion()
→ Apply via tools.apply_operations() → update Paper.data + DB commit
→ SSE "paper_applied" dengan results/errors
→ Save cleaned completion + thinking ke filesystem
```

### Frontend TODO (belum dikerjakan)
- Tambah UI collapse/expand untuk thinking di ChatMessage.vue
- Parse SSE event "thinking" dan tampilkan sebagai collapsible block
- Icon/button "Show reasoning" yang toggle visibility

## 14. SLR SYSTEM OVERHAUL + TAGGING INTEGRATION (2026-06-12)

### Fixes
1. **Column `pdf_url` missing** — model `LiteratureItem` punya kolom `pdf_url` tapi DB belum di-migrate.
   - Fix: `ALTER TABLE literature_items ADD COLUMN pdf_url TEXT`
   - Error: `psycopg2.errors.UndefinedColumn column literature_items.pdf_url does not exist`

2. **Nginx paperfull.conf missing dari sites-enabled** — symlink hilang → `paperfull.app refused to connect`.
   - Fix: `sudo ln -sf /etc/nginx/sites-available/paperfull.conf /etc/nginx/sites-enabled/` + reload nginx

3. **SLR 500: get_primary_generate_model not defined** — `slr_api.py` pakai fungsi tanpa import.
   - Fix: tambah `from utils.ai_tools.model_config import get_primary_generate_model` di top of file
   - Error: `NameError: name 'get_primary_generate_model' is not defined` at line 248

### SLR Improvements

**1. 3 Fetcher baru (total 16 sumber):**
- `core.py` — CORE API (https://api.core.ac.uk/v3), spesialis open access + PDF URLs. Requires `CORE_API_KEY`.
- `lens.py` — Lens.org API (https://api.lens.org/scholarly), metadata lengkap + citation. Requires `LENS_API_KEY`.
- `dimensions.py` — Dimensions API (https://app.dimensions.ai/api/dsl/v2), citation data + broad coverage. Requires `DIMENSIONS_API_KEY`.
- Semua return empty jika API key tidak diset (graceful degradation).

**2. Query Expansion (`orchestrator.py:expand_query()`):**
- Auto-translate Indonesian terms → English equivalents (21 terms: kecerdasan buatan→artificial intelligence, pembelajaran mesin→machine learning, dll)
- Academic synonyms (20 pairs: diagnosis→diagnostic, therapy→treatment, dll)
- Handles boolean operators (AND, OR) — wraps expansion correctly
- Dipanggil otomatis di `fetch_titles()` sebelum query dikirim ke fetchers

**3. Enhanced Topic Detection (`orchestrator.py`):**
- 5 topic baru: economics, social, education, law, agriculture
- Expanded keywords per existing topic (10-20 additional keywords each)
- Partial-match fallback untuk keywords ≥5 chars

**4. Improved Scoring (`scoring.py`):**
- SBERT weight naik: 0.45 → 0.50 (signal paling penting)
- 2 signal baru:
  - `keyword_density` (0.07 weight) — bonus kalau title mengandung exact query terms
  - `author_prestige` (0.05 weight) — team-size heuristic (multi-author = lebih prestisius)
- Relevance threshold naik: 0.40 → 0.45 (presisi lebih tinggi)
- Total weights: sbert 0.50 + tfidf 0.10 + keyword 0.07 + author 0.05 + citation 0.10 + recency 0.08 + venue 0.10 = 1.00

**5. SLR Tagging ke Chat & Paperfull:**
- **`@slr` tag di chat**: user ketik `@slr` di pesan → pinned literature items otomatis di-inject ke system prompt sebagai context, `@slr` di-strip dari pesan.
- **Paperfull auto-inject**: pinned literature selalu di-inject ke system prompt saat generate full paper (di `single.py`), tidak perlu tag.
- **API endpoint baru**: `GET /api/papers/<id>/literature/pinned` — preview apa yang akan dikirim ke AI.
- **Helper function**: `get_pinned_literature(paper_id, user_id, max_items=10)` di `slr_api.py` — format pinned items sebagai blok teks siap-inject.

### Files Changed
- `backend/tools/Literatur/fetchers/core.py` — NEW
- `backend/tools/Literatur/fetchers/lens.py` — NEW
- `backend/tools/Literatur/fetchers/dimensions.py` — NEW
- `backend/tools/Literatur/fetchers/__init__.py` — register 3 fetcher baru + topic mappings
- `backend/tools/Literatur/orchestrator.py` — expand_query(), expanded topics, partial-match detection
- `backend/tools/Literatur/scoring.py` — keyword_density, author_prestige, weight rebalance
- `backend/tools/Literatur/http_client.py` — fetch_post_json() helper
- `backend/tools/Literatur/slr_api.py` — get_pinned_literature(), GET /literature/pinned endpoint
- `backend/tools/chat/chat.py` — @slr tag detection + pinned literature injection
- `backend/tools/editor/single.py` — auto-inject pinned literature di full paper generation

### SLR Test Result (deep learning for medical image classification)
```
Total unique: 30 | Scored: 30 | Must read: 5 | Relevant: 22
Top 5 scores: 0.583–0.649
All top 5 relevan langsung ke query (medical image + deep learning)
PDF URLs populated via open_access data
```

## 15. FILE UPLOAD: ONLY EXTRACTED TEXT PERSISTED (2026-06-12)

**Problem:** PDF/DOCX/Excel/CSV yang di-upload disimpan sebagai raw binary file, padahal hanya text-nya yang dibutuhkan. Memboroskan storage.

**Fix:** Setelah upload, extract text → delete raw binary → simpan hanya text di DB (`extracted_text` column) dan user storage (`.txt` file).

**Changes:**
- `files.py:upload_paper_files()` — remove `save_uploaded_file()` call (no raw save to user storage)
- After extraction + DB commit → delete raw file from disk and S3
- `file_path` set to `""` (empty string, raw not stored)
- `serve_paper_file()` — now serves extracted text as `text/plain` instead of raw binary
- `delete_paper_file()` — check `filepath.is_file()` before unlink (handle empty path)
- Removed unused `send_file` import

**Files changed:**
- `backend/tools/File/files.py` — upload, serve, delete logic

**Behavior:**
- Upload: extract text → delete raw → DB only has `extracted_text`
- Download `/raw`: serves extracted text as `.txt` attachment
- User storage: only `.txt` files saved (via `save_file_as_txt`)
- Status.json: still records the file reference for PaperfullTab

## 17. IMAGE GENERATION TEST & UI REDESIGN (2026-06-12)

**Image Generation Test:**
- ✓ account1.png: 56 KB (compressed)
- ✓ account2.png: 60 KB (compressed)
- ✓ account3.png: 909 KB (compressed, under 1MB limit)
- ✗ account4.png: FAILED — "Memulai" overlay dialog blocking composer box

**Test location:** `/home/sirobo/papergenerator/backend/tools/image_generation/test/`

**Account4 fix:** Tambah `_dismiss_gemini_overlays()` di `_send_prompt()` — dismiss dialog "Memulai" (cdk-overlay Angular Material) via JS sebelum klik composer box. Account4 sekarang berhasil generate (105 KB, 44.6s).

**UI Redesign:**

1. **FilesTab.vue** — Removed Dokumen/Figures split tabs
   - Files tab now focused: left = file list, right = markdown preview
   - Removed sub-tab toggle (📄 Dokumen / 🖼 Figures & Images)
   - Fixed `/raw` endpoint: changed `Content-Disposition` from `attachment` to `inline` so browser displays text instead of downloading
   - Added PPTX/PPT support to ALLOWED_FILE_EXTS and mime_map

2. **ImageTab.vue** — Merged generate + upload + manage
   - Generate section at top (textarea + button)
   - Left: image list with editable names (click to rename)
   - Right: image preview (large)
   - Upload button at top right
   - Refresh button
   - Delete confirmation dialog
   - Layout mirrors FilesTab pattern (left list, right preview)

**Files changed:**
- `frontend/src/components/FilesTab.vue` — removed sub-tabs, simplified
- `frontend/src/components/ImageTab.vue` — complete rewrite, merged functionality
- `backend/tools/File/files.py` — `/raw` endpoint inline disposition, PPTX support

**Backend:** healthy, PM2 restarted. Frontend: built successfully.

_Last update: 2026-06-12. Update progresif sesuai investigasi baru._
