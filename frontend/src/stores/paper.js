import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import axios from 'axios'
import api from '../api/index.js'

const API_BASE = '/api'
axios.defaults.timeout = 0

// ─── LocalStorage helpers ─────────────────────────────────────────────────
const LS_PAPER = 'pg_paper'
const LS_JOB = 'pg_job'
const LS_LAST_PAPER_ID = 'pg_last_paper_id'

function lsSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* quota exceeded — ignore */ }
}

function lsGet(key) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : null } catch { return null }
}

function lsRemove(key) {
  try { localStorage.removeItem(key) } catch { /* ignore */ }
}

// ─── Standalone helpers (needed before store init) ────────────────────────
function createEmptyPaper() {
  return {
    journal: 'IEEE',
    title: '',
    authors: [{ name: '', affiliation: '', location: '', email: '' }],
    abstract: '',
    keywords: [],
    sections: [],
    references: [],
    figures: []
  }
}

function normContent(content) {
  if (!content) return []
  if (typeof content === 'string') return content.trim() ? [{ id: 'text', text: content }] : []
  if (!Array.isArray(content)) return []
  return content.map(item => {
    if (typeof item === 'string') return { id: 'text', text: item }
    return { ...item }
  })
}

function fromPaperJsonRaw(json) {
  const p = createEmptyPaper()
  p.journal = (json.journal || json.template || 'IEEE')
  p.title = json.title || ''
  p.authors = (json.authors || []).length ? json.authors : [{ name: '', affiliation: '', location: '', email: '' }]
  p.abstract = json.abstract || ''
  p.keywords = json.keywords || []

  const sKeys = Object.keys(json).filter(k => /^section\d+$/.test(k))
    .sort((a, b) => parseInt(a.replace('section', '')) - parseInt(b.replace('section', '')))

  if (sKeys.length) {
    for (const sKey of sKeys) {
      const sData = json[sKey]
      const sec = { title: sData.title || '', content: normContent(sData.content), subsections: [] }
      const subKeys = Object.keys(sData).filter(k => new RegExp(`^${sKey}[a-z]$`).test(k)).sort()
      for (const sk of subKeys) {
        sec.subsections.push({ title: sData[sk].title || '', content: normContent(sData[sk].content) })
      }
      p.sections.push(sec)
    }
  } else if (Array.isArray(json.sections)) {
    for (const sec of json.sections) {
      const s = { title: sec.title || '', content: normContent(sec.content), subsections: [] }
      for (const sub of (sec.subsections || [])) {
        s.subsections.push({ title: sub.title || '', content: normContent(sub.content) })
      }
      p.sections.push(s)
    }
  }

  if (json.references) {
    if (typeof json.references === 'object' && !Array.isArray(json.references) && json.references.content) {
      p.references = json.references.content || []
    } else if (Array.isArray(json.references)) {
      p.references = json.references.map(r => typeof r === 'string' ? r : (r.text || ''))
    }
  }
  return p
}

function toRomanNum(num) {
  const map = [[1000,'M'],[900,'CM'],[500,'D'],[400,'CD'],[100,'C'],[90,'XC'],[50,'L'],[40,'XL'],[10,'X'],[9,'IX'],[5,'V'],[4,'IV'],[1,'I']]
  let r = ''
  for (const [v, s] of map) { while (num >= v) { r += s; num -= v } }
  return r
}

// ─── Paper Store ──────────────────────────────────────────────────────────
export const usePaperStore = defineStore('paper', () => {
  // Restore paper from localStorage on init (if available)
  const _savedPaper = lsGet(LS_PAPER)
  const paper = ref(_savedPaper ? fromPaperJsonRaw(_savedPaper) : createEmptyPaper())

  // Current paper DB id (null = unsaved new paper)
  const currentPaperId = ref(null)
  // Paper images for the current paper
  const paperImages = ref([])

  const loading = ref(false)
  const aiLoading = ref(false)
  const aiLoadingMessage = ref('')
  const toast = ref({ show: false, message: '', type: 'info' })

  const availableJournals = ref([])
  const journalsLoading = ref(false)

  // ─── AI proposed changes (pending review) ─────────────────────────────
  // Each entry: { id, kind, before, after, payload, status: 'pending'|'accepted'|'rejected' }
  const pendingChanges = ref([])
  let _pendId = 0

  function _nextPendingId() {
    _pendId += 1
    return `pend-${Date.now()}-${_pendId}`
  }

  function pushProposal(proposal) {
    if (!proposal || !proposal.kind) return null
    const before = _captureBefore(proposal)
    const entry = {
      id: _nextPendingId(),
      kind: proposal.kind,
      payload: proposal,
      before,
      after: _previewAfter(proposal),
      status: 'pending',
      created_at: new Date().toISOString(),
    }
    pendingChanges.value.push(entry)

    // Auto-apply when the target field/section/reference is still empty (initial
    // fill). The user explicitly asked the AI to write it — making them click
    // "Accept" again in Preview is friction, and was causing whole sections to
    // get silently lost. Edits that overwrite existing content still go through
    // the diff-review flow.
    if (_isInitialFill(proposal)) {
      acceptProposal(entry.id)
    }

    return entry
  }

  function _isInitialFill(p) {
    const paper_ = paper.value
    switch (p.kind) {
      case 'title':    return !(paper_.title || '').trim()
      case 'abstract': return !(paper_.abstract || '').trim()
      case 'keywords': return !(paper_.keywords || []).length
      case 'section': {
        const idx = p.section_index
        if (idx === null || idx === undefined) return true
        const s = paper_.sections?.[idx]
        if (!s) return true
        return !_sectionContentToText(s.content).trim() && !(s.title || '').trim()
      }
      case 'reference': {
        const idx = p.ref_index
        if (idx === null || idx === undefined) return true
        const r = paper_.references?.[idx]
        return !r || !String(r).trim()
      }
      default: return false
    }
  }

  function _captureBefore(p) {
    const paper_ = paper.value
    switch (p.kind) {
      case 'title': return { title: paper_.title || '' }
      case 'abstract': return { abstract: paper_.abstract || '' }
      case 'keywords': return { keywords: [...(paper_.keywords || [])] }
      case 'journal': return { journal: paper_.journal || 'IEEE' }
      case 'section': {
        const idx = p.section_index
        if (idx === null || idx === undefined || idx >= (paper_.sections || []).length) {
          return { section: null, index: null }
        }
        const s = paper_.sections[idx]
        return {
          index: idx,
          section: {
            title: s.title || '',
            content: _sectionContentToText(s.content),
          },
        }
      }
      case 'reference': {
        const idx = p.ref_index
        if (idx === null || idx === undefined || idx >= (paper_.references || []).length) {
          return { reference: null, index: null }
        }
        return { index: idx, reference: paper_.references[idx] || '' }
      }
      case 'export_docx': return {}
      default: return {}
    }
  }

  function _previewAfter(p) {
    switch (p.kind) {
      case 'title': return { title: p.value || '' }
      case 'abstract': return { abstract: p.value || '' }
      case 'keywords': return { keywords: [...(p.value || [])] }
      case 'journal': return { journal: p.value || '' }
      case 'section': return {
        index: p.section_index,
        section: { title: p.title || '', content: p.content || '' },
      }
      case 'reference': return { index: p.ref_index, reference: p.value || '' }
      case 'export_docx': return {}
      default: return {}
    }
  }

  function _sectionContentToText(content) {
    if (!content) return ''
    if (typeof content === 'string') return content
    if (!Array.isArray(content)) return ''
    return content
      .map(it => (it && it.id === 'text' ? (it.text || '') : ''))
      .filter(Boolean)
      .join('\n\n')
  }

  function _textToSectionContent(text) {
    if (!text) return [{ id: 'text', text: '' }]
    return [{ id: 'text', text: String(text) }]
  }

  async function acceptProposal(id) {
    const idx = pendingChanges.value.findIndex(p => p.id === id)
    if (idx < 0) return
    const change = pendingChanges.value[idx]
    if (change.status !== 'pending') return
    const p = change.payload
    try {
      switch (p.kind) {
        case 'title': paper.value.title = p.value || ''; break
        case 'abstract': paper.value.abstract = p.value || ''; break
        case 'keywords': paper.value.keywords = [...(p.value || [])]; break
        case 'journal':
          if (p.value) paper.value.journal = p.value
          break
        case 'section': {
          const sIdx = p.section_index
          const sec = {
            title: p.title || '',
            content: _textToSectionContent(p.content),
            subsections: [],
          }
          if (sIdx === null || sIdx === undefined || sIdx >= paper.value.sections.length) {
            paper.value.sections.push(sec)
          } else {
            const cur = paper.value.sections[sIdx]
            paper.value.sections[sIdx] = {
              title: sec.title,
              content: sec.content,
              subsections: cur.subsections || [],
            }
          }
          break
        }
        case 'reference': {
          const rIdx = p.ref_index
          if (rIdx === null || rIdx === undefined || rIdx >= paper.value.references.length) {
            paper.value.references.push(p.value || '')
          } else {
            paper.value.references[rIdx] = p.value || ''
          }
          break
        }
        case 'export_docx':
          await exportDocx()
          break
      }
      change.status = 'accepted'
      showToast('Perubahan diterima', 'success')
    } catch (e) {
      showToast('Apply failed: ' + e.message, 'error')
    }
  }

  function rejectProposal(id) {
    const change = pendingChanges.value.find(p => p.id === id)
    if (change && change.status === 'pending') {
      change.status = 'rejected'
      showToast('Perubahan ditolak', 'info')
    }
  }

  async function acceptAllProposals() {
    const ids = pendingChanges.value.filter(p => p.status === 'pending').map(p => p.id)
    for (const id of ids) await acceptProposal(id)
  }

  function rejectAllProposals() {
    for (const p of pendingChanges.value) {
      if (p.status === 'pending') p.status = 'rejected'
    }
    showToast('Semua perubahan ditolak', 'info')
  }

  function clearResolvedProposals() {
    pendingChanges.value = pendingChanges.value.filter(p => p.status === 'pending')
  }

  /**
   * Apply a proposal immediately without going through the pending review flow.
   * Used for low-risk operational changes the AI requests (journal switch, DOCX export).
   */
  async function applyImmediate(proposal) {
    if (!proposal || !proposal.kind) return
    try {
      switch (proposal.kind) {
        case 'journal':
          if (proposal.value) {
            paper.value.journal = proposal.value
            showToast(`Jurnal diset ke ${proposal.value}`, 'success')
          }
          break
        case 'export_docx':
          await exportDocx()
          break
      }
    } catch (e) {
      showToast('Apply failed: ' + e.message, 'error')
    }
  }

  const pendingCount = computed(() =>
    pendingChanges.value.filter(p => p.status === 'pending').length
  )

  async function fetchJournals() {
    if (availableJournals.value.length) return availableJournals.value
    journalsLoading.value = true
    try {
      const res = await api.get(`${API_BASE}/journals`, { timeout: 10000 })
      availableJournals.value = (res.data?.journals || []).filter(Boolean)
      if (!availableJournals.value.length) availableJournals.value = ['IEEE']
    } catch {
      // Fallback (minimal) — backend should normally provide the full list
      availableJournals.value = ['IEEE', 'MEV', 'ULTIMACOMP']
    } finally {
      journalsLoading.value = false
    }

    const current = (paper.value.journal || 'IEEE')
    if (availableJournals.value.length && !availableJournals.value.includes(current)) {
      paper.value.journal = availableJournals.value[0]
    }
    return availableJournals.value
  }

  // ─── Auto-save paper to localStorage on every deep change ──────────────
  watch(paper, (val) => {
    try { lsSet(LS_PAPER, toPaperJson()) } catch { /* ignore */ }
  }, { deep: true })

  function showToast(message, type = 'info') {
    toast.value = { show: true, message, type }
    setTimeout(() => { toast.value.show = false }, 3500)
  }

  // ─── Auto Numbering ────────────────────────────────────────────────────
  const numbering = computed(() => {
    let imgNum = 1, tblNum = 1, eqNum = 1
    const map = new Map()
    function walk(items) {
      for (const item of (items || [])) {
        if (item.id === 'gambar') map.set(item, { num: imgNum++, label: `${imgNum - 1}` })
        else if (item.id === 'tabel') map.set(item, { num: tblNum++, label: toRomanNum(tblNum - 1) })
        else if (item.id === 'rumus') map.set(item, { num: eqNum++, label: `${eqNum - 1}` })
      }
    }
    for (const sec of paper.value.sections) {
      walk(sec.content)
      for (const sub of (sec.subsections || [])) walk(sub.content)
    }
    return map
  })

  function getItemNumber(item) { return numbering.value.get(item) || {} }

  // ─── Convert TO paper.json format ──────────────────────────────────────
  function toPaperJson() {
    const p = paper.value
    const json = { journal: p.journal || 'IEEE', title: p.title, authors: p.authors, abstract: p.abstract, keywords: p.keywords }
    let imgNum = 1, tblNum = 1, eqNum = 1

    function numContent(items) {
      return (items || []).map(item => {
        const c = { ...item }
        if (item.id === 'gambar') c.ImageNumber = String(imgNum++)
        if (item.id === 'tabel') c.TableNumber = toRomanNum(tblNum++)
        if (item.id === 'rumus') c.FormulaNumber = String(eqNum++)
        return c
      })
    }

    p.sections.forEach((sec, sIdx) => {
      const sKey = `section${sIdx + 1}`
      const sObj = { title: sec.title, content: numContent(sec.content) }
      ;(sec.subsections || []).forEach((sub, subIdx) => {
        const subKey = `${sKey}${String.fromCharCode(97 + subIdx)}`
        sObj[subKey] = { title: sub.title, content: numContent(sub.content) }
      })
      json[sKey] = sObj
    })

    json.references = {
      number: toRomanNum(p.sections.length + 1),
      title: 'REFERENCES',
      content: p.references
    }
    return json
  }

  // ─── Convert FROM paper.json or legacy format ─────────────────────────
  function fromPaperJson(json) { return fromPaperJsonRaw(json) }

  // ─── CRUD: Sections ───────────────────────────────────────────────────
  function addSection() {
    paper.value.sections.push({ title: '', content: [{ id: 'text', text: '' }], subsections: [] })
  }
  function removeSection(idx) { paper.value.sections.splice(idx, 1) }

  function addSubsection(sIdx) {
    paper.value.sections[sIdx].subsections.push({ title: '', content: [{ id: 'text', text: '' }] })
  }
  function removeSubsection(sIdx, subIdx) { paper.value.sections[sIdx].subsections.splice(subIdx, 1) }

  function addContent(container, type) {
    const items = {
      text: { id: 'text', text: '' },
      gambar: { id: 'gambar', Title: '', Path: '', Prompt: '' },
      tabel: { id: 'tabel', Title: '', Headers: ['Col 1', 'Col 2'], Rows: [['', '']] },
      rumus: { id: 'rumus', latex: '' }
    }
    if (items[type]) container.push({ ...items[type] })
  }
  function removeContent(container, idx) { container.splice(idx, 1) }
  function moveContent(container, idx, dir) {
    const newIdx = idx + dir
    if (newIdx < 0 || newIdx >= container.length) return
    const tmp = container[idx]
    container.splice(idx, 1)
    container.splice(newIdx, 0, tmp)
  }

  // ─── CRUD: Authors ────────────────────────────────────────────────────
  function addAuthor() { paper.value.authors.push({ name: '', affiliation: '', location: '', email: '' }) }
  function removeAuthor(idx) { if (paper.value.authors.length > 1) paper.value.authors.splice(idx, 1) }

  // ─── CRUD: Keywords ───────────────────────────────────────────────────
  function addKeyword(kw) { if (kw && !paper.value.keywords.includes(kw)) paper.value.keywords.push(kw) }
  function removeKeyword(idx) { paper.value.keywords.splice(idx, 1) }

  // ─── CRUD: References ─────────────────────────────────────────────────
  function addReference() { paper.value.references.push('') }
  function removeReference(idx) { paper.value.references.splice(idx, 1) }

  // ─── CRUD: Figure helpers ──────────────────────────────────────────────
  function addFigure() {
    if (!paper.value.figures) paper.value.figures = []
    paper.value.figures.push({ caption: '', hasImage: false, filename: '', url: '' })
  }
  function removeFigure(idx) { paper.value.figures.splice(idx, 1) }

  // ─── CRUD: Table helpers ──────────────────────────────────────────────
  function addTableRow(item) { item.Rows.push(new Array(item.Headers.length).fill('')) }
  function removeTableRow(item, rIdx) { item.Rows.splice(rIdx, 1) }
  function addTableCol(item) { item.Headers.push(`Col ${item.Headers.length + 1}`); item.Rows.forEach(r => r.push('')) }
  function removeTableCol(item, cIdx) {
    if (item.Headers.length > 1) { item.Headers.splice(cIdx, 1); item.Rows.forEach(r => r.splice(cIdx, 1)) }
  }

  // ─── Import / Export ──────────────────────────────────────────────────
  function newPaper() {
    paper.value = createEmptyPaper()
    currentPaperId.value = null
    lsRemove(LS_PAPER)
    lsRemove(LS_JOB)
  }

  function uploadJson(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        try {
          const data = JSON.parse(e.target.result)
          paper.value = fromPaperJsonRaw(data)
          showToast('Paper loaded from JSON!', 'success')
          resolve(true)
        } catch (err) { showToast('Invalid JSON: ' + err.message, 'error'); reject(err) }
      }
      reader.readAsText(file)
    })
  }

  function downloadJson() {
    const data = JSON.stringify(toPaperJson(), null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(paper.value.title || 'paper').replace(/[^a-zA-Z0-9_\-]/g, '_').slice(0, 60)}.json`
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
    showToast('JSON downloaded!', 'success')
  }

  async function exportDocx() {
    try {
      loading.value = true
      const journal = (paper.value.journal || 'IEEE').trim() || 'IEEE'
      const res = await api.post(`${API_BASE}/export`, { journal, paper: toPaperJson() }, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `${journal}_${(paper.value.title || 'paper').replace(/[^a-zA-Z0-9_\-]/g, '_').slice(0, 60)}.docx`
      document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(url)
      showToast('DOCX exported!', 'success')
    } catch (err) {
      showToast('Export failed: ' + (err.response?.data?.error || err.message), 'error')
    } finally { loading.value = false }
  }

  // ─── AI ───────────────────────────────────────────────────────────────

  /** Shared polling loop — used by both new generation and resume-after-refresh */
  async function _pollJob(jobId, t0) {
    while (true) {
      await new Promise(r => setTimeout(r, 3000))
      const el = Math.round((Date.now() - t0) / 1000)
      const m = Math.floor(el / 60), s = el % 60
      aiLoadingMessage.value = `AI sedang membuat paper... (${m > 0 ? m + 'm ' : ''}${s}s)`
      let poll
      try { poll = await api.get(`${API_BASE}/job/${jobId}`, { timeout: 10000 }) } catch { continue }
      if (poll.data.status === 'done') {
        paper.value = fromPaperJsonRaw(poll.data.paper)
        lsRemove(LS_JOB)
        showToast('Paper berhasil dibuat!', 'success')
        return true
      }
      if (poll.data.status === 'error') throw new Error(poll.data.error || 'Failed')
      if (Date.now() - t0 > 25 * 60 * 1000) throw new Error('Timeout: > 25 menit')
    }
  }

  async function aiGenerateFullPaper(prompt, { topic, style, pdfTexts } = {}) {
    try {
      aiLoading.value = true
      aiLoadingMessage.value = 'Menghubungi AI...'
      const payload = { prompt }
      if (topic) payload.topic = topic
      if (style) payload.style = style
      if (pdfTexts && pdfTexts.length) payload.pdf_texts = pdfTexts
      const startRes = await api.post(`${API_BASE}/generate-full`, payload, { timeout: 15000 })
      if (!startRes.data?.job_id) throw new Error(startRes.data?.error || 'No job_id')
      const jobId = startRes.data.job_id
      lsSet(LS_JOB, { jobId, t0: Date.now() })
      return await _pollJob(jobId, Date.now())
    } catch (err) {
      showToast('AI Error: ' + err.message, 'error')
      return false
    } finally { aiLoading.value = false; aiLoadingMessage.value = '' }
  }

  /**
   * Attach to a generate-full job that was started by the chat AI tool. The
   * regular spinner + polling kicks in, and when the job finishes the result
   * lands in the editor — same path as a manual /api/generate-full call.
   */
  async function attachAiJob(jobId, prompt = '') {
    if (!jobId) return false
    const t0 = Date.now()
    lsSet(LS_JOB, { jobId, t0 })
    aiLoading.value = true
    aiLoadingMessage.value = prompt
      ? `AI sedang membuat paper: "${prompt.slice(0, 50)}${prompt.length > 50 ? '…' : ''}"`
      : 'AI sedang membuat paper...'
    try {
      return await _pollJob(jobId, t0)
    } catch (err) {
      showToast('AI Error: ' + err.message, 'error')
      return false
    } finally {
      aiLoading.value = false
      aiLoadingMessage.value = ''
    }
  }

  /**
   * Call this on app mount. If a job was in-flight when the page was refreshed,
   * resume polling and restore the result automatically.
   */
  async function resumePendingJob() {
    const jobInfo = lsGet(LS_JOB)
    if (!jobInfo) return
    const { jobId, t0 } = jobInfo || {}
    if (!jobId || !t0) { lsRemove(LS_JOB); return }
    if (Date.now() - t0 > 25 * 60 * 1000) { lsRemove(LS_JOB); return }
    try {
      const check = await api.get(`${API_BASE}/job/${jobId}`, { timeout: 8000 })
      if (check.data.status === 'error' || !check.data.status) { lsRemove(LS_JOB); return }
      if (check.data.status === 'done') {
        paper.value = fromPaperJsonRaw(check.data.paper)
        lsRemove(LS_JOB)
        showToast('Paper dipulihkan dari proses sebelumnya!', 'success')
        return
      }
    } catch { lsRemove(LS_JOB); return }

    aiLoading.value = true
    aiLoadingMessage.value = 'Melanjutkan proses AI...'
    try {
      await _pollJob(jobId, t0)
    } catch (err) {
      showToast('AI Error (resumed): ' + err.message, 'error')
    } finally { aiLoading.value = false; aiLoadingMessage.value = '' }
  }

  // ─── DB Save/Load ─────────────────────────────────────────────────────
  async function savePaperToDb(silent = false) {
    try {
      if (!silent) loading.value = true
      const paperData = { ...toPaperJson(), id: currentPaperId.value || undefined }
      const res = await api.post(`${API_BASE}/papers`, paperData)
      if (res.data.id && !currentPaperId.value) {
        currentPaperId.value = res.data.id
      }
      if (currentPaperId.value) {
        lsSet(LS_LAST_PAPER_ID, currentPaperId.value)
      }
      if (!silent) showToast('Paper saved!', 'success')
      return res.data.id
    } catch (err) {
      if (!silent) showToast('Save failed: ' + (err.response?.data?.error || err.message), 'error')
      return null
    } finally { if (!silent) loading.value = false }
  }

  async function loadPaperFromDb(paperId) {
    try {
      loading.value = true
      const res = await api.get(`${API_BASE}/papers/${paperId}`)
      paper.value = fromPaperJsonRaw(res.data)
      currentPaperId.value = paperId
      lsSet(LS_LAST_PAPER_ID, paperId)
      await loadPaperImages(paperId)
      return true
    } catch (err) {
      showToast('Load failed: ' + (err.response?.data?.error || err.message), 'error')
      return false
    } finally { loading.value = false }
  }

  async function loadPaperImages(paperId) {
    try {
      const res = await api.get(`${API_BASE}/papers/${paperId}/images`)
      paperImages.value = res.data.images || []
    } catch { paperImages.value = [] }
  }

  async function uploadImage(figureIndex, file) {
    try {
      if (!currentPaperId.value) {
        // Must save paper first to get an ID
        const id = await savePaperToDb()
        if (!id) return
      }
      const formData = new FormData()
      formData.append('file', file)
      const res = await api.post(`${API_BASE}/papers/${currentPaperId.value}/images`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      const img = res.data.image
      paperImages.value.push(img)
      // Auto-assign to figure if figureIndex is provided
      if (figureIndex !== undefined && paper.value.figures?.[figureIndex]) {
        paper.value.figures[figureIndex].filename = img.filename
        paper.value.figures[figureIndex].url = img.url
      }
      showToast('Image uploaded!', 'success')
      return img
    } catch (err) {
      showToast('Upload failed: ' + (err.response?.data?.error || err.message), 'error')
      return null
    }
  }

  async function deletePaperImage(imageId) {
    try {
      await api.delete(`${API_BASE}/papers/${currentPaperId.value}/images/${imageId}`)
      paperImages.value = paperImages.value.filter(img => img.id !== imageId)
      showToast('Image deleted', 'success')
    } catch (err) {
      showToast('Delete failed: ' + (err.response?.data?.error || err.message), 'error')
    }
  }

  // ─── Helpers ──────────────────────────────────────────────────────────
  function toRoman(num) { return toRomanNum(num) }

  function getLastPaperId() {
    return lsGet(LS_LAST_PAPER_ID)
  }

  return {
    paper, loading, aiLoading, aiLoadingMessage, toast,
    currentPaperId, paperImages,
    availableJournals, journalsLoading, fetchJournals,
    pendingChanges, pendingCount,
    pushProposal, acceptProposal, rejectProposal,
    acceptAllProposals, rejectAllProposals, clearResolvedProposals,
    applyImmediate, attachAiJob,
    numbering, getItemNumber, toPaperJson, fromPaperJson,
    addSection, removeSection, addSubsection, removeSubsection,
    addContent, removeContent, moveContent,
    addAuthor, removeAuthor, addKeyword, removeKeyword,
    addReference, removeReference,
    addFigure, removeFigure,
    addTableRow, removeTableRow, addTableCol, removeTableCol,
    newPaper, uploadJson, downloadJson, exportDocx,
    aiGenerateFullPaper, resumePendingJob,
    savePaperToDb, loadPaperFromDb, loadPaperImages,
    uploadImage, deletePaperImage,
    showToast, toRoman, getLastPaperId,
    apiGet: (url) => api.get(url),
    apiUploadPdfs: (formData) => api.post(`${API_BASE}/upload-pdfs`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }),
  }
})
