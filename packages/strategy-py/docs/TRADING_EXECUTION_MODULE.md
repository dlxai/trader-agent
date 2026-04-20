# 交易执行模块文档

## 概述

交易执行模块是策略Python包的核心组件，负责从策略信号到实际订单执行的完整转换过程。该模块包含三个主要组件：

1. **买入策略决策 (BuyStrategy)** - 综合多维度信号做出买入决策
2. **执行引擎 (ExecutionEngine)** - 将决策转换为实际订单并执行
3. **信号评估器 (SignalEvaluator)** - 评估信号质量和历史表现

## 文件结构

```
packages/strategy-py/src/strategy/
├── __init__.py              # 模块导出
├── buy_strategy.py          # 买入策略决策引擎
├── execution_engine.py      # 交易执行引擎
├── signal_evaluator.py      # 信号评估器
├── polymarket_signals.py    # Polymarket专用信号
├── activity_analyzer.py    # 活动分析器
├── realtime_service.py     # 实时服务
├── signal_generator.py     # 信号生成器基类
├── entry_condition.py      # 入场条件
├── entry_validator.py      # 入场验证器
├── position_sizer.py       # 仓位计算
└── capital_flow_analyzer.py # 资本流分析器
```

## 核心组件

### 1. BuyStrategy (买入策略决策)

#### 功能
- 综合多维度信号评估市场机会
- 执行风险检查和约束验证
- 计算最优仓位和退出水平
- 生成详细的决策理由

#### 评估维度
1. **赔率偏向 (odds_bias)** - 赔率是否偏离真实概率
2. **时间衰减 (time_decay)** - 到期时间价值评估
3. **订单簿压力 (orderbook_pressure)** - 买卖盘不平衡
4. **资金流向 (capital_flow)** - 聪明钱动向
5. **信息优势 (information_edge)** - 价格-成交量背离

#### 关键约束
- **死亡区间**: $0.60-$0.85 不交易
- **单笔持仓上限**: 默认10%
- **总持仓限制**: 默认20个
- **流动性检查**: 最小$10,000

#### 使用示例

```python
from strategy import BuyStrategy, BuyStrategyConfig, MarketContext

# 创建配置
config = BuyStrategyConfig(
    death_zone_min=0.60,
    death_zone_max=0.85,
    odds_bias_weight=0.25,
    buy_threshold=0.65,
    max_single_position_pct=0.10
)

# 创建信号生成器
def my_signal_generator(context: MarketContext):
    # 实现信号逻辑
    return SignalStrength.STRONG, 0.8, "Strong buying signal"

# 初始化策略
buy_strategy = BuyStrategy(
    signal_generators=[my_signal_generator],
    risk_manager=risk_manager,
    config=config
)

# 评估市场
market_context = MarketContext(
    market_id="market-123",
    current_price=0.45,
    # ... 其他字段
)

decision = await buy_strategy.evaluate(market_context)
print(f"决策: {decision.decision.value}, 置信度: {decision.confidence}")
```

### 2. ExecutionEngine (执行引擎)

#### 功能
- 接收买入决策并执行最终风险检查
- 计算订单参数（size, price, type）
- 支持多种订单类型（市价、限价、TWAP）
- 跟踪订单状态和持仓更新
- 生成详细的执行报告

#### 支持的订单类型
1. **Market Order** - 市价单（紧急执行）
2. **Limit Order** - 限价单（指定价格）
3. **TWAP** - 时间加权平均价格（大单拆分）
4. **Stop Limit** - 止损限价单

#### 关键特性
- **滑点保护**: 最大1%滑点容忍
- **部分成交处理**: 支持50%最小成交阈值
- **TWAP执行**: 大单自动拆分执行
- **执行超时**: 默认5分钟订单超时

#### 使用示例

```python
from strategy import ExecutionEngine, ExecutionConfig, OrderType

# 创建配置
config = ExecutionConfig(
    preferred_order_type=OrderType.LIMIT,
    fallback_to_market=True,
    default_limit_offset=0.001,
    max_slippage_tolerance=0.02,
    allow_partial_fills=True,
    min_fill_threshold=0.5
)

# 初始化执行引擎
execution_engine = ExecutionEngine(
    order_manager=order_manager,
    risk_manager=risk_manager,
    position_tracker=position_tracker,
    config=config
)

# 执行买入决策
execution_report = await execution_engine.execute_buy(decision_output)

# 查看执行结果
print(f"执行状态: {execution_report.status.value}")
print(f"成交数量: {execution_report.filled_size}")
print(f"平均成交价格: {execution_report.avg_fill_price}")
print(f"滑点: {execution_report.slippage:.4%}")
```

### 3. SignalEvaluator (信号评估器)

#### 功能
- 记录和跟踪信号历史
- 评估信号质量和准确性
- 计算多种性能指标（夏普比率、胜率等）
- 动态调整信号权重
- 生成信号优化建议

#### 评估维度
1. **准确性 (Accuracy)** - 预测正确率
2. **精确率 (Precision)** - 正例预测的准确性
3. **召回率 (Recall)** - 正例的识别能力
4. **夏普比率 (Sharpe Ratio)** - 风险调整收益
5. **胜率 (Win Rate)** - 盈利交易比例
6. **盈亏比 (Profit Factor)** - 盈利/亏损比率

#### 质量等级
- **EXCELLENT** - 优秀的信号
- **GOOD** - 良好的信号
- **FAIR** - 一般的信号
- **POOR** - 较差的信号
- **UNRELIABLE** - 不可靠的信号

#### 使用示例

```python
from strategy import (
    SignalEvaluator, SignalEvaluationConfig,
    SignalRecord, SignalOutcome, SignalDirection
)
import sqlite3

# 创建评估器（使用内存数据库）
db = sqlite3.connect(':memory:')
evaluator = SignalEvaluator(db)

# 配置评估参数
evaluator.config = SignalEvaluationConfig(
    min_samples_for_metrics=5,
    min_accuracy_threshold=0.55,
    enable_dynamic_weighting=True
)

# 记录信号
signal = SignalRecord(
    signal_id="sig_001",
    signal_name="momentum_signal",
    market_id="market_A",
    outcome_id="outcome_1",
    direction=SignalDirection.BUY,
    strength=0.8,
    timestamp=datetime.now(),
    predicted_direction=SignalDirection.BUY,
    confidence=0.75
)

await evaluator.record_signal(signal)

# 记录结果
outcome = SignalOutcome(
    signal_id="sig_001",
    market_id="market_A",
    outcome_id="outcome_1",
    actual_direction=SignalDirection.BUY,
    actual_return=0.15,
    realized_pnl=150.0,
    signal_timestamp=datetime.now() - timedelta(days=10),
    outcome_timestamp=datetime.now() - timedelta(days=7),
    time_to_outcome=timedelta(days=3),
    prediction_correct=True,
    accuracy_score=0.85,
    profitability_score=0.80
)

await evaluator.record_outcome(outcome)

# 获取信号指标
metrics = evaluator.get_signal_metrics("momentum_signal")
if metrics:
    print(f"信号: {metrics.signal_name}")
    print(f"准确率: {metrics.accuracy:.2%}")
    print(f"夏普比率: {metrics.sharpe_ratio:.3f}")
    print(f"质量评级: {metrics.quality.value}")

# 获取所有权重
weights = evaluator.get_all_weights()
print("信号权重:", weights)

# 获取优化建议
recommendations = evaluator.get_signal_recommendations()
print("优化建议:", recommendations)
```

## 集成使用

完整的交易流程集成示例如下：

```python
import asyncio
from strategy import (
    BuyStrategy, BuyStrategyConfig,
    ExecutionEngine, ExecutionConfig,
    SignalEvaluator, SignalEvaluationConfig,
    MarketContext
)

async def trading_workflow():
    # 1. 初始化组件
    buy_strategy = BuyStrategy(
        signal_generators=[signal_gen_1, signal_gen_2],
        risk_manager=risk_manager,
        config=BuyStrategyConfig()
    )

    execution_engine = ExecutionEngine(
        order_manager=order_manager,
        risk_manager=risk_manager,
        position_tracker=position_tracker,
        config=ExecutionConfig()
    )

    signal_evaluator = SignalEvaluator(db_connection)

    # 2. 评估市场机会
    market_context = create_market_context()  # 创建市场上下文
    decision = await buy_strategy.evaluate(market_context)

    # 3. 执行决策
    if decision.decision.value in ['strong_buy', 'buy']:
        execution_report = await execution_engine.execute_buy(decision)

        # 4. 记录信号和结果用于评估
        await signal_evaluator.record_signal(create_signal_record(decision))

        if execution_report.status.value == 'success':
            await signal_evaluator.record_outcome(
                create_outcome_record(decision, execution_report)
            )

    # 5. 获取信号评估和优化建议
    metrics = signal_evaluator.get_signal_metrics("momentum_signal")
    recommendations = signal_evaluator.get_signal_recommendations()

    return decision, execution_report, metrics, recommendations

# 运行工作流
if __name__ == "__main__":
    asyncio.run(trading_workflow())
```

## 测试

运行示例代码：

```bash
# 进入策略包目录
cd packages/strategy-py

# 运行使用示例
python examples/trading_execution_example.py
```

## 依赖

- Python >= 3.8
- 标准库: asyncio, dataclasses, datetime, enum, typing, decimal, json, sqlite3, statistics

## 许可

MIT License
