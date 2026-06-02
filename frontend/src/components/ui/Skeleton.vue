<script setup lang="ts">
/**
 * Skeleton - Loading placeholder for better perceived performance
 * Addresses VIS-003: Generic loading UI without skeleton screens
 * 
 * Usage:
 * <Skeleton class="h-4 w-3/4" />
 * <Skeleton :count="3" class="h-16" />
 */

interface Props {
  count?: number
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  count: 1
})
</script>

<template>
  <template v-for="i in count" :key="i">
    <div 
      :class="[
        'animate-shimmer bg-gradient-to-r from-cream-200 via-cream-100 to-cream-200',
        'dark:from-ash-700 dark:via-ash-600 dark:to-ash-700',
        'bg-[length:200%_100%] rounded-lg',
        props.class
      ]"
    />
  </template>
</template>

<script lang="ts">
export default { name: 'Skeleton' }
</script>

<style scoped>
@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}
</style>
