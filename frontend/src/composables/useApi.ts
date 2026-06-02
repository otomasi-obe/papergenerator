import { ref } from 'vue'
import type { Ref } from 'vue'
import api from '../api'
import type { AxiosRequestConfig, AxiosError } from 'axios'

interface UseApiReturn<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  execute: (config: AxiosRequestConfig) => Promise<T | null>
}

export function useApi<T = any>(): UseApiReturn<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function execute(config: AxiosRequestConfig): Promise<T | null> {
    loading.value = true
    error.value = null
    try {
      const response = await api(config)
      data.value = response.data
      return response.data
    } catch (err) {
      const axiosError = err as AxiosError<{ detail?: string }>
      error.value = axiosError.response?.data?.detail || axiosError.message || 'An error occurred'
      return null
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, execute }
}
