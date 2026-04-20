import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import type { LoginCredentials, RegisterCredentials } from '@/types'

export function useAuth() {
  const navigate = useNavigate()
  const {
    user,
    isAuthenticated,
    isLoading,
    error,
    login: storeLogin,
    register: storeRegister,
    logout: storeLogout,
    clearError,
  } = useAuthStore()

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      try {
        await storeLogin(credentials.email, credentials.password)
        navigate('/dashboard')
        return true
      } catch {
        return false
      }
    },
    [storeLogin, navigate]
  )

  const register = useCallback(
    async (credentials: RegisterCredentials) => {
      try {
        await storeRegister(credentials.email, credentials.username, credentials.password)
        navigate('/dashboard')
        return true
      } catch {
        return false
      }
    },
    [storeRegister, navigate]
  )

  const logout = useCallback(async () => {
    await storeLogout()
    navigate('/login')
  }, [storeLogout, navigate])

  return {
    user,
    isAuthenticated,
    isLoading,
    error,
    login,
    register,
    logout,
    clearError,
  }
}
