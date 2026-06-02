<template>
  <div class="multi-question-card">
    <!-- Loading state -->
    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner">
        <div class="spinner"></div>
      </div>
      <div class="loading-text">Memuat pertanyaan...</div>
    </div>

    <!-- Questions (only show when not loading) -->
    <template v-else>
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
              done: hasAnswerForQuestion(q),
              active: i === currentIndex,
            }"
          />
        </div>
      </div>

      <div v-if="currentQuestion" class="question-row">
        <div class="question-label">
          {{ currentIndex + 1 }}. {{ currentQuestion.label }}
          <span v-if="currentQuestion.required" class="text-red-500 ml-1" title="Required">*</span>
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

      <!-- Validation error message -->
      <div v-if="validationError" class="px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 text-red-800 dark:text-red-200 text-sm">
        ⚠️ {{ validationError }}
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
          :disabled="!hasCurrentAnswer || submitting"
          @click="submit"
        >{{ submitting ? 'Mengirim…' : 'Kirim' }}</button>
      </div>

      <p class="hint">
        Tekan <kbd>Enter</kbd> untuk lanjut ke pertanyaan berikutnya (atau kirim jika di pertanyaan terakhir).
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, reactive, computed, watch, onMounted } from 'vue'
import type { MultiQuestionCardProps, MultiQuestionCardEmits, Question, MultiQuestionAnswer } from '../types/components'

const props = withDefaults(defineProps<MultiQuestionCardProps>(), {
  isLoading: false
})
const emit = defineEmits<MultiQuestionCardEmits>()

const answers = reactive<Record<string, string>>({})
const customAnswers = reactive<Record<string, string>>({})
const submitting = ref<boolean>(false)
const currentIndex = ref<number>(0)
const validationError = ref<string>('')

// localStorage key for draft persistence
const STORAGE_KEY = 'papergenerator_multiquestion_draft'
const DRAFT_EXPIRY_MS = 60 * 60 * 1000 // 1 hour

// Generate a stable key for this question set
const questionSetKey = computed(() => {
  return props.questions.map(q => q.key).join('|')
})

const currentQuestion = computed<Question | null>(() => props.questions[currentIndex.value] || null)
const isLast = computed<boolean>(() => currentIndex.value >= props.questions.length - 1)

function customOptionFor(question: Question | null): { value: string; label: string } | null {
  if (!question) return null
  return (question.options || []).find(o => {
    const label = String(o.label || '').trim().toLowerCase()
    return label === 'ceritakan sendiri...' || label === 'ceritakan sendiri'
  }) || null
}

function hasAnswerForQuestion(question: Question | null): boolean {
  if (!question) return false
  const selected = answers[question.key]
  if (!selected || !String(selected).trim()) return false

  const customOption = customOptionFor(question)
  if (customOption && selected === customOption.value) {
    return !!customAnswers[question.key]?.trim()
  }

  return true
}

const hasCurrentAnswer = computed<boolean>(() => {
  return hasAnswerForQuestion(currentQuestion.value)
})
const hasAnyAnswer = computed<boolean>(() =>
  props.questions.some(q => hasAnswerForQuestion(q))
)

function setAnswer(key: string, value: string): void {
  const q = props.questions.find(question => question.key === key) || null
  const customOption = customOptionFor(q)
  answers[key] = value
  if (!customOption || value !== customOption.value) {
    customAnswers[key] = ''
  }
  validationError.value = '' // Clear error when user provides answer
  saveDraft()
}

function onCustomInput(key: string): void {
  const v = customAnswers[key]
  const q = props.questions.find(question => question.key === key) || null
  const customOption = customOptionFor(q)
  if (v && v.trim()) {
    answers[key] = customOption ? customOption.value : v.trim()
    validationError.value = '' // Clear error when user provides answer
  } else if (!v) {
    if (customOption && answers[key] === customOption.value) {
      delete answers[key]
    }
    else {
    delete answers[key]
    }
  }
  saveDraft()
}

function next(): void {
  if (!hasCurrentAnswer.value) return
  if (currentIndex.value < props.questions.length - 1) {
    currentIndex.value += 1
  }
}

function prev(): void {
  if (currentIndex.value > 0) currentIndex.value -= 1
}

function onEnterAdvance(): void {
  if (!hasCurrentAnswer.value) return
  if (isLast.value) submit()
  else next()
}

async function submit(): Promise<void> {
  if (!hasCurrentAnswer.value || submitting.value) return
  
  // Validate required fields
  const missingRequired = props.questions.filter(q => q.required && !hasAnswerForQuestion(q))
  if (missingRequired.length > 0) {
    validationError.value = `Mohon jawab pertanyaan wajib: ${missingRequired.map(q => q.label).join(', ')}`
    // Jump to first missing required question
    const firstMissingIdx = props.questions.findIndex(q => q.required && !hasAnswerForQuestion(q))
    if (firstMissingIdx >= 0) {
      currentIndex.value = firstMissingIdx
    }
    return
  }
  
  validationError.value = ''
  submitting.value = true
  const payload: MultiQuestionAnswer[] = props.questions
    .filter(q => hasAnswerForQuestion(q))
    .map(q => {
      const v = answers[q.key]
      const opt = (q.options || []).find(o => o.value === v)
      // Submit the human-readable label so the chat shows the full text
      // (e.g. "Masih ide/konsep") instead of the bare code ("A"). Free-text
      // answers come from the custom input and have no matching option, so we
      // keep them verbatim.
      let value = opt ? opt.label : v
      // Guard: if the user tapped the "Ceritakan sendiri..." chip, prefer any
      // text they typed; never submit the placeholder label itself.
      if (opt && opt.label === 'Ceritakan sendiri...') {
        const typed = customAnswers[q.key]
        value = (typed && typed.trim()) || v
      }
      return { key: q.key, value }
    })
  emit('multi-question-submit', payload)
  // Clear draft after successful submission
  clearDraft()
}

// Save current answers to localStorage
function saveDraft(): void {
  try {
    const draft = {
      questionSetKey: questionSetKey.value,
      answers: { ...answers },
      customAnswers: { ...customAnswers },
      currentIndex: currentIndex.value,
      timestamp: Date.now(),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft))
  } catch (e) {
    console.warn('Failed to save draft to localStorage:', e)
  }
}

// Load saved answers from localStorage
function loadDraft(): void {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return

    const draft = JSON.parse(stored)

    // Validate draft is for the same question set
    if (draft.questionSetKey !== questionSetKey.value) {
      clearDraft()
      return
    }

    // Check if draft is not expired
    const age = Date.now() - (draft.timestamp || 0)
    if (age > DRAFT_EXPIRY_MS) {
      clearDraft()
      return
    }

    // Restore answers
    if (draft.answers) {
      Object.assign(answers, draft.answers)
    }
    if (draft.customAnswers) {
      Object.assign(customAnswers, draft.customAnswers)
    }
    if (typeof draft.currentIndex === 'number') {
      currentIndex.value = draft.currentIndex
    }
  } catch (e) {
    console.warn('Failed to load draft from localStorage:', e)
    clearDraft()
  }
}

// Clear saved draft
function clearDraft(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch (e) {
    console.warn('Failed to clear draft from localStorage:', e)
  }
}

// Watch for navigation changes to save progress
watch(currentIndex, () => {
  saveDraft()
})

onMounted(() => {
  loadDraft()
})
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
.dark .custom-input {
  background: #18232b;
  color: #f5f3ee;
  border-color: rgba(227, 236, 239, 0.18);
}
.dark .custom-input::placeholder {
  color: #9db7d3;
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
.dark .btn-secondary {
  background: #18232b;
  color: #f5f3ee;
  border-color: rgba(227, 236, 239, 0.18);
}
.dark .btn-secondary:hover:not(:disabled) {
  background: #20303a;
}
.hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-muted, #6b7280);
}
.dark .hint {
  color: #9db7d3;
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
.dark .hint kbd {
  background: #20303a;
  border-color: rgba(227, 236, 239, 0.18);
  color: #f5f3ee;
}

/* Loading state */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  min-height: 200px;
}
.loading-spinner {
  margin-bottom: 16px;
}
.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-soft, #e5e7eb);
  border-top-color: var(--accent, #2563eb);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.loading-text {
  font-size: 14px;
  color: var(--text-muted, #6b7280);
  font-weight: 500;
}
</style>
