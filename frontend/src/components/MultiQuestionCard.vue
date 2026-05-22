<template>
  <div class="multi-question-card">
    <div class="header">
      <span class="header-icon">📋</span>
      <span class="header-title">
        Pertanyaan {{ currentIndex + 1 }} / {{ questions.length }}
      </span>
      <div class="progress" aria-hidden="true">
        <span
          v-for="(q, i) in questions"
          :key="q.key + ':' + i"
          class="progress-dot"
          :class="{
            done: !!answers[q.key],
            active: i === currentIndex,
          }"
        />
      </div>
    </div>

    <div v-if="currentQuestion" class="question-row">
      <div class="question-label">
        {{ currentIndex + 1 }}. {{ currentQuestion.label }}
      </div>
      <div class="chips">
        <button
          v-for="opt in (currentQuestion.options || [])"
          :key="opt.value"
          type="button"
          class="chip"
          :class="{ selected: answers[currentQuestion.key] === opt.value }"
          @click="setAnswer(currentQuestion.key, opt.value)"
        >{{ opt.label }}</button>
      </div>
      <input
        v-model="customAnswers[currentQuestion.key]"
        class="custom-input"
        :placeholder="`Atau ketik jawaban sendiri…`"
        @input="onCustomInput(currentQuestion.key)"
        @keyup.enter="onEnterAdvance"
      />
    </div>

    <div class="actions">
      <button
        type="button"
        class="btn-secondary"
        :disabled="currentIndex === 0 || submitting"
        @click="prev"
      >← Sebelumnya</button>

      <button
        v-if="!isLast"
        type="button"
        class="btn-primary"
        :disabled="!hasCurrentAnswer || submitting"
        @click="next"
      >Lanjut →</button>

      <button
        v-else
        type="button"
        class="btn-primary"
        :disabled="!hasAnyAnswer || submitting"
        @click="submit"
      >{{ submitting ? 'Mengirim…' : 'Kirim jawaban' }}</button>
    </div>

    <p class="hint">
      Tekan <kbd>Enter</kbd> di kolom jawaban bebas untuk lanjut ke pertanyaan berikutnya.
    </p>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'

const props = defineProps({
  questions: { type: Array, required: true },
})
const emit = defineEmits(['multi-question-submit'])

const answers = reactive({})
const customAnswers = reactive({})
const submitting = ref(false)
const currentIndex = ref(0)

const currentQuestion = computed(() => props.questions[currentIndex.value] || null)
const isLast = computed(() => currentIndex.value >= props.questions.length - 1)
const hasCurrentAnswer = computed(() => {
  const q = currentQuestion.value
  if (!q) return false
  const v = answers[q.key]
  return !!(v && String(v).trim())
})
const hasAnyAnswer = computed(() =>
  Object.values(answers).some(v => v && String(v).trim())
)

function setAnswer(key, value) {
  answers[key] = value
  customAnswers[key] = ''
}

function onCustomInput(key) {
  const v = customAnswers[key]
  if (v && v.trim()) {
    answers[key] = v.trim()
  } else if (!v) {
    delete answers[key]
  }
}

function next() {
  if (!hasCurrentAnswer.value) return
  if (currentIndex.value < props.questions.length - 1) {
    currentIndex.value += 1
  }
}

function prev() {
  if (currentIndex.value > 0) currentIndex.value -= 1
}

function onEnterAdvance() {
  if (!hasCurrentAnswer.value) return
  if (isLast.value) submit()
  else next()
}

async function submit() {
  if (!hasAnyAnswer.value || submitting.value) return
  submitting.value = true
  const payload = props.questions
    .filter(q => answers[q.key])
    .map(q => ({ key: q.key, value: answers[q.key] }))
  emit('multi-question-submit', payload)
}
</script>

<style scoped>
.multi-question-card {
  border: 1px solid var(--border-soft, #e5e7eb);
  border-radius: 8px;
  padding: 12px;
  background: var(--surface-ai, #fafafa);
  color: var(--text-strong, #111);
  margin: 8px 0;
}
.header {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: var(--text-muted, #6b7280);
  margin-bottom: 10px;
}
.header-icon { font-size: 14px; }
.header-title { font-weight: 500; color: var(--text-strong, inherit); }
.progress {
  margin-left: auto;
  display: inline-flex;
  gap: 4px;
}
.progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border-soft, #d1d5db);
  transition: background 0.15s, transform 0.15s;
}
.progress-dot.done {
  background: #16a34a;
}
.progress-dot.active {
  background: var(--accent, #2563eb);
  transform: scale(1.25);
}
.question-row {
  padding: 6px 0 10px;
  position: relative;
}
.question-label {
  font-weight: 500;
  margin-bottom: 8px;
  font-size: 14px;
  color: var(--text-strong, inherit);
  line-height: 1.45;
}
.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.chip {
  padding: 5px 12px;
  border: 1px solid var(--border-strong, #d1d5db);
  border-radius: 16px;
  background: var(--bg-surface, #ffffff);
  color: var(--text-strong, #111);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.chip:hover { background: var(--bg-elev, #f3f4f6); }
.chip.selected {
  background: var(--accent, #2563eb);
  color: #ffffff;
  border-color: var(--accent, #2563eb);
}
.custom-input {
  width: 100%;
  border: 1px solid var(--border-strong, #d1d5db);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  background: var(--bg-surface, #ffffff);
  color: var(--text-strong, #111);
  box-sizing: border-box;
}
.custom-input::placeholder {
  color: var(--text-muted, #9ca3af);
  opacity: 1;
}
.custom-input:focus {
  outline: none;
  border-color: var(--accent, #2563eb);
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.18);
}
.actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.btn-primary,
.btn-secondary {
  padding: 7px 14px;
  border-radius: 6px;
  font-weight: 500;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s, opacity 0.15s;
}
.btn-primary {
  background: var(--accent, #2563eb);
  color: #ffffff;
  border: 1px solid var(--accent, #2563eb);
  margin-left: auto;
}
.btn-primary:hover:not(:disabled) {
  filter: brightness(0.95);
}
.btn-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.btn-secondary {
  background: var(--bg-surface, #ffffff);
  color: var(--text-strong, #111);
  border: 1px solid var(--border-strong, #d1d5db);
}
.btn-secondary:hover:not(:disabled) {
  background: var(--bg-elev, #f3f4f6);
}
.btn-secondary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-muted, #6b7280);
}
.hint kbd {
  background: var(--bg-elev, #f3f4f6);
  border: 1px solid var(--border-soft, #e5e7eb);
  border-radius: 3px;
  padding: 0 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
  color: var(--text-strong, inherit);
}
</style>
