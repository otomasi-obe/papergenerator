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
  if (out.includes('\\t')) out = out.replace(/\\t/g, ' ')
  return out
}

/**
 * Parse text yang mengandung inline ($...$) dan display ($$...$$) math.
 * Returns HTML string dengan math sudah di-render.
 */
export function renderRichText(text: string): string {
  if (!text) return ''

  text = decodeStrayEscapes(text)

  let result = ''
  let i = 0
  const len = text.length

  while (i < len) {
    // Check for $$...$$ (display math)
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

    // Check for $...$ (inline math)
    if (text[i] === '$' && text[i + 1] !== '$') {
      const end = text.indexOf('$', i + 1)
      if (end !== -1 && end > i + 1) {
        const latex = text.slice(i + 1, end)
        if (latex.trim()) {
          result += renderLatex(latex, false)
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
          result += renderLatex(latex, false)
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
          result += `<span class="block text-center my-2">${renderLatex(latex, true)}</span>`
        }
        i = end + 2
        continue
      }
    }

    // Regular text
    result += escapeHtml(text[i])
    i++
  }

  return result
}
