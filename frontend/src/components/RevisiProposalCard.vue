<template>
  <div
    class="revisi-proposal rounded-lg border p-3 my-2
           bg-cream-50 dark:bg-ash-800
           border-cream-300 dark:border-ash-700"
  >
    <!-- Header: tool title, scope subtitle, language badge, action buttons -->
    <div class="flex items-start justify-between gap-2 mb-2">
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2">
          <span class="text-base shrink-0">{{ icon }}</span>
          <span class="text-sm font-semibold text-ink-800 dark:text-ink-100 truncate">
            {{ title }}
          </span>
          <span
            v-if="proposal.tool === 'Translate' && proposal.target_language"
            class="text-[10px] uppercase px-1.5 py-0.5 rounded bg-navy-100 dark:bg-navy-900/40 text-navy-700 dark:text-navy-300 shrink-0"
          >
            → {{ targetLangLabel }}
          </span>
        </div>
        <div
          v-if="subtitle"
          class="text-[11px] mt-0.5 text-ink-500 dark:text-ink-300"
        >
          {{ subtitle }}
        </div>
      </div>

      <div v-if="status === 'pending'" class="flex gap-1 shrink-0">
        <button
          type="button"
          @click="onAccept"
          :disabled="busy"
          class="px-2.5 py-1 text-xs font-medium rounded
                 bg-emerald-600 hover:bg-emerald-700 text-white
                 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ busy ? '…' : '✓ Terima' }}
        </button>
        <button
          type="button"
          @click="onReject"
          :disabled="busy"
          class="px-2.5 py-1 text-xs font-medium rounded border
                 border-red-300 dark:border-red-700
                 text-red-700 dark:text-red-300
                 hover:bg-red-50 dark:hover:bg-red-900/30
                 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          ✕ Tolak
        </button>
      </div>
      <span
        v-else-if="status === 'accepted'"
        class="text-xs font-medium text-emerald-700 dark:text-emerald-300 shrink-0 self-center"
      >✓ Diterima</span>
      <span
        v-else
        class="text-xs font-medium text-red-700 dark:text-red-300 shrink-0 self-center"
      >✕ Ditolak</span>
    </div>

    <!-- Side-by-side diff: original vs rewrite -->
    <div class="diff-grid">
      <div class="diff-col diff-original">
        <div class="diff-label">Original</div>
        <pre class="diff-text">{{ originalText || '—' }}</pre>
      </div>
      <div class="diff-col diff-rewrite">
        <div class="diff-label diff-label-rewrite">Rewrite</div>
        <pre class="diff-text">{{ rewriteText || '—' }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed } from 'vue'
import { usePaperStore } from '../stores/paper'

interface Props {
  proposal: any
}

const props = defineProps<Props>()
const store = usePaperStore()
const busy = ref<boolean>(false)

const status = computed<string>(() => props.proposal.status || 'pending')

const icon = computed<string>(() => {
  const tool = props.proposal.tool
  if (tool === 'Translate') return '🌐'
  if (tool === 'Paraphrase') return '✏️'
  if (tool === 'Expand') return '📝'
  if (tool === 'Simplify') return '💡'
  if (tool === 'Formalize') return '🎓'
  return '🔧'
})

const title = computed<string>(() => {
  const tool = props.proposal.tool
  if (tool === 'Translate') return 'Translation'
  if (tool === 'Paraphrase') return 'Paraphrase'
  if (tool === 'Expand') return 'Expand'
  if (tool === 'Simplify') return 'Simplify'
  if (tool === 'Formalize') return 'Formalize'
  return tool || 'Revision'
})

const subtitle = computed<string>(() => {
  const scope = props.proposal.scope
  if (!scope) return ''
  if (scope === 'full_paper') return 'Full paper'
  if (scope === 'section') return `Section: ${props.proposal.section_title || '?'}`
  if (scope === 'subsection') return `Subsection: ${props.proposal.subsection_title || '?'}`
  if (scope === 'abstract') return 'Abstract'
  return scope
})

const targetLangLabel = computed<string>(() => {
  const lang = props.proposal.target_language
  if (!lang) return ''
  const map: Record<string, string> = {
    en: 'EN',
    id: 'ID',
    es: 'ES',
    fr: 'FR',
    de: 'DE',
    zh: 'ZH',
    ja: 'JA',
    ko: 'KO',
  }
  return map[lang] || lang.toUpperCase()
})

const originalText = computed<string>(() => {
  return props.proposal.original_text || ''
})

const rewriteText = computed<string>(() => {
  return props.proposal.rewrite_text || ''
})

// Determine which store action to call based on proposal scope
async function acceptStoreAction() {
  const p = props.proposal
  if (!p) return

  switch (p.scope) {
    case 'abstract':
      // proposal.text = new abstract content
      if (p.text !== undefined) {
        await store.acceptProposal(p.id)
      }
      break

    case 'section':
    case 'subsection':
      // proposal.rewrite = { title, content } or plain text
      if (p.section_index !== undefined) {
        if (typeof p.rewrite === 'string') {
          await store.replaceSectionText(p.section_index, p.rewrite)
        } else if (typeof p.rewrite === 'object') {
          await store.replaceSectionText(p.section_index, p.rewrite)
        }
        // Mark pending proposal as accepted so it doesn't show as pending
        try { await store.acceptProposal(p.id) } catch { /* id may not be in pendingChanges */ }
      }
      break

    case 'full_paper':
      // proposal.rewrite = full paper JSON
      if (typeof p.rewrite === 'object') {
        await store.replaceWhole(p.rewrite)
        try { await store.acceptProposal(p.id) } catch { /* */ }
      }
      break

    default:
      // Fallback: treat as generic proposal
      if (p.id) {
        await store.acceptProposal(p.id)
      } else if (p.section_index !== undefined) {
        await store.replaceSectionText(p.section_index, p.rewrite || p.text)
      }
  }
}

async function onAccept(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await acceptStoreAction()
  } finally {
    busy.value = false
  }
}

async function onReject(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    // Mark as rejected in pendingChanges so it disappears from review UI
    if (props.proposal.id) {
      try { store.rejectProposal(props.proposal.id) } catch { /* */ }
    }
    // Notify backend
    // eslint-disable-next-line no-unused-vars
    const res = await fetch(`/api/chat/revisi/${props.proposal.id}/reject`, {
      method: 'POST',
      credentials: 'include',
    }).catch(() => {/* silent - backend may not have this endpoint */})
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.diff-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
@media (max-width: 540px) {
  .diff-grid { grid-template-columns: 1fr; }
}
.diff-col {
  border-radius: 6px;
  padding: 8px 10px;
  min-width: 0;
}
.diff-original {
  background: rgba(220, 38, 38, 0.06);
  border: 1px solid rgba(220, 38, 38, 0.2);
}
.diff-rewrite {
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.2);
}
.diff-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #b91c1c;
  margin-bottom: 4px;
  font-weight: 600;
}
.diff-label-rewrite { color: #047857; }
.diff-text {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.55;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-strong, #1f2937);
}

.dark .diff-original {
  background: rgba(220, 38, 38, 0.12);
  border-color: rgba(220, 38, 38, 0.3);
}
.dark .diff-rewrite {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.3);
}
.dark .diff-label { color: #fca5a5; }
.dark .diff-label-rewrite { color: #6ee7b7; }
.dark .diff-text { color: #eddbac; }
</style>
