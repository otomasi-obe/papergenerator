<template>
  <div class="space-y-4">
    <!-- Tool header -->
    <div class="mb-4">
      <h2 class="text-lg font-bold font-serif text-ink-900 dark:text-ink-50 flex items-center gap-2">
        <span>{{ store.activeTool?.icon }}</span>
        {{ store.activeTool?.title }}
      </h2>
      <p class="text-sm text-ink-500 dark:text-ink-300 mt-1 max-w-[52ch] leading-relaxed">
        {{ store.activeTool?.desc }}
      </p>
    </div>

    <!-- Tool-specific controls -->
    <div class="flex flex-wrap gap-2.5 items-center">
      <!-- Paraphrase options -->
      <div v-if="store.activeTool?.id === 'paraphrase'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
        <button
          v-for="opt in ['Standard', 'Formal', 'Fluent', 'Concise']"
          :key="opt"
          :class="[
            'text-xs px-3 py-1.5 rounded font-medium transition-colors',
            store.selectedOption === opt
              ? 'bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700'
              : 'text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
          ]"
          @click="store.selectedOption = opt"
        >
          {{ opt }}
        </button>
      </div>

      <!-- Translator options -->
      <div v-if="store.activeTool?.id === 'translate'" class="flex items-center gap-2">
        <span class="text-xs text-ink-500 dark:text-ink-300">English →</span>
        <select
          v-model="store.selectedOption"
          class="px-2.5 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
        >
          <option>Indonesian</option>
          <option>Spanish</option>
          <option>German</option>
          <option>Chinese (Simplified)</option>
          <option>Arabic</option>
        </select>
      </div>

      <!-- Humanizer options -->
      <div v-if="store.activeTool?.id === 'humanizer'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
        <button
          v-for="opt in ['Light', 'Standard', 'Aggressive']"
          :key="opt"
          :class="[
            'text-xs px-3 py-1.5 rounded font-medium transition-colors',
            store.selectedOption === opt
              ? 'bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700'
              : 'text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
          ]"
          @click="store.selectedOption = opt"
        >
          {{ opt }}
        </button>
      </div>

      <!-- Summarize options -->
      <div v-if="store.activeTool?.id === 'summarize'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
        <button
          v-for="opt in ['TL;DR', 'Abstract', 'Bullets']"
          :key="opt"
          :class="[
            'text-xs px-3 py-1.5 rounded font-medium transition-colors',
            store.selectedOption === opt
              ? 'bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700'
              : 'text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
          ]"
          @click="store.selectedOption = opt"
        >
          {{ opt }}
        </button>
      </div>

      <!-- Run / Scan button -->
      <button
        class="px-4 py-2 rounded-lg text-xs font-semibold bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors active:scale-95 transition-transform"
        :disabled="store.isProcessing || !store.inputText.trim()"
        @click="store.processTool()"
      >
        {{ store.isProcessing ? 'Working…' : (store.activeTool?.id === 'detector' || store.activeTool?.id === 'plagiarism' ? 'Scan' : 'Run') }}
      </button>
    </div>

    <!-- Gauge for detector / plagiarism -->
    <ToolGauge
      v-if="!store.isProcessing && store.toolResult && store.activeTool?.id === 'detector'"
      :pct="store.toolResult.pct || 12"
      color="#2f9d6e"
      :title="(store.toolResult.pct || 12) + '% likely AI-generated'"
      desc="Reads mostly human · low detector risk after humanizing."
    />
    <ToolGauge
      v-if="!store.isProcessing && store.toolResult && store.activeTool?.id === 'plagiarism'"
      :pct="store.toolResult.pct || 4"
      color="#2f9d6e"
      :title="(store.toolResult.pct || 4) + '% similarity'"
      desc="No significant overlap with indexed sources. 1 minor match (common phrase)."
    />

    <!-- Two-pane Input/Output -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <!-- Input pane -->
      <div class="bg-white dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700 flex flex-col overflow-hidden">
        <div class="flex items-center justify-between px-3.5 py-2.5 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-700 text-xs font-semibold text-ink-900 dark:text-ink-50">
          <span>Input</span>
          <span class="font-normal text-ink-500 dark:text-ink-300">{{ wordCount }} words</span>
        </div>
        <textarea
          v-model="store.inputText"
          placeholder="Paste or type your text here..."
          class="w-full border-0 outline-0 resize-none bg-transparent px-3.5 py-3 text-sm leading-relaxed text-ink-900 dark:text-ink-50 min-h-[220px] placeholder-ink-500 dark:placeholder-ink-300"
        />
      </div>

      <!-- Output pane -->
      <div class="bg-white dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700 flex flex-col overflow-hidden">
        <div class="flex items-center justify-between px-3.5 py-2.5 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-700 text-xs font-semibold text-ink-900 dark:text-ink-50">
          <span>{{ store.activeTool?.id === 'detector' || store.activeTool?.id === 'plagiarism' ? 'Report' : 'Output' }}</span>
          <button
            v-if="!store.isProcessing && store.outputText"
            class="px-3 py-1 rounded-md text-xs font-semibold bg-cream-200 dark:bg-ash-600 hover:bg-cream-300 dark:hover:bg-ash-500 text-ink-900 dark:text-ink-50 transition-colors active:scale-95 transition-transform"
            @click="copyOutput"
          >
            Copy
          </button>
        </div>
        <div class="px-3.5 py-3 text-sm leading-relaxed text-ink-700 dark:text-ink-200 min-h-[220px]">
          <!-- Typing animation -->
          <div v-if="store.isProcessing && !store.outputText" class="inline-flex gap-1">
            <i class="w-1.5 h-1.5 rounded-full bg-ink-500 dark:bg-ink-300 animate-bounce" style="animation-delay: 0ms"></i>
            <i class="w-1.5 h-1.5 rounded-full bg-ink-500 dark:bg-ink-300 animate-bounce" style="animation-delay: 150ms"></i>
            <i class="w-1.5 h-1.5 rounded-full bg-ink-500 dark:bg-ink-300 animate-bounce" style="animation-delay: 300ms"></i>
          </div>
          <!-- Placeholder -->
          <span v-else-if="!store.isProcessing && !store.outputText && !store.toolResult" class="text-ink-500 dark:text-ink-300">
            Click {{ store.activeTool?.id === 'detector' || store.activeTool?.id === 'plagiarism' ? '"Scan"' : '"Run"' }} to process the input on the left.
          </span>
          <!-- Output text with diff highlighting for grammar -->
          <span v-else-if="store.activeTool?.id === 'grammar'" v-html="renderGrammarOutput(store.outputText)"></span>
          <!-- Citation output (monospace) -->
          <span v-else-if="store.activeTool?.id === 'citation'" class="font-mono text-xs leading-relaxed" v-html="store.outputText"></span>
          <!-- Plain output -->
          <span v-else-if="store.outputText" v-html="store.outputText"></span>
          <!-- Fallback -->
          <span v-else class="text-ink-500 dark:text-ink-300">Done — see the report above.</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useToolsStore } from '../stores/tools.ts'
import ToolGauge from './ToolGauge.vue'

const store = useToolsStore()

const wordCount = computed(() => {
  const text = store.inputText.trim()
  if (!text) return 0
  return text.split(/\s+/).length
})

function copyOutput() {
  if (!store.outputText) return
  navigator.clipboard.writeText(store.outputText).catch(() => {
    // Fallback
    const ta = document.createElement('textarea')
    ta.value = store.outputText
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  })
}

function renderGrammarOutput(text: string): string {
  if (!text) return ''
  // Simple diff markup: ++added++ --deleted--
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/<add>(.*?)<\/add>/g, '<span class="bg-emerald-200/30 dark:bg-emerald-800/30 rounded px-0.5">$1</span>')
    .replace(/<del>(.*?)<\/del>/g, '<span class="bg-red-200/30 dark:bg-red-800/30 line-through rounded px-0.5">$1</span>')
}
</script>
