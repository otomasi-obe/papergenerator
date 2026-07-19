<template>
 <header class="bg-gradient-to-b from-cream-200/90 via-cream-300/80 to-cream-200/70 dark:from-[#0c1628]/95 dark:via-[#1a4470]/80 dark:to-[#0c1628]/90 backdrop-blur-xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_4px_16px_rgba(0,0,0,0.04)] dark:shadow-[0_1px_3px_rgba(0,0,0,0.3),0_4px_16px_rgba(0,0,0,0.2)] border-b border-cream-300/60 dark:border-white/[0.08] sticky top-0 z-40 transition-colors duration-200">
 <div class="w-full max-w-6xl mx-auto px-4 lg:px-8 py-3 flex items-center justify-between">
 <!-- Logo + Nav -->
 <div class="flex items-center gap-4">
 <router-link to="/dashboard" class="flex items-center gap-2 min-h-[44px] min-w-[44px] text-ink-900 dark:text-ink-50 hover:text-navy-700 dark:hover:text-[#6db4f0] transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2 rounded-lg">
 <img :src="logoUrl" alt="PaperFull" class="h-7 w-7 rounded-md object-contain" />
 <span class="font-semibold font-serif">PaperFull</span>
 </router-link>
 <nav class="hidden md:flex items-center gap-2 text-sm">
 <router-link v-if="auth.isAdmin" to="/admin" class="px-3 py-1.5 min-h-[44px] min-w-[44px] flex items-center rounded-lg text-ink-700 dark:text-ink-100 hover:bg-cream-200 dark:hover:bg-ash-700 hover:text-ink-900 dark:hover:text-ink-50 transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2" active-class="bg-cream-300 dark:bg-ash-600 text-ink-900 dark:text-ink-50 font-semibold">
 Admin
 </router-link>
 </nav>
 </div>

 <!-- User Menu -->
 <div class="flex items-center gap-2">
 <UpdateHistoryButton />

 <div v-if="quota.quota_monthly > 0" ref="quotaRef" class="relative" :title="`${formatNum(quota.used_month)} / ${formatNum(quota.quota_monthly)} token bulan ini`">
 <button type="button" class="flex items-center gap-1.5 px-2.5 py-1.5 min-h-[36px] rounded-lg bg-cream-100 dark:bg-ash-700 hover:bg-cream-200 dark:hover:bg-ash-700 active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2 transition" aria-haspopup="dialog" :aria-expanded="quotaOpen" @mouseenter="quotaOpen = true" @mouseleave="quotaOpen = false" @focus="quotaOpen = true" @blur="quotaOpen = false" @keydown.escape.stop="quotaOpen = false" @click="detailModalOpen = true">
 <div class="w-16 h-1.5 rounded-full bg-cream-300 dark:bg-ash-600 overflow-hidden">
 <div class="h-full transition-all" :class="quota.percent >= 90 ? 'bg-red-500' : quota.percent >= 70 ? 'bg-amber-500' : 'bg-emerald-500'" :style="{ width: Math.min(100, quota.percent) + '%' }"></div>
 </div>
 <span class="text-[11px] font-mono tabular-nums text-ink-600 dark:text-ink-300">{{ formatNum(quota.remaining) }} token</span>
 </button>
 <div v-if="quotaOpen" role="dialog" class="absolute right-0 top-full mt-1 w-64 bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-lg p-3 z-50 text-xs" @mouseenter="quotaOpen = true" @mouseleave="quotaOpen = false" @keydown.escape.stop="quotaOpen = false">
 <div class="font-semibold text-ink-900 dark:text-ink-50 mb-1">Token usage for {{ quota.month_key }}</div>
 <div class="grid grid-cols-2 gap-1 text-ink-600 dark:text-[#fef08a]">
 <span>Today</span><span class="text-right tabular-nums">{{ formatNum(quota.used_today) }}</span>
 <span>This month</span><span class="text-right tabular-nums">{{ formatNum(quota.used_month) }}</span>
 <span>Remaining</span><span class="text-right tabular-nums">{{ formatNum(quota.remaining) }}</span>
 </div>
 <div v-if="quota.input_tokens || quota.output_tokens" class="mt-2 pt-2 border-t border-cream-300 dark:border-ash-600">
 <div class="font-semibold text-ink-900 dark:text-ink-50 mb-1">Input / Output breakdown</div>
 <div class="grid grid-cols-2 gap-1 text-ink-600 dark:text-[#fef08a]">
 <span>Input</span><span class="text-right tabular-nums">{{ formatNum(quota.input_tokens || 0) }}</span>
 <span>Output</span><span class="text-right tabular-nums">{{ formatNum(quota.output_tokens || 0) }}</span>
 </div>
 </div>
 </div>
 </div>
 <div v-else-if="quota.is_unlimited" class="px-3 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 text-[11px] font-medium text-amber-800 dark:text-amber-200">∞ admin</div>

 <button @click="purchaseModalOpen = true" class="flex items-center gap-1.5 px-2.5 py-1.5 min-h-[36px] rounded-lg bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600 text-ink-700 dark:text-[#fef9c3] hover:bg-cream-200 dark:hover:bg-ash-700 text-xs font-medium transition-all active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
 Pricing
 </button>

 <div class="bell-wrap relative" ref="bellRef">
 <button @click="onBellClick" class="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center hover:bg-cream-100 dark:hover:bg-ash-700 rounded-lg relative active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2" aria-haspopup="menu" :aria-expanded="bellOpen" :title="recentCount > 0 ? `${activeJobs.length} diproses, ${failedJobs.length} gagal, ${recentDone.length} selesai` : 'Belum ada paper yang diproses'">
 <svg class="w-5 h-5 text-ink-700 dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>
 <span v-if="recentCount > 0" class="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-emerald-500 text-white text-[10px] font-bold">{{ recentCount > 99 ? '99+' : recentCount }}</span>
 </button>
 <div v-if="bellOpen" role="menu" class="absolute right-0 mt-2 w-80 bg-cream-50 dark:bg-ash-800 rounded-xl shadow-lg border border-cream-300 dark:border-ash-700 z-50">
 <div class="p-3 border-b border-cream-200 dark:border-ash-700 text-sm font-semibold text-ink-900 dark:text-ink-50">Paper Jobs</div>
 <div class="max-h-80 overflow-y-auto p-2">
 <div v-if="streamState && streamState.generating" class="mb-2">
 <div class="px-2 py-1 text-[10px] uppercase tracking-wider text-ink-500 dark:text-[#fef08a] font-semibold">Streaming</div>
 <div class="block p-2 rounded-lg text-sm bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700 mb-1 cursor-pointer hover:bg-emerald-100 dark:hover:bg-emerald-800/30" @click="navigateToStreamPaper">
 <div class="flex items-center gap-2">
 <span class="inline-block w-3 h-3 border-2 border-emerald-300 border-t-emerald-600 dark:border-t-emerald-300 rounded-full animate-spin shrink-0"></span>
 <div class="font-medium truncate text-emerald-800 dark:text-emerald-200 flex-1">{{ streamState.generatingTopic || 'Generating...' }}</div>
 </div>
 <div class="mt-1 flex items-center gap-2">
 <div class="flex-1 h-1.5 rounded-full bg-emerald-200 dark:bg-emerald-800 overflow-hidden"><div class="h-full bg-emerald-500 dark:bg-emerald-400 transition-all" :style="{ width: (streamState.displayProgress || 0) + '%' }"></div></div>
 <span class="text-[10px] text-emerald-600 dark:text-emerald-400 tabular-nums shrink-0">{{ streamState.displayProgress || 0 }}%</span>
 </div>
 <div class="text-[10px] text-emerald-600 dark:text-emerald-400 mt-1 truncate">{{ streamState.prompt || '' }}</div>
 </div>
 </div>
 <div v-if="activeJobs.length" class="mb-2">
 <div class="px-2 py-1 text-[10px] uppercase tracking-wider text-ink-500 dark:text-[#fef08a] font-semibold">Sedang diproses</div>
 <div v-for="j in activeJobs" :key="'active-' + j.id" class="block p-2 rounded-lg text-sm bg-navy-50 dark:bg-navy-900/30 border border-navy-200 dark:border-navy-700 mb-1" :class="j.paper_id ? 'cursor-pointer hover:bg-navy-100 dark:hover:bg-navy-800/40' : ''" @click="j.paper_id && navigateToPaper(j.paper_id)">
 <div class="flex items-center gap-2">
 <span class="inline-block w-3 h-3 border-2 border-navy-300 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin shrink-0"></span>
 <div class="font-medium truncate text-navy-800 dark:text-navy-200 flex-1">{{ j.result?.partial_paper?.title || j.paper_title || 'Generating...' }}</div>
 </div>
 <div class="mt-1 flex items-center gap-2">
 <div class="flex-1 h-1.5 rounded-full bg-navy-200 dark:bg-navy-800 overflow-hidden"><div class="h-full bg-navy-500 dark:bg-cream-300 transition-all" :style="{ width: (j.progress || 0) + '%' }"></div></div>
 <span class="text-[10px] text-navy-600 dark:text-navy-400 tabular-nums shrink-0">{{ j.progress || 0 }}%</span>
 </div>
 <div class="text-[10px] text-navy-600 dark:text-navy-400 mt-1 truncate">{{ j.prompt || '' }}</div>
 </div>
 </div>
 <div v-if="failedJobs.length" class="mb-2">
 <div class="px-2 py-1 flex items-center justify-between">
 <span class="text-[10px] uppercase tracking-wider text-red-500 dark:text-red-400 font-semibold">Gagal</span>
 <button v-if="failedJobs.length > 1" @click.stop="jobsStore.clearAllFailedJobs()" class="text-[10px] text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition" title="Hapus semua notifikasi gagal">Hapus semua</button>
 </div>
 <div v-for="j in failedJobs" :key="'failed-' + j.id" class="group flex items-center gap-1 p-2 rounded-lg text-sm bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 mb-1 cursor-pointer hover:bg-red-100 dark:hover:bg-red-800/30" @click="onFailedJobClick(j)">
 <div class="flex-1 min-w-0">
 <div class="flex items-center gap-2">
 <span class="text-red-600 dark:text-red-400 shrink-0">✗</span>
 <div class="font-medium truncate text-red-800 dark:text-red-200 flex-1">{{ j.result?.partial_paper?.title || j.paper_title || 'Generating...' }}</div>
 </div>
 <div class="text-[10px] text-red-600 dark:text-red-400 mt-1 truncate">{{ j.error || j.prompt || 'Error' }}</div>
 <div class="text-[10px] text-red-500 dark:text-red-500 mt-0.5">{{ formatTime(j.updated_at) }}</div>
 </div>
 <button @click.stop="jobsStore.dismissFailedJob(j.id)" class="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-200 dark:hover:bg-red-800 rounded shrink-0" title="Hapus notifikasi"><svg class="w-3.5 h-3.5 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button>
 </div>
 </div>
 <div v-if="recentDone.length">
 <div class="px-2 py-1 text-[10px] uppercase tracking-wider text-ink-500 dark:text-[#fef08a] font-semibold">Selesai</div>
 <template v-for="j in recentDone" :key="j.id">
 <router-link v-if="j && j.paper_id" :to="{ name: 'editor', params: { paperId: j.paper_id } }" @click="onJobClick(j.id)" class="block p-2 hover:bg-cream-100 dark:hover:bg-ash-700 rounded-lg text-sm text-ink-800 dark:text-ink-100 active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
 <div class="flex items-center gap-2"><span class="text-emerald-600 dark:text-emerald-400 shrink-0">✓</span><div class="font-medium truncate">{{ j.result?.partial_paper?.title || j.paper_title || 'Untitled' }}</div></div>
 <div class="text-[10px] text-ink-500 dark:text-[#fef08a] ml-5">{{ formatTime(j.updated_at) }}</div>
 </router-link>
 </template>
 </div>
 <div v-if="!activeJobs.length && !failedJobs.length && !recentDone.length" class="text-xs text-ink-500 dark:text-[#fef08a] p-3 text-center">Belum ada paper yang diproses.</div>
 </div>
 </div>
 </div>

 <!-- User dropdown + Dev button -->
 <div class="flex items-center gap-2">
 <div class="relative" ref="menuRef">
 <button @click="menuOpen = !menuOpen" aria-haspopup="menu" :aria-expanded="menuOpen" class="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center hover:bg-cream-100 dark:hover:bg-ash-700 rounded-lg relative active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2 transition">
 <div class="flex items-center gap-1.5">
   <img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" class="w-8 h-8 rounded-full object-cover" alt="avatar" />
   <span v-else class="w-8 h-8 rounded-full bg-navy-500 dark:bg-navy-400 flex items-center justify-center text-cream-50 text-sm font-bold">{{ auth.user?.name?.[0]?.toUpperCase() || 'U' }}</span>
   <BadgeTier v-if="auth.user?.badge" :badge="auth.user.badge" size="sm" class="ring-2 ring-cream-100 dark:ring-ash-900" />
 </div>
 <svg class="w-3.5 h-3.5 ml-1.5 text-ink-400 dark:text-[#fef08a]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M19 9l-7 7-7-7"/></svg>
 </button>
 <div v-if="menuOpen" role="menu" class="absolute right-0 top-full mt-1 w-64 bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-lg overflow-hidden z-50" tabindex="-1">
 <div class="px-4 py-3 border-b border-cream-200 dark:border-ash-700">
 <p class="text-sm font-medium text-ink-900 dark:text-ink-50">{{ auth.user?.name }}</p>
 <p class="text-xs text-ink-600 dark:text-[#fef08a]">{{ auth.user?.email }}</p>
 <div class="flex items-center gap-2 mt-2 flex-wrap">
 <span v-if="auth.isAdmin" class="text-xs bg-navy-200 dark:bg-ash-700 text-ink-900 dark:text-ink-50 px-1.5 py-0.5 rounded-full">Admin</span>
 <BadgeTier v-if="auth.isDeveloper || auth.user?.email === 'anabilhisyam23@gmail.com'" badge="developer" size="sm" />
 <BadgeTier v-if="auth.user?.badge" :badge="auth.user.badge" size="sm" />
 </div>
 </div>
 <div v-if="auth.user?.badge && BADGE_TIERS[auth.user.badge]" class="px-4 py-3 border-b border-cream-200 dark:border-ash-700">
 <div class="text-[10px] uppercase tracking-wider text-ink-500 dark:text-[#fef08a] font-semibold mb-1.5">Benefit {{ BADGE_TIERS[auth.user.badge].label }}</div>
 <ul class="text-xs text-ink-600 dark:text-ink-200 space-y-1">
 <li v-for="b in BADGE_TIERS[auth.user.badge].benefits" :key="b" class="flex items-start gap-1.5"><svg class="w-3.5 h-3.5 text-emerald-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg><span>{{ b }}</span></li>
 </ul>
 <div class="mt-2 pt-2 border-t border-cream-200 dark:border-ash-700">
 <div class="text-[10px] uppercase tracking-wider text-ink-500 dark:text-[#fef08a] font-semibold mb-1.5">Image Generation</div>
 <ul class="text-xs text-ink-600 dark:text-ink-200 space-y-1">
 <li v-for="m in BADGE_TIERS[auth.user.badge].imageModels" :key="m" class="flex items-center gap-1.5"><svg class="w-3.5 h-3.5 text-blue-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg><span>{{ m }}</span></li>
 </ul>
 <p class="mt-1 text-[10px] text-ink-500 dark:text-ink-400">{{ BADGE_TIERS[auth.user.badge].imageQuality }}</p>
 </div>
 <div v-if="auth.user?.badge_expires_at && auth.user.badge !== 'trial'" class="mt-2 text-[10px] text-ink-500 dark:text-ink-400">Berlaku sampai: {{ formatDate(auth.user.badge_expires_at) }}</div>
 </div>
 <div class="px-3 py-2.5 border-b border-cream-200 dark:border-ash-700">
 <div class="text-[11px] uppercase tracking-wider text-ink-500 dark:text-[#fef08a] font-semibold mb-1.5 px-1">Theme</div>
 <div class="grid grid-cols-3 gap-1 bg-cream-100 dark:bg-ash-700 p-1 rounded-lg">
 <button v-for="opt in themeOptions" :key="opt.value" @click="setMode(opt.value)" :class="['flex items-center justify-center gap-1 py-1.5 rounded-md text-[11px] font-medium transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2', mode === opt.value ? 'bg-cream-50 dark:bg-ash-850 text-ink-900 dark:text-ink-50 shadow-sm border border-cream-300 dark:border-ash-600' : 'text-ink-600 dark:text-[#fef08a] hover:text-ink-900 dark:hover:text-ink-50']" :title="opt.label"><span aria-hidden="true">{{ opt.icon }}</span><span class="hidden xs:inline">{{ opt.label }}</span></button>
 </div>
 </div>
 <router-link to="/dashboard" @click="menuOpen = false" class="flex items-center gap-2 px-4 py-2.5 text-sm text-ink-800 dark:text-ink-100 hover:bg-cream-100 dark:hover:bg-ash-700 transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"><span aria-hidden="true">📄</span> My Papers</router-link>
 <router-link to="/settings" @click="menuOpen = false" class="flex items-center gap-2 px-4 py-2.5 text-sm text-ink-800 dark:text-ink-100 hover:bg-cream-100 dark:hover:bg-ash-700 transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"><span aria-hidden="true">⚙️</span> Settings</router-link>
 <router-link v-if="auth.isAdmin" to="/admin" @click="menuOpen = false" class="flex items-center gap-2 px-4 py-2.5 text-sm text-ink-800 dark:text-ink-100 hover:bg-cream-100 dark:hover:bg-ash-700 transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"><span aria-hidden="true">📊</span> Admin</router-link>
 <div class="border-t border-cream-200 dark:border-ash-700">
 <button @click="doLogout" class="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"><span aria-hidden="true">🚪</span> Sign Out</button>
 </div>
 </div>
 </div>

 <!-- Dev button: kanan dari dropdown user -->
 <router-link v-if="auth.isDeveloper" to="/developer" class="dev-btn flex items-center justify-center gap-1.5 p-2 min-h-[44px] min-w-[44px] rounded-lg transition-all duration-150 active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
 <span aria-hidden="true">🛠️</span> <span class="hidden sm:inline text-sm font-medium">Dev</span>
 </router-link>
 </div>
 </div>
 </div>
 </header>
 <Teleport to="body">
 <TokenPurchaseModal :isOpen="purchaseModalOpen" @close="purchaseModalOpen = false" />
 <TokenDetailModal :open="detailModalOpen" @close="detailModalOpen = false" @buy-tokens="detailModalOpen = false; purchaseModalOpen = true" />
 </Teleport>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useTheme } from '../stores/theme'
import { usePaperJobsStore } from '../stores/paperJobs'
import { useQuotaStore } from '../stores/quota'
import TokenPurchaseModal from './TokenPurchaseModal.vue'
import TokenDetailModal from './TokenDetailModal.vue'
import UpdateHistoryButton from './UpdateHistoryButton.vue'
import BadgeTier from './BadgeTier.vue'
import { BADGE_TIERS } from '../config/badgeTiers'

const logoUrl = '/assets/logo.png'
const auth = useAuthStore()
const router = useRouter()
const menuOpen = ref(false)
const quotaOpen = ref(false)
const bellOpen = ref(false)
const purchaseModalOpen = ref(false)
const detailModalOpen = ref(false)
const menuRef = ref<HTMLElement | null>(null)
const quotaRef = ref<HTMLElement | null>(null)
const bellRef = ref<HTMLElement | null>(null)

const { mode, setMode } = useTheme()
const jobsStore = usePaperJobsStore()
const recentDone = computed(() => {
 void jobsStore._clickedTick
 const clicked = jobsStore.clickedJobIds
 return jobsStore.recentDone.filter(j => !clicked.has(j.id))
})
const activeJobs = computed(() => jobsStore.globalActiveJobs || [])
const failedJobs = computed(() => jobsStore.failedJobs || [])
const streamState = computed(() => jobsStore.streamState)
const recentCount = computed(() => recentDone.value.length + activeJobs.value.length + failedJobs.value.length + (streamState.value?.generating ? 1 : 0))
const quotaStore = useQuotaStore()
const quota = computed(() => quotaStore.quota)

function onBellClick(): void { bellOpen.value = !bellOpen.value }
function navigateToPaper(paperId: string): void { bellOpen.value = false; router.push({ name: 'editor', params: { paperId } }) }
function onJobClick(jobId: string): void { jobsStore.markJobAsClicked(jobId); bellOpen.value = false }
function onFailedJobClick(job: any): void {
 jobsStore.markJobAsClicked(job.id); bellOpen.value = false
 if (job.paper_id) router.push({ name: 'editor', params: { paperId: job.paper_id } })
}
function navigateToStreamPaper(): void {
 bellOpen.value = false
 const ss = jobsStore.streamState
 if (ss?.paperId) router.push({ name: 'editor', params: { paperId: ss.paperId }, query: { panel: 'paperfull' } })
}
function formatTime(iso: string | null | undefined): string {
 if (!iso) return ''
 try { const d = new Date(iso); return Number.isNaN(d.getTime()) ? '' : d.toLocaleString() } catch { return '' }
}
function formatDate(iso: string | null | undefined): string {
 if (!iso) return ''
 try { const d = new Date(iso); return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('id-ID', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' }) } catch { return '' }
}
interface ThemeOption { value: 'light' | 'dark' | 'system'; label: string; icon: string }
const themeOptions: ThemeOption[] = [
 { value: 'light', label: 'Light', icon: '☀️' },
 { value: 'dark', label: 'Dark', icon: '🌙' },
 { value: 'system', label: 'System', icon: '🖥️' },
]
function formatNum(n: number | string): string { return Number(n || 0).toLocaleString('id-ID') }
function doLogout(): void { auth.logout(); router.push('/login') }
function handleOutsideClick(e: MouseEvent): void {
 const target = e.target as Node
 if (menuRef.value && !menuRef.value.contains(target)) menuOpen.value = false
 if (quotaRef.value && !quotaRef.value.contains(target)) quotaOpen.value = false
 if (bellRef.value && !bellRef.value.contains(target)) bellOpen.value = false
}
onMounted(() => { document.addEventListener('click', handleOutsideClick); quotaStore.startPolling(60_000) })
onUnmounted(() => { document.removeEventListener('click', handleOutsideClick); quotaStore.stopPolling() })
</script>