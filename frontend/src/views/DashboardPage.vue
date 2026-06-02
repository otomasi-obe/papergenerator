<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850 transition-colors">
    <AppHeader />

    <main class="px-4 lg:px-8 py-8">
      <!-- Header -->
      <div class="flex items-center justify-between mb-8">
        <div>
          <h1 class="text-2xl font-bold font-serif text-ink-900 dark:text-ink-50">My Papers</h1>
          <p class="text-ink-700 dark:text-ink-300 text-sm mt-1">{{ papers.length }} paper{{ papers.length === 1 ? '' : 's' }}</p>
        </div>
        <router-link to="/editor"
          class="flex items-center gap-2 px-5 py-2.5 min-h-[44px] bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-xl font-medium transition-colors shadow-sm active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
          + New Paper
        </router-link>
      </div>

      <StateView :loading="loading" :error="errorMsg" :is-empty="papers.length === 0" :on-retry="loadPapers">
        <template #loading>
          <div class="text-center py-20 text-ink-600 dark:text-ink-300">
            <div class="text-3xl mb-3 animate-spin" aria-hidden="true">⚙️</div>
            Loading your papers...
          </div>
        </template>
        <template #empty>
          <div class="text-center py-20">
            <div class="text-6xl mb-4" aria-hidden="true">📄</div>
            <h2 class="text-xl font-semibold text-ink-900 dark:text-ink-50 mb-2">No papers yet</h2>
            <p class="text-ink-700 dark:text-ink-300 mb-6">Create your first paper with AI assistance</p>
            <router-link to="/editor" class="px-6 py-3 min-h-[44px] inline-flex items-center bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-xl font-medium transition-colors active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
              Create First Paper
            </router-link>
          </div>
        </template>

        <div class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          <article v-for="paper in papers" :key="paper.id"
            class="bg-cream-50 dark:bg-ash-800 rounded-2xl border border-cream-300 dark:border-ash-700 shadow-sm hover:shadow-md transition-all overflow-hidden group hover:border-navy-500 dark:hover:border-cream-400">
            <router-link :to="{ name: 'editor', params: { paperId: paper.id } }" @click="store.currentPaperId = null"
              class="block p-5 pb-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] rounded-t-2xl">
              <h3 class="font-semibold font-serif text-ink-900 dark:text-ink-50 text-base leading-snug line-clamp-3 mb-2 group-hover:text-navy-700 dark:group-hover:text-cream-200 transition-colors">
                {{ paper.title || 'Untitled Paper' }}
              </h3>
              <div class="flex flex-wrap gap-2 text-xs text-ink-600 dark:text-ink-300">
                <span class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700">Updated {{ formatDate(paper.updated_at) }}</span>
                <span class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700"><span aria-hidden="true">🖼️</span> {{ paper.image_count || 0 }} image{{ paper.image_count === 1 ? '' : 's' }}</span>
                <span v-if="paper.journal" class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700">{{ paper.journal }}</span>
                <span v-if="paper.section_count" class="px-2 py-0.5 rounded-full bg-cream-100 dark:bg-ash-700">{{ paper.section_count }} sections</span>
              </div>
            </router-link>

            <div class="flex items-center gap-2 px-4 pb-4">
              <button @click="openPaper(paper)"
                class="flex-1 px-3 py-1.5 min-h-[44px] bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 text-xs rounded-lg transition-colors font-medium active:scale-95 transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
                Open
              </button>
              <button @click="copyPaper(paper)" :disabled="copying === paper.id"
                class="px-3 py-1.5 min-h-[44px] min-w-[44px] bg-cream-200 hover:bg-cream-300 dark:bg-ash-700 dark:hover:bg-ash-600 text-ink-900 dark:text-ink-50 text-xs rounded-lg transition-colors disabled:opacity-50 active:scale-95 transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
                title="Copy paper">
                {{ copying === paper.id ? '...' : 'Copy' }}
              </button>
              <button @click="confirmDelete(paper)"
                class="px-3 py-1.5 min-h-[44px] min-w-[44px] bg-red-50 hover:bg-red-100 dark:bg-red-900/30 dark:hover:bg-red-900/50 text-red-700 dark:text-red-400 text-xs rounded-lg transition-colors active:scale-95 transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
                title="Delete paper">
                Delete
              </button>
            </div>
          </article>
        </div>
      </StateView>
    </main>

    <AppDialog v-if="deleteTarget" :open="!!deleteTarget" title="Delete Paper?" @close="deleteTarget = null">
      <p class="text-ink-700 dark:text-ink-200 text-sm">
        "<strong>{{ deleteTarget.title || 'Untitled Paper' }}</strong>" and all its images will be permanently deleted.
      </p>
      <template #actions>
        <button @click="deleteTarget = null"
          class="px-4 py-2.5 min-h-[44px] border border-cream-400 dark:border-ash-600 hover:bg-cream-100 dark:hover:bg-ash-700 text-ink-900 dark:text-ink-50 rounded-xl text-sm font-medium transition-colors active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
          Cancel
        </button>
        <button @click="doDelete()"
          class="px-4 py-2.5 min-h-[44px] bg-[#c43655] hover:bg-[#c43655]/90 text-white rounded-xl text-sm font-medium transition-colors active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2">
          Delete
        </button>
      </template>
    </AppDialog>

    <Teleport to="body">
      <div v-if="toastMsg" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] px-4 py-2.5 rounded-lg shadow-lg text-white text-sm bg-ink-900 dark:bg-cream-200 dark:text-ash-900">{{ toastMsg }}</div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/index.js'
import AppHeader from '../components/AppHeader.vue'
import AppDialog from '../components/AppDialog.vue'
import StateView from '../components/StateView.vue'
import { usePaperStore } from '../stores/paper.js'

const router = useRouter()
const store = usePaperStore()

const papers = ref([])
const loading = ref(true)
const deleteTarget = ref(null)
const copying = ref(null)
const errorMsg = ref('')
const toastMsg = ref('')
let toastTimer = null

function showToast(msg) {
  toastMsg.value = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMsg.value = '' }, 2500)
}

async function loadPapers() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await api.get('/api/papers')
    papers.value = res.data.papers || []
  } catch (e) {
    errorMsg.value = 'Failed to load papers'
    console.error('Failed to load papers', e)
  } finally {
    loading.value = false
  }
}

function openPaper(paper) {
  store.currentPaperId = null
  router.push({ name: 'editor', params: { paperId: paper.id } })
}

async function copyPaper(paper) {
  copying.value = paper.id
  try {
    const res = await api.get(`/api/papers/${paper.id}`)
    const data = { ...res.data }
    // Find next available copy number
    const base = (data.title || 'Untitled').replace(/ \(Copy(?: \d+)?\)$/, '')
    const existing = papers.value.filter(p => p.title?.startsWith(base + ' (Copy'))
    const copyNum = existing.length + 1
    data.title = base + (copyNum > 1 ? ` (Copy ${copyNum})` : ' (Copy)')
    delete data.id
    await api.post('/api/papers', data)
    await loadPapers()
    showToast('Paper copied')
  } catch (e) {
    showToast('Copy failed — try again')
    console.error('Copy failed', e)
  } finally {
    copying.value = null
  }
}

function confirmDelete(paper) {
  deleteTarget.value = paper
}

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await api.delete(`/api/papers/${deleteTarget.value.id}`)
    papers.value = papers.value.filter(p => p.id !== deleteTarget.value.id)
    showToast('Paper deleted')
  } catch (e) {
    showToast('Delete failed — try again')
    console.error('Delete failed', e)
  } finally {
    deleteTarget.value = null
  }
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  if (diff < 86400000 * 7) return `${Math.floor(diff / 86400000)}d ago`
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

onMounted(loadPapers)

onUnmounted(() => {
  clearTimeout(toastTimer)
})
</script>
