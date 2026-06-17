<template>
  <div class="min-h-screen bg-cream-50 dark:bg-ash-850">
    <AppHeader />

    <main class="max-w-5xl mx-auto px-4 py-8">
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-2xl font-bold text-ink-900 dark:text-ink-50">File Manager</h1>
          <p class="text-ink-600 dark:text-ink-300 text-sm mt-1">Manage images for each paper</p>
        </div>
        <router-link to="/dashboard" class="text-sm text-ink-600 dark:text-ink-50 hover:text-ink-900 flex items-center gap-1">
          ← Back to Papers
        </router-link>
      </div>

      <!-- Paper selector if no paperId in route -->
      <div v-if="!currentPaperId" class="mb-6">
        <label class="block text-sm font-medium text-ink-700 dark:text-ink-200 mb-2">Select Paper</label>
        <select v-model="selectedPaperId" @change="onSelectPaper"
          class="w-full max-w-md px-3 py-2 border border-cream-300 dark:border-ash-700 rounded-xl text-sm bg-cream-50 dark:bg-ash-800 focus:ring-2 focus:ring-[var(--focus-ring)]/30 outline-none">
          <option value="">— Select a paper —</option>
          <option v-for="p in papers" :key="p.id" :value="p.id">{{ p.title }}</option>
        </select>
      </div>

      <!-- Breadcrumb for specific paper -->
      <div v-if="currentPaperId && paperTitle" class="mb-6 flex items-center gap-2">
        <router-link to="/files" class="text-sm text-[var(--accent)] hover:underline">All Papers</router-link>
        <span class="text-ink-500 dark:text-ink-300">/</span>
        <span class="text-sm font-medium text-ink-900 dark:text-ink-50">{{ paperTitle }}</span>
        <router-link :to="`/editor/${currentPaperId}`" class="ml-2 text-xs text-[var(--accent)] hover:underline">
          Edit Paper →
        </router-link>
      </div>

      <div v-if="!effectivePaperId" class="text-center py-20 text-ink-500 dark:text-ink-300">
        <div class="text-4xl mb-3">🗂️</div>
        <p>Select a paper to manage its images</p>
      </div>

      <div v-else>
        <!-- Upload Zone -->
        <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6 mb-6">
          <h2 class="font-semibold text-ink-700 dark:text-ink-200 mb-4">Upload Images</h2>
          <div
            class="border-2 border-dashed border-cream-300 dark:border-ash-700 rounded-xl p-8 text-center hover:border-[var(--accent)] cursor-pointer transition-colors"
            @click="triggerUpload"
            @dragover.prevent @drop.prevent="handleDrop"
          >
            <input ref="fileInput" type="file" accept="image/*" multiple @change="handleFileSelect" class="hidden" />
            <div v-if="uploading" class="text-[var(--accent)]">
              <div class="w-8 h-8 border-4 border-[var(--accent)]/30 border-t-[var(--accent)] rounded-full animate-spin mx-auto mb-2"></div>
              Uploading...
            </div>
            <div v-else>
              <div class="text-4xl mb-2">📁</div>
              <p class="text-ink-600 dark:text-ink-300 text-sm">Click or drag images here to upload</p>
              <p class="text-ink-500 dark:text-ink-300 text-xs mt-1">PNG, JPG, SVG, WebP supported</p>
            </div>
          </div>
        </div>

        <!-- Images Grid -->
        <div class="bg-cream-50 dark:bg-ash-800 rounded-2xl border shadow-sm p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="font-semibold text-ink-700 dark:text-ink-200">Images ({{ images.length }})</h2>
          </div>

          <div v-if="images.length === 0" class="text-center py-12 text-ink-500 dark:text-ink-300">
            <div class="text-4xl mb-3">🖼️</div>
            <p>No images uploaded for this paper yet</p>
          </div>

          <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            <div v-for="img in images" :key="img.id"
              class="group relative rounded-xl overflow-hidden border bg-cream-50 dark:bg-ash-850 aspect-square">
              <img :src="resolveUrl(img.url)" :alt="img.original_name"
                class="w-full h-full object-cover" />
              <!-- Overlay -->
              <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center p-2">
                <p class="text-white text-xs text-center truncate w-full mb-2">{{ img.original_name }}</p>
                <button @click="copyUrl(img)" class="text-xs bg-cream-50 dark:bg-ash-800/20 hover:bg-cream-50 dark:bg-ash-800/30 text-white rounded px-2 py-1 mb-1 w-full transition-colors">
                  📋 Copy URL
                </button>
                <button @click="confirmDelete(img)" class="text-xs bg-red-500/80 hover:bg-red-500 text-white rounded px-2 py-1 w-full transition-colors">
                  🗑 Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <AppDialog v-if="deleteTarget" :open="!!deleteTarget" title="Delete Image?" @close="deleteTarget = null">
      <p class="text-ink-600 dark:text-ink-300 text-sm">"{{ deleteTarget.original_name }}" will be permanently deleted.</p>
      <template #actions>
        <button @click="deleteTarget = null" class="px-4 py-2.5 border border-cream-300 dark:border-ash-700 hover:bg-cream-100 dark:hover:bg-ash-700 rounded-xl text-sm">Cancel</button>
        <button @click="doDelete()" class="px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl text-sm">Delete</button>
      </template>
    </AppDialog>

    <!-- Toast -->
    <Teleport to="body">
      <div v-if="toastMsg" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60]">
        <div class="px-4 py-2.5 rounded-lg shadow-lg text-white text-sm bg-green-600">{{ toastMsg }}</div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api/index.js'
import AppHeader from '../components/AppHeader.vue'
import AppDialog from '../components/AppDialog.vue'

const route = useRoute()
const router = useRouter()
const BASE = import.meta.env.VITE_API_URL || ''

const papers = ref([])
const selectedPaperId = ref('')
const images = ref([])
const uploading = ref(false)
const deleteTarget = ref(null)
const fileInput = ref(null)
const toastMsg = ref('')
const paperTitle = ref('')

const currentPaperId = computed(() => route.params.paperId || null)
const effectivePaperId = computed(() => currentPaperId.value || selectedPaperId.value)

function onSelectPaper() {
  if (!selectedPaperId.value) return
  router.push(`/files/${selectedPaperId.value}`)
}

function resolveUrl(url) {
  return url?.startsWith('http') ? url : `${BASE}${url}`
}

function showToast(msg) {
  toastMsg.value = msg
  setTimeout(() => { toastMsg.value = '' }, 2500)
}

async function loadPapers() {
  try {
    const res = await api.get('/api/papers')
    papers.value = res.data.papers || []
  } catch {}
}

async function loadImages() {
  const pid = effectivePaperId.value
  if (!pid) return
  try {
    const res = await api.get(`/api/papers/${pid}/images`)
    images.value = res.data.images || []
    if (currentPaperId.value) {
      const paper = papers.value.find(p => p.id === currentPaperId.value)
      paperTitle.value = paper?.title || 'Paper'
    }
  } catch {}
}

function triggerUpload() { fileInput.value?.click() }

async function handleFileSelect(e) {
  const files = Array.from(e.target.files || [])
  if (files.length) await uploadFiles(files)
  e.target.value = ''
}

async function handleDrop(e) {
  const files = Array.from(e.dataTransfer.files || []).filter(f => f.type.startsWith('image/'))
  if (files.length) await uploadFiles(files)
}

async function uploadFiles(files) {
  const pid = effectivePaperId.value
  if (!pid) return
  uploading.value = true
  for (const file of files) {
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await api.post(`/api/papers/${pid}/images`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      images.value.push(res.data.image)
    } catch (e) {
      console.error('Upload failed', e)
    }
  }
  uploading.value = false
  showToast(`${files.length} image(s) uploaded!`)
}

function confirmDelete(img) { deleteTarget.value = img }

async function doDelete() {
  if (!deleteTarget.value) return
  const pid = effectivePaperId.value
  try {
    await api.delete(`/api/papers/${pid}/images/${deleteTarget.value.id}`)
    images.value = images.value.filter(i => i.id !== deleteTarget.value.id)
    showToast('Image deleted')
  } catch {}
  deleteTarget.value = null
}

function copyUrl(img) {
  const url = resolveUrl(img.url)
  navigator.clipboard.writeText(url).then(() => showToast('URL copied!')).catch(() => {})
}

onMounted(async () => {
  await loadPapers()
  if (currentPaperId.value) {
    const paper = papers.value.find(p => p.id === currentPaperId.value)
    paperTitle.value = paper?.title || 'Paper'
    await loadImages()
  }
})

watch(effectivePaperId, async (pid, prev) => {
  if (!pid || pid === prev) return
  await loadImages()
})
</script>
