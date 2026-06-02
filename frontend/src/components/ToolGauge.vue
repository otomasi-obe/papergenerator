<template>
  <div class="flex items-center gap-3.5 p-3.5 rounded-xl bg-cream-100 dark:bg-ash-700">
    <div
      class="w-16 h-16 rounded-full flex items-center justify-center text-xl font-extrabold text-white shrink-0"
      :style="{ background: `conic-gradient(${color} ${pct * 3.6}deg, var(--border-soft) 0deg)` }"
    >
      <div class="w-[46px] h-[46px] rounded-full bg-cream-50 dark:bg-ash-800 flex items-center justify-center text-ink-900 dark:text-ink-50 text-base font-extrabold">
        {{ pct }}%
      </div>
    </div>
    <div class="min-w-0">
      <div class="text-sm font-bold text-ink-900 dark:text-ink-50">{{ title }}</div>
      <div class="text-xs text-ink-500 dark:text-ink-300 mt-0.5">{{ desc }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  pct: number
  color: string
  title: string
  desc: string
}>()
</script>
