<template>
  <button @click="$emit('click')"
    :disabled="loading"
    class="px-3 py-1.5 bg-[var(--accent)]/10 text-[var(--accent)] rounded-lg hover:bg-[var(--accent)]/20 text-xs font-medium flex items-center gap-1 disabled:opacity-50 transition-all active:scale-95 transition-transform">
    <span v-if="loading" class="spinner !w-3 !h-3 !border-[var(--accent)]/40 !border-t-[var(--accent)]"></span>
    <svg v-else class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
    </svg>
    {{ label }}
  </button>
</template>

<script setup lang="ts">
import type { AiButtonProps, AiButtonEmits } from '../types/components'

defineProps<AiButtonProps>()
defineEmits<AiButtonEmits>()
</script>
