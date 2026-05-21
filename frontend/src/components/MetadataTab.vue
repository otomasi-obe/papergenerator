<template>
  <div class="p-6 space-y-6">
    <!-- Title -->
    <div>
      <label for="meta-title" class="block text-sm font-semibold text-ink-900 dark:text-ink-50 mb-1">Paper Title</label>
      <div class="flex gap-2">
        <input id="meta-title" v-model="store.paper.title" type="text"
          placeholder="e.g.: Lane Detection Algorithm Based on Haar Feature Based Coupled Cascade Classifier"
          class="flex-1 px-4 py-2 border border-ivory-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-700 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 rounded-lg focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none" />
        <AiButton @click="aiTitle" label="AI" :loading="store.aiLoading" />
      </div>
    </div>

    <!-- Authors -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <label class="text-sm font-semibold text-ink-900 dark:text-ink-50">Authors</label>
        <button @click="store.addAuthor()"
          class="text-sm bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-anthracite-50 px-3 py-1 rounded-lg hover:bg-ivory-300 dark:hover:bg-anthracite-500 transition-colors">+ Add Author</button>
      </div>
      <div v-for="(author, index) in store.paper.authors" :key="index"
        class="border border-ivory-300 dark:border-anthracite-500 rounded-lg p-4 mb-3 bg-white dark:bg-anthracite-700 relative">
        <button v-if="store.paper.authors.length > 1" @click="store.removeAuthor(index)"
          class="absolute top-2 right-2 text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 text-lg">✕</button>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label :for="`meta-author-${index}-name`" class="block text-xs text-ink-600 dark:text-anthracite-200 mb-1">Name</label>
            <input :id="`meta-author-${index}-name`" v-model="author.name" placeholder="Full Name" class="w-full px-3 py-1.5 border border-ivory-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 rounded text-sm focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 outline-none" />
          </div>
          <div>
            <label :for="`meta-author-${index}-email`" class="block text-xs text-ink-600 dark:text-anthracite-200 mb-1">Email</label>
            <input :id="`meta-author-${index}-email`" v-model="author.email" placeholder="email@example.com"
              class="w-full px-3 py-1.5 border border-ivory-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 rounded text-sm focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 outline-none" />
          </div>
          <div>
            <label :for="`meta-author-${index}-affiliation`" class="block text-xs text-ink-600 dark:text-anthracite-200 mb-1">Affiliation</label>
            <input :id="`meta-author-${index}-affiliation`" v-model="author.affiliation" placeholder="University / Institute"
              class="w-full px-3 py-1.5 border border-ivory-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 rounded text-sm focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 outline-none" />
          </div>
          <div>
            <label :for="`meta-author-${index}-location`" class="block text-xs text-ink-600 dark:text-anthracite-200 mb-1">Location</label>
            <input :id="`meta-author-${index}-location`" v-model="author.location" placeholder="City, Country"
              class="w-full px-3 py-1.5 border border-ivory-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 rounded text-sm focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 outline-none" />
          </div>
        </div>
      </div>
    </div>

    <!-- Abstract -->
    <div>
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-semibold text-ink-900 dark:text-ink-50">Abstract</label>
        <AiButton @click="aiAbstract" label="AI Generate" :loading="store.aiLoading" />
      </div>
      <textarea v-model="store.paper.abstract" rows="5"
        placeholder="Write or generate abstract..."
        class="w-full px-4 py-2 border border-ivory-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-700 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 rounded-lg focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none text-sm resize-y"></textarea>
      <!-- AI Prompt for Abstract -->
      <AiPromptBox section="abstract" :lastText="store.paper.abstract"
        @generated="(text) => store.paper.abstract = text" />
    </div>

    <!-- Keywords -->
    <div>
      <label for="meta-keyword-input" class="block text-sm font-semibold text-ink-900 dark:text-ink-50 mb-1">Keywords</label>
      <div class="flex flex-wrap gap-2 mb-2">
        <span v-for="(kw, i) in store.paper.keywords" :key="i"
          class="inline-flex items-center bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-anthracite-50 text-sm px-3 py-1 rounded-full">
          {{ kw }}
          <button @click="store.removeKeyword(i)" class="ml-1 text-ink-600 dark:text-anthracite-200 hover:text-ink-900 dark:hover:text-anthracite-50">✕</button>
        </span>
      </div>
      <div class="flex gap-2">
        <input id="meta-keyword-input" v-model="newKeyword" placeholder="Add keyword..." @keyup.enter="addKw"
          class="flex-1 px-3 py-1.5 border border-ivory-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-700 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 rounded text-sm focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 outline-none" />
        <button @click="addKw" class="px-4 py-1.5 bg-ink-800 dark:bg-anthracite-50 text-white dark:text-anthracite-800 rounded text-sm hover:bg-ink-900 dark:hover:bg-anthracite-100">Add</button>
      </div>
    </div>

    <!-- Acknowledgment -->
    <div>
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-semibold text-ink-900 dark:text-ink-50">Acknowledgment</label>
        <AiButton @click="aiAck" label="AI Generate" :loading="store.aiLoading" />
      </div>
      <textarea v-model="store.paper.acknowledgment" rows="3"
        placeholder="Acknowledgment text..."
        class="w-full px-4 py-2 border border-ivory-300 dark:border-anthracite-500 bg-white dark:bg-anthracite-700 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 rounded-lg focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none text-sm resize-y"></textarea>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { usePaperStore } from '../stores/paper.js'
import AiButton from './AiButton.vue'
import AiPromptBox from './AiPromptBox.vue'

const store = usePaperStore()
const newKeyword = ref('')

function addKw() {
  if (newKeyword.value.trim()) {
    store.addKeyword(newKeyword.value.trim())
    newKeyword.value = ''
  }
}

async function aiTitle() {
  const result = await store.aiGenerate(
    'Generate a concise, descriptive IEEE paper title for this paper. Return only the title text.',
    'title',
    store.paper.title
  )
  if (result) store.paper.title = result.trim()
}

async function aiAbstract() {
  const result = await store.aiGenerate(
    'Generate an IEEE conference paper abstract (150-250 words). Include the problem, proposed method, key results.',
    'abstract',
    store.paper.abstract
  )
  if (result) store.paper.abstract = result.trim()
}

async function aiAck() {
  const result = await store.aiGenerate(
    'Generate an acknowledgment section for this IEEE paper. Mention funding support if applicable.',
    'acknowledgment',
    store.paper.acknowledgment
  )
  if (result) store.paper.acknowledgment = result.trim()
}
</script>
