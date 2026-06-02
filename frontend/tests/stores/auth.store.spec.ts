/**
 * Unit tests for auth store
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../../src/stores/auth'

vi.mock('../../src/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  }
}))

describe('Auth Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('should initialize with null user when localStorage is empty', () => {
    const store = useAuthStore()
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
    expect(store.isAdmin).toBe(false)
  })

  it('should initialize with user from localStorage', () => {
    const mockUser = {
      id: '1',
      email: 'test@example.com',
      name: 'Test User',
      role: 'user' as const
    }
    localStorage.setItem('user', JSON.stringify(mockUser))
    
    const store = useAuthStore()
    expect(store.user).toEqual(mockUser)
    expect(store.isLoggedIn).toBe(true)
  })

  it('should set user and save to localStorage', () => {
    const store = useAuthStore()
    const mockUser = {
      id: '1',
      email: 'test@example.com',
      name: 'Test User',
      role: 'user' as const
    }

    store.setUser(mockUser)

    expect(store.user).toEqual(mockUser)
    expect(store.isLoggedIn).toBe(true)
    expect(localStorage.getItem('user')).toBe(JSON.stringify(mockUser))
  })

  it('should clear user and remove from localStorage', () => {
    const store = useAuthStore()
    const mockUser = {
      id: '1',
      email: 'test@example.com',
      name: 'Test User',
      role: 'user' as const
    }

    store.setUser(mockUser)
    expect(store.isLoggedIn).toBe(true)

    store.setUser(null)
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
    expect(localStorage.getItem('user')).toBeNull()
  })

  it('should detect admin role correctly', () => {
    const store = useAuthStore()
    const adminUser = {
      id: '1',
      email: 'admin@example.com',
      name: 'Admin User',
      role: 'admin' as const
    }

    store.setUser(adminUser)
    expect(store.isAdmin).toBe(true)

    const regularUser = {
      id: '2',
      email: 'user@example.com',
      name: 'Regular User',
      role: 'user' as const
    }

    store.setUser(regularUser)
    expect(store.isAdmin).toBe(false)
  })

  it('should fetch user data successfully', async () => {
    const store = useAuthStore()
    const mockUser = {
      id: '1',
      email: 'test@example.com',
      name: 'Test User',
      role: 'user' as const
    }

    const api = await import('../../src/api/index')
    vi.mocked(api.default.get).mockResolvedValue({ data: mockUser })

    const result = await store.fetchMe()

    expect(result).toEqual(mockUser)
    expect(store.user).toEqual(mockUser)
    expect(store.isLoggedIn).toBe(true)
  })

  it('should handle fetch user failure', async () => {
    const store = useAuthStore()
    
    const api = await import('../../src/api/index')
    vi.mocked(api.default.get).mockRejectedValue(new Error('Unauthorized'))

    const result = await store.fetchMe()

    expect(result).toBeNull()
    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })

  it('should logout and clear user data', async () => {
    const store = useAuthStore()
    const mockUser = {
      id: '1',
      email: 'test@example.com',
      name: 'Test User',
      role: 'user' as const
    }

    store.setUser(mockUser)
    expect(store.isLoggedIn).toBe(true)

    const api = await import('../../src/api/index')
    vi.mocked(api.default.post).mockResolvedValue({})

    await store.logout()

    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
    expect(localStorage.getItem('user')).toBeNull()
  })

  it('should clear user even if logout API fails', async () => {
    const store = useAuthStore()
    const mockUser = {
      id: '1',
      email: 'test@example.com',
      name: 'Test User',
      role: 'user' as const
    }

    store.setUser(mockUser)

    const api = await import('../../src/api/index')
    vi.mocked(api.default.post).mockRejectedValue(new Error('Network error'))

    await store.logout()

    expect(store.user).toBeNull()
    expect(store.isLoggedIn).toBe(false)
  })
})
