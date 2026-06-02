<template>
  <div class="p-6">
    <!-- Tab toggle: Documents vs Figures -->
    <div class="flex items-center gap-1 mb-4 max-w-5xl mx-auto">
      <button @click="subTab = 'docs'"
        :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
          subTab === 'docs' ? 'bg-navy-700 dark:bg-cream-200 text-cream-50 dark:text-ash-900' : 'text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700']">
        📄 Dokumen
      </button>
      <button @click="subTab = 'figures'"
        :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1',
          subTab === 'figures' ? 'bg-navy-700 dark:bg-cream-200 text-cream-50 dark:text-ash-900' : 'text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700']">
        🖼 Figures &amp; Images
        <span v-if="store.figureItems.length" class="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-amber-500 text-white text-[10px] font-bold">{{ store.figureItems.length }}</span>
      </button>
    </div>

    <!-- ═══ DOCUMENTS SUB-TAB ═══ -->
    <template v-if="subTab === 'docs'">
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
          class="px-3 py-1.5 bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30"
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
      </section>
    </div>

    <AppDialog v-if="deleteFileTarget" :open="!!deleteFileTarget" title="Hapus file?" @close="deleteFileTarget = null">
      <p class="text-sm text-ink-700 dark:text-ink-200">Hapus "{{ deleteFileTarget.original_name }}"?</p>
      <template #actions>
        <button @click="deleteFileTarget = null" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button @click="confirmRemoveFile" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Delete</button>
      </template>
    </AppDialog>
    </template>

    <!-- ═══ FIGURES & IMAGES SUB-TAB ═══ -->
    <div v-if="subTab === 'figures'" class="max-w-5xl mx-auto">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">Figures &amp; Images</h2>
          <p class="text-xs text-ink-600 dark:text-ink-300 mt-0.5">
            Kelola gambar untuk setiap figure di paper. Upload gambar, generate dengan AI, atau pilih dari chart.
            Prompt dari "Generate Full Paper" otomatis tersimpan di sini — bisa dimodifikasi sebelum generate ulang.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <input ref="figureImageInput" type="file" accept="image/*" multiple class="hidden" @change="onFigureImageUpload" />
           <button @click="figureImageInput?.click()" :disabled="!store.currentPaperId"
            class="px-3 py-1.5 bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
            ＋ Upload Gambar
          </button>
           <button @click="refreshSources"
            class="px-3 py-1.5 text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700 rounded-lg text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
            ↻ Refresh
          </button>
        </div>
      </div>

      <p v-if="figureWarn" class="mb-3 text-xs text-amber-700 dark:text-amber-300">{{ figureWarn }}</p>

      <!-- No figures yet -->
      <div v-if="!store.figureItems.length" class="border-2 border-dashed border-cream-300 dark:border-ash-700 rounded-xl p-10 text-center text-ink-500 dark:text-ink-400">
        <p class="text-sm">Belum ada figure di paper.</p>
        <p class="text-xs mt-1">Tambahkan gambar di tab Editor dengan klik <strong>+ Image</strong> di section manapun.</p>
      </div>

      <!-- Figures grid -->
      <div v-else class="space-y-4">
        <div v-for="fig in store.figureItems" :key="stableKey(fig.item)"
          class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden">
          <!-- Figure header -->
          <div class="px-4 py-2.5 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-850 flex items-center gap-2">
            <span class="text-xs font-bold px-2 py-0.5 rounded bg-navy-600 dark:bg-cream-300 text-cream-50 dark:text-ash-900">Fig. {{ fig.label }}</span>
            <span class="text-xs text-ink-500 dark:text-ink-300 truncate">Section: {{ fig.sectionTitle || '(tanpa judul)' }}</span>
          </div>

          <div class="p-4 grid md:grid-cols-[200px,1fr] gap-4">
            <!-- LEFT: Image preview + picker -->
            <div class="space-y-2">
              <div class="aspect-[4/3] rounded-lg border border-cream-300 dark:border-ash-600 bg-cream-100 dark:bg-ash-700 flex items-center justify-center overflow-hidden">
                <img v-if="fig.item.Path" :src="thumbUrl(fig.item.Path)" :alt="fig.item.Title || 'Figure image'"
                  class="max-h-full max-w-full object-contain" @error="onThumbErr" />
                <div v-else class="text-ink-400 dark:text-ink-500 text-xs text-center px-2">
                  <span class="text-2xl block mb-1">🖼</span>
                  Belum ada gambar
                </div>
              </div>

              <!-- Source picker (gallery) -->
              <div class="space-y-1.5">
                <button @click="toggleFigGallery(fig)" type="button"
                  class="w-full px-2.5 py-1.5 bg-cream-200 dark:bg-anthracite-600 hover:bg-cream-300 dark:hover:bg-anthracite-500 text-navy-700 dark:text-anthracite-100 rounded text-xs font-medium flex items-center justify-between gap-1 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                  <span class="flex items-center gap-1">
                    <span>{{ figGalleryOpen[fig.label] ? '▾' : '▸' }}</span>
                    🖼 Pilih dari galeri
                  </span>
                  <span v-if="store.figureSources.length" class="text-[10px] px-1.5 py-0.5 rounded-full bg-navy-600 dark:bg-cream-300 text-cream-50 dark:text-ash-900">{{ store.figureSources.length }}</span>
                </button>

                <div v-show="figGalleryOpen[fig.label]" class="rounded border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 p-2">
                  <div v-if="!store.figureSources.length" class="text-[11px] text-ink-500 dark:text-anthracite-300 px-1 py-2 text-center">
                    Belum ada gambar. Upload, generate, atau buat chart di tab Data.
                  </div>
                  <div v-else class="grid grid-cols-3 gap-2">
                    <button v-for="src in store.figureSources" :key="src.filename" type="button"
                      @click="pickFigSource(fig, src)"
                      :disabled="store.isSourceUsedByOther(src.filename, fig.item)"
                      :class="['relative rounded border overflow-hidden text-left transition-all',
                        fig.item.Path === src.filename
                          ? 'border-navy-600 dark:border-cream-300 ring-2 ring-navy-300 dark:ring-cream-500'
                          : 'border-cream-300 dark:border-anthracite-500 hover:border-navy-400',
                        store.isSourceUsedByOther(src.filename, fig.item)
                          ? 'opacity-45 cursor-not-allowed'
                          : 'cursor-pointer']"
                      :title="store.isSourceUsedByOther(src.filename, fig.item) ? `Dipakai Fig. ${otherFigLabel(src.filename)} — tidak bisa dipilih` : src.label">
                      <div class="aspect-[4/3] bg-cream-100 dark:bg-anthracite-700 flex items-center justify-center">
                        <img :src="thumbUrl(src.filename)" :alt="src.label" class="max-h-full max-w-full object-contain" @error="onThumbErr" />
                      </div>
                      <span class="absolute top-1 left-1 text-[9px] px-1 rounded bg-black/55 text-white font-medium">{{ srcKindLabel(src.kind) }}</span>
                      <span v-if="fig.item.Path === src.filename" class="absolute top-1 right-1 text-[10px] w-4 h-4 flex items-center justify-center rounded-full bg-navy-600 dark:bg-cream-300 text-cream-50 dark:text-ash-900 font-bold">✓</span>
                      <span v-else-if="store.isSourceUsedByOther(src.filename, fig.item)" class="absolute top-1 right-1 text-[9px] px-1 rounded bg-amber-500 text-white font-medium">Fig {{ otherFigLabel(src.filename) }}</span>
                      <span class="block text-[10px] text-ink-700 dark:text-anthracite-100 px-1 py-0.5 truncate">{{ src.label }}</span>
                    </button>
                  </div>
                </div>
              </div>

              <!-- Direct upload for this figure -->
               <label class="w-full px-2.5 py-1.5 bg-cream-200 dark:bg-anthracite-600 hover:bg-cream-300 dark:hover:bg-anthracite-500 text-navy-700 dark:text-anthracite-100 rounded text-xs font-medium cursor-pointer flex items-center justify-center gap-1 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                📤 {{ fig.item.Path ? 'Ganti' : 'Upload' }} Gambar
                <input type="file" accept="image/*" class="hidden" @change="uploadForFigure($event, fig)" />
              </label>

              <button v-if="fig.item.Path" @click="removeFigImage(fig)" type="button"
                class="w-full px-2 py-1 text-red-400 hover:text-red-600 rounded text-[11px] text-center">✕ Lepas gambar</button>
            </div>

            <!-- RIGHT: Caption + Prompt -->
            <div class="space-y-3">
              <!-- Caption -->
              <div>
                <label class="block text-xs font-medium text-ink-700 dark:text-ink-200 mb-1">Caption / Judul Gambar</label>
                <input :value="fig.item.Title || ''" @input="fig.item.Title = ($event.target as HTMLInputElement).value"
                  class="w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-800 text-ink-900 dark:text-ink-50 rounded text-sm outline-none focus:border-navy-400"
                  placeholder="Fig. caption..." />
              </div>

              <!-- AI Prompt -->
              <div>
                <div class="flex items-center justify-between mb-1">
                  <label class="text-xs font-medium text-ink-700 dark:text-ink-200">AI Prompt</label>
                  <span class="text-[10px] text-ink-400 dark:text-ink-500">Generate ulang gambar dengan prompt ini</span>
                </div>
                <textarea :value="fig.item.Prompt || ''" @input="fig.item.Prompt = ($event.target as HTMLTextAreaElement).value"
                  rows="3"
                  class="w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-800 text-ink-900 dark:text-ink-50 rounded text-xs outline-none focus:border-navy-400 resize-none"
                  placeholder="Deskripsi gambar untuk AI (contoh: 'create image: diagram of IoT architecture with 3 layers...')"></textarea>
              </div>

              <!-- Generate button -->
              <div class="flex items-center gap-2">
                <button @click="generateForFigure(fig)" type="button"
                  :disabled="!String(fig.item.Prompt || '').trim() || !!figGenerating[fig.label]"
                  class="px-3 py-1.5 bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                  <span v-if="figGenerating[fig.label]" class="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
                  ✨ Generate Image
                </button>
                <span v-if="figGenerating[fig.label]" class="text-[11px] text-ink-500 dark:text-ink-300">generating…</span>
              </div>

              <!-- Filename info -->
              <p v-if="fig.item.Path" class="text-[11px] text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/30 rounded px-2 py-1 truncate" :title="fig.item.Path">📷 {{ fig.item.Path }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed, reactive } from 'vue'
import { usePaperStore } from '../stores/paper'
import { useImageGenStore } from '../stores/imageGen'
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
const imageGenStore = useImageGenStore()

const subTab = ref<'docs' | 'figures'>('docs')

const MAX_FILE_SIZE = 30 * 1024 * 1024

const files = ref<FileItem[]>([])
const loading = ref(false)
const uploading = ref(false)
const uploadProgress = ref('')
const warning = ref('')
const uploadAbortController = ref<AbortController | null>(null)

const fileInput = ref<HTMLInputElement | null>(null)
const figureImageInput = ref<HTMLInputElement | null>(null)
const activeFileId = ref<number | null>(null)
const previewText = ref('')
const deleteFileTarget = ref<FileItem | null>(null)

const figureWarn = ref('')
const figGalleryOpen = reactive<Record<string, boolean>>({})
const figGenerating = reactive<Record<string, boolean>>({})
const figKeyMap = new WeakMap<object, string>()
let _figKc = 0

function stableKey(obj: any): string {
  if (typeof obj !== 'object' || !obj) return String(obj)
  if (!figKeyMap.has(obj)) figKeyMap.set(obj, String(++_figKc))
  return figKeyMap.get(obj)!
}

const activeFile = computed(() => files.value.find(f => f.id === activeFileId.value))

async function load(): Promise<void> {
  if (!store.currentPaperId) return
  loading.value = true
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

// When switching to figures tab, ensure sources are fresh
watch(subTab, (newTab) => {
  if (newTab === 'figures' && store.currentPaperId) {
    store.loadPaperImages(store.currentPaperId)
    store.loadPaperCharts(store.currentPaperId)
  }
})

async function selectFile(f: FileItem): Promise<void> {
  activeFileId.value = f.id
  previewText.value = ''
  if (!store.currentPaperId) return
  if (['.pdf'].includes(f.ext)) return
  try {
    const res = await api.get(`/api/papers/${store.currentPaperId}/files/${f.id}/preview`)
    previewText.value = res.data.text || ''
  } catch (e: any) {
    previewText.value = '(gagal memuat preview: ' + (e.message || e) + ')'
  }
}

async function onFileChange(e: Event): Promise<void> {
  const target = e.target as HTMLInputElement
  const list = Array.from(target.files || [])
  if (fileInput.value) fileInput.value.value = ''
  if (!list.length || !store.currentPaperId) return

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

// ─── Figure / Image management ─────────────────────────────────────────
function thumbUrl(filename: string): string {
  const pid = store.currentPaperId
  if (!pid || pid === 'null' || pid === 'undefined' || !filename) return ''
  return `/api/images/${pid}/${filename}`
}

function onThumbErr(e: Event): void {
  const target = e.target as HTMLImageElement
  target.style.display = 'none'
}

function toggleFigGallery(fig: any): void {
  const k = fig.label
  figGalleryOpen[k] = !figGalleryOpen[k]
  if (figGalleryOpen[k] && store.currentPaperId) {
    store.loadPaperImages(store.currentPaperId)
    store.loadPaperCharts(store.currentPaperId)
  }
}

function pickFigSource(fig: any, src: { filename: string }): void {
  if (fig.item.Path === src.filename) {
    store.setFigureSource(fig.item, '')
    return
  }
  store.setFigureSource(fig.item, src.filename)
}

function srcKindLabel(kind: string): string {
  if (kind === 'chart') return '📊 chart'
  if (kind === 'generated') return '✨ AI'
  return '📤 upload'
}

function otherFigLabel(filename: string): string {
  const owner = store.figureSourceUsage.get(filename)
  if (!owner) return '?'
  return store.getItemNumber?.(owner)?.label || '?'
}

async function uploadForFigure(e: Event, fig: any): Promise<void> {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const img = await store.uploadImage(undefined, file)
  if (img) fig.item.Path = img.filename
  target.value = ''
  if (store.currentPaperId) store.loadPaperImages(store.currentPaperId)
}

function removeFigImage(fig: any): void {
  store.setFigureSource(fig.item, '')
}

async function generateForFigure(fig: any): Promise<void> {
  const prompt = String(fig.item.Prompt || '').trim()
  if (!prompt) return
  if (!store.currentPaperId) {
    store.showToast('Simpan paper dulu sebelum generate gambar.', 'error')
    return
  }
  const k = fig.label
  figGenerating[k] = true
  try {
    await imageGenStore.enqueue({
      paperId: store.currentPaperId,
      prompt,
      onDone: (img: any) => {
        if (img && img.filename) {
          fig.item.Path = img.filename
          if (store.currentPaperId) store.loadPaperImages(store.currentPaperId)
        }
        figGenerating[k] = false
      },
      onError: (err: any) => {
        store.showToast('Generate gagal: ' + (err || 'unknown'), 'error')
        figGenerating[k] = false
      },
    })
  } catch (err: any) {
    store.showToast('Generate gagal: ' + (err.message || err), 'error')
    figGenerating[k] = false
  }
}

async function onFigureImageUpload(e: Event): Promise<void> {
  const target = e.target as HTMLInputElement
  const files = Array.from(target.files || [])
  target.value = ''
  if (!files.length || !store.currentPaperId) return
  for (const file of files) {
    try {
      await store.uploadImage(undefined, file)
    } catch (err: any) {
      figureWarn.value = 'Upload gagal: ' + (err.message || err)
    }
  }
  if (store.currentPaperId) store.loadPaperImages(store.currentPaperId)
}

function refreshSources(): void {
  if (store.currentPaperId) {
    store.loadPaperImages(store.currentPaperId)
    store.loadPaperCharts(store.currentPaperId)
  }
}
</script>
