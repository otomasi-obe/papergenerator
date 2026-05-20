/**
 * UI store — persists per-paper UI state (active tab, chat panel open) ke
 * localStorage. Implementasi rofiq.txt #2 dan #3:
 *   - Tab terakhir yang dipilih user di-restore saat user balik ke paper itu.
 *   - Saat tidak ada tab dipilih (activeTab=''), chat panel auto full-screen.
 */
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

const LS_KEY = 'pg_ui_state_v1'

function load() {
  try {
    const raw = localStorage.getItem(LS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function save(state) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(state)) } catch { /* quota */ }
}

export const useUiStore = defineStore('ui', () => {
  // shape: { perPaper: { [paperId]: { activeTab, chatOpen } } }
  const stored = load()
  const perPaper = ref(stored.perPaper || {})

  watch(perPaper, (s) => save({ perPaper: s }), { deep: true })

  function _entry(paperId) {
    if (!paperId) return null
    if (!perPaper.value[paperId]) {
      // Default sesuai rofiq.txt #3: paper baru → chat full (no tab)
      perPaper.value[paperId] = { activeTab: '', chatOpen: true }
    }
    return perPaper.value[paperId]
  }

  function getTab(paperId) {
    return _entry(paperId)?.activeTab ?? ''
  }

  function setTab(paperId, tabId) {
    const e = _entry(paperId)
    if (e) e.activeTab = tabId || ''
  }

  function getChatOpen(paperId) {
    return _entry(paperId)?.chatOpen ?? true
  }

  function setChatOpen(paperId, isOpen) {
    const e = _entry(paperId)
    if (e) e.chatOpen = !!isOpen
  }

  function reset(paperId) {
    if (paperId && perPaper.value[paperId]) {
      delete perPaper.value[paperId]
    }
  }

  return { getTab, setTab, getChatOpen, setChatOpen, reset }
})
