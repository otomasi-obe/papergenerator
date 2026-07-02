<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <AppHeader />

    <main class="max-w-4xl mx-auto px-4 py-8">
      <!-- Header -->
      <div class="mb-8">
        <button
          @click="router.push('/dashboard')"
          class="text-sm text-ink-500 dark:text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 mb-4 flex items-center gap-1"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
          Back to Dashboard
        </button>
        <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">
          Beli Paket Token
        </h1>
        <p class="text-ink-600 dark:text-ink-300 text-sm mt-1">
          Pilih paket yang sesuai dengan kebutuhan Anda
        </p>
      </div>

      <!-- Package Grid -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          v-for="pkg in packages"
          :key="pkg.id"
          @click="selectPackage(pkg)"
          :class="[
            'relative cursor-pointer rounded-2xl border-2 p-6 transition-all hover:shadow-lg',
            selectedPackage?.id === pkg.id
              ? 'border-[var(--accent)] bg-cream-100 dark:bg-ash-700 shadow-lg'
              : 'border-cream-200 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 hover:border-[var(--accent)]'
          ]"
        >
          <!-- Popular Badge -->
          <div
            v-if="pkg.popular"
            class="absolute -top-3 left-1/2 -translate-x-1/2 bg-[var(--accent)] text-white text-xs font-bold px-3 py-1 rounded-full"
          >
            Populer
          </div>

          <!-- Package Info -->
          <div class="text-center">
            <div class="text-3xl mb-2">{{ pkg.icon }}</div>
            <h3 class="text-lg font-bold text-ink-900 dark:text-ink-50 mb-1">
              {{ pkg.name }}
            </h3>
            <p class="text-xs text-ink-500 dark:text-ink-400 mb-4">
              {{ pkg.duration }}
            </p>
            <div class="text-xl font-bold text-ink-900 dark:text-ink-50">
              {{ formatIDR(pkg.price) }}
            </div>
            <p class="text-xs text-ink-400 mt-1">
              {{ pkg.tokens }} token
            </p>
          </div>

          <!-- Selected Indicator -->
          <div
            v-if="selectedPackage?.id === pkg.id"
            class="absolute top-3 right-3 w-6 h-6 rounded-full bg-[var(--accent)] flex items-center justify-center"
          >
            <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        </div>
      </div>

      <!-- Selected Summary -->
      <div
        v-if="selectedPackage"
        class="mt-8 bg-cream-50 dark:bg-ash-800 rounded-2xl border border-cream-200 dark:border-ash-700 p-6"
      >
        <div class="flex justify-between items-center">
          <div>
            <h3 class="text-lg font-bold text-ink-900 dark:text-ink-50">
              {{ selectedPackage.name }}
            </h3>
            <p class="text-sm text-ink-500 dark:text-ink-400">
              {{ selectedPackage.tokens }} token • {{ selectedPackage.duration }}
            </p>
          </div>
          <div class="text-right">
            <div class="text-2xl font-bold text-ink-900 dark:text-ink-50">
              {{ formatIDR(selectedPackage.price) }}
            </div>
          </div>
        </div>

        <button
          @click="proceedToPayment"
          :disabled="!selectedPackage"
          class="w-full mt-4 py-3 bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all hover:shadow-md active:scale-95"
        >
          Lanjut ke Pembayaran
        </button>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'

const router = useRouter()

interface Package {
  id: string
  name: string
  duration: string
  price: number
  tokens: number
  icon: string
  popular?: boolean
}

const packages: Package[] = [
  {
    id: 'daily',
    name: 'Harian',
    duration: '1 Hari',
    price: 1000,
    tokens: 10,
    icon: '⚡'
  },
  {
    id: 'weekly',
    name: 'Mingguan',
    duration: '7 Hari',
    price: 5000,
    tokens: 60,
    icon: '📅',
    popular: true
  },
  {
    id: 'monthly',
    name: 'Bulanan',
    duration: '30 Hari',
    price: 15000,
    tokens: 200,
    icon: '🗓️'
  },
  {
    id: 'yearly',
    name: 'Tahunan',
    duration: '365 Hari',
    price: 150000,
    tokens: 3000,
    icon: '🏆'
  }
]

const selectedPackage = ref<Package | null>(null)

function selectPackage(pkg: Package) {
  selectedPackage.value = pkg
}

function proceedToPayment() {
  if (!selectedPackage.value) return
  router.push({
    path: '/tokens/checkout',
    query: {
      package: selectedPackage.value.id,
      amount: selectedPackage.value.price.toString(),
      tokens: selectedPackage.value.tokens.toString()
    }
  })
}

function formatIDR(amount: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0
  }).format(amount)
}
</script>
