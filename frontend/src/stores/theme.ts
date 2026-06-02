import { ref, computed, watch } from 'vue'

type ThemeMode = 'light' | 'dark' | 'system'
type EffectiveTheme = 'light' | 'dark'

const LS_KEY = 'pg_theme'
const VALID: ThemeMode[] = ['light', 'dark', 'system']

function readStored(): ThemeMode {
  try {
    const v = localStorage.getItem(LS_KEY)
    return VALID.includes(v as ThemeMode) ? (v as ThemeMode) : 'system'
  } catch {
    return 'system'
  }
}

function systemPrefersDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function resolve(mode: ThemeMode): EffectiveTheme {
  if (mode === 'dark') return 'dark'
  if (mode === 'light') return 'light'
  return systemPrefersDark() ? 'dark' : 'light'
}

function applyDomClass(effective: EffectiveTheme): void {
  const html = document.documentElement
  html.classList.toggle('dark', effective === 'dark')
  html.style.colorScheme = effective
}

const mode = ref<ThemeMode>(readStored())
const effective = computed(() => resolve(mode.value))

let mql: MediaQueryList | null = null

function bindSystemListener(): void {
  if (typeof window === 'undefined' || !window.matchMedia) return
  mql = window.matchMedia('(prefers-color-scheme: dark)')
  const handler = () => {
    if (mode.value === 'system') applyDomClass(resolve('system'))
  }
  if (mql.addEventListener) mql.addEventListener('change', handler)
  else if ('addListener' in mql) (mql as any).addListener(handler)
}

watch(mode, (m) => {
  try { localStorage.setItem(LS_KEY, m) } catch { /* quota — ignore */ }
  applyDomClass(resolve(m))
}, { immediate: false })

export function applyInitialTheme(): void {
  applyDomClass(resolve(mode.value))
  bindSystemListener()
}

export function useTheme() {
  function setMode(next: string): void {
    if (VALID.includes(next as ThemeMode)) mode.value = next as ThemeMode
  }
  return { mode, effective, setMode }
}
