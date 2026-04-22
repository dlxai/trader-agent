/** Strategy default configuration constants */

export const DEFAULT_SYSTEM_PROMPT = `# 你是一个专业的 Polymarket 交易员

你的任务是根据市场数据做出交易决策。

## 交易原则

1. 只在多个信号共振时入场
2. 重视基本面（比分、新闻） > 技术面（价格波动）
3. 价格剧烈波动时，先检查基本面是否有变化
4. 严格止损，不要扛单

## 分析优先级

1. Sports 市场：先看比分，再看价格
2. 其他市场：先看 Activity 流向，再看价格
3. 价格异常波动时，找出背后原因

## 输出格式

请按以下格式输出决策：
{
  "action": "buy|sell|hold",
  "side": "yes|no",
  "confidence": 0-100,
  "reasoning": "简短理由",
  "stop_loss": 0-1,
  "take_profit": 0-1,
  "risk_reward": number
}
`;

export const DEFAULT_CUSTOM_PROMPT = `请分析以下市场数据，给出交易决策：

当前价格: {price}
24h 变化: {change}%
Activity: 净流入 {netflow}
{free_text}

请判断是否应该买入/卖出/持有。
`;

export const DEFAULT_DATA_SOURCES = {
  enable_market_data: true,
  enable_activity: true,
  enable_sports_score: true,
};

export const DEFAULT_TRIGGER = {
  price_change_threshold: 5,
  activity_netflow_threshold: 1000,
  min_trigger_interval: 5,
  scan_interval: 15,
};

export const DEFAULT_FILTERS = {
  min_confidence: 40,
  min_price: 0.5,
  max_price: 0.99,
  max_spread: 3,
  max_slippage: 2,
  dead_zone_enabled: true,
  dead_zone_min: 0.7,
  dead_zone_max: 0.8,
  keywords_exclude: ['o/u', 'spread'],

  // 到期时间过滤：超过这个小时数的市场不交易
  max_hours_to_expiry: 6,  // 通用：6小时内
};

// 尾盘策略预设值
export const TAIL_FILTERS = {
  ...DEFAULT_FILTERS,
  min_price: 0.95,
  max_price: 0.99,
  max_hours_to_expiry: 2,  // 尾盘：2小时内
};

// Sports 策略预设值（更关注比分和 Activity）
export const SPORTS_FILTERS = {
  ...DEFAULT_FILTERS,
  min_price: 0.3,
  max_price: 0.95,
  max_hours_to_expiry: 4,
  dead_zone_enabled: false,  // Sports 市场不需要死区
};

export const SPORTS_TRIGGER = {
  ...DEFAULT_TRIGGER,
  price_change_threshold: 3,  // 更敏感
  min_trigger_interval: 3,    // 更频繁
};

// 策略模板类型
export type StrategyTemplateType = 'generic' | 'tail' | 'sports';

export const STRATEGY_TEMPLATES: Record<StrategyTemplateType, {
  name: string;
  description: string;
  filters: typeof DEFAULT_FILTERS;
  trigger: typeof DEFAULT_TRIGGER;
}> = {
  generic: {
    name: '通用策略',
    description: '适用于大多数市场，基于价格和 Activity 触发',
    filters: DEFAULT_FILTERS,
    trigger: DEFAULT_TRIGGER,
  },
  tail: {
    name: '尾盘策略',
    description: '在市场到期前 2 小时内交易，高概率信号',
    filters: TAIL_FILTERS,
    trigger: DEFAULT_TRIGGER,
  },
  sports: {
    name: 'Sports 策略',
    description: '专注于体育赛事市场，监控比分变化',
    filters: SPORTS_FILTERS,
    trigger: SPORTS_TRIGGER,
  },
};

export const DEFAULT_ORDER = {
  min_order_size: 10,
  max_order_size: 50,
  default_amount: 5,
};

export const DEFAULT_POSITION_MONITOR = {
  enable_stop_loss: true,
  stop_loss_percent: -15,
  enable_take_profit: true,
  take_profit_price: 0.999,
  enable_trailing_stop: true,
  trailing_stop_percent: 5,
  enable_auto_redeem: true,
};

export const DEFAULT_RISK = {
  max_positions: 3,
  min_risk_reward_ratio: 2.0,
  max_margin_usage: 0.9,
  min_position_size: 12,
};

export const DEFAULT_STRATEGY_CONFIG = {
  data_sources: DEFAULT_DATA_SOURCES,
  trigger: DEFAULT_TRIGGER,
  filters: DEFAULT_FILTERS,
  order: DEFAULT_ORDER,
  position_monitor: DEFAULT_POSITION_MONITOR,
  risk: DEFAULT_RISK,
};