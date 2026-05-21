<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850 transition-colors">
    <AppHeader />

    <!-- Sticky Toolbar -->
    <div class="bg-cream-50/95 dark:bg-ash-800/95 backdrop-blur border-b border-cream-300 dark:border-ash-700 sticky top-[57px] z-30 shadow-[0_1px_0_rgba(15,14,11,0.05)]">
      <div class="px-4 lg:px-8 py-2 flex items-center justify-between gap-2 flex-wrap">
        <!-- Left: breadcrumb + editable title + DOCX button -->
        <div class="flex items-center gap-2 min-w-0 flex-1">
          <router-link to="/dashboard"
            class="flex items-center gap-1 text-sm text-ink-700 dark:text-ink-200 hover:text-ink-900 dark:hover:text-ink-50 px-2 py-1.5 rounded hover:bg-cream-200 dark:hover:bg-ash-700 shrink-0 transition-colors">
            ← Papers
          </router-link>
          <span class="text-cream-400 dark:text-ash-600">|</span>
          <input
            v-model="store.paper.title"
            placeholder="Untitled Paper"
            class="text-sm text-ink-900 dark:text-ink-50 font-medium bg-transparent border border-transparent hover:border-cream-400 dark:hover:border-ash-600 focus:border-brown-500 dark:focus:border-cream-400 focus:bg-cream-50 dark:focus:bg-ash-800 focus:outline-none focus:ring-2 focus:ring-cream-200 dark:focus:ring-ash-700 rounded px-2 py-1 truncate min-w-0 flex-1 max-w-md transition-colors"
            title="Klik untuk mengubah judul paper"
            aria-label="Paper title"
          />
          <span v-if="store.loading" class="text-[11px] text-ink-600 dark:text-anthracite-200 animate-pulse shrink-0">Saving…</span>
          <button v-else-if="saveStatus === 'saving'" class="text-[11px] text-ink-600 dark:text-anthracite-200 animate-pulse shrink-0" type="button">Saving…</button>
          <button v-else-if="saveStatus === 'saved'" class="text-[11px] text-emerald-700 dark:text-emerald-300 shrink-0" type="button">Saved · {{ savedRelative }}</button>
          <button v-else-if="saveStatus === 'error'" @click="retrySave" class="text-[11px] text-red-600 dark:text-red-300 hover:underline shrink-0" type="button">Save failed</button>
          <button @click="store.exportDocx()" :disabled="store.loading"
            class="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600 disabled:opacity-50 shrink-0"
            title="Export DOCX">
            📄 DOCX
          </button>
          <span v-if="store.pendingCount > 0"
            class="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-700 shrink-0">
            {{ store.pendingCount }} pending
          </span>
        </div>

        <!-- Right: tabs + chat toggle -->
        <div class="flex items-center gap-1 flex-wrap">
          <div role="tablist" class="flex items-center gap-1 flex-wrap" @keydown="onTabKeydown">
          <button v-for="tab in leftTabs" :key="tab.id"
            @click="toggleTab(tab.id)"
            role="tab"
            :id="`tab-${tab.id}`"
            :aria-selected="activeTab === tab.id"
            :aria-controls="`panel-${tab.id}`"
            :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              activeTab === tab.id
                ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
                : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']">
            {{ tab.label }}
            <span v-if="tab.id === 'preview' && store.pendingCount > 0"
              class="ml-1 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-amber-500 text-white text-[10px] font-bold">{{ store.pendingCount }}</span>
          </button>
          </div>
          <button @click="toggleChat"
            :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1',
              chatOpen
                ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
                : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']"
            :title="chatOpen ? 'Tutup AI Chat' : 'Buka AI Chat'">
            💬 AI Chat
          </button>
        </div>
      </div>
    </div>

    <!-- Generation status banner (non-blocking) -->
    <div v-if="store.aiLoading"
         class="bg-amber-50 dark:bg-amber-900/30 border-b border-amber-300 dark:border-amber-700 px-4 lg:px-8 py-2.5 flex items-center gap-3 text-amber-900 dark:text-amber-200 text-sm">
      <div class="relative w-6 h-6 shrink-0">
        <div class="absolute inset-0 rounded-full border-2 border-amber-200 dark:border-amber-700"></div>
        <div class="absolute inset-0 rounded-full border-2 border-t-amber-600 dark:border-t-amber-300 animate-spin"></div>
      </div>
      <div class="flex-1 min-w-0 leading-snug">
        <span class="font-medium">{{ store.aiLoadingMessage || 'AI sedang generate paper...' }}</span>
        <span class="opacity-70 ml-2">· Elapsed: {{ aiElapsedLabel }}</span>
        <span v-if="aiElapsedSeconds > 600" class="ml-2 opacity-80">(masih bekerja — paper besar bisa sampai 15 menit)</span>
      </div>
      <button v-if="canCancelAi" @click="chatStore.stopStreaming()"
              class="shrink-0 px-2.5 py-1 rounded text-xs font-medium border border-amber-400 dark:border-amber-700 hover:bg-amber-100 dark:hover:bg-amber-900/50">Cancel</button>
    </div>

    <!-- Split layout: left tab pane (collapsible) + right chat panel.
         When no tab is selected, the left pane collapses and the chat goes
         full-width — useful for distraction-free conversation. -->
    <div ref="splitRoot" class="flex h-[calc(100vh-105px)] overflow-hidden relative">
      <!-- LEFT: editor / journal / figures / preview.
           NOTE: we use v-show (not v-if) on the outer wrapper so all panels
           — including LiteratureTab — stay mounted from the very first paint.
           This is what makes chat-triggered SLR auto-open work seamlessly:
           the literature poller is already running before the tab gets
           switched in by `ui.requestTab(...)`. -->
      <div v-show="activeTab" class="overflow-y-auto" :class="chatOpen ? 'w-1/2' : 'w-full'">
        <div class="px-4 lg:px-8 py-6">

          <!-- TAB: EDITOR -->
          <div v-show="activeTab === 'editor'" role="tabpanel" id="panel-editor" aria-labelledby="tab-editor" class="space-y-4">
        <!-- Title -->
        <div class="card border-l-4 border-l-brown-500">
          <label class="label">Title</label>
          <input v-model="store.paper.title" class="input" placeholder="Paper title..." />
        </div>

        <!-- Authors -->
        <div class="card border-l-4 border-l-brown-500">
          <div class="flex items-center justify-between mb-3">
            <label class="label !mb-0">Authors</label>
            <button @click="store.addAuthor()" class="btn-add">+ Author</button>
          </div>
          <draggable :list="store.paper.authors" :item-key="stableKey" animation="150" handle=".author-drag" class="space-y-2"
                     :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
            <template #item="{ element: author, index: i }">
              <div class="group bg-ivory-100 dark:bg-anthracite-800 border border-ivory-300 dark:border-anthracite-500 rounded-lg p-3 flex gap-2 items-start">
                <span role="button" aria-label="Drag to reorder" class="author-drag cursor-grab active:cursor-grabbing text-ivory-500 dark:text-anthracite-200 hover:text-ink-700 dark:hover:text-anthracite-50 select-none text-xl leading-tight pt-1">⠿</span>
                <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                  <button @click="moveItem(store.paper.authors, i, i - 1)" :disabled="i === 0" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move up">↑</button>
                  <button @click="moveItem(store.paper.authors, i, i + 1)" :disabled="i === store.paper.authors.length - 1" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move down">↓</button>
                </div>
                <div class="flex-1">
                  <div class="flex justify-between mb-2">
                    <span class="text-xs text-ink-700 dark:text-anthracite-100 font-medium">Author {{ i + 1 }}</span>
                    <button v-if="store.paper.authors.length > 1" @click="store.removeAuthor(i)"
                      class="text-xs text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300">✕</button>
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <input v-model="author.name" class="input-sm" placeholder="Name" />
                    <input v-model="author.email" class="input-sm" placeholder="Email" />
                    <input v-model="author.affiliation" class="input-sm col-span-2" placeholder="Affiliation" />
                    <input v-model="author.location" class="input-sm col-span-2" placeholder="Location" />
                  </div>
                </div>
              </div>
            </template>
          </draggable>
        </div>

        <!-- Abstract -->
        <div class="card border-l-4 border-l-brown-500">
          <label class="label">Abstract</label>
          <textarea v-model="store.paper.abstract" rows="2" @input="autoResize"
            ref="abstractRef"
            class="input resize-none overflow-hidden min-h-[4.5rem]" placeholder="Paper abstract..."></textarea>
        </div>

        <!-- Keywords -->
        <div class="card border-l-4 border-l-cream-500">
          <label class="label">Keywords</label>
          <div class="flex flex-wrap gap-1.5 mb-2">
            <span v-for="(kw, i) in store.paper.keywords" :key="i"
              class="bg-cream-200 text-brown-800 px-2 py-0.5 rounded text-sm flex items-center gap-1">
              {{ kw }}
              <button @click="store.removeKeyword(i)" class="text-brown-400 hover:text-brown-700 text-xs">✕</button>
            </span>
          </div>
          <div class="flex gap-2">
            <input v-model="newKeyword" class="input-sm flex-1" placeholder="Add keyword..." @keyup.enter="addKw" />
            <button @click="addKw" class="btn-add">Add</button>
          </div>
        </div>

        <!-- Sections -->
        <draggable :list="store.paper.sections" :item-key="stableKey" animation="150" handle=".section-drag" class="space-y-4"
                   :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
          <template #item="{ element: section, index: sIdx }">
            <div class="group card border-l-4 border-l-cream-600">
              <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2 flex-1 min-w-0">
                  <span role="button" aria-label="Drag to reorder" class="section-drag cursor-grab active:cursor-grabbing text-cream-400 hover:text-brown-500 select-none text-xl leading-tight shrink-0">⠿</span>
                  <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                    <button @click="moveItem(store.paper.sections, sIdx, sIdx - 1)" :disabled="sIdx === 0" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move up">↑</button>
                    <button @click="moveItem(store.paper.sections, sIdx, sIdx + 1)" :disabled="sIdx === store.paper.sections.length - 1" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move down">↓</button>
                  </div>
                  <span class="text-[10px] text-ink-500 dark:text-ink-300 font-medium uppercase tracking-wide bg-transparent border-l-2 border-ivory-300 pl-2 shrink-0">
                    Section {{ toRoman(sIdx + 1) }}
                  </span>
                  <input v-model="section.title" class="input-sm flex-1 text-base font-semibold min-w-0"
                    placeholder="Section Title (e.g. INTRODUCTION)" />
                </div>
                <button @click="store.removeSection(sIdx)"
                  class="text-xs text-red-400 hover:text-red-600 px-2 py-1 ml-2 shrink-0">✕</button>
              </div>

              <ContentList :items="section.content" :store="store" />
              <div class="flex gap-2 mt-3 flex-wrap">
                <button @click="store.addContent(section.content, 'text')" class="btn-content">+ Text</button>
                <button @click="store.addContent(section.content, 'gambar')" class="btn-content">+ Image</button>
                <button @click="store.addContent(section.content, 'tabel')" class="btn-content">+ Table</button>
                <button @click="store.addContent(section.content, 'rumus')" class="btn-content">+ Formula</button>
              </div>

              <draggable :list="section.subsections" :item-key="stableKey" animation="150" handle=".sub-drag" class="space-y-3 mt-4"
                         :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
                <template #item="{ element: sub, index: subIdx }">
                  <div class="group ml-4 border-l-2 border-cream-300 pl-4">
                    <div class="flex items-center justify-between mb-2">
                      <div class="flex items-center gap-2 flex-1 min-w-0">
                        <span role="button" aria-label="Drag to reorder" class="sub-drag cursor-grab active:cursor-grabbing text-cream-400 hover:text-brown-500 select-none shrink-0">⠿</span>
                        <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                          <button @click="moveItem(section.subsections, subIdx, subIdx - 1)" :disabled="subIdx === 0" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move up">↑</button>
                          <button @click="moveItem(section.subsections, subIdx, subIdx + 1)" :disabled="subIdx === section.subsections.length - 1" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move down">↓</button>
                        </div>
                        <span class="text-[10px] text-ink-500 dark:text-ink-300 font-medium uppercase tracking-wide bg-transparent border-l-2 border-ivory-300 pl-2 shrink-0">
                          {{ String.fromCharCode(65 + subIdx) }}
                        </span>
                        <input v-model="sub.title" class="input-sm flex-1 text-base font-semibold min-w-0"
                          placeholder="Subsection Title" />
                      </div>
                      <button @click="store.removeSubsection(sIdx, subIdx)"
                        class="text-xs text-red-400 hover:text-red-600 px-2 py-1 ml-2 shrink-0">✕</button>
                    </div>
                    <ContentList :items="sub.content" :store="store" />
                    <div class="flex gap-2 mt-2 flex-wrap">
                      <button @click="store.addContent(sub.content, 'text')" class="btn-content text-xs">+ Text</button>
                      <button @click="store.addContent(sub.content, 'gambar')" class="btn-content text-xs">+ Image</button>
                      <button @click="store.addContent(sub.content, 'tabel')" class="btn-content text-xs">+ Table</button>
                      <button @click="store.addContent(sub.content, 'rumus')" class="btn-content text-xs">+ Formula</button>
                    </div>
                  </div>
                </template>
              </draggable>

              <button @click="store.addSubsection(sIdx)"
                class="mt-3 w-full py-2 border border-dashed border-cream-400 rounded-lg text-brown-500 hover:bg-cream-100 text-sm transition-colors">
                + Add Subsection
              </button>
            </div>
          </template>
        </draggable>

        <button @click="store.addSection()"
          class="w-full py-3 border-2 border-dashed border-cream-300 rounded-xl text-brown-400 hover:border-brown-400 hover:text-brown-700 transition text-sm">
          + Add Section
        </button>

        <!-- References -->
        <div class="card border-l-4 border-l-red-400">
          <div class="flex items-center justify-between mb-3">
            <label class="label !mb-0">References</label>
            <button @click="store.addReference()" class="btn-add">+ Reference</button>
          </div>
          <draggable :list="store.paper.references" :item-key="(_, i) => i" animation="150" handle=".ref-drag" class="space-y-1.5"
                     :scroll-sensitivity="200" :scroll-speed="22" :bubble-scroll="true">
            <template #item="{ element: ref, index: i }">
              <div class="group flex gap-2 items-center">
                <span role="button" aria-label="Drag to reorder" class="ref-drag cursor-grab active:cursor-grabbing text-gray-300 hover:text-gray-500 select-none shrink-0">⠿</span>
                <div class="flex flex-col gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                  <button @click="moveItem(store.paper.references, i, i - 1)" :disabled="i === 0" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move up">↑</button>
                  <button @click="moveItem(store.paper.references, i, i + 1)" :disabled="i === store.paper.references.length - 1" class="text-[10px] text-ink-500 disabled:opacity-30" aria-label="Move down">↓</button>
                </div>
                <span class="text-[11px] text-gray-400 w-7 text-right shrink-0">[{{ i + 1 }}]</span>
                <input :value="ref" @input="store.paper.references[i] = $event.target.value"
                  class="input-sm flex-1 text-xs" placeholder="Reference text..." />
                <button @click="store.removeReference(i)" class="text-red-300 hover:text-red-500 text-xs shrink-0">✕</button>
              </div>
            </template>
          </draggable>
        </div>

        <div class="h-20"></div>
      </div>

      <!-- TAB: JOURNAL -->
      <div v-show="activeTab === 'journal'" role="tabpanel" id="panel-journal" aria-labelledby="tab-journal">
        <JournalTab />
      </div>

      <!-- TAB: LITERATURE -->
      <div v-show="activeTab === 'literature'" role="tabpanel" id="panel-literature" aria-labelledby="tab-literature">
        <LiteratureTab />
      </div>

      <!-- TAB: FILES -->
      <div v-show="activeTab === 'files'" role="tabpanel" id="panel-files" aria-labelledby="tab-files">
        <FilesTab />
      </div>

      <!-- TAB: PREVIEW -->
      <div v-show="activeTab === 'preview'" role="tabpanel" id="panel-preview" aria-labelledby="tab-preview">
        <PreviewTab />
      </div>
        </div>
      </div>

      <!-- RIGHT: chat panel. Full-width when no tab is selected. -->
      <div v-if="chatOpen" class="bg-cream-50 dark:bg-ash-800 border-l border-cream-300 dark:border-ash-700 shrink-0 overflow-hidden flex flex-col shadow-[-1px_0_0_rgba(15,14,11,0.06)]"
        :class="activeTab ? 'w-1/2' : 'w-full'">
        <ChatTab :paper-id="store.currentPaperId" @open-preview="activeTab = 'preview'" />
      </div>
    </div>

    <!-- Toast -->
    <Teleport to="body">
      <div v-if="store.toast.show" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[999]">
        <div :class="['px-4 py-2.5 rounded-lg shadow-lg text-white text-sm font-medium',
          store.toast.type === 'success' ? 'bg-green-600' :
          store.toast.type === 'error' ? 'bg-red-600' : 'bg-blue-600']">
          {{ store.toast.message }}
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import draggable from 'vuedraggable'
import { usePaperStore } from '../stores/paper.js'
import { useUiStore } from '../stores/ui.js'
import { useChatStore } from '../stores/chat.js'
import AppHeader from '../components/AppHeader.vue'
import ContentList from '../components/ContentList.vue'
import FilesTab from '../components/FilesTab.vue'
import JournalTab from '../components/JournalTab.vue'
import LiteratureTab from '../components/LiteratureTab.vue'
import PreviewTab from '../components/PreviewTab.vue'
import ChatTab from '../components/ChatTab.vue'
import { useImageGenStore } from '../stores/imageGen.js'

const store = usePaperStore()
const ui = useUiStore()
const chatStore = useChatStore()
const imageGenStore = useImageGenStore()
const route = useRoute()
const router = useRouter()

// rofiq.txt #2 + #3: tab & chat panel state per-paper, restore saat reload.
// Default paper baru = no tab + chat full (lihat ui.js).
// `activeTab` is a computed proxy onto the UI store so chat-triggered tab
// switches (e.g. SLR auto-open) take effect immediately.
const activeTab = computed({
  get: () => (store.currentPaperId ? ui.getTab(store.currentPaperId) : '') || '',
  set: (v) => {
    if (store.currentPaperId) ui.setTab(store.currentPaperId, v || '')
  },
})
// Force a re-read whenever something external bumps the signal — even when
// the new tab id is the same as the old one.
watch(() => ui.tabSwitchSignal, () => { /* computed re-evaluates via getTab */ })
const newKeyword = ref('')
const abstractRef = ref(null)
const saveStatus = ref('saved')
const lastSavedAt = ref(null)
const nowTick = ref(Date.now())
const aiStartedAt = ref(null)

// ─── Split layout state ───────────────────────────────────────────────────
const splitRoot = ref(null)
const chatOpen = ref(true)

function toggleChat() {
  chatOpen.value = !chatOpen.value
  if (store.currentPaperId) ui.setChatOpen(store.currentPaperId, chatOpen.value)
}

// ─── Topic / Style / PDF state (used by chat for file attach) ─────────────
const availableTopics = ref([])
const availableStyles = ref([])

const leftTabs = [
  { id: 'editor', label: '📝 Editor' },
  { id: 'journal', label: '📚 Journal' },
  { id: 'literature', label: '📖 Literatur' },
  { id: 'files', label: '📂 Files' },
  { id: 'preview', label: '👁 Preview' },
]

const keyMap = new WeakMap()
let __kc = 0
function stableKey(obj) {
  if (typeof obj !== 'object' || !obj) return String(obj)
  if (!keyMap.has(obj)) keyMap.set(obj, String(++__kc))
  return keyMap.get(obj)
}

let autoSaveTimer = null
let tickTimer = null
const savedRelative = computed(() => lastSavedAt.value ? 'just now' : 'just now')
const aiElapsedSeconds = computed(() => aiStartedAt.value ? Math.floor((nowTick.value - aiStartedAt.value) / 1000) : 0)
const aiElapsedLabel = computed(() => aiElapsedSeconds.value < 60 ? `0:${String(aiElapsedSeconds.value).padStart(2, '0')}` : `${Math.floor(aiElapsedSeconds.value / 60)}m ${aiElapsedSeconds.value % 60}s`)
const canCancelAi = computed(() => typeof chatStore.stopStreaming === 'function')

watch(() => store.aiLoading, (v) => {
  aiStartedAt.value = v ? Date.now() : null
})

watch(() => store.paper, () => {
  if (!store.paper.title?.trim() && !store.currentPaperId) return
  clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(async () => {
    saveStatus.value = 'saving'
    try {
      const id = await store.savePaperToDb(true)
      lastSavedAt.value = Date.now()
      saveStatus.value = 'saved'
      if (id && route.name === 'editor-new') {
        router.replace({ name: 'editor', params: { paperId: id } })
      }
    } catch (e) {
      saveStatus.value = 'error'
    }
  }, 1800)
}, { deep: true })

onUnmounted(() => {
  clearTimeout(autoSaveTimer)
  clearInterval(tickTimer)
  window.removeEventListener('resize', resizeAbstract)
})

onMounted(async () => {
  tickTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
  window.addEventListener('resize', resizeAbstract)
  imageGenStore.resume()
  const paperId = route.params.paperId
  if (paperId) {
    await store.loadPaperFromDb(paperId)
    chatOpen.value = ui.getChatOpen(paperId)
  } else {
    store.newPaper()
    store.paper.title = ''
    const newId = await store.savePaperToDb(true)
    if (newId) {
      router.replace({ name: 'editor', params: { paperId: newId } })
      chatOpen.value = ui.getChatOpen(newId)
    }
  }
  try {
    const [tRes, sRes] = await Promise.all([
      store.apiGet('/api/topics'),
      store.apiGet('/api/styles'),
    ])
    availableTopics.value = tRes?.data?.topics || []
    availableStyles.value = sRes?.data?.styles || []
  } catch (e) { /* non-critical */ }

  nextTick(() => {
    resizeAbstract()
  })
})

watch(() => store.paper.abstract, () => resizeAbstract())
watch(() => chatOpen.value, () => resizeAbstract())

watch(() => route.params.paperId, async (newId, oldId) => {
  if (newId && newId !== oldId && newId !== store.currentPaperId) {
    await store.loadPaperFromDb(newId)
    chatOpen.value = ui.getChatOpen(newId)
    resizeAbstract()
  }
})

function toRoman(num) { return store.toRoman(num) }
function toggleTab(id) {
  activeTab.value = activeTab.value === id ? '' : id
}
function onTabKeydown(e) {
  if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return
  const idx = leftTabs.findIndex(t => t.id === activeTab.value)
  const next = e.key === 'ArrowRight' ? (idx + 1) % leftTabs.length : (idx - 1 + leftTabs.length) % leftTabs.length
  activeTab.value = leftTabs[next].id
}
function moveItem(list, from, to) {
  if (!Array.isArray(list) || to < 0 || to >= list.length || from === to) return
  const [item] = list.splice(from, 1)
  list.splice(to, 0, item)
}
async function retrySave() {
  saveStatus.value = 'saving'
  try {
    await store.savePaperToDb(true)
    lastSavedAt.value = Date.now()
    saveStatus.value = 'saved'
  } catch (e) {
    saveStatus.value = 'error'
  }
}
function autoResize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}
function resizeAbstract() {
  nextTick(() => {
    const el = abstractRef.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = el.scrollHeight + 'px'
  })
}
function addKw() {
  if (newKeyword.value.trim()) { store.addKeyword(newKeyword.value.trim()); newKeyword.value = '' }
}
</script>

<style scoped>
.card { @apply bg-white dark:bg-anthracite-700 rounded-xl shadow-[0_1px_0_rgba(15,14,11,0.04),0_1px_3px_rgba(15,14,11,0.06)] border border-ivory-300 dark:border-anthracite-500 p-5; }
.label { @apply block text-sm font-medium text-ink-900 dark:text-ink-50 mb-1.5; }
.input { @apply w-full px-3 py-2 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none; }
.input-sm { @apply px-2.5 py-1.5 border border-ivory-300 dark:border-anthracite-500 rounded-lg text-sm bg-white dark:bg-anthracite-800 text-ink-900 dark:text-anthracite-50 placeholder-ivory-500 dark:placeholder-anthracite-200 focus:ring-2 focus:ring-ivory-300 dark:focus:ring-anthracite-500 focus:border-ink-700 dark:focus:border-anthracite-100 outline-none; }
.btn-add { @apply px-3 py-1 bg-ivory-200 hover:bg-ivory-300 dark:bg-anthracite-600 dark:hover:bg-anthracite-500 text-ink-900 dark:text-anthracite-50 rounded-lg text-xs font-medium transition-colors; }
.btn-content { @apply px-2.5 py-1 bg-ivory-200 hover:bg-ivory-300 dark:bg-anthracite-600 dark:hover:bg-anthracite-500 text-ink-900 dark:text-anthracite-50 rounded text-xs transition-colors; }
</style>
