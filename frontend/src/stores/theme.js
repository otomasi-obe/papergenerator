/**
 * Theme controller.
 *
 * Modes: 'light' | 'dark' | 'system'.
 * - The actual class on <html> is always either 'dark' or absent.
 * - 'system' follows prefers-color-scheme and reacts when the OS flips.
 * - The user's choice is persisted in localStorage so it survives reload.
 *
 * Designed to be safe to call before Vue mounts — index.html can call
 * `applyInitialTheme()` to avoid a flash of the wrong theme.
 */

import { ref, computed, watch } from 'vue'

const LS_KEY = 'pg_theme'
const VALID = ['light', 'dark', 'system']

function readStored() {
  try {
    const v = localStorage.getItem(LS_KEY)
    return VALID.includes(v) ? v : 'system'
  } catch {
    return 'system'
  }
}

function systemPrefersDark() {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function resolve(mode) {
  if (mode === 'dark') return 'dark'
  if (mode === 'light') return 'light'
  return systemPrefersDark() ? 'dark' : 'light'
}

function applyDomClass(effective) {
  const html = document.documentElement
  html.classList.toggle('dark', effective === 'dark')
  // Color-scheme hint helps native form controls / scrollbars match.
  html.style.colorScheme = effective
}

const mode = ref(readStored())
const effective = computed(() => resolve(mode.value))

let mql = null
function bindSystemListener() {
  if (typeof window === 'undefined' || !window.matchMedia) return
  mql = window.matchMedia('(prefers-color-scheme: dark)')
  const handler = () => {
    if (mode.value === 'system') applyDomClass(resolve('system'))
  }
  if (mql.addEventListener) mql.addEventListener('change', handler)
  else if (mql.addListener) mql.addListener(handler)
}

watch(mode, (m) => {
  try { localStorage.setItem(LS_KEY, m) } catch { /* quota — ignore */ }
  applyDomClass(resolve(m))
}, { immediate: false })

export function applyInitialTheme() {
  // Synchronous: must run before paint to avoid theme flash.
  applyDomClass(resolve(mode.value))
  bindSystemListener()
}

export function useTheme() {
  function setMode(next) {
    if (VALID.includes(next)) mode.value = next
  }
  return { mode, effective, setMode }
}
