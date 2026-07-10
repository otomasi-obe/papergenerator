<template>
  <!-- Floating button (always visible when logged in) -->
  <button
    v-if="auth.isLoggedIn && !isOpen"
    class="floating-chat-btn"
    @click="open"
    title="AI Assistant"
    aria-label="Open AI Assistant"
  >
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
    </svg>
    <span v-if="unreadCount" class="unread-badge">{{ unreadCount > 9 ? '9+' : unreadCount }}</span>
  </button>

  <!-- Floating chat panel (overlay) -->
  <Teleport to="body">
    <Transition name="panel-slide">
      <div v-if="isOpen" class="floating-chat-overlay">
        <div class="floating-chat-panel">
          <!-- Panel header -->
          <div class="panel-header">
            <span class="panel-title">AI Assistant</span>
            <div class="panel-header-actions">
              <button class="panel-btn" @click="isOpen = false" title="Close" aria-label="Close AI Assistant">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- ChatTab embedded directly -->
          <div class="panel-body">
            <ChatTab :paper-id="currentPaperId" @open-preview="isOpen = false" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ChatTab from '@/components/ChatTab.vue'

const auth = useAuthStore()
const route = useRoute()

const isOpen = ref(false)

// Extract paperId from route (works for both /editor/:id and /dashboard)
const currentPaperId = computed(() => {
  // Route params.paperId for /editor/:paperId
  if (route.params.paperId) return route.params.paperId as string
  // Route query for /dashboard?paperId=...
  if (route.query.paperId) return route.query.paperId as string
  return null
})

const unreadCount = computed(() => {
  // Count unread messages across all conversations
  // ponytail: hook into actual read-receipt system when built
  return 0
})

function open() {
  isOpen.value = true
}
</script>

<style scoped>
/* Floating button */
.floating-chat-btn {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--color-accent, #1e40af);
  color: #fff;
  border: none;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9998;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.floating-chat-btn:hover {
  transform: scale(1.08);
  box-shadow: 0 6px 28px rgba(0, 0, 0, 0.4);
}

.floating-chat-btn:active {
  transform: scale(0.95);
}

.unread-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  min-width: 20px;
  height: 20px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border: 2px solid #fff;
}

/* Overlay */
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

/* Panel */
.floating-chat-panel {
  width: 420px;
  max-width: 100vw;
  height: 600px;
  max-height: calc(100vh - 32px);
  background: var(--color-bg-elevated, #1e293b);
  border: 1px solid var(--color-border, #334155);
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
  background: var(--color-bg-surface, #0f172a);
  border-bottom: 1px solid var(--color-border, #334155);
  flex-shrink: 0;
}

.panel-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--color-text-primary, #e2e8f0);
}

.panel-header-actions {
  display: flex;
  gap: 4px;
}

.panel-btn {
  background: none;
  border: none;
  color: var(--color-text-muted, #94a3b8);
  padding: 6px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: color 0.15s, background 0.15s;
}

.panel-btn:hover {
  color: var(--color-text-primary, #e2e8f0);
  background: var(--color-bg-hover, #1e293b);
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Transition */
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: opacity 0.2s ease;
}

.panel-slide-enter-active .floating-chat-panel,
.panel-slide-leave-active .floating-chat-panel {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.panel-slide-enter-from,
.panel-slide-leave-to {
  opacity: 0;
}

.panel-slide-enter-from .floating-chat-panel,
.panel-slide-leave-to .floating-chat-panel {
  transform: translateY(20px) scale(0.96);
}
</style>