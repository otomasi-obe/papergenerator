<template>
  <div class="p-6">
    <!-- Resolved changes (collapsible at top) -->
    <div v-if="resolvedChanges.length > 0" class="mb-3 max-w-4xl mx-auto">
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

    <div class="flex items-center justify-between mb-4 max-w-4xl mx-auto">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">Paper Preview</h2>
        <button @click="editMode = !editMode"
          :class="['px-3 py-1 rounded-lg text-xs font-medium transition-colors flex items-center gap-1 active:scale-95 transition-transform',
            editMode
              ? 'bg-amber-500 text-white hover:bg-amber-600'
              : 'text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700 border border-cream-300 dark:border-ash-600']">
          <span>{{ editMode ? '👁 View' : '✏️ Edit' }}</span>
        </button>
        <span v-if="editMode" class="text-[11px] text-amber-600 dark:text-amber-300 animate-pulse">Editing — perubahan auto-save</span>
      </div>
      <div class="flex items-center gap-2">
        <!-- Zoom controls (only when tools panel is closed) -->
        <div v-if="showZoom && !editMode" class="flex items-center gap-1 border border-cream-300 dark:border-ash-600 rounded-lg overflow-hidden">
          <button @click="zoomOut" :disabled="zoomLevel <= 0.5"
            class="px-2 py-1 text-xs text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700 disabled:opacity-30 transition-colors"
            title="Zoom out">−</button>
          <span class="px-2 py-1 text-xs text-ink-600 dark:text-ink-300 tabular-nums min-w-[3rem] text-center">{{ Math.round(zoomLevel * 100) }}%</span>
          <button @click="zoomIn" :disabled="zoomLevel >= 2"
            class="px-2 py-1 text-xs text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700 disabled:opacity-30 transition-colors"
            title="Zoom in">+</button>
          <button @click="zoomLevel = 1"
            class="px-2 py-1 text-xs text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700 border-l border-cream-300 dark:border-ash-600 transition-colors"
            title="Reset zoom">↺</button>
        </div>
        <button @click="store.exportDocx()"
                    class="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm font-medium flex items-center gap-2 active:scale-95 transition-transform">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Export DOCX
        </button>
      </div>
    </div>

    <!-- IEEE Paper Preview (rendered, with INLINE diffs) -->
    <div class="paper-preview-wrapper overflow-auto">
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
        <input v-if="editMode" v-model="store.paper.title"
          class="text-2xl font-bold text-center w-full bg-transparent border-b-2 border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-2 py-1 dark:text-ash-100"
          style="font-family: 'Times New Roman', serif;" placeholder="Paper Title" />
        <h1 v-else class="text-2xl font-bold leading-tight" style="font-family: 'Times New Roman', serif;">
          {{ store.paper.title || 'Paper Title' }}
        </h1>
      </div>

      <!-- Authors -->
      <div class="text-center mb-6">
        <div v-for="(author, i) in store.paper.authors" :key="i" class="mb-2">
          <div class="text-sm" style="font-family: 'Times New Roman', serif;">{{ author.name }}</div>
           <div class="text-xs italic opacity-70 dark:opacity-60" style="font-family: 'Times New Roman', serif;">
            {{ author.affiliation }}
          </div>
          <div v-if="author.location" class="text-xs italic opacity-70 dark:opacity-60" style="font-family: 'Times New Roman', serif;">
            {{ author.location }}
          </div>
          <div v-if="author.email" class="text-xs italic opacity-70 dark:opacity-60" style="font-family: 'Times New Roman', serif;">
            e-mail: {{ author.email }}
          </div>
        </div>
      </div>

      <!-- Abstract (with inline diff if pending) -->
      <DiffBlock v-if="pendingByKind.abstract" :change="pendingByKind.abstract" :store="store">
        <template #before>
          <div class="text-justify" style="font-family: 'Times New Roman', serif; font-size: 9pt;">
            <span class="font-bold italic">Abstract—</span>
            <span class="italic">{{ store.paper.abstract || '(kosong)' }}</span>
          </div>
        </template>
        <template #after>
          <div class="text-justify" style="font-family: 'Times New Roman', serif; font-size: 9pt;">
            <span class="font-bold italic">Abstract—</span>
            <span class="italic">{{ pendingByKind.abstract.payload.value }}</span>
          </div>
        </template>
      </DiffBlock>
      <div v-else class="mb-4 text-justify" style="font-family: 'Times New Roman', serif; font-size: 9pt;">
        <span class="font-bold italic">Abstract—</span>
        <textarea v-if="editMode" v-model="store.paper.abstract"
          v-autoresize
          class="italic w-full bg-transparent border border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 rounded outline-none px-2 py-1 resize-none overflow-hidden dark:text-ash-100"
          placeholder="Paper abstract..." rows="2"></textarea>
        <span v-else class="italic">{{ store.paper.abstract || '(kosong)' }}</span>
      </div>

      <!-- Keywords (with inline diff if pending) -->
      <DiffBlock v-if="pendingByKind.keywords" :change="pendingByKind.keywords" :store="store">
        <template #before>
          <div class="text-justify" style="font-family: 'Times New Roman', serif; font-size: 9pt;">
            <span class="font-bold italic">Keywords—</span>
            <span class="italic">{{ (store.paper.keywords || []).join(', ') || '(kosong)' }}</span>
          </div>
        </template>
        <template #after>
          <div class="text-justify" style="font-family: 'Times New Roman', serif; font-size: 9pt;">
            <span class="font-bold italic">Keywords—</span>
            <span class="italic">{{ (pendingByKind.keywords.payload.value || []).join(', ') }}</span>
          </div>
        </template>
      </DiffBlock>
      <div v-else-if="store.paper.keywords.length > 0" class="mb-6 text-justify" style="font-family: 'Times New Roman', serif; font-size: 9pt;">
        <span class="font-bold italic">Keywords—</span>
        <span class="italic">{{ store.paper.keywords.join(', ') }}</span>
      </div>

      <!-- Sections -->
      <div class="space-y-4" style="font-family: 'Times New Roman', serif; font-size: 10pt;">
        <!-- Existing sections (with possible diff overlay) -->
        <div v-for="(section, sIdx) in store.paper.sections" :key="sIdx" class="mb-4">
          <DiffBlock v-if="pendingSectionByIdx[sIdx]" :change="pendingSectionByIdx[sIdx]" :store="store">
            <template #before>
              <h2 class="text-center font-bold mb-2 text-sm">
                {{ toRoman(sIdx + 1) }}. {{ section.title?.toUpperCase() }}
              </h2>
              <p class="text-justify whitespace-pre-wrap text-sm" v-html="renderInlineText(sectionText(section))"></p>
            </template>
            <template #after>
              <h2 class="text-center font-bold mb-2 text-sm">
                {{ toRoman(sIdx + 1) }}. {{ (pendingSectionByIdx[sIdx].payload.title || '').toUpperCase() }}
              </h2>
              <p class="text-justify whitespace-pre-wrap text-sm" v-html="renderInlineText(pendingSectionByIdx[sIdx].payload.content || '')"></p>
            </template>
          </DiffBlock>

          <template v-else>
            <h2 class="text-center font-bold mb-2 text-sm">
              {{ toRoman(sIdx + 1) }}. {{ section.title?.toUpperCase() }}
            </h2>

            <template v-for="(item, cIdx) in section.content" :key="cIdx">
              <div v-if="item.id === 'text' && item.text" class="mb-2">
                <textarea v-if="editMode" :value="item.text"
                  @input="onTextareaInput($event, item)"
                  v-autoresize
                  class="w-full text-justify whitespace-pre-wrap text-sm leading-snug bg-transparent border border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 rounded outline-none px-2 py-1 resize-none overflow-hidden dark:text-ash-100"
                  style="font-family: 'Times New Roman', serif;" rows="2"
                  placeholder="Tulis konten..."></textarea>
                <p v-else class="text-justify indent-6 whitespace-pre-wrap text-sm leading-snug" v-html="renderInlineText(item.text)"></p>
              </div>
              <div v-else-if="item.id === 'gambar'" class="my-3 text-center">
                <div class="inline-block border border-cream-300 dark:border-ash-600 rounded p-2">
                  <img v-if="item.Path && !failedImages.has(item.Path)" :src="imgSrc(item.Path)" class="max-h-48 mx-auto" :alt="item.Title" @error="onImgError($event, item.Path)" />
                  <div v-else-if="item.Path && failedImages.has(item.Path)" class="w-48 h-32 bg-rose-50 dark:bg-rose-900/20 flex items-center justify-center rounded text-xs text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                    ⚠️ Gambar gagal dimuat
                  </div>
                  <div v-else class="w-48 h-32 bg-cream-100 dark:bg-ash-800 flex items-center justify-center opacity-50 dark:opacity-40 text-xs">No image</div>
                </div>
                <input v-if="editMode" v-model="item.Title"
                  class="text-xs mt-1 opacity-70 dark:opacity-60 text-center bg-transparent border-b border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1"
                  placeholder="Caption gambar..." />
                <p v-else-if="item.Title" class="text-xs mt-1 opacity-70 dark:opacity-60">Fig. {{ getItemNum(item) }}. {{ item.Title }}</p>
              </div>
              <div v-else-if="item.id === 'tabel'" class="my-3">
                <input v-if="editMode" v-model="item.Title"
                  class="text-xs text-center font-semibold mb-1 w-full bg-transparent border-b border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1 dark:text-ash-100"
                  placeholder="Judul tabel..." />
                <p v-else-if="item.Title" class="text-xs text-center font-semibold mb-1">TABLE {{ getItemNum(item) }}: {{ item.Title }}</p>
                <table class="w-full text-xs border-collapse border border-cream-400 dark:border-ash-600 mx-auto">
                  <thead>
                    <tr>
                      <th v-for="(h, hi) in item.Headers" :key="hi" class="border border-cream-400 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 px-2 py-1 text-center font-semibold">{{ h }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, ri) in item.Rows" :key="ri">
                      <td v-for="(cell, ci) in row" :key="ci" class="border border-cream-400 dark:border-ash-600 px-2 py-1 text-center">{{ cell }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else-if="item.id === 'rumus' && item.latex" class="my-2 text-center text-sm">
                <input v-if="editMode" v-model="item.latex"
                  class="w-full text-center bg-transparent border-b border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1 font-mono dark:text-ash-100"
                  placeholder="LaTeX formula..." />
                <div v-else class="flex items-center justify-between">
                  <span class="flex-1 text-center" v-html="renderFormula(item.latex)"></span>
                  <span class="text-xs opacity-50 ml-4 tabular-nums">({{ getItemNum(item) }})</span>
                </div>
              </div>
            </template>

            <div v-for="(sub, subIdx) in section.subsections" :key="subIdx" class="mt-3">
              <input v-if="editMode" v-model="sub.title"
                class="font-bold italic text-sm mb-1 w-full bg-transparent border-b border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1 dark:text-ash-100"
                placeholder="Subsection title..." />
              <h3 v-else class="font-bold italic text-sm mb-1">
                {{ String.fromCharCode(65 + subIdx) }}. {{ sub.title }}
              </h3>
              <template v-for="(item, cIdx) in sub.content" :key="cIdx">
                <div v-if="item.id === 'text' && item.text" class="mb-2">
                  <textarea v-if="editMode" :value="item.text"
                    @input="onTextareaInput($event, item)"
                    v-autoresize
                    class="w-full text-justify whitespace-pre-wrap text-sm leading-snug bg-transparent border border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 rounded outline-none px-2 py-1 resize-none overflow-hidden dark:text-ash-100"
                    style="font-family: 'Times New Roman', serif;" rows="2"
                    placeholder="Tulis konten..."></textarea>
                  <p v-else class="text-justify indent-6 whitespace-pre-wrap text-sm leading-snug" v-html="renderInlineText(item.text)"></p>
                </div>
                <div v-else-if="item.id === 'gambar'" class="my-3 text-center">
                  <div class="inline-block border border-cream-300 dark:border-ash-600 rounded p-2">
                    <img v-if="item.Path && !failedImages.has(item.Path)" :src="imgSrc(item.Path)" class="max-h-48 mx-auto" :alt="item.Title" @error="onImgError($event, item.Path)" />
                    <div v-else-if="item.Path && failedImages.has(item.Path)" class="w-48 h-32 bg-rose-50 dark:bg-rose-900/20 flex items-center justify-center rounded text-xs text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                      ⚠️ Gambar gagal dimuat
                    </div>
                    <div v-else class="w-48 h-32 bg-cream-100 dark:bg-ash-800 flex items-center justify-center opacity-50 dark:opacity-40 text-xs">No image</div>
                  </div>
                  <input v-if="editMode" v-model="item.Title"
                    class="text-xs mt-1 opacity-70 dark:opacity-60 text-center bg-transparent border-b border-dashed border-cream-400 dark:border-ash-500 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1"
                    placeholder="Caption gambar..." />
                  <p v-else-if="item.Title" class="text-xs mt-1 opacity-70 dark:opacity-60">Fig. {{ getItemNum(item) }}. {{ item.Title }}</p>
                </div>
                <div v-else-if="item.id === 'tabel'" class="my-3">
                  <p class="text-xs text-center font-semibold mb-1">{{ item.Title || 'Table ' + item.TableNumber }}</p>
                  <table class="text-xs border-collapse w-full mx-auto">
                    <thead><tr><th v-for="(h,i) in item.Headers" :key="i" class="border border-cream-400 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 px-2 py-1 text-center font-semibold">{{ h }}</th></tr></thead>
                    <tbody><tr v-for="(row,ri) in item.Rows" :key="ri"><td v-for="(cell,ci) in row" :key="ci" class="border border-cream-400 dark:border-ash-600 px-2 py-1 text-center">{{ cell }}</td></tr></tbody>
                  </table>
                </div>
                <div v-else-if="item.id === 'rumus' && (item.latex || item.text)" class="my-3">
                  <div class="flex items-center justify-between">
                    <span class="flex-1 text-center" v-html="renderFormula(item.latex || item.text)"></span>
                    <span class="text-xs opacity-50 ml-4 tabular-nums">({{ getItemNum(item) }})</span>
                  </div>
                </div>
              </template>
            </div>
          </template>
        </div>

        <!-- Newly proposed sections (no existing index) -->
        <DiffBlock v-for="change in newSectionProposals" :key="change.id" :change="change" :store="store">
          <template #before>
            <p class="text-rose-700 dark:text-rose-300 italic text-xs">(belum ada section ini — akan ditambahkan)</p>
          </template>
          <template #after>
            <h2 class="text-center font-bold mb-2 text-sm">
              + {{ (change.payload.title || '').toUpperCase() }}
            </h2>
            <p class="text-justify whitespace-pre-wrap text-sm" v-html="renderInlineText(change.payload.content || '')"></p>
          </template>
        </DiffBlock>

        <!-- References -->
        <div v-if="store.paper.references.length > 0">
          <h2 class="text-center font-bold mb-2 text-sm">REFERENCES</h2>
          <div v-for="(ref, i) in store.paper.references" :key="i">
            <DiffBlock v-if="pendingRefByIdx[i]" :change="pendingRefByIdx[i]" :store="store">
              <template #before>
                <div class="text-xs leading-snug pl-6 -indent-6">[{{ i + 1 }}] {{ displayRef(ref) || '(kosong)' }}</div>
              </template>
              <template #after>
                <div class="text-xs leading-snug pl-6 -indent-6">[{{ i + 1 }}] {{ pendingRefByIdx[i].payload.value || '' }}</div>
              </template>
            </DiffBlock>
            <div v-else class="text-xs leading-snug mb-1 pl-6 -indent-6">
              [{{ i + 1 }}] {{ displayRef(ref) }}
            </div>
          </div>

          <!-- New reference proposals -->
          <DiffBlock v-for="change in newRefProposals" :key="change.id" :change="change" :store="store">
            <template #before>
              <div class="text-rose-700 dark:text-rose-300 italic text-xs pl-6 -indent-6">(referensi baru — akan ditambahkan)</div>
            </template>
            <template #after>
              <div class="text-xs leading-snug pl-6 -indent-6">+ [{{ store.paper.references.length + 1 }}] {{ change.payload.value }}</div>
            </template>
          </DiffBlock>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, nextTick } from 'vue'
import { usePaperStore } from '../stores/paper'
import DiffBlock from './DiffBlock.vue'
import { renderLatex, renderRichText } from '../composables/useMathRender'

// Track which image filenames failed to load, so we show a placeholder
const failedImages = ref(new Set<string>())

function onImgError(event: Event, filename: string) {
  const target = event.target as HTMLImageElement
  failedImages.value.add(filename)
  target.style.display = 'none'
}

function renderFormula(latex: string): string {
  return renderLatex(latex, true)
}

function renderInlineText(text: string): string {
  return renderRichText(text)
}

// Display helper for references — handles strings and structured objects
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

function imgSrc(path: string): string {
  if (!store.currentPaperId || store.currentPaperId === 'null' || store.currentPaperId === 'undefined' || !path) return ''
  // Extract basename if path is absolute filesystem path
  const filename = path.includes('/') ? path.split('/').pop() || path : path
  const url = `/api/images/${store.currentPaperId}/${filename}`
  // Append JWT token from cookie so <img> tags authenticate
  const token = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1]
  return token ? `${url}?t=${token}` : url
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

// Auto-resize directive for textareas
const vAutoresize = {
  mounted(el: HTMLTextAreaElement) {
    const resize = () => {
      el.style.height = 'auto'
      el.style.height = el.scrollHeight + 'px'
    }
    el.addEventListener('input', resize)
    // Initial resize
    nextTick(resize)
    // Store cleanup reference
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
</script>
