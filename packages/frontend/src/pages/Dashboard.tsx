import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  BarChart3,
  Activity,
  ListOrdered,
} from 'lucide-react'
import { portfoliosApi, positionsApi, ordersApi } from '@/lib/api'
import {
  formatCurrency,
  formatNumber,
  cn,
} from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { LoadingScreen } from '@/components/ui/LoadingScreen'

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ElementType
  isLoading?: boolean
}

function StatCard({
  title,
  value,
  icon: Icon,
  isLoading,
}: StatCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-8 w-24 animate-pulse rounded bg-void-200" />
        ) : (
          <div className="text-2xl font-bold font-mono">{value}</div>
        )}
      </CardContent>
    </Card>
  )
}

function RecentActivity() {
  const { data: ordersResponse, isLoading: ordersLoading } = useQuery({
    queryKey: ['orders'],
    queryFn: () => ordersApi.getAll({ limit: 10 }),
  })

  const { data: positionsResponse, isLoading: positionsLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: () => positionsApi.getAll(),
  })

  const isLoading = ordersLoading || positionsLoading

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="h-8 w-8 animate-pulse rounded-full bg-void-200" />
            <div className="flex-1 space-y-1">
              <div className="h-4 w-32 animate-pulse rounded bg-void-200" />
              <div className="h-3 w-20 animate-pulse rounded bg-void-200" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  const orders = ordersResponse?.items || []
  const positions = positionsResponse?.items || []

  // Combine and sort by date
  const activities: Array<{
    id: string
    type: 'order' | 'position'
    description: string
    timestamp: string
    side: string
    status: string
  }> = []

  orders.forEach((order) => {
    activities.push({
      id: `order-${order.id}`,
      type: 'order',
      description: `${order.side.toUpperCase()} ${order.size} ${order.symbol}`,
      timestamp: order.created_at,
      side: order.side,
      status: order.status,
    })
  })

  positions.forEach((pos) => {
    activities.push({
      id: `position-${pos.id}`,
      type: 'position',
      description: `${pos.side.toUpperCase()} ${pos.size} ${pos.symbol}`,
      timestamp: pos.opened_at,
      side: pos.side,
      status: pos.status,
    })
  })

  // Sort by timestamp desc
  activities.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

  if (activities.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-void-200">
          <ListOrdered className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="mt-4 text-lg font-semibold">暂无活动</h3>
        <p className="mt-2 max-w-sm text-sm text-muted-foreground">
          开始在 Polymarket 交易后将在此显示您的活动
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {activities.slice(0, 10).map((activity) => (
        <div
          key={activity.id}
          className="flex items-center gap-3 rounded-lg border border-void-300 bg-void-100 p-3"
        >
          <div
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-full',
              activity.type === 'order' ? 'bg-blue-500/10 text-blue-500' : 'bg-emerald-500/10 text-emerald-500'
            )}
          >
            {activity.type === 'order' ? (
              <BarChart3 className="h-4 w-4" />
            ) : (
              <TrendingUp className="h-4 w-4" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{activity.description}</p>
            <p className="text-xs text-muted-foreground">
              {new Date(activity.timestamp).toLocaleString()}
            </p>
          </div>
          <div className="text-xs text-muted-foreground capitalize">
            {activity.status}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const { data: portfoliosResponse, isLoading: portfoliosLoading } = useQuery({
    queryKey: ['portfolios'],
    queryFn: () => portfoliosApi.getAll(),
  })

  const { data: positionsResponse, isLoading: positionsLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: () => positionsApi.getAll(),
  })

  const { data: ordersResponse, isLoading: ordersLoading } = useQuery({
    queryKey: ['orders'],
    queryFn: () => ordersApi.getAll({ limit: 100 }),
  })

  const isLoading = portfoliosLoading || positionsLoading || ordersLoading

  const portfolios = portfoliosResponse?.items || []
  const positions = positionsResponse?.items || []
  const orders = ordersResponse?.items || []

  // Calculate real stats from API data
  const totalValue = portfolios.reduce((sum, p) => sum + Number(p.current_balance), 0)
  const totalPnl = portfolios.reduce((sum, p) => sum + Number(p.total_pnl), 0)
  const activePositions = positions.filter(p => p.status === 'open').length
  const pendingOrders = orders.filter(o => o.status === 'pending' || o.status === 'open').length

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          欢迎回来！这是您的 Polymarket 交易概览。
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="组合总价值"
          value={formatCurrency(totalValue)}
          icon={DollarSign}
          isLoading={portfoliosLoading}
        />
        <StatCard
          title="总盈亏"
          value={formatCurrency(totalPnl)}
          icon={totalPnl >= 0 ? TrendingUp : TrendingDown}
          isLoading={portfoliosLoading}
        />
        <StatCard
          title="持仓数量"
          value={formatNumber(activePositions)}
          icon={Activity}
          isLoading={positionsLoading}
        />
        <StatCard
          title="待处理订单"
          value={formatNumber(pendingOrders)}
          icon={BarChart3}
          isLoading={ordersLoading}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Portfolio Performance */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>组合表现</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] flex items-center justify-center text-muted-foreground">
              {portfolios.length === 0
                ? 'Create a portfolio to start trading on Polymarket'
                : 'Chart coming soon'}
            </div>
          </CardContent>
        </Card>

        {/* Portfolios Summary */}
        <Card>
          <CardHeader>
            <CardTitle>投资组合</CardTitle>
          </CardHeader>
          <CardContent>
            {portfolios.length === 0 ? (
              <div className="flex items-center justify-center h-[200px] text-muted-foreground text-sm text-center">
                No portfolios yet
              </div>
            ) : (
              <div className="space-y-3">
                {portfolios.map((portfolio) => (
                  <div key={portfolio.id} className="flex items-center justify-between p-2 rounded border">
                    <span className="font-medium">{portfolio.name}</span>
                    <span className={cn('font-mono', Number(portfolio.total_pnl) >= 0 ? 'text-emerald-500' : 'text-red-500')}>
                      {formatCurrency(Number(portfolio.total_pnl))}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>最近活动</CardTitle>
        </CardHeader>
        <CardContent>
          <RecentActivity />
        </CardContent>
      </Card>
    </div>
  )
}