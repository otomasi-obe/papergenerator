<template>
  <div class="flex flex-wrap gap-2 my-2" role="group" aria-label="Action options">
    <button
      v-for="(chip, i) in chips"
      :key="i"
      :ref="el => chipRefs[i] = el"
      @click="$emit('select', chip.value ?? chip.label)"
      @keydown.left="focusPrev(i)"
      @keydown.right="focusNext(i)"
      @keydown.home="focusFirst"
      @keydown.end="focusLast"
      :title="chip.value ?? chip.label"
      :aria-label="`Option ${i + 1} of ${chips.length}: ${chip.label}`"
      class="px-3 py-1.5 rounded-full text-sm font-medium border transition-colors
             bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
             border-cream-300 dark:border-ash-600
             text-ink-800 dark:text-ink-100
             focus:outline-none focus-visible:ring-2 focus-visible:ring-brown-400 dark:focus-visible:ring-cream-400 focus-visible:ring-offset-1"
    >
      {{ chip.label }}
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  chips: { type: Array, required: true },
})
defineEmits(['select'])

const chipRefs = ref([])

function focusPrev(currentIndex) {
  const prevIndex = currentIndex > 0 ? currentIndex - 1 : chipRefs.value.length - 1
  chipRefs.value[prevIndex]?.focus()
}

function focusNext(currentIndex) {
  const nextIndex = currentIndex < chipRefs.value.length - 1 ? currentIndex + 1 : 0
  chipRefs.value[nextIndex]?.focus()
}

function focusFirst() {
  chipRefs.value[0]?.focus()
}

function focusLast() {
  chipRefs.value[chipRefs.value.length - 1]?.focus()
}
</script>
