<template>
  <div v-if="job" class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-4 py-3 space-y-3">
    <!-- Header: Icon + Query + Cancel Button -->
    <div class="flex items-center justify-between gap-2">
      <span class="font-medium text-amber-900 dark:text-amber-100 truncate flex items-center gap-2">
        <span :class="{ 'animate-spin': isActive }" class="inline-block text-lg">
          {{ stageIcon }}
        </span>
        <span class="truncate">{{ job.query }}</span>
      </span>
      <button
        @click="$emit('cancel')"
        class="text-amber-700 dark:text-amber-300 hover:underline shrink-0 text-xs font-medium"
      >
        ✕ Hentikan
      </button>
    </div>

    <!-- Stage Badge + Progress Bar + Percentage -->
    <div class="flex items-center gap-2">
      <span
        class="px-2 py-1 rounded text-xs font-medium shrink-0 whitespace-nowrap"
        :class="stageBadgeClass"
      >
        {{ stageLabel }}
      </span>
      <div class="flex-1 h-2.5 rounded-full bg-amber-200 dark:bg-amber-900/50 overflow-hidden">
        <div
          class="h-full bg-amber-500 transition-all duration-500"
          :style="{ width: `${job.progress || 0}%` }"
        ></div>
      </div>
      <span class="text-xs font-mono text-amber-700 dark:text-amber-300 shrink-0 w-8 text-right">
        {{ job.progress || 0 }}%
      </span>
    </div>

    <!-- Main Progress Message -->
    <div class="text-amber-800 dark:text-amber-200 text-sm leading-snug">
      {{ job.progress_message || stageLabel || 'Memproses…' }}
    </div>

    <!-- Stage-Specific Details -->
    <div class="space-y-2">
      <!-- Analyzing: Show domains -->
      <div v-if="job.stage === 'analyzing'" class="text-xs text-amber-700 dark:text-amber-300 space-y-1">
        <div>📋 Menganalisis keyword dan domain…</div>
      </div>

      <!-- Fetching: Show source progress with paper counts -->
      <div v-else-if="job.stage === 'fetching'" class="space-y-2">
        <!-- Summary row: X/Y sources, N papers fetched, M dedup -->
        <div class="text-xs text-amber-700 dark:text-amber-300 flex items-center gap-2 flex-wrap">
          <span class="font-medium">📡 Sumber:</span>
          <span>{{ job.sources_completed?.length || 0 }}/{{ job.sources_total || 0 }} selesai</span>
          <span class="opacity-70">·</span>
          <span>{{ job.all_papers_count || 0 }} unique</span>
        </div>

        <!-- Source list with individual progress -->
        <div v-if="sourcesList.length > 0" class="flex flex-wrap gap-x-4 gap-y-1">
          <span v-for="src in sourcesList" :key="src.name" class="text-xs font-mono inline-flex items-center gap-1">
            {{ src.name }}
            <span v-if="src.status === 'done'" class="text-green-700 dark:text-green-300">✓</span>
            <span v-else-if="src.status === 'running'" class="text-blue-600 dark:text-blue-300 animate-pulse">⟳</span>
            <span v-else class="text-gray-400 dark:text-gray-500">⊙</span>
          </span>
        </div>

        <!-- Paper count and dedup info -->
        <div v-if="job.papers_fetched" class="text-xs text-amber-700 dark:text-amber-300 italic">
          📄 {{ job.papers_fetched }} paper ditemukan (dedup otomatis)
        </div>
      </div>

      <!-- Summarizing/Ranking: Show processing stages -->
      <div v-else-if="job.stage === 'summarizing' || job.stage === 'ranking'" class="text-xs text-amber-700 dark:text-amber-300 space-y-1">
        <div v-if="job.stage === 'summarizing'">
          <div>🔄 Deduplicating papers…</div>
          <div class="mt-1">📊 Ranking & grouping results…</div>
        </div>
      </div>

      <!-- Complete: Show final stats -->
      <div v-else-if="job.stage === 'complete' || job.status === 'done'" class="text-xs text-green-700 dark:text-green-300 space-y-1">
        <div>✅ {{ job.progress_message }}</div>
      </div>

      <!-- Error -->
      <div v-else-if="job.status === 'error'" class="text-xs text-red-700 dark:text-red-300">
        ❌ {{ job.error || 'Error' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface SLRJob {
  id: string
  job_id: string
  query: string
  status: string
  stage: string
  progress: number
  progress_message: string
  error?: string
  sources_total?: number
  sources_completed?: string[]
  sources_running?: string[]
  sources_pending?: string[]
  papers_fetched?: number
  all_papers_count?: number
}

const props = defineProps<{
  job: SLRJob | null
}>()

defineEmits<{
  cancel: []
}>()

const STAGE_LABELS: Record<string, string> = {
  pending: 'Memulai',
  analyzing: 'Menganalisis keyword',
  fetching: 'Mencari sumber',
  ranking: 'Mengurutkan relevansi',
  summarizing: 'Merangkum hasil',
  complete: 'Selesai',
  done: 'Selesai',
  error: 'Gagal',
}

const stageLabel = computed(() => {
  if (!props.job) return ''
  const stage = props.job.stage || props.job.status
  return STAGE_LABELS[stage] || stage
})

const stageIcon = computed(() => {
  if (!props.job) return ''
  const s = props.job.stage || props.job.status
  if (s === 'analyzing') return '🔍'
  if (s === 'fetching') return '📡'
  if (s === 'summarizing' || s === 'ranking') return '📊'
  if (s === 'done' || s === 'complete') return '✅'
  if (s === 'error') return '❌'
  if (s === 'cancelled') return '🚫'
  if (s === 'pending') return '⏳'
  return '⚙️'
})

const stageBadgeClass = computed(() => {
  if (!props.job) return ''
  const s = props.job.stage || props.job.status
  const base = 'px-2 py-1 rounded text-xs font-medium'
  if (s === 'analyzing' || s === 'fetching' || s === 'summarizing' || s === 'ranking') {
    return `${base} bg-blue-200 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200`
  }
  if (s === 'done' || s === 'complete') {
    return `${base} bg-green-200 text-green-800 dark:bg-green-900/40 dark:text-green-200`
  }
  if (s === 'error') {
    return `${base} bg-red-200 text-red-800 dark:bg-red-900/40 dark:text-red-200`
  }
  return `${base} bg-gray-200 text-gray-800 dark:bg-gray-700 dark:text-gray-200`
})

const isActive = computed(() => {
  if (!props.job) return false
  const s = props.job.stage || props.job.status
  return ['analyzing', 'fetching', 'summarizing', 'ranking'].includes(s)
})

const sourcesList = computed(() => {
  if (!props.job) return []
  const completed = new Set(props.job.sources_completed || [])
  const running = new Set(props.job.sources_running || [])
  const pending = new Set(props.job.sources_pending || [])
  
  const allSources = new Set([...completed, ...running, ...pending])
  
  return Array.from(allSources).sort().map(name => ({
    name,
    status: completed.has(name) ? 'done' : running.has(name) ? 'running' : 'pending',
  }))
})
</script>

<style scoped>
/* Smooth transitions for progress bar */
div.h-full {
  transition: width 500ms ease-out;
}
</style>
