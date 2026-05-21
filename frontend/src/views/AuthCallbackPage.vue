<template>
  <main class="min-h-screen bg-slate-900 flex items-center justify-center">
    <div class="text-center text-white">
      <div class="text-4xl mb-4 animate-spin" aria-hidden="true">⚙️</div>
      <p class="text-slate-400" role="status" aria-live="polite">{{ statusMsg }}</p>
    </div>
  </main>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const statusMsg = ref('Completing sign-in...')

onMounted(async () => {
  if (route.query.error) {
    statusMsg.value = 'Sign-in failed.'
    setTimeout(() => router.push('/login?error=' + route.query.error), 1500)
    return
  }

  // Cookies are already set by /api/auth/google/callback. Just load the user.
  const me = await auth.fetchMe()
  if (me) {
    statusMsg.value = `Welcome back, ${me.name || 'user'}!`
    setTimeout(() => router.push('/dashboard'), 600)
  } else {
    statusMsg.value = 'Failed to load user info.'
    setTimeout(() => router.push('/login?error=auth_failed'), 1500)
  }
})
</script>
