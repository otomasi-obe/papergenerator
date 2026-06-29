<template>
  <!-- Math CAPTCHA widget -->
  <div v-if="captchaRequired" class="captcha-widget">
    <div class="captcha-question text-sm text-cream-200/80 mb-2">
      {{ question || 'Loading...' }}
    </div>
    <div class="flex gap-2 items-center">
      <input
        ref="answerInput"
        v-model="answer"
        type="text"
        :placeholder="'Your answer'"
        class="flex-1 px-3 py-2 bg-cream-50/10 border border-cream-300/40 rounded-lg text-cream-50 placeholder-cream-300/60 text-sm focus:outline-none focus:border-navy-500 focus:ring-1 focus:ring-[#238f7f]/30"
        @keyup.enter="refresh"
      />
      <button
        type="button"
        @click="refresh"
        :disabled="loading"
        class="px-3 py-2 text-sm text-cream-200/80 hover:text-cream-50 transition-colors disabled:opacity-50"
        :title="'Refresh CAPTCHA'"
      >
        <svg class="w-5 h-5" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      </button>
    </div>
    <div v-if="error" class="text-red-400 text-xs mt-1">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api/index.js'

const props = defineProps<{
  required?: boolean
}>()

const emit = defineEmits<{
  solved: [captchaId: string, answer: string]
  unsolved: []
}>()

const captchaRequired = ref(props.required !== false)
const question = ref('')
const answer = ref('')
const captchaId = ref('')
const error = ref('')
const loading = ref(false)
const answerInput = ref<HTMLInputElement | null>(null)

async function loadCaptcha() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get('/api/auth/captcha/generate')
    const data = res.data
    if (!data.captcha_required) {
      captchaRequired.value = false
      return
    }
    captchaId.value = data.captcha_id
    question.value = data.question
    answer.value = ''
  } catch {
    error.value = 'Failed to load CAPTCHA. Refresh to retry.'
  } finally {
    loading.value = false
  }
}

async function verify() {
  if (!answer.value.trim()) return false
  try {
    const res = await api.post('/api/auth/captcha/verify', {
      captcha_id: captchaId.value,
      answer: answer.value.trim(),
    })
    if (res.data.valid) {
      error.value = ''
      emit('solved', captchaId.value, answer.value.trim())
      return true
    } else {
      error.value = 'Incorrect answer. Try again.'
      answer.value = ''
      answerInput.value?.focus()
      return false
    }
  } catch {
    error.value = 'Verification failed. Refresh CAPTCHA.'
    return false
  }
}

async function refresh() {
  await loadCaptcha()
}

// Expose for parent component
defineExpose({ loadCaptcha, verify, answer, captchaId })

onMounted(() => {
  if (captchaRequired.value) {
    loadCaptcha()
  }
})
</script>
