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

      <!-- Run SLR -->
      <div class="rounded-xl border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 p-4">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-ink-900 dark:text-anthracite-50">🔍 Jalankan SLR</h3>
          <span class="text-[10px] text-ink-500 dark:text-anthracite-200">Multi-source (OpenAlex · Crossref · arXiv · IEEE · SINTA · ...)</span>
        </div>
        <div class="flex flex-col sm:flex-row gap-2">
          <input
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
            <div class="mt-1 h-1.5 rounded-full bg-amber-200 dark:bg-amber-900/50 overflow-hidden">
              <div class="h-full bg-amber-500 transition-all" :style="{ width: `${job.progress || 0}%` }"></div>
            </div>
            <div class="mt-1 text-amber-800 dark:text-amber-200 text-[11px] truncate">
              {{ job.progress_message || job.stage || 'Menunggu worker…' }}
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
        </div>
        <div class="text-[11px] text-ink-500 dark:text-anthracite-200">
          {{ filteredItems.length }} / {{ items.length }} literatur
          · {{ pinnedCount }} pinned
        </div>
      </div>

      <!-- Table -->
      <div class="overflow-x-auto rounded-xl border border-ivory-300 dark:border-anthracite-500">
        <table class="min-w-full text-xs">
          <thead class="bg-ivory-100 dark:bg-anthracite-800 text-ink-700 dark:text-anthracite-100">
            <tr>
              <th class="px-2 py-2 text-left">📌</th>
              <th class="px-2 py-2 text-left w-10">#</th>
              <th class="px-2 py-2 text-left">Judul</th>
              <th class="px-2 py-2 text-left">Penulis</th>
              <th class="px-2 py-2 text-left w-16">Tahun</th>
              <th class="px-2 py-2 text-left">Venue</th>
              <th class="px-2 py-2 text-left">DOI / URL</th>
              <th class="px-2 py-2 text-left">Sumber</th>
              <th class="px-2 py-2 text-left">Sitasi</th>
              <th class="px-2 py-2 text-left">Skor</th>
              <th class="px-2 py-2 text-left">⭐</th>
              <th class="px-2 py-2 text-left">Aksi</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="12" class="px-3 py-6 text-center text-ink-500 dark:text-anthracite-200">Memuat…</td>
            </tr>
            <tr v-else-if="filteredItems.length === 0">
              <td colspan="12" class="px-3 py-8 text-center text-ink-500 dark:text-anthracite-200">
                Belum ada literatur. Jalankan SLR atau tambah manual untuk mulai.
              </td>
            </tr>
            <template v-else>
              <tr
                v-for="(it, i) in filteredItems"
                :key="it.id"
                :class="['border-t border-ivory-200 dark:border-anthracite-600',
                         it.pinned ? 'bg-cream-100 dark:bg-anthracite-700/60' : 'hover:bg-cream-50 dark:hover:bg-anthracite-700/30']"
              >
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
                    <div class="font-medium text-ink-900 dark:text-anthracite-50 leading-snug">{{ it.title }}</div>
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
                    <a v-else-if="it.url" :href="it.url" target="_blank" rel="noopener" class="text-blue-600 hover:underline truncate inline-block max-w-full">{{ it.url }}</a>
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
                  <span v-if="it.score_total != null" class="text-ink-700 dark:text-anthracite-100">
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePaperStore } from '../stores/paper.js'
import api from '../api/index.js'

const store = usePaperStore()
const { currentPaperId } = storeToRefs(store)

const items = ref([])
const loading = ref(false)
const filter = ref('')
const filterSource = ref('')
const onlyMustRead = ref(false)
const showAddManual = ref(false)

// SLR job runner state
const slrQuery = ref('')
const slrTopK = ref(50)
const slrRunning = ref(false)
const activeJobs = ref([])
let _pollTimer = null

// Inline edit state
const editingId = ref(null)
const editDraft = ref(null)

// Manual add form
const manualForm = ref({
  title: '', authors_str: '', year: null,
  venue: '', doi: '', url: '', summary: '',
})

const filteredItems = computed(() => {
  const q = filter.value.trim().toLowerCase()
  return items.value.filter(it => {
    if (filterSource.value && (it.source || it.source_kind) !== filterSource.value) return false
    if (onlyMustRead.value && !it.must_read) return false
    if (!q) return true
    const hay = [
      it.title, it.venue, it.publisher, it.doi, it.url,
      ((it.authors || []).join(', ')),
    ].join(' ').toLowerCase()
    return hay.includes(q)
  })
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

function sourceBadgeClass(kind) {
  switch (kind) {
    case 'slr':     return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200'
    case 'file':    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'
    case 'manual':  return 'bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-100'
    default:        return 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200'
  }
}

async function loadItems() {
  if (!currentPaperId.value) return
  loading.value = true
  try {
    const res = await api.get(`/api/papers/${currentPaperId.value}/literature`)
    items.value = res.data || []
  } catch (e) {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function loadJobs() {
  if (!currentPaperId.value) return
  try {
    const res = await api.get(`/api/papers/${currentPaperId.value}/slr/jobs`)
    const jobs = res.data || []
    const active = jobs.filter(j => j.status === 'queued' || j.status === 'running')
    activeJobs.value = active
    // If any job just transitioned to done since last poll → reload items.
    const justFinished = jobs.some(j =>
      (j.status === 'done' || j.status === 'error') &&
      _lastJobIds.has(j.id) && _lastJobStatus[j.id] !== j.status
    )
    if (justFinished) await loadItems()
    _lastJobIds = new Set(jobs.map(j => j.id))
    _lastJobStatus = Object.fromEntries(jobs.map(j => [j.id, j.status]))
    slrRunning.value = active.length > 0
  } catch { /* ignore */ }
}

let _lastJobIds = new Set()
let _lastJobStatus = {}

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
  } catch (e) {
    console.error(e)
  }
}

async function cancelJob(jobId) {
  try {
    await api.delete(`/api/slr/jobs/${jobId}`)
    await loadJobs()
  } catch { /* ignore */ }
}

async function importFromFiles() {
  if (!currentPaperId.value) return
  loading.value = true
  try {
    await api.post(`/api/papers/${currentPaperId.value}/literature/from-files`)
    await loadItems()
  } finally {
    loading.value = false
  }
}

async function addManual() {
  if (!manualForm.value.title.trim() || !currentPaperId.value) return
  const f = manualForm.value
  const authors = f.authors_str
    .split(',').map(a => a.trim()).filter(Boolean)
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
}

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
}

async function togglePin(it) {
  await api.patch(`/api/papers/${currentPaperId.value}/literature/${it.id}`, { pinned: !it.pinned })
  await loadItems()
}

async function toggleMustRead(it) {
  await api.patch(`/api/papers/${currentPaperId.value}/literature/${it.id}`, { must_read: !it.must_read })
  await loadItems()
}

async function deleteItem(it) {
  if (!confirm(`Hapus "${it.title?.slice(0, 80) || 'literatur ini'}"?`)) return
  await api.delete(`/api/papers/${currentPaperId.value}/literature/${it.id}`)
  await loadItems()
}

watch(currentPaperId, async (id) => {
  if (id) {
    await Promise.all([loadItems(), loadJobs()])
  }
})

onMounted(async () => {
  if (currentPaperId.value) {
    await Promise.all([loadItems(), loadJobs()])
  }
  _pollTimer = setInterval(loadJobs, 4000)
})

onUnmounted(() => {
  if (_pollTimer) clearInterval(_pollTimer)
})
</script>

<style scoped>
.input-sm { @apply px-2 py-1 border border-ivory-300 dark:border-anthracite-500 rounded text-xs bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 outline-none focus:ring-1 focus:ring-cream-200 dark:focus:ring-anthracite-500; }
.btn-primary { @apply px-3 py-1.5 rounded-lg text-xs font-semibold bg-brown-700 hover:bg-brown-800 text-cream-50 disabled:opacity-50; }
.btn-cancel { @apply px-3 py-1.5 rounded-lg text-xs font-medium border border-ivory-300 dark:border-anthracite-500 text-ink-700 dark:text-anthracite-100 hover:bg-ivory-100 dark:hover:bg-anthracite-700; }
.line-clamp-3 { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
</style>
