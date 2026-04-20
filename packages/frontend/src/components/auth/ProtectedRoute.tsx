import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { useEffect, useState } from 'react'

interface ProtectedRouteProps {
  children: React.ReactNode
  requireAdmin?: boolean
}

export function ProtectedRoute({ children, requireAdmin = false }: ProtectedRouteProps) {
  const { isAuthenticated, user, initialize, isLoading } = useAuthStore()
  const location = useLocation()
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    const init = async () => {
      await initialize()
      setInitialized(true)
    }
    init()
  }, [initialize])

  // Show loading screen while initializing
  if (!initialized || isLoading) {
    return <LoadingScreen message="Authenticating..." />
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Check admin requirement
  if (requireAdmin && user?.role !== 'admin') {
    return <Navigate to="/dashboard" replace />
  }

  return <>{children}</>
}
