/**
 * Chat Store — multi-chat per paper, project-scoped memory.
 *
 * Each paper (project) holds many chats. The sidebar in ChatTab shows
 * papers; expanding one shows its chats. Memory is shared across all
 * chats inside a paper and lives in the backend (ProjectMemory table).
 *
 * Streaming state is kept PER conversation in `streams[convId]` so that
 * switching chats while one is "thinking" preserves the spinner and the
 * partial content; coming back to that chat shows the in-flight reply.
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import api from '../api/index.js'
import { usePaperStore } from './paper.js'
import { useUiStore } from './ui.js'
import { useLiteratureStore } from './literature.js'

const PROPOSAL_PREFIX = '<<PROPOSAL>>'

/**
 * Sanitize raw backend / network error messages before showing them to the
 * end user. Stack traces, SQL fragments, file paths, and DB internals are
 * useless to the user and leak implementation detail. The full original is
 * still visible in the network panel for developers.
 */
function _safeErrorMessage(raw) {
  const s = String(raw || '').trim()
  if (!s) return 'Terjadi kendala teknis. Coba kirim lagi sebentar.'
  // DB / SQL errors
  if (/psycopg2|sqlalchemy|UndefinedTable|relation .* does not exist|integrityerror|operationalerror/i.test(s)) {
    return 'Ada gangguan internal di server. Coba kirim lagi sebentar.'
  }
  // Python-y traceback / file paths / SQL keywords
  if (/traceback|\bsql\b|file ".*", line \d+|raise [a-z]/i.test(s)) {
    return 'Terjadi kendala teknis. Coba kirim lagi sebentar.'
  }
  // HTTP-status / upstream API hiccups
  if (/^api error: \d+|^http \d{3}$|status_code|upstream/i.test(s)) {
    return 'AI sedang sibuk. Coba kirim lagi sebentar.'
  }
  if (s.length > 240) return s.slice(0, 240) + '…'
  return s
}

export const useChatStore = defineStore('chat', () => {
  // Sidebar — one row per paper
  const paperChats = ref([])

  // Currently-open paper and its chat list
  const currentPaperId = ref(null)
  const conversations = ref([])           // chats for the current paper
  const currentConversationId = ref(null)

  // Per-conversation runtime state (in-memory only — survives across panel
  // tab switches but not full page reloads).
  // streams[convId] = { messages, isStreaming, streamingMessage, abortCtrl }
  const streams = ref({})

  // Reactive view of the active conversation. The component reads
  // `messages` / `isStreaming` / `streamingMessage` directly, but they are
  // proxied to the per-conversation entry below.
  const messages = ref([])
  const isStreaming = ref(false)
  const streamingMessage = ref(null)
  const error = ref(null)

  // Memory for the current paper
  const memory = ref([])

  // Active background job (full-paper generation) belonging to the current
  // paper but possibly started in a different chat. While this is set, the
  // input in the current chat is locked and a banner explains why.
  const activeJob = ref(null)  // { active, job_id, prompt, elapsed_seconds } | null
  let _activeJobTimer = null

  // Backwards-compat shims for ChatTab.vue (read-only at this scope). The
  // model picker is no longer wired to the request body; these exist only so
  // existing template/script references keep building. Removing them entirely
  // requires touching ChatTab, which is out of scope for this agent.
  const selectedModel = ref(null)
  function setModel(_value) { /* no-op: model picker disabled */ }

  const currentChat = computed(() =>
    conversations.value.find(c => c.id === currentConversationId.value)
  )

  const currentPaper = computed(() =>
    paperChats.value.find(p => p.paper_id === currentPaperId.value)
  )

  function _ensureStream(convId) {
    if (!streams.value[convId]) {
      streams.value[convId] = {
        messages: [],
        isStreaming: false,
        streamingMessage: null,
        abortCtrl: null,
      }
    }
    return streams.value[convId]
  }

  function _bindActive(convId) {
    const s = _ensureStream(convId)
    messages.value = s.messages
    isStreaming.value = s.isStreaming
    streamingMessage.value = s.streamingMessage
  }

  function _syncFromStream(convId) {
    const s = streams.value[convId]
    if (!s) return
    if (currentConversationId.value === convId) {
      messages.value = s.messages
      isStreaming.value = s.isStreaming
      streamingMessage.value = s.streamingMessage
    }
  }

  async function loadPaperChats() {
    try {
      const res = await api.get('/api/chat/papers')
      paperChats.value = res.data || []
      return paperChats.value
    } catch (e) {
      error.value = e.message
      return []
    }
  }

  async function loadConversations(paperId) {
    if (!paperId) return []
    try {
      const res = await api.get(`/api/papers/${paperId}/conversations`)
      conversations.value = res.data || []
      return conversations.value
    } catch (e) {
      error.value = e.message
      conversations.value = []
      return []
    }
  }

  async function loadMemory(paperId) {
    if (!paperId) {
      memory.value = []
      return []
    }
    try {
      const res = await api.get(`/api/papers/${paperId}/memory`)
      memory.value = res.data || []
      return memory.value
    } catch (e) {
      memory.value = []
      return []
    }
  }

  async function checkActiveJob() {
    if (!currentPaperId.value) { activeJob.value = null; return null }
    try {
      const res = await api.get(`/api/papers/${currentPaperId.value}/active-job`)
      activeJob.value = res.data?.active ? res.data : null
      return activeJob.value
    } catch { activeJob.value = null; return null }
  }

  function startActiveJobPolling(paperId) {
    stopActiveJobPolling()
    if (!paperId) return
    checkActiveJob()
    _activeJobTimer = setInterval(checkActiveJob, 4000)
  }

  function stopActiveJobPolling() {
    if (_activeJobTimer) { clearInterval(_activeJobTimer); _activeJobTimer = null }
  }

  async function deleteMemoryEntry(memId) {
    if (!currentPaperId.value || !memId) return
    try {
      await api.delete(`/api/papers/${currentPaperId.value}/memory/${memId}`)
      memory.value = memory.value.filter(m => m.id !== memId)
    } catch (e) {
      error.value = e.message
    }
  }

  /**
   * Open a paper: load its chats and memory, then open the latest chat
   * (or auto-create one if none exist).
   */
  async function openPaper(paperId) {
    if (!paperId) return null
    currentPaperId.value = paperId
    messages.value = []
    currentConversationId.value = null

    await Promise.all([
      loadConversations(paperId),
      loadMemory(paperId),
    ])

    startActiveJobPolling(paperId)

    let target = conversations.value[0]
    if (!target) {
      target = await createConversation(paperId)
    }
    if (target) {
      await openConversation(target.id)
    }
    return target
  }

  async function openConversation(convId) {
    if (!convId) return null
    try {
      const res = await api.get(`/api/chat/conversations/${convId}`)
      currentConversationId.value = res.data.id
      const s = _ensureStream(convId)
      // If a stream is already running for this conv, keep its in-memory
      // messages (which include the partial assistant bubble). Otherwise,
      // hydrate from the server-saved transcript.
      if (!s.isStreaming) {
        s.messages = res.data.messages || []
        s.streamingMessage = null
      }
      _bindActive(convId)

      // bump it in the local list
      const idx = conversations.value.findIndex(c => c.id === convId)
      if (idx >= 0) {
        conversations.value[idx] = {
          ...conversations.value[idx],
          ...res.data,
          message_count: (res.data.messages || []).length,
        }
      }
      return res.data
    } catch (e) {
      error.value = e.message
      return null
    }
  }

  async function createConversation(paperId, title = 'New Chat') {
    if (!paperId) return null
    try {
      const res = await api.post(`/api/papers/${paperId}/conversations`, { title })
      const conv = res.data
      conversations.value = [conv, ...conversations.value]
      // bump the paper sidebar entry
      const row = paperChats.value.find(p => p.paper_id === paperId)
      if (row) {
        row.chat_count = (row.chat_count || 0) + 1
        row.latest_chat_id = conv.id
        row.updated_at = new Date().toISOString()
      }
      return conv
    } catch (e) {
      error.value = e.message
      return null
    }
  }

  async function newChatForCurrentPaper() {
    const conv = await createConversation(currentPaperId.value)
    if (conv) {
      currentConversationId.value = conv.id
      _ensureStream(conv.id)
      _bindActive(conv.id)
    }
    return conv
  }

  async function renameConversation(convId, title) {
    try {
      const res = await api.patch(`/api/chat/conversations/${convId}`, { title })
      const idx = conversations.value.findIndex(c => c.id === convId)
      if (idx >= 0) conversations.value[idx] = { ...conversations.value[idx], ...res.data }
    } catch (e) {
      error.value = e.message
    }
  }

  async function deleteConversation(convId) {
    try {
      await api.delete(`/api/chat/conversations/${convId}`)
      conversations.value = conversations.value.filter(c => c.id !== convId)
      delete streams.value[convId]
      if (currentConversationId.value === convId) {
        currentConversationId.value = null
        messages.value = []
        // open another chat if any, else auto-create
        if (conversations.value[0]) {
          await openConversation(conversations.value[0].id)
        } else if (currentPaperId.value) {
          const conv = await createConversation(currentPaperId.value)
          if (conv) await openConversation(conv.id)
        }
      }
      // refresh paper count
      const row = paperChats.value.find(p => p.paper_id === currentPaperId.value)
      if (row) row.chat_count = Math.max(0, (row.chat_count || 1) - 1)
    } catch (e) {
      error.value = e.message
    }
  }

  async function clearCurrentChat() {
    if (!currentConversationId.value) return
    const convId = currentConversationId.value
    const paperId = currentPaperId.value
    try {
      await api.delete(`/api/chat/conversations/${convId}`)
      conversations.value = conversations.value.filter(c => c.id !== convId)
      delete streams.value[convId]
      currentConversationId.value = null
      messages.value = []
      // create a fresh empty chat in the same paper
      if (paperId) {
        const conv = await createConversation(paperId)
        if (conv) await openConversation(conv.id)
      }
    } catch (e) {
      error.value = e.message
    }
  }

  async function sendMessage(content) {
    const convId = currentConversationId.value
    if (!convId) return
    const stream = _ensureStream(convId)
    if (stream.isStreaming) return
    error.value = null

    // Block sending while another chat in this paper is generating a paper.
    // Show an inline assistant warning instead of a silent no-op so the user
    // understands why their message did not go through.
    if (activeJob.value && activeJob.value.active) {
      stream.messages.push({
        id: Date.now(),
        role: 'user',
        content,
        created_at: new Date().toISOString(),
      })
      stream.messages.push({
        id: Date.now() + 1,
        role: 'assistant',
        content: '⚠️ Chat lain di paper ini masih generate paper. Tunggu selesai dulu, atau lakukan hal lain (edit Section, Figures, dll) sambil menunggu.',
        created_at: new Date().toISOString(),
      })
      _syncFromStream(convId)
      return
    }

    // Auto-rename a fresh chat from its first user message — the backend already
    // does this on its side, but updating the local state immediately keeps the
    // sidebar and the toolbar title in sync without waiting for a full reload.
    const conv = conversations.value.find(c => c.id === convId)
    if (conv && (!conv.title || conv.title === 'New Chat')) {
      const newTitle = content.length > 60
        ? content.slice(0, 60) + '…'
        : content
      conv.title = newTitle
    }

    stream.messages.push({
      id: Date.now(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    })

    stream.isStreaming = true
    stream.streamingMessage = {
      id: null,
      role: 'assistant',
      content: '',
      thinking: '',
      tool_calls: [],
      created_at: new Date().toISOString(),
    }
    stream.messages.push(stream.streamingMessage)

    let memoryTouched = false
    stream.abortCtrl = new AbortController()
    _syncFromStream(convId)

    try {
      const csrf = (document.cookie.match(/(?:^|;\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
      const payload = { content }
      const response = await fetch(
        `/api/chat/conversations/${convId}/messages`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': decodeURIComponent(csrf),
          },
          body: JSON.stringify(payload),
          signal: stream.abortCtrl.signal,
        }
      )

      if (!response.ok) {
        // Backend may reject the request because another chat is already
        // running a full-paper generation for this paper. Surface a friendly
        // explanation and refresh the active-job state so the banner appears.
        if (response.status === 409) {
          let payload = null
          try { payload = await response.json() } catch { /* ignore */ }
          if (payload && payload.code === 'GENERATION_IN_PROGRESS') {
            if (stream.streamingMessage) {
              stream.streamingMessage.content =
                '⚠️ Chat lain di paper ini masih generate paper. Tunggu selesai dulu, atau lakukan hal lain (edit Section, Figures, dll) sambil menunggu.'
            }
            checkActiveJob()
            return
          }
        }
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              _handleSSEEvent(convId, currentEvent, data)
              if (
                currentEvent === 'tool_call' &&
                ['SaveMemory', 'DeleteMemory'].includes(data.name)
              ) {
                memoryTouched = true
              }
            } catch { /* skip malformed */ }
          }
        }
      }

      // Update conversation list ordering / counts
      const cIdx = conversations.value.findIndex(c => c.id === convId)
      if (cIdx >= 0) {
        const cConv = conversations.value[cIdx]
        cConv.message_count = (cConv.message_count || 0) + 2
        cConv.updated_at = new Date().toISOString()
        // float to top
        conversations.value = [
          cConv,
          ...conversations.value.filter(c => c.id !== cConv.id),
        ]
      }
      const row = paperChats.value.find(c => c.paper_id === currentPaperId.value)
      if (row) {
        row.message_count = (row.message_count || 0) + 2
        row.updated_at = new Date().toISOString()
        paperChats.value = [
          row,
          ...paperChats.value.filter(c => c.paper_id !== currentPaperId.value),
        ]
      }

      if (memoryTouched && currentPaperId.value) {
        await loadMemory(currentPaperId.value)
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        if (stream.streamingMessage) {
          stream.streamingMessage.content += '\n\n_(dihentikan oleh pengguna)_'
        }
      } else {
        const friendly = _safeErrorMessage(e && e.message)
        error.value = friendly
        if (stream.streamingMessage) {
          stream.streamingMessage.content += `\n\n_${friendly}_`
        }
      }
    } finally {
      stream.isStreaming = false
      stream.streamingMessage = null
      stream.abortCtrl = null
      _syncFromStream(convId)
    }
  }

  function stopStreaming() {
    const convId = currentConversationId.value
    const s = convId && streams.value[convId]
    if (s && s.abortCtrl) {
      try { s.abortCtrl.abort() } catch { /* ignore */ }
    }
  }

  /**
   * Push a synthetic assistant message into the currently-active conversation
   * WITHOUT hitting the backend. Used by the editor (paper store) to nudge the
   * chat with a context-aware question when the user adds/uploads an image, so
   * the AI can later generate a caption + a `create image"..."` prompt.
   *
   * Silent no-op when no chat is open (e.g. user is on a tab where chat is not
   * active yet) — the editor change still proceeds.
   */
  function injectAssistantMessage(content) {
    const convId = currentConversationId.value
    if (!convId || !content) return
    const stream = _ensureStream(convId)
    const msg = {
      id: `synthetic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: 'assistant',
      content: String(content),
      created_at: new Date().toISOString(),
      metadata: { kind: 'system_note', synthetic: true },
    }
    stream.messages.push(msg)
    _syncFromStream(convId)
  }

  /**
   * Post the user's answers from a MultiQuestionCard as a single user message.
   * `answers` is an array of {key, value}. The text is formatted as a simple
   * "Jawaban saya:\nkey: value\n..." block so the backend can parse it like
   * any other user reply.
   */
  async function submitMultiQuestionAnswers(answers) {
    if (!Array.isArray(answers) || answers.length === 0) return
    const lines = answers
      .filter(a => a && a.key && a.value !== undefined && a.value !== null)
      .map(a => `${a.key}: ${a.value}`)
      .join('\n')
    if (!lines) return
    return await sendMessage(`Jawaban saya:\n${lines}`)
  }

  function _handleSSEEvent(convId, event, data) {
    // 'open_tab' is paper-scoped, not chat-scoped: it can fire even after the
    // streamingMessage has been finalised. Handle it before the early-return
    // guard below so it doesn't get swallowed.
    if (event === 'open_tab') {
      try {
        const ui = useUiStore()
        const lit = useLiteratureStore()
        const paperStore = usePaperStore()
        const pid = paperStore.currentPaperId
        const tab = data && data.tab
        if (pid && tab) {
          ui.requestTab(pid, tab)
          if (data.reason === 'slr_started' && data.job_id) {
            lit.attachJob({
              job_id:   data.job_id,
              query:    data.query,
              top_k:    data.top_k,
              ai_model: data.ai_model,
            })
          }
        }
      } catch { /* defensive: never break the SSE loop */ }
      return
    }

    const stream = streams.value[convId]
    if (!stream || !stream.streamingMessage) return
    const msg = stream.streamingMessage

    // Attach a chips payload to the currently-streaming assistant message so
    // ChatMessage.vue can render ActionChips beside its content. Backend
    // (chat.py) emits this as a typed 'chips' SSE event after a ProposeChips
    // tool call resolves.
    if (event === 'chips') {
      msg.metadata = {
        ...(msg.metadata || {}),
        kind: 'chips',
        chips: Array.isArray(data?.chips) ? data.chips : [],
        context_hint: data?.context_hint || '',
      }
      _syncFromStream(convId)
      return
    }
    switch (event) {
      case 'text':
        msg.content += data.content
        break
      case 'thinking':
        msg.thinking += data.content
        break
      case 'tool_call':
        msg.tool_calls.push({
          name: data.name,
          arguments: data.arguments,
          result: null,
          status: 'running',
        })
        break
      case 'tool_result': {
        const tc = msg.tool_calls.find(
          t => t.name === data.name && t.status === 'running'
        )
        if (tc) {
          tc.result = data.result
          tc.status = 'done'
        }
        // If this tool result contains a proposal payload, route it to the
        // paper store. Journal switches and DOCX exports auto-apply (no diff);
        // text-content changes go through the pending-review flow.
        if (typeof data.result === 'string' && data.result.startsWith(PROPOSAL_PREFIX)) {
          try {
            const proposal = JSON.parse(data.result.slice(PROPOSAL_PREFIX.length))
            const paperStore = usePaperStore()
            if (proposal.kind === 'journal' || proposal.kind === 'export_docx') {
              paperStore.applyImmediate(proposal)
            } else if (proposal.kind === 'generate_full' || proposal.kind === 'paper_progress') {
              // Full-paper job started by the AI: hand it to the paper store
              // so the existing job-polling spinner kicks in and loads the
              // result into the editor when ready. Also attach the job_id to
              // the streaming message so ChatMessage can render an inline
              // PaperProgressBubble.
              paperStore.attachAiJob(proposal.job_id, proposal.prompt)
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'paper_progress',
                job_id: proposal.job_id,
                prompt: proposal.prompt,
              }
            } else if (proposal.kind === 'slr_job') {
              // Fallback path for SLR auto-open in case the dedicated
              // `open_tab` SSE event was not emitted (older backend builds).
              const ui = useUiStore()
              const lit = useLiteratureStore()
              const pid = paperStore.currentPaperId
              if (pid) {
                ui.requestTab(pid, 'literature')
                lit.attachJob({
                  job_id:   proposal.job_id,
                  query:    proposal.query,
                  top_k:    proposal.top_k,
                  ai_model: proposal.ai_model,
                })
              }
            } else if (proposal.kind === 'propose_revisi') {
              // Paraphrase / FixGrammar / Translate proposals: stamp the
              // payload onto the streaming assistant message so ChatMessage
              // can render an inline RevisiProposalCard with diff + accept/
              // reject buttons. The card calls paper store actions on accept.
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'propose_revisi',
                tool: proposal.tool,
                scope: proposal.scope,
                section_index: proposal.section_index,
                content_index: proposal.content_index,
                text: proposal.text,
                rewrite: proposal.rewrite,
                target_language: proposal.target_language,
              }
            } else if (proposal.kind === 'chart_proposal') {
              // Chart proposal: stamp metadata so ChatMessage can render
              // an inline ChartPreviewCard with the rendered preview image
              // and a small spec describing the chart.
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'chart_proposal',
                url: proposal.url || proposal.image_url || '',
                image_id: proposal.image_id ?? null,
                spec: proposal.spec || null,
                title: proposal.title || '',
                section_index: proposal.section_index,
                content_index: proposal.content_index,
              }
            } else if (proposal.kind === 'file_review') {
              // Long file review: backend returns word_count + head/tail
              // preview + suggested kinds (e.g. cite, summarize, extract).
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'file_review',
                file_id: proposal.file_id ?? null,
                filename: proposal.filename || '',
                word_count: proposal.word_count || 0,
                head: proposal.head || '',
                tail: proposal.tail || '',
                suggested_kinds: Array.isArray(proposal.suggested_kinds)
                  ? proposal.suggested_kinds
                  : [],
              }
            } else if (proposal.kind === 'validation_error') {
              // Validation error: warning banner with optional retry / SLR
              // action. error_code drives which extra chip is shown.
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'validation_error',
                error_code: proposal.error_code || '',
                message: proposal.message || '',
                hint: proposal.hint || '',
                retry_prompt: proposal.retry_prompt || '',
              }
            } else if (proposal.kind === 'image_prompt_review') {
              // Post-paper image-prompt review (also injected from
              // paperJobs hook). Stamp metadata so ChatMessage can render
              // a checklist-style review UI.
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'image_prompt_review',
                images: Array.isArray(proposal.images) ? proposal.images : [],
                paper_id: proposal.paper_id ?? null,
              }
            } else if (proposal.kind === 'multi_question') {
              // Multi-question card: backend sends a list of questions, each
              // with chip options + free-text fallback. ChatMessage renders
              // MultiQuestionCard which submits answers as a single user
              // message via submitMultiQuestionAnswers.
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'multi_question',
                questions: Array.isArray(proposal.questions) ? proposal.questions : [],
              }
            } else if (proposal.kind === 'review_plan') {
              // Review plan: AI announces a multi-step review pass over the
              // current paper. Visual-only notice for now, with a cancel hook.
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'review_plan',
                directive: proposal.directive || '',
                scope: proposal.scope || 'whole',
              }
            } else if (proposal.kind === 'revise_data') {
              // Data revision notice for the current Section 4 (Results).
              msg.metadata = {
                ...(msg.metadata || {}),
                kind: 'revise_data',
                directive: proposal.directive || '',
              }
            } else {
              paperStore.pushProposal(proposal)
            }
          } catch { /* malformed proposal — ignore */ }
        }
        break
      }
      case 'done':
        if (data.message_id) msg.id = data.message_id
        break
      case 'error':
        msg.content += `\n\n_${_safeErrorMessage(data && data.message)}_`
        break
    }
    _syncFromStream(convId)
  }

  function reset() {
    stopActiveJobPolling()
    activeJob.value = null
    currentPaperId.value = null
    currentConversationId.value = null
    conversations.value = []
    messages.value = []
    memory.value = []
    streamingMessage.value = null
    streams.value = {}
    error.value = null
  }

  return {
    paperChats,
    currentPaperId,
    currentPaper,
    currentConversationId,
    currentChat,
    conversations,
    messages,
    memory,
    isStreaming,
    streamingMessage,
    error,
    activeJob,
    selectedModel,
    setModel,
    loadPaperChats,
    loadConversations,
    loadMemory,
    deleteMemoryEntry,
    openPaper,
    openConversation,
    createConversation,
    newChatForCurrentPaper,
    renameConversation,
    deleteConversation,
    clearCurrentChat,
    sendMessage,
    submitMultiQuestionAnswers,
    stopStreaming,
    injectAssistantMessage,
    checkActiveJob,
    startActiveJobPolling,
    stopActiveJobPolling,
    reset,
    // Backwards-compat aliases (in case other components still call them)
    openPaperChat: openPaper,
  }
})
