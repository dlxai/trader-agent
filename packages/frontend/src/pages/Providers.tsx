import { useState, useEffect } from 'react'
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
  Brain,
  ExternalLink,
  Save,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { Switch } from '@/components/ui/Switch'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { settingsApi } from '@/lib/api'
import { AVAILABLE_AI_MODELS, AI_PROVIDER_URLS, type AIModelConfig } from '@/types'
import { cn } from '@/lib/utils'

function ProviderCard({
  model,
  onToggle,
  onUpdateApiKey,
  onUpdateCustomUrl,
  onUpdateCustomModel,
  onSave,
  isSaving,
}: {
  model: AIModelConfig
  onToggle: () => void
  onUpdateApiKey: (key: string) => void
  onUpdateCustomUrl: (url: string) => void
  onUpdateCustomModel: (name: string) => void
  onSave: () => void
  isSaving: boolean
}) {
  const isEnabled = model.enabled

  return (
    <div
      className={cn(
        'rounded-lg border p-4 transition-all',
        isEnabled ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-border'
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
            <Brain className="h-5 w-5" />
          </div>
          <div>
            <h4 className="font-medium">{model.name}</h4>
            <p className="text-xs text-muted-foreground capitalize">{model.provider}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Switch checked={isEnabled} onCheckedChange={onToggle} />
        </div>
      </div>

      {isEnabled && (
        <div className="mt-4 space-y-3">
          <div className="space-y-2">
            <Label>API Key</Label>
            <div className="flex gap-2">
              <Input
                type="password"
                placeholder="输入 API Key"
                value={model.api_key || ''}
                onChange={(e) => onUpdateApiKey(e.target.value)}
                className="flex-1"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.open(AI_PROVIDER_URLS[model.provider], '_blank')}
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Label>自定义 API URL (可选)</Label>
            <Input
              placeholder="如使用代理或自定义端点"
              value={model.custom_api_url || ''}
              onChange={(e) => onUpdateCustomUrl(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>自定义模型名称 (可选)</Label>
            <Input
              placeholder="如 deepseek-chat, gpt-4 等"
              value={model.custom_model_name || ''}
              onChange={(e) => onUpdateCustomModel(e.target.value)}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default function ProvidersPage() {
  const queryClient = useQueryClient()

  // Initialize with default models
  const [models, setModels] = useState<AIModelConfig[]>(
    AVAILABLE_AI_MODELS.map(m => ({ ...m, enabled: false, api_key: '', custom_api_url: '', custom_model_name: '' }))
  )

  // Fetch current preferences from backend
  const { data: currentPrefs, isLoading } = useQuery({
    queryKey: ['user-preferences'],
    queryFn: () => settingsApi.getSettings(),
  })

  // Update models when preferences load
  useEffect(() => {
    if (currentPrefs?.ai_models) {
      setModels(prev => prev.map(m => {
        const saved = currentPrefs.ai_models?.find(sm => sm.id === m.id)
        return saved ? { ...m, ...saved } : m
      }))
    }
  }, [currentPrefs])

  const saveMutation = useMutation({
    mutationFn: (aiModels: AIModelConfig[]) =>
      settingsApi.updateSettings({ ai_models: aiModels } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-preferences'] })
      alert('配置已保存')
    },
    onError: (error) => {
      console.error('Failed to save models:', error)
      alert('保存失败，请重试')
    },
  })

  const toggleModel = (modelId: string) => {
    setModels(prev => prev.map(m =>
      m.id === modelId ? { ...m, enabled: !m.enabled } : m
    ))
  }

  const updateModelApiKey = (modelId: string, apiKey: string) => {
    setModels(prev => prev.map(m =>
      m.id === modelId ? { ...m, api_key: apiKey } : m
    ))
  }

  const updateModelCustomUrl = (modelId: string, url: string) => {
    setModels(prev => prev.map(m =>
      m.id === modelId ? { ...m, custom_api_url: url } : m
    ))
  }

  const updateModelCustomName = (modelId: string, name: string) => {
    setModels(prev => prev.map(m =>
      m.id === modelId ? { ...m, custom_model_name: name } : m
    ))
  }

  const saveModels = () => {
    saveMutation.mutate(models)
  }

  const configuredModels = models.filter(m => m.enabled && m.api_key)

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI Provider</h1>
          <p className="text-muted-foreground">
            配置您的 AI 模型
          </p>
        </div>
        <Button onClick={saveModels} isLoading={saveMutation.isPending}>
          <Save className="mr-2 h-4 w-4" />
          保存配置
        </Button>
      </div>

      {/* AI Provider Cards */}
      <div className="space-y-4">
        {models.map((model) => (
          <ProviderCard
            key={model.id}
            model={model}
            onToggle={() => toggleModel(model.id)}
            onUpdateApiKey={(key) => updateModelApiKey(model.id, key)}
            onUpdateCustomUrl={(url) => updateModelCustomUrl(model.id, url)}
            onUpdateCustomModel={(name) => updateModelCustomName(model.id, name)}
            onSave={saveModels}
            isSaving={saveMutation.isPending}
          />
        ))}
      </div>

      {/* Configured Models Summary */}
      <div className="flex items-center justify-between rounded-lg border border-border bg-muted/50 p-4">
        <div>
          <h4 className="font-medium">已配置模型 ({configuredModels.length})</h4>
          <p className="text-sm text-muted-foreground mt-1">
            {configuredModels.length === 0
              ? '请启用并配置至少一个 AI 模型'
              : configuredModels.map(m => m.name).join(', ')}
          </p>
        </div>
        <Button onClick={saveModels} isLoading={saveMutation.isPending}>
          保存配置
        </Button>
      </div>
    </div>
  )
}