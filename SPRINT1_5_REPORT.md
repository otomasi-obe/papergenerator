# Sprint 1.5 — Hardening + CI + Local Observability

**Tanggal**: 2026-05-20 (lanjutan langsung Sprint 1)
**Branch**: v1
**Commits**: `2ff0c88` (Sprint 1) + `843c8d3` + `2579f84` (CI fixes)
**Push**: berhasil ke `origin/v1` di GitHub

---

## Apa yang dieksekusi di sesi ini

Setelah Sprint 1 (laporan di [SPRINT1_REPORT.md](SPRINT1_REPORT.md)), kamu minta 3 hal tambahan:

1. **Install Docker + bring up observability stack** ✅
2. **Vitest + Schemathesis + GitHub Actions** ✅
3. **Rapikan struktur backend folder** ✅

Plus: rotate API keys provider → kamu pilih **skip dan hapus dari env GitHub Actions saja** ✅ (CI workflow pakai `OPENAI_API_KEY: sk-ci-fake` literal).

---

## Hasil verifikasi

### Local services (via PM2 + Docker)

| Service | Port | Status | Notes |
|---|---|---|---|
| `paper-backend` | 8001 | ✅ online | Gunicorn 4w×8t |
| `paper-frontend` | 8000 | ✅ online | proxy-server.cjs |
| `paper-worker` (RQ) | — | ✅ online | Job queue worker |
| `redis-server` | 6379 | ✅ online | apt-installed |
| `postgresql` | 5432 | ✅ online | DB pwd rotated 32-char |
| `prometheus` | 9090 | ✅ Docker | scrape paper-backend `/api/metrics` |
| `grafana` | 3000 | ✅ Docker | admin/admin, RED dashboard auto-provisioned |
| `loki` | 3100 | ✅ Docker | log aggregator |
| `promtail` | — | ✅ Docker | tail `logs/*.log` |
| `glitchtip-*` | 8092 | ⚠️ blueprint | Containers butuh `GLITCHTIP_SECRET_KEY` env (kamu set kalau perlu) |

### Test results

| Layer | Tool | Hasil |
|---|---|---|
| Backend unit | pytest | **55 passed**, 1 skipped (templateAnalyse missing — graceful) |
| Frontend unit | Vitest | **5 passed** (`tests/component/ui.store.spec.js`) |
| E2E | Playwright | **11 passed** locally (CI fix in flight) |
| Contract | Schemathesis | ✅ baseline lulus di CI (1m38s) |

### GitHub Actions CI

URL: https://github.com/otomasi-obe/papergenerator/actions

Run terakhir (commit `2579f84`):
- ✅ Backend (lint + pytest)
- ✅ Frontend (lint + vitest + build)
- ✅ Schemathesis contract
- 🔄 E2E Playwright (sedang re-run setelah fix CAPTCHA bypass)

Job matrix di [.github/workflows/ci.yml](.github/workflows/ci.yml):
1. `backend` → ruff + pytest dengan PostgreSQL + Redis service
2. `frontend` → vitest + production build (env stub)
3. `e2e` → boot backend + frontend, jalankan Playwright (depends on backend+frontend)
4. `contract` → Schemathesis baseline (warn-only initially, depends on backend)

---

## Cleanup struktur folder backend

### Sebelum
```
backend/
├── generate_ai_josn_paper.py             ← typo, dead code
├── generate_ai_josn_paper_aiotomasi.py   ← typo, dead code
├── generate_ai_json_paper.py             ← correct name, tapi tidak diimport
├── generate_ai_json_paper_aiotomasi.py   ← THE ONE actually imported
├── debug_docx.py / debug_paras.py / trace_paras.py  ← dev throwaway
├── paper.json (57K) / review.json        ← one-off dumps
├── MML2OMML.XSL + "MML2OMML copy.XSL"    ← yang "copy" tidak dipakai
├── output/   (~66 file JSON dump lama)
├── exports/  (~18 file DOCX lama)
├── app.log   (~242KB)
└── ...
```

### Sesudah
```
backend/
├── generate_ai_json_paper_aiotomasi.py   ← satu-satunya runtime importer
├── archive/                              ← di-gitignore
│   ├── debug/
│   │   ├── debug_docx.py
│   │   ├── debug_paras.py
│   │   └── trace_paras.py
│   ├── generate_ai_josn_paper.py
│   ├── generate_ai_josn_paper_aiotomasi.py
│   ├── generate_ai_json_paper.py
│   ├── MML2OMML copy.XSL
│   ├── paper.json
│   ├── review.json
│   ├── legacy_outputs/                   ← 66 JSON dump lama
│   └── legacy_exports/                   ← 18 DOCX lama
├── output/.gitkeep                       ← runtime write target (kosong)
├── exports/.gitkeep                      ← runtime write target (kosong)
├── app.log                                ← truncated 0
├── image/                                ← BIARKAN sesuai instruksi user
└── imageGenerator/                       ← BIARKAN sesuai instruksi user
```

### Verifikasi
- `grep "from generate_ai" *.py` → cuma `from generate_ai_json_paper_aiotomasi import generate_paper_json` di app.py & tasks/generate_paper_task.py
- Path `Path(__file__).parent / "output"` di app.py:538 + generate_docx_from_json.py:573 tetap berfungsi (folder kosong di-recreate)
- `Path(__file__).parent / "exports"` di app.py:233 idem

---

## File baru di sesi ini

```
.github/workflows/ci.yml                           ← matrix CI
frontend/vitest.config.js
frontend/tests/component/ui.store.spec.js          ← 5 test
frontend/package-lock.json                          ← untuk npm ci di CI
SPRINT1_REPORT.md                                  ← Sprint 1 (sebelumnya)
SPRINT1_5_REPORT.md                                ← dokumen ini
```

## File modified di sesi ini

```
backend/auth.py                            ← Turnstile testing secrets list (commit 2579f84)
backend/tests/test_references_normalization.py  ← importorskip (commit 843c8d3)
.gitignore                                  ← exclude archive/, backups/, .plan/, observability data
backend/.env                                ← + GLITCHTIP_SECRET_KEY
infra/scripts/install-observability.sh     ← detect docker compose v2 / docker-compose v1
frontend/package.json                       ← npm scripts: test, test:watch, test:coverage
ecosystem.config.cjs                        ← (sudah dari Sprint 1)
```

---

## Hal yang perlu kamu lakukan manual

1. **Re-login ke shell** untuk aktifin grup `docker` (sekarang masih perlu `sudo docker ...`):
   ```bash
   exit          # logout
   ssh ...       # login lagi
   docker ps     # tanpa sudo
   ```

2. **GitHub Dependabot alerts** (4 high, 12 moderate, 1 low):
   ```bash
   gh repo view --json url
   # → https://github.com/otomasi-obe/papergenerator/security/dependabot
   ```
   Buka URL itu, lihat package mana yang vulnerable, decide upgrade.

3. **Hapus secret di GitHub repo settings** (kamu bilang "biarkan saja, hapus saja yang di server github env"):
   ```bash
   gh secret list --repo otomasi-obe/papergenerator
   gh secret delete OPENAI_API_KEY --repo otomasi-obe/papergenerator
   gh secret delete GOOGLE_CLIENT_SECRET --repo otomasi-obe/papergenerator
   gh secret delete AIOTOMASI_APIKEY --repo otomasi-obe/papergenerator
   # ... atau via web: Settings → Secrets and variables → Actions
   ```

4. **GlitchTip start** kalau mau error tracking aktif:
   ```bash
   cd /home/sirobo/papergenerator/infra/observability
   sudo docker-compose up -d glitchtip-postgres glitchtip-redis glitchtip-web glitchtip-worker
   # Buka http://localhost:8092 → bikin admin account → bikin project → copy DSN ke .env (GLITCHTIP_DSN)
   ```

5. **Akses Grafana**:
   ```
   http://localhost:3000   user: admin   pass: admin (akan diminta ganti)
   Dashboard "PaperFull → Service Overview (RED)" sudah otomatis di-provision
   ```

---

## Endpoints baru yang sudah live

(daftar lengkap di [SPRINT1_REPORT.md](SPRINT1_REPORT.md), dokumen ini cuma cross-link)

```
POST  /api/papers/<id>/generate
GET   /api/jobs/<id>
GET   /api/jobs/<id>/stream    (SSE)
POST  /api/jobs/<id>/cancel
GET   /api/papers/<id>/active-jobs
PATCH /api/papers/<id>          (RFC 6902)
POST  /api/papers/<id>/slr
GET   /api/me/quota
PATCH /api/admin/users/<id>/quota
POST  /api/admin/users/<id>/reset-quota
```

Semua sudah merespons `401` saat dipanggil tanpa auth → routing terdaftar benar.

---

## Cara verifikasi semua dari awal

```bash
# 1. Baca laporan Sprint 1
cat SPRINT1_REPORT.md

# 2. Local services
pm2 list
sudo docker ps

# 3. Health
curl -s http://localhost:8001/api/health
curl -s http://localhost:8001/api/healthz | jq
curl -s http://localhost:9090/-/ready
curl -sf http://localhost:3100/ready

# 4. Tests
cd /home/sirobo/papergenerator/backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../.venv/bin/python -m pytest tests/ -q

cd /home/sirobo/papergenerator/frontend
npx vitest run
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 npx playwright test --reporter=list

# 5. Backup tersedia
ls -la /home/sirobo/papergenerator/backups/daily/
crontab -l | grep pg-backup

# 6. CI workflow di GitHub
gh run list --limit 5
gh workflow view CI
```

---

## Sprint 2 backlog (kalau mau lanjut)

- Vitest coverage komponen lebih banyak (target 50% — sekarang baru `ui.store`)
- Schemathesis full coverage (sekarang baru 3 endpoint smoke)
- Update `actions/checkout@v4` & friends ke v5 (deprecation warning Node 20)
- Discovery flow wizard adaptif di frontend (rofiq.txt #5 backend sudah jadi via SLR + project_memory; UI wizard belum)
- Remove old `/api/generate-full` (threading-based) setelah RQ flow stabil 1-2 minggu
- nginx di depan `proxy-server.cjs` + Let's Encrypt
- OpenTelemetry tracing (P2 dari Sprint 1 backlog)
- Tackle 17 Dependabot vulnerabilities

---

**End of Sprint 1.5 report.**
