import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const LS_KEY = 'pg_ui_state_v1'

interface PaperUiState {
  activeTab: string
  chatOpen: boolean
}

interface UiState {
  perPaper: Record<string, PaperUiState>
}

function load(): UiState {
  try {
    const raw = localStorage.getItem(LS_KEY)
    return raw ? JSON.parse(raw) : { perPaper: {} }
  } catch {
    return { perPaper: {} }
  }
}

function save(state: UiState): void {
  try { localStorage.setItem(LS_KEY, JSON.stringify(state)) } catch { /* quota */ }
}

export const useUiStore = defineStore('ui', () => {
  const stored = load()
  const perPaper = ref<Record<string, PaperUiState>>(stored.perPaper || {})

  const tabSwitchSignal = ref(0)

  watch(perPaper, (s) => save({ perPaper: s }), { deep: true })

  function _entry(paperId: string | null | undefined): PaperUiState | null {
    if (!paperId) return null
    if (!perPaper.value[paperId]) {
      perPaper.value[paperId] = { activeTab: '', chatOpen: true }
    }
    return perPaper.value[paperId]
  }

  function getTab(paperId: string): string {
    return _entry(paperId)?.activeTab ?? ''
  }

  function setTab(paperId: string, tabId: string): void {
    const e = _entry(paperId)
    if (e) e.activeTab = tabId || ''
  }

  function getChatOpen(paperId: string): boolean {
    return _entry(paperId)?.chatOpen ?? true
  }

  function setChatOpen(paperId: string, isOpen: boolean): void {
    const e = _entry(paperId)
    if (e) e.chatOpen = !!isOpen
  }

  function reset(paperId: string): void {
    if (paperId && perPaper.value[paperId]) {
      delete perPaper.value[paperId]
    }
  }

  function requestTab(paperId: string, tabId: string): void {
    setTab(paperId, tabId)
    tabSwitchSignal.value += 1
  }

  return {
    tabSwitchSignal,
    getTab, setTab, getChatOpen, setChatOpen, reset, requestTab,
  }
})
