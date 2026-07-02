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

      <!-- VA Bank Selection -->
      <div v-if="method === 'va' && !paymentData" class="mb-6">
        <h3 class="text-sm font-bold text-ink-700 dark:text-ink-300 mb-3">Pilih Bank</h3>
        <div class="grid grid-cols-3 sm:grid-cols-6 gap-3">
          <button v-for="bank in banks" :key="bank.code" @click="selectedBank = bank.code"
            :class="['cursor-pointer rounded-xl border-2 p-3 flex flex-col items-center gap-1 transition-all hover:shadow-sm',
              selectedBank === bank.code ? 'border-[var(--accent)] bg-cream-100 dark:bg-ash-700' : 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 hover:border-[var(--accent)]']">
            <div :class="['w-10 h-10 rounded-lg flex items-center justify-center font-bold text-xs', bank.color]">{{ bank.short }}</div>
            <span class="text-xs font-medium text-ink-700 dark:text-ink-300">{{ bank.name }}</span>
          </button>
        </div>
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
              <span class="font-medium text-ink-900 dark:text-ink-50">{{ method === 'qris' ? 'QRIS' : 'VA - ' + (selectedBank?.toUpperCase() || '') }}</span>
            </div>
            <div class="flex justify-between py-3 mt-2">
              <span class="font-bold text-ink-900 dark:text-ink-50">Total</span>
              <span class="font-bold text-lg text-ink-900 dark:text-ink-50">{{ formatIDR(amount) }}</span>
            </div>
          </div>
          <button v-if="!paymentData" @click="generatePayment" :disabled="loading || (method === 'va' && !selectedBank)"
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
            <p class="text-ink-500 dark:text-ink-400 text-sm mt-4">Menghasilkan kode pembayaran...</p>
          </div>

          <!-- QRIS Display -->
          <div v-if="paymentData && method === 'qris'" class="text-center">
            <div class="bg-white rounded-xl p-4 inline-block mb-4">
              <canvas ref="qrCanvasRef" width="240" height="240" class="w-60 h-60"></canvas>
            </div>
            <div class="bg-amber-50 dark:bg-amber-900/20 rounded-lg px-4 py-3 mb-4">
              <div class="flex justify-between items-center">
                <span class="text-amber-700 dark:text-amber-300 text-sm font-medium">Bayar sebelum:</span>
                <span class="text-amber-700 dark:text-amber-300 font-bold text-lg">{{ countdown }}</span>
              </div>
            </div>
            <div class="text-sm text-ink-600 dark:text-ink-300 space-y-1 mb-4">
              <div class="flex justify-between"><span>Amount:</span><span class="font-medium text-ink-900 dark:text-ink-50">{{ formatIDR(paymentData.amount || amount) }}</span></div>
              <div v-if="paymentData.transaction_id" class="flex justify-between"><span>ID:</span><span class="font-mono text-xs text-ink-700 dark:text-ink-300">{{ paymentData.transaction_id.slice(0, 20) }}</span></div>
            </div>
            <div class="flex gap-2 mt-4">
              <button @click="copyPaymentData" class="flex-1 py-2 text-xs font-medium text-white bg-slate-600 hover:bg-slate-500 active:bg-slate-700 rounded-lg transition-all active:scale-95">
                {{ copied ? '✓ Copied!' : 'Copy QR String' }}
              </button>
              <button @click="cancelPayment" class="flex-1 py-2 text-xs font-medium text-white bg-red-600 hover:bg-red-500 active:bg-red-700 rounded-lg transition-all active:scale-95">Batal</button>
            </div>
          </div>

          <!-- VA Display -->
          <div v-if="paymentData && method === 'va'" class="text-center">
            <div class="bg-white dark:bg-ash-700 rounded-xl p-6 mb-4">
              <div :class="['w-16 h-16 rounded-xl flex items-center justify-center mx-auto mb-3 font-black text-lg', getBankColor(selectedBank)]">{{ (selectedBank || 'BANK').toUpperCase() }}</div>
              <p class="text-xs text-ink-500 dark:text-ink-400 mb-1">Nomor Virtual Account</p>
              <p class="text-2xl font-mono font-bold tracking-wider text-ink-900 dark:text-ink-50 select-all">{{ paymentData.account_number || '000000' }}</p>
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
                <span class="text-amber-700 dark:text-amber-300 font-bold">{{ formatDate(paymentData.expires_at) }}</span>
              </div>
            </div>
            <div class="text-sm text-ink-600 dark:text-ink-300 space-y-1 mb-4">
              <div class="flex justify-between"><span>Amount:</span><span class="font-medium text-ink-900 dark:text-ink-50">{{ formatIDR(paymentData.amount || amount) }}</span></div>
            </div>
            <div class="flex gap-2 mt-4">
              <button @click="copyPaymentData" class="flex-1 py-2 text-xs font-medium text-white bg-slate-600 hover:bg-slate-500 active:bg-slate-700 rounded-lg transition-all active:scale-95">
                {{ copied ? '✓ Copied!' : 'Copy No. VA' }}
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
  qr_string?: string
  account_number?: string
  amount?: number
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
const selectedBank = ref('')

const banks = [
  { code: 'bca', name: 'BCA', short: 'BCA', color: 'bg-[#0066B3] text-white' },
  { code: 'bni', name: 'BNI', short: 'BNI', color: 'bg-[#F26522] text-white' },
  { code: 'bri', name: 'BRI', short: 'BRI', color: 'bg-[#005BAC] text-white' },
  { code: 'mandiri', name: 'Mandiri', short: 'MDR', color: 'bg-[#003F72] text-[#FFC72C]' },
  { code: 'cimb', name: 'CIMB', short: 'CMB', color: 'bg-[#8A1B24] text-white' },
  { code: 'permata', name: 'Permata', short: 'PMT', color: 'bg-[#B5A642] text-white' },
]

const pkgNames: Record<string, string> = {
  daily: 'Harian', weekly: 'Mingguan', monthly: 'Bulanan', yearly: 'Tahunan'
}

amount.value = parseInt(route.query.amount as string) || 0
tokens.value = parseInt(route.query.tokens as string) || 0
packageName.value = pkgNames[(route.query.package as string) || ''] || 'Unknown'
method.value = (route.query.method as string) === 'va' ? 'va' : 'qris'

watch(paymentData, async (val) => {
  if (val && method.value === 'qris' && val.qr_string) {
    await nextTick()
    if (qrCanvasRef.value) {
      try {
        await QRCode.toDataURL(qrCanvasRef.value, val.qr_string, {
          width: 240,
          margin: 2,
          color: { dark: '#1a1a1a', light: '#ffffff' }
        })
      } catch (e) {
        console.error('QR generation failed:', e)
      }
    }
  }
})

async function generatePayment() {
  loading.value = true
  error.value = null
  cancelled.value = false
  paymentData.value = null

  try {
    if (method.value === 'qris') {
      const response = await api.post('/api/payment/qris/generate', {
        amount: amount.value,
        description: `Token ${packageName.value} - ${tokens.value} tokens`
      })
      paymentData.value = response.data
      if (response.data.expires_at) {
        startCountdown(new Date(response.data.expires_at))
      }
    } else {
      const response = await api.post('/api/payment/va/generate', {
        amount: amount.value,
        bank: selectedBank.value,
        description: `Token ${packageName.value} - ${tokens.value} tokens`
      })
      paymentData.value = response.data
    }
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { error?: string }, status?: number }, message?: string }
    console.error('Payment error:', axiosErr)
    if (axiosErr.response?.data?.error) {
      error.value = axiosErr.response.data.error
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

async function copyPaymentData() {
  const data = method.value === 'va'
    ? paymentData.value?.account_number
    : paymentData.value?.qr_string
  if (!data) return
  try {
    await navigator.clipboard.writeText(data)
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

function formatDate(s: string) {
  return new Date(s).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' })
}

function getBankColor(code: string) {
  const bank = banks.find(b => b.code === code)
  return bank?.color || 'bg-slate-500 text-white'
}

onUnmounted(() => {
  clearCountdown()
})
</script>