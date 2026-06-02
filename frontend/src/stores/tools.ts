// @ts-nocheck
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/index.js'

const API_BASE = '/api'

export const useToolsStore = defineStore('tools', () => {
  const activeTool = ref(null)
  const inputText = ref('')
  const outputText = ref('')
  const isProcessing = ref(false)
  const selectedOption = ref('')
  const toolResult = ref(null)
  const error = ref(null)

  const TOOLS = [
    { id: 'paraphrase', icon: '✍️', tint: '#1265c8', title: 'Paraphrase', desc: 'Rewrite passages in a different tone or strength while keeping the meaning.' },
    { id: 'translate', icon: '🌐', tint: '#1265c8', title: 'Translator', desc: 'Translate between Indonesian, English and 20+ languages — academic register.' },
    { id: 'humanizer', icon: '🧬', tint: '#2f9d6e', title: 'Humanizer', desc: 'Rework AI-sounding prose to read naturally and pass AI detectors.' },
    { id: 'detector', icon: '🔍', tint: '#d9a718', title: 'AI Detector', desc: 'Estimate how likely a passage reads as AI-generated.' },
    { id: 'plagiarism', icon: '📋', tint: '#c43655', title: 'Plagiarism Check', desc: 'Scan against published sources and report a similarity score.' },
    { id: 'grammar', icon: '✓', tint: '#238f7f', title: 'Grammar & Style', desc: 'Fix grammar, clarity and academic style issues inline.' },
    { id: 'summarize', icon: '📝', tint: '#0b4088', title: 'Summarize', desc: 'Condense a section or reference into a TL;DR or abstract.' },
    { id: 'citation', icon: '📑', tint: '#c28d0d', title: 'Citation Generator', desc: 'Turn a DOI, URL or title into a formatted reference.' },
  ]

  function getDefaultOption(toolId) {
    switch (toolId) {
      case 'translate': return 'Indonesian'
      case 'paraphrase': return 'Standard'
      case 'humanizer': return 'Standard'
      case 'summarize': return 'TL;DR'
      default: return 'Standard'
    }
  }

  function setActiveTool(tool) {
    activeTool.value = tool
    selectedOption.value = getDefaultOption(tool.id)
    outputText.value = ''
    toolResult.value = null
    error.value = null
  }

  function clearActiveTool() {
    activeTool.value = null
    inputText.value = ''
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
      const payload = {
        text: inputText.value,
        option: selectedOption.value,
      }

      const response = await fetch(`${API_BASE}/tools/${activeTool.value.id}`, {
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
    outputText,
    isProcessing,
    selectedOption,
    toolResult,
    error,
    TOOLS,
    setActiveTool,
    clearActiveTool,
    processTool,
    getDefaultOption,
  }
})
