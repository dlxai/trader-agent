# AI 交易策略设计文档

## 1. 概述

本文档描述 Trader Agent 系统的 AI 交易策略功能设计。

### 1.1 目标

实现基于 AI 分析的自动交易功能，支持：
- AI 分析市场数据，生成交易信号
- 根据信号强度动态选择下单金额
- 与 Polymarket 钱包集成执行交易

### 1.2 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                         User                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Portfolios  │  │ Strategies  │  │ Signal Logs         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Portfolio   │  │ Strategy    │  │ SignalLog           │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Wallet      │  │ Order       │  │ Position            │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Polymarket API                             │
│  ┌─────────────┐  ┌─────────────┐                           │
│  │ 交易执行    │  │ 市场数据    │                           │
│  └─────────────┘  └─────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

## 2. 数据模型

### 2.1 现有模型（已存在）

#### Portfolio（投资组合）
```python
class Portfolio:
    # 关联
    user_id: UUID
    wallets: List[Wallet]  # 关联的钱包

    # 基本信息
    name: str
    initial_balance: Decimal
    current_balance: Decimal

    # 风险参数
    max_position_size: Decimal      # 最大持仓金额
    max_open_positions: int         # 最大持仓数
    stop_loss_percent: Decimal      # 止损 %
    take_profit_percent: Decimal    # 止盈 %

    # 关系
    strategies: List[Strategy]
    positions: List[Position]
    orders: List[Order]
    signals: List[SignalLog]
```

#### Wallet（Polymarket 钱包）
```python
class Wallet:
    user_id: UUID
    name: str
    address: str
    private_key_encrypted: str  # 加密的私钥
    proxy_url: str
    status: str  # active, inactive, error
    usdc_balance: str
```

#### Provider（AI 模型）
```python
class Provider:
    user_id: UUID
    name: str
    provider_type: str  # openai, claude, deepseek
    api_key_encrypted: str
    is_active: bool
```

#### SignalLog（信号记录）
```python
class SignalLog:
    # 关联
    user_id: UUID
    portfolio_id: UUID  # 关联投资组合
    strategy_id: UUID   # 关联策略

    # 信号信息
    signal_id: str
    signal_type: str  # buy, sell, hold, close
    confidence: Decimal  # 0-1 信号强度
    side: str  # yes, no

    # 交易参数
    size: Decimal  # 建议数量
    stop_loss_price: Decimal
    take_profit_price: Decimal
    risk_reward_ratio: Decimal

    # 状态
    status: str  # pending, approved, rejected, executed, expired
```

#### Order / Position
- 已有完整模型，支持与 Strategy/Portfolio 关联

### 2.4 SignalLog 扩展（AI 思维链）

SignalLog 现有字段已部分支持 AI 分析，需扩展以下字段：

```python
class SignalLog:
    # ===== 现有字段（已存在）=====
    signal_reason: Optional[str]           # AI 分析结论
    technical_indicators: Optional[dict]   # 技术指标数据
    model_version: Optional[str]           # 模型版本
    model_confidence: Optional[Decimal]    # AI 置信度

    # ===== 需新增字段 =====
    ai_thinking: Optional[Text] = None     # AI 完整思维链/推理过程
    ai_model: Optional[str] = None          # 使用的 AI 模型名称
    ai_tokens_used: Optional[int] = None    # 消耗的 tokens 数量
    ai_duration_ms: Optional[int] = None    # AI 响应耗时(毫秒)

    # 输入数据摘要（用于展示）
    input_summary: Optional[dict] = None    # K线摘要、指标汇总

    # 交易决策详情（用于展示）
    decision_details: Optional[dict] = None # 决策类型、金额理由等
```

**现有字段映射：**
| 现有字段 | 用途 |
|----------|------|
| signal_reason | AI 简短分析结论 |
| technical_indicators | 技术指标原始数据 |
| model_version | AI 模型版本 |
| model_confidence | AI 置信度（可复用为 confidence） |

**新增字段：**
| 新字段 | 用途 |
|--------|------|
| ai_thinking | 完整的 AI 推理过程 |
| ai_model | 模型名称（如 deepseek） |
| ai_tokens_used | 成本统计 |
| ai_duration_ms | 性能统计 |

### 2.5 Polymarket 特殊考量

Polymarket 是预测市场，与传统交易所不同：

| 传统交易所 | Polymarket |
|-----------|------------|
| 买入/卖出 | Yes/No (概率) |
| 价格 | 0-1 之间的概率 |
| 止损 | 概率低于某值时平仓 |
| 止盈 | 概率高于某值时平仓 |

**SignalLog 中的止盈止损对应：**
- `stop_loss_price` → 当概率低于此值时平仓（如 0.35）
- `take_profit_price` → 当概率高于此值时平仓（如 0.65）

### 2.2 扩展 Strategy 模型

现有 Strategy 模型已存在，需要扩展以下字段：

```python
class Strategy:
    # 关联（已存在）
    user_id: UUID
    portfolio_id: UUID  # 关联投资组合

    # 基本信息（已存在）
    name: str
    description: str
    type: str  # ai_trading
    is_active: bool

    # ===== 新增字段 =====

    # AI 配置
    provider_id: UUID  # 关联的 AI 模型 Provider

    # Prompt 配置
    system_prompt: str  # 系统提示词
    custom_prompt: str  # 自定义提示词

    # 数据源配置（JSON）
    data_sources: dict = {
        "kline_timeframe": "1h",      # K线时间周期
        "kline_count": 100,           # K线数量
        "enable_indicators": True,    # 是否启用技术指标
        "indicators": ["ema", "rsi", "macd"]  # 启用的指标列表
    }

    # ===== 下单金额配置（核心） =====
    # 根据信号强度动态选择下单金额
    min_order_size: Decimal = Decimal("5")      # 最小下单金额 ($)
    max_order_size: Decimal = Decimal("50")     # 最大下单金额 ($)

    # 信号强度与金额映射（可在 UI 配置）
    # confidence 0.0-0.3 → min_order_size
    # confidence 0.3-0.7 → 线性插值
    # confidence 0.7-1.0 → max_order_size

    # ===== 风险控制（已存在部分） =====
    # max_position_size, stop_loss_percent, take_profit_percent
    # 已有字段可直接使用

    # 性能统计（已有）
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: Decimal
    sharpe_ratio: Decimal
```

### 2.3 数据流

```
1. 策略启动 → 定时任务触发
2. 获取市场数据（K线、指标）
3. 调用 AI (Provider) 分析
4. 生成 SignalLog（包含 confidence）
5. 根据 confidence 计算下单金额：
   - order_size = min_order_size + (max_order_size - min_order_size) * confidence
6. 创建 Order → 执行交易
7. 更新 Position
8. 记录绩效到 Strategy
```

## 3. API 设计

### 3.1 策略 CRUD

#### POST /api/strategies
创建策略

Request:
```json
{
  "name": "AI 趋势策略",
  "description": "基于 AI 分析的趋势跟踪策略",
  "portfolio_id": "uuid",
  "provider_id": "uuid",
  "system_prompt": "你是一个专业交易员...",
  "custom_prompt": "分析以下市场数据...",
  "data_sources": {
    "kline_timeframe": "1h",
    "kline_count": 100,
    "enable_indicators": true,
    "indicators": ["ema", "rsi"]
  },
  "min_order_size": 5,
  "max_order_size": 50,
  "max_position_size": 100,
  "stop_loss_percent": 5,
  "take_profit_percent": 10,
  "max_open_positions": 3
}
```

#### GET /api/strategies
策略列表

#### GET /api/strategies/{id}
策略详情

#### PUT /api/strategies/{id}
更新策略

#### DELETE /api/strategies/{id}
删除策略

### 3.2 策略控制

#### POST /api/strategies/{id}/start
启动策略

#### POST /api/strategies/{id}/stop
停止策略

#### POST /api/strategies/{id}/run-once
手动触发一次执行（用于测试）

### 3.3 信号记录

#### GET /api/signals
信号列表（可选，按 portfolio 或 strategy 筛选）

#### GET /api/signals/{id}
信号详情

## 4. 前端设计

### 4.1 策略列表页 (StrategiesPage)

```
┌─────────────────────────────────────────────────────────────┐
│  投资组合                                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ 我的AI策略  │  │ 趋势策略   │  │ + 新建策略  │          │
│  │ ● 运行中   │  │ ○ 已停止   │  │             │          │
│  │ 胜率 65%   │  │ 胜率 45%   │  │             │          │
│  │ 交易 23    │  │ 交易 12    │  │             │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

功能：
- 显示所有策略卡片
- 显示状态（运行中/已停止）
- 显示绩效（胜率、交易数、盈亏）
- 快捷操作：启动/停止/编辑/删除

### 4.2 策略编辑器 (StrategyEditorPage)

#### 基础信息
- 策略名称
- 描述
- 关联投资组合（Portfolio）
- 关联 AI 模型（Provider）

#### AI 配置
- System Prompt（系统提示词）
- Custom Prompt（自定义提示词）
- 数据源配置：
  | 数据源 | 说明 | 来源 |
  |--------|------|------|
  | 市场数据 | 价格、成交量、订单簿 | `trading_engine/collector.py` |
  | Activity | 用户实时买入/卖出活动 | `polymarket-agent/activity_analyzer.py` |
  | Sports | 体育赛事比分 | WebSocket 实时数据 |

#### 市场过滤配置（重要！）
```
┌────────────────────────────────────────┐
│ 市场过滤                                 │
├────────────────────────────────────────┤
│ □ 只交易以下到期时间的 markets:         │
│   ○ 24小时内到期                        │
│   ○ 7天内到期                          │
│   ● 指定日期范围: [____] 至 [____]      │
│                                         │
│ 说明: 只选择到期时间在指定范围内的市场   │
└────────────────────────────────────────┘
```

#### 数据源配置（从现有代码扩展）

#### 下单金额配置（核心）
```
┌────────────────────────────────────────┐
│ 下单金额配置                            │
├────────────────────────────────────────┤
│ 最小下单金额 ($):  [5]                 │
│ 最大下单金额 ($):  [50]                │
│                                        │
│ 信号强度 → 金额映射：                   │
│ 0%  ────────────────────── 100%       │
│ [min]          ●           [max]       │
│                                        │
│ 说明：高信号强度使用更大仓位            │
└────────────────────────────────────────┘
```

#### 风险控制
- 最大持仓金额
- 最大持仓数
- 止损 %
- 止盈 %

### 4.3 实时监控面板 (StrategyMonitorPanel)

在 Dashboard 或独立页面展示策略运行实时状态。

#### 监控内容

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 策略监控                                                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ 策略: AI趋势策略    状态: ● 运行中    已运行: 2小时35分               │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ 📊 今日统计                                                         │ │
│ │ ├─ 信号: 12 (买入: 5, 卖出: 3, 持有: 4)                            │ │
│ │ ├─ 成交: 3 笔 ($85)                                                │ │
│ │ ├─ 持仓: 2 个 ($120)                                               │ │
│ │ └─ 盈亏: +$15.20 (+8.5%)                                          │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ 🧠 最新 AI 思维链                                                  │ │
│ │                                                                     │ │
│ │ 🤖 分析对象: Trump 2024 是否当选                                   │ │
│ │ ├─ 当前价格: 0.52                                                  │ │
│ │ ├─ Activity: 过去1小时买入 $45K, 卖出 $12K (净流入)               │ │
│ │ ├─ 趋势: 上涨中 (从 0.48 → 0.52)                                  │ │
│ │ └─ 置信度: 72%                                                    │ │
│ │                                                                     │ │
│ │ 💭 AI 推理:                                                        │ │
│ │   1. 价格从 0.48 上涨到 0.52，显示强劲上涨趋势                     │ │
│ │   2. Activity 显示大量资金流入 (净流入 $33K)                       │ │
│ │   3. 买入 Yes 的胜率较高，建议开多仓                               │ │
│ │                                                                     │ │
│ │ ✅ 决策: 买入 Yes  $25 (高置信度，使用较大仓位)                    │ │
│ │ 💰 止损: 0.42  止盈: 0.62  风险回报比: 1.8                         │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ 📈 持仓列表                                                        │ │
│ │ ├─ Trump 2024 Yes  @0.48  当前:0.52  +8.3%  $50                   │ │
│ │ └─ BTC ETF批准 No   @0.35  当前:0.31  -11%  $30                   │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 监控字段

| 类别 | 字段 | 说明 |
|------|------|------|
| **策略状态** | status | 运行中/已停止 |
| **运行时间** | uptime | 已运行时长 |
| **信号统计** | signals_count | 今日信号数（买/卖/持有） |
| **成交统计** | trades_count | 今日成交笔数和金额 |
| **持仓** | positions | 当前持仓列表和盈亏 |
| **实时数据** | price, activity | 当前价格、实时 Activity |
| **AI 思维链** | ai_thinking | 最新的 AI 推理过程 |

### 4.4 止盈止损监控

#### Polymarket 止盈止损逻辑

| 传统交易所 | Polymarket |
|-----------|------------|
| 买入后设置止损价 | 当概率低于 stop_loss_price 时平仓 |
| 买入后设置止盈价 | 当概率高于 take_profit_price 时平仓 |

#### 监控展示

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 止盈止损监控                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ 持仓: Trump 2024 Yes                                                   │
│ ├─ 入场价: $0.48           当前价: $0.52              盈亏: +$20 (+8%) │
│ ├─ 止盈价: $0.62 (距离 19%) ○                                          │
│ ├─ 止损价: $0.42 (距离 -19%) ●  ← 触发中                              │
│ └─ 状态: ⚠️  接近止损                                                   │
│                                                                         │
│ 自动平仓规则:                                                         │
│ ├─ [X] 启用止盈: 概率 > 0.62 时自动卖出                              │
│ ├─ [X] 启用止损: 概率 < 0.42 时自动卖出                              │
│ └─ [ ] 启用追踪止损: 回调 5%                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 止盈止损实现逻辑

```python
class PositionMonitor:
    """持仓监控 - 检测止盈止损触发"""

    async def check_stop_loss_take_profit(self, position: Position, current_price: Decimal):
        """检查是否触发止盈止损"""

        # 止盈检查 (买入 Yes)
        if position.side == "yes":
            if position.take_profit_price and current_price >= position.take_profit_price:
                await self.close_position(position, "take_profit")
            if position.stop_loss_price and current_price <= position.stop_loss_price:
                await self.close_position(position, "stop_loss")

        # 止盈检查 (买入 No)
        else:  # side == "no"
            if position.take_profit_price and current_price <= position.take_profit_price:
                await self.close_position(position, "take_profit")
            if position.stop_loss_price and current_price >= position.stop_loss_price:
                await self.close_position(position, "stop_loss")
```

### 4.5 买入/卖出信号监控

#### 信号触发流程监控

```
AI 分析 → 生成 SignalLog → 风险检查 → 执行买入/卖出 → 更新持仓

每一步都记录状态，可在 UI 展示：
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 信号执行流程                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ 14:30:15  🤖 AI 分析完成                                               │
│           ├─ 决策: 买入 Yes                                           │
│           ├─ 置信度: 75%                                              │
│           └─ 金额: $25 (高置信度)                                     │
│                                                                         │
│ 14:30:16  ⚖️  风险检查                                                 │
│           ├─ 仓位检查: ✅ 通过 (当前 2/3)                             │
│           ├─ 余额检查: ✅ 通过 (余额 $500)                            │
│           └─ 市场检查: ✅ 通过                                         │
│                                                                         │
│ 14:30:18  📤 提交订单                                                  │
│           ├─ 市场: Trump 2024                                         │
│           ├─ 方向: Buy Yes                                            │
│           ├─ 数量: $25                                                │
│           └─ 订单ID: ord_xxx                                          │
│                                                                         │
│ 14:30:20  ✅ 订单成交                                                  │
│           ├─ 成交价: $0.52                                            │
│           ├─ 手续费: $0.10                                            │
│           └─ 持仓ID: pos_xxx                                          │
│                                                                         │
│ 14:30:21  📊 持仓更新                                                  │
│           ├─ 数量: $25                                                │
│           ├─ 止盈: $0.62                                              │
│           └─ 止损: $0.42                                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 信号状态

| 状态 | 说明 |
|------|------|
| pending | 待处理 |
| analyzing | AI 分析中 |
| risk_check | 风险检查中 |
| approved | 通过审查 |
| rejected | 被拒绝 |
| submitting | 提交订单 |
| filled | 已成交 |
| failed | 失败 |

### 4.3 信号日志页 (SignalsPage)

显示 AI 生成的信号列表和决策详情。

#### 信号列表
```
┌─────────────────────────────────────────────────────────────────────────┐
│ 信号日志                                                                │
├─────────────────────────────────────────────────────────────────────────┤
│ 时间        事件                  决策    置信度  金额    状态          │
│ 14:30       Trump 2024            买入    85%     $45     ✓ 已执行     │
│ 14:00       BTC ETF批准            卖出    60%     $15     ✗ 已拒绝     │
│ 13:30       Super Bowl LVIII      持有    40%     -       ⏳ 待执行     │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 信号详情（点击展开）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ AI 思维链 (🧠 展开/收起)                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ 📊 市场分析                                                             │
│ ├─ K线: 1小时周期，50根                                                 │
│ ├─ 当前价格: 0.45                                                       │
│ ├─ RSI: 68 (超买区域)                                                  │
│ ├─ MACD: 金叉向上                                                       │
│ └─ 资金流向: 净流入 $1.2M                                               │
│                                                                         │
│ 🤔 AI 推理                                                              │
│ ├─ 技术面：RSI 处于超买区域，但 MACD 呈现金叉形态，短期有上涨动能       │
│ ├─ 资金面：机构资金持续流入，市场情绪偏多                               │
│ ├─ 事件面：距离结果公布还有3天，不确定性较高                           │
│ └─ 综合判断：概率有上升空间，建议适度参与                               │
│                                                                         │
│ 📈 交易决策                                                             │
│ ├─ 决策: 买入 Yes                                                       │
│ ├─ 置信度: 75%                                                         │
│ ├─ 理由: RSI超卖+资金流入，综合判断概率上行                            │
│ ├─ 建议入场价: 0.45                                                    │
│ ├─ 止损价: 0.35 (-22%)                                                 │
│ ├─ 止盈价: 0.65 (+44%)                                                 │
│ ├─ 风险回报比: 2.0                                                     │
│ ├─ 下单金额: $25 (高置信度，使用较大仓位)                              │
│ └─ 状态: 已执行                                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 核心展示字段

| 字段 | 说明 | 来源 |
|------|------|------|
| ai_thinking | AI 完整推理过程 | AI 响应 |
| technical_indicators | 技术指标数据 | 数据源 |
| input_summary | 输入数据摘要 | 构建 Prompt 时生成 |
| decision_details | 交易决策详情 | AI 响应解析 |

### 4.4 交易决策卡片 (DecisionCard)

在信号列表或 Dashboard 中展示每个交易决策：

```
┌────────────────────────────────────────┐
│ 🟢 LONG  BTC  85%  ● 已盈利            │
├────────────────────────────────────────┤
│ 入场: $45,000  当前: $48,000           │
│ 止损: $42,000  止盈: $52,000           │
├────────────────────────────────────────┤
│ 💡 RSI超卖+ MACD金叉，建议做多         │
└────────────────────────────────────────┘
```

#### Polymarket 专用
- 买入 Yes = 做多概率（认为事件会发生）
- 买入 No = 做空概率（认为事件不会发生）
- 概率高于 0.5 = 更有利 Yes

## 5. 执行流程

### 5.1 策略执行循环

```
┌─────────────────┐
│   定时触发      │ ← 每 N 分钟执行一次
└────────┬────────┘
         ▼
┌─────────────────┐
│  获取市场数据   │ ← K线、指标等
└────────┬────────┘
         ▼
┌─────────────────┐
│  构建 AI Prompt │ ← 拼装系统/用户 Prompt
└────────┬────────┘
         ▼
┌─────────────────┐
│  调用 AI 分析   │ ← 使用配置的 Provider
└────────┬────────┘
         ▼
┌─────────────────┐
│  解析 AI 响应   │ ← 提取交易决策
└────────┬────────┘
         ▼
┌─────────────────┐
│  生成 SignalLog │ ← 记录信号和 confidence
└────────┬────────┘
         ▼
┌─────────────────┐
│ 计算下单金额    │ ← 根据 confidence 计算
│ size = min +    │
│   (max-min)*conf│
└────────┬────────┘
         ▼
┌─────────────────┐
│  风险检查       │ ← 检查仓位、止盈止损
└────────┬────────┘
         ▼
┌─────────────────┐
│  创建 Order     │ ← 调用 Polymarket API
└────────┬────────┘
         ▼
┌─────────────────┐
│  更新策略绩效   │
└─────────────────┘
```

### 5.2 下单金额计算公式

```python
def calculate_order_size(strategy: Strategy, confidence: Decimal) -> Decimal:
    """根据信号强度计算下单金额"""
    min_size = strategy.min_order_size
    max_size = strategy.max_order_size

    # 线性插值
    order_size = min_size + (max_size - min_size) * confidence

    # 确保在范围内
    return max(min_size, min(max_size, order_size))
```

## 6. 现有代码复用

### 6.1 复用的后端模块

| 模块 | 用途 | 路径 |
|------|------|------|
| `trading_engine/collector.py` | 市场数据收集 | ✅ 直接复用 |
| `trading_engine/analyzer.py` | 信号分析（含 RiskChecker, PortfolioChecker, MarketChecker） | ✅ 直接复用 |
| `trading_engine/executor.py` | 订单执行 | ✅ 直接复用 |
| `trading_engine/event_bus.py` | 事件总线 | ✅ 直接复用 |
| `polymarket.py` | Polymarket 客户端 | ✅ 直接复用 |
| `models/signal_log.py` | 信号记录 | ✅ 扩展字段 |
| `models/order.py` | 订单 | ✅ 复用 |
| `models/position.py` | 持仓 | ✅ 复用 |
| `models/portfolio.py` | 投资组合 | ✅ 复用 |
| `models/wallet.py` | 钱包 | ✅ 复用 |
| `models/provider.py` | AI 模型 | ✅ 复用 |

### 6.2 数据源（来自 polymarket-agent）

| 数据源 | 说明 |
|--------|------|
| 市场数据 | Polymarket API 价格、成交量 |
| Activity | 用户实时买入/卖出活动分析 |
| Sports | 体育赛事 WebSocket 比分 |

### 6.3 需要新增/修改

**后端新增：**
1. 扩展 `Strategy` 模型字段
2. 新增 `Strategy` Router (CRUD + 启动/停止)
3. 扩展 `SignalLog` 模型（ai_thinking 等）
4. 实现策略执行定时任务
5. 连接 `polymarket-agent` 的 Activity 数据

**后端修改：**
1. 将现有 `trading_engine` 集成到 API 流程中

**前端新增：**
1. 新增 Strategy 类型
2. 新增 `strategiesApi`
3. 新增 `StrategiesPage`（策略列表）
4. 新增 `StrategyEditorPage`（策略编辑器）
5. 新增 `SignalsPage`（信号日志，含 AI 思维链展示）

## 7. 实施计划

### 阶段 1：基础功能
1. 扩展 Strategy 模型
2. 实现 Strategy CRUD API
3. 实现策略启动/停止
4. 前端策略列表页

### 阶段 2：AI 执行
1. 实现 AI 分析逻辑
2. 实现 SignalLog 生成
3. 实现下单金额计算
4. 实现定时执行任务

### 阶段 3：完善
1. 前端策略编辑器
2. 信号日志页面
3. 绩效统计
4. 测试和优化

## 8. 待确认问题

- [ ] 定时任务间隔（每几分钟执行一次？）
- [ ] 是否需要支持多个市场/事件选择？
- [ ] 是否需要回测功能？