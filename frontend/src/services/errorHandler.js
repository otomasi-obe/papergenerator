import { adaptErrorMessage } from '@/utils/errorMessages'

const ERROR_RECOVERY_STRATEGIES = {
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

class ErrorHandler {
  constructor() {
    this.userLevel = 'intermediate'
    this.retryAttempts = new Map()
  }

  setUserLevel(level) {
    if (['beginner', 'intermediate', 'advanced'].includes(level)) {
      this.userLevel = level
    }
  }

  parseError(error) {
    if (!error) {
      return {
        message: 'Terjadi kesalahan',
        code: 'UNKNOWN',
        category: 'SERVER',
        details: null,
        originalError: error
      }
    }

    if (error.response?.data) {
      const data = error.response.data
      return {
        message: data.error || data.message || 'Terjadi kesalahan',
        code: data.code || 'UNKNOWN',
        category: data.category || 'SERVER',
        details: data.details || null,
        statusCode: error.response.status,
        originalError: error
      }
    }

    if (error.message) {
      if (error.message.includes('Network Error') || error.code === 'ERR_NETWORK') {
        return {
          message: 'Koneksi terputus',
          code: 'NETWORK_ERROR',
          category: 'EXTERNAL',
          details: null,
          originalError: error
        }
      }

      if (error.message.includes('timeout')) {
        return {
          message: 'Request timeout',
          code: 'UPSTREAM_TIMEOUT',
          category: 'EXTERNAL',
          details: null,
          originalError: error
        }
      }
    }

    return {
      message: error.message || String(error),
      code: 'UNKNOWN',
      category: 'SERVER',
      details: null,
      originalError: error
    }
  }

  getUserFriendlyMessage(parsedError) {
    const adapted = adaptErrorMessage(
      { code: parsedError.code, message: parsedError.message },
      this.userLevel
    )
    return adapted
  }

  getRecoveryStrategy(errorCode) {
    return ERROR_RECOVERY_STRATEGIES[errorCode] || { retryable: false }
  }

  canRetry(errorCode, operationId) {
    const strategy = this.getRecoveryStrategy(errorCode)
    if (!strategy.retryable) return false

    const attempts = this.retryAttempts.get(operationId) || 0
    return attempts < (strategy.maxRetries || 0)
  }

  recordRetryAttempt(operationId) {
    const attempts = this.retryAttempts.get(operationId) || 0
    this.retryAttempts.set(operationId, attempts + 1)
  }

  resetRetryAttempts(operationId) {
    this.retryAttempts.delete(operationId)
  }

  async handleError(error, options = {}) {
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
        const retryMsg = `Mencoba lagi dalam ${strategy.retryDelay / 1000} detik...`
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

  logError(error, context = {}) {
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
