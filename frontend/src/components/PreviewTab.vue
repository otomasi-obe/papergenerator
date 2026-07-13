<template>
  <div class="p-0 h-full min-h-0 w-full min-w-0 flex flex-col overflow-hidden">
    <!-- Resolved changes (collapsible at top) -->
    <div v-if="false && resolvedChanges.length > 0" class="mb-3 max-w-4xl mx-auto">
      <button @click="resolvedOpen = !resolvedOpen"
        class="text-xs text-ink-500 dark:text-ash-300 hover:text-ink-700 dark:hover:text-ash-100 flex items-center gap-1">
        <span>{{ resolvedOpen ? '▾' : '▸' }}</span>
        Riwayat persetujuan ({{ resolvedChanges.length }})
        <button v-if="resolvedOpen" @click.stop="store.clearResolvedProposals()"
          class="ml-2 text-[10px] underline text-ink-400 dark:text-ash-400 hover:text-ink-600 dark:hover:text-ash-200">bersihkan</button>
      </button>
      <div v-if="resolvedOpen" class="mt-2 space-y-1.5">
        <div v-for="c in resolvedChanges" :key="c.id"
          class="text-[11px] flex items-center gap-2 bg-cream-50 dark:bg-ash-800 rounded px-2 py-1">
          <span :class="c.status === 'accepted' ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500 dark:text-rose-400'">
            {{ c.status === 'accepted' ? '✓' : '✕' }}
          </span>
          <span class="font-medium text-ink-600 dark:text-anthracite-100">{{ kindLabel(c.kind) }}</span>
        </div>
      </div>
    </div>

    <div class="shrink-0 flex items-center justify-between gap-3 border-b border-cream-300 bg-cream-50/90 px-4 py-3 dark:border-ash-700 dark:bg-ash-900/90">
      <div class="flex items-center gap-3">
        <!-- Journal search dropdown -->
        <div class="relative" ref="wrapRef">
          <div class="flex items-center gap-2">
            <span class="text-xs text-ink-700 dark:text-ash-300 font-medium">Template:</span>
            <div class="flex items-center gap-1.5">
              <input
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
                aria-controls="journal-preview-list"
                aria-haspopup="listbox"
                :placeholder="journalLabel"
                class="px-2 py-1 border border-cream-300 dark:border-ash-600 rounded-lg text-sm font-semibold bg-white dark:bg-ash-800 text-navy-700 dark:text-cream-200 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 focus:border-navy-500 outline-none min-w-[120px] max-w-[200px]"
              />
              <svg v-if="open" @click="open = false" class="w-4 h-4 text-ink-400 cursor-pointer" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5 15l7-7 7 7"/></svg>
              <svg v-else class="w-4 h-4 text-ink-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </div>
          </div>
          <ul v-if="open && filtered.length"
            id="journal-preview-list"
            role="listbox"
            class="absolute z-50 mt-1 w-64 bg-white dark:bg-ash-800 border border-cream-300 dark:border-ash-600 rounded-xl shadow-lg max-h-64 overflow-y-auto text-sm">
            <li
              v-for="(j, idx) in filtered"
              :key="j"
              @click="pick(j)"
              @mouseenter="$event.currentTarget.classList.add('hovering')"
              @mouseleave="$event.currentTarget.classList.remove('hovering')"
              role="option"
              :aria-selected="store.paper.journal === j"
              :class="[
                'px-3 py-2 cursor-pointer flex items-center justify-between transition-all duration-150',
                store.paper.journal === j || highlightedIndex === idx ? 'bg-cream-100 dark:bg-ash-700 font-medium text-navy-700 dark:text-cream-200 translate-x-1' : 'text-ink-800 dark:text-ash-100 hover:bg-cream-100 hover:dark:bg-ash-700 hover:translate-x-1 hover:font-medium hover:text-navy-700 hover:dark:text-cream-200',
              ]"
            >
              <span>{{ j }}</span>
              <span v-if="store.paper.journal === j" class="text-xs text-[#238f7f] dark:text-[#4eb2a3]">✓</span>
            </li>
          </ul>
          <p v-if="open && search && filtered.length === 0" class="absolute mt-1 text-xs text-ink-600 dark:text-ash-300 z-50 bg-white dark:bg-ash-800 border border-cream-300 dark:border-ash-600 rounded-lg px-3 py-2 shadow">
            Tidak ada template "{{ search }}"
          </p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <!-- Re-render PDF preview -->
        <button @click="renderPdf" :disabled="pdfLoading"
          class="px-3 py-1.5 rounded text-xs font-medium border border-cream-300 text-ink-700 transition hover:bg-cream-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 dark:border-ash-600 dark:text-ink-200 dark:hover:bg-ash-700 flex items-center gap-1.5">
          <svg v-if="pdfLoading" class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
          {{ pdfLoading ? 'Rendering...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- PDF Preview (100% match) -->
    <div class="flex-1 min-h-0 w-full min-w-0 overflow-hidden">
      <!-- Loading state with progress bar -->
      <div v-if="pdfLoading" class="h-full w-full bg-cream-50 dark:bg-ash-900 flex flex-col items-center justify-center gap-5">
        <div class="relative">
          <div class="w-12 h-12 border-4 border-cream-200 dark:border-ash-700 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin"></div>
        </div>
        <div class="text-center w-full max-w-xs">
          <p class="text-sm font-semibold text-ink-800 dark:text-ink-100">Preview PDF sedang dirender</p>
          <p class="text-xs text-ink-500 dark:text-ash-400 mt-1">Menggenerate DOCX {{ store.paper.journal || 'IEEE' }} → konversi ke PDF</p>
          <div class="w-full bg-cream-200 dark:bg-ash-700 rounded-full h-2 mt-4 overflow-hidden">
            <div class="bg-navy-600 h-full rounded-full transition-all duration-500 ease-out" :style="{ width: Math.round(pdfProgress) + '%' }"></div>
          </div>
          <p class="text-sm font-mono text-ink-600 dark:text-ash-300 mt-2">{{ Math.round(pdfProgress) }}%</p>
        </div>
      </div>

      <!-- Error state -->
      <div v-else-if="pdfError" class="h-full w-full bg-cream-50 dark:bg-ash-900 flex flex-col items-center justify-center gap-4">
        <svg class="w-10 h-10 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z"/><path d="M12 15.75h.007v.008H12v-.008z"/></svg>
        <div class="text-center">
          <p class="text-sm font-medium text-ink-700 dark:text-ink-200">Gagal merender PDF</p>
          <p class="text-xs text-ink-500 dark:text-ash-400 mt-1">{{ pdfErrorMessage }}</p>
        </div>
        <button @click="renderPdf" class="px-4 py-2 rounded text-xs font-medium bg-navy-600 text-white hover:bg-navy-700 transition">
          Coba Lagi
        </button>
      </div>

      <!-- PDF ready -->
      <div v-else-if="pdfBlobUrl" class="h-full w-full min-w-0 overflow-hidden bg-white dark:bg-ash-900 relative">
        <iframe
          :src="pdfViewerUrl"
          :key="pdfKey"
          class="block h-full w-full border-0"
          title="PDF preview"
          @error="onIframeError"
        ></iframe>
        <div class="absolute top-3 right-3 flex items-center gap-1.5">
          <button @click="downloadPdf"
          class="px-2.5 py-1.5 bg-white/90 text-navy-700 rounded text-xs font-medium shadow-sm border border-cream-300 hover:bg-white transition flex items-center gap-1">
          <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
          Export PDF
          </button>
          <button @click="store.exportDocx()" :disabled="store.loading"
          class="px-2.5 py-1.5 bg-white/90 text-navy-700 rounded text-xs font-medium shadow-sm border border-cream-300 hover:bg-white transition flex items-center gap-1 disabled:opacity-50">
          <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/></svg>
          Export DOCX
          </button>
        </div>
      </div>
      <div v-else-if="pdfUrl" class="h-full w-full min-w-0 overflow-hidden bg-white dark:bg-ash-900">
        <iframe
          :src="pdfFallbackUrl"
          :key="'fb-' + pdfKey"
          class="block h-full w-full border-0"
          title="PDF preview"
        ></iframe>
      </div>

      <!-- Initial state — waiting for auto-render -->
      <div v-else class="h-full w-full bg-cream-50 dark:bg-ash-900 flex flex-col items-center justify-center gap-4">
        <svg class="w-10 h-10 text-ink-300 dark:text-ash-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></svg>
        <p class="text-sm text-ink-500 dark:text-ash-400">Preparing preview...</p>
      </div>
    </div>

    <!-- Edit mode -->
    <div v-if="false" class="paper-preview-wrapper overflow-auto">
      <div class="paper-preview border border-cream-300 dark:border-ash-700 rounded-2xl bg-white dark:bg-ash-900 p-8 max-w-4xl mx-auto shadow-sm">
        <!-- Title -->
        <div class="text-center mb-4">
          <textarea v-model="store.paper.title" rows="1"
            class="text-2xl font-bold text-center w-full bg-transparent border-b-2 border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-2 py-1 dark:text-ash-100 resize-none overflow-hidden"
            style="font-family: 'Times New Roman', serif;"
            @input="autoResize($event)"
            placeholder="Paper Title"></textarea>
        </div>

        <!-- Authors -->
        <div class="text-center mb-6">
          <div v-for="(author, i) in store.paper.authors" :key="i" class="mb-2">
            <div class="flex flex-col gap-1 text-sm" style="font-family: 'Times New Roman', serif;">
              <input v-model="author.name" class="bg-transparent border-b border-dashed border-cream-300 dark:border-ash-500 focus:border-navy-500 outline-none px-1 dark:text-ash-100" placeholder="Author Name" />
              <input v-model="author.affiliation" class="bg-transparent border-b border-dashed border-cream-300 dark:border-ash-500 focus:border-navy-500 outline-none px-1 dark:text-ash-100 text-xs" placeholder="Affiliation" />
            </div>
          </div>
        </div>

        <!-- Abstract -->
        <div class="mb-4">
          <h2 class="text-base font-bold" style="font-family: 'Times New Roman', serif;">Abstract</h2>
          <textarea v-model="store.paper.abstract" rows="3"
            class="w-full text-sm leading-relaxed mt-1 bg-transparent border border-dashed border-cream-300 dark:border-ash-500 focus:border-navy-500 outline-none px-2 py-1 dark:text-ash-100 resize-none"
            style="font-family: 'Times New Roman', serif;"
            @input="autoResize($event)"
            placeholder="Abstract goes here..."></textarea>
        </div>

        <!-- Sections -->
        <template v-for="(section, sIdx) in store.paper.sections" :key="sIdx">
          <div class="mb-4">
            <input v-model="section.title" class="text-base font-bold w-full bg-transparent border-b border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 outline-none px-1 dark:text-ash-100"
              style="font-family: 'Times New Roman', serif;" />
            <textarea v-model="section.content" rows="2"
              class="w-full text-sm leading-relaxed mt-1 bg-transparent border border-dashed border-cream-300 dark:border-ash-500 focus:border-navy-500 outline-none px-2 py-1 dark:text-ash-100 resize-none"
              style="font-family: 'Times New Roman', serif;"
              @input="autoResize($event)"></textarea>
          </div>
        </template>

        <!-- References -->
        <div class="mt-8" v-if="store.paper.references?.length">
          <h3 class="text-base font-bold mb-3" style="font-family: 'Times New Roman', serif;">References</h3>
          <div class="space-y-1">
            <div v-for="(ref, rIdx) in store.paper.references" :key="rIdx" class="flex items-start gap-2">
              <span class="text-xs text-ink-500 mt-1">[{{ rIdx + 1 }}]</span>
              <textarea v-if="typeof ref === 'string'" v-model="store.paper.references[rIdx]"
                rows="1" class="flex-1 text-sm bg-transparent border-b border-dashed border-cream-300 dark:border-ash-500 focus:border-navy-500 outline-none dark:text-ash-100 resize-none"
                style="font-family: 'Times New Roman', serif;" @input="autoResize($event)"></textarea>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Resolved changes (collapsible at bottom) -->
    <div v-if="resolvedChanges.length > 0" class="mt-6 max-w-4xl mx-auto">
      <button @click="resolvedOpen = !resolvedOpen"
        class="text-xs text-ink-500 dark:text-ash-300 hover:text-ink-700 dark:hover:text-ash-100 flex items-center gap-1">
        <span>{{ resolvedOpen ? '▾' : '▸' }}</span>
        Resolved changes
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { usePaperStore } from '../stores/paper'
import DiffBlock from './DiffBlock.vue'
import { renderLatex, renderRichText } from '../composables/useMathRender'
import { useSanitize } from '../composables/useSanitize'
import { getJournalLayout } from '../composables/journalLayouts'
import api from '../api/index.js'

const failedImages = ref(new Set<string>())
const showPdf = ref(true)
const pdfLoading = ref(false)
const pdfError = ref(false)
const pdfErrorMessage = ref('')
const pdfUrl = ref('')
const pdfBlobUrl = ref('')
const pdfKey = ref(0)
const pdfProgress = ref(0)
const htmlRefreshing = ref(false)
const pdfViewerUrl = computed(() => pdfBlobUrl.value ? `${pdfBlobUrl.value}#toolbar=1&navpanes=0&scrollbar=1&view=FitH&zoom=page-width` : '')
const pdfFallbackUrl = computed(() => { if (!pdfUrl.value) return ''; const sep = pdfUrl.value.includes('?') ? '&' : '?'; return `${pdfUrl.value}${sep}v=${pdfKey.value}#toolbar=1&navpanes=0&scrollbar=1&view=FitH&zoom=page-width` })

function onImgError(_event: Event, filename: string) {
  failedImages.value.add(filename)
}

function renderFormula(latex: string): string {
  return renderLatex(latex, true)
}

const { sanitizeHtml } = useSanitize()

function renderInlineText(text: string): string {
  return sanitizeHtml(renderRichText(text))
}

function displayRef(ref: any): string {
  if (typeof ref === 'string') return ref
  if (ref && ref.text) return ref.text
  return store.formatRef(ref) || JSON.stringify(ref)
}

interface Props {
  showZoom?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showZoom: false,
})

const store = usePaperStore()
const uiStore = useUiStore()
const journalLabel = computed(() => store.paper.journal || 'IEEE')

// Journal search dropdown
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
  // Auto render dengan template baru
  nextTick(() => renderPdf())
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

// Fetch journals on mount
onMounted(() => {
  store.fetchJournals()
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

// ─── Journal layout ──────────────────────────────────────────────────────────
const jl = computed(() => getJournalLayout(store.paper.journal))

const journalPaperStyle = computed(() => ({
  fontFamily: jl.value.paper.fontFamily,
  fontSize: jl.value.paper.fontSize,
  lineHeight: jl.value.paper.lineHeight,
  columnCount: jl.value.paper.columns,
  columnGap: jl.value.paper.columnGap,
  textAlign: jl.value.paper.textAlign,
  padding: jl.value.paper.padding,
  maxWidth: jl.value.paper.maxWidth,
  color: jl.value.paper.color,
  background: jl.value.paper.background,
  boxShadow: '0 1px 4px rgba(0,0,0,.3)',
  minHeight: '11in',
}))

const journalHeaderStyle = computed(() => ({
  fontSize: jl.value.header?.fontSize || '8pt',
  color: jl.value.header?.color || '#666',
  borderBottom: jl.value.header?.borderBottom || 'none',
  paddingBottom: '4pt',
  marginBottom: '12pt',
  textAlign: 'center' as const,
}))

const journalTitleStyle = computed(() => ({
  fontSize: jl.value.title.fontSize,
  fontWeight: jl.value.title.fontWeight,
  textAlign: jl.value.title.textAlign,
  color: jl.value.title.color,
  marginBottom: jl.value.title.marginBottom,
}))

const journalAuthorsStyle = computed(() => ({
  fontSize: jl.value.authors.fontSize,
  textAlign: jl.value.authors.textAlign,
  marginBottom: jl.value.authors.marginBottom,
}))

const journalAbstractStyle = computed(() => ({
  fontSize: jl.value.abstract.fontSize,
  fontWeight: jl.value.abstract.labelStyle === 'bold' ? '700' : '400',
  marginBottom: '12pt',
}))

const journalKeywordsStyle = computed(() => ({
  fontSize: jl.value.abstract.fontSize,
  fontStyle: 'italic',
  marginBottom: '12pt',
  '--kw-label-weight': jl.value.abstract.labelStyle === 'bold' ? '700' : '400',
}))

const journalBodyStyle = computed(() => {
  const b = jl.value.body
  return {
    fontSize: b.fontSize,
    textAlign: b.textAlign,
    '--text-indent': b.textIndent,
  }
})

const journalReferencesStyle = computed(() => ({
  fontSize: jl.value.references.fontSize,
  marginTop: '18pt',
  borderTop: '1px solid #000',
  paddingTop: '6pt',
  '--ref-hanging': jl.value.references.hangingIndent,
}))

const journalFooterStyle = computed(() => ({
  fontSize: jl.value.footer?.fontSize || '8pt',
  color: jl.value.footer?.color || '#666',
}))

watch(() => store.currentPaperId, (newId) => {
  console.log('[PreviewTab] watch currentPaperId:', newId)
  failedImages.value = new Set()
  showPdf.value = true
  pdfUrl.value = ''
  clearPdfBlobUrl()
  pdfError.value = false
  pdfLoading.value = false
  if (newId) {
    nextTick(() => triggerRender())
  }
}, { immediate: true })

const resolvedOpen = ref(false)
const editMode = ref(false)
const zoomLevel = ref(1)

const pendingActive = computed(() =>
  (store.pendingChanges || []).filter(p => p.status === 'pending')
)
const resolvedChanges = computed(() =>
  (store.pendingChanges || []).filter(p => p.status !== 'pending')
)

const pendingByKind = computed(() => {
  const map: Record<string, any> = {}
  for (const c of pendingActive.value) {
    if (['title', 'abstract', 'keywords'].includes(c.kind)) {
      if (!map[c.kind]) map[c.kind] = c
    }
  }
  return map
})

const pendingSectionByIdx = computed(() => {
  const map: Record<number, any> = {}
  for (const c of pendingActive.value) {
    if (c.kind === 'section' && c.payload.section_index !== null && c.payload.section_index !== undefined) {
      map[c.payload.section_index] = c
    }
  }
  return map
})

const newSectionProposals = computed(() =>
  pendingActive.value.filter(c => c.kind === 'section' && (c.payload.section_index === null || c.payload.section_index === undefined))
)

const pendingRefByIdx = computed(() => {
  const map: Record<number, any> = {}
  for (const c of pendingActive.value) {
    if (c.kind === 'reference' && c.payload.ref_index !== null && c.payload.ref_index !== undefined) {
      map[c.payload.ref_index] = c
    }
  }
  return map
})

const newRefProposals = computed(() =>
  pendingActive.value.filter(c => c.kind === 'reference' && (c.payload.ref_index === null || c.payload.ref_index === undefined))
)

function zoomIn(): void {
  zoomLevel.value = Math.min(2, zoomLevel.value + 0.1)
}

function zoomOut(): void {
  zoomLevel.value = Math.max(0.5, zoomLevel.value - 0.1)
}

function onTextareaInput(event: Event, item: any): void {
  item.text = (event.target as HTMLTextAreaElement).value
}

function imgSrc(item: any): string {
  if (!store.currentPaperId || store.currentPaperId === 'null' || store.currentPaperId === 'undefined' || !item?.Path) return ''
  const pid = store.currentPaperId
  let filename = item.Path.includes('/') ? item.Path.split('/').pop() || item.Path : item.Path
  const sources = [...(store.paperImages || []), ...(store.paperCharts || [])]
  const safeFilename = filename.replace(/[^A-Za-z0-9_.-]/g, '_')
  if (!sources.some((src: any) => src?.filename === filename) && sources.some((src: any) => src?.filename === safeFilename)) {
    filename = safeFilename
  }
  if (!sources.some((src: any) => src?.filename === filename)) {
    const match = `${item.Path} ${item.Title || ''}`.match(/(?:fig|figure)\s*\.?\s*(\d+)/i)
    const figureNumber = match ? Number(match[1]) : 0
    const generated = figureNumber > 0 ? store.paperImageByIndex?.[figureNumber - 1] : null
    filename = generated?.filename || safeFilename
  }
  const usage = store.figureSourceUsage
  const used = usage.get(filename)
  if (used && used !== item) {
    for (const img of store.paperImages || []) {
      if (img.filename === filename) {
        return `/api/images/${pid}/${encodeURIComponent(img.filename)}`
      }
    }
  }
  return `/api/images/${pid}/${encodeURIComponent(filename)}`
}

function toRoman(num: number): string {
  return store.toRoman(num)
}

function getItemNum(item: any): string {
  const info = store.getItemNumber(item)
  return info.label || '?'
}

function sectionText(section: any): string {
  if (!section?.content) return ''
  return section.content
    .filter((it: any) => it && it.id === 'text')
    .map((it: any) => it.text || '')
    .join('\n\n')
}

function kindLabel(kind: string): string {
  const labels: Record<string, string> = {
    title: 'Judul',
    abstract: 'Abstrak',
    keywords: 'Keywords',
    section: 'Section',
    reference: 'Referensi',
    journal: 'Jurnal',
    export_docx: 'Export DOCX',
  }
  return labels[kind] || kind
}

const vAutoresize = {
  mounted(el: HTMLTextAreaElement) {
    const resize = () => {
      el.style.height = 'auto'
      el.style.height = el.scrollHeight + 'px'
    }
    el.addEventListener('input', resize)
    nextTick(resize)
    el._autoresizeCleanup = () => el.removeEventListener('input', resize)
  },
  updated(el: HTMLTextAreaElement) {
    nextTick(() => {
      el.style.height = 'auto'
      el.style.height = el.scrollHeight + 'px'
    })
  },
  unmounted(el: HTMLTextAreaElement) {
    el._autoresizeCleanup?.()
  },
}

function autoResize(event: Event) {
  const el = event.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

// PDF rendering with progress bar
let progressTimer: ReturnType<typeof setInterval> | null = null
console.log('[PreviewTab] script setup, paperId:', store.currentPaperId)
let renderDebounceTimer: ReturnType<typeof setTimeout> | null = null
function triggerRender() {
  if (renderDebounceTimer) return
  renderDebounceTimer = setTimeout(() => {
    renderDebounceTimer = null
    if (store.currentPaperId) renderPdf()
  }, 100)
}

async function renderPdf() {
  if (pdfLoading.value) return
  if (!store.currentPaperId) return
  pdfLoading.value = true
  pdfError.value = false
  pdfUrl.value = ''
  pdfProgress.value = 0
  clearPdfBlobUrl()

  // Simulated progress (backend doesn't support streaming progress)
  progressTimer = setInterval(() => {
    if (pdfProgress.value < 90) {
      pdfProgress.value += Math.random() * 8 + 2
      if (pdfProgress.value > 90) pdfProgress.value = 90
    }
  }, 500)

  try {
    const res = await api.post(
      `/api/papers/${encodeURIComponent(String(store.currentPaperId))}/pdf-preview`,
      { journal: store.paper.journal || 'IEEE' },
      { timeout: 300000 }
    )
    if (res.data?.pdf_url) {
      const resultUrl = res.data.pdf_url
      await loadPdfBlob(resultUrl)
      pdfProgress.value = 100
      pdfUrl.value = resultUrl
      pdfKey.value++
    } else {
      // API returned 200 but no pdf_url — treat as error
      pdfError.value = true
      pdfErrorMessage.value = res.data?.error || 'Server tidak mengembalikan PDF (mungkin konversi DOCX→PDF gagal)'
    }
    pdfLoading.value = false
  } catch (err: any) {
    pdfLoading.value = false
    pdfError.value = true
    pdfErrorMessage.value = err.response?.data?.error || err.message || 'Failed to render PDF'
  } finally {
    if (progressTimer) { clearInterval(progressTimer); progressTimer = null }
    pdfProgress.value = 0
  }
}

function refreshHtml() {
  // Clear PDF state so HTML preview re-renders
  htmlRefreshing.value = true
  pdfUrl.value = ''
  clearPdfBlobUrl()
  pdfError.value = false
  setTimeout(() => { htmlRefreshing.value = false }, 300)
}

function clearPdfBlobUrl() {
  if (pdfBlobUrl.value) URL.revokeObjectURL(pdfBlobUrl.value)
  pdfBlobUrl.value = ''
}

async function loadPdfBlob(url: string) {
  try {
    const res = await api.get(url, { responseType: 'blob', timeout: 300000 })
    const bytes = await res.data.slice(0, 4).text()
    if (bytes === '%PDF') {
      pdfBlobUrl.value = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
    }
  } catch {
    // blob fetch failed — fallback to direct URL iframe
  }
}

function onIframeError() {
  clearPdfBlobUrl()
  pdfUrl.value = ''
}

function togglePdfPreview() {
  showPdf.value = true
  if (showPdf.value && !pdfUrl.value && !pdfLoading.value) {
    renderPdf()
  }
}

function downloadPdf() {
  if (!pdfBlobUrl.value) return
  const a = document.createElement('a')
  a.href = pdfBlobUrl.value
  a.download = `${store.paper.journal || 'IEEE'}_${(store.paper.title || 'paper').replace(/[^a-zA-Z0-9_\-]/g, '_').slice(0, 60)}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// Watchers — no auto PDF render; HTML preview is always visible
// User triggers PDF manually via the PDF button

// Trigger handled by watch with immediate:true
onUnmounted(() => {
  if (progressTimer) { clearInterval(progressTimer); progressTimer = null }
  if (renderDebounceTimer) { clearTimeout(renderDebounceTimer); renderDebounceTimer = null }
  clearPdfBlobUrl()
})

// Expose renderPdf for external use
defineExpose({ renderPdf, showPdf, togglePdfPreview })
</script>

<style scoped>
/* ── Journal paper page (Scribd-style) ─────────────────────────── */
.journal-paper {
  position: relative;
  width: 8.5in;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0,0,0,.25);
  border-radius: 2px;
}

.journal-header {
  font-size: 8pt;
  color: #666;
  border-bottom: 1px solid #999;
  padding-bottom: 4pt;
  margin-bottom: 12pt;
  text-align: center;
}

.journal-title h1 {
  font-size: inherit;
  font-weight: inherit;
  text-align: inherit;
  color: inherit;
  margin: 0;
  line-height: 1.3;
}

.journal-title {
  font-size: 18pt;
  font-weight: 700;
  text-align: center;
  color: #000;
  margin-bottom: 12pt;
}

.journal-authors {
  font-size: 10pt;
  text-align: center;
  margin-bottom: 6pt;
}

.journal-abstract {
  font-size: 9pt;
  margin-bottom: 12pt;
}

.journal-abstract .abs-label {
  font-weight: 700;
  font-style: italic;
  margin-bottom: 4pt;
  display: block;
}

.journal-keywords {
  font-size: 9pt;
  font-style: italic;
  margin-bottom: 12pt;
}

.kw-label {
  font-weight: 700;
  font-style: normal;
}

/* Two-column layout for IEEE/ACM */
@media (min-width: 0px) {
  .journal-paper {
    column-count: 1;
    column-gap: 0;
  }
}

/* Journal-specific 2-column override applied inline via style binding */
.journal-paper.two-column {
  column-count: 2;
  column-gap: 0.25in;
}

/* Prevent tables/figures from breaking across columns */
.journal-paper table,
.journal-paper .journal-figure,
.journal-paper .journal-table {
  break-inside: avoid;
  -webkit-column-break-inside: avoid;
  page-break-inside: avoid;
}

/* Body text inside columns */
.journal-body {
  font-size: 9pt;
  line-height: 1.5;
  text-align: justify;
}

.journal-heading1 {
  font-size: 10pt;
  font-weight: 700;
  text-transform: uppercase;
  margin-top: 12pt;
  margin-bottom: 6pt;
  break-after: avoid;
}

.journal-heading2 {
  font-size: 9pt;
  font-weight: 600;
  font-style: italic;
  margin-top: 8pt;
  margin-bottom: 4pt;
  break-after: avoid;
}

/* Text inside journal-body inherits from journal-paper */
.journal-body > div > div {
  font-size: inherit;
  line-height: inherit;
  text-align: inherit;
}

/* References — always full-width, single column */
.journal-references {
  font-size: 8pt;
  margin-top: 18pt;
  border-top: 1px solid #000;
  padding-top: 6pt;
  column-span: all;
  -webkit-column-span: all;
}

.journal-ref-heading {
  font-size: inherit;
  font-weight: 700;
  margin-bottom: 6pt;
}

.ref-list {
  font-size: inherit;
}

.ref-item {
  font-size: inherit;
  margin-bottom: 4pt;
  padding-left: var(--ref-hanging, 0.25in);
  text-indent: calc(-1 * var(--ref-hanging, 0.25in));
}

.ref-num {
  font-size: 0.85em;
  margin-right: 4pt;
}

.journal-footer {
  font-size: 8pt;
  color: #666;
  border-top: 1px solid #999;
  padding-top: 4pt;
  margin-top: 12pt;
  text-align: center;
}

/* Abstract italic text */
.journal-abstract p:not(.abs-label) {
  font-style: normal;
  text-align: justify;
}
</style>
