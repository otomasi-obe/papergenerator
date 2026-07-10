<template>
  <div v-if="open" class="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-8 sm:pt-10">
    <div class="fixed inset-0 bg-black/30 transition-opacity z-0" @click="$emit('close')" aria-hidden="true" />
    <div class="relative z-[70] w-full max-w-2xl h-[85vh] sm:h-[90vh] bg-cream-50 dark:bg-ash-900 rounded-2xl shadow-xl flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b border-cream-200 dark:border-ash-700 shrink-0">
        <h2 class="text-lg font-bold text-ink-900 dark:text-ink-50">Detail Token</h2>
        <button @click="$emit('close')" class="p-1.5 min-h-[36px] min-w-[36px] rounded-lg text-ink-400 hover:text-ink-600 dark:hover:text-ink-300 hover:bg-cream-100 dark:hover:bg-ash-800 transition-colors" aria-label="Tutup">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
        </button>
      </div>

      <!-- Body -->
      <div class="px-5 py-4 overflow-y-auto space-y-5 flex-1" v-if="!loading && !error">
        <!-- Summary Cards -->
        <div class="grid grid-cols-2 gap-3">
          <div v-for="card in summaryCards" :key="card.label" :class="['p-3 rounded-xl border', card.colorClass]">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-lg">{{ card.icon }}</span>
              <span class="text-xs font-medium text-ink-500 dark:text-ink-400">{{ card.label }}</span>
            </div>
            <div class="text-2xl font-bold">{{ formatNum(card.value) }}</div>
          </div>
        </div>

        <!-- Trend Card -->
        <div class="p-4 rounded-xl bg-cream-50 dark:bg-ash-800 border border-cream-200 dark:border-ash-700">
          <div class="text-sm font-medium text-ink-700 dark:text-ink-300 mb-2">Trend Harian</div>
          <div class="flex items-center justify-between">
            <div>
              <div class="text-2xl font-bold text-ink-900 dark:text-ink-50">{{ formatNum(data?.today_usage || 0) }}</div>
              <div class="text-xs text-ink-500 dark:text-ink-400">Hari ini</div>
            </div>
            <div class="text-right">
              <div :class="['text-xl font-bold', trendColor]">{{ trendIcon }} {{ trendPct > 0 ? '+' : '' }}{{ trendPct }}%</div>
              <div class="text-xs text-ink-500 dark:text-ink-400">vs kemarin ({{ formatNum(data?.yesterday_usage || 0) }})</div>
            </div>
          </div>
        </div>

        <!-- Line Chart -->
        <div>
          <div class="text-sm font-medium text-ink-700 dark:text-ink-300 mb-2">Grafik Pemakaian (30 hari)</div>
          <div v-if="chartPoints.length > 0" class="rounded-xl bg-white dark:bg-ash-900 border border-cream-200 dark:border-ash-700 p-2">
            <svg width="560" height="180" viewBox="0 0 560 180" class="w-full h-auto">
              <!-- Grid lines -->
              <g stroke="#e5e5e5" stroke-width="0.5" class="dark:stroke-ash-700">
                <line v-for="i in 4" :key="'grid-'+i" :x1="chartPad.left" :y1="chartPad.top + ((i-1)/3)*chartInnerH" :x2="chartPad.left + chartInnerW" :y2="chartPad.top + ((i-1)/3)*chartInnerH" />
              </g>
              <!-- Y axis labels -->
              <g class="text-[10px] text-ink-400 dark:text-ink-500" font-family="monospace">
                <text v-for="i in 4" :key="'y-'+i" :x="chartPad.left - 8" :y="chartPad.top + ((i-1)/3)*chartInnerH + 4" text-anchor="end" dominant-baseline="middle">{{ formatNum(Math.round(chartMin + (chartRange * (4-i) / 3))) }}</text>
              </g>
              <!-- X axis labels (dates, sparse) -->
              <g class="text-[10px] text-ink-400 dark:text-ink-500" font-family="monospace">
                <text v-for="(p, i) in sparseXLabels" :key="'x-'+i" :x="getX(i * xLabelStep)" :y="180 - 6" text-anchor="middle" dominant-baseline="hanging">{{ p }}</text>
              </g>
              <!-- Axis lines -->
              <line :x1="chartPad.left" :y1="chartPad.top" :x2="chartPad.left" :y2="chartPad.top + chartInnerH" stroke="#d1d5db" stroke-width="1" class="dark:stroke-ash-600" />
              <line :x1="chartPad.left" :y1="chartPad.top + chartInnerH" :x2="chartPad.left + chartInnerW" :y2="chartPad.top + chartInnerH" stroke="#d1d5db" stroke-width="1" class="dark:stroke-ash-600" />
              <!-- Line -->
              <polyline fill="none" stroke="var(--accent)" stroke-width="2" :points="polylineStr" stroke-linecap="round" stroke-linejoin="round" />
              <!-- Dots -->
              <g>
                <circle v-for="(p, i) in chartPoints" :key="'dot-'+i" :cx="getX(i)" :cy="getY(p.tokens)" r="3" fill="var(--accent)" stroke="white" stroke-width="2" class="dark:stroke-ash-900" />
              </g>
            </svg>
          </div>
          <div v-else class="h-48 rounded-xl bg-cream-50 dark:bg-ash-800 border border-cream-200 dark:border-ash-700 flex items-center justify-center">
            <span class="text-ink-500 dark:text-ink-400 text-sm">Belum ada data pemakaian</span>
          </div>
        </div>

        <!-- Usage Table (collapsible) -->
        <div class="border border-cream-200 dark:border-ash-700 rounded-xl overflow-hidden">
          <button @click="usageOpen = !usageOpen" class="w-full px-4 py-3 bg-cream-50 dark:bg-ash-800 flex items-center justify-between text-left hover:bg-cream-100 dark:hover:bg-ash-700 transition-colors">
            <span class="font-medium text-ink-900 dark:text-ink-50">Pemakaian per Tanggal</span>
            <svg class="w-5 h-5 text-ink-400 transition-transform" :class="{ 'rotate-180': usageOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
          </button>
          <div v-show="usageOpen" class="px-4 pb-4">
            <table class="w-full text-sm">
              <thead><tr class="text-left text-xs text-ink-500 dark:text-ink-400 border-b border-cream-200 dark:border-ash-700"><th class="pb-2 pr-4">Tanggal</th><th class="pb-2 pr-4 text-right">Token</th><th class="pb-2 text-right">Calls</th></tr></thead>
              <tbody>
                <tr v-for="(d, i) in displayUsage" :key="'u-'+i" :class="['border-b border-cream-100 dark:border-ash-800', i % 2 === 0 ? 'bg-cream-50/50 dark:bg-ash-800/50' : '']">
                  <td class="py-2 pr-4 text-ink-900 dark:text-ink-500">{{ formatDate(d.date) }}</td>
                  <td class="py-2 pr-4 text-right font-mono tabular-nums text-ink-700 dark:text-ink-300">{{ formatNum(d.tokens) }}</td>
                  <td class="py-2 text-right font-mono tabular-nums text-ink-500 dark:text-ink-400">{{ d.calls }}</td>
                </tr>
                <tr v-if="displayUsage.length === 0"><td colspan="3" class="py-6 text-center text-ink-400 dark:text-ink-500 text-sm">Belum ada data pemakaian</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Purchase History Table (collapsible) -->
        <div class="border border-cream-200 dark:border-ash-700 rounded-xl overflow-hidden">
          <button @click="purchaseOpen = !purchaseOpen" class="w-full px-4 py-3 bg-cream-50 dark:bg-ash-800 flex items-center justify-between text-left hover:bg-cream-100 dark:hover:bg-ash-700 transition-colors">
            <span class="font-medium text-ink-900 dark:text-ink-50">Riwayat Transaksi</span>
            <svg class="w-5 h-5 text-ink-400 transition-transform" :class="{ 'rotate-180': purchaseOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
          </button>
          <div v-show="purchaseOpen" class="px-4 pb-4 overflow-x-auto">
            <table class="w-full text-sm">
              <thead><tr class="text-left text-xs text-ink-500 dark:text-ink-400 border-b border-cream-200 dark:border-ash-700"><th class="pb-2 pr-4">Tanggal</th><th class="pb-2 pr-4 text-right">Token</th><th class="pb-2 pr-4 text-right">Nominal</th><th class="pb-2 pr-4">Metode</th><th class="pb-2">Status</th></tr></thead>
              <tbody>
                <tr v-for="(d, i) in (data?.purchase_history || [])" :key="'p-'+i" :class="['border-b border-cream-100 dark:border-ash-800', i % 2 === 0 ? 'bg-cream-50/50 dark:bg-ash-800/50' : '']">
                  <td class="py-2 pr-4 text-ink-900 dark:text-ink-500">{{ formatDate(d.date) }}</td>
                  <td class="py-2 pr-4 text-right font-mono tabular-nums text-ink-700 dark:text-ink-300">{{ formatNum(d.tokens) }}</td>
                  <td class="py-2 pr-4 text-right font-mono tabular-nums text-ink-700 dark:text-ink-300">{{ formatIDR(d.amount) }}</td>
                  <td class="py-2 pr-4 text-ink-600 dark:text-ink-400">{{ d.payment_method || d.provider }}</td>
                  <td class="py-2"><span :class="['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', statusColor(d.status)]">{{ d.status }}</span></td>
                </tr>
                <tr v-if="(data?.purchase_history || []).length === 0"><td colspan="5" class="py-6 text-center text-ink-400 dark:text-ink-500 text-sm">Belum ada riwayat transaksi</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-12">
        <div class="w-8 h-8 border-4 border-cream-300 dark:border-ash-600 border-t-[var(--accent)] rounded-full animate-spin"></div>
      </div>

      <!-- Error -->
      <div v-if="error" class="flex flex-col items-center justify-center py-12 text-red-600 dark:text-red-400 text-center px-4">
        <p>{{ error }}</p>
        <button @click="fetchData" class="mt-3 text-sm underline hover:no-underline">Coba lagi</button>
      </div>

      <!-- Footer: beli token sudah ada di header, tidak perlu duplikat di sini -->
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import api from '../api/index'

interface TokenData {
  purchase_history: any[]
  usage_history: any[]
  trend: string
  today_usage: number
  yesterday_usage: number
  total_spent: number
  total_spent_month: number
  total_purchased: number
  remaining: number
  base_quota: number
  bonus_tokens: number
}

const props = defineProps<{ open: boolean }>()
defineEmits<{ close: [], 'buy-tokens': [] }>()

const loading = ref(true)
const error = ref<string | null>(null)
const data = ref<TokenData | null>(null)
const usageOpen = ref(true)
const purchaseOpen = ref(true)

async function fetchData() {
  loading.value = true
  error.value = null
  try {
    const res = await api.get('/api/me/token-history')
    if (res?.data) data.value = res.data
    else error.value = 'Data tidak valid'
  } catch (e: any) {
    error.value = e.response?.data?.message || 'Gagal memuat data token'
  } finally {
    loading.value = false
  }
}

watch(() => props.open, (val) => { if (val) fetchData() })

// Summary cards
const summaryCards = computed(() => {
  const d = data.value
  if (!d) return []
  const remaining = d.remaining || 0
  const remainingColor = remaining < 50000 ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800'
    : remaining < 150000 ? 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800'
    : 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
  return [
    { label: 'Sisa Token', value: remaining, icon: '💎', colorClass: remainingColor },
    { label: 'Base Quota', value: d.base_quota || 0, icon: '📦', colorClass: 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800' },
    { label: 'Bonus', value: d.bonus_tokens || 0, icon: '🎁', colorClass: 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800' },
    { label: 'Total', value: (d.base_quota || 0) + (d.bonus_tokens || 0), icon: '📊', colorClass: 'bg-navy-50 dark:bg-navy-900/20 text-navy-700 dark:text-navy-300 border-navy-200 dark:border-navy-800' },
  ]
})

// Trend
const trendColor = computed(() => {
  const t = data.value?.trend || 'stable'
  return t === 'up' ? 'text-red-600 dark:text-red-400' : t === 'down' ? 'text-emerald-600 dark:text-emerald-400' : 'text-ink-500 dark:text-ink-400'
})
const trendIcon = computed(() => {
  const t = data.value?.trend || 'stable'
  return t === 'up' ? '↑' : t === 'down' ? '↓' : '→'
})
const trendPct = computed(() => {
  const today = data.value?.today_usage || 0
  const yest = data.value?.yesterday_usage || 0
  if (yest === 0) return 0
  return Number(((today - yest) / yest * 100).toFixed(1))
})

// Chart
const chartPoints = computed(() => {
  const hist = data.value?.usage_history || []
  return [...hist].reverse() // chronological
})
const chartPad = { top: 20, right: 20, bottom: 30, left: 50 }
const chartInnerW = 560 - chartPad.left - chartPad.right
const chartInnerH = 180 - chartPad.top - chartPad.bottom
const chartMax = computed(() => Math.max(...chartPoints.value.map(p => p.tokens), 1))
const chartMin = computed(() => Math.min(...chartPoints.value.map(p => p.tokens), 0))
const chartRange = computed(() => (chartMax.value - chartMin.value) || 1)
function getX(i: number) { return chartPad.left + (i / (chartPoints.value.length - 1 || 1)) * chartInnerW }
function getY(val: number) { return chartPad.top + chartInnerH - ((val - chartMin.value) / chartRange.value) * chartInnerH }
const polylineStr = computed(() => chartPoints.value.map((p, i) => `${getX(i)},${getY(p.tokens)}`).join(' '))
const xLabelStep = computed(() => Math.ceil(chartPoints.value.length / 6) || 1)
const sparseXLabels = computed(() => {
  const pts = chartPoints.value
  const step = xLabelStep.value
  const labels: string[] = []
  for (let i = 0; i < pts.length; i += step) {
    labels.push(new Date(pts[i].date).toLocaleDateString('id-ID', { day: '2-digit', month: '2-digit' }))
  }
  if (pts.length > 0 && (pts.length - 1) % step !== 0) {
    labels.push(new Date(pts[pts.length - 1].date).toLocaleDateString('id-ID', { day: '2-digit', month: '2-digit' }))
  }
  return labels
})

// Usage table (last 7 days)
const displayUsage = computed(() => [...(data.value?.usage_history || [])].reverse().slice(0, 7))

// Helpers
function formatNum(n: number): string {
  return Number(n || 0).toLocaleString('id-ID')
}
function formatIDR(amount: number): string {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(amount || 0)
}
function formatDate(iso: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('id-ID', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' })
}
function statusColor(status: string): string {
  const map: Record<string, string> = {
    paid: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300',
    success: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300',
    pending: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
    failed: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
  }
  return map[status] || 'bg-cream-200 dark:bg-ash-700 text-ink-600 dark:text-ink-400'
}
</script>