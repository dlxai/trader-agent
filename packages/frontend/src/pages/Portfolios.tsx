import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  TrendingUp,
  TrendingDown,
  DollarSign,
  PieChart,
  Trash2,
  Edit,
  Briefcase,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { portfoliosApi, type PortfolioSummary } from '@/lib/api'
import {
  formatCurrency,
  formatPercentage,
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

function PortfolioCard({ portfolio, onDelete }: { portfolio: PortfolioSummary; onDelete: (id: string) => void }) {
  const pnlIsPositive = Number(portfolio.total_pnl) >= 0

  return (
    <Card className="group transition-all hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/5">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-lg">{portfolio.name}</CardTitle>
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
              onClick={() => onDelete(portfolio.id)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Total Value */}
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-muted-foreground">总价值</span>
          <span className="text-2xl font-bold font-mono">
            {formatCurrency(Number(portfolio.current_balance))}
          </span>
        </div>

        {/* P&L */}
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded',
                getPnlBgColor(Number(portfolio.total_pnl))
              )}
            >
              {pnlIsPositive ? (
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              ) : (
                <TrendingDown className="h-4 w-4 text-red-500" />
              )}
            </div>
            <div>
              <p className="text-sm font-medium">未实现盈亏</p>
              <p className="text-xs text-muted-foreground">
                {formatPercentage(Number(portfolio.total_pnl_percent))}
              </p>
            </div>
          </div>
          <span
            className={cn(
              'font-mono font-medium',
              getPnlColor(Number(portfolio.total_pnl))
            )}
          >
            {formatCurrency(Number(portfolio.total_pnl))}
          </span>
        </div>

        {/* Quick Actions */}
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="flex-1">
            <PieChart className="mr-2 h-4 w-4" />
            详情
          </Button>
          <Button variant="outline" size="sm" className="flex-1">
            <DollarSign className="mr-2 h-4 w-4" />
            交易
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function PortfoliosPage() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [newPortfolio, setNewPortfolio] = useState({ name: '', description: '' })
  const queryClient = useQueryClient()

  const { data: portfoliosResponse, isLoading } = useQuery({
    queryKey: ['portfolios'],
    queryFn: () => portfoliosApi.getAll(),
  })

  const portfolios = portfoliosResponse?.items || []

  const createMutation = useMutation({
    mutationFn: (data: { name: string; description?: string }) =>
      portfoliosApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
      setIsCreateDialogOpen(false)
      setNewPortfolio({ name: '', description: '' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => portfoliosApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['portfolios'] })
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate(newPortfolio)
  }

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">投资组合</h1>
          <p className="text-muted-foreground">
            管理您的投资组合并跟踪表现
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              新建组合
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>创建新投资组合</DialogTitle>
              <DialogDescription>
                创建新的投资组合来跟踪您的投资
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate}>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name">组合名称</Label>
                  <Input
                    id="name"
                    placeholder="我的组合"
                    value={newPortfolio.name}
                    onChange={(e) =>
                      setNewPortfolio((prev) => ({ ...prev, name: e.target.value }))
                    }
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">描述（可选）</Label>
                  <Input
                    id="description"
                    placeholder="描述"
                    value={newPortfolio.description}
                    onChange={(e) =>
                      setNewPortfolio((prev) => ({
                        ...prev,
                        description: e.target.value,
                      }))
                    }
                  />
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

      {/* Portfolios Grid */}
      {portfolios && portfolios.length > 0 ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {portfolios.map((portfolio) => (
            <PortfolioCard
              key={portfolio.id}
              portfolio={portfolio}
              onDelete={(id) => deleteMutation.mutate(id)}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              <Briefcase className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-lg font-semibold">暂无投资组合</h3>
            <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
              创建您的第一个投资组合来开始跟踪您的投资
            </p>
            <Button
              className="mt-6"
              onClick={() => setIsCreateDialogOpen(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              创建组合
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
