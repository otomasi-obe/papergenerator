import katex from 'katex'
import 'katex/dist/katex.min.css'

/**
 * Render LaTeX string ke HTML via KaTeX.
 * @param latex - raw LaTeX (tanpa $ atau $$)
 * @param displayMode - true = display (centered), false = inline
 */
export function renderLatex(latex: string, displayMode = false): string {
  if (!latex || !latex.trim()) return ''
  try {
    return katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      trust: true,
      strict: false,
      output: 'html',
    })
  } catch {
    // Fallback: return raw text
    return `<span class="text-red-400" title="LaTeX error">${escapeHtml(latex)}</span>`
  }
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/**
 * Decode literal escape sequences the AI sometimes emits as raw text
 * (e.g. the six characters `\u2022` instead of the real bullet `•`).
 * Without this the preview shows the literal `\u2022`. Control chars
 * (< U+0020) become a space so they don't break layout.
 */
function decodeStrayEscapes(text: string): string {
  if (!text) return text
  let out = text
  if (out.includes('\\u')) {
    out = out.replace(/\\u([0-9a-fA-F]{4})/g, (m, hex) => {
      try {
        const ch = String.fromCharCode(parseInt(hex, 16))
        return ch.charCodeAt(0) < 0x20 ? ' ' : ch
      } catch {
        return m
      }
    })
  }
  if (out.includes('\\t')) out = out.replace(/\\t(?![a-zA-Z])/g, ' ')
  // Strip literal backspace char (U+0008) — shows as empty box
  out = out.replace(/\x08/g, '')
  return out
}

/**
 * Strip control characters that render as empty boxes.
 * Keeps \n \r \t but removes everything else below U+0020.
 */
function stripControlChars(text: string): string {
  if (!text) return text
  return text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '')
}

/**
 * Parse text yang mengandung inline ($...$) dan display ($$...$$) math,
 * plus formatting toggles (\b bold, \i italic, \u underline) and
 * Markdown (**bold**, *italic*). Returns HTML with all formatting rendered.
 */
export function renderRichText(text: string): string {
  if (!text) return ''

  text = stripControlChars(text)
  text = decodeStrayEscapes(text)

  // State machine: track formatting toggles
  let result = ''
  let i = 0
  const len = text.length
  let bold = false
  let italic = false
  let underline = false

  // Open/close tracking for proper HTML nesting
  function openTags(): string {
    let s = ''
    if (bold) s += '<b>'
    if (italic) s += '<i>'
    if (underline) s += '<u>'
    return s
  }
  function closeTags(): string {
    let s = ''
    if (underline) s += '</u>'
    if (italic) s += '</i>'
    if (bold) s += '</b>'
    return s
  }

  while (i < len) {
    // Check for $$...$$ (display math)
    if (text[i] === '$' && text[i + 1] === '$') {
      const end = text.indexOf('$$', i + 2)
      if (end !== -1) {
        const latex = text.slice(i + 2, end)
        if (latex.trim()) {
          result += closeTags()
          result += `<span class="block text-center my-2">${renderLatex(latex, true)}</span>`
          result += openTags()
        }
        i = end + 2
        continue
      }
    }

    // Check for $...$ (inline math)
    if (text[i] === '$' && text[i + 1] !== '$') {
      const end = text.indexOf('$', i + 1)
      if (end !== -1 && end > i + 1) {
        const latex = text.slice(i + 1, end)
        const isCurrency = /^[0-9,.]+(\s+(and|or|to|per))?$/.test(latex.trim())
        if (latex.trim() && !isCurrency) {
          result += closeTags()
          result += renderLatex(latex, false)
          result += openTags()
        } else if (isCurrency) {
          result += escapeHtml('$' + latex + '$')
        }
        i = end + 1
        continue
      }
    }

    // Check for \(...\) (inline math)
    if (text[i] === '\\' && text[i + 1] === '(') {
      const end = text.indexOf('\\)', i + 2)
      if (end !== -1) {
        const latex = text.slice(i + 2, end)
        if (latex.trim()) {
          result += closeTags()
          result += renderLatex(latex, false)
          result += openTags()
        }
        i = end + 2
        continue
      }
    }

    // Check for \[...\] (display math)
    if (text[i] === '\\' && text[i + 1] === '[') {
      const end = text.indexOf('\\]', i + 2)
      if (end !== -1) {
        const latex = text.slice(i + 2, end)
        if (latex.trim()) {
          result += closeTags()
          result += `<span class="block text-center my-2">${renderLatex(latex, true)}</span>`
          result += openTags()
        }
        i = end + 2
        continue
      }
    }

    // \b bold toggle
    if (text[i] === '\\' && text[i + 1] === 'b') {
      result += closeTags()
      bold = !bold
      result += openTags()
      i += 2
      continue
    }

    // \i italic toggle
    if (text[i] === '\\' && text[i + 1] === 'i') {
      result += closeTags()
      italic = !italic
      result += openTags()
      i += 2
      continue
    }

    // \u underline toggle
    if (text[i] === '\\' && text[i + 1] === 'u') {
      result += closeTags()
      underline = !underline
      result += openTags()
      i += 2
      continue
    }

    // **bold** markdown
    if (text[i] === '*' && text[i + 1] === '*') {
      const end = text.indexOf('**', i + 2)
      if (end !== -1) {
        const inner = text.slice(i + 2, end)
        result += closeTags()
        result += `<b>${renderRichTextInner(inner)}</b>`
        result += openTags()
        i = end + 2
        continue
      }
    }

    // *italic* markdown (single, not double)
    if (text[i] === '*' && text[i + 1] !== '*' && text[i + 1] !== undefined) {
      const end = text.indexOf('*', i + 1)
      if (end !== -1 && end > i + 1) {
        const inner = text.slice(i + 1, end)
        if (inner.trim()) {
          result += closeTags()
          result += `<i>${renderRichTextInner(inner)}</i>`
          result += openTags()
        }
        i = end + 1
        continue
      }
    }

    // Regular text
    result += escapeHtml(text[i])
    i++
  }

  // Close any remaining open tags
  result += closeTags()

  return result
}

/**
 * Lightweight inner render for nested markdown (bold/italic content).
 * Only handles math, no recursive formatting.
 */
function renderRichTextInner(text: string): string {
  let result = ''
  let i = 0
  const len = text.length
  while (i < len) {
    if (text[i] === '$' && text[i + 1] === '$') {
      const end = text.indexOf('$$', i + 2)
      if (end !== -1) {
        const latex = text.slice(i + 2, end)
        if (latex.trim()) {
          result += `<span class="block text-center my-2">${renderLatex(latex, true)}</span>`
        }
        i = end + 2
        continue
      }
    }
    if (text[i] === '$' && text[i + 1] !== '$') {
      const end = text.indexOf('$', i + 1)
      if (end !== -1 && end > i + 1) {
        const latex = text.slice(i + 1, end)
        const isCurrency = /^[0-9,.]+$/.test(latex.trim())
        if (latex.trim() && !isCurrency) {
          result += renderLatex(latex, false)
          i = end + 1
          continue
        }
      }
    }
    result += escapeHtml(text[i])
    i++
  }
  return result
}
