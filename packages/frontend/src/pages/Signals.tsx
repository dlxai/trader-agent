import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Brain,
  TrendingUp,
  TrendingDown,
  ChevronDown,
  ChevronUp,
  Clock,
  DollarSign,
  Target,
  Activity,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { signalsApi, type SignalLogSummary } from '@/lib/api'
import { formatCurrency, cn, formatDate } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog'

function SignalCard({ signal, onClick }: { signal: SignalLogSummary; onClick: () => void }) {
  const [expanded, setExpanded] = useState(false)

  const isBuy = signal.signal_type === 'buy'
  const confidencePercent = Math.round((signal.confidence || 0) * 100)

  return (
    <Card className="transition-all hover:border-emerald-500/30">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded',
                isBuy ? 'bg-emerald-500/10' : signal.signal_type === 'sell' ? 'bg-red-500/10' : 'bg-gray-500/10'
              )}
            >
              {isBuy ? (
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              ) : signal.signal_type === 'sell' ? (
                <TrendingDown className="h-4 w-4 text-red-500" />
              ) : (
                <Activity className="h-4 w-4 text-gray-500" />
              )}
            </div>
            <div>
              <CardTitle className="text-base">
                {signal.signal_type.toUpperCase()} {signal.side?.toUpperCase()}
              </CardTitle>
              <p className="text-xs text-muted-foreground">{signal.symbol || signal.market_id}</p>
            </div>
          </div>
          <div className="text-right">
            <div className="flex items-center gap-1">
              <Target className="h-3 w-3 text-muted-foreground" />
              <span className="text-sm font-medium">{confidencePercent}%</span>
            </div>
            <span
              className={cn(
                'text-xs',
                signal.status === 'executed' ? 'text-emerald-500' :
                signal.status === 'pending' ? 'text-yellow-500' : 'text-gray-500'
              )}
            >
              {signal.status}
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Basic info */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-1 text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span>{formatDate(signal.created_at)}</span>
          </div>
          {signal.size && (
            <div className="flex items-center gap-1">
              <DollarSign className="h-3 w-3 text-muted-foreground" />
              <span className="font-mono">{formatCurrency(signal.size)}</span>
            </div>
          )}
        </div>

        {/* Signal reason */}
        {signal.signal_reason && (
          <div className="rounded bg-muted/50 p-2">
            <p className="text-xs text-muted-foreground line-clamp-2">{signal.signal_reason}</p>
          </div>
        )}

        {/* AI Thinking - expandable */}
        {signal.ai_thinking && (
          <div>
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-between text-xs"
              onClick={(e) => {
                e.stopPropagation()
                setExpanded(!expanded)
              }}
            >
              <span className="flex items-center gap-1">
                <Brain className="h-3 w-3" />
                AI 思维链
              </span>
              {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </Button>
            {expanded && (
              <div className="mt-2 rounded bg-muted/50 p-3">
                <pre className="whitespace-pre-wrap text-xs font-mono text-muted-foreground">
                  {signal.ai_thinking}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* AI Metadata */}
        {(signal.ai_model || signal.ai_tokens_used) && (
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{signal.ai_model}</span>
            <span>{signal.ai_tokens_used || 0} tokens</span>
          </div>
        )}

        {/* Actions */}
        <Button variant="outline" size="sm" className="w-full" onClick={onClick}>
          查看详情
        </Button>
      </CardContent>
    </Card>
  )
}

export default function SignalsPage() {
  const [selectedSignal, setSelectedSignal] = useState<SignalLogSummary | null>(null)
  const [page, setPage] = useState(1)

  const { data: signalsResponse, isLoading } = useQuery({
    queryKey: ['signals', page],
    queryFn: () => signalsApi.getAll({ page, pageSize: 12 }),
  })

  const signals = (signalsResponse?.items || []).filter((s) => s.signal_type === 'buy')

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">信号日志</h1>
        <p className="text-muted-foreground">
          查看 AI 交易信号和决策分析
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10">
              <TrendingUp className="h-5 w-5 text-emerald-500" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">买入信号</p>
              <p className="text-xl font-bold">{signals.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-500/10">
              <Activity className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">已执行</p>
              <p className="text-xl font-bold">
                {signals.filter(s => s.status === 'executed').length}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-purple-500/10">
              <Brain className="h-5 w-5 text-purple-500" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">总买入信号</p>
              <p className="text-xl font-bold">{signals.length}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Signals Grid */}
      {signals && signals.length > 0 ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {signals.map((signal) => (
              <SignalCard
                key={signal.id}
                signal={signal}
                onClick={() => setSelectedSignal(signal)}
              />
            ))}
          </div>

          {/* Pagination */}
          {signalsResponse && signalsResponse.total > signalsResponse.page_size && (
            <div className="flex justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
              >
                上一页
              </Button>
              <span className="flex items-center text-sm text-muted-foreground">
                第 {page} / {Math.ceil(signalsResponse.total / signalsResponse.page_size)} 页
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page * signalsResponse.page_size >= signalsResponse.total}
                onClick={() => setPage(p => p + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              <Brain className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-lg font-semibold">暂无信号</h3>
            <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
              启动策略后将会生成交易信号
            </p>
          </CardContent>
        </Card>
      )}

      {/* Signal Detail Dialog */}
      <Dialog open={!!selectedSignal} onOpenChange={() => setSelectedSignal(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>信号详情</DialogTitle>
          </DialogHeader>
          {selectedSignal && (
            <div className="space-y-4">
              {/* Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className={cn(
                      'flex h-10 w-10 items-center justify-center rounded',
                      selectedSignal.signal_type === 'buy' ? 'bg-emerald-500/10' :
                      selectedSignal.signal_type === 'sell' ? 'bg-red-500/10' : 'bg-gray-500/10'
                    )}
                  >
                    {selectedSignal.signal_type === 'buy' ? (
                      <TrendingUp className="h-5 w-5 text-emerald-500" />
                    ) : selectedSignal.signal_type === 'sell' ? (
                      <TrendingDown className="h-5 w-5 text-red-500" />
                    ) : (
                      <Activity className="h-5 w-5 text-gray-500" />
                    )}
                  </div>
                  <div>
                    <p className="text-lg font-semibold">
                      {selectedSignal.signal_type.toUpperCase()} {selectedSignal.side?.toUpperCase()}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {selectedSignal.symbol || selectedSignal.market_id}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-bold">{Math.round((selectedSignal.confidence || 0) * 100)}%</p>
                  <p className="text-xs text-muted-foreground">置信度</p>
                </div>
              </div>

              {/* Details */}
              <div className="grid grid-cols-2 gap-4 rounded-lg bg-muted/50 p-4">
                <div>
                  <p className="text-xs text-muted-foreground">状态</p>
                  <p className="font-medium">{selectedSignal.status}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">金额</p>
                  <p className="font-medium">{formatCurrency(selectedSignal.size || 0)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">时间</p>
                  <p className="font-medium">{formatDate(selectedSignal.created_at)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Signal ID</p>
                  <p className="font-mono text-xs">{selectedSignal.signal_id}</p>
                </div>
              </div>

              {/* Reasoning */}
              {selectedSignal.signal_reason && (
                <div>
                  <p className="mb-2 text-sm font-medium">交易理由</p>
                  <div className="rounded-lg bg-muted/50 p-4">
                    <p className="text-sm">{selectedSignal.signal_reason}</p>
                  </div>
                </div>
              )}

              {/* AI Thinking */}
              {selectedSignal.ai_thinking && (
                <div>
                  <p className="mb-2 text-sm font-medium">AI 思维链</p>
                  <div className="rounded-lg bg-muted/50 p-4">
                    <pre className="whitespace-pre-wrap text-xs font-mono">
                      {selectedSignal.ai_thinking}
                    </pre>
                  </div>
                </div>
              )}

              {/* AI Metadata */}
              <div className="flex items-center justify-between rounded-lg bg-muted/50 p-4">
                <div>
                  <p className="text-xs text-muted-foreground">AI 模型</p>
                  <p className="font-medium">{selectedSignal.ai_model || 'N/A'}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Token 消耗</p>
                  <p className="font-medium">{selectedSignal.ai_tokens_used || 0}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">响应时间</p>
                  <p className="font-medium">{selectedSignal.ai_duration_ms || 0}ms</p>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}