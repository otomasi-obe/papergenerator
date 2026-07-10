<script setup lang="ts">
import { onMounted, ref } from 'vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import { useUserStateStore } from './stores/userState'
import { useAuthStore } from './stores/auth'
import TokenPurchaseModal from './components/TokenPurchaseModal.vue'
import FloatingChatButton from './components/FloatingChatButton.vue'

const userState = useUserStateStore()
const auth = useAuthStore()
const tokenModalOpen = ref(false)

if (typeof window !== 'undefined') {
  window.addEventListener('open-token-purchase', () => { tokenModalOpen.value = true })
}

onMounted(async () => {
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
    <TokenPurchaseModal :is-open="tokenModalOpen" @close="tokenModalOpen = false" />
    <FloatingChatButton />
  </div>
</template>