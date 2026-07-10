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
          <div class="floating-chat-panel" :class="{ maximized: isMaximized }">
            <!-- Header with gradient -->
            <div class="panel-header">
              <div class="header-brand">
                <div class="header-avatar">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/>
                  </svg>
                </div>
                <div class="header-text">
                  <span class="panel-title">AI Assistant</span>
                  <span class="header-subtitle">PaperFull</span>
                </div>
              </div>
              <div class="panel-header-actions">
                <button class="panel-btn" @click="toggleMaximize" :title="isMaximized ? 'Restore' : 'Maximize'"
                  :aria-label="isMaximized ? 'Restore panel' : 'Maximize panel'">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline v-show="isMaximized" points="18,5 18,9 22,9"/>
                    <polyline v-show="isMaximized" points="6,19 6,15 2,15"/>
                    <polyline v-show="!isMaximized" points="18,15 18,19 22,19"/>
                    <polyline v-show="!isMaximized" points="6,9 6,5 2,5"/>
                  </svg>
                </button>
                <button class="panel-btn" @click="close" title="Minimize">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 9l-7 7-7-7"/></svg>
                </button>
              </div>
            </div>

            <!-- Body: ChatTab directly (handles paperId or global) -->
            <div class="panel-body">
              <ChatTab :paper-id="currentPaperId" />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ChatTab from '@/components/ChatTab.vue'

const auth = useAuthStore()
const route = useRoute()

const isOpen = ref(false)
const showGreeting = ref(false)
const isMaximized = ref(false)

function toggleMaximize() {
  isMaximized.value = !isMaximized.value
}

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
}

function close() {
  isOpen.value = false
}

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
  height: 50px; padding: 0 22px; border-radius: 25px;
  background: linear-gradient(135deg, #0d9488 0%, #0f766e 50%, #0d5c56 100%);
  color: #ffffff; border: none;
  box-shadow:
    0 4px 24px rgba(13, 148, 136, 0.35),
    0 0 0 1px rgba(13, 148, 136, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  cursor: pointer; display: flex; align-items: center; gap: 10px;
  z-index: 9998; font-family: inherit; font-size: 0.9rem; font-weight: 600;
  letter-spacing: 0.01em;
  overflow: visible;
  transition: transform 0.25s ease, box-shadow 0.25s ease, background 0.25s ease;
}
/* Rotating conic ring on hover */
.floating-chat-btn::after {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 28px;
  background: conic-gradient(from 0deg, #14b8a6, #0d9488, #10b981, #0d9488, #14b8a6);
  z-index: -1;
  opacity: 0;
  transition: opacity 0.25s ease;
  animation: btn-ring-spin 2s linear infinite;
}
.floating-chat-btn:hover::after { opacity: 1; }
.floating-chat-btn:hover {
  transform: scale(1.08) translateY(-2px);
  box-shadow:
    0 8px 32px rgba(13, 148, 136, 0.45),
    0 0 0 1px rgba(13, 148, 136, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.25);
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 50%, #0f766e 100%);
}
.floating-chat-btn:active { transform: scale(0.95); }
.btn-label { white-space: nowrap; }

@keyframes btn-ring-spin {
  to { transform: rotate(360deg); }
}

/* ── Overlay (non-blocking) ── */
.floating-chat-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: transparent; display: flex;
  align-items: flex-end; justify-content: flex-end;
  padding: 16px; pointer-events: none;
}

.floating-chat-panel {
  width: 440px; max-width: 100vw; height: 640px;
  max-height: calc(100vh - 32px);
  background: linear-gradient(180deg, #f8f6f2 0%, #f3efe8 100%);
  border-radius: 20px; box-shadow:
    0 20px 60px rgba(15, 39, 68, 0.25),
    0 4px 20px rgba(15, 39, 68, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
  display: flex; flex-direction: column; overflow: hidden;
  pointer-events: auto;
  position: relative;
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.floating-chat-panel.maximized {
  width: 720px;
}
.floating-chat-panel::before {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 22px;
  background: linear-gradient(180deg, #238f7f 0%, #0d9488 30%, #059669 60%, #10b981 100%);
  z-index: -1;
  opacity: 0.95;
}

/* ── Header with gradient ── */
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #1e3a5f 0%, #0f2744 60%, #0a1f38 100%);
  border-bottom: 1px solid rgba(56, 139, 253, 0.2);
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}

/* Decorative gradient shine */
.panel-header::before {
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(ellipse at 30% 20%, rgba(56, 139, 253, 0.15) 0%, transparent 50%);
  pointer-events: none;
}

.header-brand {
  display: flex; align-items: center; gap: 12px;
  position: relative; z-index: 1;
}

.header-avatar {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, #238f7f 0%, #1a7a6d 100%);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 8px rgba(35, 143, 127, 0.4);
  color: #e8f4fd;
}

.header-text {
  display: flex; flex-direction: column; gap: 1px;
}

.panel-title {
  font-weight: 700; font-size: 0.95rem; color: #f0f6fc;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.header-subtitle {
  font-size: 0.7rem; color: rgba(232, 244, 253, 0.6);
  font-weight: 500;
}

.panel-header-actions { display: flex; gap: 4px; position: relative; z-index: 1; }
.panel-btn {
  background: rgba(255, 255, 255, 0.1); border: none; color: rgba(232, 244, 253, 0.7);
  padding: 8px; border-radius: 8px; cursor: pointer; display: flex; align-items: center;
  transition: all 0.15s ease;
}
.panel-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  color: #e8f4fd;
  transform: translateY(1px);
}

.panel-body { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }

/* ── Transition ── */
.panel-fade-enter-active { transition: opacity 0.3s ease; }
.panel-fade-leave-active { transition: opacity 0.3s ease; }
.panel-fade-enter-active .floating-chat-panel { transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease; }
.panel-fade-leave-active .floating-chat-panel { transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease; }
.panel-fade-enter-from, .panel-fade-leave-to { opacity: 0; }
.panel-fade-enter-from .floating-chat-panel { transform: translateY(24px) scale(0.95); opacity: 0; }
.panel-fade-leave-to .floating-chat-panel { transform: translateY(24px) scale(0.95); opacity: 0; }

/* ── Dark mode overrides ── */
@media (prefers-color-scheme: dark) {
  .floating-chat-panel {
    background: linear-gradient(180deg, #1a1f2e 0%, #151a26 100%);
    border-color: rgba(35, 143, 127, 0.15);
    box-shadow:
      0 20px 60px rgba(0, 0, 0, 0.5),
      0 4px 20px rgba(0, 0, 0, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }
}
</style>
