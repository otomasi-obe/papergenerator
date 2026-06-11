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
 * Parse text yang mengandung inline ($...$) dan display ($$...$$) math.
 * Returns HTML string dengan math sudah di-render.
 */
export function renderRichText(text: string): string {
  if (!text) return ''

  let result = ''
  let i = 0
  const len = text.length

  while (i < len) {
    // Check for $$...$$ (display math)
    if (text[i] === '$' && text[i + 1] === '$') {
      const end = text.indexOf('$$', i + 2)
      if (end !== -1) {
        const latex = text.slice(i + 2, end)
        result += `<span class="block text-center my-2">${renderLatex(latex, true)}</span>`
        i = end + 2
        continue
      }
    }

    // Check for $...$ (inline math)
    if (text[i] === '$' && text[i + 1] !== '$') {
      const end = text.indexOf('$', i + 1)
      if (end !== -1 && end > i + 1) {
        const latex = text.slice(i + 1, end)
        result += renderLatex(latex, false)
        i = end + 1
        continue
      }
    }

    // Check for \(...\) (inline math)
    if (text[i] === '\\' && text[i + 1] === '(') {
      const end = text.indexOf('\\)', i + 2)
      if (end !== -1) {
        const latex = text.slice(i + 2, end)
        result += renderLatex(latex, false)
        i = end + 2
        continue
      }
    }

    // Check for \[...\] (display math)
    if (text[i] === '\\' && text[i + 1] === '[') {
      const end = text.indexOf('\\]', i + 2)
      if (end !== -1) {
        const latex = text.slice(i + 2, end)
        result += `<span class="block text-center my-2">${renderLatex(latex, true)}</span>`
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
