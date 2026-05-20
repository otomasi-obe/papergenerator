<template>
  <div class="min-h-screen bg-gradient-to-br from-brown-900 via-brown-800 to-stone-900 flex items-center justify-center px-4">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center mb-3">
          <img :src="logoWithText" alt="PaperFull" class="h-12 object-contain drop-shadow-[0_4px_24px_rgba(212,180,131,0.35)]" />
        </div>
        <p class="text-cream-200/70 text-sm">AI-powered academic paper writing tool</p>
      </div>

      <!-- Login Card -->
      <div class="bg-cream-50/5 border border-cream-200/15 rounded-2xl p-8 backdrop-blur-sm">
        <h2 class="text-cream-50 text-xl font-semibold mb-2 text-center">
          {{ isRegister ? 'Create an account' : 'Sign in to your account' }}
        </h2>
        <p class="text-cream-200/70 text-sm text-center mb-7">
          {{ isRegister ? 'Register with your email to get started' : 'Use your email or Google account' }}
        </p>

        <!-- Error Alert -->
        <div v-if="errorMsg" class="mb-5 flex items-center gap-2 bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded-xl p-3">
          <span>⚠️</span>
          <span>{{ errorMsg }}</span>
        </div>

        <!-- Email/Password Form -->
        <form @submit.prevent="handleSubmit" class="space-y-4 mb-5">
          <div v-if="isRegister">
            <label class="text-cream-200/70 text-xs block mb-1">Name</label>
            <input v-model="form.name" type="text" placeholder="Your full name"
              class="w-full px-4 py-3 bg-cream-50/5 border border-cream-200/15 rounded-xl text-cream-50 placeholder-cream-200/40 text-sm focus:outline-none focus:border-cream-300 focus:ring-1 focus:ring-cream-300" />
          </div>
          <div>
            <label class="text-cream-200/70 text-xs block mb-1">Email</label>
            <input v-model="form.email" type="email" placeholder="you@example.com"
              class="w-full px-4 py-3 bg-cream-50/5 border border-cream-200/15 rounded-xl text-cream-50 placeholder-cream-200/40 text-sm focus:outline-none focus:border-cream-300 focus:ring-1 focus:ring-cream-300" />
          </div>
          <div>
            <label class="text-cream-200/70 text-xs block mb-1">Password</label>
            <input v-model="form.password" type="password" placeholder="Min. 8 chars, mix of types"
              class="w-full px-4 py-3 bg-cream-50/5 border border-cream-200/15 rounded-xl text-cream-50 placeholder-cream-200/40 text-sm focus:outline-none focus:border-cream-300 focus:ring-1 focus:ring-cream-300" />
          </div>
          <!-- Cloudflare Turnstile widget — only shown for register flow -->
          <div v-if="isRegister && turnstileSiteKey" class="flex justify-center">
            <div ref="turnstileBox" class="cf-turnstile"
              :data-sitekey="turnstileSiteKey"
              data-theme="dark"
              data-callback="onTurnstileSuccess"></div>
          </div>
          <button type="submit" :disabled="submitting"
            class="w-full px-6 py-3.5 bg-cream-100 hover:bg-cream-50 text-brown-800 rounded-xl font-semibold transition-colors text-sm disabled:opacity-50">
            {{ submitting ? 'Please wait...' : (isRegister ? 'Create Account' : 'Sign In') }}
          </button>
        </form>

        <!-- Divider -->
        <div class="flex items-center gap-3 mb-5">
          <div class="flex-1 h-px bg-cream-200/15"></div>
          <span class="text-cream-200/50 text-xs">or</span>
          <div class="flex-1 h-px bg-cream-200/15"></div>
        </div>

        <!-- Google Login Button -->
        <button
          @click="auth.loginWithGoogle()"
          class="w-full flex items-center justify-center gap-3 px-6 py-3.5 bg-cream-50 text-brown-800 rounded-xl font-semibold hover:bg-cream-100 transition-all shadow-lg text-sm"
        >
          <svg class="w-5 h-5" viewBox="0 0 24 24">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg>
          Continue with Google
        </button>

        <!-- Toggle Register/Login -->
        <p class="text-center text-cream-200/70 text-sm mt-6">
          {{ isRegister ? 'Already have an account?' : "Don't have an account?" }}
          <button @click="toggleMode" class="text-cream-200 hover:text-cream-50 font-medium ml-1">
            {{ isRegister ? 'Sign In' : 'Register' }}
          </button>
        </p>

        <p class="text-center text-cream-200/40 text-xs mt-4">
          By signing in, you agree to our privacy policy.<br>
          Your papers are private and belong to you.
        </p>
      </div>

      <div class="text-center mt-6">
        <router-link to="/" class="text-cream-200/50 hover:text-cream-200 text-sm transition-colors">
          ← Back to home
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import api from '../api/index.js'
import logoWithText from '../image/logo-with-text.png'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const isRegister = ref(false)
const submitting = ref(false)
const formError = ref('')

// Turnstile site key dari env build-time. Kalau kosong, CAPTCHA dilewati FE
// dan backend juga skip (ENABLE_CAPTCHA=false). Aman untuk dev local.
const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''
const captchaToken = ref('')
const turnstileBox = ref(null)
let turnstileWidgetId = null

function loadTurnstileScript() {
  if (!turnstileSiteKey) return
  if (window.turnstile || document.querySelector('script[src*="turnstile/v0/api.js"]')) return
  const s = document.createElement('script')
  s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onTurnstileLoad'
  s.async = true
  s.defer = true
  document.head.appendChild(s)
}

function renderTurnstile() {
  if (!turnstileSiteKey || !window.turnstile || !turnstileBox.value) return
  if (turnstileWidgetId !== null) {
    try { window.turnstile.reset(turnstileWidgetId) } catch {}
  }
  turnstileWidgetId = window.turnstile.render(turnstileBox.value, {
    sitekey: turnstileSiteKey,
    callback: (token) => { captchaToken.value = token },
    'error-callback': () => { captchaToken.value = '' },
    theme: 'dark',
  })
}

window.onTurnstileLoad = () => { if (isRegister.value) renderTurnstile() }
window.onTurnstileSuccess = (token) => { captchaToken.value = token }

watch(isRegister, async (v) => {
  if (v && turnstileSiteKey) {
    await nextTick()
    renderTurnstile()
  } else {
    captchaToken.value = ''
  }
})

onMounted(() => loadTurnstileScript())

const form = reactive({
  name: '',
  email: '',
  password: '',
})

const errorMsg = computed(() => {
  if (formError.value) return formError.value
  if (route.query.error === 'auth_failed') return 'Google sign-in failed. Please try again.'
  return null
})

function toggleMode() {
  isRegister.value = !isRegister.value
  formError.value = ''
}

async function handleSubmit() {
  formError.value = ''

  if (!form.email || !form.password) {
    formError.value = 'Email and password are required'
    return
  }
  if (isRegister.value && !form.name) {
    formError.value = 'Name is required'
    return
  }
  if (form.password.length < 8) {
    formError.value = 'Password must be at least 8 characters'
    return
  }
  if (isRegister.value && turnstileSiteKey && !captchaToken.value) {
    formError.value = 'Please complete the CAPTCHA'
    return
  }

  submitting.value = true
  try {
    const endpoint = isRegister.value ? '/api/auth/register' : '/api/auth/login'
    const payload = isRegister.value
      ? { name: form.name, email: form.email, password: form.password, captcha_token: captchaToken.value }
      : { email: form.email, password: form.password }

    const res = await api.post(endpoint, payload)
    auth.setUser(res.data.user)
    router.push('/dashboard')
  } catch (err) {
    formError.value = err.response?.data?.error || 'Something went wrong. Please try again.'
    if (turnstileWidgetId !== null && window.turnstile) {
      try { window.turnstile.reset(turnstileWidgetId) } catch {}
      captchaToken.value = ''
    }
  } finally {
    submitting.value = false
  }
}
</script>
