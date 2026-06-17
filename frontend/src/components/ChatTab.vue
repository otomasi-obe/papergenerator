<template>
  <div class="flex flex-col h-full overflow-hidden bg-cream-100/40 dark:bg-ash-850">
    <!-- ─── PICKER VIEW: list of chats only (no active chat yet) ─── -->
    <template v-if="!currentConversationId">
      <header class="px-5 py-3 bg-cream-50 dark:bg-ash-800 border-b border-cream-300 dark:border-ash-700 flex items-center gap-2">
        <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 flex-1">AI Chat</h3>
        <button
          @click="createNewChat"
          :disabled="creatingChat || !currentPaperId"
          class="flex items-center gap-1.5 px-3 py-1.5 min-h-[44px] min-w-[44px] bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-xs font-medium disabled:opacity-50 transition-colors active:scale-95 transition-transform"
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
           <span class="inline-block w-5 h-5 border-2 border-navy-400 dark:border-cream-400 border-t-transparent rounded-full animate-spin mb-3"></span>
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
                 ? 'bg-navy-100 dark:bg-ash-700 border-l-4 border-navy-600 dark:border-cream-400 shadow-sm'
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
                 class="w-full text-xs px-1.5 py-0.5 border border-cream-300 dark:border-ash-600 bg-[var(--bg-surface)] text-[var(--text-strong)] rounded outline-none focus:ring-1 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
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
               class="opacity-0 group-hover:opacity-100 text-[var(--text-muted)] hover:text-[var(--text-strong)] text-xs min-h-[44px] min-w-[44px] flex items-center justify-center active:scale-95 transition-transform"
               title="Rename"
               aria-label="Rename conversation"
             ><span aria-hidden="true">✎</span></button>
             <button
               v-if="renamingId !== conv.id"
               @click.stop="confirmDeleteChat(conv)"
               class="opacity-0 group-hover:opacity-100 text-[var(--text-muted)] hover:text-red-500 dark:text-red-400 text-xs min-h-[44px] min-w-[44px] flex items-center justify-center active:scale-95 transition-transform"
              title="Delete"
              aria-label="Delete conversation"
            ><span aria-hidden="true">🗑</span></button>
          </div>
        </div>
      </div>
    </template>

    <!-- ─── ACTIVE CHAT VIEW ─── -->
    <template v-else>
      <!-- Header bar with clear chat -->
      <header class="px-4 py-2 bg-cream-50 dark:bg-ash-800 border-b border-cream-300 dark:border-ash-700 flex items-center gap-2">
        <h3 class="text-sm font-semibold text-ink-900 dark:text-ink-50 flex-1 truncate">
          {{ currentChat?.title || 'AI Chat' }}
        </h3>
        <button
          @click="chatStore.clearCurrentChat()"
          :disabled="isStreaming"
          class="flex items-center gap-1.5 px-2.5 py-1 min-h-[36px] text-[11px] font-medium text-[var(--text-muted)] hover:text-red-500 dark:text-red-400 dark:hover:text-red-400 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-40 transition-colors active:scale-95"
          title="Clear chat — hapus semua pesan"
        >
          <span aria-hidden="true">🧹</span>
          <span>Clear</span>
        </button>
        <button
          @click="openExportDraftModal"
          :disabled="isStreaming || !messages.length"
          class="flex items-center gap-1.5 px-2.5 py-1 min-h-[36px] text-[11px] font-medium text-[var(--text-muted)] hover:text-[#238f7f] dark:hover:text-[#4eb2a3] rounded-md hover:bg-green-50 dark:hover:bg-green-900/20 disabled:opacity-40 transition-colors active:scale-95"
          title="Export Draft — simpan diskusi ini sebagai draft untuk dipakai di paperfull atau chat lain"
        >
          <span aria-hidden="true">📤</span>
          <span>Export Draft</span>
        </button>
      </header>

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
            {{ greeting }}
          </h2>
          <SuggestedPrompts @select="onSuggestedPrompt" />
        </div>

        <ChatMessage
          v-for="msg in messages"
          :key="msg.id"
          :message="msg"
          :is-streaming="isStreaming && msg === messages[messages.length - 1] && msg.role === 'assistant'"
          :stream-phase="(isStreaming && msg === messages[messages.length - 1] && msg.role === 'assistant') ? streamPhase : 'idle'"
          @pick-option="pickOption"
          @chip-select="onChipSelect"
          @chart-accept="onChartAccept"
          @chart-regenerate="onChartRegenerate"
          @file-review-pick="onFileReviewPick"
          @multi-question-submit="onMultiQuestionSubmit"
          @ask-user-answer="onAskUserAnswer"
          @revisi-accepted="onRevisiAccept"
          @revisi-rejected="onRevisiReject"
          @review-cancel="onReviewCancel"
        />

        <div
          v-if="showInlineStreamingIndicator"
          class="flex gap-3 justify-start"
        >
          <div class="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-br from-navy-400 to-navy-600 flex items-center justify-center mt-1 shadow-sm">
            <svg class="w-4 h-4 text-cream-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/>
            </svg>
          </div>
          <div class="max-w-[80%] rounded-2xl px-4 py-3 ai-status-bubble">
            <div class="flex items-center gap-2 text-xs text-ink-800 dark:text-ink-100">
              <span class="inline-flex items-center gap-1 shrink-0" aria-hidden="true">
                 <span class="w-1.5 h-1.5 rounded-full bg-navy-500 dark:bg-navy-300 animate-bounce" style="animation-delay: 0ms"></span>
                 <span class="w-1.5 h-1.5 rounded-full bg-navy-500 dark:bg-navy-300 animate-bounce" style="animation-delay: 150ms"></span>
                 <span class="w-1.5 h-1.5 rounded-full bg-navy-500 dark:bg-navy-300 animate-bounce" style="animation-delay: 300ms"></span>
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
             <button @click="openPreview" class="underline font-semibold hover:text-amber-700 dark:hover:text-amber-100 active:scale-95 transition-transform">Buka Preview</button>
          </span>
        </div>
        <div class="flex items-center gap-1.5 mt-1.5">
          <button
            @click="paperStore.acceptAllProposals()"
             class="flex-1 px-2.5 py-1 min-h-[44px] text-[11px] font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white active:scale-95 transition-transform"
           >✓ Terima semua</button>
           <button
             @click="paperStore.rejectAllProposals()"
             class="flex-1 px-2.5 py-1 min-h-[44px] text-[11px] font-semibold rounded-md bg-rose-100 hover:bg-rose-200 dark:bg-rose-900/40 dark:hover:bg-rose-900/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800 active:scale-95 transition-transform"
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
             class="text-[11px] px-2.5 py-1 min-h-[44px] rounded-full bg-cream-100 dark:bg-ash-700 hover:bg-navy-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 text-ink-800 dark:text-ink-100 transition-colors border border-cream-300 dark:border-ash-600 disabled:opacity-50 disabled:cursor-not-allowed active:scale-95 transition-transform"
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
           class="shrink-0 px-2.5 py-1 min-h-[36px] text-[11px] font-semibold rounded-md bg-red-600 hover:bg-red-700 text-white transition-colors active:scale-95 transition-transform"
         >↻ Retry</button>
         <button
           @click="lastError = null"
           class="shrink-0 text-red-500 hover:text-red-700 dark:text-red-300 dark:hover:text-red-100 min-h-[36px] min-w-[36px] flex items-center justify-center active:scale-95 transition-transform"
          title="Tutup"
        >✕</button>
      </div>

      <!-- Input with drag-and-drop zone -->
      <div
        class="px-4 pb-3 bg-cream-50 dark:bg-ash-800 relative"
        @dragenter="onDragEnter"
        @dragleave="onDragLeave"
        @dragover="onDragOver"
        @drop="onDrop"
      >
        <!-- Drag overlay -->
        <div
          v-if="isDragOver"
          class="absolute inset-0 z-20 flex items-center justify-center rounded-lg border-2 border-dashed border-navy-500 dark:border-navy-400 bg-navy-50/90 dark:bg-ash-800/90 pointer-events-none"
        >
          <div class="text-center">
            <div class="text-2xl mb-1">📂</div>
            <p class="text-xs font-medium text-navy-700 dark:text-navy-300">Drop file di sini</p>
            <p class="text-[10px] text-navy-500 dark:text-navy-400">PDF, DOCX, atau DOC</p>
          </div>
        </div>
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
               class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200 ml-1 min-h-[44px] min-w-[44px] active:scale-95 transition-transform"
               title="Retry upload"
               aria-label="Retry upload"
             ><span aria-hidden="true">↻</span></button>
             <button
               v-if="!f.uploading"
               @click="removeAttachedFile(i)"
               class="text-ink-500 dark:text-ink-300 hover:text-rose-500 ml-1 min-h-[44px] min-w-[44px] active:scale-95 transition-transform"
              title="Remove"
              aria-label="Remove attached file"
            ><span aria-hidden="true">✕</span></button>
          </div>
        </div>
        <p v-if="attachWarning" class="text-[10px] text-amber-700 dark:text-amber-300 mb-1">{{ attachWarning }}</p>

        <div class="rounded-xl border-2 border-cream-400 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-sm focus-within:border-navy-500 dark:focus-within:border-navy-400 focus-within:ring-4 focus-within:ring-[#238f7f]/30 dark:focus-within:ring-[#4eb2a3]/30 transition-all">
          <div class="flex items-center gap-2 p-2">
            <div class="relative">
              <button
                @click.stop="attachMenuOpen = !attachMenuOpen"
                v-click-outside="() => { attachMenuOpen = false }"
                :disabled="isStreaming || uploadingFiles"
                class="shrink-0 min-h-[44px] min-w-[44px] px-2 text-base text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 rounded-lg transition-colors active:scale-95 transition-transform disabled:opacity-40"
                title="Lampirkan file"
                aria-label="Attach file"
              >＋</button>
              <div
                v-if="attachMenuOpen"
                class="absolute bottom-full left-0 mb-1 w-48 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-lg overflow-hidden z-30"
              >
                <button
                  type="button"
                  @click="pickUpload()"
                  class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2"
                ><span>📤</span><span>Upload file</span></button>
                <button
                  type="button"
                  @click="openExistingFiles()"
                  :disabled="!currentPaperId"
                  class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2 disabled:opacity-40 border-t border-cream-300 dark:border-ash-600"
                ><span>📁</span><span>Dari file paper ini</span></button>
              </div>
            </div>
            <input
              type="file"
              ref="fileInput"
              accept=".pdf,.docx,.doc"
              multiple
              class="hidden"
              @change="onFileChange"
            />
            <textarea
              ref="inputRef"
              v-model="inputText"
              @keydown="handleKeydown"
              :disabled="(activeJob && activeJob.active) || uploadingFiles"
              :placeholder="(activeJob && activeJob.active) ? 'Terkunci saat generate…' : uploadingFiles ? 'Mengupload file…' : (isStreaming ? 'AI mengetik…' : 'Ketik pesan…')"
              rows="1"
              class="chat-input-textarea flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink-900 dark:text-ink-50 focus:outline-none disabled:opacity-50 max-h-24 overflow-y-auto placeholder-ink-500 dark:placeholder-ink-300"
            ></textarea>
            <button
              v-if="isStreaming || uploadingFiles"
              @click="handleStop"
               class="shrink-0 min-h-[44px] min-w-[44px] bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors active:scale-95 transition-transform flex items-center justify-center"
              :title="uploadingFiles ? 'Stop upload' : 'Stop generating'"
              :aria-label="uploadingFiles ? 'Stop file upload' : 'Stop generating'"
            >
              <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1.5"/>
              </svg>
            </button>
            <button
              v-else
              @click="handleSend"
              :disabled="(!inputText.trim() && !attachedFiles.length) || (activeJob && activeJob.active) || (uploadingFiles && !isStreaming)"
               class="shrink-0 min-h-[44px] min-w-[44px] bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors active:scale-95 transition-transform flex items-center justify-center"
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
         <button @click="deleteTarget = null" class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700 active:scale-95 transition-transform">Cancel</button>
         <button @click="doDeleteChat" class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg bg-red-600 hover:bg-red-700 text-white active:scale-95 transition-transform">Delete</button>
      </template>
    </AppDialog>

    <!-- Export Draft modal -->
    <AppDialog v-if="exportDraftOpen" :open="exportDraftOpen" title="Export Draft" @close="exportDraftOpen = false">
      <div class="space-y-3">
        <p class="text-xs text-ink-600 dark:text-ink-300">
          Simpan diskusi chat ini sebagai <strong>draft bernama</strong>. Nanti bisa di-select di tab Paperfull atau di-inject ke chat lain pakai <code class="px-1 py-0.5 bg-cream-100 dark:bg-ash-700 rounded text-[10px]">@draft &lt;nama&gt;</code>.
        </p>
        <div>
          <label class="block text-xs text-ink-700 dark:text-ink-200 mb-1">Nama Draft <span class="text-red-500 dark:text-red-400">*</span></label>
          <input
            ref="exportDraftInput"
            v-model="exportDraftName"
            type="text"
            placeholder="mis. Diskusi Metodologi, Review Literatur X, dll"
            class="w-full px-2.5 py-1.5 rounded-md border border-cream-300 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 text-ink-900 dark:text-ink-50 text-xs focus:outline-none focus:ring-2 focus:ring-[#238f7f]/30 dark:focus:ring-[#4eb2a3]/30"
            @keyup.enter="doExportDraft"
          />
          <p v-if="exportDraftError" class="mt-1 text-[11px] text-red-600 dark:text-red-400">{{ exportDraftError }}</p>
        </div>
        <div class="flex items-center gap-2 text-xs text-ink-500 dark:text-ink-300">
          <input type="checkbox" v-model="exportDraftWholeConv" id="wholeConv" class="rounded" />
          <label for="wholeConv">Export seluruh conversation (bukan hanya pesan yang sedang dibaca)</label>
        </div>
        <p class="text-[11px] text-ink-500 dark:text-ink-300">
          Ukuran estimasi: {{ exportDraftEstChars }} karakter.
        </p>
      </div>
      <template #actions>
        <button @click="exportDraftOpen = false" class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700 active:scale-95 transition-transform">Cancel</button>
        <button
          @click="doExportDraft"
          :disabled="exportDraftSaving || !exportDraftName.trim()"
          class="px-3 py-1.5 min-h-[44px] text-sm rounded-lg bg-[#238f7f] hover:bg-[#1d7a6d] text-white disabled:opacity-50 active:scale-95 transition-transform"
        >
          {{ exportDraftSaving ? 'Saving…' : 'Save Draft' }}
        </button>
      </template>
    </AppDialog>

    <!-- File picker (existing paper files) -->
    <AppDialog v-if="filePickerOpen" :open="filePickerOpen" title="Pilih file dari paper ini" @close="filePickerOpen = false">
      <div class="space-y-2 max-h-60 overflow-y-auto">
        <div v-if="paperFilesLoading" class="text-xs text-ink-500 dark:text-ink-300 italic p-2">
          Loading files…
        </div>
        <div v-else-if="!paperFiles.length" class="text-xs text-ink-500 dark:text-ink-300 italic p-2">
          Belum ada file yang diupload ke paper ini.
        </div>
        <label
          v-for="f in paperFiles"
          :key="f.id"
          class="flex items-center gap-2 text-xs cursor-pointer hover:bg-cream-100 dark:hover:bg-ash-700 p-2 rounded"
        >
          <input type="checkbox" :checked="pickedFileIds.has(f.id)" @change="togglePickFile(f)" class="rounded" />
          <span class="flex-1 truncate">{{ f.original_name || f.filename }}</span>
          <span class="text-ink-500 dark:text-ink-300 text-[10px] shrink-0">{{ f.size ? humanSize(f.size) : '' }}</span>
        </label>
      </div>
      <template #actions>
        <button @click="filePickerOpen = false" class="px-3 py-1.5 text-sm rounded-lg border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
        <button
          @click="confirmPickFiles"
          :disabled="!pickedFileIds.size"
          class="px-3 py-1.5 text-sm rounded-lg bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 disabled:opacity-40"
        >Tambah ({{ pickedFileIds.size }})</button>
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
import { useAuthStore } from '../stores/auth'
import { useUserStateStore } from '../stores/userState'
import api from '../api/index'
import ChatMessage from './ChatMessage.vue'
import AppDialog from './AppDialog.vue'
import SuggestedPrompts from './SuggestedPrompts.vue'

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
const auth = useAuthStore()
const userState = useUserStateStore()
const {
  currentPaperId,
  conversations,
  currentConversationId,
  messages,
  isStreaming,
  currentChat,
  activeJob,
  streamPhase,
} = storeToRefs(chatStore)

// Greeting with nickname
// Greeting with nickname
const greeting = computed(() => {
  const nickname = auth.user?.nickname || auth.user?.name?.split(' ')[0] || auth.user?.email?.split('@')[0] || 'Anda'
  return `Halo ${nickname}! Saya PaperFull, siap menjadi asisten Anda. Sudah sampai mana progres Anda?`
})

// Persisted state via userState store (per-paper)
const inputText = computed({
  get: () => userState.get('chat.input_text', currentPaperId.value, ''),
  set: (val) => userState.set('chat.input_text', currentPaperId.value, val),
})
const inputRef = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const attachedFiles = ref<AttachedFile[]>([])
const attachWarning = ref('')
let _attachWarningTimer: number | null = null
const uploadingFiles = ref(false)
const uploadFileCount = ref({ current: 0, total: 0 })
const uploadProgress = computed(() => {
  if (!uploadFileCount.value.total) return 0
  return Math.round((uploadFileCount.value.current / uploadFileCount.value.total) * 100)
})
// AbortController for upload+extract phase — lets stop button cancel file extraction
let _uploadAbortController: AbortController | null = null
const messagesContainer = ref<HTMLElement | null>(null)
const deleteTarget = ref<Conversation | null>(null)
const creatingChat = ref(false)
const showSuggestions = ref(false)

const renamingId = ref<number | null>(null)
const renameDraft = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

// ─── Drag & Drop ───
const isDragOver = ref(false)
let _dragCounter = 0

function onDragEnter(e: DragEvent): void {
  e.preventDefault()
  _dragCounter++
  if (e.dataTransfer?.types?.includes('Files')) {
    isDragOver.value = true
  }
}

function onDragLeave(_e: DragEvent): void {
  _dragCounter--
  if (_dragCounter <= 0) {
    _dragCounter = 0
    isDragOver.value = false
  }
}

function onDragOver(e: DragEvent): void {
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
}

function onDrop(e: DragEvent): void {
  e.preventDefault()
  _dragCounter = 0
  isDragOver.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) addAttachedFiles(files)
}

// ─── Click Outside directive ───
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
    document.addEventListener('click', el.__clickOutsideHandler__)
  },
  unmounted(el: ClickOutsideElement): void {
    if (el.__clickOutsideHandler__) {
      document.removeEventListener('click', el.__clickOutsideHandler__)
    }
  },
}

const attachMenuOpen = ref(false)
function pickUpload(): void {
  attachMenuOpen.value = false
  fileInput.value?.click()
}

const filePickerOpen = ref(false)
const paperFiles = ref<PaperFile[]>([])
const paperFilesLoading = ref(false)
const pickedFileIds = ref<Set<number>>(new Set())

async function openExistingFiles(): Promise<void> {
  attachMenuOpen.value = false
  if (!currentPaperId.value) return
  filePickerOpen.value = true
  pickedFileIds.value = new Set()
  paperFilesLoading.value = true
  try {
    const res = await api.get(`/api/papers/${currentPaperId.value}/files`)
    paperFiles.value = (res.data?.files || []).map((f: any) => ({
      ...f,
      original_name: f.original_name || f.filename || f.name || 'Untitled',
    }))
  } catch {
    paperFiles.value = []
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
  filePickerOpen.value = false
  const picked = paperFiles.value.filter(f => pickedFileIds.value.has(f.id))
  for (const f of picked) {
    try {
      const res = await api.get(`/api/papers/${currentPaperId.value}/files/${f.id}/preview`)
      attachedFiles.value.push({
        name: f.original_name || f.filename || 'Unknown file',
        __preExtracted: true,
        __text: res.data?.text || '',
        __fileId: f.id,
        uploading: false,
      } as AttachedFile)
    } catch {
      attachedFiles.value.push({
        name: f.original_name || f.filename || 'Unknown file',
        __preExtracted: true,
        __text: '',
        __fileId: f.id,
        uploading: false,
      } as AttachedFile)
    }
  }
  attachWarning.value = ''
  pickedFileIds.value = new Set()
  paperFiles.value = []
  if (picked.length > 0) {
    scrollToBottom()
  }
}

function humanSize(b: number): string {
  if (!b) return '0 B'
  if (b < 1024) return b + ' B'
  if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1024 / 1024).toFixed(1) + ' MB'
}

// ─── Export Draft state ───
const exportDraftOpen = ref(false)
const exportDraftName = ref('')
const exportDraftWholeConv = ref(true)
const exportDraftSaving = ref(false)
const exportDraftError = ref('')
const exportDraftInput = ref<HTMLInputElement | null>(null)

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
  'Masih berpikir... (meramu ide)',
  'Masih berpikir... (menyusun kata)',
  'Masih berpikir... (merapikan argumen)',
  'Masih berpikir... (mengecek detail)',
  'Masih berpikir... (menyeduh insight)',
  'Masih berpikir... (sentuhan akhir)',
  'Hampir selesai...',
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

    // The store owns the real connection timeout (9 min) and surfaces genuine
    // disconnect/timeout errors via lastError. Don't raise a misleading
    // "connection problem" toast at 90s — reasoning-heavy models legitimately
    // run that long, and a false alarm makes users abandon a healthy stream.
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

/** Handle suggested prompt click from empty-state */
function onSuggestedPrompt(text: string): void {
  if (!text || isStreaming.value || !currentConversationId.value) return
  if (activeJob.value && activeJob.value.active) return
  inputText.value = text
  showSuggestions.value = false
  nextTick(() => {
    const input = document.querySelector('.chat-input-textarea') as HTMLTextAreaElement | null
    if (input) {
      input.focus()
      input.setSelectionRange(text.length, text.length)
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

async function onAskUserAnswer(answer: string): Promise<void> {
  if (!currentConversationId.value || !answer.trim()) return
  await chatStore.sendMessage(answer)
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
    
    // Check for interrupted streaming sessions and restore them
    try {
      const { useUserStateStore } = await import('../stores/userState')
      const userState = useUserStateStore()
      const savedStream = userState.get('chat.streaming', null, null)
      
      if (savedStream && savedStream.conv_id) {
        const { data } = await api.get(`/api/chat/conversations/${savedStream.conv_id}/stream-status`)
        
        if (data.status === 'streaming') {
          // Backend still streaming - reconnect
          const stream = chatStore._ensureStream(savedStream.conv_id)
          stream.isStreaming = true
          stream.connectionState = 'reconnecting'
          stream.streamingMessage = {
            id: null,
            role: 'assistant',
            content: data.content || savedStream.content || '',
            thinking: data.thinking || savedStream.thinking || '',
            tool_calls: [],
            created_at: data.started_at || savedStream.started_at,
          }
          stream.messages.push(stream.streamingMessage)
          chatStore._syncFromStream(savedStream.conv_id)
          
          // Set current conversation to the streaming one
          if (currentConversationId.value !== savedStream.conv_id) {
            await chatStore.openConversation(savedStream.conv_id)
          }
          
          showToast('Melanjutkan streaming yang terputus...', 'info')
        } else if (data.status === 'done' && data.message_id) {
          // Backend finished - fetch the complete message
          await chatStore.openConversation(savedStream.conv_id)
          userState.deleteKey('chat.streaming', null)
          showToast('Streaming selesai saat Anda refresh', 'success')
        } else {
          // Clear stale streaming state
          userState.deleteKey('chat.streaming', null)
        }
      }
    } catch { /* ignore restore errors */ }
  }
})

onUnmounted(() => {
  chatStore.stopActiveJobPolling()
})

onBeforeUnmount(() => {
  stopStreamingTimer()
  if (toastTimer) clearTimeout(toastTimer)
  if (_attachWarningTimer) clearTimeout(_attachWarningTimer)
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

  // Phase-based status (most accurate during streaming)
  const phase = streamPhase.value
  if (phase === 'sending') return 'Mengirimkan pesan...'
  if (phase === 'thinking') return 'Masih berpikir...'
  if (phase === 'composing') return 'Menyusun jawaban...'
  if (phase === 'streaming') return 'Mengetik...'

  // Fallback: legacy detection via message content
  const msg = messages.value[messages.value.length - 1]
  if (msg?.role !== 'assistant') return 'Menghubungkan...'

  // Check for active tool calls
  if (msg.tool_calls && msg.tool_calls.length > 0) {
    const lastTool = msg.tool_calls[msg.tool_calls.length - 1]
    if (lastTool.status === 'running') {
      // Friendly, user-facing labels. Never surface raw tool names like
      // "SaveWorkflowAnswers" — they look like internal errors to users.
      const toolNames: Record<string, string> = {
        'WebSearch': '🔍 Mencari di web',
        'SearchLiterature': '📚 Mencari literatur',
        'SearchArxiv': '📚 Mencari di arXiv',
        'SearchSemanticScholar': '🎓 Mencari di Semantic Scholar',
        'RunSLR': '🔬 Systematic Literature Review',
        'SearchPapers': '📄 Mencari paper',
        'GenerateFullPaper': '📝 Menyusun paper lengkap',
        'SaveMemory': '💾 Menyimpan catatan',
        'AskQuestions': '❓ Menyiapkan pertanyaan',
        'StartWorkflow': '⚙️ Menyiapkan data awal',
        'SaveWorkflowAnswers': '💾 Menyimpan jawaban',
        'ProposeSection': '✍️ Menulis bagian',
        'ProposeTitle': '📌 Menulis judul',
        'ProposeAbstract': '📄 Menulis abstrak',
        'ProposeKeywords': '🏷️ Menulis keywords',
        'ProposeReference': '📖 Menambah referensi',
        'GenerateImage': '🖼️ Membuat gambar',
        'GenerateChart': '📊 Membuat grafik',
        'CreateChart': '📊 Membuat grafik',
        'ReviewLargeFile': '📋 Meninjau berkas',
        'ClassifyFile': '📂 Memproses berkas',
        'Paraphrase': '✏️ Memparafrase teks',
        'FixGrammar': '🔧 Memperbaiki grammar',
        'Translate': '🌐 Menerjemahkan',
        'RequestExportDocx': '📥 Export DOCX',
        'ReviewPaper': '🔍 Me-review paper',
      }
      return toolNames[lastTool.name] || 'Memproses...'
    }
  }

  // Check for thinking vs typing
  if (msg.thinking && !msg.content) return 'Masih berpikir...'
  if (msg.content) return 'Mengetik...'

  return 'Mengirimkan pesan...'
})

const lastAssistantMessage = computed(() => {
  for (let index = messages.value.length - 1; index >= 0; index -= 1) {
    const message = messages.value[index]
    if (message?.role === 'assistant') return message
  }
  return null
})

const lastAssistantHasVisibleBody = computed(() => {
  const message = lastAssistantMessage.value
  if (!message) return false
  if ((message.content || '').trim()) return true
  if ((message.thinking || '').trim()) return true
  if (message.metadata?.kind) return true
  return (message.tool_calls || []).some((tool: any) => tool?.status === 'error' || !!tool?.error)
})

const showInlineStreamingIndicator = computed(() => {
  if (!isStreaming.value) return false
  return !lastAssistantHasVisibleBody.value
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

watch(() => messages.value.length, () => {
  nextTick(() => {
    if (userIsNearBottom.value) {
      scrollToBottom()
    }
  })
})

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

// ─── Export Draft ───
const exportDraftEstChars = computed(() => {
  const msgs = messages.value || []
  if (!msgs.length) return 0
  // Estimate: sum of message content lengths
  return msgs.reduce((acc, m) => acc + (m.content?.length || 0), 0)
})

function openExportDraftModal(): void {
  if (!messages.value.length) return
  exportDraftName.value = ''
  exportDraftWholeConv.value = true
  exportDraftError.value = ''
  exportDraftSaving.value = false
  exportDraftOpen.value = true
  // Focus input after dialog is rendered
  nextTick(() => {
    exportDraftInput.value?.focus()
  })
}

async function doExportDraft(): Promise<void> {
  const name = exportDraftName.value.trim()
  if (!name) {
    exportDraftError.value = 'Nama draft wajib diisi'
    return
  }
  if (name.length < 2) {
    exportDraftError.value = 'Nama terlalu pendek (min 2 karakter)'
    return
  }
  if (name.length > 200) {
    exportDraftError.value = 'Nama terlalu panjang (max 200 karakter)'
    return
  }

  const convId = currentConversationId.value
  const paperId = currentPaperId.value
  if (!convId || !paperId) {
    exportDraftError.value = 'Tidak ada conversation aktif untuk diekspor'
    return
  }

  exportDraftError.value = ''
  exportDraftSaving.value = true

  try {
  const payload: any = {
    name,
    conversation_id: convId,
    tags: [],
  }
  if (!exportDraftWholeConv.value) {
    payload.selected_message_ids = null
  }

  // Save as draft — backend also creates a PaperFile so it appears in Files tab
  const res = await api.post(`/api/papers/${paperId}/drafts`, payload)
  const draftData = res.data?.draft
  const paperFile = res.data?.paper_file

  if (paperFile) {
    showToast(`Draft "${name}" tersimpan & muncul di tab Files (${(draftData?.content_length || 0).toLocaleString()} karakter)`, 'success')
  } else {
    showToast(`Draft "${name}" tersimpan (${(draftData?.content_length || 0).toLocaleString()} karakter)`, 'success')
  }
  exportDraftOpen.value = false
  try {
    window.dispatchEvent(new CustomEvent('chat-draft-saved', { detail: { paperId, paperFile } }))
  } catch {
    /* ignore */
  }
  } catch (e: any) {
  const errCode = e?.response?.data?.code || ''
  const errMsg = e?.response?.data?.error || e?.message || ''
  if (errCode === 'CONTENT_EMPTY') {
    exportDraftError.value = 'Conversation kosong. Kirim minimal 1 pesan dulu sebelum export draft.'
  } else {
    exportDraftError.value = errMsg || 'Gagal menyimpan draft'
  }
  } finally {
  exportDraftSaving.value = false
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
    _uploadAbortController = new AbortController()

    // Mark all real files as uploading (mutate in-place to preserve File prototype)
    attachedFiles.value.forEach(f => {
      if (realFiles.includes(f as File)) {
        (f as any).uploading = true
      }
    })

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
              signal: _uploadAbortController?.signal,
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
        if (_attachWarningTimer) clearTimeout(_attachWarningTimer)
        _attachWarningTimer = setTimeout(() => { attachWarning.value = ''; _attachWarningTimer = null }, 5000) as unknown as number
      }
      
      // Show success toast for file upload
      if (fileEntries.length > 0) {
        showToast(`${fileEntries.length} file berhasil dilampirkan`, 'success')
      }
      
      const idsLine = ''
      const defaultText = fileEntries.length
        ? `Saya melampirkan ${fileEntries.length} file.`
        : ''
      // Send full text to AI — no truncation
      const names = attachedFiles.value.map(f => f.name).join(', ')
      const blocks = fileEntries.map(e => {
        const content = e.text || '(ekstrak teks gagal / kosong)'
        const header = e.id != null
          ? `--- File terlampir: ${e.name} [file_id=${e.id}] ---`
          : `--- File terlampir: ${e.name} ---`
        return `${header}\n${content}\n--- akhir file ---`
      })
      const fileBlock = blocks.length
        ? '\n\n' + blocks.join('\n\n')
        : `\n\n[File ${names} dilampirkan tetapi gagal diekstrak]`
      composed = (text || defaultText)
        + idsLine
        + fileBlock
      attachedFiles.value = []
    } catch (e: any) {
      // Handle user-initiated abort (stop button during upload)
      if (e?.name === 'AbortError' || e?.name === 'CanceledError' || _uploadAbortController?.signal.aborted) {
        showToast('Upload file dibatalkan', 'warning')
        uploadingFiles.value = false
        _uploadAbortController = null
        // Restore files with their original state (not failed)
        attachedFiles.value = attachedFiles.value.map(f => ({
          ...f,
          uploading: false,
          uploadError: '',
          canRetry: false,
        } as AttachedFile))
        return
      }
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
      _uploadAbortController = null
      return
    }
    uploadingFiles.value = false
    _uploadAbortController = null
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
  // Also abort file upload/extraction if in progress
  if (_uploadAbortController) {
    _uploadAbortController.abort()
    _uploadAbortController = null
  }
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
