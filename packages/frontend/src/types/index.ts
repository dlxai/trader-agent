// User types
export interface User {
  id: string;
  email: string;
  username: string;
  name?: string;
  role?: 'admin' | 'user';
  is_active?: boolean;
  is_verified?: boolean;
  is_superuser?: boolean;
  created_at?: string;
  updated_at?: string;
  last_login?: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  username: string;
  password: string;
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
  provider_type: string;
  type?: string;
  api_key?: string;
  api_base?: string;
  api_version?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  is_default?: boolean;
}

// Wallet types (Polymarket)
export interface Wallet {
  id: string;
  user_id: string;
  name: string;
  address?: string;
  proxy_wallet_address?: string;
  is_active: boolean;
  is_default: boolean;
  status: 'active' | 'inactive' | 'error';
  last_used_at?: string;
  last_error?: string;
  error_count: number;
  usdc_balance?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateWalletRequest {
  name: string;
  private_key: string;
  proxy_wallet_address?: string;
  is_default?: boolean;
}

export interface UpdateWalletRequest {
  name?: string;
  private_key?: string;
  proxy_wallet_address?: string;
  is_active?: boolean;
  is_default?: boolean;
}

export interface WalletTestResult {
  success: boolean;
  message: string;
  address?: string;
  balance?: string;
  error?: string;
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
  error?: { message?: string } | null;
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

// AI Model Configuration
export interface AIModelConfig {
  id: string
  name: string
  provider: string
  enabled: boolean
  api_key?: string
  custom_api_url?: string
  custom_model_name?: string
}

// Available AI models (from backend reference)
export const AVAILABLE_AI_MODELS: AIModelConfig[] = [
  { id: 'deepseek', name: 'DeepSeek V3', provider: 'deepseek', enabled: false },
  { id: 'deepseek-reasoner', name: 'DeepSeek R1', provider: 'deepseek', enabled: false },
  { id: 'qwen-turbo', name: 'Qwen Turbo', provider: 'qwen', enabled: false },
  { id: 'qwen-flash', name: 'Qwen Flash', provider: 'qwen', enabled: false },
  { id: 'openai', name: 'OpenAI', provider: 'openai', enabled: false },
  { id: 'claude', name: 'Claude', provider: 'claude', enabled: false },
  { id: 'gemini', name: 'Gemini', provider: 'gemini', enabled: false },
  { id: 'grok', name: 'Grok', provider: 'grok', enabled: false },
  { id: 'kimi', name: 'Kimi', provider: 'kimi', enabled: false },
  { id: 'minimax', name: 'MiniMax', provider: 'minimax', enabled: false },
]

// Provider API URLs
export const AI_PROVIDER_URLS: Record<string, string> = {
  deepseek: 'https://platform.deepseek.com/api_keys',
  qwen: 'https://dashscope.console.aliyun.com/apiKey',
  openai: 'https://platform.openai.com/api-keys',
  claude: 'https://console.anthropic.com/settings/keys',
  gemini: 'https://aistudio.google.com/app/apikey',
  grok: 'https://console.x.ai/',
  kimi: 'https://platform.moonshot.ai/console/api-keys',
  minimax: 'https://platform.minimax.io',
}

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
  // AI Models
  ai_models?: AIModelConfig[];
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

// Strategy types (新增)
export interface Strategy {
  id: string;
  user_id: string;
  portfolio_id: string;
  provider_id?: string;

  name: string;
  description?: string;
  type: string;
  is_active: boolean;
  is_paused: boolean;
  status: 'draft' | 'testing' | 'active' | 'paused' | 'stopped' | 'archived';

  // AI 配置
  system_prompt?: string;
  custom_prompt?: string;
  data_sources?: StrategyDataSources;
  trigger?: StrategyTrigger;
  filters?: StrategyFilters;
  position_monitor?: StrategyPositionMonitor;
  order_config?: StrategyOrderConfig;
  risk_config?: StrategyRiskConfig;

  // 下单金额
  min_order_size: number;
  max_order_size: number;

  // 市场过滤
  market_filter_days?: number;
  market_filter_type?: '24h' | '7d' | 'custom';

  // 执行间隔
  run_interval_minutes: number;
  last_run_at?: string;
  total_runs: number;

  // 风险控制
  max_position_size?: number;
  max_open_positions?: number;
  stop_loss_percent?: number;
  take_profit_percent?: number;

  // 绩效
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  sharpe_ratio?: number;

  created_at: string;
  updated_at: string;
}

export interface CreateStrategyRequest {
  name: string;
  description?: string;
  portfolio_id?: string;
  provider_id?: string;
  type?: string;
  system_prompt?: string;
  custom_prompt?: string;
  data_sources?: Record<string, unknown>;
  trigger?: Record<string, unknown>;
  filters?: Record<string, unknown>;
  position_monitor?: Record<string, unknown>;
  order?: Record<string, unknown>;
  risk?: Record<string, unknown>;
  min_order_size: number;
  max_order_size: number;
  default_amount?: number;
  market_filter_days?: number;
  market_filter_type?: string;
  run_interval_minutes?: number;
  max_position_size?: number;
  max_open_positions?: number;
  max_positions?: number;
  min_risk_reward_ratio?: number;
  max_margin_usage?: number;
  min_position_size?: number;
  stop_loss_percent?: number;
  take_profit_percent?: number;
  order_type?: string;
  time_in_force?: string;
  slippage_tolerance?: number;
  allowed_markets?: string[];
  excluded_markets?: string[];
  min_liquidity?: number;
  max_spread_percent?: number;
  trading_schedule?: Record<string, unknown>;
  timezone?: string;
}

export interface UpdateStrategyRequest {
  name?: string;
  description?: string;
  provider_id?: string;
  system_prompt?: string;
  custom_prompt?: string;
  data_sources?: StrategyDataSources;
  trigger?: StrategyTrigger;
  filters?: StrategyFilters;
  position_monitor?: StrategyPositionMonitor;
  order_config?: StrategyOrderConfig;
  risk_config?: StrategyRiskConfig;
  min_order_size?: number;
  max_order_size?: number;
  market_filter_days?: number;
  market_filter_type?: string;
  run_interval_minutes?: number;
  max_position_size?: number;
  max_open_positions?: number;
  stop_loss_percent?: number;
  take_profit_percent?: number;
  is_active?: boolean;
}

export interface StrategySummary {
  id: string;
  name: string;
  type: string;
  is_active: boolean;
  status: string;
  portfolio_id?: string;
  provider_id?: string;
  min_order_size: number;
  max_order_size: number;
  total_trades: number;
  total_pnl: number;
  total_pnl_percent?: number;
}

// Signal types (新增)
export interface SignalLog {
  id: string;
  user_id: string;
  portfolio_id?: string;
  strategy_id?: string;
  position_id?: string;

  signal_id: string;
  signal_type: 'buy' | 'sell' | 'hold' | 'close';
  confidence: number;
  side: 'yes' | 'no';

  size?: number;
  stop_loss_price?: number;
  take_profit_price?: number;
  risk_reward_ratio?: number;

  status: 'pending' | 'analyzing' | 'risk_check' | 'approved' | 'rejected' | 'executed' | 'expired';

  // AI 思维链 (新增)
  ai_thinking?: string;
  ai_model?: string;
  ai_tokens_used?: number;
  ai_duration_ms?: number;
  input_summary?: Record<string, unknown>;
  decision_details?: Record<string, unknown>;
  signal_reason?: string;
  technical_indicators?: Record<string, unknown>;

  created_at: string;
  updated_at: string;
}

// 数据源配置
export interface StrategyDataSources {
  enable_market_data: boolean;
  enable_activity: boolean;
  enable_sports_score: boolean;
}

// 触发条件
export interface StrategyTrigger {
  price_change_threshold: number;
  activity_netflow_threshold: number;
  min_trigger_interval: number;
  scan_interval: number;
}

// 信号过滤
export interface StrategyFilters {
  min_confidence: number;
  min_price: number;
  max_price: number;
  max_spread: number;
  max_slippage: number;
  dead_zone_enabled: boolean;
  dead_zone_min: number;
  dead_zone_max: number;
  keywords_exclude: string[];

  // 到期时间策略（由 ExpiryPolicy 统一处理）
  min_hours_to_expiry: number;
  max_days_to_expiry: number;
  avoid_last_minutes_before_expiry: number;
}

// 持仓监控
export interface StrategyPositionMonitor {
  enable_stop_loss: boolean;
  stop_loss_percent: number;
  enable_take_profit: boolean;
  take_profit_price: number;
  enable_trailing_stop: boolean;
  trailing_stop_percent: number;
  enable_auto_redeem: boolean;
}

// 下单配置
export interface StrategyOrderConfig {
  min_order_size: number;
  max_order_size: number;
  default_amount: number;
}

// 风险控制
export interface StrategyRiskConfig {
  max_positions: number;
  min_risk_reward_ratio: number;
  max_margin_usage: number;
  min_position_size: number;
  max_position_size?: number;
}
