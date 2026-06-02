<template>
  <div v-if="!store.activeTool" class="space-y-4">
    <div class="mb-4">
      <h2 class="text-lg font-bold font-serif text-ink-900 dark:text-ink-50 flex items-center gap-2">
        🛠 Tools
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
        @click="store.setActiveTool(tool)"
      >
        <div
          class="w-[38px] h-[38px] rounded-lg flex items-center justify-center text-lg mb-3 text-white"
          :style="{ background: tool.tint }"
        >
          {{ tool.icon }}
        </div>
        <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 mb-1">{{ tool.title }}</h3>
        <p class="text-xs text-ink-500 dark:text-ink-300 leading-relaxed">{{ tool.desc }}</p>
      </div>
    </div>
  </div>

  <ToolWorkspace v-else />
</template>

<script setup lang="ts">
import { useToolsStore } from '../stores/tools.ts'
import ToolWorkspace from './ToolWorkspace.vue'

const store = useToolsStore()
</script>
