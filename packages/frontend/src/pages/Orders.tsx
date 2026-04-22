import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search,
  MoreHorizontal,
  CheckCircle2,
  XCircle,
  Clock,
  RotateCcw,
  ListOrdered,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { ordersApi } from '@/lib/api'
import {
  formatCurrency,
  formatNumber,
  formatDate,
  formatPercentage,
  cn,
} from '@/lib/utils'

const statusConfig: Record<string, { label: string; variant: 'warning' | 'info' | 'success' | 'secondary' | 'error'; icon: React.ElementType }> = {
  pending: { label: 'Pending', variant: 'warning', icon: Clock },
  open: { label: 'Open', variant: 'info', icon: Clock },
  filled: { label: 'Filled', variant: 'success', icon: CheckCircle2 },
  partial: { label: 'Partial', variant: 'warning', icon: Clock },
  cancelled: { label: 'Cancelled', variant: 'secondary', icon: XCircle },
  rejected: { label: 'Rejected', variant: 'error', icon: XCircle },
  expired: { label: 'Expired', variant: 'secondary', icon: XCircle },
}

const typeConfig: Record<string, { label: string; color: string }> = {
  market: { label: 'Market', color: 'text-emerald-500' },
  limit: { label: 'Limit', color: 'text-blue-500' },
  stop: { label: 'Stop', color: 'text-yellow-500' },
  stop_limit: { label: 'Stop Limit', color: 'text-orange-500' },
}

export default function OrdersPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [sideFilter, setSideFilter] = useState<string>('all')

  const { data: ordersResponse, isLoading, refetch } = useQuery({
    queryKey: ['orders'],
    queryFn: () => ordersApi.getAll({ limit: 100 }),
  })

  const orders = ordersResponse?.items || []

  const filteredOrders = orders.filter((order) => {
    const matchesSearch =
      order.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      order.id.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === 'all' || order.status === statusFilter
    const matchesType = typeFilter === 'all' || order.order_type === typeFilter
    const matchesSide = sideFilter === 'all' || order.side === sideFilter

    return matchesSearch && matchesStatus && matchesType && matchesSide
  })

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">订单</h1>
          <p className="text-muted-foreground">
            查看和管理您的交易订单
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()}>
            <RotateCcw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="按交易对或ID搜索订单..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[130px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="open">Open</SelectItem>
                  <SelectItem value="filled">Filled</SelectItem>
                  <SelectItem value="partial">Partial</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>

              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="w-[130px]">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="market">Market</SelectItem>
                  <SelectItem value="limit">Limit</SelectItem>
                  <SelectItem value="stop">Stop</SelectItem>
                  <SelectItem value="stop_limit">Stop Limit</SelectItem>
                </SelectContent>
              </Select>

              <Select value={sideFilter} onValueChange={setSideFilter}>
                <SelectTrigger className="w-[110px]">
                  <SelectValue placeholder="Side" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Sides</SelectItem>
                  <SelectItem value="buy">Buy</SelectItem>
                  <SelectItem value="sell">Sell</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Orders Table */}
      <Card>
        <CardHeader>
          <CardTitle>Order History</CardTitle>
        </CardHeader>
        <CardContent>
          {filteredOrders && filteredOrders.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Time</TableHead>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Filled</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredOrders.map((order) => {
                  const status = statusConfig[order.status]
                  const type = typeConfig[order.order_type]
                  const StatusIcon = status.icon
                  const fillPercent = Number(order.size) > 0
                    ? (Number(order.filled_size) / Number(order.size)) * 100
                    : 0

                  return (
                    <TableRow key={order.id}>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {order.id.slice(0, 8)}...
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDate(order.created_at, { includeTime: true })}
                      </TableCell>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          <span>{order.symbol}</span>
                          <Badge variant="outline" className="text-2xs">
                            {order.market_id}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className={cn('text-sm font-medium', type.color)}>
                          {type.label}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={order.side === 'buy' ? 'success' : 'error'}
                          className="capitalize"
                        >
                          {order.side}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatNumber(Number(order.size), { maximumFractionDigits: 8 })}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {order.avg_fill_price ? formatCurrency(Number(order.avg_fill_price)) : 'Market'}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="font-mono">
                          {formatNumber(Number(order.filled_size), { maximumFractionDigits: 8 })}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {formatPercentage(fillPercent)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={status.variant} className="gap-1">
                          <StatusIcon className="h-3 w-3" />
                          {status.label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          ) : (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                <ListOrdered className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">No orders found</h3>
              <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
                Try adjusting your filters or place a new order to get started
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
