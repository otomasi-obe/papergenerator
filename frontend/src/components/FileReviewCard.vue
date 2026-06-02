<template>
  <div class="file-review rounded-lg border p-3 my-2
              bg-cream-50 dark:bg-ash-800
              border-cream-300 dark:border-ash-700">
    <div class="flex items-center gap-2 mb-2">
      <span class="text-base shrink-0">📄</span>
      <span class="text-sm font-medium text-ink-800 dark:text-ink-100 truncate">
        File review — {{ filename || 'file' }}
      </span>
    </div>

    <div class="text-xs text-ink-600 dark:text-ink-300 mb-2">
      <span class="font-medium">{{ wordCount.toLocaleString() }}</span> kata
      <span class="opacity-70">· terlalu panjang untuk full inject</span>
    </div>

    <details
      v-if="head || tail"
      class="text-xs mb-3 rounded-md border border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-900"
    >
      <summary class="cursor-pointer select-none px-2 py-1.5 text-ink-700 dark:text-ink-200">
        Preview awal/akhir
      </summary>
      <div class="px-2 pb-2 pt-1 space-y-2">
        <div v-if="head">
          <div class="text-[10px] uppercase tracking-wide text-ink-500 dark:text-ink-400 mb-0.5">Awal</div>
          <div class="text-ink-800 dark:text-ink-100 whitespace-pre-wrap break-words">{{ head }}</div>
        </div>
        <div v-if="tail">
          <div class="text-[10px] uppercase tracking-wide text-ink-500 dark:text-ink-400 mb-0.5">Akhir</div>
          <div class="text-ink-800 dark:text-ink-100 whitespace-pre-wrap break-words">{{ tail }}</div>
        </div>
      </div>
    </details>

    <div v-if="suggestedKinds.length" class="text-xs mb-2 text-ink-700 dark:text-ink-300">
      Pilih bagian mana yang mau diambil:
    </div>
    <div v-if="suggestedKinds.length" class="flex flex-wrap gap-2">
      <button
        v-for="kind in suggestedKinds"
        :key="kind"
        type="button"
        @click="$emit('pick', { kind, fileId })"
        class="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors
               bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
               border-cream-300 dark:border-ash-600
                text-ink-800 dark:text-ink-100
                focus:outline-none focus-visible:ring-2 focus-visible:ring-[#238f7f]/30 dark:focus:ring-cream-400"
      >
        {{ kind }}
      </button>
    </div>
    <div
      v-else
      class="text-[11px] text-ink-500 dark:text-ink-400 italic"
    >
      Tidak ada saran ekstraksi. Tanya AI untuk bagian spesifik yang dibutuhkan.
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FileReviewCardProps, FileReviewCardEmits } from '../types/components'

withDefaults(defineProps<FileReviewCardProps>(), {
  filename: '',
  wordCount: 0,
  head: '',
  tail: '',
  suggestedKinds: () => [],
  fileId: null
})

defineEmits<FileReviewCardEmits>()
</script>
