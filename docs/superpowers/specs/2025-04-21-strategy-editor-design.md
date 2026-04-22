# 策略编辑器设计文档

## 1. 概述

完善策略编辑页面，提供完整的策略配置功能，支持数据源选择、触发条件配置、AI 配置、风险控制等。

## 2. 现状分析

### 2.1 当前问题

- 前端 `Strategies.tsx` 创建表单只有 4 个字段（名称、描述、金额范围）
- 后端 `Strategy` 模型已有完整字段，但前端未暴露
- 缺少默认配置模板
- 缺少完整的策略编辑功能
- 缺少信号过滤和持仓监控配置

### 2.2 参考项目

| 项目 | 优点 |
|------|------|
| `polymarket-agent` | 信号过滤流程、持仓监控（止损/止盈/移动止盈）、配置驱动 |
| `jmwl-autotrade` | 策略配置结构、风险控制、默认配置模板 |

### 2.3 现有代码

| 模块 | 位置 | 状态 |
|------|------|------|
| Strategy 模型 | `backend-py/src/models/strategy.py` | 完整 |
| Strategy Router | `backend-py/src/routers/strategies.py` | 完整 |
| Strategy Runner | `backend-py/src/services/strategy_runner.py` | 基础实现 |
| SignalGenerator | `strategy-py/src/strategy/signal_generator.py` | 多种实现 |
| 数据源 | `strategy-py/src/strategy/realtime_service.py` 等 | WebSocket 实时 |

## 3. 设计方案

### 3.1 策略配置结构

参考 polymarket-agent 的信号过滤流程，设计如下配置：

```typescript
interface StrategyConfig {
  // 基础信息
  name: string;
  description: string;
  portfolio_id: string;

  // 数据源配置
  data_sources: {
    enable_market_data: boolean;    // 市场价格
    enable_activity: boolean;       // Activity 数据
    enable_sports_score: boolean;   // Sports 比分（自动识别 Sports 市场）
  };

  // 触发条件（事件驱动）
  trigger: {
    price_change_threshold: number;  // 价格波动阈值 (默认 5%)
    activity_netflow_threshold: number;  // Activity 净流入阈值 (默认 $1000)
    min_trigger_interval: number;    // 最小触发间隔 (默认 5 分钟)
    scan_interval: number;           // 定时扫描间隔（兜底，默认 15 分钟）
  };

  // 信号过滤（来自 polymarket-agent）
  filters: {
    min_confidence: number;          // 最小置信度 (默认 40)
    min_price: number;               // 最小价格 (默认 0.50)
    max_price: number;               // 最大价格 (默认 0.99)
    max_spread: number;              // 最大价差 (默认 3%)
    max_slippage: number;            // 最大滑点 (默认 2%)
    dead_zone_enabled: boolean;      // 启用死亡区间过滤 (默认 true)
    dead_zone_min: number;           // 死亡区间最小 (默认 0.70)
    dead_zone_max: number;           // 死亡区间最大 (默认 0.80)
    keywords_exclude: string[];      // 排除关键词 (默认 ["o/u", "spread"])
  };

  // AI 配置
  ai: {
    provider_id: string;             // 选择的 AI 服务商
    system_prompt: string;           // 系统提示词
    custom_prompt: string;           // 自定义提示词
  };

  // 下单配置
  order: {
    min_order_size: number;          // 最小下单金额 (默认 $10)
    max_order_size: number;          // 最大下单金额 (默认 $50)
    default_amount: number;          // 默认金额 (默认 $5)
  };

  // 持仓监控（来自 polymarket-agent）
  position_monitor: {
    enable_stop_loss: boolean;       // 启用止损 (默认 true)
    stop_loss_percent: number;       // 止损百分比 (默认 -15%)
    enable_take_profit: boolean;     // 启用止盈 (默认 true)
    take_profit_price: number;       // 止盈概率 (默认 0.999)
    enable_trailing_stop: boolean;   // 启用移动止盈 (默认 true)
    trailing_stop_percent: number;   // 移动止盈回调 (默认 5%)
    enable_auto_redeem: boolean;     // 自动赎回 (默认 true)
  };

  // 风险控制
  risk: {
    max_positions: number;           // 最大持仓数 (默认 3)
    min_risk_reward_ratio: number;   // 最小盈亏比 (默认 2.0)
    max_margin_usage: number;        // 最大保证金使用率 (默认 0.9)
    min_position_size: number;       // 最小持仓金额 (默认 $12)
  };
}
```

### 3.2 信号过滤流程（来自 polymarket-agent）

```
信号进入
    ↓
[1] 置信度检查 (≥ min_confidence)
    ↓
[2] 价格区间 (min_price ~ max_price)
    ↓
[3] 死亡区间过滤 (0.70-0.80 区间不交易)
    ↓
[4] 关键词过滤 (排除含 o/u, spread 的市场)
    ↓
[5] 价差检查 (≤ max_spread)
    ↓
[6] 滑点保护 (≤ max_slippage)
    ↓
[7] 冷却时间检查 (min_trigger_interval)
    ↓
[8] 资金检查 (余额是否足够)
    ↓
执行交易
```

### 3.3 默认配置模板

```typescript
const DEFAULT_STRATEGY_CONFIG = {
  data_sources: {
    enable_market_data: true,
    enable_activity: true,
    enable_sports_score: true,
  },
  trigger: {
    price_change_threshold: 5,        // 5%
    activity_netflow_threshold: 1000, // $1000
    min_trigger_interval: 5,          // 5 分钟
    scan_interval: 15,                // 15 分钟
  },
  filters: {
    min_confidence: 40,               // 来自 polymarket-agent
    min_price: 0.50,
    max_price: 0.99,
    max_spread: 3,                    // 3%
    max_slippage: 2,                  // 2%
    dead_zone_enabled: true,
    dead_zone_min: 0.70,
    dead_zone_max: 0.80,
    keywords_exclude: ["o/u", "spread"],
  },
  order: {
    min_order_size: 10,
    max_order_size: 50,
    default_amount: 5,
  },
  position_monitor: {
    enable_stop_loss: true,
    stop_loss_percent: -15,           // -15%
    enable_take_profit: true,
    take_profit_price: 0.999,
    enable_trailing_stop: true,
    trailing_stop_percent: 5,         // 5%
    enable_auto_redeem: true,
  },
  risk: {
    max_positions: 3,
    min_risk_reward_ratio: 2.0,
    max_margin_usage: 0.9,
    min_position_size: 12,
  },
};
```

### 3.3 默认 Prompt 模板

#### System Prompt（中文）

```
# 你是一个专业的 Polymarket 交易员

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
  "side": "yes|no",  // 仅 Polymarket
  "confidence": 0-100,
  "reasoning": "简短理由",
  "stop_loss": 0-1,
  "take_profit": 0-1,
  "risk_reward": number
}
```

#### Custom Prompt

```
请分析以下市场数据，给出交易决策：

当前价格: {price}
24h 变化: {change}%
Activity: 净流入 {netflow}
{free_text}

请判断是否应该买入/卖出/持有。
```

### 3.4 UI 设计

#### 3.4.1 策略列表页

- 显示所有策略卡片
- 显示状态（运行中/已停止）
- 显示绩效（胜率、交易数、盈亏）
- 快捷操作：启动/停止/编辑/删除

#### 3.4.2 策略编辑对话框

采用 Tab 切换结构：

```
┌─────────────────────────────────────────────────────────────┐
│  编辑策略                                                     │
├─────────────────────────────────────────────────────────────┤
│  [基础信息] [数据源] [触发条件] [AI配置] [风险控制]          │
└─────────────────────────────────────────────────────────────┘
```

**Tab 1: 基础信息**
- 策略名称
- 描述
- 关联投资组合（Portfolio）

**Tab 2: 数据源**
- ☑ 市场价格
- ☑ Activity 数据
- ☑ Sports 比分（仅 Sports 市场）

**Tab 3: 触发条件**
- 价格波动阈值 (5%)
- Activity 净流入阈值 ($1000)
- 最小触发间隔 (5 分钟)
- 定时扫描间隔 (15 分钟)

**Tab 4: 信号过滤**（来自 polymarket-agent）
- 最小置信度 (40%)
- 价格区间 (0.50 - 0.99)
- 最大价差 (3%)
- 最大滑点 (2%)
- ☑ 启用死亡区间过滤 (0.70 - 0.80)
- 排除关键词

**Tab 5: AI 配置**
- 选择 AI 服务商（Provider 下拉）
- System Prompt（文本域）
- Custom Prompt（文本域）

**Tab 6: 持仓监控**（来自 polymarket-agent）
- ☑ 启用止损 (15%)
- ☑ 启用止盈 (概率 ≥ 0.999)
- ☑ 启用移动止盈 (回调 5%)
- ☑ 启用自动赎回

**Tab 7: 风险控制**
- 最大持仓数 (3)
- 最小盈亏比 (2.0)
- 最大保证金使用率 (90%)
- 最小持仓金额 ($12)

#### 3.4.3 策略监控面板

显示实时状态：

```
┌─────────────────────────────────────────────────────────────┐
│  策略监控: AI 趋势策略                                       │
│  状态: ● 运行中    已运行: 2小时35分                         │
├─────────────────────────────────────────────────────────────┤
│  📊 今日统计                                                 │
│  ├─ 信号: 12 (买入: 5, 卖出: 3, 持有: 4)                    │
│  ├─ 成交: 3 笔 ($85)                                        │
│  └─ 持仓: 2 个                                              │
├─────────────────────────────────────────────────────────────┤
│  🏆 持仓列表                                                 │
│  ├─ Trump 2024 Yes  @0.48  当前:0.52  +8.3%                 │
│  │   比分: Trump 7 - 3 Biden (Trump 领先)                  │
│  └─ BTC ETF批准 No   @0.35  当前:0.31  -11%                 │
│      比分: 待确认                                           │
├─────────────────────────────────────────────────────────────┤
│  🧠 最新信号                                                 │
│  决策: 买入 YES  置信度: 75%  金额: $25                      │
│  理由: 比分利好 + 价格站稳 + Activity 净流入                │
└─────────────────────────────────────────────────────────────┘
```

## 4. 架构改进：数据源共享

### 4.1 问题

当前架构：每个策略独立创建 WebSocket 连接
- 多个策略 = 多个重复连接
- 浪费资源，增加延迟

### 4.2 改进方案

按 Portfolio 维度共享数据源：

```
                    ┌──────────────────────┐
                    │  数据源服务（单例）    │
                    │  - WebSocket 连接    │
                    │  - 价格缓存          │
                    │  - Activity 缓存     │
                    │  - 比分缓存          │
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │ 策略 A   │        │ 策略 B   │        │ 策略 C   │
    │ (同Portfolio)     │ (同Portfolio)     │ (不同Portfolio)│
    └──────────┘        └──────────┘        └──────────┘
```

- 同一个 Portfolio 下的策略共享一个数据源实例
- 不同 Portfolio 各自有独立的数据源

### 4.3 实现计划

#### 第一阶段：策略编辑表单（前端）
1. 扩展 `Strategy` 类型定义
2. 添加默认配置常量
3. 重构策略创建/编辑对话框，支持多 Tab
4. 添加 Provider 下拉选择

#### 第二阶段：后端 Schema 扩展
1. 扩展 `StrategyCreate` / `StrategyUpdate` Schema
2. 添加默认配置常量

#### 第三阶段：数据源服务重构
1. 创建 `DataSourceManager` 管理数据源生命周期
2. 按 Portfolio 维度维护数据源实例
3. 改进 `StrategyRunner` 使用共享数据源
4. 实现信号过滤流程
5. 实现持仓监控

#### 第四阶段：测试与优化
1. 集成测试多策略场景
2. 性能优化

## 5. 待确认

- [x] 触发方式：事件驱动 + 定时兜底
- [x] 数据源：价格 + Activity + Sports 比分（自动识别）
- [x] 持仓监控：持续监控，止盈/止损/比分逆转触发平仓
- [x] 默认配置模板
- [x] 默认 Prompt 模板