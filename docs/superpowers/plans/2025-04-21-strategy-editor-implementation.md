# Strategy Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善策略编辑页面，添加完整的策略配置功能（数据源、触发条件、信号过滤、持仓监控、风险控制），包含默认配置模板。

**Architecture:** 前端重构策略创建/编辑对话框为多 Tab 结构，后端扩展 Schema 支持新字段，前端添加默认配置常量和 Provider 选择功能。

**Tech Stack:** React (TanStack Query), FastAPI (Pydantic), TypeScript

---

## 文件结构

### 后端
- `packages/backend-py/src/schemas/strategy.py` - 扩展 StrategyCreate/StrategyUpdate Schema
- `packages/backend-py/src/constants/strategy.py` - 新建默认配置常量

### 前端
- `packages/frontend/src/types/index.ts` - 扩展 Strategy 类型定义
- `packages/frontend/src/constants/strategy.ts` - 新建默认配置常量
- `packages/frontend/src/lib/api.ts` - 更新 strategiesApi 类型
- `packages/frontend/src/pages/Strategies.tsx` - 重构为多 Tab 编辑对话框
- `packages/frontend/src/components/strategy/` - 新建策略编辑器组件目录

---

## Task 1: 扩展后端 Strategy Schema

**Files:**
- Modify: `packages/backend-py/src/schemas/strategy.py`

- [ ] **Step 1: 添加新的 Schema 类用于信号过滤和持仓监控**

在 `strategy.py` 文件末尾添加：

```python
class StrategyFilters(BaseSchema):
    """信号过滤配置"""
    min_confidence: int = Field(default=40, ge=0, le=100)
    min_price: Decimal = Field(default=Decimal("0.50"), ge=0, le=1)
    max_price: Decimal = Field(default=Decimal("0.99"), ge=0, le=1)
    max_spread: Decimal = Field(default=Decimal("3"), ge=0, le=100)
    max_slippage: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    dead_zone_enabled: bool = Field(default=True)
    dead_zone_min: Decimal = Field(default=Decimal("0.70"), ge=0, le=1)
    dead_zone_max: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)
    keywords_exclude: List[str] = Field(default_factory=lambda: ["o/u", "spread"])


class StrategyPositionMonitor(BaseSchema):
    """持仓监控配置"""
    enable_stop_loss: bool = Field(default=True)
    stop_loss_percent: Decimal = Field(default=Decimal("-15"), le=0)
    enable_take_profit: bool = Field(default=True)
    take_profit_price: Decimal = Field(default=Decimal("0.999"), ge=0, le=1)
    enable_trailing_stop: bool = Field(default=True)
    trailing_stop_percent: Decimal = Field(default=Decimal("5"), ge=0, le=100)
    enable_auto_redeem: bool = Field(default=True)


class StrategyTrigger(BaseSchema):
    """触发条件配置"""
    price_change_threshold: Decimal = Field(default=Decimal("5"), ge=0, le=100)
    activity_netflow_threshold: Decimal = Field(default=Decimal("1000"), ge=0)
    min_trigger_interval: int = Field(default=5, ge=1, le=1440)
    scan_interval: int = Field(default=15, ge=1, le=1440)


class StrategyDataSources(BaseSchema):
    """数据源配置"""
    enable_market_data: bool = Field(default=True)
    enable_activity: bool = Field(default=True)
    enable_sports_score: bool = Field(default=True)
```

- [ ] **Step 2: 在 StrategyBase 中添加新字段**

在 `StrategyBase` 类的 `data_sources` 字段后添加：

```python
    # 触发条件（新增）
    trigger: Optional[StrategyTrigger] = None

    # 信号过滤（新增）
    filters: Optional[StrategyFilters] = None

    # 持仓监控（新增）
    position_monitor: Optional[StrategyPositionMonitor] = None

    # 下单默认金额（新增）
    default_amount: Decimal = Field(default=Decimal("5"), ge=0)

    # 风险控制扩展（新增）
    min_risk_reward_ratio: Optional[Decimal] = Field(default=Decimal("2.0"), ge=0)
    max_margin_usage: Decimal = Field(default=Decimal("0.9"), ge=0, le=1)
    min_position_size: Decimal = Field(default=Decimal("12"), ge=0)
```

- [ ] **Step 3: 在 StrategyUpdate 中添加对应字段**

在 `StrategyUpdate` 类中添加同样的字段（使用 Optional）：

```python
    # 触发条件
    trigger: Optional[StrategyTrigger] = None

    # 信号过滤
    filters: Optional[StrategyFilters] = None

    # 持仓监控
    position_monitor: Optional[StrategyPositionMonitor] = None

    # 下单默认金额
    default_amount: Optional[Decimal] = Field(None, ge=0)

    # 风险控制扩展
    min_risk_reward_ratio: Optional[Decimal] = Field(None, ge=0)
    max_margin_usage: Optional[Decimal] = Field(None, ge=0, le=1)
    min_position_size: Optional[Decimal] = Field(None, ge=0)
```

- [ ] **Step 4: 提交**

```bash
git add packages/backend-py/src/schemas/strategy.py
git commit -m "feat: extend Strategy schemas with filters, trigger, and position_monitor"
```

---

## Task 2: 创建后端默认配置常量

**Files:**
- Create: `packages/backend-py/src/constants/strategy.py`

- [ ] **Step 1: 创建默认配置常量文件**

```python
"""Strategy default configuration constants."""

from decimal import Decimal
from typing import Dict, Any

# 默认 System Prompt
DEFAULT_SYSTEM_PROMPT = """# 你是一个专业的 Polymarket 交易员

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
"""

# 默认 Custom Prompt
DEFAULT_CUSTOM_PROMPT = """请分析以下市场数据，给出交易决策：

当前价格: {price}
24h 变化: {change}%
Activity: 净流入 {netflow}
{free_text}

请判断是否应该买入/卖出/持有。
"""

# 默认配置模板
DEFAULT_STRATEGY_CONFIG: Dict[str, Any] = {
    "data_sources": {
        "enable_market_data": True,
        "enable_activity": True,
        "enable_sports_score": True,
    },
    "trigger": {
        "price_change_threshold": 5,
        "activity_netflow_threshold": 1000,
        "min_trigger_interval": 5,
        "scan_interval": 15,
    },
    "filters": {
        "min_confidence": 40,
        "min_price": 0.50,
        "max_price": 0.99,
        "max_spread": 3,
        "max_slippage": 2,
        "dead_zone_enabled": True,
        "dead_zone_min": 0.70,
        "dead_zone_max": 0.80,
        "keywords_exclude": ["o/u", "spread"],
    },
    "order": {
        "min_order_size": 10,
        "max_order_size": 50,
        "default_amount": 5,
    },
    "position_monitor": {
        "enable_stop_loss": True,
        "stop_loss_percent": -15,
        "enable_take_profit": True,
        "take_profit_price": 0.999,
        "enable_trailing_stop": True,
        "trailing_stop_percent": 5,
        "enable_auto_redeem": True,
    },
    "risk": {
        "max_positions": 3,
        "min_risk_reward_ratio": 2.0,
        "max_margin_usage": 0.9,
        "min_position_size": 12,
    },
}
```

- [ ] **Step 2: 提交**

```bash
git add packages/backend-py/src/constants/strategy.py
git commit -m "feat: add strategy default configuration constants"
```

---

## Task 3: 扩展前端 Strategy 类型定义

**Files:**
- Modify: `packages/frontend/src/types/index.ts`

- [ ] **Step 1: 扩展 Strategy 类型**

在 `types/index.ts` 中替换现有的 Strategy 相关类型：

```typescript
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

// 信号过滤（来自 polymarket-agent）
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
}

// 持仓监控（来自 polymarket-agent）
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
}

// 完整策略配置
export interface StrategyConfig {
  data_sources: StrategyDataSources;
  trigger: StrategyTrigger;
  filters: StrategyFilters;
  order: StrategyOrderConfig;
  position_monitor: StrategyPositionMonitor;
  risk: StrategyRiskConfig;
}

// Strategy types
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

  // 触发条件
  trigger?: StrategyTrigger;

  // 信号过滤
  filters?: StrategyFilters;

  // 持仓监控
  position_monitor?: StrategyPositionMonitor;

  // 下单金额
  min_order_size: number;
  max_order_size: number;
  default_amount?: number;

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
  min_risk_reward_ratio?: number;
  max_margin_usage?: number;
  min_position_size?: number;

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
  portfolio_id: string;
  provider_id?: string;
  system_prompt?: string;
  custom_prompt?: string;
  data_sources?: StrategyDataSources;
  trigger?: StrategyTrigger;
  filters?: StrategyFilters;
  position_monitor?: StrategyPositionMonitor;
  min_order_size: number;
  max_order_size: number;
  default_amount?: number;
  market_filter_days?: number;
  market_filter_type?: string;
  run_interval_minutes?: number;
  max_position_size?: number;
  max_open_positions?: number;
  stop_loss_percent?: number;
  take_profit_percent?: number;
  min_risk_reward_ratio?: number;
  max_margin_usage?: number;
  min_position_size?: number;
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
  min_order_size?: number;
  max_order_size?: number;
  default_amount?: number;
  market_filter_days?: number;
  market_filter_type?: string;
  run_interval_minutes?: number;
  max_position_size?: number;
  max_open_positions?: number;
  stop_loss_percent?: number;
  take_profit_percent?: number;
  min_risk_reward_ratio?: number;
  max_margin_usage?: number;
  min_position_size?: number;
  is_active?: boolean;
}
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/types/index.ts
git commit -m "feat: extend Strategy types with full configuration"
```

---

## Task 4: 创建前端默认配置常量

**Files:**
- Create: `packages/frontend/src/constants/strategy.ts`

- [ ] **Step 1: 创建默认配置常量**

```typescript
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
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/constants/strategy.ts
git commit -m "feat: add frontend strategy default configuration constants"
```

---

## Task 5: 重构 Strategies.tsx 页面

**Files:**
- Modify: `packages/frontend/src/pages/Strategies.tsx`

- [ ] **Step 1: 添加导入和类型**

在文件顶部添加：

```typescript
import {
  DEFAULT_SYSTEM_PROMPT,
  DEFAULT_CUSTOM_PROMPT,
  DEFAULT_DATA_SOURCES,
  DEFAULT_TRIGGER,
  DEFAULT_FILTERS,
  DEFAULT_ORDER,
  DEFAULT_POSITION_MONITOR,
  DEFAULT_RISK,
} from '@/constants/strategy'
import { providersApi } from '@/lib/api'
import type { Provider, CreateStrategyRequest, StrategyDataSources, StrategyTrigger, StrategyFilters, StrategyPositionMonitor } from '@/types'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Switch } from '@/components/ui/Switch'
```

- [ ] **Step 2: 添加状态变量**

在组件内添加：

```typescript
const [selectedTab, setSelectedTab] = useState('basic')
const [providers, setProviders] = useState<Provider[]>([])

// 完整配置状态
const [config, setConfig] = useState({
  data_sources: DEFAULT_DATA_SOURCES,
  trigger: DEFAULT_TRIGGER,
  filters: DEFAULT_FILTERS,
  order: DEFAULT_ORDER,
  position_monitor: DEFAULT_POSITION_MONITOR,
  risk: DEFAULT_RISK,
  system_prompt: DEFAULT_SYSTEM_PROMPT,
  custom_prompt: DEFAULT_CUSTOM_PROMPT,
})
```

- [ ] **Step 3: 获取 Providers 数据**

添加 query：

```typescript
const { data: providersResponse } = useQuery({
  queryKey: ['providers'],
  queryFn: () => providersApi.getAll(),
})

useEffect(() => {
  if (providersResponse?.items) {
    setProviders(providersResponse.items)
  }
}, [providersResponse])
```

- [ ] **Step 4: 重构创建对话框表单为 Tab 结构**

将现有的表单内容重构为以下结构：

```tsx
{/* Tab 切换 */}
<div className="flex border-b mb-4">
  {['basic', 'data', 'trigger', 'filters', 'ai', 'monitor', 'risk'].map((tab) => (
    <button
      key={tab}
      onClick={() => setSelectedTab(tab)}
      className={`px-4 py-2 text-sm font-medium ${
        selectedTab === tab
          ? 'border-b-2 border-emerald-500 text-emerald-600'
          : 'text-muted-foreground'
      }`}
    >
      {tabLabels[tab]}
    </button>
  ))}
</div>

{/* Tab 内容 */}
{selectedTab === 'basic' && (
  // 基础信息：名称、描述、Portfolio 选择
)}

{selectedTab === 'data' && (
  // 数据源开关
)}

{selectedTab === 'trigger' && (
  // 触发条件
)}

{selectedTab === 'filters' && (
  // 信号过滤
)}

{selectedTab === 'ai' && (
  // AI 配置：Provider 选择、Prompt
)}

{selectedTab === 'monitor' && (
  // 持仓监控
)}

{selectedTab === 'risk' && (
  // 风险控制
)}
```

- [ ] **Step 5: 实现各个 Tab 的表单字段**

**Tab 1: 基础信息**
- Input: 策略名称
- Input: 描述
- Select: 关联 Portfolio

**Tab 2: 数据源**
- Switch: 市场价格
- Switch: Activity 数据
- Switch: Sports 比分

**Tab 3: 触发条件**
- Input (number): 价格波动阈值
- Input (number): Activity 净流入阈值
- Input (number): 最小触发间隔
- Input (number): 定时扫描间隔

**Tab 4: 信号过滤**
- Input (number): 最小置信度
- Input (number): 最小价格
- Input (number): 最大价格
- Input (number): 最大价差
- Input (number): 最大滑点
- Switch: 启用死亡区间过滤
- Input (number): 死亡区间最小
- Input (number): 死亡区间最大
- Input: 排除关键词（逗号分隔）

**Tab 5: AI 配置**
- Select: 选择 Provider（从 providers 列表）
- Textarea: System Prompt
- Textarea: Custom Prompt

**Tab 6: 持仓监控**
- Switch: 启用止损
- Input (number): 止损百分比
- Switch: 启用止盈
- Input (number): 止盈概率
- Switch: 启用移动止盈
- Input (number): 移动止盈回调
- Switch: 启用自动赎回

**Tab 7: 风险控制**
- Input (number): 最大持仓数
- Input (number): 最小盈亏比
- Input (number): 最大保证金使用率
- Input (number): 最小持仓金额

- [ ] **Step 6: 更新 handleCreate 函数**

```typescript
const handleCreate = (e: React.FormEvent) => {
  e.preventDefault()
  createMutation.mutate({
    ...newStrategy,
    ...config.order,
    default_amount: config.order.default_amount,
    data_sources: config.data_sources,
    trigger: config.trigger,
    filters: config.filters,
    position_monitor: config.position_monitor,
    system_prompt: config.system_prompt,
    custom_prompt: config.custom_prompt,
    min_risk_reward_ratio: config.risk.min_risk_reward_ratio,
    max_margin_usage: config.risk.max_margin_usage,
    min_position_size: config.risk.min_position_size,
    max_open_positions: config.risk.max_positions,
  } as CreateStrategyRequest)
}
```

- [ ] **Step 7: 提交**

```bash
git add packages/frontend/src/pages/Strategies.tsx
git commit -m "feat: refactor Strategies page with multi-tab editor"
```

---

## Task 6: 检查并确保 UI 组件完整

**Files:**
- Check: `packages/frontend/src/components/ui/`

- [ ] **Step 1: 检查是否已有 Textarea 组件**

如果不存在，创建 `Textarea.tsx`:

```typescript
import * as React from "react"
import { cn } from "@/lib/utils"

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Textarea.displayName = "Textarea"

export { Textarea }
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/components/ui/Textarea.tsx
git commit -m "feat: add Textarea component"
```

---

## Task 7: 更新 strategiesApi 类型

**Files:**
- Modify: `packages/frontend/src/lib/api.ts`

- [ ] **Step 1: 更新 API 函数返回类型**

确保 API 函数正确导入和使用新的类型。

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/lib/api.ts
git commit -m "fix: update strategiesApi types"
```

---

## Task 8: 创建数据源管理服务（支持多数据源扩展）

**Files:**
- Create: `packages/backend-py/src/services/data_source_manager.py`

- [ ] **Step 1: 创建数据源基类和注册机制**

```python
"""Data source manager for shared WebSocket connections."""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from uuid import UUID
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarketData:
    """市场数据"""
    market_id: str
    price: float
    change_24h: float
    volume: float
    timestamp: datetime


@dataclass
class ActivityData:
    """Activity 数据"""
    market_id: str
    netflow: float
    buy_volume: float
    sell_volume: float
    unique_traders: int
    timestamp: datetime


@dataclass
class SportsScoreData:
    """Sports 比分数据"""
    market_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    period: str
    timestamp: datetime


class DataSource(ABC):
    """数据源基类"""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """数据源类型标识"""
        pass

    @abstractmethod
    async def start(self) -> None:
        """启动数据源"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止数据源"""
        pass

    @abstractmethod
    async def get_market_data(self, market_id: str) -> Optional[MarketData]:
        """获取市场数据"""
        pass

    @abstractmethod
    async def get_activity(self, market_id: str) -> Optional[ActivityData]:
        """获取 Activity 数据"""
        pass

    @abstractmethod
    async def get_sports_score(self, market_id: str) -> Optional[SportsScoreData]:
        """获取 Sports 比分"""
        pass


class PolymarketDataSource(DataSource):
    """Polymarket 数据源实现"""

    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        self._proxy_url = proxy_url
        self._running = False
        self._market_cache: Dict[str, MarketData] = {}
        self._activity_cache: Dict[str, ActivityData] = {}
        self._sports_cache: Dict[str, SportsScoreData] = {}
        self._ws_task: Optional[asyncio.Task] = None

    @property
    def source_type(self) -> str:
        return "polymarket"

    async def start(self) -> None:
        """启动 WebSocket 连接"""
        self._running = True
        self._ws_task = asyncio.create_task(self._ws_loop())

    async def stop(self) -> None:
        """停止数据源"""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

    async def _ws_loop(self) -> None:
        """WebSocket 循环"""
        # 实现 WebSocket 连接和消息处理
        pass

    async def get_market_data(self, market_id: str) -> Optional[MarketData]:
        return self._market_cache.get(market_id)

    async def get_activity(self, market_id: str) -> Optional[ActivityData]:
        return self._activity_cache.get(market_id)

    async def get_sports_score(self, market_id: str) -> Optional[SportsScoreData]:
        return self._sports_cache.get(market_id)


# 数据源注册表（支持扩展）
_DATA_SOURCE_REGISTRY: Dict[str, type] = {
    "polymarket": PolymarketDataSource,
}


def register_data_source(source_type: str, source_class: type) -> None:
    """注册新的数据源类型"""
    _DATA_SOURCE_REGISTRY[source_type] = source_class


class DataSourceManager:
    """
    数据源管理器

    按 Portfolio 维度管理数据源，支持多数据源扩展。
    """

    def __init__(self):
        self._sources: Dict[UUID, DataSource] = {}  # portfolio_id -> DataSource
        self._lock = asyncio.Lock()

    async def get_or_create_source(
        self,
        portfolio_id: UUID,
        source_type: str = "polymarket",
        **kwargs
    ) -> DataSource:
        """获取或创建数据源"""
        async with self._lock:
            if portfolio_id not in self._sources:
                source_class = _DATA_SOURCE_REGISTRY.get(source_type)
                if not source_class:
                    raise ValueError(f"Unknown data source type: {source_type}")

                source = source_class(**kwargs)
                await source.start()
                self._sources[portfolio_id] = source

            return self._sources[portfolio_id]

    async def remove_source(self, portfolio_id: UUID) -> None:
        """移除数据源"""
        async with self._lock:
            if portfolio_id in self._sources:
                await self._sources[portfolio_id].stop()
                del self._sources[portfolio_id]

    async def get_all_sources(self) -> List[DataSource]:
        """获取所有数据源"""
        return list(self._sources.values())

    async def close_all(self) -> None:
        """关闭所有数据源"""
        for source in self._sources.values():
            await source.stop()
        self._sources.clear()


# 全局单例
_data_source_manager: Optional[DataSourceManager] = None


def get_data_source_manager() -> DataSourceManager:
    """获取数据源管理器单例"""
    global _data_source_manager
    if _data_source_manager is None:
        _data_source_manager = DataSourceManager()
    return _data_source_manager
```

- [ ] **Step 2: 提交**

```bash
git add packages/backend-py/src/services/data_source_manager.py
git commit -m "feat: add data source manager for shared WebSocket connections"
```

---

## Task 9: 改进 StrategyRunner 使用共享数据源

**Files:**
- Modify: `packages/backend-py/src/services/strategy_runner.py`

- [ ] **Step 1: 重构 StrategyRunner 使用 DataSourceManager**

```python
from src.services.data_source_manager import get_data_source_manager

class StrategyRunner:
    """Strategy execution runner."""

    def __init__(self):
        self._running = False
        self._tasks: dict[UUID, asyncio.Task] = {}
        self._data_source_manager = get_data_source_manager()

    async def start_strategy(self, strategy_id: UUID) -> None:
        """Start running a strategy."""
        if strategy_id in self._tasks:
            return  # Already running

        # 从数据库获取策略和 Portfolio 信息
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()
            if not strategy or not strategy.portfolio_id:
                raise ValueError("Strategy not found or no portfolio")

        # 获取或创建共享数据源
        data_source = await self._data_source_manager.get_or_create_source(
            portfolio_id=strategy.portfolio_id,
            source_type="polymarket",
            proxy_url="http://127.0.0.1:7890"
        )

        task = asyncio.create_task(self._run_strategy_loop(strategy_id, data_source))
        self._tasks[strategy_id] = task

    async def _run_strategy_loop(self, strategy_id: UUID, data_source: DataSource) -> None:
        """Main strategy execution loop with shared data source."""
        # ... 使用 data_source 获取数据，而不是每次创建新的 SDK
```

- [ ] **Step 2: 提交**

```bash
git add packages/backend-py/src/services/strategy_runner.py
git commit -m "refactor: use shared data source in StrategyRunner"
```

---

## 执行顺序

1. Task 1: 扩展后端 Strategy Schema
2. Task 2: 创建后端默认配置常量
3. Task 3: 扩展前端 Strategy 类型定义
4. Task 4: 创建前端默认配置常量
5. Task 5: 重构 Strategies.tsx 页面
6. Task 6: 检查并确保 UI 组件完整
7. Task 7: 更新 strategiesApi 类型

---

## 验证步骤

完成所有任务后，运行以下验证：

```bash
# 后端
cd packages/backend-py
python -c "from src.schemas.strategy import StrategyCreate; print('Backend OK')"

# 前端
cd packages/frontend
npm run build
```

预期：后端无错误，前端构建成功。

---

**Plan complete and saved to `docs/superpowers/plans/2025-04-21-strategy-editor-implementation.md`. Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**