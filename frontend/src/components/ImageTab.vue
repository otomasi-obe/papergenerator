<template>
  <div class="bg-white dark:bg-anthracite-700 rounded-2xl border border-ivory-300 dark:border-anthracite-500 shadow-sm p-6">
 <div class="flex items-center justify-between mb-4 max-w-5xl mx-auto">
 <div>
 <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50 flex items-center gap-2">
 <svg class="w-5 h-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3-3.086a1 1 0 0 0-1.414 0L9 18"/></svg>
 Images
 </h2>
 <p class="text-xs text-ink-600 dark:text-ink-300 mt-0.5">
 Generate gambar dengan AI, upload gambar, dan kelola semua gambar paper di satu tempat.
 </p>
 </div>
 <div class="flex items-center gap-2">
 <!-- Upload button -->
 <input ref="uploadInput" type="file" accept="image/*" multiple class="hidden" @change="onUploadChange" />
 <button @click="uploadInput?.click()" :disabled="!store.currentPaperId"
 class="px-3 py-1.5 bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-xs font-medium disabled:opacity-50 transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
 ＋ Upload Gambar
 </button>
 <!-- Refresh -->
 <button @click="refreshImages"
 class="px-3 py-1.5 text-ink-700 dark:text-ink-200 hover:bg-cream-200 dark:hover:bg-ash-700 rounded-lg text-xs font-medium transition focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
 ↻ Refresh
 </button>
 </div>
 </div>

 <p v-if="warning" class="max-w-5xl mx-auto mb-3 text-xs text-amber-700 dark:text-amber-300">{{ warning }}</p>

 <!-- Generate section -->
   <div class="max-w-5xl mx-auto mb-4 bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden">
   <div class="px-4 py-2.5 border-b border-cream-300 dark:border-ash-700 bg-cream-100 dark:bg-ash-850 flex items-center gap-2">
   <svg class="w-5 h-5 text-navy-700 dark:text-cream-200 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/></svg>
   <span class="text-xs font-semibold text-ink-700 dark:text-ink-200">Generate Image dengan AI</span>
   </div>
   <div class="p-4 flex gap-3">
   <textarea v-model="genPrompt" rows="2" placeholder="Deskripsikan gambar yang ingin dibuat… (contoh: diagram arsitektur IoT 3 layer, clean professional style)"
   class="flex-1 px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm outline-none focus:border-navy-400 resize-none"
   @keydown.ctrl.enter="generateImage"
   ></textarea>
   <button @click="generateImage" :disabled="!genPrompt.trim() || generating"
   class="px-4 py-2 bg-navy-600 hover:bg-navy-700 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 rounded-lg text-sm font-medium disabled:opacity-50 active:scale-95 whitespace-nowrap flex items-center gap-1.5 focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">
   <span v-if="generating" class="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
   {{ generating ? 'Generating…' : 'Generate' }}
   </button>
   </div>
   </div>

 <!-- Main layout: list (left) + preview (right) -->
 <div class="max-w-5xl mx-auto grid lg:grid-cols-[280px,1fr] gap-4">
 <!-- Image list (left) -->
 <aside class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden">
 <div class="px-3 py-2 border-b border-cream-300 dark:border-ash-700 text-xs font-semibold text-ink-700 dark:text-ink-200 bg-cream-100 dark:bg-ash-850">
 {{ images.length }} image{{ images.length === 1 ? '' : 's' }}
 </div>
 <div v-if="loading" class="px-3 py-6 text-center text-xs text-ink-500 dark:text-ink-300">Loading…</div>
 <div v-else-if="!images.length" class="px-3 py-12 text-center text-xs text-ink-500 dark:text-ink-300">
 Belum ada gambar.<br/>Generate atau upload di atas.
 </div>
 <ul v-else class="divide-y divide-cream-200 dark:divide-ash-700 max-h-[60vh] overflow-y-auto">
 <li
 v-for="img in images"
 :key="img.id"
 :class="[
 'group px-3 py-2 cursor-pointer flex items-start gap-2 transition',
 activeImageId === img.id ? 'bg-cream-200 dark:bg-ash-700' : 'hover:bg-cream-100 dark:hover:bg-ash-700',
 ]"
 @click="selectImage(img)"
 >
 <div class="w-10 h-10 rounded border border-cream-300 dark:border-ash-600 bg-cream-100 dark:bg-ash-700 flex-shrink-0 overflow-hidden flex items-center justify-center">
 <img v-if="!failedImages.has(img.filename)" :src="imageUrl(img)" :alt="img.original_name || img.filename" class="max-h-full max-w-full object-contain" @error="(e) => onThumbErr(e, img.filename)" />
 <div v-else class="text-[10px] text-ink-400">⚠️</div>
 </div>
 <div class="min-w-0 flex-1">
 <!-- Editable name -->
 <input
 :value="displayName(img)"
 @click.stop
 @change="renameImage(img, ($event.target as HTMLInputElement).value)"
 class="w-full text-xs bg-transparent border-0 border-b border-transparent hover:border-cream-400 dark:hover:border-ash-500 focus:border-navy-400 dark:focus:border-cream-300 text-ink-700 dark:text-ink-100 font-medium outline-none truncate px-0 py-0"
 :title="img.original_name || img.filename"
 />
 <div class="text-[10px] text-ink-500 dark:text-ink-300 mt-0.5">
 {{ formatDate(img.created_at) }}
 </div>
 </div>
 <button
 @click.stop="removeImage(img)"
 class="opacity-0 group-hover:opacity-100 text-ink-400 dark:text-ink-300 hover:text-rose-500 text-xs px-1"
 title="Hapus"
 >🗑</button>
 </li>
 </ul>
 </aside>

 <!-- Preview pane (right) -->
 <section class="bg-cream-50 dark:bg-ash-800 border border-cream-300 dark:border-ash-700 rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[60vh]">
 <header v-if="activeImage" class="px-4 py-2.5 border-b border-cream-300 dark:border-ash-700 flex items-center justify-between">
 <div class="min-w-0 flex-1">
 <input
 :value="displayName(activeImage)"
 @change="renameImage(activeImage, ($event.target as HTMLInputElement).value)"
 class="w-full text-sm font-semibold bg-transparent border-0 border-b border-transparent hover:border-cream-400 dark:hover:border-ash-500 focus:border-navy-400 dark:focus:border-cream-300 text-ink-900 dark:text-ink-50 outline-none truncate px-0 py-0"
 />
 </div>
 <div class="flex items-center gap-2 ml-2">
 <a :href="imageUrl(activeImage)" download
 class="text-xs text-ink-700 dark:text-ink-100 hover:text-ink-900 dark:hover:text-ink-50 font-medium px-2 py-1 rounded hover:bg-cream-200 dark:hover:bg-ash-700">
 Download ↓
 </a>
 </div>
 </header>

 <div v-if="!activeImage" class="flex-1 flex items-center justify-center text-xs text-ink-500 dark:text-ink-300">
 Pilih gambar di kiri untuk melihat preview.
 </div>

 <div v-else class="flex-1 overflow-y-auto bg-cream-100/40 dark:bg-ash-850 flex items-center justify-center p-4">
 <img :src="imageUrl(activeImage)" :alt="displayName(activeImage)" class="max-w-full max-h-[55vh] object-contain rounded-lg shadow-sm" @error="(e) => onThumbErr(e, activeImage.filename)" />
 </div>
 </section>
 </div>

 <AppDialog v-if="deleteTarget" :open="!!deleteTarget" title="Hapus gambar?" @close="deleteTarget = null">
 <p class="text-sm text-ink-700 dark:text-ink-200">Hapus "{{ displayName(deleteTarget) }}"?</p>
 <template #actions>
 <button @click="deleteTarget = null" class="px-3 py-1.5 text-xs rounded border border-cream-300 dark:border-ash-700 text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-ash-700">Cancel</button>
 <button @click="confirmRemoveImage" class="px-3 py-1.5 text-xs rounded bg-rose-600 hover:bg-rose-700 text-white">Delete</button>
 </template>
 </AppDialog>
 </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { usePaperStore } from '../stores/paper'
import { useImageGenStore } from '../stores/imageGen'
import { useUserStateStore } from '../stores/userState'
import api from '../api/index'
import AppDialog from './AppDialog.vue'

interface ImageItem {
 id: number
 filename: string
 original_name?: string
 url: string
 created_at: string
}

const store = usePaperStore()
const imageGen = useImageGenStore()
const userState = useUserStateStore()

const images = ref<ImageItem[]>([])
const loading = ref(false)
const generating = ref(false)
const warning = ref('')
const failedImages = ref(new Set<string>())

watch(() => store.currentPaperId, () => {
 failedImages.value = new Set()
})

// Persisted state via userState store (per-paper)
const genPrompt = computed({
 get: () => userState.get('image.gen_prompt', store.currentPaperId, ''),
 set: (val) => userState.set('image.gen_prompt', store.currentPaperId, val),
})

const uploadInput = ref<HTMLInputElement | null>(null)
const activeImageId = computed({
 get: () => userState.get('image.active_id', store.currentPaperId, null),
 set: (val) => userState.set('image.active_id', store.currentPaperId, val),
})
const deleteTarget = ref<ImageItem | null>(null)

const activeImage = computed(() => images.value.find(i => i.id === activeImageId.value))

async function loadImages(): Promise<void> {
 if (!store.currentPaperId) return
 loading.value = true
 try {
 const res = await api.get(`/api/papers/${store.currentPaperId}/images`)
 images.value = res.data.images || []
 // Sync with paper store's paperImages for gallery/figureSources
 if (store.currentPaperId) {
 store.loadPaperImages(store.currentPaperId)
 }
 if (images.value.length && !activeImageId.value) {
 selectImage(images.value[images.value.length - 1])
 }
 } catch (e: any) {
 warning.value = e.message
 } finally {
 loading.value = false
 }
}

watch(() => store.currentPaperId, () => {
 images.value = []
 activeImageId.value = null
 loadImages()
})

onMounted(loadImages)

function selectImage(img: ImageItem): void {
 activeImageId.value = img.id
}

function displayName(img: ImageItem): string {
 return img.original_name || img.filename || `Image #${img.id}`
}

function imageUrl(img: ImageItem): string {
 if (img.url) return img.url
 const pid = store.currentPaperId
 if (!pid || !img.filename) return ''
 return `/api/images/${pid}/${encodeURIComponent(img.filename)}`
}

function onThumbErr(_e: Event, filename: string): void {
 if (filename) failedImages.value.add(filename)
}

async function renameImage(img: ImageItem, newName: string): Promise<void> {
 if (!newName.trim() || !store.currentPaperId) return
 // Update local display
 img.original_name = newName.trim()
 // Persist via API if backend supports it; for now just update local
 // TODO: add PATCH /api/papers/:pid/images/:id endpoint for rename
}

async function generateImage(): Promise<void> {
 if (!store.currentPaperId) {
 store.showToast('Simpan paper dulu sebelum generate gambar.', 'error')
 return
 }
 const p = genPrompt.value.trim()
 if (!p) return
 generating.value = true
 try {
 const paperId = store.currentPaperId
 await imageGen.enqueue({
 paperId,
 prompt: p,
 onDone: async () => {
 generating.value = false
 genPrompt.value = ''
 await loadImages()
 // Select the newest image
 if (images.value.length) {
 selectImage(images.value[images.value.length - 1])
 }
 },
 onError: (err: any) => {
 store.showToast('Image error: ' + (err || err?.message || 'unknown'), 'error')
 generating.value = false
 },
 })
 } catch (e: any) {
 store.showToast('Image error: ' + (e?.message || e), 'error')
 generating.value = false
 }
}

async function onUploadChange(e: Event): Promise<void> {
 const target = e.target as HTMLInputElement
 const list = Array.from(target.files || [])
 target.value = ''
 if (!list.length || !store.currentPaperId) return

 for (const file of list) {
 try {
 const fd = new FormData()
 fd.append('file', file)
 await api.post(`/api/papers/${store.currentPaperId}/images/upload`, fd, {
 headers: { 'Content-Type': 'multipart/form-data' },
 })
 } catch (err: any) {
 warning.value = 'Upload gagal: ' + (err.response?.data?.error || err.message)
 }
 }
 await loadImages()
 // Select the newest image
 if (images.value.length) {
 selectImage(images.value[images.value.length - 1])
 }
}

function removeImage(img: ImageItem): void {
 deleteTarget.value = img
}

async function confirmRemoveImage(): Promise<void> {
 const img = deleteTarget.value
 if (!img || !store.currentPaperId) return
 try {
 await api.delete(`/api/papers/${store.currentPaperId}/images/${img.id}`)
 images.value = images.value.filter(i => i.id !== img.id)
 if (activeImageId.value === img.id) {
 activeImageId.value = images.value[0]?.id || null
 }
 } catch (e: any) {
 warning.value = 'Hapus gagal: ' + (e.response?.data?.error || e.message)
 } finally {
 deleteTarget.value = null
 }
}

function refreshImages(): void {
  loadImages()
}

function formatDate(s: string): string {
 if (!s) return ''
 const d = new Date(s)
 const diff = Date.now() - d.getTime()
 if (diff < 60000) return 'baru saja'
 if (diff < 3600000) return Math.floor(diff / 60000) + 'm lalu'
 if (diff < 86400000) return Math.floor(diff / 3600000) + 'j lalu'
 if (diff < 7 * 86400000) return Math.floor(diff / 86400000) + 'h lalu'
 return d.toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}
</script>
