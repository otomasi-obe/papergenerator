<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'

const error = ref<Error | null>(null)
const errorInfo = ref<string>('')

onErrorCaptured((err: Error, _instance, info) => {
  error.value = err
  errorInfo.value = info
  if (import.meta.env.DEV) console.error('ErrorBoundary caught:', err, info)
  return false
})

function reset() {
  error.value = null
  errorInfo.value = ''
}
</script>

<template>
  <div v-if="error" class="flex flex-col items-center justify-center min-h-[400px] p-8 text-center" role="alert">
    <div class="max-w-md">
      <h2 class="text-xl font-semibold text-ink-900 dark:text-anthracite-50 mb-2">Something went wrong</h2>
      <p class="text-sm text-ink-600 dark:text-anthracite-100 mb-4">{{ error.message }}</p>
      <p class="text-xs text-red-500 dark:text-red-400 mb-4 whitespace-pre-wrap text-left max-h-40 overflow-auto bg-cream-100 dark:bg-ash-700 p-2 rounded max-w-md">{{ error.stack }}</p>
      <button
        @click="reset"
        class="px-4 py-2 text-sm font-medium text-white bg-[var(--accent,#b54a1f)] rounded-lg hover:opacity-90 active:scale-95 transition-transform"
      >
        Try again
      </button>
    </div>
  </div>
  <slot v-else />
</template>
