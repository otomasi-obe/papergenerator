<template>
  <Teleport to="body">
    <Transition name="tour-fade">
      <div v-if="active && steps.length > 0" class="tour-overlay" role="dialog" aria-label="Guided tour">
        <!-- SVG overlay with cutout for highlighted element -->
        <svg
          class="tour-overlay-svg"
          xmlns="http://www.w3.org/2000/svg"
          :viewBox="`0 0 ${viewport.w} ${viewport.h}`"
          preserveAspectRatio="none"
        >
          <defs>
            <mask :id="maskId">
              <rect x="0" y="0" :width="viewport.w" :height="viewport.h" fill="white" />
              <rect
                :x="highlightRect.x - padding"
                :y="highlightRect.y - padding"
                :width="highlightRect.w + padding * 2"
                :height="highlightRect.h + padding * 2"
                :rx="borderRadius"
                fill="black"
              />
            </mask>
          </defs>
          <rect
            x="0"
            y="0"
            :width="viewport.w"
            :height="viewport.h"
            fill="rgba(0,0,0,0.6)"
            :mask="`url(#${maskId})`"
            class="tour-dim"
          />
        </svg>

        <!-- Pulsing highlight border -->
        <div
          v-if="highlightRect.w > 0"
          class="tour-highlight-ring"
          :style="ringStyle"
        />

        <!-- Tooltip bubble -->
        <div
          v-if="currentStep"
          ref="tooltipRef"
          class="tour-tooltip"
          :class="`tour-tooltip--${resolvedPosition}`"
          :style="tooltipStyle"
        >
          <div class="tour-tooltip-header">
            <span class="tour-step-indicator">{{ currentStepIndex + 1 }}/{{ steps.length }}</span>
            <h3 class="tour-tooltip-title">{{ currentStep.title }}</h3>
          </div>
          <p class="tour-tooltip-desc">{{ currentStep.description }}</p>
          <div class="tour-tooltip-actions">
            <button
              type="button"
              class="tour-btn tour-btn--skip"
              @click="skip"
            >
              Skip
            </button>
            <button
              v-if="currentStepIndex < steps.length - 1"
              type="button"
              class="tour-btn tour-btn--next"
              @click="next"
            >
              Next
            </button>
            <button
              v-else
              type="button"
              class="tour-btn tour-btn--done"
              @click="finish"
            >
              Done
            </button>
          </div>
          <!-- Progress dots -->
          <div class="tour-dots">
            <span
              v-for="(_, i) in steps"
              :key="i"
              class="tour-dot"
              :class="{ 'tour-dot--active': i === currentStepIndex, 'tour-dot--done': i < currentStepIndex }"
            />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount, onMounted } from 'vue'

export interface TourStep {
  target: string
  title: string
  description: string
  position?: 'top' | 'bottom' | 'left' | 'right'
}

interface Props {
  active: boolean
  steps: TourStep[]
}

interface Emits {
  (e: 'finish'): void
  (e: 'skip'): void
}

const props = withDefaults(defineProps<Props>(), {
  steps: () => [],
})
const emit = defineEmits<Emits>()

const maskId = `tour-mask-${Math.random().toString(36).slice(2, 8)}`
const padding = 8
const borderRadius = 8
const tooltipOffset = 16
const tooltipWidth = 320

const currentStepIndex = ref(0)
const highlightRect = ref({ x: 0, y: 0, w: 0, h: 0 })
const viewport = ref({ w: window.innerWidth, h: window.innerHeight })
const tooltipRef = ref<HTMLElement | null>(null)
const tooltipHeight = ref(180)

const currentStep = computed(() => props.steps[currentStepIndex.value] || null)
const resolvedPosition = computed((): string => {
  const step = currentStep.value
  if (!step) return 'bottom'
  const requested = step.position || 'bottom'
  const r = highlightRect.value
  const vh = viewport.value.h
  const vw = viewport.value.w

  // Reposition if tooltip would go off-screen
  if (requested === 'bottom' && r.y + r.h + tooltipOffset + tooltipHeight.value > vh) {
    if (r.y - tooltipOffset - tooltipHeight.value > 0) return 'top'
    return 'bottom'
  }
  if (requested === 'top' && r.y - tooltipOffset - tooltipHeight.value < 0) {
    if (r.y + r.h + tooltipOffset + tooltipHeight.value < vh) return 'bottom'
    return 'top'
  }
  if (requested === 'left' && r.x - tooltipOffset - tooltipWidth < 0) {
    if (r.x + r.w + tooltipOffset + tooltipWidth < vw) return 'right'
    return 'bottom'
  }
  if (requested === 'right' && r.x + r.w + tooltipOffset + tooltipWidth > vw) {
    if (r.x - tooltipOffset - tooltipWidth > 0) return 'left'
    return 'bottom'
  }
  return requested
})

const ringStyle = computed(() => ({
  left: `${highlightRect.value.x - padding}px`,
  top: `${highlightRect.value.y - padding}px`,
  width: `${highlightRect.value.w + padding * 2}px`,
  height: `${highlightRect.value.h + padding * 2}px`,
}))

const tooltipStyle = computed(() => {
  const r = highlightRect.value
  const pos = resolvedPosition.value
  const style: Record<string, string> = {
    position: 'absolute',
    width: `${tooltipWidth}px`,
    zIndex: '10002',
  }

  if (pos === 'bottom') {
    style.left = `${Math.max(8, Math.min(r.x + r.w / 2 - tooltipWidth / 2, viewport.value.w - tooltipWidth - 8))}px`
    style.top = `${r.y + r.h + padding + tooltipOffset}px`
  } else if (pos === 'top') {
    style.left = `${Math.max(8, Math.min(r.x + r.w / 2 - tooltipWidth / 2, viewport.value.w - tooltipWidth - 8))}px`
    style.bottom = `${viewport.value.h - r.y + padding + tooltipOffset}px`
  } else if (pos === 'left') {
    style.left = `${r.x - tooltipWidth - padding - tooltipOffset}px`
    style.top = `${Math.max(8, r.y + r.h / 2 - 90)}px`
  } else {
    // right
    style.left = `${r.x + r.w + padding + tooltipOffset}px`
    style.top = `${Math.max(8, r.y + r.h / 2 - 90)}px`
  }

  return style
})

function measureTarget(): void {
  const step = currentStep.value
  if (!step) return
  const el = document.querySelector(step.target) as HTMLElement | null
  if (el) {
    const rect = el.getBoundingClientRect()
    highlightRect.value = {
      x: rect.left,
      y: rect.top,
      w: rect.width,
      h: rect.height,
    }
    // Scroll into view smoothly
    el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' })
  }
}

function measureTooltip(): void {
  if (tooltipRef.value) {
    tooltipHeight.value = tooltipRef.value.offsetHeight || 180
  }
}

function next(): void {
  if (currentStepIndex.value < props.steps.length - 1) {
    currentStepIndex.value++
  }
}

function finish(): void {
  currentStepIndex.value = 0
  emit('finish')
}

function skip(): void {
  currentStepIndex.value = 0
  emit('skip')
}

function handleResize(): void {
  viewport.value = { w: window.innerWidth, h: window.innerHeight }
  measureTarget()
}

function handleKeydown(e: KeyboardEvent): void {
  if (!props.active) return
  if (e.key === 'Escape') skip()
  if (e.key === 'ArrowRight' || e.key === 'Enter') {
    if (currentStepIndex.value < props.steps.length - 1) next()
    else finish()
  }
  if (e.key === 'ArrowLeft' && currentStepIndex.value > 0) {
    currentStepIndex.value--
  }
}

watch(() => props.active, (isActive) => {
  if (isActive) {
    currentStepIndex.value = 0
    nextTick(() => {
      measureTarget()
      measureTooltip()
    })
  }
})

watch(currentStepIndex, () => {
  nextTick(() => {
    measureTarget()
    measureTooltip()
  })
})

onMounted(() => {
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', handleKeydown)
  if (props.active) {
    nextTick(() => measureTarget())
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
/* Overlay */
.tour-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  pointer-events: none;
}

.tour-overlay-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.tour-dim {
  pointer-events: none;
}

/* Highlight ring with pulse animation */
.tour-highlight-ring {
  position: absolute;
  border: 2px solid var(--accent-primary, #1265c8);
  border-radius: 8px;
  box-shadow:
    0 0 0 4px color-mix(in srgb, var(--accent-primary, #1265c8) 25%, transparent),
    0 0 20px color-mix(in srgb, var(--accent-primary, #1265c8) 30%, transparent);
  pointer-events: auto;
  animation: tour-pulse 2s ease-in-out infinite;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes tour-pulse {
  0%, 100% {
    box-shadow:
      0 0 0 4px color-mix(in srgb, var(--accent-primary, #1265c8) 25%, transparent),
      0 0 20px color-mix(in srgb, var(--accent-primary, #1265c8) 30%, transparent);
  }
  50% {
    box-shadow:
      0 0 0 6px color-mix(in srgb, var(--accent-primary, #1265c8) 35%, transparent),
      0 0 30px color-mix(in srgb, var(--accent-primary, #1265c8) 45%, transparent);
  }
}

/* Tooltip */
.tour-tooltip {
  pointer-events: auto;
  background: var(--cream-50, #f8f5ef);
  color: var(--text-strong, #0c0a07);
  border: 1px solid var(--border-soft, #c4a87a);
  border-radius: var(--radius-lg, 16px);
  box-shadow: var(--shadow-lg, 0 28px 64px rgba(16, 24, 31, 0.14));
  padding: var(--space-4, 16px) var(--space-5, 24px);
  animation: tour-tooltip-in 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  transition: left 0.4s cubic-bezier(0.4, 0, 0.2, 1),
              top 0.4s cubic-bezier(0.4, 0, 0.2, 1),
              bottom 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

html.dark .tour-tooltip {
  background: var(--bg-surface, #102c55);
  border-color: var(--border-soft, #2a4a6e);
}

@keyframes tour-tooltip-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.tour-tooltip-header {
  display: flex;
  align-items: center;
  gap: var(--space-2, 8px);
  margin-bottom: var(--space-2, 8px);
}

.tour-step-indicator {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--accent-primary, #1265c8);
  color: #fff;
  white-space: nowrap;
}

.tour-tooltip-title {
  margin: 0;
  font: 600 1rem/1.3 var(--font-sans, "DM Sans", sans-serif);
  color: var(--text-strong, #0c0a07);
}

.tour-tooltip-desc {
  margin: 0 0 var(--space-4, 16px) 0;
  font-size: 0.875rem;
  line-height: 1.5;
  color: var(--text-muted, #4a4035);
}

.tour-tooltip-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2, 8px);
  margin-bottom: var(--space-3, 12px);
}

/* Buttons */
.tour-btn {
  padding: 6px 16px;
  border-radius: var(--radius-sm, 6px);
  font-size: 0.8125rem;
  font-weight: 500;
  font-family: var(--font-sans, "DM Sans", sans-serif);
  cursor: pointer;
  border: none;
  transition: background 0.15s, transform 0.1s, filter 0.15s;
  line-height: 1.4;
}

.tour-btn:active {
  transform: scale(0.96);
}

.tour-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.tour-btn--skip {
  background: transparent;
  color: var(--text-muted, #4a4035);
}

.tour-btn--skip:hover {
  background: var(--bg-elev, #f0ebe2);
  color: var(--text-strong, #0c0a07);
}

.tour-btn--next,
.tour-btn--done {
  background: var(--accent-primary, #1265c8);
  color: #fff;
}

.tour-btn--next:hover,
.tour-btn--done:hover {
  filter: brightness(1.1);
}

/* Progress dots */
.tour-dots {
  display: flex;
  justify-content: center;
  gap: 6px;
}

.tour-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--border-soft, #c4a87a);
  transition: background 0.2s, transform 0.2s;
}

.tour-dot--active {
  background: var(--accent-primary, #1265c8);
  transform: scale(1.3);
}

.tour-dot--done {
  background: var(--accent, #238f7f);
}

/* Transition */
.tour-fade-enter-active,
.tour-fade-leave-active {
  transition: opacity 0.3s ease;
}

.tour-fade-enter-from,
.tour-fade-leave-to {
  opacity: 0;
}

/* Mobile adjustments */
@media (max-width: 480px) {
  .tour-tooltip {
    width: calc(100vw - 32px) !important;
    left: 16px !important;
  }

  .tour-tooltip--top,
  .tour-tooltip--bottom {
    left: 16px !important;
  }
}
</style>
