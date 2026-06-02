import { defineStore } from 'pinia'
import { ref } from 'vue'

interface SLRJobIntent {
  job_id: string
  query: string
  top_k: number
  ai_model: string
  [key: string]: unknown
}

export const useLiteratureStore = defineStore('literature', () => {
  const pendingIntent = ref<SLRJobIntent | null>(null)

  function attachJob(intent: SLRJobIntent): void {
    pendingIntent.value = intent
  }

  function consumeIntent(): SLRJobIntent | null {
    const v = pendingIntent.value
    pendingIntent.value = null
    return v
  }

  function clearIntent(): void {
    pendingIntent.value = null
  }

  return { pendingIntent, attachJob, consumeIntent, clearIntent }
})
