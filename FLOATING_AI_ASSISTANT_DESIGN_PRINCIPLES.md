# Floating AI Assistant Design Principles

## Core Philosophy
**Single global conversation that persists across all pages, with per-paper context isolation.** The AI Assistant is a non-modal, floating sidekick — always available, never blocking, context-aware.

---

## 1. Non-Modal Floating Panel
- **Always visible** (collapsible) on right/bottom edge across Dashboard, Paper Editor, Literature, Settings
- **Never blocks** tools, editor, preview, or navigation
- **Side-by-side workflow**: User runs tools, edits paper, navigates — chat stays accessible
- **No context switching**: Ask AI while tool runs; check tool output while AI responds

---

## 2. Global Conversation Persistence
- **One conversation instance** shared across all routes (Dashboard ↔ Paper Editor ↔ Literature ↔ Settings)
- **Messages persist** on route change — no reset, no reload
- **Scroll position preserved** when switching pages

---

## 3. Per-Paper Conversation Isolation
- Each paper has its **own conversation thread** (messages, context, decisions)
- **Switch paper → AI detects & warns**:
  > "Kamu pindah ke *Paper B*. Lanjutkan conversation Paper B? (Belum ada → buat baru)"
- **Dashboard (no paperId)** → Global/onboarding mode: ideation, paper discovery, planning

---

## 4. Context Awareness (AI Knows What User Is Doing)
`viewContext` object passed to AI on every message:
```typescript
interface ViewContext {
  page: 'dashboard' | 'editor' | 'literature' | 'settings' | 'tools';
  paperId?: string;
  paperTitle?: string;
  activeTool?: string;           // e.g., 'paraphrase', 'query-planner'
  editorMode?: 'edit' | 'preview' | 'split';
  selection?: string;            // highlighted text in editor
  toolOutput?: any;              // latest tool result
}
```
AI responses adapt: "Di editor *Paper A*, kamu lagi mode preview..." / "Di dashboard, kamu belom punya paper..."

---

## 5. Conversation Lifecycle
| Event | Behavior |
|-------|----------|
| **Login / first visit** | Global empty conversation (onboarding mode) |
| **Create new paper** | New paperId → new conversation thread auto-created |
| **Open existing paper** | Load that paper's conversation thread |
| **Switch paper (editor)** | Warn → save current thread → load target thread |
| **Dashboard click** | Show global thread (filterable by paper) |
| **Hard refresh** | Restore from store (IndexedDB/localStorage + server sync) |

---

## 6. UI/UX Rules
- **Floating button** (bottom-right) opens/closes panel — never covers main content
- **Panel width**: 380px desktop, full-width mobile bottom sheet
- **Collapse → pill** showing paper title / "Global Assistant"
- **Scroll-to-bottom** button (>60px from bottom) with eased animation
- **Auto-scroll off** when user scrolls up; on when AI emits new message
- **Visual distinction**: Each message tagged with paper context badge ("Paper A", "Global")

---

## 7. Technical Architecture
- **Single Pinia store** `useChatStore` (global singleton)
- **No per-page chat components** — one `FloatingChatPanel.vue` mounted in `App.vue`
- **Route watcher** updates `viewContext` → AI system prompt includes context
- **Per-paper threads** stored in `chatStore.threads: Map<paperId, Thread>`
- **Backend**: single conversation API, `paperId` optional filter

---

## 8. Benefits Over Modal/Per-Page Chat
| Problem (Current) | Floating Solution |
|-------------------|-------------------|
| Close chat to use tools | Chat + tools side-by-side |
| Close tool to ask AI | Ask AI while tool runs |
| Conversation lost on nav | Single persistent conversation |
| Dashboard = dead end | Dashboard = AI onboarding hub |
| No cross-paper reference | Global history filterable by paper |
| New user: "Mulai dari mana?" | AI: "Mau bikin paper apa?" |

---

## 9. Implementation Priority (When Ready)
1. `useChatStore` singleton + `FloatingChatPanel.vue` in `App.vue`
2. Route watcher → `viewContext` update
3. Per-paper thread map + switch logic with warning modal
4. Dashboard global mode (paper discovery, ideation)
5. Context injection to AI system prompt
6. Persistence (IndexedDB + server sync)
7. Scroll behavior + UI polish

---

## 10. Decision Log
- **2026-07-10**: Principles documented per user + dosen discussion
- Per-paper isolation > global free-for-all (dosen feedback)
- Floating non-modal > modal full-screen (tool+chat parallel workflow)
- Global persistence across nav = mandatory
- Dashboard = onboarding entry point, not dead space

---

*This document is the source of truth for Floating AI Assistant behavior. Any implementation must follow these principles.*