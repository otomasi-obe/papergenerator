# Implementation Plan — Workflow Chat + Generate Paper

**Spec:** `docs/superpowers/specs/2026-05-22-workflow-chat-generate-paper-design.md`
**Total agents:** 7 (A-G), boundary-isolated.

## Phase Order

```
Phase 0: Migration & schema (Agent C)        ← BLOCKING
Phase 1: Paralel
   ├─ 1a: Backend chat refactor (Agent A)    deps: B
   ├─ 1b: New backend modules (Agent B)
   ├─ 1c: Generate pipeline overhaul (Agent D)
   └─ 1d: SLR fixes (Agent E)
Phase 2: Paralel (after Phase 1)
   ├─ 2a: Frontend chat surface (Agent F)
   └─ 2b: Frontend progress + jobs (Agent G)
Phase 3: Integration smoke test (manual)
Phase 4: Lint + build green
```

## Constraints

1. No file overlap (boundary map below).
2. Migration backward-compatible.
3. Build hijau per phase before next.

## Boundary Map (No Overlap)

| File | Owner |
|---|---|
| `backend/models.py` | C |
| `backend/alembic/versions/<new>.py` | C |
| `backend/auto_memory.py` (new) | B |
| `backend/mode_prompts.py` (new) | B |
| `backend/chat.py` | A |
| `backend/chat_tools.py` | A (incl. SLR V-DEEPSEEK fix) |
| `backend/generate_paper_chunked.py` | D |
| `backend/app.py` | D |
| `backend/jobs_bp.py` | D |
| `backend/tasks/generate_paper_task.py` | D |
| `backend/prompt/prompt_section_only.txt` (new) | D |
| `backend/prompt/humanize_prose_only.txt` (new) | D |
| `backend/slr_bp.py` | E |
| `backend/SLR/summarizer.py` | E |
| `backend/SLR/pipeline.py` | E |
| `frontend/src/components/ChatTab.vue` | F |
| `frontend/src/components/ChatMessage.vue` | F |
| `frontend/src/components/ActionChips.vue` (new) | F |
| `frontend/src/components/PaperProgressBubble.vue` (new) | G |
| `frontend/src/stores/paperJobs.js` (new) | G |
| `frontend/src/components/AppHeader.vue` | G |
| `frontend/src/views/PaperEditorPage.vue` | G |
| `frontend/src/components/LiteratureTab.vue` | E (badge only) |

## Agent C — Phase 0 — Migration

Goal: chat-scoped memory + `paused` doc.

Tasks:
1. Add `conversation_id` FK ke `ProjectMemory` (`models.py:209-238`):
   - `String(20), FK(conversations.id, ON DELETE CASCADE), nullable=True, indexed`.
2. Drop `UniqueConstraint(paper_id, key)`.
3. Add 2 partial unique indexes:
   - `ix_pm_paper_key_global` on `(paper_id, key) WHERE conversation_id IS NULL`
   - `ix_pm_paper_conv_key` on `(paper_id, conversation_id, key) WHERE conversation_id IS NOT NULL`
4. Update `AiJob.status` docstring: add `'paused'`.
5. Migration `<rev>_memory_conv_fk_and_paused.py` (Alembic).
6. Test: `alembic upgrade head` + `downgrade -1`.

Acceptance:
- Existing rows readable (conversation_id=NULL).
- Insert two rows same (paper_id, key) with different conversation_id → no conflict.
- Build passes.

Commit: `feat(db): chat-scoped memory + paused status`.

## Agent B — Phase 1b — New Backend Modules

Goal: auto-extractor + mode prompts.

Files (CREATE):
- `backend/auto_memory.py`
- `backend/mode_prompts.py`
- `backend/tests/test_auto_memory.py`
- `backend/tests/test_mode_prompts.py`

`auto_memory.py` API:
- `extract_facts(paper_id, user_id, conv, user_msg, last_assistant_msg) -> list`
- Internal: `_regex_layer`, `_llm_fallback_layer` (V-DEEPSEEK), `_extract_expected_key`, `_confidence_filter`.
- Use existing `_save_memory()` from `chat_tools.py` (DO NOT modify it).

`mode_prompts.py` API:
- `get_mode_bundle(mode) -> (sysprompt, tool_names)`.
- Modes: `tier0`, `discovery`, `slr`, `edit`, `rapikan`, `memory`, `casual`.
- See spec §3.2 for tool lists per mode.
- Each prompt ≤2 KB.

Acceptance:
- Regex layer catches 16/20 sample replies.
- LLM fallback returns valid value or null.
- `get_mode_bundle("discovery")` returns tuple, sum bytes <4 KB.
- Stopwords (`oke`, `lanjut`, `ya`, `tidak`) rejected.

Commits: `feat(memory): auto-extraction module` + `feat(chat): mode prompts registry`.

## Agent A — Phase 1a — Chat Refactor

Goal: mode routing + auto-memory hook + drop SaveMemory + V-DEEPSEEK SLR fix.

Deps: Agent B done.

`backend/chat.py`:
1. Replace SYSTEM_PROMPT (line 64-219) with import `mode_prompts.TIER0_PROMPT`.
2. Add `_resolve_mode(conv)` helper (read `conv.metadata.mode`).
3. Replace `_select_tools` (line 480) with mode-bundle approach.
4. Hook `extract_facts(...)` at line 733 (after user msg commit, before generate()).
5. Gate memory injection (line 1071): only first turn or when explicit ask.
6. Handle `RouteIntent` tool result: persist `conv.metadata.mode`, re-call upstream same turn.
7. Drop chat-wide lock (line 712-721): block only repeat `GenerateFullPaper`.

`backend/chat_tools.py`:
1. Drop `SaveMemory` schema (1236-1247) + dispatch case (112-118).
2. Drop `GetMemory` schema (1249-1262) + dispatch case (119-120).
3. Keep `_save_memory` and `_get_memory` helper functions (auto_memory uses them).
4. Add `RouteIntent` tool (schema spec §3.3, dispatch returns `{kind:"route", mode, reasoning}`).
5. Add `ProposeChips` tool (schema spec §6.2, dispatch returns `{kind:"chips", chips}`).
6. Update `_generate_full_paper` (line 573): pass `paper_id` to `_job_create`, return `kind:"paper_progress"` payload.
7. SLR `ALLOWED_MODELS` (line 515): add `V-DEEPSEEK`.

Acceptance:
- `"halo"` first turn upstream payload <2 KB.
- Auto-extract: reply "1" to `[key=jurusan]` question saves memory.
- Mode switch via `RouteIntent` works, next call uses new bundle.
- No SaveMemory/GetMemory in tool list.
- Chat-wide lock dropped.

Commits:
1. `refactor(chat): mode-based tool routing + auto-memory hook`.
2. `refactor(chat_tools): drop SaveMemory tool, add RouteIntent + ProposeChips`.
3. `fix(slr): allow V-DEEPSEEK in chat tool path`.

## Agent D — Phase 1c — Generate Pipeline

Goal: unify pipeline, checkpoint/cancel/resume, slim section prompts.

`generate_paper_chunked.py`:
1. Add params `checkpoint_cb=None, cancel_check=None, resume_state=None` to `generate_paper_json_chunked` (line 505).
2. Define `class GenerationCancelled(Exception)`.
3. After each chunk: call `checkpoint_cb(stage, percent, partial)`.
4. Before each chunk: call `cancel_check()`, raise GenerationCancelled if true.
5. Skip chunks in `resume_state["chunks_done"]`, reuse from `partial_paper`.
6. `_generate_section`: load slim prompts (`prompt_section_only.txt` + `humanize_prose_only.txt`).

`prompt/prompt_section_only.txt` (new): ≤4 KB. Section JSON schema, numbering rules, citation format.

`prompt/humanize_prose_only.txt` (new): ≤12 KB. Anti-AI patterns, sentence variation, academic register, hedging. Drop figure/table/equation rules.

`app.py`:
1. `_job_create` (line 286-290): accept `paper_id` arg, set on row.
2. `_run_generate_full_job` (line 499): wire `make_checkpoint_cb(job_id)` + `make_cancel_check(job_id)`.
3. `app.py:725-738` GET result: don't delete row, set `result_consumed_at = utcnow()`.
4. Caller `chat_tools.py:643` (touched by Agent A) passes `paper_id` — coordinate.

`jobs_bp.py` add endpoints:
1. `GET /api/papers/<id>/ai-jobs/active` — return active job for paper.
2. `POST /api/ai-jobs/<job_id>/cancel` — set status=cancelled.
3. `POST /api/ai-jobs/<job_id>/resume` — re-enqueue with resume_state.
4. `POST /api/ai-jobs/<job_id>/retry-section` — body `{stage}`, remove from chunks_done, re-enqueue.
5. `GET /api/me/ai-jobs/recent?status=done&since=&limit=20`.

`tasks/generate_paper_task.py`:
1. Switch from legacy `generate_paper_json` to chunked.
2. Wire checkpoint_cb (DB writes to `AiJob.stage/progress/result`).
3. Wire cancel_check (DB status check).
4. Accept `resume_state` from job kwargs.

Acceptance:
- Generate, kill backend mid-section 3, restart, `/resume` → sections 3-5 regenerate, 1-2 reused.
- Cancel mid-section 3 → partial saved, status=cancelled.
- `AiJob.paper_id` set for chat-initiated jobs.
- `_job_create` doesn't delete row on GET.
- Section chunks <30 KB prompt size.

Commits:
1. `feat(generate): checkpoint + cancel + resume support`.
2. `feat(generate): slim section prompts`.
3. `fix(app): set paper_id on AiJob, don't delete on GET`.
4. `feat(jobs_bp): cancel/resume/retry-section/recent endpoints`.
5. `refactor(tasks): switch RQ worker to chunked + checkpoint`.

## Agent E — Phase 1d — SLR Fixes

Goal: ai_summary_used flag + frontend badge.

(V-DEEPSEEK fix in `chat_tools.py` moved to Agent A.)

Tasks:
1. `slr_bp.py:171`: add `V-DEEPSEEK` to allowed set.
2. `SLR/summarizer.py`: track ai_used, return tuple `(papers, ai_used)`.
3. `SLR/pipeline.py`: pass `ai_used` to `result.stats.ai_summary_used`.
4. `frontend/src/components/LiteratureTab.vue`: read `job.result?.stats?.ai_summary_used`, show badge "Summary: extractive only" when false.

Acceptance:
- SLR with `ai_model=V-DEEPSEEK` works.
- Empty AIOTOMASI env → job done, badge visible.

Commit: `fix(slr): V-DEEPSEEK whitelist + ai_summary_used flag`.

## Agent F — Phase 2a — Frontend Chat Surface

Deps: Agent A done (ProposeChips tool + paper_progress message kind).

`ActionChips.vue` (new): renders chip buttons, emits `select` on click.

`ChatMessage.vue`:
- Detect `metadata.kind === 'chips'` → render `<ActionChips>`.
- Detect `metadata.kind === 'paper_progress'` → render `<PaperProgressBubble :job-id>`.

`ChatTab.vue`:
- Empty state hero (when `messages.length === 0`):
  - `Mau buat paper apa?` + 4 entry chips + 3 quick prompts.
- Click chip → call `chatStore.sendMessage(value)`.

Acceptance:
- Empty chat shows hero.
- Chip click sends message.
- AI chips render correctly.
- paper_progress renders bubble.

Commits:
1. `feat(chat): ActionChips component`.
2. `feat(chat): empty state hero`.
3. `feat(chat): paper_progress + chips message rendering`.

## Agent G — Phase 2b — Frontend Progress

Deps: Agent D endpoints ready.

`paperJobs.js` (new Pinia store):
- State: `activeByPaper`, `recentDone`, intervals.
- Actions: `fetchActive`, `startPolling(paperId)`, `stopPolling`, `cancel`, `resume`, `retrySection`, `startGlobalPolling`, `_notify`.

`PaperProgressBubble.vue` (new):
- Sticky bottom of chat.
- Header: stage label + percent.
- Progress bar.
- Buttons: Cancel / Resume (when paused) / Retry (when error).

`AppHeader.vue`:
- Bell icon with badge for `recentDoneCount`.
- Click opens dropdown with recent done jobs.

`PaperEditorPage.vue`:
- onMount: `paperJobsStore.startPolling(paperId)`.
- onUnmount: `stopPolling()`.
- App-level: `startGlobalPolling()` once.
- On done event: toast + browser notif.
- Request browser notif permission on first generate click.

Acceptance:
- Reload mid-generate → bubble persists with same fase + %.
- Switch paper → return → bubble still active.
- Done while in another paper → toast + badge + browser notif (if granted).
- Cancel/resume/retry buttons work.

Commits:
1. `feat(stores): paperJobs store`.
2. `feat(chat): PaperProgressBubble`.
3. `feat(header): job inbox badge`.
4. `feat(editor): wire paperJobs + browser notif`.

## Phase 3 — Integration Smoke Test

1. Build hijau:
   - Backend: `python -c "import app, chat, chat_tools, auto_memory, mode_prompts, generate_paper_chunked, slr_bp, jobs_bp"`
   - `alembic upgrade head` clean.
   - Frontend: `npm run build` passes.
2. Token test: send `"halo"`, capture upstream payload, assert <2 KB.
3. Auto-memory test: `[OPSI] 1) Teknik Elektro 2) ... [/OPSI]`, reply "1", verify ProjectMemory row.
4. Mode switch test: mid-discovery say "rapikan figure", verify next call uses rapikan bundle.
5. Generate resilience: reload mid-section, cancel, resume.
6. SLR: V-DEEPSEEK runs; without AIOTOMASI env shows extractive badge.
7. Cross-paper notif: generate Paper A, switch to B, see toast/badge when A done.

## Phase 4 — Acceptance

- `pytest tests/ -x` green.
- `npm run lint` clean.
- All spec §10 acceptance criteria checked.

## Risk Register

| Risk | Mitigation |
|---|---|
| Migration breaks existing rows | Test on fresh dev DB first |
| Auto-extract over-aggressive | Confidence filter + log + manual delete UI |
| RouteIntent latency | Cache mode in conv.metadata |
| Memory FK breaks paper-delete cascade | Test paper delete removes both scopes |
| Slim prompt drops quality | Manual eyeball 3 papers before/after |
| Frontend polling overload | 3s/10s intervals, abort on tab hidden, backoff on 429 |
| Drop chat-wide lock confusion | Block only repeat GenerateFullPaper |

## Rollback

Each phase commits independently. Phase 1c break → revert in reverse: jobs_bp → tasks → app.py → chunked. Migration: `alembic downgrade -1`.
