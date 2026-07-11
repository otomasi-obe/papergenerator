<template>
  <div v-if="!store.activeTool" class="space-y-4">
    <div class="mb-4">
      <h2 class="text-lg font-bold font-serif text-ink-900 dark:text-ink-50 flex items-center gap-2">
        <svg class="w-5 h-5 text-navy-700 dark:text-cream-200 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
        Tools
      </h2>
      <p class="text-sm text-ink-500 dark:text-ink-300 mt-1 max-w-[52ch] leading-relaxed">
        AI writing toolkit — paraphrase, translate, humanize, and check your draft before submission. Each tool runs on the selected text or your whole paper.
      </p>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      <div
        v-for="tool in store.TOOLS"
        :key="tool.id"
        class="bg-white dark:bg-ash-800 rounded-2xl border border-cream-300 dark:border-ash-700 p-4 cursor-pointer hover:border-navy-500 dark:hover:border-cream-400 transition-all active:scale-[0.98] shadow-[0_1px_0_rgba(15,14,11,0.04),0_1px_3px_rgba(15,14,11,0.06)]"
        @click="handleToolClick(tool)"
      >
        <div
          class="w-[38px] h-[38px] rounded-lg flex items-center justify-center mb-3 text-white"
          :style="{ background: tool.tint }"
        >
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="tool.iconSvg"></svg>
        </div>
        <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 mb-1">{{ tool.title }}</h3>
        <p class="text-xs text-ink-500 dark:text-ink-300 leading-relaxed">{{ tool.desc }}</p>
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

const store = useToolsStore()
const showWordAddonModal = ref(false)

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
