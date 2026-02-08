import { create } from 'zustand'
import { api, type User, type AuthResponse } from '@/lib/api'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, name: string, password: string) => Promise<void>
  logout: () => void
  clearError: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null })
    try {
      const data = await api.post<AuthResponse>('/auth/login', { email, password })
      api.setTokens(data.access_token, data.csrf_token)
      set({ user: data.user, isAuthenticated: true, isLoading: false })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  register: async (email, name, password) => {
    set({ isLoading: true, error: null })
    try {
      const data = await api.post<AuthResponse>('/auth/register', { email, name, password })
      api.setTokens(data.access_token, data.csrf_token)
      set({ user: data.user, isAuthenticated: true, isLoading: false })
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false })
    }
  },

  logout: () => {
    api.clearTokens()
    set({ user: null, isAuthenticated: false })
  },

  clearError: () => set({ error: null }),
}))
