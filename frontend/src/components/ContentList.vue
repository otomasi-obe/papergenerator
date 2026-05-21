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
            <span class="content-drag cursor-grab active:cursor-grabbing text-cream-400 hover:text-brown-500 select-none text-base leading-none px-0.5" role="button" aria-label="Drag to reorder">⠿</span>
            <span v-if="item.id !== 'gambar'" class="text-[10px] font-medium uppercase tracking-wide pl-1.5 border-l-2"
              :class="badgeClass(item.id)">
              {{ badgeLabel(item, idx) }}
            </span>
            <span v-else class="text-[10px] font-medium uppercase tracking-wide pl-1.5 border-l-2"
              :class="badgeClass(item.id)">
              Fig. {{ store.getItemNumber(item)?.label || '?' }}
            </span>
          </div>
          <button @click="store.removeContent(items, idx)"
            class="text-red-300 hover:text-red-500 text-xs px-1 opacity-60 group-hover:opacity-100">✕</button>
        </div>

        <!-- TEXT -->
        <template v-if="item.id === 'text'">
          <textarea :value="item.text"
            @input="onTextInput($event, item)"
            ref="textareas"
            rows="2"
            class="content-textarea-auto w-full px-2.5 py-2 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm focus:ring-2 focus:ring-cream-200 focus:border-brown-400 outline-none resize-none overflow-hidden break-words"
            placeholder="Write text content... Use [1], [2] for citations."></textarea>
        </template>

        <!-- IMAGE / GAMBAR -->
        <template v-else-if="item.id === 'gambar'">
          <div class="space-y-2">
            <input v-model="item.Title" class="w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm outline-none focus:border-brown-400"
              placeholder="Image Title / Caption" />

            <!-- Thumbnail (always rendered when there's a path or live preview from current job) -->
            <div v-if="item.Path" class="rounded border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-700 overflow-hidden flex items-center justify-center" style="max-height:280px">
              <img :src="thumbUrl(item.Path)" :alt="item.Title || 'image'"
                   class="max-h-[280px] max-w-full object-contain"
                   @error="onThumbError($event, item)" />
            </div>

            <!-- Action row: Upload + Prompt toggle. Layout is identical
                 whether or not an image exists, so the toolbar doesn't shift. -->
            <div class="flex items-center gap-2 flex-wrap">
              <label class="px-2.5 py-1.5 bg-cream-200 dark:bg-anthracite-600 hover:bg-cream-300 dark:hover:bg-anthracite-500 text-brown-700 dark:text-anthracite-100 rounded text-xs cursor-pointer flex items-center gap-1 font-medium">
                📤 {{ item.Path ? 'Replace' : 'Upload' }}
                <input type="file" accept="image/*" class="hidden" @change="uploadContentImage($event, item)" />
              </label>
              <button @click="togglePrompt(item)" type="button"
                class="px-2.5 py-1.5 bg-cream-200 dark:bg-anthracite-600 hover:bg-cream-300 dark:hover:bg-anthracite-500 text-brown-700 dark:text-anthracite-100 rounded text-xs font-medium flex items-center gap-1">
                <span>{{ promptOpen[stableKey(item)] ? '▾' : '▸' }}</span>
                <span>Prompt &amp; Generate</span>
              </button>
              <span v-if="generating[stableKey(item)]" class="text-[11px] text-ink-500 dark:text-ink-300 flex items-center gap-1">
                <span class="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
                generating…
              </span>
              <button v-if="item.Path" @click="removeImagePath(item)" type="button"
                class="ml-auto px-2 py-1 text-red-400 hover:text-red-600 rounded text-[11px]">✕ Hapus image</button>
            </div>

            <!-- Filename hint after upload -->
            <p v-if="item.Path" class="text-[11px] text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-900/30 rounded px-2 py-1 truncate" :title="item.Path">📷 {{ item.Path }}</p>

            <!-- Prompt + Generate (hidden by default, toggled by the button above) -->
            <div v-show="promptOpen[stableKey(item)]" class="space-y-1.5">
              <textarea :value="item.Prompt || ''"
                @input="item.Prompt = $event.target.value; autoResize($event)"
                rows="2"
                class="content-textarea-auto w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 rounded text-xs outline-none focus:border-brown-400 resize-none overflow-hidden text-brown-700 dark:text-anthracite-100 dark:placeholder-anthracite-300"
                placeholder="AI Image Prompt (deskripsi gambar untuk Gemini)"></textarea>
              <button @click="generateImage(item)" type="button"
                :disabled="!String(item.Prompt || '').trim() || !!generating[stableKey(item)]"
                class="px-2.5 py-1.5 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5">
                <span v-if="generating[stableKey(item)]" class="w-3 h-3 border-2 border-cream-50 dark:border-ash-900 border-t-transparent rounded-full animate-spin"></span>
                ✨ Generate Image
              </button>
            </div>
          </div>
        </template>

        <!-- TABLE / TABEL -->
        <template v-else-if="item.id === 'tabel'">
          <div class="space-y-2">
            <input v-model="item.Title" class="w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm outline-none focus:border-brown-400"
              placeholder="Table Title" />
            <div class="overflow-x-auto">
              <table class="w-full text-xs border-collapse">
                <thead>
                  <tr>
                    <th v-for="(h, ci) in item.Headers" :key="ci"
                      class="border border-cream-300 dark:border-anthracite-500 bg-cream-100 dark:bg-anthracite-700 p-0 relative">
                      <input :value="h" @input="item.Headers[ci] = $event.target.value"
                        class="w-full px-2 py-1.5 text-xs font-semibold bg-transparent text-brown-900 dark:text-anthracite-50 outline-none text-center" />
                      <button v-if="item.Headers.length > 1"
                        @click="store.removeTableCol(item, ci)"
                        class="absolute -top-2 -right-2 bg-red-400 text-white rounded-full w-4 h-4 text-[10px] leading-none opacity-0 group-hover:opacity-100">✕</button>
                    </th>
                    <th class="w-8">
                      <button @click="store.addTableCol(item)"
                        class="text-brown-400 dark:text-anthracite-300 hover:text-brown-700 dark:hover:text-anthracite-50 text-xs">+</button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, ri) in item.Rows" :key="ri">
                    <td v-for="(cell, ci) in row" :key="ci" class="border border-cream-300 dark:border-anthracite-500 p-0">
                      <input :value="cell" @input="item.Rows[ri][ci] = $event.target.value"
                        class="w-full px-2 py-1 text-xs bg-transparent text-brown-900 dark:text-anthracite-50 outline-none" />
                    </td>
                    <td class="w-8 text-center">
                      <button @click="store.removeTableRow(item, ri)"
                        class="text-red-300 hover:text-red-500 text-[10px]">✕</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <button @click="store.addTableRow(item)"
              class="text-xs text-brown-600 dark:text-anthracite-100 hover:text-brown-800 dark:hover:text-anthracite-50">+ Add Row</button>
          </div>
        </template>

        <!-- FORMULA / RUMUS -->
        <template v-else-if="item.id === 'rumus'">
          <input v-model="item.latex" class="w-full px-2.5 py-1.5 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm font-mono outline-none focus:border-brown-400"
            placeholder="LaTeX formula, e.g. T_{total} \approx \max(T_{cap}, T_{inf}, T_{modbus})" />
          <div v-if="item.latex" class="mt-1.5 text-xs text-brown-400 dark:text-anthracite-300 font-mono bg-cream-100 dark:bg-anthracite-700 dark:text-anthracite-100 px-2 py-1 rounded break-all">
            Preview: {{ item.latex }}
          </div>
        </template>
      </div>

      <!-- Inline + insert (between this box and the next). Floats outside the
           right edge so it doesn't add vertical height. Click → mini menu. -->
      <div class="absolute -right-3 top-1/2 -translate-y-1/2 z-10" v-click-outside-content="() => closeInsert(idx)">
        <button type="button"
          @click="toggleInsert(idx)"
          :class="['w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-all',
                   'bg-cream-100 dark:bg-anthracite-700 border border-cream-300 dark:border-anthracite-500 text-brown-500 dark:text-anthracite-100',
                   'hover:bg-brown-700 hover:border-brown-700 hover:text-cream-50 dark:hover:bg-cream-200 dark:hover:text-ash-900',
                   insertOpen === idx ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
                   'shadow-sm']"
          title="Tambah konten setelah box ini">+</button>
        <div v-if="insertOpen === idx"
             class="absolute right-7 top-1/2 -translate-y-1/2 bg-cream-50 dark:bg-anthracite-700 border border-cream-300 dark:border-anthracite-500 rounded-lg shadow-lg p-1 flex flex-col min-w-[140px]">
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

<script setup>
import { onMounted, nextTick, reactive, ref, watch, computed } from 'vue'
import draggable from 'vuedraggable'
import { usePaperStore } from '../stores/paper.js'
import { useImageGenStore } from '../stores/imageGen.js'

const props = defineProps({
  items: { type: Array, required: true },
  store: { type: Object, required: true }
})

const store = usePaperStore()
const imageGenStore = useImageGenStore()

// Local UI state, keyed by stableKey(item).
const promptOpen = reactive({})
// Items currently generating: key = stableKey(item). We DERIVE this from the
// store on mount (so a page reload still shows spinners on items that have an
// in-flight job) and update it as new generates start.
const generating = reactive({})

const insertOpen = ref(-1)
function toggleInsert(idx) {
  insertOpen.value = insertOpen.value === idx ? -1 : idx
}
function closeInsert(idx) {
  if (insertOpen.value === idx) insertOpen.value = -1
}
function insertAfter(idx, type) {
  const items = {
    text: { id: 'text', text: '' },
    gambar: { id: 'gambar', Title: '', Path: '', Prompt: '' },
    tabel: { id: 'tabel', Title: '', Headers: ['Col 1', 'Col 2'], Rows: [['', '']] },
    rumus: { id: 'rumus', latex: '' }
  }
  const next = items[type]
  if (!next) return
  props.items.splice(idx + 1, 0, { ...next })
  insertOpen.value = -1
  nextTick(resizeAllTextareas)
}

// Click-outside directive (scoped to this file).
const vClickOutsideContent = {
  mounted(el, binding) {
    el.__handler__ = (e) => {
      if (!el.contains(e.target)) binding.value()
    }
    document.addEventListener('mousedown', el.__handler__)
  },
  unmounted(el) {
    document.removeEventListener('mousedown', el.__handler__)
  },
}

function autoResize(e) {
  const el = e.target
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}
function onTextInput(e, item) {
  item.text = e.target.value
  autoResize(e)
}

function resizeAllTextareas() {
  nextTick(() => {
    document.querySelectorAll('.content-textarea-auto').forEach(el => {
      el.style.height = 'auto'
      el.style.height = el.scrollHeight + 'px'
    })
  })
}

onMounted(resizeAllTextareas)
watch(() => props.items.length, () => resizeAllTextareas())
watch(() => props.items, () => resizeAllTextareas(), { deep: true })

const keyMap = new WeakMap()
let __kc = 0
function stableKey(obj) {
  if (typeof obj !== 'object' || !obj) return String(obj)
  if (!keyMap.has(obj)) keyMap.set(obj, String(++__kc))
  return keyMap.get(obj)
}

function badgeClass(id) {
  const map = {
    text: 'border-cream-300 text-brown-500 dark:text-anthracite-100',
    gambar: 'border-amber-300 text-amber-600 dark:text-amber-300',
    tabel: 'border-emerald-300 text-emerald-600 dark:text-emerald-300',
    rumus: 'border-cream-400 text-brown-600 dark:text-anthracite-100'
  }
  return map[id] || 'border-cream-300 text-brown-500'
}

function badgeLabel(item, idx) {
  const nums = store.getItemNumber(item)
  if (item.id === 'gambar') return `Fig. ${nums.label || '?'}`
  if (item.id === 'tabel') return `Table ${nums.label || '?'}`
  if (item.id === 'rumus') return `Eq. (${nums.label || '?'})`
  return 'Text'
}

function thumbUrl(filename) {
  const pid = store.currentPaperId
  if (!pid) return ''
  return `/api/images/${pid}/${filename}`
}

function onThumbError(e, item) {
  e.target.style.display = 'none'
}

async function uploadContentImage(e, item) {
  const file = e.target.files?.[0]
  if (!file) return
  const img = await store.uploadImage(undefined, file)
  if (img) item.Path = img.filename
  e.target.value = ''
}

function removeImagePath(item) {
  item.Path = ''
}

function togglePrompt(item) {
  const k = stableKey(item)
  promptOpen[k] = !promptOpen[k]
}

async function generateImage(item) {
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
      onDone: (img) => {
        if (img && img.filename) {
          item.Path = img.filename
          store.loadPaperImages(store.currentPaperId)
        }
        item.JobId = ''
        generating[k] = false
      },
      onError: (err) => {
        store.showToast('Generate gagal: ' + (err || 'unknown'), 'error')
        item.JobId = ''
        generating[k] = false
      },
      itemKey: k,
    })
    if (jobId) item.JobId = jobId
  } catch (err) {
    store.showToast('Generate gagal: ' + (err.message || err), 'error')
    generating[k] = false
  }
}

// On mount / when items change, re-attach to any persisted JobId so the spinner
// reappears after a page reload or paper switch.
function reattachJobs() {
  for (const item of (props.items || [])) {
    if (item.id !== 'gambar' || !item.JobId) continue
    const k = stableKey(item)
    const job = imageGenStore.getJob(item.JobId)
    if (!job || job.status === 'done' || job.status === 'error') {
      // Stale id — clear and skip.
      if (job?.status === 'done' && job.image?.filename && !item.Path) {
        item.Path = job.image.filename
      }
      item.JobId = ''
      continue
    }
    generating[k] = true
    imageGenStore.subscribe(item.JobId, {
      onDone: (img) => {
        if (img && img.filename) {
          item.Path = img.filename
          store.loadPaperImages(store.currentPaperId)
        }
        item.JobId = ''
        generating[k] = false
      },
      onError: (err) => {
        store.showToast('Generate gagal: ' + (err || 'unknown'), 'error')
        item.JobId = ''
        generating[k] = false
      },
    })
  }
}

watch(() => props.items, reattachJobs, { deep: false, immediate: true })
</script>
