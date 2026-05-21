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

export const usePaperJobsStore = defineStore('paperJobs', () => {
  // paperId → active job object
  const activeByPaper = ref({})
  // Most recent done jobs across all the user's papers
  const recentDone = ref([])
  // Job ids the user has already been notified about (or pre-seeded on first load)
  const seenDoneIds = ref(new Set())

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
