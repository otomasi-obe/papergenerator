<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <AppHeader />

    <main class="max-w-2xl mx-auto px-4 py-8">
      <!-- Header -->
      <div class="mb-8">
        <button
          @click="goBackToPackages"
          class="text-sm text-ink-500 dark:text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 mb-4 flex items-center gap-1"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
          Kembali ke Pilih Paket
        </button>
        <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">
          Metode Pembayaran
        </h1>
      </div>

      <!-- Order Summary -->
      <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border border-cream-200 dark:border-ash-700 p-6 mb-8">
        <h3 class="text-sm font-medium text-ink-500 dark:text-ink-400 uppercase tracking-wide mb-4">
          Ringkasan Pesanan
        </h3>
        <div class="space-y-2">
          <div class="flex justify-between">
            <span class="text-ink-700 dark:text-ink-200">Paket</span>
            <span class="font-medium text-ink-900 dark:text-ink-50">{{ packageName }}</span>
          </div>
          <BadgeTier v-if="badge" :badge="badge" size="sm" />
          <ul v-if="badge" class="text-left text-xs text-ink-600 dark:text-cream-100 space-y-0.5 border-t border-cream-200 dark:border-ash-700 pt-2">
            <li v-for="b in BADGE_TIERS[badge].benefits" :key="b" class="flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
              {{ b }}
            </li>
          </ul>
          <div class="flex justify-between">
            <span class="text-ink-700 dark:text-ink-200">Token</span>
            <span class="font-medium text-ink-900 dark:text-ink-50">{{ tokens }}</span>
          </div>
          <div class="border-t border-cream-200 dark:border-ash-700 pt-2 mt-2 flex justify-between">
            <span class="font-bold text-ink-900 dark:text-ink-50">Total</span>
            <span class="font-bold text-lg text-ink-900 dark:text-ink-50">{{ formatIDR(amount) }}</span>
          </div>
        </div>
      </div>

      <!-- Payment Methods -->
      <div class="mb-8">
        <h3 class="text-lg font-bold text-ink-900 dark:text-ink-50 mb-4">
          Pilih Metode Pembayaran
        </h3>

        <div class="space-y-3">
          <!-- QRIS -->
          <button
            @click="selectMethod('qris')"
            :class="[
              'w-full rounded-xl border-2 p-4 transition-all text-left hover:shadow-md cursor-pointer',
              selectedMethod === 'qris'
                ? 'border-[var(--accent)] bg-cream-100 dark:bg-ash-700'
                : 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 hover:border-[var(--accent)]'
            ]"
          >
            <div class="flex items-center gap-4">
              <!-- QRIS Logo -->
              <div class="w-14 h-14 rounded-xl bg-[#E31937] flex items-center justify-center shrink-0">
                <svg viewBox="0 0 100 100" class="w-10 h-10">
                  <rect x="8" y="8" width="28" height="28" rx="4" fill="white"/>
                  <rect x="64" y="8" width="12" height="12" fill="white"/>
                  <rect x="80" y="8" width="12" height="12" fill="white"/>
                  <rect x="8" y="40" width="12" height="12" fill="white"/>
                  <rect x="24" y="40" width="12" height="12" fill="white"/>
                  <rect x="40" y="40" width="20" height="20" rx="2" fill="white"/>
                  <rect x="64" y="40" width="12" height="12" fill="white"/>
                  <rect x="80" y="40" width="12" height="12" fill="white"/>
                  <rect x="8" y="64" width="12" height="12" fill="white"/>
                  <rect x="24" y="64" width="12" height="12" fill="white"/>
                  <rect x="40" y="76" width="12" height="12" fill="white"/>
                  <rect x="64" y="64" width="12" height="12" fill="white"/>
                  <rect x="80" y="64" width="12" height="12" fill="white"/>
                  <rect x="8" y="80" width="12" height="12" fill="white"/>
                  <rect x="24" y="80" width="12" height="12" fill="white"/>
                  <rect x="40" y="80" width="12" height="12" fill="white"/>
                  <rect x="64" y="80" width="12" height="12" fill="white"/>
                </svg>
              </div>

              <div class="flex-1">
                <h4 class="font-bold text-ink-900 dark:text-ink-50">QRIS</h4>
                <p class="text-xs text-ink-500 dark:text-ink-400">Scan QR Code dengan aplikasi bank/e-wallet</p>
                <div class="flex gap-1.5 mt-1.5 flex-wrap">
                  <span class="text-xs px-2 py-0.5 rounded-full bg-cream-200 dark:bg-ash-600 text-ink-600 dark:text-ink-300">GoPay</span>
                  <span class="text-xs px-2 py-0.5 rounded-full bg-cream-200 dark:bg-ash-600 text-ink-600 dark:text-ink-300">OVO</span>
                  <span class="text-xs px-2 py-0.5 rounded-full bg-cream-200 dark:bg-ash-600 text-ink-600 dark:text-ink-300">DANA</span>
                  <span class="text-xs px-2 py-0.5 rounded-full bg-cream-200 dark:bg-ash-600 text-ink-600 dark:text-ink-300">ShopeePay</span>
                </div>
              </div>

              <!-- Radio -->
              <div
                :class="[
                  'w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0',
                  selectedMethod === 'qris'
                    ? 'border-[var(--accent)] bg-[var(--accent)]'
                    : 'border-cream-300 dark:border-ash-600'
                ]"
              >
                <svg v-if="selectedMethod === 'qris'" class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </div>
          </button>

          <!-- Virtual Account -->
          <button
            @click="selectMethod('va')"
            :class="[
              'w-full rounded-xl border-2 p-4 transition-all text-left hover:shadow-md cursor-pointer',
              selectedMethod === 'va'
                ? 'border-[var(--accent)] bg-cream-100 dark:bg-ash-700'
                : 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 hover:border-[var(--accent)]'
            ]"
          >
            <div class="flex items-center gap-4">
              <!-- VA Logo -->
              <div class="w-14 h-14 rounded-xl bg-[#1A3A5C] flex items-center justify-center shrink-0">
                <span class="text-white font-black text-lg tracking-wider">VA</span>
              </div>

              <div class="flex-1">
                <h4 class="font-bold text-ink-900 dark:text-ink-50">Virtual Account</h4>
                <p class="text-xs text-ink-500 dark:text-ink-400">Transfer ke nomor rekening virtual bank</p>
                <div class="flex gap-1.5 mt-1.5 flex-wrap">
                  <span class="text-xs px-2 py-0.5 rounded-full bg-[#0066B3]/10 dark:bg-[#0066B3]/20 text-[#0066B3] dark:text-blue-300 font-medium">BCA</span>
                  <span class="text-xs px-2 py-0.5 rounded-full bg-[#F26522]/10 dark:bg-[#F26522]/20 text-[#F26522] dark:text-orange-300 font-medium">BNI</span>
                  <span class="text-xs px-2 py-0.5 rounded-full bg-[#005BAC]/10 dark:bg-[#005BAC]/20 text-[#005BAC] dark:text-blue-300 font-medium">BRI</span>
                  <span class="text-xs px-2 py-0.5 rounded-full bg-[#003F72]/10 dark:bg-[#003F72]/20 text-[#003F72] dark:text-blue-300 font-medium">Mandiri</span>
                </div>
              </div>

              <!-- Radio -->
              <div
                :class="[
                  'w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0',
                  selectedMethod === 'va'
                    ? 'border-[var(--accent)] bg-[var(--accent)]'
                    : 'border-cream-300 dark:border-ash-600'
                ]"
              >
                <svg v-if="selectedMethod === 'va'" class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
              </div>
            </div>
          </button>
        </div>
      </div>

      <!-- Action Button -->
      <button
        @click="proceedToPayment"
        :disabled="!selectedMethod"
        class="w-full py-3 bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all hover:shadow-md active:scale-95"
      >
        Lanjut ke Pembayaran
      </button>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import { BADGE_TIERS, type BadgeKey } from '../config/badgeTiers'
import BadgeTier from '../components/BadgeTier.vue'

const router = useRouter()
const route = useRoute()

const selectedMethod = ref<string | null>(null)
const packageName = ref('')
const tokens = ref(0)
const amount = ref(0)
const badge = ref<BadgeKey>('starter')

onMounted(() => {
  const pkg = route.query.package as string
  const amountStr = route.query.amount as string
  const tokensStr = route.query.tokens as string

  if (!pkg || !amountStr || !tokensStr) {
    goBackToPackages()
    return
  }

  amount.value = parseInt(amountStr)
  tokens.value = parseInt(tokensStr)

  const pkgNames: Record<string, string> = {
    daily: 'Harian (1 Hari)',
    weekly: 'Mingguan (7 Hari)',
    monthly: 'Bulanan (30 Hari)',
    yearly: 'Tahunan (365 Hari)'
  }
  const pkgBadges: Record<string, BadgeKey> = {
    daily: 'starter',
    weekly: 'pro',
    monthly: 'elite',
    yearly: 'elite'
  }
  packageName.value = pkgNames[pkg] || pkg
  badge.value = pkgBadges[pkg] || 'starter'
})

function goBackToPackages() {
  window.dispatchEvent(new Event('open-token-purchase'))
}

function selectMethod(method: string) {
  selectedMethod.value = method
}

function proceedToPayment() {
  if (!selectedMethod.value) return
  router.push({
    path: '/tokens/pay',
    query: {
      package: route.query.package,
      amount: amount.value.toString(),
      tokens: tokens.value.toString(),
      method: selectedMethod.value
    }
  })
}

function formatIDR(value: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0
  }).format(value)
}
</script>