import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
  type AxiosResponse,
  type AxiosError,
} from 'axios'
import type {
  ApiResponse,
  ApiError,
  LoginCredentials,
  RegisterCredentials,
  AuthTokens,
  User,
  Portfolio,
  Position,
  Order,
  Provider,
  CreatePortfolioRequest,
  UpdatePortfolioRequest,
  CreateOrderRequest,
  CreateProviderRequest,
  UserSettings,
  Wallet,
  CreateWalletRequest,
  UpdateWalletRequest,
  WalletTestResult,
  Strategy,
  StrategySummary,
  CreateStrategyRequest,
  UpdateStrategyRequest,
} from '@/types'

// API base URL
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Token management
const getAccessToken = (): string | null => {
  return localStorage.getItem('accessToken')
}

const setTokens = (tokens: AuthTokens): void => {
  localStorage.setItem('accessToken', tokens.accessToken)
  localStorage.setItem('refreshToken', tokens.refreshToken)
  localStorage.setItem('expiresAt', tokens.expiresAt.toString())
}

const clearTokens = (): void => {
  localStorage.removeItem('accessToken')
  localStorage.removeItem('refreshToken')
  localStorage.removeItem('expiresAt')
}

const isTokenExpired = (): boolean => {
  const expiresAt = localStorage.getItem('expiresAt')
  if (!expiresAt) return true
  return Date.now() >= parseInt(expiresAt, 10)
}

// Request interceptor
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken()

    if (token && config.headers) {
      // Check if token needs refresh
      if (isTokenExpired() && config.url !== '/auth/refresh') {
        try {
          const newToken = await authApi.refreshToken()
          config.headers.Authorization = `Bearer ${newToken}`
        } catch {
          clearTokens()
          window.location.href = '/login'
        }
      } else {
        config.headers.Authorization = `Bearer ${token}`
      }
    }

    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// Response interceptor
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    return response
  },
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }

    // Handle 401 Unauthorized
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        const newToken = await authApi.refreshToken()
        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`
        }
        return apiClient(originalRequest)
      } catch {
        clearTokens()
        window.location.href = '/login'
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  async login(credentials: LoginCredentials): Promise<{ tokens: AuthTokens; user: User }> {
    const response = await apiClient.post<ApiResponse<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      expires_in: number;
      expires_at: string;
    }>>('/auth/login', credentials)

    const { access_token, refresh_token, expires_at } = response.data.data

    // Convert expires_at string to timestamp
    const expiresAtTimestamp = new Date(expires_at).getTime()

    // Convert to the format expected by the store
    const tokens: AuthTokens = {
      accessToken: access_token,
      refreshToken: refresh_token,
      expiresAt: expiresAtTimestamp,
    }
    setTokens(tokens)

    // Fetch user data after login
    const user = await this.getCurrentUser()

    return { tokens, user }
  },

  async register(credentials: RegisterCredentials): Promise<{ tokens: AuthTokens; user: User }> {
    const response = await apiClient.post<ApiResponse<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      expires_in: number;
      expires_at: string;
    }>>('/auth/register', credentials)

    const { access_token, refresh_token, expires_at } = response.data.data

    const expiresAtTimestamp = new Date(expires_at).getTime()

    const tokens: AuthTokens = {
      accessToken: access_token,
      refreshToken: refresh_token,
      expiresAt: expiresAtTimestamp,
    }
    setTokens(tokens)

    const user = await this.getCurrentUser()

    return { tokens, user }
  },

  async logout(): Promise<void> {
    try {
      await apiClient.post('/auth/logout')
    } finally {
      clearTokens()
    }
  },

  async refreshToken(): Promise<string> {
    const refreshToken = localStorage.getItem('refreshToken')
    const response = await apiClient.post<ApiResponse<{ accessToken: string; expiresAt: number }>>('/auth/refresh', {
      refreshToken,
    })
    const { accessToken, expiresAt } = response.data.data
    localStorage.setItem('accessToken', accessToken)
    localStorage.setItem('expiresAt', expiresAt.toString())
    return accessToken
  },

  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get<ApiResponse<User>>('/users/me')
    return response.data.data
  },
}

// Portfolios API
export interface PortfolioSummary {
  id: string
  name: string
  trading_mode: string
  is_active: boolean
  current_balance: number
  total_pnl: number
  total_pnl_percent: number
  total_trades: number
  strategy_count: number
  strategy_total_pnl: number
  created_at: string
}

export interface PortfolioListResponse {
  items: PortfolioSummary[]
  total: number
  page: number
  page_size: number
}

export const portfoliosApi = {
  async getAll(): Promise<PortfolioListResponse> {
    const response = await apiClient.get<ApiResponse<PortfolioListResponse>>('/portfolios')
    return response.data.data
  },

  async getById(id: string): Promise<Portfolio> {
    const response = await apiClient.get<ApiResponse<Portfolio>>(`/portfolios/${id}`)
    return response.data.data
  },

  async create(data: CreatePortfolioRequest): Promise<Portfolio> {
    const response = await apiClient.post<ApiResponse<Portfolio>>('/portfolios', data)
    return response.data.data
  },

  async update(id: string, data: UpdatePortfolioRequest): Promise<Portfolio> {
    const response = await apiClient.patch<ApiResponse<Portfolio>>(`/portfolios/${id}`, data)
    return response.data.data
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/portfolios/${id}`)
  },

  async getStats(id: string): Promise<{
    totalValue: number
    totalCost: number
    unrealizedPnl: number
    realizedPnl: number
    pnlPercentage: number
    positions: number
  }> {
    const response = await apiClient.get<ApiResponse<{
      totalValue: number
      totalCost: number
      unrealizedPnl: number
      realizedPnl: number
      pnlPercentage: number
      positions: number
    }>>(`/portfolios/${id}/stats`)
    return response.data.data
  },
}

// Positions API
// Position response from backend (paginated)
export interface PositionListResponse {
  items: PositionSummary[]
  total: number
  page: number
  page_size: number
}

export interface PositionSummary {
  id: string
  market_id: string
  symbol: string
  side: string
  status: string
  size: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
  pnl_percent: number
  opened_at: string
  leverage: number
  portfolio?: {
    id: string
    name: string
  }
}

export const positionsApi = {
  async getAll(): Promise<PositionListResponse> {
    const response = await apiClient.get<ApiResponse<PositionListResponse>>('/positions')
    return response.data.data
  },

  async getByPortfolio(portfolioId: string): Promise<Position[]> {
    const response = await apiClient.get<ApiResponse<Position[]>>(`/portfolios/${portfolioId}/positions`)
    return response.data.data
  },

  async getById(id: string): Promise<Position> {
    const response = await apiClient.get<ApiResponse<Position>>(`/positions/${id}`)
    return response.data.data
  },

  async getHistory(id: string, params?: { from?: string; to?: string }): Promise<{
    date: string
    price: number
    value: number
    pnl: number
  }[]> {
    const response = await apiClient.get<ApiResponse<{
      date: string
      price: number
      value: number
      pnl: number
    }[]>>(`/positions/${id}/history`, { params })
    return response.data.data
  },
}

// Orders API
export interface OrderSummary {
  id: string
  market_id: string
  symbol: string
  side: string
  order_type: string
  size: number
  filled_size: number
  status: string
  created_at: string
  avg_fill_price?: number
}

export interface OrderListResponse {
  items: OrderSummary[]
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  has_prev: boolean
}

export const ordersApi = {
  async getAll(params?: {
    portfolioId?: string
    status?: string
    side?: string
    from?: string
    to?: string
    limit?: number
    offset?: number
  }): Promise<OrderListResponse> {
    const response = await apiClient.get<ApiResponse<OrderListResponse>>('/orders', { params })
    return response.data.data
  },

  async getById(id: string): Promise<Order> {
    const response = await apiClient.get<ApiResponse<Order>>(`/orders/${id}`)
    return response.data.data
  },

  async create(data: CreateOrderRequest): Promise<Order> {
    const response = await apiClient.post<ApiResponse<Order>>('/orders', data)
    return response.data.data
  },

  async cancel(id: string): Promise<Order> {
    const response = await apiClient.post<ApiResponse<Order>>(`/orders/${id}/cancel`)
    return response.data.data
  },

  async modify(id: string, updates: { quantity?: number; price?: number; stopPrice?: number }): Promise<Order> {
    const response = await apiClient.patch<ApiResponse<Order>>(`/orders/${id}`, updates)
    return response.data.data
  },
}

// Providers API
export const providersApi = {
  async getAll(): Promise<Provider[]> {
    const response = await apiClient.get<ApiResponse<Provider[]>>('/providers')
    return response.data.data
  },

  async getById(id: string): Promise<Provider> {
    const response = await apiClient.get<ApiResponse<Provider>>(`/providers/${id}`)
    return response.data.data
  },

  async create(data: CreateProviderRequest): Promise<Provider> {
    const response = await apiClient.post<ApiResponse<Provider>>('/providers', data)
    return response.data.data
  },

  async update(id: string, data: Partial<CreateProviderRequest>): Promise<Provider> {
    const response = await apiClient.patch<ApiResponse<Provider>>(`/providers/${id}`, data)
    return response.data.data
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/providers/${id}`)
  },

  async testConnection(id: string): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.post<ApiResponse<{ success: boolean; message: string }>>(`/providers/${id}/test`)
    return response.data.data
  },

  async sync(id: string): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.post<ApiResponse<{ success: boolean; message: string }>>(`/providers/${id}/sync`)
    return response.data.data
  },
}

// Wallets API (Polymarket)
export const walletsApi = {
  async getAll(): Promise<Wallet[]> {
    const response = await apiClient.get<ApiResponse<{ items: Wallet[] }>>('/wallets')
    return response.data.data.items
  },

  async getById(id: string): Promise<Wallet> {
    const response = await apiClient.get<ApiResponse<Wallet>>(`/wallets/${id}`)
    return response.data.data
  },

  async create(data: CreateWalletRequest): Promise<Wallet> {
    const response = await apiClient.post<ApiResponse<Wallet>>('/wallets', data)
    return response.data.data
  },

  async update(id: string, data: UpdateWalletRequest): Promise<Wallet> {
    const response = await apiClient.patch<ApiResponse<Wallet>>(`/wallets/${id}`, data)
    return response.data.data
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/wallets/${id}`)
  },

  async testConnection(id: string): Promise<WalletTestResult> {
    const response = await apiClient.post<ApiResponse<WalletTestResult>>(`/wallets/${id}/test`)
    return response.data.data
  },

  async setDefault(id: string): Promise<Wallet> {
    const response = await apiClient.post<ApiResponse<Wallet>>(`/wallets/default/${id}/set`)
    return response.data.data
  },
}

// Settings API (uses /api/users/me/preferences)
export const settingsApi = {
  async getSettings(): Promise<UserSettings> {
    const response = await apiClient.get<ApiResponse<UserSettings>>('/users/me/preferences')
    return response.data.data
  },

  async updateSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
    const response = await apiClient.put<ApiResponse<UserSettings>>('/users/me/preferences', settings)
    return response.data.data
  },

  async changePassword(data: { currentPassword: string; newPassword: string }): Promise<void> {
    await apiClient.post('/settings/change-password', data)
  },

  async getApiKeys(): Promise<{
    id: string
    name: string
    prefix: string
    createdAt: string
    lastUsedAt?: string
  }[]> {
    const response = await apiClient.get<ApiResponse<{
      id: string
      name: string
      prefix: string
      createdAt: string
      lastUsedAt?: string
    }[]>>('/settings/api-keys')
    return response.data.data
  },

  async createApiKey(name: string): Promise<{ id: string; key: string }> {
    const response = await apiClient.post<ApiResponse<{ id: string; key: string }>>('/settings/api-keys', { name })
    return response.data.data
  },

  async revokeApiKey(id: string): Promise<void> {
    await apiClient.delete(`/settings/api-keys/${id}`)
  },

  // Telegram 配置
  async getTelegramConfig(): Promise<{
    is_configured: boolean;
    bot_token_masked?: string;
    chat_id?: string;
  }> {
    const response = await apiClient.get<ApiResponse<{
      is_configured: boolean;
      bot_token_masked?: string;
      chat_id?: string;
    }>>('/users/me/telegram')
    return response.data.data
  },

  async configureTelegram(botToken: string, chatId: string): Promise<{
    is_configured: boolean;
    bot_token_masked?: string;
    chat_id?: string;
  }> {
    const response = await apiClient.post<ApiResponse<{
      is_configured: boolean;
      bot_token_masked?: string;
      chat_id?: string;
    }>>('/users/me/telegram', {
      bot_token: botToken,
      chat_id: chatId,
    })
    return response.data.data
  },

  async deleteTelegramConfig(): Promise<void> {
    await apiClient.delete('/users/me/telegram')
  },
}

// Export token management
// Strategies API
export const strategiesApi = {
  async getAll(params?: { page?: number; pageSize?: number; portfolioId?: string }): Promise<{
    items: StrategySummary[];
    total: number;
    page: number;
    page_size: number;
  }> {
    const response = await apiClient.get<ApiResponse<{
      items: StrategySummary[];
      total: number;
      page: number;
      page_size: number;
    }>>('/strategies', { params })
    return response.data.data
  },

  async getById(id: string): Promise<Strategy> {
    const response = await apiClient.get<ApiResponse<Strategy>>(`/strategies/${id}`)
    return response.data.data
  },

  async create(data: CreateStrategyRequest): Promise<Strategy> {
    const response = await apiClient.post<ApiResponse<Strategy>>('/strategies', data)
    return response.data.data
  },

  async update(id: string, data: UpdateStrategyRequest): Promise<Strategy> {
    const response = await apiClient.put<ApiResponse<Strategy>>(`/strategies/${id}`, data)
    return response.data.data
  },

  async delete(id: string): Promise<void> {
    await apiClient.delete(`/strategies/${id}`)
  },

  async start(id: string): Promise<Strategy> {
    const response = await apiClient.post<ApiResponse<Strategy>>(`/strategies/${id}/start`)
    return response.data.data
  },

  async stop(id: string): Promise<Strategy> {
    const response = await apiClient.post<ApiResponse<Strategy>>(`/strategies/${id}/stop`)
    return response.data.data
  },

  async runOnce(id: string): Promise<{ message: string }> {
    const response = await apiClient.post<ApiResponse<{ message: string }>>(`/strategies/${id}/run-once`)
    return response.data.data
  },
}

// Signals API
export interface SignalLogSummary {
  id: string;
  signal_id: string;
  signal_type: 'buy' | 'sell' | 'hold' | 'close';
  status: string;
  side: string;
  confidence: number;
  size?: number;
  market_id?: string;
  symbol?: string;
  ai_thinking?: string;
  ai_model?: string;
  ai_tokens_used?: number;
  ai_duration_ms?: number;
  signal_reason?: string;
  created_at: string;
}

export interface SignalListResponse {
  items: SignalLogSummary[];
  total: number;
  page: number;
  page_size: number;
}

export const signalsApi = {
  async getAll(params?: {
    page?: number;
    pageSize?: number;
    strategyId?: string;
    status?: string;
  }): Promise<SignalListResponse> {
    const response = await apiClient.get<ApiResponse<SignalListResponse>>('/signals', { params })
    return response.data.data
  },

  async getById(id: string): Promise<SignalLogSummary> {
    const response = await apiClient.get<ApiResponse<SignalLogSummary>>(`/signals/${id}`)
    return response.data.data
  },

  async getByStrategy(strategyId: string, params?: { page?: number; pageSize?: number }): Promise<SignalListResponse> {
    const response = await apiClient.get<ApiResponse<SignalListResponse>>(`/signals`, {
      params: { ...params, strategyId }
    })
    return response.data.data
  },
}

// Export token management
export { getAccessToken, setTokens, clearTokens, isTokenExpired }

// Export axios instance for custom requests
export { apiClient }


// Extended position type for UI
export interface PositionWithPortfolio extends Position {
  portfolio?: {
    id: string;
    name: string;
  };
  provider?: {
    id: string;
    name: string;
  };
}

// Export for use in other files
export type { PositionWithPortfolio as default }
