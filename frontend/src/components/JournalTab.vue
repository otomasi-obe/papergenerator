<template>
  <div class="max-w-3xl">
    <div class="bg-white dark:bg-anthracite-700 rounded-2xl border border-ivory-300 dark:border-anthracite-500 shadow-sm p-6">
      <h2 class="text-lg font-semibold text-ink-900 dark:text-anthracite-50">Journal</h2>
      <p class="text-sm text-ink-700 dark:text-anthracite-100 mt-1">
        Pilih jurnal/template tujuan untuk export DOCX. Gunakan kotak pencarian untuk menyaring.
      </p>

      <div class="mt-5">
        <label class="block text-sm font-medium text-ink-900 dark:text-anthracite-50 mb-2">Export format</label>

        <!-- Search + selected pill -->
        <div class="relative max-w-md" ref="wrapRef">
          <div class="flex items-center gap-2 mb-1.5">
            <span class="text-xs text-ink-700 dark:text-anthracite-100">Saat ini:</span>
            <span class="px-2 py-0.5 rounded-md text-xs font-semibold bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-anthracite-50">
              {{ store.paper.journal || 'IEEE' }}
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
            class="w-full px-3 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-xl text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none"
            :disabled="store.journalsLoading"
          />

          <ul v-if="open && filtered.length"
            id="journal-list"
            role="listbox"
            class="absolute z-50 mt-1 w-full bg-white dark:bg-anthracite-700 border border-ivory-300 dark:border-anthracite-500 rounded-xl shadow-lg max-h-72 overflow-y-auto text-sm">
            <li
              v-for="(j, idx) in filtered"
              :key="j"
              @click="pick(j)"
              role="option"
              :aria-selected="store.paper.journal === j"
              :class="[
                'px-3 py-2 cursor-pointer flex items-center justify-between transition-colors',
                store.paper.journal === j || highlightedIndex === idx ? 'bg-ivory-200 dark:bg-anthracite-600 font-medium text-ink-900 dark:text-anthracite-50' : 'text-ink-800 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-600',
              ]"
            >
              <span>{{ j }}</span>
              <span v-if="store.paper.journal === j" class="text-ink-700 dark:text-anthracite-100 text-xs">✓ active</span>
            </li>
          </ul>

          <p v-if="open && search && filtered.length === 0" class="absolute mt-1 text-xs text-ink-700 dark:text-anthracite-200">
            Tidak ada jurnal yang cocok dengan "<strong>{{ search }}</strong>"
          </p>
        </div>

        <p class="text-xs text-ink-700 dark:text-anthracite-200 mt-3">
          Pilihan ini menentukan template generator yang dipakai saat klik "Export DOCX".
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { usePaperStore } from '../stores/paper'

const store = usePaperStore()
const search = ref<string>('')
const open = ref<boolean>(false)
const wrapRef = ref<HTMLElement | null>(null)
const highlightedIndex = ref<number>(-1)

const filtered = computed<string[]>(() => {
  if (!search.value.trim()) return store.availableJournals || []
  const q = search.value.toLowerCase()
  return (store.availableJournals || []).filter((j: string) => j.toLowerCase().includes(q))
})

function pick(journal: string): void {
  store.paper.journal = journal
  open.value = false
  search.value = ''
  highlightedIndex.value = -1
}

function moveHighlight(delta: number): void {
  if (!filtered.value.length) return
  highlightedIndex.value = Math.max(0, Math.min(filtered.value.length - 1, highlightedIndex.value + delta))
}

function pickHighlighted(): void {
  if (highlightedIndex.value >= 0 && highlightedIndex.value < filtered.value.length) {
    pick(filtered.value[highlightedIndex.value])
  }
}

function handleClickOutside(e: MouseEvent): void {
  if (wrapRef.value && !wrapRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => {
  store.fetchJournals()
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>
