/**
 * User State Store — centralized server-side state persistence.
 * 
 * Replaces scattered localStorage with a single PostgreSQL-backed store.
 * State survives refresh, tab close, device switch, and is isolated per user.
 * 
 * Architecture:
 *   - On app init: 1x GET loads ALL state for current user
 *   - On state change: debounced batch PUT (every 2s, all dirty keys → 1 call)
 *   - Fallback: localStorage cache for instant UI on reload (before server sync)
 * 
 * Usage in components:
 *   import { useUserStateStore } from '@/stores/userState'
 *   const userState = useUserStateStore()
 * 
 *   // Get state (returns default if not set)
 *   const chatInput = userState.get('chat.input_text', paperId, '')
 *   const panel = userState.get('ui.right_panel', null, 'chat')
 * 
 *   // Set state (debounced save to DB)
 *   userState.set('chat.input_text', paperId, 'hello world')
 *   userState.set('ui.right_panel', null, 'data')
 * 
 *   // Delete state
 *   userState.deleteKey('chat.input_text', paperId)
 * 
 *   // Flush immediately (e.g., before page unload)
 *   await userState.flush()
 */

import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import api from '../api/index.js'

const LS_CACHE_KEY = 'pg_state_cache'
const DEBOUNCE_MS = 2000

interface StateEntry {
  key: string
  paper_id: string | null
  value: any
}

// Build a composite key for the internal map: "paperId|key" or "|key" (global)
function _mk(paperId: string | null, key: string): string {
  return `${paperId || ''}|${key}`
}

export const useUserStateStore = defineStore('userState', () => {
  // Internal state map: compositeKey → value.
  // Use reactive() (not ref of object) so that adding/removing keys via the
  // proxy stays reactive for both new AND existing keys. get() reads through
  // this proxy so getters (getTab/getRightPanel/getToolsOpen) track deps.
  const _map = reactive<Record<string, any>>({})
  // Set of composite keys that are dirty (need saving)
  const _dirty = new Set<string>()
  // Debounce timer
  let _timer: ReturnType<typeof setTimeout> | null = null
  // Whether initial load from server is done
  const loaded = ref(false)
  // Whether a save is in progress
  const saving = ref(false)

  // ─── Load from localStorage cache (instant) then server (async) ──────────

  function _loadFromCache() {
    try {
      const raw = localStorage.getItem(LS_CACHE_KEY)
      if (raw) {
        const entries: StateEntry[] = JSON.parse(raw)
        for (const e of entries) {
          _map[_mk(e.paper_id, e.key)] = e.value
        }
      }
    } catch { /* ignore corrupt cache */ }
  }

  async function loadFromServer(): Promise<void> {
    // Load cache first for instant UI
    _loadFromCache()

    try {
      const res = await api.get('/api/me/state')
      const state = res.data?.state || {}

      // Server returns flat dict: {key: value} for global state
      // For paper-scoped state, we need to load per-paper
      // For now, load all global state
      for (const [key, value] of Object.entries(state)) {
        _map[_mk(null, key)] = value
      }

      // Also update localStorage cache
      _saveToCache()
      loaded.value = true
    } catch {
      // Server unreachable — use cache only, will sync on next save
      loaded.value = true
    }
  }

  async function loadForPaper(paperId: string): Promise<void> {
    if (!paperId) return
    try {
      const res = await api.get('/api/me/state', { params: { paper_id: paperId } })
      const state = res.data?.state || {}
      for (const [key, value] of Object.entries(state)) {
        _map[_mk(paperId, key)] = value
      }
      _saveToCache()
    } catch { /* ignore */ }
  }

  function _saveToCache() {
    try {
      const entries: StateEntry[] = []
      for (const [compositeKey, value] of Object.entries(_map)) {
        const pipeIdx = compositeKey.indexOf('|')
        const paperId = compositeKey.slice(0, pipeIdx) || null
        const key = compositeKey.slice(pipeIdx + 1)
        entries.push({ key, paper_id: paperId, value })
      }
      // Cap cache at 500KB to avoid localStorage quota issues.
      // If over limit, evict oldest entries (keep most recent subset).
      let json = JSON.stringify(entries)
      const MAX_BYTES = 500_000
      if (json.length >= MAX_BYTES) {
        // Sort by compositeKey (which encodes paperId) — this is a rough
        // proxy for recency since newer entries tend to get set more often.
        // Better than nothing; the server always has the full truth.
        entries.sort((a, b) => b.key.localeCompare(a.key))
        // Iteratively drop the tail until under limit
        while (json.length >= MAX_BYTES && entries.length > 1) {
          entries.pop()
          json = JSON.stringify(entries)
        }
      }
      if (json.length < MAX_BYTES) {
        localStorage.setItem(LS_CACHE_KEY, json)
      }
    } catch { /* quota exceeded, ignore */ }
  }

  // ─── Public API ──────────────────────────────────────────────────────────

  function get(key: string, paperId: string | null = null, defaultValue: any = null): any {
    const ck = _mk(paperId, key)
    return ck in _map ? _map[ck] : defaultValue
  }

  function set(key: string, paperId: string | null, value: any): void {
    const ck = _mk(paperId, key)
    _map[ck] = value
    _dirty.add(ck)
    _scheduleSave()
  }

  function deleteKey(key: string, paperId: string | null = null): void {
    const ck = _mk(paperId, key)
    delete _map[ck]
    _dirty.add(ck) // Will be sent as null in batch save
    _scheduleSave()
  }

  function _scheduleSave() {
    if (_timer) clearTimeout(_timer)
    _timer = setTimeout(() => flush(), DEBOUNCE_MS)
  }

  async function flush(): Promise<void> {
    if (_dirty.size === 0) return
    if (saving.value) return

    saving.value = true
    const items: Array<{ key: string; paper_id: string | null; value: any }> = []

    for (const ck of _dirty) {
      const pipeIdx = ck.indexOf('|')
      const paperId = ck.slice(0, pipeIdx) || null
      const key = ck.slice(pipeIdx + 1)
      const value = _map[ck] ?? null
      items.push({ key, paper_id: paperId, value })
    }

    _dirty.clear()

    try {
      await api.put('/api/me/state', { items })
      _saveToCache()
    } catch {
      // Re-add to dirty set for retry on next flush
      for (const item of items) {
        _dirty.add(_mk(item.paper_id, item.key))
      }
    } finally {
      saving.value = false
    }
  }

  // Flush on page unload to avoid losing state
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', () => {
      if (_dirty.size > 0) {
        // Sync XHR as last resort for unload
        try {
          const items: Array<{ key: string; paper_id: string | null; value: any }> = []
          for (const ck of _dirty) {
            const pipeIdx = ck.indexOf('|')
            const paperId = ck.slice(0, pipeIdx) || null
            const key = ck.slice(pipeIdx + 1)
            items.push({ key, paper_id: paperId, value: _map[ck] ?? null })
          }
          // fetch + keepalive ensures cookies are sent (sendBeacon has no credentials)
          fetch('/api/me/state', {
            method: 'PUT',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items }),
            keepalive: true,
          })
        } catch { /* ignore */ }
      }
    })
  }

  return {
    loaded,
    saving,
    get,
    set,
    deleteKey,
    loadFromServer,
    loadForPaper,
    flush,
  }
})
