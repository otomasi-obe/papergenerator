<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-900">
    <AppHeader />
    <div class="max-w-2xl mx-auto px-4 py-8">
      <div class="flex items-center gap-3 mb-8">
        <router-link to="/dashboard" class="text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50 active:scale-95 transition-transform">
          ← Kembali
        </router-link>
        <h1 class="text-xl font-semibold text-ink-900 dark:text-ink-50">⚙️ Settings</h1>
      </div>

      <!-- Toast -->
      <div v-if="toast.show" :class="['fixed top-4 right-4 z-50 px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium text-white transition-all', toast.type === 'success' ? 'bg-emerald-600' : 'bg-red-600']">
        {{ toast.message }}
      </div>

      <!-- Profile Section -->
      <div class="bg-white dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700 p-6 mb-6">
        <h2 class="text-base font-semibold text-ink-900 dark:text-ink-50 mb-4">Profil</h2>
        <div class="space-y-4">
          <div>
            <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Nama Lengkap</label>
            <input
              v-model="form.name"
              type="text"
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm"
              placeholder="Nama lengkap Anda"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Nama Panggilan</label>
            <input
              v-model="form.nickname"
              type="text"
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm"
              placeholder="Bagaimana AI memanggil Anda"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Institusi / Kampus</label>
            <input
              v-model="form.institution"
              type="text"
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm"
              placeholder="Contoh: Universitas AI Sedunia"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Email</label>
            <input
              :value="auth.user?.email"
              type="email"
              disabled
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-cream-100 dark:bg-ash-700 text-ink-500 dark:text-ink-300 rounded-lg text-sm cursor-not-allowed opacity-70"
            />
          </div>
        </div>
      </div>

      <!-- Language Section -->
      <div class="bg-white dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700 p-6 mb-6">
        <h2 class="text-base font-semibold text-ink-900 dark:text-ink-50 mb-4">🌐 Bahasa & Gaya Penulisan</h2>
        <p class="text-xs text-ink-500 dark:text-ink-300 mb-3">
          AI akan menggunakan gaya bahasa ini saat menulis paper dan merespons chat.
        </p>
        <div class="grid grid-cols-2 gap-3">
          <button
            v-for="lang in langOptions"
            :key="lang.value"
            @click="form.preferred_language = lang.value"
            :class="[
              'flex items-center gap-3 p-4 rounded-lg border-2 transition-all active:scale-95 transition-transform',
              form.preferred_language === lang.value
                ? 'border-navy-500 dark:border-cream-300 bg-navy-50 dark:bg-navy-900/30'
                : 'border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-900 hover:border-cream-400 dark:hover:border-ash-500',
            ]"
          >
            <span class="text-2xl">{{ lang.icon }}</span>
            <div class="text-left">
              <div class="text-sm font-medium text-ink-900 dark:text-ink-50">{{ lang.label }}</div>
              <div class="text-[11px] text-ink-500 dark:text-ink-300">{{ lang.desc }}</div>
            </div>
          </button>
        </div>
      </div>

      <!-- Password Section -->
      <div class="bg-white dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700 p-6 mb-6">
        <h2 class="text-base font-semibold text-ink-900 dark:text-ink-50 mb-4">🔒 Ganti Password</h2>
        <div class="space-y-4">
          <div v-if="auth.user?.password_hash || hasPassword">
            <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Password Saat Ini</label>
            <input
              v-model="form.current_password"
              type="password"
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm"
              placeholder="Masukkan password saat ini"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Password Baru</label>
            <input
              v-model="form.new_password"
              type="password"
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm"
              placeholder="Minimal 6 karakter"
            />
          </div>
          <div>
            <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Konfirmasi Password Baru</label>
            <input
              v-model="form.confirm_password"
              type="password"
              class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm"
              placeholder="Ulangi password baru"
            />
          </div>
        </div>
      </div>

      <!-- Save Button -->
      <button
        @click="saveSettings"
        :disabled="saving"
        class="w-full px-6 py-3 bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-semibold disabled:opacity-50 active:scale-95 transition-transform mb-4"
      >
        <span v-if="saving">Menyimpan...</span>
        <span v-else>Simpan Pengaturan</span>
      </button>

      <!-- Tour Guide Button -->
      <button
        @click="startTour"
        class="w-full px-6 py-3 bg-cream-100 dark:bg-ash-700 hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-900 dark:text-ink-50 border border-cream-300 dark:border-ash-600 rounded-lg text-sm font-medium active:scale-95 transition-transform"
      >
        <span class="flex items-center justify-center gap-2">
          <span>🧭</span>
          <span>Panduan Saya</span>
        </span>
        <span class="text-[11px] text-ink-500 dark:text-ink-300 block mt-1">Mulai ulang tur panduan penggunaan PaperFull</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppHeader from '../components/AppHeader.vue'
import api from '../api'

const auth = useAuthStore()
const router = useRouter()

const saving = ref(false)
const hasPassword = ref(false)

const langOptions = [
  { value: 'id', label: 'Bahasa Indonesia', icon: '🇮🇩', desc: 'Paper & chat dalam Bahasa Indonesia' },
  { value: 'en', label: 'English', icon: '🔤', desc: 'Paper & chat in English' },
]

const form = reactive({
  name: '',
  nickname: '',
  institution: '',
  preferred_language: 'id',
  current_password: '',
  new_password: '',
  confirm_password: '',
})

const toast = reactive({
  show: false,
  message: '',
  type: 'success' as 'success' | 'error',
})

function showToast(message: string, type: 'success' | 'error' = 'success') {
  toast.message = message
  toast.type = type
  toast.show = true
  setTimeout(() => { toast.show = false }, 3000)
}

onMounted(async () => {
  await auth.fetchMe()
  const u = auth.user
  if (u) {
    form.name = u.name || ''
    // Default nickname from email if not set
    form.nickname = u.nickname || (u.email ? u.email.split('@')[0] : '')
    form.institution = u.institution || ''
    form.preferred_language = u.preferred_language || 'id'
    hasPassword.value = !!u.password_hash
  }
})

async function saveSettings() {
  if (form.new_password && form.new_password !== form.confirm_password) {
    showToast('Konfirmasi password tidak cocok', 'error')
    return
  }
  if (form.new_password && form.new_password.length < 6) {
    showToast('Password minimal 6 karakter', 'error')
    return
  }

  saving.value = true
  try {
    const payload: any = {
      name: form.name,
      nickname: form.nickname,
      institution: form.institution,
      preferred_language: form.preferred_language,
    }
    if (form.new_password) {
      payload.current_password = form.current_password
      payload.new_password = form.new_password
    }

    const res = await api.patch('/api/auth/me/settings', payload)
    auth.setUser(res.data)
    showToast('Pengaturan berhasil disimpan!')
    // Clear password fields
    form.current_password = ''
    form.new_password = ''
    form.confirm_password = ''
  } catch (err: any) {
    showToast(err.response?.data?.error || 'Gagal menyimpan pengaturan', 'error')
  } finally {
    saving.value = false
  }
}

function startTour() {
  // Clear tour flag so it restarts on dashboard
  localStorage.removeItem('pf_tour_done')
  router.push({ name: 'dashboard', query: { tour: '1' } })
}
</script>
