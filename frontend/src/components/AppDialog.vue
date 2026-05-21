<template>
  <Teleport to="body">
    <Transition name="app-dialog">
      <div v-if="open" class="dialog-backdrop" @click.self="emit('close')">
        <section
          ref="dialogRef"
          class="dialog-panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="resolvedLabelledById"
          tabindex="-1"
          @keydown="handleKeydown"
        >
          <header class="dialog-header">
            <h2 :id="resolvedLabelledById" class="dialog-title">{{ title }}</h2>
            <button type="button" class="dialog-close" aria-label="Close dialog" @click="emit('close')">×</button>
          </header>
          <div class="dialog-body">
            <slot />
          </div>
          <footer v-if="$slots.actions" class="dialog-actions">
            <slot name="actions" />
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, watch, ref } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  labelledById: { type: String, default: undefined },
})

const emit = defineEmits(['close'])
const dialogRef = ref(null)
const previouslyFocused = ref(null)
const generatedId = `dialog-title-${Math.random().toString(36).slice(2, 10)}`
const resolvedLabelledById = computed(() => props.labelledById || generatedId)

const focusableSelectors = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function getFocusable() {
  return Array.from(dialogRef.value?.querySelectorAll(focusableSelectors) || [])
    .filter((el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true')
}

function focusFirst() {
  const first = getFocusable()[0]
  if (first) first.focus()
  else dialogRef.value?.focus()
}

function restoreFocus() {
  previouslyFocused.value?.focus?.()
  previouslyFocused.value = null
}

function handleKeydown(event) {
  if (event.key === 'Escape') {
    emit('close')
    return
  }
  if (event.key !== 'Tab') return

  const focusable = getFocusable()
  if (!focusable.length) {
    event.preventDefault()
    dialogRef.value?.focus()
    return
  }

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.open, async (isOpen, wasOpen) => {
  if (isOpen) {
    previouslyFocused.value = document.activeElement
    await nextTick()
    focusFirst()
  } else if (wasOpen) {
    restoreFocus()
  }
}, { immediate: true })

onBeforeUnmount(restoreFocus)
</script>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  padding: var(--space-4);
  background: rgba(0, 0, 0, 0.48);
}

.dialog-panel {
  width: min(100%, 32rem);
  background: var(--bg-surface);
  color: var(--text-strong);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  outline: none;
}

.dialog-header,
.dialog-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
}

.dialog-header { border-bottom: 1px solid var(--border-soft); }
.dialog-actions { border-top: 1px solid var(--border-soft); justify-content: flex-end; }
.dialog-body { padding: var(--space-5); color: var(--text-base); }
.dialog-title { margin: 0; font: 600 1.125rem/1.4 var(--sans); }
.dialog-close { border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 1.5rem; line-height: 1; padding: var(--space-1) var(--space-2); }
.dialog-close:hover { background: var(--bg-elev); color: var(--text-strong); }
.dialog-close:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.app-dialog-enter-active,
.app-dialog-leave-active { transition: opacity var(--t-fast); }
.app-dialog-enter-active .dialog-panel,
.app-dialog-leave-active .dialog-panel { transition: transform var(--t-fast), opacity var(--t-fast); }
.app-dialog-enter-from,
.app-dialog-leave-to { opacity: 0; }
.app-dialog-enter-from .dialog-panel,
.app-dialog-leave-to .dialog-panel { opacity: 0; transform: scale(0.96); }
</style>
