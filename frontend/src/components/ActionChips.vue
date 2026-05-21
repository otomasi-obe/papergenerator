<template>
  <div class="flex flex-wrap gap-2 my-2">
    <button
      v-for="(chip, i) in chips"
      :key="i"
      @click="$emit('select', chip.value ?? chip.label)"
      :title="chip.value ?? chip.label"
      class="px-3 py-1.5 rounded-full text-sm font-medium border transition-colors
             bg-cream-100 hover:bg-cream-200 dark:bg-ash-700 dark:hover:bg-ash-600
             border-cream-300 dark:border-ash-600
             text-ink-800 dark:text-ink-100
             focus:outline-none focus:ring-2 focus:ring-brown-400 dark:focus:ring-cream-400"
    >
      {{ chip.label }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  chips: { type: Array, required: true },
})
defineEmits(['select'])
</script>
