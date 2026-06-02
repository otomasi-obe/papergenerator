<template>
  <div>
    <!-- Pending changes summary above input -->
    <div
      v-if="pendingCount > 0"
      class="px-4 pt-2 pb-2 bg-amber-50 dark:bg-amber-900/20 border-t border-amber-200 dark:border-amber-800"
    >
      <div class="flex items-center gap-2 text-xs text-amber-900 dark:text-amber-200">
        <span class="text-base leading-none shrink-0">⚠️</span>
        <span class="flex-1 leading-snug">
          <strong>{{ pendingCount }} perubahan</strong> belum disetujui.
          <button @click="$emit('open-preview')" class="underline font-semibold hover:text-amber-700 dark:hover:text-amber-100">Buka Preview</button>
        </span>
      </div>
      <div class="flex items-center gap-1.5 mt-1.5">
        <button
          @click="$emit('accept-all-proposals')"
          class="flex-1 px-2.5 py-1 min-h-[44px] text-[11px] font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white"
        >✓ Terima semua</button>
        <button
          @click="$emit('reject-all-proposals')"
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
          @click="$emit('send-suggestion', s)"
          :disabled="isStreaming || (activeJob && activeJob.active)"
          class="text-[11px] px-2.5 py-1 min-h-[44px] rounded-full bg-cream-100 dark:bg-ash-700 hover:bg-brown-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 text-ink-800 dark:text-ink-100 transition-colors border border-cream-300 dark:border-ash-600 disabled:opacity-50 disabled:cursor-not-allowed"
          :title="s.text"
        >
          {{ s.label }}
        </button>
      </div>
    </div>

    <!-- Active-job banner -->
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
      <!-- Upload progress bar -->
      <div v-if="uploadingFiles" class="mb-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-medium text-blue-900 dark:text-blue-100">
            Uploading {{ uploadFileCount.current }} of {{ uploadFileCount.total }} files...
          </span>
          <span class="text-xs font-mono text-blue-700 dark:text-blue-300">{{ uploadProgress }}%</span>
        </div>
        <div class="h-2 rounded-full bg-blue-100 dark:bg-blue-900/40 overflow-hidden">
          <div
            class="h-full rounded-full bg-blue-600 dark:bg-blue-400 transition-all duration-300"
            :style="{ width: uploadProgress + '%' }"
          ></div>
        </div>
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
              : 'bg-cream-100 dark:bg-ash-700 border border-cream-300 dark:border-ash-600 text-ink-900 dark:text-ink-50'
          ]"
        >
          <span>{{ f.uploadError ? '⚠️' : '📄' }}</span>
          <div class="flex flex-col min-w-0">
            <span class="truncate max-w-[160px]" :title="f.name">{{ f.name }}</span>
            <span v-if="f.uploadError" class="text-[10px] text-red-700 dark:text-red-300">{{ f.uploadError }}</span>
          </div>
          <button
            v-if="f.canRetry"
            @click="$emit('retry-upload', i)"
            class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200 ml-1 min-h-[24px] min-w-[24px]"
            title="Retry upload"
            aria-label="Retry upload"
          ><span aria-hidden="true">↻</span></button>
          <button
            @click="$emit('remove-attached-file', i)"
            class="text-ink-500 dark:text-ink-300 hover:text-rose-500 ml-1 min-h-[24px] min-w-[24px]"
            title="Remove"
            aria-label="Remove attached file"
          ><span aria-hidden="true">✕</span></button>
        </div>
      </div>
      <p v-if="attachWarning" class="text-[10px] text-amber-700 dark:text-amber-300 mb-1">{{ attachWarning }}</p>

      <div class="rounded-2xl border-2 border-cream-400 dark:border-ash-600 bg-cream-50 dark:bg-ash-700 shadow-sm focus-within:border-brown-500 dark:focus-within:border-cream-400 focus-within:ring-4 focus-within:ring-cream-200 dark:focus-within:ring-ash-600 transition-all">
        <div class="flex items-center gap-2 p-2">
          <button
            @click="$emit('toggle-suggestions')"
            :aria-expanded="showSuggestions && !inputText"
            class="shrink-0 h-11 min-w-[44px] px-2 text-[11px] text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 rounded-xl transition-colors"
            title="Saran"
          >💡 Saran</button>
          <input
            type="file"
            ref="fileInput"
            accept=".pdf,.docx,.doc"
            multiple
            class="hidden"
            @change="$emit('file-change', $event)"
          />
          <div class="relative shrink-0" v-click-outside="closeAttachMenu">
            <button
              @click="toggleAttachMenu"
              :disabled="isStreaming || uploadingFiles"
              class="h-11 w-11 text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-600 hover:text-ink-900 dark:hover:text-ink-50 rounded-xl transition-colors flex items-center justify-center disabled:opacity-40"
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
                @click="$emit('pick-upload')"
                class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2"
              >
                <span>📤</span><span>Upload file (PDF/DOCX)</span>
              </button>
              <button
                type="button"
                @click="$emit('open-paste-text')"
                class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2 border-t border-cream-300 dark:border-ash-600"
              >
                <span>📋</span><span>Paste teks</span>
              </button>
              <button
                type="button"
                @click="$emit('open-existing-files')"
                class="w-full text-left px-3 py-2 text-xs hover:bg-cream-200 dark:hover:bg-ash-600 text-ink-800 dark:text-ink-100 flex items-center gap-2 border-t border-cream-300 dark:border-ash-600"
              >
                <span>📁</span><span>Dari file paper ini</span>
              </button>
            </div>
          </div>
          <textarea
            ref="inputRef"
            :value="inputText"
            @input="$emit('update:inputText', ($event.target as HTMLTextAreaElement).value)"
            @keydown="handleKeydown"
            :disabled="activeJob && activeJob.active"
            :placeholder="(activeJob && activeJob.active) ? 'Terkunci saat generate…' : (isStreaming ? 'AI mengetik…' : 'Ketik pesan…')"
            rows="1"
            class="chat-input-textarea flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink-900 dark:text-ink-50 focus:outline-none disabled:opacity-50 max-h-32 overflow-y-auto placeholder-ink-500 dark:placeholder-ink-300"
          ></textarea>
          <button
            v-if="isStreaming"
            @click="$emit('stop')"
            class="shrink-0 h-11 w-11 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-colors flex items-center justify-center"
            title="Stop"
            aria-label="Stop generating"
          >
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="1.5"/>
            </svg>
          </button>
          <button
            v-else
            @click="$emit('send')"
            :disabled="(!inputText.trim() && !attachedFiles.length) || (activeJob && activeJob.active)"
            class="shrink-0 h-11 w-11 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface AttachedFile extends File {
  uploadError?: string
  canRetry?: boolean
}

interface Suggestion {
  key: string
  label: string
  text: string
}

interface ActiveJob {
  active: boolean
  prompt: string
  elapsed_seconds: number
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
  inputText: string
  isStreaming: boolean
  attachedFiles: AttachedFile[]
  attachWarning: string
  uploadingFiles: boolean
  uploadFileCount: { current: number; total: number }
  showSuggestions: boolean
  quickSuggestions: Suggestion[]
  activeJob: ActiveJob | null
  pendingCount: number
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'update:inputText', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  (e: 'file-change', event: Event): void
  (e: 'remove-attached-file', index: number): void
  (e: 'retry-upload', index: number): void
  (e: 'toggle-suggestions'): void
  (e: 'send-suggestion', suggestion: Suggestion): void
  (e: 'pick-upload'): void
  (e: 'open-paste-text'): void
  (e: 'open-existing-files'): void
  (e: 'open-preview'): void
  (e: 'accept-all-proposals'): void
  (e: 'reject-all-proposals'): void
}>()

const inputRef = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const attachMenuOpen = ref(false)

const uploadProgress = computed(() => {
  if (!props.uploadFileCount.total) return 0
  return Math.round((props.uploadFileCount.current / props.uploadFileCount.total) * 100)
})

function toggleAttachMenu(): void {
  attachMenuOpen.value = !attachMenuOpen.value
}

function closeAttachMenu(): void {
  attachMenuOpen.value = false
}

function handleKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    emit('send')
  }
}

function formatElapsed(sec: number): string {
  if (!sec || sec < 60) return `${sec || 0}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

const emit = defineEmits<{
  (e: 'update:inputText', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  (e: 'file-change', event: Event): void
  (e: 'remove-attached-file', index: number): void
  (e: 'retry-upload', index: number): void
  (e: 'toggle-suggestions'): void
  (e: 'send-suggestion', suggestion: Suggestion): void
  (e: 'pick-upload'): void
  (e: 'open-paste-text'): void
  (e: 'open-existing-files'): void
  (e: 'open-preview'): void
  (e: 'accept-all-proposals'): void
  (e: 'reject-all-proposals'): void
}>()

defineExpose({
  inputRef,
  fileInput
})
</script>
