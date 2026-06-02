import type { Directive } from 'vue'

interface AutosizeElement extends HTMLTextAreaElement {
  __autosizeHandler__?: () => void
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
    requestAnimationFrame(() => resize(el))
  },
  updated(el) {
    requestAnimationFrame(() => resize(el))
  },
  unmounted(el) {
    if (el?.__autosizeHandler__) {
      el.removeEventListener('input', el.__autosizeHandler__)
      delete el.__autosizeHandler__
    }
  },
}

export default vAutosize
