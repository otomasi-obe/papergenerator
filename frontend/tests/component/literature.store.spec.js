/**
 * Literature store unit tests.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLiteratureStore } from '../../src/stores/literature.js'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('literature store', () => {
  it('attachJob stores intent', () => {
    const lit = useLiteratureStore()
    expect(lit.pendingIntent).toBeNull()
    lit.attachJob({ job_id: 'abc12', query: 'ai', top_k: 30, ai_model: 'V-OPUS' })
    expect(lit.pendingIntent).toEqual({
      job_id: 'abc12', query: 'ai', top_k: 30, ai_model: 'V-OPUS',
    })
  })

  it('consumeIntent returns intent and clears it', () => {
    const lit = useLiteratureStore()
    lit.attachJob({ job_id: 'xyz77', query: 'q', top_k: 50, ai_model: 'V-OPUS' })
    const got = lit.consumeIntent()
    expect(got).toEqual({ job_id: 'xyz77', query: 'q', top_k: 50, ai_model: 'V-OPUS' })
    expect(lit.pendingIntent).toBeNull()
    // Second consume returns null
    expect(lit.consumeIntent()).toBeNull()
  })

  it('clearIntent clears it', () => {
    const lit = useLiteratureStore()
    lit.attachJob({ job_id: 'aaa', query: 'q' })
    lit.clearIntent()
    expect(lit.pendingIntent).toBeNull()
  })
})
