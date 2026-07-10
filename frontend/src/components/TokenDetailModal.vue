<script setup lang="ts">
import { ref, computed, watch } from 'vue'
// @ts-ignore
import api from '../api/index.ts'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'buy-tokens'): void
}>()

const loading = ref(false)
const error = ref<string | null>(null)
const tokenData = ref<any>(null)

// Computed properties from tokenData
const purchase_history = computed(() => tokenData.value?.purchase_history || [])
const usage_history = computed(() => tokenData.value?.usage_history || [])
const trend = computed(() => tokenData.value?.trend || 'stable')
const today_usage = computed(() => tokenData.value?.today_usage || 0)
const yesterday_usage = computed(() => tokenData.value?.yesterday_usage || 0)
const remaining = computed(() => tokenData.value?.remaining || 0)
const base_quota = computed(() => tokenData.value?.base_quota || 0)
const bonus_tokens = computed(() => tokenData.value?.bonus_tokens || 0)

// UI state
// const usageTableExpanded = ref(false) // ponytail: add expandable table state when needed

// Formatters
function formatNum(n: number | string): string {
  if (typeof n !== 'number') n = Number(n) || 0
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k'
  return String(n)
}

function formatIDR(amountVal: number): string {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0 }).format(amountVal)
}

function formatDate(dateStr: string): string {
  const options: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit', year: 'numeric' }
  return new Date(dateStr).toLocaleDateString('id-ID', options)
}

function formatDateTime(dateStr: string): string {
  const options: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }
  return new Date(dateStr).toLocaleDateString('id-ID', options)
}

async function fetchTokenDetails() {
  if (!props.open) return
  loading.value = true
  error.value = null
  try {
    const res = await api.get('/user/tokens/detail')
    tokenData.value = res.data.data
  } catch (e: any) {
    error.value = e?.response?.data?.message || 'Gagal memuat detail token'
  } finally {
    loading.value = false
  }
}

// Load when open changes
watch(() => props.open, (val) => {
  if (val) {
    fetchTokenDetails()
  }
})

// Initial load
if (props.open) {
  fetchTokenDetails()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade-modal">
      <div v-if="open" class="modal-overlay" @click.self="emit('close')">
        <div class="modal-container">
          <div class="modal-header">
            <h3 class="modal-title">Detail Token</h3>
            <button class="modal-close" @click="emit('close')" aria-label="Tutup">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <div class="modal-body" v-if="!loading && !error">
            <!-- Summary cards -->
            <div class="token-summary-grid">
              <div class="summary-card primary">
                <div class="summary-value">{{ remaining }}</div>
                <div class="summary-label">Token Tersisa</div>
                <div class="summary-sub" v-if="bonus_tokens > 0">+{{ bonus_tokens }} bonus</div>
              </div>
              <div class="summary-card">
                <div class="summary-value">{{ base_quota }}</div>
                <div class="summary-label">Kuota Bulanan</div>
              </div>
              <div class="summary-card">
                <div class="summary-value">{{ today_usage }}</div>
                <div class="summary-label">Dipakai Hari Ini</div>
              </div>
              <div class="summary-card">
                <div class="summary-value">{{ yesterday_usage }}</div>
                <div class="summary-label">Dipakai Kemarin</div>
              </div>
            </div>

            <!-- Usage trend indicator -->
            <div class="trend-indicator" :class="trend">
              <span class="trend-icon">
                <svg v-if="trend === 'up'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M18 15l-6-6-6 6"/>
                </svg>
                <svg v-else-if="trend === 'down'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M6 9l6 6 6-6"/>
                </svg>
                <span v-else>→</span>
              </span>
              <span class="trend-text">
                Penggunaan <strong>{{ trend === 'up' ? 'meningkat' : trend === 'down' ? 'menurun' : 'stabil' }}</strong>
              </span>
            </div>

            <!-- Usage History Table -->
            <div class="section" v-if="usage_history.length">
              <div class="section-header">
                <h4 class="section-title">Riwayat Penggunaan (7 Hari Terakhir)</h4>
              </div>
              <div class="table-wrapper">
                <table class="usage-table">
                  <thead>
                    <tr>
                      <th>Tanggal</th>
                      <th>Token Dipakai</th>
                      <th>Sisa Harian</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(item, i) in usage_history" :key="i">
                      <td>{{ formatDate(item.date) }}</td>
                      <td>{{ formatNum(item.used) }}</td>
                      <td>{{ formatNum(item.remaining) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Purchase History -->
            <div class="section" v-if="purchase_history.length">
              <div class="section-header">
                <h4 class="section-title">Riwayat Pembelian</h4>
              </div>
              <div class="table-wrapper">
                <table class="usage-table">
                  <thead>
                    <tr>
                      <th>Tanggal</th>
                      <th>Paket</th>
                      <th>Token</th>
                      <th>Harga</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(item, i) in purchase_history" :key="i">
                      <td>{{ formatDateTime(item.created_at) }}</td>
                      <td>{{ item.package_name || item.plan }}</td>
                      <td class="text-green">{{ formatNum(item.tokens) }} <span v-if="item.bonus">+{{ item.bonus }}</span></td>
                      <td>{{ formatIDR(item.amount) }}</td>
                      <td><span class="status-badge" :class="item.status">{{ item.status }}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div v-if="!usage_history.length && !purchase_history.length" class="empty-state">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              <p>Belum ada aktivitas token</p>
            </div>
          </div>

          <div v-else-if="loading" class="modal-loading">
            <div class="spinner"></div>
            <p>Memuat detail token...</p>
          </div>

          <div v-else-if="error" class="modal-error">
            <p class="error-message">{{ error }}</p>
            <button class="btn-retry" @click="fetchTokenDetails">Coba Lagi</button>
          </div>

          <div class="modal-footer">
            <button class="btn-primary" @click="emit('buy-tokens')">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 5v14M5 12h14"/>
              </svg>
              Beli Token
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  padding: 16px;
}

.modal-container {
  width: 100%;
  max-width: 520px;
  max-height: 85vh;
  background: var(--color-bg-elevated, #1e293b);
  border: 1px solid var(--color-border, #334155);
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border, #334155);
  background: var(--color-bg-surface, #0f172a);
}

.modal-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--color-text-primary, #e2e8f0);
}

.modal-close {
  background: none;
  border: none;
  color: var(--color-text-muted, #94a3b8);
  padding: 6px;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s, background 0.15s;
}

.modal-close:hover {
  color: var(--color-text-primary, #e2e8f0);
  background: var(--color-bg-hover, #1e293b);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.token-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.summary-card {
  background: var(--color-bg-surface, #0f172a);
  border: 1px solid var(--color-border, #334155);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}

.summary-card.primary {
  background: linear-gradient(135deg, var(--color-accent, #3b82f6), var(--color-accent-dark, #2563eb));
  border: none;
  color: #fff;
}

.summary-value {
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1.2;
}

.summary-label {
  font-size: 0.75rem;
  color: var(--color-text-muted, #94a3b8);
  margin-top: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.summary-card.primary .summary-label {
  color: rgba(255, 255, 255, 0.8);
}

.summary-sub {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.7);
  margin-top: 4px;
}

.trend-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px;
  border-radius: 10px;
  font-size: 0.8rem;
  color: var(--color-text-secondary, #cbd5e1);
  margin-bottom: 20px;
}

.trend-indicator.up {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.trend-indicator.down {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.trend-icon {
  display: flex;
  align-items: center;
}

.section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--color-text-primary, #e2e8f0);
}

.table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid var(--color-border, #334155);
}

.usage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.usage-table th,
.usage-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--color-border, #334155);
}

.usage-table th {
  background: var(--color-bg-surface, #0f172a);
  font-weight: 600;
  color: var(--color-text-secondary, #cbd5e1);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 0.7rem;
}

.usage-table td {
  color: var(--color-text-primary, #e2e8f0);
}

.usage-table tr:last-child td {
  border-bottom: none;
}

.text-green {
  color: #22c55e;
  font-weight: 500;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 500;
  text-transform: capitalize;
}

.status-badge.success {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.status-badge.pending {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}

.status-badge.failed {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--color-text-muted, #94a3b8);
  text-align: center;
}

.empty-state svg {
  margin-bottom: 12px;
  opacity: 0.6;
}

.modal-loading,
.modal-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--color-text-secondary, #cbd5e1);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border, #334155);
  border-top-color: var(--color-accent, #3b82f6);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.modal-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--color-border, #334155);
  background: var(--color-bg-surface, #0f172a);
}

.btn-primary {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-accent, #3b82f6);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.05s;
}

.btn-primary:hover {
  opacity: 0.9;
}

.btn-primary:active {
  transform: scale(0.98);
}

.btn-retry {
  margin-top: 12px;
  padding: 8px 16px;
  background: var(--color-bg-hover, #1e293b);
  color: var(--color-text-primary, #e2e8f0);
  border: 1px solid var(--color-border, #334155);
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-retry:hover {
  background: var(--color-bg-surface, #0f172a);
}

.error-message {
  color: #ef4444;
  margin-bottom: 8px;
}

/* Transition */
.fade-modal-enter-active,
.fade-modal-leave-active {
  transition: opacity 0.2s ease;
}

.fade-modal-enter-from,
.fade-modal-leave-to {
  opacity: 0;
}

.fade-modal-enter-from .modal-container,
.fade-modal-leave-to .modal-container {
  transform: scale(0.95) translateY(10px);
}
</style>