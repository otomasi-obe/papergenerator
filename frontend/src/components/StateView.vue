<template>
  <div class="state-view">
    <slot v-if="loading" name="loading">
      <div class="state-view__panel" role="status" aria-live="polite">
        <span class="spinner" aria-hidden="true"></span>
        <span>Loading...</span>
      </div>
    </slot>

    <slot v-else-if="error" name="error" :error="error" :retry="onRetry">
      <div class="state-view__panel" role="alert">
        <p class="state-view__title">Something went wrong</p>
        <p class="state-view__text">{{ error }}</p>
        <button v-if="onRetry" type="button" class="state-view__button" @click="onRetry">Retry</button>
      </div>
    </slot>

    <slot v-else-if="isEmpty" name="empty">
      <div class="state-view__panel">
        <p class="state-view__title">No data yet</p>
        <p class="state-view__text">There is nothing to show here.</p>
      </div>
    </slot>

    <slot v-else />
  </div>
</template>

<script setup lang="ts">
import type { StateViewProps } from '../types/components'

defineProps<StateViewProps>()
</script>

<style scoped>
.state-view { min-width: 0; }
.state-view__panel {
  display: grid;
  justify-items: center;
  gap: var(--space-3);
  padding: var(--space-6);
  color: var(--text-muted);
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg);
  text-align: center;
}
.state-view__title { margin: 0; color: var(--text-strong); font-weight: 600; }
.state-view__text { margin: 0; color: var(--text-muted); }
.state-view__button {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--accent);
  color: white;
  cursor: pointer;
  font-weight: 600;
  padding: var(--space-2) var(--space-4);
}
.state-view__button:focus-visible { outline: none; box-shadow: var(--focus-ring); }
</style>
