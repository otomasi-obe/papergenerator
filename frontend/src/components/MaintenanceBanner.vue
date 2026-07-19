<template>
  <transition
    enter-active-class="transition-all duration-300 ease-out"
    enter-from-class="-translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transition-all duration-200 ease-in"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="-translate-y-full opacity-0"
  >
    <div v-if="visible" class="fixed top-0 inset-x-0 z-[1000] pointer-events-auto">
      <div class="bg-gradient-to-r from-navy-700 via-navy-800 to-navy-700 text-white shadow-lg border-b border-navy-900/50">
        <div class="max-w-7xl mx-auto px-4 py-2.5 flex items-start gap-3">
          <!-- Logo -->
          <div class="flex-shrink-0 w-8 h-8 mt-0.5 rounded-lg bg-white/20 ring-1 ring-white/40 flex items-center justify-center backdrop-blur-sm">
            <svg class="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
            </svg>
          </div>
          <div class="flex-1 text-xs sm:text-sm leading-relaxed font-medium space-y-1 whitespace-pre-wrap">
            <p v-html="message"></p>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <label class="flex items-center gap-1.5 cursor-pointer text-xs text-navy-100/90">
              <input type="checkbox" v-model="dismissedForever" @change="saveDismissedForever" class="w-4 h-4 rounded border-navy-600 bg-navy-800 text-navy-500 focus:ring-navy-500" />
              Jangan tampilkan lagi
            </label>
            <button @click="dismiss" class="flex-shrink-0 p-1 rounded-md bg-white/10 hover:bg-white/20 transition-colors ring-1 ring-white/30" aria-label="Tutup pemberitahuan">
              <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api/index.js'

const DISMISSED_KEY = 'maintenance-banner-dismissed' // sessionStorage key
const DISMISSED_FOREVER_KEY = 'maintenance-banner-dismissed-forever' // localStorage key

const visible = ref(false)
const message = ref('')
const dismissedForever = ref(false)
let maintenanceId: string | null = null

async function loadMaintenance() {
  try {
    const res = await api.get('/api/dev/maintenance-banner/public')
    const data = res.data
    if (data.enabled && data.message) {
      maintenanceId = data.id || data.updated_at
      message.value = data.message
      // Check if user dismissed this specific maintenance
      const dismissedId = sessionStorage.getItem(DISMISSED_KEY)
      const dismissedForeverId = localStorage.getItem(DISMISSED_FOREVER_KEY)
      if (dismissedId && maintenanceId && dismissedId === maintenanceId) {
        visible.value = false
      } else if (dismissedForeverId && maintenanceId && dismissedForeverId === maintenanceId) {
        visible.value = false
        dismissedForever.value = true
      } else {
        // Show banner if not dismissed
        visible.value = true
      }
    } else {
      visible.value = false
    }
  } catch {
    visible.value = false
  }
}

function dismiss() {
  visible.value = false
  // No persistence — banner will reappear on refresh unless user checked "Jangan tampilkan lagi"
}

function saveDismissedForever() {
  if (maintenanceId && dismissedForever.value) {
    localStorage.setItem(DISMISSED_FOREVER_KEY, maintenanceId)
  } else {
    localStorage.removeItem(DISMISSED_FOREVER_KEY)
  }
}

// Listen for banner updates from dev room save
function onBannerUpdate() {
  loadMaintenance()
}

onMounted(() => {
  loadMaintenance()
  window.addEventListener('maintenance-banner-updated', onBannerUpdate)
})

onUnmounted(() => {
  window.removeEventListener('maintenance-banner-updated', onBannerUpdate)
})
</script>