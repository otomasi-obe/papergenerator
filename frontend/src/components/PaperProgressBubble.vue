<template>
  <div v-if="job"
       class="paper-progress-bubble rounded-lg border p-3 my-2
              bg-cream-50 dark:bg-ash-800
              border-cream-300 dark:border-ash-700">
    <div class="flex items-center justify-between mb-2">
      <div class="flex items-center gap-2">
        <span class="text-base" aria-hidden="true">{{ statusEmoji }}</span>
        <span class="text-sm font-medium text-ink-800 dark:text-ink-100"
              :class="{ 'gen-pulse': job.status === 'running' || job.status === 'queued' }">
          {{ stageLabel }}
          <span v-if="job.status === 'running' || job.status === 'queued'" class="gen-dots">
            <span>.</span><span>.</span><span>.</span>
          </span>
        </span>
      </div>
      <span class="text-xs font-mono font-bold text-ink-500 dark:text-ink-300 tabular-nums">{{ progress }}%</span>
    </div>
    <div class="h-2 rounded-full bg-cream-200 dark:bg-ash-700 overflow-hidden">
      <div class="h-full bg-gradient-to-r from-navy-500 to-emerald-500 dark:from-cream-300 dark:to-emerald-400 transition-all duration-1000"
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

<script setup lang="ts">
// @ts-nocheck
import { computed } from 'vue'

// @ts-ignore - paperJobs store will be converted to TypeScript in Week 3-4
const { usePaperJobsStore } = await import('../stores/paperJobs.js')

interface Props {
  jobId?: string
  paperId?: string
}

const props = withDefaults(defineProps<Props>(), {
  jobId: '',
  paperId: ''
})

const store = usePaperJobsStore()

const job = computed(() => {
  const byPaper = props.paperId
    ? store.activeByPaper[props.paperId] || null
    : null
  if (byPaper) return byPaper
  if (props.jobId) {
    const all = Object.values(store.activeByPaper || {})
    return all.find((j: any) => j && j.id === props.jobId) || null
  }
  return null
})

const STAGE_LABELS: Record<string, string> = {
  outline: 'Generating outline',
  section_1: 'Section I — Introduction',
  section_2: 'Section II — Related Work',
  section_3: 'Section III — Methodology',
  section_4: 'Section IV — Results',
  section_5: 'Section V — Discussion',
  references: 'References',
  combine: 'Combining',
}

const stageLabel = computed<string>(() => {
  const stage = job.value?.stage
  return STAGE_LABELS[stage] || stage || 'Processing'
})

const progress = computed<number>(() => {
  return Math.round(job.value?.progress || 0)
})

const statusEmoji = computed<string>(() => {
  const status = job.value?.status
  if (status === 'done') return '✓'
  if (status === 'error') return '⚠'
  if (status === 'cancelled') return '✕'
  return '⏳'
})

async function onCancel(): Promise<void> {
  if (!job.value) return
  await store.cancelJob(job.value.id)
}

async function onResume(): Promise<void> {
  if (!job.value) return
  await store.resumeJob(job.value.id)
}

async function onRetry(): Promise<void> {
  if (!job.value) return
  await store.retryJob(job.value.id)
}
</script>

<style scoped>
@keyframes gen-pulse-anim {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

@keyframes gen-dots-blink {
  0%, 20% { opacity: 0; }
  40% { opacity: 1; }
  60%, 100% { opacity: 0; }
}

.gen-pulse {
  animation: gen-pulse-anim 1.5s ease-in-out infinite;
}

.gen-dots {
  display: inline-flex;
  gap: 0;
}

.gen-dots span {
  font-weight: bold;
  animation: gen-dots-blink 1.4s ease-in-out infinite;
}

.gen-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.gen-dots span:nth-child(3) {
  animation-delay: 0.4s;
}
</style>
