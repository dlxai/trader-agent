import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Plug,
  CheckCircle2,
  XCircle,
  AlertCircle,
  RefreshCw,
  Settings,
  Trash2,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { providersApi } from '@/lib/api'
import type { Provider } from '@/types'
import { cn, formatDate } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog'



const statusConfig = {
  active: { label: 'Active', variant: 'success', icon: CheckCircle2 },
  inactive: { label: 'Inactive', variant: 'secondary', icon: XCircle },
  error: { label: 'Error', variant: 'error', icon: AlertCircle },
} as const

const typeConfig = {
  exchange: { label: 'Exchange', color: 'text-emerald-500' },
  broker: { label: 'Broker', color: 'text-blue-500' },
  data: { label: 'Data Provider', color: 'text-purple-500' },
} as const

function ProviderCard({
  provider,
  onTest,
  onSync,
  onDelete,
}: {
  provider: Provider
  onTest: (id: string) => void
  onSync: (id: string) => void
  onDelete: (id: string) => void
}) {
  const status = statusConfig[provider.status]
  const type = typeConfig[provider.type]
  const StatusIcon = status.icon

  return (
    <Card className="group transition-all hover:border-emerald-500/30">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-void-200">
              <Plug className={cn('h-5 w-5', type.color)} />
            </div>
            <div>
              <CardTitle className="text-base">{provider.name}</CardTitle>
              <CardDescription className="text-xs">
                <span className={type.color}>{type.label}</span>
                {' · '}
                {provider.lastConnectedAt
                  ? `Last connected ${formatDate(provider.lastConnectedAt, { includeTime: false })}`
                  : 'Never connected'}
              </CardDescription>
            </div>
          </div>
          <Badge variant={status.variant} className="gap-1">
            <StatusIcon className="h-3 w-3" />
            {status.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        {provider.lastError && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-500">
            <div className="flex items-center gap-2 font-medium">
              <AlertCircle className="h-4 w-4" />
              Error
            </div>
            <p className="mt-1 text-xs opacity-90">{provider.lastError}</p>
          </div>
        )}

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onTest(provider.id)}
            disabled={provider.status === 'error'}
          >
            <CheckCircle2 className="mr-2 h-3 w-3" />
            Test
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onSync(provider.id)}
            disabled={provider.status !== 'active'}
          >
            <RefreshCw className="mr-2 h-3 w-3" />
            Sync
          </Button>
          <Button variant="outline" size="sm">
            <Settings className="mr-2 h-3 w-3" />
            Configure
          </Button>
          <div className="flex-1" />
          <Button
            variant="ghost"
            size="sm"
            className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
            onClick={() => onDelete(provider.id)}
          >
            <Trash2 className="mr-2 h-3 w-3" />
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function ProvidersPage() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const queryClient = useQueryClient()

  const { data: providers, isLoading } = useQuery({
    queryKey: ['providers'],
    queryFn: () => providersApi.getAll(),
  })

  const testMutation = useMutation({
    mutationFn: (id: string) => providersApi.testConnection(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })

  const syncMutation = useMutation({
    mutationFn: (id: string) => providersApi.sync(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => providersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Providers</h1>
          <p className="text-muted-foreground">
            Manage your exchange connections and data providers
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Provider
        </Button>
      </div>

      {/* Provider Cards */}
      {providers && providers.length > 0 ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {providers.map((provider) => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              onTest={(id) => testMutation.mutate(id)}
              onSync={(id) => syncMutation.mutate(id)}
              onDelete={(id) => deleteMutation.mutate(id)}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-void-200">
              <Plug className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-lg font-semibold">No providers configured</h3>
            <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
              Add a provider to connect to an exchange or data source
            </p>
            <Button className="mt-6" onClick={() => setIsCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Provider
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Create Dialog Placeholder */}
      {isCreateDialogOpen && (
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Provider</DialogTitle>
              <DialogDescription>
                Configure a new exchange or data provider connection
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <p className="text-sm text-muted-foreground">
                Provider configuration form will be implemented here
              </p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button>Add Provider</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
