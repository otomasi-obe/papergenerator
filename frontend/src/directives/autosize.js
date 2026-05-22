/**
 * v-autosize — make a textarea grow with its content.
 *
 * Usage:
 *   <textarea v-autosize v-model="value" />
 *
 * Behavior:
 * - On mount: set height to scrollHeight (so content already in the model
 *   shows fully without manual scrolling).
 * - On every `input` event: re-measure (height to 'auto' first to allow
 *   shrinking, then to scrollHeight).
 * - When the bound value changes from the outside (e.g. v-model from a
 *   store update), the `updated` hook re-measures on the next tick.
 *
 * The element MUST be a <textarea>. Anything else is a silent no-op so the
 * directive is safe to apply broadly without breaking other inputs.
 */
function resize(el) {
  if (!el || el.tagName !== 'TEXTAREA') return
  // Reset to auto first so the element can shrink if content was deleted.
  el.style.height = 'auto'
  // Add 2px to absorb the inevitable subpixel rounding so the last line
  // never gets clipped under a scrollbar.
  el.style.height = (el.scrollHeight + 2) + 'px'
}

export const vAutosize = {
  mounted(el) {
    if (!el || el.tagName !== 'TEXTAREA') return
    el.style.overflow = 'hidden'
    el.style.resize = 'none'
    el.__autosizeHandler__ = () => resize(el)
    el.addEventListener('input', el.__autosizeHandler__)
    // First measurement may need to wait for layout; rAF is enough.
    requestAnimationFrame(() => resize(el))
  },
  updated(el) {
    // Re-measure after Vue patches new value into DOM.
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
