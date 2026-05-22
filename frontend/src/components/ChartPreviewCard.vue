<template>
  <div class="chart-proposal rounded-lg border p-3 my-2
              bg-cream-50 dark:bg-ash-800
              border-cream-300 dark:border-ash-700">
    <div class="flex items-center gap-2 mb-2">
      <span class="text-base shrink-0">📊</span>
      <span class="text-sm font-medium text-ink-800 dark:text-ink-100 truncate">
        Chart proposal
        <span v-if="kindLabel" class="opacity-70">— {{ kindLabel }}</span>
      </span>
    </div>

    <div v-if="title" class="text-xs text-ink-700 dark:text-ink-300 mb-2">
      {{ title }}
    </div>

    <div v-if="url" class="rounded-md overflow-hidden border border-cream-300 dark:border-ash-700 bg-white dark:bg-ash-900">
      <img
        :src="url"
        :alt="title || 'chart preview'"
        class="block max-w-full h-auto mx-auto"
        loading="lazy"
      />
    </div>
    <div
      v-else
      class="text-xs text-ink-500 dark:text-ink-400 italic px-2 py-3 rounded-md border border-dashed border-cream-300 dark:border-ash-700"
    >
      Preview belum tersedia.
    </div>

    <details v-if="hasSpec" class="mt-2 text-[11px] text-ink-600 dark:text-ink-300">
      <summary class="cursor-pointer select-none">Lihat spec</summary>
      <pre class="mt-1 p-2 rounded bg-cream-100 dark:bg-ash-900 overflow-x-auto whitespace-pre-wrap break-words">{{ specPretty }}</pre>
    </details>

    <div class="flex flex-wrap gap-2 mt-3">
      <button
        type="button"
        @click="$emit('accept', { imageId, spec, url })"
        class="px-3 py-1.5 rounded-md text-xs font-medium
               bg-brown-600 hover:bg-brown-700 text-cream-50
               dark:bg-cream-300 dark:hover:bg-cream-200 dark:text-ink-900
               focus:outline-none focus:ring-2 focus:ring-brown-400 dark:focus:ring-cream-400"
      >
        Pakai chart ini
      </button>
      <button
        type="button"
        @click="$emit('regenerate', { imageId, spec })"
        class="px-3 py-1.5 rounded-md text-xs font-medium border
               bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
               border-cream-300 dark:border-ash-600
               text-ink-800 dark:text-ink-100
               focus:outline-none focus:ring-2 focus:ring-brown-400 dark:focus:ring-cream-400"
      >
        Generate ulang
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  url: { type: String, default: '' },
  spec: { type: Object, default: null },
  imageId: { type: [String, Number], default: null },
  title: { type: String, default: '' },
})

defineEmits(['accept', 'regenerate'])

const kindLabel = computed(() => {
  const k = props.spec?.kind || props.spec?.type || ''
  return k ? String(k) : ''
})

const hasSpec = computed(() => {
  return !!props.spec && Object.keys(props.spec).length > 0
})

const specPretty = computed(() => {
  try { return JSON.stringify(props.spec, null, 2) }
  catch { return String(props.spec) }
})
</script>
