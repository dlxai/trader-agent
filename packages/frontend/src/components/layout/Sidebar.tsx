import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Briefcase,
  TrendingUp,
  ListOrdered,
  Settings,
  Wallet,
  Brain,
  ChevronRight,
  Zap,
  Plug,
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
    label: '仪表板',
    icon: LayoutDashboard,
    href: '/dashboard',
  },
  {
    label: '投资组合',
    icon: Briefcase,
    href: '/portfolios',
  },
  {
    label: '持仓',
    icon: TrendingUp,
    href: '/positions',
  },
  {
    label: '订单',
    icon: ListOrdered,
    href: '/orders',
  },
  {
    label: '策略',
    icon: Brain,
    href: '/strategies',
  },
  {
    label: '信号',
    icon: Zap,
    href: '/signals',
  },
  {
    label: 'AI Provider',
    icon: Plug,
    href: '/providers',
  },
  {
    label: '钱包',
    icon: Wallet,
    href: '/wallets',
  },
]

const bottomNavItems: NavItem[] = [
  {
    label: '设置',
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
    <div className="flex h-full flex-col border-r border-border bg-muted/50">
      {/* Logo */}
      <div className="flex h-16 items-center border-b border-border px-4">
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
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
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
      <div className="border-t border-border p-3">
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
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!isCollapsed && <span>{item.label}</span>}
            </NavLink>
          )
        })}

        {/* User Info */}
        {!isCollapsed && user && (
          <div className="mt-4 flex items-center gap-3 rounded-md border border-border bg-muted/50 p-3">
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
