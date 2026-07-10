<template>
  <div class="floating-chat-container">
    <!-- Welcome greeting -->
    <Transition name="greeting-slide">
      <div
        v-if="showGreeting"
        class="greeting-bubble"
        @click="dismissGreeting"
      >
        <div class="greeting-avatar">🤖</div>
        <div class="greeting-content">
          <p class="greeting-text">Halo! Ada yang bisa saya bantu?</p>
          <p class="greeting-subtext">Klik tombol AI Assistant di kanan bawah</p>
        </div>
        <button class="greeting-close" @click.stop="dismissGreeting" aria-label="Close">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
      </div>
    </Transition>

    <!-- Floating button -->
    <button
      v-if="auth.isLoggedIn && !isOpen"
      class="floating-chat-btn"
      @click="open"
      title="AI Assistant"
      aria-label="Open AI Assistant"
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
      </svg>
      <span class="btn-label">AI Assistant</span>
    </button>

    <!-- Panel overlay (non-blocking) -->
    <Teleport to="body">
      <Transition name="panel-fade">
        <div v-if="isOpen" class="floating-chat-overlay">
          <div class="floating-chat-panel">
            <!-- Header -->
            <div class="panel-header">
              <span class="panel-title">AI Assistant</span>
              <div class="panel-header-actions">
                <button class="panel-btn" @click="close" title="Close">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>

            <!-- Body: paper picker (dashboard) or ChatTab (editor) -->
            <div class="panel-body">
              <!-- Dashboard: no paperId → show paper picker -->
              <template v-if="!currentPaperId">
                <div v-if="loading" class="picker-loading">
                  <div class="spinner"></div>
                  <span>Memuat daftar paper...</span>
                </div>
                <div v-else class="picker-container">
                  <div class="picker-header">
                    <h3 class="picker-title">Pilih Paper</h3>
                    <p class="picker-desc">Pilih paper untuk mulai chat AI</p>
                  </div>

                  <div v-if="paperList.length === 0" class="picker-empty">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <p class="text-sm text-[var(--text-muted)]">Belum ada paper.</p>
                    <p class="text-xs text-[var(--text-muted)]">Buat paper baru dulu untuk mulai chat dengan AI.</p>
                  </div>

                  <div v-else class="paper-list">
                    <div
                      v-for="p in paperList"
                      :key="p.paper_id"
                      class="paper-item"
                      @click="selectPaper(p.paper_id)"
                    >
                      <div class="paper-item-icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                      </div>
                      <div class="paper-item-info">
                        <span class="paper-item-title">{{ p.paper_title || 'Untitled' }}</span>
                        <span class="paper-item-meta">{{ p.chat_count || 0 }} chat</span>
                      </div>
                      <span class="paper-item-arrow">&rarr;</span>
                    </div>
                  </div>
                </div>
              </template>

              <!-- Editor: has paperId → show ChatTab -->
              <ChatTab v-else :paper-id="currentPaperId" />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import ChatTab from '@/components/ChatTab.vue'

const auth = useAuthStore()
const chatStore = useChatStore()
const route = useRoute()
const router = useRouter()

const isOpen = ref(false)
const showGreeting = ref(false)
const loading = ref(false)
const paperList = ref<any[]>([])

const currentPaperId = computed(() => {
  if (route.params.paperId) return route.params.paperId as string
  if (route.query.paperId) return route.query.paperId as string
  return null
})

let greetingTimeout: ReturnType<typeof setTimeout> | null = null

function showGreetingAnimation() {
  if (route.name !== 'dashboard') return
  showGreeting.value = true
  greetingTimeout = setTimeout(() => {
    dismissGreeting()
  }, 5000)
}

function dismissGreeting() {
  showGreeting.value = false
  if (greetingTimeout) {
    clearTimeout(greetingTimeout)
    greetingTimeout = null
  }
}

async function open() {
  if (showGreeting.value) dismissGreeting()
  isOpen.value = true

  // If no paperId (dashboard), load paper list
  if (!currentPaperId.value) {
    loading.value = true
    try {
      paperList.value = await chatStore.loadPaperChats()
    } catch {
      paperList.value = []
    }
    loading.value = false
  } else {
    // Editor: open ChatTab directly
    await chatStore.openPaper(currentPaperId.value)
  }
}

function close() {
  isOpen.value = false
  paperList.value = []
}

async function selectPaper(paperId: string) {
  // Navigate to editor with that paper
  router.push({ name: 'editor', params: { paperId } })
  // Keep panel open — ChatTab will mount with new paperId
  await chatStore.openPaper(paperId)
}

// Close on Escape
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isOpen.value) {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  setTimeout(() => {
    showGreetingAnimation()
  }, 1000)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  if (greetingTimeout) clearTimeout(greetingTimeout)
})
</script>

<style scoped>
/* ── Greeting ── */
.greeting-bubble {
  position: fixed;
  bottom: 90px;
  right: 24px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  border: 2px solid #fbbf24;
  border-radius: 16px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
  z-index: 9997;
  cursor: pointer;
  max-width: 320px;
  animation: bounce-subtle 0.5s ease-out;
}

.greeting-avatar { font-size: 28px; flex-shrink: 0; }
.greeting-content { flex: 1; min-width: 0; }
.greeting-text { font-size: 0.95rem; font-weight: 600; color: #92400e; margin: 0 0 4px 0; line-height: 1.3; }
.greeting-subtext { font-size: 0.8rem; color: #a16207; margin: 0; line-height: 1.4; }

.greeting-close {
  position: absolute; top: 8px; right: 8px;
  background: rgba(251, 191, 36, 0.2); border: none; color: #92400e;
  padding: 4px; border-radius: 4px; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
  transition: background 0.15s;
}
.greeting-close:hover { background: rgba(251, 191, 36, 0.4); }

.greeting-slide-enter-active { transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
.greeting-slide-leave-active { transition: all 0.3s ease-in; }
.greeting-slide-enter-from { opacity: 0; transform: translateY(20px) scale(0.9); }
.greeting-slide-leave-to { opacity: 0; transform: translateX(40px); }

@keyframes bounce-subtle {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

/* ── Button ── */
.floating-chat-btn {
  position: fixed; bottom: 24px; right: 24px;
  height: 44px; padding: 0 18px; border-radius: 22px;
  background: linear-gradient(135deg, #f5e6d3, #e8d5c4);
  color: #5c3d2e; border: 1px solid rgba(92, 61, 46, 0.2);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  cursor: pointer; display: flex; align-items: center; gap: 8px;
  z-index: 9998; font-family: inherit; font-size: 0.85rem; font-weight: 600;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.floating-chat-btn:hover { transform: scale(1.05); box-shadow: 0 6px 24px rgba(0, 0, 0, 0.2); }
.floating-chat-btn:active { transform: scale(0.96); }
.btn-label { white-space: nowrap; }

/* ── Overlay (non-blocking) ── */
.floating-chat-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: transparent; display: flex;
  align-items: flex-end; justify-content: flex-end;
  padding: 16px; pointer-events: none;
}

.floating-chat-panel {
  width: 440px; max-width: 100vw; height: 620px;
  max-height: calc(100vh - 32px);
  background: #1e293b; border: 1px solid #334155;
  border-radius: 16px; box-shadow: 0 8px 40px rgba(0, 0, 0, 0.4);
  display: flex; flex-direction: column; overflow: hidden;
  pointer-events: auto;
}

.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; background: #0f172a;
  border-bottom: 1px solid #334155; flex-shrink: 0;
}
.panel-title { font-weight: 600; font-size: 0.9rem; color: #e2e8f0; }
.panel-header-actions { display: flex; gap: 4px; }
.panel-btn {
  background: none; border: none; color: #94a3b8;
  padding: 6px; border-radius: 6px; cursor: pointer;
  display: flex; align-items: center;
  transition: color 0.15s, background 0.15s;
}
.panel-btn:hover { color: #e2e8f0; background: #1e293b; }

.panel-body { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }

/* ── Paper picker ── */
.picker-loading { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 40px; color: #94a3b8; font-size: 0.85rem; }
.spinner { width: 20px; height: 20px; border: 2px solid #334155; border-top-color: #3b82f6; border-radius: 50%; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.picker-container { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.picker-header { padding: 16px 16px 8px; flex-shrink: 0; }
.picker-title { font-size: 0.9rem; font-weight: 600; color: #e2e8f0; margin: 0; }
.picker-desc { font-size: 0.75rem; color: #64748b; margin: 4px 0 0; }

.picker-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; color: #64748b; text-align: center; gap: 8px; }

.paper-list { flex: 1; overflow-y: auto; padding: 8px 0; }
.paper-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; cursor: pointer;
  transition: background 0.12s; color: #e2e8f0;
}
.paper-item:hover { background: rgba(255, 255, 255, 0.04); }
.paper-item-icon { display: flex; align-items: center; color: #64748b; flex-shrink: 0; }
.paper-item-info { flex: 1; min-width: 0; }
.paper-item-title { display: block; font-size: 0.85rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.paper-item-meta { font-size: 0.7rem; color: #64748b; }
.paper-item-arrow { color: #64748b; font-size: 0.9rem; }

/* ── Transition ── */
.panel-fade-enter-active, .panel-fade-leave-active { transition: opacity 0.2s ease; }
.panel-fade-enter-active .floating-chat-panel, .panel-fade-leave-active .floating-chat-panel { transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1); }
.panel-fade-enter-from, .panel-fade-leave-to { opacity: 0; }
.panel-fade-enter-from .floating-chat-panel, .panel-fade-leave-to .floating-chat-panel { transform: translateY(20px) scale(0.96); }
</style>