<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <AppHeader />

    <main class="max-w-6xl mx-auto px-4 py-8">
      <div class="mb-8">
        <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">
          QRIS Payment Testing
        </h1>
        <p class="text-ink-600 dark:text-ink-300 text-sm mt-1">
          Generate and test QRIS payment codes
        </p>
      </div>

      <!-- Two Column Layout -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Left: Form -->
        <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6 h-fit">
          <form @submit.prevent="generateQRIS" class="space-y-4">
            <!-- Amount Input -->
            <div>
              <label for="amount" class="block text-sm font-medium text-ink-700 dark:text-ink-200 mb-2">
                Amount (IDR)
              </label>
              <input
                id="amount"
                v-model.number="form.amount"
                type="number"
                min="1000"
                step="1000"
                required
                placeholder="50000"
                class="w-full px-4 py-2.5 rounded-xl border border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-900 text-ink-900 dark:text-ink-50 focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
              <p class="text-xs text-ink-500 dark:text-ink-400 mt-1">
                Minimum: Rp 1,000
              </p>
            </div>

            <!-- Description Input -->
            <div>
              <label for="description" class="block text-sm font-medium text-ink-700 dark:text-ink-200 mb-2">
                Description (Optional)
              </label>
              <input
                id="description"
                v-model="form.description"
                type="text"
                placeholder="Paper generation service"
                class="w-full px-4 py-2.5 rounded-xl border border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-900 text-ink-900 dark:text-ink-50 focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            </div>

            <!-- Generate Button -->
            <button
              type="submit"
              :disabled="loading"
              class="w-full px-4 py-3 bg-[var(--accent)] text-cream-50 rounded-xl font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
            >
              <span v-if="loading" class="flex items-center justify-center gap-2">
                <div class="w-4 h-4 border-2 border-cream-50/30 border-t-cream-50 rounded-full animate-spin"></div>
                Generating...
              </span>
              <span v-else>Generate QRIS Code</span>
            </button>
          </form>
        </div>

        <!-- Right: QRIS Display -->
        <div v-if="qrisData" class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
          <h3 class="font-semibold text-ink-700 dark:text-ink-200 mb-4">
            QRIS Code
          </h3>

          <!-- QR Code Image (smaller) -->
          <div class="flex flex-col items-center justify-center space-y-4">
            <div v-if="qrisData.qr_image" class="bg-white p-3 rounded-xl shadow-sm">
              <img
                :src="qrisData.qr_image"
                alt="QRIS Code"
                class="w-48 h-48 object-contain"
              />
            </div>
            
            <div v-else class="w-48 h-48 bg-cream-100 dark:bg-ash-900 rounded-xl flex items-center justify-center border-2 border-dashed border-cream-300 dark:border-ash-700">
              <p class="text-ink-400 dark:text-ink-500 text-xs">QR Code will appear here</p>
            </div>

            <!-- Payment Details (compact) -->
            <div class="w-full space-y-2 text-xs">
              <div class="flex justify-between py-1.5 border-b border-cream-200 dark:border-ash-700">
                <span class="text-ink-600 dark:text-ink-400">Amount:</span>
                <span class="font-semibold text-ink-900 dark:text-ink-50">
                  {{ formatIDR(qrisData.amount) }}
                </span>
              </div>
              
              <div v-if="qrisData.description" class="flex justify-between py-1.5 border-b border-cream-200 dark:border-ash-700">
                <span class="text-ink-600 dark:text-ink-400">Desc:</span>
                <span class="text-ink-900 dark:text-ink-50 truncate text-right ml-2">{{ qrisData.description }}</span>
              </div>
              
              <div v-if="qrisData.transaction_id" class="flex justify-between py-1.5 border-b border-cream-200 dark:border-ash-700">
                <span class="text-ink-600 dark:text-ink-400">TXN ID:</span>
                <span class="font-mono text-ink-900 dark:text-ink-50 truncate text-right ml-2">{{ qrisData.transaction_id }}</span>
              </div>

              <!-- Expiry Timer -->
              <div v-if="qrisData.expired_at" class="flex justify-between py-1.5 border-b border-cream-200 dark:border-ash-700">
                <span class="text-ink-600 dark:text-ink-400">Expires:</span>
                <span class="text-ink-900 dark:text-ink-50">{{ formatDate(qrisData.expired_at) }}</span>
              </div>

              <!-- Countdown Timer -->
              <div v-if="qrisData.expired_at" class="flex justify-between items-center py-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3">
                <span class="text-amber-700 dark:text-amber-300 text-xs font-medium">Countdown:</span>
                <div class="flex items-center gap-2">
                  <span class="text-xl font-mono tabular-nums font-bold text-amber-800 dark:text-amber-200">{{ countdown }}</span>
                  <span class="text-xs text-amber-600 dark:text-amber-400">seconds</span>
                </div>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex gap-2 mt-4">
              <button
                @click="copyQRISString"
                class="flex-1 py-2 text-xs font-medium text-white transition-colors bg-ink-600 dark:bg-ink-700 rounded-lg hover:bg-ink-700 dark:hover:bg-ink-600"
              >
                {{ copied ? '✓ Copied!' : 'Copy QRIS String' }}
              </button>
              <button
                @click="cancelPayment"
                class="flex-1 py-2 text-xs font-medium text-white transition-colors bg-red-600 rounded-lg hover:bg-red-700"
              >
                Cancel Payment
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Error Display -->
      <div v-if="error" class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 mt-4">
        <p class="text-red-800 dark:text-red-200 text-sm">
          {{ error }}
        </p>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import AppHeader from '../components/AppHeader.vue'
import api from '../api/index'

interface QRISData {
  qr_image?: string
  qr_string?: string
  amount: number
  description?: string
  transaction_id?: string
  expired_at?: string
}

const form = ref({
  amount: 50000,
  description: ''
})

const loading = ref(false)
const qrisData = ref<QRISData | null>(null)
const error = ref<string | null>(null)
const copied = ref(false)
const countdown = ref('00:00')
const cancelled = ref(false)
let countdownInterval: ReturnType<typeof setInterval> | null = null

async function generateQRIS() {
  loading.value = true
  error.value = null
  
  try {
    const response = await api.post('/api/payment/doku/generate', {
      amount: form.value.amount,
      payment_method: 'qris'
    })

    qrisData.value = response.data
    startCountdown(new Date(response.data.expires_at))
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Failed to generate QRIS'
  } finally {
    loading.value = false
  }
}

function startCountdown(expiredAt: Date) {
  clearInterval(countdownInterval!)
  updateCountdown(expiredAt)
  countdownInterval = setInterval(() => {
    updateCountdown(expiredAt)
  }, 1000)
}

function updateCountdown(expiredAt: Date) {
  const now = new Date()
  const diff = expiredAt.getTime() - now.getTime()
  const totalSeconds = Math.max(0, Math.floor(diff / 1000))
  
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  countdown.value = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  
  if (totalSeconds <= 0 && !cancelled.value) {
    clearInterval(countdownInterval!)
    // Auto-regenerate QRIS when expired
    generateQRIS()
  } else if (totalSeconds <= 0) {
    clearInterval(countdownInterval!)
  }
}

function formatIDR(amount: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0
  }).format(amount)
}

function cancelPayment() {
  cancelled.value = true
  clearInterval(countdownInterval!)
  qrisData.value = null
  form.value = { amount: 50000, description: '' }
  countdown.value = '00:00'
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short'
  })
}

async function copyQRISString() {
  if (!qrisData.value?.qr_string) return
  
  try {
    await navigator.clipboard.writeText(qrisData.value.qr_string)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Fallback silent fail
  }
}

onUnmounted(() => {
  clearInterval(countdownInterval!)
})
</script>
