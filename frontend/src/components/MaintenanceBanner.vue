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
          <!-- Logo -->
          <div class="flex-shrink-0 w-8 h-8 rounded-lg bg-white/20 ring-1 ring-white/40 flex items-center justify-center backdrop-blur-sm">
            <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
            </svg>
          </div>
          <div class="flex-1 text-xs sm:text-sm leading-snug font-medium">
            <span class="font-bold">Pemeliharaan:</span>
            Pemeliharaan sistem akan segera di lakukan mulai sekarang sampai waktu yang akan di tentukan.
            Mohon maaf jika ada sistem yang tidak bisa di gunakan sementara.
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
