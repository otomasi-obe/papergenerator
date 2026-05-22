<template>
  <div class="multi-question-card">
    <div class="header">
      <span class="header-icon">📋</span>
      <span class="header-title">{{ questions.length }} pertanyaan singkat</span>
    </div>
    <div
      v-for="(q, idx) in questions"
      :key="q.key"
      class="question-row"
      :class="{ answered: !!answers[q.key] }"
    >
      <div class="question-label">{{ idx + 1 }}. {{ q.label }}</div>
      <div class="chips">
        <button
          v-for="opt in (q.options || [])"
          :key="opt.value"
          type="button"
          class="chip"
          :class="{ selected: answers[q.key] === opt.value }"
          @click="setAnswer(q.key, opt.value)"
        >{{ opt.label }}</button>
      </div>
      <input
        v-model="customAnswers[q.key]"
        class="custom-input"
        :placeholder="`Atau ketik jawaban sendiri…`"
        @input="onCustomInput(q.key)"
      />
      <span v-if="answers[q.key]" class="check" aria-label="answered">✓</span>
    </div>
    <button
      type="button"
      class="submit"
      :disabled="!hasAnyAnswer || submitting"
      @click="submit"
    >
      {{ submitting ? 'Mengirim…' : 'Kirim jawaban' }}
    </button>
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
  margin: 8px 0;
}
.header {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 13px;
  color: var(--text-soft, #6b7280);
  margin-bottom: 8px;
}
.header-icon { font-size: 14px; }
.question-row {
  padding: 10px 0;
  border-top: 1px solid var(--border-soft, #f3f4f6);
  position: relative;
}
.question-row:first-of-type { border-top: 0; }
.question-row.answered { opacity: 0.85; }
.question-label {
  font-weight: 500;
  margin-bottom: 6px;
  font-size: 14px;
  color: var(--text-strong, inherit);
  padding-right: 18px;
}
.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.chip {
  padding: 4px 10px;
  border: 1px solid var(--border-strong, #d1d5db);
  border-radius: 16px;
  background: white;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  color: inherit;
}
.chip:hover { background: #f3f4f6; }
.chip.selected {
  background: #2563eb;
  color: white;
  border-color: #2563eb;
}
.custom-input {
  width: 100%;
  border: 1px solid var(--border-strong, #d1d5db);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 13px;
  background: white;
  color: inherit;
  box-sizing: border-box;
}
.custom-input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15);
}
.check {
  position: absolute;
  right: 4px;
  top: 10px;
  color: #16a34a;
  font-weight: 600;
}
.submit {
  margin-top: 12px;
  width: 100%;
  padding: 8px;
  border-radius: 6px;
  background: #2563eb;
  color: white;
  border: none;
  font-weight: 500;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.15s;
}
.submit:hover:not(:disabled) { background: #1d4ed8; }
.submit:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}

:global(html.dark) .multi-question-card {
  background: var(--surface-ai, #2a2825);
  border-color: var(--border-soft, #3f3c35);
}
:global(html.dark) .chip {
  background: #2a2825;
  border-color: #3f3c35;
  color: #eddbac;
}
:global(html.dark) .chip:hover { background: #3a3833; }
:global(html.dark) .custom-input {
  background: #2a2825;
  border-color: #3f3c35;
  color: #eddbac;
}
:global(html.dark) .question-row { border-top-color: #3f3c35; }
</style>
