<template>
  <header class="bg-cream-50/95 dark:bg-ash-800/95 backdrop-blur shadow-sm border-b border-cream-200 dark:border-ash-700 sticky top-0 z-40">
    <div class="w-full px-4 lg:px-8 py-3 flex items-center justify-between">
      <!-- Logo + Nav + Token quota bar (rofiq.txt: kuota tampil kiri atas) -->
      <div class="flex items-center gap-4">
        <router-link to="/dashboard" class="flex items-center gap-2 text-ink-900 dark:text-ink-50 hover:text-brown-700 dark:hover:text-cream-200 transition-colors">
          <img :src="logoUrl" alt="PaperFull" class="h-7 w-7 rounded-md object-contain" />
          <span class="font-semibold">PaperFull</span>
        </router-link>

        <!-- Token quota bar -->
        <div v-if="quota.quota_monthly > 0" class="relative group" :title="`${formatNum(quota.used_month)} / ${formatNum(quota.quota_monthly)} token bulan ini`">
          <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600 cursor-default">
            <div class="w-24 h-2 rounded-full bg-cream-300 dark:bg-ash-600 overflow-hidden">
              <div
                class="h-full transition-all"
                :class="quota.percent >= 90 ? 'bg-red-500' : quota.percent >= 70 ? 'bg-amber-500' : 'bg-emerald-500'"
                :style="{ width: Math.min(100, quota.percent) + '%' }"
              ></div>
            </div>
            <span class="text-[11px] font-mono tabular-nums text-ink-700 dark:text-ink-200">
              {{ formatNum(quota.used_month) }}/{{ formatNum(quota.quota_monthly) }}
            </span>
          </div>
          <!-- Tooltip on hover: detail breakdown -->
          <div class="hidden group-hover:block absolute left-0 top-full mt-1 w-64 bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-lg shadow-lg p-3 z-50 text-xs">
            <div class="font-semibold text-ink-900 dark:text-ink-50 mb-1">Pemakaian token bulan {{ quota.month_key }}</div>
            <div class="grid grid-cols-2 gap-1 text-ink-600 dark:text-ink-300">
              <span>Hari ini</span><span class="text-right tabular-nums">{{ formatNum(quota.used_today) }}</span>
              <span>Bulan ini</span><span class="text-right tabular-nums">{{ formatNum(quota.used_month) }}</span>
              <span>Sisa</span><span class="text-right tabular-nums">{{ formatNum(quota.remaining) }}</span>
            </div>
            <div v-if="quota.breakdown_by_model.length" class="mt-2 pt-2 border-t border-cream-200 dark:border-ash-700">
              <div class="text-[10px] uppercase text-ink-500 dark:text-ink-400 mb-1">Per model</div>
              <div v-for="b in quota.breakdown_by_model" :key="b.model" class="flex justify-between text-ink-600 dark:text-ink-300">
                <span class="truncate">{{ b.model }}</span>
                <span class="tabular-nums">{{ formatNum(b.tokens) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="quota.is_unlimited" class="px-3 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 text-[11px] font-medium text-amber-800 dark:text-amber-200">
          ∞ admin
        </div>

        <nav class="hidden md:flex items-center gap-1 text-sm">
          <router-link to="/dashboard" class="px-3 py-1.5 rounded-lg text-ink-700 dark:text-ink-100 hover:bg-cream-200 dark:hover:bg-ash-700 hover:text-ink-900 dark:hover:text-ink-50 transition-colors" active-class="bg-cream-200 dark:bg-ash-700 text-ink-900 dark:text-ink-50">
            Papers
          </router-link>
          <router-link v-if="auth.isAdmin" to="/admin" class="px-3 py-1.5 rounded-lg text-ink-700 dark:text-ink-100 hover:bg-cream-200 dark:hover:bg-ash-700 hover:text-ink-900 dark:hover:text-ink-50 transition-colors" active-class="bg-brown-200 dark:bg-ash-600 text-ink-900 dark:text-ink-50">
            Admin
          </router-link>
        </nav>
      </div>

      <!-- User Menu -->
      <div class="flex items-center gap-3">
        <div class="relative" ref="menuRef">
          <button @click="menuOpen = !menuOpen"
            class="flex items-center gap-2 px-3 py-1.5 rounded-xl hover:bg-cream-200 dark:hover:bg-ash-700 transition-colors text-sm text-ink-900 dark:text-ink-50">
            <img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" class="w-7 h-7 rounded-full" alt="avatar" />
            <span v-else class="w-7 h-7 rounded-full bg-brown-500 dark:bg-brown-400 flex items-center justify-center text-cream-50 text-xs font-bold">
              {{ auth.user?.name?.[0]?.toUpperCase() || 'U' }}
            </span>
            <span class="hidden md:inline font-medium">{{ auth.user?.name || 'User' }}</span>
            <span class="text-ink-500 dark:text-ink-300">▾</span>
          </button>

          <!-- Dropdown -->
          <div v-if="menuOpen" class="absolute right-0 top-full mt-1 w-56 bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-lg overflow-hidden z-50">
            <div class="px-4 py-3 border-b border-cream-200 dark:border-ash-700">
              <p class="text-sm font-medium text-ink-900 dark:text-ink-50">{{ auth.user?.name }}</p>
              <p class="text-xs text-ink-600 dark:text-ink-300">{{ auth.user?.email }}</p>
              <span v-if="auth.isAdmin" class="text-xs bg-brown-200 dark:bg-ash-700 text-ink-900 dark:text-ink-50 px-1.5 py-0.5 rounded mt-1 inline-block">Admin</span>
            </div>

            <!-- Theme switcher -->
            <div class="px-3 py-2.5 border-b border-cream-200 dark:border-ash-700">
              <div class="text-[11px] uppercase tracking-wider text-ink-500 dark:text-ink-400 font-semibold mb-1.5 px-1">Theme</div>
              <div class="grid grid-cols-3 gap-1 bg-cream-100 dark:bg-ash-700 p-1 rounded-lg">
                <button
                  v-for="opt in themeOptions"
                  :key="opt.value"
                  @click="setMode(opt.value)"
                  :class="[
                    'flex items-center justify-center gap-1 py-1.5 rounded-md text-[11px] font-medium transition-colors',
                    mode === opt.value
                      ? 'bg-cream-50 dark:bg-ash-850 text-ink-900 dark:text-ink-50 shadow-sm border border-cream-300 dark:border-ash-600'
                      : 'text-ink-600 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50',
                  ]"
                  :title="opt.label"
                >
                  <span aria-hidden="true">{{ opt.icon }}</span>
                  <span class="hidden xs:inline">{{ opt.label }}</span>
                </button>
              </div>
            </div>

            <router-link to="/dashboard" @click="menuOpen = false" class="flex items-center gap-2 px-4 py-2.5 text-sm text-ink-800 dark:text-ink-100 hover:bg-cream-100 dark:hover:bg-ash-700 transition-colors">
              📄 My Papers
            </router-link>
            <router-link v-if="auth.isAdmin" to="/admin" @click="menuOpen = false" class="flex items-center gap-2 px-4 py-2.5 text-sm text-ink-800 dark:text-ink-100 hover:bg-cream-100 dark:hover:bg-ash-700 transition-colors">
              📊 Admin
            </router-link>
            <div class="border-t border-cream-200 dark:border-ash-700">
              <button @click="doLogout" class="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors">
                🚪 Sign Out
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useTheme } from '../stores/theme.js'
import api from '../api/index.js'
import logoUrl from '../image/logo.png'

const auth = useAuthStore()
const router = useRouter()
const menuOpen = ref(false)
const menuRef = ref(null)

const { mode, setMode } = useTheme()

const themeOptions = [
  { value: 'light',  label: 'Light',  icon: '☀️' },
  { value: 'dark',   label: 'Dark',   icon: '🌙' },
  { value: 'system', label: 'System', icon: '🖥️' },
]

// rofiq.txt: token bar di kiri, hover untuk detail.
const quota = ref({
  quota_monthly: 0,
  used_month: 0,
  used_today: 0,
  remaining: 0,
  percent: 0,
  month_key: '',
  breakdown_by_model: [],
  is_unlimited: false,
})

let quotaTimer = null

function formatNum(n) {
  if (typeof n !== 'number') n = Number(n) || 0
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k'
  return String(n)
}

async function loadQuota() {
  try {
    const res = await api.get('/api/me/quota')
    if (res?.data) Object.assign(quota.value, res.data)
  } catch { /* not signed in or backend cold */ }
}

function doLogout() {
  auth.logout()
  router.push('/login')
}

function handleOutsideClick(e) {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    menuOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  loadQuota()
  // Refresh tiap 30 detik supaya bar terupdate setelah generate.
  quotaTimer = setInterval(loadQuota, 30_000)
})
onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
  if (quotaTimer) clearInterval(quotaTimer)
})
</script>
