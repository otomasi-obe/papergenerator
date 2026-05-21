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
          ><span class="sr-only">{{ isStreaming ? 'AI is thinking' : 'Online' }}</span></span>
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
        <!-- Empty-state hero: no messages yet. Offers entry chips + quick
             prompts to seed a focused first turn instead of staring at a
             blank textarea. -->
        <div
          v-if="!messages.length && !isStreaming"
          class="empty-hero flex flex-col items-center justify-center min-h-full px-6 py-8 text-center"
        >
          <div class="text-3xl mb-4" aria-hidden="true">📝</div>
          <h2 class="text-xl font-semibold text-ink-900 dark:text-ink-50 mb-2">
            Mau buat paper apa?
          </h2>
          <p class="text-sm text-ink-600 dark:text-ink-300 mb-6 max-w-md">
            Pilih path di bawah, atau ketik bebas.
          </p>
          <ActionChips
            :chips="entryChips"
            @select="onEntryPick"
            class="justify-center"
          />
          <div class="mt-8 text-xs uppercase tracking-wider text-ink-500 dark:text-ink-400">
            atau quick start
          </div>
          <div class="mt-3 flex flex-col gap-2 items-center">
            <button
              v-for="(qp, i) in quickPrompts"
              :key="i"
              @click="onEntryPick(qp.value)"
              class="text-sm text-brown-700 dark:text-cream-200 hover:underline"
            >
              • {{ qp.label }}
            </button>
          </div>
        </div>

        <ChatMessage
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
          :is-streaming="isStreaming && msg === messages[messages.length - 1] && msg.role === 'assistant'"
          @pick-option="pickOption"
          @chip-select="onChipSelect"
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
      <div v-if="showSuggestions && !inputText" class="px-4 pt-2 bg-cream-50 dark:bg-ash-800 border-t border-cream-300 dark:border-ash-700">
        <div class="flex flex-wrap gap-1.5 mb-2">
          <button
            v-for="s in quickSuggestions"
            :key="s.text"
            @click="sendSuggestion(s.text)"
            :disabled="isStreaming || (activeJob && activeJob.active)"
            class="text-[11px] px-2.5 py-1 rounded-full bg-cream-100 dark:bg-ash-700 hover:bg-brown-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 text-ink-800 dark:text-ink-100 transition-colors border border-cream-300 dark:border-ash-600 disabled:opacity-50 disabled:cursor-not-allowed"
            :title="s.text"
          >
            <span class="mr-1" aria-hidden="true">{{ s.icon }}</span>{{ s.text }}
          </button>
        </div>
      </div>

      <!-- Active-job banner: another chat in this paper is generating a full
           paper. We let the user keep doing other things, but the chat input
           is locked until the job finishes. -->
      <div
        v-if="activeJob && activeJob.active"
        class="mx-4 mb-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 text-amber-900 dark:text-amber-200 text-xs flex items-start gap-2"
      >
        <span class="text-base shrink-0">⏳</span>
        <div class="flex-1 leading-snug">
          <div class="font-medium">Sedang generate paper di chat lain</div>
          <div class="opacity-80 mt-0.5">"{{ activeJob.prompt }}" · {{ formatElapsed(activeJob.elapsed_seconds) }}</div>
          <div class="opacity-70 mt-0.5">Kamu bisa lakukan hal lain dulu (edit Section, lihat Figures, baca Files). Chat akan kembali aktif setelah generate selesai.</div>
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
            <button
              @click="showSuggestions = !showSuggestions"
              :aria-expanded="showSuggestions && !inputText"
              class="shrink-0 h-9 px-2 text-[11px] text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 rounded-xl transition-colors"
              title="Saran"
            >💡 Saran</button>
            <input
              type="file"
              ref="fileInput"
              accept=".pdf,.docx,.doc"
              multiple
              class="hidden"
              @change="onFileChange"
            />
            <div class="relative shrink-0" v-click-outside="closeAttachMenu">
              <button
                @click="toggleAttachMenu"
                :disabled="isStreaming || uploadingFiles"
                class="h-9 w-9 text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 rounded-xl transition-colors flex items-center justify-center disabled:opacity-40"
                :title="uploadingFiles ? 'Uploading…' : 'Lampirkan'"
              >
                <span v-if="uploadingFiles" class="w-4 h-4 border-2 border-ink-500 dark:border-ink-300 border-t-transparent rounded-full animate-spin"></span>
                <span v-else class="text-base leading-none">＋</span>
              </button>
              <div v-if="attachMenuOpen"
                class="absolute bottom-full left-0 mb-2 z-30 w-44 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-lg overflow-hidden">
                <button
                  type="button"
                  @click="pickUpload"
                  class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2"
                >
                  <span>📤</span><span>Upload baru</span>
                </button>
                <button
                  type="button"
                  @click="openExistingFiles"
                  class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2 border-t border-cream-300 dark:border-ash-600"
                >
                  <span>📁</span><span>Dari file paper ini</span>
                </button>
              </div>
            </div>
            <textarea
              ref="inputRef"
              v-model="inputText"
              @keydown="handleKeydown"
              :disabled="activeJob && activeJob.active"
              :placeholder="(activeJob && activeJob.active) ? 'Chat terkunci sampai generate paper selesai…' : (isStreaming ? 'Sedang menjawab… bisa ketik draft berikutnya' : 'Ketik pesan… (Shift+Enter untuk baris baru)')"
              rows="1"
              class="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink-900 dark:text-ink-50 focus:outline-none disabled:opacity-50 max-h-32 overflow-y-auto placeholder-ink-500 dark:placeholder-ink-300"
            ></textarea>
            <button
              v-if="isStreaming"
              @click="handleStop"
              class="shrink-0 h-9 w-9 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-colors flex items-center justify-center"
              title="Stop"
              aria-label="Stop generating"
            >
              <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1.5"/>
              </svg>
            </button>
            <button
              v-else
              @click="handleSend"
              :disabled="(!inputText.trim() && !attachedFiles.length) || (activeJob && activeJob.active)"
              class="shrink-0 h-9 w-9 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
              title="Send"
              aria-label="Send message"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"/>
              </svg>
            </button>
          </div>
          <p class="text-[10px] text-ink-500 dark:text-ink-400 px-2 pb-1">Enter to send · Shift+Enter for new line</p>
        </div>
      </div>
    </template>

    <AppDialog v-if="deleteTarget" :open="!!deleteTarget" title="Delete this chat?" @close="deleteTarget = null">
      <p class="text-sm text-ink-600 dark:text-ink-300">
        "<strong>{{ deleteTarget.title || 'Untitled chat' }}</strong>" akan dihapus permanen. Memory tetap aman.
      </p>
      <template #actions>
        <button @click="deleteTarget = null" class="px-3 py-1.5 text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button @click="doDeleteChat" class="px-3 py-1.5 text-sm rounded-lg bg-red-600 hover:bg-red-700 text-white">Delete</button>
      </template>
    </AppDialog>

    <!-- File picker (existing paper files) -->
    <AppDialog v-if="filePickerOpen" :open="filePickerOpen" title="Pilih file dari paper ini" @close="filePickerOpen = false">
      <div class="max-h-[50vh] overflow-y-auto -mx-4 px-4">
        <div v-if="paperFilesLoading" class="text-center py-6 text-xs text-ink-500 dark:text-ink-300">Loading…</div>
        <div v-else-if="!paperFiles.length" class="text-center py-6 text-xs text-ink-500 dark:text-ink-300">
          Belum ada file. Upload dulu di tab Files.
        </div>
        <ul v-else class="divide-y divide-cream-200 dark:divide-ash-700">
          <li v-for="f in paperFiles" :key="f.id"
              class="flex items-center gap-2 px-2 py-2 cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 rounded"
              @click="togglePickFile(f)">
            <input type="checkbox" :checked="pickedFileIds.has(f.id)" class="pointer-events-none" />
            <span>{{ extIcon(f.ext) }}</span>
            <div class="min-w-0 flex-1">
              <div class="text-xs text-ink-900 dark:text-ink-50 truncate" :title="f.original_name">{{ f.original_name }}</div>
              <div class="text-[10px] text-ink-500 dark:text-ink-300">{{ humanSize(f.size_bytes) }}</div>
            </div>
          </li>
        </ul>
      </div>
      <template #actions>
        <button @click="filePickerOpen = false" class="px-3 py-1.5 text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button @click="confirmPickFiles" :disabled="!pickedFileIds.size"
                class="px-3 py-1.5 text-sm rounded-lg bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-40">
          Lampirkan ({{ pickedFileIds.size }})
        </button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '../stores/chat.js'
import { usePaperStore } from '../stores/paper.js'
import api from '../api/index.js'
import ChatMessage from './ChatMessage.vue'
import AppDialog from './AppDialog.vue'
import ActionChips from './ActionChips.vue'

// Model picker — UI label is shown to the user, value is sent to backend.
// Backend allowlists {V-OPUS, V-GEMINI, V-GPT} and rejects anything else.
const MODELS = [
  { value: 'V-OPUS',   label: 'Claude Opus 4.7' },
  { value: 'V-CLAUDE', label: 'Claude Sonnet 4.5' },
  { value: 'V-GPT',    label: 'ChatGPT 5.5' },
  { value: 'V-GLM',    label: 'GLM 5' },
  { value: 'V-DEEPSEEK', label: 'DeepSeek v4 Pro' },
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
  activeJob,
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
const showSuggestions = ref(true)

const renamingId = ref(null)
const renameDraft = ref('')
const renameInput = ref(null)

// Attach menu (＋) — opens a 2-option dropdown: Upload baru / Pilih file paper.
const attachMenuOpen = ref(false)
function toggleAttachMenu() { attachMenuOpen.value = !attachMenuOpen.value }
function closeAttachMenu() { attachMenuOpen.value = false }
function pickUpload() {
  attachMenuOpen.value = false
  fileInput.value?.click()
}

// File picker state (option 2: pick from already-uploaded paper files).
const filePickerOpen = ref(false)
const paperFiles = ref([])
const paperFilesLoading = ref(false)
const pickedFileIds = ref(new Set())

async function openExistingFiles() {
  attachMenuOpen.value = false
  if (!currentPaperId.value) return
  filePickerOpen.value = true
  pickedFileIds.value = new Set()
  paperFilesLoading.value = true
  try {
    const res = await api.get(`/api/papers/${currentPaperId.value}/files`)
    paperFiles.value = res.data?.files || []
  } catch (e) {
    paperFiles.value = []
    attachWarning.value = 'Gagal memuat daftar file: ' + (e.message || e)
  } finally {
    paperFilesLoading.value = false
  }
}

function togglePickFile(f) {
  // Force a new Set so Vue re-renders the checkbox state.
  const next = new Set(pickedFileIds.value)
  if (next.has(f.id)) next.delete(f.id)
  else next.add(f.id)
  pickedFileIds.value = next
}

async function confirmPickFiles() {
  if (!pickedFileIds.value.size) return
  const ids = [...pickedFileIds.value]
  filePickerOpen.value = false
  // Fetch extracted text per file via the existing /preview endpoint, then
  // append as pseudo-attachments. We use a synthetic File-shape entry on
  // attachedFiles so the existing send pipeline handles them uniformly.
  for (const id of ids) {
    const f = paperFiles.value.find(x => x.id === id)
    if (!f) continue
    try {
      const res = await api.get(`/api/papers/${currentPaperId.value}/files/${id}/preview`)
      const text = res.data?.text || ''
      attachedFiles.value = [...attachedFiles.value, {
        name: f.original_name,
        __preExtracted: true,
        __text: text,
        __fileId: id,
      }].slice(0, 10)
    } catch (e) {
      attachWarning.value = 'Gagal baca file: ' + (e.message || e)
    }
  }
}

function extIcon(ext) {
  switch ((ext || '').toLowerCase()) {
    case '.pdf': return '📕'
    case '.docx':
    case '.doc': return '📘'
    case '.txt': return '📄'
    case '.md': return '📝'
    default: return '📁'
  }
}
function humanSize(b) {
  if (!b) return '0 B'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(1) + ' MB'
}

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

// Entry chips and quick prompts shown in the empty-state hero. Picking any
// of them just sends a message to the AI; the AI then routes via RouteIntent
// (Tier-0) and may follow up with ProposeChips for next steps.
const entryChips = [
  { label: 'Mulai dari 0',         value: 'saya mau mulai dari 0' },
  { label: 'Sudah ada literatur',  value: 'saya sudah punya literatur' },
  { label: 'Sudah ada metode',     value: 'saya sudah ada metode' },
  { label: 'Sudah ada data',       value: 'saya sudah punya data' },
]

const quickPrompts = [
  { label: 'Lanjutkan dari memory',     value: 'lanjutkan dari yang kita bahas sebelumnya' },
  { label: 'Pakai literatur yang ada',  value: 'pakai literatur yang sudah saya kumpulkan' },
  { label: 'Lihat draft saya',          value: 'tampilkan draft paper saya' },
]

function onEntryPick(value) {
  if (!value || isStreaming.value || !currentConversationId.value) return
  if (activeJob.value && activeJob.value.active) return
  chatStore.sendMessage(value)
}

function onChipSelect(value) {
  if (!value || isStreaming.value || !currentConversationId.value) return
  if (activeJob.value && activeJob.value.active) return
  chatStore.sendMessage(value)
}

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
  if (inputText.value.length > 0) showSuggestions.value = false
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

function formatElapsed(sec) {
  if (!sec || sec < 60) return `${sec || 0}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
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
  if (activeJob.value && activeJob.value.active) return
  let composed = text

  // Split attached entries: real File objects need an upload round-trip;
  // entries flagged __preExtracted come from the existing-files picker and
  // already carry their text + persistent file_id.
  const realFiles = attachedFiles.value.filter(f => !f.__preExtracted)
  const preExtracted = attachedFiles.value.filter(f => f.__preExtracted)

  if (realFiles.length || preExtracted.length) {
    uploadingFiles.value = true
    try {
      const fileEntries = []
      let warnings = []
      // Upload new files via the per-paper endpoint so they become real
      // PaperFile rows the AI can find via ListAttachedFiles and classify
      // via ClassifyFile. Falls back to /api/upload-pdfs (no persistence)
      // when the chat has no paper context.
      if (realFiles.length) {
        if (currentPaperId.value) {
          const fd = new FormData()
          realFiles.forEach(f => fd.append('files', f))
          const res = await api.post(
            `/api/papers/${currentPaperId.value}/files`,
            fd,
            { headers: { 'Content-Type': 'multipart/form-data' } },
          )
          const saved = res?.data?.files || []
          warnings = res?.data?.warnings || []
          for (const s of saved) {
            fileEntries.push({
              id: s.id,
              name: s.original_name || s.filename || '',
              text: s.text || '',
            })
          }
        } else {
          const fd = new FormData()
          realFiles.forEach(f => fd.append('files', f))
          const res = await paperStore.apiUploadPdfs(fd)
          const texts = res?.data?.pdf_texts || []
          warnings = res?.data?.warnings || []
          texts.forEach((t, i) => {
            fileEntries.push({ id: null, name: realFiles[i]?.name || '', text: t })
          })
        }
      }
      for (const f of preExtracted) {
        fileEntries.push({
          id: f.__fileId ?? null,
          name: f.name || '',
          text: f.__text || '',
        })
      }

      attachWarning.value = warnings.join('; ')
      const names = attachedFiles.value.map(f => f.name).join(', ')
      const blocks = fileEntries.map(e => {
        const header = e.id != null
          ? `--- File terlampir: ${e.name} [file_id=${e.id}] ---`
          : `--- File terlampir: ${e.name} ---`
        return `${header}\n${e.text || '(ekstrak teks gagal / kosong)'}\n--- akhir file ---`
      })
      const fileBlock = blocks.length
        ? '\n\n' + blocks.join('\n\n')
        : `\n\n[File ${names} dilampirkan tetapi gagal diekstrak]`
      const idsHint = fileEntries.filter(e => e.id != null).map(e => e.id).join(',')
      const idsLine = idsHint
        ? `\n[FILE_IDS=${idsHint}] (use ClassifyFile after asking 'ini file apa?')`
        : ''
      composed = (text || `Saya melampirkan ${attachedFiles.value.length} file. Tolong tanya dulu "ini file apa?" untuk masing-masing file dengan ProposeChips, lalu panggil ClassifyFile sesuai jawaban user.`)
        + idsLine
        + fileBlock
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
  inputRef.value?.focus()
}

async function pickOption(text) {
  if (isStreaming.value || !currentConversationId.value) return
  await chatStore.sendMessage(text)
}

function openPreview() {
  emit('open-preview')
}
</script>
