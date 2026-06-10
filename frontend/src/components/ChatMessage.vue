<template>
  <div
    v-if="shouldRenderMessage"
    :class="['flex gap-3', message.role === 'user' ? 'justify-end' : 'justify-start']"
  >
    <!-- AI Avatar -->
    <div v-if="message.role === 'assistant'" class="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-br from-navy-400 to-navy-600 dark:from-cream-300 dark:to-cream-400 flex items-center justify-center mt-1 shadow-sm">
      <svg class="w-4 h-4 text-cream-50 dark:text-ash-900" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/>
      </svg>
    </div>

    <!-- Message Content -->
    <div :class="['max-w-[80%] rounded-2xl px-4 py-3', messageClasses]">
      <!-- Thinking Block -->
      <ThinkingBlock
        v-if="message.thinking"
        :content="message.thinking"
        :is-streaming="isStreaming && !message.content"
      />

      <!-- Full-paper generation progress (in-chat). The AI's GenerateFullPaper
           tool call kicks off a long backend job; instead of an overlay, we
           show this animated progress block right inside the chat bubble. -->
      <div
        v-if="generatingPaper"
        class="mb-3 p-4 rounded-xl border border-navy-300 dark:border-cream-600 bg-gradient-to-r from-cream-50 to-navy-50 dark:from-ash-700 dark:to-ash-800"
      >
        <div class="flex items-center gap-3">
          <div class="relative w-10 h-10 shrink-0">
            <div class="absolute inset-0 rounded-full border-2 border-cream-300 dark:border-ash-600"></div>
            <div class="absolute inset-0 rounded-full border-2 border-t-navy-600 dark:border-t-cream-200 animate-spin"></div>
            <div class="absolute inset-0 flex items-center justify-center text-base">📝</div>
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-semibold text-ink-900 dark:text-ink-50">AI sedang menulis paper lengkap</div>
            <div class="text-xs text-ink-700 dark:text-ink-300 mt-0.5">Proses ini biasanya 3-10 menit. Editor akan auto-load hasilnya.</div>
            <div class="mt-2 h-1 rounded-full bg-cream-200 dark:bg-ash-600 overflow-hidden">
              <div class="h-full w-1/3 rounded-full bg-gradient-to-r from-navy-400 to-navy-600 dark:from-cream-300 dark:to-cream-400 animate-progress-slide"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Text Content -->
      <div
        v-if="visibleContent"
        class="prose prose-sm max-w-none break-words"
        v-html="renderedContent"
      ></div>

      <!-- Multi-choice options are now handled exclusively by MultiQuestionCard
           via the AskQuestions tool. No inline parsing needed. -->

      <!-- Structured chips proposed by ProposeChips tool (kind=chips). -->
      <ActionChips
        v-if="metaKind === 'chips' && metaChips.length && message.role === 'assistant'"
        :chips="metaChips"
        @select="(v) => $emit('chip-select', v)"
      />

      <!-- Inline paper-generation progress bubble (kind=paper_progress).
           PaperProgressBubble is owned by Agent G; if missing, the async
           component falls back to a small TODO placeholder. -->
      <PaperProgressBubble
        v-if="metaKind === 'paper_progress' && metaJobId && message.role === 'assistant'"
        :job-id="metaJobId"
        :paper-id="currentPaperId"
        class="mt-2"
      />

      <!-- Inline revisi proposal card (kind=propose_revisi). Shown when an AI
           Paraphrase / FixGrammar / Translate tool returns a rewrite payload.
           User can accept (apply via paper store) or reject the change. -->
      <RevisiProposalCard
        v-if="metaKind === 'propose_revisi' && message.role === 'assistant'"
        :proposal="message.metadata"
        @accepted="$emit('revisi-accepted', $event)"
        @rejected="$emit('revisi-rejected', $event)"
      />

      <!-- Inline chart preview (kind=chart_proposal). Backend tool renders the
           chart server-side and returns a URL + spec; the user can accept it
           into the paper or ask for a regenerate. -->
      <ChartPreviewCard
        v-if="metaKind === 'chart_proposal' && message.role === 'assistant'"
        :url="message.metadata?.url"
        :spec="message.metadata?.spec"
        :image-id="message.metadata?.image_id"
        :title="message.metadata?.title"
        @accept="$emit('chart-accept', { ...message.metadata, ...$event })"
        @regenerate="$emit('chart-regenerate', { ...message.metadata, ...$event })"
      />

      <!-- Inline long-file review (kind=file_review). Used when an attached
           file is too big to inject in full; user picks which slice/kind to
           pull into context. -->
      <FileReviewCard
        v-if="metaKind === 'file_review' && message.role === 'assistant'"
        :filename="message.metadata.filename"
        :word-count="message.metadata.word_count || 0"
        :head="message.metadata.head"
        :tail="message.metadata.tail"
        :suggested-kinds="message.metadata.suggested_kinds"
        :file-id="message.metadata.file_id"
        @pick="$emit('file-review-pick', { ...message.metadata, ...$event })"
      />

      <!-- Multi-question card (kind=multi_question). Renders 1-5 questions
           with chip options + free-text fallback. Submits a single grouped
           user message via submitMultiQuestionAnswers. -->
      <MultiQuestionCard
        v-if="metaKind === 'multi_question' && message.role === 'assistant' && (message.metadata.questions || []).length"
        :questions="message.metadata.questions"
        @multi-question-submit="$emit('multi-question-submit', $event)"
      />

      <!-- Review plan notice (kind=review_plan). Visual-only banner that the
           AI is starting a multi-step review pass over the paper. -->
      <div
        v-if="metaKind === 'review_plan' && message.role === 'assistant'"
        class="my-2 p-3 rounded-lg border border-navy-300 dark:border-navy-600 bg-navy-50 dark:bg-navy-900/20"
      >
        <div class="flex items-start gap-2">
          <span class="text-base leading-none mt-0.5">🔍</span>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-navy-800 dark:text-navy-100">
              Memulai review menyeluruh
            </div>
            <div
              v-if="message.metadata.directive"
              class="text-xs text-navy-700 dark:text-navy-200 mt-0.5 break-words"
            >
              {{ message.metadata.directive }}
            </div>
            <div
              v-if="message.metadata.scope"
              class="text-[10px] uppercase tracking-wide text-navy-600 dark:text-navy-300 mt-1"
            >
              scope: {{ message.metadata.scope }}
            </div>
            <div class="mt-2">
              <button
                type="button"
                @click="$emit('review-cancel', message.metadata)"
                class="px-3 py-1 rounded-full text-xs font-medium border
                       bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
                       border-cream-300 dark:border-ash-600
                       text-ink-800 dark:text-ink-100"
              >
                Batalkan
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Data revision notice (kind=revise_data). Small banner showing the
           AI plans to revise data in Section 4 (Results). Visual-only. -->
      <div
        v-if="metaKind === 'revise_data' && message.role === 'assistant'"
        class="my-2 p-2.5 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 text-xs text-amber-900 dark:text-amber-100"
      >
        <span class="font-medium">📊 Revisi data Section 4:</span>
        <span class="ml-1 break-words">{{ message.metadata.directive || '(tanpa keterangan)' }}</span>
      </div>


      <!-- Inline validation banner (kind=validation_error). Shown when a
           tool refuses to run (e.g. NEED_MORE_LITERATURE) and offers a
           one-click recovery action. -->
      <div
        v-if="metaKind === 'validation_error' && message.role === 'assistant'"
        class="my-2 p-3 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20"
      >
        <div class="flex items-start gap-2">
          <span class="text-base leading-none mt-0.5">⚠️</span>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-amber-900 dark:text-amber-100">
              {{ message.metadata.message || 'Tidak bisa lanjut.' }}
            </div>
            <div
              v-if="message.metadata.hint"
              class="text-xs text-amber-800 dark:text-amber-200 mt-0.5"
            >
              {{ message.metadata.hint }}
            </div>
            <div
              v-if="message.metadata.error_code"
              class="text-[10px] uppercase tracking-wide text-amber-700 dark:text-amber-300 mt-1"
            >
              {{ message.metadata.error_code }}
            </div>
            <div class="flex flex-wrap gap-2 mt-2">
              <button
                v-if="message.metadata.error_code === 'NEED_MORE_LITERATURE'"
                type="button"
                @click="$emit('chip-select', 'Jalankan SLR untuk mencari literatur tambahan.')"
                class="px-3 py-1.5 rounded-full text-xs font-medium border
                       bg-amber-100 hover:bg-amber-200 dark:bg-amber-800/40 dark:hover:bg-amber-800/60
                       border-amber-300 dark:border-amber-700
                       text-amber-900 dark:text-amber-100"
              >
                Jalankan SLR
              </button>
              <button
                v-if="message.metadata.retry_prompt"
                type="button"
                @click="$emit('chip-select', message.metadata.retry_prompt)"
             class="px-3 py-1.5 rounded-full text-xs font-medium border
                    bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
                    border-cream-300 dark:border-ash-600
                    text-ink-800 dark:text-ink-100 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30"
              >
                Coba lagi
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Inline image-prompt review (kind=image_prompt_review). Posted by
           the paperJobs hook when a full-paper job finishes; lists each
           figure prompt with quick actions. -->
      <div
        v-if="metaKind === 'image_prompt_review' && message.role === 'assistant'"
        class="my-2 p-3 rounded-lg border border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-800"
      >
        <div class="flex items-center gap-2 mb-2">
          <span class="text-base">🖼️</span>
          <span class="text-sm font-medium text-ink-800 dark:text-ink-100">
            Review prompt gambar ({{ (message.metadata.images || []).length }})
          </span>
        </div>
        <ol class="space-y-2 text-xs text-ink-800 dark:text-ink-100">
          <li
            v-for="(im, i) in (message.metadata.images || [])"
            :key="i"
            class="rounded border border-cream-300 dark:border-ash-700 p-2 bg-cream-100 dark:bg-ash-900"
          >
            <div class="font-medium">Fig. {{ i + 1 }} — {{ im.title || 'Untitled' }}</div>
            <div class="opacity-80 mt-0.5 whitespace-pre-wrap break-words">{{ im.prompt }}</div>
          </li>
        </ol>
        <div class="flex flex-wrap gap-2 mt-3">
          <button
            type="button"
            @click="$emit('chip-select', 'Generate semua prompt gambar di paper sekarang.')"
           class="px-3 py-1.5 rounded-full text-xs font-medium
                  bg-navy-600 hover:bg-navy-700 text-cream-50
                  dark:bg-cream-300 dark:hover:bg-cream-200 dark:text-ink-900 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30"
          >Generate semua</button>
          <button
            type="button"
            @click="$emit('chip-select', 'Tolong bantu edit prompt gambar dulu sebelum generate.')"
            class="px-3 py-1.5 rounded-full text-xs font-medium border
                   bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
                   border-cream-300 dark:border-ash-600
                   text-ink-800 dark:text-ink-100"
          >Edit prompt dulu</button>
          <button
            type="button"
            @click="$emit('chip-select', 'Skip generate gambar untuk sekarang.')"
            class="px-3 py-1.5 rounded-full text-xs font-medium border
                   bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
                   border-cream-300 dark:border-ash-600
                   text-ink-800 dark:text-ink-100"
          >Skip</button>
        </div>
      </div>

      <!-- Tool call errors (only show errors, hidden by default) -->
      <div
        v-if="errorToolCalls.length && message.role === 'assistant'"
        class="mt-3 space-y-2"
      >
        <div
          v-for="(tc, idx) in errorToolCalls"
          :key="idx"
          class="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 overflow-hidden"
        >
          <div class="px-3 py-2 flex items-center gap-2 bg-red-100 dark:bg-red-900/30 border-b border-red-200 dark:border-red-800">
            <span class="w-2 h-2 rounded-full bg-red-500"></span>
            <span class="text-xs font-medium text-red-900 dark:text-red-200">Tool Error: {{ tc.name }}</span>
          </div>
          <div class="px-3 py-2">
            <button
              @click="toggleToolError(idx)"
              class="flex items-center gap-1.5 text-xs text-red-700 dark:text-red-300 hover:text-red-900 dark:hover:text-red-100 font-medium"
            >
              <svg
                :class="['w-3 h-3 transition-transform', toolErrorsOpen[idx] ? 'rotate-90' : '']"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path d="M6 4l8 6-8 6V4z"/>
              </svg>
              Show Details
            </button>
            <div v-show="toolErrorsOpen[idx]" class="mt-2 space-y-2">
              <div v-if="tc.error" class="text-xs text-red-800 dark:text-red-200 bg-white dark:bg-red-950/30 rounded p-2 border border-red-200 dark:border-red-800">
                <div class="font-medium mb-1">Error:</div>
                <pre class="whitespace-pre-wrap break-words font-mono text-[11px]">{{ tc.error }}</pre>
              </div>
              <div v-if="tc.result" class="text-xs text-red-800 dark:text-red-200 bg-white dark:bg-red-950/30 rounded p-2 border border-red-200 dark:border-red-800">
                <div class="font-medium mb-1">Result:</div>
                <pre class="whitespace-pre-wrap break-words font-mono text-[11px]">{{ tc.result }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>


    </div>

    <!-- User Avatar -->
    <div v-if="message.role === 'user'" class="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-br from-cream-500 to-navy-500 flex items-center justify-center mt-1 shadow-sm">
      <svg class="w-4 h-4 text-cream-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, defineAsyncComponent } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js/lib/core'
import { useSanitize } from '../composables/useSanitize'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import ThinkingBlock from './ThinkingBlock.vue'
import ActionChips from './ActionChips.vue'
import RevisiProposalCard from './RevisiProposalCard.vue'
import ChartPreviewCard from './ChartPreviewCard.vue'
import FileReviewCard from './FileReviewCard.vue'
import MultiQuestionCard from './MultiQuestionCard.vue'
import { usePaperStore } from '../stores/paper'

interface ToolCall {
  name: string
  status?: string
  error?: string
  result?: string
  arguments?: any
}

interface MessageMetadata {
  kind?: string
  chips?: any[]
  job_id?: string
  error_code?: string
  retry_prompt?: string
  images?: Array<{ title?: string; prompt: string }>
  [key: string]: any
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content?: string
  thinking?: string
  tool_calls?: ToolCall[]
  metadata?: MessageMetadata
}

interface Props {
  message: ChatMessage
  isStreaming?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isStreaming: false
})

interface Emits {
  (e: 'pick-option', text: string): void
  (e: 'chip-select', value: string): void
  (e: 'revisi-accepted', event: any): void
  (e: 'revisi-rejected', event: any): void
  (e: 'chart-accept', data: any): void
  (e: 'chart-regenerate', data: any): void
  (e: 'file-review-pick', value: any): void
  (e: 'multi-question-submit', value: any): void
  (e: 'review-cancel'): void
}

defineEmits<Emits>()

const paperStore = usePaperStore()
const currentPaperId = computed(() => paperStore.currentPaperId || '')
const { sanitizeHtml } = useSanitize()

const PaperProgressBubble = defineAsyncComponent({
  loader: () => import('./PaperProgressBubble.vue'),
  loadingComponent: {
    template: `
      <div class="mt-2 p-3 rounded-lg border border-cream-300 dark:border-ash-700 bg-cream-50 dark:bg-ash-800 text-xs">
        <div class="flex items-center gap-2">
          <div class="w-4 h-4 border-2 border-ink-300 dark:border-ink-500 border-t-transparent rounded-full animate-spin"></div>
          <span class="text-ink-700 dark:text-ink-200">Memuat progress…</span>
        </div>
      </div>
    `,
  },
  errorComponent: {
    props: ['jobId'],
    template: `
      <div class="mt-2 p-3 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 text-xs text-amber-900 dark:text-amber-200">
        <div class="font-medium">📝 Generate paper started</div>
        <div class="opacity-80 mt-0.5">Job <code class="font-mono">{{ jobId }}</code> sedang berjalan. Bubble progress sedang dimuat…</div>
      </div>
    `,
  },
  delay: 200,
  timeout: 8000,
})

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('css', css)

const toolErrorsOpen = ref<Record<number, boolean>>({})

const errorToolCalls = computed(() => {
  const calls = props.message.tool_calls || []
  return calls.filter(tc => tc.status === 'error' || tc.error)
})

function toggleToolError(idx: number): void {
  toolErrorsOpen.value[idx] = !toolErrorsOpen.value[idx]
}

const metaKind = computed(() => props.message?.metadata?.kind || null)
const metaChips = computed(() => {
  const c = props.message?.metadata?.chips
  return Array.isArray(c) ? c : []
})
const metaJobId = computed(() => props.message?.metadata?.job_id || null)

const generatingPaper = computed(() => {
  const tc = (props.message.tool_calls || []).find(
    tc => tc.name === 'GenerateFullPaper'
  )
  if (!tc) return false

  if (tc.status !== 'done') return false

  try {
    const result = tc.result || ''
    if (result.startsWith('<<PROPOSAL>>')) {
      const jsonStr = result.substring('<<PROPOSAL>>'.length)
      const payload = JSON.parse(jsonStr)
      return payload.kind === 'generate_full' && !!payload.job_id
    }
  } catch (e) {
    return false
  }

  return false
})

// Leaked control-token scrubber (mirrors backend _scrub_control_tokens).
// Some chat templates (DeepSeek/DSML-style) occasionally emit their tool-call /
// role control tokens into the content stream. The backend strips these on new
// turns, but messages persisted before that fix still carry them, so we also
// scrub at render time. Fullwidth pipes (U+FF5C) never appear in real prose.
const LEAKED_TOKENS = [
  '<｜DSML｜function_calls',
  '<｜DSML｜function▁calls',
  '<|DSML|function_calls',
  '<｜tool▁calls▁begin｜>',
  '<｜tool▁call▁begin｜>',
  '<｜tool▁calls▁end｜>',
  '<｜tool▁call▁end｜>',
  '<｜tool▁sep｜>',
  '<｜tool▁outputs▁begin｜>',
  '<｜tool▁output▁begin｜>',
  '<｜tool▁outputs▁end｜>',
  '<｜tool▁output▁end｜>',
  '<｜begin▁of▁sentence｜>',
  '<｜end▁of▁sentence｜>',
  '<｜User｜>',
  '<｜Assistant｜>',
  '<｜System｜>',
]
const CTRL_CLOSED_RE = /<[｜|][^<>]{0,40}?[｜|]>/g

function scrubControlTokens(text: string): string {
  if (!text) return text
  let out = text
  for (const tok of LEAKED_TOKENS) {
    if (out.includes(tok)) out = out.split(tok).join('')
  }
  if (out.includes('<｜') || out.includes('<|')) {
    out = out.replace(CTRL_CLOSED_RE, '')
  }
  return out
}

const visibleContent = computed(() => {
  return scrubControlTokens(props.message.content || '').trim()
})

const messageClasses = computed(() => {
  if (props.message.role === 'user') {
    return 'chat-bubble-user'
  }
  return 'chat-bubble-ai'
})

marked.setOptions({
  highlight(code: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value
    }
    return hljs.highlightAuto(code).value
  },
  breaks: true,
  gfm: true,
})

const renderedContent = computed(() => {
  if (!visibleContent.value) return ''
  try {
    const raw = marked.parse(visibleContent.value) as string
    return sanitizeHtml(raw, { USE_PROFILES: { html: true } })
  } catch {
    return sanitizeHtml(visibleContent.value, { USE_PROFILES: { html: true } })
  }
})

const shouldRenderMessage = computed(() => {
  if (props.message.role === 'user') return true
  if (visibleContent.value) return true
  if ((props.message.thinking || '').trim()) return true
  if (generatingPaper.value) return true
  if (metaKind.value) return true
  if (errorToolCalls.value.length > 0) return true
  return false
})
</script>

<style scoped>
/* In-chat full-paper-generation progress shimmer. */
@keyframes progress-slide {
  0% { transform: translateX(-100%); }
  50% { transform: translateX(150%); }
  100% { transform: translateX(-100%); }
}
.animate-progress-slide {
  animation: progress-slide 2.4s ease-in-out infinite;
}

/* Chat bubble theming via CSS tokens — single source of truth.
   rofiq.txt #1: user box putih di light, dark anthracite di dark. */
.chat-bubble-user {
  background: var(--surface-user);
  color: var(--surface-user-text);
  border: 1px solid var(--border-strong);
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.chat-bubble-ai {
  background: var(--surface-ai);
  color: var(--text-strong);
  border: 1px solid var(--border-soft);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

.prose :deep(pre) {
  background: #1e1e2e;
  border-radius: 0.75rem;
  padding: 1rem;
  overflow-x: auto;
  margin: 0.75rem 0;
}

.prose :deep(pre code) {
  color: #cdd6f4;
  font-size: 0.8rem;
  line-height: 1.5;
}

.prose :deep(code:not(pre code)) {
  background: #f1e7d8;
  padding: 0.15rem 0.4rem;
  border-radius: 0.375rem;
  font-size: 0.8rem;
  color: #5b3d20;
}
.dark .prose :deep(code:not(pre code)) {
  background: #2a2825;
  color: #eddbac;
}

.prose-invert :deep(code:not(pre code)) {
  background: rgba(253, 250, 243, 0.2);
  color: #f5ead0;
}

.prose :deep(p) { margin: 0.5rem 0; }
.prose :deep(p:first-child) { margin-top: 0; }
.prose :deep(p:last-child) { margin-bottom: 0; }

.prose :deep(ul), .prose :deep(ol) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.prose :deep(li) { margin: 0.25rem 0; }

.prose :deep(h1), .prose :deep(h2), .prose :deep(h3) {
  margin: 0.75rem 0 0.5rem;
  font-weight: 600;
}

.prose :deep(blockquote) {
  border-left: 3px solid #79522a;
  padding-left: 0.75rem;
  margin: 0.5rem 0;
  color: #5b3d20;
}
.dark .prose :deep(blockquote) {
  border-left-color: #cca97f;
  color: #cbc7ba;
}

.prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75rem 0;
  font-size: 0.8rem;
}

.prose :deep(th), .prose :deep(td) {
  border: 1px solid #cca97f;
  padding: 0.4rem 0.6rem;
}
.dark .prose :deep(th),
.dark .prose :deep(td) {
  border-color: #3f3c35;
}

.prose :deep(th) {
  background: #fbf5e9;
  font-weight: 600;
}
.dark .prose :deep(th) {
  background: #2a2825;
  color: #f5f3ee;
}

.dark .prose :deep(td) {
  color: #f5f3ee;
}

.prose :deep(a) {
  color: #79522a;
  text-decoration: underline;
}
.dark .prose :deep(a) {
  color: #eddbac;
}

.prose-invert :deep(a) {
  color: #fbf5e9;
}
</style>
