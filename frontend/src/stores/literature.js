/**
 * Literature store — bridges chat-triggered SLR runs with the LiteratureTab UI.
 *
 * When the chat tool RunSLR enqueues a job on the backend, the SSE handler
 * in chat.js parks an "intent" here and asks the UI store to switch to the
 * literature tab. LiteratureTab consumes the intent on mount (or via watcher
 * if it's already mounted) to pre-fill the query input and optimistically
 * show the active job card without re-POSTing /slr/jobs.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useLiteratureStore = defineStore('literature', () => {
  // pendingIntent shape: { job_id, query, top_k, ai_model } | null
  const pendingIntent = ref(null)

  function attachJob(intent) {
    pendingIntent.value = intent
  }

  function consumeIntent() {
    const v = pendingIntent.value
    pendingIntent.value = null
    return v
  }

  function clearIntent() {
    pendingIntent.value = null
  }

  return { pendingIntent, attachJob, consumeIntent, clearIntent }
})
