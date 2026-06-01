// ═══════════════════════════════════════════════════════
// WMS Panama — Auth Store (Zustand)
// ═══════════════════════════════════════════════════════
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { authApi } from '@/api/endpoints'
import type { User } from '@/types'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean

  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  fetchMe: () => Promise<void>
  hasPermission: (permission: string) => boolean
  hasRole: (role: string) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (email, password) => {
        set({ isLoading: true })
        try {
          const tokens = await authApi.login(email, password)
          localStorage.setItem('access_token', tokens.access_token)
          localStorage.setItem('refresh_token', tokens.refresh_token)
          const user = await authApi.me()
          set({ user, isAuthenticated: true, isLoading: false })
        } catch (err) {
          set({ isLoading: false })
          throw err
        }
      },

      logout: async () => {
        const refresh = localStorage.getItem('refresh_token') ?? ''
        try { await authApi.logout(refresh) } catch { /* ignore */ }
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({ user: null, isAuthenticated: false })
      },

      fetchMe: async () => {
        const token = localStorage.getItem('access_token')
        if (!token) return
        try {
          const user = await authApi.me()
          set({ user, isAuthenticated: true })
        } catch {
          set({ user: null, isAuthenticated: false })
        }
      },

      hasPermission: (permission) => {
        const { user } = get()
        return user?.permissions?.includes(permission) ?? false
      },

      hasRole: (role) => {
        const { user } = get()
        return user?.roles?.includes(role) ?? false
      },
    }),
    {
      name: 'wms-auth',
      partialize: (s) => ({ user: s.user, isAuthenticated: s.isAuthenticated }),
    }
  )
)
