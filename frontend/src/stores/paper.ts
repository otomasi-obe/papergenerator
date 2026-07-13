// @ts-nocheck
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import api from '../api/index.js'

const API_BASE = '/api'

// ─── LocalStorage helpers ─────────────────────────────────────────────────
const LS_PAPER = 'pg_paper'
const LS_JOB = 'pg_job'
const LS_LAST_PAPER_ID = 'pg_last_paper_id'

function lsSet(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* quota exceeded — ignore */
  }
}

function lsGet(key) {
  try {
    const v = localStorage.getItem(key)
    return v ? JSON.parse(v) : null
  } catch {
    return null
  }
}

function lsRemove(key) {
  try {
    localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}

// ─── Standalone helpers (needed before store init) ────────────────────────

// Language templates loaded from backend prompt files
let _langTemplates: Record<string, any> = {}

async function _fetchLangTemplate(lang: string): Promise<any | null> {
  if (_langTemplates[lang]) return _langTemplates[lang]
  try {
    const res = await fetch(`/api/papers/template/${lang}`)
    if (res.ok) {
      const data = await res.json()
      _langTemplates[lang] = data
      return data
    }
  } catch { /* ignore */ }
  return null
}

function createEmptyPaper() {
  return {
    journal: 'IEEE',
    citation_style: 'ieee',
    language: 'id',
    title: '',
    authors: [{ name: '', affiliation: '', location: '', email: '' }],
    abstract: '',
    keywords: [],
    sections: [],
    references: [],
    figures: [],
  }
}

function normContent(content) {
  if (!content) return []
  if (typeof content === 'string') return content.trim() ? [{ id: 'text', text: content }] : []
  if (!Array.isArray(content)) return []
  return content.map((item) => {
    if (typeof item === 'string') return { id: 'text', text: item }
    return { ...item }
  })
}

// Format a structured reference object (from AI output) into a display string.
// Handles journal, conference, book, book_chapter, thesis, website types.
// Uses a generic format that works across citation styles (author, year, title, venue).
function _formatStructuredRef(ref: any): string {
  if (!ref || typeof ref !== 'object') return ''
  const authors = Array.isArray(ref.authors) ? ref.authors.join(', ') : (ref.authors || '')
  const year = ref.year || ''
  const title = ref.title || ''
  const type = ref.type || ''
  const journal = ref.journal || ''
  const conference = ref.conference || ''
  const volume = ref.volume || ''
  const issue = ref.issue || ''
  const pages = ref.pages || ''
  const doi = ref.doi || ''
  const publisher = ref.publisher || ''
  const location = ref.location || ''
  const url = ref.url || ''
  const accessed = ref.accessed || ''
  const institution = ref.institution || ''
  const bookTitle = ref.book_title || ''
  const editors = Array.isArray(ref.editors) ? ref.editors.join(', ') : (ref.editors || '')

  if (!title && !authors) return ''

  let parts: string[] = []

  // Authors
  if (authors) parts.push(authors)

  // Year in parentheses
  if (year) parts.push(`(${year})`)

  // Title
  if (title) {
    if (type === 'journal' || type === 'conference') {
      parts.push(`"${title}"`)
    } else {
      parts.push(title)
    }
  }

  // Venue/journal
  if (type === 'journal' && journal) {
    let venue = journal
    if (volume) venue += `, vol. ${volume}`
    if (issue) venue += `, no. ${issue}`
    if (pages) venue += `, pp. ${pages}`
    parts.push(venue)
  } else if (type === 'conference' && conference) {
    let venue = `in ${conference}`
    if (pages) venue += `, pp. ${pages}`
    parts.push(venue)
  } else if (type === 'book') {
    if (location && publisher) parts.push(`${location}: ${publisher}`)
    else if (publisher) parts.push(publisher)
    if (pages) parts.push(`pp. ${pages}`)
  } else if (type === 'book_chapter') {
    if (bookTitle) {
      let ch = `in ${bookTitle}`
      if (editors) ch += `, ${editors}, Eds.`
      parts.push(ch)
    }
    if (publisher) parts.push(publisher)
    if (pages) parts.push(`pp. ${pages}`)
  } else if (type === 'thesis') {
    if (institution) parts.push(institution)
    parts.push('Thesis')
  } else if (type === 'website' && url) {
    parts.push(`[Online]. Available: ${url}`)
    if (accessed) parts.push(`(Accessed: ${accessed})`)
  }

  // DOI
  if (doi) parts.push(`doi: ${doi}`)

  return parts.join('. ').replace(/\.\./g, '.') + '.'
}

function fromPaperJsonRaw(json) {
  if (!json || typeof json !== 'object') {
    return createEmptyPaper()
  }
  const p = createEmptyPaper()
  p.journal = json.journal || json.template || 'IEEE'
  p.citation_style = json.citation_style || 'ieee'
  p.language = json.language || 'id'
  p.title = json.title || ''
  p.authors = (json.authors || []).length
    ? json.authors
    : [{ name: '', affiliation: '', location: '', email: '' }]
  p.abstract = json.abstract || ''
  p.keywords = json.keywords || []

  const sKeys = Object.keys(json)
    .filter((k) => /^section\d+$/.test(k))
    .sort((a, b) => parseInt(a.replace('section', '')) - parseInt(b.replace('section', '')))

  if (sKeys.length) {
    for (const sKey of sKeys) {
      const sData = json[sKey]
      const sec = { title: sData.title || '', content: normContent(sData.content), subsections: [] }
      const subKeys = Object.keys(sData)
        .filter((k) => new RegExp(`^${sKey}[a-z]$`).test(k))
        .sort()
      for (const sk of subKeys) {
        sec.subsections.push({
          title: sData[sk].title || '',
          content: normContent(sData[sk].content),
        })
      }
      p.sections.push(sec)
    }
  } else if (Array.isArray(json.sections)) {
    for (const sec of json.sections) {
      const s = { title: sec.title || '', content: normContent(sec.content), subsections: [] }
      for (const sub of sec.subsections || []) {
        s.subsections.push({ title: sub.title || '', content: normContent(sub.content) })
      }
      p.sections.push(s)
    }
  }

  if (json.references) {
    if (
      typeof json.references === 'object' &&
      !Array.isArray(json.references) &&
      (json.references.content || json.references.items)
    ) {
      // Dict-wrapped: { title, content: [...] } or { title, items: [...] }
      p.references = json.references.content || json.references.items || []
    } else if (Array.isArray(json.references)) {
      // Keep structured objects as-is for downstream style formatting.
      // Display components format them via _formatStructuredRef.
      p.references = json.references.map((r) => {
        if (typeof r === 'string') return r
        if (r.text) return r.text
        // Structured reference object — keep the full object for style reformatting
        return r
      })
    }
  }
  // Restore figure metadata if persisted
  if (Array.isArray(json.figures)) {
    p.figures = json.figures.map((f) => ({
      caption: f.caption || '',
      hasImage: !!f.hasImage,
      filename: f.filename || '',
      url: f.url || '',
    }))
  }
  return p
}

function toRomanNum(num) {
  const map = [
    [1000, 'M'],
    [900, 'CM'],
    [500, 'D'],
    [400, 'CD'],
    [100, 'C'],
    [90, 'XC'],
    [50, 'L'],
    [40, 'XL'],
    [10, 'X'],
    [9, 'IX'],
    [5, 'V'],
    [4, 'IV'],
    [1, 'I'],
  ]
  let r = ''
  for (const [v, s] of map) {
    while (num >= v) {
      r += s
      num -= v
    }
  }
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
  // Charts generated from the Data/Charts tab (usable as figure sources)
  const paperCharts = ref([])

  const loading = ref(false)
  const aiLoading = ref(false)
  const aiLoadingMessage = ref('')
  const toast = ref({ show: false, message: '', type: 'info' })

  // ─── Undo/Redo State Management ───────────────────────────────────────
  const undoStack = ref([])
  const redoStack = ref([])
  const MAX_HISTORY = 50
  let isUndoRedoOperation = false

  function recordChange(actionName = 'edit') {
    // Don't record during undo/redo operations
    if (isUndoRedoOperation) return

    // Create a deep copy of the current paper state
    const snapshot = JSON.parse(JSON.stringify(paper.value))

    undoStack.value.push({
      state: snapshot,
      action: actionName,
      timestamp: Date.now()
    })

    // Limit stack size to MAX_HISTORY
    if (undoStack.value.length > MAX_HISTORY) {
      undoStack.value.shift()
    }

    // Clear redo stack when a new change is made
    redoStack.value = []
  }

  function undo() {
    if (undoStack.value.length === 0) {
      showToast('Nothing to undo', 'info')
      return false
    }

    isUndoRedoOperation = true

    // Save current state to redo stack
    const currentSnapshot = JSON.parse(JSON.stringify(paper.value))
    redoStack.value.push({
      state: currentSnapshot,
      timestamp: Date.now()
    })

    // Limit redo stack size
    if (redoStack.value.length > MAX_HISTORY) {
      redoStack.value.shift()
    }

    // Restore previous state
    const previousState = undoStack.value.pop()
    paper.value = JSON.parse(JSON.stringify(previousState.state))

    isUndoRedoOperation = false
    showToast(`Undone: ${previousState.action}`, 'success')
    return true
  }

  function redo() {
    if (redoStack.value.length === 0) {
      showToast('Nothing to redo', 'info')
      return false
    }

    isUndoRedoOperation = true

    // Save current state to undo stack
    const currentSnapshot = JSON.parse(JSON.stringify(paper.value))
    undoStack.value.push({
      state: currentSnapshot,
      action: 'redo',
      timestamp: Date.now()
    })

    // Limit undo stack size
    if (undoStack.value.length > MAX_HISTORY) {
      undoStack.value.shift()
    }

    // Restore next state
    const nextState = redoStack.value.pop()
    paper.value = JSON.parse(JSON.stringify(nextState.state))

    isUndoRedoOperation = false
    showToast('Redone', 'success')
    return true
  }

  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

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
      case 'title':
        return !(paper_.title || '').trim()
      case 'abstract':
        return !(paper_.abstract || '').trim()
      case 'keywords':
        return !(paper_.keywords || []).length
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
      default:
        return false
    }
  }

  function _captureBefore(p) {
    const paper_ = paper.value
    switch (p.kind) {
      case 'title':
        return { title: paper_.title || '' }
      case 'abstract':
        return { abstract: paper_.abstract || '' }
      case 'keywords':
        return { keywords: [...(paper_.keywords || [])] }
      case 'journal':
        return { journal: paper_.journal || 'IEEE' }
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
      case 'export_docx':
        return {}
      default:
        return {}
    }
  }

  function _previewAfter(p) {
    switch (p.kind) {
      case 'title':
        return { title: p.value || '' }
      case 'abstract':
        return { abstract: p.value || '' }
      case 'keywords':
        return { keywords: [...(p.value || [])] }
      case 'journal':
        return { journal: p.value || '' }
      case 'section':
        return {
          index: p.section_index,
          section: { title: p.title || '', content: p.content || '' },
        }
      case 'reference':
        return { index: p.ref_index, reference: p.value || '' }
      case 'export_docx':
        return {}
      default:
        return {}
    }
  }

  function _sectionContentToText(content) {
    if (!content) return ''
    if (typeof content === 'string') return content
    if (!Array.isArray(content)) return ''
    return content
      .map((it) => (it && it.id === 'text' ? it.text || '' : ''))
      .filter(Boolean)
      .join('\n\n')
  }

  function _textToSectionContent(text) {
    if (!text) return [{ id: 'text', text: '' }]
    return [{ id: 'text', text: String(text) }]
  }

  async function acceptProposal(id) {
    const idx = pendingChanges.value.findIndex((p) => p.id === id)
    if (idx < 0) return
    const change = pendingChanges.value[idx]
    if (change.status !== 'pending') return
    const p = change.payload
    try {
      switch (p.kind) {
        case 'title':
          paper.value.title = p.value || ''
          break
        case 'abstract':
          paper.value.abstract = p.value || ''
          break
        case 'keywords':
          paper.value.keywords = [...(p.value || [])]
          break
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
    const change = pendingChanges.value.find((p) => p.id === id)
    if (change && change.status === 'pending') {
      change.status = 'rejected'
      showToast('Perubahan ditolak', 'info')
    }
  }

  async function acceptAllProposals() {
    const ids = pendingChanges.value.filter((p) => p.status === 'pending').map((p) => p.id)
    for (const id of ids) await acceptProposal(id)
  }

  function rejectAllProposals() {
    for (const p of pendingChanges.value) {
      if (p.status === 'pending') p.status = 'rejected'
    }
    showToast('Semua perubahan ditolak', 'info')
  }

  function clearResolvedProposals() {
    pendingChanges.value = pendingChanges.value.filter((p) => p.status === 'pending')
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

  // ─── Revisi (Paraphrase / FixGrammar / Translate) apply helpers ───────
  // These are called by RevisiProposalCard.vue when the user accepts an
  // AI-proposed rewrite. They mutate the paper in place and trigger an
  // autosave so the change is persisted.

  async function replaceContent(sIdx, cIdx, newText) {
    const sec = paper.value.sections?.[sIdx]
    if (!sec) throw new Error('Section tidak ditemukan')
    if (!Array.isArray(sec.content)) sec.content = []
    const item = sec.content[cIdx]
    if (!item) throw new Error('Paragraph tidak ditemukan')
    sec.content[cIdx] = { ...item, id: item.id || 'text', text: String(newText ?? '') }
    if (currentPaperId.value) {
      try {
        await savePaperToDb(true)
      } catch {
        /* ignore — local watcher persists too */
      }
    }
    showToast('Paragraph diperbarui', 'success')
  }

  async function replaceSectionText(sIdx, payload) {
    const sec = paper.value.sections?.[sIdx]
    if (!sec) throw new Error('Section tidak ditemukan')
    if (typeof payload === 'string') {
      sec.content = _textToSectionContent(payload)
    } else if (payload && typeof payload === 'object') {
      if (payload.title !== undefined) sec.title = payload.title || sec.title
      if (payload.content !== undefined) {
        sec.content =
          typeof payload.content === 'string'
            ? _textToSectionContent(payload.content)
            : normContent(payload.content)
      }
      if (Array.isArray(payload.subsections)) sec.subsections = payload.subsections
    } else {
      throw new Error('Payload section tidak dikenali')
    }
    if (currentPaperId.value) {
      try {
        await savePaperToDb(true)
      } catch {
        /* ignore */
      }
    }
    showToast('Section diperbarui', 'success')
  }

  async function replaceWhole(payload) {
    if (typeof payload === 'string') {
      // Fallback: drop into the first section's first paragraph.
      if (!paper.value.sections.length) addSection()
      const sec = paper.value.sections[0]
      if (!Array.isArray(sec.content) || !sec.content.length) {
        sec.content = [{ id: 'text', text: '' }]
      }
      sec.content[0] = { ...sec.content[0], id: sec.content[0].id || 'text', text: payload }
    } else if (payload && typeof payload === 'object') {
      if (payload.sections || payload.title || payload.abstract) {
        paper.value = fromPaperJsonRaw(payload)
      } else {
        Object.assign(paper.value, payload)
      }
    } else {
      throw new Error('Payload paper tidak dikenali')
    }
    if (currentPaperId.value) {
      try {
        await savePaperToDb(true)
      } catch {
        /* ignore */
      }
    }
    showToast('Paper diperbarui', 'success')
  }

  const pendingCount = computed(
    () => pendingChanges.value.filter((p) => p.status === 'pending').length
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

    const current = paper.value.journal || 'IEEE'
    if (availableJournals.value.length) {
      // Handle MDPI sub-journals: MDPI_acoustics → check if 'MDPI' is in the main list
      const normalized = current.startsWith('MDPI_') ? 'MDPI' : current
      if (!availableJournals.value.includes(normalized)) {
        paper.value.journal = availableJournals.value[0]
      }
    }
    return availableJournals.value
  }

  // ─── MDPI sub-journals ────────────────────────────────────────────────
  const mdpiSubJournals = ref([])
  const mdpiSubJournalsLoading = ref(false)

  async function fetchMDPISubJournals() {
    if (mdpiSubJournals.value.length) return mdpiSubJournals.value
    mdpiSubJournalsLoading.value = true
    try {
      const res = await api.get(`${API_BASE}/journals/mdpi`, { timeout: 10000 })
      mdpiSubJournals.value = res.data?.mdpi_journals || []
    } catch {
      mdpiSubJournals.value = []
    } finally {
      mdpiSubJournalsLoading.value = false
    }
    return mdpiSubJournals.value
  }

  // ─── Auto-save paper to localStorage on every deep change ──────────────
  watch(
    paper,
    (val) => {
      try {
        lsSet(LS_PAPER, toPaperJson())
      } catch {
        /* ignore */
      }
    },
    { deep: true }
  )

  // When paperImages arrives (after loadPaperImages), auto-inject gambar items
  // into sections if they don't already exist. This covers the case where
  // applyPaperData is called before images are loaded.

  let _toastTimer: ReturnType<typeof setTimeout> | null = null
  function showToast(message, type = 'info', duration = 3500) {
    if (_toastTimer) clearTimeout(_toastTimer)
    toast.value = { show: true, message, type }
    _toastTimer = setTimeout(() => {
      toast.value.show = false
      _toastTimer = null
    }, duration)
  }

  // ─── Auto Numbering ────────────────────────────────────────────────────
  const numbering = computed(() => {
    let imgNum = 1,
      tblNum = 1,
      eqNum = 1
    const map = new Map()
    function walk(items) {
      for (const item of items || []) {
        if (item.id === 'gambar') map.set(item, { num: imgNum++, label: `${imgNum - 1}` })
        else if (item.id === 'tabel')
          map.set(item, { num: tblNum++, label: toRomanNum(tblNum - 1) })
        else if (item.id === 'rumus') map.set(item, { num: eqNum++, label: `${eqNum - 1}` })
      }
    }
    for (const sec of paper.value.sections) {
      walk(sec.content)
      for (const sub of sec.subsections || []) walk(sub.content)
    }
    return map
  })

  function getItemNumber(item) {
    return numbering.value.get(item) || {}
  }

  // Flat, document-ordered list of every inline figure (`gambar`) block in the
  // paper, with its number label and where it lives. Used by the Files tab's
  // aggregate "Figures" manager so the user can see/edit every figure + prompt
  // in one place. Returns live references — editing `.item.Prompt` etc. writes
  // straight back into the reactive paper.
  const figureItems = computed(() => {
    const out = []
    function walk(items, sectionIndex, subIndex, sectionTitle) {
      ;(items || []).forEach((item) => {
        if (item.id !== 'gambar') return
        const n = numbering.value.get(item) || {}
        out.push({
          item,
          label: n.label || '?',
          num: n.num || 0,
          sectionIndex,
          subIndex,
          sectionTitle: sectionTitle || '',
        })
      })
    }
    ;(paper.value.sections || []).forEach((sec, sIdx) => {
      walk(sec.content, sIdx, null, sec.title)
      ;(sec.subsections || []).forEach((sub, subIdx) => {
        walk(sub.content, sIdx, subIdx, sub.title || sec.title)
      })
    })
    return out
  })

  // ─── Figure sources (Model A) ──────────────────────────────────────────
  // A "figure source" is an image the user can attach to an inline `gambar`
  // block. Sources come from two pools that already live in the backend:
  //   • paperImages  — uploaded files + AI-generated images
  //   • paperCharts  — charts/graphs built in the Data tab
  // Every source is keyed by its stored `filename` (what we persist in
  // item.Path). Charts and images are both served from /api/images/<pid>/<fn>.
  const figureSources = computed(() => {
    const out = []
    for (const img of paperImages.value || []) {
      if (!img?.filename) continue
      out.push({
        filename: img.filename,
        url: img.url || '',
        label: img.original_name || img.filename,
        // Heuristic: generated images use a gen_/ai_ prefix; everything else
        // is treated as a user upload. Either way it's a valid source.
        kind: /^(gen_|ai_|img_gen)/i.test(img.filename) ? 'generated' : 'upload',
        created_at: img.created_at || '',
      })
    }
    for (const c of paperCharts.value || []) {
      if (!c?.filename) continue
      out.push({
        filename: c.filename,
        url: c.url || '',
        label: c.original_name || `${c.kind || 'chart'} chart`,
        kind: 'chart',
        created_at: c.created_at || '',
      })
    }
    return out
  })

  // Map: filename -> the `gambar` item currently using it (first match wins).
  // Used to enforce "one source per figure" — a source already attached to
  // another figure can't be re-used.
  const figureSourceUsage = computed(() => {
    const map = new Map()
    function walk(items) {
      for (const item of items || []) {
        if (item.id === 'gambar' && item.Path) {
          // Normalize to basename — Path may be absolute filesystem path after reconcile
          const key = item.Path.includes('/') ? item.Path.split('/').pop() : item.Path
          if (!map.has(key)) map.set(key, item)
        }
      }
    }
    for (const sec of paper.value.sections || []) {
      walk(sec.content)
      for (const sub of sec.subsections || []) walk(sub.content)
    }
    return map
  })

  /** Is `filename` already attached to a different figure than `item`? */
  function isSourceUsedByOther(filename, item) {
    if (!filename) return false
    const owner = figureSourceUsage.value.get(filename)
    return !!owner && owner !== item
  }

  /**
   * Attach a source image to a `gambar` item, enforcing the no-conflict rule.
   * Returns true on success, false if the source is taken by another figure.
   */
  function setFigureSource(item, filename) {
    if (!item || item.id !== 'gambar') return false
    if (filename && isSourceUsedByOther(filename, item)) {
      showToast('Gambar ini sudah dipakai figure lain. Lepas dulu dari figure tsb.', 'error')
      return false
    }
    recordChange('set figure image')
    item.Path = filename || ''
    return true
  }

  // ─── Convert TO paper.json format ──────────────────────────────────────
  function toPaperJson() {
    const p = paper.value
    const json = {
      journal: p.journal || 'IEEE',
      citation_style: p.citation_style || 'ieee',
      language: p.language || 'id',
      title: p.title,
      authors: p.authors,
      abstract: p.abstract,
      keywords: p.keywords,
    }
    let imgNum = 1,
      tblNum = 1,
      eqNum = 1

    function numContent(items) {
      return (items || []).map((item) => {
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
      content: p.references,
    }
    // Persist figure metadata so it survives save/load round-trips
    if (Array.isArray(p.figures) && p.figures.length) {
      json.figures = p.figures
    }
    return json
  }

  // ─── Convert FROM paper.json or legacy format ─────────────────────────
  function fromPaperJson(json) {
    return fromPaperJsonRaw(json)
  }

  // ─── CRUD: Sections ───────────────────────────────────────────────────
  function addSection() {
    recordChange('add section')
    if (!Array.isArray(paper.value.sections)) paper.value.sections = []
    paper.value.sections.push({ title: '', content: [{ id: 'text', text: '' }], subsections: [] })
  }
  function removeSection(idx) {
    recordChange('remove section')
    paper.value.sections.splice(idx, 1)
  }

  function addSubsection(sIdx) {
    recordChange('add subsection')
    const sec = paper.value.sections?.[sIdx]
    if (!sec) return
    if (!Array.isArray(sec.subsections)) sec.subsections = []
    sec.subsections.push({ title: '', content: [{ id: 'text', text: '' }] })
  }
  function removeSubsection(sIdx, subIdx) {
    recordChange('remove subsection')
    const sec = paper.value.sections?.[sIdx]
    if (!sec || !Array.isArray(sec.subsections)) return
    if (subIdx >= 0 && subIdx < sec.subsections.length) {
      sec.subsections.splice(subIdx, 1)
    }
  }

  function addContent(container, type) {
    recordChange(`add ${type}`)
    const items = {
      text: { id: 'text', text: '' },
      gambar: { id: 'gambar', Title: '', Path: '', Prompt: '' },
      tabel: { id: 'tabel', Title: '', Headers: ['Col 1', 'Col 2'], Rows: [['', '']] },
      rumus: { id: 'rumus', latex: '' },
    }
    if (items[type]) {
      container.push({ ...items[type] })
      if (type === 'gambar') {
        try {
          // Lazy import to avoid the chat.js ↔ paper.js circular dep loop.
          import('./chat.js')
            .then(({ useChatStore }) => {
              const chat = useChatStore()
              chat.injectAssistantMessage?.(
                'Saya menambahkan slot gambar baru di section. Itu gambar apa keterangannya? ' +
                  'Tulis caption + deskripsi visual singkat, supaya saya bisa generate prompt format (create image"...").'
              )
            })
            .catch(() => {
              /* chat store unavailable — silent no-op */
            })
        } catch {
          /* ignore */
        }
      }
    }
  }
  function removeContent(container, idx) {
    recordChange('remove content')
    container.splice(idx, 1)
  }
  function moveContent(container, idx, dir) {
    recordChange('move content')
    const newIdx = idx + dir
    if (newIdx < 0 || newIdx >= container.length) return
    const tmp = container[idx]
    container.splice(idx, 1)
    container.splice(newIdx, 0, tmp)
  }

  // ─── CRUD: Authors ────────────────────────────────────────────────────
  function addAuthor() {
    recordChange('add author')
    if (!Array.isArray(paper.value.authors)) paper.value.authors = []
    paper.value.authors.push({ name: '', affiliation: '', location: '', email: '' })
  }
  function removeAuthor(idx) {
    recordChange('remove author')
    if (Array.isArray(paper.value.authors) && paper.value.authors.length > 1) paper.value.authors.splice(idx, 1)
  }

  // ─── CRUD: Keywords ───────────────────────────────────────────────────
  function addKeyword(kw) {
    recordChange('add keyword')
    if (kw && !paper.value.keywords.includes(kw)) paper.value.keywords.push(kw)
  }
  function removeKeyword(idx) {
    recordChange('remove keyword')
    paper.value.keywords.splice(idx, 1)
  }

  // ─── CRUD: References ─────────────────────────────────────────────────
  function addReference() {
    recordChange('add reference')
    if (!Array.isArray(paper.value.references)) paper.value.references = []
    paper.value.references.push('')
  }
  function removeReference(idx) {
    recordChange('remove reference')
    paper.value.references.splice(idx, 1)
  }

  // ─── CRUD: Figure helpers ──────────────────────────────────────────────
  function addFigure() {
    recordChange('add figure')
    if (!paper.value.figures) paper.value.figures = []
    paper.value.figures.push({ caption: '', hasImage: false, filename: '', url: '' })
  }
  function removeFigure(idx) {
    recordChange('remove figure')
    paper.value.figures.splice(idx, 1)
  }

  // ─── Figure → Section gambar bridge ─────────────────────────────────────
  // REMOVED: injecting figures into sections caused images to appear in wrong
  // sections (e.g., Kesimpulan). Figures now only render where explicitly placed.
  // The PreviewTab error handler shows "Gambar gagal dimuat" for broken images.
  // function injectFigureImagesIntoSections() { /* removed */ }

  // ─── CRUD: Table helpers ──────────────────────────────────────────────
  function addTableRow(item) {
    recordChange('add table row')
    item.Rows.push(new Array(item.Headers.length).fill(''))
  }
  function removeTableRow(item, rIdx) {
    recordChange('remove table row')
    item.Rows.splice(rIdx, 1)
  }
  function addTableCol(item) {
    recordChange('add table column')
    item.Headers.push(`Col ${item.Headers.length + 1}`)
    item.Rows.forEach((r) => r.push(''))
  }
  function removeTableCol(item, cIdx) {
    recordChange('remove table column')
    if (item.Headers.length > 1) {
      item.Headers.splice(cIdx, 1)
      item.Rows.forEach((r) => r.splice(cIdx, 1))
    }
  }

  // ─── Import / Export ──────────────────────────────────────────────────
  async function newPaper(language: string = 'id') {
    // Try to load language template for initial structure
    const template = await _fetchLangTemplate(language)
    if (template) {
      paper.value = fromPaperJsonRaw(template)
    } else {
      paper.value = createEmptyPaper()
    }
    currentPaperId.value = null
    paperImages.value = []
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
        } catch (err) {
          showToast('Invalid JSON: ' + err.message, 'error')
          reject(err)
        }
      }
      reader.onerror = () => {
        showToast('Failed to read file: ' + (reader.error?.message || 'unknown error'), 'error')
        reject(reader.error || new Error('FileReader error'))
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
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    showToast('JSON downloaded!', 'success')
  }

  async function exportDocx() {

    try {
      loading.value = true
      const journal = (paper.value.journal || 'IEEE').trim() || 'IEEE'
      const res = await api.post(
        `${API_BASE}/export`,
        { journal, paper_id: currentPaperId.value, paper: toPaperJson() },
        { responseType: 'blob', timeout: 300000 }  // 5 minutes for large DOCX with images
      )
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `${journal}_${(paper.value.title || 'paper').replace(/[^a-zA-Z0-9_\-]/g, '_').slice(0, 60)}.docx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
      showToast('DOCX exported!', 'success')
    } catch (err) {
      let msg = err.message
      // When responseType is 'blob', error response body is a Blob — try to read it
      if (err.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text()
          const json = JSON.parse(text)
          msg = json.error || msg
        } catch {
          // not JSON — use default message
        }
      } else if (err.response?.data?.error) {
        msg = err.response.data.error
      }
      showToast('Export failed: ' + msg, 'error')
    } finally {
      loading.value = false
    }
  }

  // ─── AI ───────────────────────────────────────────────────────────────

  async function aiGenerateFullPaper(prompt, { topic, style, pdfTexts } = {}) {
    try {
      const payload = { prompt }
      if (topic) payload.topic = topic
      if (style) payload.style = style
      if (pdfTexts && pdfTexts.length) payload.pdf_texts = pdfTexts
      if (currentPaperId.value) payload.paper_id = currentPaperId.value
      const startRes = await api.post(`${API_BASE}/generate-full`, payload, { timeout: 15000 })
      if (!startRes.data?.job_id) throw new Error(startRes.data?.error || 'No job_id')
      const jobId = startRes.data.job_id
      lsSet(LS_JOB, { jobId, t0: Date.now() })
      showToast('Paper generation started! Check the bell icon for progress.', 'info')
      return jobId
    } catch (err) {
      showToast('AI Error: ' + err.message, 'error')
      return null
    }
  }

  /**
   * Attach to a generate-full job that was started by the chat AI tool.
   * Non-blocking — the paperJobs store handles polling and result delivery.
   */
  async function attachAiJob(jobId, prompt = '') {
    if (!jobId) return false
    lsSet(LS_JOB, { jobId, t0: Date.now() })
    showToast('Paper generation started! Check the bell icon for progress.', 'info')
    return true
  }

  /**
   * Call this on app mount. If a job was in-flight when the page was refreshed,
   * check its status and let the paperJobs store handle active polling.
   */
  async function resumePendingJob() {
    const jobInfo = lsGet(LS_JOB)
    if (!jobInfo) return
    const { jobId, t0 } = jobInfo || {}
    if (!jobId || !t0) {
      lsRemove(LS_JOB)
      return
    }
    if (Date.now() - t0 > 25 * 60 * 1000) {
      lsRemove(LS_JOB)
      return
    }
    try {
      const check = await api.get(`${API_BASE}/job/${jobId}`, { timeout: 8000 })
      if (check.data.status === 'error' || !check.data.status) {
        lsRemove(LS_JOB)
        return
      }
      if (check.data.status === 'done') {
        paper.value = fromPaperJsonRaw(check.data.paper)
        lsRemove(LS_JOB)
        showToast('Paper dipulihkan dari proses sebelumnya!', 'success')
        return
      }
      // Still running — the paperJobs store will pick it up via its polling
    } catch {
      lsRemove(LS_JOB)
    }
  }

  // ─── DB Save/Load ─────────────────────────────────────────────────────
  async function savePaperToDb(silent = false) {
    try {
      if (!silent) loading.value = true
      const paperData = { ...toPaperJson() }
      if (currentPaperId.value) paperData.id = currentPaperId.value
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
    } finally {
      if (!silent) loading.value = false
    }
  }

  // Loading flag to prevent auto-save during DB reload
  const _loadingFromDb = ref(false)

  async function loadPaperFromDb(paperId) {
    if (!paperId || paperId === 'null' || paperId === 'undefined') {
      showToast('Invalid paper ID', 'error')
      return false
    }
    try {
      loading.value = true
      _loadingFromDb.value = true
      const res = await api.get(`${API_BASE}/papers/${paperId}`)
      paper.value = fromPaperJsonRaw(res.data)
      currentPaperId.value = res.data.id || paperId
      // Clear undo/redo stacks so Ctrl+Z doesn't revert to pre-reload state
      undoStack.value = []
      redoStack.value = []
      lsSet(LS_LAST_PAPER_ID, currentPaperId.value)
      await loadPaperImages(currentPaperId.value)
      loadPaperCharts(currentPaperId.value)
      return true
    } catch (err) {
      const status = err.response?.status
      const errMsg = err.response?.data?.error || err.message
      // If the paper no longer exists (404), purge stale cache so the editor
      // doesn't keep trying to load a deleted paper on every revisit.
      if (status === 404) {
        lsRemove(LS_LAST_PAPER_ID)
        currentPaperId.value = null
        showToast('Paper tidak ditemukan. Mungkin sudah dihapus.', 'error')
      } else {
        showToast('Load failed: ' + errMsg, 'error')
      }
      return false
    } finally {
      loading.value = false
      // Defer clearing the flag so the watcher has time to see it
      // and skip the auto-save that would otherwise overwrite the loaded data
      setTimeout(() => { _loadingFromDb.value = false }, 50)
    }
  }

  // Apply paper data directly (e.g., from SSE done event) without fetching from DB
  function applyPaperData(data) {
    if (!data) return
    paper.value = fromPaperJsonRaw(data)
    // Reset undo/redo history since we have new content
    undoStack.value = []
    redoStack.value = []
    recordChange('generate paper')
  }

  async function loadPaperImages(paperId) {
    if (!paperId) {
      paperImages.value = []
      return
    }
    try {
      const res = await api.get(`${API_BASE}/papers/${paperId}/images`)
      paperImages.value = res.data.images || []
    } catch {
      paperImages.value = []
    }
  }

  async function loadPaperCharts(paperId) {
    if (!paperId) {
      paperCharts.value = []
      return
    }
    try {
      const res = await api.get(`${API_BASE}/papers/${paperId}/charts`)
      paperCharts.value = res.data.charts || []
    } catch {
      paperCharts.value = []
    }
  }

  async function uploadImage(figureIndex, file) {
    try {
      if (!currentPaperId.value) {
        // Must save paper first to get an ID
        const id = await savePaperToDb()
        if (!id) return
      }
      if (!currentPaperId.value) return // guard in case save didn't populate the ref
      const formData = new FormData()
      formData.append('file', file)
      const res = await api.post(`${API_BASE}/papers/${currentPaperId.value}/images`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const img = res.data.image
      paperImages.value.push(img)
      // Auto-assign to figure if figureIndex is provided
      if (figureIndex !== undefined && paper.value.figures?.[figureIndex]) {
        paper.value.figures[figureIndex].filename = img.filename
        paper.value.figures[figureIndex].url = img.url
      }
      showToast('Image uploaded!', 'success')
      try {
        // Nudge the chat so the AI can ask for a caption + reference context.
        // Lazy import to avoid the chat.js ↔ paper.js circular dep loop.
        import('./chat.js')
          .then(({ useChatStore }) => {
            const chat = useChatStore()
            chat.injectAssistantMessage?.(
              `Gambar "${file.name}" berhasil diupload. Itu gambar apa keterangannya? ` +
                `Saya pakai untuk caption Fig. dan referensi di prose.`
            )
          })
          .catch(() => {
            /* chat store unavailable — silent no-op */
          })
      } catch {
        /* ignore */
      }
      return img
    } catch (err) {
      showToast('Upload failed: ' + (err.response?.data?.error || err.message), 'error')
      return null
    }
  }

  async function deletePaperImage(imageId) {
    if (!currentPaperId.value) return
    try {
      await api.delete(`${API_BASE}/papers/${currentPaperId.value}/images/${imageId}`)
      paperImages.value = paperImages.value.filter((img) => img.id !== imageId)
      showToast('Image deleted', 'success')
    } catch (err) {
      showToast('Delete failed: ' + (err.response?.data?.error || err.message), 'error')
    }
  }

  // ─── Helpers ──────────────────────────────────────────────────────────
  function toRoman(num) {
    return toRomanNum(num)
  }

  function getLastPaperId() {
    return lsGet(LS_LAST_PAPER_ID)
  }

  return {
    paper,
    loading,
    aiLoading,
    aiLoadingMessage,
    toast,
    currentPaperId,
    paperImages,
    figureSources,
    figureSourceUsage,
    // Index-based mapping: maps an integer index (0-based document order)
    // to the corresponding paperImages entry. Used to resolve AI placeholder
    // paths (gambar/fig1.png) to actual filenames (gen_abc123.png).
    paperImageByIndex: computed(() => {
      const genImages = (paperImages.value || []).filter(img =>
        /^(gen_|ai_|img_gen)/i.test(img.filename || '')
      )
      return genImages
    }),
    paperCharts,
    availableJournals,
    journalsLoading,
    fetchJournals,
    mdpiSubJournals,
    mdpiSubJournalsLoading,
    fetchMDPISubJournals,
    pendingChanges,
    pendingCount,
    pushProposal,
    acceptProposal,
    rejectProposal,
    acceptAllProposals,
    rejectAllProposals,
    clearResolvedProposals,
    applyImmediate,
    attachAiJob,
    replaceContent,
    replaceSectionText,
    replaceWhole,
    numbering,
    getItemNumber,
    figureItems,
    isSourceUsedByOther,
    setFigureSource,
    toPaperJson,
    fromPaperJson,
    addSection,
    removeSection,
    addSubsection,
    removeSubsection,
    addContent,
    removeContent,
    moveContent,
    addAuthor,
    removeAuthor,
    addKeyword,
    removeKeyword,
    addReference,
    removeReference,
    addFigure,
    removeFigure,
    addTableRow,
    removeTableRow,
    addTableCol,
    removeTableCol,
    newPaper,
    uploadJson,
    downloadJson,
    exportDocx,
    
    aiGenerateFullPaper,
    resumePendingJob,
    savePaperToDb,
    loadPaperFromDb,
    _loadingFromDb,
    applyPaperData,
    loadPaperImages,
    loadPaperCharts,
    uploadImage,
    deletePaperImage,
    showToast,
    toRoman,
    getLastPaperId,
    undo,
    redo,
    canUndo,
    canRedo,
    formatRef: _formatStructuredRef,
    apiGet: (url) => api.get(url),
    apiUploadPdfs: (formData) =>
      api.post(`${API_BASE}/upload-pdfs`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }),

    async getSignedImageUrl(filename: string): Promise<string> {
      if (!currentPaperId.value) return ''
      try {
        const res = await api.post(`${API_BASE}/papers/${currentPaperId.value}/sign`, {
          scope: 'image',
          resource_id: filename,
          ttl_seconds: 3600
        })
        return res.data.url
      } catch {
        // Fallback to unsigned URL (may fail on cross-origin)
        return `/api/images/${currentPaperId.value}/${encodeURIComponent(filename)}`
      }
    },
  }
})
