import { useState } from 'react'
import { Bell, Shield, Palette, Moon, Sun, Monitor, Eye, EyeOff } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Separator } from '@/components/ui/Separator'
import { Switch } from '@/components/ui/Switch'
import { cn } from '@/lib/utils'

interface SettingsSectionProps {
  title: string
  description?: string
  children: React.ReactNode
}

function SettingsSection({ title, description, children }: SettingsSectionProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-medium">{title}</h3>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      <div className="space-y-4">
        {children}
      </div>
    </div>
  )
}

function AppearanceSettings() {
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('dark')
  const resolvedTheme = theme === 'system' ? 'dark' : theme

  return (
    <SettingsSection
      title="Appearance"
      description="Customize how WestGardeng looks on your device"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <button
            onClick={() => setTheme('light')}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all',
              theme === 'light'
                ? 'border-emerald-500 bg-emerald-500/10'
                : 'border-void-300 hover:border-void-400'
            )}
          >
            <Sun className="h-6 w-6" />
            <span className="text-sm font-medium">Light</span>
          </button>
          <button
            onClick={() => setTheme('dark')}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all',
              theme === 'dark'
                ? 'border-emerald-500 bg-emerald-500/10'
                : 'border-void-300 hover:border-void-400'
            )}
          >
            <Moon className="h-6 w-6" />
            <span className="text-sm font-medium">Dark</span>
          </button>
          <button
            onClick={() => setTheme('system')}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all',
              theme === 'system'
                ? 'border-emerald-500 bg-emerald-500/10'
                : 'border-void-300 hover:border-void-400'
            )}
          >
            <Monitor className="h-6 w-6" />
            <span className="text-sm font-medium">System</span>
          </button>
        </div>
        <p className="text-sm text-muted-foreground">
          Current theme: <span className="font-medium capitalize">{resolvedTheme}</span>
        </p>
      </div>
    </SettingsSection>
  )
}

function NotificationSettings() {
  const [settings, setSettings] = useState({
    email: true,
    push: true,
    trades: true,
    orders: true,
    priceAlerts: false,
  })

  return (
    <SettingsSection
      title="Notifications"
      description="Choose what notifications you want to receive"
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between rounded-lg border border-void-300 p-4">
          <div className="space-y-0.5">
            <Label className="text-base">Email Notifications</Label>
            <p className="text-sm text-muted-foreground">
              Receive notifications via email
            </p>
          </div>
          <Switch
            checked={settings.email}
            onCheckedChange={(checked) =>
              setSettings({ ...settings, email: checked })
            }
          />
        </div>

        <div className="flex items-center justify-between rounded-lg border border-void-300 p-4">
          <div className="space-y-0.5">
            <Label className="text-base">Push Notifications</Label>
            <p className="text-sm text-muted-foreground">
              Receive push notifications in your browser
            </p>
          </div>
          <Switch
            checked={settings.push}
            onCheckedChange={(checked) =>
              setSettings({ ...settings, push: checked })
            }
          />
        </div>

        <Separator />

        <div className="space-y-3">
          <h4 className="text-sm font-medium">Notification Types</h4>

          <div className="flex items-center justify-between">
            <Label className="text-sm">Trade Executions</Label>
            <Switch
              checked={settings.trades}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, trades: checked })
              }
            />
          </div>

          <div className="flex items-center justify-between">
            <Label className="text-sm">Order Updates</Label>
            <Switch
              checked={settings.orders}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, orders: checked })
              }
            />
          </div>

          <div className="flex items-center justify-between">
            <Label className="text-sm">Price Alerts</Label>
            <Switch
              checked={settings.priceAlerts}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, priceAlerts: checked })
              }
            />
          </div>
        </div>
      </div>
    </SettingsSection>
  )
}

function SecuritySettings() {
  const [showPassword, setShowPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)

  return (
    <SettingsSection
      title="Security"
      description="Manage your security settings"
    >
      <div className="space-y-4">
        {/* Password Change */}
        <div className="rounded-lg border border-void-300 p-4">
          <h4 className="text-sm font-medium mb-4">Change Password</h4>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="current">Current Password</Label>
              <div className="relative">
                <Input
                  id="current"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter current password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="new">New Password</Label>
              <div className="relative">
                <Input
                  id="new"
                  type={showNewPassword ? 'text' : 'password'}
                  placeholder="Enter new password"
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword(!showNewPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showNewPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            <Button className="w-full">Update Password</Button>
          </div>
        </div>

        <Separator />

        {/* Two-Factor Authentication */}
        <div className="rounded-lg border border-void-300 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-medium">Two-Factor Authentication</h4>
              <p className="text-sm text-muted-foreground">
                Add an extra layer of security to your account
              </p>
            </div>
            <Button variant="outline">Enable</Button>
          </div>
        </div>

        {/* API Keys */}
        <div className="rounded-lg border border-void-300 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-medium">API Keys</h4>
              <p className="text-sm text-muted-foreground">
                Manage API keys for programmatic access
              </p>
            </div>
            <Button variant="outline">Manage</Button>
          </div>
        </div>
      </div>
    </SettingsSection>
  )
}

// Main Settings Page
export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<'appearance' | 'notifications' | 'security'>('appearance')

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account settings and preferences
        </p>
      </div>

      {/* Settings Layout */}
      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Sidebar Navigation */}
        <Card className="lg:w-64 lg:shrink-0">
          <CardContent className="p-2">
            <nav className="space-y-1">
              <button
                onClick={() => setActiveTab('appearance')}
                className={cn(
                  'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  activeTab === 'appearance'
                    ? 'bg-emerald-500/10 text-emerald-500'
                    : 'text-muted-foreground hover:bg-void-200 hover:text-foreground'
                )}
              >
                <Palette className="h-4 w-4" />
                Appearance
              </button>
              <button
                onClick={() => setActiveTab('notifications')}
                className={cn(
                  'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  activeTab === 'notifications'
                    ? 'bg-emerald-500/10 text-emerald-500'
                    : 'text-muted-foreground hover:bg-void-200 hover:text-foreground'
                )}
              >
                <Bell className="h-4 w-4" />
                Notifications
              </button>
              <button
                onClick={() => setActiveTab('security')}
                className={cn(
                  'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  activeTab === 'security'
                    ? 'bg-emerald-500/10 text-emerald-500'
                    : 'text-muted-foreground hover:bg-void-200 hover:text-foreground'
                )}
              >
                <Shield className="h-4 w-4" />
                Security
              </button>
            </nav>
          </CardContent>
        </Card>

        {/* Main Content */}
        <div className="flex-1">
          <Card>
            <CardContent className="p-6">
              {activeTab === 'appearance' && <AppearanceSettings />}
              {activeTab === 'notifications' && <NotificationSettings />}
              {activeTab === 'security' && <SecuritySettings />}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
