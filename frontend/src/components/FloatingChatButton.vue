<template>
  <div class="floating-chat-container">
    <!-- Welcome greeting (dashboard first visit) -->
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

    <!-- Panel overlay (non-blocking, transparent background) -->
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

            <!-- Body: ChatTab directly (has its own picker) -->
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
import { useChatStore } from '@/stores/chat'
import ChatTab from '@/components/ChatTab.vue'

const auth = useAuthStore()
const chatStore = useChatStore()
const route = useRoute()

const isOpen = ref(false)
const showGreeting = ref(false)

// Extract paperId from route
const currentPaperId = computed(() => {
  if (route.params.paperId) return route.params.paperId as string
  if (route.query.paperId) return route.query.paperId as string
  return null
})

let greetingTimeout: ReturnType<typeof setTimeout> | null = null

function showGreetingAnimation() {
  // Only show on dashboard
  if (route.name !== 'dashboard') return
  // Check localStorage to avoid showing again
  const seen = localStorage.getItem('ai_greeting_seen')
  if (seen) return
  
  showGreeting.value = true
  // Auto-dismiss after 5 seconds
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
  localStorage.setItem('ai_greeting_seen', 'true')
}

async function open() {
  // Hide greeting if visible
  if (showGreeting.value) {
    dismissGreeting()
  }
  
  isOpen.value = true

  // If we have paperId, openPaper in chat store
  if (currentPaperId.value) {
    await chatStore.openPaper(currentPaperId.value)
  }
  // If no paperId (dashboard), ChatTab shows its picker
}

function close() {
  isOpen.value = false
  // Don't reset chatStore — keep conversation state for next open
}

// Close on Escape
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isOpen.value) {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  // Show greeting on dashboard
  setTimeout(() => {
    showGreetingAnimation()
  }, 1000) // Delay 1s after mount
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  if (greetingTimeout) {
    clearTimeout(greetingTimeout)
  }
})
</script>

<style scoped>
/* ── Greeting bubble ── */
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

.greeting-avatar {
  font-size: 28px;
  flex-shrink: 0;
}

.greeting-content {
  flex: 1;
  min-width: 0;
}

.greeting-text {
  font-size: 0.95rem;
  font-weight: 600;
  color: #92400e;
  margin: 0 0 4px 0;
  line-height: 1.3;
}

.greeting-subtext {
  font-size: 0.8rem;
  color: #a16207;
  margin: 0;
  line-height: 1.4;
}

.greeting-close {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(251, 191, 36, 0.2);
  border: none;
  color: #92400e;
  padding: 4px;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.greeting-close:hover {
  background: rgba(251, 191, 36, 0.4);
}

/* Greeting transition */
.greeting-slide-enter-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.greeting-slide-leave-active {
  transition: all 0.3s ease-in;
}

.greeting-slide-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.9);
}

.greeting-slide-leave-to {
  opacity: 0;
  transform: translateX(40px);
}

@keyframes bounce-subtle {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

/* ── Floating button ── */
.floating-chat-btn {
  position: fixed;
  bottom: 24px;
  right: 24px;
  height: 44px;
  padding: 0 18px;
  border-radius: 22px;
  background: linear-gradient(135deg, #f5e6d3, #e8d5c4);
  color: #5c3d2e;
  border: 1px solid rgba(92, 61, 46, 0.2);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 9998;
  font-family: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.floating-chat-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.2);
}

.floating-chat-btn:active {
  transform: scale(0.96);
}

.btn-label {
  white-space: nowrap;
}

/* ── Overlay (non-blocking, transparent) ── */
.floating-chat-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: transparent;
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 16px;
  pointer-events: none;
}

/* ── Panel ── */
.floating-chat-panel {
  width: 440px;
  max-width: 100vw;
  height: 620px;
  max-height: calc(100vh - 32px);
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.4);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  pointer-events: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #0f172a;
  border-bottom: 1px solid #334155;
  flex-shrink: 0;
}

.panel-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: #e2e8f0;
}

.panel-header-actions {
  display: flex;
  gap: 4px;
}

.panel-btn {
  background: none;
  border: none;
  color: #94a3b8;
  padding: 6px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: color 0.15s, background 0.15s;
}

.panel-btn:hover {
  color: #e2e8f0;
  background: #1e293b;
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ── Transition ── */
.panel-fade-enter-active,
.panel-fade-leave-active {
  transition: opacity 0.2s ease;
}

.panel-fade-enter-active .floating-chat-panel,
.panel-fade-leave-active .floating-chat-panel {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.panel-fade-enter-from,
.panel-fade-leave-to {
  opacity: 0;
}

.panel-fade-enter-from .floating-chat-panel,
.panel-fade-leave-to .floating-chat-panel {
  transform: translateY(20px) scale(0.96);
}
</style>