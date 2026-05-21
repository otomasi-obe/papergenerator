/**
 * LiteratureTab.vue — render-only tests.
 *
 * Stubs the paper store + axios api, then asserts that the right
 * static UI scaffolding shows up for empty / filtered / loading states.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../src/api/index.js', () => ({
  default: {
    get: vi.fn(async () => ({ data: [] })),
    post: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: {} })),
  },
}))

import LiteratureTab from '../../src/components/LiteratureTab.vue'
import api from '../../src/api/index.js'
import { usePaperStore } from '../../src/stores/paper.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  api.get.mockImplementation(async () => ({ data: [] }))
  api.post.mockImplementation(async () => ({ data: {} }))
  api.patch.mockImplementation(async () => ({ data: {} }))
  api.delete.mockImplementation(async () => ({ data: {} }))
})

async function mountTab() {
  const store = usePaperStore()
  store.currentPaperId = 'paperRENDER'
  const wrapper = mount(LiteratureTab)
  await flushPromises()
  return wrapper
}

describe('LiteratureTab — render', () => {
  it('renders header, run-SLR card, filter input and table', async () => {
    const w = await mountTab()
    const html = w.html()
    expect(html).toContain('Literatur')
    expect(html).toContain('Jalankan SLR')
    expect(w.find('input[placeholder*="topik"]').exists()).toBe(true)
    expect(w.find('input[placeholder*="Filter"]').exists()).toBe(true)
    expect(w.find('table').exists()).toBe(true)
  })

  it('shows empty-state message when items are zero', async () => {
    const w = await mountTab()
    expect(w.text()).toContain('Belum ada literatur')
  })

  it('shows "Memuat…" while loading=true', async () => {
    let resolveGet
    api.get.mockImplementation(
      () => new Promise((res) => { resolveGet = res })
    )
    const store = usePaperStore()
    store.currentPaperId = 'paperLOADING'
    const w = mount(LiteratureTab)
    await flushPromises()
    expect(w.text()).toContain('Memuat…')
    resolveGet({ data: [] })
    await flushPromises()
  })

  it('shows "Belum ada literatur" when filter excludes everything', async () => {
    api.get.mockImplementation(async (url) => {
      if (url.endsWith('/literature')) {
        return {
          data: [
            { id: 1, title: 'reinforcement learning', authors: ['A'], pinned: false,
              source: 'arxiv', source_kind: 'slr' },
          ],
        }
      }
      return { data: [] }
    })
    const w = await mountTab()
    expect(w.text()).toContain('reinforcement learning')

    await w.find('input[placeholder*="Filter"]').setValue('zzz-not-matching')
    await flushPromises()
    // The component has 3 empty states. When items.length>0 but
    // filteredItems=0, it shows the "no matches" message.
    expect(w.find('tbody').text()).toMatch(
      /Tidak ada literatur yang cocok|Tidak ada hasil sesuai filter/
    )
  })
})
