<template>
  <div class="flex flex-wrap gap-2 my-2" role="group" aria-label="Action options">
    <button
      v-for="(chip, i) in chips"
      :key="i"
      :ref="(el) => { if (el) chipRefs[i] = el as HTMLElement }"
      @click="$emit('select', chip.value ?? chip.label)"
      @keydown.left="focusPrev(i)"
      @keydown.right="focusNext(i)"
      @keydown.home="focusFirst"
      @keydown.end="focusLast"
      :title="chip.value ?? chip.label"
      :aria-label="`Option ${i + 1} of ${chips.length}: ${chip.label}`"
      class="px-3 py-1.5 min-h-[44px] min-w-[44px] rounded-full text-sm font-medium border transition-colors
             bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
             border-cream-300 dark:border-ash-600
             text-ink-800 dark:text-ink-100
             focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-400 dark:focus-visible:ring-cream-400 focus-visible:ring-offset-1"
    >
      {{ chip.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ActionChipsProps, ActionChipsEmits } from '../types/components'

defineProps<ActionChipsProps>()
defineEmits<ActionChipsEmits>()

const chipRefs = ref<Record<number, HTMLElement>>({})

function focusPrev(currentIndex: number): void {
  const keys = Object.keys(chipRefs.value).map(Number).sort((a, b) => a - b)
  const currentPos = keys.indexOf(currentIndex)
  const prevIndex = currentPos > 0 ? keys[currentPos - 1] : keys[keys.length - 1]
  chipRefs.value[prevIndex]?.focus()
}

function focusNext(currentIndex: number): void {
  const keys = Object.keys(chipRefs.value).map(Number).sort((a, b) => a - b)
  const currentPos = keys.indexOf(currentIndex)
  const nextIndex = currentPos < keys.length - 1 ? keys[currentPos + 1] : keys[0]
  chipRefs.value[nextIndex]?.focus()
}

function focusFirst(): void {
  const keys = Object.keys(chipRefs.value).map(Number).sort((a, b) => a - b)
  chipRefs.value[keys[0]]?.focus()
}

function focusLast(): void {
  const keys = Object.keys(chipRefs.value).map(Number).sort((a, b) => a - b)
  chipRefs.value[keys[keys.length - 1]]?.focus()
}
</script>
