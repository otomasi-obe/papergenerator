<template>
  <div class="p-6">
    <!-- Resolved changes (collapsible at top) -->
    <div v-if="resolvedChanges.length > 0" class="mb-3 max-w-4xl mx-auto">
      <button @click="resolvedOpen = !resolvedOpen"
        class="text-xs text-ink-500 hover:text-ink-700 flex items-center gap-1">
        <span>{{ resolvedOpen ? '▾' : '▸' }}</span>
        Riwayat persetujuan ({{ resolvedChanges.length }})
        <button v-if="resolvedOpen" @click.stop="store.clearResolvedProposals()"
          class="ml-2 text-[10px] underline text-ink-400 hover:text-ink-600">bersihkan</button>
      </button>
      <div v-if="resolvedOpen" class="mt-2 space-y-1.5">
        <div v-for="c in resolvedChanges" :key="c.id"
          class="text-[11px] flex items-center gap-2 bg-cream-50 rounded px-2 py-1">
          <span :class="c.status === 'accepted' ? 'text-emerald-600' : 'text-rose-500'">
            {{ c.status === 'accepted' ? '✓' : '✕' }}
          </span>
          <span class="font-medium text-ink-600">{{ kindLabel(c.kind) }}</span>
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
        <span v-if="editMode" class="text-[11px] text-amber-600 dark:text-amber-400 animate-pulse">Editing — perubahan auto-save</span>
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

    <!-- IEEE Paper Preview (rendered, with INLINE diffs) -->
    <div class="paper-preview border border-cream-300 dark:border-ash-700 rounded-2xl bg-white dark:bg-ash-900 p-8 max-w-4xl mx-auto shadow-sm">
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
          class="text-2xl font-bold text-center w-full bg-transparent border-b-2 border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-2 py-1"
          style="font-family: 'Times New Roman', serif;" placeholder="Paper Title" />
        <h1 v-else class="text-2xl font-bold leading-tight" style="font-family: 'Times New Roman', serif;">
          {{ store.paper.title || 'Paper Title' }}
        </h1>
      </div>

      <!-- Authors -->
      <div class="text-center mb-6">
        <div v-for="(author, i) in store.paper.authors" :key="i" class="mb-2">
          <div class="text-sm" style="font-family: 'Times New Roman', serif;">{{ author.name }}</div>
           <div class="text-xs italic text-ink-600 dark:text-ink-400" style="font-family: 'Times New Roman', serif;">
            {{ author.affiliation }}
          </div>
          <div v-if="author.location" class="text-xs italic text-ink-600 dark:text-ink-400" style="font-family: 'Times New Roman', serif;">
            {{ author.location }}
          </div>
          <div v-if="author.email" class="text-xs italic text-ink-600 dark:text-ink-400" style="font-family: 'Times New Roman', serif;">
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
          class="italic w-full bg-transparent border border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 rounded outline-none px-2 py-1 resize-none min-h-[4rem]"
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
              <p class="text-justify whitespace-pre-wrap text-sm">{{ sectionText(section) }}</p>
            </template>
            <template #after>
              <h2 class="text-center font-bold mb-2 text-sm">
                {{ toRoman(sIdx + 1) }}. {{ (pendingSectionByIdx[sIdx].payload.title || '').toUpperCase() }}
              </h2>
              <p class="text-justify whitespace-pre-wrap text-sm">{{ pendingSectionByIdx[sIdx].payload.content || '' }}</p>
            </template>
          </DiffBlock>

          <template v-else>
            <h2 class="text-center font-bold mb-2 text-sm">
              {{ toRoman(sIdx + 1) }}. {{ section.title?.toUpperCase() }}
            </h2>

            <template v-for="(item, cIdx) in section.content" :key="cIdx">
              <div v-if="item.id === 'text' && item.text" class="mb-2">
                <textarea v-if="editMode" :value="item.text"
                  @input="item.text = ($event.target as HTMLTextAreaElement).value"
                  class="w-full text-justify whitespace-pre-wrap text-sm leading-snug bg-transparent border border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 rounded outline-none px-2 py-1 resize-none min-h-[3rem]"
                  style="font-family: 'Times New Roman', serif;" rows="2"
                  placeholder="Tulis konten..."></textarea>
                <p v-else class="text-justify indent-6 whitespace-pre-wrap text-sm leading-snug">{{ item.text }}</p>
              </div>
              <div v-else-if="item.id === 'gambar'" class="my-3 text-center">
                <div class="inline-block border border-cream-300 rounded p-2">
                  <img v-if="item.Path" :src="imgSrc(item.Path)" class="max-h-48 mx-auto" :alt="item.Title" />
                  <div v-else class="w-48 h-32 bg-cream-100 flex items-center justify-center text-ink-400 text-xs">No image</div>
                </div>
                <input v-if="editMode" v-model="item.Title"
                  class="text-xs mt-1 text-ink-600 text-center bg-transparent border-b border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1"
                  placeholder="Caption gambar..." />
                <p v-else-if="item.Title" class="text-xs mt-1 text-ink-600">Fig. {{ getItemNum(item) }}. {{ item.Title }}</p>
              </div>
              <div v-else-if="item.id === 'tabel'" class="my-3">
                <input v-if="editMode" v-model="item.Title"
                  class="text-xs text-center font-semibold mb-1 w-full bg-transparent border-b border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1"
                  placeholder="Judul tabel..." />
                <p v-else-if="item.Title" class="text-xs text-center font-semibold mb-1">TABLE {{ getItemNum(item) }}: {{ item.Title }}</p>
                <table class="w-full text-xs border-collapse border border-cream-400 mx-auto">
                  <thead>
                    <tr>
                      <th v-for="(h, hi) in item.Headers" :key="hi" class="border border-cream-400 bg-cream-50 px-2 py-1 text-center font-semibold">{{ h }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, ri) in item.Rows" :key="ri">
                      <td v-for="(cell, ci) in row" :key="ci" class="border border-cream-400 px-2 py-1 text-center">{{ cell }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else-if="item.id === 'rumus' && item.latex" class="my-2 text-center font-mono text-sm text-ink-700">
                <input v-if="editMode" v-model="item.latex"
                  class="text-center bg-transparent border-b border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1 font-mono"
                  placeholder="LaTeX formula..." />
                <span v-else>({{ getItemNum(item) }}) &nbsp; {{ item.latex }}</span>
              </div>
            </template>

            <div v-for="(sub, subIdx) in section.subsections" :key="subIdx" class="mt-3">
              <input v-if="editMode" v-model="sub.title"
                class="font-bold italic text-sm mb-1 w-full bg-transparent border-b border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1"
                placeholder="Subsection title..." />
              <h3 v-else class="font-bold italic text-sm mb-1">
                {{ String.fromCharCode(65 + subIdx) }}. {{ sub.title }}
              </h3>
              <template v-for="(item, cIdx) in sub.content" :key="cIdx">
                <div v-if="item.id === 'text' && item.text" class="mb-2">
                  <textarea v-if="editMode" :value="item.text"
                    @input="item.text = ($event.target as HTMLTextAreaElement).value"
                    class="w-full text-justify whitespace-pre-wrap text-sm leading-snug bg-transparent border border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 rounded outline-none px-2 py-1 resize-none min-h-[3rem]"
                    style="font-family: 'Times New Roman', serif;" rows="2"
                    placeholder="Tulis konten..."></textarea>
                  <p v-else class="text-justify indent-6 whitespace-pre-wrap text-sm leading-snug">{{ item.text }}</p>
                </div>
                <div v-else-if="item.id === 'gambar'" class="my-3 text-center">
                  <div class="inline-block border border-cream-300 rounded p-2">
                    <img v-if="item.Path" :src="imgSrc(item.Path)" class="max-h-48 mx-auto" :alt="item.Title" />
                    <div v-else class="w-48 h-32 bg-cream-100 flex items-center justify-center text-ink-400 text-xs">No image</div>
                  </div>
                  <input v-if="editMode" v-model="item.Title"
                    class="text-xs mt-1 text-ink-600 text-center bg-transparent border-b border-dashed border-cream-400 focus:border-navy-500 focus:ring-[#238f7f]/30 outline-none px-1"
                    placeholder="Caption gambar..." />
                  <p v-else-if="item.Title" class="text-xs mt-1 text-ink-600">Fig. {{ getItemNum(item) }}. {{ item.Title }}</p>
                </div>
              </template>
            </div>
          </template>
        </div>

        <!-- Newly proposed sections (no existing index) -->
        <DiffBlock v-for="change in newSectionProposals" :key="change.id" :change="change" :store="store">
          <template #before>
            <p class="text-rose-700 italic text-xs">(belum ada section ini — akan ditambahkan)</p>
          </template>
          <template #after>
            <h2 class="text-center font-bold mb-2 text-sm">
              + {{ (change.payload.title || '').toUpperCase() }}
            </h2>
            <p class="text-justify whitespace-pre-wrap text-sm">{{ change.payload.content || '' }}</p>
          </template>
        </DiffBlock>

        <!-- References -->
        <div v-if="store.paper.references.length > 0">
          <h2 class="text-center font-bold mb-2 text-sm">REFERENCES</h2>
          <div v-for="(ref, i) in store.paper.references" :key="i">
            <DiffBlock v-if="pendingRefByIdx[i]" :change="pendingRefByIdx[i]" :store="store">
              <template #before>
                <div class="text-xs leading-snug pl-6 -indent-6">[{{ i + 1 }}] {{ ref || '(kosong)' }}</div>
              </template>
              <template #after>
                <div class="text-xs leading-snug pl-6 -indent-6">[{{ i + 1 }}] {{ pendingRefByIdx[i].payload.value || '' }}</div>
              </template>
            </DiffBlock>
            <div v-else class="text-xs leading-snug mb-1 pl-6 -indent-6">
              [{{ i + 1 }}] {{ ref }}
            </div>
          </div>

          <!-- New reference proposals -->
          <DiffBlock v-for="change in newRefProposals" :key="change.id" :change="change" :store="store">
            <template #before>
              <div class="text-rose-700 italic text-xs pl-6 -indent-6">(referensi baru — akan ditambahkan)</div>
            </template>
            <template #after>
              <div class="text-xs leading-snug pl-6 -indent-6">+ [{{ store.paper.references.length + 1 }}] {{ change.payload.value }}</div>
            </template>
          </DiffBlock>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed } from 'vue'
import { usePaperStore } from '../stores/paper'
import DiffBlock from './DiffBlock.vue'

const store = usePaperStore()
const resolvedOpen = ref(false)
const editMode = ref(false)

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

function imgSrc(path: string): string {
  if (!store.currentPaperId || store.currentPaperId === 'null' || store.currentPaperId === 'undefined' || !path) return ''
  return `/api/images/${store.currentPaperId}/${path}`
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
</script>
