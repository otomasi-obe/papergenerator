import katex from 'katex'
import 'katex/dist/katex.min.css'
import DOMPurify from 'dompurify'

/**
 * Render LaTeX string ke HTML via KaTeX.
 * @param latex - raw LaTeX (tanpa $ atau $$)
 * @param displayMode - true = display (centered), false = inline
 */

function sanitizeHtml(html: string): string {
  // Use DOMPurify for robust XSS protection (replaces regex sanitizer)
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['span', 'math', 'semantics', 'annotation', 'mrow', 'mi', 'mo', 'mn', 'msub', 'msup', 'mfrac', 'msubsup', 'msqrt', 'mtext', 'annotation-xml', 'svg', 'path'],
    ALLOWED_ATTR: ['class', 'aria-hidden', 'style', 'width', 'height', 'viewBox', 'd', 'xmlns', 'encoding'],
  })
}

export function renderLatex(latex: string, displayMode = false): string {
  if (!latex || !latex.trim()) return ''
  try {
    const html = katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      trust: false,
      strict: false,
      output: 'html',
    })
    return sanitizeHtml(html)
  } catch {
    // Fallback: return raw text
    return `<span class="text-red-400" title="LaTeX error">${escapeHtml(latex)}</span>`
  }
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;')
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
  // Convert literal \n (backslash+n, not real newline) to line breaks,
  // but skip LaTeX commands like \nabla, \neq, \nsubseteq, etc.
  if (out.includes('\\n')) out = out.replace(/\\n(?![a-zA-Z])/g, '<br/>')
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
 * Fix missing spaces after LaTeX commands (e.g. \sumj → \sum j).
 * AI-generated content sometimes omits the space between command and variable.
 */
function fixLatexSpacing(latex: string): string {
  // Pattern: \<letters> immediately followed by another letter
  // e.g. "\sumj" → "\sum j", "\prodj" → "\prod j"
  return latex.replace(/\\([a-zA-Z]+)([a-zA-Z])/g, (_m, cmd, next) => {
    return `\\${cmd} ${next}`
  })
}

/**
 * Parse text yang mengandung inline ($...$) dan display ($$...$$) math,
 * plus formatting toggles (\b bold, \i italic, \u underline) and
 * Markdown (**bold**, *italic*). Returns HTML with all formatting rendered.
 */

/**
 * Auto-wrap raw LaTeX commands (like \\tau, \\omega_a) in $...$ delimiters
 * when they appear outside existing math blocks.
 */
function wrapRawLatex(text: string): string {
  if (!text) return text
  // Phase 1: wrap sub/super without $ (v_i → $v_i$, x^2 → $x^2$, P_loss → $P_{loss}$)
  // Also handles AI-generated spaces: P_l oss → $P_{loss}$, ΔV_m ax → $ΔV_{max}$
  // Both phases skip existing $...$ and $$...$$

  // Step 1a: fix split-subscripts where AI inserts space mid-subscript
  // Pattern: letter_letter<space>letters (e.g. P_l oss → P_loss, PF_b ase → PF_base)
  text = text.replace(/([a-zA-ZΑ-Ωα-ω])_([a-zA-Z]) ([a-z]{1,12})(?=[\s.,;:)}\]!?]|$)/g, '$1_{$2$3}')
  
  // Step 1b: wrap subscript/superscript patterns (v_i, x^2, P_loss, c_1,c_2)
  const wrapSubSup = (t: string): string => {
    return t.replace(/(?<!\$)([a-zA-ZΑ-Ωα-ω0-9)\]}Δ]+)((?:[_^](?:\{[^{}]*\}|[a-zA-Z0-9]+))+)/g, (match, base: string, ops: string) => {
      // Don't wrap if base is too long (likely a word, not a variable)
      if (base.length > 8) return match
      // Don't wrap common false positives: URLs, filenames, code-like patterns
      if (/^https?/.test(base) || /\./.test(base)) return match
      // Wrap multi-char subscript/superscript in {} for KaTeX
      // e.g. P_loss → P_{loss}, x^2n → x^{2n} (but keep single chars: v_i, x^2)
      const fixedOps = ops.replace(/([_^])([a-zA-Z0-9]{2,})/g, '$1{$2}')
      return '$' + base + fixedOps + '$'
    })
  }
  text = wrapSubSup(text)
  
  // Step 1c: wrap standalone single-letter variables (v, x, y, z, w, t, etc.)
  // Only wrap if followed by space/punctuation (not part of a word)
  // Common math variables: v, x, y, z, w, t, u, p, q, r, s, m, n, k, i, j
  // Greek letters: α, β, γ, δ, ε, ζ, η, θ, ι, κ, λ, μ, ν, ξ, π, ρ, σ, τ, υ, φ, χ, ψ, ω
  const singleLetterVars = 'vxyzwtupqrsmnkijαβγδεζηθικλμνξπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ'
  text = text.replace(new RegExp(`(?<![a-zA-ZΑ-Ωα-ω])([${singleLetterVars}])(?=[\\s.,;:)}\\]!?]|$)`, 'g'), '$$$1$')
  
  // Step 1d: wrap comma-separated variable lists (c_1,c_2 → $c_1$,$c_2$)
  // This is handled by Step 1b for each variable separately, but ensure commas are preserved
  
  // Phase 2: wrap raw \commands outside $...$
  let result = ''
  let i = 0
  const len = text.length
  while (i < len) {
    // Skip $$...$$ display math
    if (text[i] === '$' && text[i + 1] === '$') {
      const end = text.indexOf('$$', i + 2)
      if (end !== -1) { result += text.slice(i, end + 2); i = end + 2; continue }
    }
    // Skip $...$ inline math
    if (text[i] === '$') {
      const end = text.indexOf('$', i + 1)
      if (end !== -1) { result += text.slice(i, end + 1); i = end + 1; continue }
    }
    // Found backslash outside any math block
    if (text[i] === '\\') {
      const next = text[i + 1]
      // Skip \b, \i, \u toggles when NOT followed by a letter
      if (next === 'b' || next === 'i') {
        const after = text[i + 2] || ''
        if (!/[a-zA-Z]/.test(after)) { result += text[i]; i++; continue }
      }
      // Skip \u toggle and unicode escapes like \u2022
      if (next === 'u') { result += text[i]; i++; continue }
      // Skip \( and \[ LaTeX delimiters
      if (next === '(' || next === '[') { result += text[i]; i++; continue }
      // It's a raw LaTeX command like \tau, \omega — wrap in $...$
      if (/[a-zA-Z]/.test(next || '')) {
        let end = i + 1
        while (end < len && /[a-zA-Z]/.test(text[end])) { end++ }
        // Subscript: _text or _{text}
        if (text[end] === '_') {
          end++
          if (text[end] === '{') {
            let depth = 1; end++
            while (end < len && depth > 0) {
              if (text[end] === '{') depth++
              else if (text[end] === '}') depth--
              end++
            }
          } else {
            while (end < len && /[a-zA-Z0-9]/.test(text[end])) { end++ }
          }
        }
        // Superscript: ^text or ^{text}
        if (text[end] === '^') {
          end++
          if (text[end] === '{') {
            let depth = 1; end++
            while (end < len && depth > 0) {
              if (text[end] === '{') depth++
              else if (text[end] === '}') depth--
              end++
            }
          } else {
            while (end < len && /[a-zA-Z0-9]/.test(text[end])) { end++ }
          }
        }
        result += '$' + text.slice(i, end) + '$'
        i = end
        continue
      }
    }
    result += text[i]
    i++
  }
  return result
}

export function renderRichText(text: string): string {
  if (!text) return ''

  text = stripControlChars(text)
  text = decodeStrayEscapes(text)
  text = wrapRawLatex(text)

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
        const latex = fixLatexSpacing(text.slice(i + 2, end))
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
        const latex = fixLatexSpacing(text.slice(i + 1, end))
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

    // Check for \(...\) (inline math, LaTeX delimiters)
    if (text[i] === '\\' && text[i + 1] === '(') {
      const end = text.indexOf('\\)', i + 2)
      if (end !== -1) {
        const latex = fixLatexSpacing(text.slice(i + 2, end))
        if (latex.trim()) {
          result += closeTags()
          result += renderLatex(latex, false)
          result += openTags()
        }
        i = end + 2
        continue
      }
    }

    // Check for \[...\] (display math, LaTeX delimiters)
    if (text[i] === '\\' && text[i + 1] === '[') {
      const end = text.indexOf('\\]', i + 2)
      if (end !== -1) {
        const latex = fixLatexSpacing(text.slice(i + 2, end))
        if (latex.trim()) {
          result += closeTags()
          result += `<span class="block text-center my-2">${renderLatex(latex, true)}</span>`
          result += openTags()
        }
        i = end + 2
        continue
      }
    }

    // \b bold toggle (guard: NOT preceded by backslash, NOT followed by lowercase letter, to avoid \beta, \binom)
    if (text[i] === '\\' && text[i + 1] === 'b' && !/[a-z]/.test(text[i + 2] || '') && !(i > 0 && /[a-z\\]/.test(text[i - 1]))) {
      result += closeTags()
      bold = !bold
      result += openTags()
      i += 2
      continue
    }

    // \i italic toggle (guard: NOT preceded by backslash/letter, NOT followed by lowercase letter, to avoid \int, \in, \infty)
    if (text[i] === '\\' && text[i + 1] === 'i' && !/[a-z]/.test(text[i + 2] || '') && !(i > 0 && /[a-z\\]/.test(text[i - 1]))) {
      result += closeTags()
      italic = !italic
      result += openTags()
      i += 2
      continue
    }

    // \u underline toggle (guard: NOT preceded by backslash/letter, NOT followed by lowercase letter/hex, to avoid \u2022 etc.)
    if (text[i] === '\\' && text[i + 1] === 'u' && !/[a-z0-9]/.test(text[i + 2] || '') && !(i > 0 && /[a-z\\]/.test(text[i - 1]))) {
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
 * Handles math AND formatting toggles (\b \i \u).
 */
function renderRichTextInner(text: string): string {
  let result = ''
  let i = 0
  const len = text.length
  while (i < len) {
    // $$...$$ display math
    if (text[i] === '$' && text[i + 1] === '$') {
      const end = text.indexOf('$$', i + 2)
      if (end !== -1) {
        const latex = fixLatexSpacing(text.slice(i + 2, end))
        if (latex.trim()) {
          result += `<span class="block text-center my-2">${renderLatex(latex, true)}</span>`
        }
        i = end + 2
        continue
      }
    }
    // $...$ inline math
    if (text[i] === '$' && text[i + 1] !== '$') {
      const end = text.indexOf('$', i + 1)
      if (end !== -1 && end > i + 1) {
        const latex = fixLatexSpacing(text.slice(i + 1, end))
        const isCurrency = /^[0-9,.]+$/.test(latex.trim())
        if (latex.trim() && !isCurrency) {
          result += renderLatex(latex, false)
          i = end + 1
          continue
        }
      }
    }
    // \b \i \u toggles (guarded: NOT preceded by backslash/letter, NOT followed by lowercase)
    if (text[i] === '\\' && text[i + 1] === 'b' && !/[a-zA-Z]/.test(text[i + 2] || '') && !(i > 0 && /[a-z\\]/.test(text[i - 1]))) {
      i += 2; continue
    }
    if (text[i] === '\\' && text[i + 1] === 'i' && !/[a-zA-Z]/.test(text[i + 2] || '') && !(i > 0 && /[a-z\\]/.test(text[i - 1]))) {
      i += 2; continue
    }
    if (text[i] === '\\' && text[i + 1] === 'u' && !/[a-zA-Z0-9]/.test(text[i + 2] || '') && !(i > 0 && /[a-z\\]/.test(text[i - 1]))) {
      i += 2; continue
    }
    result += escapeHtml(text[i])
    i++
  }
  return result
}