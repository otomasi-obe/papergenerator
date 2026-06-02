import { ref } from 'vue'
import type { Ref } from 'vue'

interface ErrorState {
  message: string
  code?: string | number
  retry?: () => Promise<void>
}

interface UseErrorHandlerReturn {
  error: Ref<ErrorState | null>
  handleError: (err: unknown, retryFn?: () => Promise<void>) => void
  clearError: () => void
  withErrorHandling: <T>(fn: () => Promise<T>) => Promise<T | null>
}

export function useErrorHandler(): UseErrorHandlerReturn {
  const error = ref<ErrorState | null>(null)

  function handleError(err: unknown, retryFn?: () => Promise<void>) {
    if (err instanceof Error) {
      error.value = {
        message: err.message,
        retry: retryFn,
      }
    } else if (typeof err === 'string') {
      error.value = { message: err, retry: retryFn }
    } else {
      error.value = { message: 'An unexpected error occurred', retry: retryFn }
    }
  }

  function clearError() {
    error.value = null
  }

  async function withErrorHandling<T>(fn: () => Promise<T>): Promise<T | null> {
    clearError()
    try {
      return await fn()
    } catch (err) {
      handleError(err, () => withErrorHandling(fn) as Promise<any>)
      return null
    }
  }

  return { error, handleError, clearError, withErrorHandling }
}
