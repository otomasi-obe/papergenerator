import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

const API_BASE = '/api'

// Set global axios defaults — no timeout for long-running AI calls
axios.defaults.timeout = 0

export const usePaperStore = defineStore('paper', () => {
  // ─── State ────────────────────────────────────────────────────────────────
  const paper = ref(createEmptyPaper())
  const loading = ref(false)
  const aiLoading = ref(false)
  const aiLoadingMessage = ref('')
  const toast = ref({ show: false, message: '', type: 'info' })
  const activeTab = ref('metadata')
  const savedPapers = ref([])

  // ─── Helper ───────────────────────────────────────────────────────────────
  function createEmptyPaper() {
    return {
      id: null,
      title: '',
      authors: [{ name: '', affiliation: '', location: '', email: '' }],
      abstract: '',
      keywords: [],
      sections: [],
      acknowledgment: '',
      references: [],
      figures: [],
      tables: [],
      equations: []
    }
  }

  function generateId() {
    return 'id-' + Math.random().toString(36).substr(2, 9)
  }

  function showToast(message, type = 'info') {
    toast.value = { show: true, message, type }
    setTimeout(() => { toast.value.show = false }, 3000)
  }

  // ─── Computed ─────────────────────────────────────────────────────────────
  const hasContent = computed(() => {
    return paper.value.title || paper.value.abstract || paper.value.sections.length > 0
  })

  // ─── Paper CRUD ───────────────────────────────────────────────────────────
  function newPaper() {
    paper.value = createEmptyPaper()
    showToast('New paper created', 'success')
  }

  async function savePaper() {
    try {
      loading.value = true
      if (!paper.value.id) {
        paper.value.id = generateId()
      }
      const res = await axios.post(`${API_BASE}/papers`, paper.value)
      showToast('Paper saved successfully', 'success')
      await loadPaperList()
      return res.data
    } catch (err) {
      showToast('Failed to save paper: ' + (err.response?.data?.error || err.message), 'error')
    } finally {
      loading.value = false
    }
  }

  async function loadPaper(id) {
    try {
      loading.value = true
      const res = await axios.get(`${API_BASE}/papers/${id}`)
      paper.value = res.data
      showToast('Paper loaded', 'success')
    } catch (err) {
      showToast('Failed to load paper: ' + (err.response?.data?.error || err.message), 'error')
    } finally {
      loading.value = false
    }
  }

  async function deletePaper(id) {
    try {
      await axios.delete(`${API_BASE}/papers/${id}`)
      if (paper.value.id === id) {
        newPaper()
      }
      await loadPaperList()
      showToast('Paper deleted', 'success')
    } catch (err) {
      showToast('Failed to delete paper', 'error')
    }
  }

  async function loadPaperList() {
    try {
      const res = await axios.get(`${API_BASE}/papers`)
      savedPapers.value = res.data.papers || []
    } catch (err) {
      console.error('Failed to load paper list:', err)
    }
  }

  // ─── Authors ──────────────────────────────────────────────────────────────
  function addAuthor() {
    paper.value.authors.push({ name: '', affiliation: '', location: '', email: '' })
  }

  function removeAuthor(index) {
    if (paper.value.authors.length > 1) {
      paper.value.authors.splice(index, 1)
    }
  }

  // ─── Sections ─────────────────────────────────────────────────────────────
  function addSection() {
    const num = paper.value.sections.length + 1
    const roman = toRoman(num)
    paper.value.sections.push({
      id: generateId(),
      number: roman,
      title: '',
      content: '',
      subsections: []
    })
  }

  function removeSection(index) {
    paper.value.sections.splice(index, 1)
    // Renumber
    paper.value.sections.forEach((s, i) => {
      s.number = toRoman(i + 1)
    })
  }

  function addSubsection(sectionIndex) {
    const section = paper.value.sections[sectionIndex]
    const letter = String.fromCharCode(65 + section.subsections.length)
    section.subsections.push({
      id: generateId(),
      letter,
      title: '',
      content: '',
      numberedItems: []
    })
  }

  function removeSubsection(sectionIndex, subIndex) {
    const section = paper.value.sections[sectionIndex]
    section.subsections.splice(subIndex, 1)
    // Re-letter
    section.subsections.forEach((s, i) => {
      s.letter = String.fromCharCode(65 + i)
    })
  }

  function addNumberedItem(sectionIndex, subIndex) {
    const sub = paper.value.sections[sectionIndex].subsections[subIndex]
    sub.numberedItems.push({
      number: sub.numberedItems.length + 1,
      title: '',
      content: ''
    })
  }

  function removeNumberedItem(sectionIndex, subIndex, itemIndex) {
    const sub = paper.value.sections[sectionIndex].subsections[subIndex]
    sub.numberedItems.splice(itemIndex, 1)
    sub.numberedItems.forEach((item, i) => { item.number = i + 1 })
  }

  // ─── References ───────────────────────────────────────────────────────────
  function addReference() {
    const nextId = paper.value.references.length > 0
      ? Math.max(...paper.value.references.map(r => r.id)) + 1
      : 1
    paper.value.references.push({ id: nextId, text: '' })
  }

  function removeReference(index) {
    paper.value.references.splice(index, 1)
    // Renumber
    paper.value.references.forEach((r, i) => { r.id = i + 1 })
  }

  // ─── Figures ──────────────────────────────────────────────────────────────
  function addFigure() {
    const nextNum = paper.value.figures.length + 1
    paper.value.figures.push({
      id: `figure-${nextNum}`,
      caption: `Fig. ${nextNum}. `,
      filename: '',
      url: ''
    })
  }

  function removeFigure(index) {
    paper.value.figures.splice(index, 1)
    paper.value.figures.forEach((f, i) => {
      f.id = `figure-${i + 1}`
    })
  }

  async function uploadImage(index, file) {
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await axios.post(`${API_BASE}/upload-image`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      if (res.data.success) {
        paper.value.figures[index].filename = res.data.filename
        paper.value.figures[index].url = res.data.url
        showToast('Image uploaded', 'success')
      }
    } catch (err) {
      showToast('Image upload failed: ' + (err.response?.data?.error || err.message), 'error')
    }
  }

  // ─── Tables ───────────────────────────────────────────────────────────────
  function addTable() {
    const nextNum = paper.value.tables.length + 1
    paper.value.tables.push({
      id: `table-${nextNum}`,
      caption: `TABLE ${toRoman(nextNum)}. `,
      headers: ['Column 1', 'Column 2', 'Column 3'],
      rows: [['', '', '']]
    })
  }

  function removeTable(index) {
    paper.value.tables.splice(index, 1)
  }

  function addTableRow(tableIndex) {
    const table = paper.value.tables[tableIndex]
    table.rows.push(new Array(table.headers.length).fill(''))
  }

  function removeTableRow(tableIndex, rowIndex) {
    paper.value.tables[tableIndex].rows.splice(rowIndex, 1)
  }

  function addTableColumn(tableIndex) {
    const table = paper.value.tables[tableIndex]
    table.headers.push(`Column ${table.headers.length + 1}`)
    table.rows.forEach(row => row.push(''))
  }

  function removeTableColumn(tableIndex, colIndex) {
    const table = paper.value.tables[tableIndex]
    if (table.headers.length > 1) {
      table.headers.splice(colIndex, 1)
      table.rows.forEach(row => row.splice(colIndex, 1))
    }
  }

  // ─── Equations ────────────────────────────────────────────────────────────
  function addEquation() {
    const nextNum = paper.value.equations.length + 1
    paper.value.equations.push({
      id: `eq-${nextNum}`,
      latex: '',
      number: nextNum
    })
  }

  function removeEquation(index) {
    paper.value.equations.splice(index, 1)
    paper.value.equations.forEach((eq, i) => {
      eq.id = `eq-${i + 1}`
      eq.number = i + 1
    })
  }

  // ─── Keywords ─────────────────────────────────────────────────────────────
  function addKeyword(keyword) {
    if (keyword && !paper.value.keywords.includes(keyword)) {
      paper.value.keywords.push(keyword)
    }
  }

  function removeKeyword(index) {
    paper.value.keywords.splice(index, 1)
  }

  // ─── AI Generate ──────────────────────────────────────────────────────────
  async function aiGenerate(prompt, section = 'general', lastText = '') {
    try {
      aiLoading.value = true
      const res = await axios.post(`${API_BASE}/generate`, {
        prompt,
        section,
        lastText,
        paperContext: {
          title: paper.value.title,
          authors: paper.value.authors,
          abstract: paper.value.abstract
        }
      })
      if (res.data.success) {
        showToast(`AI generated (${res.data.usage?.total_tokens || 0} tokens)`, 'success')
        return res.data.content
      }
      throw new Error(res.data.error || 'Generation failed')
    } catch (err) {
      showToast('AI error: ' + (err.response?.data?.error || err.message), 'error')
      return null
    } finally {
      aiLoading.value = false
    }
  }

  async function aiGenerateFullPaper(prompt) {
    try {
      aiLoading.value = true
      aiLoadingMessage.value = 'Menghubungi AI...'

      // ── Step 1: Start the background job ─────────────────────────────────
      let startRes
      try {
        startRes = await axios.post(`${API_BASE}/generate-full`, { prompt }, { timeout: 15000 })
      } catch (startErr) {
        throw new Error('Gagal menghubungi server: ' + (startErr.response?.data?.error || startErr.message))
      }

      if (!startRes.data?.job_id) {
        throw new Error(startRes.data?.error || 'Server tidak mengembalikan job_id')
      }

      const jobId = startRes.data.job_id
      const startTime = Date.now()
      const MAX_WAIT_MS = 12 * 60 * 1000  // 12 minutes hard limit

      // ── Step 2: Poll until done ───────────────────────────────────────────
      while (true) {
        await new Promise(resolve => setTimeout(resolve, 3000))   // wait 3 s

        const elapsed = Math.round((Date.now() - startTime) / 1000)
        const mins = Math.floor(elapsed / 60)
        const secs = elapsed % 60
        const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
        aiLoadingMessage.value = `🤖 AI sedang membuat paper... (${timeStr})`

        let pollRes
        try {
          pollRes = await axios.get(`${API_BASE}/job/${jobId}`, { timeout: 10000 })
        } catch (pollErr) {
          // If the server returns 404 the job was already consumed — treat as error.
          if (pollErr.response?.status === 404) {
            throw new Error('Job tidak ditemukan. Server mungkin di-restart. Coba lagi.')
          }
          // Other network errors during poll — retry silently
          console.warn('[aiGenerateFullPaper] poll error (retrying):', pollErr.message)
          continue
        }

        const { status } = pollRes.data

        if (status === 'done') {
          paper.value = { ...createEmptyPaper(), ...pollRes.data.paper, id: paper.value.id }
          const usage = pollRes.data.usage || {}
          showToast(`Paper berhasil dibuat! (${timeStr}, ${usage.total_tokens || '?'} token)`, 'success')
          return true
        }

        if (status === 'error') {
          const errMsg = pollRes.data.error || 'Generasi gagal'
          throw new Error(pollRes.data.timeout ? `Timeout: ${errMsg}` : errMsg)
        }

        // status === 'pending' → continue polling
        if (Date.now() - startTime > MAX_WAIT_MS) {
          throw new Error('Timeout: proses melebihi 12 menit. Coba topik yang lebih singkat.')
        }
      }
    } catch (err) {
      showToast('Error AI: ' + (err.response?.data?.error || err.message), 'error')
      return false
    } finally {
      aiLoading.value = false
      aiLoadingMessage.value = ''
    }
  }

  // ─── Export ───────────────────────────────────────────────────────────────
  async function exportDocx() {
    try {
      loading.value = true
      const res = await axios.post(`${API_BASE}/export`, { paper: paper.value }, {
        responseType: 'blob'
      })
      const url = window.URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `${paper.value.title || 'paper'}.docx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      showToast('DOCX exported!', 'success')
    } catch (err) {
      showToast('Export failed: ' + (err.response?.data?.error || err.message), 'error')
    } finally {
      loading.value = false
    }
  }

  // ─── Helpers ──────────────────────────────────────────────────────────────
  function toRoman(num) {
    const romanNumerals = [
      [1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'],
      [100, 'C'], [90, 'XC'], [50, 'L'], [40, 'XL'],
      [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']
    ]
    let result = ''
    for (const [value, numeral] of romanNumerals) {
      while (num >= value) {
        result += numeral
        num -= value
      }
    }
    return result
  }

  return {
    // State
    paper, loading, aiLoading, aiLoadingMessage, toast, activeTab, savedPapers,
    // Computed
    hasContent,
    // Paper CRUD
    newPaper, savePaper, loadPaper, deletePaper, loadPaperList,
    // Authors
    addAuthor, removeAuthor,
    // Sections
    addSection, removeSection, addSubsection, removeSubsection,
    addNumberedItem, removeNumberedItem,
    // References
    addReference, removeReference,
    // Figures
    addFigure, removeFigure, uploadImage,
    // Tables
    addTable, removeTable, addTableRow, removeTableRow,
    addTableColumn, removeTableColumn,
    // Equations
    addEquation, removeEquation,
    // Keywords
    addKeyword, removeKeyword,
    // AI
    aiGenerate, aiGenerateFullPaper,
    // Export
    exportDocx,
    // Helpers
    showToast, generateId, toRoman
  }
})
