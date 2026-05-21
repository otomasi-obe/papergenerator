<template>
  <div class="max-w-7xl">
    <div class="bg-white dark:bg-anthracite-700 rounded-2xl border border-ivory-300 dark:border-anthracite-500 shadow-sm p-6 space-y-5">
      <!-- Header -->
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div class="min-w-0">
          <h2 class="text-lg font-semibold text-ink-900 dark:text-anthracite-50">📚 Literatur</h2>
          <p class="text-sm text-ink-700 dark:text-anthracite-100 mt-1">
            Tabel referensi paper. Hasil SLR otomatis tersimpan di sini, dan bisa juga ditambah / diedit manual.
            Data ini dipakai sebagai sumber utama saat generate paper lengkap.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button
            @click="importFromFiles"
            :disabled="loading"
            class="px-3 py-1.5 rounded-lg text-xs font-medium bg-ivory-200 hover:bg-ivory-300 dark:bg-anthracite-600 dark:hover:bg-anthracite-500 text-ink-900 dark:text-anthracite-50 disabled:opacity-50"
            title="Import file PDF/DOCX yang sudah diupload"
          >📂 Import dari File</button>
          <button
            @click="showAddManual = !showAddManual"
            class="px-3 py-1.5 rounded-lg text-xs font-medium bg-brown-700 hover:bg-brown-800 text-cream-50"
          >＋ Tambah Manual</button>
        </div>
      </div>

      <!-- Inline error banner -->
      <div
        v-if="loadError"
        class="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 px-3 py-2 text-xs flex items-center justify-between gap-2"
      >
        <span class="text-red-800 dark:text-red-200 truncate">{{ loadError }}</span>
        <button
          @click="retryLoad"
          class="px-2 py-1 rounded bg-red-600 hover:bg-red-700 text-white text-[11px] font-semibold shrink-0"
        >Coba lagi</button>
      </div>

      <!-- Run SLR -->
      <div ref="slrCardRef" class="rounded-xl border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 p-4">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-ink-900 dark:text-anthracite-50">🔍 Jalankan SLR</h3>
          <span class="text-[10px] text-ink-500 dark:text-anthracite-200">Multi-source (OpenAlex · Crossref · arXiv · IEEE · SINTA · ...)</span>
        </div>
        <div class="flex flex-col sm:flex-row gap-2">
          <input
            ref="slrInputRef"
            v-model="slrQuery"
            @keyup.enter="runSLR"
            type="text"
            placeholder="Ketik topik (mis. 'reinforcement learning untuk navigasi AGV')"
            class="flex-1 px-3 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 focus:ring-2 focus:ring-cream-200 outline-none"
            :disabled="slrRunning"
          />
          <select
            v-model="slrTopK"
            class="px-2 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50"
            :disabled="slrRunning"
          >
            <option :value="20">Top 20</option>
            <option :value="30">Top 30</option>
            <option :value="50">Top 50</option>
            <option :value="80">Top 80</option>
          </select>
          <button
            @click="runSLR"
            :disabled="slrRunning || !slrQuery.trim()"
            class="px-4 py-2 rounded-lg text-sm font-semibold bg-brown-700 hover:bg-brown-800 text-cream-50 disabled:opacity-50"
          >
            {{ slrRunning ? 'Mencari…' : 'Jalankan SLR' }}
          </button>
        </div>

        <!-- Active jobs -->
        <div v-if="activeJobs.length" class="mt-3 space-y-2">
          <div v-for="job in activeJobs" :key="job.id"
               class="rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-3 py-2 text-xs">
            <div class="flex items-center justify-between gap-2">
              <span class="font-medium text-amber-900 dark:text-amber-100 truncate">
                {{ job.status === 'running' ? '⏳' : '⏸' }}
                {{ job.query }}
              </span>
              <button @click="cancelJob(job.id)"
                      class="text-amber-700 dark:text-amber-300 hover:underline shrink-0">cancel</button>
            </div>
            <div class="mt-1 flex items-center gap-2">
              <span
                class="px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0"
                :class="stageBadgeClass(job)"
              >{{ stageLabel(job.stage) || stageLabel(job.status) || '—' }}</span>
              <div class="flex-1 h-1.5 rounded-full bg-amber-200 dark:bg-amber-900/50 overflow-hidden">
                <div class="h-full bg-amber-500 transition-all" :style="{ width: `${job.progress || 0}%` }"></div>
              </div>
            </div>
            <div class="mt-1 text-amber-800 dark:text-amber-200 text-[11px] truncate">
              {{ job.progress_message || stageLabel(job.stage) || 'Menunggu worker…' }}
            </div>
          </div>
        </div>
      </div>

      <!-- Add manual form -->
      <div v-if="showAddManual" class="rounded-xl border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 p-4 space-y-2">
        <h3 class="text-sm font-semibold text-ink-900 dark:text-anthracite-50">＋ Tambah Literatur Manual</h3>
        <input v-model="manualForm.title" placeholder="Judul *" class="input-sm w-full" />
        <input v-model="manualForm.authors_str" placeholder="Authors (pisah koma)" class="input-sm w-full" />
        <div class="grid grid-cols-2 gap-2">
          <input v-model.number="manualForm.year" type="number" placeholder="Year" class="input-sm" />
          <input v-model="manualForm.venue" placeholder="Venue / Journal" class="input-sm" />
          <input v-model="manualForm.doi" placeholder="DOI" class="input-sm" />
          <input v-model="manualForm.url" placeholder="URL" class="input-sm" />
        </div>
        <textarea v-model="manualForm.summary" rows="2" placeholder="Ringkasan / catatan singkat" class="input-sm w-full resize-y"></textarea>
        <div class="flex gap-2 justify-end">
          <button @click="showAddManual = false" class="btn-cancel">Batal</button>
          <button @click="addManual" :disabled="!manualForm.title.trim()" class="btn-primary">Simpan</button>
        </div>
      </div>

      <!-- Filters -->
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div class="flex items-center gap-2 flex-wrap">
          <input v-model="filter" placeholder="🔍 Filter judul / penulis / venue / DOI" class="input-sm w-72" />
          <select v-model="filterSource" class="input-sm">
            <option value="">Semua sumber</option>
            <option v-for="s in availableSources" :key="s" :value="s">{{ s }}</option>
          </select>
          <label class="flex items-center gap-1 text-xs text-ink-700 dark:text-anthracite-100">
            <input v-model="onlyMustRead" type="checkbox" class="rounded" />
            Hanya must-read
          </label>
          <label class="flex items-center gap-1 text-xs text-ink-700 dark:text-anthracite-100">
            <input v-model="onlyPinned" type="checkbox" class="rounded" />
            Hanya pinned
          </label>
          <label class="flex items-center gap-1 text-xs text-ink-700 dark:text-anthracite-100">
            Tahun ≥
            <input
              v-model.number="minYear"
              type="number"
              min="1500"
              max="2100"
              placeholder="ex: 2018"
              class="input-sm w-24"
            />
          </label>
        </div>
        <div class="text-[11px] text-ink-500 dark:text-anthracite-200 flex items-center gap-2">
          <span
            v-if="lastSlrJob && lastSlrJob.status === 'done'"
            :class="aiSummaryUsed
              ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-700'
              : 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-700'"
            :title="aiSummaryUsed
              ? 'AI summaries enabled — top-K papers received LLM-generated summaries.'
              : 'AI summary not configured. Set AIOTOMASI_API + AIOTOMASI_APIKEY for AI-generated summaries.'"
            class="px-2 py-0.5 rounded text-[10px] font-medium"
          >{{ aiSummaryUsed ? '✨ AI summaries' : 'Summary: extractive only' }}</span>
          <span>{{ filteredItems.length }} / {{ items.length }} literatur · {{ pinnedCount }} pinned</span>
        </div>
      </div>

      <!-- Bulk action toolbar -->
      <div
        v-if="selectionCount > 0"
        class="flex items-center gap-2 flex-wrap rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-3 py-2 text-xs"
      >
        <span class="font-medium text-amber-900 dark:text-amber-100">{{ selectionCount }} dipilih</span>
        <button
          @click="bulkSetPinned(true)"
          :disabled="bulkBusy"
          class="px-2 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white disabled:opacity-50"
        >Pin</button>
        <button
          @click="bulkSetPinned(false)"
          :disabled="bulkBusy"
          class="px-2 py-1 rounded bg-amber-200 dark:bg-amber-800 text-amber-900 dark:text-amber-100 hover:bg-amber-300 dark:hover:bg-amber-700 disabled:opacity-50"
        >Unpin</button>
        <button
          @click="bulkToggleMustRead"
          :disabled="bulkBusy"
          class="px-2 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white disabled:opacity-50"
        >Toggle must-read</button>
        <button
          @click="bulkDelete"
          :disabled="bulkBusy"
          class="px-2 py-1 rounded bg-red-600 hover:bg-red-700 text-white disabled:opacity-50"
        >Hapus</button>
        <button
          @click="clearSelection"
          :disabled="bulkBusy"
          class="px-2 py-1 rounded text-amber-800 dark:text-amber-200 hover:underline"
        >Bersihkan</button>
        <span v-if="bulkMsg" class="ml-auto text-amber-800 dark:text-amber-200">{{ bulkMsg }}</span>
      </div>

      <!-- Table -->
      <div class="overflow-x-auto rounded-xl border border-ivory-300 dark:border-anthracite-500">
        <table class="min-w-full text-xs">
          <thead class="bg-ivory-100 dark:bg-anthracite-800 text-ink-700 dark:text-anthracite-100">
            <tr>
              <th class="px-2 py-2 text-left w-6">
                <input
                  type="checkbox"
                  :checked="allVisibleSelected"
                  :indeterminate.prop="someVisibleSelected && !allVisibleSelected"
                  @change="toggleSelectAllVisible"
                  title="Pilih semua di tampilan ini"
                />
              </th>
              <th class="px-2 py-2 text-left">📌</th>
              <th class="px-2 py-2 text-left w-10">#</th>
              <th class="px-2 py-2 text-left">
                <button @click="setSort('title')" class="hover:underline font-semibold">
                  Judul{{ sortIndicator('title') }}
                </button>
              </th>
              <th class="px-2 py-2 text-left">Penulis</th>
              <th class="px-2 py-2 text-left w-16">
                <button @click="setSort('year')" class="hover:underline font-semibold">
                  Tahun{{ sortIndicator('year') }}
                </button>
              </th>
              <th class="px-2 py-2 text-left">Venue</th>
              <th class="px-2 py-2 text-left">DOI / URL</th>
              <th class="px-2 py-2 text-left">Sumber</th>
              <th class="px-2 py-2 text-left">
                <button @click="setSort('citations')" class="hover:underline font-semibold">
                  Sitasi{{ sortIndicator('citations') }}
                </button>
              </th>
              <th class="px-2 py-2 text-left">
                <button @click="setSort('score')" class="hover:underline font-semibold">
                  Skor{{ sortIndicator('score') }}
                </button>
              </th>
              <th class="px-2 py-2 text-left">⭐</th>
              <th class="px-2 py-2 text-left">Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="13" class="px-3 py-6 text-center text-ink-500 dark:text-anthracite-200">Memuat…</td>
            </tr>
            <tr v-else-if="items.length === 0">
              <td colspan="13" class="px-3 py-8 text-center text-ink-500 dark:text-anthracite-200">
                <div class="space-y-3">
                  <div>Belum ada literatur. Jalankan SLR atau tambah manual untuk mulai.</div>
                  <button
                    v-if="paperTitle"
                    @click="startSLRFromPaperTopic"
                    class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-brown-700 hover:bg-brown-800 text-cream-50"
                  >Jalankan SLR otomatis dari topik paper ini</button>
                </div>
              </td>
            </tr>
            <tr v-else-if="filteredItems.length === 0">
              <td colspan="13" class="px-3 py-8 text-center text-ink-500 dark:text-anthracite-200">
                Tidak ada literatur yang cocok dengan filter ini. Coba ubah / kosongkan filter.
              </td>
            </tr>
            <template v-else>
              <tr
                v-for="(it, i) in displayedItems"
                :key="it.id"
                :class="['border-t border-ivory-200 dark:border-anthracite-600',
                         it.pinned ? 'bg-cream-100 dark:bg-anthracite-700/60' : 'hover:bg-cream-50 dark:hover:bg-anthracite-700/30']"
              >
                <td class="px-2 py-2 align-top">
                  <input
                    type="checkbox"
                    :checked="selectedIds.has(it.id)"
                    @change="toggleSelect(it.id)"
                  />
                </td>
                <td class="px-2 py-2 align-top">
                  <button @click="togglePin(it)" class="text-base leading-none" :title="it.pinned ? 'Unpin' : 'Pin ke atas'">
                    {{ it.pinned ? '📌' : '📍' }}
                  </button>
                </td>
                <td class="px-2 py-2 align-top text-ink-500">{{ i + 1 }}</td>
                <td class="px-2 py-2 align-top">
                  <div v-if="editingId === it.id">
                    <input v-model="editDraft.title" class="input-sm w-full" />
                    <textarea v-model="editDraft.summary" rows="2" class="input-sm w-full mt-1 resize-y" placeholder="Summary"></textarea>
                  </div>
                  <div v-else>
                    <div class="font-medium text-ink-900 dark:text-anthracite-50 leading-snug line-clamp-2" :title="it.title">{{ it.title }}</div>
                    <div v-if="it.summary" class="mt-1 text-[11px] text-ink-700 dark:text-anthracite-200 leading-snug line-clamp-3">{{ it.summary }}</div>
                  </div>
                </td>
                <td class="px-2 py-2 align-top text-ink-700 dark:text-anthracite-100 max-w-[180px] truncate" :title="(it.authors||[]).join(', ')">
                  <input v-if="editingId === it.id" v-model="editDraft.authors_str" class="input-sm w-full" />
                  <span v-else>{{ (it.authors || []).slice(0,3).join(', ') }}{{ (it.authors||[]).length > 3 ? ' …' : '' }}</span>
                </td>
                <td class="px-2 py-2 align-top">
                  <input v-if="editingId === it.id" v-model.number="editDraft.year" type="number" class="input-sm w-20" />
                  <span v-else>{{ it.year || '–' }}</span>
                </td>
                <td class="px-2 py-2 align-top text-ink-700 dark:text-anthracite-100 max-w-[200px] truncate" :title="it.venue">
                  <input v-if="editingId === it.id" v-model="editDraft.venue" class="input-sm w-full" />
                  <span v-else>{{ it.venue || '–' }}</span>
                </td>
                <td class="px-2 py-2 align-top text-ink-700 dark:text-anthracite-100 max-w-[180px] truncate">
                  <template v-if="editingId === it.id">
                    <input v-model="editDraft.doi" placeholder="DOI" class="input-sm w-full" />
                    <input v-model="editDraft.url" placeholder="URL" class="input-sm w-full mt-1" />
                  </template>
                  <template v-else>
                    <a v-if="it.doi" :href="`https://doi.org/${it.doi}`" target="_blank" rel="noopener" class="text-blue-600 hover:underline">{{ it.doi }}</a>
                    <a v-else-if="it.url" :href="safeUrl(it.url)" target="_blank" rel="noopener" class="text-blue-600 hover:underline truncate inline-block max-w-full">{{ it.url }}</a>
                    <span v-else>–</span>
                  </template>
                </td>
                <td class="px-2 py-2 align-top">
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-medium" :class="sourceBadgeClass(it.source_kind)">
                    {{ it.source || it.source_kind }}
                  </span>
                </td>
                <td class="px-2 py-2 align-top text-ink-700 dark:text-anthracite-100">{{ it.citations ?? '–' }}</td>
                <td class="px-2 py-2 align-top">
                  <span
                    v-if="it.score_total != null"
                    class="text-ink-700 dark:text-anthracite-100"
                    :title="it.score_breakdown ? JSON.stringify(it.score_breakdown, null, 2) : ''"
                  >
                    {{ (it.score_total).toFixed(2) }}
                  </span>
                  <span v-else class="text-ink-400">–</span>
                </td>
                <td class="px-2 py-2 align-top">
                  <button @click="toggleMustRead(it)" :title="it.must_read ? 'Tandai biasa' : 'Tandai must-read'">
                    {{ it.must_read ? '⭐' : '☆' }}
                  </button>
                </td>
                <td class="px-2 py-2 align-top whitespace-nowrap">
                  <template v-if="editingId === it.id">
                    <button @click="saveEdit" class="btn-primary text-[10px] px-2 py-0.5">Save</button>
                    <button @click="cancelEdit" class="btn-cancel text-[10px] px-2 py-0.5 ml-1">Cancel</button>
                  </template>
                  <template v-else>
                    <button @click="startEdit(it)" title="Edit" class="text-ink-600 hover:text-ink-900 px-1">✎</button>
                    <button @click="deleteItem(it)" title="Hapus" class="text-red-500 hover:text-red-700 px-1">✕</button>
                  </template>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <p class="text-[11px] text-ink-500 dark:text-anthracite-200">
        💡 <strong>Tip:</strong> hasil yang di-pin / must-read diprioritaskan oleh AI saat generate paper.
        Klik pada chat dan ketik <em>"buatkan literatur review tentang ..."</em> untuk menjalankan SLR otomatis.
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { usePaperStore } from '../stores/paper.js'
import { useLiteratureStore } from '../stores/literature.js'
import api from '../api/index.js'

const store = usePaperStore()
const litStore = useLiteratureStore()
const { currentPaperId } = storeToRefs(store)

const items = ref([])
const loading = ref(false)
const loadError = ref('')

const filter = ref('')
const filterSource = ref('')
const onlyMustRead = ref(false)
const onlyPinned = ref(false)
const minYear = ref(null)

const showAddManual = ref(false)

// SLR job runner state
const slrQuery = ref('')
const slrTopK = ref(50)
const slrRunning = ref(false)
const activeJobs = ref([])
const lastSlrJob = ref(null)
const slrCardRef = ref(null)
const slrInputRef = ref(null)
let _pollTimer = null
let _extraFastPolls = 0

// Inline edit state
const editingId = ref(null)
const editDraft = ref(null)

// Manual add form
const manualForm = ref({
  title: '', authors_str: '', year: null,
  venue: '', doi: '', url: '', summary: '',
})

// Bulk selection state
const selectedIds = ref(new Set())
const bulkBusy = ref(false)
const bulkMsg = ref('')
const selectionCount = computed(() => selectedIds.value.size)

// Sorting state
const sortKey = ref('default') // 'default' | 'title' | 'year' | 'score' | 'citations'
const sortDir = ref('desc')

const paperTitle = computed(() => store.paper?.title || '')

const aiSummaryUsed = computed(() => {
  return !!(lastSlrJob.value && lastSlrJob.value.stats && lastSlrJob.value.stats.ai_summary_used)
})

const filteredItems = computed(() => {
  const q = filter.value.trim().toLowerCase()
  const minY = (minYear.value != null && minYear.value !== '' && Number.isFinite(Number(minYear.value)))
    ? Number(minYear.value)
    : null
  return items.value.filter(it => {
    if (filterSource.value && (it.source || it.source_kind) !== filterSource.value) return false
    if (onlyMustRead.value && !it.must_read) return false
    if (onlyPinned.value && !it.pinned) return false
    if (minY != null && (it.year == null || Number(it.year) < minY)) return false
    if (!q) return true
    const hay = [
      it.title, it.venue, it.publisher, it.doi, it.url,
      ((it.authors || []).join(', ')),
    ].join(' ').toLowerCase()
    return hay.includes(q)
  })
})

const displayedItems = computed(() => {
  const arr = filteredItems.value.slice()
  if (sortKey.value === 'default') {
    arr.sort((a, b) => {
      const pinDiff = (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0)
      if (pinDiff !== 0) return pinDiff
      const sa = a.score_total ?? -Infinity
      const sb = b.score_total ?? -Infinity
      return sb - sa
    })
    return arr
  }
  const dir = sortDir.value === 'asc' ? 1 : -1
  arr.sort((a, b) => {
    let va, vb
    switch (sortKey.value) {
      case 'title':
        va = (a.title || '').toLowerCase()
        vb = (b.title || '').toLowerCase()
        break
      case 'year':
        va = a.year ?? -Infinity
        vb = b.year ?? -Infinity
        break
      case 'score':
        va = a.score_total ?? -Infinity
        vb = b.score_total ?? -Infinity
        break
      case 'citations':
        va = a.citations ?? -Infinity
        vb = b.citations ?? -Infinity
        break
      default:
        return 0
    }
    if (va < vb) return -1 * dir
    if (va > vb) return 1 * dir
    return 0
  })
  return arr
})

const pinnedCount = computed(() => items.value.filter(i => i.pinned).length)
const availableSources = computed(() => {
  const set = new Set()
  for (const it of items.value) {
    if (it.source) set.add(it.source)
    else if (it.source_kind) set.add(it.source_kind)
  }
  return Array.from(set).sort()
})

const allVisibleSelected = computed(() => {
  const arr = displayedItems.value
  if (arr.length === 0) return false
  for (const it of arr) {
    if (!selectedIds.value.has(it.id)) return false
  }
  return true
})

const someVisibleSelected = computed(() => {
  for (const it of displayedItems.value) {
    if (selectedIds.value.has(it.id)) return true
  }
  return false
})

function sourceBadgeClass(kind) {
  switch (kind) {
    case 'slr':     return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200'
    case 'file':    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'
    case 'manual':  return 'bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-100'
    default:        return 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200'
  }
}

const STAGE_LABELS = {
  queued: 'Antri',
  fetching: 'Mencari sumber',
  source_done: 'Mengambil hasil',
  dedup_done: 'Dedup selesai',
  scoring: 'Ranking',
  scored: 'Ranking selesai',
  summarizing: 'AI ringkas',
  summarized: 'AI ringkas (progress)',
  complete: 'Selesai',
  running: 'Berjalan',
  done: 'Selesai',
  error: 'Gagal',
}

function stageLabel(stage) {
  if (!stage) return ''
  return STAGE_LABELS[stage] || stage
}

function stageBadgeClass(job) {
  if (job?.status === 'error') {
    return 'bg-red-200 text-red-900 dark:bg-red-900 dark:text-red-100'
  }
  if (job?.status === 'done' || job?.stage === 'complete') {
    return 'bg-emerald-200 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100'
  }
  if (job?.status === 'queued' || job?.stage === 'queued') {
    return 'bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100'
  }
  return 'bg-amber-200 text-amber-900 dark:bg-amber-800 dark:text-amber-100'
}

function toast(msg, type = 'info') {
  if (typeof store.showToast === 'function') store.showToast(msg, type)
  else if (type === 'error') console.error(msg)
  else console.info(msg)
}

function safeUrl(u) {
  if (typeof u !== 'string') return '#'
  return /^(https?:\/\/|\/)/.test(u) ? u : '#'
}

// ----- Filter persistence -----
function filterStorageKey(paperId) {
  return `lit.filter.${paperId}`
}

function isAllFiltersDefault() {
  return !filter.value
    && !filterSource.value
    && !onlyMustRead.value
    && !onlyPinned.value
    && (minYear.value == null || minYear.value === '')
}

function saveFilterState() {
  if (!currentPaperId.value) return
  try {
    if (isAllFiltersDefault()) {
      localStorage.removeItem(filterStorageKey(currentPaperId.value))
      return
    }
    const payload = {
      filter: filter.value,
      filterSource: filterSource.value,
      onlyMustRead: onlyMustRead.value,
      onlyPinned: onlyPinned.value,
      minYear: minYear.value,
    }
    localStorage.setItem(filterStorageKey(currentPaperId.value), JSON.stringify(payload))
  } catch { /* ignore quota / unavailable */ }
}

function loadFilterStateFor(paperId) {
  try {
    const raw = localStorage.getItem(filterStorageKey(paperId))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch { return null }
}

function applySavedFilter(saved) {
  if (!saved) {
    filter.value = ''
    filterSource.value = ''
    onlyMustRead.value = false
    onlyPinned.value = false
    minYear.value = null
    return
  }
  filter.value = saved.filter || ''
  filterSource.value = saved.filterSource || ''
  onlyMustRead.value = !!saved.onlyMustRead
  onlyPinned.value = !!saved.onlyPinned
  minYear.value = (saved.minYear === '' || saved.minYear == null) ? null : Number(saved.minYear)
}

watch(
  [filter, filterSource, onlyMustRead, onlyPinned, minYear],
  () => { saveFilterState() }
)

// ----- Loaders -----
async function loadItems() {
  if (!currentPaperId.value) return
  loading.value = true
  try {
    const res = await api.get(`/api/papers/${currentPaperId.value}/literature`)
    const data = res.data
    if (Array.isArray(data)) {
      items.value = data
    } else if (data && Array.isArray(data.items)) {
      items.value = data.items
    } else {
      items.value = []
    }
    loadError.value = ''
  } catch (e) {
    loadError.value = 'Gagal memuat literatur: ' + (e?.response?.data?.error || e?.message || 'network error')
  } finally {
    loading.value = false
  }
}

let _lastJobIds = new Set()
let _lastJobStatus = {}

async function loadJobs() {
  if (!currentPaperId.value) return
  try {
    const res = await api.get(`/api/papers/${currentPaperId.value}/slr/jobs`)
    const jobs = res.data || []
    const active = jobs.filter(j => j.status === 'queued' || j.status === 'running')
    activeJobs.value = active
    const finished = jobs
      .filter(j => j.status === 'done' || j.status === 'error')
      .sort((a, b) => {
        const ta = new Date(a.finished_at || a.queued_at || 0).getTime()
        const tb = new Date(b.finished_at || b.queued_at || 0).getTime()
        return tb - ta
      })
    lastSlrJob.value = finished[0] || null
    const newlyDone = jobs.filter(j =>
      j.status === 'done' &&
      (!_lastJobIds.has(j.id) || _lastJobStatus[j.id] !== 'done')
    )
    const justFinished = jobs.some(j =>
      (j.status === 'done' || j.status === 'error') &&
      (!_lastJobIds.has(j.id) || _lastJobStatus[j.id] !== j.status)
    )
    if (justFinished) {
      // Re-arm one extra fast cycle so the first idle poll still happens
      // quickly after the final job state lands.
      _extraFastPolls = 1
      await loadItems()
      if (newlyDone.length > 0) {
        toast(`SLR selesai. ${items.value.length} literatur masuk.`, 'success')
      }
    }
    _lastJobIds = new Set(jobs.map(j => j.id))
    _lastJobStatus = Object.fromEntries(jobs.map(j => [j.id, j.status]))
    slrRunning.value = active.length > 0
    // If items load was previously failing, clear the banner now that jobs OK.
    // Only clear if loadItems also succeeded (loadError already empty after success).
  } catch (e) {
    loadError.value = 'Gagal memuat status job: ' + (e?.response?.data?.error || e?.message || 'network error')
  }
}

async function retryLoad() {
  loadError.value = ''
  await Promise.all([loadItems(), loadJobs()])
}

function schedulePoll() {
  if (_pollTimer) clearTimeout(_pollTimer)
  let delay
  if (activeJobs.value.length > 0) {
    delay = 2500
  } else if (_extraFastPolls > 0) {
    _extraFastPolls--
    delay = 2500
  } else {
    delay = 30000
  }
  _pollTimer = setTimeout(async () => {
    await loadJobs()
    schedulePoll()
  }, delay + Math.floor(Math.random() * 500))
}

// ----- SLR runner -----
async function runSLR() {
  const q = slrQuery.value.trim()
  if (!q || !currentPaperId.value) return
  slrRunning.value = true
  try {
    await api.post(`/api/papers/${currentPaperId.value}/slr/jobs`, {
      query: q,
      top_k: slrTopK.value,
      ai_summarize: true,
      ai_model: 'V-OPUS',
    })
    await loadJobs()
    // Re-arm the poller on the fast cadence so the newly-queued job's
    // completion is detected within seconds, not the next 30s tick. Without
    // this, the table appears "empty" for up to half a minute after the job
    // actually finishes because schedulePoll() was last called when
    // activeJobs was empty (delay=30000).
    schedulePoll()
  } catch (e) {
    const msg = e?.response?.data?.error || e?.message || 'SLR failed'
    toast('SLR error: ' + msg, 'error')
  } finally {
    slrRunning.value = false
  }
}

async function cancelJob(jobId) {
  if (!confirm('Hentikan job SLR ini? Hasil parsial dihilangkan.')) return
  try {
    await api.delete(`/api/slr/jobs/${jobId}`)
    await loadJobs()
  } catch (e) {
    toast('Cancel failed: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
}

async function startSLRFromPaperTopic() {
  const title = paperTitle.value
  if (title) slrQuery.value = title
  await nextTick()
  if (slrCardRef.value && typeof slrCardRef.value.scrollIntoView === 'function') {
    slrCardRef.value.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  setTimeout(() => {
    if (slrInputRef.value && typeof slrInputRef.value.focus === 'function') {
      slrInputRef.value.focus()
    }
  }, 250)
}

// ----- Import / manual -----
async function importFromFiles() {
  if (!currentPaperId.value) return
  loading.value = true
  try {
    const res = await api.post(`/api/papers/${currentPaperId.value}/literature/from-files`)
    const created = (res?.data?.created || []).length
    toast(created > 0 ? `Imported ${created} file${created === 1 ? '' : 's'}` : '0 new files', created > 0 ? 'success' : 'info')
    await loadItems()
  } catch (e) {
    toast('Import failed: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  } finally {
    loading.value = false
  }
}

function validateManual(f) {
  if (f.doi) {
    const d = f.doi.trim()
    if (d && !/^10\.\d{4,9}\//.test(d)) {
      toast('DOI tidak valid (format: 10.XXXX/...)', 'error')
      return false
    }
  }
  if (f.url) {
    const u = f.url.trim()
    if (u && !/^https?:\/\//.test(u)) {
      toast('URL harus diawali http:// atau https://', 'error')
      return false
    }
  }
  if (f.year != null && f.year !== '') {
    const y = Number(f.year)
    const max = new Date().getFullYear() + 1
    if (!Number.isFinite(y) || y < 1500 || y > max) {
      toast(`Year harus antara 1500 dan ${max}`, 'error')
      return false
    }
  }
  return true
}

async function addManual() {
  if (!manualForm.value.title.trim() || !currentPaperId.value) return
  const f = manualForm.value
  if (!validateManual(f)) return
  const authors = f.authors_str
    .split(',').map(a => a.trim()).filter(Boolean)
  try {
    await api.post(`/api/papers/${currentPaperId.value}/literature`, {
      title: f.title.trim(),
      authors,
      year: f.year || null,
      venue: f.venue.trim() || '',
      doi: f.doi.trim() || null,
      url: f.url.trim() || '',
      summary: f.summary.trim() || '',
      source_kind: 'manual',
      source: 'manual',
    })
    manualForm.value = { title: '', authors_str: '', year: null,
                          venue: '', doi: '', url: '', summary: '' }
    showAddManual.value = false
    await loadItems()
    toast('Literatur ditambahkan', 'success')
  } catch (e) {
    toast('Tambah gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
}

// ----- Inline edit -----
function startEdit(it) {
  editingId.value = it.id
  editDraft.value = {
    title: it.title || '',
    authors_str: (it.authors || []).join(', '),
    year: it.year,
    venue: it.venue || '',
    doi: it.doi || '',
    url: it.url || '',
    summary: it.summary || '',
  }
}

function cancelEdit() {
  editingId.value = null
  editDraft.value = null
}

async function saveEdit() {
  if (!editingId.value || !currentPaperId.value) return
  const d = editDraft.value
  const authors = d.authors_str.split(',').map(a => a.trim()).filter(Boolean)
  try {
    await api.patch(`/api/papers/${currentPaperId.value}/literature/${editingId.value}`, {
      title: d.title,
      authors,
      year: d.year || null,
      venue: d.venue,
      doi: d.doi || null,
      url: d.url,
      summary: d.summary,
    })
    cancelEdit()
    await loadItems()
    toast('Tersimpan', 'success')
  } catch (e) {
    toast('Save gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
}

async function togglePin(it) {
  const prev = it.pinned
  it.pinned = !prev
  try {
    await api.patch(`/api/papers/${currentPaperId.value}/literature/${it.id}`, { pinned: it.pinned })
  } catch (e) {
    it.pinned = prev
    toast('Pin gagal', 'error')
  }
}

async function toggleMustRead(it) {
  const prev = it.must_read
  it.must_read = !prev
  try {
    await api.patch(`/api/papers/${currentPaperId.value}/literature/${it.id}`, { must_read: it.must_read })
  } catch (e) {
    it.must_read = prev
    toast('Toggle gagal', 'error')
  }
}

async function deleteItem(it) {
  if (!confirm(`Hapus "${it.title?.slice(0, 80) || 'literatur ini'}"?`)) return
  try {
    await api.delete(`/api/papers/${currentPaperId.value}/literature/${it.id}`)
    await loadItems()
    toast('Dihapus', 'success')
  } catch (e) {
    toast('Hapus gagal: ' + (e?.response?.data?.error || e?.message || ''), 'error')
  }
}

// ----- Selection / bulk actions -----
function toggleSelect(id) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleSelectAllVisible() {
  const ids = displayedItems.value.map(i => i.id)
  if (allVisibleSelected.value) {
    const next = new Set(selectedIds.value)
    for (const id of ids) next.delete(id)
    selectedIds.value = next
  } else {
    const next = new Set(selectedIds.value)
    for (const id of ids) next.add(id)
    selectedIds.value = next
  }
}

function clearSelection() {
  selectedIds.value = new Set()
}

function pruneSelection() {
  const known = new Set(items.value.map(i => i.id))
  const next = new Set()
  for (const id of selectedIds.value) {
    if (known.has(id)) next.add(id)
  }
  selectedIds.value = next
}

async function runBulk(label, fn) {
  const ids = Array.from(selectedIds.value)
  if (ids.length === 0) return 0
  bulkBusy.value = true
  bulkMsg.value = `${label} ${ids.length}…`
  let okCount = 0
  try {
    const results = await Promise.all(ids.map(id => fn(id).then(() => true).catch(() => false)))
    okCount = results.filter(Boolean).length
  } finally {
    bulkBusy.value = false
    bulkMsg.value = ''
  }
  return okCount
}

async function bulkDelete() {
  const total = selectedIds.value.size
  if (total === 0) return
  if (!confirm(`Hapus ${total} literatur terpilih? Tindakan ini tidak bisa dibatalkan.`)) return
  const ok = await runBulk('Menghapus', (id) =>
    api.delete(`/api/papers/${currentPaperId.value}/literature/${id}`)
  )
  clearSelection()
  await loadItems()
  if (ok === total) toast(`Dihapus ${ok} literatur`, 'success')
  else toast(`Dihapus ${ok}/${total} (sisanya gagal)`, ok > 0 ? 'info' : 'error')
}

async function bulkSetPinned(pinned) {
  const total = selectedIds.value.size
  if (total === 0) return
  const ok = await runBulk(pinned ? 'Pin' : 'Unpin', (id) =>
    api.patch(`/api/papers/${currentPaperId.value}/literature/${id}`, { pinned })
  )
  await loadItems()
  pruneSelection()
  toast(`${pinned ? 'Pinned' : 'Unpinned'} ${ok}/${total}`, ok > 0 ? 'success' : 'error')
}

async function bulkToggleMustRead() {
  const total = selectedIds.value.size
  if (total === 0) return
  const anyNotMustRead = items.value.some(it => selectedIds.value.has(it.id) && !it.must_read)
  const newValue = anyNotMustRead
  const ok = await runBulk('Memperbarui', (id) =>
    api.patch(`/api/papers/${currentPaperId.value}/literature/${id}`, { must_read: newValue })
  )
  await loadItems()
  pruneSelection()
  toast(`${newValue ? 'Must-read' : 'Biasa'}: ${ok}/${total}`, ok > 0 ? 'success' : 'error')
}

// ----- Sorting -----
function setSort(key) {
  if (sortKey.value !== key) {
    sortKey.value = key
    sortDir.value = key === 'title' ? 'asc' : 'desc'
    return
  }
  // cycle: desc -> asc -> default ; asc -> desc -> default depending on first
  if (sortDir.value === 'desc') {
    sortDir.value = 'asc'
  } else if (sortDir.value === 'asc') {
    sortKey.value = 'default'
    sortDir.value = 'desc'
  }
}

function sortIndicator(key) {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? ' ▲' : ' ▼'
}

/**
 * Apply an intent parked by the chat store after a chat-triggered RunSLR.
 * The backend has already created the job — we DO NOT re-POST. We just
 * pre-fill the query input and surface an optimistic job card so the user
 * sees immediate feedback while the next poll picks up the real job state.
 */
function applyIntent(intent) {
  if (!intent) return
  if (intent.query) slrQuery.value = intent.query
  if (intent.top_k) slrTopK.value = intent.top_k
  if (intent.job_id && !activeJobs.value.find(j => j.id === intent.job_id)) {
    activeJobs.value = [{
      id: intent.job_id,
      query: intent.query,
      status: 'queued',
      progress: 0,
      progress_message: 'Starting…',
    }, ...activeJobs.value]
    slrRunning.value = true
  }
  loadJobs().finally(() => schedulePoll())
}

watch(currentPaperId, async (id) => {
  // Reset cross-paper state so a stale "justFinished" detection from another
  // paper doesn't fire after switching.
  _lastJobIds = new Set()
  _lastJobStatus = {}
  activeJobs.value = []
  lastSlrJob.value = null
  selectedIds.value = new Set()
  loadError.value = ''
  // Restore filters: defaults first, then overlay any saved state for this paper.
  applySavedFilter(id ? loadFilterStateFor(id) : null)
  if (id) {
    await Promise.all([loadItems(), loadJobs()])
    schedulePoll()
  }
})

watch(() => litStore.pendingIntent, (intent) => {
  if (intent) applyIntent(litStore.consumeIntent())
})

onMounted(async () => {
  if (currentPaperId.value) {
    applySavedFilter(loadFilterStateFor(currentPaperId.value))
    await Promise.all([loadItems(), loadJobs()])
  }
  applyIntent(litStore.consumeIntent())
  schedulePoll()
})

onUnmounted(() => {
  if (_pollTimer) clearTimeout(_pollTimer)
})
</script>

<style scoped>
.input-sm { @apply px-2 py-1 border border-ivory-300 dark:border-anthracite-500 rounded text-xs bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 outline-none focus:ring-1 focus:ring-cream-200 dark:focus:ring-anthracite-500; }
.btn-primary { @apply px-3 py-1.5 rounded-lg text-xs font-semibold bg-brown-700 hover:bg-brown-800 text-cream-50 disabled:opacity-50; }
.btn-cancel { @apply px-3 py-1.5 rounded-lg text-xs font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700; }
.line-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.line-clamp-3 { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
</style>
