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
        <button @click="downloadPdf" :disabled="!pdfBlobUrl || pdfLoading"
          class="px-3 py-1.5 rounded text-xs font-medium bg-navy-600 text-white transition hover:bg-navy-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50">
          PDF
        </button>
        <button @click="renderPdf" :disabled="pdfLoading"
          class="px-3 py-1.5 rounded text-xs font-medium border border-cream-300 text-ink-700 transition hover:bg-cream-200 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 dark:border-ash-600 dark:text-ink-200 dark:hover:bg-ash-700">
          Refresh
        </button>
      </div>
    </div>

    <!-- PDF Preview -->
    <div class="paper-preview-wrapper flex-1 min-h-0 w-full min-w-0 overflow-hidden">
      <!-- Loading state -->
      <div v-if="pdfLoading" class="h-full w-full bg-white dark:bg-ash-900 p-8 shadow-sm flex flex-col items-center justify-center gap-4">
        <div class="relative">
          <div class="w-10 h-10 border-3 border-cream-300 dark:border-ash-600 border-t-navy-600 dark:border-t-cream-300 rounded-full animate-spin"></div>
        </div>
        <div class="text-center">
          <p class="text-sm font-medium text-ink-700 dark:text-ink-200">Rendering {{ store.paper.journal || 'IEEE' }} PDF...</p>
          <p class="text-xs text-ink-500 dark:text-ash-400 mt-1">Generating from template, please wait</p>
        </div>
      </div>

      <div v-else-if="pdfBlobUrl" class="h-full w-full min-w-0 overflow-hidden bg-white dark:bg-ash-900">
        <iframe
          :src="pdfViewerUrl"
          :key="pdfKey"
          class="block h-full w-full border-0"
          title="PDF preview"
          @error="onIframeError"
        ></iframe>
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

    <!-- HTML Paper Preview (rendered, with INLINE diffs) — shown as fallback when PDF is not ready -->
    <div v-if="!pdfBlobUrl && !pdfUrl" class="paper-preview-wrapper overflow-auto">
      <div class="paper-preview border border-cream-300 dark:border-ash-700 rounded-2xl bg-white dark:bg-ash-900 p-8 max-w-4xl mx-auto shadow-sm"
        :style="{ transform: (showZoom && !editMode) ? `scale(${zoomLevel})` : '', transformOrigin: 'top center', transition: 'transform 0.2s ease' }">
        <!-- Title (with inline diff if pending) -->
        <DiffBlock v-if="pendingByKind.title" :change="pendingByKind.title" :store="store" align="center">
          <template #before>
            <h1 class="text-2xl font-bold leading-tight" style="font-family: 'Times New Roman', serif;">
              {{ store.paper.title || 'Paper Title' }}
            </h1>
          </template>
          <template #after>
            <h1 class="text-2xl font-bold leading-tight" style="font-family: 'Times New Roman', serif;">
              {{ pendingByKind.title.payload.value || 'Paper Title' }}
            </h1>
          </template>
        </DiffBlock>
        <div v-else class="text-center mb-4">
          <h1 class="text-2xl font-bold leading-tight" style="font-family: 'Times New Roman', serif;">
            {{ store.paper.title || 'Paper Title' }}
          </h1>
        </div>

        <!-- Authors -->
        <div class="text-center mb-6">
          <div v-for="(author, i) in store.paper.authors" :key="i" class="mb-2">
            <div class="text-sm" style="font-family: 'Times New Roman', serif;">
              {{ author.name || 'Author Name' }}<span v-if="author.affiliation" class="text-ink-600 dark:text-ink-300"> — {{ author.affiliation }}</span>
            </div>
          </div>
        </div>

        <!-- Abstract -->
        <DiffBlock v-if="pendingByKind.abstract" :change="pendingByKind.abstract" :store="store">
          <template #before>
            <div class="mb-4">
              <h2 class="text-base font-bold" style="font-family: 'Times New Roman', serif;">Abstract</h2>
              <p class="text-sm leading-relaxed mt-1" style="font-family: 'Times New Roman', serif;">
                {{ store.paper.abstract || 'Abstract goes here...' }}
              </p>
            </div>
          </template>
          <template #after>
            <div class="mb-4">
              <h2 class="text-base font-bold" style="font-family: 'Times New Roman', serif;">Abstract</h2>
              <p class="text-sm leading-relaxed mt-1" style="font-family: 'Times New Roman', serif;">
                {{ pendingByKind.abstract.payload.value || '' }}
              </p>
            </div>
          </template>
        </DiffBlock>
        <div v-else class="mb-4">
          <h2 class="text-base font-bold" style="font-family: 'Times New Roman', serif;">Abstract</h2>
          <p class="text-sm leading-relaxed mt-1" style="font-family: 'Times New Roman', serif;">
            {{ store.paper.abstract || 'Abstract goes here...' }}
          </p>
        </div>

        <!-- Keywords -->
        <div class="mb-6" v-if="store.paper.keywords?.length">
          <p class="text-sm" style="font-family: 'Times New Roman', serif;">
            <strong>Keywords:</strong> {{ store.paper.keywords.join(', ') }}
          </p>
        </div>

        <!-- New section proposals (not yet in the paper) -->
        <div v-if="newSectionProposals.length" class="mb-4 space-y-2">
          <div v-for="c in newSectionProposals" :key="c.id"
            class="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700">
            <DiffBlock :change="c" :store="store">
              <template #after>
                <h3 class="text-sm font-bold text-amber-800 dark:text-amber-200" style="font-family: 'Times New Roman', serif;">
                  {{ c.payload.title || 'New Section' }}
                </h3>
                <div class="text-sm mt-1" style="font-family: 'Times New Roman', serif;" v-html="renderInlineText(c.payload.text || '')"></div>
              </template>
            </DiffBlock>
          </div>
        </div>

        <!-- Sections -->
        <template v-for="(section, sIdx) in store.paper.sections" :key="sIdx">
          <DiffBlock v-if="pendingSectionByIdx[sIdx]" :change="pendingSectionByIdx[sIdx]" :store="store">
            <template #before>
              <div class="mb-4">
                <h3 class="text-base font-bold mt-6 mb-2" style="font-family: 'Times New Roman', serif;">
                  {{ getItemNum(section) }}. {{ section.title || 'Untitled Section' }}
                </h3>
                <div class="text-sm leading-relaxed" style="font-family: 'Times New Roman', serif;"
                  v-html="renderInlineText(sectionText(section))"></div>
              </div>
            </template>
            <template #after>
              <div class="mb-4">
                <h3 class="text-base font-bold mt-6 mb-2" style="font-family: 'Times New Roman', serif;">
                  {{ getItemNum(section) }}. {{ pendingSectionByIdx[sIdx].payload.title || 'Untitled Section' }}
                </h3>
                <div class="text-sm leading-relaxed" style="font-family: 'Times New Roman', serif;"
                  v-html="renderInlineText(pendingSectionByIdx[sIdx].payload.text || '')"></div>
              </div>
            </template>
          </DiffBlock>
          <div v-else class="mb-4">
            <h3 class="text-base font-bold mt-6 mb-2" style="font-family: 'Times New Roman', serif;">
              {{ getItemNum(section) }}. {{ section.title || 'Untitled Section' }}
            </h3>
            <div class="text-sm leading-relaxed" style="font-family: 'Times New Roman', serif;"
              v-html="renderInlineText(sectionText(section))"></div>

            <!-- Subsections -->
            <div v-for="(sub, subIdx) in section.subsections || []" :key="subIdx" class="mb-3 ml-4">
              <h4 class="text-sm font-semibold mt-4 mb-1" style="font-family: 'Times New Roman', serif;">
                {{ getItemNum(sub) }}. {{ sub.title || 'Untitled Subsection' }}
              </h4>
              <div class="text-sm leading-relaxed" style="font-family: 'Times New Roman', serif;"
                v-html="renderInlineText(sub.content?.map?.((c:any) => c.text).join('\n\n') || '')"></div>
            </div>
          </div>
        </template>

        <!-- References -->
        <div class="mt-8" v-if="store.paper.references?.length">
          <h3 class="text-base font-bold mb-3" style="font-family: 'Times New Roman', serif;">References</h3>
          <div class="space-y-1">
            <div v-for="(ref, rIdx) in store.paper.references" :key="rIdx" class="text-sm" style="font-family: 'Times New Roman', serif;">
              <DiffBlock v-if="pendingRefByIdx[rIdx]" :change="pendingRefByIdx[rIdx]" :store="store" :index="rIdx">
                <template #before>
                  <span class="text-xs text-ink-500 mr-1">[{{ rIdx + 1 }}]</span>{{ displayRef(ref) }}
                </template>
                <template #after>
                  <span class="text-xs text-ink-500 mr-1">[{{ rIdx + 1 }}]</span>{{ pendingRefByIdx[rIdx].payload.text || '' }}
                </template>
              </DiffBlock>
              <span v-else>
                <span class="text-xs text-ink-500 mr-1">[{{ rIdx + 1 }}]</span>{{ displayRef(ref) }}
              </span>
            </div>
            <!-- New reference proposals -->
            <div v-for="c in newRefProposals" :key="c.id"
              class="p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700">
              <DiffBlock :change="c" :store="store">
                <template #after>
                  <span class="text-xs text-amber-600 dark:text-amber-400 mr-1">[New]</span>{{ c.payload.text || '' }}
                </template>
              </DiffBlock>
            </div>
          </div>
        </div>

        <!-- New Ref Proposals not rendered inline -->
        <div v-if="newRefProposals.length" class="mt-4">
          <h4 class="text-sm font-semibold mb-2">New References</h4>
          <div v-for="c in newRefProposals" :key="c.id"
            class="p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700">
            <DiffBlock :change="c" :store="store">
              <template #after>
                <span class="text-xs text-amber-600 dark:text-amber-400 mr-1">[New]</span>{{ c.payload.text || '' }}
              </template>
            </DiffBlock>
          </div>
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
import api from '../api/index.js'

const failedImages = ref(new Set<string>())
const showPdf = ref(true)
const pdfLoading = ref(false)
const pdfError = ref(false)
const pdfErrorMessage = ref('')
const pdfUrl = ref('')
const pdfBlobUrl = ref('')
const pdfKey = ref(0)
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

watch(() => store.currentPaperId, () => {
  failedImages.value = new Set()
  // Reset PDF state on paper change
  showPdf.value = true
  pdfUrl.value = ''
  clearPdfBlobUrl()
  pdfError.value = false
  pdfLoading.value = false
  if (store.currentPaperId) renderPdf()
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

// PDF rendering
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
  clearPdfBlobUrl()
  try {
    const res = await api.post(
      `/api/papers/${encodeURIComponent(String(store.currentPaperId))}/pdf-preview`,
      { journal: store.paper.journal || 'IEEE' },
      { timeout: 300000 }
    )
    if (res.data?.pdf_url) {
      pdfUrl.value = res.data.pdf_url
      await loadPdfBlob(res.data.pdf_url)
      pdfKey.value++
      pdfLoading.value = false
    } else {
      throw new Error('No PDF URL in response')
    }
  } catch (err: any) {
    pdfLoading.value = false
    pdfError.value = true
    pdfErrorMessage.value = err.response?.data?.error || err.message || 'Failed to render PDF'
  }
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
  pdfBlobUrl.value = ''
  pdfUrl.value = pdfUrl.value
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

// Auto-render when PDF tab is shown or journal changes and PDF not ready
watch(() => showPdf.value, async (show) => {
  if (show && store.currentPaperId && !pdfUrl.value && !pdfLoading.value) {
    await renderPdf()
  }
})

// Auto-render when journal changes
watch(() => store.paper.journal, async (newJ, oldJ) => {
  if (showPdf.value && pdfUrl.value && !pdfLoading.value) {
    await renderPdf()
  }
})

onMounted(() => {
  if (showPdf.value && store.currentPaperId && !pdfUrl.value && !pdfLoading.value) {
    renderPdf()
  }
})

onUnmounted(clearPdfBlobUrl)

// Expose renderPdf for external use
defineExpose({ renderPdf, showPdf, togglePdfPreview })
</script>
