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
      :class="{ 'is-streaming': isStreaming, 'has-unread': hasUnread }"
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
              <ChatTab :paper-id="currentPaperId" @open-preview="onOpenPreview" />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePaperStore } from '@/stores/paper'
import { useChatStore } from '@/stores/chat'
import ChatTab from '@/components/ChatTab.vue'
import { useUiStore } from '@/stores/ui'

const auth = useAuthStore()
const route = useRoute()
const paperStore = usePaperStore()
const chatStore = useChatStore()
const ui = useUiStore()

const currentPaperId = computed(() => paperStore.currentPaperId || null)

// [FIX] Wire ChatTab's `open-preview` event so the "Buka Preview" button
// actually switches to the preview tab. Previously the event was emitted but
// no parent handler caught it, so the button did nothing.
function onOpenPreview(): void {
  if (!currentPaperId.value) return
  ui.setTab(currentPaperId.value, 'preview')
  // Bump the signal so PaperEditorPage's computed re-evaluates even if the
  // tab id is unchanged.
  ui.tabSwitchSignal++
}
const showGreeting = ref(false)
const isOpen = ref(false)
const isMaximized = ref(false)
const hasUnread = ref(false)

// #2: running ring when AI streaming
const isStreaming = computed(() => chatStore.isStreaming)

// #3: red dot when AI finished while panel closed
watch(isStreaming, (val, oldVal) => {
  if (oldVal === true && val === false && !isOpen.value) {
    hasUnread.value = true
  }
})

function open() {
  if (showGreeting.value) dismissGreeting()
  isOpen.value = true
  hasUnread.value = false // clear on open
}

function close() {
  isOpen.value = false
}

function toggleMaximize() {
  isMaximized.value = !isMaximized.value
}

// [FIX] Read from paperStore (authoritative), NOT route params.
// Route may change before paper is loaded (dashboard→editor navigation).
// paperStore.currentPaperId is set AFTER loadPaperFromDb completes,
// so it stays consistent across navigation.

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

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isOpen.value) {
    close()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  // Open floating AI Assistant when triggered from LiteratureTab
  window.addEventListener('open-ai-assistant', open)
  setTimeout(() => {
    showGreetingAnimation()
  }, 1000)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('open-ai-assistant', open)
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
  padding: 18px 18px 16px;
  min-height: 86px;
  background: color-mix(in srgb, var(--accent-warning) 15%, var(--bg-surface) 85%);
  border: 1px solid color-mix(in srgb, var(--accent-warning) 40%, transparent);
  border-radius: 16px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
  z-index: 9997;
  cursor: pointer;
  max-width: 320px;
  animation: bounce-subtle 0.5s ease-out;
}

.greeting-avatar { font-size: 28px; flex-shrink: 0; }
.greeting-content { flex: 1; min-width: 0; }
.greeting-text { font-size: 0.95rem; font-weight: 600; color: var(--accent-warning); margin: 0 0 4px 0; line-height: 1.3; }
.greeting-subtext { font-size: 0.8rem; color: color-mix(in srgb, var(--accent-warning) 80%, var(--text-secondary)); margin: 0; line-height: 1.4; }

.greeting-close {
  position: absolute; top: 8px; right: 8px;
  background: rgba(251, 191, 36, 0.2); border: none; color: #92400e;
  padding: 4px; border-radius: 4px; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
  transition: background 0.15s;
}
.greeting-close:hover { background: rgba(251, 191, 36, 0.4); }

html.dark .greeting-bubble {
  background: linear-gradient(135deg, #0c1018 0%, #121d2c 55%, #0a0e18 100%);
  border-color: rgba(109, 180, 240, 0.35);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(109, 180, 240, 0.12);
}
html.dark .greeting-text { color: #8ec5eb; }
html.dark .greeting-subtext { color: #6db4f0; }
html.dark .greeting-close { background: rgba(109, 180, 240, 0.12); color: #d8efff; }
html.dark .greeting-close:hover { background: rgba(109, 180, 240, 0.22); }

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
  background: linear-gradient(135deg, #f5f0e8 0%, #ffffff 50%, #e6d3b3 100%);
  background-size: 200% 200%;
  animation: gradient-shift 6s ease infinite;
  color: #1a1a1a; border: none;
  box-shadow:
    0 4px 24px rgba(214, 196, 168, 0.45),
    0 0 0 1px rgba(214, 196, 168, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.6);
  cursor: pointer; display: flex; align-items: center; gap: 10px;
  z-index: 9998; font-family: inherit; font-size: 0.9rem; font-weight: 600;
  letter-spacing: 0.01em;
  overflow: visible;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.floating-chat-btn svg { color: #1a1a1a; stroke: #1a1a1a; flex-shrink: 0; }
.btn-label { white-space: nowrap; color: #1a1a1a; }
.floating-chat-btn:hover {
  transform: scale(1.06) translateY(-2px);
  box-shadow:
    0 8px 32px rgba(214, 196, 168, 0.55),
    0 0 0 1px rgba(214, 196, 168, 0.6),
    inset 0 1px 0 rgba(255, 255, 255, 0.7);
}
.floating-chat-btn:active { transform: scale(0.95); }

@keyframes gradient-shift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

/* Dark mode: keep navy gradient + white text for contrast */
html.dark .floating-chat-btn {
  background: linear-gradient(135deg, var(--navy-800) 0%, var(--accent-primary) 50%, var(--navy-700) 100%);
  background-size: 200% 200%;
  animation: gradient-shift-dark 6s ease infinite;
  color: #ffffff;
  box-shadow:
    0 4px 24px color-mix(in srgb, var(--accent-primary) 30%, transparent),
    0 0 0 1px color-mix(in srgb, var(--accent-primary) 20%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}
html.dark .floating-chat-btn svg { color: #ffffff; stroke: #ffffff; }
html.dark .btn-label { color: #ffffff; }
html.dark .floating-chat-btn:hover {
  transform: scale(1.06) translateY(-2px);
  box-shadow:
    0 8px 32px color-mix(in srgb, var(--accent-primary) 40%, transparent),
    0 0 0 1px color-mix(in srgb, var(--accent-primary) 25%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.15);
}
html.dark .floating-chat-btn:active { transform: scale(0.95); }

@keyframes gradient-shift-dark {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

/* #3: Red dot notification when AI finished while panel closed */
.floating-chat-btn.has-unread::after {
  content: '';
  position: absolute;
  top: 4px;
  right: 4px;
  width: 10px;
  height: 10px;
  background: #ef4444;
  border: 2px solid #fff;
  border-radius: 50%;
  box-shadow: 0 0 0 2px #ef4444;
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.2); opacity: 0.7; }
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
  max-height: calc(100vh - 96px);
  background: #faf9f6;
  border-radius: 20px;
  box-shadow:
    0 12px 40px rgba(15, 39, 68, 0.15),
    0 4px 16px rgba(15, 39, 68, 0.08);
  display: flex; flex-direction: column; overflow: hidden;
  pointer-events: auto;
  position: relative;
  transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1), height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.floating-chat-panel.maximized {
  width: min(1200px, calc(100vw - 32px));
  height: calc(100vh - 32px);
}

/* ── Header with gradient ── */
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #e8e0d0 0%, #f5f0e8 50%, #e6d3b3 100%);
  border-bottom: 1px solid rgba(166, 138, 92, 0.3);
  flex-shrink: 0;
}

.header-brand {
  display: flex; align-items: center; gap: 12px;
  position: relative; z-index: 1;
}

.header-avatar {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, #f5f0e8 0%, #e6d3b3 100%);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 8px rgba(166, 138, 92, 0.35);
  color: #1a1a1a;
}

.header-text {
  display: flex; flex-direction: column; gap: 1px;
}

.panel-title {
  font-weight: 700; font-size: 0.95rem; color: #1a1610;
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.4);
}

.header-subtitle {
  font-size: 0.7rem; color: rgba(26, 22, 16, 0.55);
  font-weight: 500;
}

.panel-header-actions { display: flex; gap: 4px; position: relative; z-index: 1; }
.panel-btn {
  background: rgba(255, 255, 255, 0.4); border: none; color: rgba(26, 22, 16, 0.65);
  padding: 8px; border-radius: 8px; cursor: pointer; display: flex; align-items: center;
  transition: all 0.15s ease;
}
.panel-btn:hover {
  background: rgba(255, 255, 255, 0.7);
  color: #1a1610;
  transform: translateY(1px);
}

/* Dark mode: navy gradient header + white text + blue avatar */
html.dark .panel-header {
  background: linear-gradient(135deg, #0f2744 0%, #1265c8 50%, #0b4088 100%);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
html.dark .header-avatar {
  background: linear-gradient(135deg, var(--accent-primary) 0%, var(--navy-700) 100%);
  color: #e8f4fd;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--accent-primary) 40%, transparent);
}
html.dark .panel-title { color: #f0f6fc; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3); }
html.dark .header-subtitle { color: rgba(232, 244, 253, 0.6); }
html.dark .panel-btn { background: rgba(255, 255, 255, 0.1); color: rgba(232, 244, 253, 0.7); }
html.dark .panel-btn:hover { background: rgba(255, 255, 255, 0.2); color: #e8f4fd; }

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
html.dark .floating-chat-panel {
  background: #1c2a3e;
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.45),
    0 4px 16px rgba(0, 0, 0, 0.3);
}
</style>
