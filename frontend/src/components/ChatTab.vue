<template>
  <div class="flex flex-col h-full overflow-hidden bg-cream-100/40 dark:bg-ash-850">
    <!-- ─── PICKER VIEW: list of chats only (no active chat yet) ─── -->
    <template v-if="!currentConversationId">
      <header class="px-5 py-3 bg-cream-50 dark:bg-ash-800 border-b border-cream-300 dark:border-ash-700 flex items-center gap-2">
        <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 flex-1">AI Chat</h3>
        <button
          @click="createNewChat"
          :disabled="creatingChat || !currentPaperId"
          class="flex items-center gap-1.5 px-3 py-1.5 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
        >
          <span class="text-sm leading-none">＋</span>
          {{ creatingChat ? 'Creating…' : 'New chat' }}
        </button>
      </header>

      <div class="flex-1 overflow-y-auto p-3">
        <p class="text-[11px] text-slate-500 mb-2 px-1">
          Pilih chat yang sudah ada, atau buat chat baru.
        </p>
        <div v-if="!currentPaperId" class="px-3 py-6 text-center text-xs text-slate-400">
          Memuat paper…
        </div>
        <div v-else-if="conversations.length === 0" class="px-3 py-12 text-center text-xs text-slate-400">
          Belum ada chat. Klik <strong>+ New chat</strong> untuk memulai.
        </div>

        <div class="space-y-1.5">
          <div
            v-for="conv in conversations"
            :key="conv.id"
            class="group flex items-center gap-2 rounded-lg px-3 py-2.5 cursor-pointer hover:bg-white hover:shadow-sm border border-transparent hover:border-slate-200 transition-all"
            @click="handleSelectConversation(conv.id)"
          >
            <span class="text-base leading-none">💬</span>
            <div class="min-w-0 flex-1">
              <input
                v-if="renamingId === conv.id"
                v-model="renameDraft"
                @click.stop
                @keyup.enter="commitRename(conv)"
                @keyup.escape="cancelRename"
                @blur="commitRename(conv)"
                class="w-full text-xs px-1.5 py-0.5 border border-indigo-300 rounded outline-none focus:ring-1 focus:ring-indigo-300"
                :ref="el => (renameInput = el)"
              />
              <div v-else class="text-sm text-slate-700 truncate leading-snug">
                {{ conv.title || 'Untitled chat' }}
              </div>
              <div class="text-[10px] text-slate-400 mt-0.5">
                {{ conv.message_count || 0 }} msg · {{ formatDate(conv.updated_at) }}
              </div>
            </div>
            <button
              v-if="renamingId !== conv.id"
              @click.stop="startRename(conv)"
              class="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-700 text-xs px-1"
              title="Rename"
            >✎</button>
            <button
              v-if="renamingId !== conv.id"
              @click.stop="confirmDeleteChat(conv)"
              class="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 text-xs px-1"
              title="Delete"
            >🗑</button>
          </div>
        </div>

        <!-- Memory section (collapsible) -->
        <div v-if="currentPaperId" class="mt-5 border-t border-slate-200 pt-3">
          <button
            @click="memoryOpen = !memoryOpen"
            class="w-full flex items-center justify-between text-xs font-medium text-slate-600 hover:text-slate-800"
          >
            <span class="flex items-center gap-1.5">
              🧠 Project memory
              <span
                v-if="memory.length"
                class="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-indigo-100 text-indigo-700 text-[10px] font-semibold"
              >{{ memory.length }}</span>
            </span>
            <span class="text-slate-400">{{ memoryOpen ? '▾' : '▸' }}</span>
          </button>
          <div v-if="memoryOpen" class="mt-2 space-y-1.5">
            <div v-if="memory.length === 0" class="text-[11px] text-slate-400 px-1">
              Empty. AI akan menyimpan fakta penting paper ini secara otomatis.
            </div>
            <div
              v-for="m in memory"
              :key="m.id"
              class="bg-white border border-slate-200 rounded-md px-2 py-1.5 text-[11px] flex items-start gap-1.5 group/mem"
            >
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5 mb-0.5">
                  <span class="text-slate-400 text-[10px] uppercase tracking-wide">{{ m.kind }}</span>
                  <span class="text-slate-700 font-medium truncate">{{ m.key }}</span>
                </div>
                <div class="text-slate-600 leading-snug">{{ m.value }}</div>
              </div>
              <button
                @click="chatStore.deleteMemoryEntry(m.id)"
                class="opacity-0 group-hover/mem:opacity-100 text-slate-400 hover:text-red-500"
                title="Forget"
              >✕</button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ─── ACTIVE CHAT VIEW ─── -->
    <template v-else>
      <!-- Header with back button -->
      <header class="px-4 py-3 bg-cream-50 dark:bg-ash-800 border-b border-cream-300 dark:border-ash-700 flex items-center gap-2">
        <button
          @click="goBack"
          class="text-ink-700 dark:text-ink-200 hover:text-ink-900 dark:hover:text-ink-50 text-sm px-2 py-1 rounded hover:bg-cream-200 dark:hover:bg-ash-700 transition-colors"
          title="Kembali ke daftar chat"
        >← Back</button>
        <div class="relative shrink-0">
          <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-brown-500 to-brown-700 dark:from-brown-400 dark:to-brown-600 flex items-center justify-center">
            <svg class="w-3.5 h-3.5 text-cream-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/>
            </svg>
          </div>
          <span
            :class="[
              'absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-cream-50 dark:border-ash-800',
              isStreaming ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400',
            ]"
          ></span>
        </div>
        <div class="min-w-0 flex-1">
          <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 truncate">
            {{ currentChat?.title || 'AI Chat' }}
          </h3>
          <p :class="['text-[10px]', isStreaming ? 'text-amber-700 dark:text-amber-300' : 'text-emerald-700 dark:text-emerald-300']">
            {{ isStreaming ? 'Sedang berpikir…' : 'Online' }}
          </p>
        </div>

        <!-- Model picker — UI labels (Claude/Gemini/Chatgpt) hide upstream
             V-OPUS / V-GEMINI / V-GPT identifiers per product spec. -->
        <div class="relative shrink-0" v-click-outside="closeModelMenu">
          <button
            @click="modelMenuOpen = !modelMenuOpen"
            :disabled="isStreaming"
            class="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 text-ink-800 dark:text-ink-100 hover:bg-cream-200 dark:hover:bg-ash-600 disabled:opacity-50 transition-colors"
            :title="'Model: ' + currentModelLabel"
          >
            <span class="leading-none">{{ currentModelLabel }}</span>
            <span class="text-[9px] opacity-60 leading-none">▾</span>
          </button>
          <div
            v-if="modelMenuOpen"
            class="absolute right-0 top-full mt-1 z-40 w-32 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-lg overflow-hidden"
            role="menu"
          >
            <button
              v-for="m in MODELS"
              :key="m.value"
              @click="selectModel(m.value)"
              :class="[
                'w-full text-left px-3 py-1.5 text-[11px] hover:bg-cream-200 dark:hover:bg-ash-600 transition-colors flex items-center justify-between',
                m.value === selectedModel ? 'bg-cream-100 dark:bg-ash-600 font-semibold text-ink-900 dark:text-ink-50' : 'text-ink-700 dark:text-ink-200'
              ]"
              role="menuitem"
            >
              <span>{{ m.label }}</span>
              <span v-if="m.value === selectedModel" class="text-emerald-600 dark:text-emerald-400">✓</span>
            </button>
          </div>
        </div>
      </header>

      <!-- Messages -->
      <div ref="messagesContainer" class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        <div v-if="messages.length === 0 && !isStreaming"
          class="flex flex-col items-center justify-center min-h-full text-center py-6">
          <div class="w-12 h-12 rounded-2xl bg-indigo-100 flex items-center justify-center mb-3">
            <svg class="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09z"/>
            </svg>
          </div>
          <h3 class="text-base font-semibold text-slate-800 mb-1.5">Mulai percakapan</h3>
          <p class="text-xs text-slate-500 max-w-md leading-relaxed">
            Ketik pesan, atau pilih saran cepat di bawah.
          </p>
        </div>

        <ChatMessage
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
          :is-streaming="isStreaming && msg === messages[messages.length - 1] && msg.role === 'assistant'"
          @pick-option="pickOption"
        />
      </div>

      <!-- Pending changes summary above input -->
      <div
        v-if="paperStore.pendingCount > 0"
        class="px-4 pt-2 pb-2 bg-amber-50 dark:bg-amber-900/20 border-t border-amber-200 dark:border-amber-800"
      >
        <div class="flex items-center gap-2 text-xs text-amber-900 dark:text-amber-200">
          <span class="text-base leading-none shrink-0">⚠️</span>
          <span class="flex-1 leading-snug">
            <strong>{{ paperStore.pendingCount }} perubahan</strong> belum disetujui.
            <button @click="openPreview" class="underline font-semibold hover:text-amber-700 dark:hover:text-amber-100">Buka Preview</button>
          </span>
        </div>
        <div class="flex items-center gap-1.5 mt-1.5">
          <button
            @click="paperStore.acceptAllProposals()"
            class="flex-1 px-2.5 py-1 text-[11px] font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white"
          >✓ Terima semua</button>
          <button
            @click="paperStore.rejectAllProposals()"
            class="flex-1 px-2.5 py-1 text-[11px] font-semibold rounded-md bg-rose-100 hover:bg-rose-200 dark:bg-rose-900/40 dark:hover:bg-rose-900/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
          >✕ Tolak semua</button>
        </div>
      </div>

      <!-- Suggestion chips -->
      <div class="px-4 pt-2 bg-cream-50 dark:bg-ash-800 border-t border-cream-300 dark:border-ash-700">
        <div class="flex flex-wrap gap-1.5 mb-2">
          <button
            v-for="s in quickSuggestions"
            :key="s.text"
            @click="sendSuggestion(s.text)"
            :disabled="isStreaming"
            class="text-[11px] px-2.5 py-1 rounded-full bg-cream-100 dark:bg-ash-700 hover:bg-brown-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 text-ink-800 dark:text-ink-100 transition-colors border border-cream-300 dark:border-ash-600 disabled:opacity-50 disabled:cursor-not-allowed"
            :title="s.text"
          >
            <span class="mr-1">{{ s.icon }}</span>{{ s.text }}
          </button>
        </div>
      </div>

      <!-- Input -->
      <div class="px-4 pb-3 bg-cream-50 dark:bg-ash-800">
        <!-- Attached files preview -->
        <div v-if="attachedFiles.length" class="mb-2 flex flex-wrap gap-1.5">
          <div
            v-for="(f, i) in attachedFiles"
            :key="i"
            class="flex items-center gap-1.5 bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600 rounded-md px-2 py-1 text-[11px] text-ink-900 dark:text-ink-50"
          >
            <span>📄</span>
            <span class="truncate max-w-[160px]" :title="f.name">{{ f.name }}</span>
            <button
              @click="removeAttachedFile(i)"
              class="text-ink-500 dark:text-ink-300 hover:text-rose-500 ml-1"
              title="Remove"
            >✕</button>
          </div>
        </div>
        <p v-if="attachWarning" class="text-[10px] text-amber-700 dark:text-amber-300 mb-1">{{ attachWarning }}</p>

        <div class="rounded-2xl border-2 border-cream-400 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-sm focus-within:border-brown-500 dark:focus-within:border-cream-400 focus-within:ring-4 focus-within:ring-cream-200 dark:focus-within:ring-ash-600 transition-all">
          <div class="flex items-end gap-2 p-2">
            <input
              type="file"
              ref="fileInput"
              accept=".pdf,.docx,.doc"
              multiple
              class="hidden"
              @change="onFileChange"
            />
            <button
              @click="fileInput?.click()"
              :disabled="isStreaming || uploadingFiles"
              class="shrink-0 h-9 w-9 text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 rounded-xl transition-colors flex items-center justify-center disabled:opacity-40"
              :title="uploadingFiles ? 'Uploading…' : 'Lampirkan file (PDF/DOCX/DOC)'"
            >
              <span v-if="uploadingFiles" class="w-4 h-4 border-2 border-ink-500 dark:border-ink-300 border-t-transparent rounded-full animate-spin"></span>
              <span v-else class="text-base leading-none">＋</span>
            </button>
            <textarea
              ref="inputRef"
              v-model="inputText"
              @keydown="handleKeydown"
              :disabled="isStreaming"
              placeholder="Ketik pesan… (Shift+Enter untuk baris baru)"
              rows="1"
              class="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink-900 dark:text-ink-50 focus:outline-none disabled:opacity-50 max-h-32 overflow-y-auto placeholder-ink-500 dark:placeholder-ink-300"
            ></textarea>
            <button
              v-if="isStreaming"
              @click="handleStop"
              class="shrink-0 h-9 w-9 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-colors flex items-center justify-center"
              title="Stop"
            >
              <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1.5"/>
              </svg>
            </button>
            <button
              v-else
              @click="handleSend"
              :disabled="!inputText.trim() && !attachedFiles.length"
              class="shrink-0 h-9 w-9 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
              title="Send"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Delete chat confirm -->
    <div
      v-if="deleteTarget"
      class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      @click.self="deleteTarget = null"
    >
      <div class="bg-white rounded-xl shadow-xl p-5 max-w-sm w-full">
        <h3 class="font-semibold text-slate-800 mb-1.5">Delete this chat?</h3>
        <p class="text-sm text-slate-500 mb-4">
          "<strong>{{ deleteTarget.title || 'Untitled chat' }}</strong>" akan dihapus permanen. Memory tetap aman.
        </p>
        <div class="flex gap-2 justify-end">
          <button @click="deleteTarget = null"
            class="px-3 py-1.5 text-sm rounded-lg border border-slate-200 hover:bg-slate-50">
            Cancel
          </button>
          <button @click="doDeleteChat"
            class="px-3 py-1.5 text-sm rounded-lg bg-red-600 hover:bg-red-700 text-white">
            Delete
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '../stores/chat.js'
import { usePaperStore } from '../stores/paper.js'
import ChatMessage from './ChatMessage.vue'

// Model picker — UI label is shown to the user, value is sent to backend.
// Backend allowlists {V-OPUS, V-GEMINI, V-GPT} and rejects anything else.
const MODELS = [
  { value: 'V-OPUS',   label: 'Claude' },
  { value: 'V-GEMINI', label: 'Gemini' },
  { value: 'V-GPT',    label: 'Chatgpt' },
]
const LS_MODEL_KEY = 'pg_chat_model'

// Light-weight click-outside directive used by the model menu.
const vClickOutside = {
  mounted(el, binding) {
    el.__clickOutsideHandler__ = (event) => {
      if (!(el === event.target || el.contains(event.target))) {
        binding.value(event)
      }
    }
    document.addEventListener('mousedown', el.__clickOutsideHandler__)
  },
  unmounted(el) {
    document.removeEventListener('mousedown', el.__clickOutsideHandler__)
  },
}

const props = defineProps({
  paperId: { type: String, default: null },
})

const emit = defineEmits(['open-preview'])

const chatStore = useChatStore()
const paperStore = usePaperStore()
const {
  currentPaperId,
  conversations,
  currentConversationId,
  messages,
  memory,
  isStreaming,
  currentChat,
} = storeToRefs(chatStore)

const inputText = ref('')
const inputRef = ref(null)
const fileInput = ref(null)
const attachedFiles = ref([])
const attachWarning = ref('')
const uploadingFiles = ref(false)
const messagesContainer = ref(null)
const deleteTarget = ref(null)
const creatingChat = ref(false)
const memoryOpen = ref(false)

const renamingId = ref(null)
const renameDraft = ref('')
const renameInput = ref(null)

// Model picker state — persisted in localStorage; restored on mount.
const modelMenuOpen = ref(false)
const selectedModel = ref(localStorage.getItem(LS_MODEL_KEY) || MODELS[0].value)
const currentModelLabel = computed(
  () => MODELS.find(m => m.value === selectedModel.value)?.label || MODELS[0].label
)

function selectModel(value) {
  if (!MODELS.some(m => m.value === value)) return
  selectedModel.value = value
  localStorage.setItem(LS_MODEL_KEY, value)
  modelMenuOpen.value = false
  chatStore.setModel(value)
}

function closeModelMenu() {
  modelMenuOpen.value = false
}

// Sync the store with the restored selection on mount, BEFORE any sendMessage.
chatStore.setModel(selectedModel.value)

const quickSuggestions = [
  { icon: '✍️', text: 'Bantu tulis abstrak' },
  { icon: '✍️', text: 'Bantu tulis pendahuluan' },
  { icon: '🔍', text: 'Review pendahuluan saya' },
  { icon: '📚', text: 'Cari referensi terkait' },
  { icon: '🎨', text: 'Parafrase paragraf saya' },
  { icon: '🪶', text: 'Perbaiki grammar' },
]

onMounted(async () => {
  if (props.paperId) {
    if (currentPaperId.value !== props.paperId) {
      currentPaperId.value = props.paperId
      await chatStore.loadConversations(props.paperId)
      await chatStore.loadMemory(props.paperId)
    }
    // Auto-open most recent chat, or auto-create one if none exist yet,
    // so the user lands directly inside a chat (same as a "new chat" state).
    if (!currentConversationId.value) {
      const latest = conversations.value[0]
      if (latest) {
        await chatStore.openConversation(latest.id)
      } else {
        await chatStore.newChatForCurrentPaper()
      }
    }
  }
})

watch(
  () => props.paperId,
  async (id) => {
    if (id && id !== currentPaperId.value) {
      currentPaperId.value = id
      currentConversationId.value = null
      messages.value = []
      await chatStore.loadConversations(id)
      await chatStore.loadMemory(id)
      const latest = conversations.value[0]
      if (latest) {
        await chatStore.openConversation(latest.id)
      } else {
        await chatStore.newChatForCurrentPaper()
      }
    }
  }
)

watch(messages, () => nextTick(scrollToBottom), { deep: true })

watch(inputText, () => {
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
      inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 128) + 'px'
    }
  })
})

watch(currentChat, (chat) => {
  if (!chat) return
  const t = (chat.title || '').trim()
  if (!t || t === 'New Chat') return
  const cur = (paperStore.paper.title || '').trim()
  if (!cur || cur === 'Untitled' || cur === 'Untitled Paper') {
    paperStore.paper.title = t
  }
})

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

function formatDate(s) {
  if (!s) return ''
  const d = new Date(s)
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return 'Baru saja'
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm lalu'
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'j lalu'
  if (diff < 7 * 86400000) return Math.floor(diff / 86400000) + 'h lalu'
  return d.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}

async function handleSelectConversation(convId) {
  if (convId === currentConversationId.value) return
  await chatStore.openConversation(convId)
  scrollToBottom()
}

async function createNewChat() {
  if (!currentPaperId.value || creatingChat.value) return
  creatingChat.value = true
  try {
    const conv = await chatStore.newChatForCurrentPaper()
    if (conv) {
      currentConversationId.value = conv.id
      messages.value = []
    }
  } finally {
    creatingChat.value = false
  }
}

function goBack() {
  currentConversationId.value = null
  messages.value = []
}

function startRename(conv) {
  renamingId.value = conv.id
  renameDraft.value = conv.title || ''
  nextTick(() => {
    if (renameInput.value && renameInput.value.focus) {
      renameInput.value.focus()
      renameInput.value.select?.()
    }
  })
}

function cancelRename() {
  renamingId.value = null
  renameDraft.value = ''
}

async function commitRename(conv) {
  const title = renameDraft.value.trim()
  const id = renamingId.value
  renamingId.value = null
  renameDraft.value = ''
  if (!id || !title || title === conv.title) return
  await chatStore.renameConversation(id, title)
}

function confirmDeleteChat(conv) {
  deleteTarget.value = conv
}

async function doDeleteChat() {
  const id = deleteTarget.value?.id
  deleteTarget.value = null
  if (id) await chatStore.deleteConversation(id)
}

async function handleSend() {
  const text = inputText.value.trim()
  if ((!text && !attachedFiles.value.length) || isStreaming.value || !currentConversationId.value) return
  let composed = text

  // Upload attached files first; their extracted text is appended to the message.
  if (attachedFiles.value.length) {
    uploadingFiles.value = true
    try {
      const fd = new FormData()
      attachedFiles.value.forEach(f => fd.append('files', f))
      const res = await paperStore.apiUploadPdfs(fd)
      const texts = res?.data?.pdf_texts || []
      const warnings = res?.data?.warnings || []
      attachWarning.value = warnings.join('; ')
      const names = attachedFiles.value.map(f => f.name).join(', ')
      const fileBlock = texts.length
        ? `\n\n--- File terlampir (${names}) ---\n${texts.join('\n\n')}\n--- akhir file ---`
        : `\n\n[File ${names} dilampirkan tetapi gagal diekstrak]`
      composed = (text || `Saya melampirkan ${attachedFiles.value.length} file. Tolong baca dan beri ringkasan/analisis.`) + fileBlock
      attachedFiles.value = []
    } catch (e) {
      attachWarning.value = 'Upload gagal: ' + (e.message || e)
      uploadingFiles.value = false
      return
    }
    uploadingFiles.value = false
  }

  inputText.value = ''
  await chatStore.sendMessage(composed)
}

function onFileChange(e) {
  const files = Array.from(e.target.files || [])
  addAttachedFiles(files)
  if (fileInput.value) fileInput.value.value = ''
}

function addAttachedFiles(files) {
  const allowed = files.filter(f => /\.(pdf|docx|doc)$/i.test(f.name))
  if (files.length !== allowed.length) {
    attachWarning.value = 'Hanya PDF, DOCX, dan DOC yang didukung.'
  } else {
    attachWarning.value = ''
  }
  const merged = [...attachedFiles.value, ...allowed].slice(0, 5)
  if (merged.length === 5 && (attachedFiles.value.length + allowed.length) > 5) {
    attachWarning.value = 'Maksimal 5 file. Sisanya diabaikan.'
  }
  attachedFiles.value = merged
}

function removeAttachedFile(i) {
  attachedFiles.value = attachedFiles.value.filter((_, idx) => idx !== i)
}

function handleStop() {
  chatStore.stopStreaming()
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function sendSuggestion(text) {
  if (isStreaming.value) return
  inputText.value = text
  handleSend()
}

async function pickOption(text) {
  if (isStreaming.value || !currentConversationId.value) return
  await chatStore.sendMessage(text)
}

function openPreview() {
  emit('open-preview')
}
</script>
