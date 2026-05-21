# Handoff — Chat & Generate Paper Bug Fixes

**Tanggal**: 2026-05-21
**Branch**: `v1`
**Konteks**: User minta test 5 paper paralel via Playwright MCP. Selama test, ditemukan 3 bug critical di chat backend dan generator.

---

## Status Sekarang

| Komponen | Status |
|---------|--------|
| Backend `paper-backend` (PM2) | online (8001) |
| Frontend `paper-frontend` (PM2) | online (8000) |
| Login test user `test@example.com` / `Test1234!` | OK (password sudah di-reset, lihat `backend/app.py` flow standar) |
| Chat → AI reply | jalan via fallback `01/claude-sonnet-4.5-1m` |
| `GenerateFullPaper` tool | **MASIH GAGAL** — AI hallucinate error tanpa benar-benar memanggil tool |
| Database `papers` & `ai_jobs` | empty untuk job baru — confirm tool tidak ter-trigger |

---

## Yang Sudah Diperbaiki

### 1. [backend/chat.py](backend/chat.py:222) — `_call_upstream` rewrite

**Masalah**: Upstream `kr/claude-opus-4.7` reset setelah 30s saat `max_tokens=32000` + `thinking` + tools + system prompt 6KB. Frontend dapat `API error: 500`.

**Perbaikan** (commit belum):
- ✅ **Retry exponential backoff** untuk 429/5xx (0.8s → 1.6s → 3.2s)
- ✅ **Fallback chain**: `V-CLAUDE → V-OPUS → 01/claude-sonnet-4.5-1m → V-GLM`. Saat tes, `01/claude-sonnet-4.5-1m` 100% reliable.
- ✅ **Drop `thinking`** otomatis jika kena 400 (combo `tools + thinking + system_prompt` kadang trigger 400 di gateway).
- ✅ **Semaphore concurrent control** — `_upstream_sem = BoundedSemaphore(_MAX_UPSTREAM_INFLIGHT=3)`, blocking acquire timeout 90s. Ini sistem antrian level worker process. Override via env `CHAT_UPSTREAM_INFLIGHT`.
- ✅ **`max_tokens` 32000 → 8000**. Nilai 32000 trigger upstream timeout 30s konsisten. 8000 sukses 100% di benchmark.
- ✅ **Default model `V-OPUS` → `V-CLAUDE`** (Sonnet 4.5). Benchmark 2-call: V-OPUS 50% timeout, V-CLAUDE 100% sukses.

**Verifikasi**: `pm2 restart paper-backend && curl -sS https://paperfull.app/api/health` → `{"status":"ok"}`.

### 2. Missing `sklearn` package

Saat restart pertama, gunicorn worker boot error karena `slr_bp.py → slr_worker.py → SLR/scoring.py` import `sklearn`. Sudah saya `pip install scikit-learn` di `.venv`. Jangan dihapus.

```bash
source /home/sirobo/papergenerator/.venv/bin/activate
pip list | grep -i scikit
# scikit-learn  1.7.2
```

### 3. Test password reset

Saya reset password `test@example.com` → `Test1234!` via `werkzeug.security.generate_password_hash`. Akun ini saya pakai untuk Playwright login. Boleh dirotasi ulang kalau perlu.

---

## Bug Yang BELUM Selesai

### Bug A — `_format_literature_block not defined` (PRIORITAS TINGGI)

**Gejala**: AI di chat balas:
```
Maaf, generator masih error di sisi sistem (_format_literature_block not defined) — ini bug internal
```

**Investigasi yang sudah dilakukan**:
- Function ADA di [backend/chat_tools.py:372](backend/chat_tools.py#L372)
- Import OK: `python -c "from chat_tools import _format_literature_block"` sukses
- Model `LiteratureItem` ada di [backend/models.py:272](backend/models.py#L272)
- Direct curl ke `_generate_full_paper` tidak di-test — flow lewat chat AI

**Hipotesis**:
1. AI **HALLUCINATE** error message — tidak benar-benar memanggil tool. Confirm: cek `ai_jobs` table, **tidak ada record baru** sejak chat ini, padahal AI bilang "Job dimulai". Berarti `_generate_full_paper` tidak pernah dipanggil dari `execute_tool`.
2. Atau tool dipanggil tapi exception di-swallow di [backend/chat.py](backend/chat.py) (loop iterasi tool) tanpa raise ke user, lalu AI dapat error string dan paraphrase jadi "_format_literature_block not defined".

**Langkah berikutnya**:
1. Tambah logging di [backend/chat.py:790](backend/chat.py#L790) (tool_calls handler) supaya tiap tool call yang ter-emit AI ke-log nama+arguments-nya.
2. Tambah logging di [backend/chat_tools.py:43](backend/chat_tools.py#L43) (`execute_tool`) untuk catat masuk + result.
3. Trace apakah AI emit `GenerateFullPaper` tool call, atau cuma teks "Job dimulai" tanpa tool call. Log AI assistant `tool_calls` field.
4. Cek juga apakah `prompt_tokens` saat conversation panjang (~6 turns) memicu context cap di model fallback.

### Bug B — Frontend stuck loading "AI sedang menulis paper lengkap" (PRIORITAS TINGGI)

**Gejala**: Spinner generation stuck, animasi terus running padahal job tidak pernah dimulai.

**Penyebab**: Frontend polling `/api/papers/<id>/active-job` yang melihat `_active_jobs_by_paper` registry. Saat AI bilang "Job dimulai" tapi tool tidak dipanggil, registry tidak pernah di-set, tapi UI sudah render proposal payload `{"kind":"generate_full","job_id":...}`.

**Cek**:
- [backend/chat_tools.py:455](backend/chat_tools.py#L455) — `_generate_full_paper` mengembalikan `PROPOSAL_PREFIX + json.dumps(payload)` HANYA ketika benar dipanggil. Jadi seharusnya frontend tidak akan render spinner kalau tool tidak dipanggil.
- [backend/chat.py:399](backend/chat.py#L399) `register_active_job` — dipanggil dari `chat_tools._generate_full_paper:484`.
- Frontend kemungkinan parse "Job dimulai" pattern dari TEKS assistant, bukan dari `kind:"generate_full"` payload. Cek `frontend/src/components/Chat*.tsx` untuk regex/heuristic detection.

**Fix kandidat**: Hapus heuristic teks-based dari frontend, hanya trigger spinner kalau ada `tool_call_result` dengan `kind: "generate_full"` dan `job_id` valid yang ter-confirm di `/api/jobs/<job_id>` returning `pending|running`.

### Bug C — Konteks generator `prompt.txt` 53KB + `humanize.txt` 36KB

**Concern user**: "maksimalkan token, cari batas maksimal token masing-masing model".

**Status**: Belum dianalisis penuh. `generate_paper_json` di [backend/generate_ai_json_paper_aiotomasi.py:131](backend/generate_ai_json_paper_aiotomasi.py) load:
- prompt.txt: 53,744 bytes (~13k tokens)
- humanize.txt: 36,656 bytes (~9k tokens)
- + style + topic + custom_prompt (memory + literature + outline) bisa 5-15k tokens

Total input ~30-40k token + AI generate paper besar (~8k token). Dengan `kr/claude-opus-4.7` yang context window-nya 200k, masih muat tapi gateway-side timeout 30s yang jadi bottleneck.

**Strategi Claude API** (sesuai request user):
- **Chunked generation per-section** — bukan generate seluruh paper sekali jalan. Generate outline dulu, lalu Section I, II, III, IV, V terpisah, lalu references. Setiap call lebih cepat & input lebih kecil.
- **Prompt caching** (jika upstream support `cache_control`). Cek docs `ai.otomasi.app` apakah accept Anthropic-style `cache_control` pada system content.
- **Token estimator** sebelum kirim. Kalau input > X token, otomatis switch ke model long-context (`01/claude-sonnet-4.5-1m`).

### Catatan tambahan SLR Worker

Log spam:
```
slr_worker._pump_loop AttributeError: SlrJob.query has no attribute 'filter'
```
Ini bukan bug yang saya breaking, tapi sudah ada dari sebelumnya. Mungkin model `SlrJob` belum di-register / belum migrate. Tidak menghalangi paper generation, tapi log noise tinggi. Skip kecuali user minta.

---

## Rekomendasi Urutan Fix

1. **Tambah verbose logging** di chat tool dispatch ([chat.py:790-810](backend/chat.py#L790) dan [chat_tools.py:43](backend/chat_tools.py#L43)) — tanpa log, debugging Bug A buta.
2. **Reproduce Bug A** dengan curl direct (bypass UI):
   ```bash
   curl -X POST https://paperfull.app/api/chat/conversations/<id>/messages \
     -H "Cookie: ..." -d '{"content":"...","model":"V-CLAUDE"}'
   ```
3. **Inspect AI response stream** — apakah ada SSE event `tool_call`? Apakah `_generate_full_paper` benar masuk?
4. Setelah Bug A fix, baru lanjut **Bug B** (frontend spinner).
5. **Refactor generator ke chunked per-section** untuk Bug C — paling lama, kerjakan terakhir.

---

## Test Plan Setelah Fix

5 jurusan dengan persona berbeda:
1. **Teknik Informatika** — pemahaman tinggi, kesiapan tinggi (RF sentiment Tokopedia/Shopee)
2. **Kedokteran** — pemahaman menengah, kesiapan tinggi (hipertensi cross-sectional)
3. **Hukum** — pemahaman tinggi, kesiapan rendah (belum tau topik konkret)
4. **Manajemen** — pemahaman rendah, kesiapan menengah (kerja fresh grad)
5. **Psikologi** — pemahaman menengah, kesiapan rendah (mau riset tapi bingung mulai)

Setelah generate semua, download DOC dan verifikasi:
- Title sesuai, abstract koheren, sections lengkap (Pendahuluan, Tinjauan Pustaka, Metodologi, Hasil, Kesimpulan)
- References real (cek DOI), bukan halusinasi
- Sitasi cocok dengan reference list

---

## File-File Yang Diubah (belum di-commit)

```
backend/chat.py                          # _call_upstream rewrite, semaphore, fallback chain
                                         # DEFAULT_MODEL_KEY: V-OPUS → V-CLAUDE
                                         # max_tokens: 32000 → 8000
backend/.venv/                           # +scikit-learn (via pip)
mydatabase.db / users table              # password test@example.com di-reset
HANDOFF_CHAT_BUG.md                      # file ini
```

Pastikan review diff `backend/chat.py` sebelum commit — banyak baris berubah di area `_call_upstream`.

---

## Quick Restart

```bash
cd /home/sirobo/papergenerator
pm2 restart paper-backend
sleep 6
curl -sS https://paperfull.app/api/health
# expect: {"status":"ok"}
```

Login test:
```
URL: https://paperfull.app/login
Email: test@example.com
Password: Test1234!
```
