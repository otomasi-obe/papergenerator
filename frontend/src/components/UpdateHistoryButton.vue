<template>
  <!-- Inline button + dropdown panel -->
  <div class="relative" ref="rootRef">
    <button
      @click="togglePanel"
      class="flex items-center gap-1.5 px-3 py-1.5 min-h-[40px] rounded-lg bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600 text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 active:scale-95 transition text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50"
      :title="`Update v${currentVersion?.version || 'baru'}`"
      aria-label="Riwayat update"
      aria-haspopup="true"
      :aria-expanded="panelOpen"
    >
      <span>📋</span>
      <span class="hidden sm:inline">Update</span>
      <span v-if="hasUnseen" class="relative flex h-2 w-2">
        <span class="absolute inset-0 rounded-full bg-amber-400 animate-ping"></span>
        <span class="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
      </span>
    </button>

    <!-- Dropdown panel -->
    <transition
      enter-active-class="transition ease-out duration-200"
      enter-from-class="opacity-0 translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition ease-in duration-150"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-1"
    >
      <div
        v-if="panelOpen"
        class="absolute right-0 top-full mt-1 w-[360px] max-h-[70vh] flex flex-col rounded-xl border border-cream-300 dark:border-ash-600 bg-white/95 dark:bg-ash-800/95 backdrop-blur-xl shadow-2xl overflow-hidden z-50"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-2.5 bg-cream-50 dark:bg-ash-700 border-b border-cream-200 dark:border-ash-600 shrink-0">
          <div class="flex items-center gap-2">
            <span class="text-sm">📋</span>
            <span class="text-sm font-bold text-ink-900 dark:text-ink-50">Riwayat Update</span>
            <span class="text-[11px] text-ink-600 dark:text-ink-300">{{ versions.length }} versi</span>
          </div>
          <button @click="closePanel" class="p-1 rounded text-ink-500 dark:text-ink-400 hover:text-ink-900 dark:hover:text-ink-50 hover:bg-cream-200 dark:hover:bg-ash-600 transition" aria-label="Tutup">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 min-h-0 overflow-y-auto p-2.5 space-y-2">
          <div v-for="v in versions" :key="v.version" class="bg-cream-50 dark:bg-ash-700/50 rounded-lg border border-cream-200 dark:border-ash-600 p-2.5">
            <div class="flex items-start justify-between gap-2 mb-1.5">
              <div class="flex items-center gap-2">
                <span class="px-1.5 py-0.5 text-[10px] font-bold rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400">v{{ v.version }}</span>
                <span class="text-sm font-semibold text-ink-900 dark:text-ink-50">{{ v.title || `v${v.version}` }}</span>
              </div>
              <span class="text-[10px] text-ink-600 dark:text-ink-300 whitespace-nowrap">{{ formatDate(v.released) }}</span>
            </div>
            <ul v-if="v.changes?.length" class="space-y-1 pl-1">
              <li v-for="(c, i) in v.changes" :key="i" class="flex items-start gap-2 text-xs leading-relaxed text-ink-800 dark:text-ink-200">
                <span :class="badgeClass(c.type)" class="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase flex-shrink-0 mt-0.5">
                  {{ c.type === 'new' ? '✦ NEW' : c.type === 'fix' ? '🔧 FIX' : '⚡ UPD' }}
                </span>
                <span>{{ c.text }}</span>
              </li>
            </ul>
          </div>
          <div v-if="!versions.length" class="text-center py-6 text-ink-600 dark:text-ink-300 text-sm">Belum ada riwayat update</div>
        </div>

        <!-- Footer -->
        <div class="px-3 py-2 bg-cream-50 dark:bg-ash-700 border-t border-cream-200 dark:border-ash-600 shrink-0 flex items-center justify-between">
          <span class="text-[10px] text-ink-600 dark:text-ink-300">Dicek: {{ lastChecked }}</span>
          <button @click="refresh" class="text-[11px] font-medium text-[var(--accent)] hover:underline" :disabled="loading">{{ loading ? 'Memuat...' : 'Cek ulang' }}</button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'

interface Change { type: 'new' | 'fix' | 'improvement'; text: string }
interface Version { version: string; released: string; title: string; changes: Change[] }

const panelOpen = ref(false)
const versions = ref<Version[]>([])
const loading = ref(false)
const lastChecked = ref('')
const rootRef = ref<HTMLElement | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const LS_KEY = 'pf_update_versions_seen'

function badgeClass(type: string) {
  if (type === 'new') return 'bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300'
  if (type === 'fix') return 'bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300'
  return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
}

function formatDate(s?: string) {
  if (!s) return ''
  return new Date(s).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' })
}

async function loadVersions() {
  loading.value = true
  try {
    const res = await fetch('/api/version?t=' + Date.now())
    if (res.ok) {
      const data = await res.json()
      if (data?.history?.length) versions.value = data.history
      else if (data?.version) versions.value = [data]
    }
    lastChecked.value = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function togglePanel() {
  if (!panelOpen.value) loadVersions()
  panelOpen.value = !panelOpen.value
}

function closePanel() {
  panelOpen.value = false
}

function refresh() {
  loadVersions()
}

function onClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    closePanel()
  }
}

const currentVersion = computed(() => versions.value[0] || null)

const hasUnseen = computed(() => {
  if (!currentVersion.value) return false
  try {
    const seen = localStorage.getItem(LS_KEY) || ''
    return seen !== currentVersion.value.version
  } catch {
    return true
  }
})

onMounted(() => {
  loadVersions()
  document.addEventListener('click', onClickOutside)
  // Auto-poll setiap 30s untuk cek versi baru
  pollTimer = setInterval(loadVersions, 30_000)
})

onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  if (pollTimer) clearInterval(pollTimer)
})

function markAllSeen() {
  if (currentVersion.value) {
    try {
      localStorage.setItem(LS_KEY, currentVersion.value.version)
    } catch {}
  }
}

defineExpose({ markAllSeen })
</script>
