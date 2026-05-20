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
          <input
            v-model="search"
            @focus="open = true"
            @input="open = true"
            @keydown.escape="open = false"
            @keydown.enter.prevent="pickFirstFiltered"
            type="text"
            placeholder="🔍 Cari jurnal (contoh: IEEE, JOKI, JNTETI…)"
            class="w-full px-3 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-xl text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none"
            :disabled="store.journalsLoading"
          />

          <ul v-if="open && filtered.length"
            class="absolute z-50 mt-1 w-full bg-white dark:bg-anthracite-700 border border-ivory-300 dark:border-anthracite-500 rounded-xl shadow-lg max-h-72 overflow-y-auto text-sm">
            <li
              v-for="j in filtered"
              :key="j"
              @click="pick(j)"
              :class="[
                'px-3 py-2 cursor-pointer flex items-center justify-between transition-colors',
                store.paper.journal === j ? 'bg-ivory-200 dark:bg-anthracite-600 font-medium text-ink-900 dark:text-anthracite-50' : 'text-ink-800 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-600',
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

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { usePaperStore } from '../stores/paper.js'

const store = usePaperStore()
const search = ref('')
const open = ref(false)
const wrapRef = ref(null)

const filtered = computed(() => {
  const list = (store.availableJournals || [])
  const q = search.value.trim().toLowerCase()
  if (!q) return list
  return list.filter(j => j.toLowerCase().includes(q))
})

function pick(j) {
  store.paper.journal = j
  search.value = ''
  open.value = false
}

function pickFirstFiltered() {
  if (filtered.value.length) pick(filtered.value[0])
}

function onClickOutside(e) {
  if (wrapRef.value && !wrapRef.value.contains(e.target)) open.value = false
}

onMounted(() => {
  store.fetchJournals()
  document.addEventListener('mousedown', onClickOutside)
})
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))
</script>
