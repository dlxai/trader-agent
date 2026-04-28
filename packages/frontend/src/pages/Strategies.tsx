import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Play,
  Pause,
  Trash2,
  Brain,
  Settings,
  Database,
  Zap,
  Filter,
  Bot,
  Monitor,
  Shield,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { strategiesApi, providersApi, portfoliosApi } from '@/lib/api'
import type { StrategySummary, CreateStrategyRequest, UpdateStrategyRequest } from '@/types'
import {
  formatCurrency,
  cn,
  getPnlColor,
  getPnlBgColor,
} from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Switch } from '@/components/ui/Switch'
import { Separator } from '@/components/ui/Separator'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import {
  DEFAULT_SYSTEM_PROMPT,
  DEFAULT_CUSTOM_PROMPT,
  DEFAULT_DATA_SOURCES,
  DEFAULT_TRIGGER,
  DEFAULT_FILTERS,
  TAIL_FILTERS,
  SPORTS_FILTERS,
  SPORTS_TRIGGER,
  DEFAULT_ORDER,
  DEFAULT_POSITION_MONITOR,
  DEFAULT_RISK,
} from '@/constants/strategy'

// Tab labels mapping
const tabLabels: Record<string, string> = {
  basic: '基础信息',
  data: '数据源',
  trigger: '触发条件',
  filters: '信号过滤',
  ai: 'AI配置',
  monitor: '持仓监控',
  risk: '风险控制',
}

function StrategyCard({ strategy, onDelete, onStart, onStop, onEdit, isLoading, portfolios }: { strategy: StrategySummary; onDelete: (id: string) => void; onStart: (id: string) => void; onStop: (id: string) => void; onEdit: (strategy: StrategySummary) => void; isLoading?: boolean; portfolios: any[] }) {
  const pnlIsPositive = Number(strategy.total_pnl) >= 0
  const portfolioName = portfolios.find(p => p.id === strategy.portfolio_id)?.name || '未绑定组合'
  const hasPortfolio = !!strategy.portfolio_id

  return (
    <Card className="group transition-all hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/5">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-lg">{strategy.name}</CardTitle>
            <p className="text-xs text-muted-foreground mt-0.5">{portfolioName}</p>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-0 group-hover:opacity-100 hover:text-red-500"
              onClick={() => onDelete(strategy.id)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status */}
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-muted-foreground">状态</span>
          <span className={cn(
            'px-2 py-1 rounded-full text-xs font-medium',
            strategy.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-700'
          )}>
            {strategy.is_active ? '运行中' : '已停止'}
          </span>
        </div>

        {/* Order Size Range */}
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-muted-foreground">下单金额范围</span>
          <span className="text-2xl font-bold font-mono">
            {formatCurrency(strategy.min_order_size)} - {formatCurrency(strategy.max_order_size)}
          </span>
        </div>

        {/* P&L */}
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded',
                getPnlBgColor(Number(strategy.total_pnl))
              )}
            >
              {pnlIsPositive ? (
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              ) : (
                <TrendingDown className="h-4 w-4 text-red-500" />
              )}
            </div>
            <div>
              <p className="text-sm font-medium">总盈亏</p>
              <p className="text-xs text-muted-foreground">
                {strategy.total_trades} 笔交易
              </p>
            </div>
          </div>
          <span
            className={cn(
              'font-mono font-medium',
              getPnlColor(Number(strategy.total_pnl))
            )}
          >
            {formatCurrency(Number(strategy.total_pnl))}
          </span>
        </div>

        {/* Quick Actions */}
        <div className="flex gap-2">
          {strategy.is_active ? (
            <Button variant="outline" size="sm" className="flex-1" disabled={isLoading} isLoading={isLoading} onClick={() => onStop(strategy.id)}>
              <Pause className="mr-2 h-4 w-4" />
              {isLoading ? '停止中...' : '停止'}
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              disabled={isLoading || !hasPortfolio}
              isLoading={isLoading}
              onClick={() => {
                if (!hasPortfolio) {
                  alert('请先绑定投资组合')
                  return
                }
                onStart(strategy.id)
              }}
              title={hasPortfolio ? '启动策略' : '请先绑定投资组合'}
            >
              <Play className="mr-2 h-4 w-4" />
              {isLoading ? '启动中...' : '启动'}
            </Button>
          )}
          <Button variant="outline" size="sm" className="flex-1" disabled={isLoading} onClick={() => onEdit(strategy)}>
            <DollarSign className="mr-2 h-4 w-4" />
            编辑
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function StrategiesPage() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [selectedStrategy, setSelectedStrategy] = useState<StrategySummary | null>(null)
  const [selectedTab, setSelectedTab] = useState('basic')

  // Basic info state
  const [newStrategy, setNewStrategy] = useState({
    name: '',
    description: '',
    min_order_size: 1,
    max_order_size: 5,
    provider_id: '',
    portfolio_id: '',
  })

  // Full config state
  const [config, setConfig] = useState({
    template: 'generic' as 'generic' | 'tail' | 'sports',
    data_sources: DEFAULT_DATA_SOURCES,
    trigger: DEFAULT_TRIGGER,
    filters: DEFAULT_FILTERS,
    order: DEFAULT_ORDER,
    position_monitor: DEFAULT_POSITION_MONITOR,
    risk: DEFAULT_RISK,
    system_prompt: DEFAULT_SYSTEM_PROMPT,
    custom_prompt: DEFAULT_CUSTOM_PROMPT,
  })

  const queryClient = useQueryClient()

  // Fetch providers from backend (UUID-based)
  const { data: providersData } = useQuery({
    queryKey: ['providers'],
    queryFn: () => providersApi.getAll(),
  })

  const providers = providersData || []

  // Fetch portfolios from backend
  const { data: portfoliosData } = useQuery({
    queryKey: ['portfolios'],
    queryFn: () => portfoliosApi.getAll(),
  })

  const portfolios = portfoliosData?.items || []

  const { data: strategiesResponse, isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: () => strategiesApi.getAll(),
  })

  const strategies = strategiesResponse?.items || []

  const createMutation = useMutation({
    mutationFn: (data: CreateStrategyRequest) =>
      strategiesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      setIsCreateDialogOpen(false)
      setNewStrategy({ name: '', description: '', min_order_size: 1, max_order_size: 5, provider_id: '' })
      setConfig({
        template: 'generic',
        data_sources: DEFAULT_DATA_SOURCES,
        trigger: DEFAULT_TRIGGER,
        filters: DEFAULT_FILTERS,
        order: DEFAULT_ORDER,
        position_monitor: DEFAULT_POSITION_MONITOR,
        risk: DEFAULT_RISK,
        system_prompt: DEFAULT_SYSTEM_PROMPT,
        custom_prompt: DEFAULT_CUSTOM_PROMPT,
      })
      setSelectedTab('basic')
    },
    onError: (error: any) => {
      console.error('Create strategy error:', error)
      const detail = error?.response?.data?.detail
      let msg: string
      if (Array.isArray(detail)) {
        msg = detail.map((d: any) => `${d.loc?.join('.')}: ${d.msg}`).join('\n')
      } else {
        msg = detail || error?.message || '未知错误'
      }
      alert('创建失败: ' + msg)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => strategiesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const startMutation = useMutation({
    mutationFn: (id: string) => strategiesApi.start(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      alert('策略已启动')
    },
    onError: (error: any) => {
      console.error('Start strategy error:', error)
      const detail = error?.response?.data?.detail
      alert('启动失败: ' + (detail || error?.message || '未知错误'))
    },
  })

  const stopMutation = useMutation({
    mutationFn: (id: string) => strategiesApi.stop(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      alert('策略已停止')
    },
    onError: (error: any) => {
      console.error('Stop strategy error:', error)
      const detail = error?.response?.data?.detail
      alert('停止失败: ' + (detail || error?.message || '未知错误'))
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateStrategyRequest }) =>
      strategiesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      setIsEditDialogOpen(false)
      setSelectedStrategy(null)
      setSelectedTab('basic')
    },
  })

  // Handle edit button click
  const handleEdit = (strategy: StrategySummary) => {
    setSelectedStrategy(strategy)
    setIsEditDialogOpen(true)
    setSelectedTab('basic')
  }

  // Load strategy data for editing
  const { data: editStrategyData } = useQuery({
    queryKey: ['strategy', selectedStrategy?.id],
    queryFn: () => strategiesApi.getById(selectedStrategy!.id),
    enabled: !!selectedStrategy?.id && isEditDialogOpen,
  })

  // Populate form when editing
  useEffect(() => {
    if (editStrategyData) {
      const strategy = editStrategyData as any // Cast to access all fields
      setNewStrategy({
        name: strategy.name,
        description: strategy.description || '',
        min_order_size: strategy.min_order_size,
        max_order_size: strategy.max_order_size,
        provider_id: strategy.provider_id || '',
        portfolio_id: strategy.portfolio_id || '',
      })
      setConfig({
        template: 'generic',
        data_sources: strategy.data_sources || DEFAULT_DATA_SOURCES,
        trigger: strategy.trigger || DEFAULT_TRIGGER,
        filters: strategy.filters || DEFAULT_FILTERS,
        order: {
          min_order_size: strategy.min_order_size,
          max_order_size: strategy.max_order_size,
          default_amount: (strategy as any).default_amount || 5,
        },
        position_monitor: strategy.position_monitor || DEFAULT_POSITION_MONITOR,
        risk: {
          max_positions: strategy.max_open_positions || 100,
          min_risk_reward_ratio: (strategy as any).min_risk_reward_ratio || 2.0,
          max_margin_usage: 0.9,
          min_position_size: 1,
          max_position_size: 5,
        },
        system_prompt: strategy.system_prompt || DEFAULT_SYSTEM_PROMPT,
        custom_prompt: strategy.custom_prompt || DEFAULT_CUSTOM_PROMPT,
      })
    }
  }, [editStrategyData])

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newStrategy.name.trim()) {
      alert('策略名称不能为空')
      return
    }
    // Flatten config for backend API
    const strategyData: CreateStrategyRequest = {
      ...newStrategy,
      provider_id: newStrategy.provider_id || undefined,
      portfolio_id: newStrategy.portfolio_id || undefined,
      type: 'ai' as const,
      // Data sources
      data_sources: config.data_sources,
      // Trigger
      trigger: config.trigger,
      // Filters
      filters: config.filters,
      // Position monitor
      position_monitor: config.position_monitor,
      // Order config (flat)
      min_order_size: config.order.min_order_size,
      max_order_size: config.order.max_order_size,
      default_amount: config.order.default_amount,
      // Risk config (flat)
      max_open_positions: config.risk.max_positions,
      min_risk_reward_ratio: config.risk.min_risk_reward_ratio,
      max_margin_usage: config.risk.max_margin_usage,
      min_position_size: config.risk.min_position_size,
      // AI prompts
      system_prompt: config.system_prompt,
      custom_prompt: config.custom_prompt,
    }
    console.log('Creating strategy with data:', strategyData)
    createMutation.mutate(strategyData)
  }

  const handleUpdate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedStrategy) return

    const strategyData: UpdateStrategyRequest = {
      name: newStrategy.name,
      description: newStrategy.description,
      provider_id: newStrategy.provider_id || undefined,
      portfolio_id: newStrategy.portfolio_id || undefined,
      data_sources: config.data_sources,
      trigger: config.trigger,
      filters: config.filters,
      position_monitor: config.position_monitor,
      min_order_size: newStrategy.min_order_size,
      max_order_size: newStrategy.max_order_size,
      system_prompt: config.system_prompt,
      custom_prompt: config.custom_prompt,
    }

    updateMutation.mutate({ id: selectedStrategy.id, data: strategyData })
  }

  // Reset form to defaults
  const resetForm = () => {
    setNewStrategy({ name: '', description: '', min_order_size: 10, max_order_size: 100, provider_id: '', portfolio_id: '' })
    setConfig({
      template: 'generic',
      data_sources: DEFAULT_DATA_SOURCES,
      trigger: DEFAULT_TRIGGER,
      filters: DEFAULT_FILTERS,
      order: DEFAULT_ORDER,
      position_monitor: DEFAULT_POSITION_MONITOR,
      risk: DEFAULT_RISK,
      system_prompt: DEFAULT_SYSTEM_PROMPT,
      custom_prompt: DEFAULT_CUSTOM_PROMPT,
    })
    setSelectedTab('basic')
  }

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">交易策略</h1>
          <p className="text-muted-foreground">
            管理您的自动化交易策略并跟踪表现
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          新建策略
        </Button>
      </div>

      {/* Create Dialog */}
      <Dialog
          open={isCreateDialogOpen}
          onOpenChange={(open) => {
            setIsCreateDialogOpen(open)
            if (!open) resetForm()
          }}
        >
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
              <DialogHeader>
                <DialogTitle>创建新策略</DialogTitle>
                <DialogDescription>
                  配置您的自动化交易策略
                </DialogDescription>
              </DialogHeader>

              {/* Tab Navigation */}
              <div className="flex border-b mb-4 overflow-x-auto">
                {Object.entries(tabLabels).map(([key, label]) => {
                  const iconMap: Record<string, React.ReactNode> = {
                    basic: <Settings className="h-4 w-4 mr-2" />,
                    data: <Database className="h-4 w-4 mr-2" />,
                    trigger: <Zap className="h-4 w-4 mr-2" />,
                    filters: <Filter className="h-4 w-4 mr-2" />,
                    ai: <Bot className="h-4 w-4 mr-2" />,
                    monitor: <Monitor className="h-4 w-4 mr-2" />,
                    risk: <Shield className="h-4 w-4 mr-2" />,
                  }
                  return (
                    <button
                      key={key}
                      onClick={() => setSelectedTab(key)}
                      className={cn(
                        'flex items-center px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                        selectedTab === key
                          ? 'border-emerald-500 text-emerald-600'
                          : 'border-transparent text-muted-foreground hover:text-foreground'
                      )}
                    >
                      {iconMap[key]}
                      {label}
                    </button>
                  )
                })}
              </div>

              {/* Tab Content */}
              <div className="flex-1 overflow-y-auto min-h-[300px] max-h-[500px]">
                <form onSubmit={handleCreate} className="space-y-4">
                  {/* Basic Tab */}
                  {selectedTab === 'basic' && (
                    <div className="space-y-4">
                      {/* 策略模板选择 */}
                      <div className="space-y-2">
                        <Label>策略模板</Label>
                        <Select
                          value={config.template || 'generic'}
                          onValueChange={(value) => {
                            const templates = {
                              generic: () => ({
                                filters: DEFAULT_FILTERS,
                                trigger: DEFAULT_TRIGGER,
                              }),
                              tail: () => ({
                                filters: TAIL_FILTERS,
                                trigger: DEFAULT_TRIGGER,
                              }),
                              sports: () => ({
                                filters: SPORTS_FILTERS,
                                trigger: SPORTS_TRIGGER,
                              }),
                            }
                            const template = templates[value as keyof typeof templates]()
                            setConfig((prev: any) => ({
                              ...prev,
                              template: value,
                              filters: template.filters,
                              trigger: template.trigger,
                            }))
                          }}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="选择策略模板" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="generic">
                              <div>
                                <div className="font-medium">通用策略</div>
                                <div className="text-xs text-muted-foreground">适用于大多数市场</div>
                              </div>
                            </SelectItem>
                            <SelectItem value="tail">
                              <div>
                                <div className="font-medium">尾盘策略</div>
                                <div className="text-xs text-muted-foreground">到期前 2 小时，高概率</div>
                              </div>
                            </SelectItem>
                            <SelectItem value="sports">
                              <div>
                                <div className="font-medium">Sports 策略</div>
                                <div className="text-xs text-muted-foreground">体育赛事，监控比分</div>
                              </div>
                            </SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <Separator />

                      <div className="space-y-2">
                        <Label htmlFor="name">策略名称</Label>
                        <Input
                          id="name"
                          placeholder="我的策略"
                          value={newStrategy.name}
                          onChange={(e) =>
                            setNewStrategy((prev) => ({ ...prev, name: e.target.value }))
                          }
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="description">描述（可选）</Label>
                        <Input
                          id="description"
                          placeholder="描述"
                          value={newStrategy.description}
                          onChange={(e) =>
                            setNewStrategy((prev) => ({
                              ...prev,
                              description: e.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="portfolio_id">投资组合</Label>
                        <select
                          id="portfolio_id"
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                          value={newStrategy.portfolio_id || ''}
                          onChange={(e) =>
                            setNewStrategy((prev) => ({ ...prev, portfolio_id: e.target.value }))
                          }
                        >
                          <option value="">选择投资组合...</option>
                          {portfolios.map((p: any) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="min_order_size">最小下单金额</Label>
                          <Input
                            id="min_order_size"
                            type="number"
                            placeholder="10"
                            value={newStrategy.min_order_size}
                            onChange={(e) =>
                              setNewStrategy((prev) => ({
                                ...prev,
                                min_order_size: Number(e.target.value),
                              }))
                            }
                            required
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="max_order_size">最大下单金额</Label>
                          <Input
                            id="max_order_size"
                            type="number"
                            placeholder="100"
                            value={newStrategy.max_order_size}
                            onChange={(e) =>
                              setNewStrategy((prev) => ({
                                ...prev,
                                max_order_size: Number(e.target.value),
                              }))
                            }
                            required
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Data Sources Tab */}
                  {selectedTab === 'data' && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>市场数据</Label>
                          <p className="text-sm text-muted-foreground">启用价格和交易量数据</p>
                        </div>
                        <Switch
                          checked={config.data_sources.enable_market_data}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              data_sources: { ...prev.data_sources, enable_market_data: checked },
                            }))
                          }
                        />
                      </div>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>Activity 流向</Label>
                          <p className="text-sm text-muted-foreground">启用资金流向数据</p>
                        </div>
                        <Switch
                          checked={config.data_sources.enable_activity}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              data_sources: { ...prev.data_sources, enable_activity: checked },
                            }))
                          }
                        />
                      </div>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>体育比分</Label>
                          <p className="text-sm text-muted-foreground">启用体育赛事比分数据</p>
                        </div>
                        <Switch
                          checked={config.data_sources.enable_sports_score}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              data_sources: { ...prev.data_sources, enable_sports_score: checked },
                            }))
                          }
                        />
                      </div>
                    </div>
                  )}

                  {/* Trigger Tab */}
                  {selectedTab === 'trigger' && (
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="price_change_threshold">价格变动阈值 (%)</Label>
                        <Input
                          id="price_change_threshold"
                          type="number"
                          step="0.1"
                          value={config.trigger.price_change_threshold}
                          onChange={(e) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              trigger: { ...prev.trigger, price_change_threshold: Number(e.target.value) },
                            }))
                          }
                        />
                        <p className="text-xs text-muted-foreground">价格变动超过此阈值时触发扫描</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="activity_netflow_threshold">Activity 净流入阈值</Label>
                        <Input
                          id="activity_netflow_threshold"
                          type="number"
                          value={config.trigger.activity_netflow_threshold}
                          onChange={(e) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              trigger: { ...prev.trigger, activity_netflow_threshold: Number(e.target.value) },
                            }))
                          }
                        />
                        <p className="text-xs text-muted-foreground">净流入超过此阈值时触发</p>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="min_trigger_interval">最小触发间隔 (分钟)</Label>
                          <Input
                            id="min_trigger_interval"
                            type="number"
                            value={config.trigger.min_trigger_interval}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                trigger: { ...prev.trigger, min_trigger_interval: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="scan_interval">扫描间隔 (秒)</Label>
                          <Input
                            id="scan_interval"
                            type="number"
                            value={config.trigger.scan_interval}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                trigger: { ...prev.trigger, scan_interval: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Filters Tab */}
                  {selectedTab === 'filters' && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="min_confidence">最小置信度</Label>
                          <Input
                            id="min_confidence"
                            type="number"
                            min="0"
                            max="100"
                            value={config.filters.min_confidence}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, min_confidence: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="max_spread">最大价差 (%)</Label>
                          <Input
                            id="max_spread"
                            type="number"
                            step="0.1"
                            value={config.filters.max_spread}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, max_spread: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="min_price">最小价格</Label>
                          <Input
                            id="min_price"
                            type="number"
                            step="0.01"
                            value={config.filters.min_price}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, min_price: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="max_price">最大价格</Label>
                          <Input
                            id="max_price"
                            type="number"
                            step="0.01"
                            value={config.filters.max_price}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, max_price: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                      <Separator />
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <Label htmlFor="dead_zone_enabled">死区过滤</Label>
                          <Switch
                            id="dead_zone_enabled"
                            checked={config.filters.dead_zone_enabled}
                            onCheckedChange={(checked) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, dead_zone_enabled: checked },
                              }))
                            }
                          />
                        </div>
                        {config.filters.dead_zone_enabled && (
                          <div className="grid grid-cols-2 gap-4 mt-2">
                            <div className="space-y-2">
                              <Label htmlFor="dead_zone_min">死区最小值</Label>
                              <Input
                                id="dead_zone_min"
                                type="number"
                                step="0.01"
                                value={config.filters.dead_zone_min}
                                onChange={(e) =>
                                  setConfig((prev: any) => ({
                                    ...prev,
                                    filters: { ...prev.filters, dead_zone_min: Number(e.target.value) },
                                  }))
                                }
                              />
                            </div>
                            <div className="space-y-2">
                              <Label htmlFor="dead_zone_max">死区最大值</Label>
                              <Input
                                id="dead_zone_max"
                                type="number"
                                step="0.01"
                                value={config.filters.dead_zone_max}
                                onChange={(e) =>
                                  setConfig((prev: any) => ({
                                    ...prev,
                                    filters: { ...prev.filters, dead_zone_max: Number(e.target.value) },
                                  }))
                                }
                              />
                            </div>
                          </div>
                        )}
                      </div>
                      <Separator />
                      <div className="space-y-2">
                        <Label className="font-medium">到期时间策略</Label>
                        <p className="text-xs text-muted-foreground">由 ExpiryPolicy 统一处理，SignalFilter 不再拦截时间</p>
                      </div>
                      <div className="grid grid-cols-3 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="min_hours_to_expiry">最小到期时间 (小时)</Label>
                          <Input
                            id="min_hours_to_expiry"
                            type="number"
                            step="0.5"
                            value={config.filters.min_hours_to_expiry}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, min_hours_to_expiry: Number(e.target.value) },
                              }))
                            }
                          />
                          <p className="text-xs text-muted-foreground">避免太早入场</p>
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="max_days_to_expiry">最大到期时间 (天)</Label>
                          <Input
                            id="max_days_to_expiry"
                            type="number"
                            step="0.5"
                            value={config.filters.max_days_to_expiry}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, max_days_to_expiry: Number(e.target.value) },
                              }))
                            }
                          />
                          <p className="text-xs text-muted-foreground">避免资金锁死</p>
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="avoid_last_minutes_before_expiry">结算前规避 (分钟)</Label>
                          <Input
                            id="avoid_last_minutes_before_expiry"
                            type="number"
                            step="5"
                            value={config.filters.avoid_last_minutes_before_expiry}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, avoid_last_minutes_before_expiry: Number(e.target.value) },
                              }))
                            }
                          />
                          <p className="text-xs text-muted-foreground">临近结算不交易</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* AI Config Tab */}
                  {selectedTab === 'ai' && (
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="provider_id">AI Provider</Label>
                        <select
                          id="provider_id"
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                          value={newStrategy.provider_id || ''}
                          onChange={(e) =>
                            setNewStrategy((prev) => ({ ...prev, provider_id: e.target.value }))
                          }
                        >
                          <option value="">选择 Provider...</option>
                          {providers.map((provider: any) => (
                            <option key={provider.id} value={provider.id}>
                              {provider.name} ({provider.provider_type || provider.provider})
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="system_prompt">System Prompt</Label>
                        <textarea
                          id="system_prompt"
                          className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                          value={config.system_prompt}
                          onChange={(e) =>
                            setConfig((prev: any) => ({ ...prev, system_prompt: e.target.value }))
                          }
                          placeholder="输入系统提示词..."
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="custom_prompt">Custom Prompt 模板</Label>
                        <textarea
                          id="custom_prompt"
                          className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                          value={config.custom_prompt}
                          onChange={(e) =>
                            setConfig((prev: any) => ({ ...prev, custom_prompt: e.target.value }))
                          }
                          placeholder="输入自定义提示词模板..."
                        />
                        <p className="text-xs text-muted-foreground">
                          可用变量: {'{price}'}, {'{change}'}, {'{netflow}'}, {'{free_text}'}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Monitor Tab */}
                  {selectedTab === 'monitor' && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>止损</Label>
                          <p className="text-sm text-muted-foreground">启用自动止损</p>
                        </div>
                        <Switch
                          checked={config.position_monitor.enable_stop_loss}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              position_monitor: { ...prev.position_monitor, enable_stop_loss: checked },
                            }))
                          }
                        />
                      </div>
                      {config.position_monitor.enable_stop_loss && (
                        <div className="pl-4 space-y-2">
                          <Label htmlFor="stop_loss_percent">止损比例 (%)</Label>
                          <Input
                            id="stop_loss_percent"
                            type="number"
                            step="0.1"
                            value={config.position_monitor.stop_loss_percent}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                position_monitor: { ...prev.position_monitor, stop_loss_percent: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      )}
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>止盈</Label>
                          <p className="text-sm text-muted-foreground">启用自动止盈</p>
                        </div>
                        <Switch
                          checked={config.position_monitor.enable_take_profit}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              position_monitor: { ...prev.position_monitor, enable_take_profit: checked },
                            }))
                          }
                        />
                      </div>
                      {config.position_monitor.enable_take_profit && (
                        <div className="pl-4 space-y-2">
                          <Label htmlFor="take_profit_price">止盈价格</Label>
                          <Input
                            id="take_profit_price"
                            type="number"
                            step="0.001"
                            value={config.position_monitor.take_profit_price}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                position_monitor: { ...prev.position_monitor, take_profit_price: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      )}
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>追踪止损</Label>
                          <p className="text-sm text-muted-foreground">启用追踪止损</p>
                        </div>
                        <Switch
                          checked={config.position_monitor.enable_trailing_stop}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              position_monitor: { ...prev.position_monitor, enable_trailing_stop: checked },
                            }))
                          }
                        />
                      </div>
                      {config.position_monitor.enable_trailing_stop && (
                        <div className="pl-4 space-y-2">
                          <Label htmlFor="trailing_stop_percent">追踪止损比例 (%)</Label>
                          <Input
                            id="trailing_stop_percent"
                            type="number"
                            step="0.1"
                            value={config.position_monitor.trailing_stop_percent}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                position_monitor: { ...prev.position_monitor, trailing_stop_percent: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      )}
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>自动赎回</Label>
                          <p className="text-sm text-muted-foreground">事件结束后自动赎回</p>
                        </div>
                        <Switch
                          checked={config.position_monitor.enable_auto_redeem}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              position_monitor: { ...prev.position_monitor, enable_auto_redeem: checked },
                            }))
                          }
                        />
                      </div>
                    </div>
                  )}

                  {/* Risk Tab */}
                  {selectedTab === 'risk' && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="max_positions">最大持仓数</Label>
                          <Input
                            id="max_positions"
                            type="number"
                            value={config.risk.max_positions}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                risk: { ...prev.risk, max_positions: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="min_risk_reward_ratio">最小盈亏比</Label>
                          <Input
                            id="min_risk_reward_ratio"
                            type="number"
                            step="0.1"
                            value={config.risk.min_risk_reward_ratio}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                risk: { ...prev.risk, min_risk_reward_ratio: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="max_margin_usage">最大保证金使用率</Label>
                          <Input
                            id="max_margin_usage"
                            type="number"
                            step="0.01"
                            max="1"
                            value={config.risk.max_margin_usage}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                risk: { ...prev.risk, max_margin_usage: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="min_position_size">最小持仓金额</Label>
                          <Input
                            id="min_position_size"
                            type="number"
                            value={config.risk.min_position_size}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                risk: { ...prev.risk, min_position_size: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </form>
              </div>

              {/* Dialog Footer */}
              <DialogFooter className="mt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setIsCreateDialogOpen(false)
                    resetForm()
                  }}
                >
                  取消
                </Button>
                <Button type="submit" isLoading={createMutation.isPending} onClick={handleCreate}>
                  创建
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* Edit Dialog */}
          <Dialog
            open={isEditDialogOpen}
            onOpenChange={(open) => {
              setIsEditDialogOpen(open)
              if (!open) {
                setSelectedStrategy(null)
                resetForm()
              }
            }}
          >
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
              <DialogHeader>
                <DialogTitle>编辑策略</DialogTitle>
                <DialogDescription>
                  修改策略配置
                </DialogDescription>
              </DialogHeader>

              {/* Tab Navigation */}
              <div className="flex border-b mb-4 overflow-x-auto">
                {Object.entries(tabLabels).map(([key, label]) => {
                  const iconMap: Record<string, React.ReactNode> = {
                    basic: <Settings className="h-4 w-4 mr-2" />,
                    data: <Database className="h-4 w-4 mr-2" />,
                    trigger: <Zap className="h-4 w-4 mr-2" />,
                    filters: <Filter className="h-4 w-4 mr-2" />,
                    ai: <Bot className="h-4 w-4 mr-2" />,
                    monitor: <Monitor className="h-4 w-4 mr-2" />,
                    risk: <Shield className="h-4 w-4 mr-2" />,
                  }
                  return (
                    <button
                      key={key}
                      onClick={() => setSelectedTab(key)}
                      className={cn(
                        'flex items-center px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                        selectedTab === key
                          ? 'border-emerald-500 text-emerald-600'
                          : 'border-transparent text-muted-foreground hover:text-foreground'
                      )}
                    >
                      {iconMap[key]}
                      {label}
                    </button>
                  )
                })}
              </div>

              {/* Tab Content */}
              <div className="flex-1 overflow-y-auto min-h-[300px] max-h-[500px]">
                <form onSubmit={handleUpdate} className="space-y-4">
                  {/* Basic Tab */}
                  {selectedTab === 'basic' && (
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="edit-name">策略名称</Label>
                        <Input
                          id="edit-name"
                          placeholder="我的策略"
                          value={newStrategy.name}
                          onChange={(e) =>
                            setNewStrategy((prev) => ({ ...prev, name: e.target.value }))
                          }
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="edit-description">描述（可选）</Label>
                        <Input
                          id="edit-description"
                          placeholder="描述"
                          value={newStrategy.description}
                          onChange={(e) =>
                            setNewStrategy((prev) => ({
                              ...prev,
                              description: e.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="edit-portfolio_id">投资组合</Label>
                        <select
                          id="edit-portfolio_id"
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                          value={newStrategy.portfolio_id || ''}
                          onChange={(e) =>
                            setNewStrategy((prev) => ({ ...prev, portfolio_id: e.target.value }))
                          }
                        >
                          <option value="">选择投资组合...</option>
                          {portfolios.map((p: any) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="edit-min_order_size">最小下单金额</Label>
                          <Input
                            id="edit-min_order_size"
                            type="number"
                            placeholder="10"
                            value={newStrategy.min_order_size}
                            onChange={(e) =>
                              setNewStrategy((prev) => ({
                                ...prev,
                                min_order_size: Number(e.target.value),
                              }))
                            }
                            required
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="edit-max_order_size">最大下单金额</Label>
                          <Input
                            id="edit-max_order_size"
                            type="number"
                            placeholder="100"
                            value={newStrategy.max_order_size}
                            onChange={(e) =>
                              setNewStrategy((prev) => ({
                                ...prev,
                                max_order_size: Number(e.target.value),
                              }))
                            }
                            required
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Data Sources Tab - reuse same content as create */}
                  {selectedTab === 'data' && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>市场数据</Label>
                          <p className="text-xs text-muted-foreground">实时价格监控</p>
                        </div>
                        <Switch
                          checked={config.data_sources.enable_market_data}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              data_sources: { ...prev.data_sources, enable_market_data: checked },
                            }))
                          }
                        />
                      </div>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>Activity 流入</Label>
                          <p className="text-xs text-muted-foreground">交易活动监控</p>
                        </div>
                        <Switch
                          checked={config.data_sources.enable_activity}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              data_sources: { ...prev.data_sources, enable_activity: checked },
                            }))
                          }
                        />
                      </div>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>Sports 比分</Label>
                          <p className="text-xs text-muted-foreground">体育赛事比分监控</p>
                        </div>
                        <Switch
                          checked={config.data_sources.enable_sports_score}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              data_sources: { ...prev.data_sources, enable_sports_score: checked },
                            }))
                          }
                        />
                      </div>
                    </div>
                  )}

                  {/* Trigger Tab */}
                  {selectedTab === 'trigger' && (
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="edit-price_change_threshold">价格变动阈值 (%)</Label>
                        <Input
                          id="edit-price_change_threshold"
                          type="number"
                          step="0.1"
                          value={config.trigger.price_change_threshold}
                          onChange={(e) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              trigger: { ...prev.trigger, price_change_threshold: Number(e.target.value) },
                            }))
                          }
                        />
                        <p className="text-xs text-muted-foreground">价格变动超过此阈值时触发扫描</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="edit-activity_netflow_threshold">Activity 净流入阈值</Label>
                        <Input
                          id="edit-activity_netflow_threshold"
                          type="number"
                          value={config.trigger.activity_netflow_threshold}
                          onChange={(e) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              trigger: { ...prev.trigger, activity_netflow_threshold: Number(e.target.value) },
                            }))
                          }
                        />
                        <p className="text-xs text-muted-foreground">净流入超过此阈值时触发</p>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="edit-min_trigger_interval">最小触发间隔 (分钟)</Label>
                          <Input
                            id="edit-min_trigger_interval"
                            type="number"
                            value={config.trigger.min_trigger_interval}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                trigger: { ...prev.trigger, min_trigger_interval: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="edit-scan_interval">扫描间隔 (秒)</Label>
                          <Input
                            id="edit-scan_interval"
                            type="number"
                            value={config.trigger.scan_interval}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                trigger: { ...prev.trigger, scan_interval: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Filters Tab */}
                  {selectedTab === 'filters' && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="edit-min_confidence">最小置信度</Label>
                          <Input
                            id="edit-min_confidence"
                            type="number"
                            min="0"
                            max="100"
                            value={config.filters.min_confidence}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, min_confidence: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="edit-max_spread">最大价差 (%)</Label>
                          <Input
                            id="edit-max_spread"
                            type="number"
                            step="0.1"
                            value={config.filters.max_spread}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, max_spread: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="edit-min_price">最小价格</Label>
                          <Input
                            id="edit-min_price"
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            value={config.filters.min_price}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, min_price: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="edit-max_price">最大价格</Label>
                          <Input
                            id="edit-max_price"
                            type="number"
                            step="0.01"
                            min="0"
                            max="1"
                            value={config.filters.max_price}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, max_price: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>死区过滤</Label>
                          <p className="text-xs text-muted-foreground">0.60-0.85 价格区间不交易</p>
                        </div>
                        <Switch
                          checked={config.filters.dead_zone_enabled}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              filters: { ...prev.filters, dead_zone_enabled: checked },
                            }))
                          }
                        />
                      </div>
                      {config.filters.dead_zone_enabled && (
                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <Label htmlFor="edit-dead_zone_min">死区最小值</Label>
                            <Input
                              id="edit-dead_zone_min"
                              type="number"
                              step="0.01"
                              min="0"
                              max="1"
                              value={config.filters.dead_zone_min}
                              onChange={(e) =>
                                setConfig((prev: any) => ({
                                  ...prev,
                                  filters: { ...prev.filters, dead_zone_min: Number(e.target.value) },
                                }))
                              }
                            />
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="edit-dead_zone_max">死区最大值</Label>
                            <Input
                              id="edit-dead_zone_max"
                              type="number"
                              step="0.01"
                              min="0"
                              max="1"
                              value={config.filters.dead_zone_max}
                              onChange={(e) =>
                                setConfig((prev: any) => ({
                                  ...prev,
                                  filters: { ...prev.filters, dead_zone_max: Number(e.target.value) },
                                }))
                              }
                            />
                          </div>
                        </div>
                      )}
                      <Separator />
                      <div className="space-y-2">
                        <Label className="font-medium">到期时间策略</Label>
                        <p className="text-xs text-muted-foreground">由 ExpiryPolicy 统一处理，SignalFilter 不再拦截时间</p>
                      </div>
                      <div className="grid grid-cols-3 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="edit-min_hours_to_expiry">最小到期时间 (小时)</Label>
                          <Input
                            id="edit-min_hours_to_expiry"
                            type="number"
                            step="0.5"
                            value={config.filters.min_hours_to_expiry}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, min_hours_to_expiry: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="edit-max_days_to_expiry">最大到期时间 (天)</Label>
                          <Input
                            id="edit-max_days_to_expiry"
                            type="number"
                            step="0.5"
                            value={config.filters.max_days_to_expiry}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, max_days_to_expiry: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="edit-avoid_last_minutes_before_expiry">结算前规避 (分钟)</Label>
                          <Input
                            id="edit-avoid_last_minutes_before_expiry"
                            type="number"
                            step="5"
                            value={config.filters.avoid_last_minutes_before_expiry}
                            onChange={(e) =>
                              setConfig((prev: any) => ({
                                ...prev,
                                filters: { ...prev.filters, avoid_last_minutes_before_expiry: Number(e.target.value) },
                              }))
                            }
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* AI Tab */}
                  {selectedTab === 'ai' && (
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="edit-provider_id">AI Provider</Label>
                        <select
                          id="edit-provider_id"
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                          value={newStrategy.provider_id || ''}
                          onChange={(e) =>
                            setNewStrategy((prev) => ({ ...prev, provider_id: e.target.value }))
                          }
                        >
                          <option value="">选择 Provider...</option>
                          {providers.map((provider: any) => (
                            <option key={provider.id} value={provider.id}>
                              {provider.name} ({provider.provider_type || provider.provider})
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="edit-system_prompt">System Prompt</Label>
                        <textarea
                          id="edit-system_prompt"
                          className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                          placeholder="输入 System Prompt..."
                          value={config.system_prompt}
                          onChange={(e) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              system_prompt: e.target.value,
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="edit-custom_prompt">Custom Prompt 模板</Label>
                        <textarea
                          id="edit-custom_prompt"
                          className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                          placeholder="输入自定义提示词模板..."
                          value={config.custom_prompt}
                          onChange={(e) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              custom_prompt: e.target.value,
                            }))
                          }
                        />
                      </div>
                    </div>
                  )}

                  {/* Monitor Tab */}
                  {selectedTab === 'monitor' && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>止损</Label>
                          <p className="text-xs text-muted-foreground">亏损达到百分比自动平仓</p>
                        </div>
                        <Switch
                          checked={config.position_monitor.enable_stop_loss}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              position_monitor: { ...prev.position_monitor, enable_stop_loss: checked },
                            }))
                          }
                        />
                      </div>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>止盈</Label>
                          <p className="text-xs text-muted-foreground">达到目标价格自动平仓</p>
                        </div>
                        <Switch
                          checked={config.position_monitor.enable_take_profit}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              position_monitor: { ...prev.position_monitor, enable_take_profit: checked },
                            }))
                          }
                        />
                      </div>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>追踪止损</Label>
                          <p className="text-xs text-muted-foreground">随价格移动调整止损</p>
                        </div>
                        <Switch
                          checked={config.position_monitor.enable_trailing_stop}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              position_monitor: { ...prev.position_monitor, enable_trailing_stop: checked },
                            }))
                          }
                        />
                      </div>
                      <Separator />
                      <div className="flex items-center justify-between">
                        <div>
                          <Label>自动赎回</Label>
                          <p className="text-xs text-muted-foreground">市场到期自动赎回</p>
                        </div>
                        <Switch
                          checked={config.position_monitor.enable_auto_redeem}
                          onCheckedChange={(checked) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              position_monitor: { ...prev.position_monitor, enable_auto_redeem: checked },
                            }))
                          }
                        />
                      </div>
                    </div>
                  )}

                  {/* Risk Tab */}
                  {selectedTab === 'risk' && (
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="edit-max_positions">最大持仓数</Label>
                        <Input
                          id="edit-max_positions"
                          type="number"
                          value={config.risk.max_positions}
                          onChange={(e) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              risk: { ...prev.risk, max_positions: Number(e.target.value) },
                            }))
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="edit-min_risk_reward_ratio">最小盈亏比</Label>
                        <Input
                          id="edit-min_risk_reward_ratio"
                          type="number"
                          step="0.1"
                          value={config.risk.min_risk_reward_ratio}
                          onChange={(e) =>
                            setConfig((prev: any) => ({
                              ...prev,
                              risk: { ...prev.risk, min_risk_reward_ratio: Number(e.target.value) },
                            }))
                          }
                        />
                      </div>
                    </div>
                  )}
                </form>
              </div>

              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setIsEditDialogOpen(false)
                    setSelectedStrategy(null)
                    resetForm()
                  }}
                >
                  取消
                </Button>
                <Button type="submit" isLoading={updateMutation.isPending} onClick={handleUpdate}>
                  保存
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

      {/* Strategies Grid */}
      {strategies && strategies.length > 0 ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {strategies.map((strategy) => (
            <StrategyCard
              key={strategy.id}
              strategy={strategy}
              onDelete={(id) => deleteMutation.mutate(id)}
              onStart={(id) => startMutation.mutate(id)}
              onStop={(id) => stopMutation.mutate(id)}
              onEdit={handleEdit}
              isLoading={startMutation.isPending || stopMutation.isPending || deleteMutation.isPending || updateMutation.isPending}
              portfolios={portfolios}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              <Brain className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-lg font-semibold">暂无策略</h3>
            <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
              创建您的第一个自动化交易策略来开始
            </p>
            <Button
              className="mt-6"
              onClick={() => setIsCreateDialogOpen(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              创建策略
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
