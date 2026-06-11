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
  const user = ref<User | null>(JSON.parse(localStorage.getItem('user') || 'null'))

  const isLoggedIn = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  function setUser(userData: User | null): void {
    user.value = userData
    if (userData) {
      localStorage.setItem('user', JSON.stringify(userData))
    } else {
      localStorage.removeItem('user')
    }
  }

  async function fetchMe(): Promise<User | null> {
    try {
      const res = await api.get<User>('/api/auth/me')
      setUser(res.data)
      return res.data
    } catch {
      setUser(null)
      return null
    }
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

  fetchMe()

  return { user, isLoggedIn, isAdmin, setUser, fetchMe, loginWithGoogle, logout }
})
