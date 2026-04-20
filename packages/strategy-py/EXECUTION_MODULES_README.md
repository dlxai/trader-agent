# 交易执行模块

本文档描述了交易执行模块的实现，包括买入策略决策引擎、执行引擎和信号评估器。

## 模块结构

```
strategy/
├── __init__.py                    # 导出所有模块
├── buy_strategy.py                # 买入策略决策引擎
├── execution_engine.py            # 执行引擎
├── signal_evaluator.py            # 信号评估器
└── ...
```

## 1. 买入策略决策 (BuyStrategy)

### 功能概述

买入策略引擎综合多种信号源，通过加权评分系统做出买入决策。

### 主要特性

- **多维度信号评估**: 赔率偏向、时间衰减、订单簿压力、资金流向、信息优势
- **风险检查**: 死亡区间检测、持仓限制、总敞口限制、相关性检查
- **动态仓位计算**: 基于评分和风险等级计算最优仓位
- **综合评分系统**: 加权信号组合，生成置信度评分

### 使用示例

```python
from decimal import Decimal
from datetime import timedelta
from strategy import (
    BuyStrategy, BuyStrategyConfig, MarketCondition,
    SignalType, SignalGenerator
)

# 配置
config = BuyStrategyConfig(
    min_composite_score=0.6,
    min_confidence=0.7,
    max_position_size_usd=Decimal("1000"),
)

# 创建策略
strategy = BuyStrategy(
    signal_generators=signal_generators,
    risk_manager=risk_manager,
    config=config,
)

# 评估市场
market_condition = MarketCondition(
    market_id="0x123...",
    current_price=Decimal("0.35"),
    best_bid=Decimal("0.34"),
    best_ask=Decimal("0.36"),
    volume_24h=Decimal("50000"),
    liquidity_depth=Decimal("20000"),
    spread_pct=0.02,
    volatility=0.03,
    time_to_resolution=timedelta(days=3),
)

decision = await strategy.evaluate(market_condition)

if decision.should_buy:
    print(f"建议买入: {decision.side} ${decision.size} @ ${decision.price}")
    print(f"置信度: {decision.confidence:.2%}, 评分: {decision.composite_score:.3f}")
```

## 2. 执行引擎 (ExecutionEngine)

### 功能概述

执行引擎负责将买入决策转换为实际订单，管理订单生命周期，并生成执行报告。

### 主要特性

- **多种订单类型**: 市价单、限价单、TWAP（时间加权平均价格）、冰山订单
- **订单状态跟踪**: 实时监控订单状态变化
- **滑点保护**: 可配置的滑点容忍度
- **TWAP执行**: 大单拆分，时间均匀执行
- **执行报告**: 详细的执行结果和性能指标

### 使用示例

```python
from strategy import (
    ExecutionEngine, ExecutionConfig,
    OrderManager, RiskManager, PositionTracker
)

# 配置
config = ExecutionConfig(
    default_slippage_bps=50,
    max_slippage_bps=200,
    order_timeout_seconds=60,
    twap_slices=5,
    twap_interval_seconds=60,
    dry_run=False,  # 设置为True进行模拟
)

# 创建引擎
engine = ExecutionEngine(
    order_manager=order_manager,
    risk_manager=risk_manager,
    position_tracker=position_tracker,
    config=config,
)

# 执行买入决策
report = await engine.execute_buy_decision(decision, market_condition)

# 检查结果
print(f"执行结果: {report.result.name}")
print(f"成交率: {report.fill_percentage:.1f}%")
print(f"滑点: {report.slippage_bps} bps")
print(f"执行时间: {report.execution_time_ms} ms")
```

## 3. 信号评估器 (SignalEvaluator)

### 功能概述

信号评估器负责评估信号质量和历史表现，通过回测和统计分析优化信号权重。

### 主要特性

- **信号质量评估**: 准确率、夏普比率、胜率、盈亏比等多维度指标
- **历史回测**: 基于历史信号数据模拟交易
- **权重优化**: 等权重、基于表现、夏普最大化等多种优化方法
- **性能摘要**: 综合性能统计和分析
- **数据持久化**: SQLite数据库存储信号历史和指标

### 使用示例

```python
from strategy import SignalEvaluator, create_signal_evaluator

# 创建评估器
evaluator = create_signal_evaluator(
    db_path="signals.db",
    signal_sources=[],
    market_data_provider=None,
)

# 记录信号
record_id = evaluator.record_signal(
    signal_type="ODDS_BIAS",
    market_id="0x123...",
    side="YES",
    confidence=0.8,
    score=0.7,
    predicted_outcome="YES",
)

# 后续更新结果
evaluator.update_signal_result(
    record_id=record_id,
    actual_outcome="YES",
    pnl=Decimal("50"),
)

# 评估信号质量
metrics = await evaluator.evaluate_signal("ODDS_BIAS", lookback_days=30)

print(f"信号类型: {metrics.signal_type}")
print(f"准确率: {metrics.accuracy:.2%}")
print(f"夏普比率: {metrics.sharpe_ratio:.3f}")
print(f"胜率: {metrics.win_rate:.2%}")
print(f"质量分数: {metrics.quality_score:.3f}")
print(f"质量等级: {metrics.quality_grade.name}")

# 优化权重
weights = await evaluator.optimize_weights(
    lookback_days=30,
    method="performance_based"
)

print("\n优化后的权重:")
for signal_type, weight in weights.weights.items():
    print(f"  {signal_type}: {weight:.3f}")

# 获取性能摘要
summary = evaluator.get_performance_summary(
    start_date=datetime.now() - timedelta(days=30),
    end_date=datetime.now(),
)

print(f"\n性能摘要:")
print(f"  总信号数: {summary.get('total_signals', 0)}")
print(f"  准确率: {summary.get('accuracy', 0):.2%}")
print(f"  胜率: {summary.get('win_rate', 0):.2%}")
```

## 测试

运行单元测试：

```bash
cd packages/strategy-py
python -m pytest tests/test_execution_modules.py -v
```

运行示例：

```bash
cd packages/strategy-py/examples
python execution_module_example.py
```

## 依赖

- Python 3.8+
- numpy (用于数值计算)
- sqlite3 (内置)

安装依赖：

```bash
pip install numpy
```

## 注意事项

1. **死亡区间**: $0.60-$0.85 价格区间不交易
2. **最小仓位**: $10 最小交易金额
3. **超时**: 默认订单超时 60 秒
4. **滑点**: 默认滑点容忍 50 bps (0.5%)

## 许可证

MIT License
