# Backend — PaperFull API Server

> Flask + SQLAlchemy + PostgreSQL — REST API untuk AI-powered academic paper generation.

---

## 1. Struktur Folder

```
backend/
├── app.py                        # Main Flask app (~1430 lines) — config, endpoints, job store
├── requirements.txt              # Python dependencies (31 packages)
├── requirements-dev.txt          # Dev dependencies
├── gunicorn.conf.py              # Production server config (4 workers × 8 threads)
├── conftest.py                   # PyTest fixtures & test config
├── alembic.ini                   # Alembic migration config
├── openapi.yaml                  # OpenAPI 3.1 spec (~60 KB / 15K+ lines)
├── pyproject.toml                # Python project metadata
├── pytest.ini                    # PyTest configuration
├── mypy.ini                      # MyPy type checking config
├── start.sh                      # Startup script
├── run_tests.sh                  # Test runner script
├── create_user.py                # CLI user creation utility
├── reset_password.py             # CLI password reset utility
├── searchPaper.py                # Multi-source academic search (~1191 lines)
├──
├── api/                          # Flask Blueprints (14 blueprints)
│   ├── __init__.py
│   ├── auth_bp.py                # Authentication: email/password, Google OAuth, JWT (~437 lines)
│   ├── admin_bp.py               # Admin: users, papers, usage stats (~242 lines)
│   ├── chat_bp.py                # Chat: multi-chat, SSE streaming, tools (~1248 lines)
│   ├── papers_bp.py              # Paper CRUD: list, create, update, delete (~294 lines)
│   ├── files_bp.py               # File management: upload, preview, serve (~537 lines)
│   ├── jobs_bp.py                # Job management: RQ, SSE progress, cancel/resume (~572 lines)
│   ├── charts_bp.py              # Chart generation: matplotlib PNG (~415 lines)
│   ├── images_bp.py              # Image management: upload, signed URLs (~328 lines)
│   ├── image_jobs_bp.py          # Image generation jobs: Gemini pool (~156 lines)
│   ├── slr_bp.py                 # SLR + Literature CRUD (~942 lines)
│   ├── quota_bp.py               # Token quota tracking (~105 lines)
│   ├── health_bp.py              # Health checks: liveness + readiness (~125 lines)
│   ├── workflow_bp.py            # Workflow onboarding questions (~52 lines)
│   ├── tools_bp.py               # Writing tools: 8 AI tools via SSE (~230 lines)
│   ├── logging_bp.py             # Frontend log ingestion (~76 lines)
│   └── data/                     # Static data files
│
├── database/                     # Database layer
│   ├── __init__.py
│   ├── models.py                 # SQLAlchemy models (~541 lines)
│   └── alembic/                  # Migration scripts
│       ├── env.py
│       └── versions/             # 8 migration files
│
├── paper_generation/             # Paper generation engine
│   ├── __init__.py
│   ├── single.py                 # Single-shot generation (~679 lines)
│   ├── chunked.py                # Chunked generation: 7-chunk pipeline (~1111 lines)
│   ├── api_client.py             # AI API client: SSE streaming + fallback (~140 lines)
│   ├── utils.py                  # Shared helpers: paths, HMAC tokens (~83 lines)
│   ├── extract_pdfs.py           # PDF text extraction: PyMuPDF (~519 lines)
│   ├── quality_validator.py      # Paper quality checks (~344 lines)
│   ├── section_generator.py      # Individual section generation (~242 lines)
│   ├── workflow_integration.py   # Workflow context injection (~235 lines)
│   └── test_improvements.py      # Test improvements
│
├── chat/                         # Chat system
│   ├── __init__.py
│   ├── tools.py                  # Tool executor: 30+ tools (~104K / ~3000+ lines)
│   ├── mode_prompts.py           # Mode system: 8 modes (~364 lines)
│   ├── auto_memory.py            # Automatic fact extraction (~449 lines)
│   └── data/                     # Chat data files
│
├── core/                         # Core utilities
│   ├── __init__.py
│   ├── errors.py                 # Error handling system: codes, categories (~335 lines)
│   ├── cache.py                  # In-memory TTL cache (~63 lines)
│   ├── env_loader.py             # Safe .env loading (~60 lines)
│   ├── retry_helper.py           # Retry with exponential backoff (~112 lines)
│   ├── log_helper.py             # Context-aware logging (~147 lines)
│   ├── storage_helper.py         # File path resolution (~272 lines)
│   ├── s3_storage.py             # S3-compatible storage (MinIO/AWS) (~250 lines)
│   └── chart_generator.py        # Matplotlib chart generation (~261 lines)
│
├── workers/                      # Background workers
│   ├── __init__.py
│   ├── slr_worker.py             # SLR worker pool: 10 workers (~527 lines)
│   ├── image_worker.py           # Image generation: 4 Gemini accounts (~405 lines)
│   └── worker.sh                 # Worker startup script
│
├── monitoring/                   # Observability
│   ├── __init__.py
│   ├── observability.py          # Legacy observability (~203 lines)
│   └── observability_v2.py       # Prometheus metrics + JSON logging (~380 lines)
│
├── middleware/                   # Request middleware
│   ├── __init__.py
│   ├── validation.py             # JSONSchema request validation (~121 lines)
│   └── error_handler.py          # Error formatting middleware (~80 lines)
│
├── schemas/                      # JSONSchema definitions
│   ├── __init__.py
│   ├── papers_schemas.py         # Paper create/update schemas
│   ├── chat_schemas.py           # Chat request schemas
│   └── common_schemas.py         # Common type schemas
│
├── config/                       # Configuration
│   ├── __init__.py
│   ├── settings.py               # App settings (~150 lines)
│   ├── security.py               # Security headers config (~100 lines)
│   └── extensions.py             # Extension initialization (~130 lines)
│
├── slr/                          # SLR pipeline
│   ├── __init__.py
│   ├── pipeline.py               # SLR pipeline orchestration (~350 lines)
│   ├── orchestrator.py           # Multi-source orchestration (~270 lines)
│   ├── http_client.py            # HTTP client with SSRF protection (~100 lines)
│   ├── paper.py                  # Paper data model (~30 lines)
│   ├── scoring.py                # Result scoring (~230 lines)
│   ├── summarizer.py             # AI summarization (~370 lines)
│   ├── text_cleaner.py           # Text cleaning (~55 lines)
│   ├── unpaywall.py              # Unpaywall integration (~120 lines)
│   ├── cli.py                    # CLI runner (~100 lines)
│   ├── run_slr.py                # Standalone runner (~120 lines)
│   ├── fetchers/                 # Source fetchers (19+ sources)
│   │   ├── __init__.py
│   │   ├── openalex.py
│   │   ├── crossref.py
│   │   ├── arxiv.py
│   │   ├── semantic_scholar.py
│   │   ├── pubmed.py
│   │   ├── europepmc.py
│   │   ├── doaj.py
│   │   ├── dblp.py
│   │   ├── openaire.py
│   │   ├── hal.py
│   │   ├── plos.py
│   │   ├── biorxiv.py
│   │   ├── zenodo.py
│   │   ├── datacite.py
│   │   ├── osf.py
│   │   ├── huggingface.py
│   │   ├── inspirehep.py
│   │   ├── eric.py
│   │   └── (keyed: core, lens, nasa_ads, springer, unpaywall)
│   └── results/                  # Result processing
│
├── workflows/                    # Workflow questionnaire system
│   ├── __init__.py
│   ├── engine.py                 # 9-phase questionnaire engine (~1355 lines)
│   ├── tool.py                   # Workflow tool integration (~560 lines)
│   ├── riset/                    # Research domain data
│   └── terminal/                 # Terminal rendering
│
├── image_generation/             # Image generation (Gemini browser automation)
│   ├── __init__.py
│   ├── open_gemini.py            # Playwright-based Gemini automation (~1124 lines)
│   ├── GeminiCookies.py          # Google account login + cookie scraping (~416 lines)
│   ├── CreateImageGemini.py      # Image generation pool: 4 accounts (~663 lines)
│   ├── compress.py               # Image compression to <1MB
│   ├── account1/                 # Chrome profile for Gemini account 1
│   ├── account2/                 # Chrome profile for Gemini account 2
│   ├── account3/                 # Chrome profile for Gemini account 3
│   ├── account4/                 # Chrome profile for Gemini account 4
│   └── *.json                    # Cookie files
│
├── tasks/                        # RQ tasks
│   ├── __init__.py
│   └── generate_paper_task.py    # Paper generation RQ task (~280 lines)
│
├── templates/                    # DOCX templates
│   ├── __init__.py
│   ├── _docx_base.py             # Base DOCX builder
│   ├── template_registry.py      # Template registry
│   ├── template_api.py           # Template API
│   ├── APAgen.py                 # APA format
│   ├── IEEEgen.py                # IEEE format
│   ├── Springergen.py            # Springer format
│   ├── JRCgen.py, JAMRISgen.py   # Journal templates
│   ├── IJITEEgen.py, ELKOLINDgen.py
│   ├── CCJgen.py, AMORIgen.py
│   ├── JTMMgen.py, JTRANSIENTgen.py
│   ├── (20+ more *gen.py files)  # Journal-specific generators
│   └── *.docx                    # DOCX template files
│
├── prompt/                       # AI prompts
│   ├── prompt.txt                # Main generation prompt (~56K)
│   ├── prompt_section_only.txt   # Section-only prompt
│   ├── humanize.txt              # Humanize instructions (~37K)
│   ├── humanize_prose_only.txt   # Prose-only humanize
│   ├── tes.py, tes.txt           # Test prompts
│   └── style/                    # Style guides
│
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── helpers/                  # Test helpers
│   │   ├── __init__.py
│   │   └── mock_ai.py            # Mock AI responses
│   ├── performance/              # Performance tests
│   │   ├── test_performance_infrastructure.py
│   │   ├── run_performance_tests.py
│   │   ├── mock_server.py
│   │   └── simple_mock_server.py
│   ├── test_*.py                 # 25+ test files
│   └── playwright_mcp_runner.py  # Playwright MCP test runner
│
├── data/                         # Runtime data
│   ├── uploads/                  # Uploaded files
│   ├── exports/                  # DOCX exports
│   ├── logs/                     # Application logs
│   └── <username>/<paper_id>/    # Per-user per-paper data
│       ├── generation/<job_id>/  # Generation logs
│       ├── images/               # Paper images
│       ├── files/                # Attached files
│       └── docx/                 # Generated DOCX
│
├── infra/                        # Infrastructure configs
├── auth/                         # Auth utilities
├── routes/                       # Route utilities
├── exports/                      # Export artifacts
├── output/                       # Output artifacts
├── .venv/                        # Python virtual environment
└── __pycache__/                  # Python cache
```

---

## 2. Tech Stack

| Layer          | Technology                                              |
|----------------|--------------------------------------------------------|
| Framework      | Flask 3.1                                               |
| Database       | PostgreSQL + SQLAlchemy 3.1 + Alembic 1.13            |
| Auth           | Flask-JWT-Extended 4.6 + Google OAuth (Authlib 1.3)   |
| Cache/Queue    | Redis 5.0 + RQ 1.16                                    |
| HTTP Client    | Requests 2.31                                           |
| AI API         | AIOTOMASI (VIOLA-GENERATE, VIOLA-CHAT)                 |
| Search         | 19 free + 5 keyed academic sources                     |
| Image Gen      | Playwright 1.49 + Gemini browser automation            |
| Charts         | Matplotlib 3.10 + NumPy 1.26                           |
| DOCX           | python-docx 1.1.2                                       |
| PDF            | PyMuPDF 1.24.5                                          |
| Monitoring     | Prometheus Client + Sentry/GlitchTip                   |
| Rate Limiting  | Flask-Limiter 3.5                                       |
| Server         | Gunicorn 23 (4 workers × 8 threads)                    |
| Testing        | PyTest + Schemathesis 3.36 (API contract)              |
| Validation     | JSONSchema 4.22                                         |

---

## 3. Arsitektur

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NGINX / REVERSE PROXY                         │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────┐
│                          GUNICORN (4 workers × 8 threads)                  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        FLASK APP (app.py)                             │  │
│  │                                                                       │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────────┐  │  │
│  │  │  Blueprints  │  │  Middleware   │  │  Extensions                  │  │  │
│  │  │  (14 total)  │  │  - CORS      │  │  - SQLAlchemy               │  │  │
│  │  │  - auth      │  │  - JWT       │  │  - JWTManager               │  │  │
│  │  │  - chat      │  │  - RateLimit│  │  - Limiter                   │  │  │
│  │  │  - papers    │  │  - Security │  │  - OAuth                     │  │  │
│  │  │  - files     │  │    Headers  │  │  - Sentry                    │  │  │
│  │  │  - jobs      │  │  - ProxyFix │  │  - Observability             │  │  │
│  │  │  - charts    │  │  - Validation│  │  - Alembic                   │  │  │
│  │  │  - images    │  └──────────────┘  └─────────────────────────────┘  │  │
│  │  │  - slr       │                                                     │  │
│  │  │  - tools     │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  - admin     │  │              CORE MODULES                     │  │  │
│  │  │  - quota     │  │  - errors.py (error codes + categories)      │  │  │
│  │  │  - health    │  │  - cache.py (TTL cache)                      │  │  │
│  │  │  - workflow  │  │  - storage_helper.py (file paths)            │  │  │
│  │  │  - logging   │  │  - s3_storage.py (S3/MinIO)                  │  │  │
│  │  └──────┬──────┘  │  - chart_generator.py (matplotlib)           │  │  │
│  │         │          │  - retry_helper.py (exponential backoff)     │  │  │
│  │         │          │  - log_helper.py (context logging)           │  │  │
│  │         │          └──────────────────────────────────────────────┘  │  │
│  │         │                                                            │  │
│  │         ▼                                                            │  │
│  │  ┌──────────────────────────────────────────────────────────────┐    │  │
│  │  │                    SERVICE LAYER                              │    │  │
│  │  │                                                               │    │  │
│  │  │  ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐ │    │  │
│  │  │  │ paper_generation │  │  chat/        │  │  slr/           │ │    │  │
│  │  │  │ - single.py      │  │  - tools.py   │  │  - pipeline.py  │ │    │  │
│  │  │  │ - chunked.py     │  │  - mode_      │  │  - orchestrator │ │    │  │
│  │  │  │ - api_client.py  │  │    prompts.py │  │  - fetchers/    │ │    │  │
│  │  │  │ - extract_pdfs.py│  │  - auto_      │  │  - scoring.py   │ │    │  │
│  │  │  │ - quality_       │  │    memory.py  │  │  - summarizer   │ │    │  │
│  │  │  │   validator.py   │  │              │  │  - 19+ sources  │ │    │  │
│  │  │  │ - section_       │  │              │  │                 │ │    │  │
│  │  │  │   generator.py   │  │              │  │                 │ │    │  │
│  │  │  └─────────────────┘  └──────────────┘  └─────────────────┘ │    │  │
│  │  │                                                               │    │  │
│  │  │  ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐ │    │  │
│  │  │  │ image_generation │  │  workflows/   │  │  templates/     │ │    │  │
│  │  │  │ - open_gemini.py │  │  - engine.py  │  │  - _docx_base   │ │    │  │
│  │  │  │ - CreateImage    │  │  - tool.py    │  │  - 20+ *gen.py  │ │    │  │
│  │  │  │   Gemini.py      │  │  - 9 phases   │  │  - *.docx       │ │    │  │
│  │  │  │ - GeminiCookies  │  │  - 50+ Qs     │  │  - template_    │ │    │  │
│  │  │  │ - 4 accounts     │  │              │  │    registry     │ │    │  │
│  │  │  └─────────────────┘  └──────────────┘  └─────────────────┘ │    │  │
│  │  └──────────────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │  Redis + RQ       │  │  PostgreSQL  │  │  File System / S3            │  │
│  │  - Job queues     │  │  - Users     │  │  - data/uploads/             │  │
│  │  - Pub/Sub        │  │  - Papers    │  │  - data/exports/             │  │
│  │  - Rate limits    │  │  - Messages  │  │  - data/<user>/<paper>/      │  │
│  │  - Caching        │  │  - Jobs      │  │    - generation/             │  │
│  │                   │  │  - Literature│  │    - images/                 │  │
│  │                   │  │  - Images    │  │    - files/                  │  │
│  │                   │  │  - Files     │  │    - docx/                   │  │
│  │                   │  │  - Memory    │  │                              │  │
│  └──────────────────┘  └──────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Database Models (`database/models.py`)

### 4.1 Entity Relationship Diagram

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│  User     │────▶│  Paper        │────▶│ PaperImage   │
│           │ 1:N │              │ 1:N │              │
│ id (PK)   │     │ id (PK)      │     │ id (PK)      │
│ google_id │     │ user_id (FK) │     │ paper_id (FK)│
│ email     │     │ title        │     │ user_id (FK) │
│ name      │     │ data (JSONB) │     │ filename     │
│ password  │     │ created_at   │     │ file_path    │
│ role      │     │ updated_at   │     └──────────────┘
│ token_    │     │ active_op    │
│  quota_   │     └──────┬───────┘     ┌──────────────┐
│  monthly  │            │ 1:N         │ PaperFile    │
│ token_    │            ├────────────▶│              │
│  used     │            │             │ id (PK)      │
│ usage_    │            │             │ paper_id (FK)│
│  month    │            │             │ filename     │
└─────┬─────┘            │             │ ext          │
      │ 1:N              │             │ extracted_   │
      │                  │             │  text        │
      ▼                  │             └──────────────┘
┌──────────────┐         │
│ ApiUsageLog  │         │     ┌──────────────┐
│              │         ├────▶│ Conversation │
│ id (PK)      │         │ 1:N │              │
│ user_id (FK) │         │     │ id (PK)      │
│ endpoint     │         │     │ paper_id (FK)│
│ tokens       │         │     │ title        │
│ model        │         │     └──────┬───────┘
│ created_at   │         │            │ 1:N
└──────────────┘         │            ▼
                         │     ┌──────────────┐
                         │     │ ChatMessage  │
                         │     │              │
                         │     │ id (PK)      │
                         │     │ conv_id (FK) │
                         │     │ role         │
                         │     │ content      │
                         │     │ thinking     │
                         │     │ tool_calls   │
                         │     └──────────────┘
                         │
                         │     ┌──────────────┐
                         ├────▶│ ProjectMemory│
                         │ 1:N │              │
                         │     │ paper_id(FK) │
                         │     │ conv_id (FK) │
                         │     │ key          │
                         │     │ value        │
                         │     │ kind         │
                         │     └──────────────┘
                         │
                         │     ┌──────────────┐
                         ├────▶│ AiJob        │
                         │ 1:N │              │
                         │     │ id (PK)      │
                         │     │ user_id (FK) │
                         │     │ paper_id (FK)│
                         │     │ kind         │
                         │     │ status       │
                         │     │ progress     │
                         │     │ stage        │
                         │     │ result (JSON)│
                         │     └──────────────┘
                         │
                         │     ┌──────────────┐
                         ├────▶│ Literature   │
                         │ 1:N │ Item         │
                         │     │              │
                         │     │ paper_id(FK) │
                         │     │ source_kind  │
                         │     │ title, year  │
                         │     │ doi, url     │
                         │     │ score_total  │
                         │     │ must_read    │
                         │     └──────────────┘
                         │
                         │     ┌──────────────┐
                         ├────▶│ SlrJob       │
                         │ 1:N │              │
                         │     │ id (PK)      │
                         │     │ query        │
                         │     │ sources      │
                         │     │ status       │
                         │     │ result (JSON)│
                         │     └──────────────┘
                         │
                         │     ┌──────────────┐
                         └────▶│ ImageGenJob  │
                               │              │
                               │ id (PK)      │
                               │ prompt       │
                               │ status       │
                               │ worker       │
                               │ image_id(FK) │
                               └──────────────┘
```

### 4.2 Model Details

```pseudo-code
MODEL User:
  id: Integer (PK)
  google_id: String(100) UNIQUE NULL
  email: String(255) UNIQUE NOT NULL
  name: String(255) NOT NULL
  password_hash: String(255) NULL
  avatar_url: String(500)
  role: String(20) = 'user' | 'admin'
  token_quota_monthly: Integer = 1,000,000
  token_used_month: Integer = 0
  usage_month_key: String(7) = 'YYYY-MM'
  papers: Relationship → Paper (1:N, cascade delete)
  set_password(pw) / check_password(pw)

MODEL Paper:
  id: String(20) (PK) — UUID hex 12 chars
  user_id: Integer (FK → users.id)
  title: Text = 'Untitled'
  data: JSON/JSONB — full paper structure
  active_operation: String(50) — operation locking
  active_operation_job_id: String(50)
  images: Relationship → PaperImage (1:N, cascade)
  files: Relationship → PaperFile (1:N, cascade)
  conversations: Relationship → Conversation (1:N, cascade)
  memory_entries: Relationship → ProjectMemory (1:N, cascade)

MODEL PaperImage:
  id, paper_id, user_id, filename, original_name, file_path

MODEL PaperFile:
  id, paper_id, user_id, filename, original_name, ext, size_bytes,
  file_path, extracted_text (cached for preview)

MODEL Conversation:
  id: String(20) (PK)
  user_id, paper_id, title
  messages: Relationship → ChatMessage (1:N, cascade, ordered by created_at)

MODEL ChatMessage:
  id, conversation_id (FK), role, content, thinking, tool_calls (JSON)

MODEL ProjectMemory:
  id, paper_id, user_id, conversation_id (NULL=global),
  key, value, kind='fact'
  UNIQUE INDEX: (paper_id, key) WHERE conversation_id IS NULL
  UNIQUE INDEX: (paper_id, conversation_id, key) WHERE NOT NULL

MODEL AiJob:
  id: String(20) (PK)
  user_id, paper_id, kind='generate_paper'
  status: queued|running|paused|done|error|cancelled
  progress: 0-100, stage: outline|sections|references|combine
  result: JSON, error: Text

MODEL LiteratureItem:
  id, paper_id, user_id
  source_kind: slr|file|manual
  source, title, authors[], year, venue, publisher
  doi, url, pdf_url, abstract, summary
  citations, score_total, score_breakdown
  must_read, is_relevant, notes, pinned
  file_id (FK), slr_job_id (FK)

MODEL SlrJob:
  id: String(20) (PK)
  user_id, paper_id, conversation_id
  query, sources[], top_k=50, per_source=60, year_from
  ai_summarize, ai_model='V-OPUS'
  status: queued|running|done|error|cancelled
  stage, progress, progress_message, result (JSON), error

MODEL ImageGenJob:
  id: String(32) (PK)
  user_id, paper_id, prompt
  status: queued|running|done|error|cancelled
  worker: account1|account2|account3|account4
  image_id (FK → PaperImage)

MODEL ApiUsageLog:
  id, user_id, endpoint, prompt_tokens, completion_tokens,
  total_tokens, model, created_at
```

---

## 5. API Endpoints

### 5.1 Auth (`/api/auth/*`)

```pseudo-code
POST /api/auth/register
  BODY: {name, email, password}
  → 201 {access_token, refresh_token, user}
  VALIDASI: password strength (8+ chars, 3/4 classes)
  SIDE EFFECT: first user → auto-promote to admin

POST /api/auth/login
  BODY: {email, password}
  → 200 {access_token, refresh_token, user}
  SIDE EFFECT: set HttpOnly cookies (access + refresh + CSRF)

GET /api/auth/google/login
  → 302 redirect ke Google OAuth consent
  HMAC-signed state token untuk CSRF protection

GET /api/auth/google/callback
  ← Google redirect dengan code
  → exchange code → tokens → get user info
  → create/update user di DB
  → set JWT cookies
  → 302 redirect ke frontend /auth/callback

POST /api/auth/refresh
  ← Refresh token dari cookie
  → 200 {access_token} (new access token)

POST /api/auth/logout
  → 200 unset JWT cookies

GET /api/auth/me
  ← JWT dari cookie/header
  → 200 {user}

RATE LIMIT: 10 per minute
```

### 5.2 Papers (`/api/papers/*`)

```pseudo-code
GET /api/papers?limit=20&offset=0
  ← JWT
  → 200 {papers[], pagination: {limit, offset, total, has_more}}

POST /api/papers
  ← JWT, BODY: {id?, data, template?}
  → 201 {paper}
  VALIDASI: paper_id format (UUID regex)

GET /api/papers/:paper_id
  ← JWT
  → 200 {paper} (include_data=true)

PATCH /api/papers/:paper_id
  ← JWT, BODY: {data} atau JSON Patch (RFC 6902)
  → 200 {paper}
  SUPPORT: jsonpatch operations (add, remove, replace, move, copy, test)

DELETE /api/papers/:paper_id
  ← JWT
  → 204 (cascade: images, files, conversations, memory, jobs, literature)

POST /api/papers/:paper_id/copy
  ← JWT
  → 201 {paper} (deep copy dengan new ID)

POST /api/papers/:paper_id/generate
  ← JWT, BODY: {prompt, paper_id, template?, stream?}
  → 202 {job_id}
  SIDE EFFECT: enqueue RQ job

GET /api/papers/:paper_id/active-jobs
  ← JWT
  → 200 {jobs[]}

GET /api/papers/:paper_id/ai-jobs/active
  ← JWT
  → 200 {job} | null

GET /api/papers/:paper_id/chat
  ← JWT
  → 200 {conversations[]}

POST /api/papers/:paper_id/chat
  ← JWT, BODY: {title}
  → 201 {conversation}

POST /api/papers/:paper_id/workflow/onboarding
  ← JWT
  → 200 {questions: [...]} (static Phase 0 + Phase 1 questions)
```

### 5.3 Chat (`/api/chat/*`)

```pseudo-code
POST /api/chat/stream
  ← JWT, BODY: {paper_id, message, conversation_id, attached_files[], mode?}
  → SSE stream
  EVENTS:
    thinking   → {type:'thinking', content}
    content    → {type:'content', content}
    tool_call  → {type:'tool_call', tool: {name, args, result}}
    proposal   → {type:'proposal', proposal: {type, data}}
    chart      → {type:'chart', chart: {image_id, caption}}
    file_review→ {type:'file_review', review}
    multi_q    → {type:'multi_question', questions[]}
    slr        → {type:'slr', results}
    done       → {type:'done'}
    error      → {type:'error', message}

GET /api/chat/:conv_id/messages
  ← JWT
  → 200 {messages[]}

DELETE /api/chat/:conv_id
  ← JWT
  → 204 (cascade: messages, chat-scoped memory)

GET /api/chat/modes
  → 200 {modes[]}
```

### 5.4 Jobs (`/api/jobs/*`)

```pseudo-code
GET /api/jobs/:job_id
  ← JWT
  → 200 {id, status, progress, stage, error, result}

GET /api/jobs/:job_id/stream
  ← JWT
  → SSE stream: {stage, percent, partial_paper}

POST /api/jobs/:job_id/cancel
  ← JWT
  → 200 {status: 'cancelled'}
  SIDE EFFECT: set Redis cancel key

POST /api/ai-jobs/:job_id/cancel
  ← JWT
  → 200

POST /api/ai-jobs/:job_id/resume
  ← JWT
  → 200 {job_id} (re-enqueue dengan checkpoint)

POST /api/ai-jobs/:job_id/retry-section
  ← JWT, BODY: {stage}
  → 200 {job_id} (hapus chunk + section, re-enqueue)

GET /api/me/ai-jobs/recent
  ← JWT, QUERY: {status?, limit?}
  → 200 {jobs[]}
```

### 5.5 Files (`/api/papers/:paper_id/files/*`)

```pseudo-code
GET /api/papers/:paper_id/files
  ← JWT
  → 200 {files[]}

POST /api/papers/:paper_id/files
  ← JWT, multipart/form-data
  → 201 {file: {id, filename, original_name, ext, size, url, preview_url}}
  VALIDASI: magic bytes check, ext whitelist, max 30MB per file
  SIDE EFFECT: extract text (PyMuPDF/python-docx/openpyxl) via ThreadPool(20)

GET /api/papers/:paper_id/files/:file_id/preview
  ← JWT
  → 200 {text, truncated} (max 20K chars)

GET /api/papers/:paper_id/files/:file_id/raw
  ← JWT / signed URL / legacy token
  → file bytes (download)

DELETE /api/papers/:paper_id/files/:file_id
  ← JWT
  → 204
```

### 5.6 Images (`/api/papers/:paper_id/images/*`)

```pseudo-code
GET /api/papers/:paper_id/images
  ← JWT
  → 200 {images[]}

POST /api/papers/:paper_id/images
  ← JWT, multipart/form-data
  → 201 {image: {id, filename, url}}
  VALIDASI: magic bytes, ext whitelist (.png,.jpg,.jpeg,.gif,.bmp,.webp)

DELETE /api/papers/:paper_id/images/:image_id
  ← JWT
  → 204

GET /api/papers/:paper_id/images/:image_id/sign
  ← JWT
  → 200 {signed_url} (HMAC-signed, short-lived)

GET /api/images/:paper_id/:filename
  ← JWT / signed URL / legacy token
  → image bytes
```

### 5.7 Charts (`/api/papers/:paper_id/charts`)

```pseudo-code
GET /api/papers/:paper_id/charts
  ← JWT
  → 200 {charts[]}

POST /api/papers/:paper_id/charts
  ← JWT, BODY: {kind, title, xlabel, ylabel, data, series_labels}
  → 201 {image_id, filename, url}
  KINDS: line, bar, scatter, hist, box, heatmap, pie
  SIDE EFFECT: matplotlib → PNG → PaperImage row

POST /api/papers/:paper_id/charts/:chart_id/data
  ← JWT, multipart (CSV/Excel)
  → 200 {columns[], rows[], row_count}

DELETE /api/papers/:paper_id/charts/:chart_id
  ← JWT
  → 204
```

### 5.8 SLR + Literature

```pseudo-code
// SLR Jobs
POST /api/papers/:paper_id/slr/jobs
  ← JWT, BODY: {query, sources[], top_k, per_source, year_from, ai_summarize}
  → 202 {job_id}
  SIDE EFFECT: enqueue SLR worker job

GET /api/papers/:paper_id/slr/jobs
  ← JWT
  → 200 {jobs[]}

GET /api/slr/jobs/:job_id
  ← JWT
  → 200 {id, status, progress, stage, result, stats}

DELETE /api/slr/jobs/:job_id
  ← JWT
  → 204 (cancel + delete)

// Literature CRUD
GET /api/papers/:paper_id/literature
  ← JWT, QUERY: {source?, year?, sort?, dir?}
  → 200 {items[]}

POST /api/papers/:paper_id/literature
  ← JWT, BODY: {title, authors, year, doi, url, ...}
  → 201 {item}

PATCH /api/papers/:paper_id/literature/:id
  ← JWT, BODY: {fields to update}
  → 200 {item}

DELETE /api/papers/:paper_id/literature/:id
  ← JWT
  → 204

POST /api/papers/:paper_id/literature/from-files
  ← JWT, BODY: {file_ids[]}
  → 201 {items[]}
  SIDE EFFECT: extract metadata dari PDF/DOCX → LiteratureItem
```

### 5.9 Image Generation Jobs

```pseudo-code
POST /api/image-jobs
  ← JWT, BODY: {paper_id, prompt}
  → 202 {job_id}
  LIMIT: max 12 inflight per user

GET /api/image-jobs
  ← JWT, QUERY: {user_id, status?}
  → 200 {jobs[]}

DELETE /api/image-jobs/:job_id
  ← JWT
  → 204 (cancel)
```

### 5.10 Writing Tools (`/api/tools/*`)

```pseudo-code
POST /api/tools/paraphrase  ← JWT, BODY: {text, option} → SSE stream
POST /api/tools/translate   ← JWT, BODY: {text, option} → SSE stream
POST /api/tools/humanizer   ← JWT, BODY: {text, option} → SSE stream
POST /api/tools/detector    ← JWT, BODY: {text} → SSE → JSON {pct, reasons, suggestions}
POST /api/tools/plagiarism  ← JWT, BODY: {text} → SSE → JSON {pct, matches, suggestions}
POST /api/tools/grammar     ← JWT, BODY: {text} → SSE → HTML dengan <add>/<del>
POST /api/tools/summarize   ← JWT, BODY: {text, option} → SSE stream
POST /api/tools/citation    ← JWT, BODY: {text} → SSE stream
```

### 5.11 Quota

```pseudo-code
GET /api/quota
  ← JWT
  → 200 {monthly_limit, used, remaining, by_model: {}}

GET /api/quota/history
  ← JWT
  → 200 {usage[]}
```

### 5.12 Admin (`/api/admin/*`)

```pseudo-code
GET /api/admin/users
  ← JWT (admin only)
  → 200 {users[], pagination}

POST /api/admin/users/:id/promote
  ← JWT (admin)
  → 200 {user}

POST /api/admin/users/:id/quota
  ← JWT (admin), BODY: {quota}
  → 200 {user}

GET /api/admin/papers
  ← JWT (admin)
  → 200 {papers[], pagination}

GET /api/admin/usage
  ← JWT (admin)
  → 200 {tokens: {}, endpoints: {}, daily: [], perUser: []}
```

### 5.13 Health

```pseudo-code
GET /api/health
  → 200 {status: 'ok'}

GET /api/health/ready
  → 200 {db: 'ok', disk: 'ok', memory: 'ok'}
  → 503 if any check fails
```

### 5.14 Logging

```pseudo-code
POST /api/logs
  ← JWT, BODY: {logs: [{level, message, data, timestamp}]}
  → 204
  SIDE EFFECT: write ke app.log
```

### 5.15 Docs

```pseudo-code
GET /api/docs
  → HTML (Swagger UI dari CDN)

GET /api/openapi.yaml
  → YAML (OpenAPI 3.1 spec)
```

---

## 6. Paper Generation Engine

### 6.1 Single-Shot Generation (`paper_generation/single.py`)

```pseudo-code
FUNGSI generate_paper_json_single(prompt, paper_id, user_id, job_id):
  // 1. Build system prompt
  system = LOAD prompt.txt
  system += LOAD humanize.txt
  system += build_style_context(paper.data)
  system += build_topic_context(prompt)

  // 2. Load context
  context = []
  context += load_chat_history(paper_id)
  context += load_literature(paper_id)
  context += load_attached_files(paper_id)

  // 3. Call AI API
  response = api_client.stream_chat(
    model = MODELGENERATE (VIOLA-GENERATE)
    messages = [system, ...context, {role:'user', content:prompt}]
  )

  // 4. Parse JSON response
  raw_json = extract_json(response.content)
  paper_data = json.loads(raw_json)
  
  // Fallback: json_repair jika parse gagal
  IF parse fails:
    paper_data = json_repair.loads(raw_json)

  // 5. Validate paper shape
  validate_paper_structure(paper_data)
  // Check: title, abstract, sections, references

  // 6. Quality check
  quality = quality_validator.validate(paper_data)
  // Check: IMRAD structure, abstract length, citation presence

  // 7. Save per-job log
  save_generation_log(job_id, response, paper_data)

  RETURN paper_data
```

### 6.2 Chunked Generation (`paper_generation/chunked.py`)

```pseudo-code
FUNGSI generate_paper_chunked(prompt, paper_id, user_id, job_id):
  // 7-chunk pipeline:
  // Chunk 0: Outline
  // Chunk 1: Introduction
  // Chunk 2: Literature Review / Methodology
  // Chunk 3: Results
  // Chunk 4: Discussion
  // Chunk 5: Conclusion
  // Chunk 6: References

  checkpoint = load_checkpoint(job_id) || {chunks_done: [], partial_paper: {}}

  FOR chunk_index IN 0..6:
    IF chunk_index IN checkpoint.chunks_done:
      CONTINUE  // Skip completed chunks

    // Check cancel flag
    IF is_cancelled(job_id):
      SAVE checkpoint
      THROW GenerationCancelled

    // Build chunk-specific prompt
    system = build_chunk_prompt(chunk_index, prompt)
    context = build_full_context(paper_id, checkpoint.partial_paper)

    // Generate chunk
    response = api_client.stream_chat(model, [system, ...context])
    chunk_data = parse_json(response.content)

    // Update checkpoint
    checkpoint.partial_paper = merge(checkpoint.partial_paper, chunk_data)
    checkpoint.chunks_done.push(chunk_index)
    SAVE checkpoint

    // Publish progress
    publish_progress(job_id, {
      stage: chunk_name(chunk_index),
      percent: (chunk_index + 1) / 7 * 100,
      partial: checkpoint.partial_paper
    })

  // Final: combine all chunks
  final_paper = post_process(checkpoint.partial_paper)
  validate_paper_structure(final_paper)

  RETURN final_paper

// Resume support
FUNGSI resume_chunked(job_id):
  checkpoint = load_checkpoint(job_id)
  // Continue from where left off

// Retry section
FUNGSI retry_section(job_id, stage):
  checkpoint = load_checkpoint(job_id)
  REMOVE stage FROM chunks_done
  REMOVE matching section FROM partial_paper
  SAVE checkpoint
  RE-ENQUEUE job
```

### 6.3 AI API Client (`paper_generation/api_client.py`)

```pseudo-code
CLASS AiApiClient:
  PRIMARY_MODEL = 'VIOLA-GENERATE'
  FALLBACK_MODEL = 'VIOLA-CHAT'
  API_URL = AIOTOMASI_API + '/chat/completions'
  API_KEY = AIOTOMASI_APIKEY

  FUNGSI stream_chat(model, messages, max_tokens=8192):
    FOR retry IN 0..2:
      TRY:
        response = requests.post(API_URL, {
          'model': model,
          'messages': messages,
          'stream': True,
          'max_tokens': max_tokens
        }, stream=True, timeout=300)

        FOR line in response.iter_lines():
          IF line.startswith('data: '):
            chunk = json.loads(line[6:])
            IF chunk == '[DONE]': BREAK
            YIELD chunk

        RETURN  // Success

      CATCH (Timeout, ConnectionError):
        IF retry == 1: SWITCH to FALLBACK_MODEL
        SLEEP(2^retry)
        CONTINUE

      CATCH (APIError):
        LOG error
        THROW
```

---

## 7. Chat System

### 7.1 Chat Flow (`api/chat_bp.py`)

```pseudo-code
ENDPOINT POST /api/chat/stream:
  1. Validate JWT → user_id
  2. Parse body: {paper_id, message, conversation_id, attached_files, mode}
  3. Load/create conversation
  4. Load project memory (paper-global + chat-scoped)
  5. Load mode bundle (system prompt + tool list)
  6. IF mode == 'tier0':
       mode = classify_intent(message)  // RouteIntent
  7. Build messages array:
     [system_prompt, memory_summary, ...history, user_message]
  8. Stream SSE:
     FOR EACH chunk FROM ai_api:
       IF chunk has tool_calls:
         FOR EACH tool_call:
           result = execute_tool(tool_call, paper_id, user_id)
           YIELD {type:'tool_call', tool: result}
           // Feed tool result back into conversation
           CONTINUE AI stream with tool result
       IF chunk has content:
         SCRUB leaked control tokens (DeepSeek-style)
         YIELD {type:'content', content}
     YIELD {type:'done'}
  9. Save messages to DB
  10. Extract facts → auto_memory
```

### 7.2 Tool Executor (`chat/tools.py`)

```pseudo-code
// 30+ available tools:
TOOLS:
  WebSearch          → Search web via searchPaper.py
  SearchPapers       → Search academic papers (19+ sources)
  GenerateFullPaper  → Trigger chunked paper generation
  RunSLR             → Start SLR job
  ProposeSection     → Generate section content proposal
  ProposeParaphrase  → Paraphrase text
  ProposeTranslate   → Translate text
  ProposeGrammar     → Fix grammar
  ProposeChart       → Generate chart
  ProposeRevision    → Full revision proposal
  ReviewFile         → Review attached file
  MultiQuestion      → Generate questionnaire
  SaveMemory         → Save fact to ProjectMemory
  ReadMemory         → Read from ProjectMemory
  ReadFile           → Read attached file content
  WriteFile          → Write to paper data
  BashCommand        → Sandboxed bash execution
  // ... more tools

FUNCSI execute_tool(tool_call, paper_id, user_id):
  tool_name = tool_call.name
  args = tool_call.args

  // Paper locking: acquire active_operation lock
  acquire_paper_lock(paper_id, job_id)

  SWITCH tool_name:
    case 'GenerateFullPaper':
      result = generate_paper_chunked(args.prompt, paper_id, user_id, job_id)
    case 'RunSLR':
      result = enqueue_slr_job(args.query, paper_id, user_id)
    case 'ProposeSection':
      result = generate_section_proposal(args, paper_id)
    case 'SaveMemory':
      result = save_project_memory(paper_id, args.key, args.value)
    // ... etc

  release_paper_lock(paper_id)

  RETURN {name: tool_name, args, result}

// Proposal system: tools emit <<PROPOSAL>> sentinel
// Frontend detects proposal type and renders appropriate UI
```

### 7.3 Mode System (`chat/mode_prompts.py`)

```pseudo-code
MODES:
  tier0      → Router: classify intent, delegate to appropriate mode
  discovery  → Explore topic, find research gap
  slr        → Systematic literature review
  edit       → Edit existing paper sections
  rapikan    → Polish/format paper
  memory     → Review/manage project memory
  casual     → General chat

EACH MODE HAS:
  - system_prompt: string (scoped instructions)
  - tools: string[] (subset of available tools)
  - description: string

FUNGSI get_mode_bundle(mode):
  RETURN {system_prompt, tools, description}

FUNGSI classify_intent(message):
  // Tier-0 classifier
  // Returns: 'discovery' | 'slr' | 'edit' | 'rapikan' | 'memory' | 'casual'
```

### 7.4 Auto Memory (`chat/auto_memory.py`)

```pseudo-code
FUNGSI extract_facts(message, paper_id, conversation_id):
  // Layer 1: Regex extraction
  facts = regex_extract(message)
  // Patterns: "judulnya adalah...", "metodologi: ...", "gaya: ..."

  // Layer 2: LLM fallback for unstructured
  IF no facts from regex:
    facts = llm_extract_facts(message)

  // Save to ProjectMemory
  FOR EACH fact IN facts:
    save_memory(paper_id, conversation_id, fact.key, fact.value)

FUNGSI get_memory_summary(paper_id, conversation_id):
  global_mem = ProjectMemory.query WHERE paper_id AND conversation_id IS NULL
  chat_mem = ProjectMemory.query WHERE paper_id AND conversation_id = ?
  RETURN format_as_text(global_mem + chat_mem)
```

---

## 8. SLR Pipeline

### 8.1 Architecture

```pseudo-code
┌──────────────────────────────────────────────────────────────┐
│                     SLR PIPELINE                              │
│                                                               │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────┐  │
│  │  Query    │───▶│  Orchestrator │───▶│  Fetchers (19+)   │  │
│  │  + Params │    │              │    │  - OpenAlex        │  │
│  └──────────┘    │  - Dedup     │    │  - CrossRef        │  │
│                  │  - Merge     │    │  - arXiv           │  │
│                  │  - Score     │    │  - Semantic Scholar│  │
│                  └──────┬───────┘    │  - PubMed          │  │
│                         │            │  - Europe PMC      │  │
│                         ▼            │  - DOAJ, DBLP      │  │
│                  ┌──────────────┐    │  - PLOS, bioRxiv   │  │
│                  │  Scoring      │    │  - Zenodo, OSF     │  │
│                  │  - Relevance  │    │  - (5 keyed)       │  │
│                  │  - Citations  │    └───────────────────┘  │
│                  │  - Recency    │                            │
│                  └──────┬───────┘                            │
│                         │                                     │
│                         ▼                                     │
│                  ┌──────────────┐    ┌───────────────────┐  │
│                  │  Summarizer   │───▶│  LiteratureItem    │  │
│                  │  (AI)         │    │  (DB rows)         │  │
│                  └──────────────┘    └───────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 8.2 Worker Pool (`workers/slr_worker.py`)

```pseudo-code
// 10 workers with atomic job claiming

FUNGSI slr_worker_loop():
  LOOP:
    // Atomic claim: UPDATE ... WHERE status='queued' RETURNING
    job = claim_next_job()
    IF job IS NULL:
      SLEEP(5)
      CONTINUE

    TRY:
      UPDATE job SET status='running', started_at=NOW()

      // Execute pipeline
      results = slr_pipeline.run(
        query=job.query,
        sources=job.sources,
        top_k=job.top_k,
        per_source=job.per_source,
        year_from=job.year_from,
        progress_callback=lambda p: update_progress(job.id, p)
      )

      // AI summarization
      IF job.ai_summarize:
        summary = summarizer.summarize(results)
        results.ai_summary = summary

      // Save results as LiteratureItem rows
      FOR EACH paper IN results.papers:
        create_literature_item(job.paper_id, job.user_id, paper, job.id)

      UPDATE job SET status='done', result=results, finished_at=NOW()

    CATCH Exception:
      UPDATE job SET status='error', error=str(e)

FUNGSI claim_next_job():
  // Atomic claim with row-level lock
  job = SlrJob.query
    .filter_by(status='queued')
    .order_by(SlrJob.queued_at)
    .with_for_update(skip_locked=True)
    .first()
  COMMIT
  RETURN job
```

### 8.3 Search Sources (19 Free + 5 Keyed)

```pseudo-code
FREE_SOURCES:
  OpenAlex, CrossRef, arXiv, Semantic Scholar, Europe PMC,
  PubMed, DOAJ, DBLP, OpenAIRE, HAL, PLOS, bioRxiv,
  Zenodo, DataCite, OSF, HuggingFace, InspireHEP, ERIC

KEYED_SOURCES (require API key):
  CORE, Lens, NASA ADS, Springer, Unpaywall

SSRF_PROTECTION:
  ALLOWLIST = [
    'api.openalex.org', 'api.crossref.org', 'export.arxiv.org',
    'api.semanticscholar.org', 'eutils.ncbi.nlm.nih.gov',
    'www.ebi.ac.uk', 'doaj.org', 'dblp.org',
    'api.openaire.eu', 'api.hal.inria.fr',
    'api.plos.org', 'biorxiv.org', 'zenodo.org',
    'api.datacite.org', 'api.osf.io',
    'huggingface.co', 'inspirehep.net',
    'eric.ed.gov', 'api.unpaywall.org',
    'api.core.ac.uk', 'api.lens.org',
    'api.adsabs.harvard.eu', 'api.springernature.com'
  ]
  BLOCK all requests NOT matching allowlist
```

---

## 9. Image Generation

### 9.1 Architecture

```pseudo-code
┌──────────────────────────────────────────────────────────────┐
│                  IMAGE GENERATION POOL                        │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Worker 1 │  │ Worker 2 │  │ Worker 3 │  │ Worker 4 │   │
│  │ Account1 │  │ Account2 │  │ Account3 │  │ Account4 │   │
│  │          │  │          │  │          │  │          │   │
│  │Playwright│  │Playwright│  │Playwright│  │Playwright│   │
│  │→ Gemini  │  │→ Gemini  │  │→ Gemini  │  │→ Gemini  │   │
│  │  Browser │  │  Browser │  │  Browser │  │  Browser │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│       │              │              │              │          │
│       └──────────────┴──────────────┴──────────────┘          │
│                          │                                    │
│                    ┌─────▼─────┐                              │
│                    │  Redis     │                              │
│                    │  Queue    │                              │
│                    └───────────┘                              │
└──────────────────────────────────────────────────────────────┘
```

### 9.2 Worker Flow (`workers/image_worker.py`)

```pseudo-code
FUNGSI image_worker_loop(account_name, profile_path):
  // Initialize Playwright browser with Gemini profile
  browser = launch_persistent_context(profile_path)
  page = browser.new_page()
  
  // Warm: navigate to Gemini
  page.goto('https://gemini.google.com')
  WAIT for page ready

  LOOP:
    // Claim job atomically
    job = claim_image_job(account_name)
    IF job IS NULL:
      SLEEP(10)
      CONTINUE

    TRY:
      UPDATE job SET status='running', worker=account_name

      // Navigate to Gemini and submit prompt
      page.goto('https://gemini.google.com')
      fill_prompt_input(page, job.prompt)
      click_generate(page)

      // Intercept image response
      image_data = intercept_image_response(page, timeout=120)

      // Compress to <1MB
      compressed = compress_image(image_data, max_bytes=1_000_000)

      // Save to file system
      filename = uuid4 + '.png'
      save_path = data/uploads/paper_images/filename
      write_file(save_path, compressed)

      // Create PaperImage row
      image = PaperImage(paper_id, user_id, filename, save_path)
      db.session.add(image)
      db.session.commit()

      UPDATE job SET status='done', image_id=image.id, finished_at=NOW()

    CATCH Exception:
      UPDATE job SET status='error', error=str(e)

    // Keep browser warm (don't close between jobs)
```

---

## 10. Workflows (Questionnaire System)

### 10.1 9-Phase Engine (`workflows/engine.py`)

```pseudo-code
WORKFLOW_PHASES:
  Phase 0: Pre-Questionnaire — Status Awal
    - Progress level, data readiness, team size

  Phase 1: Profil Dasar Paper
    - Field of study (13 options), paper type, target publication

  Phase 2: Detail Penelitian
    - Title, research questions, methodology

  Phase 3: Metodologi
    - Quantitative/qualitative/mixed, data collection, analysis

  Phase 4: Hasil & Analisis
    - Key findings, statistical tests, visualizations

  Phase 5: Diskusi
    - Interpretation, comparison with prior work, limitations

  Phase 6: Conditional Branching
    - Quantitative → statistical analysis details
    - Qualitative → thematic analysis details
    - Literature → review methodology

  Phase 7: Kesimpulan & Abstrak
    - Conclusions, contributions, future work

  Phase 8: Final Review
    - Complete paper review, export options

EACH QUESTION HAS:
  - id: string (e.g., "1.1")
  - question: string
  - key: string (for storing answer)
  - options: [{label, value}] (4 options + 1 custom)
  - depends_on: [question_ids] (conditional display)
  - ai_recommendations: boolean (generate AI options)

FUNGSI get_phase_questions(phase, answers):
  questions = WORKFLOW_PHASES[phase].questions
  // Filter by depends_on
  filtered = [q FOR q IN questions IF all_deps_met(q, answers)]
  // Generate AI recommendations if enabled
  FOR q IN filtered:
    IF q.ai_recommendations:
      q.ai_options = generate_ai_options(q, answers)
  RETURN filtered

FUNGSI validate_answers(answers):
  // Cross-check validation
  // e.g., IF paper_type == 'literature_review' AND methodology == 'experiment'
  //   → WARNING: inconsistent
```

---

## 11. Monitoring & Observability

### 11.1 Prometheus Metrics (`monitoring/observability_v2.py`)

```pseudo-code
METRICS:
  http_requests_total{method, endpoint, status}     → Counter
  http_request_duration_seconds{method, endpoint}   → Histogram
  http_requests_in_flight                           → Gauge
  ai_generation_total{status}                       → Counter
  log_errors_total{error_type, error_code}          → Counter
  slow_operations_total{operation, threshold_ms}    → Counter
  frontend_errors_total{error_type, page}           → Counter
  rate_limit_requests{endpoint, status}             → Counter
  rate_limit_breaches{endpoint, limit_type}         → Counter

LOG FILES (TimedRotatingFileHandler, daily rotation):
  app.log      → INFO+, 7-day retention, gzip
  error.log    → ERROR+, 30-day retention, gzip
  access.log   → HTTP access, 7-day retention
  worker.log   → Background workers, 7-day retention
  perf.log     → Performance warnings, 7-day retention

LOG FORMAT: JSON structured
  {
    "timestamp": "ISO8601",
    "level": "INFO",
    "module": "api.chat_bp",
    "message": "...",
    "user_id": 123,
    "paper_id": "abc123",
    "duration_ms": 45.2,
    "extra": {...}
  }
```

### 11.2 Sentry/GlitchTip Integration

```pseudo-code
IF GLITCHTIP_DSN is set:
  sentry_sdk.init(
    dsn=GLITCHTIP_DSN,
    integrations=[FlaskIntegration(), SqlalchemyIntegration()],
    traces_sample_rate=0.05,
    send_default_pii=False,
    release=SENTRY_RELEASE,
    environment=FLASK_ENV
  )
```

---

## 12. Security

### 12.1 Security Headers

```pseudo-code
ON every response:
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), microphone=(), camera=()
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  Content-Security-Policy: (strict CSP)
  Cache-Control: no-store (for /api/* paths)
```

### 12.2 JWT Configuration

```pseudo-code
JWT_TOKEN_LOCATION = ['cookies', 'headers']
JWT_ACCESS_TOKEN_EXPIRES = 1 hour
JWT_REFRESH_TOKEN_EXPIRES = 7 days
JWT_COOKIE_SECURE = true
JWT_COOKIE_HTTPONLY = true
JWT_COOKIE_SAMESITE = 'Lax'
JWT_COOKIE_CSRF_PROTECT = true
JWT_ACCESS_CSRF_HEADER_NAME = 'X-CSRF-TOKEN'
```

### 12.3 Rate Limiting

```pseudo-code
DEFAULT: 1000 per minute per IP
AUTH endpoints: 10 per minute per IP
STORAGE: Redis (production) / memory (development)
ON BREACH: JSON {error, code: 'RATE_LIMIT_EXCEEDED', retry_after: 60}
```

### 12.4 Input Validation

```pseudo-code
// JSONSchema validation via middleware
@validate_request(PAPER_CREATE_SCHEMA)
@validate_query(PAPER_LIST_QUERY_SCHEMA)

// File validation
- Magic bytes check (PDF: %PDF, DOCX: PK\x03\x04, etc.)
- Extension whitelist
- Size limit: 30MB per file, 60MB total multipart

// Paper ID validation
PAPER_ID_RE = regex(r'^[a-f0-9]{12}$')

// SSRF protection for external API calls
ALLOWLIST = [known academic API domains only]
BLOCK all other outbound requests
```

### 12.5 Database Safeguards

```pseudo-code
// PostgreSQL session defaults
SET statement_timeout = '30s'
SET idle_in_transaction_session_timeout = '5min'
SET lock_timeout = '5s'

// Production drop_all protection
db.drop_all = _safe_drop_all  // Refuses unless PAPERFULL_ALLOW_DESTRUCTIVE_DB=1

// Connection pooling
pool_size = 12, max_overflow = 28, pool_timeout = 30s
pool_recycle = 1800s, pool_pre_ping = true
```

---

## 13. DOCX Export

### 13.1 Template System

```pseudo-code
AVAILABLE TEMPLATES (deteksi otomatis dari templates/ folder):
  IEEE, APA, Springer, JRC, JAMRIS, IJITEE, ELKOLIND,
  CCJ, AMORI, JTMM, JTRANSIENT, JNTETI, JMEMGEN,
  JOKI, JEEMECS, JCEF, JIEB, IJECE, IJEECS,
  IJIMS, IJITEE, IJT, IJRED, EASR, ELCTRICES,
  DJLIT, CERiMRE, ICET, ICIMECE, ICONIE,
  MEV, ROTASI, ULTIMACOMP, UITM

EACH TEMPLATE HAS:
  - *.docx file (base template)
  - *gen.py module with build_document() function

FUNGSI build_document(paper_data, template_code):
  canonical = resolve_journal_code(template_code)
  builder = import_module(f'template.{canonical}gen')
  doc = builder.build_document(paper_data)
  // Build: title, authors, abstract, sections, references, figures
  RETURN docx.Document

ENDPOINT POST /api/export/docx:
  BODY: {paper_data, journal: 'IEEE'}
  → DOCX file download
```

---

## 14. Integrasi Backend ↔ Frontend

### 14.1 Request Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                        REQUEST LIFECYCLE                               │
│                                                                        │
│  Frontend (Axios)                                                      │
│      │                                                                 │
│      ├── Cookie (JWT access + CSRF) ──────────────────────────────┐   │
│      ├── Header: X-CSRF-TOKEN                                      │   │
│      └── Body: JSON / FormData                                     │   │
│                                                                     ▼   │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  NGINX / Reverse Proxy                                          │   │
│  │  - SSL termination                                              │   │
│  │  - Proxy headers (X-Forwarded-For, X-Forwarded-Proto)           │   │
│  └──────────────────────────────┬───────────────────────────────────┘   │
│                                 │                                       │
│  ┌──────────────────────────────▼───────────────────────────────────┐   │
│  │  Gunicorn Worker                                                │   │
│  │                                                                 │   │
│  │  ┌──────────────────────────────────────────────────────────┐  │   │
│  │  │  Flask App                                                │  │   │
│  │  │                                                           │  │   │
│  │  │  1. ProxyFix (trust X-Forwarded-*)                       │  │   │
│  │  │  2. CORS check                                            │  │   │
│  │  │  3. Rate limit check                                      │  │   │
│  │  │  4. JWT verification (cookie → identity)                 │  │   │
│  │  │  5. CSRF verification (double-submit)                    │  │   │
│  │  │  6. JSONSchema validation (middleware)                   │  │   │
│  │  │  7. Blueprint route handler                               │  │   │
│  │  │  8. Business logic                                       │  │   │
│  │  │  9. DB operation (SQLAlchemy)                            │  │   │
│  │  │  10. Response                                             │  │   │
│  │  │  11. Security headers                                     │  │   │
│  │  │  12. Prometheus metrics                                   │  │   │
│  │  └──────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                 │                                       │
│                                 ▼                                       │
│  Response ← JSON / File / SSE Stream                                   │
│      │                                                                 │
│      ▼                                                                 │
│  Frontend Axios Interceptor                                            │
│      ├── 200-299 → resolve promise                                     │
│      ├── 401 → try refresh → retry / redirect login                   │
│      ├── 429 → show rate limit message                                 │
│      └── 500 → show error + report to Sentry                           │
└────────────────────────────────────────────────────────────────────────┘
```

### 14.2 SSE Endpoints (Server-Sent Events)

```
┌──────────────────────────────────────────────────────────────┐
│                   SSE ENDPOINTS                               │
│                                                               │
│  1. POST /api/chat/stream                                    │
│     → Chat responses (thinking, content, tool_calls, etc.)   │
│     → Frontend: chat.ts store                                │
│                                                               │
│  2. GET /api/jobs/:job_id/stream                             │
│     → Paper generation progress                              │
│     → Frontend: paperJobs.ts store                           │
│                                                               │
│  3. POST /api/tools/:tool_name                               │
│     → Writing tool streaming output                          │
│     → Frontend: tools.ts store                               │
│                                                               │
│  SSE Protocol:                                                │
│    data: {"type": "...", "content": "..."}\n\n               │
│    data: [DONE]\n\n                                           │
│                                                               │
│  Redis Pub/Sub untuk job progress:                            │
│    Worker → PUBLISH job:{id}:progress → Redis                 │
│    Flask → SUBSCRIBE → forward as SSE                         │
└──────────────────────────────────────────────────────────────┘
```

### 14.3 File Storage

```pseudo-code
// Local file storage structure:
data/
├── uploads/                    # Uploaded files
│   ├── <uuid>.pdf
│   ├── <uuid>.docx
│   └── ...
├── exports/                    # Generated DOCX
│   ├── <paper_id>_<timestamp>.docx
│   └── ...
├── logs/                       # Application logs
│   ├── app.log
│   ├── error.log
│   ├── access.log
│   ├── worker.log
│   └── perf.log
└── <username>/                 # Per-user data
    └── <paper_id>/             # Per-paper data
        ├── generation/         # Generation logs
        │   └── <job_id>/
        │       ├── prompt.txt
        │       ├── response.json
        │       └── paper.json
        ├── images/             # Paper images
        ├── files/              # Attached files
        └── docx/               # Generated DOCX

// S3-compatible storage (optional, via boto3):
// Same structure, different backend
```

---

## 15. Configuration

### 15.1 Environment Variables

```pseudo-code
// Required:
DATABASE_URL              # postgresql://user:pass@host:db
JWT_SECRET_KEY            # Secure random string
SECRET_KEY                # Flask secret key

// AI API:
AIOTOMASI_API             # Base URL for AI API
AIOTOMASI_APIKEY          # API key
MODELGENERATE             # Default: VIOLA-GENERATE
MODELCHAT                 # Default: VIOLA-CHAT

// OAuth:
GOOGLE_CLIENT_ID          # Google OAuth client ID
GOOGLE_CLIENT_SECRET      # Google OAuth client secret

// Redis:
REDIS_URL                 # redis://localhost:6379/0
RATELIMIT_STORAGE_URI     # redis://... (required in production)

// Optional:
SENTRY_DSN / GLITCHTIP_DSN  # Error tracking
SENTRY_RELEASE              # Version tag
FLASK_ENV                   # production / development / testing
PRODUCTION                  # true / false
SESSION_COOKIE_DOMAIN       # Domain for session cookies
FRONTEND_URL_ALLOWLIST      # Comma-separated allowed redirect URLs
SIGNED_URL_SECRET           # HMAC key for signed URLs
PAPERFULL_ALLOW_DESTRUCTIVE_DB  # Set to 1 to allow db.drop_all()

// S3 (optional):
S3_ENDPOINT                 # MinIO/AWS endpoint
S3_ACCESS_KEY
S3_SECRET_KEY
S3_BUCKET
```

### 15.2 Gunicorn Config (`gunicorn.conf.py`)

```pseudo-code
workers = 4
threads = 8
worker_class = 'gthread'
timeout = 120          # seconds
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
worker_tmp_dir = '/dev/shm'
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
accesslog = 'data/logs/access.log'
errorlog = 'data/logs/error.log'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
```

---

## 16. Testing

```pseudo-code
// Test structure:
tests/
├── conftest.py                    # Shared fixtures
├── helpers/
│   ├── __init__.py
│   └── mock_ai.py                # Mock AI responses
├── performance/
│   ├── test_performance_infrastructure.py
│   ├── run_performance_tests.py
│   ├── mock_server.py
│   └── simple_mock_server.py
├── test_api_contract.py          # Schemathesis API contract tests
├── test_admin_bp.py
├── test_auth_bp.py
├── test_charts_bp.py
├── test_chat_bp.py
├── test_chat_model_picker.py
├── test_config.py
├── test_critical_fixes.py
├── test_errors.py
├── test_generate_paper_chunked.py
├── test_health.py
├── test_image_fixes.py
├── test_jobs_bp.py
├── test_literature_routes.py
├── test_mode_prompts.py
├── test_openapi_spec.py
├── test_papers_bp_patch.py
├── test_password_strength.py
├── test_paragraph_context.py
├── test_playwright_paper_generation.py
├── test_quota_bp.py
├── test_rate_limit_metrics.py
├── test_references_normalization.py
├── test_review_large_file.py
├── test_signed_url.py
├── test_slr_bp_routes.py
├── test_slr_worker.py
├── test_storage_helper.py
├── test_swagger_ui.py
├── test_validation_middleware.py
└── playwright_mcp_runner.py

// Run tests:
pytest                          # All tests
pytest tests/test_auth_bp.py   # Specific test
pytest -x                      # Stop on first failure
pytest --cov                   // With coverage
```

---

## 17. Deployment

```pseudo-code
// Production deployment:

// 1. Backend:
cd backend/
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # Run migrations
gunicorn -c gunicorn.conf.py app:app

// 2. Workers (separate terminals/processes):
python -m workers.slr_worker          # SLR workers
python -m workers.image_worker        # Image generation workers
# atau gunakan worker.sh

// 3. Frontend:
cd frontend/
npm install
npm run build                 # Production build
# Serve dist/ via Nginx atau:
npx serve -s dist -l 1000

// 4. Nginx config (example):
# Proxy /api/* → gunicorn :8001
# Serve / → frontend dist/
# SSL termination
# Static file serving
```

---

## 18. Ringkasan Fitur

| Fitur | Module | Endpoint |
|-------|--------|----------|
| Email/password auth | auth_bp.py | POST /api/auth/login, /register |
| Google OAuth 2.0 | auth_bp.py | GET /api/auth/google/* |
| JWT + Refresh | auth_bp.py | POST /api/auth/refresh |
| Paper CRUD | papers_bp.py | CRUD /api/papers/* |
| JSON Patch (RFC 6902) | papers_bp.py | PATCH /api/papers/:id |
| Chat (SSE streaming) | chat_bp.py | POST /api/chat/stream |
| Tool execution | chat/tools.py | (via chat stream) |
| Mode system (8 modes) | chat/mode_prompts.py | GET /api/chat/modes |
| Auto memory | chat/auto_memory.py | (via SaveMemory tool) |
| Paper generation (single) | paper_generation/single.py | POST /api/generate |
| Paper generation (chunked) | paper_generation/chunked.py | POST /api/generate |
| Job management (RQ) | jobs_bp.py | /api/jobs/*, /api/ai-jobs/* |
| Job SSE progress | jobs_bp.py | GET /api/jobs/:id/stream |
| Cancel/Resume/Retry | jobs_bp.py | POST /api/ai-jobs/:id/* |
| File upload/preview | files_bp.py | /api/papers/:id/files/* |
| Image upload/serve | images_bp.py | /api/papers/:id/images/* |
| Signed URLs | images_bp.py | GET /api/images/:id/sign |
| Chart generation | charts_bp.py | /api/papers/:id/charts |
| SLR (19+ sources) | slr_bp.py, slr/ | /api/slr/jobs/* |
| SLR worker pool | workers/slr_worker.py | (background) |
| Literature CRUD | slr_bp.py | /api/papers/:id/literature/* |
| Image generation (Gemini) | image_jobs_bp.py | POST /api/image-jobs |
| Image worker pool (4 acc) | workers/image_worker.py | (background) |
| Writing tools (8 tools) | tools_bp.py | POST /api/tools/:tool |
| Token quota | quota_bp.py | GET /api/quota |
| Admin dashboard | admin_bp.py | /api/admin/* |
| Workflow questionnaire | workflow_bp.py | /api/papers/:id/workflow/* |
| DOCX export | templates/ | POST /api/export/docx |
| Health checks | health_bp.py | GET /api/health |
| Frontend log ingestion | logging_bp.py | POST /api/logs |
| Swagger UI | app.py | GET /api/docs |
| OpenAPI spec | app.py | GET /api/openapi.yaml |
| Prometheus metrics | monitoring/observability_v2.py | (internal) |
| Sentry error tracking | app.py | (internal) |
| Rate limiting | Flask-Limiter | (global) |
| SSRF protection | slr/http_client.py | (internal) |
| DB migration | alembic/ | alembic upgrade head |
