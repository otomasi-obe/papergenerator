<template>
  <div v-if="!store.activeTool" class="space-y-5 px-4 lg:px-6 py-4 pb-20">
    <!-- Paper Tools section -->
    <div>
      <h2 class="text-sm font-semibold text-ink-600 dark:text-ink-300 uppercase tracking-wide mb-3">Paper Tools</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          v-for="pt in PAPER_TOOLS"
          :key="pt.id"
          type="button"
          class="group bg-white/90 dark:bg-ash-800/80 rounded-2xl border border-cream-200/80 dark:border-ash-600/70 p-4 text-left cursor-pointer hover:border-navy-500/70 dark:hover:border-cream-300/80 hover:-translate-y-0.5 transition-all active:scale-[0.98] shadow-[0_1px_0_rgba(15,14,11,0.04),0_8px_24px_rgba(15,14,11,0.04)] hover:shadow-[0_1px_0_rgba(15,14,11,0.05),0_12px_30px_rgba(15,14,11,0.08)] focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-500/35 dark:focus-visible:ring-cream-300/35"
          @click="$emit('openPanel', pt.panel)"
        >
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-xl flex items-center justify-center text-navy-700 dark:text-cream-200 bg-cream-100/80 dark:bg-ash-700/80 ring-1 ring-cream-200/70 dark:ring-ash-600/70 shrink-0 group-hover:bg-cream-200/80 dark:group-hover:bg-ash-600/80 transition-colors">
              <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="pt.iconSvg"></svg>
            </div>
            <div class="min-w-0">
              <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 mb-1">{{ pt.title }}</h3>
              <p class="text-xs text-ink-500 dark:text-ink-300 leading-relaxed">{{ pt.desc }}</p>
            </div>
          </div>
        </button>
      </div>
    </div>

    <!-- Writing Tools section -->
    <div>
      <h2 class="text-sm font-semibold text-ink-600 dark:text-ink-300 uppercase tracking-wide mb-3">Writing Tools</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          v-for="tool in store.TOOLS"
          :key="tool.id"
          type="button"
          class="group bg-white/90 dark:bg-ash-800/80 rounded-2xl border border-cream-200/80 dark:border-ash-600/70 p-4 text-left cursor-pointer hover:border-navy-500/70 dark:hover:border-cream-300/80 hover:-translate-y-0.5 transition-all active:scale-[0.98] shadow-[0_1px_0_rgba(15,14,11,0.04),0_8px_24px_rgba(15,14,11,0.04)] hover:shadow-[0_1px_0_rgba(15,14,11,0.05),0_12px_30px_rgba(15,14,11,0.08)] focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-500/35 dark:focus-visible:ring-cream-300/35"
          @click="handleToolClick(tool)"
        >
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-xl flex items-center justify-center text-navy-700 dark:text-cream-200 bg-cream-100/80 dark:bg-ash-700/80 ring-1 ring-cream-200/70 dark:ring-ash-600/70 shrink-0 group-hover:bg-cream-200/80 dark:group-hover:bg-ash-600/80 transition-colors">
              <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="tool.iconSvg"></svg>
            </div>
            <div class="min-w-0">
              <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 mb-1">{{ tool.title }}</h3>
              <p class="text-xs text-ink-500 dark:text-ink-300 leading-relaxed">{{ tool.desc }}</p>
            </div>
          </div>
        </button>
      </div>
    </div>

    <WordAddonInstallModal
      :show="showWordAddonModal"
      @close="showWordAddonModal = false"
    />
  </div>

  <ToolWorkspace v-else />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useToolsStore } from '../stores/tools.ts'
import ToolWorkspace from './ToolWorkspace.vue'
import WordAddonInstallModal from './WordAddonInstallModal.vue'

defineEmits<{ openPanel: [panel: string] }>()

const store = useToolsStore()
const showWordAddonModal = ref(false)

const PAPER_TOOLS = [
  { id: 'paperfull', panel: 'paperfull', title: 'Generate Full', desc: 'Generate a complete academic paper from your outline using AI.', iconSvg: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><polyline points="14 2 14 8 20 8"/><path d="M9 15l2 2 4-4"/>' },
  { id: 'journal', panel: 'journal', title: 'Journal', desc: 'Search and select target journals matching your paper topic.', iconSvg: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>' },
  { id: 'literature', panel: 'literature', title: 'Literatur', desc: 'Find and manage references from academic databases.', iconSvg: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>' },
  { id: 'files', panel: 'files', title: 'Files', desc: 'Upload and manage supporting documents for your paper.', iconSvg: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>' },
  { id: 'data', panel: 'data', title: 'Data', desc: 'Import and visualize research data, tables, and charts.', iconSvg: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>' },
  { id: 'image', panel: 'image', title: 'Image', desc: 'Generate or manage figures and diagrams for your paper.', iconSvg: '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>' },
]

function handleToolClick(tool) {
  if (tool.external) {
    if (tool.id === 'word-addon') {
      showWordAddonModal.value = true
    }
    return
  }
  store.setActiveTool(tool)
}
</script>
