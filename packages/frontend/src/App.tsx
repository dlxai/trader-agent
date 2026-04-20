import { useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { Toaster } from '@/components/ui/Toaster'

function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAuthenticated, isLoading, initialize } = useAuthStore()
  const { initialize: initializeTheme } = useThemeStore()

  // Initialize theme on mount
  useEffect(() => {
    initializeTheme()
  }, [initializeTheme])

  // Initialize auth on mount
  useEffect(() => {
    initialize()
  }, [initialize])

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated && location.pathname !== '/login') {
      navigate('/login', { state: { from: location }, replace: true })
    }
  }, [isAuthenticated, isLoading, location, navigate])

  // Show loading screen while initializing
  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <>
      <Outlet />
      <Toaster />
    </>
  )
}

export default App
