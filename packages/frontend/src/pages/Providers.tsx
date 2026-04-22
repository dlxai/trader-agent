import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Brain,
  ExternalLink,
  Save,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { Switch } from '@/components/ui/Switch'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import { providersApi, settingsApi } from '@/lib/api'
import { AI_PROVIDER_URLS, type AIModelConfig } from '@/types'
import { cn } from '@/lib/utils'
import { useToast } from '@/hooks/useToast'

interface ProviderTypeInfo {
  name: string
  models: string[]
  supports: string[]
}

function ProviderCard({
  model,
  providerTypes,
  fetchedModels,
  onToggle,
  onUpdateApiKey,
  onUpdateCustomUrl,
  onUpdateCustomModel,
  onFetchModels,
  isFetchingModels,
}: {
  model: AIModelConfig
  providerTypes: Record<string, ProviderTypeInfo>
  fetchedModels?: string[]
  onToggle: () => void
  onUpdateApiKey: (key: string) => void
  onUpdateCustomUrl: (url: string) => void
  onUpdateCustomModel: (name: string) => void
  onFetchModels: () => void
  isFetchingModels: boolean
}) {
  // Use fetched models if available, otherwise fall back to predefined models
  const availableModels = fetchedModels && fetchedModels.length > 0
    ? fetchedModels
    : (providerTypes[model.provider]?.models || [])

  return (
    <div
      className={cn(
        'rounded-lg border p-4 transition-all',
        model.enabled ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-border'
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
          <Switch checked={model.enabled} onCheckedChange={onToggle} />
        </div>
      </div>

      {model.enabled && (
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
              {AI_PROVIDER_URLS[model.provider] && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(AI_PROVIDER_URLS[model.provider], '_blank')}
                >
                  <ExternalLink className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>自定义 API URL (可选)</Label>
              <Button
                variant="outline"
                size="sm"
                onClick={onFetchModels}
                disabled={isFetchingModels || !model.api_key || !model.custom_api_url}
              >
                {isFetchingModels ? '获取中...' : '获取模型'}
              </Button>
            </div>
            <Input
              placeholder="如 https://api.deepseek.com"
              value={model.custom_api_url || ''}
              onChange={(e) => onUpdateCustomUrl(e.target.value)}
            />
            {fetchedModels && fetchedModels.length > 0 && (
              <p className="text-xs text-emerald-500">已获取 {fetchedModels.length} 个模型，请从下拉选择</p>
            )}
          </div>

          <div className="space-y-2">
            <Label>选择模型</Label>
            {availableModels.length > 0 ? (
              <Select
                value={
                  availableModels.includes(model.custom_model_name || '')
                    ? model.custom_model_name || ''
                    : '__custom__'
                }
                onValueChange={(value) => {
                  if (value === '__custom__') {
                    onUpdateCustomModel('')
                  } else {
                    onUpdateCustomModel(value)
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择模型" />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                  <SelectItem value="__custom__">其他（自定义）</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <p className="text-sm text-muted-foreground">该 provider 暂不支持自动获取模型列表</p>
            )}
            {/* Show input when: custom mode selected (empty input) OR custom model name not in list */}
            {(!availableModels.includes(model.custom_model_name || '') || model.custom_model_name === '') && (
              <Input
                placeholder="输入自定义模型名称"
                value={model.custom_model_name || ''}
                onChange={(e) => onUpdateCustomModel(e.target.value)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function buildModelsFromProviderTypes(
  providerTypes: Record<string, ProviderTypeInfo>
): AIModelConfig[] {
  return Object.entries(providerTypes).flatMap(([providerKey, providerInfo]) => {
    if (providerInfo.models.length === 0) {
      return [{
        id: providerKey,
        name: providerInfo.name,
        provider: providerKey,
        enabled: false,
        api_key: '',
        custom_api_url: '',
        custom_model_name: '',
      }]
    }
    return [{
      id: providerKey,
      name: providerInfo.name,
      provider: providerKey,
      enabled: false,
      api_key: '',
      custom_api_url: '',
      custom_model_name: providerInfo.models[0],
    }]
  })
}

export default function ProvidersPage() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  // Fetch available provider types from backend
  const { data: providerTypes, isLoading: isLoadingTypes } = useQuery({
    queryKey: ['provider-types'],
    queryFn: () => providersApi.getProviderTypes(),
  })

  // Initialize models from backend provider types
  const [models, setModels] = useState<AIModelConfig[]>([])
  const [fetchedModelsMap, setFetchedModelsMap] = useState<Record<string, string[]>>({})
  const [isFetchingModelsId, setIsFetchingModelsId] = useState<string | null>(null)

  // Build models list when provider types load
  useEffect(() => {
    if (providerTypes) {
      setModels(buildModelsFromProviderTypes(providerTypes))
    }
  }, [providerTypes])

  // Fetch current saved preferences from backend
  const { data: currentPrefs, isLoading: isLoadingPrefs } = useQuery({
    queryKey: ['user-preferences'],
    queryFn: () => settingsApi.getSettings(),
  })

  // Fetch existing providers from backend
  const { data: existingProviders } = useQuery({
    queryKey: ['providers'],
    queryFn: () => providersApi.getAll(),
  })

  // Merge saved preferences into models list
  useEffect(() => {
    if (currentPrefs?.ai_models && models.length > 0) {
      setModels((prev) =>
        prev.map((m) => {
          const saved = currentPrefs.ai_models?.find((sm) => sm.id === m.id)
          return saved ? { ...m, ...saved } : m
        })
      )
    }
  }, [currentPrefs])

  const saveMutation = useMutation({
    mutationFn: async (aiModels: AIModelConfig[]) => {
      // Save to user preferences
      await settingsApi.updateSettings({ ai_models: aiModels } as any)

      // Sync enabled models to providers table
      const existingProvidersMap = new Map(
        (existingProviders || []).map((p: any) => [p.provider_type, p])
      )

      for (const model of aiModels) {
        if (!model.enabled || !model.api_key) continue

        const existing = existingProvidersMap.get(model.provider)
        const providerData = {
          name: model.name,
          provider_type: model.provider,
          type: 'llm',
          api_key: model.api_key,
          api_base: model.custom_api_url || undefined,
          model: model.custom_model_name || undefined,
          is_default: false,
        }

        if (existing) {
          await providersApi.update(existing.id, providerData)
        } else {
          await providersApi.create(providerData as any)
        }
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-preferences'] })
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      toast({ title: '配置已保存', variant: 'default' })
    },
    onError: (error) => {
      console.error('Failed to save models:', error)
      toast({ title: '保存失败，请重试', variant: 'destructive' })
    },
  })

  const toggleModel = (modelId: string) => {
    setModels((prev) =>
      prev.map((m) => (m.id === modelId ? { ...m, enabled: !m.enabled } : m))
    )
  }

  const updateModelApiKey = (modelId: string, apiKey: string) => {
    setModels((prev) =>
      prev.map((m) => (m.id === modelId ? { ...m, api_key: apiKey } : m))
    )
  }

  const updateModelCustomUrl = (modelId: string, url: string) => {
    setModels((prev) =>
      prev.map((m) => (m.id === modelId ? { ...m, custom_api_url: url } : m))
    )
  }

  const updateModelCustomName = (modelId: string, name: string) => {
    setModels((prev) =>
      prev.map((m) => (m.id === modelId ? { ...m, custom_model_name: name } : m))
    )
  }

  const fetchModelsForProvider = async (modelId: string) => {
    const model = models.find((m) => m.id === modelId)
    if (!model?.api_key || !model?.custom_api_url) {
      toast({ title: '请先填写 API Key 和 API URL', variant: 'destructive' })
      return
    }
    setIsFetchingModelsId(modelId)
    try {
      const result = await providersApi.fetchModels(model.custom_api_url, model.api_key, model.provider)
      if (result.error) {
        toast({ title: '获取模型失败', description: result.error, variant: 'destructive' })
      } else {
        setFetchedModelsMap((prev) => ({ ...prev, [modelId]: result.models }))
        toast({ title: `成功获取 ${result.models.length} 个模型` })
      }
    } catch (err) {
      toast({ title: '获取模型失败', variant: 'destructive' })
    } finally {
      setIsFetchingModelsId(null)
    }
  }

  const saveModels = () => {
    saveMutation.mutate(models)
  }

  const configuredModels = models.filter((m) => m.enabled && m.api_key)

  if (isLoadingTypes || isLoadingPrefs) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI Provider</h1>
          <p className="text-muted-foreground">配置您的 AI 模型</p>
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
            providerTypes={providerTypes || {}}
            fetchedModels={fetchedModelsMap[model.id]}
            onToggle={() => toggleModel(model.id)}
            onUpdateApiKey={(key) => updateModelApiKey(model.id, key)}
            onUpdateCustomUrl={(url) => updateModelCustomUrl(model.id, url)}
            onUpdateCustomModel={(name) => updateModelCustomName(model.id, name)}
            onFetchModels={() => fetchModelsForProvider(model.id)}
            isFetchingModels={isFetchingModelsId === model.id}
          />
        ))}
      </div>

      {/* Configured Models Summary */}
      <div className="flex items-center justify-between rounded-lg border border-border bg-muted/50 p-4">
        <div>
          <h4 className="font-medium">已配置模型 ({configuredModels.length})</h4>
          <p className="mt-1 text-sm text-muted-foreground">
            {configuredModels.length === 0
              ? '请启用并配置至少一个 AI 模型'
              : configuredModels.map((m) => m.name).join(', ')}
          </p>
        </div>
        <Button onClick={saveModels} isLoading={saveMutation.isPending}>
          保存配置
        </Button>
      </div>
    </div>
  )
}
