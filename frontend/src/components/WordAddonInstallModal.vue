<template>
 <Teleport to="body">
 <Transition name="addon-modal">
 <div
 v-if="show"
 class="fixed inset-0 z-50 grid place-items-center p-4 bg-black/50 dark:bg-black/60"
 @click.self="emit('close')"
 >
 <section
 ref="panelRef"
 class="relative w-full max-w-2xl bg-cream-50 dark:bg-ash-850 border border-cream-300 dark:border-ash-700 rounded-2xl shadow-2xl outline-none"
 role="dialog"
 aria-modal="true"
 aria-label="Install VIOLA AI Assistant for Word"
 tabindex="-1"
 @keydown="onKeydown"
 >
 <!-- Header -->
 <header class="flex items-center justify-between px-6 pt-5 pb-3 border-b border-cream-300 dark:border-ash-700">
 <h2 class="text-lg font-semibold text-ink-900 dark:text-ink-50">
 Install VIOLA AI Assistant for Word
 </h2>
 <button
 type="button"
 class="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg text-ink-500 dark:text-ink-300 hover:bg-cream-200 dark:hover:bg-ash-700 hover:text-ink-900 dark:hover:text-ink-50 transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
 aria-label="Tutup dialog"
 @click="emit('close')"
 >
 <span class="text-2xl leading-none" aria-hidden="true">&times;</span>
 </button>
 </header>

 <!-- Tab selector -->
 <div class="flex border-b border-cream-300 dark:border-ash-700 px-6" role="tablist">
 <button
 v-for="tab in tabs"
 :key="tab.key"
 role="tab"
 :aria-selected="activeTab === tab.key"
 :class="[
 'min-h-[44px] px-4 text-sm font-medium transition focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2',
 activeTab === tab.key
 ? 'text-navy-700 dark:text-cream-200 border-b-2 border-navy-600 dark:border-cream-400'
 : 'text-ink-500 dark:text-ink-300 hover:text-ink-700 dark:hover:text-ink-200 border-b-2 border-transparent'
 ]"
 @click="activeTab = tab.key"
 >
 {{ tab.label }}
 </button>
 </div>

 <!-- Body -->
 <div class="px-6 py-5 space-y-5">
 <!-- Desktop tab -->
 <template v-if="activeTab === 'desktop'">
 <p class="text-sm text-ink-700 dark:text-ink-300">
 Ikuti langkah-langkah berikut untuk memasang VIOLA AI di Microsoft Word Desktop.
 </p>

 <a
 :href="downloadUrl"
 class="inline-flex items-center gap-2 px-5 py-2.5 min-h-[44px] rounded-xl bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 text-sm font-medium transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
 download
 >
 <span aria-hidden="true">📥</span>
 Download Manifest File
 </a>

 <ol class="space-y-3 text-sm text-ink-700 dark:text-ink-300 list-decimal list-inside marker:font-semibold marker:text-navy-600 dark:marker:text-cream-400">
 <li>Buka Microsoft Word (aplikasi Desktop)</li>
 <li>
 Masuk ke tab
 <strong class="text-ink-900 dark:text-ink-50">Insert</strong>
 &rarr;
 <strong class="text-ink-900 dark:text-ink-50">Get Add-ins</strong>
 &rarr;
 <strong class="text-ink-900 dark:text-ink-50">My Add-ins</strong>
 </li>
 <li>
 Klik
 <strong class="text-ink-900 dark:text-ink-50">Upload My Add-in</strong>
 di bagian bawah
 </li>
 <li>Pilih file <strong class="text-ink-900 dark:text-ink-50">VIOLA-AI-Assistant.xml</strong> yang sudah diunduh</li>
 <li>Klik <strong class="text-ink-900 dark:text-ink-50">OK</strong> untuk memasang</li>
 </ol>

 <div class="text-xs text-ink-500 dark:text-ink-300 bg-cream-100 dark:bg-ash-800 rounded-xl px-4 py-3">
 Add-in akan muncul di ribbon tab
 <strong class="text-ink-700 dark:text-ink-200">Home</strong>.
 </div>
 </template>

 <!-- Online tab -->
 <template v-if="activeTab === 'online'">
 <p class="text-sm text-ink-700 dark:text-ink-300">
 Gunakan VIOLA AI langsung di Word Online (tanpa perlu mengunduh).
 </p>

 <button
 type="button"
 class="inline-flex items-center gap-2 px-5 py-2.5 min-h-[44px] rounded-xl bg-navy-700 hover:bg-navy-800 dark:bg-cream-200 dark:hover:bg-cream-100 text-cream-50 dark:text-ash-900 text-sm font-medium transition active:scale-95 focus-visible:ring-2 focus-visible:ring-[#238f7f] focus-visible:ring-offset-2"
 @click="openWordOnline"
 >
 <span aria-hidden="true">🌐</span>
 Open in Word Online
 </button>

 <div class="text-xs text-ink-500 dark:text-ink-300 bg-cream-100 dark:bg-ash-800 rounded-xl px-4 py-3">
 Anda akan diminta masuk dengan akun Microsoft Anda.
 </div>
 </template>
 </div>
 </section>
 </div>
 </Transition>
 </Teleport>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, watch, nextTick } from 'vue'

defineOptions({ inheritAttrs: false })

interface Props {
 show: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
 close: []
}>()

const panelRef = ref<HTMLElement | null>(null)
const previouslyFocused = ref<HTMLElement | null>(null)

type TabKey = 'desktop' | 'online'

interface Tab {
 key: TabKey
 label: string
}

const tabs: Tab[] = [
 { key: 'desktop', label: 'Desktop' },
 { key: 'online', label: 'Online' },
]

const activeTab = ref<TabKey>('desktop')

const downloadUrl = '/api/word-addon/download-manifest'

const manifestUrl = `${window.location.origin}/api/word-addon/manifest.xml`

const wordOnlineUrl = `https://www.office.com/launch/word?auth=2&wdManifestUrl=${encodeURIComponent(manifestUrl)}`

function openWordOnline(): void {
 window.open(wordOnlineUrl, '_blank')
}

function onKeydown(event: KeyboardEvent): void {
 if (event.key === 'Escape') {
 emit('close')
 return
 }
 if (event.key !== 'Tab') return

 const focusable = getFocusable()
 if (!focusable.length) return

 const currentIndex = focusable.indexOf(document.activeElement as HTMLElement)
 if (event.shiftKey) {
 if (currentIndex <= 0) {
 event.preventDefault()
 focusable[focusable.length - 1].focus()
 }
 } else {
 if (currentIndex === focusable.length - 1) {
 event.preventDefault()
 focusable[0].focus()
 }
 }
}

const focusableSelectors = [
 'a[href]',
 'button:not([disabled])',
 'textarea:not([disabled])',
 'input:not([disabled])',
 'select:not([disabled])',
 '[tabindex]:not([tabindex="-1"])',
].join(',')

function getFocusable(): HTMLElement[] {
 return Array.from(panelRef.value?.querySelectorAll(focusableSelectors) || [])
 .filter((el): el is HTMLElement =>
 !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true'
 )
}

function focusFirst(): void {
 const first = getFocusable()[0]
 if (first) first.focus()
 else panelRef.value?.focus()
}

function restoreFocus(): void {
 previouslyFocused.value?.focus?.()
 previouslyFocused.value = null
}

watch(() => props.show, async (isOpen) => {
 if (isOpen) {
 activeTab.value = 'desktop'
 previouslyFocused.value = document.activeElement as HTMLElement
 await nextTick()
 focusFirst()
 } else {
 restoreFocus()
 }
})

onBeforeUnmount(() => {
 if (props.show) restoreFocus()
})
</script>

<style scoped>
.addon-modal-enter-active,
.addon-modal-leave-active {
 transition: opacity 0.2s ease;
}
.addon-modal-enter-active section,
.addon-modal-leave-active section {
 transition: transform 0.2s ease, opacity 0.2s ease;
}
.addon-modal-enter-from,
.addon-modal-leave-to {
 opacity: 0;
}
.addon-modal-enter-from section,
.addon-modal-leave-to section {
 opacity: 0;
 transform: scale(0.96) translateY(8px);
}
</style>
