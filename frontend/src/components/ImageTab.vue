<template>
  <div class="space-y-4">
    <div class="flex items-center gap-2">
      <span class="text-lg">🖼</span>
      <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">Image</h2>
    </div>

    <p class="text-sm text-ink-600 dark:text-ink-300">
      Buat gambar untuk paper dari prompt deskriptif. Hasil akan ditampilkan di bawah dan bisa
      disisipkan ke section.
    </p>

    <div>
      <label class="block text-xs text-ink-600 dark:text-ink-300 mb-1">Prompt</label>
      <textarea
        v-model="prompt"
        rows="4"
        placeholder="Deskripsikan gambar yang ingin dibuat…"
        class="w-full px-3 py-2 border border-cream-300 dark:border-ash-600 bg-white dark:bg-ash-900 text-ink-900 dark:text-ink-50 rounded-lg text-sm"
      ></textarea>
    </div>

    <button
      @click="generate"
      :disabled="!prompt.trim() || generating"
      class="w-full px-4 py-2 bg-navy-600 hover:bg-navy-700 text-cream-50 dark:bg-cream-200 dark:hover:bg-cream-100 dark:text-ash-900 rounded-lg text-sm font-medium disabled:opacity-50 active:scale-95 transition-transform focus-visible:ring-2 focus-visible:ring-[#238f7f]/30"
    >
      {{ generating ? 'Membuat…' : 'Generate Image' }}
    </button>

    <div v-if="resultUrl" class="border border-cream-300 dark:border-ash-600 rounded-xl overflow-hidden">
      <div class="bg-cream-100 dark:bg-ash-850 px-3 py-2 text-xs font-semibold text-ink-700 dark:text-ink-100 border-b border-cream-300 dark:border-ash-600">
        Hasil
      </div>
      <img :src="resultUrl" alt="Generated image" class="max-w-full h-auto block" />
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref } from 'vue'
import { usePaperStore } from '../stores/paper'
import { useImageGenStore } from '../stores/imageGen'

const paperStore = usePaperStore()
const imageGen = useImageGenStore()
const prompt = ref('')
const generating = ref(false)
const resultUrl = ref('')

function resolveFilename(img: any): string {
  if (!img) return ''
  if (typeof img === 'string') return img
  return img.filename || img.image || ''
}

async function generate() {
  if (!paperStore.currentPaperId) {
    paperStore.showToast('Simpan paper dulu sebelum generate gambar.', 'error')
    return
  }
  const p = prompt.value.trim()
  if (!p) return
  generating.value = true
  try {
    const paperId = paperStore.currentPaperId
    await imageGen.enqueue({
      paperId,
      prompt: p,
      onDone: (img) => {
        const filename = resolveFilename(img)
        if (filename) resultUrl.value = `/api/images/${paperId}/${filename}`
        generating.value = false
      },
      onError: (err) => {
        paperStore.showToast('Image error: ' + err, 'error')
        generating.value = false
      },
    })
  } catch (e: any) {
    paperStore.showToast('Image error: ' + (e?.message || e), 'error')
    generating.value = false
  }
}
</script>
