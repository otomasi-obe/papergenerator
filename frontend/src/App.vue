<script setup lang="ts">
import { onMounted } from 'vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import { useUserStateStore } from './stores/userState'
import { useAuthStore } from './stores/auth'

const userState = useUserStateStore()
const auth = useAuthStore()

onMounted(async () => {
  // Load user state from server once auth is ready
  // (authStore.fetchMe() is already called on store init)
  if (auth.isLoggedIn) {
    await userState.loadFromServer()
  }
})
</script>

<template>
  <div id="main-content">
    <ErrorBoundary>
      <router-view />
    </ErrorBoundary>
  </div>
</template>
