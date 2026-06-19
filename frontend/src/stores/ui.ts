import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useUserStateStore } from './userState'

const LS_KEY = 'pg_ui_state_v2'

interface PaperUiState {
  activeTab: string
  rightPanel: string
  toolsOpen: boolean
  editorVisible: boolean
}

interface UiState {
  perPaper: Record<string, PaperUiState>
}

function load(): UiState {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (raw) return JSON.parse(raw)
    // Migrate from v1
    const rawV1 = localStorage.getItem('pg_ui_state_v1')
    if (rawV1) {
      const v1 = JSON.parse(rawV1)
      const migrated: Record<string, PaperUiState> = {}
      for (const [k, v] of Object.entries(v1.perPaper || {})) {
        migrated[k] = { activeTab: (v as any).activeTab || 'editor', rightPanel: '', toolsOpen: false, editorVisible: true }
      }
      localStorage.removeItem('pg_ui_state_v1')
      return { perPaper: migrated }
    }
    return { perPaper: {} }
  } catch {
    return { perPaper: {} }
  }
}

function save(state: UiState): void {
  try { localStorage.setItem(LS_KEY, JSON.stringify(state)) } catch { /* quota */ }
}

export const useUiStore = defineStore('ui', () => {
  const userState = useUserStateStore()
  const stored = load()
  const perPaper = ref<Record<string, PaperUiState>>(stored.perPaper || {})

  const tabSwitchSignal = ref(0)

  // Watch for changes and sync to userState (debounced via userState store).
  // Only set keys that actually changed to avoid unnecessary DB writes.
  let _lastPerPaper = JSON.stringify(perPaper.value)
  watch(perPaper, (s) => {
    save({ perPaper: s })
    const snap = JSON.stringify(s)
    _lastPerPaper = snap
    void _lastPerPaper
  }, { deep: true })

  function _entry(paperId: string | null | undefined): PaperUiState | null {
    if (!paperId) return null
    if (!perPaper.value[paperId]) {
      perPaper.value[paperId] = { activeTab: 'editor', rightPanel: '', toolsOpen: false, editorVisible: true }
    }
    return perPaper.value[paperId]
  }

  function getTab(paperId: string): string {
    // Try userState first (server-synced), fallback to localStorage
    const fromServer = userState.get('ui.tab', paperId, null)
    if (fromServer) return fromServer
    return _entry(paperId)?.activeTab ?? ''
  }

  function setTab(paperId: string, tabId: string): void {
    const e = _entry(paperId)
    if (e) e.activeTab = tabId || ''
    if (paperId) userState.set('ui.tab', paperId, tabId || '')
  }

  function getRightPanel(paperId: string): string {
    const fromServer = userState.get('ui.right_panel', paperId, null)
    if (fromServer) return fromServer
    return _entry(paperId)?.rightPanel ?? ''
  }

  function setRightPanel(paperId: string, panel: string): void {
    const e = _entry(paperId)
    if (e) e.rightPanel = panel || ''
    if (paperId) userState.set('ui.right_panel', paperId, panel || '')
  }

  function getToolsOpen(paperId: string): boolean {
    const fromServer = userState.get('ui.tools_open', paperId, null)
    if (fromServer !== null) return fromServer
    return _entry(paperId)?.toolsOpen ?? false
  }

  function setToolsOpen(paperId: string, open: boolean): void {
    const e = _entry(paperId)
    if (e) e.toolsOpen = open
    if (paperId) userState.set('ui.tools_open', paperId, open)
  }

  function getEditorVisible(paperId: string): boolean {
    const fromServer = userState.get('ui.editor_visible', paperId, null)
    if (fromServer !== null) return fromServer
    return _entry(paperId)?.editorVisible ?? true
  }

  function setEditorVisible(paperId: string, visible: boolean): void {
    const e = _entry(paperId)
    if (e) e.editorVisible = visible
    if (paperId) userState.set('ui.editor_visible', paperId, visible)
  }

  function switchToTab(paperId: string, tabId: string): void {
    setTab(paperId, tabId)
    tabSwitchSignal.value++
  }

  return {
    perPaper,
    tabSwitchSignal,
    getTab,
    setTab,
    getRightPanel,
    setRightPanel,
    getToolsOpen,
    setToolsOpen,
    getEditorVisible,
    setEditorVisible,
    switchToTab,
  }
})
