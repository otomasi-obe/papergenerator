<template>
  <header class="bg-cream-50/95 dark:bg-ash-800/95 backdrop-blur shadow-sm border-b border-cream-200 dark:border-ash-700 sticky top-0 z-40">
    <div class="w-full px-4 lg:px-8 py-3 flex items-center justify-between">
      <!-- Logo + Nav + Token quota bar (rofiq.txt: kuota tampil kiri atas) -->
      <div class="flex items-center gap-4">
        <router-link to="/dashboard" class="flex items-center gap-2 min-h-[44px] min-w-[44px] text-ink-900 dark:text-ink-50 hover:text-brown-700 dark:hover:text-cream-200 transition-colors">
          <img :src="logoUrl" alt="PaperFull" class="h-7 w-7 rounded-md object-contain" />
          <span class="font-semibold">PaperFull</span>
        </router-link>

        <!-- Token quota bar -->
        <div v-if="quota.quota_monthly > 0" ref="quotaRef" class="relative" :title="`${formatNum(quota.used_month)} / ${formatNum(quota.quota_monthly)} token bulan ini`">
          <button type="button" class="flex items-center gap-2 px-3 py-1.5 min-h-[44px] min-w-[44px] rounded-lg bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600" aria-haspopup="dialog" :aria-expanded="quotaOpen" @click="quotaOpen = !quotaOpen" @focus="quotaOpen = true" @keydown.escape.stop="quotaOpen = false">
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
          </button>
          <!-- Tooltip: detail breakdown -->
          <div v-if="quotaOpen" role="dialog" class="absolute left-0 top-full mt-1 w-64 bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-lg shadow-lg p-3 z-50 text-xs" @keydown.escape.stop="quotaOpen = false">
            <div class="font-semibold text-ink-900 dark:text-ink-50 mb-1">Pemakaian token bulan {{ quota.month_key }}</div>
            <div class="grid grid-cols-2 gap-1 text-ink-600 dark:text-ink-300">
              <span>Hari ini</span><span class="text-right tabular-nums">{{ formatNum(quota.used_today) }}</span>
              <span>Bulan ini</span><span class="text-right tabular-nums">{{ formatNum(quota.used_month) }}</span>
              <span>Sisa</span><span class="text-right tabular-nums">{{ formatNum(quota.remaining) }}</span>
            </div>
          </div>
        </div>
        <div v-else-if="quota.is_unlimited" class="px-3 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 text-[11px] font-medium text-amber-800 dark:text-amber-200">
          ∞ admin
        </div>

        <nav class="hidden md:flex items-center gap-2 text-sm">
          <router-link to="/dashboard" class="px-3 py-1.5 min-h-[44px] min-w-[44px] flex items-center rounded-lg text-ink-700 dark:text-ink-100 hover:bg-cream-200 dark:hover:bg-ash-700 hover:text-ink-900 dark:hover:text-ink-50 transition-colors" active-class="bg-cream-300 dark:bg-ash-600 text-ink-900 dark:text-ink-50 font-semibold">
            Papers
          </router-link>
          <router-link v-if="auth.isAdmin" to="/admin" class="px-3 py-1.5 min-h-[44px] min-w-[44px] flex items-center rounded-lg text-ink-700 dark:text-ink-100 hover:bg-cream-200 dark:hover:bg-ash-700 hover:text-ink-900 dark:hover:text-ink-50 transition-colors" active-class="bg-cream-300 dark:bg-ash-600 text-ink-900 dark:text-ink-50 font-semibold">
            Admin
          </router-link>
        </nav>
      </div>

      <!-- User Menu -->
      <div class="flex items-center gap-2">
        <!-- Job inbox bell -->
        <div class="bell-wrap relative" ref="bellRef">
          <button @click="onBellClick"
            class="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center hover:bg-cream-100 dark:hover:bg-ash-700 rounded-lg relative"
            aria-haspopup="menu"
            :aria-expanded="bellOpen"
            :title="recentCount > 0 ? `${recentCount} paper baru selesai` : 'Belum ada paper baru selesai'">
            <svg class="w-5 h-5 text-ink-700 dark:text-ink-200" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/>
            </svg>
            <span v-if="recentCount > 0"
                  class="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-emerald-500 text-white text-[10px] font-bold">
              {{ recentCount > 99 ? '99+' : recentCount }}
            </span>
          </button>
          <div v-if="bellOpen"
               role="menu"
               class="absolute right-0 mt-2 w-72 bg-cream-50 dark:bg-ash-800 rounded-lg shadow-lg border border-cream-300 dark:border-ash-700 z-50">
            <div class="p-3 border-b border-cream-200 dark:border-ash-700 text-sm font-semibold text-ink-900 dark:text-ink-50">
              Recent generated papers
            </div>
            <div class="max-h-80 overflow-y-auto p-2">
              <div v-if="!recentDone.length" class="text-xs text-ink-500 dark:text-ink-300 p-3 text-center">
                Belum ada paper yang baru selesai.
              </div>
              <router-link v-for="j in recentDone" :key="j.id"
                 :to="{ name: 'editor', params: { paperId: j.paper_id } }"
                 @click="bellOpen = false"
                 class="block p-2 hover:bg-cream-100 dark:hover:bg-ash-700 rounded text-sm text-ink-800 dark:text-ink-100">
                <div class="font-medium truncate">{{ j.result?.partial_paper?.title || j.paper_title || 'Untitled' }}</div>
                <div class="text-[10px] text-ink-500 dark:text-ink-300">{{ formatTime(j.updated_at) }}</div>
              </router-link>
            </div>
          </div>
        </div>

        <div class="relative" ref="menuRef">
          <button @click="menuOpen = !menuOpen"
            class="flex items-center gap-2 px-3 py-1.5 min-h-[44px] rounded-xl hover:bg-cream-200 dark:hover:bg-ash-700 transition-colors text-sm text-ink-900 dark:text-ink-50"
            aria-haspopup="menu"
            :aria-expanded="menuOpen">
            <img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" class="w-7 h-7 rounded-full" alt="avatar" />
            <span v-else class="w-7 h-7 rounded-full bg-brown-500 dark:bg-brown-400 flex items-center justify-center text-cream-50 text-xs font-bold">
              {{ auth.user?.name?.[0]?.toUpperCase() || 'U' }}
            </span>
            <span class="hidden md:inline font-medium">{{ auth.user?.name || 'User' }}</span>
            <span class="text-ink-500 dark:text-ink-300">▾</span>
          </button>

          <!-- Dropdown -->
          <div v-if="menuOpen" role="menu" class="absolute right-0 top-full mt-1 w-56 bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-lg overflow-hidden z-50">
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
              <span aria-hidden="true">📄</span> My Papers
            </router-link>
            <router-link v-if="auth.isAdmin" to="/admin" @click="menuOpen = false" class="flex items-center gap-2 px-4 py-2.5 text-sm text-ink-800 dark:text-ink-100 hover:bg-cream-100 dark:hover:bg-ash-700 transition-colors">
              <span aria-hidden="true">📊</span> Admin
            </router-link>
            <div class="border-t border-cream-200 dark:border-ash-700">
              <button @click="doLogout" class="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors">
                <span aria-hidden="true">🚪</span> Sign Out
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useTheme } from '../stores/theme'
import { usePaperJobsStore } from '../stores/paperJobs'
import { useQuotaStore } from '../stores/quota'

const logoUrl = '/logo.png'

const auth = useAuthStore()
const router = useRouter()
const menuOpen = ref(false)
const quotaOpen = ref(false)
const bellOpen = ref(false)
const menuRef = ref<HTMLElement | null>(null)
const quotaRef = ref<HTMLElement | null>(null)
const bellRef = ref<HTMLElement | null>(null)

const { mode, setMode } = useTheme()

const jobsStore = usePaperJobsStore()
const recentDone = computed(() => jobsStore.recentDone)
const recentCount = computed(() => recentDone.value.length)

const quotaStore = useQuotaStore()
const quota = computed(() => quotaStore.quota)

function onBellClick(): void {
  bellOpen.value = !bellOpen.value
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ''
    return d.toLocaleString()
  } catch {
    return ''
  }
}

interface ThemeOption {
  value: 'light' | 'dark' | 'system'
  label: string
  icon: string
}

const themeOptions: ThemeOption[] = [
  { value: 'light',  label: 'Light',  icon: '☀️' },
  { value: 'dark',   label: 'Dark',   icon: '🌙' },
  { value: 'system', label: 'System', icon: '🖥️' },
]

function formatNum(n: number | string): string {
  if (typeof n !== 'number') n = Number(n) || 0
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k'
  return String(n)
}

function doLogout(): void {
  auth.logout()
  router.push('/login')
}

function handleOutsideClick(e: MouseEvent): void {
  const target = e.target as Node
  if (menuRef.value && !menuRef.value.contains(target)) {
    menuOpen.value = false
  }
  if (quotaRef.value && !quotaRef.value.contains(target)) {
    quotaOpen.value = false
  }
  if (bellRef.value && !bellRef.value.contains(target)) {
    bellOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  quotaStore.startPolling(60_000)
})
onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
  quotaStore.stopPolling()
})
</script>
