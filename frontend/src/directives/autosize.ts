import type { Directive } from 'vue'
import { nextTick } from 'vue'

interface AutosizeElement extends HTMLTextAreaElement {
  __autosizeHandler__?: () => void
  __autosizeObserver__?: ResizeObserver
}

function resize(el: AutosizeElement): void {
  if (!el || el.tagName !== 'TEXTAREA') return
  el.style.height = 'auto'
  el.style.height = (el.scrollHeight + 2) + 'px'
}

export const vAutosize: Directive<AutosizeElement> = {
  mounted(el) {
    if (!el || el.tagName !== 'TEXTAREA') return
    el.style.overflow = 'hidden'
    el.style.resize = 'none'
    el.__autosizeHandler__ = () => resize(el)
    el.addEventListener('input', el.__autosizeHandler__)
    // Initial resize after DOM settles
    requestAnimationFrame(() => resize(el))
    // Watch parent for layout changes that might affect height
    // (e.g., content loaded programmatically, section expanded)
    if (el.parentElement) {
      const observer = new ResizeObserver(() => {
        requestAnimationFrame(() => resize(el))
      })
      observer.observe(el.parentElement)
      el.__autosizeObserver__ = observer
    }
  },
  updated(el) {
    // Double-buffer: nextTick ensures Vue has patched DOM,
    // requestAnimationFrame ensures browser has laid out
    nextTick(() => {
      requestAnimationFrame(() => resize(el))
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
