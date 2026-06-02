<template>
  <div class="mt-2 border rounded-lg bg-gray-50 p-3">
    <div class="flex items-center gap-2 mb-2">
      <svg class="w-4 h-4 text-[var(--accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
      </svg>
      <span class="text-xs font-medium text-gray-600">AI Prompt — edit this {{ section }}</span>
    </div>
    <div class="flex gap-2">
      <input v-model="prompt" type="text"
        :placeholder="`e.g.: Rewrite to be more formal, Add more detail about methodology...`"
        class="flex-1 px-3 py-1.5 border rounded text-sm focus:ring-2 focus:ring-[var(--focus-ring)]/30 focus:border-[var(--accent)] outline-none"
        @keyup.enter="generate" :disabled="loading" />
      <button @click="generate"
        :disabled="loading || !prompt.trim()"
        class="px-4 py-1.5 bg-[var(--accent)] text-white rounded text-sm hover:bg-[var(--accent)]/90 disabled:opacity-50 flex items-center gap-1">
        <span v-if="loading" class="spinner !w-3 !h-3"></span>
        <span>Send</span>
      </button>
    </div>
    <p class="text-xs text-gray-400 mt-1">Sends current text + your prompt to AI. Result will replace current content.</p>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { usePaperStore } from '../stores/paper'
import type { AiPromptBoxProps, AiPromptBoxEmits } from '../types/components'

const props = defineProps<AiPromptBoxProps>()

const emit = defineEmits<AiPromptBoxEmits>()

// @ts-ignore - paper store will be converted to TypeScript in Week 3-4
const { usePaperStore } = await import('../stores/paper.js')
const store = usePaperStore()

const prompt = ref<string>('')
const loading = ref<boolean>(false)

async function generate(): Promise<void> {
  if (!prompt.value.trim()) return
  loading.value = true
  try {
    const result = await store.aiGenerate(prompt.value, props.section, props.lastText)
    if (result) {
      emit('generated', result.trim())
      prompt.value = ''
    }
  } finally {
    loading.value = false
  }
}
</script>
