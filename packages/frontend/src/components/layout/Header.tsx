import { Menu, Bell, Search, Sun, Moon, Command } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import { cn } from '@/lib/utils'

interface HeaderProps {
  onMenuClick: () => void
  onToggleSidebar: () => void
  isSidebarOpen: boolean
}

export function Header({ onMenuClick, onToggleSidebar, isSidebarOpen }: HeaderProps) {
  const { toggleTheme, resolvedTheme } = useThemeStore()
  const { user } = useAuthStore()

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-void-300 bg-void-50/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-void-50/80">
      {/* Left section */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={onMenuClick}
          className="lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleSidebar}
          className="hidden lg:flex"
        >
          <Command className={cn('h-5 w-5 transition-transform', !isSidebarOpen && 'rotate-180')} />
        </Button>
      </div>

      {/* Center section - Search */}
      <div className="hidden flex-1 items-center justify-center px-8 md:flex">
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search portfolios, positions, orders..."
            className="h-9 w-full rounded-md border border-void-300 bg-void-100 pl-10 pr-4 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          />
          <kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 items-center gap-0.5 rounded border border-void-300 bg-void-200 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground md:flex">
            <span>Ctrl</span>
            <span>K</span>
          </kbd>
        </div>
      </div>

      {/* Right section */}
      <div className="flex items-center gap-2">
        {/* Theme toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          className="hidden sm:flex"
        >
          {resolvedTheme === 'dark' ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
        </Button>

        {/* Notifications */}
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-emerald-500" />
        </Button>

        {/* User menu */}
        {user && (
          <div className="flex items-center gap-3 pl-4 border-l border-void-300">
            <div className="hidden md:block text-right">
              <p className="text-sm font-medium">{(user as any).username || (user as any).name || 'User'}</p>
              <p className="text-xs text-muted-foreground">{user.email}</p>
            </div>
            <div className="h-9 w-9 rounded-full bg-emerald-500/10 flex items-center justify-center">
              <span className="text-sm font-medium text-emerald-500">
                {((user as any).username || (user as any).name || 'U').slice(0, 2).toUpperCase()}
              </span>
            </div>
          </div>
        )}
      </div>
    </header>
  )
}
