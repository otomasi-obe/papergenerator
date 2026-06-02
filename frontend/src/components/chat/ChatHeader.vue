<template>
  <header class="px-4 py-3 bg-cream-50 dark:bg-ash-800 border-b border-cream-300 dark:border-ash-700 flex items-center gap-2">
    <button
      @click="$emit('go-back')"
      class="text-ink-700 dark:text-ink-200 hover:text-ink-900 dark:hover:text-ink-50 text-sm px-2 py-1 min-h-[44px] min-w-[44px] flex items-center justify-center rounded hover:bg-cream-200 dark:hover:bg-ash-700 transition-colors"
      title="Kembali ke daftar chat"
    >← Back</button>
    <div class="relative shrink-0">
      <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-brown-500 to-brown-700 dark:from-brown-400 dark:to-brown-600 flex items-center justify-center">
        <svg class="w-3.5 h-3.5 text-cream-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/>
        </svg>
      </div>
      <span
        :class="[
          'absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-cream-50 dark:border-ash-800',
          isStreaming ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400',
        ]"
      ><span class="sr-only">{{ isStreaming ? 'AI is thinking' : 'Online' }}</span></span>
    </div>
    <div class="min-w-0 flex-1">
      <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 truncate">
        {{ currentChat?.title || 'AI Chat' }}
      </h3>
      <p :class="['text-[10px]', statusColor]">
        {{ statusMessage }}
      </p>
    </div>
  </header>
</template>

<script setup lang="ts">
interface Chat {
  id: number
  title: string
}

interface Props {
  currentChat: Chat | null
  isStreaming: boolean
  statusMessage: string
  statusColor: string
}

defineProps<Props>()

defineEmits<{
  (e: 'go-back'): void
}>()
</script>
