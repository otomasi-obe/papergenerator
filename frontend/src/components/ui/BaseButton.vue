<script setup lang="ts">
/**
 * BaseButton - Unified button component for consistent UI
 * Addresses CONSIST-001: Button classes inconsistent across pages
 * 
 * Usage:
 * <BaseButton variant="primary" size="md">Submit</BaseButton>
 * <BaseButton variant="danger" :loading="isDeleting">Delete</BaseButton>
 */

interface Props {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  icon?: string
  fullWidth?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  fullWidth: false
})

const variantClasses = {
  primary: 'bg-accent-primary hover:bg-blue-700 dark:bg-accent-primary dark:hover:bg-blue-600 text-white shadow-sm hover:shadow-md',
  secondary: 'bg-cream-200 hover:bg-cream-300 dark:bg-ash-700 dark:hover:bg-ash-600 text-ink-900 dark:text-ink-50',
  danger: 'bg-red-600 hover:bg-red-700 text-white',
  ghost: 'bg-transparent hover:bg-cream-100 dark:hover:bg-ash-700 text-ink-700 dark:text-ink-200',
  outline: 'bg-transparent border-2 border-accent-primary text-accent-primary hover:bg-accent-primary hover:text-white'
}

const sizeClasses = {
  sm: 'px-3 py-1.5 text-xs min-h-[36px]',
  md: 'px-4 py-2.5 text-sm min-h-[44px]',
  lg: 'px-6 py-3 text-base min-h-[52px]'
}

const isDisabled = computed(() => props.disabled || props.loading)
</script>

<template>
  <button
    :class="[
      'inline-flex items-center justify-center gap-2 font-medium rounded-xl transition-all duration-200',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary focus-visible:ring-offset-2',
      'active:scale-95',
      variantClasses[variant],
      sizeClasses[size],
      { 'w-full': fullWidth },
      { 'opacity-50 cursor-not-allowed': isDisabled }
    ]"
    :disabled="isDisabled"
  >
    <svg v-if="loading" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
    <slot />
  </button>
</template>

<script lang="ts">
import { computed } from 'vue'
export default { name: 'BaseButton' }
</script>
