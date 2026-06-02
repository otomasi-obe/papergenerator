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
  color: #374151;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.dark .kbd {
  color: #e5e7eb;
  background: #374151;
  border-color: #4b5563;
}

.shortcut-description {
  font-size: 0.875rem;
  color: #6b7280;
}

.dark .shortcut-description {
  color: #9ca3af;
}

.btn-primary {
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  background: #8b7355;
  color: white;
  border: none;
  cursor: pointer;
  transition: background-color 0.2s;
}

.btn-primary:hover {
  background: #6d5a44;
}

.btn-primary:focus-visible {
  outline: 2px solid #8b7355;
  outline-offset: 2px;
}
</style>
