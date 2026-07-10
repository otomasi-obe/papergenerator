<template>
  <header class="bg-navy-900/95 backdrop-blur-sm border-b border-white/10 sticky top-0 z-40">
    <div class="max-w-7xl mx-auto px-8 py-4 flex items-center justify-between">
      <!-- Logo -->
      <router-link to="/" class="flex items-center gap-2.5 group">
        <img :src="logoWithText" alt="PaperFull" class="h-9 object-contain" />
        <span class="text-xs bg-cream-300/20 text-cream-200 px-2 py-0.5 rounded-full font-medium">Multi-Journal</span>
      </router-link>

      <!-- Right side nav -->
      <div class="flex items-center gap-3">
      <!-- Update Button -->
      <UpdateHistoryButton />

      <!-- Info Dropdown -->
        <div class="relative" ref="dropdownRef">
          <button
            @click="dropdownOpen = !dropdownOpen"
            class="flex items-center gap-1.5 px-4 py-2 bg-white/95 hover:bg-amber-50 text-amber-900 border border-amber-300/50 shadow-sm rounded-full font-bold transition-all text-sm active:scale-95"
          >
            {{ t('nav.info') }}
            <svg 
              class="w-4 h-4 transition-transform duration-200"
              :class="{ 'rotate-180': dropdownOpen }"
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          <!-- Dropdown Menu -->
          <transition
            enter-active-class="transition ease-out duration-200"
            enter-from-class="opacity-0 translate-y-1"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition ease-in duration-150"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 translate-y-1"
          >
            <div
              v-if="dropdownOpen"
              class="absolute right-0 mt-2 w-56 bg-white border border-amber-200 rounded-xl shadow-xl overflow-hidden z-50"
            >
              <router-link
                to="/terms"
                class="block px-4 py-3 text-sm text-amber-900 hover:bg-amber-50 transition-colors border-b border-amber-100 last:border-b-0"
                @click="dropdownOpen = false"
              >
                <div class="font-semibold">{{ t('dropdown.terms') }}</div>
                <div class="text-xs text-amber-700 mt-0.5">{{ t('dropdown.termsDesc') }}</div>
              </router-link>
              <router-link
                to="/refund"
                class="block px-4 py-3 text-sm text-amber-900 hover:bg-amber-50 transition-colors border-b border-amber-100 last:border-b-0"
                @click="dropdownOpen = false"
              >
                <div class="font-semibold">{{ t('dropdown.refund') }}</div>
                <div class="text-xs text-amber-700 mt-0.5">{{ t('dropdown.refundDesc') }}</div>
              </router-link>
              <router-link
                to="/faq"
                class="block px-4 py-3 text-sm text-amber-900 hover:bg-amber-50 transition-colors border-b border-amber-100 last:border-b-0"
                @click="dropdownOpen = false"
              >
                <div class="font-semibold">{{ t('dropdown.faq') }}</div>
                <div class="text-xs text-amber-700 mt-0.5">{{ t('dropdown.faqDesc') }}</div>
              </router-link>
              <router-link
                to="/contact"
                class="block px-4 py-3 text-sm text-amber-900 hover:bg-amber-50 transition-colors border-b border-amber-100 last:border-b-0"
                @click="dropdownOpen = false"
              >
                <div class="font-semibold">{{ t('dropdown.contact') }}</div>
                <div class="text-xs text-amber-700 mt-0.5">{{ t('dropdown.contactDesc') }}</div>
              </router-link>
            </div>
          </transition>
        </div>

        <!-- Language Toggle -->
        <button
          @click="toggleLanguage"
          class="flex items-center gap-1.5 px-4 py-2 bg-white/95 hover:bg-amber-50 text-amber-900 border border-amber-300/50 rounded-full font-bold transition-all text-sm active:scale-95"
          :title="locale === 'id' ? 'Switch to English' : 'Ganti ke Bahasa Indonesia'"
        >
          {{ locale === 'id' ? '🇮🇩 ID' : '🇬🇧 EN' }}
        </button>

        <!-- Sign In Button -->
        <router-link to="/login"
          class="flex items-center gap-2 px-5 py-2 bg-white hover:bg-amber-50 text-amber-900 border border-amber-300 rounded-full font-bold transition-all text-sm active:scale-95"
        >
          {{ t('nav.signIn') }}
        </router-link>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../composables/useI18n'
import UpdateHistoryButton from './UpdateHistoryButton.vue'

const logoWithText = '/assets/logo-with-text.png'

const { t, locale, setLocale } = useI18n()

const dropdownOpen = ref(false)
const dropdownRef = ref<HTMLElement | null>(null)

function toggleLanguage() {
  setLocale(locale.value === 'id' ? 'en' : 'id')
}

function handleClickOutside(event: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    dropdownOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>
