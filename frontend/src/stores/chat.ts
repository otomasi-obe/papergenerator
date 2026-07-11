// @ts-nocheck
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

let _msgIdCounter = 0
function _nextMsgId() { return Date.now() * 1000 + (++_msgIdCounter) }

/**
 * Sanitize raw backend / network error messages before showing them to the
 * end user. Stack traces, SQL fragments, file paths, and DB internals are
 * useless to the user and leak implementation detail. The full original is
 * still visible in the network panel for developers.
 */
function _safeErrorMessage(raw) {
  const s = String(raw || '').trim()
  if (!s) return 'Terjadi kendala teknis. Coba kirim lagi sebentar.'

  // Already user-friendly (from backend SSE 'error' events — Indonesian messages)
  if (/^(gagal|terjadi|ai belum|ai terlalu|koneksi|server sedang|terlalu banyak|api key|model ai|anda tidak|sesi anda|resource tidak|data yang)/i.test(s)) {
    return s
  }

  // Connection timeout (from our retry logic)
  if (/connection timeout/i.test(s)) {
    return '⏱️ Koneksi ke server timeout. Periksa koneksi internet Anda.'
  }

  // Network errors
  if (/failed to fetch|network error|networkerror|net::err/i.test(s)) {
    return '🌐 Tidak bisa terhubung ke server. Periksa koneksi internet Anda dan coba lagi.'
  }

  // HTTP errors with specific status codes
  if (/http 401|unauthorized/i.test(s)) {
    return '🔒 Sesi Anda telah berakhir. Silakan login kembali.'
  }
  if (/http 403|forbidden/i.test(s)) {
    return '🚫 Anda tidak memiliki akses untuk melakukan ini.'
  }
  if (/http 404|not found/i.test(s)) {
    return '❓ Resource tidak ditemukan. Mungkin sudah dihapus.'
  }
  if (/http 429|too many requests|rate limit/i.test(s)) {
    return '⏸️ Terlalu banyak request. Tunggu sebentar lalu coba lagi.'
  }
  if (/http 500|http 502|http 503|http 504|internal server error|bad gateway|service unavailable|gateway timeout/i.test(s)) {
    return '⚠️ Server sedang mengalami gangguan. Coba lagi dalam beberapa saat.'
  }

  // DB / SQL errors - specific mappings with actionable recovery
  if (/UndefinedTable|relation .* does not exist/i.test(s)) {
    return '🔧 Database belum siap (tabel tidak ditemukan). Hubungi admin untuk menjalankan migrasi database, atau coba refresh halaman.'
  }
  if (/IntegrityError|duplicate key|unique constraint|foreign key constraint/i.test(s)) {
    return '⚠️ Data yang Anda masukkan sudah ada atau tidak valid. Coba ubah input Anda atau refresh halaman untuk melihat data terbaru.'
  }
  if (/OperationalError|database is locked|connection refused|connection timeout/i.test(s)) {
    return '🔌 Koneksi ke database terputus. Tunggu beberapa saat lalu coba lagi, atau hubungi admin jika masalah berlanjut.'
  }
  if (/psycopg2|sqlalchemy/i.test(s)) {
    return '💾 Terjadi masalah saat menyimpan data. Coba kirim lagi, atau hubungi admin jika error terus muncul.'
  }

  // Python-y traceback / file paths / SQL keywords
  if (/traceback|\bsql\b|file ".*", line \d+|raise [a-z]/i.test(s)) {
    return 'Terjadi kendala teknis. Coba kirim lagi sebentar.'
  }

  // HTTP-status / upstream API hiccups (only match exact patterns, not "upstream" as substring)
  if (/^api error: \d+|^http \d{3}$|^status_code:/i.test(s)) {
    return 'AI belum berhasil merespons. Coba lagi atau ubah permintaan Anda.'
  }

  // Truncate very long messages
  if (s.length > 240) return s.slice(0, 240) + '…'
  return s
}

/**
 * Language-aware UI string helper.
 * Returns English or Indonesian text based on the current paper language.
 */
function _uiStr(id: string, en: string): string {
  try {
    const paperStore = usePaperStore()
    if (paperStore.paper.language === 'en') return en
  } catch { /* ignore */ }
  return id
}

/**
 * Convert a PROPOSAL payload into a user-friendly message for display in the
 * chat. The structured data is already handled (stored in msg.metadata or
 * routed to the paper store), so this is just a confirmation message.
 */
function _getFriendlyProposalMessage(proposal) {
  const kind = proposal.kind || ''
  
  switch (kind) {
    case 'paper_progress':
    case 'generate_full':
      return `✓ Paper generation started (job: ${proposal.job_id || 'unknown'}). Editor akan auto-load hasilnya.`
    
    case 'slr_job':
      return `✓ Literature search started for "${proposal.query || 'query'}". Check Literature tab untuk hasilnya.`
    
    case 'journal':
      return `✓ Journal template switched to: ${proposal.value || 'unknown'}`
    
    case 'export_docx':
      return `✓ DOCX export started. File akan tersedia di tab Export.`
    
    case 'title':
      return `✓ Title proposal: "${(proposal.value || '').slice(0, 80)}${(proposal.value || '').length > 80 ? '...' : ''}"`
    
    case 'abstract':
      return `✓ Abstract proposal (${(proposal.value || '').length} chars)`
    
    case 'keywords':
      const kw = Array.isArray(proposal.value) ? proposal.value : []
      return `✓ Keywords proposal: ${kw.slice(0, 3).join(', ')}${kw.length > 3 ? ` +${kw.length - 3} more` : ''}`
    
    case 'section':
      return `✓ Section ${proposal.section_index != null ? proposal.section_index + 1 : '?'} proposal: "${(proposal.title || '').slice(0, 50)}"`
    
    case 'reference':
      return `✓ Reference [${proposal.ref_index != null ? proposal.ref_index + 1 : '?'}] proposal`
    
    case 'propose_revisi':
      return `✓ ${proposal.tool || 'Revision'} proposal ready (scope: ${proposal.scope || 'paragraph'})`
    
    case 'chart_proposal':
      return `✓ Chart generated: "${(proposal.title || 'Untitled').slice(0, 50)}"`
    
    case 'file_review':
      return `✓ File review: ${proposal.filename || 'unknown'} (${proposal.word_count || 0} words)`
    
    case 'validation_error':
      return `⚠ ${proposal.message || 'Validation error'}`
    
    case 'multi_question':
      const qCount = Array.isArray(proposal.questions) ? proposal.questions.length : 0
      return `✓ ${qCount} question${qCount !== 1 ? 's' : ''} ready`
    
    case 'ask_user':
      return `❓ ${proposal.question || 'Pertanyaan untuk Anda'}`
    
    case 'review_plan':
      return `✓ Review plan: ${proposal.directive || 'starting review'}`
    
    case 'revise_data':
      return `✓ Data revision: ${proposal.directive || 'updating Section 4'}`
    
    case 'chips':
      return `✓ Suggestion chips ready`
    
    case 'setting_saved':
      return `✓ Setting saved: ${proposal.key || 'unknown'} = ${proposal.value || ''}`
    
    case 'file_classified':
      return `✓ File classified: ${proposal.original_name || 'unknown'} as ${proposal.file_kind || 'other'}`
    
    case 'file_classified_error':
      return `✗ File classification failed: ${proposal.error || 'unknown error'}`
    
    default:
      // Generic fallback for unknown proposal types
      return `✓ Action completed (${kind || 'unknown'})`
  }
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
  // streams[convId] = { messages, isStreaming, streamingMessage, abortCtrl, connectionState }
  const streams = ref({})

  // Session persistence for streaming state
  const SESSION_KEY = 'chat_streams_state'

  function _saveStreamsToSession() {
    try {
      const serializable = {}
      for (const [convId, s] of Object.entries(streams.value)) {
        if (s.isStreaming && s.streamingMessage) {
          serializable[convId] = {
            isStreaming: true,
            streamingMessage: {
              content: s.streamingMessage.content || '',
              thinking: s.streamingMessage.thinking || '',
              tool_calls: s.streamingMessage.tool_calls || [],
              created_at: s.streamingMessage.created_at || new Date().toISOString(),
            },
            searchResults: s.searchResults || [],
            searchMessage: s.searchMessage || '',
            savedAt: Date.now(),
          }
        }
      }
      if (Object.keys(serializable).length) {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(serializable))
      } else {
        sessionStorage.removeItem(SESSION_KEY)
      }
    } catch { /* ignore */ }
  }

  function _restoreStreamsFromSession() {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY)
      if (!raw) return
      const saved = JSON.parse(raw)
      // Only restore streams saved within last 15 minutes
      const cutoff = Date.now() - 15 * 60 * 1000
      const restoredConvIds = []
      for (const [convId, data] of Object.entries(saved)) {
        if (data.savedAt && data.savedAt > cutoff && data.isStreaming) {
          const stream = _ensureStream(convId)
          stream.isStreaming = true
          stream.connectionState = 'reconnecting'
          stream.streamingMessage = {
            id: null,
            role: 'assistant',
            content: data.streamingMessage?.content || '',
            thinking: data.streamingMessage?.thinking || '',
            tool_calls: data.streamingMessage?.tool_calls || [],
            created_at: data.streamingMessage?.created_at || new Date().toISOString(),
          }
          stream.searchResults = data.searchResults || []
          stream.searchMessage = data.searchMessage || ''
          stream.messages = [...stream.messages, stream.streamingMessage]
          restoredConvIds.push(convId)
        }
      }
      // BUG 1/2: Start resume poller for each restored stream so the spinner
      // doesn't stay stuck and content updates from Redis snapshots.
      for (const convId of restoredConvIds) {
        _startResumePoll(convId)
      }
    } catch { /* ignore */ }
  }

  function _clearSessionStream(convId) {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY)
      if (!raw) return
      const saved = JSON.parse(raw)
      delete saved[convId]
      if (Object.keys(saved).length) {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(saved))
      } else {
        sessionStorage.removeItem(SESSION_KEY)
      }
    } catch { /* ignore */ }
  }

  // Lock to prevent concurrent sendMessage calls (race condition guard).
  // Set true while a send is in-flight, cleared in finally.
  let _sendingLock = false

  // Throttle for userState DB writes during streaming (BUG 4)
  let _lastUserStateSync = 0

  // Reactive view of the active conversation. The component reads
  // `messages` / `isStreaming` / `streamingMessage` directly, but they are
  // proxied to the per-conversation entry below.
  const messages = ref([])
  const isStreaming = ref(false)
  const streamingMessage = ref(null)
  const connectionState = ref('idle') // 'idle' | 'connecting' | 'connected' | 'disconnected' | 'retrying'
  const streamPhase = ref('idle') // 'idle' | 'sending' | 'thinking' | 'composing' | 'streaming' | 'done'
  const searchResults = ref<any[]>([])
  const searchMessage = ref('')
  const error = ref(null)

  // Active background job (full-paper generation) belonging to the current
  // paper but possibly started in a different chat. While this is set, the
  // input in the current chat is locked and a banner explains why.
  const activeJob = ref(null)  // { active, job_id, prompt, elapsed_seconds } | null
  let _activeJobTimer = null

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
        connectionState: 'idle',
        streamPhase: 'idle',
      }
    }
    return streams.value[convId]
  }

  function _bindActive(convId) {
    const s = _ensureStream(convId)
    messages.value = s.messages
    isStreaming.value = s.isStreaming
    streamingMessage.value = s.streamingMessage
    connectionState.value = s.connectionState
    streamPhase.value = s.streamPhase || 'idle'
    searchResults.value = s.searchResults || []
    searchMessage.value = s.searchMessage || ''
  }

  async function _syncFromStream(convId) {
    const s = streams.value[convId]
    if (!s) return
    if (currentConversationId.value === convId) {
      messages.value = s.messages
      isStreaming.value = s.isStreaming
      streamingMessage.value = s.streamingMessage
      connectionState.value = s.connectionState
      streamPhase.value = s.streamPhase || 'idle'
      searchResults.value = s.searchResults || []
      searchMessage.value = s.searchMessage || ''
    }
    // Persist streaming state to userState (DB) for cross-device/refresh survival
    // Throttle: max once per 5 seconds to avoid DB write flood (BUG 4)
    if (s.isStreaming && s.streamingMessage && Date.now() - _lastUserStateSync > 5000) {
      _lastUserStateSync = Date.now()
      try {
        const { useUserStateStore } = await import('./userState')
        const userState = useUserStateStore()
        userState.set('chat.streaming', null, {
          conv_id: convId,
          content: s.streamingMessage.content || '',
          thinking: s.streamingMessage.thinking || '',
          started_at: s.streamingMessage.created_at || new Date().toISOString(),
          saved_at: Date.now(),
        })
      } catch { /* ignore if userState not ready */ }
    }
    _saveStreamsToSession()
  }

  function _hydrateMessageMetadata(message) {
    if (!message || message.metadata?.kind) return message
    const calls = Array.isArray(message.tool_calls) ? message.tool_calls : []
    for (let index = calls.length - 1; index >= 0; index -= 1) {
      const result = calls[index]?.result
      if (typeof result !== 'string' || !result.startsWith(PROPOSAL_PREFIX)) continue
      try {
        const proposal = JSON.parse(result.slice(PROPOSAL_PREFIX.length))
        // Reconstruct metadata for ALL proposal kinds from tool_calls
        switch (proposal.kind) {
          case 'multi_question':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'multi_question',
                questions: Array.isArray(proposal.questions) ? proposal.questions : [],
                phase: proposal.phase,
                phase_name: proposal.phase_name,
                description: proposal.description,
              },
            }
          case 'ask_user':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'ask_user',
                question: proposal.question || '',
                options: Array.isArray(proposal.options) ? proposal.options : [],
              },
            }
          case 'chips':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'chips',
                chips: Array.isArray(proposal.chips) ? proposal.chips : [],
                context_hint: proposal.context_hint || '',
              },
            }
          case 'chart_proposal':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'chart_proposal',
                url: proposal.url || proposal.image_url || '',
                image_id: proposal.image_id ?? null,
                spec: proposal.spec || null,
                title: proposal.title || '',
                section_index: proposal.section_index,
                content_index: proposal.content_index,
              },
            }
          case 'revise_data':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'revise_data',
                directive: proposal.directive || '',
              },
            }
          case 'propose_revisi':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'propose_revisi',
                tool: proposal.tool,
                scope: proposal.scope,
                section_index: proposal.section_index,
                content_index: proposal.content_index,
                text: proposal.text,
                rewrite: proposal.rewrite,
                target_language: proposal.target_language,
              },
            }
          case 'file_review':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'file_review',
                file_id: proposal.file_id ?? null,
                filename: proposal.filename || '',
                word_count: proposal.word_count || 0,
                head: proposal.head || '',
                tail: proposal.tail || '',
                suggested_kinds: Array.isArray(proposal.suggested_kinds) ? proposal.suggested_kinds : [],
              },
            }
          case 'review_plan':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'review_plan',
                directive: proposal.directive || '',
                scope: proposal.scope || 'whole',
              },
            }
          case 'image_prompt_review':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'image_prompt_review',
                images: Array.isArray(proposal.images) ? proposal.images : [],
                paper_id: proposal.paper_id ?? null,
              },
            }
          case 'validation_error':
            return {
              ...message,
              metadata: {
                ...(message.metadata || {}),
                kind: 'validation_error',
                error_code: proposal.error_code || '',
                message: proposal.message || '',
                hint: proposal.hint || '',
                retry_prompt: proposal.retry_prompt || '',
              },
            }
          default:
            break
        }
      } catch { /* ignore malformed persisted proposal */ }
    }
    return message
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
    try {
      const url = paperId ? `/api/papers/${paperId}/conversations` : '/api/chat/conversations'
      const res = await api.get(url)
      conversations.value = res.data || []
      return conversations.value
    } catch (e) {
      // 404 = paper doesn't exist (deleted). Don't surface as a chat error;
      // the editor page handles stale-paper cleanup.
      if (e?.response?.status !== 404) {
        error.value = e.message
      }
      conversations.value = []
      return []
    }
  }

  // Load ALL user conversations (global + paper-linked) for dashboard view
  async function loadAllConversations() {
    try {
      const res = await api.get('/api/chat/conversations')
      conversations.value = res.data || []
      return conversations.value
    } catch (e) {
      error.value = e.message
      conversations.value = []
      return []
    }
  }

  async function checkActiveJob() {
    if (!currentPaperId.value) { activeJob.value = null; return null }
    if (_checkingJob) return null  // Re-entrancy guard
    _checkingJob = true
    try {
      const res = await api.get(`/api/papers/${currentPaperId.value}/active-jobs`)
      activeJob.value = res.data?.active ? res.data : null
      return activeJob.value
    } catch { activeJob.value = null; return null }
    finally { _checkingJob = false }
  }
  let _checkingJob = false

  function startActiveJobPolling(paperId) {
    stopActiveJobPolling()
    if (!paperId) return
    checkActiveJob()
    _activeJobTimer = setInterval(checkActiveJob, 4000)
  }

  function stopActiveJobPolling() {
    if (_activeJobTimer) { clearInterval(_activeJobTimer); _activeJobTimer = null }
  }

  let _openPaperGen = 0
  async function openPaper(paperId) {
    if (!paperId) return null
    const gen = ++_openPaperGen

    // [FIX] paperId = view context only. NEVER reset active conversation.
    // The conversation persists across navigation (dashboard ↔ editor).
    // Only update currentPaperId and sync the active conversation's messages.

    const prevPaperId = currentPaperId.value
    currentPaperId.value = paperId

    // Start job polling for this paper
    startActiveJobPolling(paperId)

    // If we don't have messages loaded for the current conversation,
    // load them (they were from a different conversation or empty).
    if (currentConversationId.value) {
      const stream = streams.value[currentConversationId.value]
      if (!stream || stream.messages.length === 0) {
        // Load messages for the active conversation (it's still the same conv)
        await openConversation(currentConversationId.value)
      }
      // IMPORTANT: DO NOT call loadConversations(paperId) here!
      // That would replace the conversations list and lose the global conversation.
      // The active conversation persists regardless of paperId.
      return currentChat
    }

    // If no active conversation, create one for this paper
    if (!currentConversationId.value) {
      await loadConversations(paperId)
      if (gen !== _openPaperGen) return null

      let target = null
      try {
        const savedConvId = localStorage.getItem('chat_last_conv_id')
        if (savedConvId) {
          target = conversations.value.find(c => c.id === savedConvId) || null
        }
      } catch { /* ignore */ }
      if (!target) {
        target = conversations.value[0]
      }
      if (!target) {
        target = await createConversation(paperId)
      }
      if (target) {
        await openConversation(target.id)
      }
    }

    return currentChat
  }

  // ── Resume poller for streams reconnected after a page refresh ────────────
  // When the user refreshes mid-stream, openConversation() restores the Redis
  // snapshot and sets isStreaming=true, but there is no live SSE socket anymore.
  // Without a poller the spinner stays stuck and the content is frozen at the
  // moment of refresh. These helpers poll /stream-status to pull the latest
  // snapshot and finalize the message when the backend marks it done/error.
  const _resumePollers = {}  // convId -> interval id

  function _stopResumePoll(convId) {
    if (_resumePollers[convId]) {
      clearInterval(_resumePollers[convId])
      delete _resumePollers[convId]
    }
  }

  async function _finalizeResumedStream(convId, reloadMessages = true) {
    _stopResumePoll(convId)
    const s = streams.value[convId]
    if (!s) return
    s.isStreaming = false
    s.streamingMessage = null
    s.connectionState = 'idle'
    s.streamPhase = 'idle'
    _clearSessionStream(convId)
    // Reload the authoritative transcript so the completed assistant message
    // (persisted by the backend) replaces the partial reconnected bubble.
    if (reloadMessages) {
      try {
        const res = await api.get(`/api/chat/conversations/${convId}`)
        s.messages = (res.data.messages || []).map(_hydrateMessageMetadata)
      } catch { /* keep partial content if the reload fails */ }
    }
    _syncFromStream(convId)
  }

  function _startResumePoll(convId) {
    _stopResumePoll(convId)
    const startedAt = Date.now()
    const MAX_RESUME_MS = 15 * 60 * 1000  // stop trying after 15 min
    let consecutiveFailures = 0  // BUG 14: track consecutive failures
    _resumePollers[convId] = setInterval(async () => {
      const s = streams.value[convId]
      if (!s || !s.isStreaming) { _stopResumePoll(convId); return }
      if (Date.now() - startedAt > MAX_RESUME_MS) {
        await _finalizeResumedStream(convId)
        return
      }
      try {
        const res = await api.get(`/api/chat/conversations/${convId}/stream-status`)
        consecutiveFailures = 0  // BUG 14: reset on success
        const status = res.data || {}
        if (status.status === 'streaming') {
          if (s.streamingMessage) {
            if (typeof status.content === 'string') s.streamingMessage.content = status.content
            if (typeof status.thinking === 'string') s.streamingMessage.thinking = status.thinking
          }
          // Advance the visual phase as fresh snapshots arrive: once content
          // appears we're composing/streaming; until then keep showing thinking.
          if (status.content) s.streamPhase = 'streaming'
          else if (status.thinking) s.streamPhase = 'thinking'
          s.connectionState = 'connected'
          _syncFromStream(convId)
        } else if (status.status === 'done') {
          await _finalizeResumedStream(convId)
        } else if (status.status === 'error') {
          if (s.streamingMessage && status.error) {
            s.streamingMessage.content = (s.streamingMessage.content || '') + `\n\n_${_safeErrorMessage(status.error)}_`
          }
          await _finalizeResumedStream(convId)
        } else if (status.status === 'not_found') {
          // Redis key expired (stream finished + TTL elapsed) or was cancelled.
          // The final message lives in the DB, so reload the transcript.
          await _finalizeResumedStream(convId)
        }
      } catch (err) {
        // BUG 14: Track consecutive failures and warn user after 10
        consecutiveFailures++
        if (consecutiveFailures === 10) {
          if (import.meta.env.DEV) console.warn(`[ResumePoll] ${convId}: 10 consecutive failures. Stream may be stuck. Consider refreshing or stopping manually.`, err)
          const s2 = streams.value[convId]
          if (s2) {
            s2.connectionState = 'disconnected'
            _syncFromStream(convId)
          }
        }
      }
    }, 2000)
  }

  async function openConversation(convId) {
    if (!convId) return null
    try {
      const res = await api.get(`/api/chat/conversations/${convId}`)
      currentConversationId.value = res.data.id
      // Persist last active conv ID to localStorage so openPaper restores it
      try { localStorage.setItem('chat_last_conv_id', convId) } catch { /* ignore */ }
      const s = _ensureStream(convId)
      // If a stream is already running for this conv, keep its in-memory
      // messages (which include the partial assistant bubble). Otherwise,
      // hydrate from the server-saved transcript.
      // BUG FIX: When isStreaming=true AND connectionState='reconnecting' (restored from sessionStorage),
      // still fetch messages from API and replace the streaming bubble instead of skipping.
      const _isReconnectingStream = s.isStreaming && s.connectionState === 'reconnecting'
      if (!s.isStreaming || _isReconnectingStream) {
        s.messages = (res.data.messages || []).map(_hydrateMessageMetadata)
        if (!s.isStreaming) s.streamingMessage = null
        
        // Check if there's a saved streaming state in sessionStorage
        try {
          const raw = sessionStorage.getItem(SESSION_KEY)
          if (raw) {
            const saved = JSON.parse(raw)
            const savedStream = saved[convId]
            const cutoff = Date.now() - 15 * 60 * 1000
            if (savedStream && savedStream.savedAt > cutoff && savedStream.isStreaming) {
              // Check backend stream status FIRST before restoring
              let serverDone = false
              try {
                const statusRes = await api.get(`/api/chat/conversations/${convId}/stream-status`)
                const status = statusRes.data
                if (status.status === 'done') {
                  // Stream already finished — server messages already have the completed one
                  // Don't restore streaming state, just clean up this conv's sessionStorage entry
                  serverDone = true
                  _clearSessionStream(convId)
                } else if (status.status === 'streaming') {
                  // Backend still active — restore and reconnect
                  s.isStreaming = true
                  s.connectionState = 'connected'
                  const _restoredContent = status.content || savedStream.streamingMessage?.content || ''
                  const _restoredThinking = status.thinking || savedStream.streamingMessage?.thinking || ''
                  s.streamingMessage = {
                    id: `streaming-${Date.now()}`,
                    role: 'assistant',
                    content: _restoredContent,
                    thinking: _restoredThinking,
                    tool_calls: savedStream.streamingMessage?.tool_calls || [],
                    created_at: savedStream.streamingMessage?.created_at || new Date().toISOString(),
                  }
                  // Restore the visual phase so the thinking/composing indicator
                  // shows immediately instead of defaulting to 'idle' (which would
                  // leave the bubble blank until the poller finalizes).
                  s.streamPhase = _restoredContent ? 'streaming' : (_restoredThinking ? 'thinking' : 'composing')
                  // Replace the LAST assistant message from server (if any) instead of appending
                  // This prevents duplicate reasoning blocks
                  // Manual reverse loop — findLastIndex is ES2023 and crashes older browsers
                  let lastAssistantIdx = -1
                  for (let _i = s.messages.length - 1; _i >= 0; _i--) {
                    if (s.messages[_i].role === 'assistant') { lastAssistantIdx = _i; break }
                  }
                  if (lastAssistantIdx >= 0) {
                    s.messages[lastAssistantIdx] = s.streamingMessage
                  } else {
                    s.messages = [...s.messages, s.streamingMessage]
                  }
                  // The live SSE socket died with the old page. Start a poller
                  // that pulls fresh snapshots from Redis and finalizes the
                  // message when the backend completes — otherwise the spinner
                  // stays stuck and content is frozen at the refresh point.
                  _startResumePoll(convId)
                } else if (status.status === 'error') {
                  s.isStreaming = false
                  s.connectionState = 'disconnected'
                  serverDone = true
                  _clearSessionStream(convId)
                }
              } catch {
                // Backend check failed — don't restore, mark idle
                s.connectionState = 'idle'
                serverDone = true
              }
            }
          }
        } catch { /* ignore */ }
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
      // 404 = conversation doesn't exist. Suppress for stale refs; only
      // surface unexpected errors.
      if (e?.response?.status !== 404) {
        error.value = e.message
      }
      return null
    }
  }

  async function createConversation(paperId, title = 'New Chat') {
    // paperId is optional — null = global conversation
    try {
      const url = paperId ? `/api/papers/${paperId}/conversations` : '/api/chat/conversations'
      const res = await api.post(url, { title })
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
      // 404 = paper doesn't exist. Suppress — editor handles stale-paper cleanup.
      if (e?.response?.status !== 404) {
        error.value = e.message
      }
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

  async function newGlobalChat() {
    const conv = await createConversation(null)
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
      _stopResumePoll(convId)
      delete streams.value[convId]
      if (currentConversationId.value === convId) {
        closeConversation()
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
      _stopResumePoll(convId)
      delete streams.value[convId]
      closeConversation()
      // create a fresh empty chat in the same paper
      if (paperId) {
        const conv = await createConversation(paperId)
        if (conv) await openConversation(conv.id)
      }
    } catch (e) {
      error.value = e.message
    }
  }

  async function sendMessage(content, images?: Array<{name: string, data: string}>) {
    // Prevent concurrent sends (race condition / double-click guard)
    if (_sendingLock) return
    const convId = currentConversationId.value
    if (!convId) return
    const stream = _ensureStream(convId)
    if (stream.isStreaming) return
    error.value = null

    try {
      _sendingLock = true

      // Block sending while another chat in this paper is generating a paper.
      // Show an inline assistant warning instead of a silent no-op so the user
      // understands why their message did not go through.
      if (activeJob.value && activeJob.value.active) {
        // Show warning as toast instead of pushing ghost user + assistant messages
        window.dispatchEvent(new CustomEvent('papergenerator-toast', {
          detail: {
            message: '⚠️ Chat lain di paper ini masih generate paper. Tunggu selesai dulu, atau lakukan hal lain (edit Section, Figures, dll) sambil menunggu.',
            type: 'warning',
          },
        }))
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
        id: _nextMsgId(),
        role: 'user',
        content,
        images: images && images.length ? images : undefined,
        created_at: new Date().toISOString(),
      })

      stream.isStreaming = true
      stream.connectionState = 'connecting'
      stream.streamPhase = 'sending'
      stream.streamingMessage = {
        id: null,
        role: 'assistant',
        content: '',
        thinking: '',
        tool_calls: [],
        created_at: new Date().toISOString(),
      }
      stream.messages.push(stream.streamingMessage)

      // memoryTouched removed — unused
      stream.abortCtrl = new AbortController()
      _syncFromStream(convId)

      // Backend handles AI retries: 3-model chain × 5 attempts × 30s each.
      // Keep the browser request alive long enough and avoid showing retry text.
      const MAX_RETRIES = 3
      const RETRY_DELAYS = [2000, 5000, 10000]
      const CONNECTION_TIMEOUT = 540000 // 9 minutes

      for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
              try {
                const csrf = (document.cookie.match(/(?:^|;\\s*)csrf_access_token=([^;]+)/) || [])[1] || ''
                const payload: any = { content }
                if (images && images.length) {
                  payload.images = images
                }

                // Realtime view context: route/location + in-memory paper draft.
                // currentPaperId here belongs to chat store; paperStore is the authoritative editor state.
                const paperStore = usePaperStore()
                const viewPaperId = paperStore.currentPaperId || currentPaperId.value || null
                payload.view_context = {
                  paperId: viewPaperId,
                  location: viewPaperId ? 'editor' : 'dashboard',
                  path: window.location?.pathname || '',
                  paper: viewPaperId ? paperStore.toPaperJson() : null,
                }

                // Create timeout that will abort the connection after CONNECTION_TIMEOUT
          const timeoutId = setTimeout(() => {
            if (stream.abortCtrl && !stream.abortCtrl.signal.aborted) {
              stream.abortCtrl.abort(new Error('Connection timeout'))
            }
          }, CONNECTION_TIMEOUT)

          try {
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

            clearTimeout(timeoutId)
            stream.connectionState = 'connected'
            _syncFromStream(convId)

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
                  stream.connectionState = 'idle'
                  checkActiveJob()
                  return
                }
              }
              throw new Error(`HTTP ${response.status}`)
            }

            if (!response.body) {
              throw new Error('Response body is null')
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
                  } catch (parseErr) { if (import.meta.env.DEV) console.warn('[SSE] Malformed chunk skipped:', line, parseErr) }
                }
              }
            }

            // Update conversation list ordering / counts
            // BUG 26: Use actual message count from done event or stream, not hardcoded +2
            const _actualCount = stream._finalMessageCount ?? stream.messages.length
            const cIdx = conversations.value.findIndex(c => c.id === convId)
            if (cIdx >= 0) {
              const cConv = conversations.value[cIdx]
              cConv.message_count = _actualCount
              cConv.updated_at = new Date().toISOString()
              // float to top
              conversations.value = [
                cConv,
                ...conversations.value.filter(c => c.id !== cConv.id),
              ]
            }
            const row = paperChats.value.find(c => c.paper_id === currentPaperId.value)
            if (row) {
              row.message_count = (row.message_count || 0) + 1  // BUG 26: +1 for user msg; assistant count updated by done event
              row.updated_at = new Date().toISOString()
              paperChats.value = [
                row,
                ...paperChats.value.filter(c => c.paper_id !== currentPaperId.value),
              ]
            }

            // Success - break retry loop
            break
          } finally {
            clearTimeout(timeoutId)
          }
        } catch (e) {
          const isLastAttempt = attempt === MAX_RETRIES - 1
          const isUserAbort = e instanceof Error && e.name === 'AbortError' && e.message !== 'Connection timeout'

          if (isUserAbort) {
            // User manually stopped - don't retry
            if (stream.streamingMessage) {
              stream.streamingMessage.content = (stream.streamingMessage.content || '') + '\n\n_(' + _uiStr('dihentikan oleh pengguna', 'stopped by user') + ')_'
            }
            stream.connectionState = 'idle'
            break
          }

          if (isLastAttempt) {
            // Final attempt failed - show error
            const friendly = _safeErrorMessage(e && e.message)
            error.value = friendly
            if (stream.streamingMessage) {
              // If assistant message is still empty (no content received), remove it from array
              // Otherwise append error message
              if (!stream.streamingMessage.content && !stream.streamingMessage.thinking) {
                const idx = stream.messages.findIndex(m => m === stream.streamingMessage)
                if (idx >= 0) {
                  stream.messages.splice(idx, 1)
                  // Also remove the preceding user message to avoid ghost user msg
                  if (idx > 0 && stream.messages[idx - 1]?.role === 'user') {
                    stream.messages.splice(idx - 1, 1)
                  }
                }
              } else {
                stream.streamingMessage.content = (stream.streamingMessage.content || '') + `\n\n_${friendly}_`
              }
            }
            stream.connectionState = 'disconnected'
            break
          } else {
            // Silent frontend retry fallback; normally unused because backend retries.
            stream.connectionState = 'retrying'
            _syncFromStream(convId)
            await new Promise(resolve => setTimeout(resolve, RETRY_DELAYS[attempt]))

            // Create new abort controller for next attempt
            stream.connectionState = 'connecting'
            stream.abortCtrl = new AbortController()
          }
        }
      }

    } finally {
      // Guaranteed cleanup: always release lock and abort controller.
      _sendingLock = false
      stream.abortCtrl = null
      // Only null streamingMessage if the stream did NOT finish normally
      // (i.e. error/abort path). When streamPhase is 'done', the message
      // was already finalized in stream.messages — nulling streamingMessage
      // here would cause a flash of missing content before re-render.
      if (stream.streamPhase !== 'done') {
        stream.isStreaming = false
        stream.streamingMessage = null
      } else {
        stream.isStreaming = false
        // Leave streamingMessage as the finalized reference so UI doesn't flash.
      }
      stream.streamPhase = 'idle'
      if (stream.connectionState !== 'disconnected') {
        stream.connectionState = 'idle'
      }
      // Clear saved streaming state from sessionStorage
      _clearSessionStream(convId)
      _syncFromStream(convId)
      // Clean userState.chat.streaming so cross-device restore doesn't show stale bubble
      try {
        const { useUserStateStore } = await import('./userState')
        useUserStateStore().deleteKey('chat.streaming')
      } catch { /* ignore */ }
      // Refresh quota after every chat message (token usage changes)
      try {
        const { useQuotaStore } = await import('./quota')
        useQuotaStore().fetchQuota()
      } catch { /* non-critical */ }
    }
  }

  async function stopStreaming() {
    const convId = currentConversationId.value
    const s = convId && streams.value[convId]
    if (!s) return

    // Stop any resume poller first so it can't revive state after cancel.
    if (convId) _stopResumePoll(convId)

    // If we have an active abort controller, use it (local abort)
    if (s.abortCtrl) {
      try { s.abortCtrl.abort() } catch { /* ignore */ }
      _syncFromStream(convId)
      return
    }
    
    // No abort controller but isStreaming is true (e.g., after refresh)
    // Call backend to cancel the stream
    if (s.isStreaming) {
      try {
        await api.post(`/api/chat/conversations/${convId}/cancel-stream`)
        // Update local state
        s.isStreaming = false
        s.connectionState = 'idle'
        if (s.streamingMessage) {
          s.streamingMessage.content = (s.streamingMessage.content || '') + '\n\n_(' + _uiStr('dihentikan oleh pengguna', 'stopped by user') + ')_\n\n'
        }
        _syncFromStream(convId)
      } catch {
        // Cancel failed - mark as idle anyway
        s.isStreaming = false
        s.connectionState = 'idle'
        _syncFromStream(convId)
      }
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
   * Push a synthetic assistant message carrying a multi_question card WITHOUT
   * hitting the AI. Used by the "Buat baru" entry path: the backend returns the
   * offline onboarding questions (static, with recommended answers) over REST,
   * and we render them directly. When the user submits, the answers flow back
   * through submitMultiQuestionAnswers → the AI continues the dynamic phases.
   */
  function injectMultiQuestion(proposal) {
    const convId = currentConversationId.value
    if (!convId || !proposal) return
    const stream = _ensureStream(convId)
    const intro = proposal.description
      ? String(proposal.description)
      : 'Lengkapi data dasar paper kamu (otomatis, tanpa AI).'
    const msg = {
      id: `synthetic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: 'assistant',
      content: intro,
      created_at: new Date().toISOString(),
      metadata: {
        kind: 'multi_question',
        synthetic: true,
        questions: Array.isArray(proposal.questions) ? proposal.questions : [],
        phase: proposal.phase,
        phase_name: proposal.phase_name,
        onboarding: !!proposal.onboarding,
      },
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

  async function _handleSSEEvent(convId, event, data) {
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
          ui.switchToTab(pid, tab)
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

    // 'paper_applied' — AI edited the paper data directly via [APPLY_PAPER] tags.
    // Reload the paper from DB so the editor reflects the changes.
    if (event === 'paper_applied') {
      try {
        const paperStore = usePaperStore()
        if (data?.errors && Array.isArray(data.errors) && data.errors.length > 0) {
          if (import.meta.env.DEV) console.error('[chat] paper_applied errors:', data.errors)
          window.dispatchEvent(new CustomEvent('papergenerator-toast', {
            detail: { message: 'Apply error: ' + data.errors.join('; '), type: 'error' },
          }))
        }
        if (data?.success !== false && paperStore.currentPaperId) {
          await paperStore.loadPaperFromDb(paperStore.currentPaperId)
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
        if (stream.streamPhase === 'composing' || stream.streamPhase === 'sending') {
          stream.streamPhase = 'streaming'
        }
        msg.content += data.content
        break
      case 'thinking':
        if (stream.streamPhase === 'sending' || stream.streamPhase === 'idle') {
          stream.streamPhase = 'thinking'
        }
        msg.thinking += data.content
        break
      case 'thinking_done':
        // Thinking phase ended, waiting for content
        if (stream.streamPhase === 'thinking') {
          stream.streamPhase = 'composing'
        }
        break
      case 'composing_start':
        stream.streamPhase = 'composing'
        break
      case 'search_phase_start':
        // Search phase started — show "Mencari referensi..." in UI
        stream.streamPhase = 'searching'
        stream.searchResults = []
        stream.searchMessage = data.message || 'Mencari referensi...'
        break
      case 'search_started':
        // Individual search query started
        if (!stream.searchResults) stream.searchResults = []
        stream.searchResults.push({
          type: data.type,
          query: data.query,
          icon: data.icon || '🔍',
          status: 'running',
          results: [],
        })
        break
      case 'search_complete':
        // Individual search completed — update results
        if (stream.searchResults) {
          const idx = stream.searchResults.findIndex(
            s => s.type === data.type && s.query === data.query && s.status === 'running'
          )
          if (idx >= 0) {
            stream.searchResults[idx].status = 'done'
            stream.searchResults[idx].results = data.results || []
            stream.searchResults[idx].count = data.count || 0
            stream.searchResults[idx].error = data.error || null
          }
        }
        break
      case 'search_phase_end':
        // All searches done — transition to composing
        stream.streamPhase = 'composing'
        break
      case 'replace_text':
        msg.content = data.content || ''
        break
      case 'ask_user':
        msg.metadata = {
          ...(msg.metadata || {}),
          kind: 'ask_user',
          question: data.question || '',
          options: Array.isArray(data.options) ? data.options : [],
        }
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
                ui.switchToTab(pid, 'literature')
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
            // Replace raw PROPOSAL JSON with user-friendly message so the chat
            // doesn't display the full payload. The structured data is already
            // in msg.metadata or handled by the paper store.
            if (tc) {
              tc.result = _getFriendlyProposalMessage(proposal)
            }
          } catch { /* malformed proposal — ignore */ }
        }
        break
      }
      case 'done':
        if (data.message_id) msg.id = data.message_id
        // BUG 26: Capture actual message count from done event if available
        if (data.message_count != null) stream._finalMessageCount = data.message_count
        // Capture DOCX file info if present
        if (data.file_url) {
          msg.metadata = {
            ...(msg.metadata || {}),
            file_url: data.file_url,
            file_name: data.file_name || '',
          }
        }
        stream.streamPhase = 'done'
        break
      case 'docx_ready':
        // DOCX file generated — stamp download info on streaming message
        msg.metadata = {
          ...(msg.metadata || {}),
          file_url: data.url || '',
          file_name: data.filename || '',
        }
        break
      case 'error':
        msg.content += `\n\n_${_safeErrorMessage(data && data.message)}_`
        break
    }
    _syncFromStream(convId)
  }

  function reset() {
    stopActiveJobPolling()
    for (const convId in _resumePollers) _stopResumePoll(convId)
    // Clear all persisted stream state from sessionStorage
    for (const convId of Object.keys(streams.value)) {
      _clearSessionStream(convId)
    }
    try { sessionStorage.removeItem(SESSION_KEY) } catch { /* ignore */ }
    // Clear userState streaming reference
    try {
      import('./userState').then(({ useUserStateStore }) => {
        useUserStateStore().deleteKey('chat.streaming')
      }).catch(() => {})
    } catch { /* ignore */ }
    activeJob.value = null
    currentPaperId.value = null
    currentConversationId.value = null
    conversations.value = []
    messages.value = []
    streamingMessage.value = null
    isStreaming.value = false
    connectionState.value = 'idle'
    streamPhase.value = 'idle'
    searchResults.value = []
    searchMessage.value = ''
    streams.value = {}
    error.value = null
    try { localStorage.removeItem('chat_last_conv_id') } catch { /* ignore */ }
  }

  // Restore any in-flight streams from sessionStorage on store init
  _restoreStreamsFromSession()

  /**
   * Close the current conversation: null currentConversationId AND reset all
   * message/stream state to prevent stale references.
   */
  function closeConversation() {
    currentConversationId.value = null
    messages.value = []
    isStreaming.value = false
    streamingMessage.value = null
    connectionState.value = 'idle'
    streamPhase.value = 'idle'
    searchResults.value = []
    searchMessage.value = ''
    try { localStorage.removeItem('chat_last_conv_id') } catch { /* ignore */ }
  }

  return {
    paperChats,
    currentPaperId,
    currentPaper,
    currentConversationId,
    currentChat,
    conversations,
    messages,
    isStreaming,
    streamingMessage,
    connectionState,
    streamPhase,
    searchResults,
    searchMessage,
    error,
    activeJob,
    loadPaperChats,
    loadConversations,
    loadAllConversations,
    openPaper,
    openConversation,
    closeConversation,
    createConversation,
    newChatForCurrentPaper,
    newGlobalChat,
    renameConversation,
    deleteConversation,
    clearCurrentChat,
    sendMessage,
    submitMultiQuestionAnswers,
    stopStreaming,
    injectAssistantMessage,
    injectMultiQuestion,
    checkActiveJob,
    // Internal functions for streaming restore
    _ensureStream,
    _syncFromStream,
    startActiveJobPolling,
    stopActiveJobPolling,
    reset,

  }
})
