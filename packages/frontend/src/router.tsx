import { createBrowserRouter, Navigate, Outlet, type RouteObject } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { MainLayout } from '@/components/layout/MainLayout'
import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { LoadingScreen } from '@/components/ui/LoadingScreen'

// Lazy load pages
const LoginPage = lazy(() => import('@/pages/Login'))
const DashboardPage = lazy(() => import('@/pages/Dashboard'))
const PortfoliosPage = lazy(() => import('@/pages/Portfolios'))
const StrategiesPage = lazy(() => import('@/pages/Strategies'))
const PositionsPage = lazy(() => import('@/pages/Positions'))
const OrdersPage = lazy(() => import('@/pages/Orders'))
const ProvidersPage = lazy(() => import('@/pages/Providers'))
const WalletsPage = lazy(() => import('@/pages/Wallets'))
const SettingsPage = lazy(() => import('@/pages/Settings'))
const NotFoundPage = lazy(() => import('@/pages/NotFound'))

// Wrap component with suspense
const withSuspense = (Component: React.ComponentType) => {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <Component />
    </Suspense>
  )
}

// Define routes
const routes: RouteObject[] = [
  {
    path: '/login',
    element: withSuspense(LoginPage),
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <MainLayout>
          <Outlet />
        </MainLayout>
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: <Navigate to="/dashboard" replace />,
      },
      {
        path: 'dashboard',
        element: withSuspense(DashboardPage),
      },
      {
        path: 'portfolios',
        element: withSuspense(PortfoliosPage),
      },
      {
        path: 'portfolios/:id',
        element: withSuspense(PortfoliosPage),
      },
      {
        path: 'positions',
        element: withSuspense(PositionsPage),
      },
      {
        path: 'positions/:id',
        element: withSuspense(PositionsPage),
      },
      {
        path: 'orders',
        element: withSuspense(OrdersPage),
      },
      {
        path: 'providers',
        element: withSuspense(ProvidersPage),
      },
      {
        path: 'wallets',
        element: withSuspense(WalletsPage),
      },
      {
        path: 'strategies',
        element: withSuspense(StrategiesPage),
      },
      {
        path: 'settings',
        element: withSuspense(SettingsPage),
      },
    ],
  },
  {
    path: '*',
    element: withSuspense(NotFoundPage),
  },
]

export const router = createBrowserRouter(routes)
