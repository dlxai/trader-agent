# 资金流辅助止盈止损系统

## 简介

本模块实现了资金流分析辅助决策系统，通过实时监控市场资金流向，结合价格信号，为交易决策提供智能支持。

## 核心功能

1. **资金流数据收集**：净资金流统计、唯一交易者统计、价格变动关联分析
2. **信号计算**：资金加速信号、极端流检测、连续流统计、资金强度评分
3. **辅助决策**：权重融合、极端情况处理、置信度计算
4. **统计分析**：准确率统计、失效分析、回测报告、实时监控

## 快速开始

### 安装依赖

```bash
pip install pandas numpy
```

### 基础使用

```python
from strategy.capital_flow_analyzer import create_default_system
from datetime import datetime, timedelta

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

print(f"决策: {result.action.value}")
print(f"退出比例: {result.exit_ratio:.0%}")
print(f"置信度: {result.confidence:.1%}")
```

## 文件结构

```
packages/strategy-py/
├── src/strategy/
│   ├── __init__.py
│   └── capital_flow_analyzer.py  # 主实现文件
├── tests/
│   └── test_capital_flow_analyzer.py  # 单元测试
├── examples/
│   └── capital_flow_example.py  # 使用示例
└── docs/
    └── capital_flow_analyzer.md  # 详细文档
```

## 运行测试

```bash
# 运行所有测试
cd packages/strategy-py
python -m pytest tests/test_capital_flow_analyzer.py -v

# 运行特定测试类
python -m pytest tests/test_capital_flow_analyzer.py::TestCapitalFlowCollector -v

# 运行示例
python examples/capital_flow_example.py
```

## 配置参数

### 数据收集器

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| windows | List[int] | [60, 300, 900] | 时间窗口（秒） |
| max_history | int | 10000 | 最大历史记录数 |

### 信号计算器

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| history_window | int | 300 | 历史数据窗口 |
| acceleration_lookback | int | 3 | 加速检测回看期数 |
| extreme_std_threshold | float | 2.0 | 极端流标准差阈值 |

### 决策引擎

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| weights | Dict[str, float] | {"price_based_exit": 0.7, ...} | 决策权重 |
| confidence_threshold | float | 0.6 | 置信度阈值 |
| enable_extreme_override | bool | True | 启用极端情况覆盖 |

## 性能基准

在标准开发环境（Python 3.9+, 8GB RAM）下：

- 添加单笔交易：< 0.1ms
- 查询指标（1000条数据）：< 10ms
- 计算所有信号：< 50ms
- 完整决策流程：< 100ms

## 贡献

欢迎提交 Issue 和 Pull Request。在贡献代码时，请：

1. 遵循 PEP 8 编码规范
2. 为新功能添加单元测试
3. 更新相关文档
4. 确保所有测试通过

## 许可证

本模块采用与项目相同的许可证。
