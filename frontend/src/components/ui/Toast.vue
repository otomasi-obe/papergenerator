<script setup lang="ts">
/**
 * Toast - Notification system for user feedback
 * Addresses UX issues around feedback clarity
 */

import { useToast } from './useToast'

const { toasts, remove: removeToast } = useToast()

const iconMap = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ'
}

const colorMap = {
  success: 'bg-emerald-600 dark:bg-emerald-500',
  error: 'bg-red-600 dark:bg-red-500',
  warning: 'bg-amber-600 dark:bg-amber-500',
  info: 'bg-blue-600 dark:bg-blue-500'
}
</script>

<template>
  <Teleport to="body">
    <div 
      class="fixed bottom-6 right-6 z-[9999] flex flex-col gap-3"
      aria-live="polite"
      aria-atomic="true"
    >
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="[
            'px-5 py-3 rounded-xl shadow-lg text-white font-medium text-sm',
            'flex items-center gap-3 min-w-[280px] max-w-md',
            'animate-slide-up',
            colorMap[toast.type]
          ]"
          role="alert"
        >
          <span class="text-lg" aria-hidden="true">{{ iconMap[toast.type] }}</span>
          <span class="flex-1">{{ toast.message }}</span>
          <button
            @click="removeToast(toast.id)"
            class="hover:opacity-75 transition-opacity"
            aria-label="Dismiss notification"
          >
            ✕
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(2rem);
}

.toast-leave-to {
  opacity: 0;
  transform: translateY(1rem);
}
</style>
