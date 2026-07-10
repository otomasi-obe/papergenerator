<template>
  <div
    class="group bg-cream-100/50 dark:bg-ash-850/50 border border-cream-300 dark:border-ash-700 rounded-xl p-4 hover:border-navy-400 dark:hover:border-cream-400 transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer"
    @click="handleClick"
    role="button"
    :tabindex="passwordGated ? 0 : -1"
    @keydown.enter="handleClick"
    @keydown.space.prevent="handleClick"
  >
    <div class="flex items-start gap-3">
      <div class="text-3xl shrink-0" :class="passwordGated ? 'opacity-70' : ''">{{ icon }}</div>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <h3 class="font-semibold text-ink-900 dark:text-ink-100 text-sm truncate">{{ title }}</h3>
          <span v-if="passwordGated" class="flex-shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
            🔒 Locked
          </span>
        </div>
        <p class="text-xs text-ink-600 dark:text-ink-300 mt-1 line-clamp-2">{{ description }}</p>
        <div class="flex flex-wrap gap-1 mt-3" v-if="options.length > 0">
          <span
            v-for="opt in options.slice(0, 3)"
            :key="opt"
            class="px-2 py-0.5 text-[10px] font-medium rounded-full bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-200 border border-cream-300 dark:border-ash-600"
          >
            {{ opt }}
          </span>
          <span v-if="options.length > 3" class="px-2 py-0.5 text-[10px] font-medium rounded-full bg-cream-200 dark:bg-ash-700 text-ink-500 dark:text-ink-300 border border-cream-300 dark:border-ash-600">
            +{{ options.length - 3 }} more
          </span>
        </div>
        <div v-else class="mt-3 text-center text-xs text-ink-500 dark:text-ink-300 py-2">
          <span class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-cream-200 dark:bg-ash-700 border border-cream-300 dark:border-ash-600">
            <span class="text-base">🔐</span> Enter password to unlock
          </span>
        </div>
      </div>
    </div>
    <!-- Hover indicator -->
    <div class="absolute bottom-0 left-0 right-0 h-0.5 bg-navy-500 dark:bg-cream-400 scale-x-0 group-hover:scale-x-100 transition-transform duration-200 origin-center rounded-b-xl" />
  </div>
</template>

<script setup lang="ts">
interface Props {
  id: string
  icon: string
  title: string
  description: string
  options: string[]
  passwordGated?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  run: [tool: Props]
}>()

function handleClick() {
  if (props.passwordGated) {
    emit('run', props)
  } else {
    emit('run', props)
  }
}
</script>