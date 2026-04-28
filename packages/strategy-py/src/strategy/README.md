# 买入策略系统 (Buy Strategy System)

## 概述

买入策略系统是一个完整的多模块交易决策框架，提供从信号生成到订单执行的全流程支持。

## 核心模块

### 1. 信号生成模块 (Signal Generator)

**文件**: `signal_generator.py`

生成多维度交易信号：

#### 技术分析信号
- 支撑位/阻力位突破
- 移动平均线交叉（金叉/死叉）
- RSI超卖/超买信号

#### 基本面信号
- 隐含概率偏差（市场价格 vs 理论概率）
- 赔率优势分析
- 事件驱动信号

#### 资金流信号
- 大单进场检测
- 鲸鱼动向追踪
- 资金流向分析（净流入/流出）

**关键类**:
- `Signal`: 信号数据类
- `SignalType`: 信号类型枚举
- `SignalStrength`: 信号强度枚举
- `TechnicalSignalGenerator`: 技术分析信号生成器
- `CapitalFlowSignalGenerator`: 资金流信号生成器

### 2. 基本面信号模块 (Fundamental Signals)

**文件**: `fundamental_signals.py`

专门处理基于基本面分析的信号：

- **隐含概率偏差**: 识别市场价格与理论概率的差异
- **赔率优势**: 计算预期收益率，寻找有利赔率
- **事件驱动**: 监控重大事件前后的价格异常

**关键类**:
- `FundamentalSignalGenerator`: 基本面信号生成器
- `FundamentalConfig`: 基本面分析配置

### 3. 入场条件验证模块 (Entry Condition)

**文件**: `entry_condition.py`

验证市场是否满足买入条件。已在 `StrategyRunner` 中通过 `_EntryConditionAdapter` 接入。

**验证项**:
- **价格区间检查**: 避免"死亡区间"（$0.60-$0.85）
- **流动性检查**: 确保最小 $1000 流动性
- **订单簿深度检查**: 确保最小 $500 深度
- **到期时间检查**: 避免即将到期（<6h）或过远（>365d）的市场
- **波动率检查**: 避免过高（>50%）或过低（<1%）波动率的市场

**关键类**:
- `EntryConditionValidator`: 入场条件验证器（需传入 MarketInfoSource, LiquiditySource, VolatilitySource 协议实现）
- `EntryConditionConfig`: 入场条件配置
- `EntryValidationResult`: 验证结果
- `EntryCheckResult`: 检查结果枚举

**接入方式**:
```python
# StrategyRunner 内部使用 _EntryConditionAdapter 包装 MarketData
adapter = _EntryConditionAdapter(market_data)
validator = EntryConditionValidator(adapter, adapter, adapter, config=EntryConditionConfig(...))
result = validator.validate(market_id, current_price=0.71)
if not result.can_enter:
    # 拒绝该市场
```

### 4. 仓位大小计算模块 (Position Sizer)

**文件**: `position_sizer.py`

多种策略计算合适的仓位大小：

- **凯利公式** (Kelly Criterion): 基于胜率和赔率的最优仓位
- **固定风险比例**: 每笔交易风险固定资金比例（如2%）
- **信心度加权**: 根据信号强度调整仓位
- **波动率调整**: 根据市场波动率调整仓位

**关键类**:
- `PositionSizer`: 仓位大小计算器
- `PositionSizerConfig`: 仓位配置
- `PositionSizingResult`: 计算结果
- `PortfolioState`: 投资组合状态
- `KellyCriterionStrategy`: 凯利公式策略
- `FixedRiskStrategy`: 固定风险策略
- `ConfidenceWeightedStrategy`: 信心度加权策略

### 5. 订单执行模块 (Execution Strategy)

**文件**: `execution_strategy.py`

多种订单执行策略：

- **立即执行** (Immediate): 立即以限价或市价下单
- **限价单** (Limit): 指定价格，可能不成交
- **市价单** (Market): 立即成交，滑点大
- **TWAP**: 时间加权平均价格，适合大额订单
- **分批建仓** (DCA): 分散买入时机，降低风险

**关键类**:
- `ExecutionStrategy`: 执行策略基类
- `ImmediateExecutionStrategy`: 立即执行策略
- `DCAExecutionStrategy`: 分批建仓策略
- `TWAPExecutionStrategy`: TWAP策略
- `ExecutionPlan`: 执行计划
- `Order`: 订单数据类
- `OrderType`: 订单类型枚举
- `OrderStatus`: 订单状态枚举

### 6. 主策略协调器 (Buy Strategy)

**文件**: `buy_strategy.py`

协调各模块工作，提供完整的买入决策流程：

- 信号生成
- 入场条件验证
- 仓位大小计算
- 订单执行
- 交易记录
- 状态管理

**关键类**:
- `BuyStrategy`: 主策略类
- `BuyStrategyConfig`: 策略配置
- `BuyStrategyState`: 策略状态
- `TradeRecord`: 交易记录

## 使用示例

### 基本使用

```python
from strategy import (
    BuyStrategy,
    BuyStrategyConfig,
    PortfolioState,
    ExecutionStrategyType,
)

# 创建配置
config = BuyStrategyConfig(
    min_signal_strength=SignalStrength.MODERATE,
    default_execution_strategy=ExecutionStrategyType.DCA,
)

# 初始化策略
strategy = BuyStrategy(
    config=config,
    price_source=your_price_source,
    market_data_source=your_market_data_source,
    # ... 其他数据源
)

# 设置投资组合
portfolio = PortfolioState(
    total_capital=10000.0,
    available_capital=10000.0,
    total_risk_exposure=0.0,
)
strategy.set_portfolio(portfolio)

# 激活策略
strategy.activate()

# 评估市场并执行交易
async def trade():
    # 评估市场
    result = await strategy.evaluate_market("market-001")

    if result['can_enter']:
        # 执行买入
        success, trade = await strategy.enter_position(
            market_id="market-001",
            size=result['position_sizing']['final_size'],
            price=result['position_sizing'].get('entry_price'),
        )

        if success:
            print(f"Trade executed: {trade.trade_id}")

# 运行
asyncio.run(trade())
```

### 运行完整策略周期

```python
# 运行一个完整的策略周期
result = await strategy.run_cycle(
    market_ids=["market-001", "market-002", "market-003"]
)

print(f"Markets evaluated: {result['markets_evaluated']}")
print(f"Signals generated: {result['signals_generated']}")
print(f"Trades executed: {result['trades_executed']}")
```

## 配置说明

### 信号生成配置

```python
config = BuyStrategyConfig(
    min_signal_strength=SignalStrength.MODERATE,  # 最小信号强度
    min_signal_confidence=0.6,  # 最小信号置信度
    max_signals_per_market=5,  # 每个市场最大信号数
)
```

### 入场条件配置

```python
from strategy import EntryConditionConfig

entry_config = EntryConditionConfig(
    price_min=0.05,  # 最小价格
    price_max=0.95,  # 最大价格
    death_zone_min=0.60,  # 死亡区间下界
    death_zone_max=0.85,  # 死亡区间上界
    min_liquidity=1000,  # 最小流动性
    min_order_book_depth=500,  # 最小订单簿深度
)
```

### 仓位大小配置

```python
from strategy import PositionSizerConfig, PositionSizingMethod

position_config = PositionSizerConfig(
    default_method=PositionSizingMethod.FIXED_RISK,
    fixed_risk_percentage=0.02,  # 每笔交易风险 2%
    max_single_position_pct=0.25,  # 单市场最大 25%
    max_total_exposure_pct=0.80,  # 总敞口最大 80%
)
```

## 测试

运行示例：

```bash
cd packages/strategy-py
python examples/buy_strategy_example.py
```

## 依赖

- Python 3.8+
- asyncio
- dataclasses
- typing
- datetime
- logging
- json
- pathlib

## 许可证

MIT License
