"""
资金流辅助止盈止损系统 - 使用示例

本示例展示如何使用 CapitalFlowAssistedExit 系统来：
1. 初始化系统
2. 添加交易数据
3. 注册持仓
4. 检查退出条件
5. 获取分析报告
"""

import random
import time
from datetime import datetime, timedelta
from typing import List, Dict

# 导入资金流分析模块
import sys
sys.path.insert(0, 'packages/strategy-py/src')

from strategy.capital_flow_analyzer import (
    CapitalFlowAssistedExit,
    CapitalFlowCollector,
    FlowSignalCalculator,
    FlowAssistedDecision,
    FlowAnalytics,
    FlowDirection,
    SignalStrength,
    DecisionAction,
    create_default_system,
)


def example_1_basic_usage():
    """示例1: 基本使用方法"""
    print("=" * 60)
    print("示例1: 基本使用")
    print("=" * 60)

    # 创建默认配置的系统
    exit_system = create_default_system(enabled=True)

    # 模拟添加一些交易数据
    print("\n1. 添加模拟交易数据...")
    base_time = datetime.now() - timedelta(minutes=10)

    for i in range(60):  # 60分钟的数据
        timestamp = base_time + timedelta(minutes=i)
        # 模拟价格从0.5上涨到0.65
        price = 0.5 + (i / 60) * 0.15 + random.uniform(-0.01, 0.01)
        size = random.uniform(10, 100)
        # 前30分钟主要是买入，后30分钟主要是卖出
        side = "buy" if i < 30 or random.random() > 0.6 else "sell"

        exit_system.add_trade(timestamp, price, size, side, trader_id=f"trader_{i % 20}")

    print(f"   已添加60条交易记录")

    # 注册持仓
    print("\n2. 注册持仓...")
    exit_system.register_position(
        position_id="pos_demo_001",
        entry_price=0.5,
        size=1000,
        side="long",
        metadata={"market": "BTC-USD", "strategy": "trend_following"}
    )
    print("   持仓已注册: pos_demo_001")

    # 检查退出条件
    print("\n3. 检查退出条件...")
    current_price = 0.62  # 当前盈利24%

    # 模拟价格止盈信号
    price_signal = {
        "type": "take_profit",
        "trigger_price": 0.60,
        "profit_pct": 0.24
    }

    result = exit_system.check_exit_conditions(
        position_id="pos_demo_001",
        current_price=current_price,
        price_signal=price_signal
    )

    print(f"\n   决策结果:")
    print(f"   - 行动: {result.action.value}")
    print(f"   - 退出比例: {result.exit_ratio:.0%}")
    print(f"   - 置信度: {result.confidence:.1%}")
    print(f"   - 推理过程:")
    for reason in result.reasoning:
        print(f"     * {reason}")

    # 获取监控面板
    print("\n4. 实时监控面板:")
    dashboard = exit_system.get_realtime_dashboard()
    print(f"   - 系统状态: {'启用' if dashboard.get('timestamp') else '禁用'}")
    if "performance" in dashboard:
        perf = dashboard["performance"]
        print(f"   - 累计准确率: {perf.get('accuracy', 0):.1%}")
        print(f"   - F1分数: {perf.get('f1_score', 0):.2f}")

    return exit_system


def example_2_custom_configuration():
    """示例2: 自定义配置"""
    print("\n" + "=" * 60)
    print("示例2: 自定义配置")
    print("=" * 60)

    # 自定义权重配置
    custom_weights = {
        "price_based_exit": 0.5,      # 降低价格信号权重
        "flow_acceleration": 0.5,   # 提高资金流权重
    }

    # 创建自定义配置的系统
    exit_system = CapitalFlowAssistedExit(
        config={"enabled": True},
        decision_config={
            "weights": custom_weights,
            "confidence_threshold": 0.7,  # 提高置信度阈值
            "enable_extreme_override": True,
        },
        collector_config={
            "windows": [60, 300, 600],  # 1分钟、5分钟、10分钟
            "max_history": 5000,
        },
        calculator_config={
            "history_window": 200,
            "extreme_std_threshold": 2.5,  # 更严格的极端流阈值
            "consecutive_threshold": 4,      # 更长的连续流阈值
        },
        analytics_config={
            "performance_window": 2000,
            "backtest_enabled": True,
            "realtime_dashboard": True,
        }
    )

    print("\n已创建自定义配置的系统:")
    print(f"- 价格信号权重: {custom_weights['price_based_exit']}")
    print(f"- 资金流权重: {custom_weights['flow_acceleration']}")
    print(f"- 置信度阈值: 0.7")
    print(f"- 极端流阈值: 2.5σ")

    return exit_system


def example_3_batch_processing():
    """示例3: 批量数据处理"""
    print("\n" + "=" * 60)
    print("示例3: 批量数据处理与回测")
    print("=" * 60)

    # 创建系统
    exit_system = create_default_system(enabled=True)

    # 生成批量历史数据
    print("\n1. 生成批量历史数据...")
    batch_trades = []
    base_time = datetime.now() - timedelta(hours=2)

    for i in range(500):  # 500条交易记录
        timestamp = base_time + timedelta(seconds=i * 15)  # 每15秒一条
        price = 0.5 + 0.1 * np.sin(i / 50) + random.uniform(-0.02, 0.02)
        size = random.uniform(5, 50)
        side = "buy" if np.sin(i / 50) > 0 else "sell"

        batch_trades.append({
            "timestamp": timestamp,
            "price": price,
            "size": size,
            "side": side,
            "trader_id": f"trader_{i % 30}"
        })

    # 批量添加
    exit_system.add_trades_batch(batch_trades)
    print(f"   已批量添加 {len(batch_trades)} 条交易记录")

    # 获取资金流分布分析
    print("\n2. 资金流分布分析:")
    distribution = exit_system.collector.get_flow_distribution(window_seconds=3600, bins=10)
    if "error" not in distribution:
        print(f"   - 数据点数: {distribution['data_points']}")
        print(f"   - 平均流量: {distribution['mean']:.2f}")
        print(f"   - 标准差: {distribution['std']:.2f}")
        print(f"   - 流量范围: [{distribution['min']:.2f}, {distribution['max']:.2f}]")

    # 生成回测报告
    print("\n3. 回测报告:")
    report = exit_system.analytics.generate_backtest_report()
    if "error" not in report:
        print(f"   - 总决策数: {report['total_decisions']}")
        print(f"   - 预测准确率: {report['prediction_accuracy']:.1%}")
        print(f"   - 行动分布: {report['action_distribution']}")
    else:
        print(f"   - {report['error']}")

    return exit_system


def example_4_integration_with_risk_management():
    """示例4: 与现有风险管理模块集成"""
    print("\n" + "=" * 60)
    print("示例4: 与风险管理模块集成")
    print("=" * 60)

    # 导入现有的风险管理模块
    try:
        from risk_management.trailing_stop_service import TrailingStopService
        from risk_management.partial_exit_service import PartialExitService
        print("\n成功导入风险管理模块")
    except ImportError as e:
        print(f"\n无法导入风险管理模块: {e}")
        print("继续演示集成模式...")
        TrailingStopService = None
        PartialExitService = None

    # 创建资金流辅助退出系统
    flow_exit = create_default_system(enabled=True)

    # 模拟集成场景
    print("\n1. 模拟持仓场景:")

    # 注册持仓
    position_id = "pos_integration_001"
    entry_price = 0.55
    current_price = 0.68  # 盈利约23%

    flow_exit.register_position(
        position_id=position_id,
        entry_price=entry_price,
        size=500,
        side="long"
    )

    print(f"   - 持仓ID: {position_id}")
    print(f"   - 入场价: ${entry_price:.2f}")
    print(f"   - 当前价: ${current_price:.2f}")
    print(f"   - 当前盈利: {(current_price - entry_price) / entry_price:.1%}")

    # 添加历史交易数据
    print("\n2. 添加历史交易数据...")
    base_time = datetime.now() - timedelta(minutes=30)

    for i in range(60):
        timestamp = base_time + timedelta(minutes=i)
        price = entry_price + (i / 60) * (current_price - entry_price) + random.uniform(-0.01, 0.01)
        size = random.uniform(20, 100)
        # 最近10分钟主要是卖出（负向资金流）
        side = "sell" if i > 50 else "buy"

        flow_exit.add_trade(timestamp, price, size, side, trader_id=f"trader_{i % 10}")

    print("   已添加60分钟的历史交易数据")

    # 集成场景：移动止损 + 资金流信号
    print("\n3. 集成决策场景:")

    # 场景1: 移动止损触发 + 负向资金流
    print("\n   场景1: 移动止损触发 + 负向资金流")

    # 模拟移动止损服务返回的信号
    trailing_stop_signal = {
        "type": "trailing_stop",
        "trigger_price": current_price * 0.95,
        "drawdown": 0.05
    }

    # 使用资金流系统做出决策
    result = flow_exit.check_exit_conditions(
        position_id=position_id,
        current_price=current_price,
        price_signal=trailing_stop_signal
    )

    print(f"   - 决策行动: {result.action.value}")
    print(f"   - 退出比例: {result.exit_ratio:.0%}")
    print(f"   - 决策理由:")
    for reason in result.reasoning[:2]:
        print(f"     * {reason}")

    # 场景2: 未达到止盈，但检测到极端负向资金流
    print("\n   场景2: 未达到止盈 + 极端负向资金流")

    # 模拟未达到止盈的情况
    no_signal = None

    # 模拟价格回调
    lower_price = current_price * 0.95

    result2 = flow_exit.check_exit_conditions(
        position_id=position_id,
        current_price=lower_price,
        price_signal=no_signal
    )

    print(f"   - 当前价格: ${lower_price:.2f} (回调5%)")
    print(f"   - 决策行动: {result2.action.value}")
    print(f"   - 决策置信度: {result2.confidence:.1%}")

    # 获取综合分析
    print("\n4. 综合分析报告:")
    dashboard = flow_exit.get_realtime_dashboard()

    if "flow_metrics" in dashboard:
        print("   - 资金流指标 (1分钟窗口):")
        metrics_1m = dashboard["flow_metrics"].get(60, {})
        print(f"     * 净流入: {metrics_1m.get('net_flow', 0):.2f}")
        print(f"     * 价格变化: {metrics_1m.get('price_change_pct', 0):.2f}%")

    if "performance" in dashboard:
        perf = dashboard["performance"]
        print(f"   - 系统性能:")
        print(f"     * 准确率: {perf.get('accuracy', 0):.1%}")
        print(f"     * F1分数: {perf.get('f1_score', 0):.2f}")

    print("\n集成演示完成!")


def run_all_examples():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("资金流辅助止盈止损系统 - 完整示例")
    print("=" * 60)

    # 示例1: 基本使用
    example_1_basic_usage()

    # 示例2: 自定义配置
    example_2_custom_configuration()

    # 示例3: 批量处理
    example_3_batch_processing()

    # 示例4: 集成
    example_4_integration_with_risk_management()

    print("\n" + "=" * 60)
    print("所有示例运行完成!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_examples()
