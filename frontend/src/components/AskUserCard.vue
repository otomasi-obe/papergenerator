<template>
  <div class="ask-user-card">
    <!-- Question -->
    <div class="ask-header">
      <span class="ask-icon">❓</span>
      <span class="ask-question">{{ question }}</span>
    </div>

    <!-- Options as chips -->
    <div class="ask-options">
      <button
        v-for="(opt, idx) in options"
        :key="idx"
        type="button"
        class="ask-chip"
        :class="{ selected: selected === opt }"
        :disabled="submitted"
        @click="pickOption(opt)"
      >
        <span class="chip-num">{{ idx + 1 }}</span>
        {{ opt }}
      </button>
    </div>

    <!-- Free text input -->
    <div class="ask-custom">
      <input
        v-model="customAnswer"
        class="ask-input"
        placeholder="Atau ketik jawaban Anda sendiri…"
        :disabled="submitted"
        @input="onCustomInput"
        @keyup.enter="submit"
      />
    </div>

    <!-- Submit button -->
    <div class="ask-actions">
      <button
        type="button"
        class="ask-submit"
        :disabled="!hasAnswer || submitted"
        @click="submit"
      >
        {{ submitted ? '✓ Terkirim' : 'Kirim Jawaban' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed } from 'vue'

const props = defineProps<{
  question: string
  options: string[]
}>()

const emit = defineEmits<{
  (e: 'answer', value: string): void
}>()

const selected = ref<string>('')
const customAnswer = ref<string>('')
const submitted = ref(false)

const hasAnswer = computed(() => {
  if (customAnswer.value.trim()) return true
  if (selected.value) return true
  return false
})

function pickOption(opt: string): void {
  selected.value = opt
  customAnswer.value = ''
}

function onCustomInput(): void {
  if (customAnswer.value.trim()) {
    selected.value = ''
  }
}

function submit(): void {
  if (!hasAnswer.value || submitted.value) return
  submitted.value = true
  const answer = customAnswer.value.trim() || selected.value
  emit('answer', answer)
}
</script>

<style scoped>
.ask-user-card {
  border: 1.5px solid var(--border-soft, #dfcfb5);
  border-radius: 12px;
  padding: 14px;
  background: var(--surface-ai, #fbf8f1);
  color: var(--text-strong, #0c1c3c);
  margin: 8px 0;
}

.ask-header {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.ask-icon {
  font-size: 18px;
  flex-shrink: 0;
  line-height: 1.4;
}

.ask-question {
  font-weight: 600;
  font-size: 14px;
  line-height: 1.45;
  color: var(--text-strong, inherit);
}

.ask-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-bottom: 10px;
}

.ask-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid var(--border-strong, #c3aa83);
  border-radius: 8px;
  background: var(--bg-surface, #ffffff);
  color: var(--text-strong, #0c1c3c);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
  line-height: 1.35;
}

.ask-chip:hover:not(:disabled):not(.selected) {
  background: var(--bg-elev, #faf5ec);
  border-color: var(--accent-primary, #1265c8);
}

.ask-chip.selected {
  background: var(--accent-primary, #1265c8);
  color: #ffffff;
  border-color: var(--accent-primary, #1265c8);
}

.ask-chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ask-chip:active:not(:disabled) {
  transform: scale(0.97);
}

.chip-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--border-soft, #dfcfb5);
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.ask-chip.selected .chip-num {
  background: rgba(255, 255, 255, 0.25);
}

.ask-custom {
  margin-bottom: 10px;
}

.ask-input {
  width: 100%;
  border: 1px solid var(--border-strong, #c3aa83);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  background: var(--bg-surface, #ffffff);
  color: var(--text-strong, #0c1c3c);
  box-sizing: border-box;
}

.ask-input::placeholder {
  color: var(--text-muted, #3e70a8);
  opacity: 1;
}

.ask-input:focus {
  outline: none;
  border-color: var(--accent-primary, #1265c8);
  box-shadow: 0 0 0 2px rgba(35, 143, 127, 0.18);
}

.ask-input:disabled {
  opacity: 0.5;
}

.ask-actions {
  display: flex;
  justify-content: flex-end;
}

.ask-submit {
  padding: 7px 18px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  background: var(--accent-primary, #1265c8);
  color: #ffffff;
  border: 1px solid var(--accent-primary, #1265c8);
  transition: all 0.15s;
}

.ask-submit:hover:not(:disabled) {
  filter: brightness(0.92);
}

.ask-submit:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ask-submit:active:not(:disabled) {
  transform: scale(0.96);
}

/* Dark mode */
.dark .ask-user-card {
  background: var(--surface-ai, #163d71);
  border-color: var(--border-soft, #1e518e);
}

.dark .ask-chip {
  background: var(--bg-surface, #102c55);
  color: var(--text-strong, #f0f5fb);
  border-color: var(--border-strong, #1e518e);
}

.dark .ask-chip:hover:not(:disabled):not(.selected) {
  background: var(--bg-elev, #163d71);
}

.dark .chip-num {
  background: var(--border-soft, #1e518e);
}

.dark .ask-input {
  background: var(--bg-surface, #102c55);
  color: var(--text-strong, #f0f5fb);
  border-color: var(--border-strong, #1e518e);
}

.dark .ask-input::placeholder {
  color: var(--text-muted, #8eb3d8);
}
</style>
