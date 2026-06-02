<script setup lang="ts">
import ErrorBoundary from './components/ErrorBoundary.vue'
</script>

<template>
  <div id="main-content">
    <ErrorBoundary>
      <router-view />
    </ErrorBoundary>
  </div>
</template>
