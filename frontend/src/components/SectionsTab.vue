<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-brown-800 dark:text-anthracite-50">Paper Sections</h2>
      <button @click="store.addSection()"
        class="px-4 py-2 bg-brown-600 dark:bg-anthracite-600 text-cream-50 rounded-lg hover:bg-brown-700 dark:hover:bg-anthracite-500 text-sm font-medium">
        + Add Section
      </button>
    </div>

    <div v-if="store.paper.sections.length === 0"
      class="text-center py-12 text-brown-400 dark:text-anthracite-200">
      <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p>No sections yet. Add a section or generate a full paper.</p>
    </div>

    <!-- Sections List -->
    <div v-for="(section, sIdx) in store.paper.sections" :key="section.id"
      class="border dark:border-anthracite-500 rounded-xl mb-4 overflow-hidden">

      <!-- Section Header -->
      <div class="bg-cream-200 dark:bg-anthracite-700 px-4 py-3 flex items-center justify-between cursor-pointer"
        @click="toggleSection(Number(sIdx))">
        <div class="flex items-center gap-2">
          <svg :class="['w-4 h-4 transition-transform', expandedSections[Number(sIdx)] ? 'rotate-90' : '']"
            fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
          </svg>
          <span class="font-bold text-brown-800 dark:text-anthracite-50">{{ section.number }}.</span>
          <input v-model="section.title" placeholder="Section Title (e.g. INTRODUCTION)"
            class="bg-transparent font-semibold text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 focus:outline-none focus:bg-cream-50 dark:focus:bg-anthracite-800 px-2 py-0.5 rounded"
            @click.stop />
        </div>
        <div class="flex items-center gap-2">
          <AiButton @click.stop="aiSection(Number(sIdx))" label="AI" :loading="store.aiLoading" />
          <button @click.stop="store.addSubsection(Number(sIdx))"
            class="text-xs bg-cream-100 dark:bg-anthracite-600 text-brown-700 dark:text-anthracite-100 px-2 py-1 rounded hover:bg-cream-300 dark:hover:bg-anthracite-500">+ Sub</button>
          <button @click.stop="store.removeSection(Number(sIdx))"
            class="text-xs text-red-400 hover:text-red-600">✕ Remove</button>
        </div>
      </div>

      <!-- Section Content -->
      <div v-show="expandedSections[Number(sIdx)]" class="p-4 space-y-4">
        <div>
          <label class="block text-xs text-brown-500 dark:text-anthracite-200 mb-1">Section Content</label>
          <textarea v-model="section.content" rows="6" v-autosize
            placeholder="Write section content... Use [1], [2] for citations. Use $$formula$$ for equations."
            class="w-full px-3 py-2 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded-lg text-sm focus:ring-2 focus:ring-cream-200 focus:border-brown-400 outline-none resize-y"></textarea>
          <AiPromptBox :section="section.title || 'section'" :lastText="section.content"
            @generated="(text: string) => section.content = text" />
        </div>

        <!-- Subsections -->
        <div v-for="(sub, subIdx) in section.subsections" :key="sub.id"
          class="border-l-4 border-cream-400 dark:border-anthracite-500 pl-4 ml-2 space-y-3">

          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="font-semibold text-brown-700 dark:text-anthracite-100 text-sm">{{ sub.letter }}.</span>
              <input v-model="sub.title" placeholder="Subsection Title"
                class="font-medium text-sm bg-transparent text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 focus:outline-none focus:bg-cream-50 dark:focus:bg-anthracite-800 px-2 py-0.5 rounded border-b border-cream-300 dark:border-anthracite-500" />
            </div>
            <div class="flex items-center gap-2">
              <AiButton @click="aiSubsection(Number(sIdx), Number(subIdx))" label="AI" :loading="store.aiLoading" />
              <button @click="store.addNumberedItem(Number(sIdx), Number(subIdx))"
                class="text-xs bg-cream-200 dark:bg-anthracite-600 text-brown-700 dark:text-anthracite-100 px-2 py-1 rounded hover:bg-cream-300 dark:hover:bg-anthracite-500"># Item</button>
              <button @click="store.removeSubsection(Number(sIdx), Number(subIdx))"
                class="text-xs text-red-400 hover:text-red-600">✕</button>
            </div>
          </div>

          <textarea v-model="sub.content" rows="4" v-autosize
            placeholder="Subsection content..."
            class="w-full px-3 py-2 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm focus:ring-2 focus:ring-cream-200 focus:border-brown-400 outline-none resize-y"></textarea>
          <AiPromptBox :section="sub.title || 'subsection'" :lastText="sub.content"
            @generated="(text: string) => sub.content = text" />

          <!-- Numbered Items (like "1) Weak Classifier Design") -->
          <div v-for="(item, itemIdx) in sub.numberedItems" :key="itemIdx"
            class="border-l-4 border-cream-300 dark:border-anthracite-500 pl-3 ml-2 space-y-2">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-sm font-semibold text-brown-600 dark:text-anthracite-100">{{ item.number }})</span>
                <input v-model="item.title" placeholder="Item Title"
                  class="text-sm bg-transparent text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 focus:outline-none focus:bg-cream-50 dark:focus:bg-anthracite-800 px-2 py-0.5 rounded border-b border-cream-300 dark:border-anthracite-500" />
              </div>
              <div class="flex items-center gap-1">
                <AiButton @click="aiNumberedItem(Number(sIdx), Number(subIdx), Number(itemIdx))" label="AI" :loading="store.aiLoading" />
                <button @click="store.removeNumberedItem(Number(sIdx), Number(subIdx), Number(itemIdx))"
                  class="text-xs text-red-400 hover:text-red-600">✕</button>
              </div>
            </div>
            <textarea v-model="item.content" rows="3" v-autosize
              placeholder="Item content..."
              class="w-full px-3 py-2 border border-cream-300 dark:border-anthracite-500 bg-cream-50 dark:bg-anthracite-800 text-brown-900 dark:text-anthracite-50 dark:placeholder-anthracite-300 rounded text-sm focus:ring-2 focus:ring-cream-200 focus:border-brown-400 outline-none resize-y"></textarea>
            <AiPromptBox :section="item.title || 'item'" :lastText="item.content"
              @generated="(text: string) => item.content = text" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { usePaperStore } from '../stores/paper'
import AiButton from './AiButton.vue'
import AiPromptBox from './AiPromptBox.vue'

// @ts-ignore - paper store will be converted to TypeScript in Week 3-4
const { usePaperStore } = await import('../stores/paper.js')

const store = usePaperStore()
const expandedSections = reactive<Record<number, boolean>>({})

function toggleSection(idx: number): void {
  expandedSections[idx] = !expandedSections[idx]
}

async function aiSection(sIdx: number): Promise<void> {
  const section = store.paper.sections[sIdx]
  const result = await store.aiGenerate(
    `Write the content for section "${section.number}. ${section.title}" of this IEEE conference paper. Write detailed, formal academic content with citations [1], [2] etc.`,
    section.title || 'section',
    section.content
  )
  if (result) section.content = result.trim()
}

async function aiSubsection(sIdx: number, subIdx: number): Promise<void> {
  const sub = store.paper.sections[sIdx].subsections[subIdx]
  const parentTitle = store.paper.sections[sIdx].title
  const result = await store.aiGenerate(
    `Write the content for subsection "${sub.letter}. ${sub.title}" under section "${parentTitle}". Write detailed academic content.`,
    sub.title || 'subsection',
    sub.content
  )
  if (result) sub.content = result.trim()
}

async function aiNumberedItem(sIdx: number, subIdx: number, itemIdx: number): Promise<void> {
  const item = store.paper.sections[sIdx].subsections[subIdx].numberedItems[itemIdx]
  const result = await store.aiGenerate(
    `Write the content for "${item.number}) ${item.title}". Write formal academic content with technical detail.`,
    item.title || 'item',
    item.content
  )
  if (result) item.content = result.trim()
}
</script>
