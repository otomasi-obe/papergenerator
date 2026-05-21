# Workflow Chat + Generate Paper — Design Spec

**Tanggal:** 2026-05-22 (revised)
**Status:** Draft v2, menunggu review user
**Scope:** Token-efficient chat routing, auto-memory, chunked paper generation resilience, SLR completeness, branching workflow, persistent progress.

## 1. Konteks

Audit code menemukan masalah struktural yang harus dibereskan sekaligus:

1. **Token waste parah.** "halo" satu kata = 13.4 KB ke API (~3,300 tokens). Penyebab: full SYSTEM_PROMPT 7.4 KB + 9 tool schemas 4.7 KB (floor `_BASE_TOOLS`). Tiap turn re-ship semuanya.
2. **Memory tidak auto.** AI harus eksplisit panggil `SaveMemory` setiap step → boros token + sering forget. Memory juga di-prefetch ke system prompt **setiap turn** (boros lagi).
3. **Generate paper chunked tidak resilient.** Section chunks masih 90 KB prompt (claim "minimal" salah). Chat path tidak set `paper_id` di `AiJob`, no progress persistence, no cancel, no resume, no partial save. Dua pipeline paralel: chat (chunked tanpa progress) vs REST (legacy 90 KB tapi punya progress).
4. **SLR works tapi punya bug whitelist.** `V-DEEPSEEK` ditolak di SLR. AI summary silently skip tanpa signal UI saat env kosong.
5. **Workflow linear.** User dipaksa lewat 7 step walau sudah punya literatur/metode/data.

Solusinya **terintegrasi** karena (1) menentukan struktur tool routing yang akan dipakai (2)(3)(4)(5).

## 2. Tujuan

- Wire bytes per turn turun **>90%** untuk turn casual.
- AI tidak perlu eksplisit panggil `SaveMemory` lagi — backend auto-extract.
- Generate paper bisa cancel/pause/resume/retry tanpa kehilangan chunk yang sudah selesai.
- User bisa skip step yang sudah punya jawabannya.
- Progress generate paper persisten lintas reload/device.
- SLR jalan dengan model apapun yang dipilih user.

## 3. Arsitektur Tool Routing — "Tier-0 RouteIntent + Mode Bundles"

### 3.1 Konsep

Setiap turn, payload upstream HANYA berisi:
- **Mini system prompt** (~100 bytes, 1 baris)
- **Tier-0 tool**: `RouteIntent` (1 tool, ~400 bytes) — HANYA ada saat router belum tahu mode
- **Mode-specific bundle** (sekitar 1-3 KB) — saat router sudah klasifikasi user intent
- Memory block injected **hanya turn pertama** atau saat user explicitly minta `lihat ingatan`.

```
                    ┌────────────────────────────────────┐
                    │  user msg                           │
                    └────────────────────────────────────┘
                                   │
                                   ▼
                    ┌────────────────────────────────────┐
                    │  auto-memory extractor (regex+LLM)  │
                    │  saves facts BEFORE main call       │
                    └────────────────────────────────────┘
                                   │
                                   ▼
                    ┌────────────────────────────────────┐
                    │  mode resolver:                     │
                    │  - read conv.metadata.mode          │
                    │  - if missing → use Tier-0 mode     │
                    └────────────────────────────────────┘
                                   │
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                     ▼
       Tier-0 (mini)         Mode bundle               Edit/SLR/etc
       1 tool (Route-        (full tools for           (mode-specific)
       Intent), 100B         that mode)
       sysprompt
```

### 3.2 Modes & Tool Bundles

| Mode | System prompt size | Tools | Total bytes | Use case |
|---|---:|---|---:|---|
| `tier0` | ~120 B | `RouteIntent` only | ~520 B | First turn, classification, casual chat |
| `discovery` | ~2 KB (steps 1-7 condensed) | `RunSLR`, `GetLiterature`, `ListAttachedFiles`, `ReadAttachedFile`, `GenerateFullPaper`, `ProposeChips` | ~3.5 KB | 7-step workflow |
| `slr` | ~800 B | `RunSLR`, `GetLiterature`, `SearchPapers`, `ListAttachedFiles`, `ReadAttachedFile` | ~3.1 KB | "carikan literatur" / SLR run |
| `edit` | ~1 KB | `GetPaperContent`, `GetPaperSection`, `Propose*` (6), `RequestExportDocx` | ~3 KB | Edit existing paper |
| `rapikan` | ~600 B | `GetPaperContent`, `GetPaperSection`, `GetPaperNumbering`, `ProposeSection` | ~1.6 KB | Renumber Fig./Table/Eq. |
| `memory` | ~300 B | `ListMemory`, `DeleteMemory` (no SaveMemory — auto-extracted) | ~700 B | "lihat ingatan", "lupakan X" |

`SaveMemory` **dihapus** dari tool list. `GetMemory` dihapus dari tool list (memory di-inject ke system prompt saat needed). `ListMemory`/`DeleteMemory` tetap ada untuk mode `memory`.

### 3.3 RouteIntent Tool Schema

```json
{
  "name": "RouteIntent",
  "description": "Classify user message intent into a mode. Call this FIRST when mode is unknown. After this returns, the next turn will receive the mode-specific tools and prompt.",
  "parameters": {
    "type": "object",
    "properties": {
      "mode": {
        "type": "string",
        "enum": ["discovery", "slr", "edit", "rapikan", "memory", "casual"]
      },
      "reasoning": {
        "type": "string",
        "description": "1-line why."
      }
    },
    "required": ["mode"]
  }
}
```

**Flow saat AI panggil RouteIntent:**
1. Backend dapat `mode` value dari tool call.
2. Persist ke `Conversation.metadata = {mode, mode_set_at}`.
3. Re-call upstream dengan mode bundle (sysprompt + tools mode tersebut).
4. AI lanjut dengan context yang lebih kaya.

**Flow saat sudah ada `conversation.metadata.mode`:**
1. Skip Tier-0 entirely.
2. Langsung kirim mode bundle.
3. **Mode bisa berubah** — kalau user bilang "kembali ke awal" atau intent tiba-tiba beda, AI bisa panggil `RouteIntent` lagi (Tier-0 sentinel), backend reset mode.

### 3.4 Mini System Prompt (Tier-0)

```
You are PaperFull's academic-paper assistant. Match user's language (default ID).
First, classify intent by calling RouteIntent. Be concise.
```

Itu saja. ~120 bytes.

### 3.5 Mode-Specific System Prompts

Setiap mode punya prompt fokus. Contoh `discovery` mode:

```
You are guiding the user through a 7-step discovery to plan their paper.

Steps: jurusan → topik → latar belakang → literatur → metode → data → confirm.
ASK ONE QUESTION PER MESSAGE. Use ProposeChips to give 3-4 option chips.
Skip steps the user already answered (memory injected below shows what's known).

After step 7, call GenerateFullPaper.
```

`memory` block diinject di bawah system prompt **hanya saat masuk mode pertama kali** atau saat AI minta `GetMemory`. **Tidak setiap turn lagi.**

## 4. Auto-Memory Extraction

### 4.1 Hook Point

Di `backend/chat.py:733`, **setelah** `db.session.commit()` user msg, **sebelum** `def generate()`:

```python
db.session.commit()  # existing — user msg saved

# NEW: auto-extract facts from user reply
extracted = _auto_extract_facts(
    paper_id=conv.paper_id,
    user_id=user_id,
    conv=conv,
    user_msg=content,
    last_assistant_msg=_get_last_assistant_msg(conv.id)
)
# extracted: List[{key, value, kind, confidence}]
# Each fact upserted via existing _save_memory() helper.

def generate():
    ...
```

### 4.2 Hybrid Strategy

**Layer 1 — Regex (fast, free):**
- Detect `[OPSI]` patterns and option-reply (`"1"`, `"pilih 2"`, `"yang ketiga"`).
- Detect explicit `"ingat: X"`, `"simpan ini: X"` patterns.
- Detect AI's last question's `[key=...]` marker (parse from sysprompt template).
- Match user reply against expected key.

**Layer 2 — LLM fallback (only when):**
- Last assistant msg announced a specific key.
- Regex didn't extract that key.
- Use V-DEEPSEEK (cheap, fast).
- Tight prompt: `"From this user reply to question about <key>, return JSON {value: string} | null. No prose."`
- Output capped 64 tokens.

**Confidence filter:** only upsert if extracted value non-empty AND value isn't a system-y phrase (`"oke"`, `"lanjut"`, `"yes"`).

### 4.3 Memory Scope — Add `conversation_id` FK

Migration tipis di `ProjectMemory`:

```sql
ALTER TABLE project_memory
  ADD COLUMN conversation_id VARCHAR(20) NULL
    REFERENCES conversations(id) ON DELETE CASCADE;
CREATE INDEX ix_project_memory_conv ON project_memory(conversation_id);

-- existing rows: conversation_id stays NULL = paper-scoped (legacy/manual)
-- new auto-extracted rows: conversation_id = conv.id

-- replace old unique:
ALTER TABLE project_memory DROP CONSTRAINT uq_project_memory_paper_key;
CREATE UNIQUE INDEX uq_project_memory_paper_key_global
  ON project_memory(paper_id, key) WHERE conversation_id IS NULL;
CREATE UNIQUE INDEX uq_project_memory_paper_conv_key
  ON project_memory(paper_id, conversation_id, key)
  WHERE conversation_id IS NOT NULL;
```

**Behavior:**
- Auto-extracted facts → `conversation_id = conv.id` (chat-scoped, deleted with chat).
- Manual via `ListMemory`/UI manual edit → `conversation_id = NULL` (paper-scoped, persist).
- AI prefetches: `WHERE paper_id = X AND (conversation_id IS NULL OR conversation_id = current)`.

**Chat delete cleanup** (`chat.py:642`):

```python
# Cascade FK already drops chat-scoped memory; just delete conv:
db.session.delete(conv)
db.session.commit()
```

### 4.4 Memory Injection Strategy (Token Saving)

**Sekarang (boros):** `chat.py:1071-1073` inject memory tiap turn.

**Baru:**
- Inject memory **hanya saat masuk mode pertama kali** (`is_first_turn_in_mode = True`).
- Inject memory **saat user explicitly minta** ("ingatan?", "apa yang kamu ingat").
- Inject memory **saat AI panggil GetMemory tool** (kept for `memory` mode).

Untuk turn biasa di tengah workflow: tidak inject (AI sudah tahu dari turn sebelumnya).

## 5. Generate Paper — Resilience Overhaul

### 5.1 Unifikasi Dua Pipeline

**Sekarang:**
- Chat path: `chat_tools._generate_full_paper` → `app._run_generate_full_job` (thread) → `generate_paper_json_chunked()`. Chunked tapi no progress/cancel.
- REST path: `jobs_bp.enqueue_generate` → RQ worker → `tasks/generate_paper_task.py` → `generate_paper_json()` (legacy 90 KB single call). Punya progress/cancel.

**Setelah:**
- **Satu pipeline:** RQ worker pakai `generate_paper_json_chunked()` dengan checkpoint callback.
- Chat path push job ke RQ queue (sama kayak REST path), dapat `job_id`.
- Frontend polling endpoint sama untuk chat-initiated dan REST-initiated.

### 5.2 Checkpoint Callback di Chunked Orchestrator

Modifikasi `backend/generate_paper_chunked.py:505-626`:

```python
def generate_paper_json_chunked(
    custom_prompt,
    *,
    checkpoint_cb=None,  # NEW: called after each chunk
    cancel_check=None,   # NEW: returns True to abort
    resume_state=None,   # NEW: dict with chunks_done, partial_paper
    **kwargs
):
    state = resume_state or {"chunks_done": [], "partial_paper": {}}

    def _checkpoint(stage, percent, partial):
        state["chunks_done"].append(stage)
        state["partial_paper"] = partial
        if checkpoint_cb:
            checkpoint_cb(stage=stage, progress=percent, partial=partial)
        if cancel_check and cancel_check():
            raise GenerationCancelled(stage)

    if "outline" not in state["chunks_done"]:
        outline = _generate_outline(...)
        partial = {"outline": outline, ...}
        _checkpoint("outline", 10, partial)

    for i in range(1, 6):
        chunk_id = f"section_{i}"
        if chunk_id in state["chunks_done"]:
            continue  # resume: skip already-done sections
        section = _generate_section(i, outline, ...)
        partial["sections"].append(section)
        _checkpoint(chunk_id, 10 + i*15, partial)

    if "references" not in state["chunks_done"]:
        refs = _generate_references(...)
        partial["references"] = refs
        _checkpoint("references", 90, partial)

    if "combine" not in state["chunks_done"]:
        result = _combine(partial)
        _checkpoint("combine", 100, result)
        return result
```

### 5.3 AiJob Schema Mapping (No Heavy Migration)

Reuse `AiJob` (`backend/models.py:241`). Mapping ke design:

| Field | Value |
|---|---|
| `kind` | `'generate_paper'` |
| `paper_id` | **MUST be set** (currently NULL for chat path — bug) |
| `status` | `queued` / `running` / `paused` / `done` / `error` / `cancelled` (add `paused`) |
| `stage` | `outline` / `section_1` .. `section_5` / `references` / `combine` |
| `progress` | 0-100 |
| `result` (JSON) | `{partial_paper: {...}, chunks_done: [...], last_error_chunk: 'section_3' \| null}` |
| `error` | error message terakhir |

**Migration tipis:** dokumentasi `paused` value di docstring `AiJob.status`, tidak perlu schema change.

**Bug fix wajib:** `app.py:286-290` `_job_create` HARUS terima `paper_id` arg dan set ke row. Caller `chat_tools.py:643` HARUS pass `paper_id`.

### 5.4 Endpoints Baru

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/papers/{id}/ai-jobs/active` | Job non-final untuk paper ini |
| POST | `/api/ai-jobs/{job_id}/cancel` | Cancel running job, save partial |
| POST | `/api/ai-jobs/{job_id}/resume` | Resume dari `chunks_done` checkpoint |
| POST | `/api/ai-jobs/{job_id}/retry-section` | Retry chunk yang error/skip |
| GET | `/api/me/ai-jobs/recent?status=done&since=...` | Untuk badge inbox global |

**JANGAN delete `AiJob` row pada GET result** (`app.py:725-738` saat ini). Replace dengan `result_consumed_at` timestamp. Cleanup row >7 hari via cron.

### 5.5 Slim Section Prompts

Bug doc: chunk 2-6 masih kirim 90 KB. Fix:

- Extract section schema dari `prompt.txt` ke `prompt_section_only.txt` (~3 KB per section type).
- `humanize.txt` dipecah jadi `humanize_prose_only.txt` (~10 KB, rules untuk text saja, no figure/table/equation rules).
- `_generate_section` pass: outline + previous_sections context + section schema + humanize_prose. Total ~15 KB instead of 90 KB.

Ini membuat section chunk lebih cepat (target <30s per section, sekarang bisa 60s+ karena prompt besar).

### 5.6 Frontend `paper_progress` Message Kind

Backend kirim chat message dengan `metadata.kind = 'paper_progress'` saat generate dimulai:

```json
{
  "role": "assistant",
  "content": "🚀 Generating paper... (Outline)",
  "metadata": {
    "kind": "paper_progress",
    "job_id": "abc123",
    "stage": "outline",
    "progress": 10
  }
}
```

Frontend `ChatTab.vue` deteksi `metadata.kind === 'paper_progress'`, render `<PaperProgressBubble>` sticky di bawah message list. Bubble polling job tiap 3s, update fase + progress bar. Saat done, jadi bubble normal "✓ Paper generated, klik Preview".

### 5.7 Drop Chat-Wide Lock

`backend/chat.py:712-721` saat ini block ALL chat saat ada generate aktif. Salah.

Fix: hanya block panggil `GenerateFullPaper` lagi saat sudah ada job aktif untuk paper itu. User tetap bisa chat normal.

## 6. Branching Workflow di Discovery Mode

### 6.1 First Turn Detection

Saat masuk mode `discovery` pertama kali (chat baru, no message kecuali user msg pertama):

1. AI panggil `GetMemory` (sekarang internal call, belum di tool list discovery — kita add temporarily atau backend prefetch).
2. AI panggil `GetLiterature` untuk cek literatur ada/tidak.
3. AI cek `Paper.files` (untuk tau user upload file/tidak).
4. Berdasarkan state, AI panggil `ProposeChips` dengan opsi yang relevan.

**Skenario state:**
| Memory | Literature | Files | Chip suggestions |
|---|---|---|---|
| Empty | Empty | Empty | "Mulai dari 0" / "Sudah ada literatur (upload)" / "Sudah ada metode" / "Sudah ada data" |
| Has `jurusan, topik` | Empty | Empty | "Lanjut cari literatur" / "Saya upload file literatur" / "Skip literatur, langsung metode" |
| Has memory + Lit ≥10 | Has | Empty | "Lanjut ke metode" / "Tambah literatur lagi" / "Mulai ulang" |
| Has all + data | Has | Has | "Generate paper sekarang" / "Review dulu" / "Mulai ulang" |

### 6.2 ProposeChips Tool

Tool baru di `chat_tools.py`:

```python
{
    "name": "ProposeChips",
    "description": "Show user clickable option chips. Each chip becomes a user message when clicked.",
    "parameters": {
        "type": "object",
        "properties": {
            "chips": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "string"}
                    },
                    "required": ["label", "value"]
                },
                "minItems": 2,
                "maxItems": 6
            },
            "context_hint": {"type": "string"}
        },
        "required": ["chips"]
    }
}
```

Backend execute: tidak side-effect, return `{kind: 'chips', chips: [...]}` payload.

Frontend `ChatTab.vue` deteksi message dengan `metadata.kind === 'chips'`, render `<ActionChips>` di bubble. Klik chip = inject `value` sebagai user message + auto-send.

### 6.3 Empty State Hero (Frontend)

Saat `messages.length === 0` di `ChatTab.vue`:

```
┌──────────────────────────────────┐
│  Mau buat paper apa?             │
│                                  │
│  [Mulai dari 0]                  │
│  [Sudah ada literatur]           │
│  [Sudah ada metode]              │
│  [Sudah ada data]                │
│                                  │
│  ─── atau ketik bebas ───        │
│                                  │
│  • Lanjutkan dari memory         │
│  • Pakai literatur yang ada      │
│  • Lihat draft saya              │
└──────────────────────────────────┘
```

Klik chip / quick prompt → inject jadi user message + send. Backend handle normal (auto-extract + RouteIntent → discovery mode).

## 7. SLR Bug Fixes

### 7.1 V-DEEPSEEK Whitelist

**File:** `backend/slr_bp.py:171` & `backend/chat_tools.py:515`

```python
# Sekarang:
if model not in {"V-OPUS", "V-CLAUDE", "V-GPT", "V-GLM"}:
    model = "V-OPUS"

# Fix:
if model not in {"V-OPUS", "V-CLAUDE", "V-GPT", "V-GLM", "V-DEEPSEEK"}:
    model = "V-OPUS"
```

### 7.2 AI Summary Status Flag

**File:** `backend/SLR/summarizer.py` & `backend/SLR/pipeline.py`

Pipeline result tambah `stats.ai_summary_used: bool`. False kalau env kosong / fallback total ke extractive.

Frontend `LiteratureTab.vue` tambah badge "extractive only" kalau false di header tabel.

## 8. Komponen Baru / Diubah — Boundary Map

### Backend

| File | Perubahan | Owner agent |
|---|---|---|
| `backend/chat.py` | Mini sysprompt + mode resolver, drop chat-wide lock, hook auto-extract, gate memory injection | A |
| `backend/chat_tools.py` | Drop SaveMemory tool, add RouteIntent + ProposeChips, update tool dispatch | A |
| `backend/auto_memory.py` | **Baru**: regex+LLM extractor | B |
| `backend/mode_prompts.py` | **Baru**: mini sysprompt + per-mode prompts + mode-tool bundles | B |
| `backend/models.py` | Add `conversation_id` FK ke `ProjectMemory`, doc `paused` status | C |
| `backend/alembic/versions/xxx_memory_conv_fk.py` | Migration | C |
| `backend/generate_paper_chunked.py` | Add `checkpoint_cb`, `cancel_check`, `resume_state` params | D |
| `backend/app.py` | `_job_create` add `paper_id` arg, drop AiJob delete on GET | D |
| `backend/jobs_bp.py` | Endpoints baru: cancel/resume/retry-section, GET active per paper, GET recent done | D |
| `backend/tasks/generate_paper_task.py` | Switch ke chunked, wire checkpoint_cb ke `AiJob.stage`/`progress`/`result` | D |
| `backend/slr_bp.py` | V-DEEPSEEK whitelist | E |
| `backend/SLR/summarizer.py` | `ai_summary_used` flag | E |
| `backend/SLR/pipeline.py` | Pass flag through | E |
| `backend/prompt/prompt_section_only.txt` | **Baru**: slim section schema | D |
| `backend/prompt/humanize_prose_only.txt` | **Baru**: prose-only humanize rules | D |

### Frontend

| File | Perubahan | Owner agent |
|---|---|---|
| `frontend/src/components/ChatTab.vue` | Empty state hero, integrate ActionChips & PaperProgressBubble, drop SaveMemory display | F |
| `frontend/src/components/ChatMessage.vue` | Render `metadata.kind === 'chips'` & `paper_progress` | F |
| `frontend/src/components/ActionChips.vue` | **Baru** | F |
| `frontend/src/components/PaperProgressBubble.vue` | **Baru**: sticky bubble, progress bar, cancel/resume/retry buttons | G |
| `frontend/src/stores/paperJobs.js` | **Baru**: active job + recent jobs polling | G |
| `frontend/src/components/AppHeader.vue` | Badge inbox global (recent done jobs) | G |
| `frontend/src/components/LiteratureTab.vue` | "extractive only" badge if !ai_summary_used | E |
| `frontend/src/views/PaperEditorPage.vue` | Wire paperJobs store, toast+browser notif on done | G |

### Boundary Constraints
- **Agent A** owns chat.py + chat_tools.py (heavy edits, single agent untuk hindari konflik).
- **Agent B** writes new files only (auto_memory.py + mode_prompts.py), no overlap with A.
- **Agent C** owns models.py + alembic migration only.
- **Agent D** owns generate_paper_chunked.py + app.py + jobs_bp.py + tasks/. Heavy area, single agent.
- **Agent E** owns SLR fixes (small, scoped).
- **Agent F** owns ChatTab.vue + ChatMessage.vue + ActionChips.vue (frontend chat surface).
- **Agent G** owns PaperProgressBubble.vue + paperJobs.js + AppHeader.vue + PaperEditorPage.vue.

7 agents max paralel, no file overlap.

## 9. Edge Case

- **Mode switch mid-conversation.** User di `discovery` tiba-tiba bilang "rapikan figure". AI panggil `RouteIntent(mode=rapikan)` → next turn pakai bundle rapikan. Memory tetap accessible.
- **Auto-extract salah ekstrak fakta.** Confidence filter + log. Manual delete via UI.
- **Resume saat literatur baru ditambah.** Warning: "Konteks berubah, hasil section sebelumnya mungkin tidak konsisten. Resume / Full regenerate?".
- **Multiple papers concurrent generate.** Allowed. Tiap paper punya AiJob row terpisah.
- **Browser notif denied.** Toast + badge tetap jalan.
- **Polling offline.** Backoff retry 3x, lalu pause sampai `window focus` event.
- **Chip value tidak match.** Backend handle gracefully (treat as plain text user message).
- **Chat dihapus saat AiJob aktif.** AiJob tidak terhapus (FK `paper_id`, bukan `conversation_id`). Job lanjut sampai selesai.

## 10. Testing

### Backend

- Unit test auto-extractor: regex layer pada 20 sample replies (`"1"`, `"yang ketiga"`, `"Teknik Informatika"`, dst.).
- Unit test mode resolver: each mode loads correct tools + prompt size.
- Unit test checkpoint callback: chunk N saved, partial_paper accumulated, resume_state.chunks_done correct.
- Unit test cancel: raise `GenerationCancelled` di tengah chunk 3, verify partial sampai chunk 2 tersimpan.
- Unit test resume: feed `resume_state={chunks_done:['outline','section_1','section_2']}`, verify section 3-5 generate, section 1-2 skip.
- Integration test full chat flow: "halo" → RouteIntent → casual reply, byte budget <2KB.
- Integration test discovery flow: 7 step dengan auto-extract, verify all keys saved.
- Integration test SLR: "buatkan literatur review" → mode `slr` → RunSLR call → verify job dibuat.
- Integration test generate: "generate paper" → RQ job → checkpoint per chunk → verify AiJob.result.partial_paper berkembang.

### Frontend

- Component test `ActionChips`: klik chip emit value yang benar.
- Component test `PaperProgressBubble`: render fase yang benar dari job state.
- Component test `ChatTab` empty state: render hero saat messages kosong.
- E2E test: full generate flow + reload mid-way + verify progress restored + cancel + resume.

### Acceptance Criteria

- [ ] "halo" turn payload <2 KB.
- [ ] Auto-extract: user reply "1" untuk pertanyaan jurusan → `jurusan` ter-save tanpa AI panggil tool.
- [ ] Generate paper reload mid-section → bubble masih muncul, fase + % sama.
- [ ] Cancel di section 3 → resume → section 3-5 regenerate, 1-2 reused.
- [ ] Chat-wide lock dropped: user bisa chat sambil generate jalan.
- [ ] Empty state chat tampil hero + 4 chip + 3 quick prompt.
- [ ] Browser notif fire saat permission granted dan paper selesai.
- [ ] Mode bundle benar untuk tiap intent: discovery / slr / edit / rapikan / memory / casual.
- [ ] V-DEEPSEEK boleh dipakai SLR.
- [ ] AI summary "extractive only" badge muncul di Literature tab kalau env kosong.
- [ ] Delete chat → memory chat-scoped terhapus, paper-scoped tetap.

## 11. Out of Scope

- Edit-after-generate diff preview accept/reject (spec terpisah).
- Data input modal Excel/CSV (spec terpisah).
- Citation validator [L1]..[Ln] matching (spec terpisah).
- Light-mode polish & dark token consistency audit (spec terpisah).
- Keyboard shortcut (Cmd+K, Cmd+S).
- Image generation queue position display.

## 12. Rencana Rollout

Urutan kerja (paralel saat aman):

1. **Migration & schema** (Agent C) — landing dulu karena semua agent lain tergantung schema.
2. **Backend core paralel** (A, B, D, E):
   - A: chat.py + chat_tools.py refactor.
   - B: auto_memory.py + mode_prompts.py.
   - D: generate_paper_chunked + jobs_bp + app.py.
   - E: SLR fixes.
3. **Frontend paralel** (F, G):
   - F: ChatTab + ActionChips.
   - G: PaperProgressBubble + paperJobs store + AppHeader.
4. **Integration smoke test** — manual test flow chat → SLR → generate → reload.
5. **Build hijau** + lint + acceptance test.

Tiap step harus pass build + tidak break existing flow.

---

**End of spec.**
