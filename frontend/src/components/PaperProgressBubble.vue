<template>
  <div v-if="job"
       class="paper-progress-bubble rounded-lg border p-3 my-2
              bg-cream-50 dark:bg-ash-800
              border-cream-300 dark:border-ash-700">
    <div class="flex items-center justify-between mb-2">
      <div class="flex items-center gap-2">
        <span class="text-base" aria-hidden="true">{{ statusEmoji }}</span>
        <span class="text-sm font-medium text-ink-800 dark:text-ink-100">{{ stageLabel }}</span>
      </div>
      <span class="text-xs text-ink-500 dark:text-ink-300 tabular-nums">{{ progress }}%</span>
    </div>
    <div class="h-1.5 rounded-full bg-cream-200 dark:bg-ash-700 overflow-hidden">
      <div class="h-full bg-brown-500 dark:bg-cream-300 transition-all"
           :style="{ width: progress + '%' }" />
    </div>
    <div v-if="job.status !== 'done'" class="mt-2 flex gap-2 text-xs">
      <button v-if="job.status === 'running' || job.status === 'queued'"
              @click="onCancel"
              class="px-2 py-1 rounded text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30">
        Cancel
      </button>
      <button v-if="['paused', 'cancelled'].includes(job.status)"
              @click="onResume"
              class="px-2 py-1 rounded text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/30">
        Resume
      </button>
      <button v-if="job.status === 'error'"
              @click="onRetry"
              class="px-2 py-1 rounded text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/30">
        Retry section
      </button>
    </div>
    <div v-if="job.status === 'error' && job.error"
         class="mt-2 text-xs text-red-600 dark:text-red-300">
      {{ job.error }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { usePaperJobsStore } from '../stores/paperJobs.js'

const props = defineProps({
  jobId: { type: String, default: '' },
  paperId: { type: String, default: '' },
})

const store = usePaperJobsStore()

// Subscribe by paperId — there's only ever one active job per paper, and the
// store keys by paperId. Fall back to scanning all active jobs by jobId if
// paperId is not yet wired (chat injection happens before paper store has
// re-fetched its active job).
const job = computed(() => {
  const byPaper = props.paperId
    ? store.activeByPaper[props.paperId] || null
    : null
  if (byPaper) return byPaper
  if (props.jobId) {
    const all = Object.values(store.activeByPaper || {})
    return all.find(j => j && j.id === props.jobId) || null
  }
  return null
})

const STAGE_LABELS = {
  outline: 'Generating outline',
  section_1: 'Section I — Introduction',
  section_2: 'Section II — Related Work',
  section_3: 'Section III — Methodology',
  section_4: 'Section IV — Results',
  section_5: 'Section V — Discussion',
  references: 'References',
  combine: 'Combining',
}

const stageLabel = computed(() => {
  const stage = job.value?.stage
  return STAGE_LABELS[stage] || (stage ? stage : 'Working...')
})

const progress = computed(() => Math.max(0, Math.min(100, job.value?.progress ?? 0)))

const statusEmoji = computed(() => {
  const s = job.value?.status
  if (s === 'done') return '✓'
  if (s === 'cancelled' || s === 'paused') return '⏸'
  if (s === 'error') return '⚠'
  return '⏳'
})

async function onCancel() {
  if (job.value) await store.cancel(job.value.id)
}
async function onResume() {
  if (job.value) await store.resume(job.value.id)
}
async function onRetry() {
  if (job.value) await store.retrySection(job.value.id, job.value.stage)
}
</script>
