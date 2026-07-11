<template>
  <!-- Suggested prompts for chat empty state -->
  <div class="suggested-prompts w-full max-w-lg mx-auto mt-4">
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
      <button
        v-for="(prompt, idx) in prompts"
        :key="idx"
        @click="$emit('select', prompt.text)"
        class="group flex items-start gap-2.5 p-3 rounded-xl border border-cream-200/60 dark:border-ash-600/60 bg-cream-50/50 dark:bg-ash-800/50 hover:bg-cream-100/50 dark:hover:bg-ash-700/50 transition-colors text-left active:scale-[0.98]"
      >
        <span class="text-lg shrink-0 mt-0.5" aria-hidden="true">{{ prompt.icon }}</span>
        <span class="text-sm text-ink-900 dark:text-ink-100 leading-snug group-hover:text-navy-700 dark:group-hover:text-navy-200 transition-colors">
          {{ prompt.text }}
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck

interface Prompt {
  icon: string
  text: string
}

const prompts: Prompt[] = [
  { icon: '📖', text: 'Buatkan kerangka paper tentang topik...' },
  { icon: '🔍', text: 'Carikan referensi paper tentang...' },
  { icon: '✍️', text: 'Tulis pendahuluan untuk paper saya' },
  { icon: '📊', text: 'Analisis data dan buatkan chart' },
  { icon: '📝', text: 'Parafrase section Introduction' },
  { icon: '🔢', text: 'Jelaskan rumus yang cocok untuk metode...' },
  { icon: '📚', text: 'Review paper saya dan beri saran perbaikan' },
  { icon: '🌐', text: 'Translate paper saya ke Bahasa Inggris' },
]
</script>
