<template>
  <article class="bg-cream-50 dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700 p-4 hover:shadow-md transition-all">
    <div class="flex items-start justify-between gap-3 mb-2">
      <h3 class="font-semibold text-ink-900 dark:text-ink-50 text-base leading-snug flex-1">
        {{ item.title }}
      </h3>
      <div class="flex gap-1 flex-shrink-0">
        <button
          v-if="item.doi"
          @click="openDoi"
          class="px-2 py-1 text-xs bg-cream-200 dark:bg-ash-700 hover:bg-cream-300 dark:hover:bg-ash-600 rounded transition-colors"
          title="Open DOI"
        >
          DOI
        </button>
        <button
          v-if="item.url"
          @click="openUrl"
          class="px-2 py-1 text-xs bg-cream-200 dark:bg-ash-700 hover:bg-cream-300 dark:hover:bg-ash-600 rounded transition-colors"
          title="Open URL"
        >
          URL
        </button>
      </div>
    </div>

    <div class="text-sm text-ink-700 dark:text-ink-300 mb-2">
      <p v-if="item.authors && item.authors.length > 0" class="mb-1">
        {{ formatAuthors(item.authors) }}
      </p>
      <div class="flex flex-wrap gap-2 text-xs">
        <span v-if="item.year" class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700">
          {{ item.year }}
        </span>
        <span v-if="item.venue" class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700">
          {{ item.venue }}
        </span>
        <span v-if="item.citations !== null && item.citations !== undefined" class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700">
          {{ item.citations }} citations
        </span>
        <span v-if="item.score_total !== null && item.score_total !== undefined" class="px-2 py-0.5 rounded-full bg-brown-100 dark:bg-brown-900/30 text-brown-800 dark:text-brown-300">
          Score: {{ item.score_total.toFixed(2) }}
        </span>
        <span class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700">
          {{ item.source }}
        </span>
      </div>
    </div>

    <p v-if="item.abstract || item.summary" class="text-sm text-ink-600 dark:text-ink-400 line-clamp-3 mb-3">
      {{ item.summary || item.abstract }}
    </p>

    <div class="flex gap-2">
      <button
        @click="$emit('add-to-library', item)"
        class="flex-1 px-3 py-1.5 min-h-[44px] bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 text-sm rounded-lg transition-colors font-medium"
      >
        Add to Library
      </button>
      <button
        @click="expanded = !expanded"
        class="px-3 py-1.5 min-h-[44px] bg-cream-200 hover:bg-cream-300 dark:bg-ash-700 dark:hover:bg-ash-600 text-ink-900 dark:text-ink-50 text-sm rounded-lg transition-colors"
      >
        {{ expanded ? 'Less' : 'More' }}
      </button>
    </div>

    <div v-if="expanded" class="mt-3 pt-3 border-t border-cream-300 dark:border-ash-700">
      <div v-if="item.abstract" class="mb-3">
        <h4 class="font-semibold text-sm text-ink-900 dark:text-ink-50 mb-1">Abstract</h4>
        <p class="text-sm text-ink-600 dark:text-ink-400">{{ item.abstract }}</p>
      </div>
      <div v-if="item.publisher" class="mb-2">
        <span class="font-semibold text-sm text-ink-900 dark:text-ink-50">Publisher:</span>
        <span class="text-sm text-ink-600 dark:text-ink-400 ml-2">{{ item.publisher }}</span>
      </div>
      <div v-if="item.doi" class="mb-2">
        <span class="font-semibold text-sm text-ink-900 dark:text-ink-50">DOI:</span>
        <span class="text-sm text-ink-600 dark:text-ink-400 ml-2">{{ item.doi }}</span>
      </div>
      <div v-if="item.score_breakdown && Object.keys(item.score_breakdown).length > 0" class="mb-2">
        <h4 class="font-semibold text-sm text-ink-900 dark:text-ink-50 mb-1">Score Breakdown</h4>
        <div class="flex flex-wrap gap-2">
          <span
            v-for="(score, key) in item.score_breakdown"
            :key="key"
            class="px-2 py-0.5 text-xs rounded-full bg-cream-100 dark:bg-ash-700"
          >
            {{ key }}: {{ score.toFixed(2) }}
          </span>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { LiteraturePaper } from '../types/slr'

interface Props {
  item: LiteraturePaper
}

defineProps<Props>()

defineEmits<{
  'add-to-library': [item: LiteraturePaper]
}>()

const expanded = ref(false)

function formatAuthors(authors: string[]): string {
  if (authors.length === 0) return 'Unknown authors'
  if (authors.length === 1) return authors[0]
  if (authors.length === 2) return `${authors[0]} and ${authors[1]}`
  if (authors.length <= 5) return `${authors.slice(0, -1).join(', ')}, and ${authors[authors.length - 1]}`
  return `${authors.slice(0, 3).join(', ')}, et al.`
}

function openDoi() {
  const props = defineProps<Props>()
  if (props.item.doi) {
    window.open(`https://doi.org/${props.item.doi}`, '_blank')
  }
}

function openUrl() {
  const props = defineProps<Props>()
  if (props.item.url) {
    window.open(props.item.url, '_blank')
  }
}
</script>
