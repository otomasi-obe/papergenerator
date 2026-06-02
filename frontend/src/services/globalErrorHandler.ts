import type { App, ComponentPublicInstance } from 'vue'

interface UiStore {
  showToast?: (options: { type: string; message: string; duration: number }) => void
}

declare global {
  function useUiStore(): UiStore | undefined
}

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

    const uiStore = typeof useUiStore !== 'undefined' ? useUiStore() : undefined
    if (uiStore?.showToast) {
      uiStore.showToast({
        type: 'error',
        message: 'Terjadi kesalahan. Silakan refresh halaman.',
        duration: 5000
      })
    }
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
