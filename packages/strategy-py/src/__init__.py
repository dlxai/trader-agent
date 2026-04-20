"""
策略Python包

该包提供了完整的交易策略实现，包括：
- 买入策略决策 (BuyStrategy)
- 执行引擎 (ExecutionEngine)
- 信号评估器 (SignalEvaluator)
- Polymarket专用信号
- 活动分析器
- 实时服务
"""

__version__ = "1.0.0"

# 从strategy模块导出所有公共接口
from strategy import *
