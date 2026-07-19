# Changelog

All notable changes to PaperFull (papergenerator) are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [1.5.3] — 2026-07-20

### Added
- **Kritik & Saran (Feedback)**: tombol 💬 di AppHeader + `FeedbackModal.vue` + `Feedback` model (user_id, email, message, status) + endpoint submit/list (`/feedback`)
- **Developer Room access management**: `is_developer` flag di `User`, endpoint `/dev/list` + `/dev/add` (hanya `anabilhisyam23@gmail.com`), guard `requiresDev` di router + `isDeveloper` di auth store (ganti hardcode email)
- **Cancel generate-stream**: endpoint `POST /api/papers/<id>/cancel` set Redis cancel flag + update `AiJob` status, frontend `PaperfullTab.stopGeneration()` panggil API lalu abort SSE
- **Generate-stream progress events**: emit progress tiap ~2% / 50 token via SSE
- **paper-image-worker PM2 process**: `tools.image_generation.worker_runner` sebagai proses PM2 terpisah (restart_delay 5s, max_restarts 10)

### Fixed
- **Duplicate Dev button**: hapus tombol Dev ganda di AppHeader (satu di dropdown, satu standalone)
- **MaintenanceBanner**: tambah `onUnmounted` listener cleanup + event `maintenance-banner-updated` dari Dev Room
- **word-GPT-Plus submodule**: hide official API key settings (`officialAPIKey`/`officialBasePath`/`officialCustomModel`) + yarn lock refresh

### Changed
- **Image badge-tier models**: unify ke working GPT-5.5 + z-image untuk semua tier (elite/pro/starter/trial), drop Cloudflare models (HTTP 401)
- **Z-Image prompt**: extractive summarizer (3 kalimat) kalau prompt >400 char, fallback hard truncate

## [1.5.2] — 2026-07-18

### Fixed
- **AI reasoning + image progress via SSE**: `PaperfullTab` handle `thinking` / `content` / `progress` / `image_generation` SSE events — reasoning stream, JSON tokens, dan image progress render live
- **Image reconciliation race**: pindah ke background thread biar survive `GeneratorExit` (client disconnect) dan gak race frontend reload
- **Dark theme tokens**: unify `anthracite` → `ash` across components
- **Version-based cache-bust**: `main.ts` fetch `version-history.json` (no-store), bandingin `localStorage pf_version`, force reload sekali kalau mismatch → fix silent stale-index.html serving old chunks (Vite keep old hashed chunks, no ChunkLoadError fired)
- **Version bump**: `version-history.json` → 1.5.2

### Changed
- **Unified dark theme tokens** across all components

## [1.5.1] — 2026-07-18

### Fixed
- **stale chunk auto-reload**: `main.ts` + router catch `ChunkLoadError`/`Failed to fetch dynamically imported module` → auto reload once after deploy
- **nginx no-cache**: move no-cache headers to `location /` (cover all SPA routes)
- **vite localhost leak**: skip vue-vendor/katex in localhost scan
- **.env production**: `VITE_API_URL` empty (endpoints already prefixed `/api`)
- **last_seen throttle**: in-memory 60s throttle per worker (ponytail: Redis upgrade)
- **admin delete-log**: PaperDeleteLog model + `/admin/delete-log` endpoint, audit log before delete (title, user snapshot), online status dot (Active/last Xm/offline)
- **image-gen multi-model fallback**: cx/gpt-5.5-image → ag/gemini → alibaba/wan fallback with logging per attempt
- **dispatcher stuck jobs**: `_dispatched` set cleanup every poll cycle (fix stuck jobs <256)
- **SameFileError**: fix when out_path == dest (same dir)
- **dark mode UI**: ChatTab ash-800/60 bg + border + hover glow, FloatingChatButton panel bg lighten, TokenDetailModal SVG labels + padding + clip fix
- **login redirect localhost**: clean rebuild fix (cache issue)

### Added
- **badge tier system**: Trial/Starter/Pro/Elite with JOURNAL_TIERS (10/19/36/49), BadgeTier.vue component, locked items (🔒), auto-switch to IEEE on downgrade
- **MaintenanceBanner component**: site-wide maintenance notice
- **AdminPage improvements**: client-side pagination 50/page, search all users (limit=2000), Role+Tier badge chip, Delete Log tab with search
- **PRISMA flow in SLR**: statistics in job result
- **DOI dedup priority chain**: DOI→PMID→PMC→arXiv→S2→OpenAlex→Crossref→title fuzzy
- **canonical merge**: multi-source attribution, sources list, external IDs
- **reuse_port=False**: prevents orphan gunicorn workers
- **token deduction fix**: actual LLM calls not json.dumps
- **SLR improvements**: cap enforcement, dynamic timeout, orphan job sweep

### Removed
- **Rubric tool**: disabled from frontend TOOLS array, UI, and store logic

## [1.5.0] — 2026-07-17

### Fixed
- **Login redirect ke localhost:9001**: stale Vite build cache mengandung `VITE_API_URL=http://localhost:9001` dari sesi dev sebelumnya. Clean rebuild (`rm -rf node_modules/.vite dist`) memperbaiki. Tidak ada perubahan source code — murni cache issue.
- **Translator**: `ai_generate` args swap di line 280 — `detect_system` masuk ke slot prompt dan sebaliknya. AI detect bahasa mendapat instruksi bukan teks.
- **Paraphrase**: `_apply_synonyms` selalu return `changes: false` — regex hanya match base form exact, tidak handle inflected forms. Fix: inflection-aware regex dengan English morphology proper (`demonstrates`→`shows`, `utilizing`→`using`, `utilized`→`used`).
- **Plagiarism**: payload contract — `run_plagiarism` tidak return `text` + `result`, frontend dapat JSON string sebagai `outputText`. Fix: tambah `text` summary + `result` full object.
- **Plagiarism breakdown display**: non-fullscan mode (Offline/Web/AI Check) menampilkan `Offline: undefined% Web: undefined% AI: undefined%`. Fix: tampilkan `Verbatim/Paraphrased/Idea` untuk mode non-fullscan, `Offline/Web/AI` hanya untuk Full Scan.
- **AI Detector**: payload contract sama dengan plagiarism — `run_detector` return `text` summary + `result` full object.
- **Grammar**: subject-verb agreement hanya match `is`/`are`, tidak `was`/`were` → "results was", "they was" lolos. Fix: tambah pattern `was`/`were` untuk semua subject-verb rules. Tambah rule `its`/`it's` confused word.
- **Error v-if priority di ToolWorkspace**: `store.error` dicek setelah `!store.outputText && !store.toolResult` — saat error terjadi, output lama masih ada → error block dilewati, UI render output lama. Fix: pindah `v-else-if="store.error"` sebelum placeholder/output.
- **SLR**: enforce `top_n` cap, fix orphan workers, fix token deduction.
- **Dark mode**: floating AI chat + token detail chart dark mode fix.
- **Dark mode**: Open button border + token package hover glow.
- **Dashboard**: header height fix, empty search state, clear search button.

### Added
- **Build-time localhost leak check**: Vite plugin yang fail build kalau ada `localhost` reference di output — mencegah regression login redirect.
- **Dashboard UX**: snippet preview, search, sort, date tooltip.
- **Dashboard**: snippet always visible, search box visibility, New Paper glow.
- **Token packages**: pricing update + UI colors.

### Removed
- **Rubric tool**: disabled dari frontend TOOLS array, UI, dan store logic. Tool ini bukan untuk PaperFull (journal generation) — cocok untuk VIOLA (OBE/RPS). Backend code tetap ada, hanya di-hide di frontend.
