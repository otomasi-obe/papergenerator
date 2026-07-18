import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'
import { applyInitialTheme } from './stores/theme'
import { vAutosize } from './directives/autosize'
import { setupErrorHandler } from './services/globalErrorHandler'
import { logger } from './utils/logger'
import api from './api/index'
import './style.css'

// Wire logger to axios so frontend logs actually reach the backend
logger.setApi(api)

applyInitialTheme()

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.directive('autosize', vAutosize)

setupErrorHandler(app)

// Catch dynamic import failures (stale chunk hash after deploy) → reload once
let _chunkReloaded = false
window.addEventListener('error', (event: ErrorEvent) => {
  const msg = event.message || ''
  const isChunkLoad = msg.includes('Failed to fetch dynamically imported module')
    || msg.includes('error loading dynamically imported module')
    || event.error?.name === 'ChunkLoadError'
  if (isChunkLoad && !_chunkReloaded) {
    _chunkReloaded = true
    window.location.reload()
    return
  }
  if (import.meta.env.DEV) logger.error('Uncaught error', {
    message: event.message,
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
    error: event.error?.stack || String(event.error)
  })
})

// Also catch unhandled promise rejections from dynamic imports
window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
  const reason = event.reason
  const msg = reason?.message || String(reason)
  if ((msg.includes('Failed to fetch dynamically imported module')
       || msg.includes('error loading dynamically imported module')
       || reason?.name === 'ChunkLoadError') && !_chunkReloaded) {
    _chunkReloaded = true
    window.location.reload()
  }
})

// Version-based cache-bust: if a new build deployed, force reload once.
// Guards against stale index.html (browser cache) serving old chunks that
// still exist on disk (Vite keeps old hashed chunks) → no ChunkLoadError,
// user just silently runs old code. Compare deploy VERSION to localStorage.
const PF_VERSION_KEY = 'pf_version'
fetch(`${import.meta.env.BASE_URL}version-history.json`, { cache: 'no-store' })
  .then((r) => (r.ok ? r.json() : null))
  .then((data) => {
    const v = data?.version
    if (!v) return
    const stored = localStorage.getItem(PF_VERSION_KEY)
    if (stored && stored !== v && !_chunkReloaded) {
      _chunkReloaded = true
      localStorage.setItem(PF_VERSION_KEY, v)
      window.location.reload()
    } else {
      localStorage.setItem(PF_VERSION_KEY, v)
    }
  })
  .catch(() => { /* offline / 404 → skip, chunk-error handler is backup */ })

logger.info('Application initialized', {
  mode: import.meta.env.MODE,
  base: import.meta.env.BASE_URL
})

app.mount('#app')

if (import.meta.env.DEV || import.meta.env.MODE === 'development') {
  (window as any).__pinia = pinia
}
