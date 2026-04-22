# AI 交易策略实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 AI 交易策略功能，包括策略管理、AI 分析下单金额计算、止盈止损监控

**Architecture:** 后端在现有 trading_engine 基础上扩展 Strategy CRUD API + 策略执行服务；前端新增策略管理页面和信号日志页面

**Tech Stack:** Python FastAPI, React + TypeScript, SQLAlchemy

---

## 文件结构

```
packages/backend-py/src/
├── models/
│   ├── strategy.py          # 扩展字段
│   └── signal_log.py        # 扩展 AI 思维链字段
├── schemas/
│   └── strategy.py          # 新建: Strategy Schema
├── routers/
│   ├── strategies.py        # 新建: Strategy CRUD + 启动/停止
│   └── signals.py           # 新建: SignalLog API (可选)
├── services/
│   ├── strategy_runner.py   # 新建: 策略执行定时任务
│   └── position_monitor.py  # 新建: 止盈止损监控
└── main.py                  # 注册 Router

packages/frontend/src/
├── types/index.ts           # 扩展 Strategy 类型
├── lib/api.ts               # 新增 strategiesApi
├── pages/
│   ├── Strategies.tsx       # 新建: 策略列表
│   ├── StrategyEditor.tsx   # 新建: 策略编辑器
│   └── Signals.tsx          # 新建: 信号日志
├── router.tsx               # 添加路由
└── components/layout/Sidebar.tsx  # 添加菜单
```

---

## 阶段 1: 后端基础 - Strategy API

### Task 1.1: 扩展 Strategy 模型字段

**Files:**
- Modify: `packages/backend-py/src/models/strategy.py`

- [ ] **Step 1: 添加新字段到 Strategy 模型**

在 `class Strategy` 中添加以下字段（找到约第43行 risk_parameters 后）:

```python
# AI 配置 (新增)
provider_id: Mapped[Optional[UUID]] = mapped_column(
    ForeignKey("providers.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)

# Prompt 配置 (新增)
system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
custom_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

# 数据源配置 (新增, JSON)
data_sources: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

# 下单金额配置 (新增)
min_order_size: Mapped[Decimal] = mapped_column(
    Numeric(19, 8),
    default=Decimal("5"),
)
max_order_size: Mapped[Decimal] = mapped_column(
    Numeric(19, 8),
    default=Decimal("50"),
)

# 市场过滤配置 (新增)
market_filter_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
market_filter_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
# "24h", "7d", "custom"

# 执行间隔配置 (新增)
run_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)

# 运行统计 (新增)
last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
total_runs: Mapped[int] = mapped_column(Integer, default=0)
```

- [ ] **Step 2: 添加 relationship**

找到约第120行的 Relationships 部分，添加：

```python
# 新增关系
provider: Mapped[Optional["Provider"]] = relationship(back_populates="strategies")
```

- [ ] **Step 3: 提交**

```bash
git add packages/backend-py/src/models/strategy.py
git commit -m "feat: extend Strategy model with AI config fields"
```

---

### Task 1.2: 新增 Strategy Schema

**Files:**
- Create: `packages/backend-py/src/schemas/strategy.py`
- Modify: `packages/backend-py/src/schemas/__init__.py`

- [ ] **Step 1: 创建 Strategy Schema**

```python
"""Strategy schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============ Request Schemas ============

class StrategyCreate(BaseModel):
    """Strategy creation request."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    portfolio_id: UUID
    provider_id: Optional[UUID] = None

    # Prompt 配置
    system_prompt: Optional[str] = None
    custom_prompt: Optional[str] = None

    # 数据源配置
    data_sources: Optional[dict] = None

    # 下单金额配置
    min_order_size: Decimal = Field(default=Decimal("5"), ge=0)
    max_order_size: Decimal = Field(default=Decimal("50"), ge=0)

    # 市场过滤
    market_filter_days: Optional[int] = None
    market_filter_type: Optional[str] = None

    # 执行间隔
    run_interval_minutes: int = Field(default=15, ge=1, le=1440)

    # 风险控制 (复用 Portfolio 的)
    max_position_size: Optional[Decimal] = None
    max_open_positions: Optional[int] = None
    stop_loss_percent: Optional[Decimal] = None
    take_profit_percent: Optional[Decimal] = None


class StrategyUpdate(BaseModel):
    """Strategy update request."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    provider_id: Optional[UUID] = None
    system_prompt: Optional[str] = None
    custom_prompt: Optional[str] = None
    data_sources: Optional[dict] = None
    min_order_size: Optional[Decimal] = Field(None, ge=0)
    max_order_size: Optional[Decimal] = Field(None, ge=0)
    market_filter_days: Optional[int] = None
    market_filter_type: Optional[str] = None
    run_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    max_position_size: Optional[Decimal] = None
    max_open_positions: Optional[int] = None
    stop_loss_percent: Optional[Decimal] = None
    take_profit_percent: Optional[Decimal] = None
    is_active: Optional[bool] = None


# ============ Response Schemas ============

class StrategyResponse(BaseModel):
    """Strategy response."""
    id: UUID
    user_id: UUID
    portfolio_id: Optional[UUID]
    provider_id: Optional[UUID]

    name: str
    description: Optional[str]
    type: str
    is_active: bool
    is_paused: bool
    status: str

    # AI 配置
    system_prompt: Optional[str]
    custom_prompt: Optional[str]
    data_sources: Optional[dict]

    # 下单金额
    min_order_size: Decimal
    max_order_size: Decimal

    # 市场过滤
    market_filter_days: Optional[int]
    market_filter_type: Optional[str]

    # 执行间隔
    run_interval_minutes: int
    last_run_at: Optional[datetime]
    total_runs: int

    # 风险控制
    max_position_size: Optional[Decimal]
    max_open_positions: Optional[int]
    stop_loss_percent: Optional[Decimal]
    take_profit_percent: Optional[Decimal]

    # 性能统计
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: Decimal
    sharpe_ratio: Optional[Decimal]

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategySummary(BaseModel):
    """Strategy summary for list view."""
    id: UUID
    name: str
    type: str
    is_active: bool
    status: str
    min_order_size: Decimal
    max_order_size: Decimal
    total_trades: int
    total_pnl: Decimal

    model_config = {"from_attributes": True}


class StrategyListResponse(BaseModel):
    """Strategy list response."""
    items: list[StrategySummary]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 2: 更新 __init__.py**

```python
# 添加到 packages/backend-py/src/schemas/__init__.py
from .strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategySummary,
    StrategyListResponse,
)
```

- [ ] **Step 3: 提交**

```bash
git add packages/backend-py/src/schemas/strategy.py packages/backend-py/src/schemas/__init__.py
git commit -m "feat: add Strategy schemas"
```

---

### Task 1.3: 新增 Strategy Router

**Files:**
- Create: `packages/backend-py/src/routers/strategies.py`
- Modify: `packages/backend-py/src/routers/__init__.py`
- Modify: `packages/backend-py/src/main.py`

- [ ] **Step 1: 创建 Strategy Router**

```python
"""Strategy router."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_session
from src.models.strategy import Strategy
from src.models.portfolio import Portfolio
from src.models.user import User
from src.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategySummary,
    StrategyListResponse,
)
from src.schemas.base import ApiResponse
from src.dependencies import get_current_active_user
from src.core.exceptions import NotFoundError

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.post(
    "",
    response_model=ApiResponse[StrategyResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_strategy(
    request: StrategyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new strategy."""
    # 验证 portfolio 存在
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == request.portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError("Portfolio", f"Portfolio {request.portfolio_id} not found")

    # 创建策略
    strategy = Strategy(
        id=UUID(),
        user_id=current_user.id,
        portfolio_id=request.portfolio_id,
        name=request.name,
        description=request.description,
        type="ai_trading",
        provider_id=request.provider_id,
        system_prompt=request.system_prompt,
        custom_prompt=request.custom_prompt,
        data_sources=request.data_sources or {},
        min_order_size=request.min_order_size,
        max_order_size=request.max_order_size,
        market_filter_days=request.market_filter_days,
        market_filter_type=request.market_filter_type,
        run_interval_minutes=request.run_interval_minutes,
        max_position_size=request.max_position_size or portfolio.max_position_size,
        max_open_positions=request.max_open_positions or portfolio.max_open_positions,
        stop_loss_percent=request.stop_loss_percent or portfolio.stop_loss_percent,
        take_profit_percent=request.take_profit_percent or portfolio.take_profit_percent,
        is_active=False,
        status="draft",
    )

    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
        message="Strategy created successfully",
    )


@router.get(
    "",
    response_model=ApiResponse[StrategyListResponse],
)
async def list_strategies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    portfolio_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List user's strategies."""
    query = select(Strategy).where(Strategy.user_id == current_user.id)

    if portfolio_id:
        query = query.where(Strategy.portfolio_id == portfolio_id)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    strategies = result.scalars().all()

    items = [
        StrategySummary(
            id=s.id,
            name=s.name,
            type=s.type,
            is_active=s.is_active,
            status=s.status,
            min_order_size=s.min_order_size,
            max_order_size=s.max_order_size,
            total_trades=s.total_trades,
            total_pnl=s.total_pnl,
        )
        for s in strategies
    ]

    return ApiResponse(
        success=True,
        data=StrategyListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/{strategy_id}",
    response_model=ApiResponse[StrategyResponse],
)
async def get_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get a specific strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
    )


@router.put(
    "/{strategy_id}",
    response_model=ApiResponse[StrategyResponse],
)
async def update_strategy(
    strategy_id: UUID,
    request: StrategyUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Update a strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    update_data = request.model_dump(exclude_unset=True)

    # 处理 is_active 状态变更
    if "is_active" in update_data:
        new_active = update_data.pop("is_active")
        if new_active and not strategy.is_active:
            # 启动策略
            strategy.status = "active"
        elif not new_active and strategy.is_active:
            # 停止策略
            strategy.status = "stopped"

    for field, value in update_data.items():
        setattr(strategy, field, value)

    await db.commit()
    await db.refresh(strategy)

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
        message="Strategy updated successfully",
    )


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Delete a strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    # 停止策略
    strategy.is_active = False
    strategy.status = "archived"

    await db.commit()

    return None


@router.post(
    "/{strategy_id}/start",
    response_model=ApiResponse[StrategyResponse],
)
async def start_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Start a strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    strategy.is_active = True
    strategy.status = "active"

    await db.commit()
    await db.refresh(strategy)

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
        message="Strategy started successfully",
    )


@router.post(
    "/{strategy_id}/stop",
    response_model=ApiResponse[StrategyResponse],
)
async def stop_strategy(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Stop a strategy."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    strategy.is_active = False
    strategy.status = "stopped"

    await db.commit()
    await db.refresh(strategy)

    return ApiResponse(
        success=True,
        data=StrategyResponse.model_validate(strategy),
        message="Strategy stopped successfully",
    )


@router.post(
    "/{strategy_id}/run-once",
    response_model=ApiResponse[dict],
)
async def run_strategy_once(
    strategy_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Manually trigger strategy execution once."""
    result = await db.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.user_id == current_user.id,
        )
    )
    strategy = result.scalar_one_or_none()

    if strategy is None:
        raise NotFoundError("Strategy", f"Strategy {strategy_id} not found")

    # TODO: 调用策略执行服务

    return ApiResponse(
        success=True,
        data={"message": "Strategy execution triggered"},
    )
```

- [ ] **Step 2: 注册 Router**

在 `packages/backend-py/src/main.py` 中添加:

```python
from src.routers import health, auth, users, portfolios, positions, orders, providers, wallets, strategies

# 在 app.include_router 部分添加
app.include_router(strategies.router)
```

- [ ] **Step 3: 提交**

```bash
git add packages/backend-py/src/routers/strategies.py packages/backend-py/src/main.py
git commit -m "feat: add Strategy router with CRUD and start/stop"
```

---

### Task 1.4: 扩展 SignalLog 模型

**Files:**
- Modify: `packages/backend-py/src/models/signal_log.py`

- [ ] **Step 1: 添加 AI 思维链相关字段**

在约第154行 (source 字段后) 添加:

```python
# AI 思维链 (新增)
ai_thinking: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
ai_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
ai_tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
ai_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

# 输入数据摘要 (新增)
input_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

# 交易决策详情 (新增)
decision_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 2: 提交**

```bash
git add packages/backend-py/src/models/signal_log.py
git commit -m "feat: extend SignalLog with AI thinking chain fields"
```

---

## 阶段 2: 前端基础 - 策略管理

### Task 2.1: 新增 Strategy 类型

**Files:**
- Modify: `packages/frontend/src/types/index.ts`

- [ ] **Step 1: 添加 Strategy 类型**

在文件末尾添加:

```typescript
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
  data_sources?: Record<string, unknown>;

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
  portfolio_id: string;
  provider_id?: string;
  system_prompt?: string;
  custom_prompt?: string;
  data_sources?: Record<string, unknown>;
  min_order_size: number;
  max_order_size: number;
  market_filter_days?: number;
  market_filter_type?: string;
  run_interval_minutes?: number;
  max_position_size?: number;
  max_open_positions?: number;
  stop_loss_percent?: number;
  take_profit_percent?: number;
}

export interface UpdateStrategyRequest {
  name?: string;
  description?: string;
  provider_id?: string;
  system_prompt?: string;
  custom_prompt?: string;
  data_sources?: Record<string, unknown>;
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
  min_order_size: number;
  max_order_size: number;
  total_trades: number;
  total_pnl: number;
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
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/types/index.ts
git commit -m "feat: add Strategy and SignalLog types"
```

---

### Task 2.2: 新增 strategiesApi

**Files:**
- Modify: `packages/frontend/src/lib/api.ts`

- [ ] **Step 1: 添加 strategiesApi**

在文件末尾 (Wallet API 后) 添加:

```typescript
// Strategies API
export interface StrategySummary {
  id: string
  name: string
  type: string
  is_active: boolean
  status: string
  min_order_size: number
  max_order_size: number
  total_trades: number
  total_pnl: number
}

export interface StrategyListResponse {
  items: StrategySummary[]
  total: number
  page: number
  page_size: number
}

export const strategiesApi = {
  async getAll(params?: {
    page?: number
    pageSize?: number
    portfolioId?: string
  }): Promise<StrategyListResponse> {
    const response = await apiClient.get<ApiResponse<StrategyListResponse>>('/strategies', { params })
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
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/lib/api.ts
git commit -m "feat: add strategiesApi"
```

---

### Task 2.3: 新增 StrategiesPage

**Files:**
- Create: `packages/frontend/src/pages/Strategies.tsx`

- [ ] **Step 1: 创建策略列表页面**

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Play,
  Square,
  Trash2,
  Edit,
  Brain,
  Settings,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { LoadingScreen } from '@/components/ui/LoadingScreen'
import { strategiesApi, type StrategySummary } from '@/lib/api'
import { formatCurrency, formatPercentage, cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'

function StrategyCard({
  strategy,
  onStart,
  onStop,
  onEdit,
  onDelete,
}: {
  strategy: StrategySummary
  onStart: () => void
  onStop: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const pnlIsPositive = strategy.total_pnl >= 0

  return (
    <Card className="group transition-all hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/5">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            <CardTitle className="text-lg">{strategy.name}</CardTitle>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-0 group-hover:opacity-100"
              onClick={onEdit}
            >
              <Edit className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 opacity-0 group-hover:opacity-100 hover:text-red-500"
              onClick={onDelete}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">状态</span>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                'h-2 w-2 rounded-full',
                strategy.is_active ? 'bg-green-500' : 'bg-gray-400'
              )}
            />
            <span className="text-sm font-medium">
              {strategy.is_active ? '运行中' : '已停止'}
            </span>
          </div>
        </div>

        {/* Order Size */}
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">下单金额</span>
          <span className="font-mono">
            ${strategy.min_order_size} - ${strategy.max_order_size}
          </span>
        </div>

        {/* Stats */}
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded',
                pnlIsPositive ? 'bg-emerald-500/10' : 'bg-red-500/10'
              )}
            >
              {pnlIsPositive ? (
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              ) : (
                <TrendingDown className="h-4 w-4 text-red-500" />
              )}
            </div>
            <div>
              <p className="text-sm font-medium">总盈亏</p>
              <p className="text-xs text-muted-foreground">
                交易 {strategy.total_trades} 次
              </p>
            </div>
          </div>
          <span
            className={cn(
              'font-mono font-medium',
              pnlIsPositive ? 'text-emerald-500' : 'text-red-500'
            )}
          >
            {formatCurrency(strategy.total_pnl)}
          </span>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          {strategy.is_active ? (
            <Button variant="outline" size="sm" className="flex-1" onClick={onStop}>
              <Square className="mr-2 h-4 w-4" />
              停止
            </Button>
          ) : (
            <Button variant="outline" size="sm" className="flex-1" onClick={onStart}>
              <Play className="mr-2 h-4 w-4" />
              启动
            </Button>
          )}
          <Button variant="outline" size="sm" className="flex-1">
            <Settings className="mr-2 h-4 w-4" />
            配置
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function StrategiesPage() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [newStrategy, setNewStrategy] = useState({
    name: '',
    description: '',
    portfolio_id: '',
    min_order_size: 5,
    max_order_size: 50,
  })
  const queryClient = useQueryClient()

  const { data: strategiesResponse, isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: () => strategiesApi.getAll(),
  })

  const strategies = strategiesResponse?.items || []

  const createMutation = useMutation({
    mutationFn: (data: typeof newStrategy) => strategiesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      setIsCreateDialogOpen(false)
      setNewStrategy({
        name: '',
        description: '',
        portfolio_id: '',
        min_order_size: 5,
        max_order_size: 50,
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => strategiesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const startMutation = useMutation({
    mutationFn: (id: string) => strategiesApi.start(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: (id: string) => strategiesApi.stop(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate(newStrategy)
  }

  if (isLoading) {
    return <LoadingScreen />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">策略</h1>
          <p className="text-muted-foreground">
            管理 AI 交易策略
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              新建策略
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>创建新策略</DialogTitle>
              <DialogDescription>
                创建 AI 交易策略
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreate}>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="name">策略名称</Label>
                  <Input
                    id="name"
                    placeholder="AI 趋势策略"
                    value={newStrategy.name}
                    onChange={(e) =>
                      setNewStrategy((prev) => ({ ...prev, name: e.target.value }))
                    }
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">描述</Label>
                  <Input
                    id="description"
                    placeholder="描述"
                    value={newStrategy.description}
                    onChange={(e) =>
                      setNewStrategy((prev) => ({ ...prev, description: e.target.value }))
                    }
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="min_order_size">最小下单金额 ($)</Label>
                    <Input
                      id="min_order_size"
                      type="number"
                      value={newStrategy.min_order_size}
                      onChange={(e) =>
                        setNewStrategy((prev) => ({
                          ...prev,
                          min_order_size: Number(e.target.value),
                        }))
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="max_order_size">最大下单金额 ($)</Label>
                    <Input
                      id="max_order_size"
                      type="number"
                      value={newStrategy.max_order_size}
                      onChange={(e) =>
                        setNewStrategy((prev) => ({
                          ...prev,
                          max_order_size: Number(e.target.value),
                        }))
                      }
                    />
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateDialogOpen(false)}
                >
                  取消
                </Button>
                <Button type="submit" isLoading={createMutation.isPending}>
                  创建
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Strategies Grid */}
      {strategies && strategies.length > 0 ? (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {strategies.map((strategy) => (
            <StrategyCard
              key={strategy.id}
              strategy={strategy}
              onStart={() => startMutation.mutate(strategy.id)}
              onStop={() => stopMutation.mutate(strategy.id)}
              onEdit={() => {}}
              onDelete={() => deleteMutation.mutate(strategy.id)}
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-void-200">
              <Brain className="h-6 w-6 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-lg font-semibold">暂无策略</h3>
            <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
              创建您的第一个 AI 交易策略
            </p>
            <Button
              className="mt-6"
              onClick={() => setIsCreateDialogOpen(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              创建策略
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/pages/Strategies.tsx
git commit -m "feat: add Strategies page"
```

---

### Task 2.4: 添加路由

**Files:**
- Modify: `packages/frontend/src/router.tsx`

- [ ] **Step 1: 添加策略路由**

在路由配置中添加:

```tsx
// 添加导入
import Strategies from '@/pages/Strategies'

// 在路由配置中添加
{
  path: '/strategies',
  element: <Strategies />>,
}
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/router.tsx
git commit -m "feat: add strategies route"
```

---

### Task 2.5: 添加侧边栏入口

**Files:**
- Modify: `packages/frontend/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: 添加策略菜单**

在侧边栏导航中添加策略入口:

```tsx
// 添加导入
import { Brain } from 'lucide-react'

// 在导航配置中添加
{
  title: '策略',
  href: '/strategies',
  icon: Brain,
},
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: add strategies to sidebar"
```

---

## 阶段 3: 策略执行引擎 (后端服务)

### Task 3.1: 实现策略定时任务服务

**Files:**
- Create: `packages/backend-py/src/services/strategy_runner.py`

- [ ] **Step 1: 创建策略执行服务**

```python
"""Strategy runner service for scheduled execution."""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.strategy import Strategy
from src.models.portfolio import Portfolio
from src.models.wallet import Wallet
from src.models.signal_log import SignalLog
from src.models.order import Order
from src.models.position import Position
from src.models.provider import Provider
from src.polymarket import get_client


class StrategyRunner:
    """Strategy execution runner."""

    def __init__(self):
        self._running = False
        self._tasks: dict[UUID, asyncio.Task] = {}

    async def start_strategy(self, strategy_id: UUID) -> None:
        """Start running a strategy."""
        if strategy_id in self._tasks:
            return  # Already running

        task = asyncio.create_task(self._run_strategy_loop(strategy_id))
        self._tasks[strategy_id] = task

    async def stop_strategy(self, strategy_id: UUID) -> None:
        """Stop a running strategy."""
        if strategy_id in self._tasks:
            self._tasks[strategy_id].cancel()
            del self._tasks[strategy_id]

    async def _run_strategy_loop(self, strategy_id: UUID) -> None:
        """Main strategy execution loop."""
        async with AsyncSessionLocal() as db:
            # Get strategy
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if not strategy:
                return

            interval = strategy.run_interval_minutes * 60  # Convert to seconds

            while strategy.is_active:
                try:
                    await self._execute_strategy(db, strategy)
                    strategy.last_run_at = datetime.utcnow()
                    strategy.total_runs += 1
                    await db.commit()
                except Exception as e:
                    print(f"Strategy execution error: {e}")

                await asyncio.sleep(interval)

                # Refresh strategy state
                await db.refresh(strategy)

    async def _execute_strategy(
        self, db: AsyncSession, strategy: Strategy
    ) -> Optional[SignalLog]:
        """Execute strategy once."""

        # 1. 获取市场数据 (过滤到期时间)
        markets = await self._get_available_markets(strategy)

        if not markets:
            return None

        # 2. 调用 AI 分析
        ai_result = await self._call_ai_analysis(strategy, markets)

        if not ai_result:
            return None

        # 3. 计算下单金额
        order_size = self._calculate_order_size(
            strategy, ai_result.get("confidence", 0.5)
        )

        # 4. 创建 SignalLog
        signal_log = SignalLog(
            id=UUID(),
            user_id=strategy.user_id,
            portfolio_id=strategy.portfolio_id,
            strategy_id=strategy.id,
            signal_id=str(UUID()),
            signal_type=ai_result.get("action", "hold"),
            confidence=Decimal(str(ai_result.get("confidence", 0))),
            side=ai_result.get("side", "yes"),
            size=Decimal(str(order_size)),
            stop_loss_price=Decimal(str(ai_result.get("stop_loss", 0)))
            if ai_result.get("stop_loss") else None,
            take_profit_price=Decimal(str(ai_result.get("take_profit", 0)))
            if ai_result.get("take_profit") else None,
            risk_reward_ratio=Decimal(str(ai_result.get("risk_reward", 0)))
            if ai_result.get("risk_reward") else None,
            status="approved",
            signal_reason=ai_result.get("reasoning", ""),
            ai_thinking=ai_result.get("thinking", ""),
            ai_model=ai_result.get("model", ""),
            ai_tokens_used=ai_result.get("tokens_used"),
            ai_duration_ms=ai_result.get("duration_ms"),
            input_summary=ai_result.get("input_summary"),
            decision_details=ai_result.get("decision_details"),
        )

        db.add(signal_log)
        await db.commit()

        # 5. 如果是买入/卖出信号，执行订单
        if ai_result.get("action") in ["buy", "sell"]:
            await self._execute_order(db, strategy, signal_log)

        return signal_log

    async def _get_available_markets(
        self, strategy: Strategy
    ) -> list[dict]:
        """Get available markets based on filter."""

        # TODO: 实现 Polymarket 市场查询
        # 根据 strategy.market_filter_days 过滤

        return []

    async def _call_ai_analysis(
        self, strategy: Strategy, markets: list[dict]
    ) -> Optional[dict]:
        """Call AI to analyze markets."""

        # TODO: 实现 AI 调用
        # 1. 构建 Prompt
        # 2. 调用 Provider
        # 3. 解析响应

        return None

    def _calculate_order_size(
        self, strategy: Strategy, confidence: float
    ) -> Decimal:
        """Calculate order size based on confidence."""

        min_size = float(strategy.min_order_size)
        max_size = float(strategy.max_order_size)

        # Linear interpolation
        order_size = min_size + (max_size - min_size) * confidence

        # Clamp to range
        return Decimal(str(max(min_size, min(max_size, order_size))))

    async def _execute_order(
        self,
        db: AsyncSession,
        strategy: Strategy,
        signal_log: SignalLog,
    ) -> None:
        """Execute order based on signal."""

        # TODO: 实现订单执行
        # 1. 获取 Wallet
        # 2. 创建 Order
        # 3. 调用 Polymarket API
        # 4. 创建 Position


# Global instance
strategy_runner = StrategyRunner()
```

- [ ] **Step 2: 提交**

```bash
git add packages/backend-py/src/services/strategy_runner.py
git commit -m "feat: add strategy runner service"
```

---

### Task 3.2: 实现止盈止损监控

**Files:**
- Create: `packages/backend-py/src/services/position_monitor.py`

- [ ] **Step 1: 创建止盈止损监控服务**

```python
"""Position monitor for stop-loss and take-profit."""

import asyncio
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.position import Position
from src.models.order import Order


class PositionMonitor:
    """Monitor positions for stop-loss and take-profit triggers."""

    def __init__(self):
        self._running = False
        self._check_interval = 60  # Check every 60 seconds

    async def start(self) -> None:
        """Start the position monitor."""
        self._running = True
        asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the position monitor."""
        self._running = False

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                async with AsyncSessionLocal() as db:
                    await self._check_positions(db)
            except Exception as e:
                print(f"Position monitor error: {e}")

            await asyncio.sleep(self._check_interval)

    async def _check_positions(self, db: AsyncSession) -> None:
        """Check all open positions for stop-loss/take-profit."""
        result = await db.execute(
            select(Position).where(Position.status == "open")
        )
        positions = result.scalars().all()

        for position in positions:
            await self._check_position(db, position)

    async def _check_position(
        self, db: AsyncSession, position: Position
    ) -> None:
        """Check a single position."""

        # TODO: 获取当前价格
        current_price = position.current_price

        if not current_price:
            return

        # Check stop-loss (买入 Yes)
        if position.side == "yes":
            if (
                position.stop_loss_price
                and current_price <= position.stop_loss_price
            ):
                await self._close_position(db, position, "stop_loss")

            if (
                position.take_profit_price
                and current_price >= position.take_profit_price
            ):
                await self._close_position(db, position, "take_profit")

        # Check stop-loss (买入 No)
        else:  # side == "no"
            if (
                position.stop_loss_price
                and current_price >= position.stop_loss_price
            ):
                await self._close_position(db, position, "stop_loss")

            if (
                position.take_profit_price
                and current_price <= position.take_profit_price
            ):
                await self._close_position(db, position, "take_profit")

    async def _close_position(
        self,
        db: AsyncSession,
        position: Position,
        close_reason: str,
    ) -> None:
        """Close a position."""

        # TODO: 执行平仓订单
        # 1. 获取当前价格
        # 2. 创建卖出订单
        # 3. 更新 Position

        position.status = "closed"
        await db.commit()


# Global instance
position_monitor = PositionMonitor()
```

- [ ] **Step 2: 提交**

```bash
git add packages/frontend/src/services/position_monitor.py
git commit -m "feat: add position monitor service"
```

---

## 实施完成总结

| 阶段 | 任务数 | 描述 |
|------|--------|------|
| 1 | 4 | 后端基础 - Strategy API |
| 2 | 5 | 前端基础 - 策略管理 |
| 3 | 2 | 策略执行引擎 |
| **总计** | **11** | |

---

## Plan Complete

Plan complete and saved to `docs/superpowers/plans/2025-04-21-ai-strategy-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?