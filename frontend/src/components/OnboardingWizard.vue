<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="open"
        class="fixed inset-0 z-[100] flex items-center justify-center bg-ash-900/60 backdrop-blur-sm"
      >
        <Transition name="slide" mode="out-in">
          <div
            :key="step"
            class="bg-white dark:bg-ash-800 rounded-xl border border-cream-300 dark:border-ash-700 shadow-2xl w-full max-w-md mx-4 overflow-hidden"
          >
            <!-- Step Indicator -->
            <div class="px-6 pt-5 pb-2">
              <div class="flex items-center justify-between mb-1">
                <span class="text-xs text-ink-500 dark:text-ink-300">Langkah {{ step }}/4</span>
                <button
                  @click="skip"
                  class="text-xs text-ink-500 dark:text-ink-300 hover:text-ink-900 dark:hover:text-ink-50 transition-colors"
                >
                  Lewati →
                </button>
              </div>
              <div class="w-full bg-cream-200 dark:bg-ash-700 rounded-full h-1.5">
                <div
                  class="bg-navy-600 dark:bg-cream-300 h-1.5 rounded-full transition-all duration-300"
                  :style="{ width: `${(step / 4) * 100}%` }"
                />
              </div>
            </div>

            <!-- Step Content -->
            <div class="px-6 py-5">
              <!-- Step 1: Welcome + Nickname -->
              <div v-if="step === 1">
                <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50 mb-1">
                  Selamat datang! 👋
                </h2>
                <p class="text-sm text-ink-500 dark:text-ink-300 mb-5">
                  PaperFull membantu Anda menulis paper akademik dengan bantuan AI — dari riset literatur, drafting, hingga formatting. Mari mulai dengan mengenal Anda lebih dekat.
                </p>
                <div>
                  <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Nama Panggilan</label>
                  <input
                    v-model="form.nickname"
                    type="text"
                    class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-navy-500/30 dark:focus:ring-cream-300/30"
                    :placeholder="nicknamePlaceholder"
                  />
                </div>
              </div>

              <!-- Step 2: Full Name -->
              <div v-else-if="step === 2">
                <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50 mb-1">
                  Nama Lengkap
                </h2>
                <p class="text-sm text-ink-500 dark:text-ink-300 mb-5">
                  Nama lengkap Anda akan digunakan pada halaman judul paper.
                </p>
                <div>
                  <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Nama Lengkap</label>
                  <input
                    v-model="form.name"
                    type="text"
                    class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-navy-500/30 dark:focus:ring-cream-300/30"
                    placeholder="Masukkan nama lengkap Anda"
                  />
                </div>
              </div>

              <!-- Step 3: Institution -->
              <div v-else-if="step === 3">
                <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50 mb-1">
                  Institusi
                </h2>
                <p class="text-sm text-ink-500 dark:text-ink-300 mb-5">
                  Institusi atau kampus Anda akan ditampilkan pada paper yang dihasilkan.
                </p>
                <div>
                  <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Institusi / Kampus</label>
                  <input
                    v-model="form.institution"
                    type="text"
                    class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-navy-500/30 dark:focus:ring-cream-300/30"
                    placeholder="Contoh: Universitas AI Sedunia"
                  />
                </div>
              </div>

              <!-- Step 4: Language -->
              <div v-else-if="step === 4">
                <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50 mb-1">
                  Bahasa & Gaya Penulisan
                </h2>
                <p class="text-sm text-ink-500 dark:text-ink-300 mb-5">
                  AI akan menggunakan bahasa ini saat menulis paper dan merespons chat.
                </p>
                <div class="grid grid-cols-2 gap-3">
                  <button
                    v-for="lang in langOptions"
                    :key="lang.value"
                    @click="form.preferred_language = lang.value"
                    :class="[
                      'flex items-center gap-3 p-4 rounded-lg border-2 transition-all active:scale-95',
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
            </div>

            <!-- Navigation Buttons -->
            <div class="px-6 pb-5 flex gap-3">
              <button
                v-if="step > 1"
                @click="step--"
                class="flex-1 px-4 py-2.5 border border-cream-300 dark:border-ash-600 text-ink-700 dark:text-ink-300 rounded-lg text-sm font-medium hover:bg-cream-100 dark:hover:bg-ash-700 active:scale-95 transition-transform"
              >
                ← Kembali
              </button>
              <button
                v-if="step < 4"
                @click="step++"
                class="flex-1 px-4 py-2.5 bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-semibold active:scale-95 transition-transform"
              >
                Lanjut →
              </button>
              <button
                v-else
                @click="save"
                :disabled="saving"
                class="flex-1 px-4 py-2.5 bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-semibold disabled:opacity-50 active:scale-95 transition-transform"
              >
                <span v-if="saving">Menyimpan...</span>
                <span v-else>Simpan & Mulai ✨</span>
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, reactive, watch, computed } from 'vue'
import api from '../api/index'

const props = defineProps({
  open: { type: Boolean, required: true },
  user: { type: Object, default: null },
})

const emit = defineEmits(['complete'])

const step = ref(1)
const saving = ref(false)

const form = reactive({
  nickname: '',
  name: '',
  institution: '',
  preferred_language: 'id',
})

const langOptions = [
  { value: 'id', label: 'Bahasa Indonesia', icon: '🇮🇩', desc: 'Paper & chat dalam Bahasa Indonesia' },
  { value: 'en', label: 'English', icon: '🔤', desc: 'Paper & chat in English' },
]

const nicknamePlaceholder = computed(() => {
  if (props.user?.email) {
    return props.user.email.split('@')[0]
  }
  return 'Nama panggilan Anda'
})

watch(() => props.open, (val) => {
  if (val && props.user) {
    form.nickname = props.user.nickname || ''
    form.name = props.user.name || ''
    form.institution = props.user.institution || ''
    form.preferred_language = props.user.preferred_language || 'id'
    step.value = 1
  }
})

function skip() {
  emit('complete')
}

async function save() {
  saving.value = true
  try {
    const payload: any = {
      nickname: form.nickname || (props.user?.email?.split('@')[0] ?? ''),
      name: form.name,
      institution: form.institution,
      preferred_language: form.preferred_language,
    }
    await api.patch('/api/auth/me/settings', payload)
    emit('complete')
  } catch (err: any) {
    console.error('Failed to save onboarding settings:', err)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.slide-enter-from {
  transform: translateX(30px);
  opacity: 0;
}
.slide-leave-to {
  transform: translateX(-30px);
  opacity: 0;
}
</style>
