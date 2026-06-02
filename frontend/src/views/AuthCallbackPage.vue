<template>
  <main class="min-h-screen bg-navy-900 flex items-center justify-center">
    <div class="text-center text-white">
      <div class="text-4xl mb-4 animate-spin" aria-hidden="true">⚙️</div>
      <p class="text-ink-300" role="status" aria-live="polite">{{ statusMsg }}</p>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const statusMsg = ref('Completing sign-in...')

onMounted(async () => {
  // Handle explicit error from Google OAuth callback
  if (route.query.error) {
    const errorCode = route.query.error as string
    const errorMessages: Record<string, string> = {
      auth_failed: 'Google sign-in failed.',
      google_denied: 'Access was denied.',
      invalid_state: 'Session invalid.',
      csrf_detected: 'Security check failed.',
      session_expired: 'Session expired.',
    }
    statusMsg.value = errorMessages[errorCode] || 'Sign-in failed.'
    setTimeout(() => router.push('/login?error=' + errorCode), 2000)
    return
  }

  // Direct access to /auth/callback without OAuth flow — no code param
  if (!route.query.code) {
    statusMsg.value = 'Invalid sign-in attempt.'
    setTimeout(() => router.push('/login'), 1500)
    return
  }

  // Cookies are already set by /api/auth/google/callback. Just load the user.
  try {
    const me = await auth.fetchMe()
    if (me) {
      statusMsg.value = `Welcome, ${me.name || 'user'}!`
      setTimeout(() => router.push('/dashboard'), 500)
    } else {
      // fetchMe returned null — cookies may not be set yet (race) or invalid
      statusMsg.value = 'Completing sign-in...'
      // Retry once after short delay
      await new Promise(r => setTimeout(r, 1000))
      const me2 = await auth.fetchMe()
      if (me2) {
        statusMsg.value = `Welcome, ${me2.name || 'user'}!`
        setTimeout(() => router.push('/dashboard'), 500)
      } else {
        statusMsg.value = 'Failed to load user info.'
        setTimeout(() => router.push('/login?error=auth_failed'), 2000)
      }
    }
  } catch {
    statusMsg.value = 'Failed to complete sign-in.'
    setTimeout(() => router.push('/login?error=auth_failed'), 2000)
  }
})
</script>
