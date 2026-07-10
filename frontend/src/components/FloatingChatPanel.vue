<template>
  <div class="floating-chat" :class="{ collapsed: isCollapsed }">
    <!-- Header -->
    <div class="floating-chat-header" @click="toggleCollapse">
      <div class="header-left">
        <span class="header-title">💬 AI Assistant</span>
        <span class="context-badge" v-if="currentPaperTitle">#{{ currentPaperTitle }}</span>
      </div>
      <div class="header-right">
        <button class="header-btn" @click.stop="chatStore.clearCurrentChat()" title="New Chat">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
        </button>
        <button class="header-btn" @click.stop="closePanel" title="Minimize">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg>
        </button>
      </div>
    </div>

    <!-- Body -->
    <div class="floating-chat-body" v-show="!isCollapsed">
      <!-- Messages -->
      <div class="floating-chat-messages" ref="messagesContainer" @scroll="onScroll">
        <div v-if="!messages.length && !isStreaming" class="empty-state">
          <p>👋 Halo! Tanya apa saja tentang paper kamu.</p>
        </div>

        <div v-for="(msg, idx) in messages" :key="msg.id || idx"
             class="chat-msg" :class="msg.role">
          <!-- User message -->
          <template v-if="msg.role === 'user'">
            <div class="msg-content">{{ msg.content }}</div>
          </template>

          <!-- Assistant message -->
          <template v-else>
            <div class="msg-content" v-html="renderMarkdown(msg.content)"></div>
            <!-- Multi-question -->
            <div v-if="msg.metadata?.kind === 'multi_question'" class="proposal multi-question">
              <div v-for="(q, qi) in msg.metadata.questions" :key="qi" class="mq-item">
                <span class="mq-num">{{ Number(qi) + 1 }}.</span>
                <span>{{ q }}</span>
              </div>
            </div>
            <!-- Ask user -->
            <div v-if="msg.metadata?.kind === 'ask_user'" class="proposal ask-user">
              <p class="ask-q">{{ msg.metadata.question }}</p>
              <div class="ask-opts" v-if="msg.metadata.options?.length">
                <button v-for="(opt, oi) in msg.metadata.options" :key="oi"
                        class="ask-opt-btn" @click="chatStore.sendMessage(opt)">
                  {{ opt }}
                </button>
              </div>
            </div>
            <!-- Chips -->
            <div v-if="msg.metadata?.kind === 'chips'" class="proposal chips">
              <button v-for="(chip, ci) in msg.metadata.chips" :key="ci"
                      class="chip-btn" @click="chatStore.sendMessage(chip)">
                {{ chip }}
              </button>
            </div>
          </template>
        </div>

        <!-- Streaming message -->
        <div v-if="isStreaming && streamingMessage" class="chat-msg assistant streaming">
          <div class="msg-content" v-html="renderMarkdown(streamingMessage.content || '')"></div>
          <span class="streaming-dot">...</span>
        </div>
      </div>

      <!-- Scroll-to-bottom button -->
      <button v-if="showScrollBtn" class="scroll-bottom-btn" @click="scrollToBottom">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
      </button>

      <!-- Input -->
      <div class="floating-chat-input">
        <textarea v-model="inputText"
                  @keydown.enter.exact="sendMessage"
                  placeholder="Ketik pesan..."
                  :disabled="isStreaming"
                  rows="1"
                  ref="inputRef"></textarea>
        <button class="send-btn" @click="sendMessage"
                :disabled="isStreaming || !inputText.trim()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { usePaperStore } from '@/stores/paper'
import { useUserStateStore } from '@/stores/userState'

const chatStore = useChatStore()
const paperStore = usePaperStore()
const userState = useUserStateStore()

const { messages, isStreaming, streamingMessage } = storeToRefs(chatStore)

// ── State ───────────────────────────────────────────────────────────────────
const isCollapsed = ref(false)
const inputText = ref('')
const messagesContainer = ref<HTMLDivElement | null>(null)
const showScrollBtn = ref(false)
let userScrolledUp = false

// ── Computed ────────────────────────────────────────────────────────────────
const currentPaperTitle = computed(() => {
  const pid = chatStore.currentPaperId
  if (!pid) return null
  // paperStore exposes paper (singular) as a reactive ref
  const p = (paperStore as any).paper
  return p?.title || null
})

// ── Methods ─────────────────────────────────────────────────────────────────
const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const closePanel = () => {
  isCollapsed.value = true
}

const sendMessage = () => {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return
  chatStore.sendMessage(text)
  inputText.value = ''
}

// Simple markdown render (no `marked` dep, ponytail: swap for marked when needed)
const renderMarkdown = (text: string): string => {
  if (!text) return ''
  // Basic: bold, italic, code, newlines
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

// ── Scroll behavior ─────────────────────────────────────────────────────────
const scrollToBottom = () => {
  if (!messagesContainer.value) return
  messagesContainer.value.scrollTo({
    top: messagesContainer.value.scrollHeight,
    behavior: 'smooth',
  })
  userScrolledUp = false
  showScrollBtn.value = false
}

const onScroll = () => {
  if (!messagesContainer.value) return
  const el = messagesContainer.value
  const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  userScrolledUp = distFromBottom > 60
  showScrollBtn.value = distFromBottom > 60
}

// Auto-scroll when new messages arrive (only if user hasn't scrolled up)
watch(
  () => messages.value.length,
  () => {
    nextTick(() => {
      if (!userScrolledUp) {
        scrollToBottom()
      }
    })
  },
)

// Auto-scroll during streaming
watch(
  () => streamingMessage.value?.content,
  () => {
    nextTick(() => {
      if (!userScrolledUp) {
        scrollToBottom()
      }
    })
  },
)

// ── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  try {
    const saved = userState.get('chat.floating.collapsed')
    if (saved !== undefined) isCollapsed.value = saved
  } catch { /* ignore */ }
})

onBeforeUnmount(() => {
  try {
    userState.set('chat.floating.collapsed', null, isCollapsed.value)
  } catch { /* ignore */ }
})
</script>

<style scoped>
.floating-chat {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 380px;
  max-height: 520px;
  background: var(--color-bg-elevated, #1e293b);
  border: 1px solid var(--color-border, #334155);
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  z-index: 9999;
  font-family: var(--font-sans, Inter, sans-serif);
  font-size: 0.875rem;
  overflow: hidden;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.floating-chat.collapsed {
  width: auto;
  max-height: 48px;
  border-radius: 24px;
}

/* ── Header ── */
.floating-chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--color-bg-surface, #1a2332);
  border-bottom: 1px solid var(--color-border, #334155);
  cursor: pointer;
  user-select: none;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  font-weight: 600;
  color: var(--color-text-primary, #e2e8f0);
  font-size: 0.9rem;
}

.context-badge {
  font-size: 0.7rem;
  background: var(--color-accent, #3b82f6);
  color: #fff;
  padding: 2px 8px;
  border-radius: 10px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-right {
  display: flex;
  gap: 4px;
}

.header-btn {
  background: none;
  border: none;
  color: var(--color-text-muted, #94a3b8);
  padding: 4px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
}

.header-btn:hover {
  color: var(--color-text-primary, #e2e8f0);
  background: var(--color-bg-hover, #334155);
}

/* ── Body ── */
.floating-chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
}

.floating-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 380px;
}

.empty-state {
  text-align: center;
  color: var(--color-text-muted, #64748b);
  padding: 24px 12px;
  font-size: 0.85rem;
}

/* ── Messages ── */
.chat-msg {
  max-width: 90%;
  padding: 8px 12px;
  border-radius: 12px;
  line-height: 1.45;
  word-break: break-word;
}

.chat-msg.user {
  align-self: flex-end;
  background: var(--color-accent, #3b82f6);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.chat-msg.assistant {
  align-self: flex-start;
  background: var(--color-bg-surface, #1a2332);
  color: var(--color-text-primary, #e2e8f0);
  border: 1px solid var(--color-border, #334155);
  border-bottom-left-radius: 4px;
}

.chat-msg.streaming {
  opacity: 0.85;
}

.streaming-dot {
  animation: blink 1s infinite;
  margin-left: 2px;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.msg-content :deep(code) {
  background: rgba(0,0,0,0.2);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.8rem;
}

.msg-content :deep(strong) {
  font-weight: 600;
}

/* ── Proposals ── */
.proposal {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--color-bg-hover, #1e293b);
  border: 1px solid var(--color-border, #334155);
}

.ask-q {
  margin-bottom: 6px;
  font-weight: 500;
}

.ask-opts, .chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ask-opt-btn, .chip-btn {
  background: var(--color-bg-elevated, #0f172a);
  border: 1px solid var(--color-border, #334155);
  color: var(--color-text-primary, #e2e8f0);
  padding: 4px 12px;
  border-radius: 14px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.15s;
}

.ask-opt-btn:hover, .chip-btn:hover {
  background: var(--color-accent, #3b82f6);
  color: #fff;
}

.mq-item {
  display: flex;
  gap: 4px;
  margin: 2px 0;
}

.mq-num {
  color: var(--color-text-muted, #94a3b8);
  font-weight: 500;
}

/* ── Scroll button ── */
.scroll-bottom-btn {
  position: absolute;
  bottom: 60px;
  right: 16px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-accent, #3b82f6);
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  z-index: 10;
  transition: transform 0.2s ease;
}

.scroll-bottom-btn:hover {
  transform: scale(1.1);
}

/* ── Input ── */
.floating-chat-input {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--color-border, #334155);
  background: var(--color-bg-surface, #1a2332);
  flex-shrink: 0;
}

.floating-chat-input textarea {
  flex: 1;
  background: var(--color-bg-elevated, #0f172a);
  border: 1px solid var(--color-border, #334155);
  border-radius: 20px;
  padding: 8px 14px;
  color: var(--color-text-primary, #e2e8f0);
  font-size: 0.85rem;
  resize: none;
  outline: none;
  font-family: inherit;
  max-height: 80px;
}

.floating-chat-input textarea:focus {
  border-color: var(--color-accent, #3b82f6);
}

.floating-chat-input textarea::placeholder {
  color: var(--color-text-muted, #64748b);
}

.send-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--color-accent, #3b82f6);
  color: #fff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: opacity 0.15s;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-btn:hover:not(:disabled) {
  opacity: 0.9;
}

/* ── Scrollbar ── */
.floating-chat-messages::-webkit-scrollbar {
  width: 5px;
}
.floating-chat-messages::-webkit-scrollbar-track {
  background: transparent;
}
.floating-chat-messages::-webkit-scrollbar-thumb {
  background: var(--color-border, #334155);
  border-radius: 3px;
}
</style>