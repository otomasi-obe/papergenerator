import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import api from '../api/index.js'

/**
 * Image generation queue (frontend side).
 *
 * Backend has the real worker pool (4 workers, 1 per Gemini account, sequential
 * per worker). This store just submits jobs and polls for completion. Subscribers
 * get notified via callbacks even if the user navigates between papers — we keep
 * an in-memory map of jobId → { paperId, contentItemKey, callbacks }.
 *
 * The job state itself (queued / running / done / error) is persisted on the
 * backend, so a page refresh recovers gracefully via the resume() helper.
 */
const LS_KEY = 'pg_image_gen_jobs'

export const useImageGenStore = defineStore('imageGen', () => {
  // jobId → { paperId, prompt, status, image, error, itemKey }
  const jobs = reactive({})
  // active poll timer id (single shared poller for all in-flight jobs)
  let pollTimer = null
  // jobId → array of {onDone, onError}
  const subscribers = reactive({})

  function _persist() {
    try {
      const slim = {}
      for (const [id, j] of Object.entries(jobs)) {
        slim[id] = {
          paperId: j.paperId,
          prompt: j.prompt,
          status: j.status,
          image: j.image,
          error: j.error,
          itemKey: j.itemKey,
        }
      }
      localStorage.setItem(LS_KEY, JSON.stringify(slim))
    } catch { /* quota */ }
  }

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (!raw) return
      const data = JSON.parse(raw)
      for (const [id, j] of Object.entries(data || {})) {
        if (!jobs[id]) jobs[id] = { ...j }
      }
    } catch { /* ignore */ }
  }

  function _ensurePoller() {
    if (pollTimer) return
    pollTimer = setInterval(_poll, 3000)
  }

  function _stopPollerIfIdle() {
    const inflight = Object.values(jobs).some(j => j.status === 'queued' || j.status === 'running')
    if (!inflight && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function _poll() {
    const inflightIds = Object.entries(jobs)
      .filter(([, j]) => j.status === 'queued' || j.status === 'running')
      .map(([id]) => id)
    if (!inflightIds.length) {
      _stopPollerIfIdle()
      return
    }
    for (const id of inflightIds) {
      try {
        const res = await api.get(`/api/image-jobs/${id}`)
        const data = res.data || {}
        const cur = jobs[id]
        if (!cur) continue
        cur.status = data.status || cur.status
        if (data.status === 'done') {
          cur.image = data.image
          _notify(id, 'done', data.image)
        } else if (data.status === 'error') {
          cur.error = data.error || 'unknown'
          _notify(id, 'error', cur.error)
        }
      } catch (e) {
        // 404 → job hilang dari server, anggap error
        if (e?.response?.status === 404) {
          jobs[id].status = 'error'
          jobs[id].error = 'Job tidak ditemukan'
          _notify(id, 'error', jobs[id].error)
        }
      }
    }
    _persist()
    _stopPollerIfIdle()
  }

  function _notify(id, kind, payload) {
    const subs = subscribers[id] || []
    for (const cb of subs) {
      try {
        if (kind === 'done' && cb.onDone) cb.onDone(payload)
        if (kind === 'error' && cb.onError) cb.onError(payload)
      } catch { /* swallow */ }
    }
    delete subscribers[id]
  }

  /**
   * Enqueue a new generate-image job.
   *
   * If `itemKey` is supplied and there's already an in-flight job with the same
   * paperId+itemKey, we just attach the callbacks to that job — preventing
   * accidental double-clicks from spamming Gemini accounts.
   */
  async function enqueue({ paperId, prompt, onDone, onError, itemKey }) {
    if (!paperId || !prompt) {
      onError && onError('paperId/prompt kosong')
      return null
    }
    if (itemKey) {
      const existing = Object.entries(jobs).find(
        ([, j]) => j.paperId === paperId && j.itemKey === itemKey &&
                   (j.status === 'queued' || j.status === 'running')
      )
      if (existing) {
        const [eid] = existing
        if (!subscribers[eid]) subscribers[eid] = []
        subscribers[eid].push({ onDone, onError })
        return eid
      }
    }
    try {
      const res = await api.post('/api/image-jobs', { paper_id: paperId, prompt })
      const id = res.data?.id
      if (!id) throw new Error(res.data?.error || 'Backend tidak mengembalikan job id')
      jobs[id] = {
        paperId,
        prompt,
        status: res.data.status || 'queued',
        image: null,
        error: null,
        itemKey: itemKey || null,
      }
      if (!subscribers[id]) subscribers[id] = []
      subscribers[id].push({ onDone, onError })
      _persist()
      _ensurePoller()
      return id
    } catch (e) {
      const msg = e.response?.data?.error || e.message || 'enqueue gagal'
      onError && onError(msg)
      return null
    }
  }

  /**
   * Subscribe to an existing job (used after page reload to re-attach UI to a
   * job that's still running on the backend).
   */
  function subscribe(jobId, { onDone, onError }) {
    if (!jobId) return
    if (!subscribers[jobId]) subscribers[jobId] = []
    subscribers[jobId].push({ onDone, onError })
    _ensurePoller()
  }

  function getJob(jobId) {
    return jobs[jobId] || null
  }

  /** Find in-flight job for a given paper+itemKey, if any. */
  function findActive(paperId, itemKey) {
    return Object.entries(jobs).find(
      ([, j]) => j.paperId === paperId && j.itemKey === itemKey &&
                 (j.status === 'queued' || j.status === 'running')
    )?.[0] || null
  }

  /**
   * On app startup, ask backend for all in-flight image jobs belonging to the
   * current user, hydrate local store, and start polling. This survives across
   * paper switches and full page reloads.
   */
  async function resume() {
    _load()
    try {
      const res = await api.get('/api/image-jobs')
      const list = res.data?.jobs || []
      for (const j of list) {
        jobs[j.id] = {
          paperId: j.paper_id,
          prompt: j.prompt,
          status: j.status,
          image: j.image || null,
          error: j.error || null,
          itemKey: jobs[j.id]?.itemKey || null,
        }
      }
      _persist()
      if (list.some(j => j.status === 'queued' || j.status === 'running')) {
        _ensurePoller()
      }
    } catch { /* non-critical */ }
  }

  return {
    jobs,
    enqueue,
    subscribe,
    getJob,
    findActive,
    resume,
  }
})
