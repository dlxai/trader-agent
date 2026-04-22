import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Bell, Shield, Palette, Moon, Sun, Monitor, Eye, EyeOff } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Separator } from '@/components/ui/Separator'
import { Switch } from '@/components/ui/Switch'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/stores/theme'
import { settingsApi } from '@/lib/api'

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
  const { theme, resolvedTheme, setTheme } = useThemeStore()

  return (
    <SettingsSection
      title="外观"
      description="自定义 WestGardeng 在您设备上的显示效果"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-4">
          <button
            onClick={() => setTheme('light')}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all',
              theme === 'light'
                ? 'border-emerald-500 bg-emerald-500/10'
                : 'border-border hover:border-border'
            )}
          >
            <Sun className="h-6 w-6" />
            <span className="text-sm font-medium">浅色</span>
          </button>
          <button
            onClick={() => setTheme('dark')}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all',
              theme === 'dark'
                ? 'border-emerald-500 bg-emerald-500/10'
                : 'border-border hover:border-border'
            )}
          >
            <Moon className="h-6 w-6" />
            <span className="text-sm font-medium">深色</span>
          </button>
          <button
            onClick={() => setTheme('system')}
            className={cn(
              'flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all',
              theme === 'system'
                ? 'border-emerald-500 bg-emerald-500/10'
                : 'border-border hover:border-border'
            )}
          >
            <Monitor className="h-6 w-6" />
            <span className="text-sm font-medium">跟随系统</span>
          </button>
        </div>
        <p className="text-sm text-muted-foreground">
          当前主题: <span className="font-medium capitalize">{resolvedTheme === 'dark' ? '深色' : '浅色'}</span>
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
  const [showTelegramConfig, setShowTelegramConfig] = useState(false)
  const [botToken, setBotToken] = useState('')
  const [chatId, setChatId] = useState('')

  // 获取 Telegram 配置
  const { data: telegramConfig, refetch } = useQuery({
    queryKey: ['telegram-config'],
    queryFn: () => settingsApi.getTelegramConfig(),
  })

  // 保存 Telegram 配置
  const saveTelegramMutation = useMutation({
    mutationFn: () => settingsApi.configureTelegram(botToken, chatId),
    onSuccess: () => {
      alert('Telegram 配置成功！请检查 Bot 是否收到测试消息。')
      setShowTelegramConfig(false)
      setBotToken('')
      setChatId('')
      refetch()
    },
    onError: () => {
      alert('配置失败，请检查 Token 和 Chat ID 是否正确')
    },
  })

  // 删除 Telegram 配置
  const deleteTelegramMutation = useMutation({
    mutationFn: () => settingsApi.deleteTelegramConfig(),
    onSuccess: () => {
      alert('已解除 Telegram 通知')
      refetch()
    },
  })

  const telegramConnected = telegramConfig?.is_configured

  return (
    <SettingsSection
      title="通知"
      description="选择您希望接收的通知类型"
    >
      <div className="space-y-4">
        {/* Telegram 通知 */}
        <div className="rounded-lg border border-border p-4">
          {showTelegramConfig ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-base">配置 Telegram Bot</Label>
                <Button variant="ghost" size="sm" onClick={() => setShowTelegramConfig(false)}>
                  取消
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                1. 在 @BotFather 创建 Bot<br />
                2. 启动 Bot 后发送 /start<br />
                3. 访问 https://t.me/userinfobot 获取你的 Chat ID
              </p>
              <div className="space-y-2">
                <Input
                  placeholder="Bot Token (如 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11)"
                  value={botToken}
                  onChange={(e) => setBotToken(e.target.value)}
                />
                <Input
                  placeholder="Chat ID (如 123456789)"
                  value={chatId}
                  onChange={(e) => setChatId(e.target.value)}
                />
                <Button
                  className="w-full"
                  onClick={() => saveTelegramMutation.mutate()}
                  disabled={!botToken || !chatId || saveTelegramMutation.isPending}
                  isLoading={saveTelegramMutation.isPending}
                >
                  保存并发送测试消息
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <Label className="text-base">Telegram 通知</Label>
                  {telegramConnected && (
                    <span className="text-xs bg-emerald-500/10 text-emerald-500 px-2 py-0.5 rounded-full">
                      已连接
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {telegramConfig?.bot_token_masked
                    ? `Bot: ${telegramConfig.bot_token_masked} | Chat ID: ${telegramConfig.chat_id}`
                    : '通过 Telegram Bot 接收交易通知'}
                </p>
              </div>
              <div className="flex gap-2">
                {telegramConnected && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteTelegramMutation.mutate()}
                    className="text-red-500 hover:text-red-600"
                  >
                    解除
                  </Button>
                )}
                <Button
                  variant={telegramConnected ? 'outline' : 'default'}
                  size="sm"
                  onClick={() => setShowTelegramConfig(true)}
                >
                  {telegramConnected ? '重新配置' : '配置'}
                </Button>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border p-4">
          <div className="space-y-0.5">
            <Label className="text-base">邮件通知</Label>
            <p className="text-sm text-muted-foreground">
              通过邮件接收通知
            </p>
          </div>
          <Switch
            checked={settings.email}
            onCheckedChange={(checked) =>
              setSettings({ ...settings, email: checked })
            }
          />
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border p-4">
          <div className="space-y-0.5">
            <Label className="text-base">浏览器推送</Label>
            <p className="text-sm text-muted-foreground">
              在浏览器中接收推送通知
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
          <h4 className="text-sm font-medium">通知类型</h4>

          <div className="flex items-center justify-between">
            <Label className="text-sm">交易执行</Label>
            <Switch
              checked={settings.trades}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, trades: checked })
              }
            />
          </div>

          <div className="flex items-center justify-between">
            <Label className="text-sm">订单更新</Label>
            <Switch
              checked={settings.orders}
              onCheckedChange={(checked) =>
                setSettings({ ...settings, orders: checked })
              }
            />
          </div>

          <div className="flex items-center justify-between">
            <Label className="text-sm">价格提醒</Label>
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
      title="安全"
      description="Manage your security settings"
    >
      <div className="space-y-4">
        {/* Password Change */}
        <div className="rounded-lg border border-border p-4">
          <h4 className="text-sm font-medium mb-4">修改密码</h4>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="current">当前密码</Label>
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
              <Label htmlFor="new">新密码</Label>
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

            <Button className="w-full">更新密码</Button>
          </div>
        </div>

        <Separator />

        {/* Two-Factor Authentication */}
        <div className="rounded-lg border border-border p-4">
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
        <div className="rounded-lg border border-border p-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-medium">API 密钥</h4>
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
        <h1 className="text-2xl font-bold tracking-tight">设置</h1>
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
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                <Palette className="h-4 w-4" />
                外观
              </button>
              <button
                onClick={() => setActiveTab('notifications')}
                className={cn(
                  'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  activeTab === 'notifications'
                    ? 'bg-emerald-500/10 text-emerald-500'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                <Bell className="h-4 w-4" />
                通知
              </button>
              <button
                onClick={() => setActiveTab('security')}
                className={cn(
                  'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  activeTab === 'security'
                    ? 'bg-emerald-500/10 text-emerald-500'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                <Shield className="h-4 w-4" />
                安全
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
