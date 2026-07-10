import { ref, defineStore } from 'pinia'

export const useGlobalChatStore = defineStore('global', () => {
  const messages = ref([])
  const isStreaming = ref(false)
  const streamingMessage = ref(null)
  const inputValue = ref('')
  const SESSION_KEY = 'global_chat_messages'

  // Load messages from localStorage on init
  const loadMessages = () => {
    try {
      const saved = localStorage.getItem(SESSION_KEY)
      if (saved) {
        messages.value = JSON.parse(saved)
      }
    } catch (e) {
      console.warn('Failed to load global chat from localStorage', e)
      messages.value = []
    }
  }

  // Save messages to localStorage
  const saveMessages = () => {
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(messages.value))
    } catch (e) {
      console.warn('Failed to save global chat to localStorage', e)
    }
  }

  // Add a user message and simulate a response (for demo)
  const sendMessage = async (text) => {
    if (!text.trim() || isStreaming.value) return

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString()
    }

    messages.value.push(userMessage)
    saveMessages()

    // Simulate AI response (in real implementation, this would call a backend)
    isStreaming.value = true
    streamingMessage.value = {
      id: null,
      role: 'assistant',
      content: '',
      thinking: '',
      tool_calls: [],
      created_at: new Date().toISOString()
    }

    // Simulate streaming by adding dots every 300ms
    let dots = 0
    const interval = setInterval(() => {
      dots = (dots + 1) % 4
      streamingMessage.value.content = 'Thinking' + '.'.repeat(dots)
    }, 300)

    // Simulate delay
    await new Promise(resolve => setTimeout(resolve, 2000))

    clearInterval(interval)
    isStreaming.value = false
    const aiMessage = {
      id: Date.now() + 1,
      role: 'assistant',
      content: 'This is a simulated AI response. In the real implementation, this would connect to the backend for global chat.',
      created_at: new Date().toISOString()
    }
    messages.value.push(aiMessage)
    streamingMessage.value = null
    saveMessages()
  }

  const clearChat = () => {
    messages.value = []
    isStreaming.value = false
    streamingMessage.value = null
    saveMessages()
  }

  // Initialize
  loadMessages()

  return {
    messages,
    isStreaming,
    streamingMessage,
    inputValue,
    sendMessage,
    clearChat,
    loadMessages,
    saveMessages
  }
})