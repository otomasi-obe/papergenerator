/**
 * Axios API client.
 * Auth: httpOnly cookies (set by backend) + double-submit CSRF header.
 * No JWT in localStorage. Cookies travel automatically with `withCredentials`.
 */
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 0,           // long AI ops can run for minutes
  withCredentials: true, // include httpOnly auth cookies
})

function readCookie(name) {
  const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[1]) : null
}

// Attach the CSRF double-submit token for state-changing requests.
api.interceptors.request.use((config) => {
  const method = (config.method || 'get').toLowerCase()
  if (['post', 'put', 'patch', 'delete'].includes(method)) {
    // Refresh endpoint uses the refresh-cookie CSRF token.
    const isRefresh = (config.url || '').includes('/api/auth/refresh')
    const csrf = readCookie(isRefresh ? 'csrf_refresh_token' : 'csrf_access_token')
    if (csrf) config.headers['X-CSRF-TOKEN'] = csrf
  }
  return config
})

// Single-flight refresh: if multiple requests 401 at once, only one /refresh fires.
let refreshPromise = null

async function tryRefresh() {
  if (!refreshPromise) {
    refreshPromise = api.post('/api/auth/refresh')
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config || {}
    const status = error.response?.status

    // Don't retry the refresh call itself, and don't retry if we already retried.
    const isAuthEndpoint = (original.url || '').includes('/api/auth/')
    if (status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true
      try {
        await tryRefresh()
        return api(original)
      } catch {
        // fall through to logout redirect
      }
    }

    if (status === 401) {
      // Cookies already gone or refresh failed — clear local user, send to login.
      try { localStorage.removeItem('user') } catch {}
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
