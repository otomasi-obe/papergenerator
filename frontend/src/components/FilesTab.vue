<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4 max-w-5xl mx-auto">
      <div>
        <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">Files</h2>
        <p class="text-xs text-ink-600 dark:text-ink-300 mt-0.5">PDF / DOCX / DOC / TXT / MD / XLSX / XLS / CSV — max 30MB per file. Bisa upload banyak file sekaligus.</p>
      </div>
      <div class="flex items-center gap-2">
        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.docx,.doc,.txt,.md,.xlsx,.xls,.csv"
          multiple
          class="hidden"
          @change="onFileChange"
        />
        <button
          v-if="!uploading"
          @click="fileInput?.click()"
          :disabled="!store.currentPaperId"
          class="px-3 py-1.5 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
        >
          ＋ Upload file
        </button>
        <div v-else class="flex items-center gap-2">
          <span class="text-xs text-ink-600 dark:text-ink-300">{{ uploadProgress }}</span>
          <button
            @click="cancelUpload"
            class="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-medium transition-colors"
          >
            ✕ Cancel
          </button>
        </div>
      </div>
    </div>

    <p v-if="warning" class="max-w-5xl mx-auto mb-3 text-xs text-amber-700 dark:text-amber-300">{{ warning }}</p>

    <div class="max-w-5xl mx-auto grid lg:grid-cols-[280px,1fr] gap-4">
      <!-- File list -->
      <aside class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden">
        <div class="px-3 py-2 border-b border-cream-300 dark:border-ash-700 text-xs font-semibold text-ink-700 dark:text-ink-200 bg-cream-100 dark:bg-ash-850">
          {{ files.length }} file{{ files.length === 1 ? '' : 's' }}
        </div>
        <div v-if="loading" class="px-3 py-6 text-center text-xs text-ink-500 dark:text-ink-300">Loading…</div>
        <div v-else-if="!files.length" class="px-3 py-12 text-center text-xs text-ink-500 dark:text-ink-300">
          Belum ada file. Klik <strong>＋ Upload file</strong>.
        </div>
        <ul v-else class="divide-y divide-cream-200 dark:divide-ash-700 max-h-[60vh] overflow-y-auto">
          <li
            v-for="f in files"
            :key="f.id"
            :class="[
              'group px-3 py-2 cursor-pointer flex items-start gap-2 transition-colors',
              activeFileId === f.id ? 'bg-cream-200 dark:bg-ash-700' : 'hover:bg-cream-100 dark:hover:bg-ash-700',
            ]"
            @click="selectFile(f)"
          >
            <span class="text-base leading-none pt-0.5">{{ extIcon(f.ext) }}</span>
            <div class="min-w-0 flex-1">
              <div :class="['text-xs truncate', activeFileId === f.id ? 'text-ink-900 dark:text-ink-50 font-semibold' : 'text-ink-700 dark:text-ink-100 font-medium']" :title="f.original_name">
                {{ f.original_name }}
              </div>
              <div class="text-[10px] text-ink-500 dark:text-ink-300 mt-0.5">
                {{ humanSize(f.size_bytes) }} · {{ formatDate(f.created_at) }}
              </div>
            </div>
            <button
              @click.stop="removeFile(f)"
              class="opacity-0 group-hover:opacity-100 text-ink-400 dark:text-ink-300 hover:text-rose-500 text-xs px-1"
              title="Hapus"
            >🗑</button>
          </li>
        </ul>
      </aside>

      <!-- Preview pane -->
      <section class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[60vh]">
        <header v-if="activeFile" class="px-4 py-2.5 border-b border-cream-300 dark:border-ash-700 flex items-center justify-between">
          <div class="min-w-0 flex-1">
            <div class="text-sm font-semibold text-ink-900 dark:text-ink-50 truncate" :title="activeFile.original_name">
              {{ extIcon(activeFile.ext) }} {{ activeFile.original_name }}
            </div>
            <div class="text-[11px] text-ink-500 dark:text-ink-300">{{ humanSize(activeFile.size_bytes) }}</div>
          </div>
          <div class="flex items-center gap-2">
            <a
              :href="rawUrl(activeFile)"
              download
              class="text-xs text-ink-700 dark:text-ink-100 hover:text-ink-900 dark:hover:text-ink-50 font-medium px-2 py-1 rounded hover:bg-cream-200 dark:hover:bg-ash-700"
            >Download ↓</a>
            <a
              :href="rawUrl(activeFile)"
              target="_blank"
              rel="noopener"
              class="text-xs text-ink-700 dark:text-ink-100 hover:text-ink-900 dark:hover:text-ink-50 font-medium px-2 py-1 rounded hover:bg-cream-200 dark:hover:bg-ash-700"
            >Buka di tab baru ↗</a>
          </div>
        </header>

        <div v-if="!activeFile" class="flex-1 flex items-center justify-center text-xs text-ink-500 dark:text-ink-300">
          Pilih file di kiri untuk melihat preview.
        </div>

        <div v-else class="flex-1 overflow-y-auto bg-cream-100/40 dark:bg-ash-850">
          <!-- PDF inline iframe -->
          <iframe
            v-if="activeFile.ext === '.pdf'"
            :src="rawUrl(activeFile)"
            class="w-full h-full min-h-[60vh] border-0 bg-white"
          />
          <!-- TXT / MD / CSV -->
          <pre
            v-else-if="['.txt', '.md', '.csv'].includes(activeFile.ext)"
            class="px-5 py-4 text-xs leading-relaxed text-ink-800 dark:text-ink-100 whitespace-pre-wrap font-mono"
          >{{ previewText || '(kosong)' }}</pre>
          <!-- DOCX / DOC / XLSX / XLS: show extracted text -->
          <div v-else class="px-5 py-4 text-xs leading-relaxed text-ink-800 dark:text-ink-100 whitespace-pre-wrap font-mono">
            <div v-if="!previewText" class="text-ink-500 dark:text-ink-300">(tidak bisa di-preview di browser)</div>
            <template v-else>{{ previewText }}</template>
          </div>
        </div>
          </div>
          <!-- TXT / MD -->
          <pre
            v-else-if="['.txt', '.md'].includes(activeFile.ext)"
            class="px-5 py-4 text-xs leading-relaxed text-ink-800 dark:text-ink-100 whitespace-pre-wrap font-mono"
          >{{ previewText || '(kosong)' }}</pre>
          <!-- DOCX / DOC: show extracted text -->
          <div v-else class="px-5 py-4 text-xs leading-relaxed text-ink-800 dark:text-ink-100 whitespace-pre-wrap font-mono">
            <div v-if="!previewText" class="text-ink-500 dark:text-ink-300">(tidak bisa di-preview di browser)</div>
            <template v-else>{{ previewText }}</template>
          </div>
        </div>
      </section>
    </div>

    <AppDialog v-if="deleteFileTarget" :open="!!deleteFileTarget" title="Hapus file?" @close="deleteFileTarget = null">
      <p class="text-sm text-ink-700 dark:text-ink-200">Hapus "{{ deleteFileTarget.original_name }}"?</p>
      <template #actions>
        <button @click="deleteFileTarget = null" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button @click="confirmRemoveFile" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Delete</button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { usePaperStore } from '../stores/paper.js'
import api from '../api/index.js'
import AppDialog from './AppDialog.vue'

const store = usePaperStore()

const MAX_FILE_SIZE = 30 * 1024 * 1024 // 30MB

const files = ref([])
const loading = ref(false)
const uploading = ref(false)
const uploadProgress = ref('')
const warning = ref('')
const uploadAbortController = ref(null)

const fileInput = ref(null)
const activeFileId = ref(null)
const previewText = ref('')
const deleteFileTarget = ref(null)

const activeFile = computed(() => files.value.find(f => f.id === activeFileId.value))
const pdfError = ref(false)

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

  // Frontend validation: check file sizes before upload
  const oversized = list.filter(f => f.size > MAX_FILE_SIZE)
  if (oversized.length > 0) {
    const names = oversized.map(f => f.name).join(', ')
    warning.value = `File terlalu besar (max 30MB): ${names}`
    if (oversized.length === list.length) return
  }

  const validFiles = list.filter(f => f.size <= MAX_FILE_SIZE)
  if (!validFiles.length) return

  uploading.value = true
  warning.value = ''
  uploadProgress.value = `0/${validFiles.length} files - 0%`
  
  // Create AbortController for cancellation support
  uploadAbortController.value = new AbortController()
  
  try {
    const fd = new FormData()
    validFiles.forEach(f => fd.append('files', f))
    const res = await api.post(`/api/papers/${store.currentPaperId}/files`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      signal: uploadAbortController.value.signal,
      onUploadProgress: (evt) => {
        if (evt.total) {
          const pct = Math.round((evt.loaded / evt.total) * 100)
          uploadProgress.value = `${validFiles.length} files - ${pct}%`
        }
      },
    })
    const newFiles = res.data.files || []
    files.value = [...newFiles, ...files.value]
    if (newFiles.length) selectFile(newFiles[0])
    if (res.data.warnings?.length) warning.value = res.data.warnings.join('; ')
  } catch (e) {
    if (e.name === 'CanceledError' || e.code === 'ERR_CANCELED') {
      warning.value = 'Upload dibatalkan'
    } else {
      warning.value = 'Upload gagal: ' + (e.response?.data?.error || e.message)
    }
  } finally {
    uploading.value = false
    uploadProgress.value = ''
    uploadAbortController.value = null
  }
}

function cancelUpload() {
  if (uploadAbortController.value) {
    uploadAbortController.value.abort()
  }
}

function removeFile(f) {
  deleteFileTarget.value = f
}

async function confirmRemoveFile() {
  const f = deleteFileTarget.value
  if (!f) return
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
  } finally {
    deleteFileTarget.value = null
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
    case '.xlsx':
    case '.xls': return '📊'
    case '.csv': return '📈'
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
