<template>
 <div class="p-6"
  @dragover.prevent="dragging = true"
  @dragleave.self="dragging = false"
  @drop.prevent="onDrop">

  <!-- Drag overlay -->
  <div v-if="dragging" class="fixed inset-0 z-50 bg-[#238f7f]/10 dark:bg-[#238f7f]/20 flex items-center justify-center pointer-events-none">
    <div class="bg-white dark:bg-ash-800 border-2 border-dashed border-[#238f7f] rounded-2xl px-12 py-16 text-center shadow-xl">
      <div class="text-5xl mb-3">📂</div>
      <div class="text-lg font-semibold text-ink-900 dark:text-ink-50">Drop file di sini</div>
      <div class="text-xs text-ink-500 dark:text-ink-300 mt-1">Upload otomatis saat dilepas</div>
    </div>
  </div>

 <div class="flex items-center justify-between mb-4 max-w-5xl mx-auto">
 <div>
 <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">Files</h2>
 <p class="text-xs text-ink-600 dark:text-ink-300 mt-0.5">PDF / DOCX / DOC / TXT / MD / XLSX / XLS / CSV / PPTX — tanpa batasan ukuran file. Bisa upload banyak file sekaligus. Drag & drop dari desktop.</p>
 </div>
 <div class="flex items-center gap-2">
 <input
 ref="fileInput"
 type="file"
 accept=".pdf,.docx,.doc,.txt,.md,.xlsx,.xls,.csv,.pptx,.ppt"
 multiple
 class="hidden"
 @change="onFileChange"
 />
 <button
 v-if="!uploading"
 @click="fileInput?.click()"
 :disabled="!store.currentPaperId"
 class="px-3 py-1.5 bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-xs font-medium disabled:opacity-50 transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30"
 >
 ＋ Upload file
 </button>
 <div v-else class="flex items-center gap-2">
 <span class="text-xs text-ink-600 dark:text-ink-300">{{ uploadProgress }}</span>
 <button
 @click="cancelUpload"
 class="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-medium transition"
 >
 ✕ Cancel
 </button>
 </div>
 </div>
 </div>

 <p v-if="warning" class="max-w-5xl mx-auto mb-3 text-xs text-amber-700 dark:text-amber-300">{{ warning }}</p>

 <div class="max-w-5xl mx-auto grid lg:grid-cols-[280px,1fr] gap-4">
 <!-- File list (left) -->
 <aside class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden">

 <!-- Toolbar: select all + bulk delete -->
 <div class="px-3 py-2 border-b border-cream-300 dark:border-ash-700 flex items-center justify-between bg-cream-100 dark:bg-ash-850">
   <label class="flex items-center gap-1.5 text-xs font-semibold text-ink-700 dark:text-ink-200 cursor-pointer select-none">
     <input type="checkbox" :checked="allChecked" @change="toggleAll"
      class="h-3.5 w-3.5 rounded accent-navy-700" />
     <span>{{ files.length }} file{{ files.length === 1 ? '' : 's' }}</span>
   </label>
   <button v-if="selectedIds.size > 0"
    @click="bulkRemove"
    class="px-2 py-1 text-[11px] rounded bg-rose-600 hover:bg-rose-700 text-white font-medium transition">
     🗑 Hapus {{ selectedIds.size }} file
   </button>
 </div>

 <div v-if="loading" class="px-3 py-6 text-center text-xs text-ink-500 dark:text-ink-300">Loading…</div>
 <div v-else-if="!files.length" class="px-3 py-12 text-center text-xs text-ink-500 dark:text-ink-300">
 Belum ada file. Klik <strong>＋ Upload file</strong> atau drag & drop di sini.
 </div>
 <ul v-else class="divide-y divide-cream-200 dark:divide-ash-700 max-h-[60vh] overflow-y-auto">
 <li
 v-for="f in files"
 :key="f.id"
 draggable="true"
 :class="[
 'group px-3 py-2 cursor-pointer flex items-start gap-1.5 transition',
 activeFileId === f.id ? 'bg-cream-200 dark:bg-ash-700' : 'hover:bg-cream-100 dark:hover:bg-ash-700',
 ]"
 @click="selectFile(f)"
 @dragstart.self="onDragStart($event, f)"
 @dragover.self.prevent="onItemDragOver(f)"
 @drop.self.prevent="onItemDrop(f)">
 <input type="checkbox" :checked="selectedIds.has(f.id)" @change.stop="toggleOne(f.id)"
  class="mt-1 h-3.5 w-3.5 rounded accent-navy-700 shrink-0" />
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
 title="Hapus">🗑</button>
 </li>
 </ul>
 </aside>

 <!-- Preview pane (right) -->
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
 </div>
 </header>

 <div v-if="!activeFile" class="flex-1 flex items-center justify-center text-xs text-ink-500 dark:text-ink-300">
 Pilih file di kiri untuk melihat preview.
 </div>

 <div v-else class="flex-1 overflow-y-auto bg-cream-100/40 dark:bg-ash-850">
 <!-- All files: show extracted markdown text -->
 <div v-if="previewLoading" class="px-5 py-8 text-center text-xs text-ink-500 dark:text-ink-300">Loading preview…</div>
 <div v-else-if="!previewText" class="px-5 py-8 text-center text-xs text-ink-500 dark:text-ink-300">
 (preview tidak tersedia)
 </div>
 <div v-else class="px-5 py-4 text-xs leading-relaxed text-ink-800 dark:text-ink-100 whitespace-pre-wrap font-mono">
 {{ previewText }}
 </div>
 </div>
 </section>
 </div>
 </div>

 <AppDialog v-if="deleteFileTarget" :open="!!deleteFileTarget" title="Hapus file?" @close="deleteFileTarget = null">
 <p class="text-sm text-ink-700 dark:text-ink-200">Hapus "{{ deleteFileTarget.original_name }}"?</p>
 <template #actions>
 <button @click="deleteFileTarget = null" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
 <button @click="confirmRemoveFile" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Delete</button>
 </template>
 </AppDialog>

 <AppDialog :open="!!bulkConfirmTarget" title="Hapus file?" @close="bulkConfirmTarget = false">
 <p class="text-sm text-ink-700 dark:text-ink-200">Hapus <strong>{{ selectedIds.size }}</strong> file yang dipilih?</p>
 <template #actions>
 <button @click="bulkConfirmTarget = false" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
 <button @click="confirmBulkRemove" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Delete All</button>
 </template>
 </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { usePaperStore } from '../stores/paper'
import api from '../api/index'
import AppDialog from './AppDialog.vue'

interface FileItem {
 id: number
 original_name: string
 filename: string
 ext: string
 size: number
 size_bytes?: number
 url: string
 uploaded_at: string
 created_at?: string
}

const store = usePaperStore()

const MAX_FILE_SIZE = 1024 * 1024 * 1024 // 1GB per file (unrestricted)

const files = ref<FileItem[]>([])
const loading = ref(false)
const uploading = ref(false)
const uploadProgress = ref('')
const previewLoading = ref(false)
const warning = ref('')
const uploadAbortController = ref<AbortController | null>(null)
const dragging = ref(false)
const selectedIds = ref(new Set<number>())
const bulkConfirmTarget = ref(false)
const dragTarget = ref<FileItem | null>(null)

const fileInput = ref<HTMLInputElement | null>(null)
const activeFileId = ref<number | null>(null)
const previewText = ref('')
const deleteFileTarget = ref<FileItem | null>(null)

const activeFile = computed(() => files.value.find(f => f.id === activeFileId.value))

const allChecked = computed(() => files.value.length > 0 && selectedIds.value.size === files.value.length)

async function load(): Promise<void> {
 if (!store.currentPaperId) return
 loading.value = true
 selectedIds.value = new Set()
 try {
 const res = await api.get(`/api/papers/${store.currentPaperId}/files`)
 files.value = res.data.files || []
 if (files.value.length && !activeFileId.value) {
 selectFile(files.value[0])
 }
 } catch (e: any) {
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

// Refresh file list when a chat draft is exported (cross-component signal)
function _onChatDraftSaved(e: Event): void {
 const detail = (e as CustomEvent)?.detail
 if (detail?.paperId && detail.paperId === store.currentPaperId) {
 load()
 }
}
onMounted(() => window.addEventListener('chat-draft-saved', _onChatDraftSaved as EventListener))
onUnmounted(() => window.removeEventListener('chat-draft-saved', _onChatDraftSaved as EventListener))

async function selectFile(f: FileItem): Promise<void> {
 activeFileId.value = f.id
 previewText.value = ''
 previewLoading.value = true
 if (!store.currentPaperId) { previewLoading.value = false; return }
 try {
 const res = await api.get(`/api/papers/${store.currentPaperId}/files/${f.id}/preview`)
 previewText.value = res.data.text || ''
 } catch (e: any) {
 previewText.value = '(gagal memuat preview: ' + (e.message || e) + ')'
 } finally {
 previewLoading.value = false
 }
}

async function onFileChange(e: Event): Promise<void> {
 const target = e.target as HTMLInputElement
 const list = Array.from(target.files || [])
 if (fileInput.value) fileInput.value.value = ''
 if (!list.length || !store.currentPaperId) return
 await uploadFiles(list)
}

async function onDrop(e: DragEvent): Promise<void> {
 dragging.value = false
 const list = Array.from(e.dataTransfer?.files || [])
 if (!list.length || !store.currentPaperId) return
 await uploadFiles(list)
}

function onDragStart(e: DragEvent, _f: FileItem): void {
 e.dataTransfer!.effectAllowed = 'move'
 ;(e.target as HTMLElement).classList.add('opacity-50')
}

function onItemDragOver(f: FileItem): void {
 dragTarget.value = f
}

function onItemDrop(target: FileItem): Promise<void> {
 dragTarget.value = null
 if (!store.currentPaperId) return
 const fromIdx = files.value.findIndex(f => f.id === target.id)
 const toIdx = files.value.findIndex(f => f.id === (dragTarget.value?.id ?? -1))
 if (fromIdx === -1 || toIdx === -1 || fromIdx === toIdx) return
 const [moved] = files.value.splice(fromIdx, 1)
 files.value.splice(toIdx, 0, moved)
}

async function uploadFiles(validFiles: File[]): Promise<void> {
 const oversized = validFiles.filter(f => f.size > MAX_FILE_SIZE)
 if (oversized.length > 0) {
 const names = oversized.map(f => f.name).join(', ')
 warning.value = `File terlalu besar: ${names}`
 if (oversized.length === validFiles.length) return
 }

 validFiles = validFiles.filter(f => f.size <= MAX_FILE_SIZE)
 if (!validFiles.length) return

 uploading.value = true
 warning.value = ''
 uploadProgress.value = `0/${validFiles.length} files - 0%`

 uploadAbortController.value = new AbortController()

 try {
 const fd = new FormData()
 validFiles.forEach(f => fd.append('files', f))
 const res = await api.post(`/api/papers/${store.currentPaperId}/files`, fd, {
 headers: { 'Content-Type': 'multipart/form-data' },
 signal: uploadAbortController.value.signal,
 onUploadProgress: (evt: any) => {
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
 } catch (e: any) {
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

function cancelUpload(): void {
 if (uploadAbortController.value) {
 uploadAbortController.value.abort()
 }
}

// ── Checkbox helpers ──
function toggleOne(id: number): void {
 if (selectedIds.value.has(id)) selectedIds.value.delete(id)
 else selectedIds.value.add(id)
 selectedIds.value = new Set(selectedIds.value)
}

function toggleAll(): void {
 if (allChecked.value) selectedIds.value = new Set()
 else selectedIds.value = new Set(files.value.map(f => f.id))
}

function bulkRemove(): void {
 if (selectedIds.value.size === 0) return
 bulkConfirmTarget.value = true
}

async function confirmBulkRemove(): Promise<void> {
 if (!store.currentPaperId) return
 const ids = [...selectedIds.value]
 bulkConfirmTarget.value = false
 try {
 await Promise.all(
 ids.map(id => api.delete(`/api/papers/${store.currentPaperId}/files/${id}`))
 )
 files.value = files.value.filter(f => !ids.includes(f.id))
 selectedIds.value = new Set()
 if (!files.value.find(f => f.id === activeFileId.value)) {
 activeFileId.value = files.value[0]?.id || null
 previewText.value = ''
 if (activeFileId.value) selectFile(files.value[0])
 }
 } catch (e: any) {
 warning.value = 'Hapus gagal: ' + (e.response?.data?.error || e.message)
 }
}

function removeFile(f: FileItem): void {
 deleteFileTarget.value = f
}

async function confirmRemoveFile(): Promise<void> {
 const f = deleteFileTarget.value
 if (!f || !store.currentPaperId) return
 try {
 await api.delete(`/api/papers/${store.currentPaperId}/files/${f.id}`)
 files.value = files.value.filter(x => x.id !== f.id)
 if (activeFileId.value === f.id) {
 activeFileId.value = files.value[0]?.id || null
 previewText.value = ''
 if (activeFileId.value) selectFile(files.value[0])
 }
 } catch (e: any) {
 warning.value = 'Hapus gagal: ' + (e.response?.data?.error || e.message)
 } finally {
 deleteFileTarget.value = null
 }
}

function rawUrl(f: FileItem): string {
 return f.url
}

function extIcon(ext: string): string {
 switch ((ext || '').toLowerCase()) {
 case '.pdf': return '📕'
 case '.docx':
 case '.doc': return '📘'
 case '.xlsx':
 case '.xls': return '📊'
 case '.csv': return '📈'
 case '.pptx':
 case '.ppt': return '📙'
 case '.txt': return '📄'
 case '.md': return '📝'
 default: return '📁'
 }
}

function humanSize(b: number): string {
 if (!b) return '0 B'
 if (b < 1024) return b + ' B'
 if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
 return (b / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDate(s: string): string {
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
