/**
 * Auth Store — JWT lives in httpOnly cookies (set/cleared by backend).
 * Pinia keeps a hot copy of the user object in localStorage for fast initial paint;
 * the source of truth is /api/auth/me.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/index.js'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const isLoggedIn = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  function setUser(userData) {
    user.value = userData
    if (userData) {
      localStorage.setItem('user', JSON.stringify(userData))
    } else {
      localStorage.removeItem('user')
    }
  }

  async function fetchMe() {
    try {
      const res = await api.get('/api/auth/me')
      setUser(res.data)
      return res.data
    } catch {
      setUser(null)
      return null
    }
  }

  function loginWithGoogle() {
    const backendUrl = import.meta.env.VITE_API_URL || ''
    window.location.href = `${backendUrl}/api/auth/google/login`
  }

  async function logout() {
    try {
      await api.post('/api/auth/logout')
    } catch {
      // Even if the call fails (cookie expired etc.), clear local state.
    }
    setUser(null)
  }

  // Bootstrap user on first store init — cheap, lets the app know who's signed in.
  fetchMe()

  return { user, isLoggedIn, isAdmin, setUser, fetchMe, loginWithGoogle, logout }
})
