import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Briefcase,
  TrendingUp,
  ListOrdered,
  Plug,
  Settings,
  Wallet,
  ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth'

interface SidebarProps {
  isCollapsed?: boolean
  onClose?: () => void
}

interface NavItem {
  label: string
  icon: React.ElementType
  href: string
  children?: { label: string; href: string }[]
}

const navItems: NavItem[] = [
  {
    label: 'Dashboard',
    icon: LayoutDashboard,
    href: '/dashboard',
  },
  {
    label: 'Portfolios',
    icon: Briefcase,
    href: '/portfolios',
  },
  {
    label: 'Positions',
    icon: TrendingUp,
    href: '/positions',
  },
  {
    label: 'Orders',
    icon: ListOrdered,
    href: '/orders',
  },
  {
    label: 'Providers',
    icon: Plug,
    href: '/providers',
  },
]

const bottomNavItems: NavItem[] = [
  {
    label: 'Settings',
    icon: Settings,
    href: '/settings',
  },
]

export function Sidebar({ isCollapsed = false, onClose }: SidebarProps) {
  const { user } = useAuthStore()

  const isActive = (href: string) => {
    if (href === '/dashboard') {
      return location.pathname === href
    }
    return location.pathname.startsWith(href)
  }

  return (
    <div className="flex h-full flex-col border-r border-void-300 bg-void-50">
      {/* Logo */}
      <div className="flex h-16 items-center border-b border-void-300 px-4">
        <NavLink
          to="/dashboard"
          className="flex items-center gap-3"
          onClick={onClose}
        >
          <div className="flex h-8 w-8 items-center justify-center rounded bg-emerald-500">
            <Wallet className="h-5 w-5 text-black" />
          </div>
          {!isCollapsed && (
            <span className="text-lg font-semibold text-foreground">
              WestGardeng
            </span>
          )}
        </NavLink>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const active = isActive(item.href)
          return (
            <NavLink
              key={item.href}
              to={item.href}
              onClick={onClose}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                active
                  ? 'bg-emerald-500/10 text-emerald-500'
                  : 'text-muted-foreground hover:bg-void-200 hover:text-foreground'
              )}
            >
              <item.icon className={cn(
                'h-4 w-4 shrink-0',
                active && 'text-emerald-500'
              )} />
              {!isCollapsed && (
                <>
                  <span className="flex-1">{item.label}</span>
                  {item.children && (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </>
              )}
            </NavLink>
          )
        })}
      </nav>

      {/* Bottom Navigation */}
      <div className="border-t border-void-300 p-3">
        {bottomNavItems.map((item) => {
          const active = isActive(item.href)
          return (
            <NavLink
              key={item.href}
              to={item.href}
              onClick={onClose}
              className={cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                active
                  ? 'bg-emerald-500/10 text-emerald-500'
                  : 'text-muted-foreground hover:bg-void-200 hover:text-foreground'
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!isCollapsed && <span>{item.label}</span>}
            </NavLink>
          )
        })}

        {/* User Info */}
        {!isCollapsed && user && (
          <div className="mt-4 flex items-center gap-3 rounded-md border border-void-300 bg-void-100 p-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
              <span className="text-xs font-medium">
                {(user.name || 'U').slice(0, 2).toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="truncate text-sm font-medium">{user.name}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
