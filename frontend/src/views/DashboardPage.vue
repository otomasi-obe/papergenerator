<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850 transition-colors">
    <AppHeader />

    <main class="px-4 lg:px-8 py-8">
      <!-- Header -->
      <div class="flex items-center justify-between mb-8">
        <div>
          <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">My Papers</h1>
          <p class="text-ink-700 dark:text-ink-300 text-sm mt-1">{{ papers.length }} paper{{ papers.length === 1 ? '' : 's' }}</p>
        </div>
        <router-link to="/editor"
          class="flex items-center gap-2 px-5 py-2.5 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-xl font-medium transition-colors shadow-sm">
          + New Paper
        </router-link>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-20 text-ink-600 dark:text-ink-300">
        <div class="text-3xl mb-3 animate-spin">⚙️</div>
        Loading your papers...
      </div>

      <!-- Empty State -->
      <div v-else-if="papers.length === 0" class="text-center py-20">
        <div class="text-6xl mb-4">📄</div>
        <h2 class="text-xl font-semibold text-ink-900 dark:text-ink-50 mb-2">No papers yet</h2>
        <p class="text-ink-700 dark:text-ink-300 mb-6">Create your first paper with AI assistance</p>
        <router-link to="/editor" class="px-6 py-3 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-xl font-medium transition-colors">
          Create First Paper
        </router-link>
      </div>

      <!-- Paper Grid -->
      <div v-else class="grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <div v-for="paper in papers" :key="paper.id"
          @click="openPaper(paper)"
          class="bg-cream-50 dark:bg-ash-800 rounded-2xl border border-cream-300 dark:border-ash-700 shadow-sm hover:shadow-md transition-all overflow-hidden group cursor-pointer hover:border-brown-500 dark:hover:border-cream-400">

          <!-- Card Body (clickable) -->
          <div class="p-5 pb-3">
            <h3 class="font-semibold text-ink-900 dark:text-ink-50 text-sm leading-snug line-clamp-3 mb-2 group-hover:text-brown-700 dark:group-hover:text-cream-200 transition-colors">
              {{ paper.title || 'Untitled Paper' }}
            </h3>
            <p class="text-xs text-ink-600 dark:text-ink-300">
              Updated {{ formatDate(paper.updated_at) }}
            </p>
          </div>

          <!-- Stats row -->
          <div class="flex items-center gap-3 px-5 pb-3 text-xs text-ink-600 dark:text-ink-300">
            <span class="flex items-center gap-1">🖼️ {{ paper.image_count || 0 }} image{{ paper.image_count === 1 ? '' : 's' }}</span>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-1 px-4 pb-4" @click.stop>
            <button @click="openPaper(paper)"
              class="flex-1 px-3 py-1.5 bg-brown-700 hover:bg-brown-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 text-xs rounded-lg transition-colors font-medium">
              Open
            </button>
            <button @click="copyPaper(paper)" :disabled="copying === paper.id"
              class="px-3 py-1.5 bg-cream-200 hover:bg-cream-300 dark:bg-ash-700 dark:hover:bg-ash-600 text-ink-900 dark:text-ink-50 text-xs rounded-lg transition-colors disabled:opacity-50"
              title="Copy paper">
              {{ copying === paper.id ? '...' : 'Copy' }}
            </button>
            <button @click="confirmDelete(paper)"
              class="px-3 py-1.5 bg-red-50 hover:bg-red-100 dark:bg-red-900/30 dark:hover:bg-red-900/50 text-red-700 dark:text-red-400 text-xs rounded-lg transition-colors"
              title="Delete paper">
              Delete
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- Delete Confirm Modal -->
    <div v-if="deleteTarget" class="fixed inset-0 bg-ash-900/60 dark:bg-ash-900/80 flex items-center justify-center z-50 p-4" @click.self="deleteTarget = null">
      <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl shadow-xl p-6 max-w-sm w-full border border-cream-300 dark:border-ash-700">
        <div class="text-2xl mb-3">🗑️</div>
        <h3 class="font-semibold text-ink-900 dark:text-ink-50 mb-2">Delete Paper?</h3>
        <p class="text-ink-700 dark:text-ink-200 text-sm mb-5">
          "<strong>{{ deleteTarget.title || 'Untitled Paper' }}</strong>" and all its images will be permanently deleted.
        </p>
        <div class="flex gap-3">
          <button @click="deleteTarget = null"
            class="flex-1 px-4 py-2.5 border border-cream-400 dark:border-ash-600 hover:bg-cream-100 dark:hover:bg-ash-700 text-ink-900 dark:text-ink-50 rounded-xl text-sm font-medium transition-colors">
            Cancel
          </button>
          <button @click="doDelete()"
            class="flex-1 px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm font-medium transition-colors">
            Delete
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api/index.js'
import AppHeader from '../components/AppHeader.vue'
import { usePaperStore } from '../stores/paper.js'

const router = useRouter()
const store = usePaperStore()

const papers = ref([])
const loading = ref(true)
const deleteTarget = ref(null)
const copying = ref(null)

async function loadPapers() {
  loading.value = true
  try {
    const res = await api.get('/api/papers')
    papers.value = res.data.papers || []
  } catch (e) {
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
  } catch (e) {
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
  } catch (e) {
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
</script>
