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
      <div v-if="store.activeTool?.id === 'translate'" class="flex flex-wrap items-center gap-2">
        <!-- Source Language -->
        <select
          v-model="selectedSource"
          class="px-2.5 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
        >
          <option v-for="lang in sourceLanguages" :key="lang" :value="lang">{{ lang }}</option>
        </select>

        <span class="text-ink-500 dark:text-ink-300 text-sm">→</span>

        <!-- Target Language -->
        <select
          v-model="store.selectedOption"
          class="px-2.5 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
        >
          <option v-for="lang in targetLanguages" :key="lang" :value="lang">{{ lang }}</option>
        </select>

        <!-- Advanced toggle -->
        <button
          @click="showAdvanced = !showAdvanced"
          class="px-2.5 py-2 rounded-md text-xs font-medium border border-cream-300 dark:border-ash-600 bg-cream-100 dark:bg-ash-700 text-ink-700 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-ash-600 transition-colors"
        >
          {{ showAdvanced ? 'Hide' : 'Advanced' }}
        </button>

        <!-- Advanced options -->
        <div v-if="showAdvanced" class="flex items-center gap-2 w-full mt-1">
          <!-- Engine selector -->
          <select
            v-model="selectedEngine"
            class="px-2.5 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
          >
            <option v-for="eng in engines" :key="eng.value" :value="eng.value">{{ eng.label }}</option>
          </select>

          <!-- Domain selector -->
          <select
            v-model="selectedDomain"
            class="px-2.5 py-2 border border-cream-300 dark:border-ash-600 rounded-md text-xs bg-white dark:bg-ash-800 text-ink-900 dark:text-ink-50 outline-none focus:border-navy-500 dark:focus:border-cream-400 focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
          >
            <option v-for="dom in domains" :key="dom.value" :value="dom.value">{{ dom.label }}</option>
          </select>
        </div>
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

      <!-- Plagiarism options -->
      <div v-if="store.activeTool?.id === 'plagiarism'" class="inline-flex gap-1 bg-cream-100 dark:bg-ash-700 rounded-md p-0.5">
        <button
          v-for="opt in ['AI Check', 'Web Search', 'Offline', 'Full Scan']"
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

      <!-- Grammar (LLM) options -->
      <div v-else-if="store.activeTool?.id === 'grammar'" class="flex flex-wrap gap-2">
        <button v-for="opt in ['Standard','Grammar','Spelling','Style','Clarity','Academic','Indonesian']" :key="opt"
          @click="store.selectedOption = opt"
          :class="['px-3 py-1 rounded-full text-xs font-medium border transition',
                   store.selectedOption === opt ? 'bg-navy-600 text-white border-navy-600' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-600 hover:border-navy-500']">
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
            <span v-if="store.activeTool?.id === 'plagiarism'" class="block mt-1 text-xs">Select mode: AI Check, Web Search, Offline, or Full Scan.</span>
          </span>
          <!-- Output text with diff highlighting for grammar -->
          <span v-else-if="store.activeTool?.id === 'grammar'" v-html="renderGrammarOutput(store.outputText)"></span>
          <!-- Citation output (monospace) -->
          <!-- Plagiarism report: highlighted sentences + sources -->
          <div v-else-if="store.activeTool?.id === 'plagiarism' && store.toolResult" class="space-y-3">
            <!-- Breakdown (Full Scan) -->
            <div v-if="store.toolResult.breakdown" class="flex gap-2 text-xs text-ink-600 dark:text-ink-300 mb-2">
              <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">Offline: {{ store.toolResult.breakdown.offline_pct }}%</span>
              <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">Web: {{ store.toolResult.breakdown.web_pct }}%</span>
              <span class="px-2 py-0.5 rounded bg-cream-200 dark:bg-ash-600">AI: {{ store.toolResult.breakdown.ai_pct }}%</span>
            </div>
            <!-- Reasons -->
            <div v-if="store.toolResult.reasons?.length" class="text-xs">
              <div class="font-semibold text-ink-700 dark:text-ink-200 mb-1">Findings:</div>
              <ul class="list-disc list-inside space-y-0.5 text-ink-600 dark:text-ink-300">
                <li v-for="(r, i) in store.toolResult.reasons" :key="i">{{ r }}</li>
              </ul>
            </div>
            <!-- Highlighted sentences -->
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
                  <div class="text-ink-500 dark:text-ink-400 mt-0.5">{{ h.issue }}<span v-if="h.note"> — {{ h.note }}</span></div>
                </li>
              </ul>
            </div>
            <!-- Sources -->
            <div v-if="store.toolResult.sources?.length" class="text-xs">
              <div class="font-semibold text-ink-700 dark:text-ink-200 mb-1">Potential sources:</div>
              <ul class="space-y-1">
                <li v-for="(s, i) in store.toolResult.sources" :key="i" class="text-ink-600 dark:text-ink-300">
                  <a :href="s.url" target="_blank" rel="noopener" class="text-navy-600 dark:text-cream-300 underline hover:no-underline">{{ s.title || s.url }}</a>
                  <span v-if="s.match_pct" class="ml-1 text-red-500 font-medium">{{ s.match_pct }}% match</span>
                </li>
              </ul>
            </div>
            <!-- Suggestions -->
            <div v-if="store.toolResult.suggestions?.length" class="text-xs">
              <div class="font-semibold text-ink-700 dark:text-ink-200 mb-1">Suggestions:</div>
              <ul class="list-disc list-inside space-y-0.5 text-ink-600 dark:text-ink-300">
                <li v-for="(s, i) in store.toolResult.suggestions" :key="i">{{ s }}</li>
              </ul>
            </div>
          </div>
          <!-- Plain output -->
          <span v-else-if="store.activeTool?.id !== 'plagiarism' && store.outputText" v-html="store.outputText"></span>
          <!-- Fallback -->
          <span v-else class="text-ink-500 dark:text-ink-300">Done — see the report above.</span>
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

const allLanguages = [
  'Afrikaans', 'Albanian', 'Amharic', 'Arabic', 'Armenian', 'Azerbaijani',
  'Basque', 'Belarusian', 'Bengali', 'Bosnian', 'Bulgarian', 'Burmese',
  'Catalan', 'Cebuano', 'Chinese (Simplified)', 'Chinese (Traditional)',
  'Corsican', 'Croatian', 'Czech', 'Danish', 'Dutch', 'English', 'Esperanto',
  'Estonian', 'Finnish', 'French', 'Frisian', 'Galician', 'Georgian',
  'German', 'Greek', 'Gujarati', 'Haitian Creole', 'Hausa', 'Hawaiian',
  'Hebrew', 'Hindi', 'Hmong', 'Hungarian', 'Icelandic', 'Igbo', 'Indonesian',
  'Irish', 'Italian', 'Japanese', 'Javanese', 'Kannada', 'Kazakh', 'Khmer',
  'Kinyarwanda', 'Korean', 'Kurdish', 'Kyrgyz', 'Lao', 'Latin', 'Latvian',
  'Lithuanian', 'Luxembourgish', 'Macedonian', 'Malagasy', 'Malay',
  'Malayalam', 'Maltese', 'Maori', 'Marathi', 'Mongolian', 'Nepali',
  'Norwegian', 'Nyanja', 'Odia', 'Pashto', 'Persian', 'Polish', 'Portuguese',
  'Punjabi', 'Romanian', 'Russian', 'Samoan', 'Scots Gaelic', 'Serbian',
  'Sesotho', 'Shona', 'Sindhi', 'Sinhala', 'Slovak', 'Slovenian', 'Somali',
  'Spanish', 'Sundanese', 'Swahili', 'Swedish', 'Tagalog', 'Tajik', 'Tamil',
  'Tatar', 'Telugu', 'Thai', 'Turkish', 'Turkmen', 'Ukrainian', 'Urdu',
  'Uyghur', 'Uzbek', 'Vietnamese', 'Welsh', 'Xhosa', 'Yiddish', 'Yoruba',
  'Zulu'
]

const sourceLanguages = ['Auto (Detect)', ...allLanguages]
const targetLanguages = allLanguages

const engines = [
  { value: 'ai', label: 'AI (Smart)' },
  { value: 'google', label: 'Google (Free)' },
  { value: 'mymemory', label: 'MyMemory (Free)' },
  { value: 'deepl', label: 'DeepL' },
  { value: 'libre', label: 'LibreTranslate' },
  { value: 'argos', label: 'Argos (Offline)' }
]

const domains = [
  { value: 'general', label: 'General' },
  { value: 'academic', label: 'Academic' },
  { value: 'technical', label: 'Technical' },
  { value: 'casual', label: 'Casual' },
  { value: 'legal', label: 'Legal' },
  { value: 'medical', label: 'Medical' }
]

const selectedSource = computed({
  get: () => store.selectedSource,
  set: (v) => { store.selectedSource = v }
})
const selectedEngine = computed({
  get: () => store.selectedEngine,
  set: (v) => { store.selectedEngine = v }
})
const selectedDomain = computed({
  get: () => store.selectedDomain,
  set: (v) => { store.selectedDomain = v }
})
const showAdvanced = ref(false)

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
  return text
    .replace(/<add>(.*?)<\/add>/g, '<span class="bg-emerald-200/30 dark:bg-emerald-800/30 rounded px-0.5">$1</span>')
    .replace(/<del>(.*?)<\/del>/g, '<span class="bg-red-200/30 dark:bg-red-800/30 line-through rounded px-0.5">$1</span>')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
</script>
