<template>
  <div class="bg-cream-50 dark:bg-ash-850 min-h-screen">
    <div class="border-b border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-800">
      <div class="px-4 lg:px-8">
        <div class="flex gap-1 overflow-x-auto">
          <button
            @click="activeTab = 'top'"
            :class="[
              'px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === 'top'
                ? 'border-navy-700 dark:border-cream-200 text-navy-700 dark:text-cream-200'
                : 'border-transparent text-ink-600 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
            ]"
          >
            Top {{ result.top_k }} Results
            <span class="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-navy-100 dark:bg-navy-900/30">
              {{ result.top_papers?.length || 0 }}
            </span>
          </button>
          <button
            v-for="(sourceData, sourceName) in result.sources"
            :key="sourceName"
            @click="activeTab = sourceName"
            :class="[
              'px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === sourceName
                ? 'border-navy-700 dark:border-cream-200 text-navy-700 dark:text-cream-200'
                : 'border-transparent text-ink-600 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
            ]"
          >
            {{ formatSourceName(sourceName) }}
            <span class="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-cream-100 dark:bg-ash-700">
              {{ sourceData.count || sourceData.papers?.length || 0 }}
            </span>
          </button>
        </div>
      </div>
    </div>

    <div class="px-4 lg:px-8 py-6">
      <div v-if="activeTab === 'top'" class="space-y-4">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-xl font-bold text-ink-900 dark:text-ink-50">
              Top {{ result.top_k }} Recommendations
            </h2>
            <p class="text-sm text-ink-600 dark:text-ink-300 mt-1">
              {{ result.total_found }} papers found across all sources
            </p>
          </div>
          <button
            @click="$emit('export', 'top')"
            class="px-4 py-2 min-h-[44px] bg-cream-200 hover:bg-cream-300 dark:bg-ash-700 dark:hover:bg-ash-600 text-ink-900 dark:text-ink-50 rounded-lg text-sm font-medium transition-colors"
          >
            Export
          </button>
        </div>

         <div v-if="result.summary" class="bg-navy-50 dark:bg-navy-900/20 border border-navy-200 dark:border-navy-800 rounded-xl p-4 mb-4">
          <h3 class="font-semibold text-navy-900 dark:text-navy-200 mb-2">AI Summary</h3>
          <p class="text-sm text-navy-800 dark:text-navy-300">{{ result.summary }}</p>
        </div>

        <div v-if="!result.top_papers || result.top_papers.length === 0" class="text-center py-12">
          <div class="text-4xl mb-3">📚</div>
          <p class="text-ink-600 dark:text-ink-300">No results found</p>
        </div>

        <LiteratureCard
          v-for="(paper, idx) in result.top_papers"
          :key="`top-${idx}`"
          :item="paper"
          @add-to-library="$emit('add-to-library', $event)"
        />
      </div>

      <div v-else class="space-y-4">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-xl font-bold text-ink-900 dark:text-ink-50">
              {{ formatSourceName(activeTab) }} Results
            </h2>
            <p class="text-sm text-ink-600 dark:text-ink-300 mt-1">
              {{ currentSourceData?.count || currentSourceData?.papers?.length || 0 }} papers
            </p>
          </div>
          <button
            @click="$emit('export', activeTab)"
            class="px-4 py-2 min-h-[44px] bg-cream-200 hover:bg-cream-300 dark:bg-ash-700 dark:hover:bg-ash-600 text-ink-900 dark:text-ink-50 rounded-lg text-sm font-medium transition-colors"
          >
            Export
          </button>
        </div>

        <div v-if="currentSourceData?.error" class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 mb-4">
          <p class="text-sm text-red-800 dark:text-red-300">
            <strong>Error:</strong> {{ currentSourceData.error }}
          </p>
        </div>

        <div v-if="!currentSourceData?.papers || currentSourceData.papers.length === 0" class="text-center py-12">
          <div class="text-4xl mb-3">📚</div>
          <p class="text-ink-600 dark:text-ink-300">No results from this source</p>
        </div>

        <LiteratureCard
          v-for="(paper, idx) in currentSourceData?.papers"
          :key="`${activeTab}-${idx}`"
          :item="paper"
          @add-to-library="$emit('add-to-library', $event)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { SlrResult, LiteraturePaper } from '../types/slr'
import LiteratureCard from './LiteratureCard.vue'

interface Props {
  result: SlrResult
}

const props = defineProps<Props>()

defineEmits<{
  'add-to-library': [paper: LiteraturePaper]
  'export': [tab: string]
}>()

const activeTab = ref<string>('top')

const currentSourceData = computed(() => {
  if (activeTab.value === 'top') return null
  return props.result.sources?.[activeTab.value]
})

function formatSourceName(name: string): string {
  const nameMap: Record<string, string> = {
    'scopus': 'Scopus',
    'ieee': 'IEEE Xplore',
    'crossref': 'Crossref',
    'semantic_scholar': 'Semantic Scholar',
    'arxiv': 'arXiv',
    'pubmed': 'PubMed',
    'openalex': 'OpenAlex',
    'core': 'CORE'
  }
  return nameMap[name] || name.charAt(0).toUpperCase() + name.slice(1)
}
</script>
