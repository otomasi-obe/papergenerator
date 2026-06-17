import type { App, ComponentPublicInstance } from 'vue'
import { useUiStore } from '../stores/ui'

export function setupErrorHandler(app: App): void {
  app.config.errorHandler = (err: unknown, instance: ComponentPublicInstance | null, info: string) => {
    console.error('[Global Error Handler]', {
      error: err,
      component: instance?.$options?.name || 'Unknown',
      info,
      timestamp: new Date().toISOString()
    })

    if (import.meta.env.PROD) {
      // TODO: Integrate with Sentry or logging service
    }

    try {
      const uiStore = useUiStore() as any
      if (uiStore?.showToast) {
        uiStore.showToast({
          type: 'error',
          message: 'Terjadi kesalahan. Silakan refresh halaman.',
          duration: 5000
        })
      }
    } catch { /* ui store not available */ }
  }

  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    console.error('[Unhandled Promise Rejection]', event.reason)

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
