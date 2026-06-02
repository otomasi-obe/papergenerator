<template>
  <div class="flex flex-col h-full overflow-hidden">
    <header class="px-5 py-3 bg-cream-50 dark:bg-ash-800 border-b border-cream-300 dark:border-ash-700 flex items-center gap-2">
      <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 flex-1">AI Chat</h3>
      <button
        @click="$emit('create-new-chat')"
        :disabled="creatingChat || !currentPaperId"
        class="flex items-center gap-1.5 px-3 py-1.5 min-h-[44px] min-w-[44px] bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
      >
        <span class="text-sm leading-none">＋</span>
        {{ creatingChat ? 'Creating…' : 'New chat' }}
      </button>
    </header>

    <div class="flex-1 overflow-y-auto p-3">
      <p v-if="currentPaperId" class="text-[11px] text-[var(--text-muted)] mb-2 px-1">
        Pilih chat yang sudah ada, atau buat chat baru.
      </p>
      <div v-if="!currentPaperId" class="px-3 py-10 text-center">
        <span class="inline-block w-5 h-5 border-2 border-brown-400 dark:border-cream-400 border-t-transparent rounded-full animate-spin mb-3"></span>
        <p class="text-xs text-[var(--text-muted)]">Paper sedang disiapkan…</p>
        <p class="text-[10px] text-[var(--text-muted)] mt-1 opacity-70">Chat akan aktif setelah paper tersimpan.</p>
      </div>
      <div v-else-if="conversations.length === 0" class="px-3 py-12 text-center text-xs text-[var(--text-muted)]">
        Belum ada chat. Klik <strong>+ New chat</strong> untuk memulai.
      </div>

      <div class="space-y-1.5">
        <div
          v-for="(conv, idx) in conversations"
          :key="conv.id"
          :class="[
            'group flex items-center gap-2 rounded-lg px-3 py-2.5 cursor-pointer transition-all',
            idx === 0
              ? 'bg-brown-50 dark:bg-ash-700 border-2 border-brown-400 dark:border-cream-500 shadow-sm'
              : 'hover:bg-[var(--bg-surface)] hover:shadow-sm border border-transparent hover:border-[var(--border-soft)]'
          ]"
          @click="$emit('select-conversation', conv.id)"
        >
          <span class="text-base leading-none">
            {{ idx === 0 ? '💬' : '💭' }}
          </span>
          <div class="min-w-0 flex-1">
            <input
              v-if="renamingId === conv.id"
              v-model="renameDraft"
              @click.stop
              @keyup.enter="commitRename(conv)"
              @keyup.escape="cancelRename"
              @blur="commitRename(conv)"
              class="w-full text-xs px-1.5 py-0.5 border border-indigo-300 dark:border-indigo-600 bg-[var(--bg-surface)] text-[var(--text-strong)] rounded outline-none focus:ring-1 focus:ring-indigo-300 dark:focus:ring-indigo-600"
              :ref="el => (renameInput = el)"
            />
            <div v-else class="text-sm text-[var(--text-strong)] truncate leading-snug">
              {{ conv.title || 'Untitled chat' }}
            </div>
            <div class="text-[10px] text-[var(--text-muted)] mt-0.5">
              {{ conv.message_count || 0 }} msg · {{ formatDate(conv.updated_at) }}
            </div>
          </div>
          <button
            v-if="renamingId !== conv.id"
            @click.stop="startRename(conv)"
            class="opacity-0 group-hover:opacity-100 text-[var(--text-muted)] hover:text-[var(--text-strong)] text-xs min-h-[44px] min-w-[44px] flex items-center justify-center"
            title="Rename"
            aria-label="Rename conversation"
          ><span aria-hidden="true">✎</span></button>
          <button
            v-if="renamingId !== conv.id"
            @click.stop="$emit('delete-conversation', conv)"
            class="opacity-0 group-hover:opacity-100 text-[var(--text-muted)] hover:text-red-500 text-xs min-h-[44px] min-w-[44px] flex items-center justify-center"
            title="Delete"
            aria-label="Delete conversation"
          ><span aria-hidden="true">🗑</span></button>
        </div>
      </div>

      <!-- Memory section (collapsible) -->
      <ChatMemorySection
        :memory="memory"
        :is-open="memoryOpen"
        :current-paper-id="currentPaperId"
        @toggle="$emit('toggle-memory')"
        @delete-entry="$emit('delete-memory-entry', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref } from 'vue'
import ChatMemorySection from './ChatMemorySection.vue'

interface Conversation {
  id: number
  title: string
  message_count: number
  updated_at: string
}

interface MemoryEntry {
  id: number
  kind: string
  key: string
  value: string
}

interface Props {
  conversations: Conversation[]
  currentPaperId: string | null
  creatingChat: boolean
  memory: MemoryEntry[]
  memoryOpen: boolean
}

defineProps<Props>()

defineEmits<{
  (e: 'create-new-chat'): void
  (e: 'select-conversation', id: number): void
  (e: 'rename-conversation', id: number, title: string): void
  (e: 'delete-conversation', conv: Conversation): void
  (e: 'toggle-memory'): void
  (e: 'delete-memory-entry', id: number): void
}>()

const renamingId = ref<number | null>(null)
const renameDraft = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

function startRename(conv: Conversation): void {
  renamingId.value = conv.id
  renameDraft.value = conv.title || ''
  nextTick(() => {
    if (renameInput.value && renameInput.value.focus) {
      renameInput.value.focus()
      renameInput.value.select?.()
    }
  })
}

function cancelRename(): void {
  renamingId.value = null
  renameDraft.value = ''
}

function commitRename(conv: Conversation): void {
  const title = renameDraft.value.trim()
  const id = renamingId.value
  renamingId.value = null
  renameDraft.value = ''
  if (!id || !title || title === conv.title) return
  emit('rename-conversation', id, title)
}

function formatDate(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return 'Baru saja'
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm lalu'
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'j lalu'
  if (diff < 7 * 86400000) return Math.floor(diff / 86400000) + 'h lalu'
  return d.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}

const emit = defineEmits<{
  (e: 'create-new-chat'): void
  (e: 'select-conversation', id: number): void
  (e: 'rename-conversation', id: number, title: string): void
  (e: 'delete-conversation', conv: Conversation): void
  (e: 'toggle-memory'): void
  (e: 'delete-memory-entry', id: number): void
}>()
</script>
