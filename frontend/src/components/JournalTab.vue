<template>
  <div class="max-w-3xl">
    <div class="bg-white dark:bg-ash-700 rounded-2xl border border-ivory-300 dark:border-ash-500 shadow-sm p-6">
      <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50 font-serif flex items-center gap-2"><svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>Journal</h2>
      <p class="text-sm text-ink-700 dark:text-ash-300 mt-1">
        Pilih jurnal/template tujuan untuk export DOCX. Gunakan kotak pencarian untuk menyaring.
      </p>

      <div class="mt-5">
        <label class="block text-sm font-medium text-ink-900 dark:text-ink-50 mb-2">Export format</label>

        <!-- Search + selected pill -->
        <div class="relative max-w-md" ref="wrapRef">
          <div class="flex items-center gap-2 mb-1.5">
            <span class="text-xs text-ink-700 dark:text-ash-300">Saat ini:</span>
            <span class="px-2 py-0.5 rounded-md text-xs font-semibold bg-ivory-200 dark:bg-ash-600 text-ink-900 dark:text-ink-50">
              {{ displayJournal }}
            </span>
          </div>
          <label for="journal-search" class="sr-only">Cari jurnal</label>
          <input
            id="journal-search"
            v-model="search"
            @focus="open = true"
            @input="open = true"
            @keydown.escape="open = false"
            @keydown.down.prevent="moveHighlight(1)"
            @keydown.up.prevent="moveHighlight(-1)"
            @keydown.enter.prevent="pickHighlighted"
            type="text"
            role="combobox"
            :aria-expanded="open"
            aria-controls="journal-list"
            aria-haspopup="listbox"
            placeholder="🔍 Cari jurnal (contoh: IEEE, JOKI, JNTETI…)"
            class="w-full px-3 py-2 border border-ivory-300 dark:border-ash-500 rounded-xl text-sm bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 placeholder-ivory-500 dark:placeholder-ash-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 focus:border-navy-500 dark:focus:border-navy-400 outline-none"
            :disabled="store.journalsLoading"
          />

          <ul v-if="open && filtered.length"
            id="journal-list"
            role="listbox"
            class="absolute z-50 mt-1 w-full bg-white dark:bg-ash-700 border border-ivory-300 dark:border-ash-500 rounded-xl shadow-lg max-h-72 overflow-y-auto text-sm">
            <li
              v-for="(j, idx) in filtered"
              :key="j"
              @click="!isLocked(j) && pick(j)"
              role="option"
              :aria-selected="store.paper.journal === j"
              :class="[
                'px-3 py-2 flex items-center justify-between transition-colors',
                isLocked(j)
                  ? 'cursor-not-allowed opacity-50'
                  : 'cursor-pointer',
                store.paper.journal === j || highlightedIndex === idx ? 'bg-ivory-200 dark:bg-ash-600 font-medium text-ink-900 dark:text-ink-50' : 'text-ink-800 dark:text-ash-100 hover:bg-ivory-100 dark:hover:bg-ash-600',
              ]"
            >
              <span class="flex items-center gap-2">
                <span>{{ j }}</span>
                <span :class="['text-[10px] px-1.5 py-0.5 rounded-full font-semibold', tierStyle(j)]" :title="`Tier: ${tierLabel(j)}`">
                  {{ tierShort(j) }}
                </span>
              </span>
              <span class="flex items-center gap-1">
                <span v-if="isLocked(j)" class="text-xs">🔒</span>
                <span v-if="store.paper.journal === j" class="text-ink-700 dark:text-ash-100 text-xs">✓ active</span>
              </span>
            </li>
          </ul>

          <p v-if="open && search && filtered.length === 0" class="absolute mt-1 text-xs text-ink-700 dark:text-ash-300">
            Tidak ada jurnal yang cocok dengan "<strong>{{ search }}</strong>"
          </p>
        </div>

        <!-- MDPI Sub-Journal Dropdown -->
        <div v-if="isMDPI" class="mt-4">
          <label class="block text-sm font-medium text-ink-900 dark:text-ink-50 mb-2">
            🏷️ Pilih Jurnal Spesifik MDPI ({{ store.mdpiSubJournals.length }} tersedia)
          </label>
          <div class="relative max-w-md" ref="mdpiWrapRef">
            <input
              v-model="mdpiSearch"
              @focus="mdpiOpen = true"
              @input="mdpiOpen = true"
              @keydown.escape="mdpiOpen = false"
              @keydown.down.prevent="moveMdpiHighlight(1)"
              @keydown.up.prevent="moveMdpiHighlight(-1)"
              @keydown.enter.prevent="pickMdpiHighlighted"
              type="text"
              placeholder="🔍 Cari jurnal MDPI (contoh: energies, ijms, sensors…)"
              class="w-full px-3 py-2 border border-[#238f7f]/30 dark:border-[#4eb2a3]/30 rounded-xl text-sm bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 placeholder-ivory-500 dark:placeholder-ash-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 focus:border-[#238f7f] dark:focus:border-[#4eb2a3] outline-none"
              :disabled="store.mdpiSubJournalsLoading"
            />

            <ul v-if="mdpiOpen && filteredMdpi.length"
              id="mdpi-journal-list"
              role="listbox"
              class="absolute z-50 mt-1 w-full bg-white dark:bg-ash-700 border border-[#238f7f]/30 dark:border-[#4eb2a3]/30 rounded-xl shadow-lg max-h-72 overflow-y-auto text-sm">
              <li
                              v-for="(j, idx) in filteredMdpi"
                              :key="j.key"
                              @click="pickMdpi(j)"
                              role="option"
                              :aria-selected="store.paper.mdpiJournal === j.key"
                              :class="[
                                'px-3 py-2 flex items-center justify-between transition-colors cursor-pointer',
                                store.paper.mdpiJournal === j.key || mdpiHighlightedIndex === idx ? 'bg-ivory-200 dark:bg-ash-600 font-medium text-ink-900 dark:text-ink-50' : 'text-ink-800 dark:text-ash-100 hover:bg-ivory-100 dark:hover:bg-ash-600',
                              ]"
                            >
                <div>
                  <span class="font-medium">{{ j.short_name }}</span>
                  <span class="text-xs text-ink-700 dark:text-ash-300 ml-2">({{ j.year }}, Vol. {{ j.volume }})</span>
                </div>
                <span v-if="isMdpiSelected(j)" class="text-[#238f7f] dark:text-[#4eb2a3] text-xs">✓ active</span>
              </li>
            </ul>

            <p v-if="mdpiOpen && mdpiSearch && filteredMdpi.length === 0" class="absolute mt-1 text-xs text-ink-700 dark:text-ash-300">
              Tidak ada jurnal MDPI yang cocok dengan "<strong>{{ mdpiSearch }}</strong>"
            </p>
          </div>
        </div>

        <p class="text-xs text-ink-700 dark:text-ash-300 mt-3">
          Pilihan ini menentukan template generator yang dipakai saat klik "Export DOCX".
        </p>

        <!-- Citation Style Selector -->
        <div class="mt-6">
          <label class="block text-sm font-medium text-ink-900 dark:text-ink-50 mb-2">Gaya Sitasi</label>
          <select
            v-model="store.paper.citation_style"
            class="max-w-md w-full px-3 py-2 border border-ivory-300 dark:border-ash-500 rounded-xl text-sm bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 focus:border-navy-500 dark:focus:border-navy-400 outline-none"
          >
            <option value="ieee">IEEE — Nomor dalam kurung [1,2]</option>
            <option value="apa">APA 7th — Author (Year)</option>
            <option value="mla">MLA 9th — Author Page</option>
            <option value="chicago">Chicago 17th — Author-Year</option>
            <option value="harvard">Harvard — Author (Year)</option>
            <option value="vancouver">Vancouver — Nomor berurutan (medis)</option>
            <option value="acs">ACS — Nomor superscript [1,2]</option>
          </select>
          <p class="text-xs text-ink-700 dark:text-ash-300 mt-2">
                    Gaya sitasi menentukan format referensi dalam teks dan daftar pustaka.
                  </p>
        </div>

        <!-- Language Selector -->
        <div class="mt-6">
          <label class="block text-sm font-medium text-ink-900 dark:text-ink-50 mb-2">🌐 Bahasa Paper</label>
          <select
            v-model="store.paper.language"
            class="max-w-md w-full px-3 py-2 border border-ivory-300 dark:border-ash-500 rounded-xl text-sm bg-white dark:bg-ash-700 text-ink-900 dark:text-ink-50 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 focus:border-navy-500 dark:focus:border-navy-400 outline-none"
          >
            <option value="id">🇮🇩 Bahasa Indonesia</option>
            <option value="en">🔤 English</option>
          </select>
          <p class="text-xs text-ink-700 dark:text-ash-300 mt-2">
            Bahasa untuk penulisan paper dan respons chat. Diskusi tetap bisa dalam bahasa apapun — editor output akan mengikuti pilihan ini.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { usePaperStore } from '../stores/paper'
import { useToolsStore } from '../stores/tools'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'
import { journalTier, isJournalUnlocked, TIER_BADGE_STYLE, TIER_SHORT, type BadgeKey } from '../config/badgeTiers'

const store = usePaperStore()
const toolsStore = useToolsStore()
const uiStore = useUiStore()
const authStore = useAuthStore()

const userBadge = computed<BadgeKey | undefined>(() => authStore.user?.badge as BadgeKey | undefined)

function isLocked(j: string): boolean {
  return !isJournalUnlocked(j, userBadge.value)
}
function tierStyle(j: string): string {
  return TIER_BADGE_STYLE[journalTier(j)]
}
function tierShort(j: string): string {
  return TIER_SHORT[journalTier(j)]
}
function tierLabel(j: string): string {
  return journalTier(j).charAt(0).toUpperCase() + journalTier(j).slice(1)
}

const search = ref<string>('')
const open = ref<boolean>(false)
const wrapRef = ref<HTMLElement | null>(null)
const highlightedIndex = ref<number>(-1)

// MDPI sub-journals
const mdpiSearch = ref<string>('')
const mdpiOpen = ref<boolean>(false)
const mdpiWrapRef = ref<HTMLElement | null>(null)
const mdpiHighlightedIndex = ref<number>(-1)

const isMDPI = computed<boolean>(() => {
  const j = store.paper.journal || ''
  return j === 'MDPI' || j.startsWith('MDPI_')
})

const displayJournal = computed<string>(() => {
  const j = store.paper.journal || 'IEEE'
  if (j.startsWith('MDPI_')) {
    const subKey = j.substring(5)
    const sub = store.mdpiSubJournals.find((s: any) => s.key === subKey)
    if (sub) return `MDPI ${sub.short_name}`
    return j
  }
  return j
})

const filtered = computed<string[]>(() => {
  if (!search.value.trim()) return store.availableJournals || []
  const q = search.value.toLowerCase()
  return (store.availableJournals || []).filter((j: string) => j.toLowerCase().includes(q))
})

const filteredMdpi = computed<any[]>(() => {
  const subs = store.mdpiSubJournals || []
  if (!mdpiSearch.value.trim()) return subs
  const q = mdpiSearch.value.toLowerCase()
  return subs.filter((j: any) =>
    j.short_name.toLowerCase().includes(q) || j.key.toLowerCase().includes(q)
  )
})

function pick(journal: string): void {
  store.paper.journal = journal
  open.value = false
  search.value = ''
  highlightedIndex.value = -1
}

function moveHighlight(delta: number): void {
  if (!filtered.value.length) return
  let next = highlightedIndex.value
  let attempts = 0
  do {
    next = Math.max(0, Math.min(filtered.value.length - 1, next + delta))
    attempts++
  } while (isLocked(filtered.value[next]) && attempts < filtered.value.length)
  highlightedIndex.value = next
}

function pickHighlighted(): void {
  if (highlightedIndex.value >= 0 && highlightedIndex.value < filtered.value.length) {
    const j = filtered.value[highlightedIndex.value]
    if (!isLocked(j)) pick(j)
  }
}

// MDPI pick
function pickMdpi(j: any): void {
  store.paper.journal = 'MDPI_' + j.key
  mdpiOpen.value = false
  mdpiSearch.value = ''
  mdpiHighlightedIndex.value = -1
}

function isMdpiSelected(j: any): boolean {
  return store.paper.journal === 'MDPI_' + j.key
}

function moveMdpiHighlight(delta: number): void {
  if (!filteredMdpi.value.length) return
  mdpiHighlightedIndex.value = Math.max(0, Math.min(filteredMdpi.value.length - 1, mdpiHighlightedIndex.value + delta))
}

function pickMdpiHighlighted(): void {
  if (mdpiHighlightedIndex.value >= 0 && mdpiHighlightedIndex.value < filteredMdpi.value.length) {
    pickMdpi(filteredMdpi.value[mdpiHighlightedIndex.value])
  }
}

// Click outside handlers
function handleClickOutside(e: MouseEvent): void {
  if (wrapRef.value && !wrapRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

function handleMdpiClickOutside(e: MouseEvent): void {
  if (mdpiWrapRef.value && !mdpiWrapRef.value.contains(e.target as Node)) {
    mdpiOpen.value = false
  }
}

// Fetch MDPI sub-journals when MDPI is selected
watch(isMDPI, (val) => {
  if (val) {
    store.fetchMDPISubJournals()
  }
})

// Persist language change to DB immediately so chat backend sees the new value
watch(
  () => store.paper.language,
  async (newLang) => {
    if (newLang && (newLang === 'en' || newLang === 'id')) {
      await store.savePaperToDb(true) // silent save
    }
  }
)

onMounted(() => {
  store.fetchJournals()
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('click', handleMdpiClickOutside)
  // Pre-fetch MDPI if currently selected
  if (isMDPI.value) store.fetchMDPISubJournals()
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('click', handleMdpiClickOutside)
})
</script>