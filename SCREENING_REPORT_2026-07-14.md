# SCREENING REPORT — papergenerator (2026-07-14)

Screening lengkap (READ-ONLY, belum ada perubahan source). Fokus: PDF/tabel,
streaming AI chat, generate image (AG+Codex), dan bug lain.

## STATUS: SCREENING BERJALAN (sub-agent area SLR/translator/payment/frontend masih jalan)

## A. BUG KRITIS — STREAMING AI CHAT TIDAK MUNCUL
Lokasi: deploy/paperfull.conf
- Route `/api/chat/` (POST SSE dari backend chat.py) masuk ke block general
  `location /api/` (baris 166) yang MENGAKTIFKAN:
    proxy_cache paperfull_cache;
    proxy_cache_valid 200 5s;
  dan TIDAK men-set `proxy_buffering off`.
- Akibatnya nginx MEM-BUFFER response SSE sampai selesai baru dikirim → token
  tidak muncul progressive (atau baru muncul semua di akhir / gagal).
- Bukti: route SSE lain (`/api/generate`, `generate-stream`, `slr/jobs/.../stream`)
  SEMUA punya `proxy_buffering off; proxy_cache off; chunked_transfer_encoding on;`
  tapi `/api/chat/` tidak.
- Backend chat.py sudah benar: yield `_sse("text", ...)` progressive, frontend
  chat.ts `_handleSSEEvent` case 'text' benar (`msg.content += data.content`).
- FIX: tambah block khusus
    location /api/chat/ { ... proxy_buffering off; proxy_cache off; chunked_transfer_encoding on; }

## B. BUG KRITIS — GENERATE IMAGE (AG & CODEX)
Lokasi: backend/tools/image_generation/image_api_v2.py
- BARIS 133: header `"Authorization: Bearer ***"` → API key di-HARDCODE literal
  `***` (bukan API_KEY env). Provider AG SELALU gagal 401.
  Bukti: API_KEY dibaca dari env (baris 43) tapi tidak dipakai di _call_ag.
- Provider list default & env: `cloudflare,alibaba,ag` (IMAGE_GEN_PROVIDERS di
  .env = cloudflare,alibaba,ag). User minta HANYA `ag,codex`.
- image_api_v2.py BELUM punya provider `codex` (OpenAI gpt-image-1).
- CreateImageGemini.py hanya Gemini (tidak ada Codex).
- FIX:
  1. Baris 133 → `f"Authorization: Bearer {API_KEY}"`.
  2. Tambah provider `codex` (OpenAI images/generations, model gpt-image-1)
     di PROVIDER_MODELS + _call_codex + _call_provider dispatch.
  3. Set IMAGE_GEN_PROVIDERS=ag,codex di .env.
  4. Hapus cloudflare/alibaba dari default (atau set via env).

## C. BUG — TABEL SALAH DI PREVIEW PDF
Lokasi: backend/tools/Journal/_docx_base.py  (dipakai banyak journal incl IEEE default)
- add_table (baris ~839-882):
  - Baris 845: `if not headers: return` → tabel TANPA header LANGSUNG DI-SKIP
    (tidak muncul di PDF) → "preview banyak yang salah dari tabel".
  - Baris 857: `table = doc.add_table(rows=len(rows)+1, cols=len(headers))`.
    Loop row (872-880) pakai `if column_index >= len(headers): break` →
    * row lebih panjang dari header → data terpotong (kolom hilang).
    * row lebih pendek dari header → kolom kosong (tidak dipadatkan).
    Tidak ada normalisasi panjang row → tabel tidak sejajar / rusak saat
    LibreOffice render.
- Inkonsistensi antar gen: IJITEEgen.add_table pakai `row_data[:len(headers)]`
  (aman), tapi _docx_base & banyak gen lain pakai `break` (rawan).
- FIX: normalisasi setiap row ke len(headers) (pad/truncate), dan beri default
  header kalau kosong agar tabel tetap muncul.

## D. AREA LAIN (di-screen sub-agent, menunggu laporan)
- backend/tools/Literatur/* (SLR pipeline)
- frontend/src/* (Vue components/views/stores)
- backend/tools/paraphrase, translator, humanizer, payment, data/chart, admin,
  chat(non-stream), ai_tools, quota, core

## CATATAN
- 24 file modified (uncommitted) — ada pekerjaan tengah jalan (termasuk
  tools_api.py tambah endpoint /api/tools/rubric, paraphrase +70 baris,
  payment/doku dirombak). Tidak diubah selama screening.
- Endpoint baru /api/tools/rubric (SSE) juga butuh proxy_buffering off di nginx
  (masuk block /api/ → buffering ON). Perlu ditambahkan ke whitelist.
