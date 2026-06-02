<script setup lang="ts">
/**
 * BaseInput - Unified input component for consistent form styling
 * Addresses CONSIST-004: Form input styling mismatch
 * 
 * Usage:
 * <BaseInput v-model="email" label="Email" type="email" :error="errors.email" />
 * <BaseInput v-model="title" label="Paper Title" placeholder="Enter title..." />
 */

interface Props {
  modelValue: string | number
  label?: string
  type?: 'text' | 'email' | 'password' | 'number' | 'url'
  placeholder?: string
  error?: string
  hint?: string
  disabled?: boolean
  required?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  disabled: false,
  required: false
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void
}>()

const inputId = `input-${Math.random().toString(36).slice(2, 9)}`

function onInput(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>

<template>
  <div class="w-full">
    <!-- Label -->
    <label 
      v-if="label" 
      :for="inputId"
      class="block text-sm font-medium text-ink-700 dark:text-ink-200 mb-1.5"
    >
      {{ label }}
      <span v-if="required" class="text-red-500 ml-1" aria-label="required">*</span>
    </label>

    <!-- Input field -->
    <div class="relative">
      <input
        :id="inputId"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :aria-invalid="!!error"
        :aria-describedby="error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined"
        @input="onInput"
        :class="[
          'w-full px-4 py-2.5 min-h-[44px] rounded-xl border transition-all duration-200',
          'bg-cream-50 dark:bg-ash-800',
          'text-ink-900 dark:text-ink-50',
          'placeholder:text-ink-400 dark:placeholder:text-ink-500',
          'focus:outline-none focus:ring-2 focus:ring-offset-0',
          error 
            ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20' 
            : 'border-cream-300 dark:border-ash-600 focus:border-accent-primary focus:ring-accent-primary/20',
          { 'opacity-50 cursor-not-allowed': disabled }
        ]"
      />
    </div>

    <!-- Error message -->
    <p 
      v-if="error" 
      :id="`${inputId}-error`"
      class="mt-1.5 text-xs text-red-600 dark:text-red-400 flex items-center gap-1"
      role="alert"
    >
      <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
        <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
      </svg>
      {{ error }}
    </p>

    <!-- Hint text -->
    <p 
      v-else-if="hint" 
      :id="`${inputId}-hint`"
      class="mt-1.5 text-xs text-ink-500 dark:text-ink-400"
    >
      {{ hint }}
    </p>
  </div>
</template>

<script lang="ts">
export default { name: 'BaseInput' }
</script>
