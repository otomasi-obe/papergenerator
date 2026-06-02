<template>
  <div class="rounded-lg border border-cream-300 bg-cream-50 overflow-hidden text-xs">
    <!-- Header -->
    <div class="flex items-center gap-2 px-3 py-2 bg-cream-100 border-b border-cream-300">
      <div :class="['w-2 h-2 rounded-full', statusColor]"></div>
      <span class="font-mono font-medium text-ink-700">{{ toolCall.name }}</span>
      <span class="text-ink-400 ml-auto">{{ statusLabel }}</span>
    </div>

    <!-- Arguments -->
    <div class="px-3 py-2 border-b border-cream-200">
      <div class="text-ink-500 mb-1 font-medium">Arguments:</div>
      <pre class="text-ink-700 font-mono whitespace-pre-wrap break-all bg-white rounded p-2 border border-cream-200">{{ formattedArgs }}</pre>
    </div>

    <!-- Result -->
    <div v-if="toolCall.result" class="px-3 py-2">
      <button
        @click="showResult = !showResult"
        class="flex items-center gap-1 text-ink-500 hover:text-ink-700 font-medium mb-1 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30 active:scale-95 transition-transform"
      >
        <svg
          :class="['w-3 h-3 transition-transform', showResult ? 'rotate-90' : '']"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path d="M6 4l8 6-8 6V4z"/>
        </svg>
        Result
      </button>
      <pre
        v-show="showResult"
        class="text-ink-600 font-mono whitespace-pre-wrap break-all bg-white rounded p-2 border border-cream-200 max-h-48 overflow-y-auto"
      >{{ toolCall.result }}</pre>
    </div>

    <!-- Running indicator -->
    <div v-if="toolCall.status === 'running'" class="px-3 py-2 flex items-center gap-2">
      <span class="inline-block w-3 h-3 border-2 border-[var(--accent)]/70 border-t-transparent rounded-full animate-spin"></span>
      <span class="text-ink-500">Executing...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ToolCallBlockProps } from '../types/components'

const props = defineProps<ToolCallBlockProps>()

const showResult = ref<boolean>(false)

const statusColor = computed<string>(() => {
  if (props.toolCall.status === 'running') return 'bg-yellow-400 animate-pulse'
  if (props.toolCall.status === 'done') return 'bg-green-400'
  return 'bg-ink-400'
})

const statusLabel = computed<string>(() => {
  if (props.toolCall.status === 'running') return 'running'
  if (props.toolCall.status === 'done') return 'completed'
  return ''
})

const formattedArgs = computed<string>(() => {
  if (!props.toolCall.arguments) return '{}'
  if (typeof props.toolCall.arguments === 'string') return props.toolCall.arguments
  return JSON.stringify(props.toolCall.arguments, null, 2)
})
</script>
