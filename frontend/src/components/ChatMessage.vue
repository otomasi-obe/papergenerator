<template>
  <div :class="['flex gap-3', message.role === 'user' ? 'justify-end' : 'justify-start']">
    <!-- AI Avatar -->
    <div v-if="message.role === 'assistant'" class="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-br from-brown-400 to-brown-600 flex items-center justify-center mt-1 shadow-sm">
      <svg class="w-4 h-4 text-cream-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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

      <!-- Tool Calls -->
      <div v-if="message.tool_calls && message.tool_calls.length > 0" class="space-y-2 mb-3">
        <ToolCallBlock
          v-for="(tc, idx) in message.tool_calls"
          :key="idx"
          :tool-call="tc"
        />
      </div>

      <!-- Text Content -->
      <div
        v-if="visibleContent"
        class="prose prose-sm max-w-none break-words"
        v-html="renderedContent"
      ></div>

      <!-- Multi-choice chips parsed from [OPSI] block in AI message -->
      <div
        v-if="mcOptions.length && message.role === 'assistant' && !isStreaming"
        class="mt-3 flex flex-col gap-1.5"
      >
        <button
          v-for="(opt, i) in mcOptions"
          :key="i"
          @click="$emit('pick-option', opt)"
          class="text-left text-sm px-3 py-2 rounded-xl border border-amber-300 dark:border-amber-700 bg-amber-50 hover:bg-amber-100 dark:bg-amber-900/30 dark:hover:bg-amber-900/50 hover:border-amber-400 dark:hover:border-amber-500 text-amber-900 dark:text-amber-200 transition-colors"
        >
          <span class="inline-block w-5 text-amber-700 dark:text-amber-300 font-semibold">{{ i + 1 }}.</span>
          {{ opt }}
        </button>
        <p class="text-[11px] text-amber-800/70 dark:text-amber-300/70 mt-0.5 px-1">
          Atau ketik jawaban sendiri di kotak input.
        </p>
      </div>

      <!-- Streaming cursor -->
      <span
        v-if="isStreaming && message.role === 'assistant' && !message.content && !message.thinking"
        class="inline-flex items-center gap-1 py-1"
      >
        <span class="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
        <span class="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
        <span class="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
      </span>
    </div>

    <!-- User Avatar -->
    <div v-if="message.role === 'user'" class="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-br from-cream-500 to-brown-500 flex items-center justify-center mt-1 shadow-sm">
      <svg class="w-4 h-4 text-cream-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/>
      </svg>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import ThinkingBlock from './ThinkingBlock.vue'
import ToolCallBlock from './ToolCallBlock.vue'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('css', css)

const props = defineProps({
  message: { type: Object, required: true },
  isStreaming: { type: Boolean, default: false }
})

defineEmits(['pick-option'])

// Strip [OPSI]…[/OPSI] block from the visible content; we render those as
// buttons below. Tolerates close-tag forgotten by the model.
const OPSI_RE = /\[OPSI\]([\s\S]*?)(?:\[\/OPSI\]|$)/i

const visibleContent = computed(() => {
  const c = props.message.content || ''
  return c.replace(OPSI_RE, '').trim()
})

const mcOptions = computed(() => {
  const c = props.message.content || ''
  const m = c.match(OPSI_RE)
  if (!m) return []
  const block = m[1] || ''
  // Accept "1) foo", "1. foo", "- foo", "• foo"
  const lines = block.split('\n')
    .map(l => l.replace(/^\s*(?:\d+[\)\.\:]|[-•*])\s*/, '').trim())
    .filter(Boolean)
  return lines.slice(0, 4)
})

const messageClasses = computed(() => {
  if (props.message.role === 'user') {
    // Light: putih dengan border tegas (rofiq.txt #1: user box harusnya putih saat tema light)
    // Dark: warm dark anthracite, kontras cukup
    return 'chat-bubble-user'
  }
  return 'chat-bubble-ai'
})

marked.setOptions({
  highlight(code, lang) {
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
    const raw = marked.parse(visibleContent.value)
    return DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } })
  } catch {
    return DOMPurify.sanitize(visibleContent.value, { USE_PROFILES: { html: true } })
  }
})
</script>

<style scoped>
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
:deep(html.dark) .prose :deep(code:not(pre code)) {
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
:deep(html.dark) .prose :deep(blockquote) {
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
:deep(html.dark) .prose :deep(th),
:deep(html.dark) .prose :deep(td) {
  border-color: #3f3c35;
}

.prose :deep(th) {
  background: #fbf5e9;
  font-weight: 600;
}
:deep(html.dark) .prose :deep(th) {
  background: #2a2825;
}

.prose :deep(a) {
  color: #79522a;
  text-decoration: underline;
}
:deep(html.dark) .prose :deep(a) {
  color: #eddbac;
}

.prose-invert :deep(a) {
  color: #fbf5e9;
}
</style>
