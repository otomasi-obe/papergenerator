import { adaptErrorMessage } from '@/utils/errorMessages'
import type { AxiosError } from 'axios'

interface RecoveryStrategy {
  retryable: boolean
  retryDelay?: number
  maxRetries?: number
  redirectToLogin?: boolean
}

const ERROR_RECOVERY_STRATEGIES: Record<string, RecoveryStrategy> = {
  UPSTREAM_TIMEOUT: {
    retryable: true,
    retryDelay: 30000,
    maxRetries: 3
  },
  TOOL_EXECUTION_FAILED: {
    retryable: true,
    retryDelay: 5000,
    maxRetries: 2
  },
  PAPER_LOCKED: {
    retryable: true,
    retryDelay: 10000,
    maxRetries: 5
  },
  NETWORK_ERROR: {
    retryable: true,
    retryDelay: 5000,
    maxRetries: 3
  },
  RATE_LIMIT_EXCEEDED: {
    retryable: true,
    retryDelay: 60000,
    maxRetries: 1
  },
  QUOTA_EXCEEDED: {
    retryable: false
  },
  UNAUTHORIZED: {
    retryable: false,
    redirectToLogin: true
  },
  TOKEN_EXPIRED: {
    retryable: false,
    redirectToLogin: true
  }
}

interface ParsedError {
  message: string
  code: string
  category: string
  details: unknown
  statusCode?: number
  originalError: unknown
}

interface ToastStore {
  showToast: (message: string, type: string) => void
}

interface HandleErrorOptions {
  operationId?: string | null
  onRetry?: (() => Promise<unknown>) | null
  showToast?: boolean
  toastStore?: ToastStore | null
}

interface HandleErrorResult {
  handled: boolean
  retry: boolean
  result?: unknown
  parsed?: ParsedError
  friendly?: ReturnType<typeof adaptErrorMessage>
  strategy?: RecoveryStrategy
}

type UserLevel = 'beginner' | 'intermediate' | 'advanced'

class ErrorHandler {
  private userLevel: UserLevel
  private retryAttempts: Map<string, number>

  constructor() {
    this.userLevel = 'intermediate'
    this.retryAttempts = new Map()
  }

  setUserLevel(level: string): void {
    if (['beginner', 'intermediate', 'advanced'].includes(level)) {
      this.userLevel = level as UserLevel
    }
  }

  parseError(error: unknown): ParsedError {
    if (!error) {
      return {
        message: 'Terjadi kesalahan',
        code: 'UNKNOWN',
        category: 'SERVER',
        details: null,
        originalError: error
      }
    }

    const axiosError = error as AxiosError<{
      error?: string
      message?: string
      code?: string
      category?: string
      details?: unknown
    }>

    if (axiosError.response?.data) {
      const data = axiosError.response.data
      const status = axiosError.response.status

      let code = data.code || 'UNKNOWN'
      if (status === 404) {
        code = data.code || 'RESOURCE_NOT_FOUND'
      }

      return {
        message: data.error || data.message || (status === 404 ? 'Resource tidak ditemukan' : 'Terjadi kesalahan'),
        code,
        category: data.category || 'SERVER',
        details: data.details || null,
        statusCode: status,
        originalError: error
      }
    }

    const errorWithMessage = error as { message?: string; code?: string }

    if (errorWithMessage.message) {
      if (errorWithMessage.message.includes('Network Error') || errorWithMessage.code === 'ERR_NETWORK') {
        return {
          message: 'Koneksi terputus',
          code: 'NETWORK_ERROR',
          category: 'EXTERNAL',
          details: null,
          originalError: error
        }
      }

      if (errorWithMessage.message.includes('timeout')) {
        return {
          message: 'Request timeout',
          code: 'UPSTREAM_TIMEOUT',
          category: 'EXTERNAL',
          details: null,
          originalError: error
        }
      }

      if (axiosError.response?.status === 404) {
        return {
          message: 'Resource tidak ditemukan',
          code: 'RESOURCE_NOT_FOUND',
          category: 'CLIENT',
          details: null,
          statusCode: 404,
          originalError: error
        }
      }
    }

    return {
      message: errorWithMessage.message || String(error),
      code: 'UNKNOWN',
      category: 'SERVER',
      details: null,
      originalError: error
    }
  }

  getUserFriendlyMessage(parsedError: ParsedError): ReturnType<typeof adaptErrorMessage> {
    const adapted = adaptErrorMessage(
      { code: parsedError.code, message: parsedError.message },
      this.userLevel
    )
    return adapted
  }

  getRecoveryStrategy(errorCode: string): RecoveryStrategy {
    return ERROR_RECOVERY_STRATEGIES[errorCode] || { retryable: false }
  }

  canRetry(errorCode: string, operationId: string): boolean {
    const strategy = this.getRecoveryStrategy(errorCode)
    if (!strategy.retryable) return false

    const attempts = this.retryAttempts.get(operationId) || 0
    return attempts < (strategy.maxRetries || 0)
  }

  recordRetryAttempt(operationId: string): void {
    const attempts = this.retryAttempts.get(operationId) || 0
    this.retryAttempts.set(operationId, attempts + 1)
  }

  resetRetryAttempts(operationId: string): void {
    this.retryAttempts.delete(operationId)
  }

  async handleError(error: unknown, options: HandleErrorOptions = {}): Promise<HandleErrorResult> {
    const {
      operationId = null,
      onRetry = null,
      showToast = true,
      toastStore = null
    } = options

    const parsed = this.parseError(error)
    const friendly = this.getUserFriendlyMessage(parsed)
    const strategy = this.getRecoveryStrategy(parsed.code)

    if (showToast && toastStore) {
      toastStore.showToast(friendly.message, 'error')
    }

    if (strategy.redirectToLogin && typeof window !== 'undefined') {
      setTimeout(() => {
        window.location.href = '/login'
      }, 2000)
      return { handled: true, retry: false }
    }

    if (operationId && this.canRetry(parsed.code, operationId) && onRetry) {
      this.recordRetryAttempt(operationId)
      
      if (showToast && toastStore) {
        const retryMsg = `Mencoba lagi dalam ${(strategy.retryDelay || 0) / 1000} detik...`
        toastStore.showToast(retryMsg, 'info')
      }

      await new Promise(resolve => setTimeout(resolve, strategy.retryDelay))
      
      try {
        const result = await onRetry()
        this.resetRetryAttempts(operationId)
        return { handled: true, retry: true, result }
      } catch (retryError) {
        return this.handleError(retryError, { ...options, operationId })
      }
    }

    return {
      handled: true,
      retry: false,
      parsed,
      friendly,
      strategy
    }
  }

  logError(error: unknown, context: Record<string, unknown> = {}): void {
    const parsed = this.parseError(error)
    
    if (this.userLevel === 'advanced' || parsed.category === 'SERVER') {
      console.error('[ErrorHandler]', {
        ...parsed,
        context,
        timestamp: new Date().toISOString()
      })
    }
  }
}

export const errorHandler = new ErrorHandler()

export default errorHandler
