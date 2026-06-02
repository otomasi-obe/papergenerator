<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold text-gray-800">References</h2>
        <p class="text-sm text-gray-500">IEEE citation format. Reference in text with [1], [2], etc.</p>
      </div>
      <div class="flex gap-2">
        <AiButton @click="aiGenerateRefs" label="AI Generate All" :loading="store.aiLoading" />
        <button @click="store.addReference()"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium">
          + Add Reference
        </button>
      </div>
    </div>

    <div v-if="store.paper.references.length === 0"
      class="text-center py-12 text-gray-400">
      <svg class="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
      </svg>
      <p>No references yet.</p>
    </div>

    <div v-for="(ref, index) in store.paper.references" :key="ref.id"
      class="flex items-start gap-3 mb-3 group">
      <span class="text-sm font-mono bg-gray-100 px-2 py-1.5 rounded text-gray-600 min-w-[40px] text-center">
        [{{ Number(index) + 1 }}]
      </span>
      <div class="flex-1">
        <textarea v-model="ref.text" rows="2" v-autosize
          :placeholder="`A. Author, B. Author, &quot;Title of paper,&quot; Journal Name, vol. X, no. Y, pp. 1-10, 2024.`"
          class="w-full px-3 py-1.5 border rounded text-sm focus:ring-2 focus:ring-blue-200 outline-none resize-y"></textarea>
      </div>
      <div class="flex flex-col gap-1">
        <AiButton @click="aiEditRef(Number(index))" label="AI" :loading="store.aiLoading" />
        <button @click="store.removeReference(Number(index))"
          class="text-red-400 hover:text-red-600 text-xs opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
      </div>
    </div>

    <!-- AI Prompt for References -->
    <div class="mt-4 border rounded-lg bg-gray-50 p-4">
      <div class="flex items-center gap-2 mb-2">
        <svg class="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
        </svg>
        <span class="text-sm font-medium text-gray-600">AI Prompt — add references</span>
      </div>
      <div class="flex gap-2">
        <input v-model="refPrompt" type="text"
          placeholder="e.g.: Add 5 references about lane detection using machine learning"
          class="flex-1 px-3 py-1.5 border rounded text-sm focus:ring-2 focus:ring-purple-200 focus:border-purple-400 outline-none"
          @keyup.enter="aiAddRefs" />
        <button @click="aiAddRefs"
          :disabled="store.aiLoading || !refPrompt.trim()"
          class="px-4 py-1.5 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 disabled:opacity-50">
          Send
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { usePaperStore } from '../stores/paper'
import AiButton from './AiButton.vue'

// @ts-ignore - paper store will be converted to TypeScript in Week 3-4
const { usePaperStore } = await import('../stores/paper.js')
const store = usePaperStore()
const refPrompt = ref<string>('')

async function aiGenerateRefs(): Promise<void> {
  const allText = [
    store.paper.abstract || '',
    ...store.paper.sections.map((s: any) => {
      let text = s.content || ''
      for (const sub of s.subsections || []) {
        text += ' ' + (sub.content || '')
        for (const item of sub.numberedItems || []) {
          text += ' ' + (item.content || '')
        }
      }
      return text
    })
  ].join(' ')

  const result = await store.aiGenerate(
    `Based on the following paper content, generate IEEE format references that match the citations [1], [2], etc. mentioned in the text. Return each reference on a new line in format: [N] Author, "Title," Journal, vol. X, pp. X-Y, Year.\n\nPaper content:\n${allText.substring(0, 3000)}`,
    'references',
    store.paper.references.map((r: any, i: number) => `[${i + 1}] ${r.text}`).join('\n')
  )
  if (result) {
    parseAndSetReferences(result)
  }
}

async function aiEditRef(index: number): Promise<void> {
  const ref = store.paper.references[index]
  const result = await store.aiGenerate(
    `Fix this IEEE reference to proper format: ${ref.text}. Return only the corrected reference text without the [N] number.`,
    'reference',
    ref.text
  )
  if (result) {
    store.paper.references[index].text = result.trim().replace(/^\[\d+\]\s*/, '')
  }
}

async function aiAddRefs(): Promise<void> {
  if (!refPrompt.value.trim()) return
  const currentCount = store.paper.references.length
  const result = await store.aiGenerate(
    `${refPrompt.value}\n\nReturn references in IEEE format, each on a new line. Start numbering from [${currentCount + 1}]. Format: [N] Author, "Title," Journal, vol. X, pp. X-Y, Year.`,
    'references',
    ''
  )
  if (result) {
    parseAndAddReferences(result, currentCount)
    refPrompt.value = ''
  }
}

function parseAndSetReferences(text: string): void {
  const lines = text.split('\n').filter(l => l.trim())
  store.paper.references = []
  let id = 1
  for (const line of lines) {
    const cleaned = line.replace(/^\[\d+\]\s*/, '').trim()
    if (cleaned) {
      store.paper.references.push({ id: id++, text: cleaned })
    }
  }
}

function parseAndAddReferences(text: string, startId: number): void {
  const lines = text.split('\n').filter(l => l.trim())
  let id = startId + 1
  for (const line of lines) {
    const cleaned = line.replace(/^\[\d+\]\s*/, '').trim()
    if (cleaned) {
      store.paper.references.push({ id: id++, text: cleaned })
    }
  }
}
</script>
