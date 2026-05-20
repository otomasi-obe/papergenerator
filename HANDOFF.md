# PaperFull — Audit & Refactor Handoff Report

**Tanggal**: 2026-05-20
**Branch**: `v1`
**Commit terakhir**: `58f84fd`, `9a57a24`
**Status**: Backend & frontend running di PM2, 11/11 E2E test passed

---

## 📊 Quick Status

| Service | Status | Port | Notes |
|---------|--------|------|-------|
| `paper-backend` | online | 8001 | Gunicorn 4w × 8t, JSON logging |
| `paper-frontend` | online | 8000 | proxy-server.cjs hardened |
| PostgreSQL | ok | 5432 | 9 tabel, 21 index, JSONB di papers.data |
| `/api/health` | 200 | — | Liveness probe |
| `/api/healthz` | 200 | — | DB + disk readiness |
| `/api/metrics` | 200 | — | Prometheus exposition |
| `/api/openapi.yaml` | 200 | — | 19.7KB spec |
| `/api/docs` | 200 | — | Swagger UI (CDN) |

---

## ✅ Yang Sudah Selesai (Sesi 2026-05-20)

### Commit `9a57a24` — Security Hardening + Observability + Blueprint Refactor

**P0 Security**
- Rotate `JWT_SECRET_KEY`, `SECRET_KEY`, `SIGNED_URL_SECRET` di `backend/.env`
  - Backup di `backend/.env.bak.20260520-161211`
  - Git history bersih, `.env` sudah di `.gitignore`
- JWT migrate dari `localStorage` → **httpOnly cookies + CSRF double-submit**
  - Access token 1 jam, refresh token 7 hari (rotating)
  - Cookie flags: `httpOnly`, `Secure`, `SameSite=Lax`, `JWT_COOKIE_CSRF_PROTECT=True`
  - CSRF header: `X-CSRF-TOKEN` dari cookie `csrf_access_token` / `csrf_refresh_token`
  - Endpoint baru: `POST /api/auth/refresh` (rotating refresh)

**Operational hardening**
- `frontend/proxy-server.cjs`:
  - `process.on('uncaughtException'/'unhandledRejection')` handlers
  - `ECONNREFUSED` → `503 + Retry-After: 5`
  - Kill upstream saat client abort
  - Hapus log spam per-request
- `backend/gunicorn.conf.py`:
  - `post_fork` excepthook untuk silence `SystemExit(0)` shutdown noise (gthread + Py3.10 atexit race)

**Observability (file baru `backend/observability.py`)**
- `JSONFormatter` — single-line JSON log untuk Loki/ELK
- `X-Request-ID` correlation di setiap response
- Prometheus metrics: `http_requests_total`, `http_request_duration_seconds`, `http_requests_in_flight`, `ai_generation_total`
- `/api/healthz` — deep readiness (DB SELECT 1 + disk free check)
- `/metrics` endpoint Prometheus exposition format

**Database (no downtime)**
- 6 index baru via `CREATE INDEX CONCURRENTLY`:
  - `ix_papers_user_id`
  - `ix_paper_images_user_id`
  - `ix_paper_files_user_id`
  - `ix_conversations_user_paper`
  - `ix_chat_messages_conv_created`
  - `ix_api_usage_logs_user_created`

**Architecture (app.py 1279 → 742 LoC, -42%)**
- `backend/papers_bp.py` (145 LoC) — CRUD + cascade delete
- `backend/files_bp.py` (227 LoC) — upload/list/delete/raw/preview
- `backend/images_bp.py` (201 LoC) — paper images + sign URL + image serve
- `backend/paper_utils.py` (81 LoC) — `PAPER_ID_RE`, `safe_paper_dir`, signed token, magic-byte sniff

**Frontend refactor**
- `frontend/src/api/index.js` — `withCredentials: true`, single-flight refresh interceptor, CSRF auto-attach
- `frontend/src/stores/auth.js` — hapus token state, pakai cookies
- `frontend/src/stores/chat.js` — SSE pakai `credentials: 'include'` + CSRF
- `frontend/src/views/AuthCallbackPage.vue` — tidak baca `?token=` dari URL
- `frontend/src/views/LoginPage.vue` — hapus `auth.setToken`
- `FilesTab.vue`, `PreviewTab.vue` — hapus `?t=token` di image/file URL

### Commit `58f84fd` — OpenAPI + JSONB + E2E

**API Contract**
- `backend/openapi.yaml` — OpenAPI 3.1 spec lengkap (Auth/Papers/Files/Images/Generation/Export/Admin/Health/Metrics)
- `/api/openapi.yaml` serve YAML spec
- `/api/docs` serve Swagger UI dari CDN (jsdelivr) dengan request interceptor auto-CSRF

**Database — JSONB Migration**
- `ALTER TABLE papers ALTER COLUMN data TYPE jsonb USING data::jsonb` (18 rows)
- `ix_papers_data_gin` GIN index dengan `jsonb_path_ops` (CONCURRENTLY)
- `models.py` — import `JSONB` dari `sqlalchemy.dialects.postgresql`, switch `Paper.data` ke JSONB
- Backup: `/tmp/papers_backup_20260520-175101.sql`

**Testing**
- `frontend/playwright.config.js` (Chromium, baseURL: localhost:8000, retain-on-failure)
- `frontend/e2e/smoke.spec.js` (10 tests):
  - landing page renders
  - login page form visible
  - `/api/health` 200
  - `/api/healthz` schema valid
  - `/api/metrics` Prometheus format
  - `/api/papers` 401 (auth required)
  - `/api/auth/login` bad creds 401
  - `/api/openapi.yaml` valid
  - `/api/docs` Swagger UI mounts
  - Security headers present (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `X-Request-ID`)
- `frontend/e2e/auth.spec.js` (1 comprehensive test):
  - register → cookies (httpOnly + CSRF) → `/me` → list papers empty
  - CSRF reject without header → CSRF allow with header
  - refresh rotates tokens → logout → 401 after
- `npm run test:e2e` ready
- `frontend/.gitignore` — exclude test artifacts

---

## 🔧 Konfigurasi Penting

### File baru
```
backend/papers_bp.py          (145 LoC)
backend/files_bp.py           (227 LoC)
backend/images_bp.py          (201 LoC)
backend/paper_utils.py        (81 LoC)
backend/observability.py      (185 LoC)
backend/openapi.yaml          (709 LoC)
frontend/playwright.config.js
frontend/e2e/smoke.spec.js
frontend/e2e/auth.spec.js
frontend/.gitignore
```

### Endpoint paths
```
/api/auth/register     POST    public
/api/auth/login        POST    public
/api/auth/google/login GET     public
/api/auth/google/callback GET  public (sets cookies)
/api/auth/refresh      POST    refresh-cookie required, rotates
/api/auth/me           GET     auth required
/api/auth/logout       POST    public (clears cookies)

/api/papers            GET/POST       papers_bp
/api/papers/<id>       GET/PUT/DELETE papers_bp
/api/papers/<id>/files          GET/POST   files_bp
/api/papers/<id>/files/<fid>    DELETE     files_bp
/api/papers/<id>/files/<fid>/raw GET       files_bp (signed URL ok)
/api/papers/<id>/files/<fid>/preview GET   files_bp
/api/papers/<id>/images         GET/POST   images_bp
/api/papers/<id>/images/<iid>   DELETE     images_bp
/api/papers/<id>/sign           POST       images_bp (mint signed URL)
/api/images/<id>/<filename>     GET        image_serve_bp

/api/admin/users    GET admin role required
/api/admin/papers   GET
/api/admin/usage    GET
/api/admin/stats    GET

/api/health         GET liveness
/api/healthz        GET readiness (DB + disk)
/metrics            GET Prometheus
/api/metrics        GET Prometheus (alias for proxy)
/api/openapi.yaml   GET spec
/api/docs           GET Swagger UI
```

### Database state
- **Total tabel**: 9 (`users`, `papers`, `paper_images`, `paper_files`, `conversations`, `chat_messages`, `project_memory`, `ai_jobs`, `api_usage_logs`)
- **Total index**: 21 (PK + 14 manual)
- **Row count saat audit**: users=9, papers=18, conversations=21, chat_messages=38, project_memory=15
- **JSONB columns**: `papers.data` (dengan GIN index `ix_papers_data_gin`)

---

## 🚧 Yang Belum Selesai (Backlog)

### P1 — Should do
1. **Pagination cursor-based** untuk `/api/papers`, `/api/admin/users`, `/api/admin/papers`
   - Saat ini offset-based (sudah pakai `limit`/`offset`)
   - Better: opaque cursor (created_at + id)
2. **Alembic migration tool**
   - Saat ini `db.create_all()` di app boot, no versioning
   - Setup `alembic init` + first migration sebagai baseline
3. **Redis** untuk rate limit + AiJob queue
   - Saat ini `RATELIMIT_STORAGE_URI=memory://` (per-worker, tidak konsisten)
   - AiJob storage di DB (works, tapi polling)
   - Migrate ke Redis Streams atau Celery + RabbitMQ
4. **CAPTCHA di `/api/auth/register`**
   - Cloudflare Turnstile (gratis) atau hCaptcha
   - Cegah spam akun
5. **Backup PostgreSQL otomatis**
   - Cron `pg_dump` harian + WAL archive
   - Off-site backup (S3 / B2 / rclone)

### P2 — Nice to have
6. **nginx di depan `proxy-server.cjs`**
   - gzip/brotli, cache static asset, rate limit per-IP
   - Let's Encrypt auto-renew
7. **OpenTelemetry tracing**
   - Distributed trace ke Jaeger / Tempo
   - Lengkapi observability stack yang sudah dimulai
8. **Grafana + Prometheus** stack di server
   - Visualize metrics yang sudah ter-expose
   - Dashboard RED method (Rate, Errors, Duration)
9. **Frontend code splitting**
   - Saat ini bundle 199KB main + 381KB PaperEditorPage
   - Lazy load AdminPage, FilesPage
10. **jsonschema validation untuk `papers.data`**
    - Di-skip karena polymorphic
    - Solusi: discriminated union schema per stage (draft → final)

### P3 — Future
11. **Quota per user** (token / paper count by role)
12. **Multi-language paper template** (ACM, Springer, jurnal nasional)
13. **Paper versioning** (`paper_versions` table dengan diff)
14. **Collaborative editing** (CRDT / OT)
15. **Image client-side compression** sebelum upload
16. **i18n** (Indonesia + English)
17. **Frontend test** (Vitest untuk komponen)
18. **Pre-commit hook** (gitleaks + bandit + ruff + eslint)

---

## ⚠️ Things to Know (Gotcha)

### Konsekuensi dari refactor
- **Semua user existing harus login ulang** (rotate JWT secret + format change ke cookie)
- **Token lifetime**: 30 hari → 1 jam access + 7 hari refresh (auto-refresh seamless)
- **OPENAI_API_KEY, GOOGLE_CLIENT_SECRET, AIOTOMASI_APIKEY** belum di-rotate (perlu manual via dashboard provider)
- **DB password** belum di-rotate (user pilih scope minimal)

### Files modified tapi belum di-commit (dari sebelum session ini)
```
backend/prompt/topic/*.txt           (banyak file template)
backend/prompt/journal/*.txt
backend/prompt/style/*.txt
backend/searchPaper.py
backend/chat.py
backend/chat_tools.py
backend/admin.py
backend/extract_pdfs.py
backend/generate_*.py
backend/template/*
ai/, prompt/, output/, exports/
.kilo/agent-manager.json
IEEE_*.docx
```
Ini bukan dari kerja session ini — Anda decide kapan/apa yang mau di-commit.

### PM2 restart count
- `paper-backend`: 21× (mostly clean SIGINT dari restart manual saya)
- `paper-frontend`: 27× (sebelum hardening proxy-server.cjs)
- Setelah hardening, restart count akan stabil

---

## 🔑 Cara Verify Setelah Restart Server

```bash
# 1. PM2 status
pm2 list

# 2. Health checks
curl -sf http://localhost:8001/api/health
curl -sf http://localhost:8001/api/healthz

# 3. Metrics
curl -s http://localhost:8001/api/metrics | head -20

# 4. OpenAPI + Swagger UI
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8001/api/openapi.yaml
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8001/api/docs

# 5. E2E tests
cd /home/sirobo/papergenerator/frontend
npm run test:e2e

# 6. DB state
PGPASSWORD=papergenerator123 psql -h localhost -U papergenerator -d papergenerator \
  -c "\dt" -c "\di public.ix_*"
```

---

## 📞 Cara Lanjut di Chat Berikutnya

Buka chat baru di Claude Code, paste paragraf ini:

> Saya melanjutkan audit/refactor PaperFull. Branch v1, commit terakhir 58f84fd. Backend & frontend running di PM2, 11/11 E2E test passed. Baca /home/sirobo/papergenerator/HANDOFF.md untuk full context, lalu lanjutkan dengan task ini: [PILIH SATU dari backlog P1/P2/P3 di file]

Contoh task starter:

- **"setup Alembic migration sebagai baseline"** — P1 #2
- **"pasang Cloudflare Turnstile di register"** — P1 #4
- **"setup pg_dump cron + rclone ke S3"** — P1 #5
- **"setup nginx di depan proxy-server.cjs dengan gzip + Let's Encrypt"** — P2 #6
- **"setup Grafana + Prometheus stack via Docker compose"** — P2 #8
- **"frontend code splitting + lazy load route"** — P2 #9

---

**End of handoff report.**
