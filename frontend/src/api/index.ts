import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 900000,  // 15 minutes — supports large file uploads
  withCredentials: true,
})

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[1]) : null
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const method = (config.method || 'get').toLowerCase()
  if (['post', 'put', 'patch', 'delete'].includes(method)) {
    const isRefresh = (config.url || '').includes('/api/auth/refresh')
    const csrf = readCookie(isRefresh ? 'csrf_refresh_token' : 'csrf_access_token')
    if (csrf) config.headers['X-CSRF-TOKEN'] = csrf
  }
  return config
})

let refreshPromise: Promise<unknown> | null = null

async function tryRefresh(): Promise<unknown> {
  if (!refreshPromise) {
    refreshPromise = api.post('/api/auth/refresh')
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
    const status = error.response?.status

    const isAuthEndpoint = (original?.url || '').includes('/api/auth/')
    if (status === 401 && !original?._retry && !isAuthEndpoint) {
      original._retry = true
      try {
        await tryRefresh()
        return api(original)
      } catch {
        // fall through to logout redirect
      }
    }

    if (status === 401) {
      try { localStorage.removeItem('pg_user') } catch {}
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
