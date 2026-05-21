<template>
  <div class="revisi-proposal rounded-lg border p-3 my-2
              bg-cream-50 dark:bg-ash-800
              border-cream-300 dark:border-ash-700">
    <div class="flex items-center justify-between mb-2 gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <span class="text-base shrink-0">{{ icon }}</span>
        <span class="text-sm font-medium text-ink-800 dark:text-ink-100 truncate">
          {{ title }}
        </span>
        <span
          v-if="proposal.scope"
          class="text-[10px] uppercase px-1.5 py-0.5 rounded bg-cream-200 dark:bg-ash-700 text-ink-700 dark:text-ink-300 shrink-0"
        >
          {{ proposal.scope }}
        </span>
        <span
          v-if="proposal.tool === 'Translate' && proposal.target_language"
          class="text-[10px] uppercase px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 shrink-0"
        >
          → {{ proposal.target_language }}
        </span>
      </div>
      <div v-if="status === 'pending'" class="flex gap-1 shrink-0">
        <button
          @click="onAccept"
          :disabled="busy"
          class="px-2 py-1 text-xs rounded text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ busy ? '…' : '✓ Accept' }}
        </button>
        <button
          @click="onReject"
          :disabled="busy"
          class="px-2 py-1 text-xs rounded text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          ✕ Reject
        </button>
      </div>
      <span
        v-else-if="status === 'accepted'"
        class="text-xs text-emerald-700 dark:text-emerald-300 shrink-0"
      >✓ Accepted</span>
      <span
        v-else
        class="text-xs text-red-700 dark:text-red-300 shrink-0"
      >✕ Rejected</span>
    </div>

    <div v-if="originalText" class="mb-2">
      <div class="text-[10px] uppercase tracking-wide text-ink-500 dark:text-ink-400 mb-1">Original</div>
      <div class="text-xs text-ink-700 dark:text-ink-300 line-through opacity-60 leading-relaxed whitespace-pre-wrap">{{ originalText }}</div>
    </div>
    <div v-if="rewriteText">
      <div class="text-[10px] uppercase tracking-wide text-emerald-700 dark:text-emerald-400 mb-1">Proposal</div>
      <div class="text-xs text-ink-800 dark:text-ink-100 leading-relaxed whitespace-pre-wrap">{{ rewriteText }}</div>
    </div>

    <div
      v-if="locationLabel"
      class="mt-2 text-[10px] text-ink-500 dark:text-ink-400"
    >
      {{ locationLabel }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { usePaperStore } from '../stores/paper'

const props = defineProps({
  proposal: { type: Object, required: true },
})
const emit = defineEmits(['accepted', 'rejected'])

const paperStore = usePaperStore()
const status = ref('pending')
const busy = ref(false)

const ICON_MAP = {
  Paraphrase: '✍',
  FixGrammar: '✓',
  Translate: '🌐',
}
const TITLE_MAP = {
  Paraphrase: 'Paraphrase proposal',
  FixGrammar: 'Grammar fix',
  Translate: 'Translation',
}

const icon = computed(() => ICON_MAP[props.proposal.tool] || '✏')
const title = computed(() => TITLE_MAP[props.proposal.tool] || 'Edit proposal')

function _stringify(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string') return v
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

const originalText = computed(() => _stringify(props.proposal.text))
const rewriteText = computed(() => _stringify(props.proposal.rewrite))

const locationLabel = computed(() => {
  const p = props.proposal
  if (p.section_index === undefined || p.section_index === null) return ''
  let s = `Section ${p.section_index}`
  if (p.content_index !== undefined && p.content_index !== null) {
    s += ` · paragraph ${p.content_index + 1}`
  }
  return s
})

async function onAccept() {
  if (status.value !== 'pending' || busy.value) return
  busy.value = true
  const p = props.proposal
  try {
    if (p.scope === 'paragraph' && p.section_index !== undefined && p.content_index !== undefined) {
      await paperStore.replaceContent(p.section_index, p.content_index, p.rewrite)
    } else if (p.scope === 'section' && p.section_index !== undefined) {
      await paperStore.replaceSectionText(p.section_index, p.rewrite)
    } else if (p.scope === 'whole') {
      await paperStore.replaceWhole(p.rewrite)
    } else if (p.section_index !== undefined && p.content_index !== undefined) {
      await paperStore.replaceContent(p.section_index, p.content_index, p.rewrite)
    } else if (p.section_index !== undefined) {
      await paperStore.replaceSectionText(p.section_index, p.rewrite)
    } else {
      throw new Error('Tidak ada target section/paragraph yang valid')
    }
    status.value = 'accepted'
    emit('accepted', p)
  } catch (e) {
    console.warn('Apply revisi failed', e)
    paperStore.showToast?.('Gagal apply: ' + (e?.message || e), 'error')
  } finally {
    busy.value = false
  }
}

function onReject() {
  if (status.value !== 'pending') return
  status.value = 'rejected'
  emit('rejected', props.proposal)
}
</script>
