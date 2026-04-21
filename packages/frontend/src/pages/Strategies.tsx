import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Play,
  Pause,
  Trash2,
  Edit,
  Brain,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { strategiesApi } from '@/lib/api'
import type { StrategySummary } from '@/types'
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
  DialogTrigger,
} from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'

function StrategyCard({ strategy, onDelete, onStart, onStop }: { strategy: StrategySummary; onDelete: (id: string) => void; onStart: (id: string) => void; onStop: (id: string) => void }) {
  const pnlIsPositive = Number(strategy.total_pnl) >= 0

  return (
    <Card className="group transition-all hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/5">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-lg">{strategy.name}</CardTitle>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-0 group-hover:opacity-100"
            >
              <Edit className="h-4 w-4" />
            </Button>
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
            <Button variant="outline" size="sm" className="flex-1" onClick={() => onStop(strategy.id)}>
              <Pause className="mr-2 h-4 w-4" />
              停止
            </Button>
          ) : (
            <Button variant="outline" size="sm" className="flex-1" onClick={() => onStart(strategy.id)}>
              <Play className="mr-2 h-4 w-4" />
              启动
            </Button>
          )}
          <Button variant="outline" size="sm" className="flex-1">
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
  const [newStrategy, setNewStrategy] = useState({ name: '', description: '', min_order_size: 10, max_order_size: 100 })
  const queryClient = useQueryClient()

  const { data: strategiesResponse, isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: () => strategiesApi.getAll(),
  })

  const strategies = strategiesResponse?.items || []

  const createMutation = useMutation({
    mutationFn: (data: any) =>
      strategiesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      setIsCreateDialogOpen(false)
      setNewStrategy({ name: '', description: '', min_order_size: 10, max_order_size: 100 })
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
    },
  })

  const stopMutation = useMutation({
    mutationFn: (id: string) => strategiesApi.stop(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate(newStrategy)
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
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              新建策略
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>创建新策略</DialogTitle>
              <DialogDescription>
                创建新的自动化交易策略
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate}>
              <div className="space-y-4 py-4">
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
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateDialogOpen(false)}
                >
                  取消
                </Button>
                <Button type="submit" isLoading={createMutation.isPending}>
                  创建
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

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
