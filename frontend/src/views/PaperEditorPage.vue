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
          />
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
          <button v-for="tab in leftTabs" :key="tab.id"
            @click="toggleTab(tab.id)"
            :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              activeTab === tab.id
                ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
                : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']">
            {{ tab.label }}
            <span v-if="tab.id === 'preview' && store.pendingCount > 0"
              class="ml-1 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-amber-500 text-white text-[10px] font-bold">{{ store.pendingCount }}</span>
          </button>
          <button @click="toggleChat"
            :class="['px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1',
              chatOpen
                ? 'bg-ivory-200 dark:bg-anthracite-600 text-ink-900 dark:text-ink-50'
                : 'text-ink-700 dark:text-ink-200 hover:bg-ivory-200 dark:hover:bg-anthracite-600']"
            :title="chatOpen ? 'Tutup AI Chat' : 'Buka AI Chat'">
            💬 AI Chat
            <span class="text-[10px] opacity-60">{{ chatOpen ? '◀' : '▶' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Split layout: left tab pane (collapsible) + right chat panel.
         When no tab is selected, the left pane collapses and the chat goes
         full-width — useful for distraction-free conversation. -->
    <div ref="splitRoot" class="flex h-[calc(100vh-105px)] overflow-hidden relative">
      <!-- LEFT: editor / journal / figures / preview (hidden when no tab is active) -->
      <div v-if="activeTab" class="overflow-y-auto" :class="chatOpen ? 'w-1/2' : 'w-full'">
        <div class="px-4 lg:px-8 py-6">

          <!-- TAB: EDITOR -->
          <div v-show="activeTab === 'editor'" class="space-y-4">
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
          <draggable :list="store.paper.authors" :item-key="stableKey" animation="150" handle=".author-drag" class="space-y-2">
            <template #item="{ element: author, index: i }">
              <div class="bg-ivory-100 dark:bg-anthracite-800 border border-ivory-300 dark:border-anthracite-500 rounded-lg p-3 flex gap-2 items-start">
                <span class="author-drag cursor-grab active:cursor-grabbing text-ivory-500 dark:text-anthracite-200 hover:text-ink-700 dark:hover:text-anthracite-50 select-none text-xl leading-tight pt-1">⠿</span>
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
            class="input resize-none overflow-hidden" placeholder="Paper abstract..."></textarea>
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
        <draggable :list="store.paper.sections" :item-key="stableKey" animation="150" handle=".section-drag" class="space-y-4">
          <template #item="{ element: section, index: sIdx }">
            <div class="card border-l-4 border-l-cream-600">
              <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2 flex-1 min-w-0">
                  <span class="section-drag cursor-grab active:cursor-grabbing text-cream-400 hover:text-brown-500 select-none text-xl leading-tight shrink-0">⠿</span>
                  <span class="text-xs font-bold text-brown-700 bg-cream-200 px-2 py-0.5 rounded shrink-0">
                    Section {{ toRoman(sIdx + 1) }}
                  </span>
                  <input v-model="section.title" class="input-sm flex-1 font-semibold min-w-0"
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

              <draggable :list="section.subsections" :item-key="stableKey" animation="150" handle=".sub-drag" class="space-y-3 mt-4">
                <template #item="{ element: sub, index: subIdx }">
                  <div class="ml-4 border-l-2 border-cream-300 pl-4">
                    <div class="flex items-center justify-between mb-2">
                      <div class="flex items-center gap-2 flex-1 min-w-0">
                        <span class="sub-drag cursor-grab active:cursor-grabbing text-cream-400 hover:text-brown-500 select-none shrink-0">⠿</span>
                        <span class="text-xs font-bold text-brown-700 bg-cream-200 px-1.5 py-0.5 rounded shrink-0">
                          {{ String.fromCharCode(65 + subIdx) }}
                        </span>
                        <input v-model="sub.title" class="input-sm flex-1 font-medium min-w-0"
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
          <draggable :list="store.paper.references" :item-key="(_, i) => i" animation="150" handle=".ref-drag" class="space-y-1.5">
            <template #item="{ element: ref, index: i }">
              <div class="flex gap-2 items-center">
                <span class="ref-drag cursor-grab active:cursor-grabbing text-gray-300 hover:text-gray-500 select-none shrink-0">⠿</span>
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
      <div v-show="activeTab === 'journal'">
        <JournalTab />
      </div>

      <!-- TAB: FIGURES -->
      <div v-show="activeTab === 'figures'">
        <FiguresTab />
      </div>

      <!-- TAB: FILES -->
      <div v-show="activeTab === 'files'">
        <FilesTab />
      </div>

      <!-- TAB: PREVIEW -->
      <div v-show="activeTab === 'preview'">
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

    <!-- Loading Overlay -->
    <Teleport to="body">
      <div v-if="store.loading || store.aiLoading" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
        <div class="bg-white rounded-xl p-8 shadow-2xl text-center max-w-sm mx-4">
          <div class="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mx-auto mb-4"></div>
          <p class="text-sm text-gray-700 font-medium">
            {{ store.aiLoading ? store.aiLoadingMessage || 'AI sedang memproses...' : 'Processing...' }}
          </p>
          <p v-if="store.aiLoading" class="text-xs text-gray-400 mt-2">This may take 3–15 minutes.</p>
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
import AppHeader from '../components/AppHeader.vue'
import ContentList from '../components/ContentList.vue'
import FiguresTab from '../components/FiguresTab.vue'
import FilesTab from '../components/FilesTab.vue'
import JournalTab from '../components/JournalTab.vue'
import PreviewTab from '../components/PreviewTab.vue'
import ChatTab from '../components/ChatTab.vue'

const store = usePaperStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

// rofiq.txt #2 + #3: tab & chat panel state per-paper, restore saat reload.
// Default paper baru = no tab + chat full (lihat ui.js).
const activeTab = ref('')
const newKeyword = ref('')
const abstractRef = ref(null)

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
  { id: 'figures', label: '🖼️ Figures' },
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
watch(() => store.paper, () => {
  if (!store.paper.title?.trim() && !store.currentPaperId) return
  clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(async () => {
    const id = await store.savePaperToDb(true)
    if (id && route.name === 'editor-new') {
      router.replace({ name: 'editor', params: { paperId: id } })
    }
  }, 1800)
}, { deep: true })

onUnmounted(() => clearTimeout(autoSaveTimer))

onMounted(async () => {
  const paperId = route.params.paperId
  if (paperId) {
    await store.loadPaperFromDb(paperId)
    activeTab.value = ui.getTab(paperId)
    chatOpen.value = ui.getChatOpen(paperId)
  } else {
    store.newPaper()
    store.paper.title = ''
    const newId = await store.savePaperToDb(true)
    if (newId) {
      router.replace({ name: 'editor', params: { paperId: newId } })
      activeTab.value = ui.getTab(newId)
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
    if (abstractRef.value) {
      abstractRef.value.style.height = 'auto'
      abstractRef.value.style.height = abstractRef.value.scrollHeight + 'px'
    }
  })
})

watch(() => route.params.paperId, async (newId, oldId) => {
  if (newId && newId !== oldId && newId !== store.currentPaperId) {
    await store.loadPaperFromDb(newId)
    activeTab.value = ui.getTab(newId)
    chatOpen.value = ui.getChatOpen(newId)
  }
})

function toRoman(num) { return store.toRoman(num) }
function toggleTab(id) {
  activeTab.value = activeTab.value === id ? '' : id
  if (store.currentPaperId) ui.setTab(store.currentPaperId, activeTab.value)
}
function autoResize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
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
