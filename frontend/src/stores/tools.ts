// @ts-nocheck
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/index.js'

const API_BASE = '/api'

export const useToolsStore = defineStore('tools', () => {
  const activeTool = ref(null)
  const toolInputs = ref({}) as import('vue').Ref<Record<string, string>>
  const outputText = ref('')
  const isProcessing = ref(false)
  const selectedOption = ref('')
  const selectedSource = ref('Auto (Detect)')
  const selectedEngine = ref('ai')
  const selectedDomain = ref('general')
  const translatorConfig = ref({ engines: [] as string[], languages: [] as string[], domains: [] as string[] })
  const toolResult = ref(null)
  const error = ref(null)
  const mode = ref('program')

  const inputText = computed({
    get: () => {
      if (!activeTool.value) return ''
      return toolInputs.value[activeTool.value.id] || ''
    },
    set: (val: string) => {
      if (activeTool.value) {
        toolInputs.value = { ...toolInputs.value, [activeTool.value.id]: val }
      }
    },
  })

  const TOOLS = [
    { id: 'detector', icon: '🔍', tint: '#d9a718', title: 'AI Detector', desc: 'Estimate how likely a passage reads as AI-generated.' },
    { id: 'paraphrase', icon: '✍️', tint: '#1265c8', title: 'Paraphrase', desc: 'Rewrite passages in a different tone or strength while keeping the meaning.' },
    { id: 'translate', icon: '🌐', tint: '#1265c8', title: 'Translator', desc: 'Translate between Indonesian, English and 20+ languages — academic register.' },
    { id: 'humanizer', icon: '🧬', tint: '#2f9d6e', title: 'Humanizer', desc: 'Rework AI-sounding prose to read naturally and pass AI detectors.', modes: ['program', 'ai'] },
    { id: 'plagiarism', icon: '📋', tint: '#c43655', title: 'Plagiarism Check', desc: 'Multi-mode plagiarism scanner: AI Check, Web Search, Offline analysis, or Full Scan.' },
    { id: 'grammar', icon: '✨', tint: '#1e6e8f', title: 'Grammar', desc: 'LLM-powered academic grammar correction with inline diff. Slower but context-aware.' },
    { id: 'summarize', icon: '📝', tint: '#0b4088', title: 'Summarize', desc: 'Condense a section or reference into a TL;DR or abstract.' },
    { id: 'word-addon', icon: '📄', tint: '#2b579a', title: 'Word Addon', desc: 'Install VIOLA AI assistant untuk Microsoft Word. Chat dengan AI langsung di dokumen Anda.', external: true },
  ]

  function getDefaultOption(toolId) {
    switch (toolId) {
      case 'translate': return 'Indonesian'
      case 'paraphrase': return 'Standard'
      case 'humanizer': return 'Standard'
      case 'grammar': return 'Standard'
      case 'plagiarism': return 'AI Check'
      case 'summarize': return 'TL;DR'
      default: return 'Standard'
    }
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
    activeTool.value = tool
    selectedOption.value = getDefaultOption(tool.id)
    selectedSource.value = 'Auto (Detect)'
    selectedEngine.value = 'ai'
    selectedDomain.value = 'general'
    if (tool.id === 'translate') loadTranslatorConfig()
    mode.value = 'program'
    outputText.value = ''
    toolResult.value = null
    error.value = null
  }

  function setMode(m) {
    mode.value = m
  }

  function clearActiveTool() {
    if (activeTool.value) {
      const next = { ...toolInputs.value }
      delete next[activeTool.value.id]
      toolInputs.value = next
    }
    activeTool.value = null
    outputText.value = ''
    toolResult.value = null
    error.value = null
  }

  async function processTool() {
    if (!activeTool.value || !inputText.value.trim()) return

    isProcessing.value = true
    outputText.value = ''
    toolResult.value = null
    error.value = null

    try {
      const csrf = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
      const payload: Record<string, any> = { text: inputText.value, option: selectedOption.value }
      if (activeTool.value.id === 'translate') {
        payload.source_language = selectedSource.value === 'Auto (Detect)' ? 'auto' : selectedSource.value
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

      const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-TOKEN': decodeURIComponent(csrf),
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

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
                outputText.value += data.text
              }
              if (data.result) {
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
      error.value = e.message || 'Terjadi kesalahan saat memproses'
    } finally {
      isProcessing.value = false
    }
  }

  return {
    activeTool,
    inputText,
    toolInputs,
    outputText,
    isProcessing,
    selectedOption,
    toolResult,
    error,
    mode,
    TOOLS,
    selectedSource,
    selectedEngine,
    selectedDomain,
    translatorConfig,
    setActiveTool,
    setMode,
    clearActiveTool,
    processTool,
    getDefaultOption,
    loadTranslatorConfig,
  }
})
