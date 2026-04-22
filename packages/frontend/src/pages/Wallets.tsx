import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Wallet as WalletIcon,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Settings,
  Trash2,
  Eye,
  EyeOff,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { walletsApi } from '@/lib/api'
import type { Wallet as WalletType, CreateWalletRequest, WalletTestResult } from '@/types'
import { formatDate } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog'
import { useToast } from '@/hooks/useToast'

const statusConfig = {
  active: { label: 'Active', variant: 'success' as const, icon: CheckCircle2 },
  inactive: { label: 'Inactive', variant: 'secondary' as const, icon: XCircle },
  error: { label: 'Error', variant: 'error' as const, icon: AlertCircle },
} as const

function WalletCard({
  wallet,
  onTest,
  onSetDefault,
  onDelete,
  isTesting,
  isSettingDefault,
  isDeleting,
}: {
  wallet: WalletType
  onTest: (id: string) => void
  onSetDefault: (id: string) => void
  onDelete: (id: string) => void
  isTesting: boolean
  isSettingDefault: boolean
  isDeleting: boolean
}) {
  const status = statusConfig[wallet.status]
  const StatusIcon = status.icon

  return (
    <Card className="group transition-all hover:border-emerald-500/30">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
              <WalletIcon className="h-5 w-5 text-emerald-500" />
            </div>
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                {wallet.name}
                {wallet.is_default && (
                  <Badge variant="success" className="text-xs">Default</Badge>
                )}
              </CardTitle>
              <CardDescription className="text-xs">
                {wallet.address ? (
                  <span className="font-mono">{wallet.address.slice(0, 10)}...{wallet.address.slice(-6)}</span>
                ) : (
                  'No address'
                )}
                {' · '}
                {wallet.last_used_at
                  ? `Last used ${formatDate(wallet.last_used_at, { includeTime: false })}`
                  : 'Never used'}
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
        {wallet.usdc_balance && (
          <div className="mb-4 rounded-lg bg-emerald-500/10 p-3 text-sm">
            <span className="text-muted-foreground">Balance: </span>
            <span className="font-medium text-emerald-500">{wallet.usdc_balance} USDC</span>
          </div>
        )}

        {wallet.last_error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-500">
            <div className="flex items-center gap-2 font-medium">
              <AlertCircle className="h-4 w-4" />
              Error
            </div>
            <p className="mt-1 text-xs opacity-90">{wallet.last_error}</p>
          </div>
        )}

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onTest(wallet.id)}
            disabled={isTesting}
          >
            {isTesting ? (
              <span className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <CheckCircle2 className="mr-2 h-3 w-3" />
            )}
            {isTesting ? 'Testing...' : 'Test'}
          </Button>
          {!wallet.is_default && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onSetDefault(wallet.id)}
              disabled={isSettingDefault}
            >
              {isSettingDefault ? (
                <span className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : (
                <Settings className="mr-2 h-3 w-3" />
              )}
              {isSettingDefault ? 'Updating...' : 'Set Default'}
            </Button>
          )}
          <div className="flex-1" />
          <Button
            variant="ghost"
            size="sm"
            className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
            onClick={() => onDelete(wallet.id)}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <span className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <Trash2 className="mr-2 h-3 w-3" />
            )}
            {isDeleting ? 'Deleting...' : 'Delete'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function CreateWalletDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (wallet: WalletType) => void
}) {
  const [name, setName] = useState('')
  const [privateKey, setPrivateKey] = useState('')
  const [proxyWalletAddress, setProxyWalletAddress] = useState('')
  const [showPrivateKey, setShowPrivateKey] = useState(false)
  const [isDefault, setIsDefault] = useState(false)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const createMutation = useMutation({
    mutationFn: (data: CreateWalletRequest) => walletsApi.create(data),
    onSuccess: (wallet: WalletType) => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] })
      toast({ title: 'Wallet created successfully', description: 'Fetching balance...' })
      setName('')
      setPrivateKey('')
      setProxyWalletAddress('')
      onOpenChange(false)
      // Auto-test after creation
      onCreated(wallet)
    },
    onError: (error: Error) => {
      toast({ title: 'Failed to create wallet', description: error.message, variant: 'destructive' })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({
      name,
      private_key: privateKey,
      proxy_wallet_address: proxyWalletAddress || undefined,
      is_default: isDefault,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Polymarket Wallet</DialogTitle>
          <DialogDescription>
            Configure your Polymarket wallet to enable trading
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Wallet Name</Label>
              <Input
                id="name"
                placeholder="My Main Wallet"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="privateKey">Private Key</Label>
              <div className="relative">
                <Input
                  id="privateKey"
                  type={showPrivateKey ? 'text' : 'password'}
                  placeholder="0x..."
                  value={privateKey}
                  onChange={(e) => setPrivateKey(e.target.value)}
                  required
                  className="font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPrivateKey(!showPrivateKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPrivateKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="text-xs text-muted-foreground">
                Your private key is encrypted and stored securely
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="proxyWalletAddress">Proxy Wallet Address (Optional)</Label>
              <Input
                id="proxyWalletAddress"
                placeholder="0x..."
                value={proxyWalletAddress}
                onChange={(e) => setProxyWalletAddress(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="isDefault"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="rounded border-border"
              />
              <Label htmlFor="isDefault" className="text-sm font-normal">
                Set as default wallet
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" type="button" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Wallet'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function WalletsPage() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: wallets, isLoading } = useQuery({
    queryKey: ['wallets'],
    queryFn: () => walletsApi.getAll(),
  })

  const testMutation = useMutation({
    mutationFn: (id: string) => walletsApi.testConnection(id),
    onSuccess: (data: WalletTestResult) => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] })
      if (data.success) {
        toast({ title: 'Connection successful', description: `Balance: ${data.balance} USDC` })
      } else {
        toast({ title: 'Connection failed', description: data.error || data.message, variant: 'destructive' })
      }
    },
    onError: (error: Error) => {
      toast({ title: 'Connection failed', description: error.message, variant: 'destructive' })
    },
  })

  const setDefaultMutation = useMutation({
    mutationFn: (id: string) => walletsApi.setDefault(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] })
      toast({ title: 'Default wallet updated' })
    },
    onError: (error: Error) => {
      toast({ title: 'Failed to update default', description: error.message, variant: 'destructive' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => walletsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] })
      toast({ title: 'Wallet deleted' })
    },
    onError: (error: Error) => {
      toast({ title: 'Failed to delete wallet', description: error.message, variant: 'destructive' })
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
          <h1 className="text-2xl font-bold tracking-tight">Wallets</h1>
          <p className="text-muted-foreground">
            Manage your Polymarket wallet connections
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Wallet
        </Button>
      </div>

      {/* Wallet Cards */}
      {wallets && wallets.length > 0 ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {wallets.map((wallet) => (
            <WalletCard
              key={wallet.id}
              wallet={wallet}
              onTest={(id) => testMutation.mutate(id)}
              onSetDefault={(id) => setDefaultMutation.mutate(id)}
              onDelete={(id) => deleteMutation.mutate(id)}
              isTesting={testMutation.isPending && testMutation.variables === wallet.id}
              isSettingDefault={setDefaultMutation.isPending && setDefaultMutation.variables === wallet.id}
              isDeleting={deleteMutation.isPending && deleteMutation.variables === wallet.id}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              <WalletIcon className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-lg font-semibold">No wallets configured</h3>
            <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
              Add a Polymarket wallet to start trading
            </p>
            <Button className="mt-6" onClick={() => setIsCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Wallet
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Create Dialog */}
      <CreateWalletDialog
        open={isCreateDialogOpen}
        onOpenChange={setIsCreateDialogOpen}
        onCreated={(wallet) => testMutation.mutate(wallet.id)}
      />
    </div>
  )
}