# Frontend — paper-generator-frontend

> Vue 3 + TypeScript + Vite — SPA untuk AI-powered academic paper generation.

---

## 1. Struktur Folder

```
frontend/
├── index.html                  # Entry HTML
├── package.json                # Dependencies & scripts
├── vite.config.ts              # Vite config + proxy ke backend :8001
├── tsconfig.json               # TypeScript config
├── tsconfig.node.json          # TS config untuk vite.config.ts
├── tailwind.config.js          # Custom color palette & fonts
├── postcss.config.js           # PostCSS: tailwindcss + autoprefixer
├── playwright.config.ts        # E2E testing config
│
├── src/
│   ├── main.ts                 # Bootstrap: Vue, Pinia, Router, Theme, ErrorHandler
│   ├── App.vue                 # Root component: ErrorBoundary + router-view
│   ├── env.d.ts                # Vite env type declarations
│   ├── style.css               # Global CSS variables (light/dark themes)
│   │
│   ├── api/
│   │   ├── index.ts            # Axios instance + CSRF interceptor + token refresh
│   │   └── charts.ts           # Charts API (CRUD + uploadData)
│   │
│   ├── router/
│   │   └── index.ts            # Vue Router: /, /login, /auth/callback, /dashboard, /editor, /admin
│   │
│   ├── stores/                 # Pinia state management (10 stores)
│   │   ├── auth.ts             # Auth: Google OAuth, login, logout, /me
│   │   ├── chat.ts             # Chat: multi-chat SSE, tool calls, proposal handling (~1042 lines)
│   │   ├── paper.ts            # Paper: CRUD sections, authors, refs, undo/redo, DOCX export (~1363 lines)
│   │   ├── paperJobs.ts        # Job tracking: polling, notifications, chat injection
│   │   ├── imageGen.ts         # Image gen: queue, polling, subscriber pattern
│   │   ├── literature.ts       # SLR job intent: attach/consume/clear
│   │   ├── quota.ts            # Token quota: fetch, polling, dedup
│   │   ├── theme.ts            # Theme: light/dark/system, localStorage
│   │   ├── tools.ts            # Writing tools: paraphrase, translate, humanizer, etc.
│   │   └── ui.ts               # UI state: active tab, chat panel, tab signal
│   │
│   ├── services/
│   │   ├── errorHandler.ts     # Error parsing, user-friendly messages, retry
│   │   └── globalErrorHandler.ts # Vue global error + unhandled rejection
│   │
│   ├── types/
│   │   ├── components.ts       # TypeScript interfaces untuk props/emits
│   │   ├── router.d.ts         # Vue Router meta augmentation
│   │   └── slr.ts              # SLR types: SlrJob, SlrResult, LiteraturePaper
│   │
│   ├── utils/
│   │   ├── errorMessages.ts    # User-level error messages (beginner/intermediate/advanced)
│   │   └── logger.ts           # Buffered log shipping to backend, perf tracking
│   │
│   ├── composables/
│   │   ├── useKeyboardShortcuts.ts # Keyboard shortcut binding
│   │   └── useSanitize.ts      # DOMPurify wrapper + math sanitization
│   │
│   ├── directives/
│   │   └── autosize.ts         # v-autosize: auto-resize textarea
│   │
│   ├── config/                 # (kosong — placeholder)
│   ├── examples/               # (kosong — placeholder)
│   │
│   ├── views/                  # 7 halaman
│   │   ├── LandingPage.vue     # Marketing landing: hero, features, domains, CTA (302 lines)
│   │   ├── LoginPage.vue       # Login/register: email+password, Google OAuth, Turnstile (255 lines)
│   │   ├── AuthCallbackPage.vue # OAuth callback handler (68 lines)
│   │   ├── DashboardPage.vue   # Paper list: copy, delete, open (197 lines)
│   │   ├── PaperEditorPage.vue # Main editor: toolbar, tabs, split layout, auto-save (789 lines)
│   │   ├── FilesPage.vue       # Standalone file manager: upload, grid, delete (231 lines)
│   │   └── AdminPage.vue       # Admin: API stats, papers, user quota mgmt (389 lines)
│   │
│   ├── components/             # 34 reusable components
│   │   ├── AppHeader.vue       # Header: logo, quota bar, job bell, theme switcher
│   │   ├── AppDialog.vue       # Accessible modal: focus trap, escape
│   │   ├── StateView.vue       # Loading/empty/error state wrapper
│   │   ├── ErrorBoundary.vue   # Vue error boundary with reset
│   │   │
│   │   ├── ContentList.vue     # Draggable content: text, image, table, formula (465 lines)
│   │   ├── ChatTab.vue         # Full chat: streaming, file attach, suggestions (1520 lines)
│   │   ├── ChatMessage.vue     # Chat message: markdown, thinking, tool calls (671 lines)
│   │   ├── ThinkingBlock.vue   # Collapsible AI thinking indicator
│   │   ├── ToolCallBlock.vue   # Tool call display: args/result
│   │   ├── ToolGauge.vue       # Circular gauge for detector/plagiarism scores
│   │   ├── ToolWorkspace.vue   # Tool execution UI: input/output, gauge, grammar diff
│   │   ├── PaperProgressBubble.vue # Inline paper gen progress: cancel/resume/retry
│   │   ├── ChartPreviewCard.vue # Chart proposal: accept/regenerate
│   │   ├── FileReviewCard.vue  # Long file review: head/tail preview
│   │   │
│   │   ├── SectionsTab.vue     # Legacy sections editor with AI prompts
│   │   ├── PreviewTab.vue      # Full paper preview: inline diffs, IEEE format (362 lines)
│   │   ├── MetadataTab.vue     # Title, authors, abstract, keywords, acknowledgment
│   │   ├── JournalTab.vue      # Journal/template selector with search
│   │   ├── LiteratureTab.vue   # SLR runner, table, bulk actions, manual add (1221 lines)
│   │   ├── LiteratureCard.vue  # Literature paper card: expand/collapse
│   │   ├── SLRResultsView.vue  # SLR results: per-source tabs, AI summary
│   │   ├── FilesTab.vue        # File manager: docs + figures sub-tabs, upload (619 lines)
│   │   ├── DataTab.vue         # Data management: sources, tables, chart editor (769 lines)
│   │   ├── ChartsTab.vue       # Legacy charts: manual/JSON data input
│   │   ├── ReferencesTab.vue   # References with AI generation
│   │   │
│   │   ├── DiffBlock.vue       # Before/after diff: accept/reject
│   │   ├── RevisiProposalCard.vue # Side-by-side diff for paraphrase/translate/grammar
│   │   ├── MultiQuestionCard.vue # Multi-question form: chips, localStorage draft (516 lines)
│   │   │
│   │   ├── ActionChips.vue     # Keyboard-navigable chip buttons
│   │   ├── AiButton.vue        # Small AI action button with spinner
│   │   ├── AiPromptBox.vue     # AI prompt input for section editing
│   │   ├── ShortcutsHelp.vue   # Keyboard shortcuts help dialog
│   │   ├── ToolsTab.vue        # Tool picker grid
│   │   │
│   │   └── (lainnya)
│   │
│   └── image/
│       ├── landing-page.jpg    # Landing page hero image (201KB)
│       └── logo-with-text.png  # Logo dengan teks (79KB)
│
├── test-results.json/          # Test result artifacts
├── playwright-report/          # Playwright HTML report
├── logs/                       # Log files
└── node_modules/               # Dependencies
```

**Total: ~74 source files** (tanpa node_modules)

---

## 2. Tech Stack

| Layer           | Technology                                                      |
|-----------------|-----------------------------------------------------------------|
| Framework       | Vue 3.5 (Composition API)                                       |
| Language        | TypeScript 6.0                                                  |
| Build           | Vite 6.1                                                        |
| State           | Pinia 2.3                                                       |
| Routing         | Vue Router 4.5                                                  |
| HTTP            | Axios 1.7                                                       |
| Charts          | Chart.js 4.5 + vue-chartjs 5.3                                  |
| Markdown        | Marked 18.0                                                     |
| Sanitization    | DOMPurify 3.4                                                   |
| Syntax Highlight| Highlight.js 11.11                                              |
| Math Render     | KaTeX 0.16                                                      |
| Drag & Drop     | vuedraggable 4.1                                                |
| CSS             | Tailwind CSS 3.4                                                |
| Testing         | Vitest (unit) + Playwright (E2E + load test)                    |
| Linting         | ESLint 10.4 + Prettier 3.8                                      |

---

## 3. Arsitektur & Alur Data

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Browser (Vue 3 SPA)                               │
│                                                                          │
│  ┌─────────┐    ┌──────────────┐    ┌────────────────────────────────┐  │
│  │  Views   │───▶│   Stores      │───▶│         API Layer              │  │
│  │(7 halaman)│   │  (Pinia)     │    │   (Axios + CSRF interceptor)   │  │
│  └─────────┘    └──────────────┘    └────────────────────────────────┘  │
│       │                │                            │                    │
│       ▼                ▼                            ▼                    │
│  ┌─────────┐    ┌──────────────┐    ┌────────────────────────────────┐  │
│  │Components│   │ localStorage │    │   Backend API (localhost:8001) │  │
│  │ (34 buah)│   │ (persist)    │    │   /api/*                       │  │
│  └─────────┘    └──────────────┘    └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Alur Request

```
User Action → View/Component → Store Action → API Call (Axios) → Backend
                  │                │                                  │
                  ▼                ▼                                  ▼
            Components         State Update                    DB Response
            Re-render          localStorage                    ←── JSON
```

### Pola Authentication Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                    AUTHENTICATION FLOW                             │
│                                                                   │
│  ┌─────────┐         ┌──────────┐         ┌──────────────────┐  │
│  │ Login   │────────▶│ Backend   │────────▶│ JWT Cookies       │  │
│  │ Page    │  POST   │ /auth/   │  200    │ (HttpOnly+CSRF)   │  │
│  └─────────┘  /login │ login    │         │                   │  │
│                      └──────────┘         │ Access Token: 1h  │  │
│                                           │ Refresh Token: 7d │  │
│  ┌─────────┐         ┌──────────┐         └──────────────────┘  │
│  │ Google  │────────▶│ Backend   │              │                │
│  │ OAuth   │ redirect│ /auth/   │              │                │
│  │ Button  │         │ google/* │              │                │
│  └─────────┘         └──────────┘              │                │
│                                                ▼                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   SETIAP API REQUEST                        │ │
│  │                                                             │ │
│  │  1. Cookie otomatis terkirim (HttpOnly)                     │ │
│  │  2. CSRF token dari cookie → X-CSRF-TOKEN header           │ │
│  │  3. 401 → coba refresh → ulangi request                    │ │
│  │  4. Refresh gagal → redirect /login                        │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Routing

```
GET /                         → LandingPage        (public)
GET /login                    → LoginPage          (public)
GET /auth/callback            → AuthCallbackPage   (public)
GET /dashboard                → DashboardPage      (auth required)
GET /editor                   → PaperEditorPage    (auth required, new paper)
GET /editor/:paperId          → PaperEditorPage    (auth required, existing paper)
GET /admin                    → AdminPage          (auth + admin required)
GET /*                        → redirect /dashboard (catch-all)
```

**Navigasi Guards:**
- `requiresAuth` → redirect ke `/login` jika belum login
- `requiresAdmin` → redirect ke `/dashboard` jika bukan admin
- `public` + sudah login → redirect ke `/dashboard`

---

## 5. API Layer (`src/api/`)

### `src/api/index.ts` — Axios Instance (63 lines)

```pseudo-code
// Konfigurasi
CREATE axios instance:
  baseURL = VITE_API_URL atau ''
  timeout = 30000ms
  withCredentials = true  // kirim cookies

// Request Interceptor
ON setiap request:
  IF method IN [post, put, patch, delete]:
    BACA csrf_token dari cookie
    SET header X-CSRF-TOKEN

// Response Interceptor
ON response error:
  IF status == 401 DAN bukan auth endpoint DAN belum retry:
    TRY refresh token (POST /api/auth/refresh)
    IF berhasil: ulangi request asli
    IF gagal: redirect ke /login
  
  IF status == 401:
    HAPUS localStorage 'user'
    redirect ke /login

// Token Refresh Deduplication
FUNGSI tryRefresh():
  IF tidak ada refreshPromise aktif:
    refreshPromise = POST /api/auth/refresh
    SETELAH selesai: refreshPromise = null
  RETURN refreshPromise
```

### `src/api/charts.ts` — Charts API (68 lines)

```pseudo-code
FUNGSI getCharts(userId, paperId)     → GET    /api/charts?userId=...&paperId=...
FUNGSI getChart(chartId)              → GET    /api/charts/:chartId
FUNGSI createChart(data)              → POST   /api/charts
FUNGSI updateChart(chartId, data)     → PUT    /api/charts/:chartId
FUNGSI deleteChart(chartId)           → DELETE /api/charts/:chartId
FUNGSI uploadData(chartId, formData)  → POST   /api/charts/:chartId/data
```

---

## 6. Stores (State Management)

### 6.1 `auth.ts` — Authentication Store (~57 lines)

```pseudo-code
STORE auth:
  STATE:
    user = null | UserObject
    token = null | string

  GETTER:
    isLoggedIn = (token != null DAN user != null)
    isAdmin = (user.role == 'admin')

  ACTIONS:
    async login(email, password):
      response = POST /api/auth/login {email, password}
      token = response.access_token
      user = response.user

    async register(name, email, password):
      response = POST /api/auth/register {name, email, password}
      token = response.access_token
      user = response.user

    async loginWithGoogle():
      redirect ke GET /api/auth/google/login

    async fetchMe():
      response = GET /api/auth/me
      user = response.user

    async logout():
      POST /api/auth/logout
      user = null
      CLEAR localStorage
      redirect ke /login
```

### 6.2 `paper.ts` — Paper Store (~1363 lines) — STORE UTAMA

```pseudo-code
STORE paper:
  STATE:
    paper = {
      journal, title, authors[], abstract, keywords[],
      sections[{title, content[{id,text,...}], subsections[]}],
      references[], figures[]
    }
    currentPaperId = null | string
    paperImages = [], paperCharts = []
    loading = false
    aiLoading = false, aiLoadingMessage = ''
    toast = {show, message, type}
    undoStack = [{state, action, timestamp}]
    redoStack = [{state, action, timestamp}]

  // Persistence
  ON paper.value CHANGE (debounced):
    lsSet('pg_paper', paper.value)
    IF currentPaperId != null: debouncedSaveToBackend()

  ON init:
    saved = lsGet('pg_paper')
    IF saved: paper.value = fromPaperJsonRaw(saved)

  // CRUD
  ACTIONS:
    async createPaper():
      response = POST /api/papers {data: paper.value}
      currentPaperId = response.paper.id

    async loadPaper(paperId):
      response = GET /api/papers/:paperId
      paper.value = fromPaperJsonRaw(response.paper.data)
      currentPaperId = paperId

    async savePaper():
      IF currentPaperId == null:
        POST /api/papers {data: paper.value}
      ELSE:
        PATCH /api/papers/:currentPaperId {data: paper.value}

    async deletePaper(paperId):
      DELETE /api/papers/:paperId

    async exportDocx():
      POST /api/export/docx {paper_data: paper.value}
      // Download DOCX

    async copyPaper(paperId):
      POST /api/papers/:paperId/copy

  // Section Management
  addSection() / removeSection(i) / updateSectionTitle(i, title)
  addSubsection(sectionIndex)

  // Author Management
  addAuthor() / removeAuthor(index)

  // Keywords
  addKeyword(kw) / removeKeyword(index)

  // References
  addReference(ref) / removeReference(index)
  generateReferences()  // via AI chat

  // AI Generation
  async promptGenerate(promptText, paperId):
    response = POST /api/generate {prompt, paper_id: paperId}
    jobId = response.job_id
    START polling GET /api/job/:jobId
    IF done: paper.value = fromPaperJsonRaw(result)
    IF error: SHOW error

  // Undo/Redo (MAX_HISTORY = 50)
  recordChange(actionName):
    IF isUndoRedoOperation: RETURN
    snapshot = deepCopy(paper.value)
    undoStack.push({state: snapshot, action: actionName})
    IF undoStack.length > 50: shift()
    redoStack = []

  undo() / redo():
    PUSH current to opposite stack
    POP from target stack
    SET paper.value = popped.state
    IsUndoRedoOperation = true/false

  // Getters
  canUndo = undoStack.length > 0
  canRedo = redoStack.length > 0
  pendingCount = hitung content blocks 'pending'
```

### 6.3 `chat.ts` — Chat Store (~1042 lines)

```pseudo-code
STORE chat:
  STATE:
    conversations = []
    activeConversationId = null
    messages = []
    streaming = false
    streamingContent = ''
    streamingThinking = ''
    activeJobId = null
    isOnline = navigator.onLine
    offlineChats = []

  ACTIONS:
    async fetchConversations(paperId):
      GET /api/papers/:paperId/chat

    async createConversation(paperId, title):
      POST /api/papers/:paperId/chat {title}

    async selectConversation(convId):
      GET /api/chat/:convId/messages

    async sendMessage(text, paperId, options):
      // 1. Optimistic UI: tambah user message
      // 2. Setup SSE connection
      // 3. POST /api/chat/stream      ,
                          conversation_id, attached_files, mode)
      // 4. Parse SSE events:
      //    thinking → update streamingThinking
      //    content  → append streamingContent
      //    tool_call → handleToolCall
      //    proposal  → handleProposal
      //    chart     → handleChartProposal
      //    done      → FINALIZE message
      // 5. Retry dengan backoff (max 3x, 1s→2s→4s)

  // Proposal Handling
  handleProposal(proposal):
    SWITCH proposal.type:
      case 'section'    → paperStore.applyProposal()
      case 'paraphrase' → Show RevisiProposalCard
      case 'translate'  → Show RevisiProposalCard
      case 'grammar'    → Show RevisiProposalCard
      case 'full_paper' → paperStore.showPaperProposal()
      case 'revisi'     → Show diff view

  // File Attachment
  async uploadFile(file, paperId):
    POST /api/papers/:paperId/files {file}

  async pasteImage(blob, paperId):
    POST /api/papers/:paperId/images {blob}

  // Offline Support
  async retryOfflineChats():
    IF online AND offlineChats.length > 0:
      FOR EACH chat IN offlineChats:
        TRY sendMessage()
          ON success: REMOVE dari offlineChats
          ON failure: KEEP

  // Memory
  async saveMemory(paperId, key, value):
    POST /api/papers/:paperId/memory {key, value}

  async getMemory(paperId):
    GET /api/papers/:paperId/memory
```

### 6.4 `paperJobs.ts` — Job Tracking Store (~250 lines)

```pseudo-code
STORE paperJobs:
  STATE:
    activeJobs = []
    recentDone = []
    notifiedJobIds = new Set()

  ACTIONS:
    async fetchActiveJobs(paperId):
      GET /api/papers/:paperId/active-jobs

    async fetchRecentDoneJobs():
      GET /api/me/ai-jobs/recent {status:'done', limit:10}

    startPolling(paperId):
      EVERY 3000ms:
        response = GET /api/papers/:paperId/ai-jobs/active
        IF response.job.status == 'done' AND !notified:
          SHOW browser notification
          TRIGGER chatStore.injectJobResult()
        IF no active job: CLEAR interval

    async cancelJob(jobId):    POST /api/jobs/:jobId/cancel
    async resumeJob(jobId):    POST /api/ai-jobs/:jobId/resume
    async retrySection(jobId, stage):
      POST /api/ai-jobs/:jobId/retry-section {stage}
```

### 6.5 `imageGen.ts` — Image Generation Store (~212 lines)

```pseudo-code
STORE imageGen:
  STATE:
    jobs = []
    subscribers = {}   // Callbacks per content item ID

  ACTIONS:
    async generateImage(paperId, prompt, contentItemId):
      response = POST /api/image-jobs {paper_id, prompt}
      jobs.push({id, status:'queued', prompt})
      lsSet('imageGen_jobs', jobs)
      SUBSCRIBE(contentItemId, callback)

    startPolling():
      EVERY 5000ms:
        response = GET /api/image-jobs?user_id=me
        FOR EACH job IN response.jobs:
          UPDATE local job
          IF status == 'done':
            NOTIFY subscribers
            REMOVE job

    subscribe(contentItemId, callback):
      subscribers[contentItemId] = callback
```

### 6.6 `tools.ts` — Writing Tools Store (~131 lines)

```pseudo-code
STORE tools:
  STATE:
    activeTool = null  // paraphrase|translate|humanizer|detector|plagiarism|grammar|summarize|citation
    inputText = ''
    outputText = ''
    streaming = false

  TOOLS_MAP:
    paraphrase → POST /api/tools/paraphrase  SSE
    translate  → POST /api/tools/translate   SSE
    humanizer  → POST /api/tools/humanizer   SSE
    detector   → POST /api/tools/detector    SSE → JSON {pct, reasons, suggestions}
    plagiarism → POST /api/tools/plagiarism  SSE → JSON {pct, matches, suggestions}
    grammar    → POST /api/tools/grammar     SSE → HTML dengan <add>/<del> tags
    summarize  → POST /api/tools/summarize   SSE
    citation   → POST /api/tools/citation    SSE

  ACTIONS:
    async runTool(toolName, text, option):
      streaming = true
      POST /api/tools/:toolName {text, option}
      FOR EACH event IN stream:
        IF content: outputText += event.content
        IF done: streaming = false

    parseGrammarOutput(html):
      RETURN parsed <add>/<del> tags ke diff format
```

### 6.7 `quota.ts` — Token Quota Store (~86 lines)

```pseudo-code
STORE quota:
  STATE: monthlyLimit, monthlyUsed, usageByModel, loading

  GETTER:
    percentUsed = (monthlyUsed / monthlyLimit) * 100
    remaining = monthlyLimit - monthlyUsed
    isNearLimit = percentUsed >= 80
    isExceeded = monthlyUsed >= monthlyLimit

  ACTIONS:
    async fetchQuota():  GET /api/quota
    startPolling():      EVERY 30s → fetchQuota()
    async fetchUsageHistory(): GET /api/quota/history
```

### 6.8 `theme.ts` — Theme Store (~65 lines)

```pseudo-code
STORE theme:
  STATE: mode = 'system' | 'light' | 'dark'

  ACTIONS:
    setTheme(mode):
      theme.mode = mode
      lsSet('theme', mode)
      APPLY class ke document.body

    applyInitialTheme():
      saved = lsGet('theme') || 'system'
      setTheme(saved)

    applyThemeToDOM(mode):
      IF dark:   body.classList.add('dark')
      IF light:  body.classList.remove('dark')
      IF system: check prefers-color-scheme media query
```

### 6.9 `literature.ts` — SLR Intent Store (~30 lines)

```pseudo-code
STORE literature:
  STATE:
    slrJobId = null
    attachAfterUpload = false

  ACTIONS:
    setSlrJobId(jobId):    slrJobId = jobId
    consumeSlrJobId():      id = slrJobId; slrJobId = null; return id
    clearSlrIntent():       slrJobId = null
```

### 6.10 `ui.ts` — UI State Store (~77 lines)

```pseudo-code
STORE ui:
  STATE: perPaperTab = {}, chatOpen = false, tabSwitchSignal = 0

  ACTIONS:
    setActiveTab(paperId, tabId): perPaperTab[paperId] = tabId
    toggleChat():                  chatOpen = !chatOpen
    signalTabSwitch():             tabSwitchSignal++
```

---

## 7. Views (Halaman)

### 7.1 `LandingPage.vue` (~302 lines)

```pseudo-code
COMPONENT LandingPage:
  // Marketing landing page
  TEMPLATE:
    - Hero: judul, deskripsi, tombol "Mulai Sekarang"
    - Features grid: fitur utama
    - Domains: bidang ilmu yang didukung
    - CTA: call-to-action
```

### 7.2 `LoginPage.vue` (~255 lines)

```pseudo-code
COMPONENT LoginPage:
  STATE: mode='login'|'register', email, password, name, error, turnstileToken

  TEMPLATE:
    - Toggle login/register
    - Form: email, password, (name jika register)
    - Cloudflare Turnstile CAPTCHA
    - "Login with Google" button

  METHODS:
    handleSubmit():
      IF login:  authStore.login(email, password)
      IF register: authStore.register(name, email, password)
    handleGoogleLogin(): window.location = '/api/auth/google/login'
```

### 7.3 `AuthCallbackPage.vue` (~68 lines)

```pseudo-code
COMPONENT AuthCallbackPage:
  ON MOUNTED:
    params = URLSearchParams(window.location.search)
    accessToken = params.get('access_token')
    tokenStore.set(accessToken, refreshToken)
    await authStore.fetchMe()
    slrJobId = params.get('attach_slr_job')
    IF slrJobId: literatureStore.setSlrJobId(slrJobId)
    redirect ke /dashboard
```

### 7.4 `DashboardPage.vue` (~197 lines)

```pseudo-code
COMPONENT DashboardPage:
  STATE: papers = [], loading, error

  ON CREATED: loadPapers()

  METHODS:
    async loadPapers():
      GET /api/papers?limit=20&offset=0

    async createNewPaper():
      paper = POST /api/papers {data: emptyPaper}
      router.push('/editor/' + paper.id)

    async openPaper(id):   router.push('/editor/' + id)
    async copyPaper(id):   POST /api/papers/:id/copy → refresh list
    async deletePaper(id): DELETE /api/papers/:id → remove from list
```

### 7.5 `PaperEditorPage.vue` (~789 lines) — HALAMAN UTAMA

```pseudo-code
COMPONENT PaperEditorPage:
  // ┌──────────────────────────────────────────────────────────┐
  // │ AppHeader: quota, theme, user menu, job bell             │
  // ├──────────────────────────────────────────────────────────┤
  // │ Toolbar: [← Papers] | Title | DOCX Undo Redo | Tabs     │
  // │         [Editor][Journal][Lit][Files][Data][Preview][?]  │
  // │         [🛠 Tools] [💬 AI Chat]                           │
  // ├────────────────────────────┬─────────────────────────────┤
  // │ LEFT PANEL (50%)           │ RIGHT PANEL (50%)           │
  // │                            │                             │
  // │ EditorTab / JournalTab     │ ChatTab (SSE streaming)     │
  // │ LiteratureTab / FilesTab   │                             │
  // │ DataTab / PreviewTab       │                             │
  // │ ToolsTab / ToolWorkspace   │                             │
  // ├────────────────────────────┴─────────────────────────────┤
  // │ AI Loading Banner (if aiLoading)                         │
  // └──────────────────────────────────────────────────────────┘

  STATE:
    store = usePaperStore()
    activeTab = null  // 'editor'|'journal'|'literature'|'files'|'data'|'preview'|'tools'
    chatOpen = true
    saveStatus = 'saved'|'saving'|'error'

  TABS_LIST (leftTabs):
    editor     → "Editor"       → ContentList
    journal    → "Journal"      → JournalTab
    literature → "Literature"   → LiteratureTab
    files      → "Files"        → FilesTab
    data       → "Data"         → DataTab
    preview    → "Preview"      → PreviewTab

  ON CREATED:
    paperId = route.params.paperId
    IF paperId: store.loadPaper(paperId)
    ELSE: store.initEmptyPaper()
    paperJobsStore.startPolling(paperId)
    quotaStore.startPolling()

  METHODS:
    toggleTab(tabId):     activeTab = tabId
    toggleChat():         chatOpen = !chatOpen
    toggleTools():        activeTab = 'tools' atau null
    handlePapersBack():   router.push('/dashboard')
    retrySave():          store.savePaper()

  KEYBOARD SHORTCUTS:
    Ctrl+Z        → Undo
    Ctrl+Shift+Z  → Redo
    Ctrl+S        → Save
    Ctrl+B        → Toggle chat
    ?             → Show shortcuts
```

### 7.6 `FilesPage.vue` (~231 lines)

```pseudo-code
COMPONENT FilesPage:
  STATE: files[], uploadProgress{}, dragOver

  TEMPLATE:
    - Drag & drop upload zone
    - File grid: thumbnail, name, size, date
    - Per-file: preview, download, delete
```

### 7.7 `AdminPage.vue` (~389 lines)

```pseudo-code
COMPONENT AdminPage:
  STATE:
    users[], allPapers[], usageStats
    activeSection = 'usage'|'papers'|'users'

  METHODS:
    fetchUsageStats(): GET /api/admin/usage
    fetchAllPapers():  GET /api/admin/papers
    fetchUsers():      GET /api/admin/users
    promoteUser(id):   POST /api/admin/users/:id/promote
    updateQuota(id, q): POST /api/admin/users/:id/quota {quota}
```

---

## 8. Components Detail

### 8.1 `ChatTab.vue` (~1520 lines) — Komponen Terbesar

```pseudo-code
COMPONENT ChatTab:
  PROPS: paperId
  STATE: conversations[], activeConversation, newMessage, fileInput

  TEMPLATE:
    - Conversation list (dropdown/sidebar)
    - Messages area (scrollable) → ChatMessage per message
    - Input area:
      ├── Textarea (v-autosize)
      ├── File attach button
      ├── Quick suggestion chips
      └── Send button
    - File drop overlay
    - Offline onboarding banner

  METHODS:
    async send():
      text = newMessage.trim()
      messages.push({role:'user', content:text})
      newMessage = ''
      chatStore.sendMessage(text, paperId, {attached_files})

    onFilePick(event):
      FOR EACH file:
        IF image → chatStore.pasteImage(file, paperId)
        ELSE    → chatStore.uploadFile(file, paperId)

    onDrop(event): HANDLE file drop

    handlePaste(event): HANDLE clipboard image paste

    handleSuggestionClick(s): newMessage = s.text; send()

    scrollToBottom(): auto-scroll saat streaming
```

### 8.2 `ChatMessage.vue` (~671 lines)

```pseudo-code
COMPONENT ChatMessage:
  PROPS: message {role, content, thinking, tool_calls, ...}

  TEMPLATE:
    - Role indicator
    - ThinkingBlock (jika ada)
    - Content (marked → DOMPurify → HTML)
    - ToolCallBlocks
    - PaperProgressBubble
    - ChartPreviewCard
    - FileReviewCard
    - MultiQuestionCard
    - RevisiProposalCard

  MESSAGE TYPES HANDLED:
    text, thinking, tool_call, paper_progress, chart,
    file_review, multi_question, proposal, slr, error

  METHODS:
    renderMarkdown(content): marked.parse() + DOMPurify.sanitize()
    handleAcceptProposal():  store.applyProposal()
    handleRejectProposal():  store.rejectProposal()
```

### 8.3 `ContentList.vue` (~465 lines)

```pseudo-code
COMPONENT ContentList:
  PROPS: sections (Array)
  // vuedraggable untuk reorder

  TEMPLATE FOR EACH section:
    - Section title (editable)
    - Draggable content blocks:
      - TextBlock   → textarea dengan markdown
      - ImageBlock  → upload/gallery/prompt/generate
      - TableBlock  → inline table editor
      - FormulaBlock → KaTeX math editor
    - Inline insert menu (hover antar blocks)
    - Add subsection button

  METHODS:
    addTextBlock / addImageBlock / removeBlock / moveBlock
    generateImage(blockIndex, prompt):
      imageGenStore.generateImage(...)
      SHOW loading state
    onTextChange(): recordChange()
```

### 8.4 `LiteratureTab.vue` (~1221 lines)

```pseudo-code
COMPONENT LiteratureTab:
  PROPS: paperId
  STATE: literature[], slrJobs[], activeS, filterSource, filterYear,
         sortBy, sortDir, selectedIds, showAddForm, editingItem

  ON CREATED:
    fetchLiterature()
    fetchSlrJobs()
    slrJobId = literatureStore.consumeSlrJobId()
    IF slrJobId: autoOpenResults()

  METHODS:
    async fetchLiterature(): GET /api/papers/:paperId/literature
    async runSlr(query, sources, topK):
      POST /api/papers/:paperId/slr/jobs {query, sources, top_k}
      START polling GET /api/slr/jobs/:jobId

    async addManualEntry(data):  POST /api/papers/:paperId/literature
    async updateItem(id, data):  PATCH /api/papers/:paperId/literature/:id
    async deleteItem(id):        DELETE /api/papers/:paperId/literature/:id
    async importFromFiles(ids):  POST /api/papers/:paperId/literature/from-files

    filteredLiterature():
      FILTER BY source, year
      SORT BY score/title/year

  TEMPLATE:
    - SLR Runner (query input, sources checkboxes, run button)
    - Job status card (progress)
    - Literature table (sortable columns)
    - Bulk actions (select all, delete selected, export)
    - Per-item: edit, delete, pin, toggle relevance
    - Manual add form (modal)
    - SLRResultsView (if SLR job done)
```

### 8.5 `FilesTab.vue` (~619 lines)

```pseudo-code
COMPONENT FilesTab:
  PROPS: paperId
  STATE: files[], activeSubTab='documents'|'figures', uploadProgress{},
         dragOver, previewingFile

  TEMPLATE:
    - Sub-tabs: Documents | Figures
    - Documents: list (name, size, date, extracted text preview)
    - Figures: gallery grid + AI image generation
    - Upload zone (drag & drop)
    - Upload progress bars

  METHODS:
    async uploadFiles(files):
      FOR EACH file: POST /api/papers/:paperId/files {file}
    async deleteFile(id):     DELETE /api/papers/:paperId/files/:id
    async previewText(fileId): GET /api/papers/:paperId/files/:fileId/preview
```

### 8.6 `DataTab.vue` (~769 lines)

```pseudo-code
COMPONENT DataTab:
  PROPS: paperId
  STATE: dataSources[], tables[], selectedTable, chartConfig, previewChart

  CHART_CONFIG: {type, xColumn, yColumn, groupColumn, title, labels, colors}

  METHODS:
    async uploadDataFile(file): POST /api/charts/:chartId/data
    parseTable(sourceId):       Parse CSV/Excel ke columns+rows
    updateChartConfig(k, v):    debouncedPreviewChart()
    async generateChart():      POST /api/charts {paper_id, config}
    async saveChartToPaper():   POST /api/charts/:id/save-to-paper

  // localStorage persistence
```

### 8.7 `PreviewTab.vue` (~362 lines)

```pseudo-code
COMPONENT PreviewTab:
  STATE: previewMode='formatted'|'raw', editMode=false

  METHODS:
    formattedPreview():
      sections = buildNumberedSections(paper)
      references = formatIEEE(paper.references)
      RETURN formatted HTML dengan inline diffs untuk pending changes

    toggleEditMode(): editMode = !editMode
    async exportDocx(): store.exportDocx()

  TEMPLATE:
    - Toolbar: Mode toggle, Edit toggle, Export DOCX
    - Preview area: rendered IEEE-formatted paper
```

### 8.8 `RevisiProposalCard.vue` (~220 lines)

```pseudo-code
COMPONENT RevisiProposalCard:
  PROPS: proposal, sectionIndex, blockIndex
  TEMPLATE:
    - Original text (left) | Proposed text (right)
    - Accept / Reject buttons
  METHODS:
    handleAccept(): store.applyProposal(...)
    handleReject(): store.rejectProposal(...)
```

### 8.9 `MultiQuestionCard.vue` (~516 lines)

```pseudo-code
COMPONENT MultiQuestionCard:
  PROPS: job, questions, proposal
  STATE: answers{}, draft{}

  TEMPLATE FOR EACH question:
    SWITCH question.type:
      case 'text'     → Text input
      case 'textarea' → Textarea
      case 'select'   → Dropdown
      case 'chips'    → Multi-select chip buttons
      case 'radio'    → Radio buttons
      case 'number'   → Number input

  ON answers CHANGE: localStorage.setItem('multi_q_draft_'+job.id, answers)

  METHODS:
    submit(): POST /api/chat/answers {job_id, answers}
    saveDraft(): localStorage persist
```

### 8.10 `MetadataTab.vue` (~138 lines)

```pseudo-code
COMPONENT MetadataTab:
  // Title, Authors, Abstract, Keywords, Acknowledgment
  // Masing-masing punya tombol AI generate
  METHODS:
    generateTitle():    chatStore.send(AI_GENERATE_TITLE_PROMPT)
    generateAbstract(): chatStore.send(AI_GENERATE_ABSTRACT_PROMPT)
    generateKeywords(): chatStore.send(AI_GENERATE_KEYWORDS_PROMPT)
```

### 8.11 `JournalTab.vue` (~122 lines)

```pseudo-code
COMPONENT JournalTab:
  STATE: journals=[], searchQuery='', selectedJournal='IEEE'

  METHODS:
    async fetchJournals(): GET /api/journals
    selectJournal(code): journalStore.setJournal(code)
    searchJournals(query): filter by name/code
```

### 8.12 `AppHeader.vue` (~238 lines)

```pseudo-code
COMPONENT AppHeader:
  STATE: showUserMenu, jobNotifications[]

  TEMPLATE:
    - Logo + title
    - Quota bar (percent used)
    - Job bell notification (activeJobs badge)
    - User menu dropdown:
      - Theme switcher (light/dark/system)
      - Profile
      - Admin panel (if admin)
      - Logout

  METHODS:
    async handleLogout(): authStore.logout()
    setTheme(mode):      themeStore.setTheme(mode)
    toggleJobPanel():    show/hide job notifications
```

---

## 9. Services

### 9.1 `errorHandler.ts` (~255 lines)

```pseudo-code
CLASS ErrorHandler:
  METHODS:
    parseError(error) → {code, message, category, retryable}

    getMessage(code, level) → user-friendly message
      // level: 'beginner' | 'intermediate' | 'advanced'

    getRecoveryStrategy(code):
      SWITCH code:
        'NETWORK_ERROR'  → retry with backoff
        'TOKEN_EXPIRED'  → refresh token
        'TIMEOUT'        → retry once
        'RATE_LIMITED'   → wait & retry
        'SERVER_ERROR'   → retry with backoff

    retry(fn, options):
      maxRetries = options.max || 3
      FOR i IN 0..maxRetries:
        TRY: RETURN await fn()
        CATCH: SLEEP(1000 * 2^i)
```

### 9.2 `globalErrorHandler.ts` (~49 lines)

```pseudo-code
FUNGSI setupErrorHandler(app):
  app.config.errorHandler = (err, vm, info):
    logger.error('Vue error', {error: err, component: vm, info})

  window.addEventListener('unhandledrejection', event):
    logger.error('Unhandled rejection', {reason: event.reason})
```

---

## 10. Utils

### 10.1 `logger.ts` (~193 lines)

```pseudo-code
CLASS Logger:
  STATE: buffer=[], flushInterval=5000ms, maxBufferSize=100

  METHODS:
    debug/info/warn/error(message, data):
      entry = {level, message, data, timestamp, sessionId}
      buffer.push(entry)
      IF buffer.length >= maxBufferSize: flush()

    flush():
      IF buffer empty: RETURN
      POST /api/logs {logs: buffer}
      buffer = []

    trackPerformance(operation, duration):
      log('info', 'performance', {operation, duration})

    trackUserAction(action, data):
      log('info', 'user_action', {action, data})

  SET_INTERVAL(5000, flush)
  window.addEventListener('beforeunload', flush)
```

### 10.2 `errorMessages.ts` (~242 lines)

```pseudo-code
// Mapping error codes → Bahasa Indonesia messages
ERROR_MESSAGES:
  NETWORK_ERROR:          "Koneksi internet terputus..."
  TOKEN_EXPIRED:          "Sesi Anda berakhir. Silakan login kembali."
  RATE_LIMITED:           "Terlalu banyak request. Coba lagi nanti."
  FILE_TOO_LARGE:         "File terlalu besar. Maksimum 30MB."
  AI_GENERATION_FAILED:   "AI gagal membuat paper. Coba lagi."
  VALIDATION_FAILED:      "Data yang dikirim tidak valid."
  UNAUTHORIZED:           "Anda tidak memiliki akses."
  NOT_FOUND:              "Data tidak ditemukan."
  SERVER_ERROR:           "Terjadi kesalahan server."
  // ... 40+ more mappings
```

---

## 11. Types (`src/types/`)

### 11.1 `components.ts` (~135 lines)

```pseudo-code
TYPE Author = { name: string, affiliation: string, location?: string, email?: string }
TYPE ContentBlock = { id: string, text?: string, url?: string, caption?: string, ... }
TYPE Section = { title: string, content: ContentBlock[], subsections: Section[] }
TYPE Reference = string | { text: string, doi?: string }
TYPE Figure = { caption: string, hasImage: boolean, filename: string, url: string }
TYPE PaperData = { journal, title, authors[], abstract, keywords[], sections[], references[], figures[] }
TYPE ChatMessage = { id, role:'user'|'assistant'|'system', content, thinking?, tool_calls?, createdAt }
TYPE Conversation = { id, paperId, title, messages[], messageCount, createdAt, updatedAt }
TYPE JobInfo = { id, status, progress, stage, error?, started_at?, updated_at? }
TYPE QuotaInfo = { monthlyLimit, used, byModel: Record<string, number> }
```

### 11.2 `slr.ts` (~100 lines)

```pseudo-code
TYPE LiteraturePaper = { title, authors[], year, venue, doi, url, abstract, citations, score }
TYPE SlrResult = { papers[], stats: {total, bySource}, aiSummary }
TYPE LiteratureItem = {
  id, paperId, sourceKind:'slr'|'file'|'manual', source,
  title, authors[], year, venue, publisher, doi, url, pdfUrl,
  abstract, summary, citations, scoreTotal, scoreBreakdown,
  mustRead, isRelevant, notes, pinned, fileId, slrJobId
}
```

---

## 12. Composables

### 12.1 `useKeyboardShortcuts.ts` (~63 lines)

```pseudo-code
FUNGSI useKeyboardShortcuts():
  shortcuts = new Map()

  function bind(keyCombo, handler):
    // keyCombo: "ctrl+s", "ctrl+shift+z", "?"
    shortcuts.set(normalize(keyCombo), handler)

  function handleKeydown(event):
    combo = buildCombo(event)
    handler = shortcuts.get(combo)
    IF handler: event.preventDefault(); handler()

  ON MOUNTED:   document.addEventListener('keydown', handleKeydown)
  ON UNMOUNTED: document.removeEventListener('keydown', handleKeydown)

  RETURN { bind, unbind }
```

### 12.2 `useSanitize.ts` (~42 lines)

```pseudo-code
FUNGSI useSanitize():
  function sanitizeHtml(html):
    DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [b,i,em,strong,a,p,br,ul,ol,li,h1-h4,pre,code,
                      blockquote,table,thead,tbody,tr,td,th,img,span,div,add,del],
      ALLOWED_ATTR: [href,title,src,alt,class,data-math]
    })

  function sanitizeMath(text):
    // Allow: $...$, $$...\$, \(...\), \[...\]
    // Escape potentially dangerous content outside math delimiters
```

---

## 13. Integrasi Frontend ↔ Backend

### 13.1 Mapping Endpoint → Store → Component

```
┌──────────────────────────────┬──────────────────────────────┬──────────────────────┐
│ ENDPOINT                     │ STORE                        │ COMPONENT            │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ POST /api/auth/login         │ auth.login()                 │ LoginPage            │
│ POST /api/auth/register      │ auth.register()              │ LoginPage            │
│ GET  /api/auth/google/login  │ auth.loginWithGoogle()       │ LoginPage            │
│ GET  /api/auth/me            │ auth.fetchMe()               │ AppHeader            │
│ POST /api/auth/logout        │ auth.logout()                │ AppHeader            │
│ POST /api/auth/refresh       │ (axios interceptor)          │ (otomatis)           │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ GET  /api/papers             │ paper.loadPapers()           │ DashboardPage        │
│ POST /api/papers             │ paper.createPaper()          │ DashboardPage        │
│ GET  /api/papers/:id         │ paper.loadPaper()            │ PaperEditorPage      │
│ PATCH /api/papers/:id        │ paper.savePaper()            │ PaperEditorPage      │
│ DELETE /api/papers/:id       │ paper.deletePaper()          │ DashboardPage        │
│ POST /api/papers/:id/copy    │ paper.copyPaper()            │ DashboardPage        │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ GET  /api/papers/:id/chat    │ chat.fetchConversations()    │ ChatTab              │
│ POST /api/chat/stream        │ chat.sendMessage()           │ ChatTab              │
│ POST /api/chat/:id/messages  │ chat.selectConversation()   │ ChatTab              │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ POST /api/generate           │ paper.promptGenerate()       │ PaperEditorPage      │
│ GET  /api/job/:id            │ paperJobs.fetchActiveJobs()  │ PaperEditorPage      │
│ GET  /api/jobs/:id/stream    │ paperJobs.listenToEvents()   │ PaperProgressBubble  │
│ POST /api/jobs/:id/cancel    │ paperJobs.cancelJob()        │ PaperProgressBubble  │
│ POST /api/ai-jobs/:id/resume │ paperJobs.resumeJob()        │ PaperProgressBubble  │
│ POST /api/ai-jobs/:id/retry  │ paperJobs.retrySection()     │ PaperProgressBubble  │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ POST /api/image-jobs         │ imageGen.generateImage()     │ ContentList          │
│ GET  /api/image-jobs         │ imageGen.startPolling()      │ ContentList          │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ GET  /api/papers/:id/files   │ filesTab.fetchFiles()       │ FilesTab             │
│ POST /api/papers/:id/files   │ filesTab.uploadFiles()       │ FilesTab             │
│ DEL  /api/papers/:id/files/n │ filesTab.deleteFile()       │ FilesTab             │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ POST /api/tools/paraphrase   │ tools.runTool()              │ ToolWorkspace        │
│ POST /api/tools/translate    │ tools.runTool()              │ ToolWorkspace        │
│ POST /api/tools/grammar      │ tools.runTool()              │ ToolWorkspace        │
│ POST /api/tools/humanizer    │ tools.runTool()              │ ToolWorkspace        │
│ POST /api/tools/detector     │ tools.runTool()              │ ToolGauge            │
│ POST /api/tools/plagiarism   │ tools.runTool()              │ ToolGauge            │
│ POST /api/tools/summarize    │ tools.runTool()              │ ToolWorkspace        │
│ POST /api/tools/citation     │ tools.runTool()              │ ToolWorkspace        │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ GET  /api/papers/:id/lit     │ litTab.fetchLiterature()    │ LiteratureTab        │
│ POST /api/papers/:id/slr     │ litTab.runSlr()              │ LiteratureTab        │
│ GET  /api/slr/jobs/:id       │ litTab.pollSlrJob()          │ SLRResultsView       │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ GET  /api/quota              │ quota.fetchQuota()           │ AppHeader            │
│ GET  /api/quota/history      │ quota.fetchUsageHistory()   │ AdminPage            │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ GET  /api/admin/usage        │ admin.fetchUsageStats()      │ AdminPage            │
│ GET  /api/admin/papers       │ admin.fetchAllPapers()       │ AdminPage            │
│ GET  /api/admin/users        │ admin.fetchUsers()           │ AdminPage            │
│ POST /api/admin/users/:id/   │ admin.promoteUser()          │ AdminPage            │
│ POST /api/admin/users/:id/   │ admin.updateQuota()          │ AdminPage            │
├──────────────────────────────┼──────────────────────────────┼──────────────────────┤
│ GET  /api/charts             │ charts.getCharts()           │ DataTab              │
│ POST /api/charts             │ charts.createChart()         │ DataTab              │
│ POST /api/export/docx        │ paper.exportDocx()           │ PreviewTab           │
│ POST /api/logs               │ logger.flush()               │ (global)             │
└──────────────────────────────┴──────────────────────────────┴──────────────────────┘
```

### 13.2 Pola SSE (Server-Sent Events)

```
┌────────────────────────────────────────────────────────────┐
│                   SSE STREAM PATTERN                       │
│                                                            │
│  Frontend                          Backend                  │
│  ────────                          ───────                  │
│       ── POST /api/chat/stream ──▶                          │
│       ◀── data: {"type":"thinking","content":"..."} ──     │
│       ◀── data: {"type":"content","content":"..."} ──      │
│       ◀── data: {"type":"tool_call","tool":{...}} ──       │
│       ◀── data: {"type":"proposal","proposal":{...}} ──    │
│       ◀── data: {"type":"chart","chart":{...}} ──          │
│       ◀── data: {"type":"file_review","review":{...}} ──   │
│       ◀── data: {"type":"multi_question","qs":[...]} ──    │
│       ◀── data: {"type":"slr","results":{...}} ──          │
│       ◀── data: {"type":"done"} ──                         │
│                                                            │
│  ChatStore:                                                │
│    streaming = true                                        │
│    FOR EACH event IN stream:                               │
│      SWITCH event.type:                                    │
│        thinking   → streamingThinking += content           │
│        content    → streamingContent += content            │
│        tool_call  → handleToolCall(tool)                   │
│        proposal   → handleProposal(proposal)               │
│        done       → FINALIZE; streaming = false            │
│                                                            │
│  ChatTab (UI):                                             │
│    Watch streamingContent → re-render message              │
│    scrollToBottom()                                        │
└────────────────────────────────────────────────────────────┘
```

### 13.3 Vite Proxy (Development)

```
Browser :5173 ──/api/*──▶ Vite Dev Server ──proxy──▶ Backend :8001

vite.config.ts:
  proxy: {
    '/api': {
      target: 'http://localhost:8001',
      changeOrigin: true,
      proxyTimeout: 0,   // No timeout untuk SSE
      timeout: 0
    }
  }

Production:
  Vite build → static files → served by Nginx/Backend
  API calls langsung ke backend (same origin atau CORS)
```

---

## 14. Build & Scripts

```pseudo-code
// package.json scripts:

"dev"       → vite --host                    # Dev server :5173
"build"     → vue-tsc --noEmit && vite build # Type-check + production build
"type-check"→ vue-tsc --noEmit              # Type check saja
"preview"   → vite preview                  # Preview production build

"test:unit"          → vitest run             # Unit test
"test:unit:watch"    → vitest                 # Unit test watch mode
"test:unit:coverage" → vitest run --coverage  # Coverage

"test:e2e"           → playwright test        # E2E test
"test:e2e:ui"        → playwright test --ui   # E2E dengan UI

"test:load"          → playwright (load config) # Load testing
"test:load:concurrent" → concurrent users test
"test:load:race"     → race conditions test
"test:load:queue"    → queue management test

"lint"     → eslint src --ext .vue,.ts,.js --fix
"format"   → prettier --write src/
```

### Build Output

```
dist/
├── assets/
│   ├── js/
│   │   ├── vue-vendor-[hash].js     # Vue + Router + Pinia
│   │   ├── markdown-[hash].js       # marked + DOMPurify
│   │   ├── highlight-[hash].js      # highlight.js
│   │   ├── katex-[hash].js          # KaTeX
│   │   └── index-[hash].js          # App code
│   ├── images/
│   │   └── [name]-[hash].[ext]
│   └── fonts/
│       └── [name]-[hash].[ext]
└── index.html
```

---

## 15. Ringkasan Fitur

| Fitur | Komponen/Store | Endpoint |
|-------|---------------|----------|
| Login/Register (email+password) | LoginPage, auth.ts | POST /api/auth/login, /register |
| Google OAuth | LoginPage, AuthCallbackPage | GET /api/auth/google/* |
| JWT + Refresh Token | api/index.ts (interceptor) | POST /api/auth/refresh |
| Dashboard paper list | DashboardPage, paper.ts | GET /api/papers |
| Create/Copy/Delete paper | DashboardPage, paper.ts | POST/DELETE /api/papers/:id |
| Editor WYSIWYG | PaperEditorPage, ContentList | — |
| Section CRUD | paper.ts | PATCH /api/papers/:id |
| Author management | paper.ts | PATCH /api/papers/:id |
| Undo/Redo | paper.ts (stack-based) | — (local) |
| AI Paper Generation | paper.ts, paperJobs.ts | POST /api/generate, /api/jobs SSE |
| Job progress/cancel/resume | PaperProgressBubble | POST /api/jobs/:id/* |
| AI Chat (SSE streaming) | ChatTab, chat.ts | POST /api/chat/stream |
| Tool calls | ChatMessage, ToolCallBlock | (via chat stream |
| Proposals (paraphrase/etc) | RevisiProposalCard | (via chat stream) |
| File attachment | ChatTab | POST /api/papers/:id/files |
| Writing tools (8 tools) | ToolWorkspace, tools.ts | POST /api/tools/:tool |
| SLR search | LiteratureTab | POST /api/slr/jobs |
| SLR results | SLRResultsView | GET /api/slr/jobs/:id |
| Literature management | LiteratureTab | CRUD /api/papers/:id/literature |
| Image generation | ContentList, imageGen.ts | POST /api/image-jobs |
| Chart creation | DataTab | POST /api/charts |
| DOCX export | PreviewTab, paper.ts | POST /api/export/docx |
| Token quota | AppHeader, quota.ts | GET /api/quota |
| Theme (light/dark/system) | AppHeader, theme.ts | — (localStorage) |
| Admin panel | AdminPage | GET /api/admin/* |
| Keyboard shortcuts | ShortcutsHelp, composables | — |
| Offline support | chat.ts (queue) | — |
| Error handling | errorHandler.ts, globalErrorHandler.ts | — |
| Log shipping | logger.ts | POST /api/logs |
| Multi-question form | MultiQuestionCard | POST /api/chat/answers |
