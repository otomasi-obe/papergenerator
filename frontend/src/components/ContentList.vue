<template>
  <draggable :list="items" :item-key="stableKey" animation="150" handle=".content-drag" class="space-y-1.5"
             :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
    <template #item="{ element: item, index: idx }">
    <div class="relative">
      <!-- Box (utama) -->
      <div class="bg-ivory-100 dark:bg-anthracite-800 border border-ivory-300 dark:border-anthracite-500 rounded-lg p-3 relative group transition-colors"
           :data-content-box="idx">

        <!-- Item header -->
        <div class="flex items-center justify-between mb-1.5">
          <div class="flex items-center gap-1.5">
             <span class="content-drag cursor-grab active:cursor-grabbing text-cream-400 dark:text-ash-400 hover:text-navy-500 dark:hover:text-cream-300 select-none text-base leading-none px-0.5" role="button" aria-label="Drag to reorder">⠿</span>
            <span v-if="item.id !== 'gambar'" class="text-[10px] font-medium uppercase tracking-wide pl-1.5 border-l-2"
              :class="badgeClass(item.id)">
              {{ badgeLabel(item, idx) }}
            </span>
            <span v-else class="text-[10px] font-medium uppercase tracking-wide pl-1.5 border-l-2"
              :class="badgeClass(item.id)">
              Fig. {{ store.getItemNumber?.(item)?.label || '?' }}
            </span>
          </div>
          <button @click="store.removeContent(items, idx)"
            class="text-red-300 dark:text-red-400 hover:text-red-500 dark:hover:text-red-300 text-xs px-1 opacity-60 group-hover:opacity-100">✕</button>
        </div>

        <!-- TEXT -->
        <template v-if="item.id === 'text'">
          <textarea :value="item.text"
            @input="item.text = ($event.target as HTMLTextAreaElement).value"
            v-autosize
            rows="2"
             class="content-textarea-auto w-full px-2.5 py-2 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-navy-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm focus:ring-2 focus:ring-cream-200 focus:border-navy-400 outline-none break-words resize-none overflow-hidden"
            placeholder="Write text content... Use [1], [2] for citations."></textarea>
        </template>

        <!-- IMAGE / GAMBAR -->
        <template v-else-if="item.id === 'gambar'">
          <div class="space-y-2">
             <input v-model="item.Title" class="w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-navy-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm outline-none focus:border-navy-400"
              placeholder="Image Title / Caption" />

            <!-- Thumbnail (always rendered when there's a path or live preview from current job) -->
            <div v-if="item.Path" class="rounded border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-700 overflow-hidden flex items-center justify-center" style="max-height:280px">
              <img :src="thumbUrl(item.Path)" :alt="item.Title || 'image'"
                   class="max-h-[280px] max-w-full object-contain"
                   @error="onThumbError($event, item)" />
            </div>

            <!-- Action row: Upload + Gallery + Prompt toggle. Layout is identical
                 whether or not an image exists, so the toolbar doesn't shift. -->
            <div class="flex items-center gap-2 flex-wrap">
               <label class="px-2.5 py-1.5 bg-cream-200 dark:bg-anthracite-600 hover:bg-cream-300 dark:hover:bg-anthracite-500 text-navy-700 dark:text-anthracite-100 rounded text-xs cursor-pointer flex items-center gap-1 font-medium focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                📤 {{ item.Path ? 'Replace' : 'Upload' }}
                <input type="file" accept="image/*" class="hidden" @change="uploadContentImage($event, item)" />
              </label>
              <button @click="toggleGallery(item)" type="button"
                class="px-2.5 py-1.5 bg-cream-200 dark:bg-anthracite-600 hover:bg-cream-300 dark:hover:bg-anthracite-500 text-navy-700 dark:text-anthracite-100 rounded text-xs font-medium flex items-center gap-1 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                <span>{{ galleryOpen[stableKey(item)] ? '▾' : '▸' }}</span>
                <span>🖼 Set dari galeri</span>
                <span v-if="store.figureSources.length"
                  class="inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-navy-600 dark:bg-cream-300 text-cream-50 dark:text-ash-900 text-[10px] font-bold">{{ store.figureSources.length }}</span>
              </button>
              <button @click="togglePrompt(item)" type="button"
                class="px-2.5 py-1.5 bg-cream-200 dark:bg-anthracite-600 hover:bg-cream-300 dark:hover:bg-anthracite-500 text-navy-700 dark:text-anthracite-100 rounded text-xs font-medium flex items-center gap-1 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                <span>{{ promptOpen[stableKey(item)] ? '▾' : '▸' }}</span>
                <span>Prompt &amp; Generate</span>
              </button>
              <span v-if="generating[stableKey(item)]" class="text-[11px] text-ink-500 dark:text-ink-300 flex items-center gap-1">
                <span class="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
                generating…
              </span>
              <button v-if="item.Path" @click="removeImagePath(item)" type="button"
                class="ml-auto px-2 py-1 text-red-400 dark:text-red-300 hover:text-red-600 dark:hover:text-red-200 rounded text-[11px]">✕ Lepas image</button>
            </div>

            <!-- Filename hint after upload -->
            <p v-if="item.Path" class="text-[11px] text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/30 rounded px-2 py-1 truncate" :title="item.Path">📷 {{ item.Path }}</p>

            <!-- Source gallery (upload + generated images + charts). Pick one to
                 attach to this figure. A source already used by another figure
                 is disabled so two figures can never share the same image. -->
            <div v-show="galleryOpen[stableKey(item)]" class="rounded border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 p-2">
              <div v-if="!store.figureSources.length" class="text-[11px] text-ink-500 dark:text-anthracite-300 px-1 py-2 text-center">
                Belum ada gambar. Upload, generate dari prompt, atau buat chart di tab Data.
              </div>
              <div v-else class="grid grid-cols-3 sm:grid-cols-4 gap-2">
                <button v-for="src in store.figureSources" :key="src.filename"
                  type="button"
                  @click="pickSource(item, src)"
                  :disabled="store.isSourceUsedByOther(src.filename, item)"
                  :class="['group/src relative rounded border overflow-hidden text-left transition-all',
                    item.Path === src.filename
                      ? 'border-navy-600 dark:border-cream-300 ring-2 ring-navy-300 dark:ring-cream-500'
                      : 'border-cream-300 dark:border-anthracite-500 hover:border-navy-400',
                    store.isSourceUsedByOther(src.filename, item)
                      ? 'opacity-45 cursor-not-allowed'
                      : 'cursor-pointer']"
                  :title="store.isSourceUsedByOther(src.filename, item)
                    ? `Dipakai Fig. ${otherFigLabel(src.filename)} — tidak bisa dipilih`
                    : src.label">
                  <div class="aspect-[4/3] bg-cream-100 dark:bg-anthracite-700 flex items-center justify-center">
                    <img :src="thumbUrl(src.filename)" :alt="src.label"
                         class="max-h-full max-w-full object-contain"
                         @error="onThumbError($event, item)" />
                  </div>
                  <span class="absolute top-1 left-1 text-[9px] px-1 rounded bg-black/55 text-white font-medium">{{ srcKindLabel(src.kind) }}</span>
                   <span v-if="item.Path === src.filename" class="absolute top-1 right-1 text-[10px] w-4 h-4 flex items-center justify-center rounded-full bg-navy-600 dark:bg-cream-300 text-cream-50 dark:text-ash-900 font-bold">✓</span>
                  <span v-else-if="store.isSourceUsedByOther(src.filename, item)" class="absolute top-1 right-1 text-[9px] px-1 rounded bg-amber-500 text-white font-medium">Fig {{ otherFigLabel(src.filename) }}</span>
                  <span class="block text-[10px] text-ink-700 dark:text-anthracite-100 px-1 py-0.5 truncate">{{ src.label }}</span>
                </button>
              </div>
            </div>

            <!-- Prompt + Generate (hidden by default, toggled by the button above) -->
            <div v-show="promptOpen[stableKey(item)]" class="space-y-1.5">
              <textarea :value="item.Prompt || ''"
                @input="item.Prompt = ($event.target as HTMLTextAreaElement).value"
                v-autosize
                rows="2"
                 class="content-textarea-auto w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 rounded text-xs outline-none focus:border-navy-400 text-navy-700 dark:text-anthracite-100 dark:placeholder-anthracite-300 resize-none overflow-hidden"
                placeholder="AI Image Prompt (deskripsi gambar untuk Gemini)"></textarea>
              <button @click="generateImage(item)" type="button"
                :disabled="!String(item.Prompt || '').trim() || !!generating[stableKey(item)]"
                class="px-2.5 py-1.5 bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
                <span v-if="generating[stableKey(item)]" class="w-3 h-3 border-2 border-cream-50 dark:border-ash-900 border-t-transparent rounded-full animate-spin"></span>
                ✨ Generate Image
              </button>
            </div>
          </div>
        </template>

        <!-- TABLE / TABEL -->
        <template v-else-if="item.id === 'tabel'">
          <div class="space-y-2">
             <input v-model="item.Title" class="w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-navy-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm outline-none focus:border-navy-400"
              placeholder="Table Title" />
            <div class="overflow-x-auto">
              <table class="w-full text-xs border-collapse">
                <thead>
                  <tr>
                    <th v-for="(h, ci) in item.Headers" :key="ci"
                      class="border border-cream-300 dark:border-anthracite-500 bg-cream-100 dark:bg-anthracite-700 p-0 relative">
                      <input :value="h" @input="item.Headers[ci] = ($event.target as HTMLInputElement).value"
                        class="w-full px-2 py-1.5 text-xs font-semibold bg-transparent text-navy-900 dark:text-anthracite-50 outline-none text-center" />
                      <button v-if="item.Headers.length > 1"
                        @click="store.removeTableCol(item, ci)"
                        class="absolute -top-2 -right-2 bg-red-400 text-white rounded-full w-4 h-4 text-[10px] leading-none opacity-0 group-hover:opacity-100">✕</button>
                    </th>
                    <th class="w-8">
                       <button @click="store.addTableCol(item)"
                        class="text-navy-400 dark:text-anthracite-300 hover:text-navy-700 dark:hover:text-anthracite-50 text-xs focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">+</button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, ri) in item.Rows" :key="ri">
                    <td v-for="(cell, ci) in row" :key="ci" class="border border-cream-300 dark:border-anthracite-500 p-0">
                       <input :value="cell" @input="item.Rows[ri][ci] = ($event.target as HTMLInputElement).value"
                        class="w-full px-2 py-1 text-xs bg-transparent text-navy-900 dark:text-anthracite-50 outline-none" />
                    </td>
                    <td class="w-8 text-center">
                      <button @click="store.removeTableRow(item, ri)"
                        class="text-red-300 dark:text-red-400 hover:text-red-500 dark:hover:text-red-300 text-[10px]">✕</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
             <button @click="store.addTableRow(item)"
              class="text-xs text-navy-600 dark:text-anthracite-100 hover:text-navy-800 dark:hover:text-anthracite-50 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">+ Add Row</button>
          </div>
        </template>

        <!-- FORMULA / RUMUS -->
        <template v-else-if="item.id === 'rumus'">
           <input v-model="item.latex" class="w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-navy-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm font-mono outline-none focus:border-navy-400"
            placeholder="LaTeX formula, e.g. T_{total} \approx \max(T_{cap}, T_{inf}, T_{modbus})" />
           <div v-if="item.latex" class="mt-1.5 text-center text-sm bg-cream-100 dark:bg-anthracite-700 dark:text-anthracite-100 px-2 py-2 rounded" v-html="renderFormula(item.latex)"></div>
        </template>
      </div>

      <!-- Inline + insert (between this box and the next). Sits at the bottom
           right edge so it never overlaps with content, and the popup menu
           opens upward or leftward to stay within the pane. -->
      <div class="absolute right-2 bottom-0 translate-y-1/2 z-20" v-click-outside-content="() => closeInsert(idx)">
        <button type="button"
          @click="toggleInsert(idx)"
          :class="['w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all',
                   'bg-cream-100 dark:bg-anthracite-700 border border-cream-300 dark:border-anthracite-500 text-navy-500 dark:text-anthracite-100',
                   'hover:bg-navy-700 hover:border-navy-700 hover:text-cream-50 dark:hover:bg-cream-200 dark:hover:text-ash-900',
                   insertOpen === idx ? 'opacity-100 scale-110' : 'opacity-0 group-hover:opacity-100 focus:opacity-100',
                   'shadow-sm']"
          title="Tambah konten setelah box ini">+</button>
        <div v-if="insertOpen === idx"
             class="absolute right-0 bottom-full mb-1 bg-cream-50 dark:bg-anthracite-700 border border-cream-300 dark:border-anthracite-500 rounded-lg shadow-lg p-1 flex flex-col min-w-[140px] z-30">
          <button type="button" @click="insertAfter(idx, 'text')"
            class="text-left px-2.5 py-1 text-xs rounded hover:bg-cream-200 dark:hover:bg-anthracite-600 text-ink-900 dark:text-anthracite-50">📝 Text</button>
          <button type="button" @click="insertAfter(idx, 'gambar')"
            class="text-left px-2.5 py-1 text-xs rounded hover:bg-cream-200 dark:hover:bg-anthracite-600 text-ink-900 dark:text-anthracite-50">🖼 Image</button>
          <button type="button" @click="insertAfter(idx, 'tabel')"
            class="text-left px-2.5 py-1 text-xs rounded hover:bg-cream-200 dark:hover:bg-anthracite-600 text-ink-900 dark:text-anthracite-50">📊 Table</button>
          <button type="button" @click="insertAfter(idx, 'rumus')"
            class="text-left px-2.5 py-1 text-xs rounded hover:bg-cream-200 dark:hover:bg-anthracite-600 text-ink-900 dark:text-anthracite-50">∑ Formula</button>
        </div>
      </div>
    </div>
    </template>
  </draggable>
</template>

<script setup lang="ts">
// @ts-nocheck
import { onMounted, nextTick, reactive, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { usePaperStore } from '../stores/paper'
import { useImageGenStore } from '../stores/imageGen'
import { renderLatex } from '../composables/useMathRender'

function renderFormula(latex: string): string {
  return renderLatex(latex, true)
}

interface ContentItem {
  id: 'text' | 'gambar' | 'tabel' | 'rumus'
  text?: string
  Title?: string
  Path?: string
  Prompt?: string
  JobId?: string
  Headers?: string[]
  Rows?: string[][]
  latex?: string
}

interface Props {
  items: ContentItem[]
  store: any
}

const props = defineProps<Props>()

const store = usePaperStore()
const imageGenStore = useImageGenStore()

const promptOpen: Record<string, boolean> = reactive({})
const generating: Record<string, boolean> = reactive({})
const galleryOpen: Record<string, boolean> = reactive({})

const insertOpen = ref(-1)

function toggleInsert(idx: number): void {
  insertOpen.value = insertOpen.value === idx ? -1 : idx
}

function closeInsert(idx: number): void {
  if (insertOpen.value === idx) insertOpen.value = -1
}

function insertAfter(idx: number, type: 'text' | 'gambar' | 'tabel' | 'rumus'): void {
  const items: Record<string, Partial<ContentItem>> = {
    text: { id: 'text', text: '' },
    gambar: { id: 'gambar', Title: '', Path: '', Prompt: '' },
    tabel: { id: 'tabel', Title: '', Headers: ['Col 1', 'Col 2'], Rows: [['', '']] },
    rumus: { id: 'rumus', latex: '' }
  }
  const next = items[type]
  if (!next) return
  props.items.splice(idx + 1, 0, { ...next } as ContentItem)
  insertOpen.value = -1
  nextTick(resizeAllTextareas)
}

interface ClickOutsideElement extends HTMLElement {
  __handler__?: (e: MouseEvent) => void
}

const vClickOutsideContent = {
  mounted(el: ClickOutsideElement, binding: any): void {
    el.__handler__ = (e: MouseEvent) => {
      if (!el.contains(e.target as Node)) binding.value()
    }
    document.addEventListener('mousedown', el.__handler__)
  },
  unmounted(el: ClickOutsideElement): void {
    if (el.__handler__) {
      document.removeEventListener('mousedown', el.__handler__)
    }
  },
}

function resizeAllTextareas(): void {
  nextTick(() => {
    // Target textareas with v-autosize (content-textarea-auto class) and
    // also any textarea inside ContentList that has resize-none (v-autosize sets it)
    const els = document.querySelectorAll('textarea.content-textarea-auto, textarea[style*="resize: none"]')
    els.forEach(el => {
      const textarea = el as HTMLTextAreaElement
      textarea.style.height = 'auto'
      textarea.style.height = textarea.scrollHeight + 'px'
    })
  })
}

onMounted(resizeAllTextareas)
onMounted(() => {
  // Warm the chart pool so the gallery picker has chart sources available
  // without the user needing to open the Data tab first.
  if (store.currentPaperId && !(store.paperCharts && store.paperCharts.length)) {
    store.loadPaperCharts(store.currentPaperId)
  }
})
watch(() => props.items, () => resizeAllTextareas(), { deep: true })

const keyMap = new WeakMap<object, string>()
let __kc = 0

function stableKey(obj: any): string {
  if (typeof obj !== 'object' || !obj) return String(obj)
  if (!keyMap.has(obj)) keyMap.set(obj, String(++__kc))
  return keyMap.get(obj)!
}

function badgeClass(id: string): string {
  const map: Record<string, string> = {
     text: 'border-cream-300 text-navy-500 dark:text-anthracite-100',
     gambar: 'border-amber-300 text-amber-600 dark:text-amber-300',
     tabel: 'border-emerald-300 text-emerald-600 dark:text-emerald-300',
     rumus: 'border-cream-400 text-navy-600 dark:text-anthracite-100'
  }
   return map[id] || 'border-cream-300 text-navy-500'
}

function badgeLabel(item: ContentItem, _idx: number): string {
  const nums = store.getItemNumber?.(item) || {}
  if (item.id === 'gambar') return `Fig. ${nums.label || '?'}`
  if (item.id === 'tabel') return `Table ${nums.label || '?'}`
  if (item.id === 'rumus') return `Eq. (${nums.label || '?'})`
  return 'Text'
}

function thumbUrl(filename: string): string {
  const pid = store.currentPaperId
  if (!pid || pid === 'null' || pid === 'undefined' || !filename) return ''
  return `/api/images/${pid}/${filename}`
}

function onThumbError(e: Event, _item: ContentItem): void {
  const target = e.target as HTMLImageElement
  target.style.display = 'none'
}

async function uploadContentImage(e: Event, item: ContentItem): Promise<void> {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const img = await store.uploadImage(undefined, file)
  if (img) item.Path = img.filename
  target.value = ''
}

function removeImagePath(item: ContentItem): void {
  store.setFigureSource(item, '')
}

function togglePrompt(item: ContentItem): void {
  const k = stableKey(item)
  promptOpen[k] = !promptOpen[k]
}

function toggleGallery(item: ContentItem): void {
  const k = stableKey(item)
  galleryOpen[k] = !galleryOpen[k]
  // Make sure the chart pool is fresh when the user opens the picker.
  if (galleryOpen[k] && store.currentPaperId) {
    store.loadPaperImages(store.currentPaperId)
    store.loadPaperCharts(store.currentPaperId)
  }
}

function pickSource(item: ContentItem, src: { filename: string }): void {
  // If this source is already attached to this item, picking it again clears it.
  if (item.Path === src.filename) {
    store.setFigureSource(item, '')
    return
  }
  store.setFigureSource(item, src.filename)
}

function srcKindLabel(kind: string): string {
  if (kind === 'chart') return '📊 chart'
  if (kind === 'generated') return '✨ AI'
  return '📤 upload'
}

/** Figure number label of the OTHER figure currently using this source. */
function otherFigLabel(filename: string): string {
  const owner = store.figureSourceUsage.get(filename)
  if (!owner) return '?'
  return store.getItemNumber?.(owner)?.label || '?'
}

async function generateImage(item: ContentItem): Promise<void> {
  const prompt = String(item.Prompt || '').trim()
  if (!prompt) return
  if (!store.currentPaperId) {
    store.showToast('Simpan paper dulu sebelum generate gambar.', 'error')
    return
  }
  const k = stableKey(item)
  generating[k] = true
  try {
    const jobId = await imageGenStore.enqueue({
      paperId: store.currentPaperId,
      prompt,
      onDone: (img: any) => {
        // _notify passes a string (image filename) or object
        const filename = typeof img === 'string' ? img : (img?.filename || img?.image || '')
        if (filename) {
          item.Path = filename
          if (store.currentPaperId) store.loadPaperImages(store.currentPaperId)
        }
        item.JobId = ''
        generating[k] = false
      },
      onError: (err: any) => {
        store.showToast('Generate gagal: ' + (err || 'unknown'), 'error')
        item.JobId = ''
        generating[k] = false
      },
      itemKey: k,
    })
    if (jobId) item.JobId = jobId
  } catch (err: any) {
    store.showToast('Generate gagal: ' + (err.message || err), 'error')
    generating[k] = false
  }
}

function reattachJobs(): void {
  for (const item of (props.items || [])) {
    if (item.id !== 'gambar' || !item.JobId) continue
    const k = stableKey(item)
    const job = imageGenStore.getJob(item.JobId)
    if (!job || job.status === 'done' || job.status === 'error') {
      if (job?.status === 'done' && job.image?.filename && !item.Path) {
        item.Path = job.image.filename
      }
      item.JobId = ''
      continue
    }
    generating[k] = true
    imageGenStore.subscribe(item.JobId, {
      onDone: (img: any) => {
        // _notify passes a string (image filename) or object
        const filename = typeof img === 'string' ? img : (img?.filename || img?.image || '')
        if (filename) {
          item.Path = filename
          if (store.currentPaperId) store.loadPaperImages(store.currentPaperId)
        }
        item.JobId = ''
        generating[k] = false
      },
      onError: (err: any) => {
        store.showToast('Generate gagal: ' + (err || 'unknown'), 'error')
        item.JobId = ''
        generating[k] = false
      },
    })
  }
}

watch(() => props.items, reattachJobs, { deep: false, immediate: true })
</script>
