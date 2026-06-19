import { defineStore } from 'pinia'
import { ref } from 'vue'

interface LitIntent {
  action?: string
  query?: string
  top_k?: number
  job_id?: string
  ai_model?: string
  message?: string
  paperId?: string | number
  itemCount?: number
  [key: string]: unknown
}

export const useLiteratureStore = defineStore('literature', () => {
  const pendingIntent = ref<LitIntent | null>(null)

  function setIntent(intent: LitIntent): void {
    pendingIntent.value = intent
  }

  function attachJob(intent: LitIntent): void {
    pendingIntent.value = intent
  }

  function consumeIntent(): LitIntent | null {
    const v = pendingIntent.value
    pendingIntent.value = null
    return v
  }

  function clearIntent(): void {
    pendingIntent.value = null
  }

  return { pendingIntent, setIntent, attachJob, consumeIntent, clearIntent }
})