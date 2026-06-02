// @ts-nocheck
import DOMPurify from 'dompurify'

/**
 * Composable for sanitizing HTML content to prevent XSS attacks
 */
export function useSanitize() {
  /**
   * Sanitize HTML string using DOMPurify
   * @param dirty - The potentially unsafe HTML string
   * @param config - Optional DOMPurify configuration
   * @returns Sanitized HTML string safe for rendering
   */
  const sanitizeHtml = (dirty: string, config?: DOMPurify.Config): string => {
    return DOMPurify.sanitize(dirty, config) as string
  }

  /**
   * Sanitize HTML with MathJax/KaTeX support
   * Allows math-related tags and attributes while preventing XSS
   */
  const sanitizeMath = (dirty: string): string => {
    return DOMPurify.sanitize(dirty, {
      ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mroot'],
      ADD_ATTR: ['xmlns', 'display', 'displaystyle'],
      ALLOWED_TAGS: [
        'span', 'div', 'p', 'br',
        'math', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mroot',
        'annotation', 'semantics'
      ],
      ALLOWED_ATTR: [
        'class', 'style', 'xmlns', 'display', 'displaystyle',
        'data-katex', 'data-katex-display'
      ]
    }) as string
  }

  return {
    sanitizeHtml,
    sanitizeMath
  }
}
