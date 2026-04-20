# 资金流分析辅助决策系统

## 概述

资金流分析辅助决策系统（Capital Flow Analyzer）是一套用于辅助交易决策的智能分析系统。它通过实时监控和分析市场资金流向，结合价格信号，为止盈止损决策提供数据支持。

## 核心模块

### 1. CapitalFlowCollector（资金流数据收集器）

负责实时收集和统计资金流数据：

- **净资金流统计**：支持多个时间窗口（默认1分钟、5分钟、15分钟）
- **唯一交易者统计**：跟踪不同交易者的买卖行为
- **价格变动关联**：分析资金流与价格变动的相关性
- **成交量分布**：分析成交量的时间分布

**主要方法**：

```python
# 添加单笔交易
collector.add_trade(
    timestamp=datetime.now(),
    price=0.55,
    size=100,
    side="buy",  # or "sell"
    trader_id="trader_001"
)

# 批量添加交易
collector.add_trades_batch(trades_list)

# 获取资金流指标
metrics = collector.get_flow_metrics(window_seconds=60)
print(f"净流入: {metrics.net_flow}")
print(f"流入: {metrics.inflow}")
print(f"流出: {metrics.outflow}")

# 获取多窗口指标
multi_metrics = collector.get_multi_window_metrics()

# 获取资金流分布
distribution = collector.get_flow_distribution(window_seconds=3600, bins=10)
```

### 2. FlowSignalCalculator（资金流信号计算器）

基于资金流数据计算各类交易信号：

- **资金加速信号**：检测连续多分钟的流入/流出加速
- **极端流检测**：识别超过历史均值2倍标准差的异常流动
- **连续流统计**：统计连续N分钟同向流入/流出的情况
- **资金流向强度评分**：综合多维度计算资金强度（0-100分）

**主要方法**：

```python
# 创建计算器
calculator = FlowSignalCalculator(
    history_window=300,           # 历史数据窗口
    acceleration_lookback=3,      # 加速检测回看期数
    extreme_std_threshold=2.0,    # 极端流标准差阈值
    consecutive_threshold=3       # 连续流阈值
)

# 添加分钟资金流数据
calculator.add_minute_flow(timestamp, net_flow)

# 计算所有信号
signals = calculator.calculate_signals()

# 处理信号
for signal in signals:
    print(f"信号类型: {signal.signal_type}")
    print(f"方向: {signal.direction.value}")
    print(f"强度: {signal.strength.name}")
    print(f"置信度: {signal.confidence:.1%}")
    print(f"建议行动: {signal.suggested_action.value}")
```

### 3. FlowAssistedDecision（辅助决策引擎）

融合价格信号和资金流信号，提供智能决策：

- **权重分配**：价格基础退出权重(0.7) + 资金流加速权重(0.3)
- **信号融合逻辑**：价格信号为主，资金流为辅
- **极端情况处理**：资金流异常时提前退出或推迟退出
- **置信度计算**：结合多个信号来源的不确定性

**主要方法**：

```python
# 创建决策引擎
decision = FlowAssistedDecision(
    weights={
        "price_based_exit": 0.7,
        "flow_acceleration": 0.3,
    },
    confidence_threshold=0.6,
    enable_extreme_override=True
)

# 做出决策
result = decision.make_decision(
    position_id="pos_123",
    price_signal={
        "type": "take_profit",
        "trigger_price": 0.65,
        "profit_pct": 0.20
    },
    flow_signals=flow_signals,  # 从 calculator 获取
    context={"market": "BTC-USD"}
)

# 处理决策结果
print(f"决策行动: {result.action.value}")
print(f"退出比例: {result.exit_ratio:.0%}")
print(f"置信度: {result.confidence:.1%}")
print("决策理由:")
for reason in result.reasoning:
    print(f"  - {reason}")
```

### 4. FlowAnalytics（统计和报告模块）

提供完整的资金流分析统计和报告功能：

- **检测准确率统计**：真阳性、假阳性、真阴性、假阴性
- **资金流失效分析**：何时信号有效，何时无效
- **历史回测报告**：基于历史数据验证策略效果
- **实时监控面板**：当前资金流状态、信号强度

**主要方法**：

```python
# 创建分析模块
analytics = FlowAnalytics(
    performance_window=1000,
    backtest_enabled=True,
    realtime_dashboard=True
)

# 记录预测结果
analytics.record_prediction(
    prediction={"is_positive": True, "confidence": 0.8},
    actual_outcome=True,  # 预测正确
    metadata={"signal_type": "acceleration"}
)

# 记录信号
analytics.record_signal(flow_signal, outcome="correct")

# 记录决策
analytics.record_decision(decision_result, actual_pnl=0.05)

# 获取性能摘要
summary = analytics.get_performance_summary()
print(f"总预测数: {summary['predictions']['total']}")
print(f"准确率: {summary['metrics']['accuracy']:.1%}")
print(f"精确率: {summary['metrics']['precision']:.1%}")
print(f"召回率: {summary['metrics']['recall']:.1%}")
print(f"F1分数: {summary['metrics']['f1_score']:.2f}")

# 分析信号有效性
effectiveness = analytics.analyze_signal_effectiveness(
    signal_type="acceleration",
    time_range=(datetime.now() - timedelta(days=7), datetime.now())
)

# 生成回测报告
backtest_report = analytics.generate_backtest_report(
    start_time=datetime.now() - timedelta(days=30),
    end_time=datetime.now()
)

# 获取实时监控面板
dashboard = analytics.get_realtime_dashboard()
```

## 快速开始

### 基础使用

```python
from strategy.capital_flow_analyzer import create_default_system

# 创建系统
exit_system = create_default_system(enabled=True)

# 添加交易数据
exit_system.add_trade(
    timestamp=datetime.now(),
    price=0.55,
    size=100,
    side="buy",
    trader_id="trader_001"
)

# 注册持仓
exit_system.register_position(
    position_id="pos_123",
    entry_price=0.5,
    size=1000,
    side="long"
)

# 检查退出条件
result = exit_system.check_exit_conditions(
    position_id="pos_123",
    current_price=0.6,
    price_signal={"type": "take_profit", "profit_pct": 0.2}
)

if result.action.value == "exit_immediately":
    print("建议立即退出!")
```

### 自定义配置

```python
from strategy.capital_flow_analyzer import CapitalFlowAssistedExit

# 创建自定义配置的系统
exit_system = CapitalFlowAssistedExit(
    config={"enabled": True},
    collector_config={
        "windows": [60, 300, 600],  # 1分钟、5分钟、10分钟
        "max_history": 5000,
    },
    calculator_config={
        "history_window": 200,
        "extreme_std_threshold": 2.5,
        "consecutive_threshold": 4,
    },
    decision_config={
        "weights": {
            "price_based_exit": 0.5,
            "flow_acceleration": 0.5,
        },
        "confidence_threshold": 0.7,
    },
    analytics_config={
        "performance_window": 2000,
        "backtest_enabled": True,
    }
)
```

## 性能考虑

### 数据缓存策略

- **原始交易记录**：使用 `deque` 存储，支持 O(1) 的添加和自动淘汰
- **DataFrame 缓存**：交易数据缓存为 DataFrame，TTL 为 1 秒
- **指标缓存**：预计算的窗口指标缓存 1 秒

### 性能基准

在标准开发环境（Python 3.9+, 8GB RAM）下：

- 添加单笔交易：< 0.1ms
- 查询指标（1000条数据）：< 10ms
- 计算所有信号：< 50ms
- 完整决策流程：< 100ms

### 优化建议

1. **高并发场景**：考虑使用异步 I/O 或线程池
2. **大数据量**：增加 `max_history` 并定期清理旧数据
3. **实时性要求**：调整缓存 TTL 或禁用缓存
4. **内存限制**：减小历史窗口或使用流式计算

## 配置参考

### CapitalFlowCollector 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| windows | List[int] | [60, 300, 900] | 时间窗口（秒） |
| max_history | int | 10000 | 最大历史记录数 |
| config | Dict | {} | 额外配置 |

### FlowSignalCalculator 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| history_window | int | 300 | 历史数据窗口 |
| acceleration_lookback | int | 3 | 加速检测回看期数 |
| extreme_std_threshold | float | 2.0 | 极端流标准差阈值 |
| consecutive_threshold | int | 3 | 连续流阈值 |

### FlowAssistedDecision 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| weights | Dict[str, float] | {"price_based_exit": 0.7, "flow_acceleration": 0.3} | 决策权重 |
| confidence_threshold | float | 0.6 | 置信度阈值 |
| enable_extreme_override | bool | True | 启用极端情况覆盖 |

### FlowAnalytics 配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| performance_window | int | 1000 | 性能统计窗口 |
| backtest_enabled | bool | True | 启用回测功能 |
| realtime_dashboard | bool | True | 启用实时监控面板 |

## 常见问题

### Q: 如何处理缺失的交易者ID？

A: `trader_id` 是可选参数。如果不提供，唯一交易者统计将基于其他维度。

### Q: 系统支持哪些时间精度？

A: 系统支持秒级精度的时间戳。对于更高精度（毫秒/微秒），会截断到秒级。

### Q: 如何处理时区问题？

A: 建议使用 UTC 时间或确保所有时间戳使用相同时区。系统内部不进行时区转换。

### Q: 可以同时跟踪多个持仓吗？

A: 是的，使用 `register_position()` 注册多个持仓，每个持仓有独立的ID。

### Q: 如何清空历史数据？

A: 创建新的实例或调用内部方法（不推荐在生产环境使用）：

```python
# 创建新实例（推荐）
new_system = create_default_system()

# 或清空特定模块
collector._trades.clear()
calculator._minute_flows.clear()
```

## 贡献指南

欢迎提交 Issue 和 Pull Request。在贡献代码时，请：

1. 遵循 PEP 8 编码规范
2. 为新功能添加单元测试
3. 更新相关文档
4. 确保所有测试通过

## 许可证

本模块采用与项目相同的许可证。

## 更新日志

### v1.0.0 (2024-XX-XX)

- 初始版本发布
- 实现四个核心模块
- 支持多种信号检测算法
- 提供完整的统计报告功能
