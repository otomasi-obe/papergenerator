<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <AppHeader />
    <main class="max-w-6xl mx-auto px-4 py-8">
      <div class="mb-8">
        <button
          @click="router.push('/tokens/checkout')"
          class="text-sm text-ink-500 dark:text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 mb-4 flex items-center gap-1"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
          Kembali ke Metode Pembayaran
        </button>
        <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">Pembayaran {{ method === 'qris' ? 'QRIS' : 'Virtual Account' }}</h1>
        <p class="text-ink-600 dark:text-ink-300 text-sm mt-1">
          {{ method === 'qris' ? 'Scan QR code untuk menyelesaikan pembayaran' : 'Transfer ke nomor rekening virtual' }}
        </p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Left: Order Summary -->
        <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6 h-fit">
          <h3 class="text-lg font-bold text-ink-900 dark:text-ink-50 mb-4">Detail Pesanan</h3>
          <div class="space-y-3">
            <div class="flex justify-between py-2 border-b border-cream-200 dark:border-ash-700">
              <span class="text-ink-600 dark:text-ink-300">Paket</span>
              <span class="font-medium text-ink-900 dark:text-ink-50">{{ packageName }}</span>
            </div>
            <div class="flex justify-between py-2 border-b border-cream-200 dark:border-ash-700">
              <span class="text-ink-600 dark:text-ink-300">Token</span>
              <span class="font-medium text-ink-900 dark:text-ink-50">{{ tokens }}</span>
            </div>
            <div class="flex justify-between py-2 border-b border-cream-200 dark:border-ash-700">
              <span class="text-ink-600 dark:text-ink-300">Metode</span>
              <span class="font-medium text-ink-900 dark:text-ink-50">{{ method === 'qris' ? 'QRIS' : 'Virtual Account' }}</span>
            </div>
            <div class="flex justify-between py-3 mt-2">
              <span class="font-bold text-ink-900 dark:text-ink-50">Total</span>
              <span class="font-bold text-lg text-ink-900 dark:text-ink-50">{{ formatIDR(amount) }}</span>
            </div>
          </div>
          <button v-if="!paymentData" @click="generatePayment" :disabled="loading"
            class="w-full mt-6 py-3 bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all hover:shadow-md active:scale-95">
            {{ loading ? 'Memproses...' : 'Bayar Sekarang' }}
          </button>
        </div>

        <!-- Right: Payment Display -->
        <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
          <h3 class="text-lg font-bold text-ink-900 dark:text-ink-50 mb-4 text-center">
            {{ method === 'qris' ? 'QRIS Code' : 'Virtual Account' }}
          </h3>

          <!-- Loading -->
          <div v-if="loading" class="flex flex-col items-center justify-center py-12">
            <div class="w-12 h-12 border-4 border-cream-300 dark:border-ash-600 border-t-[var(--accent)] rounded-full animate-spin"></div>
            <p class="text-ink-500 dark:text-ink-400 text-sm mt-4">Membuat pembayaran...</p>
          </div>

          <!-- QRIS Display (iPaymu) -->
          <div v-if="paymentData && method === 'qris'" class="text-center">
            <div class="bg-white rounded-xl p-4 inline-block mb-4">
              <img v-if="paymentData.qr_image" :src="paymentData.qr_image" alt="QRIS" class="w-60 h-60 mx-auto" />
              <canvas v-else ref="qrCanvasRef" width="240" height="240" class="w-60 h-60 mx-auto"></canvas>
            </div>
            <div class="bg-amber-50 dark:bg-amber-900/20 rounded-lg px-4 py-3 mb-4">
              <div class="flex justify-between items-center">
                <span class="text-amber-700 dark:text-amber-300 text-sm font-medium">Bayar sebelum:</span>
                <span class="text-amber-700 dark:text-amber-300 font-bold text-lg">{{ countdown }}</span>
              </div>
            </div>
            <div class="text-sm text-ink-600 dark:text-ink-300 space-y-1 mb-4">
              <div class="flex justify-between"><span>Amount:</span><span class="font-medium text-ink-900 dark:text-ink-50">{{ formatIDR(paymentData.amount || amount) }}</span></div>
              <div v-if="paymentData.transaction_id" class="flex justify-between"><span>ID:</span><span class="font-mono text-xs text-ink-700 dark:text-ink-300">{{ paymentData.transaction_id.slice(0, 24) }}</span></div>
            </div>
            <a v-if="paymentData.payment_url" :href="paymentData.payment_url" target="_blank" rel="noopener"
              class="block w-full py-2 text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 rounded-lg transition-all active:scale-95 mb-2 text-center">
              Buka di Halaman iPaymu ↗
            </a>
            <div class="flex gap-2 mt-2">
              <button @click="copyPaymentUrl" class="flex-1 py-2 text-xs font-medium text-white bg-slate-600 hover:bg-slate-500 active:bg-slate-700 rounded-lg transition-all active:scale-95">
                {{ copied ? '✓ Copied!' : 'Copy Link' }}
              </button>
              <button @click="cancelPayment" class="flex-1 py-2 text-xs font-medium text-white bg-red-600 hover:bg-red-500 active:bg-red-700 rounded-lg transition-all active:scale-95">Batal</button>
            </div>
          </div>

          <!-- VA Display -->
          <div v-if="paymentData && method === 'va'" class="text-center">
            <div class="bg-white dark:bg-ash-700 rounded-xl p-6 mb-4">
              <div class="w-16 h-16 rounded-xl flex items-center justify-center mx-auto mb-3 font-black text-lg bg-slate-500 text-white">VA</div>
              <p class="text-xs text-ink-500 dark:text-ink-400 mb-1">Nomor Virtual Account</p>
              <p class="text-2xl font-mono font-bold tracking-wider text-ink-900 dark:text-ink-50 select-all">{{ paymentData.payment_no || '000000' }}</p>
            </div>
            <div class="bg-cyan-50 dark:bg-cyan-900/20 rounded-lg px-4 py-3 mb-4">
              <div class="flex items-center justify-center gap-2">
                <div class="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></div>
                <span class="text-cyan-700 dark:text-cyan-300 text-sm font-medium">Menunggu Pembayaran</span>
              </div>
            </div>
            <div class="bg-amber-50 dark:bg-amber-900/20 rounded-lg px-4 py-3 mb-4">
              <div class="flex justify-between items-center">
                <span class="text-amber-700 dark:text-amber-300 text-sm font-medium">Bayar sebelum:</span>
                <span class="text-amber-700 dark:text-amber-300 font-bold text-lg">{{ countdown }}</span>
              </div>
            </div>
            <div class="text-sm text-ink-600 dark:text-ink-300 space-y-1 mb-4">
              <div class="flex justify-between"><span>Amount:</span><span class="font-medium text-ink-900 dark:text-ink-50">{{ formatIDR(paymentData.amount || amount) }}</span></div>
            </div>
            <a v-if="paymentData.payment_url" :href="paymentData.payment_url" target="_blank" rel="noopener"
              class="block w-full py-2 text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 rounded-lg transition-all active:scale-95 mb-2 text-center">
              Buka Halaman Pembayaran ↗
            </a>
            <div class="flex gap-2 mt-4">
              <button @click="copyPaymentUrl" class="flex-1 py-2 text-xs font-medium text-white bg-slate-600 hover:bg-slate-500 active:bg-slate-700 rounded-lg transition-all active:scale-95">
                {{ copied ? '✓ Copied!' : 'Copy Link' }}
              </button>
              <button @click="cancelPayment" class="flex-1 py-2 text-xs font-medium text-white bg-red-600 hover:bg-red-500 active:bg-red-700 rounded-lg transition-all active:scale-95">Batal</button>
            </div>
          </div>

          <!-- Error -->
          <div v-if="error" class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 mt-4">
            <p class="text-red-800 dark:text-red-200 text-sm">{{ error }}</p>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import api from '../api/index'
import QRCode from 'qrcode'

const router = useRouter()
const route = useRoute()

interface PaymentData {
  payment_url?: string
  qr_image?: string
  qr_string?: string
  payment_no?: string
  session_id?: string
  amount?: number
  tokens?: number
  description?: string
  transaction_id?: string
  expires_at?: string
}

const loading = ref(false)
const paymentData = ref<PaymentData | null>(null)
const error = ref<string | null>(null)
const copied = ref(false)
const countdown = ref('00:00')
const cancelled = ref(false)
const expired = ref(false)
const expiredTimerId = ref<ReturnType<typeof setTimeout> | null>(null)
const qrCanvasRef = ref<HTMLCanvasElement | null>(null)
let countdownInterval: ReturnType<typeof setInterval> | null = null
let isRegenerating = false

const packageName = ref('')
const tokens = ref(0)
const amount = ref(0)
const method = ref<'qris' | 'va'>('qris')

const pkgNames: Record<string, string> = {
  daily: 'Harian', weekly: 'Mingguan', monthly: 'Bulanan', yearly: 'Tahunan'
}

amount.value = parseInt(route.query.amount as string) || 0
tokens.value = parseInt(route.query.tokens as string) || 0
packageName.value = pkgNames[(route.query.package as string) || ''] || 'Unknown'
method.value = (route.query.method as string) === 'va' ? 'va' : 'qris'

// Fallback: render QR from qr_string if no qr_image
watch(paymentData, async (val) => {
  if (val && method.value === 'qris' && val.qr_string && !val.qr_image) {
    await nextTick()
    if (qrCanvasRef.value) {
      try {
        await QRCode.toDataURL(qrCanvasRef.value, val.qr_string, {
          width: 240,
          margin: 2,
          color: { dark: '#1a1a1a', light: '#ffffff' }
        })
      } catch { /* QR render failed — user can use payment_url instead */ }
    }
  }
})

async function generatePayment() {
  if (!amount.value || amount.value <= 0) {
    error.value = 'Jumlah pembayaran tidak valid. Silakan pilih paket token.'
    loading.value = false
    return
  }
  loading.value = true
  error.value = null
  cancelled.value = false
  paymentData.value = null

  try {
    const endpoint = method.value === 'va' ? '/api/payment/doku/generate-va' : '/api/payment/doku/generate'
    const payload: Record<string, unknown> = {
      amount: amount.value,
      tokens: tokens.value
    }
    if (method.value === 'va') payload.channel = 'VIRTUAL_ACCOUNT_BRI'
    const response = await api.post(endpoint, payload)
    paymentData.value = response.data
    if (response.data.expires_at) {
      startCountdown(new Date(response.data.expires_at))
    }
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { error?: string; message?: string }, status?: number }, message?: string }
    if (axiosErr.response?.data?.error) {
      error.value = axiosErr.response.data.error
    } else if (axiosErr.response?.data?.message) {
      error.value = axiosErr.response.data.message
    } else if (axiosErr.response?.status === 401) {
      error.value = 'Sesi login habis. Silakan login ulang.'
    } else if (axiosErr.response?.status === 502) {
      error.value = 'Server sedang maintenance. Coba lagi dalam beberapa menit.'
    } else {
      error.value = axiosErr.message || 'Gagal menghasilkan kode pembayaran.'
    }
  } finally {
    loading.value = false
  }
}

function startCountdown(expiredAt: Date) {
  clearInterval(countdownInterval!)
  updateCountdown(expiredAt)
  countdownInterval = setInterval(() => updateCountdown(expiredAt), 1000)
}

async function updateCountdown(expiredAt: Date) {
  const now = new Date()
  const diff = expiredAt.getTime() - now.getTime()
  const seconds = Math.max(0, Math.floor(diff / 1000))
  const m = Math.floor(seconds / 60), s = seconds % 60
  countdown.value = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  if (seconds <= 0 && !cancelled.value && !expired.value && !isRegenerating) {
    clearInterval(countdownInterval!)
    expired.value = true
    isRegenerating = true
    countdown.value = '🔄 Regenerate...'
    await new Promise(r => { expiredTimerId.value = setTimeout(r, 1500) })
    if (!cancelled.value) {
      expired.value = false
      isRegenerating = false
      await generatePayment()
    } else {
      isRegenerating = false
    }
  }
}

function clearCountdown() {
  clearInterval(countdownInterval!)
  countdown.value = '00:00'
  if (expiredTimerId.value) {
    clearTimeout(expiredTimerId.value)
    expiredTimerId.value = null
  }
}

async function copyPaymentUrl() {
  if (!paymentData.value?.payment_url) return
  try {
    await navigator.clipboard.writeText(paymentData.value.payment_url)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}

function cancelPayment() {
  cancelled.value = true
  isRegenerating = false
  clearCountdown()
  paymentData.value = null
}

function formatIDR(v: number) {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(v)
}

onUnmounted(() => {
  clearCountdown()
})
</script>