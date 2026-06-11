<template>
  <div class="mb-2 thinking-container">
    <button
      @click="isOpen = !isOpen"
      class="flex items-center gap-2 text-xs transition-colors thinking-toggle"
      :class="isStreaming ? 'thinking-active' : 'thinking-idle'"
    >
      <svg
        :class="['w-3 h-3 transition-transform', isOpen ? 'rotate-90' : '']"
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path d="M6 4l8 6-8 6V4z"/>
      </svg>
      <span class="font-medium">
        <span v-if="isStreaming && !content" class="inline-flex items-center gap-1.5 thinking-label">
          <span class="thinking-flash-text">Masih berpikir</span>
          <span class="thinking-dots">
            <span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
          </span>
          <span class="thinking-shimmer-bar">
            <span class="shimmer-glow" />
          </span>
        </span>
        <span v-else-if="isStreaming && content">
          Masih berpikir... <span class="inline-flex items-center gap-1 ml-1">
            <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce"></span>
            <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
            <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
          </span>
        </span>
        <span v-else>💭 Reasoning</span>
      </span>
    </button>
    <div
      v-show="isOpen"
      class="mt-1.5 pl-5 border-l-2 border-[var(--accent)]/25 thinking-content"
    >
      <p class="text-xs text-ink-500 dark:text-ink-400 whitespace-pre-wrap leading-relaxed">
        {{ content || '...' }}
      </p>
      <!-- Streaming cursor when content is being received -->
      <span
        v-if="isStreaming"
        class="inline-block w-1.5 h-3.5 bg-[var(--accent)]/80 animate-pulse align-middle ml-0.5"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ThinkingBlockProps } from '../types/components'

const props = defineProps<ThinkingBlockProps>()

const isOpen = ref<boolean>(false)

// Auto-open when content starts flowing during streaming
watch(
  () => props.content,
  (newVal) => {
    if (props.isStreaming && newVal) {
      isOpen.value = true
    }
  }
)

// Also auto-open when streaming starts
watch(
  () => props.isStreaming,
  (streaming) => {
    if (streaming) {
      // Slight delay to let the label animate first, then auto-expand
      setTimeout(() => { isOpen.value = true }, 800)
    }
  }
)
</script>

<style scoped>
/* --- Flash text: pulsing glow on "Masih berpikir" --- */
@keyframes flash-pulse {
  0%, 100% {
    opacity: 1;
    text-shadow: 0 0 0px transparent;
  }
  50% {
    opacity: 0.6;
    text-shadow: 0 0 8px var(--accent, #238f7f);
  }
}

.thinking-flash-text {
  background: linear-gradient(
    90deg,
    var(--accent, #238f7f) 0%,
    var(--accent, #238f7f) 30%,
    #fff 50%,
    var(--accent, #238f7f) 70%,
    var(--accent, #238f7f) 100%
  );
  background-size: 200% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer-slide 1.8s linear infinite, flash-pulse 1.2s ease-in-out infinite;
}

/* --- Animated dots: sequential bounce --- */
@keyframes dot-blink {
  0%, 20% { opacity: 0; }
  40% { opacity: 1; }
  60%, 100% { opacity: 0; }
}

.thinking-dots {
  display: inline-flex;
  gap: 1px;
}

.thinking-dots .dot {
  color: var(--accent, #238f7f);
  font-weight: bold;
  animation: dot-blink 1.4s ease-in-out infinite;
}

.thinking-dots .dot:nth-child(2) {
  animation-delay: 0.2s;
}

.thinking-dots .dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes shimmer-slide {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

.thinking-label {
  position: relative;
  overflow: hidden;
}

.thinking-shimmer-text {
  background: linear-gradient(
    90deg,
    var(--accent, #238f7f) 0%,
    var(--accent, #238f7f) 40%,
    #fff 50%,
    var(--accent, #238f7f) 60%,
    var(--accent, #238f7f) 100%
  );
  background-size: 200% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer-slide 1.8s linear infinite;
}

.thinking-shimmer-bar {
  display: inline-block;
  width: 40px;
  height: 12px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--accent, #238f7f) 15%, transparent);
  overflow: hidden;
  vertical-align: middle;
}

.shimmer-glow {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 6px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--accent, #238f7f)20 30%,
    var(--accent, #238f7f)70 50%,
    var(--accent, #238f7f)20 70%,
    transparent 100%
  );
  background-size: 200% 100%;
  animation: shimmer-slide 1.2s ease-in-out infinite;
}

.thinking-toggle {
  color: var(--text-muted, #6b7280);
}

.thinking-active {
  color: var(--accent, #238f7f);
}

.thinking-active:hover {
  color: var(--accent, #238f7f);
  opacity: 0.85;
}

.thinking-idle {
  color: var(--accent, #238f7f);
  opacity: 0.85;
}

.thinking-idle:hover {
  color: var(--accent, #238f7f);
  opacity: 1;
}

.thinking-content {
  max-height: 400px;
  overflow-y: auto;
}
</style>