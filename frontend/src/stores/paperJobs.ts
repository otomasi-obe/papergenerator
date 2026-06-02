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
 * State is intentionally NOT persisted to localStorage; the source of truth
 * lives on the backend, and a refresh re-fetches everything.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api/index.js'
import { usePaperStore } from './paper.js'

export const usePaperJobsStore = defineStore('paperJobs', () => {
  // paperId → active job object
  const activeByPaper = ref({})
  // Most recent done jobs across all the user's papers
  const recentDone = ref([])
  // Job ids the user has already been notified about (or pre-seeded on first load)
  const seenDoneIds = ref(new Set())
  // Job ids that have already triggered the post-done chat injection. We
  // track this separately from seenDoneIds because notifications and the
  // chat hook have different lifecycles (e.g. seenDoneIds is seeded on the
  // first load to suppress back-fill notifs, but we still want the hook to
  // fire exactly once per job).
  const _processedJobIds = new Set()

  let activePollInterval = null
  let globalPollInterval = null
  let currentPaperId = null

  async function fetchActive(paperId) {
    if (!paperId) return
    try {
      const r = await api.get(`/api/papers/${paperId}/ai-jobs/active`)
      const job = r?.data
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
        console.warn('paperJobs.fetchActive failed', e)
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
      console.warn('paperJobs.cancel failed', e)
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
      console.warn('paperJobs.resume failed', e)
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
      console.warn('paperJobs.retrySection failed', e)
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
      console.warn('paperJobs._onJobDone hook failed', e)
    }
  }

  async function fetchRecentDone() {
    try {
      const r = await api.get('/api/me/ai-jobs/recent', {
        params: { status: 'done', limit: 10 },
      })
      const list = Array.isArray(r?.data) ? r.data : (r?.data?.jobs || [])
      const firstLoad = seenDoneIds.value.size === 0
      const newOnes = list.filter(j => !seenDoneIds.value.has(j.id))
      if (firstLoad) {
        // Don't fire notifs for the back-fill on first load — user already
        // knows about them. Just seed the seen-set.
        list.forEach(j => seenDoneIds.value.add(j.id))
      } else {
        newOnes.forEach(j => {
          seenDoneIds.value.add(j.id)
          _notify(j)
          _onJobDone(j)
        })
      }
      recentDone.value = list
    } catch (e) {
      console.warn('paperJobs.fetchRecentDone failed', e)
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

  return {
    activeByPaper,
    recentDone,
    fetchActive,
    startPolling,
    stopPolling,
    cancel,
    resume,
    retrySection,
    fetchRecentDone,
    startGlobalPolling,
    stopGlobalPolling,
    requestNotifPermission,
  }
})
