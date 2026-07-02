<template>
 <main class="min-h-screen bg-gradient-to-br from-navy-900 via-navy-800 to-navy-900 flex items-center justify-center px-4">
 <div class="w-full max-w-md">
 <!-- Logo -->
 <div class="text-center mb-8">
 <div class="inline-flex items-center justify-center mb-3">
 <img :src="logoWithText" alt="PaperFull" class="h-12 object-contain drop-shadow-[0_4px_24px_rgba(11,64,136,0.25)]" />
 </div>
 <p class="text-cream-200/80 text-sm">AI-powered academic paper writing tool</p>
 </div>

 <!-- Login Card -->
 <div class="bg-cream-50/10 border border-cream-300/40 rounded-2xl p-8 backdrop-blur-sm">
 <h2 class="text-cream-50 text-xl font-semibold mb-2 text-center font-serif">
 {{ isRegister ? 'Create an account' : 'Sign in to your account' }}
 </h2>
 <p class="text-cream-200/80 text-sm text-center mb-7">
 {{ isRegister ? 'Register with your email to get started' : 'Use your email or Google account' }}
 </p>

 <!-- Error Alert -->
 <div v-if="errorMsg" class="mb-5 flex items-center gap-2 bg-red-500/15 border border-red-500/40 text-red-300 dark:text-red-400 text-sm rounded-xl p-3">
 <span>⚠️</span>
 <span>{{ errorMsg }}</span>
 </div>

 <!-- Email/Password Form -->
 <form @submit.prevent="handleSubmit" class="space-y-4 mb-5">
 <div v-if="isRegister" class="block">
 <label for="login-name" class="block text-xs font-medium mb-1 text-cream-100/90">
 Name <span class="text-red-400">*</span>
 </label>
 <input id="login-name" v-model="form.name" type="text" placeholder="Your full name"
 autocomplete="name" aria-required="true"
 class="w-full px-4 py-3 bg-cream-50/10 border border-cream-300/40 rounded-xl text-cream-50 placeholder-cream-300/60 text-sm focus:outline-none focus:border-navy-500 focus:ring-1 focus:ring-[#238f7f]/30" />
 </div>
 <div class="block">
 <label for="login-email" class="block text-xs font-medium mb-1 text-cream-100/90">
 Email <span class="text-red-400">*</span>
 </label>
 <input id="login-email" v-model="form.email" type="email" placeholder="you@example.com"
 autocomplete="email" inputmode="email" aria-required="true"
 class="w-full px-4 py-3 bg-cream-50/10 border border-cream-300/40 rounded-xl text-cream-50 placeholder-cream-300/60 text-sm focus:outline-none focus:border-navy-500 focus:ring-1 focus:ring-[#238f7f]/30" />
 </div>
 <div class="block">
 <label for="login-password" class="block text-xs font-medium mb-1 text-cream-100/90">
 Password <span class="text-red-400">*</span>
 </label>
 <div class="relative">
 <input id="login-password" v-model="form.password" :type="showPassword ? 'text' : 'password'" placeholder="Min. 8 chars, mix of types"
 :autocomplete="isRegister ? 'new-password' : 'current-password'" aria-required="true"
 class="w-full px-4 py-3 bg-cream-50/10 border border-cream-300/40 rounded-xl text-cream-50 placeholder-cream-300/60 text-sm focus:outline-none focus:border-navy-500 focus:ring-1 focus:ring-[#238f7f]/30 pr-12" />
 <button
 type="button"
 @click="showPassword = !showPassword"
 :aria-label="showPassword ? 'Hide password' : 'Show password'"
 class="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-cream-200/80 hover:text-cream-50 transition"
 >
 {{ showPassword ? 'Hide' : 'Show' }}
 </button>
 </div>
 </div>
 <!-- Cloudflare Turnstile widget — only shown for register flow -->
 <div v-if="isRegister && turnstileSiteKey" class="flex justify-center">
 <div ref="turnstileBox" class="cf-turnstile"
 :data-sitekey="turnstileSiteKey"
 data-theme="dark"
 data-callback="onTurnstileSuccess"></div>
 </div>
 <!-- Math CAPTCHA widget — for register (always) and login (when required) -->
 <div v-if="showCaptcha" class="block">
 <label class="block text-xs font-medium mb-1 text-cream-100/90">
 Security Check
 </label>
 <CaptchaWidget
 ref="captchaWidget"
 :required="showCaptcha"
 />
 </div>
 <button type="submit" :disabled="submitting"
 class="w-full px-6 py-3.5 bg-amber-500 hover:bg-amber-400 active:bg-amber-600 text-white rounded-xl font-semibold transition text-sm disabled:opacity-50 active:scale-95 shadow-lg shadow-amber-500/25 border border-amber-400/30">
 {{ submitting ? 'Please wait...' : (isRegister ? 'Create Account' : 'Sign In') }}
 </button>
 </form>

 <!-- Divider -->
 <div class="flex items-center gap-3 mb-5">
 <div class="flex-1 h-px bg-cream-300/40"></div>
 <span class="text-cream-200/80 text-xs">or</span>
 <div class="flex-1 h-px bg-cream-300/40"></div>
 </div>

 <!-- Google Login Button -->
 <button
 @click="auth.loginWithGoogle()"
 class="w-full flex items-center justify-center gap-3 px-6 py-3.5 bg-white hover:bg-cream-100 text-navy-900 rounded-xl font-semibold transition-all shadow-lg text-sm active:scale-95 border border-cream-300/40"
 >
 <svg class="w-5 h-5" viewBox="0 0 24 24">
 <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
 <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
 <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
 <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66-2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
 </svg>
 Continue with Google
 </button>

 <!-- Toggle Register/Login -->
 <p class="text-center text-cream-200/80 text-sm mt-6">
 {{ isRegister ? 'Already have an account?' : "Don't have an account?" }}
 <button @click="toggleMode" class="text-cream-100 hover:text-cream-50 font-medium ml-1">
 {{ isRegister ? 'Sign In' : 'Register' }}
 </button>
 </p>

 <p class="text-center text-cream-200/70 text-xs mt-4">
 By signing in, you agree to our privacy policy.<br>
 Your papers are private and belong to you.
 </p>
 </div>

 <div class="text-center mt-6">
 <router-link to="/" class="text-cream-200/80 hover:text-cream-200 text-sm transition">
 ← Back to home
 </router-link>
 </div>
 </div>
 </main>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import api from '../api/index.js'
import CaptchaWidget from '../components/CaptchaWidget.vue'
const logoWithText = '/assets/logo-with-text.png'

// Extend Window interface for Turnstile
declare global {
 interface Window {
 turnstile?: any
 onTurnstileLoad?: () => void
 onTurnstileSuccess?: (token: string) => void
 }
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const isRegister = ref(false)
const submitting = ref(false)
const formError = ref('')
const showPassword = ref(false)

// Turnstile site key dari env build-time. Kalau kosong, CAPTCHA dilewati FE
// dan backend juga skip (ENABLE_CAPTCHA=false). Aman untuk dev local.
const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''
const captchaToken = ref('')
const turnstileBox = ref(null)
let turnstileWidgetId = null

// Math CAPTCHA state
const captchaWidget = ref<InstanceType<typeof CaptchaWidget> | null>(null)
const captchaRequired = ref(false)
const captchaEnabled = ref(false)

// Show captcha widget for register (when enabled) or login (when required)
const showCaptcha = computed(() => {
 if (isRegister.value) return captchaEnabled.value
 return captchaRequired.value
})

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
 // Reload captcha widget when switching modes
 if (captchaWidget.value) {
 captchaWidget.value.loadCaptcha()
 }
})

async function checkCaptchaStatus() {
 try {
 const res = await api.get('/api/auth/captcha/status')
 captchaEnabled.value = res.data.captcha_enabled
 captchaRequired.value = res.data.captcha_required
 } catch {
 // If check fails, assume disabled (dev mode)
 captchaEnabled.value = false
 captchaRequired.value = false
 }
}

onMounted(() => {
 loadTurnstileScript()
 checkCaptchaStatus()
})

const form = reactive({
 name: '',
 email: '',
 password: '',
})

const errorMessages: Record<string, string> = {
 auth_failed: 'Google sign-in failed. Please try again or use email instead.',
 google_denied: 'You denied access. Please click "Continue with Google" and accept the permissions.',
 email_not_allowed: 'This Google account is not authorized. Only specific emails can log in.',
 invalid_state: 'Sign-in session invalid. Please close this tab and sign in again.',
 csrf_detected: 'Security check failed. Please sign in again.',
 session_expired: 'Sign-in session expired. Please try again.',
}

const errorMsg = computed(() => {
 if (formError.value) return formError.value
 const code = route.query.error as string
 if (code && errorMessages[code]) return errorMessages[code]
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

 // Build payload
 const payload: Record<string, unknown> = isRegister.value
 ? { name: form.name, email: form.email, password: form.password, captcha_token: captchaToken.value }
 : { email: form.email, password: form.password }

 // Attach math CAPTCHA answer if widget is visible
 if (showCaptcha.value && captchaWidget.value) {
 const widget = captchaWidget.value
 if (!widget.answer || !widget.captchaId) {
 formError.value = 'Please complete the security check'
 submitting.value = false
 return
 }
 payload.math_captcha_id = widget.captchaId
 payload.math_captcha_answer = widget.answer
 }

 const res = await api.post(endpoint, payload)
 auth.setUser(res.data.user)
 router.push('/dashboard')
 } catch (err: any) {
 const responseData = err.response?.data
 formError.value = responseData?.error || 'Something went wrong. Please try again.'

 // If server says captcha is required, show the widget and reload it
 if (responseData?.captcha_required) {
 captchaRequired.value = true
 await nextTick()
 if (captchaWidget.value) {
 captchaWidget.value.loadCaptcha()
 }
 }

 // Reset Turnstile token on error
 if (turnstileWidgetId !== null && window.turnstile) {
 try { window.turnstile.reset(turnstileWidgetId) } catch {}
 captchaToken.value = ''
 }
 } finally {
 submitting.value = false
 }
}
</script>
