<template>
  <div class="floating-chat-container">
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

    <!-- Panel overlay -->
    <Teleport to="body">
      <Transition name="panel-fade">
        <div v-if="isOpen" class="floating-chat-overlay" @click.self="close">
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
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import ChatTab from '@/components/ChatTab.vue'

const auth = useAuthStore()
const chatStore = useChatStore()
const route = useRoute()
const router = useRouter()

const isOpen = ref(false)

// Extract paperId from route (works for /editor/:paperId, /dashboard?paperId=...)
const currentPaperId = computed(() => {
  if (route.params.paperId) return route.params.paperId as string
  if (route.query.paperId) return route.query.paperId as string
  return null
})

let paperPickerTimeout: ReturnType<typeof setTimeout> | null = null

async function open() {
  isOpen.value = true

  // If on dashboard without paperId, navigate to papers list first
  if (!currentPaperId.value && route.name === 'dashboard') {
    // Open paper picker modal or navigate
    router.push({ name: 'papers' })
    return
  }

  // If we have paperId, openPaper in chat store
  if (currentPaperId.value) {
    await chatStore.openPaper(currentPaperId.value)
  }
}

function close() {
  isOpen.value = false
  // Don't reset chatStore - keep conversation state for next open
  if (paperPickerTimeout) {
    clearTimeout(paperPickerTimeout)
    paperPickerTimeout = null
  }
}

// Close on Escape
onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isOpen.value) {
    close()
  }
}
</script>

<style scoped>
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

/* ── Overlay ── */
.floating-chat-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 16px;
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