import type { App, ComponentPublicInstance } from 'vue'
import { usePaperStore } from '../stores/paper'

export function setupErrorHandler(app: App): void {
  app.config.errorHandler = (err: unknown, instance: ComponentPublicInstance | null, info: string) => {
    if (import.meta.env.DEV) console.error('[Global Error Handler]', {
      error: err,
      component: instance?.$options?.name || 'Unknown',
      info,
      timestamp: new Date().toISOString()
    })

    if (import.meta.env.PROD) {
      // TODO: Integrate with Sentry or logging service
    }

    try {
      const paperStore = usePaperStore()
      if (paperStore?.showToast) {
        paperStore.showToast('Terjadi kesalahan. Silakan refresh halaman.', 'error')
      }
    } catch { /* paper store not available */ }
  }

  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    if (import.meta.env.DEV) console.error('[Unhandled Promise Rejection]', event.reason)

    if (import.meta.env.PROD) {
      // TODO: Send to logging service
    }

    event.preventDefault()
  })

  if (import.meta.env.DEV) {
    app.config.warnHandler = (msg: string, _instance: ComponentPublicInstance | null, trace: string) => {
      console.warn('[Vue Warning]', msg, trace)
    }
  }
}
