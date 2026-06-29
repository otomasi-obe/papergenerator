<template>
  <div class="mb-2 thinking-container">
    <button
      @click="isOpen = !isOpen"
      class="flex items-center gap-2 text-xs transition-colors thinking-toggle"
      :class="thinkingActive ? 'thinking-active' : 'thinking-idle'"
    >
      <svg
        :class="['w-3 h-3 transition-transform', isOpen ? 'rotate-90' : '']"
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path d="M6 4l8 6-8 6V4z"/>
      </svg>
      <span class="font-medium">
        <!-- Phase: actively thinking -->
        <span v-if="isThinking" class="inline-flex items-center gap-1.5 thinking-label">
          <span class="thinking-flash-text">{{ thinkingLabel }}</span>
          <span class="thinking-dots">
            <span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
          </span>
        </span>
        <!-- Phase: thinking has content and still streaming -->
        <span v-else-if="isStreaming && content && !isThinkingDone">
          {{ thinkingLabelElipsis }} <span class="inline-flex items-center gap-1 ml-1">
            <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce"></span>
            <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce" style="animation-delay: 0.1s"></span>
            <span class="inline-block w-1 h-1 bg-[var(--accent)]/70 rounded-full animate-bounce" style="animation-delay: 0.2s"></span>
          </span>
        </span>
        <!-- Phase: thinking done — show completed state -->
        <span v-else>💭 Reasoning</span>
      </span>
    </button>
    <div
      v-show="isOpen"
      class="mt-1.5 pl-5 border-l-2 border-[var(--accent)]/25 thinking-content"
    >
      <p class="text-xs text-ink-500 dark:text-cream-200 whitespace-pre-wrap leading-relaxed">
        {{ content || '...' }}
      </p>
      <!-- Streaming cursor when content is being received -->
      <span
        v-if="isThinking"
        class="inline-block w-1.5 h-3.5 bg-[var(--accent)]/80 animate-pulse align-middle ml-0.5"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onBeforeUnmount } from 'vue'
import { usePaperStore } from '../stores/paper'

const paperStore = usePaperStore()

const props = defineProps<{
  content: string
  isStreaming: boolean
  streamPhase?: string
}>()

const isOpen = ref<boolean>(false)

// Language-aware labels
const thinkingLabel = computed(() =>
  paperStore.paper.language === 'en' ? 'Thinking' : 'Masih berpikir'
)
const thinkingLabelElipsis = computed(() =>
  paperStore.paper.language === 'en' ? 'Thinking...' : 'Masih berpikir...'
)

let _openTimer: ReturnType<typeof setTimeout> | null = null
let _closeTimer: ReturnType<typeof setTimeout> | null = null

// Derived: actively thinking (phase === 'thinking' or streaming with no content yet)
const isThinking = computed(() => {
  if (props.streamPhase === 'thinking') return true
  if (props.isStreaming && !props.content) return true
  return false
})

// Derived: thinking phase is done
const isThinkingDone = computed(() => {
  return props.streamPhase === 'composing' || props.streamPhase === 'streaming' || props.streamPhase === 'done'
})

// Whether the thinking block header should show active styling
const thinkingActive = computed(() => {
  return isThinking.value || (props.isStreaming && !isThinkingDone.value)
})

// Auto-open when content starts flowing during streaming
watch(
  () => props.content,
  (newVal) => {
    if (props.isStreaming && newVal && isThinking.value) {
      isOpen.value = true
    }
  }
)

// Also auto-open when streaming starts in thinking phase
watch(
  () => props.isStreaming,
  (streaming) => {
    if (streaming && isThinking.value) {
      // Slight delay to let the label animate first, then auto-expand
      clearTimeout(_openTimer)
      _openTimer = setTimeout(() => { isOpen.value = true }, 800)
    }
  }
)

// Auto-close thinking block when phase moves past thinking (composing/streaming)
// but only if it was auto-opened (not manually toggled by user)
watch(
  () => props.streamPhase,
  (newPhase) => {
    if ((newPhase === 'composing' || newPhase === 'streaming') && isOpen.value) {
      // Collapse thinking block when content starts flowing
      // User can still re-open it manually
      clearTimeout(_closeTimer)
      _closeTimer = setTimeout(() => { isOpen.value = false }, 500)
    }
  }
)

onBeforeUnmount(() => {
  if (_openTimer !== null) {
    clearTimeout(_openTimer)
    _openTimer = null
  }
  if (_closeTimer !== null) {
    clearTimeout(_closeTimer)
    _closeTimer = null
  }
})
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