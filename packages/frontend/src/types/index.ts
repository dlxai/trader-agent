// User types
export interface User {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'user';
  createdAt: string;
  updatedAt: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  password: string;
  name: string;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
}

// Portfolio types
export interface Portfolio {
  id: string;
  name: string;
  description?: string;
  userId: string;
  totalValue: number;
  totalCost: number;
  unrealizedPnl: number;
  realizedPnl: number;
  pnlPercentage: number;
  createdAt: string;
  updatedAt: string;
}

export interface CreatePortfolioRequest {
  name: string;
  description?: string;
}

export interface UpdatePortfolioRequest {
  name?: string;
  description?: string;
}

// Position types
export interface Position {
  id: string;
  portfolioId: string;
  symbol: string;
  exchange: string;
  side: 'long' | 'short';
  quantity: number;
  avgCost: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  realizedPnl: number;
  pnlPercentage: number;
  createdAt: string;
  updatedAt: string;
}

export interface PositionWithPortfolio extends Position {
  portfolio: Portfolio;
}

// Order types
export interface Order {
  id: string;
  portfolioId: string;
  positionId?: string;
  symbol: string;
  exchange: string;
  side: 'buy' | 'sell';
  type: 'market' | 'limit' | 'stop' | 'stop_limit';
  status: 'pending' | 'open' | 'filled' | 'partial' | 'cancelled' | 'rejected' | 'expired';
  quantity: number;
  filledQuantity: number;
  price?: number;
  stopPrice?: number;
  avgFillPrice?: number;
  commission?: number;
  createdAt: string;
  updatedAt: string;
}

export interface CreateOrderRequest {
  portfolioId: string;
  symbol: string;
  exchange: string;
  side: 'buy' | 'sell';
  type: 'market' | 'limit' | 'stop' | 'stop_limit';
  quantity: number;
  price?: number;
  stopPrice?: number;
}

// Provider types
export interface Provider {
  id: string;
  name: string;
  type: 'exchange' | 'broker' | 'data';
  status: 'active' | 'inactive' | 'error';
  config: Record<string, unknown>;
  credentials?: Record<string, string>;
  lastConnectedAt?: string;
  lastError?: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreateProviderRequest {
  name: string;
  type: 'exchange' | 'broker' | 'data';
  config: Record<string, unknown>;
  credentials?: Record<string, string>;
}

// Market data types
export interface PriceQuote {
  symbol: string;
  exchange: string;
  bid: number;
  ask: number;
  last: number;
  volume24h: number;
  change24h: number;
  change24hPercent: number;
  timestamp: string;
}

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// WebSocket message types
export type WebSocketMessage =
  | PriceUpdateMessage
  | OrderUpdateMessage
  | PositionUpdateMessage
  | TradeMessage
  | SystemMessage;

export interface PriceUpdateMessage {
  type: 'price';
  data: PriceQuote;
}

export interface OrderUpdateMessage {
  type: 'order';
  data: Order;
}

export interface PositionUpdateMessage {
  type: 'position';
  data: Position;
}

export interface TradeMessage {
  type: 'trade';
  data: {
    id: string;
    orderId: string;
    symbol: string;
    side: 'buy' | 'sell';
    quantity: number;
    price: number;
    commission: number;
    timestamp: string;
  };
}

export interface SystemMessage {
  type: 'system';
  data: {
    event: 'connected' | 'disconnected' | 'error' | 'maintenance';
    message?: string;
    timestamp: string;
  };
}

// API response types
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  meta?: {
    page?: number;
    limit?: number;
    total?: number;
  };
}

export interface ApiError {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, string[]>;
  };
}

// Settings types
export interface UserSettings {
  theme: 'dark' | 'light' | 'system';
  language: string;
  timezone: string;
  dateFormat: string;
  timeFormat: '12h' | '24h';
  notifications: {
    email: boolean;
    push: boolean;
    trades: boolean;
    orders: boolean;
    priceAlerts: boolean;
  };
  trading: {
    confirmBeforeTrade: boolean;
    defaultOrderType: 'market' | 'limit';
    quantityStep: number;
  };
  dashboard: {
    widgets: string[];
    layout: 'compact' | 'comfortable';
  };
}

// Dashboard types
export interface DashboardStats {
  totalValue: number;
  totalPnl: number;
  pnlPercentage: number;
  activePositions: number;
  pendingOrders: number;
  todayTrades: number;
  todayVolume: number;
}

export interface ChartDataPoint {
  timestamp: string;
  value: number;
  pnl?: number;
}

export interface AssetAllocation {
  symbol: string;
  value: number;
  percentage: number;
  color: string;
}
