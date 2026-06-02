<template>
  <div ref="messagesContainer" @scroll="checkScrollPosition" class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
    <!-- Empty-state hero: no messages yet. Offers entry chips + quick
         prompts to seed a focused first turn instead of staring at a
         blank textarea. -->
    <div
      v-if="!messages.length && !isStreaming"
      class="empty-hero flex flex-col items-center justify-center min-h-full px-6 py-8 text-center"
    >
      <div class="text-3xl mb-4" aria-hidden="true">📝</div>
      <h2 class="text-xl font-semibold text-ink-900 dark:text-ink-50 mb-2">
        Mau buat paper apa?
      </h2>
      <p class="text-sm text-ink-600 dark:text-ink-300 mb-6 max-w-md">
        Pilih path di bawah, atau ketik bebas.
      </p>
      <ActionChips
        :chips="entryChips"
        @select="$emit('entry-pick', $event)"
        class="justify-center"
      />
      <div class="mt-8 text-xs uppercase tracking-wider text-ink-500 dark:text-ink-400">
        atau quick start
      </div>
      <div class="mt-3 flex flex-col gap-2 items-center">
        <button
          v-for="(qp, i) in quickPrompts"
          :key="i"
          @click="$emit('entry-pick', qp.value)"
          class="text-sm text-brown-700 dark:text-cream-200 hover:underline"
        >
          • {{ qp.label }}
        </button>
      </div>
    </div>

    <ChatMessage
      v-for="msg in messages"
      :key="msg.id"
      :message="msg"
      :is-streaming="isStreaming && msg === messages[messages.length - 1] && msg.role === 'assistant'"
      @pick-option="$emit('pick-option', $event)"
      @chip-select="$emit('chip-select', $event)"
      @chart-accept="$emit('chart-accept', $event)"
      @chart-regenerate="$emit('chart-regenerate', $event)"
      @file-review-pick="$emit('file-review-pick', $event)"
      @multi-question-submit="$emit('multi-question-submit', $event)"
      @revisi-accepted="$emit('revisi-accepted')"
      @revisi-rejected="$emit('revisi-rejected')"
      @review-cancel="$emit('review-cancel')"
    />
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed } from 'vue'
import ChatMessage from '../ChatMessage.vue'
import ActionChips from '../ActionChips.vue'

interface Message {
  id: number
  role: string
  content?: string
  thinking?: string
  tool_calls?: any[]
}

interface Chip {
  label: string
  value: string
}

interface Props {
  messages: Message[]
  isStreaming: boolean
  entryChips: Chip[]
  quickPrompts: Chip[]
}

defineProps<Props>()

defineEmits<{
  (e: 'entry-pick', value: string): void
  (e: 'pick-option', text: string): void
  (e: 'chip-select', value: string): void
  (e: 'chart-accept', data: any): void
  (e: 'chart-regenerate', data: any): void
  (e: 'file-review-pick', data: any): void
  (e: 'multi-question-submit', answers: any): void
  (e: 'revisi-accepted'): void
  (e: 'revisi-rejected'): void
  (e: 'review-cancel'): void
  (e: 'scroll-position-change', isNearBottom: boolean): void
}>()

const messagesContainer = ref<HTMLElement | null>(null)
const emit = defineEmits<{
  (e: 'entry-pick', value: string): void
  (e: 'pick-option', text: string): void
  (e: 'chip-select', value: string): void
  (e: 'chart-accept', data: any): void
  (e: 'chart-regenerate', data: any): void
  (e: 'file-review-pick', data: any): void
  (e: 'multi-question-submit', answers: any): void
  (e: 'revisi-accepted'): void
  (e: 'revisi-rejected'): void
  (e: 'review-cancel'): void
  (e: 'scroll-position-change', isNearBottom: boolean): void
}>()

function checkScrollPosition(): void {
  if (!messagesContainer.value) return
  const container = messagesContainer.value
  const scrollTop = container.scrollTop
  const scrollHeight = container.scrollHeight
  const clientHeight = container.clientHeight
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  const isNearBottom = distanceFromBottom < 100
  emit('scroll-position-change', isNearBottom)
}

function scrollToBottom(): void {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

defineExpose({
  scrollToBottom,
  messagesContainer
})
</script>
