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
            @click="store.acceptProposal(change.id)"
            class="px-2 py-0.5 text-[10px] font-semibold rounded-md bg-emerald-600 hover:bg-emerald-700 text-white"
            title="Accept this change"
          >✓ Terima</button>
          <button
            @click="store.rejectProposal(change.id)"
            class="px-2 py-0.5 text-[10px] font-semibold rounded-md bg-slate-100 hover:bg-rose-100 text-slate-600 hover:text-rose-700 border border-slate-200"
            title="Reject this change"
          >✕ Tolak</button>
        </div>
      </div>
      <slot name="after" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  change: { type: Object, required: true },
  store: { type: Object, required: true },
  align: { type: String, default: '' },
})
</script>
