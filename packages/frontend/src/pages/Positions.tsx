import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Search,
  ArrowUpDown,
  Plus,
  Briefcase,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { positionsApi } from '@/lib/api'
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
  cn,
  getPnlColor,
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

interface PositionWithPortfolio {
  id: string
  symbol: string
  exchange: string
  side: 'long' | 'short'
  quantity: number
  avgCost: number
  currentPrice: number
  marketValue: number
  unrealizedPnl: number
  pnlPercentage: number
  portfolio: {
    id: string
    name: string
  }
}

export default function PositionsPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<'value' | 'pnl' | 'symbol'>('value')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  const { data: positions, isLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: () => positionsApi.getAll(),
  })

  const filteredPositions = positions?.filter(
    (pos) =>
      pos.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      pos.portfolio.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const sortedPositions = filteredPositions?.sort((a, b) => {
    let comparison = 0
    switch (sortBy) {
      case 'value':
        comparison = a.marketValue - b.marketValue
        break
      case 'pnl':
        comparison = a.unrealizedPnl - b.unrealizedPnl
        break
      case 'symbol':
        comparison = a.symbol.localeCompare(b.symbol)
        break
    }
    return sortOrder === 'asc' ? comparison : -comparison
  })

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Positions</h1>
          <p className="text-muted-foreground">
            View and manage your active trading positions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline">
            <Filter className="mr-2 h-4 w-4" />
            Filter
          </Button>
        </div>
      </div>

      {/* Search and Sort */}
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search positions by symbol or portfolio..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={sortBy === 'value' ? 'default' : 'outline'}
            size="sm"
            onClick={() => {
              if (sortBy === 'value') {
                setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
              } else {
                setSortBy('value')
                setSortOrder('desc')
              }
            }}
          >
            <ArrowUpDown className="mr-2 h-3 w-3" />
            Value
          </Button>
          <Button
            variant={sortBy === 'pnl' ? 'default' : 'outline'}
            size="sm"
            onClick={() => {
              if (sortBy === 'pnl') {
                setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
              } else {
                setSortBy('pnl')
                setSortOrder('desc')
              }
            }}
          >
            <ArrowUpDown className="mr-2 h-3 w-3" />
            P&L
          </Button>
        </div>
      </div>

      {/* Positions Table */}
      <Card>
        <CardHeader>
          <CardTitle>Active Positions</CardTitle>
        </CardHeader>
        <CardContent>
          {sortedPositions && sortedPositions.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Portfolio</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead className="text-right">Quantity</TableHead>
                  <TableHead className="text-right">Avg Cost</TableHead>
                  <TableHead className="text-right">Current</TableHead>
                  <TableHead className="text-right">Market Value</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedPositions.map((position) => {
                  const pnlIsPositive = position.unrealizedPnl >= 0
                  return (
                    <TableRow key={position.id}>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          <span className="text-foreground">{position.symbol}</span>
                          <Badge variant="outline" className="text-2xs">
                            {position.exchange}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {position.portfolio.name}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={position.side === 'long' ? 'success' : 'error'}
                          className="capitalize"
                        >
                          {position.side}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatNumber(position.quantity, { maximumFractionDigits: 8 })}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">
                        {formatCurrency(position.avgCost)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatCurrency(position.currentPrice)}
                      </TableCell>
                      <TableCell className="text-right font-mono font-medium">
                        {formatCurrency(position.marketValue)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className={cn('font-mono', getPnlColor(position.unrealizedPnl))}>
                          {formatCurrency(position.unrealizedPnl)}
                        </div>
                        <div className={cn('text-xs font-mono', getPnlColor(position.pnlPercentage))}>
                          {formatPercentage(position.pnlPercentage)}
                        </div>
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
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-void-200">
                <Briefcase className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">No positions yet</h3>
              <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                Start trading to build your portfolio and track your performance
              </p>
              <Button className="mt-6">
                <Plus className="mr-2 h-4 w-4" />
                Place Order
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

