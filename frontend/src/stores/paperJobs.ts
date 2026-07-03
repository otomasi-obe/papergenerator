// @ts-nocheck
/**
 * Paper-generation job tracking (frontend side).
 *
 * Backend owns the worker; this store just polls and dispatches user actions
 * (cancel / resume / retry-section). Two pollers run independently:
 *   - `activePollInterval` (3s) tracks the in-flight job for the currently
 *     open paper, used to drive the inline progress bubble inside chat.
 *   - `globalPollInterval` (10s) refreshes the recent-done list used by the
 *     header bell badge + dropdown, plus fires browser notifications for
 *     newly-finished jobs the user hasn't seen yet.
 *
 * Stream state (reasoning/content text, progress) IS persisted to localStorage
 * so users can see their in-progress generation after page refresh.
 * The source of truth for job status lives on the backend.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/index.js'
import { usePaperStore } from './paper.js'

export const usePaperJobsStore = defineStore('paperJobs', () => {
  // paperId → active job object
  const activeByPaper = ref({})
  // All active jobs across all papers (for bell icon)
  const globalActiveJobs = ref([])
  // Failed/error jobs (shown in bell until clicked)
  const failedJobs = ref([])
  // Most recent done jobs across all the user's papers
  const recentDone = ref([])
  // Job ids the user has already been notified about (or pre-seeded on first load)
  const seenDoneIds = ref(new Set())
  // Job ids that have been clicked/viewed by the user (to hide from bell dropdown)
  // Array + reactive counter — Vue doesn't track Set.add() in computed deps,
  // so we bump _clickedTick on every add to force re-evaluation.
  // Persisted to localStorage so clicked jobs stay hidden across page refresh.
  const LS_CLICKED = 'pg_bell_clicked_ids'
  let _savedClicked: string[] = []
  try {
    const raw = localStorage.getItem(LS_CLICKED)
    if (raw) _savedClicked = JSON.parse(raw)
  } catch { /* ignore */ }
  const _clickedIds = new Set(_savedClicked)
  const _clickedTick = ref(0)

  function _persistClicked() {
    try {
      // Only keep the last 100 ids to avoid unbounded growth
      const arr = [..._clickedIds].slice(-100)
      localStorage.setItem(LS_CLICKED, JSON.stringify(arr))
    } catch { /* quota exceeded or private mode */ }
  }
  // Job ids that have already triggered the post-done chat injection. We
  // track this separately from seenDoneIds because notifications and the
  // chat hook have different lifecycles (e.g. seenDoneIds is seeded on the
  // first load to suppress back-fill notifs, but we still want the hook to
  // fire exactly once per job).
  const _processedJobIds = new Set()

  // Stuck job detection: track when we first saw each active job at 0% progress
  // Map<jobId, { firstSeenAt: number, lastProgress: number }>
  const _stuckTracker = new Map()
  const STUCK_TIMEOUT_MS = 5 * 60 * 1000 // 5 minutes at 0% = stuck

  let activePollInterval = null
  let globalPollInterval = null
  let currentPaperId = null

  async function fetchActive(paperId) {
    if (!paperId) return
    try {
      const r = await api.get(`/api/papers/${paperId}/ai-jobs/active`)
      const job = r.data?.job  // nested under 'job' key
      if (job && job.id) {
        activeByPaper.value = { ...activeByPaper.value, [paperId]: job }
      } else {
        const next = { ...activeByPaper.value }
        delete next[paperId]
        activeByPaper.value = next
      }
    } catch (e) {
      // 404 = no active job for this paper. Anything else is just a warning.
      if (e?.response?.status !== 404) {
        if (import.meta.env.DEV) console.warn('paperJobs.fetchActive failed', e)
      } else {
        const next = { ...activeByPaper.value }
        delete next[paperId]
        activeByPaper.value = next
      }
    }
  }

  function startPolling(paperId) {
    stopPolling()
    if (!paperId) return
    currentPaperId = paperId
    fetchActive(paperId)
    activePollInterval = setInterval(() => fetchActive(paperId), 3000)
  }

  function stopPolling() {
    if (activePollInterval) clearInterval(activePollInterval)
    activePollInterval = null
    currentPaperId = null
  }

  async function cancel(jobId) {
    if (!jobId) return false
    try {
      await api.post(`/api/ai-jobs/${jobId}/cancel`)
      if (currentPaperId) await fetchActive(currentPaperId)
      return true
    } catch (e) {
      if (import.meta.env.DEV) console.warn('paperJobs.cancel failed', e)
      return false
    }
  }

  async function resume(jobId) {
    if (!jobId) return false
    try {
      await api.post(`/api/ai-jobs/${jobId}/resume`)
      if (currentPaperId) await fetchActive(currentPaperId)
      return true
    } catch (e) {
      if (import.meta.env.DEV) console.warn('paperJobs.resume failed', e)
      return false
    }
  }

  async function retrySection(jobId, stage) {
    if (!jobId) return false
    try {
      await api.post(`/api/ai-jobs/${jobId}/retry-section`, { stage })
      if (currentPaperId) await fetchActive(currentPaperId)
      return true
    } catch (e) {
      if (import.meta.env.DEV) console.warn('paperJobs.retrySection failed', e)
      return false
    }
  }

  function _notify(job) {
    if (typeof Notification === 'undefined') return
    if (Notification.permission !== 'granted') return
    const title = job?.result?.partial_paper?.title || 'Your paper is ready'
    try {
      new Notification('Paper generated', {
        body: title,
        icon: '/favicon.ico',
        tag: `paper-job-${job.id}`,
      })
    } catch { /* some browsers throw if called too early */ }
  }

  // Dismiss a failed job from the bell notification (client-side only)
  function dismissFailedJob(jobId) {
    failedJobs.value = failedJobs.value.filter(j => j.id !== jobId)
  }

  // Clear all failed jobs from the bell notification (client-side only)
  function clearAllFailedJobs() {
    failedJobs.value = []
  }

  // Walk the paper JSON for figure-blocks (`id === 'gambar'`) and collect
  // their {title, prompt, section, content_index}. Used by the post-done
  // hook to surface a one-shot image-prompt review chat bubble.
  function _collectImagePrompts(paper) {
    const imgs = []
    const sections = paper?.data?.sections || paper?.sections || []
    sections.forEach((s, sIdx) => {
      const items = s.content || []
      items.forEach((c, cIdx) => {
        if (c && c.id === 'gambar' && (c.Prompt || c.prompt)) {
          imgs.push({
            section_index: sIdx,
            content_index: cIdx,
            title: c.Title || c.title || '',
            prompt: c.Prompt || c.prompt || '',
          })
        }
      })
    })
    return imgs
  }

  // Post-done hook for full-paper jobs: nudges the user to review the
  // figure prompts the writer produced before triggering bulk image gen.
  // Silent no-op if there is no chat open or the kind doesn't match.
  // Guarded against re-firing for the same job id across the polling lifetime.
  async function _onJobDone(job) {
    if (!job?.id) return
    if (_processedJobIds.has(job.id)) return
    _processedJobIds.add(job.id)
    const kind = job.kind || job.tool || job.action || ''
    const isFullPaper =
      kind === 'generate_full_paper' ||
      kind === 'generate_paper' ||
      kind === 'generate_full'
    if (!isFullPaper) return
    try {
      const paperStore = usePaperStore()
      // Lazy-import the chat store to avoid the chat.js ↔ paper.js circular
      // dep loop (paper.js already lazy-imports chat.js).
      const { useChatStore } = await import('./chat.js')
      const chatStore = useChatStore()
      const paper = paperStore.paper
      if (!paper) return
      // job.paper_id is always set; bail if the user is on a different paper
      if (job.paper_id && paper.id && job.paper_id !== paper.id) return
      const images = _collectImagePrompts(paper)
      if (!images.length) return
      const lines = images.map((im, i) => {
        const t = im.title || 'Untitled'
        return `**Fig. ${i + 1}** — ${t}\n  prompt: ${im.prompt}`
      })
      const body =
        'Paper sudah selesai. Saya menemukan ' + images.length +
        ' prompt gambar:\n\n' + lines.join('\n\n') +
        '\n\nMau saya generate semua sekarang, edit prompt dulu, atau skip?'
      chatStore.injectAssistantMessage(body)
    } catch (e) {
      if (import.meta.env.DEV) console.warn('paperJobs._onJobDone hook failed', e)
    }
  }
  async function fetchRecentDone() {
    try {
      const r = await api.get('/api/me/ai-jobs/recent', {
        params: { limit: 20 },
      })
      const list = Array.isArray(r?.data) ? r.data : (r?.data?.jobs || [])

      // Split into active, done, and failed jobs
      const active = list.filter(j => j.status === 'running' || j.status === 'pending' || j.status === 'queued')
      const done = list.filter(j => j.status === 'done')
      const failed = list.filter(j => j.status === 'error' || j.status === 'cancelled')
      globalActiveJobs.value = active
      // Only add new failures that aren't already clicked/dismissed
      failedJobs.value = failed.filter(j => !_clickedIds.has(j.id))

      // Check for stuck jobs (0% progress for too long)
      _checkStuckJobs()

      const firstLoad = seenDoneIds.value.size === 0
      const newOnes = done.filter(j => !seenDoneIds.value.has(j.id))
      if (firstLoad) {
        // Don't fire notifs for the back-fill on first load — user already
        // knows about them. Just seed the seen-set.
        done.forEach(j => seenDoneIds.value.add(j.id))
      } else {
        newOnes.forEach(j => {
          seenDoneIds.value.add(j.id)
          _notify(j)
          _onJobDone(j)
        })
      }
      recentDone.value = done.filter(j => j.paper_id)
    } catch (e) {
      if (import.meta.env.DEV) console.warn('paperJobs.fetchRecentDone failed', e)
    }
  }

  function startGlobalPolling() {
    if (globalPollInterval) return
    fetchRecentDone()
    globalPollInterval = setInterval(fetchRecentDone, 10000)
  }

  function stopGlobalPolling() {
    if (globalPollInterval) clearInterval(globalPollInterval)
    globalPollInterval = null
  }

  async function requestNotifPermission() {
    if (typeof Notification === 'undefined') return false
    if (Notification.permission === 'granted') return true
    if (Notification.permission === 'denied') return false
    try {
      const result = await Notification.requestPermission()
      return result === 'granted'
    } catch {
      return false
    }
  }

  function markJobAsClicked(jobId) {
    if (jobId && !_clickedIds.has(jobId)) {
      _clickedIds.add(jobId)
      _clickedTick.value++ // force reactive re-evaluation
      _persistClicked()
    }
  }

  // Check if any active jobs are stuck at 0% progress for too long.
  // If so, mark them as failed and notify the user.
  async function _checkStuckJobs() {
    const now = Date.now()
    const stuckJobIds = []

    // Check global active jobs
    for (const job of globalActiveJobs.value) {
      const progress = job.progress || 0
      const existing = _stuckTracker.get(job.id)

      if (progress > 0) {
        // Job is making progress, remove from tracker
        _stuckTracker.delete(job.id)
        continue
      }

      if (!existing) {
        // First time seeing this job at 0%, start tracking
        _stuckTracker.set(job.id, { firstSeenAt: now, lastProgress: 0 })
      } else {
        // Check if it's been stuck too long
        const elapsed = now - existing.firstSeenAt
        if (elapsed >= STUCK_TIMEOUT_MS) {
          stuckJobIds.push(job.id)
        }
      }
    }

    // Mark stuck jobs as failed (parallel cancel to avoid sequential stalls)
    const cancelPromises = stuckJobIds.map(async (jobId) => {
      try {
        await api.post(`/api/ai-jobs/${jobId}/cancel`)
        // Add to failed jobs list (will be shown in bell)
        const stuckJob = globalActiveJobs.value.find(j => j.id === jobId)
        if (stuckJob) {
          const failedJob = {
            ...stuckJob,
            status: 'error',
            error: 'Job stuck at 0% — auto-cancelled after 5 minutes',
          }
          if (!_clickedIds.has(jobId)) {
            failedJobs.value = [failedJob, ...failedJobs.value]
          }
          globalActiveJobs.value = globalActiveJobs.value.filter(j => j.id !== jobId)
        }
        _stuckTracker.delete(jobId)
      } catch (e) {
        if (import.meta.env.DEV) console.warn('Failed to cancel stuck job', jobId, e)
      }
    })
    await Promise.allSettled(cancelPromises)
  }

  // ── Paperfull SSE streaming state ──────────────────────────────────────
  // Lives in store so it survives component unmount (user navigates away).
  // Persisted to localStorage so it also survives page refresh.
  const LS_STREAM = 'pg_stream_state'

  let _savedStream = null
  try {
    const raw = localStorage.getItem(LS_STREAM)
    if (raw) _savedStream = JSON.parse(raw)
  } catch { /* ignore */ }

  const streamState = ref(_savedStream)

  function _persistStream() {
    try {
      if (streamState.value) {
        localStorage.setItem(LS_STREAM, JSON.stringify(streamState.value))
      } else {
        localStorage.removeItem(LS_STREAM)
      }
    } catch { /* quota exceeded or private mode */ }
  }

  function setStreamState(data) {
    streamState.value = data ? { ...data, _updatedAt: Date.now() } : null
    _persistStream()
  }

  function updateStreamProgress(pct) {
    if (streamState.value) {
      streamState.value = { ...streamState.value, displayProgress: pct, _updatedAt: Date.now() }
      _persistStream()
    }
  }

  // Mark stream as connection-lost (SSE dropped, backend may still be running)
  function setConnectionLost(lost) {
    if (streamState.value) {
      streamState.value = { ...streamState.value, connectionLost: !!lost, _updatedAt: Date.now() }
      _persistStream()
    }
  }

  function clearStreamState() {
    streamState.value = null
    _persistStream()
  }

  // Check if the persisted stream state is stale (>5 min without update).
  // Call this on app mount to clear zombie streams from a previous session.
  function clearStaleStreamState() {
    if (streamState.value?._updatedAt) {
      const age = Date.now() - streamState.value._updatedAt
      if (age > 5 * 60 * 1000) {
        clearStreamState()
        return true
      }
    } else if (streamState.value) {
      // No timestamp — assume stale
      clearStreamState()
      return true
    }
    return false
  }

  return {
    activeByPaper,
    globalActiveJobs,
    failedJobs,
    recentDone,
    clickedJobIds: computed(() => { void _clickedTick.value; return _clickedIds }),
    _clickedTick,
    streamState,
    setStreamState,
    updateStreamProgress,
    setConnectionLost,
    clearStreamState,
    clearStaleStreamState,
    fetchActive,
    startPolling,
    stopPolling,
    cancel,
    resume,
    retrySection,
    dismissFailedJob,
    clearAllFailedJobs,
    fetchRecentDone,
    startGlobalPolling,
    stopGlobalPolling,
    requestNotifPermission,
    markJobAsClicked,
  }
})
