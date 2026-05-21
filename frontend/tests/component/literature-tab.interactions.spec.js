/**
 * LiteratureTab.vue — interaction tests.
 *
 * Stubs the api module so PATCH/POST/DELETE return canned values,
 * then exercises the user paths: pin toggle, must-read toggle, addManual,
 * deleteItem, filter narrowing, runSLR error path.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../src/api/index.js', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import LiteratureTab from '../../src/components/LiteratureTab.vue'
import api from '../../src/api/index.js'
import { usePaperStore } from '../../src/stores/paper.js'

const SAMPLE = [
  {
    id: 1, title: 'reinforcement learning for AGV',
    authors: ['Alice', 'Bob'], year: 2024, venue: 'IEEE Trans. Robotics',
    publisher: 'IEEE', doi: '10.1109/abc.2024.001', url: '',
    abstract: '', summary: '',
    citations: 12, score_total: 0.85, score_breakdown: {},
    must_read: false, is_relevant: true, notes: '', pinned: false,
    source_kind: 'slr', source: 'openalex',
  },
  {
    id: 2, title: 'deep learning survey',
    authors: ['Carol'], year: 2022, venue: 'Nature',
    publisher: '', doi: '', url: 'https://example.org/x',
    abstract: '', summary: '',
    citations: 999, score_total: 0.7, score_breakdown: {},
    must_read: true, is_relevant: true, notes: '', pinned: true,
    source_kind: 'manual', source: 'manual',
  },
]

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()

  api.get.mockImplementation(async (url) => {
    if (url.endsWith('/literature')) return { data: structuredClone(SAMPLE) }
    if (url.endsWith('/slr/jobs')) return { data: [] }
    return { data: [] }
  })
  api.post.mockImplementation(async () => ({ data: {} }))
  api.patch.mockImplementation(async () => ({ data: {} }))
  api.delete.mockImplementation(async () => ({ data: {} }))
})

async function mountTab() {
  const store = usePaperStore()
  store.currentPaperId = 'paperINT01'
  const wrapper = mount(LiteratureTab, {
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

describe('LiteratureTab — interactions', () => {
  it('clicking pin button dispatches PATCH', async () => {
    const w = await mountTab()
    const pinButtons = w.findAll('tbody button')
    expect(pinButtons.length).toBeGreaterThan(0)

    // The first column button is the pin toggle. Find the row for item id=1
    // (which is unpinned) and click its pin button.
    const firstPinBtn = w.findAll('tbody tr')[0].find('button')
    await firstPinBtn.trigger('click')
    await flushPromises()

    expect(api.patch).toHaveBeenCalled()
    const [url, body] = api.patch.mock.calls[0]
    expect(url).toMatch(/\/literature\/\d+$/)
    expect(body).toHaveProperty('pinned')
  })

  it('clicking must-read toggles dispatches PATCH', async () => {
    const w = await mountTab()
    // Find the first ⭐/☆ button — it's in the must-read column.
    const allBtns = w.findAll('tbody button')
    const mustReadBtn = allBtns.find(b => /[⭐☆]/.test(b.text()))
    expect(mustReadBtn).toBeTruthy()
    await mustReadBtn.trigger('click')
    await flushPromises()

    expect(api.patch).toHaveBeenCalled()
    const [url, body] = api.patch.mock.calls[0]
    expect(url).toMatch(/\/literature\/\d+$/)
    expect(body).toHaveProperty('must_read')
  })

  it('addManual: requires title and resets form on success', async () => {
    const w = await mountTab()
    // Open manual form
    const addBtn = w.findAll('button').find(b => b.text().includes('Tambah Manual'))
    await addBtn.trigger('click')
    await flushPromises()

    // Save button should be disabled when title is empty
    const saveBtn = w.findAll('button').find(b => b.text() === 'Simpan')
    expect(saveBtn.attributes('disabled')).toBeDefined()

    // Fill title + DOI + URL
    const titleInput = w.find('input[placeholder^="Judul"]')
    await titleInput.setValue('My new paper')
    const doiInput = w.find('input[placeholder="DOI"]')
    await doiInput.setValue('10.1234/abc.567')
    const urlInput = w.find('input[placeholder="URL"]')
    await urlInput.setValue('https://example.org/p')

    // Save now enabled
    expect(saveBtn.attributes('disabled')).toBeUndefined()
    await saveBtn.trigger('click')
    await flushPromises()

    expect(api.post).toHaveBeenCalled()
    const [url, body] = api.post.mock.calls.find(
      ([u]) => u.endsWith('/literature') && !u.endsWith('/from-files')
    ) || []
    expect(body).toBeTruthy()
    expect(body.title).toBe('My new paper')
    expect(body.doi).toBe('10.1234/abc.567')
    expect(body.url).toBe('https://example.org/p')
    // After successful submit, the manual form panel is hidden (showAddManual=false).
    expect(w.find('input[placeholder^="Judul"]').exists()).toBe(false)
  })

  it('deleteItem: confirms via window.confirm and dispatches DELETE', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const w = await mountTab()

    const deleteBtns = w.findAll('button').filter(b => b.text() === '✕')
    expect(deleteBtns.length).toBeGreaterThan(0)
    await deleteBtns[0].trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalled()
    expect(api.delete).toHaveBeenCalled()
    expect(api.delete.mock.calls[0][0]).toMatch(/\/literature\/\d+$/)
    confirmSpy.mockRestore()
  })

  it('deleteItem: window.confirm=false short-circuits without DELETE', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const w = await mountTab()
    const deleteBtns = w.findAll('button').filter(b => b.text() === '✕')
    await deleteBtns[0].trigger('click')
    await flushPromises()

    expect(api.delete).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('filter input narrows table case-insensitively across title/authors/venue/doi', async () => {
    const w = await mountTab()
    expect(w.findAll('tbody tr').length).toBe(2)

    // Filter by author surname (different case)
    await w.find('input[placeholder*="Filter"]').setValue('CAROL')
    await flushPromises()
    let rows = w.findAll('tbody tr').filter(r => r.find('td').exists() &&
      !r.text().includes('Belum ada literatur'))
    expect(rows.length).toBe(1)
    expect(rows[0].text()).toContain('deep learning')

    // Filter by DOI
    await w.find('input[placeholder*="Filter"]').setValue('10.1109')
    await flushPromises()
    rows = w.findAll('tbody tr').filter(r => r.find('td').exists() &&
      !r.text().includes('Belum ada literatur'))
    expect(rows.length).toBe(1)
    expect(rows[0].text()).toContain('reinforcement')

    // Filter by venue substring
    await w.find('input[placeholder*="Filter"]').setValue('nature')
    await flushPromises()
    rows = w.findAll('tbody tr').filter(r => r.find('td').exists() &&
      !r.text().includes('Belum ada literatur'))
    expect(rows.length).toBe(1)
    expect(rows[0].text()).toContain('deep learning')
  })

  it('runSLR error path: when POST rejects, slrRunning resets to false', async () => {
    api.post.mockImplementation(async (url) => {
      if (url.includes('/slr/jobs')) {
        const e = new Error('Boom')
        return Promise.reject(e)
      }
      return { data: {} }
    })

    const w = await mountTab()
    const queryInput = w.find('input[placeholder*="topik"]')
    await queryInput.setValue('reinforcement learning')

    const runBtn = w.findAll('button').find(b =>
      b.text().includes('Jalankan SLR') || b.text().includes('Mencari')
    )
    expect(runBtn).toBeTruthy()
    await runBtn.trigger('click')
    await flushPromises()
    await flushPromises()

    // Button label should NOT be stuck on "Mencari…" — slrRunning must reset.
    // The B-1 fix: after the POST rejects, the input/select must re-enable.
    const labelAfter = w.findAll('button')
      .find(b => b.text().includes('Jalankan SLR') || b.text().includes('Mencari'))
      .text()
    if (labelAfter.includes('Mencari')) {
      // Implementation hasn't been patched — surface a clear failure.
      throw new Error('B-1 fix missing: slrRunning stays true after POST rejection')
    }
    expect(labelAfter).toContain('Jalankan SLR')
  })
})
