// ═══════════════════════════════════════════════════════
// WMS Panama — Axios HTTP Client
// ═══════════════════════════════════════════════════════
import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios'
import toast from 'react-hot-toast'

const BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1'

// ── Instancia principal ────────────────────────────────
export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor: inyecta JWT ──────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor: manejo de errores ───────────
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status

    if (status === 401) {
      // Intentar refresh
      const refreshed = await tryRefreshToken()
      if (refreshed && error.config) {
        return api.request(error.config as AxiosRequestConfig)
      }
      // Refresh fallido → logout
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
      return Promise.reject(error)
    }

    if (status === 403) {
      toast.error('No tienes permiso para realizar esta acción.')
    } else if (status === 422) {
      const data = error.response?.data as { detail?: unknown }
      const detail = data?.detail
      if (Array.isArray(detail)) {
        detail.forEach((e: { msg?: string }) => toast.error(e.msg ?? 'Error de validación'))
      } else if (typeof detail === 'string') {
        toast.error(detail)
      }
    } else if (status === 409) {
      const data = error.response?.data as { detail?: string }
      toast.error(data?.detail ?? 'Conflicto de estado.')
    } else if (status && status >= 500) {
      toast.error('Error del servidor. Por favor contacta soporte.')
    }

    return Promise.reject(error)
  }
)

async function tryRefreshToken(): Promise<boolean> {
  const refresh = localStorage.getItem('refresh_token')
  if (!refresh) return false
  try {
    const { data } = await axios.post(`${BASE_URL}/auth/refresh`, {
      refresh_token: refresh,
    })
    localStorage.setItem('access_token', data.access_token)
    if (data.refresh_token) {
      localStorage.setItem('refresh_token', data.refresh_token)
    }
    return true
  } catch {
    return false
  }
}

export default api
