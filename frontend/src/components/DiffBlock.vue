<template>
  <div :class="['my-2 group/diff relative rounded-lg overflow-hidden', align === 'center' ? 'text-center' : '']">
    <details class="bg-rose-50/60 border-l-4 border-rose-300 px-3 py-2 text-slate-700">
      <summary class="text-[10px] uppercase tracking-wide text-rose-600 font-semibold cursor-pointer">− Removed / Sebelum · Show original</summary>
      <div class="mt-1">
        <slot name="before" />
      </div>
    </details>
    <div class="bg-emerald-50/60 border-l-4 border-emerald-400 px-3 py-2 mt-0.5">
      <div class="flex items-center justify-between mb-1 gap-2">
        <span class="text-[10px] uppercase tracking-wide text-emerald-700 font-semibold">+ Added / Sesudah</span>
        <div class="flex items-center gap-1.5 shrink-0">
          <button
            @click="handleAccept"
            :disabled="processing"
            class="px-2 py-0.5 text-[10px] font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
            title="Accept this change"
            aria-label="Accept change"
          >✓ Terima</button>
          <button
            @click="handleReject"
            :disabled="processing"
            class="px-2 py-0.5 text-[10px] font-semibold rounded-md bg-slate-100 hover:bg-rose-100 text-slate-600 hover:text-rose-700 border border-slate-200 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
            title="Reject this change"
            aria-label="Reject change"
          >✕ Tolak</button>
        </div>
      </div>
      <slot name="after" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  change: { type: Object, required: true },
  store: { type: Object, required: true },
  align: { type: String, default: '' },
})

const processing = ref(false)

async function handleAccept() {
  if (processing.value) return
  processing.value = true
  try {
    await props.store.acceptProposal(props.change.id)
  } finally {
    processing.value = false
  }
}

async function handleReject() {
  if (processing.value) return
  processing.value = true
  try {
    await props.store.rejectProposal(props.change.id)
  } finally {
    processing.value = false
  }
}
</script>
