import { useQuery } from '@tanstack/react-query'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  BarChart3,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { dashboardApi } from '@/lib/api'
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
  cn,
} from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

interface StatCardProps {
  title: string
  value: string | number
  change?: number
  changeLabel?: string
  icon: React.ElementType
  prefix?: string
  suffix?: string
  isLoading?: boolean
}

function StatCard({
  title,
  value,
  change,
  changeLabel,
  icon: Icon,
  isLoading,
}: StatCardProps) {
  const isPositive = change && change > 0
  const isNegative = change && change < 0

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
          <>
            <div className="text-2xl font-bold font-mono">{value}</div>
            {change !== undefined && (
              <div className="mt-1 flex items-center gap-1 text-xs">
                {isPositive ? (
                  <ArrowUpRight className="h-3 w-3 text-emerald-500" />
                ) : isNegative ? (
                  <ArrowDownRight className="h-3 w-3 text-red-500" />
                ) : null}
                <span
                  className={cn(
                    'font-mono',
                    isPositive && 'text-emerald-500',
                    isNegative && 'text-red-500',
                    !isPositive && !isNegative && 'text-muted-foreground'
                  )}
                >
                  {formatPercentage(change)}
                </span>
                {changeLabel && (
                  <span className="text-muted-foreground">{changeLabel}</span>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

function RecentActivity() {
  const { data: activities, isLoading } = useQuery({
    queryKey: ['dashboard', 'activity'],
    queryFn: () => dashboardApi.getRecentActivity(),
  })

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

  return (
    <div className="space-y-3">
      {activities?.map((activity) => (
        <div
          key={activity.id}
          className="flex items-center gap-3 rounded-lg border border-void-300 bg-void-100 p-3"
        >
          <div
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-full',
              activity.type === 'trade' && 'bg-emerald-500/10 text-emerald-500',
              activity.type === 'order' && 'bg-blue-500/10 text-blue-500',
              activity.type === 'deposit' && 'bg-emerald-500/10 text-emerald-500',
              activity.type === 'withdrawal' && 'bg-red-500/10 text-red-500'
            )}
          >
            {activity.type === 'trade' && <TrendingUp className="h-4 w-4" />}
            {activity.type === 'order' && <BarChart3 className="h-4 w-4" />}
            {activity.type === 'deposit' && <TrendingUp className="h-4 w-4" />}
            {activity.type === 'withdrawal' && <TrendingDown className="h-4 w-4" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{activity.description}</p>
            <p className="text-xs text-muted-foreground">
              {new Date(activity.timestamp).toLocaleString()}
            </p>
          </div>
          {activity.amount !== undefined && (
            <div className={cn(
              'text-sm font-mono',
              activity.amount > 0 ? 'text-emerald-500' : 'text-red-500'
            )}>
              {activity.amount > 0 ? '+' : ''}
              {formatCurrency(activity.amount)}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: () => dashboardApi.getStats(),
  })

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Welcome back! Here's an overview of your trading activity.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Portfolio Value"
          value={stats ? formatCurrency(stats.totalValue) : '-'}
          change={stats?.pnlPercentage}
          changeLabel="vs last month"
          icon={DollarSign}
          isLoading={statsLoading}
        />
        <StatCard
          title="Total P&L"
          value={stats ? formatCurrency(stats.totalPnl) : '-'}
          change={stats?.pnlPercentage}
          icon={TrendingUp}
          isLoading={statsLoading}
        />
        <StatCard
          title="Active Positions"
          value={stats ? formatNumber(stats.activePositions) : '-'}
          icon={Activity}
          isLoading={statsLoading}
        />
        <StatCard
          title="Pending Orders"
          value={stats ? formatNumber(stats.pendingOrders) : '-'}
          icon={BarChart3}
          isLoading={statsLoading}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Portfolio Performance */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Portfolio Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[300px] flex items-center justify-center text-muted-foreground">
              Chart placeholder - Portfolio value over time
            </div>
          </CardContent>
        </Card>

        {/* Asset Allocation */}
        <Card>
          <CardHeader>
            <CardTitle>Asset Allocation</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[200px] flex items-center justify-center text-muted-foreground">
              Pie chart placeholder
            </div>
            <div className="mt-4 space-y-2">
              {['BTC', 'ETH', 'SOL', 'Others'].map((asset, i) => (
                <div key={asset} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div
                      className="h-3 w-3 rounded-full"
                      style={{
                        backgroundColor: ['#10b981', '#3b82f6', '#8b5cf6', '#6b7280'][i],
                      }}
                    />
                    <span>{asset}</span>
                  </div>
                  <span className="font-mono text-muted-foreground">
                    {25 - i * 5}%
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Activity */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Recent Activity</CardTitle>
          <Badge variant="outline">Live</Badge>
        </CardHeader>
        <CardContent>
          <RecentActivity />
        </CardContent>
      </Card>
    </div>
  )
}
