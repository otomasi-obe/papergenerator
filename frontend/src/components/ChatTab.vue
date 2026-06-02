<template>
  <div class="flex flex-col h-full overflow-hidden bg-cream-100/40 dark:bg-ash-850">
    <!-- ─── PICKER VIEW: list of chats only (no active chat yet) ─── -->
    <template v-if="!currentConversationId">
      <header class="px-5 py-3 bg-cream-50 dark:bg-ash-800 border-b border-cream-300 dark:border-ash-700 flex items-center gap-2">
        <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 flex-1">AI Chat</h3>
        <button
          @click="createNewChat"
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
              conv.id === currentConversationId
                ? 'bg-brown-100 dark:bg-ash-700 border-l-4 border-brown-600 dark:border-cream-400 shadow-sm'
                : 'hover:bg-[var(--bg-surface)] hover:shadow-sm border border-transparent hover:border-[var(--border-soft)]'
            ]"
            @click="handleSelectConversation(conv.id)"
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
                ref="renameInput"
              />
              <div v-else class="text-sm text-[var(--text-strong)] truncate leading-snug">
                {{ conversationTitle(conv.title) }}
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
              @click.stop="confirmDeleteChat(conv)"
              class="opacity-0 group-hover:opacity-100 text-[var(--text-muted)] hover:text-red-500 text-xs min-h-[44px] min-w-[44px] flex items-center justify-center"
              title="Delete"
              aria-label="Delete conversation"
            ><span aria-hidden="true">🗑</span></button>
          </div>
        </div>

        <!-- Memory section (collapsible) -->
        <div v-if="currentPaperId" class="mt-5 border-t border-[var(--border-soft)] pt-3">
          <button
            @click="memoryOpen = !memoryOpen"
            class="w-full flex items-center justify-between min-h-[44px] text-xs font-medium text-[var(--text-base)] hover:text-[var(--text-strong)]"
            :title="`Project memory (${memory.length} items)`"
          >
            <span class="flex items-center gap-1.5">
              🧠
              <span
                v-if="memory.length"
                class="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-indigo-100 text-indigo-700 text-[10px] font-semibold"
              >{{ memory.length }}</span>
            </span>
            <span class="text-[var(--text-muted)]">{{ memoryOpen ? '▾' : '▸' }}</span>
          </button>
          <div v-if="memoryOpen" class="mt-2 space-y-1.5">
            <div v-if="memory.length === 0" class="text-[11px] text-[var(--text-muted)] px-1">
              Empty. AI akan menyimpan fakta penting paper ini secara otomatis.
            </div>
            <div
              v-for="m in memory"
              :key="m.id"
              class="bg-[var(--bg-surface)] border border-[var(--border-soft)] rounded-md px-2 py-1.5 text-[11px] flex items-start gap-1.5 group/mem"
            >
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5 mb-0.5">
                  <span class="text-[var(--text-muted)] text-[10px] uppercase tracking-wide">{{ m.kind }}</span>
                  <span class="text-[var(--text-strong)] font-medium truncate">{{ m.key }}</span>
                </div>
                <div class="text-[var(--text-base)] leading-snug">{{ m.value }}</div>
              </div>
              <button
                @click="chatStore.deleteMemoryEntry(m.id)"
                class="opacity-0 group-hover/mem:opacity-100 text-[var(--text-muted)] hover:text-red-500 min-h-[44px] min-w-[44px] flex items-center justify-center"
                title="Forget"
                aria-label="Forget memory entry"
              ><span aria-hidden="true">✕</span></button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ─── ACTIVE CHAT VIEW ─── -->
    <template v-else>
      <!-- Messages -->
      <div ref="messagesContainer" @scroll="checkScrollPosition" class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        <!-- Empty-state hero: no messages yet. Offers entry chips + quick
             prompts to seed a focused first turn instead of staring at a
             blank textarea. -->
        <div
          v-if="!messages.length && !isStreaming"
          class="empty-hero flex flex-col items-center justify-center min-h-full px-6 py-8 text-center"
        >
          <div class="text-3xl mb-4" aria-hidden="true">📝</div>
          <h2 class="text-xl font-semibold text-ink-900 dark:text-ink-50 mb-2">
            Halo saya paperfully siap menjadi asisten anda, sudah sampai mana progres anda ?
          </h2>
          <ActionChips
            :chips="entryChips"
            @select="onEntryPick"
            class="justify-center"
          />
        </div>

        <ChatMessage
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
          :is-streaming="isStreaming && msg === messages[messages.length - 1] && msg.role === 'assistant'"
          @pick-option="pickOption"
          @chip-select="onChipSelect"
          @chart-accept="onChartAccept"
          @chart-regenerate="onChartRegenerate"
          @file-review-pick="onFileReviewPick"
          @multi-question-submit="onMultiQuestionSubmit"
          @revisi-accepted="onRevisiAccept"
          @revisi-rejected="onRevisiReject"
          @review-cancel="onReviewCancel"
        />

        <div
          v-if="showInlineStreamingIndicator"
          class="flex gap-3 justify-start"
        >
          <div class="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-br from-brown-400 to-brown-600 flex items-center justify-center mt-1 shadow-sm">
            <svg class="w-4 h-4 text-cream-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/>
            </svg>
          </div>
          <div class="max-w-[80%] rounded-2xl px-4 py-3 ai-status-bubble">
            <div class="flex items-center gap-2 text-xs text-ink-800 dark:text-ink-100">
              <span class="inline-flex items-center gap-1 shrink-0" aria-hidden="true">
                <span class="w-1.5 h-1.5 rounded-full bg-brown-500 dark:bg-brown-300 animate-bounce" style="animation-delay: 0ms"></span>
                <span class="w-1.5 h-1.5 rounded-full bg-brown-500 dark:bg-brown-300 animate-bounce" style="animation-delay: 150ms"></span>
                <span class="w-1.5 h-1.5 rounded-full bg-brown-500 dark:bg-brown-300 animate-bounce" style="animation-delay: 300ms"></span>
              </span>
              <Transition name="fade" mode="out-in">
                <span :key="streamingIndicatorText" class="font-medium leading-snug">{{ streamingIndicatorText }}</span>
              </Transition>
              <span class="font-mono text-[10px] opacity-70 shrink-0">{{ streamingElapsed }}s</span>
            </div>
          </div>
        </div>
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
            class="flex-1 px-2.5 py-1 min-h-[44px] text-[11px] font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white"
          >✓ Terima semua</button>
          <button
            @click="paperStore.rejectAllProposals()"
            class="flex-1 px-2.5 py-1 min-h-[44px] text-[11px] font-semibold rounded-md bg-rose-100 hover:bg-rose-200 dark:bg-rose-900/40 dark:hover:bg-rose-900/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800"
          >✕ Tolak semua</button>
        </div>
      </div>

      <!-- Suggestion chips -->
      <div v-if="showSuggestions && !inputText" class="px-4 pt-2 bg-cream-50 dark:bg-ash-800 border-t border-cream-300 dark:border-ash-700">
        <div class="flex flex-wrap gap-2 mb-2">
          <button
            v-for="s in quickSuggestions"
            :key="s.key"
            @click="sendSuggestion(s)"
            :disabled="isStreaming || (activeJob && activeJob.active)"
            class="text-[11px] px-2.5 py-1 min-h-[44px] rounded-full bg-cream-100 dark:bg-ash-700 hover:bg-brown-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 text-ink-800 dark:text-ink-100 transition-colors border border-cream-300 dark:border-ash-600 disabled:opacity-50 disabled:cursor-not-allowed"
            :title="s.text"
          >
            {{ s.label }}
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

      <!-- Error banner with retry -->
      <div
        v-if="lastError"
        class="mx-4 mb-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-300 dark:border-red-700 text-red-900 dark:text-red-200 text-xs flex items-start gap-2"
      >
        <span class="text-base shrink-0">⚠️</span>
        <div class="flex-1 leading-snug">
          <div class="font-medium">Terjadi kesalahan</div>
          <div class="opacity-90 mt-0.5">{{ lastError }}</div>
        </div>
        <button
          @click="retryLastMessage"
          class="shrink-0 px-2.5 py-1 min-h-[36px] text-[11px] font-semibold rounded-md bg-red-600 hover:bg-red-700 text-white transition-colors"
        >↻ Retry</button>
        <button
          @click="lastError = null"
          class="shrink-0 text-red-500 hover:text-red-700 dark:text-red-300 dark:hover:text-red-100 min-h-[36px] min-w-[36px] flex items-center justify-center"
          title="Tutup"
        >✕</button>
      </div>

      <!-- Input -->
      <div class="px-4 pb-3 bg-cream-50 dark:bg-ash-800">
        <!-- Upload progress bar (prominent) -->
        <div v-if="uploadingFiles" class="mb-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-medium text-blue-900 dark:text-blue-100">
              Uploading {{ uploadFileCount.current }} of {{ uploadFileCount.total }} files
            </span>
            <span class="text-xs font-mono text-blue-700 dark:text-blue-300">{{ uploadProgress }}%</span>
          </div>
          <div class="h-2 rounded-full bg-blue-100 dark:bg-blue-900/40 overflow-hidden">
            <div
              class="h-full rounded-full bg-blue-600 dark:bg-blue-400 transition-all duration-300 ease-out"
              :style="{ width: uploadProgress + '%' }"
            ></div>
          </div>
          <p class="text-[10px] text-blue-700 dark:text-blue-300 mt-1.5">Please wait while files are being uploaded...</p>
        </div>

        <!-- Attached files preview -->
        <div v-if="attachedFiles.length" class="mb-2 flex flex-wrap gap-1.5">
          <div
            v-for="(f, i) in attachedFiles"
            :key="i"
            :class="[
              'flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px]',
              f.uploadError
                ? 'bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-800 text-red-900 dark:text-red-100'
                : f.uploading
                ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-300 dark:border-blue-800 text-blue-900 dark:text-blue-100'
                : 'bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600 text-ink-900 dark:text-ink-50'
            ]"
          >
            <span v-if="f.uploading" class="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></span>
            <span v-else>{{ f.uploadError ? '⚠️' : f.__preExtracted ? '✓' : '📄' }}</span>
            <div class="flex flex-col min-w-0">
              <span class="truncate max-w-[160px]" :title="f.name">{{ f.name }}</span>
              <span v-if="f.uploadError" class="text-[10px] text-red-700 dark:text-red-300">{{ f.uploadError }}</span>
              <span v-else-if="f.uploading" class="text-[10px] text-blue-700 dark:text-blue-300">Uploading...</span>
              <span v-else-if="f.__preExtracted" class="text-[10px] text-emerald-700 dark:text-emerald-300">Ready</span>
            </div>
            <button
              v-if="f.canRetry"
              @click="retryUpload(i)"
              class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200 ml-1 min-h-[44px] min-w-[44px]"
              title="Retry upload"
              aria-label="Retry upload"
            ><span aria-hidden="true">↻</span></button>
            <button
              v-if="!f.uploading"
              @click="removeAttachedFile(i)"
              class="text-ink-500 dark:text-ink-300 hover:text-rose-500 ml-1 min-h-[44px] min-w-[44px]"
              title="Remove"
              aria-label="Remove attached file"
            ><span aria-hidden="true">✕</span></button>
          </div>
        </div>
        <p v-if="attachWarning" class="text-[10px] text-amber-700 dark:text-amber-300 mb-1">{{ attachWarning }}</p>

        <div class="rounded-2xl border-2 border-cream-400 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-sm focus-within:border-brown-500 dark:focus-within:border-cream-400 focus-within:ring-4 focus-within:ring-cream-200 dark:focus-within:ring-ash-600 transition-all">
          <div class="flex items-center gap-2 p-2">
            <button
              @click="showSuggestions = !showSuggestions"
              :aria-expanded="showSuggestions && !inputText"
              class="shrink-0 min-h-[44px] min-w-[44px] px-2 text-[11px] text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 rounded-xl transition-colors"
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
                class="min-h-[44px] min-w-[44px] text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 rounded-xl transition-colors flex items-center justify-center disabled:opacity-40"
                :title="uploadingFiles ? `Uploading ${uploadFileCount.current}/${uploadFileCount.total}…` : 'Lampirkan'"
                :aria-label="uploadingFiles ? `Uploading ${uploadFileCount.current} of ${uploadFileCount.total} files` : 'Attach files'"
              >
                <span v-if="uploadingFiles" class="w-4 h-4 border-2 border-ink-500 dark:border-ink-300 border-t-transparent rounded-full animate-spin"></span>
                <span v-else class="text-base leading-none">＋</span>
              </button>
              <div v-if="attachMenuOpen"
                class="absolute bottom-full left-0 mb-2 z-30 w-48 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-lg overflow-hidden">
                <button
                  type="button"
                  @click="pickUpload"
                  class="w-full text-left px-3 py-2 min-h-[44px] text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2"
                >
                  <span>📤</span><span>Upload file (PDF/DOCX)</span>
                </button>
                <button
                  type="button"
                  @click="openPasteText"
                  class="w-full text-left px-3 py-2 min-h-[44px] text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2 border-t border-cream-300 dark:border-ash-600"
                >
                  <span>📋</span><span>Paste teks</span>
                </button>
                <button
                  type="button"
                  @click="openExistingFiles"
                  class="w-full text-left px-3 py-2 min-h-[44px] text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2 border-t border-cream-300 dark:border-ash-600"
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
              :placeholder="(activeJob && activeJob.active) ? 'Terkunci saat generate…' : (isStreaming ? 'AI mengetik…' : 'Ketik pesan…')"
              rows="1"
              class="chat-input-textarea flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink-900 dark:text-ink-50 focus:outline-none disabled:opacity-50 max-h-32 overflow-y-auto placeholder-ink-500 dark:placeholder-ink-300"
            ></textarea>
            <button
              v-if="isStreaming"
              @click="handleStop"
              class="shrink-0 min-h-[44px] min-w-[44px] bg-red-600 hover:bg-red-700 text-white rounded-xl transition-colors flex items-center justify-center"
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
              class="shrink-0 min-h-[44px] min-w-[44px] bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
              title="Send"
              aria-label="Send message"
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

    <AppDialog v-if="deleteTarget" :open="!!deleteTarget" title="Delete this chat?" @close="deleteTarget = null">
      <p class="text-sm text-ink-600 dark:text-ink-300">
        "<strong>{{ deleteTarget.title || 'Untitled chat' }}</strong>" akan dihapus permanen. Memory tetap aman.
      </p>
      <template #actions>
        <button @click="deleteTarget = null" class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button @click="doDeleteChat" class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg bg-red-600 hover:bg-red-700 text-white">Delete</button>
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
              <div class="text-[10px] text-ink-500 dark:text-ink-300">{{ humanSize(f.size_bytes || f.size || 0) }}</div>
            </div>
          </li>
        </ul>
      </div>
      <template #actions>
        <button @click="filePickerOpen = false" class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button @click="confirmPickFiles" :disabled="!pickedFileIds.size"
                class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-40">
          Lampirkan ({{ pickedFileIds.size }})
        </button>
      </template>
    </AppDialog>
    <!-- Paste-text dialog: lampirkan blok teks bebas (mis. salinan abstract / catatan
         dari Word) tanpa harus upload file. Diserahkan ke chat sebagai "file" semu
         dengan nama yang user beri. -->
    <AppDialog v-if="pasteTextOpen" :open="pasteTextOpen" title="Paste teks" @close="pasteTextOpen = false">
      <div class="space-y-2">
        <label class="block text-xs text-ink-700 dark:text-ink-200">
          Nama (opsional)
          <input
            v-model="pasteTextName"
            type="text"
            placeholder="e.g. Catatan metode, Outline bab 2"
            class="mt-1 w-full px-2.5 py-1.5 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 text-ink-900 dark:text-ink-50 text-xs focus:outline-none focus:ring-2 focus:ring-brown-300 dark:focus:ring-cream-400"
          />
        </label>
        <label class="block text-xs text-ink-700 dark:text-ink-200">
          Isi teks
          <textarea
            v-model="pasteTextContent"
            rows="10"
            placeholder="Tempel teks di sini… (max ~50.000 karakter)"
            class="mt-1 w-full px-2.5 py-1.5 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 text-ink-900 dark:text-ink-50 text-xs focus:outline-none focus:ring-2 focus:ring-brown-300 dark:focus:ring-cream-400 font-mono"
          ></textarea>
        </label>
        <p class="text-[10px] text-ink-500 dark:text-ink-300">
          Teks akan ikut dikirim ke AI sebagai "lampiran" pada pesan berikutnya.
        </p>
      </div>
      <template #actions>
        <button @click="pasteTextOpen = false" class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button
          @click="confirmPasteText"
          :disabled="!pasteTextContent.trim()"
          class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-40"
        >Lampirkan</button>
      </template>
    </AppDialog>

    <!-- Toast notifications -->
    <Teleport to="body">
      <div
        v-if="toastMessage"
        :class="[
          'fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] px-4 py-2.5 rounded-lg shadow-lg text-white text-sm max-w-md transition-all',
          toastType === 'success' ? 'bg-emerald-600' :
          toastType === 'error' ? 'bg-red-600' :
          toastType === 'warning' ? 'bg-amber-600' :
          'bg-ink-900 dark:bg-cream-200 dark:text-ash-900'
        ]"
      >
        {{ toastMessage }}
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '../stores/chat'
import { usePaperStore } from '../stores/paper'
import api from '../api/index'
import ChatMessage from './ChatMessage.vue'
import AppDialog from './AppDialog.vue'
import ActionChips from './ActionChips.vue'

interface AttachedFile extends File {
  __preExtracted?: boolean
  __text?: string
  __fileId?: number | null
  __isPaste?: boolean
  uploading?: boolean
  uploadError?: string
  canRetry?: boolean
}

interface PaperFile {
  id: number
  original_name: string
  filename: string
  ext: string
  size: number
  size_bytes?: number
  url: string
  text?: string
}

interface Conversation {
  id: number
  title: string
  message_count: number
  updated_at: string
}

interface FileEntry {
  id: number | null
  name: string
  text: string
}

interface Suggestion {
  key: string
  label: string
  text: string
}

interface Chip {
  label: string
  value: string
}

interface ClickOutsideElement extends HTMLElement {
  __clickOutsideHandler__?: (event: MouseEvent) => void
}

const vClickOutside = {
  mounted(el: ClickOutsideElement, binding: any): void {
    el.__clickOutsideHandler__ = (event: MouseEvent) => {
      if (!(el === event.target || el.contains(event.target as Node))) {
        binding.value(event)
      }
    }
    document.addEventListener('mousedown', el.__clickOutsideHandler__)
  },
  unmounted(el: ClickOutsideElement): void {
    if (el.__clickOutsideHandler__) {
      document.removeEventListener('mousedown', el.__clickOutsideHandler__)
    }
  },
}

interface Props {
  paperId?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  paperId: null
})

const emit = defineEmits<{
  (e: 'open-preview'): void
}>()

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
const inputRef = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const attachedFiles = ref<AttachedFile[]>([])
const attachWarning = ref('')
const uploadingFiles = ref(false)
const uploadFileCount = ref({ current: 0, total: 0 })
const uploadProgress = computed(() => {
  if (!uploadFileCount.value.total) return 0
  return Math.round((uploadFileCount.value.current / uploadFileCount.value.total) * 100)
})
const messagesContainer = ref<HTMLElement | null>(null)
const deleteTarget = ref<Conversation | null>(null)
const creatingChat = ref(false)
const memoryOpen = ref(false)
const showSuggestions = ref(false)

const renamingId = ref<number | null>(null)
const renameDraft = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

const attachMenuOpen = ref(false)
function toggleAttachMenu(): void { attachMenuOpen.value = !attachMenuOpen.value }
function closeAttachMenu(): void { attachMenuOpen.value = false }
function pickUpload(): void {
  attachMenuOpen.value = false
  fileInput.value?.click()
}

const filePickerOpen = ref(false)
const paperFiles = ref<PaperFile[]>([])
const paperFilesLoading = ref(false)
const pickedFileIds = ref<Set<number>>(new Set())

const pasteTextOpen = ref(false)
const pasteTextName = ref('')
const pasteTextContent = ref('')

// ─── Timeout & Error Handling ───
const streamingElapsed = ref(0)
const streamingTimer = ref<number | null>(null)
const showTimeoutWarning = ref(false)
const lastError = ref<string | null>(null)
const lastUserMessage = ref<string>('')

// Playful, rotating "still working" lines. We deliberately DON'T tell the user
// the AI is slow ("lebih lama dari biasanya") — that just makes waiting feel
// worse. Instead we cycle light, on-brand messages so the wait feels alive.
const FUN_WAIT_MESSAGES = [
  'Meramu ide terbaik untukmu',
  'Menyusun kata demi kata',
  'Merapikan argumen biar tajam',
  'Mengecek detail biar rapi',
  'Menyeduh insight akademik',
  'Menambahkan sentuhan akhir',
  'Sebentar lagi siap',
]
const streamingFunMessage = ref(FUN_WAIT_MESSAGES[0])
let _funMsgIndex = 0

// ─── Toast Notifications ───
const toastMessage = ref('')
const toastType = ref<'success' | 'error' | 'warning' | 'info'>('info')
let toastTimer: number | null = null

function showToast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info', duration = 3000): void {
  toastMessage.value = message
  toastType.value = type
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toastMessage.value = ''
  }, duration)
}

function startStreamingTimer(): void {
  stopStreamingTimer()
  streamingElapsed.value = 0
  showTimeoutWarning.value = false
  _funMsgIndex = 0
  streamingFunMessage.value = FUN_WAIT_MESSAGES[0]

  streamingTimer.value = window.setInterval(() => {
    streamingElapsed.value++

    // After a short delay, switch to the playful waiting card and keep its
    // message rotating. No "AI is slow" copy — just a lively animation.
    if (streamingElapsed.value >= 8) {
      showTimeoutWarning.value = true
      if (streamingElapsed.value % 3 === 0) {
        _funMsgIndex = (_funMsgIndex + 1) % FUN_WAIT_MESSAGES.length
        streamingFunMessage.value = FUN_WAIT_MESSAGES[_funMsgIndex]
      }
    }

    // Hard timeout is still handled by the chat store; surface a real error
    // only if we somehow reach it here.
    if (streamingElapsed.value === 90) {
      showTimeoutWarning.value = false
      showToast('Sepertinya ada gangguan koneksi. Silakan coba lagi.', 'error', 5000)
    }
  }, 1000)
}

function stopStreamingTimer(): void {
  if (streamingTimer.value) {
    clearInterval(streamingTimer.value)
    streamingTimer.value = null
  }
  streamingElapsed.value = 0
  showTimeoutWarning.value = false
}

async function retryLastMessage(): Promise<void> {
  if (!lastUserMessage.value) {
    showToast('Tidak ada pesan untuk di-retry', 'warning')
    return
  }
  
  lastError.value = null
  showToast('Mengirim ulang pesan...', 'info')
  
  try {
    await chatStore.sendMessage(lastUserMessage.value)
  } catch (e: any) {
    lastError.value = e.message || 'Gagal mengirim pesan'
    showToast('Gagal mengirim ulang pesan', 'error')
  }
}

function openPasteText(): void {
  attachMenuOpen.value = false
  pasteTextName.value = ''
  pasteTextContent.value = ''
  pasteTextOpen.value = true
}

function confirmPasteText(): void {
  const text = pasteTextContent.value.trim()
  if (!text) return
  const trimmed = text.slice(0, 50_000)
  const name = (pasteTextName.value.trim() || 'pasted-text.txt').slice(0, 120)
  attachedFiles.value = [...attachedFiles.value, {
    name,
    __preExtracted: true,
    __text: trimmed,
    __fileId: null,
    __isPaste: true,
  } as AttachedFile].slice(0, 10)
  pasteTextOpen.value = false
}

async function openExistingFiles(): Promise<void> {
  attachMenuOpen.value = false
  if (!currentPaperId.value) return
  filePickerOpen.value = true
  pickedFileIds.value = new Set()
  paperFilesLoading.value = true
  try {
    const res = await api.get(`/api/papers/${currentPaperId.value}/files`)
    paperFiles.value = res.data?.files || []
  } catch (e: any) {
    paperFiles.value = []
    attachWarning.value = 'Gagal memuat daftar file: ' + (e.message || e)
  } finally {
    paperFilesLoading.value = false
  }
}

function togglePickFile(f: PaperFile): void {
  const next = new Set(pickedFileIds.value)
  if (next.has(f.id)) next.delete(f.id)
  else next.add(f.id)
  pickedFileIds.value = next
}

async function confirmPickFiles(): Promise<void> {
  if (!pickedFileIds.value.size) return
  if (!currentPaperId.value) return
  const ids = [...pickedFileIds.value]
  filePickerOpen.value = false
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
      } as AttachedFile].slice(0, 10)
    } catch (e: any) {
      attachWarning.value = 'Gagal baca file: ' + (e.message || e)
    }
  }
}

function extIcon(ext: string): string {
  switch ((ext || '').toLowerCase()) {
    case '.pdf': return '📕'
    case '.docx':
    case '.doc': return '📘'
    case '.txt': return '📄'
    case '.md': return '📝'
    default: return '📁'
  }
}

function humanSize(b: number): string {
  if (!b) return '0 B'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(1) + ' MB'
}

const quickSuggestions: Suggestion[] = [
  { key: 'paperfull', label: 'paperfull', text: 'Generate paper lengkap (auto full paper).' },
  { key: 'abstract',  label: 'abstract',  text: 'Revisi abstract paper saya.' },
  { key: 'section',   label: 'section',   text: 'Saya mau revisi sebuah section. Tanyakan dulu section nomor berapa, lalu fokus revisi bagian itu saja.' },
  { key: 'data',      label: 'data',      text: 'Revisi data saya (Section 4 / Hasil) — perbaiki tabel, angka, dan grafik bila perlu.' },
  { key: 'review',    label: 'Review',    text: 'Lakukan review menyeluruh paper saya sesuai arahan saya — beri rekomendasi per bagian.' },
  { key: 'literatur', label: 'Literatur', text: 'Cari literatur tambahan. Baca dulu literatur yang sudah ada, lalu sarankan keyword tambahan dan jalankan SLR untuk keyword itu.' },
  { key: 'parafrase', label: 'Parafrase', text: 'Parafrase. Tanyakan dulu scope-nya: paragraf tertentu, section tertentu, atau seluruh paper.' },
  { key: 'grammar',   label: 'Grammar',   text: 'Perbaiki grammar. Tanyakan dulu scope-nya: paragraf tertentu, section tertentu, atau seluruh paper.' },
  { key: 'translate', label: 'Translate', text: 'Translate. Tanyakan dulu scope-nya (paragraf/section/seluruh) dan target_language (id/en).' },
]

const entryChips: Chip[] = [
  { label: '🆕 Buat baru',           value: 'buat_baru' },
  { label: '📄 Saya sudah punya draft', value: 'punya_draft' },
]

function onEntryPick(value: string): void {
  if (!value || isStreaming.value || !currentConversationId.value) return
  if (activeJob.value && activeJob.value.active) return

  // "Buat baru" → fetch the offline onboarding questions (static template with
  // recommended answers) and render them DIRECTLY as a card. No AI round-trip:
  // the user fills the template, then submitting flows into the dynamic phases.
  if (value === 'buat_baru') {
    void startOfflineOnboarding()
    return
  }

  // Jangan tembak AI langsung — arahkan ke flow input data dulu
  if (value === 'punya_draft') {
    inputText.value = 'Saya sudah punya draft paper. Tolong tanyakan dulu detail paper saya yang sudah ada.'
  } else {
    inputText.value = value
  }
  showSuggestions.value = false
  nextTick(() => {
    const input = document.querySelector('.chat-input-textarea') as HTMLTextAreaElement | null
    if (input) {
      input.focus()
      input.setSelectionRange(inputText.value.length, inputText.value.length)
    }
  })
}

/**
 * Start the "Buat baru" flow offline: ask the backend for the static onboarding
 * questions (no AI), then render them as a multi_question card. Falls back to a
 * plain seeded prompt if the endpoint is unavailable.
 */
async function startOfflineOnboarding(): Promise<void> {
  const paperId = currentPaperId.value
  if (!paperId) return
  showSuggestions.value = false
  try {
    const res = await api.post(`/api/papers/${paperId}/workflow/onboarding`)
    const proposal = res?.data
    if (proposal && Array.isArray(proposal.questions) && proposal.questions.length) {
      chatStore.injectMultiQuestion(proposal)
      return
    }
  } catch (e) {
    console.warn('Offline onboarding failed, falling back to seeded prompt:', e)
  }
  // Fallback: seed the input so the user can still kick off via the AI.
  inputText.value = 'Saya mau membuat paper baru dari awal. Tolong tanyakan data-data yang diperlukan dulu.'
  nextTick(() => {
    const input = document.querySelector('.chat-input-textarea') as HTMLTextAreaElement | null
    if (input) {
      input.focus()
      input.setSelectionRange(inputText.value.length, inputText.value.length)
    }
  })
}

function onChipSelect(value: string): void {
  if (!value || isStreaming.value || !currentConversationId.value) return
  if (activeJob.value && activeJob.value.active) return
  // Jangan auto-send — isi input dulu, biarkan user edit lalu kirim manual
  inputText.value = value
  showSuggestions.value = false
  nextTick(() => {
    const input = document.querySelector('.chat-input-textarea') as HTMLTextAreaElement | null
    if (input) {
      input.focus()
      input.setSelectionRange(inputText.value.length, inputText.value.length)
    }
  })
}

async function onChartAccept({ image_id, spec }: any): Promise<void> {
  if (!currentConversationId.value) return
  await chatStore.sendMessage(
    `Pakai chart ini (image_id=${image_id}) di Section 4 dengan caption "${spec?.title || 'Hasil evaluasi'}".`
  )
}

async function onChartRegenerate(): Promise<void> {
  if (!currentConversationId.value) return
  await chatStore.sendMessage(
    `Regenerate chart yang baru aja kamu bikin dengan parameter berbeda — jelaskan dulu apa yang mau diubah.`
  )
}

async function onFileReviewPick({ file_id, kinds }: any): Promise<void> {
  if (!currentConversationId.value) return
  const k = (kinds || []).join(', ') || 'data'
  await chatStore.sendMessage(`Untuk file id=${file_id}, ambil bagian: ${k}. Lanjutkan analisis.`)
}

async function onMultiQuestionSubmit(answers: any): Promise<void> {
  if (!currentConversationId.value) return
  if (chatStore.submitMultiQuestionAnswers) {
    return chatStore.submitMultiQuestionAnswers(answers)
  }
  const lines = (answers || []).map((a: any) => `${a.key}: ${a.value}`).join('\n')
  await chatStore.sendMessage(`Jawaban saya:\n${lines}`)
}

async function onRevisiAccept(): Promise<void> {
  if (!currentConversationId.value) return
  await chatStore.sendMessage(`Terima rewrite ini.`)
}

async function onRevisiReject(): Promise<void> {
  if (!currentConversationId.value) return
  await chatStore.sendMessage(`Tolak rewrite ini, coba versi lain.`)
}

async function onReviewCancel(): Promise<void> {
  if (!currentConversationId.value) return
  await chatStore.sendMessage(`Batal review.`)
}

onMounted(async () => {
  if (props.paperId) {
    await chatStore.openPaper(props.paperId)
  }
})

onUnmounted(() => {
  chatStore.stopActiveJobPolling()
})

onBeforeUnmount(() => {
  stopStreamingTimer()
  if (toastTimer) clearTimeout(toastTimer)
})

watch(
  () => props.paperId,
  async (id) => {
    if (!id) {
      currentPaperId.value = null
      currentConversationId.value = null
      messages.value = []
      chatStore.stopActiveJobPolling()
      return
    }
    if (id !== currentPaperId.value) {
      await chatStore.openPaper(id)
    }
  }
)

const userIsNearBottom = ref(true)
const lastScrollTop = ref(0)

const statusMessage = computed(() => {
  if (!isStreaming.value) return 'Online'

  const msg = messages.value[messages.value.length - 1]
  if (msg?.role !== 'assistant') return 'Processing...'

  // Check for active tool calls
  if (msg.tool_calls && msg.tool_calls.length > 0) {
    const lastTool = msg.tool_calls[msg.tool_calls.length - 1]
    if (lastTool.status === 'running') {
      // Friendly, user-facing labels. Never surface raw tool names like
      // "SaveWorkflowAnswers" — they look like internal errors to users.
      const toolNames: Record<string, string> = {
        'SearchLiterature': 'Mencari literatur',
        'RunSLR': 'Mengumpulkan referensi',
        'SearchPapers': 'Mencari paper',
        'GenerateFullPaper': 'Menyusun paper',
        'SaveMemory': 'Menyimpan catatan',
        'AskQuestions': 'Menyiapkan pertanyaan',
        'StartWorkflow': 'Menyiapkan data awal',
        'SaveWorkflowAnswers': 'Menyimpan jawaban',
        'ProposeSection': 'Menulis bagian',
        'GenerateImage': 'Membuat gambar',
        'GenerateChart': 'Membuat grafik',
        'ReviewLargeFile': 'Meninjau berkas',
        'ClassifyFile': 'Memproses berkas',
      }
      return toolNames[lastTool.name] || 'Memproses'
    }
  }

  // Check for thinking vs typing
  if (msg.thinking && !msg.content) return 'Sedang berpikir'
  if (msg.content) return 'Sedang mengetik'

  return 'Memproses'
})

const lastAssistantMessage = computed(() => {
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const message = messages.value[index]
    if (message?.role === 'assistant') return message
  }
  return null
})

const showInlineStreamingIndicator = computed(() => {
  if (!isStreaming.value || streamingElapsed.value <= 5) return false
  const lastAssistant = lastAssistantMessage.value
  if (!lastAssistant) return true
  return !!showTimeoutWarning.value || !!(lastAssistant.tool_calls || []).length
})

const streamingIndicatorText = computed(() =>
  showTimeoutWarning.value ? `${streamingFunMessage.value}...` : statusMessage.value
)

function conversationTitle(title?: string | null): string {
  const normalized = String(title || '').trim()
  return !normalized || normalized === 'New Chat' ? 'Chat tanpa judul' : normalized
}

function checkScrollPosition(): void {
  if (!messagesContainer.value) return
  const container = messagesContainer.value
  const scrollTop = container.scrollTop
  const scrollHeight = container.scrollHeight
  const clientHeight = container.clientHeight
  const distanceFromBottom = scrollHeight - scrollTop - clientHeight
  userIsNearBottom.value = distanceFromBottom < 100
  lastScrollTop.value = scrollTop
}

watch(messages, () => {
  nextTick(() => {
    if (userIsNearBottom.value) {
      scrollToBottom()
    }
  })
}, { deep: true })

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

// Watch streaming state to manage timer
watch(isStreaming, (streaming) => {
  if (streaming) {
    startStreamingTimer()
  } else {
    stopStreamingTimer()
  }
})

// Watch for errors from chat store
watch(() => chatStore.error, (error) => {
  if (error) {
    lastError.value = error
    showToast(error, 'error', 5000)
  }
})

watch(currentConversationId, () => {
  showSuggestions.value = false
})

function scrollToBottom(): void {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    userIsNearBottom.value = true
  }
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

function formatElapsed(sec: number): string {
  if (!sec || sec < 60) return `${sec || 0}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

async function handleSelectConversation(convId: number): Promise<void> {
  if (convId === currentConversationId.value) return
  await chatStore.openConversation(convId)
  showSuggestions.value = false
  scrollToBottom()
}

async function createNewChat(): Promise<void> {
  if (!currentPaperId.value || creatingChat.value) return
  creatingChat.value = true
  try {
    const conv = await chatStore.newChatForCurrentPaper()
    if (conv) {
      currentConversationId.value = conv.id
      messages.value = []
      showSuggestions.value = false
      showToast('Chat baru berhasil dibuat', 'success')
    }
  } catch (e: any) {
    showToast('Gagal membuat chat baru', 'error')
  } finally {
    creatingChat.value = false
    uploadFileCount.value = { current: 0, total: 0 }
  }
}

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

async function commitRename(conv: Conversation): Promise<void> {
  const title = renameDraft.value.trim()
  const id = renamingId.value
  renamingId.value = null
  renameDraft.value = ''
  if (!id || !title || title === conv.title) return
  try {
    await chatStore.renameConversation(id, title)
    showToast('Chat berhasil di-rename', 'success')
  } catch (e: any) {
    showToast('Gagal rename chat', 'error')
  }
}

function confirmDeleteChat(conv: Conversation): void {
  deleteTarget.value = conv
}

async function doDeleteChat(): Promise<void> {
  const id = deleteTarget.value?.id
  const title = deleteTarget.value?.title || 'Chat'
  deleteTarget.value = null
  if (!id) return
  try {
    await chatStore.deleteConversation(id)
    showToast(`"${title}" berhasil dihapus`, 'success')
  } catch (e: any) {
    showToast('Gagal menghapus chat', 'error')
  }
}

async function handleSend(): Promise<void> {
  const text = inputText.value.trim()
  if ((!text && !attachedFiles.value.length) || isStreaming.value || !currentConversationId.value) return
  if (activeJob.value && activeJob.value.active) return
  let composed = text

  const realFiles = attachedFiles.value.filter(f => !f.__preExtracted)
  const preExtracted = attachedFiles.value.filter(f => f.__preExtracted)

  if (realFiles.length || preExtracted.length) {
    uploadingFiles.value = true
    uploadFileCount.value = { current: 0, total: realFiles.length }

    // Mark all real files as uploading
    attachedFiles.value = attachedFiles.value.map(f =>
      realFiles.includes(f as File) ? { ...f, uploading: true } as AttachedFile : f
    )

    try {
      const fileEntries: FileEntry[] = []
      let warnings: string[] = []
      if (realFiles.length) {
        if (currentPaperId.value) {
          uploadFileCount.value.current = 0
          const fd = new FormData()
          realFiles.forEach(f => fd.append('files', f))
          const res = await api.post(
            `/api/papers/${currentPaperId.value}/files`,
            fd,
            {
              headers: { 'Content-Type': 'multipart/form-data' },
              onUploadProgress: (evt: any) => {
                if (evt.total) {
                  const pct = Math.round((evt.loaded / evt.total) * 100)
                  uploadFileCount.value.current = Math.floor((pct / 100) * realFiles.length)
                }
              }
            },
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
          texts.forEach((t: string, i: number) => {
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

      // Clear uploading state from successfully uploaded files
      attachedFiles.value = attachedFiles.value.map(f => {
        if (f.uploading) {
          return { ...f, uploading: false } as AttachedFile
        }
        return f
      })

      attachWarning.value = warnings.join('; ')
      if (attachWarning.value) {
        setTimeout(() => { attachWarning.value = '' }, 5000)
      }
      
      // Show success toast for file upload
      if (fileEntries.length > 0) {
        showToast(`${fileEntries.length} file berhasil dilampirkan`, 'success')
      }
      
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
        ? `\n[FILE_IDS=${idsHint}] (use AskQuestions with key=file_kind:<id> per file, then ClassifyFile per answer; options must include paper_slr/paper_read/data/image/template)`
        : ''
      const defaultText = fileEntries.length
        ? `Saya melampirkan ${fileEntries.length} file. Tanya dulu "ini file apa?" untuk masing-masing file via AskQuestions (satu pertanyaan per file_id, key=file_kind:<id>) dengan pilihan: paper_slr, paper_read, data, image, template. Lalu panggil ClassifyFile sesuai jawaban. Untuk file paper_slr >3000 kata, pakai ReviewLargeFile.`
        : ''
      composed = (text || defaultText)
        + idsLine
        + fileBlock
      attachedFiles.value = []
    } catch (e: any) {
      const status = e?.response?.status
      const data = e?.response?.data || {}
      let msg: string
      if (status === 413) {
        msg = data.hint || 'File too large'
      } else if (status === 401) {
        msg = 'Session expired'
      } else if (data.error) {
        msg = `${data.error}${data.hint ? ' — ' + data.hint : ''}`
      } else {
        msg = e.message || String(e) || 'Upload failed'
      }

      // Mark files as failed with retry option instead of clearing them
      attachedFiles.value = attachedFiles.value.map(f => ({
        ...f,
        uploading: false,
        uploadError: msg,
        canRetry: status !== 401 // Don't allow retry on auth errors
      } as AttachedFile))

      attachWarning.value = 'Upload gagal: ' + msg + (status !== 401 ? ' — Klik ↻ untuk retry.' : ' — Silakan login ulang.')
      showToast('Upload file gagal: ' + msg, 'error')
      uploadingFiles.value = false
      return
    }
    uploadingFiles.value = false
  }

  // Store last message for retry
  lastUserMessage.value = composed
  lastError.value = null
  
  inputText.value = ''
  
  try {
    await chatStore.sendMessage(composed)
  } catch (e: any) {
    lastError.value = e.message || 'Gagal mengirim pesan'
    showToast('Gagal mengirim pesan', 'error')
  }
}

function onFileChange(e: Event): void {
  const target = e.target as HTMLInputElement
  const files = Array.from(target.files || [])
  addAttachedFiles(files)
  if (fileInput.value) fileInput.value.value = ''
}

function addAttachedFiles(files: File[]): void {
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
  attachedFiles.value = merged as AttachedFile[]
}

function removeAttachedFile(i: number): void {
  attachedFiles.value = attachedFiles.value.filter((_, idx) => idx !== i)
}

async function retryUpload(i: number): Promise<void> {
  const file = attachedFiles.value[i]
  if (!file || !file.canRetry) return

  // Clear error state and mark as uploading
  attachedFiles.value[i] = {
    ...file,
    uploading: true,
    uploadError: undefined,
    canRetry: false
  } as AttachedFile

  // Retry the upload
  uploadingFiles.value = true
  uploadFileCount.value = { current: 0, total: 1 }

  try {
    const fd = new FormData()
    fd.append('files', file)

    if (currentPaperId.value) {
      const res = await api.post(
        `/api/papers/${currentPaperId.value}/files`,
        fd,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (evt: any) => {
            if (evt.total) {
              const pct = Math.round((evt.loaded / evt.total) * 100)
              uploadFileCount.value.current = pct / 100
            }
          }
        }
      )

      const saved = res?.data?.files?.[0]
      if (saved) {
        // Replace with successfully uploaded file
        attachedFiles.value[i] = {
          name: saved.original_name || saved.filename || file.name,
          __preExtracted: true,
          __text: saved.text || '',
          __fileId: saved.id,
          uploading: false,
        } as AttachedFile
        attachWarning.value = ''
        showToast('File berhasil di-upload', 'success')
      }
    }
  } catch (e: any) {
    // Mark as failed again
    const status = e?.response?.status
    const data = e?.response?.data || {}
    let msg = status === 413 ? 'File too large' :
              status === 401 ? 'Session expired' :
              data.error || e.message || 'Upload failed'

    attachedFiles.value[i] = {
      ...file,
      uploadError: msg,
      canRetry: status !== 401
    }
    attachWarning.value = 'Retry gagal: ' + msg
    showToast('Retry upload gagal: ' + msg, 'error')
  } finally {
    uploadingFiles.value = false
  }
}

function handleStop(): void {
  chatStore.stopStreaming()
}

function handleKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function sendSuggestion(s: Suggestion | string): void {
  if (isStreaming.value || !currentConversationId.value) return
  if (activeJob.value && activeJob.value.active) return
  const text = (typeof s === 'object' && s.text) || (typeof s === 'string' ? s : '')
  if (!text) return
  // Isi input dulu — biarkan user edit sebelum kirim manual (Enter / klik Send).
  // Tidak auto-send agar user bisa menyesuaikan prompt sesuai kebutuhan.
  showSuggestions.value = false
  inputText.value = text
  // Fokus kembali ke input setelah chip diklik
  nextTick(() => {
    const input = document.querySelector('.chat-input-textarea') as HTMLTextAreaElement | null
    if (input) {
      input.focus()
      // Letakkan kursor di akhir teks
      input.setSelectionRange(text.length, text.length)
    }
  })
}

async function pickOption(text: string): Promise<void> {
  if (isStreaming.value || !currentConversationId.value) return
  inputText.value = text
  showSuggestions.value = false
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.focus()
      inputRef.value.setSelectionRange(text.length, text.length)
    }
  })
}

function openPreview(): void {
  emit('open-preview')
}
</script>

<style scoped>
/* Fade for the rotating "still working" message so each line swaps smoothly. */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}
.fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.ai-status-bubble {
  background: var(--surface-ai, #fafafa);
  color: var(--text-strong, #111);
  border: 1px solid var(--border-soft, #e5e7eb);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
</style>
