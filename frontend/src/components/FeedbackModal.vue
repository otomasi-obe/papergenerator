<template>
  <Teleport to="body">
    <div v-if="isOpen" class="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" @click.self="$emit('close')">
      <div class="w-full max-w-md bg-white dark:bg-ash-800 rounded-2xl border border-cream-300 dark:border-ash-700 shadow-xl overflow-hidden">
        <!-- Header -->
        <div class="px-5 py-4 border-b border-cream-200 dark:border-ash-700 flex items-center justify-between">
          <h3 class="font-semibold text-ink-900 dark:text-ink-50 flex items-center gap-2">
            <span aria-hidden="true">💬</span> Kritik & Saran
          </h3>
          <button @click="$emit('close')" class="p-1.5 rounded-lg hover:bg-cream-100 dark:hover:bg-ash-700 transition" aria-label="Close">
            <svg class="w-5 h-5 text-ink-500 dark:text-ink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <!-- Body -->
        <div class="p-5 space-y-4">
          <p class="text-sm text-ink-600 dark:text-ink-300">
            Sampaikan kritik, saran, atau laporan bug. Kami akan meninjau di Dev Room.
          </p>

          <div v-if="error" class="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
            {{ error }}
          </div>

          <div v-if="success" class="p-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 text-sm">
            ✅ Terima kasih! Feedback Anda telah terkirim.
          </div>

          <textarea
            v-model="message"
            rows="5"
            maxlength="2000"
            placeholder="Tulis kritik atau saran Anda di sini..."
            class="w-full px-3 py-2 text-sm border border-cream-300 dark:border-ash-700 rounded-lg bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-100 focus:outline-none focus:ring-2 focus:ring-[#238f7f] resize-none"
            :disabled="loading"
          ></textarea>

          <div class="flex items-center justify-between text-xs text-ink-500 dark:text-ink-400">
            <span>{{ message.length }} / 2000</span>
            <button
              @click="submit"
              :disabled="loading || !message.trim()"
              class="px-4 py-2 text-sm rounded-lg bg-[var(--accent)] text-cream-50 hover:opacity-90 disabled:opacity-50 transition flex items-center gap-1.5"
            >
              <span v-if="loading" class="animate-spin h-4 w-4 border-2 border-cream-200 border-t-cream-50 rounded-full"></span>
              <span>{{ loading ? 'Mengirim...' : 'Kirim' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '../api/index.js'

defineProps<{ isOpen: boolean }>()
defineEmits<{ close: [] }>()

const message = ref('')
const loading = ref(false)
const error = ref('')
const success = ref(false)

async function submit() {
  error.value = ''
  success.value = false
  if (!message.value.trim()) {
    error.value = 'Pesan tidak boleh kosong'
    return
  }
  loading.value = true
  try {
    const res = await api.post('/api/feedback', { message: message.value.trim() })
    if (res.data?.success) {
      success.value = true
      message.value = ''
      setTimeout(() => {
        success.value = false
        // emit close after 1.5s
      }, 1500)
    } else {
      error.value = res.data?.error || 'Gagal mengirim feedback'
    }
  } catch (e: any) {
    error.value = e.response?.data?.error || 'Terjadi kesalahan'
  } finally {
    loading.value = false
  }
}
</script>
