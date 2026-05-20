/**
 * UI store unit tests — covers per-paper tab + chat-open persistence
 * (rofiq.txt #2 + #3).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUiStore } from '../../src/stores/ui.js'

beforeEach(() => {
  // Fresh pinia + reset localStorage between tests so persistence layer is clean.
  setActivePinia(createPinia())
  if (typeof localStorage !== 'undefined') localStorage.clear()
})

describe('ui store', () => {
  it('returns chat-full default for a brand-new paper (no tab selected)', () => {
    const ui = useUiStore()
    expect(ui.getTab('paper-A')).toBe('')
    expect(ui.getChatOpen('paper-A')).toBe(true)
  })

  it('persists tab choice and recalls it', () => {
    const ui = useUiStore()
    ui.setTab('paper-A', 'editor')
    expect(ui.getTab('paper-A')).toBe('editor')
    ui.setTab('paper-A', 'preview')
    expect(ui.getTab('paper-A')).toBe('preview')
  })

  it('keeps state separate per paper id', () => {
    const ui = useUiStore()
    ui.setTab('paper-A', 'editor')
    ui.setTab('paper-B', 'figures')
    expect(ui.getTab('paper-A')).toBe('editor')
    expect(ui.getTab('paper-B')).toBe('figures')
  })

  it('toggles chat panel independently per paper', () => {
    const ui = useUiStore()
    ui.setChatOpen('paper-A', false)
    expect(ui.getChatOpen('paper-A')).toBe(false)
    expect(ui.getChatOpen('paper-B')).toBe(true) // default for unseen paper
  })

  it('reset(paperId) drops only that entry', () => {
    const ui = useUiStore()
    ui.setTab('paper-A', 'editor')
    ui.setTab('paper-B', 'preview')
    ui.reset('paper-A')
    expect(ui.getTab('paper-A')).toBe('') // back to default
    expect(ui.getTab('paper-B')).toBe('preview')
  })
})
