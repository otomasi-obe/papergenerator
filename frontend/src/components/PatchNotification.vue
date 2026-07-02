<template>
  <transition
    enter-active-class="transition-all duration-500 ease-out"
    enter-from-class="translate-y-full opacity-0 scale-95"
    enter-to-class="translate-y-0 opacity-100 scale-100"
    leave-active-class="transition-all duration-300 ease-in"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="translate-y-full opacity-0"
  >
    <div v-if="visible" class="fixed bottom-6 right-6 z-[999] max-w-sm w-full pointer-events-auto">
      <div class="relative bg-white/95 dark:bg-ash-800/95 backdrop-blur-xl rounded-2xl shadow-2xl shadow-black/20 border border-amber-300/30 dark:border-amber-600/20 overflow-hidden">
        <!-- Top accent bar -->
        <div class="h-1 bg-gradient-to-r from-amber-400 via-emerald-400 to-amber-400 animate-gradient-x"></div>

        <!-- Close button -->
        <button
          @click="dismiss"
          class="absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-full text-ink-400 hover:text-ink-600 dark:text-ink-500 dark:hover:text-ink-300 hover:bg-ink-100 dark:hover:bg-ash-700 transition-colors"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>

        <div class="px-5 pt-4 pb-5">
          <!-- Header -->
          <div class="flex items-center gap-2.5 mb-3">
            <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center text-white text-xs font-black shadow-sm">
              🚀
            </div>
            <div>
              <h4 class="text-sm font-bold text-ink-900 dark:text-ink-50 leading-tight">{{ data?.title || 'Update Available' }}</h4>
              <p class="text-[11px] text-ink-400 dark:text-ink-500">{{ formatDate(data?.released) }}</p>
            </div>
          </div>

          <!-- Changes summary -->
          <div class="space-y-1.5 mb-4">
            <div
              v-for="(change, i) in (data?.changes || []).slice(0, 5)"
              :key="i"
              class="flex items-center gap-2.5 text-xs leading-relaxed change-item"
              :style="{ animationDelay: (i * 80 + 300) + 'ms' }"
            >
              <span :class="badgeClass(change.type)" class="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase flex-shrink-0">
                {{ change.type === 'new' ? '✦ NEW' : change.type === 'fix' ? '🔧 FIX' : '⚡ UPD' }}
              </span>
              <span class="text-ink-600 dark:text-ink-300">{{ change.text }}</span>
            </div>
          </div>

          <!-- Footer -->
          <button
            @click="dismiss"
            class="w-full py-2 text-xs font-semibold text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 hover:bg-amber-100 dark:hover:bg-amber-900/40 rounded-lg transition-colors"
          >
            Got it 👍
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface Change {
  type: 'new' | 'fix' | 'improvement'
  text: string
}

interface VersionData {
  version: string
  released: string
  title: string
  changes: Change[]
}

const visible = ref(false)
const data = ref<VersionData | null>(null)

function badgeClass(type: string) {
  if (type === 'new') return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
  if (type === 'fix') return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400'
  return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
}

function formatDate(s?: string) {
  if (!s) return ''
  return new Date(s).toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' })
}

function dismiss() {
  visible.value = false
}

onMounted(async () => {
  try {
    const res = await fetch('/version.json?t=' + Date.now())
    if (!res.ok) return
    const json: VersionData = await res.json()
    data.value = json

    // Show after 1s delay
    setTimeout(() => { visible.value = true }, 1000)

    // Auto-dismiss after 10s if no interaction
    setTimeout(() => {
      if (visible.value) dismiss()
    }, 11000)
  } catch {
    // silent — no popup if version.json unavailable
  }
})
</script>

<style scoped>
.change-item {
  opacity: 0;
  animation: changeReveal 0.4s ease-out forwards;
}

@keyframes changeReveal {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}

.animate-gradient-x {
  background-size: 200% 100%;
  animation: gradientX 3s linear infinite;
}

@keyframes gradientX {
  0% { background-position: 0% 50%; }
  100% { background-position: 200% 50%; }
}

@media (prefers-reduced-motion: reduce) {
  .change-item { animation: none; opacity: 1; }
  .animate-gradient-x { animation: none; }
}
</style>
