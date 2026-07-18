# PaperGenerator — Project Memory

## Tech Stack
- **Backend**: Python 3.11+ / Flask / Gunicorn
- **Frontend**: Vue 3 (Composition API) / Vite / TypeScript / Tailwind CSS
- **Database**: PostgreSQL (SQLAlchemy/Flask-SQLAlchemy, Alembic migrations)
- **Cache/Queue**: Redis (job progress, SSE pubsub, rate limiting)
- **Deployment**: Nginx reverse proxy (paperfull.conf) / PM2 (ecosystem.config.cjs)
- **Auth**: Flask-JWT-Extended (cookie-based) + Google OAuth

## Directory Structure
```
papergenerator/
├── backend/
│   ├── main.py              # Flask app, all route registration (~3200 lines)
│   ├── tools/
│   │   ├── Literatur/slr.py  # SLR orchestrator + literature endpoints (~4000 lines)
│   │   ├── Journal/          # DOCX generation per journal format
│   │   ├── chat/             # AI chat (SSE streaming)
│   │   ├── image_generation/ # AG + Codex image generation
│   │   ├── payment/doku.py   # Payment (DOKU)
│   │   ├── paperfull/        # Full paper generation jobs
│   │   ├── editor/           # Paper CRUD, section generation
│   │   └── ...               # paraphrase, humanizer, rubric, etc.
│   ├── utils/
│   │   ├── database/models.py # All SQLAlchemy models
│   │   ├── ai_tools/         # Model router, tools API
│   │   ├── auth_bp.py        # Auth blueprint
│   │   ├── quota.py          # Token quota management
│   │   └── ...
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/            # Page components (Landing, Login, Dashboard, Editor, etc.)
│   │   ├── components/       # Shared components (41 files)
│   │   ├── stores/           # Pinia stores (auth, paper, quota, paperJobs)
│   │   ├── api/              # Axios API client
│   │   ├── composables/      # Vue composables (useI18n, etc.)
│   │   ├── style.css         # Global CSS + design tokens
│   │   └── App.vue / main.ts
│   ├── tailwind.config.js    # Color system: navy, cream, ash, ivory, anthracite, ink, gold
│   └── vite.config.ts
├── deploy/
│   └── paperfull.conf        # Nginx config (SSE routes, caching, security headers)
└── ecosystem.config.cjs      # PM2 process manager config
```

## Key APIs
- `POST /api/papers/<id>/slr/jobs` — Start SLR job
- `GET /api/slr/jobs/<id>` — Poll SLR status
- `GET /api/slr/jobs/<id>/stream` — SSE stream for SLR progress
- `POST /api/papers/<id>/generate-stream` — SSE paper generation
- `POST /api/chat/` — SSE AI chat
- `POST /api/tools/rubric` — SSE rubric analysis
- `GET/POST /api/papers` — Paper CRUD
- `GET /api/papers/<id>/literature` — Literature items

## Color System (Tailwind)
- **navy** — primary brand (CTA, headings, sidebar)
- **cream** — light mode surfaces/panels
- **ash** — dark mode surfaces (blue-dark tint)
- **ivory** — paper-like backgrounds
- **anthracite** — warm dark text
- **ink** — cool gray chrome
- **gold** — accents, badges, premium highlights

## Known Fixed Bugs (2026-07-15)

### Round 1
- B1: `_push_count` race condition in SLR → added `_push_count_lock`
- B2: `_jobs` dict declared twice (line 71 & 2605) → removed duplicate
- F1: CSS vars `--cream-600`/`--cream-700` missing → added to `:root`
- Visual polish: Login, Dashboard, Landing, AppHeader upgraded

### Round 2
- SEC-1: Payment callback `_verify_snap_signature()` always returned `True` → HMAC-SHA512 verification
- SEC-3: `_COLUMNS` in db_cache.py → marked `Final[str]` to prevent SQL injection risk
- BUG-5: `generate_qris()` double-parse `request.get_json()` → removed duplicate
- BUG-6: Payment `_token_cache` race condition → added `_token_lock`
- BUG-7: Payment `db.session.commit()` → `safe_commit()` for deadlock retry
- BUG-8: Payment callback status '07'/'09' mapped as `failed` → corrected to `pending`
- BUG-9: Nginx `client_max_body_size` 1100M → 110M (aligned with Flask 100MB)

## Security Notes
- `v-html` in ChatMessage/PaperfullTab → already sanitized via `useSanitize()` composable
- `v-html` in ToolWorkspace → safe (manual HTML escape in `renderGrammarOutput()`)
- `v-html` in ContentList → safe (KaTeX renderer output)
- JWT: httpOnly cookies + CSRF double-submit + cookie-secure
- Payment: HMAC-SHA512 signature verification + IDOR guard
- CORS: explicit origins only (no wildcard)
