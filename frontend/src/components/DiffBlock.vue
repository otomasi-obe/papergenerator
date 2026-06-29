<template>
 <div :class="['my-2 group/diff relative rounded-lg overflow-hidden', align === 'center' ? 'text-center' : '']">
 <details class="bg-rose-50/60 dark:bg-rose-950/40 border-l-4 border-rose-300 dark:border-rose-600 px-3 py-2 text-ink-700 dark:text-rose-200">
 <summary class="text-[10px] uppercase tracking-wide text-rose-600 dark:text-rose-400 font-semibold cursor-pointer focus-visible:ring-2 focus-visible:ring-[#238f7f]/30">− Removed / Sebelum · Show original</summary>
 <div class="mt-1">
 <slot name="before" />
 </div>
 </details>
 <div class="bg-emerald-50/60 dark:bg-emerald-950/40 border-l-4 border-emerald-400 dark:border-emerald-600 px-3 py-2 mt-0.5">
 <div class="flex items-center justify-between mb-1 gap-2">
 <span class="text-[10px] uppercase tracking-wide text-emerald-700 dark:text-emerald-400 font-semibold">+ Added / Sesudah</span>
 <div class="flex items-center gap-1.5 shrink-0">
 <button
 @click="handleAccept"
 :disabled="processing"
 class="px-2 py-0.5 min-h-[44px] min-w-[44px] text-[10px] font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50 disabled:cursor-not-allowed transition focus-visible:ring-2 focus-visible:ring-[#238f7f]/30 active:scale-95 "
 title="Accept this change"
 aria-label="Accept change"
 >✓ Terima</button>
 <button
 @click="handleReject"
 :disabled="processing"
 class="px-2 py-0.5 min-h-[44px] min-w-[44px] text-[10px] font-semibold rounded-md bg-cream-100 dark:bg-ash-700 hover:bg-rose-100 dark:hover:bg-rose-900/50 text-ink-600 dark:text-ash-200 hover:text-rose-700 dark:hover:text-rose-300 border border-cream-300 dark:border-ash-600 disabled:opacity-50 disabled:cursor-not-allowed transition focus-visible:ring-2 focus-visible:ring-[#238f7f]/30 active:scale-95 "
 title="Reject this change"
 aria-label="Reject change"
 >✕ Tolak</button>
 </div>
 </div>
 <slot name="after" />
 </div>
 </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { DiffBlockProps } from '../types/components'

const props = defineProps<DiffBlockProps>()

const processing = ref<boolean>(false)

async function handleAccept(): Promise<void> {
 if (processing.value) return
 processing.value = true
 try {
 await props.store.acceptProposal(props.change.id)
 } finally {
 processing.value = false
 }
}

async function handleReject(): Promise<void> {
 if (processing.value) return
 processing.value = true
 try {
 await props.store.rejectProposal(props.change.id)
 } finally {
 processing.value = false
 }
}
</script>
