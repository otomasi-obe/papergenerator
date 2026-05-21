<template>
  <div class="mb-2">
    <button
      @click="isOpen = !isOpen"
      class="flex items-center gap-2 text-xs text-[var(--accent)] hover:text-[var(--accent)]/80 transition-colors"
    >
      <svg
        :class="['w-3 h-3 transition-transform', isOpen ? 'rotate-90' : '']"
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path d="M6 4l8 6-8 6V4z"/>
      </svg>
      <span class="font-medium">
        <span v-if="isStreaming && !content" class="inline-flex items-center gap-1">
          Thinking
          <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce"></span>
          <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
          <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
        </span>
        <span v-else>Thinking</span>
      </span>
    </button>
    <div
      v-show="isOpen"
      class="mt-1.5 pl-5 border-l-2 border-[var(--accent)]/25"
    >
      <p class="text-xs text-ink-500 dark:text-ink-400 whitespace-pre-wrap leading-relaxed">{{ content }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  content: { type: String, default: '' },
  isStreaming: { type: Boolean, default: false }
})

const isOpen = ref(false)
</script>
