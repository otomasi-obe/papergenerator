<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import { useUserStateStore } from './stores/userState'
import { useAuthStore } from './stores/auth'
import TokenPurchaseModal from './components/TokenPurchaseModal.vue'
import FloatingChatButton from './components/FloatingChatButton.vue'
import MaintenanceBanner from './components/MaintenanceBanner.vue'

const userState = useUserStateStore()
const auth = useAuthStore()
const tokenModalOpen = ref(false)

if (typeof window !== 'undefined') {
  window.addEventListener('open-token-purchase', () => { tokenModalOpen.value = true })
}

onMounted(async () => {
  // load userState if logged in
  if (auth.isLoggedIn) {
    await userState.loadFromServer()
  }
})

// Heartbeat: start when logged in, stop when logged out
watch(() => auth.isLoggedIn, (val) => {
  if (val) auth.startHeartbeat()
  else auth.stopHeartbeat()
}, { immediate: true })
</script>

<template>
  <div id="main-content">
    <MaintenanceBanner />
    <ErrorBoundary>
      <router-view />
    </ErrorBoundary>
    <TokenPurchaseModal :is-open="tokenModalOpen" @close="tokenModalOpen = false" />
    <FloatingChatButton />
  </div>
</template>