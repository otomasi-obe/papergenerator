/**
 * Error Handling Examples
 * =======================
 * Examples showing how to use the new error handling system in Vue components.
 */

import axios from 'axios'
import { errorHandler } from '@/services/errorHandler'
import { useStore } from '@/stores/ui'

/**
 * Example 1: Basic error handling with toast
 */
export async function exampleBasicError() {
  const store = useStore()
  
  try {
    const response = await axios.get('/api/papers/invalid-id')
    return response.data
  } catch (error) {
    await errorHandler.handleError(error, {
      showToast: true,
      toastStore: store
    })
  }
}

/**
 * Example 2: Error handling with automatic retry
 */
export async function exampleWithRetry(paperId) {
  const store = useStore()
  const operationId = `generate-${paperId}`
  
  try {
    const response = await axios.post(`/api/papers/${paperId}/generate`)
    errorHandler.resetRetryAttempts(operationId)
    return response.data
  } catch (error) {
    const result = await errorHandler.handleError(error, {
      operationId,
      onRetry: () => axios.post(`/api/papers/${paperId}/generate`),
      showToast: true,
      toastStore: store
    })
    
    if (result.retry && result.result) {
      return result.result.data
    }
    
    throw error
  }
}

/**
 * Example 3: Manual error parsing without automatic handling
 */
export function exampleManualParsing(error) {
  const parsed = errorHandler.parseError(error)
  
  console.log('Error details:', {
    message: parsed.message,
    code: parsed.code,
    category: parsed.category,
    statusCode: parsed.statusCode
  })
  
  const friendly = errorHandler.getUserFriendlyMessage(parsed)
  
  console.log('User-friendly message:', friendly.message)
  console.log('Suggested action:', friendly.action)
  console.log('Show details:', friendly.showDetails)
  
  return { parsed, friendly }
}

/**
 * Example 4: Checking if operation can be retried
 */
export function exampleCheckRetry(error, operationId) {
  const parsed = errorHandler.parseError(error)
  const canRetry = errorHandler.canRetry(parsed.code, operationId)
  const strategy = errorHandler.getRecoveryStrategy(parsed.code)
  
  console.log('Can retry:', canRetry)
  console.log('Retry strategy:', strategy)
  
  return { canRetry, strategy }
}

/**
 * Example 5: Vue Composable for error handling
 */
export function useErrorHandler() {
  const store = useStore()
  
  const handleError = async (error, options = {}) => {
    return await errorHandler.handleError(error, {
      showToast: true,
      toastStore: store,
      ...options
    })
  }
  
  const handleErrorWithRetry = async (error, operationId, retryFn) => {
    return await errorHandler.handleError(error, {
      operationId,
      onRetry: retryFn,
      showToast: true,
      toastStore: store
    })
  }
  
  const parseError = (error) => {
    return errorHandler.parseError(error)
  }
  
  const setUserLevel = (level) => {
    errorHandler.setUserLevel(level)
  }
  
  return {
    handleError,
    handleErrorWithRetry,
    parseError,
    setUserLevel
  }
}

/**
 * Example 6: Component usage with composition API
 */
export const ExampleComponent = {
  setup() {
    const { handleError, handleErrorWithRetry } = useErrorHandler()
    const paperId = ref('abc123')
    const loading = ref(false)
    
    const loadPaper = async () => {
      loading.value = true
      try {
        const response = await axios.get(`/api/papers/${paperId.value}`)
        return response.data
      } catch (error) {
        await handleError(error)
      } finally {
        loading.value = false
      }
    }
    
    const generatePaper = async () => {
      loading.value = true
      const operationId = `generate-${paperId.value}`
      
      try {
        const response = await axios.post(`/api/papers/${paperId.value}/generate`)
        return response.data
      } catch (error) {
        const result = await handleErrorWithRetry(
          error,
          operationId,
          () => axios.post(`/api/papers/${paperId.value}/generate`)
        )
        
        if (result.retry && result.result) {
          return result.result.data
        }
      } finally {
        loading.value = false
      }
    }
    
    return {
      paperId,
      loading,
      loadPaper,
      generatePaper
    }
  }
}

/**
 * Example 7: Axios interceptor integration
 */
export function setupAxiosInterceptors() {
  axios.interceptors.response.use(
    response => response,
    async error => {
      const parsed = errorHandler.parseError(error)
      
      if (parsed.code === 'UNAUTHORIZED' || parsed.code === 'TOKEN_EXPIRED') {
        window.location.href = '/login'
        return Promise.reject(error)
      }
      
      errorHandler.logError(error, {
        url: error.config?.url,
        method: error.config?.method
      })
      
      return Promise.reject(error)
    }
  )
}

/**
 * Example 8: Error boundary for Vue components
 */
export const ErrorBoundary = {
  name: 'ErrorBoundary',
  
  data() {
    return {
      hasError: false,
      errorInfo: null
    }
  },
  
  errorCaptured(err, instance, info) {
    this.hasError = true
    this.errorInfo = errorHandler.parseError(err)
    
    errorHandler.logError(err, {
      component: instance?.$options?.name,
      info
    })
    
    return false
  },
  
  render() {
    if (this.hasError) {
      return h('div', { class: 'error-boundary' }, [
        h('h3', 'Terjadi kesalahan'),
        h('p', this.errorInfo?.message || 'Unknown error'),
        h('button', {
          onClick: () => {
            this.hasError = false
            this.errorInfo = null
          }
        }, 'Coba lagi')
      ])
    }
    
    return this.$slots.default?.()
  }
}

/**
 * Example 9: Store integration
 */
export const exampleStoreActions = {
  async loadPapers({ commit }) {
    const store = useStore()
    
    try {
      const response = await axios.get('/api/papers')
      commit('SET_PAPERS', response.data)
      return response.data
    } catch (error) {
      await errorHandler.handleError(error, {
        showToast: true,
        toastStore: store
      })
      throw error
    }
  },
  
  async savePaper({ commit }, { paperId, data }) {
    const store = useStore()
    const operationId = `save-${paperId}`
    
    try {
      const response = await axios.put(`/api/papers/${paperId}`, data)
      commit('UPDATE_PAPER', response.data)
      errorHandler.resetRetryAttempts(operationId)
      return response.data
    } catch (error) {
      const result = await errorHandler.handleError(error, {
        operationId,
        onRetry: () => axios.put(`/api/papers/${paperId}`, data),
        showToast: true,
        toastStore: store
      })
      
      if (result.retry && result.result) {
        commit('UPDATE_PAPER', result.result.data)
        return result.result.data
      }
      
      throw error
    }
  }
}
