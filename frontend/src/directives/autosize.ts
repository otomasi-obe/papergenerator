import type { Directive } from 'vue'
import { nextTick } from 'vue'

interface AutosizeElement extends HTMLTextAreaElement {
  __autosizeHandler__?: () => void
  __autosizeObserver__?: ResizeObserver
}

// Batch all autosize resizes into a single scroll save/restore to prevent
// race conditions when multiple textareas resize in the same frame
// (each one would save a scrollTop already corrupted by the previous resize).
let pendingResizes: AutosizeElement[] = []
let batchScheduled = false

function flushResizes(): void {
  const els = pendingResizes
  pendingResizes = []
  batchScheduled = false
  if (!els.length) return
  // Find the scroll ancestor from the first element
  const scrollParent = els[0]?.closest('.overflow-y-auto') as HTMLElement | null
  const st = scrollParent?.scrollTop ?? 0
  for (const el of els) {
    if (!el || el.tagName !== 'TEXTAREA') continue
    el.style.height = 'auto'
    el.style.height = (el.scrollHeight + 2) + 'px'
  }
  if (scrollParent && scrollParent.scrollTop !== st) {
    scrollParent.scrollTop = st
  }
}

function scheduleResize(el: AutosizeElement): void {
  if (!el || el.tagName !== 'TEXTAREA') return
  if (!pendingResizes.includes(el)) {
    pendingResizes.push(el)
  }
  if (!batchScheduled) {
    batchScheduled = true
    requestAnimationFrame(flushResizes)
  }
}

export const vAutosize: Directive<AutosizeElement> = {
  mounted(el) {
    if (!el || el.tagName !== 'TEXTAREA') return
    el.style.overflow = 'hidden'
    el.style.resize = 'none'
    el.__autosizeHandler__ = () => scheduleResize(el)
    el.addEventListener('input', el.__autosizeHandler__)
    // Initial resize after DOM settles
    requestAnimationFrame(() => scheduleResize(el))
    // Watch parent for layout changes that might affect height
    // (e.g., content loaded programmatically, section expanded)
    if (el.parentElement) {
      const observer = new ResizeObserver(() => {
        requestAnimationFrame(() => scheduleResize(el))
      })
      observer.observe(el.parentElement)
      el.__autosizeObserver__ = observer
    }
  },
  updated(el) {
    // Double-buffer: nextTick ensures Vue has patched DOM,
    // requestAnimationFrame ensures browser has laid out
    nextTick(() => {
      requestAnimationFrame(() => scheduleResize(el))
    })
  },
  unmounted(el) {
    if (el?.__autosizeHandler__) {
      el.removeEventListener('input', el.__autosizeHandler__)
      delete el.__autosizeHandler__
    }
    if (el?.__autosizeObserver__) {
      el.__autosizeObserver__.disconnect()
      delete el.__autosizeObserver__
    }
  },
}

export default vAutosize
