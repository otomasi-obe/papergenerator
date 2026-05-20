<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4 max-w-5xl mx-auto">
      <div>
        <h2 class="text-lg font-semibold text-gray-800">Files</h2>
        <p class="text-xs text-gray-500 mt-0.5">PDF / DOCX / DOC / TXT / MD — max 10MB per file.</p>
      </div>
      <div class="flex items-center gap-2">
        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.docx,.doc,.txt,.md"
          multiple
          class="hidden"
          @change="onFileChange"
        />
        <button
          @click="fileInput?.click()"
          :disabled="!store.currentPaperId || uploading"
          class="px-3 py-1.5 bg-brown-600 hover:bg-brown-700 text-cream-50 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
        >
          <span v-if="uploading">Uploading…</span>
          <span v-else>＋ Upload file</span>
        </button>
      </div>
    </div>

    <p v-if="warning" class="max-w-5xl mx-auto mb-3 text-xs text-amber-600">{{ warning }}</p>

    <div class="max-w-5xl mx-auto grid lg:grid-cols-[280px,1fr] gap-4">
      <!-- File list -->
      <aside class="bg-white border rounded-xl shadow-sm overflow-hidden">
        <div class="px-3 py-2 border-b text-xs font-semibold text-slate-600 bg-slate-50">
          {{ files.length }} file{{ files.length === 1 ? '' : 's' }}
        </div>
        <div v-if="loading" class="px-3 py-6 text-center text-xs text-slate-400">Loading…</div>
        <div v-else-if="!files.length" class="px-3 py-12 text-center text-xs text-slate-400">
          Belum ada file. Klik <strong>＋ Upload file</strong>.
        </div>
        <ul v-else class="divide-y divide-slate-100 max-h-[60vh] overflow-y-auto">
          <li
            v-for="f in files"
            :key="f.id"
            :class="[
              'group px-3 py-2 cursor-pointer flex items-start gap-2 transition-colors',
              activeFileId === f.id ? 'bg-cream-200' : 'hover:bg-cream-100',
            ]"
            @click="selectFile(f)"
          >
            <span class="text-base leading-none pt-0.5">{{ extIcon(f.ext) }}</span>
            <div class="min-w-0 flex-1">
              <div :class="['text-xs truncate', activeFileId === f.id ? 'text-brown-800 font-semibold' : 'text-brown-700 font-medium']" :title="f.original_name">
                {{ f.original_name }}
              </div>
              <div class="text-[10px] text-slate-400 mt-0.5">
                {{ humanSize(f.size_bytes) }} · {{ formatDate(f.created_at) }}
              </div>
            </div>
            <button
              @click.stop="removeFile(f)"
              class="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-500 text-xs px-1"
              title="Hapus"
            >🗑</button>
          </li>
        </ul>
      </aside>

      <!-- Preview pane -->
      <section class="bg-white border rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[60vh]">
        <header v-if="activeFile" class="px-4 py-2.5 border-b flex items-center justify-between">
          <div class="min-w-0 flex-1">
            <div class="text-sm font-semibold text-slate-800 truncate" :title="activeFile.original_name">
              {{ extIcon(activeFile.ext) }} {{ activeFile.original_name }}
            </div>
            <div class="text-[11px] text-slate-400">{{ humanSize(activeFile.size_bytes) }}</div>
          </div>
          <a
            :href="rawUrl(activeFile)"
            target="_blank"
            rel="noopener"
            class="text-xs text-brown-600 hover:text-brown-800 font-medium px-2 py-1 rounded hover:bg-cream-200"
          >Buka di tab baru ↗</a>
        </header>

        <div v-if="!activeFile" class="flex-1 flex items-center justify-center text-xs text-slate-400">
          Pilih file di kiri untuk melihat preview.
        </div>

        <div v-else class="flex-1 overflow-y-auto bg-slate-50">
          <!-- PDF inline iframe -->
          <iframe
            v-if="activeFile.ext === '.pdf'"
            :src="rawUrl(activeFile)"
            class="w-full h-full min-h-[60vh] border-0 bg-white"
          />
          <!-- TXT / MD -->
          <pre
            v-else-if="['.txt', '.md'].includes(activeFile.ext)"
            class="px-5 py-4 text-xs leading-relaxed text-slate-700 whitespace-pre-wrap font-mono"
          >{{ previewText || '(kosong)' }}</pre>
          <!-- DOCX / DOC: show extracted text -->
          <div v-else class="px-5 py-4 text-xs leading-relaxed text-slate-700 whitespace-pre-wrap font-mono">
            <div v-if="!previewText" class="text-slate-400">(tidak bisa di-preview di browser)</div>
            <template v-else>{{ previewText }}</template>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { usePaperStore } from '../stores/paper.js'
import api from '../api/index.js'

const store = usePaperStore()

const files = ref([])
const loading = ref(false)
const uploading = ref(false)
const warning = ref('')

const fileInput = ref(null)
const activeFileId = ref(null)
const previewText = ref('')

const activeFile = computed(() => files.value.find(f => f.id === activeFileId.value))

async function load() {
  if (!store.currentPaperId) return
  loading.value = true
  try {
    const res = await api.get(`/api/papers/${store.currentPaperId}/files`)
    files.value = res.data.files || []
    if (files.value.length && !activeFileId.value) {
      selectFile(files.value[0])
    }
  } catch (e) {
    warning.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => store.currentPaperId, () => {
  files.value = []
  activeFileId.value = null
  previewText.value = ''
  load()
})

onMounted(load)

async function selectFile(f) {
  activeFileId.value = f.id
  previewText.value = ''
  if (['.pdf'].includes(f.ext)) return
  try {
    const res = await api.get(`/api/papers/${store.currentPaperId}/files/${f.id}/preview`)
    previewText.value = res.data.text || ''
  } catch (e) {
    previewText.value = '(gagal memuat preview: ' + (e.message || e) + ')'
  }
}

async function onFileChange(e) {
  const list = Array.from(e.target.files || [])
  if (fileInput.value) fileInput.value.value = ''
  if (!list.length || !store.currentPaperId) return

  uploading.value = true
  warning.value = ''
  try {
    const fd = new FormData()
    list.forEach(f => fd.append('files', f))
    const res = await api.post(`/api/papers/${store.currentPaperId}/files`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const newFiles = res.data.files || []
    files.value = [...newFiles, ...files.value]
    if (newFiles.length) selectFile(newFiles[0])
    if (res.data.warnings?.length) warning.value = res.data.warnings.join('; ')
  } catch (e) {
    warning.value = 'Upload gagal: ' + (e.response?.data?.error || e.message)
  } finally {
    uploading.value = false
  }
}

async function removeFile(f) {
  if (!confirm(`Hapus "${f.original_name}"?`)) return
  try {
    await api.delete(`/api/papers/${store.currentPaperId}/files/${f.id}`)
    files.value = files.value.filter(x => x.id !== f.id)
    if (activeFileId.value === f.id) {
      activeFileId.value = files.value[0]?.id || null
      previewText.value = ''
      if (activeFileId.value) selectFile(files.value[0])
    }
  } catch (e) {
    warning.value = 'Hapus gagal: ' + (e.response?.data?.error || e.message)
  }
}

function rawUrl(f) {
  // Cookies travel with same-origin GET — no token in query string needed.
  return f.url
}

function extIcon(ext) {
  switch ((ext || '').toLowerCase()) {
    case '.pdf': return '📕'
    case '.docx':
    case '.doc': return '📘'
    case '.txt': return '📄'
    case '.md': return '📝'
    default: return '📁'
  }
}

function humanSize(b) {
  if (!b) return '0 B'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDate(s) {
  if (!s) return ''
  const d = new Date(s)
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return 'baru saja'
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm lalu'
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'j lalu'
  if (diff < 7 * 86400000) return Math.floor(diff / 86400000) + 'h lalu'
  return d.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}
</script>
