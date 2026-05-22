# LAPORAN REVIEW SISTEM PAPERFULL
## Comprehensive Analysis: Workflow, Chat, Prompt, Tools & UI/UX

**Tanggal:** 2026-05-22  
**Reviewer:** Kiro AI  
**Scope:** Full system review berdasarkan handoff document, codebase analysis, dan user requirements gathering  
**Status:** Final Recommendations Ready for Implementation

---

## EXECUTIVE SUMMARY

### Konteks Review

PaperFull adalah aplikasi AI-powered academic paper generator yang telah melalui major refactoring (26 commits, 84/84 tests pass). Sistem menggunakan:
- **Backend:** Flask + SQLAlchemy + RQ workers + threading hybrid
- **Frontend:** Vue 3 + Pinia + Tailwind (dark mode support)
- **AI:** V-DEEPSEEK untuk chat, V-OPUS untuk paper generation
- **Architecture:** Mode-based tool routing dengan 8 modes, 30 tools, auto-memory extraction

### Key Achievements ✅

1. **Token Efficiency:** Reduced dari 13.4KB → <2KB per turn (95% reduction)
2. **Resilient Generation:** Chunked paper generation dengan checkpoint/cancel/resume
3. **Auto-Memory:** Ekstraksi fakta otomatis tanpa AI harus panggil tool
4. **Flexible Workflow:** Mode-based routing yang bisa skip steps
5. **Progress Tracking:** Real-time progress untuk long-running operations

### Critical Findings ⚠️

1. **No User Level Adaptation:** Semua user (beginner → advanced) dapat experience yang sama
2. **Workflow Rigidity:** Discovery mode 7-step masih terlalu sequential untuk expert users
3. **Invisible AI Too Invisible:** User tidak tahu capabilities, tidak ada onboarding
4. **No Operation Locking:** Multiple generation jobs bisa conflict dalam 1 paper
5. **File Upload Flow:** Tidak ada classification step sebelum process

### User Requirements (Dari Questionnaire)

| Requirement | User Choice |
|-------------|-------------|
| **Target User** | Semua level equally supported (Beginner, Intermediate, Advanced, Non-Technical) |
| **Literatur Source** | Hybrid (upload beberapa + AI cari tambahan) |
| **Workflow Style** | Flexible, AI detect kebutuhan dari first message |
| **File Upload** | Classify file dulu, baru decide extraction strategy |
| **UI Transparency** | Invisible AI (hide mode/tools/memory dari user) |
| **Error Messages** | Adaptive (beginner: friendly, advanced: technical) |
| **Mode Persistence** | In-memory OK (no migration needed) |
| **Long Operations** | Parallel antar paper; dalam 1 paper: 1 generation job + diskusi OK, tapi tidak bisa trigger edit/generate lagi |

---

## PART 1: SYSTEM ARCHITECTURE REVIEW

### 1.1 Mode-Based Tool Routing

**Konsep:**
```
User Message → Auto-Memory Extract → Mode Resolver → Bundle (Prompt + Tools) → Upstream AI
```

**8 Modes Implemented:**

| Mode | Prompt Size | Tools Count | Use Case |
|------|-------------|-------------|----------|
| `tier0` | 158 B | 1 | Router classification |
| `discovery` | 1584 B | 12 | 7-step paper planning workflow |
| `slr` | 644 B | 5 | Literature search |
| `edit` | 1121 B | 11 | Paper editing |
| `rapikan` | 616 B | 4 | Renumbering figures/tables/equations |
| `revisi` | 1574 B | 15 | Targeted revisions |
| `memory` | 287 B | 2 | Memory management |
| `casual` | 158 B | 0 | Chitchat |

**Strengths:**
- ✅ Massive token savings (95% reduction for casual turns)
- ✅ Scoped tools prevent AI overwhelm
- ✅ Clear separation of concerns per mode
- ✅ AI can switch modes via RouteIntent tool

**Weaknesses:**
- ⚠️ Mode invisible to user (acceptable per user requirement)
- ⚠️ In-memory persistence only (acceptable per user requirement)
- ⚠️ No mode history/audit trail
- ⚠️ RouteIntent can misclassify without correction mechanism

### 1.2 Auto-Memory Extraction

**Architecture:**
- **Layer 1:** Regex (fast, free) - [OPSI] blocks, explicit patterns, expected keys
- **Layer 2:** LLM Fallback (V-DEEPSEEK) - 64 token cap, 10s timeout, confidence filter

**Strengths:**
- ✅ No tool burden on AI (SaveMemory/GetMemory removed)
- ✅ Hybrid approach balances speed and accuracy
- ✅ Confidence filtering prevents garbage saves

**Weaknesses:**
- ⚠️ Only extracts single facts, not bulk info from first message
- ⚠️ No user visibility into what's being remembered (acceptable per user requirement)

### 1.3 Chat System (SSE Streaming)

**SSE Events:** thinking, content, tool_call, tool_result, chips, paper_progress, error, done

**Strengths:**
- ✅ Real-time feedback
- ✅ Tool transparency
- ✅ Graceful error handling
- ✅ Concurrent safety (semaphore limits)

**Weaknesses:**
- ⚠️ No retry mechanism on stream failure
- ⚠️ Tool loop can hit max iterations without early stop
- ⚠️ No user-initiated cancellation (except full-paper jobs)

### 1.4 Tools System (30 Tools)

**Categories:**
- **Discovery (12):** RunSLR, GetLiterature, GenerateFullPaper, ProposeChips, AskQuestions, ClassifyFile, etc.
- **Edit (11):** GetPaperContent, ProposeTitle/Abstract/Keywords/Section/Reference, GenerateChart, etc.
- **Revisi (15):** All edit tools + Paraphrase, FixGrammar, Translate, ReviewPaper, ReviseData
- **Meta (3):** RouteIntent, ListMemory, DeleteMemory

**Strengths:**
- ✅ Clear naming, scoped by mode, propose pattern, async job tools

**Weaknesses:**
- ⚠️ No user-facing tool documentation
- ⚠️ Missing tools: SearchWeb, ExplainConcept, SuggestTopics
- ⚠️ Tool error messages not actionable

---

## PART 2: CRITICAL ISSUES & RECOMMENDATIONS

### Issue 1: No User Level Adaptation ⚠️ CRITICAL

**Problem:** Semua user dapat experience yang sama, tidak ada personalization.

**Impact:** Beginners overwhelmed, advanced users frustrated, non-technical users intimidated.

**Solution:** User level detection + adaptive UI

**Implementation:**
```javascript
// stores/user.js
const userPreferences = ref({
  experience_level: 'auto', // auto | beginner | intermediate | advanced
  show_technical_details: false,
  workflow_style: 'guided' // guided | express | expert
})

function detectUserLevel() {
  // Auto-detect dari behavior indicators
  const indicators = {
    beginner: ['bingung', 'tidak tahu', 'gimana', 'contoh', firstTimeUser],
    advanced: ['langsung generate', uploadMultipleFiles, useTechnicalTerms]
  }
}
```

**UI Adaptation:**
- Beginner: Step-by-step dengan tooltips, examples, explanations
- Intermediate: Faster workflow, skip known steps
- Advanced: Bulk input form, direct tool access
- Non-Technical: Simple mode, plain language, visual wizard

**Priority:** P0 (Critical)

---

### Issue 2: Workflow Rigidity ⚠️ CRITICAL

**Problem:** Discovery mode enforces sequential 7-step Q&A bahkan kalau user sudah kasih bulk info.

**Impact:** Expert users waste time, no fast-track.

**Solution:** Smart first-message parser untuk bulk info extraction

**Implementation:**
```python
# auto_memory.py - enhance extract_facts()
def extract_bulk_info(user_msg: str) -> dict:
    """
    Extract multiple facts from single message.
    
    Example: "Saya mahasiswa Teknik Informatika mau nulis paper tentang 
    optimasi algoritma genetika untuk scheduling. Saya sudah punya 5 paper."
    
    Output: {
      'jurusan': 'Teknik Informatika',
      'topik': 'optimasi algoritma genetika untuk scheduling',
      'literatur': 'sudah (5 paper)'
    }
    """
    # Use V-DEEPSEEK with structured output
    prompt = f"""Extract research paper planning info from this message.
    Return JSON with keys: jurusan, topik, latar_belakang, literatur_status, 
    metode, data_status. Only include keys with clear values."""
```

**Mode Prompt Update:**
```python
# mode_prompts.py - DISCOVERY_PROMPT
"""
SMART START:
If user's first message contains multiple facts (jurusan + topik + metode + data),
extract ALL via auto-memory, then:
  1. Summarize: "Oke, jadi kamu mau nulis paper tentang X di jurusan Y. Betul?"
  2. Ask ONLY for missing critical info
  3. Skip to step 7 (confirm & generate)

Do NOT force sequential Q&A when user already gave bulk info.
"""
```

**Priority:** P0 (Critical)

---

### Issue 3: No Operation Locking ⚠️ CRITICAL

**Problem:** Tidak ada mechanism untuk prevent multiple generation jobs dalam 1 paper.

**Impact:** Data races, conflicts, unclear paper state.

**Solution:** Paper-level operation lock

**Implementation:**
```python
# models.py
class Paper(db.Model):
    active_operation = db.Column(String(50), nullable=True)  
    # Values: None | 'generating' | 'slr_running'
    active_operation_job_id = db.Column(String(50), nullable=True)

# chat_tools.py
def _check_paper_lock(paper_id, operation_type):
    """
    Rules:
    - generating: block other generate/edit, allow chat/slr
    - slr_running: allow all (read-only)
    
    Returns: (allowed: bool, reason: str)
    """
    paper = Paper.query.get(paper_id)
    if paper.active_operation == 'generating':
        if operation_type in ['generate', 'edit_apply']:
            return False, "Paper sedang di-generate. Tunggu selesai atau cancel."
    return True, None
```

**Frontend Indicator:**
```vue
<!-- ChatTab.vue -->
<div v-if="paperLocked" class="paper-lock-banner">
  <strong>Paper sedang di-generate</strong>
  <p>Kamu masih bisa chat untuk diskusi, tapi tidak bisa trigger generate/edit baru.</p>
  <button @click="cancelGeneration">Cancel</button>
</div>
```

**Priority:** P0 (Critical)

---

### Issue 4: File Classification Not Enforced ⚠️ HIGH

**Problem:** AI bisa proceed tanpa classify file type dulu.

**Impact:** Wrong file processing, user confusion.

**Solution:** Enforce classification step

**Implementation:**
```python
# chat_tools.py - ClassifyFile tool
def _classify_file(file_id, kind=None):
    if kind is None:
        # Return question proposal
        return {
            "kind": "multi_question",
            "questions": [{
                "key": f"file_kind:{file_id}",
                "label": f"File '{filename}' ini apa?",
                "options": [
                    {"label": "Paper review (masuk SLR)", "value": "paper_slr"},
                    {"label": "Paper jadi (retemplating)", "value": "paper_read"},
                    {"label": "Data file (tabel/grafik)", "value": "data"},
                    {"label": "Gambar (figure)", "value": "image"},
                    {"label": "Template jurnal", "value": "template"}
                ]
            }]
        }
```

**Mode Prompt Update:**
```python
# mode_prompts.py - DISCOVERY_PROMPT & REVISI_PROMPT
"""
FILE UPLOADS:
When [FILE_IDS=...] appears:
  1. Call ClassifyFile(file_id) WITHOUT kind parameter
  2. Tool returns AskQuestions proposal
  3. Wait for user answer
  4. Call ClassifyFile(file_id, kind=<answer>) to apply
  5. Process file based on kind
"""
```

**Priority:** P0 (Critical) - enforcement via prompt

---

### Issue 5: Adaptive Error Messages ⚠️ HIGH

**Problem:** Error messages tidak sesuai user level.

**Solution:** Error message adapter

**Implementation:**
```javascript
// utils/errorMessages.js
export function adaptErrorMessage(error, userLevel) {
  const errorMap = {
    'UPSTREAM_TIMEOUT': {
      beginner: 'AI sedang sibuk. Coba lagi dalam 30 detik ya 😊',
      intermediate: 'Server timeout. Retry dalam 30 detik atau cek koneksi.',
      advanced: 'Upstream timeout after 180s. Retry or check network/API status.'
    },
    'PAPER_LOCKED': {
      beginner: 'Paper sedang diproses. Tunggu sebentar ya 😊',
      intermediate: 'Paper locked: generation in progress. Wait or cancel.',
      advanced: 'Paper locked by active operation (job_id: XXX). Cancel or wait.'
    }
  }
  
  const level = userLevel === 'auto' ? detectLevel() : userLevel
  return errorMap[error.code]?.[level] || error.message
}
```

**Priority:** P1 (High)

---

### Issue 6: Hybrid Literature Workflow ⚠️ HIGH

**Problem:** Current workflow assumes either "belum ada" (SLR) or "sudah ada" (upload), tidak ada hybrid.

**Solution:** Support upload + auto-search dalam satu workflow

**Mode Prompt Update:**
```python
# mode_prompts.py - DISCOVERY_PROMPT
"""
LITERATUR (key=referensi_terpilih):
  [OPSI]
    1) Belum ada, AI carikan (SLR auto-search)
    2) Sudah punya, akan upload file
    3) Punya beberapa, tapi perlu tambahan (hybrid)
  [/OPSI]
  
  If option 3 (hybrid):
    - ListAttachedFiles to see uploaded
    - Ask: "Berapa paper tambahan yang perlu AI carikan? (suggest: 10-20)"
    - RunSLR with top_k from user answer
    - Combine uploaded + SLR results
"""
```

**Priority:** P1 (High)

---

### Issue 7: Invisible AI - Hide Internal State ⚠️ MEDIUM

**Problem:** Current UI shows mode, tools, memory terlalu prominent.

**Solution:** Hide by default per user requirement

**Implementation:**
```vue
<!-- ChatTab.vue - REMOVE mode indicator -->
<!-- Memory - collapse by default -->
<button @click="showMemory = !showMemory" class="memory-toggle">
  <span>🧠</span>
  <span v-if="memory.length" class="badge">{{ memory.length }}</span>
</button>

<!-- Tool calls - hide unless error -->
<div v-if="message.tool_error" class="tool-error">
  <span>⚠️ Terjadi kendala</span>
  <button @click="showDetails = !showDetails">Detail</button>
</div>
```

**Priority:** P1 (High)

---

## PART 3: IMPLEMENTATION ROADMAP

### Week 1: Critical Fixes (P0)
- [ ] **Smart first-message parser** - bulk info extraction
  - File: `backend/auto_memory.py`
  - Add `extract_bulk_info()` function
  - Update `mode_prompts.py` DISCOVERY_PROMPT
  
- [ ] **Operation locking per paper** - prevent conflicts
  - File: `backend/models.py` - add `active_operation` column
  - File: `backend/chat_tools.py` - add `_check_paper_lock()`
  - File: `frontend/src/components/ChatTab.vue` - add lock banner
  
- [ ] **File classification enforcement** - classify dulu
  - File: `backend/mode_prompts.py` - update FILE UPLOADS section
  - Test: ensure AI always calls ClassifyFile without kind first
  
- [ ] **User level detection system**
  - File: `frontend/src/stores/user.js` - create new store
  - Add `detectUserLevel()` function
  - Add preference UI in settings

### Week 2: High Priority (P1)
- [ ] **Invisible AI UI** - hide mode/tools/memory
  - File: `frontend/src/components/ChatTab.vue`
  - File: `frontend/src/components/ChatMessage.vue`
  
- [ ] **Adaptive error messages**
  - File: `frontend/src/utils/errorMessages.js` - create new
  - File: `frontend/src/stores/chat.js` - use adapter
  
- [ ] **Hybrid literature workflow**
  - File: `backend/mode_prompts.py` - update LITERATUR section
  
- [ ] **Stream cancellation**
  - File: `frontend/src/stores/chat.js` - add abortController
  - File: `frontend/src/components/ChatTab.vue` - add stop button

### Week 3: Polish & Testing
- [ ] User level preference UI
- [ ] Adaptive empty state (beginner vs advanced)
- [ ] Cross-paper parallel operations testing
- [ ] E2E testing all user levels
- [ ] Documentation update

---

## PART 4: TECHNICAL SPECIFICATIONS

### Spec 1: Smart First-Message Parser

**File:** `backend/auto_memory.py`

**Function Signature:**
```python
def extract_bulk_info(user_msg: str, paper_id: str, user_id: int) -> dict[str, str]:
    """
    Extract multiple research paper planning facts from a single user message.
    
    Args:
        user_msg: User's first message (potentially containing bulk info)
        paper_id: Paper ID for memory storage
        user_id: User ID for memory storage
    
    Returns:
        Dict of extracted facts: {key: value}
        Example: {
            'jurusan': 'Teknik Informatika',
            'topik': 'optimasi algoritma genetika',
            'metode': 'algoritma genetika',
            'literatur': 'sudah (5 paper)'
        }
    """
```

**LLM Prompt:**
```python
BULK_EXTRACT_PROMPT = """
Extract research paper planning information from this user message.

Return JSON with these keys (only include if clearly stated):
- jurusan: academic department/major
- topik: research topic
- latar_belakang: background/motivation
- literatur_status: "belum" | "sudah" | "sebagian"
- metode: research method/approach
- data_status: "belum" | "sudah" | "estimasi"
- kesimpulan_target: expected conclusion/findings

Return {} if no clear information extractable.

User message: {user_msg}
"""
```

**Integration Point:**
```python
# chat.py - in send_message() before generate()
if is_first_message_in_conversation:
    bulk_facts = extract_bulk_info(content, paper_id, user_id)
    for key, value in bulk_facts.items():
        _save_memory(paper_id, user_id, key, value, kind="fact")
```

---

### Spec 2: Operation Locking

**Database Schema:**
```python
# models.py
class Paper(db.Model):
    # ... existing fields ...
    active_operation = db.Column(String(50), nullable=True)
    active_operation_job_id = db.Column(String(50), nullable=True)
    active_operation_started_at = db.Column(DateTime, nullable=True)
```

**Lock Check Function:**
```python
# chat_tools.py
def _check_paper_lock(paper_id: str, operation_type: str) -> tuple[bool, str | None]:
    """
    Check if paper is locked by another operation.
    
    Args:
        paper_id: Paper ID to check
        operation_type: 'generate' | 'edit_apply' | 'slr' | 'chat'
    
    Returns:
        (allowed, reason): (True, None) if allowed, (False, reason) if blocked
    """
    paper = Paper.query.get(paper_id)
    if not paper or not paper.active_operation:
        return True, None
    
    # Rules
    if paper.active_operation == 'generating':
        if operation_type in ['generate', 'edit_apply']:
            return False, "Paper sedang di-generate. Tunggu selesai atau cancel dulu."
    
    return True, None

def _set_paper_lock(paper_id: str, operation: str, job_id: str = None):
    """Set paper lock."""
    paper = Paper.query.get(paper_id)
    paper.active_operation = operation
    paper.active_operation_job_id = job_id
    paper.active_operation_started_at = datetime.utcnow()
    db.session.commit()

def _clear_paper_lock(paper_id: str):
    """Clear paper lock."""
    paper = Paper.query.get(paper_id)
    paper.active_operation = None
    paper.active_operation_job_id = None
    paper.active_operation_started_at = None
    db.session.commit()
```

**Usage in Tools:**
```python
# chat_tools.py - _generate_full_paper()
def _generate_full_paper(...):
    # Check lock
    allowed, reason = _check_paper_lock(paper_id, 'generate')
    if not allowed:
        return {"error": reason}
    
    # Set lock
    _set_paper_lock(paper_id, 'generating', job_id)
    
    # Start job...
    
    # Clear lock in worker callback on completion
```

---

### Spec 3: Adaptive Error Messages

**File:** `frontend/src/utils/errorMessages.js`

```javascript
const ERROR_MESSAGES = {
  UPSTREAM_TIMEOUT: {
    beginner: {
      message: 'AI sedang sibuk. Coba lagi dalam 30 detik ya 😊',
      action: 'Retry',
      showDetails: false
    },
    intermediate: {
      message: 'Server timeout. Retry dalam 30 detik atau cek koneksi.',
      action: 'Retry',
      showDetails: true
    },
    advanced: {
      message: 'Upstream timeout after 180s. Check network/API status.',
      action: 'Retry',
      showDetails: true
    }
  },
  TOOL_EXECUTION_FAILED: {
    beginner: {
      message: 'Ada yang salah. Coba kirim ulang pesanmu.',
      action: 'Retry',
      showDetails: false
    },
    intermediate: {
      message: 'Tool execution gagal. Coba lagi atau ubah request.',
      action: 'Retry',
      showDetails: true
    },
    advanced: {
      message: 'Tool execution failed. Check logs for details.',
      action: 'Retry',
      showDetails: true
    }
  },
  PAPER_LOCKED: {
    beginner: {
      message: 'Paper sedang diproses. Tunggu sebentar ya 😊',
      action: 'Wait',
      showDetails: false
    },
    intermediate: {
      message: 'Paper locked: generation in progress. Wait or cancel.',
      action: 'Cancel',
      showDetails: true
    },
    advanced: {
      message: 'Paper locked by active operation. Cancel or wait for completion.',
      action: 'Cancel',
      showDetails: true
    }
  }
}

export function adaptErrorMessage(error, userLevel = 'intermediate') {
  const errorCode = error.code || 'UNKNOWN'
  const levelMap = ERROR_MESSAGES[errorCode]
  
  if (!levelMap) {
    return {
      message: error.message || 'Terjadi kesalahan',
      action: 'Retry',
      showDetails: userLevel !== 'beginner'
    }
  }
  
  return levelMap[userLevel] || levelMap.intermediate
}
```

---

## PART 5: TESTING CHECKLIST

### Unit Tests
- [ ] `test_extract_bulk_info()` - various input formats
- [ ] `test_check_paper_lock()` - all operation combinations
- [ ] `test_adapt_error_message()` - all error codes × user levels

### Integration Tests
- [ ] Smart parser: bulk input → skip to confirm
- [ ] Operation lock: generate → block second generate
- [ ] Operation lock: generate → allow chat
- [ ] File classification: upload → classify → process
- [ ] Adaptive errors: beginner sees friendly, advanced sees technical

### E2E Tests
- [ ] Beginner flow: guided 7-step → generate
- [ ] Intermediate flow: bulk input → fast-track → generate
- [ ] Advanced flow: upload files → hybrid literature → generate
- [ ] Cross-paper: generate Paper A → switch to B → generate B (parallel OK)
- [ ] Same-paper: generate → try edit (blocked) → cancel → edit (OK)

---

## PART 6: NEXT STEPS

### Immediate Actions (This Week)
1. **Review & Approve** this laporan dengan stakeholders
2. **Create GitHub Issues** untuk tiap P0 item
3. **Setup Development Branch** `feature/user-level-adaptation`
4. **Assign Tasks** ke developers

### Week 1 Sprint
- Implement P0 items (smart parser, operation locking, file classification, user level detection)
- Write unit tests
- Code review

### Week 2 Sprint
- Implement P1 items (invisible AI UI, adaptive errors, hybrid literature, stream cancellation)
- Integration tests
- UI/UX polish

### Week 3 Sprint
- E2E testing
- Bug fixes
- Documentation
- Deploy to staging

### Week 4
- User acceptance testing
- Production deployment
- Monitor metrics

---

## APPENDIX A: FILE REFERENCE

### Backend Files Modified
- `backend/auto_memory.py` - add extract_bulk_info()
- `backend/models.py` - add Paper.active_operation
- `backend/chat_tools.py` - add _check_paper_lock(), _set_paper_lock(), _clear_paper_lock()
- `backend/mode_prompts.py` - update DISCOVERY_PROMPT, REVISI_PROMPT
- `backend/chat.py` - integrate bulk extraction

### Frontend Files Modified
- `frontend/src/stores/user.js` - NEW: user preferences store
- `frontend/src/stores/chat.js` - integrate error adapter
- `frontend/src/utils/errorMessages.js` - NEW: error message adapter
- `frontend/src/components/ChatTab.vue` - add lock banner, hide mode indicator
- `frontend/src/components/ChatMessage.vue` - hide tool calls unless error

### Test Files Created
- `backend/tests/test_bulk_extraction.py` - NEW
- `backend/tests/test_paper_locking.py` - NEW
- `frontend/tests/unit/errorMessages.spec.js` - NEW
- `frontend/tests/e2e/user-levels.spec.js` - NEW

---

## APPENDIX B: METRICS TO TRACK

### User Experience Metrics
- Time to first paper generation (by user level)
- Workflow completion rate (7-step vs fast-track)
- Error recovery rate (retry success rate)
- User level detection accuracy

### System Performance Metrics
- Token usage per conversation (target: <2KB for casual, <5KB for discovery)
- Generation success rate (target: >95%)
- Operation lock conflicts (target: <1% of operations)
- Stream failure rate (target: <2%)

### Feature Adoption Metrics
- Bulk input usage rate (% of users who provide bulk info in first message)
- Hybrid literature usage rate (% of users who use upload + auto-search)
- File classification accuracy (% of files correctly classified)
- User level preference changes (how often users manually adjust level)

---

**END OF REPORT**

Generated: 2026-05-22  
Next Review: After Week 3 implementation  
Contact: Kiro AI / Rofiq (Product Owner)
