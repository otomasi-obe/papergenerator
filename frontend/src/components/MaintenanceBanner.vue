<template>
  <transition
    enter-active-class="transition-all duration-300 ease-out"
    enter-from-class="-translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transition-all duration-200 ease-in"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="-translate-y-full opacity-0"
  >
    <div
      v-if="visible"
      class="fixed top-0 inset-x-0 z-[1000] pointer-events-auto"
    >
      <div class="bg-gradient-to-r from-amber-600 via-amber-700 to-amber-600 text-white shadow-lg border-b border-amber-800/50">
        <div class="max-w-7xl mx-auto px-4 py-2.5 flex items-center gap-3">
          <div class="flex-shrink-0 w-7 h-7 rounded-md bg-white/15 ring-1 ring-white/40 flex items-center justify-center backdrop-blur-sm">
            <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.094-4.165a3.75 3.75 0 11-5.304 5.304m5.304-5.304L21 7.5m-5.304 5.304L17.25 13.5"/>
            </svg>
          </div>
          <div class="flex-1 text-xs sm:text-sm leading-snug font-medium">
            <span class="font-bold">Pemberitahuan:</span>
            Sistem penyisihan dan penyesuaian badge serta benefit untuk semua akun sedang dalam pemeliharaan dan akan diterapkan pada waktu yang akan ditentukan.
            <span class="block sm:inline opacity-95 mt-0.5 sm:mt-0 sm:ml-1">— Terima kasih, Paperfull Developer Tim</span>
          </div>
          <button
            @click="dismiss"
            class="flex-shrink-0 p-1 rounded-md bg-white/10 hover:bg-white/20 transition-colors ring-1 ring-white/30"
            aria-label="Tutup pemberitahuan"
          >
            <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const DISMISSED_KEY = 'maintenance-banner-dismissed'
const visible = ref(false)

onMounted(() => {
  const dismissed = localStorage.getItem(DISMISSED_KEY)
  if (!dismissed) {
    visible.value = true
  }
})

function dismiss() {
  visible.value = false
  localStorage.setItem(DISMISSED_KEY, String(Date.now()))
}
</script>
