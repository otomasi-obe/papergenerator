# Changelog

All notable changes to PaperFull (papergenerator) are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

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
