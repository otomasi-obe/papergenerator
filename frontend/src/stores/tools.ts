// @ts-nocheck
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/index.js'

const API_BASE = '/api'
const LS_KEY = 'pf_tool_state'

// ── localStorage helpers ────────────────────────────────────────────────────

function loadPersistedState(): Record<string, any> {
  try {
    const raw = localStorage.getItem(LS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch { return {} }
}

function savePersistedState(state: Record<string, any>) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(state))
  } catch { /* quota exceeded — silently ignore */ }
}

export const useToolsStore = defineStore('tools', () => {
  // ── Restore persisted state ───────────────────────────────────────────────
  const _persisted = loadPersistedState()

  const activeTool = ref(null)
  const toolInputs = ref(_persisted._inputs || {}) as import('vue').Ref<Record<string, string>>
  const toolOutputs = ref(_persisted._outputs || {}) as import('vue').Ref<Record<string, string>>
  const toolResults = ref(_persisted._results || {}) as import('vue').Ref<Record<string, any>>
  const toolOptions = ref(_persisted._options || {}) as import('vue').Ref<Record<string, string>>
  const toolSources = ref(_persisted._sources || {}) as import('vue').Ref<Record<string, string>>

  const isProcessing = ref(false)
  const selectedOption = ref('')
  const selectedSource = ref('Indonesian')
  const selectedEngine = ref('ai')
  const selectedDomain = ref('general')
  const translatorConfig = ref({ engines: [] as string[], languages: [] as string[], domains: [] as string[] })
  const error = ref(null)
  let _activeAbortCtrl: AbortController | null = null
  const mode = ref('program')

  // ── Computed: input/output/result bound to active tool ────────────────────

  const inputText = computed({
    get: () => {
      if (!activeTool.value) return ''
      return toolInputs.value[activeTool.value.id] || ''
    },
    set: (val: string) => {
      if (activeTool.value) {
        toolInputs.value = { ...toolInputs.value, [activeTool.value.id]: val }
        _schedulePersist()
      }
    },
  })

  const outputText = computed({
    get: () => {
      if (!activeTool.value) return ''
      return toolOutputs.value[activeTool.value.id] || ''
    },
    set: (val: string) => {
      if (activeTool.value) {
        toolOutputs.value = { ...toolOutputs.value, [activeTool.value.id]: val }
        _schedulePersist()
      }
    },
  })

  const toolResult = computed({
    get: () => {
      if (!activeTool.value) return null
      return toolResults.value[activeTool.value.id] || null
    },
    set: (val: any) => {
      if (activeTool.value) {
        toolResults.value = { ...toolResults.value, [activeTool.value.id]: val }
        _schedulePersist()
      }
    },
  })

  // ── Debounced persist ─────────────────────────────────────────────────────
  let _persistTimer: any = null
  function _schedulePersist() {
    if (_persistTimer) clearTimeout(_persistTimer)
    _persistTimer = setTimeout(() => {
      // Cap each tool's input/output to 50KB to avoid bloating localStorage
      const cappedInputs: Record<string, string> = {}
      const cappedOutputs: Record<string, string> = {}
      for (const [k, v] of Object.entries(toolInputs.value)) cappedInputs[k] = (v || '').slice(0, 50000)
      for (const [k, v] of Object.entries(toolOutputs.value)) cappedOutputs[k] = (v || '').slice(0, 50000)
      savePersistedState({
        _inputs: cappedInputs,
        _outputs: cappedOutputs,
        _results: toolResults.value,
        _options: toolOptions.value,
        _sources: toolSources.value,
      })
    }, 500)
  }

  const TOOLS = [
      { id: 'detector', icon: '🔍', tint: '#d9a718', title: 'AI Detector', desc: 'Estimate how likely a passage reads as AI-generated.', iconSvg: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>' },
      { id: 'paraphrase', icon: '✍️', tint: '#1265c8', title: 'Paraphrase', desc: 'Rewrite passages in a different tone or strength while keeping the meaning.', iconSvg: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>' },
      { id: 'translate', icon: '🌐', tint: '#1265c8', title: 'Translator', desc: 'Translate between Indonesian and English — academic register.', iconSvg: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>' },
      { id: 'humanizer', icon: '🧬', tint: '#2f9d6e', title: 'Humanizer', desc: 'Rework AI-sounding prose to read naturally and pass AI detectors.', modes: ['program', 'ai'], iconSvg: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>' },
      { id: 'plagiarism', icon: '📋', tint: '#c43655', title: 'Plagiarism Check', desc: 'Multi-mode plagiarism scanner: AI Check, Web Search, Offline analysis, or Full Scan.', iconSvg: '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>' },
      { id: 'grammar', icon: '✨', tint: '#1e6e8f', title: 'Grammar', desc: 'AI-powered grammar correction with inline diff.', iconSvg: '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>' },
      { id: 'summarize', icon: '📝', tint: '#0b4088', title: 'Summarize', desc: 'Condense a section or reference into a TL;DR or abstract.', iconSvg: '<path d="M4 12h16"/><path d="M4 18h12"/><path d="m15 5-3 3-3-3"/><path d="M12 2v6"/>' },
      { id: 'word-addon', icon: '📄', tint: '#2b579a', title: 'Word Addon', desc: 'Install the PaperFull AI assistant for Microsoft Word and chat with AI inside your document.', external: true, iconSvg: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>' },
    ]

  function getDefaultOption(toolId) {
    switch (toolId) {
      case 'translate': return 'English'
      case 'paraphrase': return 'Standard'
      case 'humanizer': return 'Standard'
      case 'grammar': return 'Standard'
      case 'plagiarism': return 'AI Check'
      case 'summarize': return 'TL;DR'
      case 'detector': return 'Fast'
      default: return 'Standard'
    }
  }

  function getDefaultSource(toolId) {
    if (toolId === 'translate') return 'Indonesian'
    return ''
  }

  async function loadTranslatorConfig() {
    try {
      const csrf = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
      const r = await fetch(`${API_BASE}/tools/translate/config`, {
        credentials: 'include',
        headers: { 'X-CSRF-TOKEN': decodeURIComponent(csrf) },
      })
      if (r.ok) translatorConfig.value = await r.json()
    } catch { /* ignore */ }
  }

  function setActiveTool(tool) {
    // Save current tool's option & source before switching
    if (activeTool.value) {
      toolOptions.value = { ...toolOptions.value, [activeTool.value.id]: selectedOption.value }
      if (activeTool.value.id === 'translate') {
        toolSources.value = { ...toolSources.value, [activeTool.value.id]: selectedSource.value }
      }
    }

    activeTool.value = tool

    // Restore saved option/source for this tool, or use defaults
    const savedOption = toolOptions.value[tool.id]
    selectedOption.value = savedOption || getDefaultOption(tool.id)

    if (tool.id === 'translate') {
      const savedSource = toolSources.value[tool.id]
      selectedSource.value = savedSource || getDefaultSource(tool.id)
      loadTranslatorConfig()
    }

    mode.value = 'program'
    error.value = null
    // output/result are already computed from per-tool maps — no reset needed
  }

  function setMode(m) {
    mode.value = m
  }

  /** Clear input + output + result for the active tool only */
  function clearToolData() {
    if (!activeTool.value) return
    const id = activeTool.value.id
    const newInputs = { ...toolInputs.value }
    const newOutputs = { ...toolOutputs.value }
    const newResults = { ...toolResults.value }
    delete newInputs[id]
    delete newOutputs[id]
    delete newResults[id]
    toolInputs.value = newInputs
    toolOutputs.value = newOutputs
    toolResults.value = newResults
    error.value = null
    _schedulePersist()
  }

  function clearActiveTool() {
    activeTool.value = null
    error.value = null
  }

  async function processTool() {
    if (!activeTool.value || !inputText.value.trim()) return

    isProcessing.value = true
    // Don't clear output/result immediately — keep previous until new arrives
    error.value = null

    const prevOutput = outputText.value
    const prevResult = toolResult.value
    let newOutput = ''
    let newResult = null

    try {
      const csrf = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
      const payload: Record<string, any> = { text: inputText.value, option: selectedOption.value }
      if (activeTool.value.id === 'translate') {
        payload.source_language = selectedSource.value
        payload.engine = selectedEngine.value
        payload.domain = selectedDomain.value
      }

      let endpoint = `${API_BASE}/tools/${activeTool.value.id}`
      if (activeTool.value.id === 'grammar') {
        endpoint = `${API_BASE}/tools/ai-grammar`
      }
      if (activeTool.value.id === 'humanizer') {
        payload.mode = mode.value
      }

      _activeAbortCtrl?.abort()
      _activeAbortCtrl = new AbortController()
      const abortCtrl = _activeAbortCtrl
      const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        signal: abortCtrl.signal,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-TOKEN': decodeURIComponent(csrf),
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      if (!response.body) {
        throw new Error('Response body is null')
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      // Clear previous output when we start receiving
      outputText.value = ''
      toolResult.value = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.text) {
                newOutput += data.text
                outputText.value = newOutput
              }
              if (data.result) {
                newResult = data.result
                toolResult.value = data.result
              }
              if (data.error) {
                error.value = data.error
              }
            } catch { /* skip malformed */ }
          }
        }
      }
    } catch (e) {
      error.value = (e instanceof Error ? e.message : String(e)) || 'Terjadi kesalahan saat memproses'
    } finally {
      _activeAbortCtrl = null
      isProcessing.value = false
      _schedulePersist()
    }
  }

  return {
    activeTool,
    inputText,
    outputText,
    toolResult,
    toolInputs,
    toolOutputs,
    toolResults,
    toolOptions,
    toolSources,
    isProcessing,
    selectedOption,
    selectedSource,
    selectedEngine,
    selectedDomain,
    translatorConfig,
    error,
    mode,
    TOOLS,
    setActiveTool,
    setMode,
    clearActiveTool,
    clearToolData,
    processTool,
    getDefaultOption,
    loadTranslatorConfig,
    cancelTool: () => { _activeAbortCtrl?.abort(); _activeAbortCtrl = null },
    dispose() {
      if (_persistTimer) { clearTimeout(_persistTimer); _persistTimer = null }
    },
  }
})
