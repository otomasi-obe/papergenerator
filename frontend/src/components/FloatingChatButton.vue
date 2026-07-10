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
              <button v-if="selectedConv" class="panel-btn" @click="selectedConv = null; selectedPaperId = null" title="Back to conversations">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              </button>
              <span class="panel-title">{{ selectedConv ? 'AI Assistant — Chat' : 'AI Assistant' }}</span>
              <div class="panel-header-actions">
                <button class="panel-btn" @click="close" title="Close">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </div>
            </div>

            <!-- Body: ChatTab or Conversation Picker -->
            <div class="panel-body" v-if="selectedConv && selectedPaperId">
              <ChatTab :paper-id="selectedPaperId" />
            </div>
            <div class="panel-body" v-else>
              <!-- Loading -->
              <div v-if="loading" class="picker-loading">
                <div class="spinner"></div>
                <span>Memuat percakapan...</span>
              </div>

              <!-- Conversation picker -->
              <div v-else class="conv-picker">
                <div
                  v-for="p in paperChats"
                  :key="p.paper_id"
                  class="paper-group"
                >
                  <div class="paper-row" @click="togglePaper(p.paper_id)">
                    <span class="paper-icon">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    </span>
                    <span class="paper-title">{{ p.paper_title || 'Untitled' }}</span>
                    <span class="paper-chat-count">{{ p.chat_count || 0 }}</span>
                    <span class="expand-chevron" :class="{ expanded: expandedPaper === p.paper_id }">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                    </span>
                  </div>

                  <!-- Conversations for this paper -->
                  <div v-if="expandedPaper === p.paper_id" class="conv-list">
                    <div
                      v-for="c in paperConvs[p.paper_id] || []"
                      :key="c.id"
                      class="conv-row"
                      @click="selectConversation(p.paper_id, c)"
                    >
                      <span class="conv-icon">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                      </span>
                      <span class="conv-title">{{ c.title || `Chat ${c.id.slice(0, 6)}` }}</span>
                      <span class="conv-arrow">&rarr;</span>
                    </div>
                    <div v-if="!(paperConvs[p.paper_id] || []).length" class="conv-empty">
                      <span>Belum ada percakapan</span>
                    </div>
                  </div>
                </div>

                <div v-if="!paperChats.length" class="picker-empty">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                  <p>Belum ada percakapan AI. Mulai dengan membuat paper baru.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import ChatTab from '@/components/ChatTab.vue'

const auth = useAuthStore()
const chatStore = useChatStore()

const isOpen = ref(false)
const loading = ref(false)

// Conversation picker state
const paperChats = ref<any[]>([])
const paperConvs = ref<Record<string, any[]>>({})
const expandedPaper = ref<string | null>(null)

// Selected conversation → show ChatTab
const selectedConv = ref<any>(null)
const selectedPaperId = ref<string | null>(null)

async function open() {
  isOpen.value = true
  loading.value = true
  selectedConv.value = null
  selectedPaperId.value = null
  try {
    paperChats.value = await chatStore.loadPaperChats()
  } catch {
    paperChats.value = []
  }
  loading.value = false
}

function close() {
  isOpen.value = false
  selectedConv.value = null
  selectedPaperId.value = null
  expandedPaper.value = null
}

async function togglePaper(paperId: string) {
  if (expandedPaper.value === paperId) {
    expandedPaper.value = null
    return
  }
  expandedPaper.value = paperId
  // Load conversations if not loaded
  if (!paperConvs.value[paperId]) {
    const convs = await chatStore.loadConversations(paperId)
    paperConvs.value = { ...paperConvs.value, [paperId]: convs }
  }
}

function selectConversation(paperId: string, conv: any) {
  selectedPaperId.value = paperId
  selectedConv.value = conv
  // Open paper + conversation in chat store
  chatStore.openPaper(paperId).then(() => {
    chatStore.openConversation(conv.id)
  })
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
  gap: 8px;
  padding: 10px 14px;
  background: #0f172a;
  border-bottom: 1px solid #334155;
  flex-shrink: 0;
}

.panel-title {
  flex: 1;
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

/* ── Loading ── */
.picker-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px;
  color: #94a3b8;
  font-size: 0.85rem;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #334155;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Conversation picker ── */
.conv-picker {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.paper-group {
  border-bottom: 1px solid #1e293b;
}

.paper-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.12s;
  color: #e2e8f0;
}

.paper-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.paper-icon {
  display: flex;
  align-items: center;
  color: #64748b;
  flex-shrink: 0;
}

.paper-title {
  flex: 1;
  font-size: 0.85rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.paper-chat-count {
  font-size: 0.7rem;
  color: #64748b;
  background: #0f172a;
  padding: 1px 6px;
  border-radius: 8px;
  min-width: 18px;
  text-align: center;
}

.expand-chevron {
  display: flex;
  align-items: center;
  color: #64748b;
  transition: transform 0.15s;
}

.expand-chevron.expanded {
  transform: rotate(180deg);
}

/* Conversations */
.conv-list {
  background: #0f172a;
}

.conv-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px 8px 36px;
  cursor: pointer;
  transition: background 0.12s;
  color: #cbd5e1;
  font-size: 0.82rem;
}

.conv-row:hover {
  background: rgba(59, 130, 246, 0.08);
  color: #e2e8f0;
}

.conv-icon {
  display: flex;
  align-items: center;
  color: #64748b;
  flex-shrink: 0;
}

.conv-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-arrow {
  color: #64748b;
  font-size: 0.8rem;
}

.conv-empty {
  padding: 8px 16px 8px 36px;
  color: #64748b;
  font-size: 0.78rem;
  font-style: italic;
}

.picker-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #64748b;
  text-align: center;
  gap: 12px;
}

.picker-empty p {
  font-size: 0.85rem;
  color: #94a3b8;
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