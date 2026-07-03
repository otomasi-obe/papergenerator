import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/index'

interface QuotaData {
  quota_monthly: number
  used_month: number
  used_today: number
  remaining: number
  percent: number
  month_key: string
  breakdown_by_model: any[]
  is_unlimited: boolean
  input_tokens?: number
  output_tokens?: number
}

const INITIAL_QUOTA: QuotaData = {
  quota_monthly: 0,
  used_month: 0,
  used_today: 0,
  remaining: 0,
  percent: 0,
  month_key: '',
  breakdown_by_model: [],
  is_unlimited: false,
  input_tokens: 0,
  output_tokens: 0,
}

export const useQuotaStore = defineStore('quota', () => {
  const quota = ref<QuotaData>({ ...INITIAL_QUOTA })
  const isLoading = ref(false)
  const lastFetchTime = ref<number>(0)
  let pollingTimer: ReturnType<typeof setInterval> | null = null

  async function fetchQuota(): Promise<void> {
    // Deduplicate: skip if already fetching or fetched within last 5 seconds
    const now = Date.now()
    if (isLoading.value || now - lastFetchTime.value < 5000) {
      return
    }

    isLoading.value = true
    try {
      const res = await api.get('/api/me/quota')
      if (res?.data) {
        // Merge with defaults to guard against missing/null fields
        const safe = { ...INITIAL_QUOTA, ...res.data }
        Object.assign(quota.value, safe)
        lastFetchTime.value = now
      }
    } catch (e) {
      // Not signed in or backend cold - keep existing quota state
      if (import.meta.env.DEV) console.warn('[quota] fetchQuota failed:', e instanceof Error ? e.message : String(e))
    } finally {
      isLoading.value = false
    }
  }

  function startPolling(intervalMs: number = 60_000): void {
    // Stop any existing timer first
    stopPolling()

    // Fetch immediately
    fetchQuota()

    // Then poll at interval
    pollingTimer = setInterval(fetchQuota, intervalMs)
  }

  function stopPolling(): void {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
    }
  }

  function reset(): void {
    quota.value = { ...INITIAL_QUOTA }
    lastFetchTime.value = 0
    stopPolling()
  }

  return {
    quota,
    isLoading,
    fetchQuota,
    startPolling,
    stopPolling,
    reset,
  }
})
