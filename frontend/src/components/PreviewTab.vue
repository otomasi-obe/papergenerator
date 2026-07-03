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
        <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">
          {{ journalLabel }}
        </h2>

      </div>
      <div class="flex items-center gap-2">
        <!-- Full 100% PDF preview button -->
        <button @click="renderPdf" :disabled="pdfLoading"
          class="px-3 py-1.5 rounded text-xs font-medium bg-navy-600 text-white transition hover:bg-navy-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 flex items-center gap-1.5">
          <svg v-if="pdfLoading" class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
          <svg v-else class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6M12 18v-6M9 15l3 3 3-3"/></svg>
          {{ pdfLoading ? 'Rendering PDF...' : 'PDF (Full)' }}
        </button>
        <!-- Refresh HTML preview -->
        <button @click="refreshHtml" :disabled="htmlRefreshing"
          class="px-3 py-1.5 rounded text-xs font-medium border border-cream-300 text-ink-700 transition hover:bg-cream-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 dark:border-ash-600 dark:text-ink-200 dark:hover:bg-ash-700">
          {{ htmlRefreshing ? '...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- PDF Preview (100% match) — shown when user clicks PDF button -->
    <div class="paper-preview-wrapper flex-1 min-h-0 w-full min-w-0 overflow-hidden">
      <!-- Loading state with progress bar -->
      <div v-if="pdfLoading" class="h-full w-full bg-white dark:bg-ash-900 p-8 shadow-sm flex flex-col items-center justify-center gap-4">
        <div class="relative">
          <div class="w-10 h-10 border-3 border-cream-300 dark:border-ash-600 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin"></div>
        </div>
        <div class="text-center w-full max-w-sm">
          <p class="text-sm font-medium text-ink-700 dark:text-ink-200">Rendering {{ store.paper.journal || 'IEEE' }} PDF...</p>
          <p class="text-xs text-ink-500 dark:text-ash-400 mt-1">Generating DOCX → converting to PDF (100% match)</p>
          <div class="w-full bg-cream-200 dark:bg-ash-700 rounded-full h-1.5 mt-3 overflow-hidden">
            <div class="bg-navy-600 h-full rounded-full transition-all duration-700 ease-out" :style="{ width: pdfProgress + '%' }"></div>
          </div>
          <p class="text-xs text-ink-400 dark:text-ash-500 mt-1">{{ pdfProgress }}%</p>
        </div>
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
        <!-- Download button overlay -->
        <button @click="downloadPdf"
          class="absolute top-3 right-3 px-2.5 py-1.5 bg-white/90 text-navy-700 rounded text-xs font-medium shadow-sm border border-cream-300 hover:bg-white transition flex items-center gap-1">
          <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
          Download
        </button>
      </div>
      <div v-else-if="pdfUrl" class="h-full w-full min-w-0 overflow-hidden bg-white dark:bg-ash-900">
        <iframe
          :src="pdfFallbackUrl"
          :key="'fb-' + pdfKey"
          class="block h-full w-full border-0"
          title="PDF preview"
        ></iframe>
      </div>
    </div>

    <!-- HTML Paper Preview — Scribd-style journal layout -->
    <div v-if="!pdfBlobUrl && !pdfUrl" class="paper-preview-wrapper overflow-auto" style="background:#525659">
      <!-- Paper page — mimics A4/Letter with shadow -->
      <div
        class="journal-paper mx-auto my-4"
        :style="journalPaperStyle"
      >
        <!-- Running header (journal-specific) -->
        <div v-if="jl.header?.show" class="journal-header" :style="journalHeaderStyle">
          {{ jl.header.text }}
        </div>

        <!-- Title -->
        <div class="journal-title" :style="journalTitleStyle">
          <DiffBlock v-if="pendingByKind.title" :change="pendingByKind.title" :store="store" align="center">
            <template #before>
              <h1>{{ store.paper.title || 'Paper Title' }}</h1>
            </template>
            <template #after>
              <h1>{{ pendingByKind.title.payload.value || 'Paper Title' }}</h1>
            </template>
          </DiffBlock>
          <h1 v-else>{{ store.paper.title || 'Paper Title' }}</h1>
        </div>

        <!-- Authors -->
        <div class="journal-authors" :style="journalAuthorsStyle">
          <div v-for="(author, i) in store.paper.authors" :key="i">
            {{ author.name || 'Author Name' }}<span v-if="author.affiliation"> — {{ author.affiliation }}</span>
          </div>
        </div>

        <!-- Abstract -->
        <div class="journal-abstract" :style="journalAbstractStyle">
          <DiffBlock v-if="pendingByKind.abstract" :change="pendingByKind.abstract" :store="store">
            <template #before>
              <p class="abs-label">{{ jl.abstract.label }}</p>
              <p>{{ store.paper.abstract || 'Abstract goes here...' }}</p>
            </template>
            <template #after>
              <p class="abs-label">{{ jl.abstract.label }}</p>
              <p>{{ pendingByKind.abstract.payload.value || '' }}</p>
            </template>
          </DiffBlock>
          <template v-else>
            <p class="abs-label">{{ jl.abstract.label }}</p>
            <p>{{ store.paper.abstract || 'Abstract goes here...' }}</p>
          </template>
        </div>

        <!-- Keywords -->
        <div v-if="jl.keywords?.show && store.paper.keywords?.length" class="journal-keywords" :style="journalKeywordsStyle">
          <span class="kw-label">{{ jl.keywords.label }}</span>{{ store.paper.keywords.join(jl.keywords.separator) }}
        </div>

        <!-- Column wrapper for IEEE/ACM two-column journals -->
        <div class="journal-body" :style="journalBodyStyle">
          <!-- New section proposals -->
          <div v-if="newSectionProposals.length" class="mb-4 space-y-2">
            <div v-for="c in newSectionProposals" :key="c.id"
              class="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700">
              <DiffBlock :change="c" :store="store">
                <template #after>
                  <h3 class="text-sm font-bold text-amber-800 dark:text-amber-200">{{ c.payload.title || 'New Section' }}</h3>
                  <div class="text-sm mt-1" v-html="renderInlineText(c.payload.text || '')"></div>
                </template>
              </DiffBlock>
            </div>
          </div>

          <!-- Sections -->
          <template v-for="(section, sIdx) in store.paper.sections" :key="sIdx">
            <DiffBlock v-if="pendingSectionByIdx[sIdx]" :change="pendingSectionByIdx[sIdx]" :store="store">
              <template #before>
                <div class="mb-4">
                  <h3 class="journal-heading1">{{ getItemNum(section) }}. {{ section.title || 'Untitled Section' }}</h3>
                  <div v-html="renderInlineText(sectionText(section))"></div>
                </div>
              </template>
              <template #after>
                <div class="mb-4">
                  <h3 class="journal-heading1">{{ getItemNum(section) }}. {{ pendingSectionByIdx[sIdx].payload.title || 'Untitled Section' }}</h3>
                  <div v-html="renderInlineText(pendingSectionByIdx[sIdx].payload.text || '')"></div>
                </div>
              </template>
            </DiffBlock>
            <div v-else class="mb-4">
              <h3 class="journal-heading1">{{ getItemNum(section) }}. {{ section.title || 'Untitled Section' }}</h3>
              <div v-html="renderInlineText(sectionText(section))"></div>

              <!-- Subsections -->
              <div v-for="(sub, subIdx) in section.subsections || []" :key="subIdx" class="mb-3 ml-4">
                <h4 class="journal-heading2">{{ getItemNum(sub) }}. {{ sub.title || 'Untitled Subsection' }}</h4>
                <div v-html="renderInlineText(sub.content?.map?.((c: any) => c.text).join('\n\n') || '')"></div>
              </div>
            </div>
          </template>
        </div>

        <!-- References -->
        <div v-if="store.paper.references?.length" class="journal-references" :style="journalReferencesStyle">
          <h3 class="journal-ref-heading">{{ jl.references.label }}</h3>
          <div class="ref-list">
            <div v-for="(ref, rIdx) in store.paper.references" :key="rIdx" class="ref-item">
              <DiffBlock v-if="pendingRefByIdx[rIdx]" :change="pendingRefByIdx[rIdx]" :store="store" :index="rIdx">
                <template #before>
                  <span class="ref-num">[{{ rIdx + 1 }}]</span>{{ displayRef(ref) }}
                </template>
                <template #after>
                  <span class="ref-num">[{{ rIdx + 1 }}]</span>{{ pendingRefByIdx[rIdx].payload.text || '' }}
                </template>
              </DiffBlock>
              <span v-else>
                <span class="ref-num">[{{ rIdx + 1 }}]</span>{{ displayRef(ref) }}
              </span>
            </div>
            <!-- New reference proposals -->
            <div v-for="c in newRefProposals" :key="c.id"
              class="ref-item p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700">
              <DiffBlock :change="c" :store="store">
                <template #after>
                  <span class="ref-num text-amber-600">[New]</span>{{ c.payload.text || '' }}
                </template>
              </DiffBlock>
            </div>
          </div>
        </div>

        <!-- Running footer -->
        <div v-if="jl.footer?.show" class="journal-footer" :style="journalFooterStyle">
          <span v-if="jl.footer.text">{{ jl.footer.text }}</span>
        </div>
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
const pdfViewerUrl = computed(() => pdfBlobUrl.value ? pdfBlobUrl.value : '')
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
const journalLabel = computed(() => store.paper.journal || 'IEEE')

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

watch(() => store.currentPaperId, () => {
  failedImages.value = new Set()
  // Reset PDF state on paper change — don't auto-render PDF
  showPdf.value = true
  pdfUrl.value = ''
  clearPdfBlobUrl()
  pdfError.value = false
  pdfLoading.value = false
})

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
async function renderPdf() {
  if (pdfLoading.value) return
  if (!store.currentPaperId) {
    pdfError.value = true
    pdfErrorMessage.value = 'Paper belum tersimpan'
    return
  }
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
    pdfProgress.value = 95
    if (res.data?.pdf_url) {
      const url = res.data.pdf_url
      await loadPdfBlob(url)
      pdfProgress.value = 100
      if (pdfBlobUrl.value) {
        pdfUrl.value = url
        pdfKey.value++
      }
      pdfLoading.value = false
    } else {
      throw new Error('No PDF URL in response')
    }
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

onMounted(() => {
  // Don't auto-render PDF — show HTML preview by default. User clicks "PDF (Full)" to generate.
})

onUnmounted(clearPdfBlobUrl)

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
