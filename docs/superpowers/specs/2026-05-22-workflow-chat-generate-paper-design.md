# Workflow Chat + Generate Paper — Design Spec

**Tanggal:** 2026-05-22
**Status:** Draft, menunggu review user
**Scope:** Chat workflow, generate paper progress, branching path user, empty state, notifikasi.

## 1. Konteks

Paper Generator saat ini memaksa semua user lewat 7-step linear (jurusan → topik → latar belakang → literatur → metode → data → confirm) walau user sudah punya literatur, metode, atau data dari project sebelumnya. Selain itu, generate paper jalan async 5-15 menit via 7 chunks (outline + 5 sections + references), tapi progress hanya tampil sebagai banner toolbar yang hilang saat user pindah paper / reload. Kalau ada error di chunk ke-5, semua chunk sebelumnya hilang.

Spec ini menetapkan workflow baru yang **branching, persistent, dan resumable**.

## 2. Tujuan

- User bisa skip step yang sudah punya jawabannya (literatur / metode / data).
- Progress generate paper tetap terlihat saat pindah paper / reload / device.
- Cancel atau error tidak menghilangkan chunk yang sudah selesai.
- User dapat tau paper selesai walau lagi di paper lain.
- Empty state chat tidak bingungin user baru.

## 3. Keputusan Brainstorm

| # | Area | Keputusan |
|---|---|---|
| 1 | Progress UI | Sticky bubble di chat dengan progress bar + label fase (Outline / Section I-V / References) |
| 2 | Persistensi | DB-backed (`AiJob`), polling tiap 3s |
| 3 | Branching | AI tanya 1x dengan 4 chip: Mulai 0 / Sudah literatur / Sudah metode / Sudah data |
| 4 | Chip render | Generic component, AI kirim metadata `{chips: [{label, value}, ...]}` |
| 5 | Cancel/error | Partial save + resume per section + retry |
| 6 | Empty state | Hero "Mau buat paper apa?" + 4 chip path + 3 quick prompt |
| 7 | Notifikasi | Toast + badge + browser Notification API |

## 4. Arsitektur

### 4.1 Tabel & State Backend

**Reuse:** `AiJob` (`backend/models.py:241`) sudah ada dengan kolom: `id, user_id, paper_id, kind, status, progress, stage, prompt, result, error, timeout, started_at, updated_at`.

**Mapping ke design ini (tanpa migration):**
- `stage` → simpan fase sekarang: `'outline' | 'section_1' .. 'section_5' | 'references' | 'combine'`.
- `result` (JSON) → simpan: `{partial_paper: {...}, chunks_done: ['outline', 'section_1', ...], last_error_chunk: 'section_3' | null}`.
- `status` value baru: tambah `'paused'` ke enum (sekarang: `queued|running|done|error|cancelled`).
- `error` → error message terakhir untuk chunk yang fail.

**Migration ringan (opsional, untuk query speed):**
- Tambah `paused_at DateTime nullable` kalau perlu sort/filter paused jobs.

Strategi ini menghindari migration berat — semua data tambahan masuk ke kolom JSON `result` yang sudah ada.

**Endpoint baru:**

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/papers/{id}/ai-jobs/active` | Job aktif untuk paper ini (status running/paused/queued) |
| POST | `/api/ai-jobs/{job_id}/cancel` | Cancel job, save partial |
| POST | `/api/ai-jobs/{job_id}/resume` | Resume dari chunk berikutnya |
| POST | `/api/ai-jobs/{job_id}/retry-section` | Retry chunk yang error |
| GET | `/api/me/ai-jobs/recent?status=done` | Untuk badge inbox global |

### 4.2 Generate Paper Flow

```
User klik "generate full paper"
  → backend create AiJob(status=queued, phase=outline, progress=0)
  → return job_id ke chat sebagai bubble metadata {kind: 'paper_progress', job_id}
  → background worker pick up:
    - Phase outline → update phase, progress=10, save partial
    - Phase section_1 → update phase, progress=25, save partial
    - ...
    - Phase combine → progress=100, status=done

Kalau error di chunk N:
  → status=paused, error_message set, partial_result tersimpan
  → frontend tampilkan tombol Retry section / Skip section / Discard

Kalau cancel:
  → status=cancelled, partial_result tersimpan
  → frontend tampilkan tombol Resume / Discard
```

### 4.3 Frontend State

**Store baru:** `frontend/src/stores/paperJobs.js`

```js
state: {
  activeJobByPaper: Map<paperId, JobState>,
  recentDoneJobs: JobSummary[],  // untuk badge global
}

actions: {
  startPolling(paperId)       // poll /api/papers/{id}/ai-jobs/active tiap 3s
  startGlobalPolling()         // poll /api/me/ai-jobs/recent untuk badge
  cancel(jobId)
  resume(jobId)
  retrySection(jobId)
}
```

**Polling lifecycle:**
- `startPolling(paperId)` dipanggil saat `PaperEditorPage` mount + saat ada bubble dengan `kind=paper_progress` masuk chat.
- Stop polling saat status final (done/error/cancelled) atau user pindah paper.
- Global polling jalan terus selama user login (untuk badge & toast cross-paper).

### 4.4 Chat Bubble Sticky

Chat message punya schema `metadata.kind = 'paper_progress'` dengan `job_id`.

Render logic di `ChatTab.vue`:
- Cari message dengan `kind=paper_progress` yang status non-final.
- Render di posisi sticky di bawah list pesan (di atas input box).
- Auto-collapse jadi mini-banner kalau user scroll up dari bubble.
- Setelah job done, bubble jadi "✓ Paper generated, klik Preview".

### 4.5 Action Chips (Generic)

**Schema metadata message:**

```json
{
  "kind": "chips",
  "chips": [
    {"label": "Mulai dari 0", "value": "start_zero"},
    {"label": "Sudah ada literatur", "value": "has_literature"},
    {"label": "Sudah ada metode", "value": "has_method"},
    {"label": "Sudah ada data", "value": "has_data"}
  ],
  "context": "user_state_detection"
}
```

Component: `frontend/src/components/ActionChips.vue`. Klik chip → inject `value` sebagai user message + auto-send.

AI kirim metadata via tool call baru: `ProposeChips({chips, context})` — frontend tangkap di stream handler dan attach ke message.

### 4.6 Branching Workflow di `chat.py`

Update SYSTEM_PROMPT:

```
SAAT CHAT BARU DIMULAI (tidak ada history):
1. Call GetMemory + GetLiterature
2. Kalau memory + literatur kosong → call ProposeChips dengan 4 path:
   start_zero / has_literature / has_method / has_data
3. Kalau ada data, langsung kirim chips:
   "Saya lihat kamu sudah punya N literatur dan metode tersimpan.
    Mau lanjut dari sini, atau review dari awal?"
   chips: [continue_from_step_X, restart_from_zero]

Berdasarkan chip yang dipilih:
- start_zero      → STEP 1 (jurusan)
- has_literature  → STEP 5 (metode), karena step 1-4 sudah dibahas
- has_method      → STEP 6 (data)
- has_data        → STEP 7 (confirm)
```

### 4.7 Empty State Chat

Saat `messages.length === 0` di `ChatTab.vue`:

```
┌─────────────────────────────────┐
│  Mau buat paper apa?            │
│                                 │
│  [Mulai dari 0]                 │
│  [Sudah ada literatur]          │
│  [Sudah ada metode]             │
│  [Sudah ada data]               │
│                                 │
│  ─── atau ─────                 │
│                                 │
│  • Lanjutkan dari memory        │
│  • Pakai literatur yang ada     │
│  • Lihat draft saya             │
└─────────────────────────────────┘
```

Klik chip atau quick prompt → inject sebagai user message + send.

### 4.8 Notifikasi Selesai

3 channel:
1. **Toast bottom-right** (existing toast component, extend untuk action button "Buka").
2. **Badge angka** di tombol "💬 AI Chat" di toolbar — count dari `recentDoneJobs.length`.
3. **Browser Notification API** — request permission saat user klik "generate paper" pertama kali. Kalau granted, fire `new Notification(...)`.

Trigger: global polling detect job baru pindah ke `status=done` → broadcast event.

## 5. Komponen Baru / Diubah

### Backend

| File | Perubahan |
|---|---|
| `backend/models.py` | Tambah `'paused'` ke comment status di `AiJob`. Optional: `paused_at` column |
| `backend/alembic/versions/xxx_ai_job_paused_at.py` | Migration tipis (kalau pakai `paused_at`) |
| `backend/generate_paper_chunked.py` | Tulis partial_result + update progress per chunk; support resume dari chunks_done |
| `backend/jobs_bp.py` | Endpoint baru: GET active per paper, POST cancel/resume/retry, GET recent |
| `backend/chat.py` | SYSTEM_PROMPT: branching logic + ProposeChips call |
| `backend/chat_tools.py` | Tool baru `ProposeChips`, sudah ada GetMemory & GetLiterature |

### Frontend

| File | Perubahan |
|---|---|
| `frontend/src/stores/paperJobs.js` | **Baru**: store untuk active + recent jobs, polling |
| `frontend/src/components/ActionChips.vue` | **Baru**: render chip array generic |
| `frontend/src/components/PaperProgressBubble.vue` | **Baru**: sticky bubble dengan progress bar + cancel/retry |
| `frontend/src/components/ChatTab.vue` | Empty state hero, attach ProgressBubble, render ActionChips dari metadata |
| `frontend/src/components/ChatMessage.vue` | Render metadata.chips kalau ada |
| `frontend/src/components/AppHeader.vue` | Badge inbox global |
| `frontend/src/views/PaperEditorPage.vue` | Pakai paperJobs store untuk badge "pending" yang sudah ada |

## 6. Edge Case

- **User start generate, langsung tutup tab.** → Backend tetap jalan via worker, polling resume saat user buka lagi. ✓
- **User cancel di tengah Section III, mau Resume tapi prompt sudah berubah (e.g. literatur baru ditambah).** → Resume reuse outline + section sebelumnya, tapi section III dan setelahnya regenerate dengan context terbaru. Risk: inconsistency antara section. Mitigasi: warning saat resume "Konteks sudah berubah, hasil mungkin tidak konsisten dengan section sebelumnya. Mau tetap resume atau full regenerate?"
- **Multiple jobs untuk paper sama.** → Backend reject job baru kalau sudah ada job non-final untuk paper tersebut. Frontend disable tombol "generate" + tampilkan "Job lain sedang jalan".
- **Browser notif permission denied.** → Toast + badge tetap jalan. Tidak ada error.
- **Polling jalan saat user offline.** → Standar fetch error, retry dengan backoff. Setelah 3 fail, stop polling sampai window focus event.
- **Chip dipilih saat `value` tidak match.** → Backend handle gracefully (default ke STEP 1 dengan note "tidak terdeteksi state, mulai dari awal").

## 7. Testing

**Backend:**
- Unit test `_generate_paper_chunked`: verify partial_result tersimpan setelah tiap chunk.
- Test resume: kill worker di chunk 3, restart, verify chunk 1-2 tidak di-redo.
- Test cancel: cancel di chunk 3, verify partial_result tersimpan, status=cancelled.

**Frontend:**
- Component test `PaperProgressBubble`: render fase yang benar dari job.phase.
- Component test `ActionChips`: klik chip emit value yang benar.
- Component test `ChatTab` empty state: render hero saat messages kosong.
- E2E test (Playwright kalau ada): full generate flow + reload mid-way + verify progress restored.

## 8. Out of Scope (Tidak Dikerjakan Sekarang)

- Edit-after-generate dengan diff preview accept/reject.
- Data input modal (Excel/CSV upload).
- Citation validator [L1]..[Ln] matching.
- Light-mode polish & dark token consistency audit.
- Keyboard shortcut (Cmd+K, Cmd+S).
- Image generation queue position display.

Item-item di atas dibahas di spec terpisah.

## 9. Rencana Rollout

1. Migration + backend endpoint + worker partial save.
2. Frontend store + PaperProgressBubble + integrate ke ChatTab.
3. Action chips component + ProposeChips tool + branching SYSTEM_PROMPT.
4. Empty state hero.
5. Notifikasi (toast + badge + browser API).
6. Manual QA + acceptance test.

Tiap step harus pass build + tidak break existing chat. Migration backward-compatible.

## 10. Acceptance Criteria

- [ ] User generate paper → reload browser → progress bubble masih muncul dengan fase & % yang sama.
- [ ] User cancel di Section III → klik Resume → Section III regenerate, Section I-II tidak.
- [ ] User pindah paper saat generate → balik lagi → progress bubble masih jalan.
- [ ] Paper selesai saat user di paper lain → toast muncul + badge bertambah.
- [ ] Chat baru dengan literatur kosong + memory kosong → 4 chip path muncul, klik chip "Sudah ada metode" → AI skip ke STEP 6.
- [ ] Empty state chat tampil hero dengan 4 chip + 3 quick prompt.
- [ ] Browser notif fire saat permission granted dan paper selesai.
