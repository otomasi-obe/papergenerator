import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/index'

interface User {
  id: string
  email: string
  name: string
  nickname?: string
  institution?: string
  preferred_language?: string
  role: 'user' | 'admin'
  [key: string]: unknown
}

export const useAuthStore = defineStore('auth', () => {
  let _user: User | null = null
  try {
    const stored = localStorage.getItem('pg_user')
    if (stored) _user = JSON.parse(stored)
  } catch { _user = null }
  const user = ref<User | null>(_user)
  const _loaded = ref(false)
  let _inflight: Promise<User | null> | null = null

  const isLoggedIn = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  function setUser(userData: User | null): void {
    user.value = userData
    try {
      if (userData) {
        localStorage.setItem('pg_user', JSON.stringify(userData))
      } else {
        localStorage.removeItem('pg_user')
      }
    } catch {
      // localStorage can throw (quota, private browsing, security restrictions)
      // State is still updated in memory, so app works fine
    }
  }

  async function fetchMe(): Promise<User | null> {
    // Dedupe concurrent calls: the store fires fetchMe() on init AND the router
    // guard calls it on first navigation. Without this, two /api/auth/me race
    // on every cold load. Share the in-flight promise instead.
    if (_inflight) return _inflight
    _inflight = (async () => {
      try {
        const res = await api.get<User>('/api/auth/me')
        setUser(res.data)
        return res.data
      } catch {
        setUser(null)
        return null
      } finally {
        _loaded.value = true
        _inflight = null
      }
    })()
    return _inflight
  }

  function loginWithGoogle(): void {
    const backendUrl = import.meta.env.VITE_API_URL || ''
    const redirectTo = `${window.location.origin}/auth/callback`
    window.location.href = `${backendUrl}/api/auth/google/login?redirect_to=${encodeURIComponent(redirectTo)}`
  }

  async function logout(): Promise<void> {
    try {
      await api.post('/api/auth/logout')
    } catch {
      // Even if the call fails (cookie expired etc.), clear local state.
    }
    setUser(null)
    window.location.href = '/'
  }

  return { user, isLoggedIn, isAdmin, setUser, fetchMe, loginWithGoogle, logout, _loaded }
})
