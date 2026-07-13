<template>
 <div class="space-y-4">
 <!-- Tool header -->
 <div class="mb-4 flex items-start justify-between">
 <div>
 <h2 class="text-lg font-bold font-serif text-ink-900 dark:text-ink-50 flex items-center gap-2">
   <svg class="w-5 h-5 text-navy-700 dark:text-cream-200 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="store.activeTool?.iconSvg"></svg>
   {{ store.activeTool?.title }}
 </h2>
 <p class="text-sm text-ink-500 dark:text-ink-300 mt-1 max-w-[52ch] leading-relaxed">
 {{ store.activeTool?.desc }}
 </p>
 </div>
 <!-- Clear button -->
 <button
 v-if="store.inputText || store.outputText || store.toolResult"
 class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 border border-red-200 dark:border-red-800 transition active:scale-95 shrink-0 mt-1"
 @click="store.clearToolData()"
 title="Clear input & output"
 >
 <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
 Clear
 </button>
 </div>

 <!-- Tool-specific controls -->
 <div class="flex flex-wrap gap-2.5 items-center">
 <!-- Paraphrase options -->
 <div v-if="store.activeTool?.id === 'paraphrase'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
 <button
 v-for="opt in ['Standard', 'Formal', 'Fluent', 'Concise']"
 :key="opt"
 :class="[
 'text-xs px-3 py-1.5 rounded font-medium transition',
 store.selectedOption === opt
 ? 'bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700'
 : 'text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
 ]"
 @click="store.selectedOption = opt"
 >
 {{ opt }}
 </button>
 </div>

 <!-- Translator options (ID ↔ EN only) -->
 <div v-if="store.activeTool?.id === 'translate'" class="flex items-center gap-2">
 <select
 v-model="store.selectedSource"
 class="px-3 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 font-medium"
 >
 <option value="Indonesian">🇮🇩 Indonesian</option>
 <option value="English">🇬🇧 English</option>
 </select>

 <!-- Swap button -->
 <button
 @click="swapLanguages"
 class="p-2 rounded-full border border-cream-300 dark:border-ash-600 bg-cream-100 dark:bg-ash-700 text-ink-700 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-ash-600 transition active:scale-90"
 title="Swap languages"
 >
 <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"/></svg>
 </button>

 <select
 v-model="store.selectedOption"
 class="px-3 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30 font-medium"
 >
 <option value="English">🇬🇧 English</option>
 <option value="Indonesian">🇮🇩 Indonesian</option>
 </select>

 <!-- Engine selector -->
  <select
  v-model="store.selectedEngine"
 class="px-2.5 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
 >
 <option v-for="eng in engineOptions" :key="eng.value" :value="eng.value">{{ eng.label }}</option>
 </select>

 <!-- Domain selector -->
 <select
 v-model="store.selectedDomain"
 class="px-2.5 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
 >
 <option v-for="dom in domainOptions" :key="dom" :value="dom">{{ dom }}</option>
 </select>
 </div>

 <!-- Detector options -->
 <div v-if="store.activeTool?.id === 'detector'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
 <button
 v-for="opt in ['Fast', 'Deep', 'Hybrid']"
 :key="opt"
 :class="[
 'text-xs px-3 py-1.5 rounded font-medium transition',
 store.selectedOption === opt
 ? 'bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700'
 : 'text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
 ]"
 @click="store.selectedOption = opt"
 >
 {{ opt }}
 </button>
 </div>

 <!-- Humanizer options -->
 <div v-if="store.activeTool?.id === 'humanizer'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
 <button
 v-for="opt in ['Light', 'Standard', 'Aggressive']"
 :key="opt"
 :class="[
 'text-xs px-3 py-1.5 rounded font-medium transition',
 store.selectedOption === opt
 ? 'bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700'
 : 'text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
 ]"
 @click="store.selectedOption = opt"
 >
 {{ opt }}
 </button>
 </div>

 <!-- Plagiarism options -->
 <div v-if="store.activeTool?.id === 'plagiarism'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
 <button
 v-for="opt in ['AI Check', 'Web Search', 'Offline', 'Full Scan']"
 :key="opt"
 :class="[
 'text-xs px-3 py-1.5 rounded font-medium transition',
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
 'text-xs px-3 py-1.5 rounded font-medium transition',
 store.selectedOption === opt
 ? 'bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700'
 : 'text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
 ]"
 @click="store.selectedOption = opt"
 >
 {{ opt }}
 </button>
 </div>

 <!-- Grammar options -->
 <div v-if="store.activeTool?.id === 'grammar'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
 <button
 v-for="opt in ['Standard','Grammar','Spelling','Style','Clarity','Academic','Indonesian']"
 :key="opt"
 :class="[
 'text-xs px-3 py-1.5 rounded font-medium transition',
 store.selectedOption === opt
 ? 'bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-700'
 : 'text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50'
 ]"
 @click="store.selectedOption = opt"
 >
 {{ opt }}
 </button>
 </div>

 <!-- Run button -->
 <button
 class="px-4 py-2 rounded-lg text-xs font-semibold bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-50 disabled:cursor-not-allowed transition active:scale-95 "
 :disabled="store.isProcessing || !store.inputText.trim()"
 @click="store.processTool()"
 >
 {{ store.isProcessing ? 'Working…' : (store.activeTool?.id === 'detector' || store.activeTool?.id === 'plagiarism' ? 'Scan' : 'Run') }}
 </button>
 </div>

 <!-- Detector Report -->
 <div
 v-if="!store.isProcessing && store.toolResult && store.activeTool?.id === 'detector'"
 class="space-y-3"
 >
 <!-- Score + Verdict -->
 <div class="flex items-center gap-3.5 p-3.5 rounded-xl bg-cream-100 dark:bg-ash-700">
 <div
 class="w-16 h-16 rounded-full flex items-center justify-center text-xl font-extrabold shrink-0"
 :style="{ background: `conic-gradient(${detectorColor} ${(store.toolResult.pct || 0) * 3.6}deg, var(--border-soft) 0deg)` }"
 >
 <div class="w-[46px] h-[46px] rounded-full bg-cream-50 dark:bg-ash-800 flex items-center justify-center text-ink-900 dark:text-ink-50 text-base font-extrabold">
 {{ Math.round(store.toolResult.pct || 0) }}%
 </div>
 </div>
 <div class="min-w-0 flex-1">
 <div class="text-sm font-bold text-ink-900 dark:text-ink-50">
 {{ store.toolResult.verdict }}
 </div>
 <div class="text-xs text-ink-500 dark:text-ink-300 mt-0.5">
 {{ detectorSubtitle }}
 </div>
 <div v-if="store.toolResult.model?.attributed && store.toolResult.model.attributed !== 'Unknown'" class="mt-1">
 <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-cream-200 dark:bg-ash-600 text-ink-700 dark:text-ink-200">
 🤖 {{ store.toolResult.model.attributed }}
 <span class="text-ink-400 dark:text-ink-300">({{ store.toolResult.model.confidence }}%)</span>
 </span>
 </div>
 </div>
 <div v-if="store.toolResult.stats" class="flex gap-2 text-xs text-ink-500 dark:text-ink-300 shrink-0">
 <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">{{ store.toolResult.stats.words }} words</span>
 <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">{{ store.toolResult.stats.sentences }} sentences</span>
 <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">{{ store.toolResult.stats.flagged_sentences }} flagged</span>
 </div>
 </div>

 <!-- Engine breakdown (collapsible) -->
 <details class="group">
 <summary class="cursor-pointer text-xs font-semibold text-ink-600 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50 select-none">
 ▸ Engine breakdown ({{ store.toolResult.engines?.length || 0 }} engines)
 </summary>
 <div class="mt-2 space-y-1.5 pl-1">
 <div
 v-for="eng in (store.toolResult.engines || []).slice(0, 12)"
 :key="eng.id"
 class="flex items-center gap-2 text-xs"
 >
 <span class="w-32 text-ink-600 dark:text-ink-300 truncate">{{ eng.label }}</span>
 <div class="flex-1 h-2 rounded-full bg-cream-200 dark:bg-ash-600 overflow-hidden">
 <div
 class="h-full rounded-full transition-all duration-500"
 :style="{ width: eng.score + '%', background: engineBarColor(eng.score) }"
 ></div>
 </div>
 <span class="w-10 text-right font-mono text-ink-500 dark:text-ink-300">{{ Math.round(eng.score) }}%</span>
 </div>
 </div>
 </details>
 </div>

 <!-- Plagiarism gauge -->
 <ToolGauge
 v-if="!store.isProcessing && store.toolResult && store.activeTool?.id === 'plagiarism'"
 :pct="store.toolResult.pct || 0"
 :color="(store.toolResult.pct || 0) >= 50 ? '#dc2626' : (store.toolResult.pct || 0) >= 25 ? '#f59e0b' : '#2f9d6e'"
 :title="(store.toolResult.pct || 0) + '% similarity detected'"
 :desc="(store.toolResult.pct || 0) >= 50 ? 'High plagiarism risk — review highlighted passages.' : (store.toolResult.pct || 0) >= 25 ? 'Moderate similarity — consider paraphrasing flagged sections.' : 'Low similarity — text appears mostly original.'"
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
 ref="inputTextarea"
 :value="store.inputText"
 @input="onInput"
 placeholder="Paste or type your text here..."
 class="w-full border-0 outline-0 resize-none bg-transparent px-3.5 py-3 text-sm leading-relaxed text-ink-900 dark:text-ink-50 placeholder-ink-500 dark:placeholder-ink-300"
 :style="{ minHeight: '220px' }"
 />
 </div>

 <!-- Output pane -->
 <div class="bg-white dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700 flex flex-col overflow-hidden">
 <div class="flex items-center justify-between px-3.5 py-2.5 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-700 text-xs font-semibold text-ink-900 dark:text-ink-50">
 <span>{{ store.activeTool?.id === 'detector' || store.activeTool?.id === 'plagiarism' ? 'Report' : 'Output' }}</span>
 <div class="flex items-center gap-1.5">
 <button
 v-if="!store.isProcessing && store.outputText"
 class="px-3 py-1 rounded-md text-xs font-semibold bg-cream-200 dark:bg-ash-600 hover:bg-cream-300 dark:hover:bg-ash-500 text-ink-900 dark:text-ink-50 transition active:scale-95"
 @click="copyOutput"
 >
 Copy
 </button>
 </div>
 </div>
 <div class="px-3.5 py-3 text-sm leading-relaxed text-ink-700 dark:text-ink-200 min-h-[220px] overflow-auto">
 <!-- Typing animation -->
 <div v-if="store.isProcessing && !store.outputText && !store.toolResult" class="flex items-center gap-2">
 <div class="inline-flex gap-1">
 <i class="w-1.5 h-1.5 rounded-full bg-ink-500 dark:bg-ink-300 animate-bounce" style="animation-delay: 0ms"></i>
 <i class="w-1.5 h-1.5 rounded-full bg-ink-500 dark:bg-ink-300 animate-bounce" style="animation-delay: 150ms"></i>
 <i class="w-1.5 h-1.5 rounded-full bg-ink-500 dark:bg-ink-300 animate-bounce" style="animation-delay: 300ms"></i>
 </div>
 <span class="text-xs text-ink-400 dark:text-ink-300">{{ processingLabel }}</span>
 </div>

 <!-- Placeholder -->
 <span v-else-if="!store.isProcessing && !store.outputText && !store.toolResult" class="text-ink-500 dark:text-ink-300">
 Click {{ store.activeTool?.id === 'detector' || store.activeTool?.id === 'plagiarism' ? '"Scan"' : '"Run"' }} to process the input on the left.
 </span>

 <!-- Error -->
 <div v-if="store.error" class="p-2.5 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 text-xs mb-2">
 ⚠ {{ store.error }}
 </div>

 <!-- Grammar: inline diff -->
 <span v-else-if="store.activeTool?.id === 'grammar' && store.outputText" v-html="renderGrammarOutput(store.outputText)"></span>

 <!-- Plagiarism report -->
 <div v-else-if="store.activeTool?.id === 'plagiarism' && store.toolResult" class="space-y-3">
 <div v-if="store.toolResult.breakdown" class="flex gap-2 text-xs text-ink-600 dark:text-ink-300 mb-2">
 <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">Offline: {{ store.toolResult.breakdown.offline_pct }}%</span>
 <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">Web: {{ store.toolResult.breakdown.web_pct }}%</span>
 <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">AI: {{ store.toolResult.breakdown.ai_pct }}%</span>
 </div>
 <div v-if="store.toolResult.reasons?.length" class="text-xs">
 <div class="font-semibold text-ink-700 dark:text-ink-200 mb-1">Findings:</div>
 <ul class="list-disc list-inside space-y-0.5 text-ink-600 dark:text-ink-300">
 <li v-for="(r, i) in store.toolResult.reasons" :key="i">{{ r }}</li>
 </ul>
 </div>
 <div v-if="store.toolResult.highlighted_sentences?.length" class="text-xs">
 <div class="font-semibold text-ink-700 dark:text-ink-200 mb-1">Flagged passages:</div>
 <ul class="space-y-1">
 <li v-for="(h, i) in store.toolResult.highlighted_sentences" :key="i"
 class="border-l-3 pl-2 py-1"
 :class="{
 'border-red-400 bg-red-50/50 dark:bg-red-900/20': h.severity === 'high',
 'border-amber-400 bg-amber-50/50 dark:bg-amber-900/20': h.severity === 'moderate',
 'border-blue-400 bg-blue-50/50 dark:bg-blue-900/20': h.severity === 'low',
 }">
 <span class="text-ink-800 dark:text-ink-100">"{{ h.text }}"</span>
 <div class="text-ink-500 dark:text-ink-300 mt-0.5">{{ h.issue }}<span v-if="h.note"> — {{ h.note }}</span></div>
 </li>
 </ul>
 </div>
 <div v-if="store.toolResult.sources?.length" class="text-xs">
 <div class="font-semibold text-ink-700 dark:text-ink-200 mb-1">Potential sources:</div>
 <ul class="space-y-1">
 <li v-for="(s, i) in store.toolResult.sources" :key="i" class="text-ink-600 dark:text-ink-300">
 <a :href="s.url" target="_blank" rel="noopener" class="text-navy-600 dark:text-cream-300 underline hover:no-underline">{{ s.title || s.url }}</a>
 <span v-if="s.match_pct" class="ml-1 text-red-500 dark:text-red-400 font-medium">{{ s.match_pct }}% match</span>
 </li>
 </ul>
 </div>
 <div v-if="store.toolResult.suggestions?.length" class="text-xs">
 <div class="font-semibold text-ink-700 dark:text-ink-200 mb-1">Suggestions:</div>
 <ul class="list-disc list-inside space-y-0.5 text-ink-600 dark:text-ink-300">
 <li v-for="(s, i) in store.toolResult.suggestions" :key="i">{{ s }}</li>
 </ul>
 </div>
 </div>

 <!-- Detector: sentence highlighting -->
 <div v-else-if="store.activeTool?.id === 'detector' && store.toolResult?.sentences?.length" class="space-y-3">
 <div class="text-xs text-ink-500 dark:text-ink-300 leading-relaxed">
 Sentences are color-coded by AI likelihood.
 <span class="inline-flex items-center gap-1.5 ml-2">
 <span class="w-2.5 h-2.5 rounded-full bg-red-400"></span> High
 <span class="w-2.5 h-2.5 rounded-full bg-amber-400 ml-1"></span> Moderate
 <span class="w-2.5 h-2.5 rounded-full bg-blue-400 ml-1"></span> Low
 <span class="w-2.5 h-2.5 rounded-full bg-ink-200 dark:bg-ink-600 ml-1"></span> Clean
 </span>
 </div>
 <div class="space-y-1.5">
 <div
 v-for="(sent, i) in store.toolResult.sentences"
 :key="i"
 class="rounded-lg px-3 py-2 text-sm leading-relaxed border-l-3 transition cursor-default"
 :class="sentenceClass(sent)"
 :title="sent.reasons?.join(', ') || 'No AI signals detected'"
 >
 <span class="text-ink-800 dark:text-ink-100">{{ sent.text }}</span>
 <div v-if="sent.reasons?.length" class="mt-1 flex flex-wrap gap-1">
 <span
 v-for="(r, j) in sent.reasons"
 :key="j"
 class="text-[10px] px-1.5 py-0.5 rounded bg-ink-100 dark:bg-ash-600 text-ink-500 dark:text-ink-300"
 >{{ r }}</span>
 </div>
 </div>
 </div>
 <!-- LLM result (deep/hybrid mode) -->
 <div v-if="store.toolResult.llm" class="mt-2 p-3 rounded-lg bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600">
 <div class="text-xs font-semibold text-ink-700 dark:text-ink-200 mb-1.5">
 🤖 LLM Analysis ({{ store.toolResult.llm.pct }}%)
 </div>
 <ul v-if="store.toolResult.llm.reasons?.length" class="list-disc list-inside space-y-0.5 text-xs text-ink-600 dark:text-ink-300">
 <li v-for="(r, i) in store.toolResult.llm.reasons" :key="i">{{ r }}</li>
 </ul>
 <div v-if="store.toolResult.llm.suggestions?.length" class="mt-2">
 <div class="text-xs font-semibold text-ink-700 dark:text-ink-200 mb-1">Suggestions:</div>
 <ul class="list-disc list-inside space-y-0.5 text-xs text-ink-600 dark:text-ink-300">
 <li v-for="(s, i) in store.toolResult.llm.suggestions" :key="i">{{ s }}</li>
 </ul>
 </div>
 </div>
 </div>

 <!-- Plain output (paraphrase, translate, humanizer, summarize) -->
 <div v-else-if="store.outputText" class="whitespace-pre-wrap">{{ store.outputText }}</div>

 <!-- Fallback -->
 <span v-else-if="!store.isProcessing && store.toolResult" class="text-ink-500 dark:text-ink-300">Done — see the report above.</span>
 </div>
 </div>
 </div>
 </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted } from 'vue'
import { useToolsStore } from '../stores/tools.ts'
import ToolGauge from './ToolGauge.vue'

const store = useToolsStore()
const inputTextarea = ref<HTMLTextAreaElement | null>(null)

const wordCount = computed(() => {
 const text = store.inputText.trim()
 if (!text) return 0
 return text.split(/\s+/).length
})

const processingLabel = computed(() => {
 const id = store.activeTool?.id
 if (id === 'detector') return 'Analyzing text…'
 if (id === 'plagiarism') return 'Scanning…'
 if (id === 'translate') return 'Translating…'
 if (id === 'summarize') return 'Summarizing…'
 if (id === 'grammar') return 'Checking grammar…'
 if (id === 'paraphrase') return 'Rewriting…'
 if (id === 'humanizer') return 'Humanizing…'
 return 'Processing…'
})

function autoResizeTextarea() {
 nextTick(() => {
 const el = inputTextarea.value
 if (!el) return
 el.style.height = 'auto'
 el.style.height = el.scrollHeight + 'px'
 })
}

function onInput(e: Event) {
 const target = e.target as HTMLTextAreaElement
 store.inputText = target.value
 autoResizeTextarea()
}

watch(() => store.inputText, () => {
 autoResizeTextarea()
})

watch(() => store.activeTool, () => {
 nextTick(() => autoResizeTextarea())
})

onMounted(() => {
 autoResizeTextarea()
})

// ── Translator: swap languages ──────────────────────────────────────────────

function swapLanguages() {
 const src = store.selectedSource
 const tgt = store.selectedOption
 store.selectedSource = tgt
 store.selectedOption = src
 // Also swap input/output text
 const inp = store.inputText
 const out = store.outputText
 if (out) {
 store.inputText = out
 store.outputText = inp
 } else {
 // No output yet — clear input so user re-types with correct source
 store.inputText = ''
 }
 store.error = null
}

const engines = [
 { value: 'ai', label: 'AI (Smart)' },
 { value: 'google', label: 'Google (Free)' },
 { value: 'mymemory', label: 'MyMemory (Free)' },
]

// Normalize engine options: backend returns strings, fallback has {value,label}
const engineOptions = computed(() => {
 const cfg = store.translatorConfig?.engines
 if (!cfg || !cfg.length) return engines
 return cfg.map((e: string | {value: string; label: string}) =>
  typeof e === 'string' ? { value: e, label: e } : e
 )
})

// Normalize domain options: backend returns strings
const domainOptions = computed(() => {
 const cfg = store.translatorConfig?.domains
 if (!cfg || !cfg.length) return ['general', 'academic', 'technical', 'casual', 'legal', 'medical']
 return cfg.map((d: string) => (typeof d === 'string' ? d : d))
})

function copyOutput() {
 if (!store.outputText) return
 navigator.clipboard.writeText(store.outputText).catch(() => {
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
 // First escape HTML, then apply diff markers
 const escaped = text
 .replace(/&/g, '&amp;')
 .replace(/</g, '&lt;')
 .replace(/>/g, '&gt;')
 return escaped
 .replace(/&lt;add&gt;(.*?)&lt;\/add&gt;/g, '<span class="bg-emerald-200/30 dark:bg-emerald-800/30 rounded px-0.5">$1</span>')
 .replace(/&lt;del&gt;(.*?)&lt;\/del&gt;/g, '<span class="bg-red-200/30 dark:bg-red-800/30 line-through rounded px-0.5">$1</span>')
}

// ── Detector helpers ────────────────────────────────────────────────────────

const detectorColor = computed(() => {
 const pct = store.toolResult?.pct || 0
 if (pct >= 75) return '#dc2626'
 if (pct >= 55) return '#f59e0b'
 if (pct >= 35) return '#eab308'
 return '#2f9d6e'
})

const detectorSubtitle = computed(() => {
 const pct = store.toolResult?.pct || 0
 if (pct >= 75) return 'Teks sangat mirip dengan output AI. Pertimbangkan humanizer.'
 if (pct >= 55) return 'Ada indikasi teks dihasilkan AI. Review bagian yang di-highlight.'
 if (pct >= 35) return 'Beberapa pola AI terdeteksi. Kemungkinan campuran manusia + AI.'
 return 'Teks terlihat alami dan ditulis oleh manusia.'
})

function sentenceClass(sent: { severity: string }) {
 const s = sent.severity
 if (s === 'high') return 'border-red-400 bg-red-50/60 dark:bg-red-900/20 hover:bg-red-50 dark:hover:bg-red-900/30'
 if (s === 'moderate') return 'border-amber-400 bg-amber-50/60 dark:bg-amber-900/20 hover:bg-amber-50 dark:hover:bg-amber-900/30'
 if (s === 'low') return 'border-blue-400 bg-blue-50/60 dark:bg-blue-900/20 hover:bg-blue-50 dark:hover:bg-blue-900/30'
 return 'border-ink-200 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 hover:bg-cream-100 dark:hover:bg-ash-700'
}

function engineBarColor(score: number) {
 if (score >= 70) return '#dc2626'
 if (score >= 50) return '#f59e0b'
 if (score >= 30) return '#eab308'
 return '#2f9d6e'
}
</script>
