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
    <div :class="['max-w-[88%] rounded-2xl px-5 py-3.5', messageClasses]">
      <!-- Thinking Block -->
      <ThinkingBlock
        v-if="message.thinking"
        :content="message.thinking"
        :is-streaming="streamPhase === 'thinking' || streamPhase === 'composing'"
        :stream-phase="streamPhase"
      />

      <!-- Search Progress Block: visible during/after websearch phase.
           Shows each fetcher (source type + query) with its status, so the
           user can follow the AI's reference-gathering step between the
           reasoning (thinking) block and the final text answer. -->
      <div
        v-if="searchResults && searchResults.length > 0"
        class="search-progress-block mb-3 rounded-xl border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-800 overflow-hidden"
      >
        <div class="px-4 py-2.5 bg-cream-100 dark:bg-ash-700 border-b border-cream-300 dark:border-ash-600">
          <div class="text-xs font-semibold text-ink-700 dark:text-ink-200 flex items-center gap-2">
            <svg
              v-if="searchRunning"
              class="w-4 h-4 animate-spin text-[var(--accent)]"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
            <span v-else class="text-base leading-none">🌐</span>
            {{ searchMessage || 'Mencari referensi...' }}
          </div>
        </div>
        <div class="px-4 py-2 space-y-1.5">
          <div
            v-for="(search, idx) in searchResults"
            :key="idx"
            class="flex items-center gap-2 text-xs"
          >
            <span class="flex-shrink-0">
              {{ search.status === 'done' ? '✅' : '🔍' }}
            </span>
            <span class="text-ink-500 dark:text-ink-400 font-mono">[{{ idx + 1 }}/{{ searchResults.length }}]</span>
            <span class="font-medium text-ink-800 dark:text-ink-100">{{ search.type }}</span>
            <span class="text-ink-400 dark:text-ink-500 truncate flex-1">{{ search.query }}</span>
            <span v-if="search.status === 'done'" class="text-green-600 dark:text-green-400 font-medium whitespace-nowrap">
              {{ search.count || (search.results?.length) || 0 }} results
            </span>
            <span v-else class="text-[var(--accent)] animate-pulse whitespace-nowrap">searching...</span>
          </div>
        </div>
      </div>

      <!-- Attached Images (user messages only) -->
      <div v-if="message.images && message.images.length" class="mb-3 flex flex-wrap gap-2">
        <div
          v-for="(img, i) in message.images"
          :key="i"
          class="relative rounded-lg overflow-hidden border border-cream-300 dark:border-ash-600 bg-cream-100 dark:bg-ash-700 shadow-sm"
        >
          <img
            :src="img.data.startsWith('data:') ? img.data : `data:image/jpeg;base64,${img.data}`"
            :alt="img.name"
            class="max-w-[200px] max-h-[150px] object-cover"
          />
          <div class="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-[9px] px-1.5 py-0.5 truncate">
            {{ img.name }}
          </div>
        </div>
      </div>

      <!-- Composing indicator: shown BELOW thinking when reasoning is done but content hasn't started -->
      <div
        v-if="streamPhase === 'composing'"
        class="composing-indicator flex items-center gap-2 py-2 text-xs text-ink-500 dark:text-ink-300 mt-1"
      >
        <span class="inline-flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-[var(--accent)]/60 animate-bounce"></span>
          <span class="w-1.5 h-1.5 rounded-full bg-[var(--accent)]/60 animate-bounce" style="animation-delay: 0.15s"></span>
          <span class="w-1.5 h-1.5 rounded-full bg-[var(--accent)]/60 animate-bounce" style="animation-delay: 0.3s"></span>
        </span>
        <span class="font-medium animate-pulse">Menyusun jawaban...</span>
      </div>

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

      <!-- Text Content: RAW during streaming, RENDERED when done.
           NOTE (BUG-29): LaTeX/math is intentionally NOT rendered during
           streaming to avoid flickering from incomplete LaTeX tokens.
           Content renders as plain text with a cursor, then switches to
           full markdown+KaTeX rendering once streaming completes. -->
      <div
        v-if="visibleContent && isActivelyStreaming"
        class="prose prose-sm max-w-none break-words whitespace-pre-wrap text-ink-900 dark:text-ink-100"
      >{{ visibleContent }}<span class="typing-cursor" /></div>
      <div
        v-else-if="visibleContent"
        class="prose prose-sm max-w-none break-words dark:prose-invert dark:text-[color:var(--text-base)]"
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

      <!-- Ask-user card (kind=ask_user). AI asks a question with 4 options
           + free text. User picks or types answer, sends back as message. -->
      <AskUserCard
        v-if="metaKind === 'ask_user' && message.role === 'assistant' && message.metadata.question"
        :question="message.metadata.question"
        :options="message.metadata.options || []"
        @answer="$emit('ask-user-answer', $event)"
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

      <!-- Tool calls: show ALL tools (running + done), not just errors.
           This gives the user real-time visibility into what the AI is doing —
           web searches, reasoning steps, paper generation, etc. -->
      <div
        v-if="allToolCalls.length && message.role === 'assistant'"
        class="mt-2 space-y-1.5"
      >
        <div
          v-for="(tc, idx) in allToolCalls"
          :key="idx"
          :class="[
            'rounded-lg border overflow-hidden text-xs transition-all',
            tc.status === 'running'
              ? 'border-navy-300 dark:border-navy-600 bg-navy-50/50 dark:bg-navy-900/20'
              : tc.status === 'error'
              ? 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20'
              : 'border-cream-300 dark:border-ash-600 bg-cream-50/50 dark:bg-ash-800/50'
          ]"
        >
          <!-- Tool header: icon + name + status -->
          <button
            @click="toggleToolDetail(idx)"
            class="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
          >
            <!-- Status icon -->
            <span v-if="tc.status === 'running'" class="shrink-0 w-4 h-4 border-2 border-navy-400 border-t-navy-700 dark:border-t-cream-300 rounded-full animate-spin"></span>
            <span v-else-if="tc.status === 'done'" class="shrink-0 text-emerald-600 dark:text-emerald-400">✓</span>
            <span v-else-if="tc.status === 'error'" class="shrink-0 text-red-500 dark:text-red-400">✗</span>

            <!-- Tool name + description -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5">
                <span :class="[
                  'font-medium truncate',
                  tc.status === 'running' ? 'text-navy-800 dark:text-navy-200' :
                  tc.status === 'error' ? 'text-red-800 dark:text-red-200' :
                  'text-ink-700 dark:text-ink-200'
                ]">{{ toolLabel(tc.name) }}</span>
                <span v-if="tc.status === 'running'" class="shrink-0 text-[10px] text-navy-600 dark:text-navy-400 font-medium">
                  {{ toolRunningText(tc.name) }}
                </span>
              </div>
              <!-- Tool detail line: query for search, scope for edits, etc. -->
              <div v-if="toolDetail(tc)" class="text-[10px] text-ink-500 dark:text-ink-300 truncate mt-0.5">
                {{ toolDetail(tc) }}
              </div>
            </div>

            <!-- Expand chevron -->
            <svg
              :class="['w-3 h-3 shrink-0 transition-transform text-ink-400', toolDetailsOpen[idx] ? 'rotate-90' : '']"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path d="M6 4l8 6-8 6V4z"/>
            </svg>
          </button>

          <!-- Expandable detail: arguments + result -->
          <div v-show="toolDetailsOpen[idx]" class="px-3 pb-2 space-y-1.5">
            <div v-if="tc.arguments && Object.keys(tc.arguments).length" class="text-ink-600 dark:text-ink-300">
              <div class="font-medium text-[10px] uppercase tracking-wide text-ink-500 dark:text-ink-300 mb-0.5">Arguments</div>
              <pre class="whitespace-pre-wrap break-words font-mono text-[10px] bg-white/50 dark:bg-black/20 rounded p-1.5 max-h-32 overflow-y-auto">{{ formatToolArgs(tc.arguments) }}</pre>
            </div>
            <div v-if="tc.result" class="text-ink-600 dark:text-ink-300">
              <div class="font-medium text-[10px] uppercase tracking-wide text-ink-500 dark:text-ink-300 mb-0.5">Result</div>
              <pre class="whitespace-pre-wrap break-words font-mono text-[10px] bg-white/50 dark:bg-black/20 rounded p-1.5 max-h-48 overflow-y-auto">{{ formatToolResult(tc.result) }}</pre>
            </div>
            <div v-if="tc.error" class="text-red-700 dark:text-red-300">
              <div class="font-medium text-[10px] uppercase tracking-wide text-red-500 dark:text-red-400 mb-0.5">Error</div>
              <pre class="whitespace-pre-wrap break-words font-mono text-[10px] bg-red-100/50 dark:bg-red-900/20 rounded p-1.5">{{ tc.error }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- Old error-only block removed — replaced by the unified tool display above -->

      <!-- DOCX Download Button — shown when message has generated .docx file -->
      <div
        v-if="message.metadata?.file_url && message.role === 'assistant'"
        class="mt-3 pt-3 border-t border-cream-300 dark:border-ash-600"
      >
        <a
          :href="message.metadata.file_url"
          :download="message.metadata.file_name || 'document.docx'"
          class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                 bg-navy-500 hover:bg-navy-600 dark:bg-cream-400 dark:hover:bg-cream-500
                 text-cream-50 dark:text-ash-900
                 transition-colors shadow-sm hover:shadow"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          <span>📄 {{ message.metadata.file_name || 'Download DOCX' }}</span>
        </a>
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
import MarkdownIt from 'markdown-it'
import { katex } from '@mdit/plugin-katex'
import hljs from 'highlight.js/lib/core'
import { useSanitize } from '../composables/useSanitize'
import 'katex/dist/katex.min.css'
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
import AskUserCard from './AskUserCard.vue'
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

interface SearchItem {
  type?: string
  query?: string
  icon?: string
  status?: string
  results?: any[]
  count?: number
  error?: string | null
}

interface Props {
  message: ChatMessage
  isStreaming?: boolean
  streamPhase?: string
  searchResults?: SearchItem[]
  searchMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  isStreaming: false,
  streamPhase: 'idle',
  searchResults: () => [],
  searchMessage: ''
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
  (e: 'ask-user-answer', value: string): void
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

const toolDetailsOpen = ref<Record<number, boolean>>({})

const allToolCalls = computed(() => {
  const calls = props.message.tool_calls || []
  return calls.filter(tc => tc && tc.name)
})

function toggleToolDetail(idx: number): void {
  toolDetailsOpen.value[idx] = !toolDetailsOpen.value[idx]
}

// Human-friendly tool labels
const TOOL_LABELS: Record<string, string> = {
  WebSearch: '🔍 Web Search',
  SearchArxiv: '📚 Search arXiv',
  SearchSemanticScholar: '🎓 Search Semantic Scholar',
  GenerateFullPaper: '📝 Generate Full Paper',
  ProposeChips: '💡 Propose Actions',
  ProposeTitle: '📌 Propose Title',
  ProposeAbstract: '📄 Propose Abstract',
  ProposeKeywords: '🏷️ Propose Keywords',
  ProposeSection: '📑 Propose Section',
  ProposeReference: '📖 Propose Reference',
  ProposeJournal: '📰 Propose Journal',
  RequestExportDocx: '📥 Export DOCX',
  Paraphrase: '✏️ Paraphrase',
  FixGrammar: '🔧 Fix Grammar',
  Translate: '🌐 Translate',
  SetCitationStyle: '📋 Set Citation Style',
  SetLanguage: '🌍 Set Language',
  AskQuestions: '❓ Ask Questions',
  RouteIntent: '🔀 Route Intent',
  CreateChart: '📊 Create Chart',
  SLR: '🔬 Systematic Literature Review',
  ReviewPaper: '🔍 Review Paper',
}

const TOOL_RUNNING: Record<string, string> = {
  WebSearch: 'mencari...',
  SearchArxiv: 'mencari paper...',
  SearchSemanticScholar: 'mencari paper...',
  GenerateFullPaper: 'menulis paper...',
  ProposeSection: 'menulis section...',
  Paraphrase: 'memparafrase...',
  FixGrammar: 'memperbaiki grammar...',
  Translate: 'menerjemahkan...',
  SLR: 'melakukan SLR...',
  ReviewPaper: 'me-review paper...',
  CreateChart: 'membuat chart...',
}

function toolLabel(name: string): string {
  return TOOL_LABELS[name] || name
}

function toolRunningText(name: string): string {
  return TOOL_RUNNING[name] || 'berjalan...'
}

function toolDetail(tc: any): string {
  const args = tc.arguments || {}
  const name = tc.name || ''
  // WebSearch → show query
  if (name === 'WebSearch' && args.query) return `Query: "${args.query}"`
  if (name === 'SearchArxiv' && args.query) return `Query: "${args.query}"`
  if (name === 'SearchSemanticScholar' && args.query) return `Query: "${args.query}"`
  if (name === 'GenerateFullPaper' && args.prompt) return args.prompt.slice(0, 80)
  if (name === 'ProposeSection' && args.title) return `Section: ${args.title}`
  if (name === 'ProposeTitle' && args.title) return args.title
  if (name === 'ProposeJournal' && args.journal) return args.journal
  if (name === 'Translate' && args.target_language) return `→ ${args.target_language}`
  if (name === 'SetCitationStyle' && args.style) return `Style: ${args.style}`
  if (name === 'SetLanguage' && args.language) return `Language: ${args.language}`
  if (name === 'CreateChart' && args.title) return args.title
  if (name === 'SLR' && args.query) return `Query: "${args.query}"`
  if (name === 'Paraphrase' && args.scope) return `Scope: ${args.scope}`
  if (name === 'FixGrammar' && args.scope) return `Scope: ${args.scope}`
  return ''
}

function formatToolArgs(args: any): string {
  if (!args || typeof args !== 'object') return String(args || '')
  try {
    return JSON.stringify(args, null, 2)
  } catch {
    return String(args)
  }
}

function formatToolResult(result: any): string {
  if (typeof result === 'string') {
    // Truncate very long results for the collapsed view
    if (result.length > 2000) return result.slice(0, 2000) + '...(truncated)'
    return result
  }
  try {
    const s = JSON.stringify(result, null, 2)
    if (s.length > 2000) return s.slice(0, 2000) + '...(truncated)'
    return s
  } catch {
    return String(result)
  }
}

// Whether any search fetcher is still in progress — drives the header spinner.
const searchRunning = computed(() =>
  Array.isArray(props.searchResults) && props.searchResults.some(s => s?.status !== 'done')
)

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
  // Strip leaked MATH_N placeholder tokens (model sometimes outputs these
  // instead of actual LaTeX $...$). They look broken to the user.
  out = out.replace(/\bMATH_\d+\b/g, '')
  return out
}

const visibleContent = computed(() => {
  let raw = scrubControlTokens(props.message.content || '').trim()
  // Strip leading whitespace from every line so markdown-it doesn't
  // interpret 4+ spaces as a <pre> code block (indentation bug).
  // Keep intentional indents inside fenced code blocks intact.
  if (!raw) return ''

  // For user messages: collapse file blocks to just the filename
  if (props.message.role === 'user') {
    // Replace full file blocks with just "📎 filename"
    raw = raw.replace(
      /--- File terlampir: (.+?)(?: \[file_id=\d+\])? ---\n[\s\S]*?--- akhir file ---/g,
      (_, name) => `📎 ${name.trim()}`
    )
    // Clean up: remove "Saya melampirkan N file." if file names follow
    raw = raw.replace(/^Saya melampirkan \d+ file\.\s*/m, '')
    raw = raw.trim()
  }

  // Normalize LaTeX delimiters: convert \[...\] to $$...$$ and \(...\) to $...$
  // This ensures @mdit/plugin-katex can render all LaTeX formats.
  // Must be done BEFORE markdown-it processing.
  // Note: In JS regex replacement, $$ is special (escapes $), so use $$$$ for literal $$
  raw = raw.replace(/\\\[/g, '$$$$')  // \[ → $$
  raw = raw.replace(/\\\]/g, '$$$$')  // \] → $$
  raw = raw.replace(/\\\(/g, '$')     // \( → $
  raw = raw.replace(/\\\)/g, '$')     // \) → $

  const lines = raw.split('\n')
  let inFence = false
  const cleaned = lines.map(line => {
    if (line.trimStart().startsWith('```')) {
      inFence = !inFence
      return line.trimStart()
    }
    if (inFence) return line
    // Remove leading whitespace from non-code lines
    return line.replace(/^\s+/, '')
  }).join('\n')
  return cleaned
})

const messageClasses = computed(() => {
  if (props.message.role === 'user') {
    return 'chat-bubble-user'
  }
  return 'chat-bubble-ai'
})

// ── markdown-it with KaTeX plugin ──────────────────────────────────────────
// KaTeX plugin handles $...$ inline and $$...$$ display math at parser level,
// so no manual regex extraction is needed.
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: false,
  breaks: false,
  highlight(code: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value } catch {}
    }
    try { return hljs.highlightAuto(code).value } catch {}
    return ''
  },
})

md.use(katex, {
  throwOnError: false,
  errorColor: '#cc0000',
})

const renderedContent = computed(() => {
  if (!visibleContent.value) return ''
  try {
    const html = md.render(visibleContent.value)
    // Use permissive sanitize config that preserves KaTeX HTML
    // (spans with classes, inline styles, aria attributes)
    return sanitizeHtml(html, {
      USE_PROFILES: { html: true },
      ADD_ATTR: ['class', 'style', 'aria-hidden', 'data-katex', 'data-katex-display'],
      ADD_TAGS: ['annotation', 'semantics', 'math', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mroot'],
    })
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
  if (allToolCalls.value.length > 0) return true
  return false
})

// True when this message is the one currently being streamed from the backend.
// Used to show raw text during streaming and only render markdown+LaTeX when done.
const isActivelyStreaming = computed(() => {
  if (!props.isStreaming) return false
  if (props.message.role !== 'assistant') return false
  const phase = props.streamPhase
  return phase === 'sending' || phase === 'thinking' || phase === 'composing' || phase === 'streaming'
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
  background: var(--bg-elev);
  border: 1px solid var(--border-soft);
  border-radius: 0.75rem;
  padding: 1rem;
  overflow-x: auto;
  margin: 0.75rem 0;
}
html.dark .prose :deep(pre) { background: #0a1628; border: 1px solid var(--border-soft); }

.prose :deep(pre code) {
  color: var(--text-strong);
  font-size: 0.8rem;
  line-height: 1.5;
}
html.dark .prose :deep(pre code) {
  color: #cdd6f4;
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

/* ── Typography: clean, ChatGPT-style ── */
.prose :deep(p) {
  margin: 0.45rem 0;
  line-height: 1.7;
}
.prose :deep(p:first-child) { margin-top: 0; }
.prose :deep(p:last-child) { margin-bottom: 0; }

/* Lists — minimal indent, clean bullets */
.prose :deep(ul) {
  margin: 0.5rem 0;
  padding-left: 1.25rem;
  list-style: disc;
}
.prose :deep(ol) {
  margin: 0.5rem 0;
  padding-left: 1.25rem;
  list-style: decimal;
}
.prose :deep(ul ul), .prose :deep(ol ol),
.prose :deep(ul ol), .prose :deep(ol ul) {
  margin: 0.15rem 0;
}
.prose :deep(li) {
  margin: 0.3rem 0;
  line-height: 1.7;
  padding-left: 0.15rem;
}
.prose :deep(li > p) {
  margin: 0.15rem 0;
}

/* Headings */
.prose :deep(h1), .prose :deep(h2), .prose :deep(h3), .prose :deep(h4) {
  margin: 1rem 0 0.4rem;
  font-weight: 600;
  line-height: 1.35;
}
.prose :deep(h1) { font-size: 1.2rem; }
.prose :deep(h2) { font-size: 1.1rem; }
.prose :deep(h3) { font-size: 1rem; }
.prose :deep(h4) { font-size: 0.95rem; }

/* Blockquote */
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

/* Tables — display:block + overflow-x:auto so wide tables scroll
   inside the bubble instead of overflowing past the bubble edge. */
.prose :deep(table) {
  display: block;
  overflow-x: auto;
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
  background: #1b3558;
  color: #f5f3ee;
}
.dark .prose :deep(td) {
  color: #f5f3ee;
}

/* Links */
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

/* Horizontal rule */
.prose :deep(hr) {
  border: none;
  border-top: 1px solid #cca97f;
  margin: 1rem 0;
}
.dark .prose :deep(hr) {
  border-top-color: #3f3c35;
}

/* Strong / emphasis */
.prose :deep(strong) { font-weight: 600; }
.prose :deep(em) { font-style: italic; }

.typing-cursor {
  display: inline-block;
  width: 0.375rem;
  height: 1rem;
  margin-left: 0.125rem;
  vertical-align: middle;
  background: color-mix(in srgb, var(--accent) 80%, transparent);
  animation: typing-cursor-pulse 6s ease-in-out infinite;
}

@keyframes typing-cursor-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}

/* Prevent leading whitespace from creating <pre> blocks */
.prose :deep(> *:first-child) { margin-top: 0; }
</style>
