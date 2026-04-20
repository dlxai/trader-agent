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
  PriceQuote,
  Candle,
  UserSettings,
  DashboardStats,
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
    const response = await apiClient.post<ApiResponse<{ tokens: AuthTokens; user: User }>>('/auth/login', credentials)
    const { tokens, user } = response.data.data
    setTokens(tokens)
    return { tokens, user }
  },

  async register(credentials: RegisterCredentials): Promise<{ tokens: AuthTokens; user: User }> {
    const response = await apiClient.post<ApiResponse<{ tokens: AuthTokens; user: User }>>('/auth/register', credentials)
    const { tokens, user } = response.data.data
    setTokens(tokens)
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
    const response = await apiClient.get<ApiResponse<User>>('/auth/me')
    return response.data.data
  },
}

// Portfolios API
export const portfoliosApi = {
  async getAll(): Promise<Portfolio[]> {
    const response = await apiClient.get<ApiResponse<Portfolio[]>>('/portfolios')
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
export const positionsApi = {
  async getAll(): Promise<PositionWithPortfolio[]> {
    const response = await apiClient.get<ApiResponse<PositionWithPortfolio[]>>('/positions')
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
export const ordersApi = {
  async getAll(params?: {
    portfolioId?: string
    status?: string
    side?: string
    from?: string
    to?: string
    limit?: number
    offset?: number
  }): Promise<{ orders: Order[]; total: number }> {
    const response = await apiClient.get<ApiResponse<{ orders: Order[]; total: number }>>('/orders', { params })
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

// Market data API
export const marketDataApi = {
  async getQuote(symbol: string, exchange?: string): Promise<PriceQuote> {
    const response = await apiClient.get<ApiResponse<PriceQuote>>('/market/quote', {
      params: { symbol, exchange },
    })
    return response.data.data
  },

  async getQuotes(symbols: string[]): Promise<PriceQuote[]> {
    const response = await apiClient.get<ApiResponse<PriceQuote[]>>('/market/quotes', {
      params: { symbols: symbols.join(',') },
    })
    return response.data.data
  },

  async getCandles(
    symbol: string,
    params: {
      exchange?: string
      interval?: '1m' | '5m' | '15m' | '1h' | '4h' | '1d' | '1w'
      from?: string
      to?: string
      limit?: number
    }
  ): Promise<Candle[]> {
    const response = await apiClient.get<ApiResponse<Candle[]>>('/market/candles', {
      params: { symbol, ...params },
    })
    return response.data.data
  },

  async searchSymbols(query: string): Promise<{
    symbol: string
    name: string
    exchange: string
    type: string
  }[]> {
    const response = await apiClient.get<ApiResponse<{
      symbol: string
      name: string
      exchange: string
      type: string
    }[]>>('/market/search', {
      params: { q: query },
    })
    return response.data.data
  },
}

// Dashboard API
export const dashboardApi = {
  async getStats(): Promise<DashboardStats> {
    const response = await apiClient.get<ApiResponse<DashboardStats>>('/dashboard/stats')
    return response.data.data
  },

  async getPortfolioHistory(params?: { from?: string; to?: string }): Promise<{
    date: string
    value: number
    pnl: number
  }[]> {
    const response = await apiClient.get<ApiResponse<{
      date: string
      value: number
      pnl: number
    }[]>>('/dashboard/history', { params })
    return response.data.data
  },

  async getAssetAllocation(): Promise<{
    symbol: string
    value: number
    percentage: number
  }[]> {
    const response = await apiClient.get<ApiResponse<{
      symbol: string
      value: number
      percentage: number
    }[]>>('/dashboard/allocation')
    return response.data.data
  },

  async getRecentActivity(): Promise<{
    id: string
    type: 'trade' | 'order' | 'deposit' | 'withdrawal'
    description: string
    amount?: number
    timestamp: string
  }[]> {
    const response = await apiClient.get<ApiResponse<{
      id: string
      type: 'trade' | 'order' | 'deposit' | 'withdrawal'
      description: string
      amount?: number
      timestamp: string
    }[]>>('/dashboard/activity')
    return response.data.data
  },
}

// Settings API
export const settingsApi = {
  async getSettings(): Promise<UserSettings> {
    const response = await apiClient.get<ApiResponse<UserSettings>>('/settings')
    return response.data.data
  },

  async updateSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
    const response = await apiClient.patch<ApiResponse<UserSettings>>('/settings', settings)
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
