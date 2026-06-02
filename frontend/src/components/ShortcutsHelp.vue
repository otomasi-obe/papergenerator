<template>
  <AppDialog :open="open" title="Keyboard Shortcuts" @close="emit('close')">
    <div class="shortcuts-grid">
      <div v-for="(shortcut, index) in shortcuts" :key="index" class="shortcut-row">
        <div class="shortcut-keys">
          <kbd class="kbd">{{ getShortcutLabel(shortcut) }}</kbd>
        </div>
        <div class="shortcut-description">{{ shortcut.description }}</div>
      </div>
    </div>
    <template #actions>
      <button
        @click="emit('close')"
        class="btn-primary"
      >
        Close
      </button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import AppDialog from './AppDialog.vue'
import { getShortcutLabel, type KeyboardShortcut } from '../composables/useKeyboardShortcuts'

interface Props {
  open: boolean
  shortcuts: KeyboardShortcut[]
}

interface Emits {
  (e: 'close'): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()
</script>

<style scoped>
.shortcuts-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.shortcut-row {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 1rem;
  align-items: center;
  padding: 0.5rem 0;
}

.shortcut-keys {
  display: flex;
  gap: 0.25rem;
  align-items: center;
  min-width: 120px;
}

.kbd {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1;
  color: var(--text-strong);
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: 0.375rem;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.shortcut-description {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.btn-primary {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  background: var(--accent);
  color: white;
  border: none;
  cursor: pointer;
  transition: background-color 0.2s, transform 0.15s;
}

.btn-primary:hover {
  filter: brightness(0.95);
}

.btn-primary:active {
  transform: scale(0.95);
}

.btn-primary:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px #238f7f;
}
</style>
