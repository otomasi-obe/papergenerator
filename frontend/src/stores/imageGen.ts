// @ts-nocheck
import { defineStore } from 'pinia'
import { reactive } from 'vue'
import api from '../api/index'

const LS_KEY = 'pg_image_gen_jobs'

interface ImageGenJob {
  paperId: string
  prompt: string
  status: 'queued' | 'running' | 'done' | 'error'
  image: string | null
  error: string | null
  itemKey: string | null
}

interface JobSubscriber {
  onDone?: (image: string) => void
  onError?: (error: string) => void
}

interface EnqueueParams {
  paperId: string
  prompt: string
  onDone?: (image: string) => void
  onError?: (error: string) => void
  itemKey?: string
}

export const useImageGenStore = defineStore('imageGen', () => {
  const jobs = reactive<Record<string, ImageGenJob>>({})
  let pollTimer: number | null = null
  const subscribers = reactive<Record<string, JobSubscriber[]>>({})

  function _persist(): void {
    try {
      const slim: Record<string, Omit<ImageGenJob, never>> = {}
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

  function _load(): void {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (!raw) return
      const data = JSON.parse(raw) as Record<string, ImageGenJob>
      for (const [id, j] of Object.entries(data || {})) {
        if (!jobs[id]) jobs[id] = { ...j }
      }
    } catch { /* ignore */ }
  }

  function _ensurePoller(): void {
    if (pollTimer) return
    pollTimer = window.setInterval(_poll, 3000)
  }

  function _stopPollerIfIdle(): void {
    const inflight = Object.values(jobs).some(j => j.status === 'queued' || j.status === 'running')
    if (!inflight && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function _poll(): Promise<void> {
    const inflightIds = Object.entries(jobs)
      .filter(([, j]) => j.status === 'queued' || j.status === 'running')
      .map(([id]) => id)
    if (!inflightIds.length) {
      _stopPollerIfIdle()
      return
    }
    for (const id of inflightIds) {
      try {
        const res = await api.get<{ status: string; image?: string; error?: string }>(`/api/image-jobs/${id}`)
        const data = res.data || {}
        const cur = jobs[id]
        if (!cur) continue
        cur.status = (data.status as ImageGenJob['status']) || cur.status
        if (data.status === 'done') {
          cur.image = data.image || null
          _notify(id, 'done', data.image || '')
        } else if (data.status === 'error') {
          cur.error = data.error || 'unknown'
          _notify(id, 'error', cur.error)
        }
      } catch (e: unknown) {
        const error = e as { response?: { status?: number } }
        if (error?.response?.status === 404) {
          jobs[id].status = 'error'
          jobs[id].error = 'Job tidak ditemukan'
          _notify(id, 'error', jobs[id].error || 'unknown')
        }
      }
    }
    _persist()
    _stopPollerIfIdle()
  }

  function _notify(id: string, kind: 'done' | 'error', payload: string): void {
    const subs = subscribers[id] || []
    for (const cb of subs) {
      try {
        if (kind === 'done' && cb.onDone) cb.onDone(payload)
        if (kind === 'error' && cb.onError) cb.onError(payload)
      } catch { /* swallow */ }
    }
    delete subscribers[id]
  }

  async function enqueue({ paperId, prompt, onDone, onError, itemKey }: EnqueueParams): Promise<string | null> {
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
      const res = await api.post<{ id?: string; status?: string; error?: string }>('/api/image-jobs', { paper_id: paperId, prompt })
      const id = res.data?.id
      if (!id) throw new Error(res.data?.error || 'Backend tidak mengembalikan job id')
      jobs[id] = {
        paperId,
        prompt,
        status: (res.data.status as ImageGenJob['status']) || 'queued',
        image: null,
        error: null,
        itemKey: itemKey || null,
      }
      if (!subscribers[id]) subscribers[id] = []
      subscribers[id].push({ onDone, onError })
      _persist()
      _ensurePoller()
      return id
    } catch (e: unknown) {
      const error = e as { response?: { data?: { error?: string } }; message?: string }
      const msg = error.response?.data?.error || error.message || 'enqueue gagal'
      onError && onError(msg)
      return null
    }
  }

  function subscribe(jobId: string, { onDone, onError }: JobSubscriber): void {
    if (!jobId) return
    if (!subscribers[jobId]) subscribers[jobId] = []
    subscribers[jobId].push({ onDone, onError })
    _ensurePoller()
  }

  function getJob(jobId: string): ImageGenJob | null {
    return jobs[jobId] || null
  }

  function findActive(paperId: string, itemKey: string): string | null {
    return Object.entries(jobs).find(
      ([, j]) => j.paperId === paperId && j.itemKey === itemKey &&
                 (j.status === 'queued' || j.status === 'running')
    )?.[0] || null
  }

  async function resume(): Promise<void> {
    _load()
    try {
      const res = await api.get<{ jobs?: Array<{ id: string; paper_id: string; prompt: string; status: string; image?: string; error?: string }> }>('/api/image-jobs')
      const list = res.data?.jobs || []
      for (const j of list) {
        jobs[j.id] = {
          paperId: j.paper_id,
          prompt: j.prompt,
          status: j.status as ImageGenJob['status'],
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
