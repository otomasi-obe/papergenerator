<template>
  <div v-if="currentPaperId" class="mt-5 border-t border-[var(--border-soft)] pt-3">
    <button
      @click="$emit('toggle')"
      class="w-full flex items-center justify-between min-h-[44px] text-xs font-medium text-[var(--text-base)] hover:text-[var(--text-strong)]"
      :title="`Project memory (${memory.length} items)`"
    >
      <span class="flex items-center gap-1.5">
        🧠
        <span
          v-if="memory.length"
          class="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-indigo-100 text-indigo-700 text-[10px] font-semibold"
        >{{ memory.length }}</span>
      </span>
      <span class="text-[var(--text-muted)]">{{ isOpen ? '▾' : '▸' }}</span>
    </button>
    <div v-if="isOpen" class="mt-2 space-y-1.5">
      <div v-if="memory.length === 0" class="text-[11px] text-[var(--text-muted)] px-1">
        Empty. AI akan menyimpan fakta penting paper ini secara otomatis.
      </div>
      <div
        v-for="m in memory"
        :key="m.id"
        class="bg-[var(--bg-surface)] border border-[var(--border-soft)] rounded-md px-2 py-1.5 text-[11px] flex items-start gap-1.5 group/mem"
      >
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-1.5 mb-0.5">
            <span class="text-[var(--text-muted)] text-[10px] uppercase tracking-wide">{{ m.kind }}</span>
            <span class="text-[var(--text-strong)] font-medium truncate">{{ m.key }}</span>
          </div>
          <div class="text-[var(--text-base)] leading-snug">{{ m.value }}</div>
        </div>
        <button
          @click="$emit('delete-entry', m.id)"
          class="opacity-0 group-hover/mem:opacity-100 text-[var(--text-muted)] hover:text-red-500 min-h-[44px] min-w-[44px] flex items-center justify-center"
          title="Forget"
          aria-label="Forget memory entry"
        ><span aria-hidden="true">✕</span></button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface MemoryEntry {
  id: number
  kind: string
  key: string
  value: string
}

interface Props {
  memory: MemoryEntry[]
  isOpen: boolean
  currentPaperId: string | null
}

defineProps<Props>()

defineEmits<{
  (e: 'toggle'): void
  (e: 'delete-entry', id: number): void
}>()
</script>
