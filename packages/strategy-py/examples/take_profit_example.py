"""
止盈服务系统使用示例

演示如何使用固定止盈、部分止盈、追踪止盈服务
"""

import asyncio
from typing import Optional

# 导入止盈服务
from src.risk_management.fixed_take_profit import (
    FixedTakeProfitExecutor,
    TakeProfitConfig,
    TakeProfitType,
    create_fixed_percentage_take_profit,
)
from src.risk_management.partial_exit import (
    PartialExitService,
    TierConfig,
    PartialExitConfig,
    create_custom_partial_exit_service,
)
from src.risk_management.trailing_stop import (
    TrailingStopService,
    TrailingTier,
    TrailingStopConfig,
    create_default_trailing_stop_service,
)
from src.risk_management.take_profit_manager import (
    TakeProfitManager,
    TakeProfitPriority,
    create_take_profit_manager,
)


class MockOrderManager:
    """模拟的订单管理器，用于示例"""

    async def create_order(self, order_params):
        """模拟创建订单"""
        class MockResult:
            def __init__(self):
                self.success = True
                self.order_id = "mock_order_123"
                self.avg_fill_price = 0.55
                self.error_message = None

        # 模拟延迟
        await asyncio.sleep(0.1)
        return MockResult()


async def example_fixed_take_profit():
    """
    固定止盈服务示例

    演示如何使用固定百分比止盈
    """
    print("\n=== 固定止盈服务示例 ===\n")

    # 创建模拟订单管理器
    order_manager = MockOrderManager()

    # 创建固定止盈执行器（15% 止盈）
    tp_executor = create_fixed_percentage_take_profit(
        order_manager=order_manager,
        percentage=0.15,  # 15% 止盈
        slippage_tolerance=0.02,
        max_retries=3
    )

    # 添加持仓
    position = tp_executor.add_position(
        position_id="pos_yes_001",
        token_id="token_yes_123",
        market_id="market_456",
        token_type="yes",
        entry_price=0.50,
        size=100.0,
        side="LONG"
    )

    print(f"添加持仓: {position.position_id}")
    print(f"  入场价格: {position.entry_price:.4f}")
    print(f"  止盈价格: {position.take_profit_price:.4f}")
    print(f"  预期利润: {(position.take_profit_price - position.entry_price) / position.entry_price:.2%}")

    # 模拟价格更新
    test_prices = [0.52, 0.55, 0.57, 0.60]  # 价格逐步上涨

    for price in test_prices:
        print(f"\n当前价格: {price:.4f}")
        trigger = tp_executor.update_price(position.position_id, price)

        if trigger:
            print(f"  止盈触发! 类型: {trigger.trigger_type}")
            print(f"  当前价格: {trigger.current_price:.4f}")
            print(f"  止盈价格: {trigger.take_profit_price:.4f}")

            # 执行止盈
            execution = await tp_executor.execute_take_profit(trigger)
            print(f"  执行结果: {'成功' if execution.success else '失败'}")
            if execution.success:
                print(f"  成交价格: {execution.exit_price:.4f}")
                print(f"  实际利润: {execution.profit_pct:.2%}")
            break
        else:
            profit_pct = (price - position.entry_price) / position.entry_price
            print(f"  当前利润: {profit_pct:.2%}, 未触发止盈")

    print("\n固定止盈示例完成!")


async def example_partial_exit():
    """
    部分止盈服务示例

    演示如何使用三级分级止盈
    """
    print("\n=== 部分止盈服务示例 ===\n")

    # 创建模拟订单管理器
    order_manager = MockOrderManager()

    # 创建自定义档位配置
    tiers = [
        TierConfig(
            tier=1,
            profit_target=0.20,  # 20% 利润
            exit_ratio=0.25,     # 卖出 25%
            description="Tier 1: 20% profit, exit 25%"
        ),
        TierConfig(
            tier=2,
            profit_target=0.40,  # 40% 利润
            exit_ratio=0.35,     # 卖出 35%
            description="Tier 2: 40% profit, exit 35%"
        ),
        TierConfig(
            tier=3,
            profit_target=0.60,  # 60% 利润
            exit_ratio=0.40,     # 卖出 40%（剩余全部）
            description="Tier 3: 60% profit, exit 40%"
        ),
    ]

    # 创建部分止盈服务
    partial_service = create_custom_partial_exit_service(
        order_manager=order_manager,
        tiers=tiers,
        slippage_tolerance=0.02,
        max_retries=3
    )

    # 添加持仓
    position = partial_service.add_position(
        position_id="pos_no_002",
        token_id="token_no_456",
        market_id="market_789",
        token_type="no",  # NO 代币
        entry_price=0.50,
        size=100.0,
        side="LONG"
    )

    print(f"添加持仓: {position.position_id}")
    print(f"  代币类型: {position.token_type.value}")
    print(f"  入场价格: {position.entry_price:.4f}")
    print(f"  持仓数量: {position.size}")

    print("\n部分止盈档位配置:")
    for tier in tiers:
        print(f"  Tier {tier.tier}: 利润 {tier.profit_target:.0%}, 卖出 {tier.exit_ratio:.0%}")

    # 模拟价格变化（NO 代币价格下降表示盈利）
    # NO 代币: 入场价 0.50, 价格越低盈利越高
    test_prices = [0.48, 0.45, 0.40, 0.35, 0.30]

    print("\n开始模拟价格变化...")
    for price in test_prices:
        profit_pct = (position.entry_price - price) / position.entry_price
        print(f"\n当前价格: {price:.4f}, 当前利润: {profit_pct:.2%}")

        triggers = partial_service.update_price(position.position_id, price)

        if triggers:
            for trigger in triggers:
                print(f"  部分止盈触发! Tier {trigger.tier}")
                print(f"  目标利润: {trigger.profit_target:.2%}")
                print(f"  当前利润: {trigger.profit_pct:.2%}")
                print(f"  出场比例: {trigger.exit_ratio:.0%}")
                print(f"  出场数量: {trigger.exit_size:.2f}")

                # 执行部分止盈
                execution = await partial_service.execute_partial_exit(trigger)
                print(f"  执行结果: {'成功' if execution.success else '失败'}")
                if execution.success:
                    print(f"  成交价格: {execution.exit_price:.4f}")
                    print(f"  实际利润: {execution.profit_pct:.2%}")
                    print(f"  剩余仓位: {execution.remaining_size:.2f}")
                    if execution.is_fully_exited:
                        print("  仓位已完全出场!")
                        return
        else:
            print(f"  未触发任何止盈档位")

    print("\n部分止盈示例完成!")


async def example_trailing_stop():
    """
    追踪止盈服务示例

    演示如何使用六级追踪止盈
    """
    print("\n=== 追踪止盈服务示例 ===\n")

    # 创建模拟订单管理器
    order_manager = MockOrderManager()

    # 创建追踪止盈服务（使用默认六级配置）
    trailing_service = create_default_trailing_stop_service(
        order_manager=order_manager,
        slippage_tolerance=0.02,
        max_retries=3
    )

    print("追踪止盈档位配置:")
    for tier in trailing_service.config.tiers:
        print(f"  Tier {tier.tier}: 利润 {tier.min_profit:.0%}-{tier.max_profit:.0%}, 回撤 {tier.drawdown:.0%}")

    # 添加持仓
    position = trailing_service.add_position(
        position_id="pos_yes_003",
        token_id="token_yes_789",
        market_id="market_abc",
        token_type="yes",
        entry_price=0.50,
        size=100.0,
        side="LONG"
    )

    print(f"\n添加持仓: {position.position_id}")
    print(f"  入场价格: {position.entry_price:.4f}")

    # 模拟价格上涨过程
    # 价格从 0.50 上涨到 0.85，然后回撤触发追踪止盈
    test_prices = [
        0.52,  # 利润 4%
        0.55,  # 利润 10% - 进入 Tier 2
        0.58,  # 利润 16% - 仍在 Tier 2
        0.62,  # 利润 24% - 进入 Tier 3
        0.68,  # 利润 36% - 进入 Tier 4
        0.75,  # 利润 50% - 进入 Tier 5
        0.82,  # 利润 64% - 进入 Tier 6
        0.85,  # 利润 70% - 最高价格
        0.83,  # 回撤到 97.6%，触发 Tier 6 的 3% 回撤限制
    ]

    print("\n开始模拟价格上涨和回撤过程...")
    for i, price in enumerate(test_prices):
        profit_pct = (price - position.entry_price) / position.entry_price
        print(f"\nStep {i+1}: 价格={price:.4f}, 利润={profit_pct:.2%}")

        trigger = trailing_service.update_price(position.position_id, price)

        if trigger:
            print(f"  追踪止盈触发!")
            print(f"  触发档位: Tier {trigger.tier}")
            print(f"  最高价格: {trigger.highest_price:.4f}")
            print(f"  追踪止损价格: {trigger.trailing_stop_price:.4f}")
            print(f"  当前价格: {trigger.current_price:.4f}")
            print(f"  实际回撤: {trigger.actual_drawdown:.2%}")
            print(f"  允许回撤: {trigger.drawdown:.2%}")

            # 执行追踪止盈
            execution = await trailing_service.execute_trailing_stop(trigger)
            print(f"\n  执行结果: {'成功' if execution.success else '失败'}")
            if execution.success:
                print(f"  成交价格: {execution.exit_price:.4f}")
                print(f"  实际利润: {execution.profit_pct:.2%}")
                print(f"  利润金额: ${execution.profit_amount:.2f}")

            print("\n追踪止盈示例完成!")
            return
        else:
            # 显示当前档位信息
            if position.current_tier > 0:
                tier = trailing_service.config.tiers[position.current_tier - 1]
                print(f"  当前档位: Tier {position.current_tier}")
                print(f"  最高价格: {position.highest_price:.4f}")
                print(f"  追踪止损: {position.trailing_stop_price:.4f}")
                print(f"  允许回撤: {tier.drawdown:.0%}")

    print("\n价格序列结束，未触发追踪止盈")


async def example_take_profit_manager():
    """
    综合止盈管理器示例

    演示如何使用统一的管理器协调多种止盈服务
    """
    print("\n=== 综合止盈管理器示例 ===\n")

    # 创建模拟订单管理器
    order_manager = MockOrderManager()

    # 创建综合止盈管理器
    manager = create_take_profit_manager(
        order_manager=order_manager,
        priority=TakeProfitPriority.PARTIAL_FIRST,
        enabled=True,
        fixed_enabled=True,
        partial_enabled=True,
        trailing_enabled=True,
        deduplication_window_ms=5000
    )

    print("综合止盈管理器配置:")
    print(f"  优先级策略: {manager.config.priority.value}")
    print(f"  固定止盈: {'启用' if manager.config.fixed_enabled else '禁用'}")
    print(f"  部分止盈: {'启用' if manager.config.partial_enabled else '禁用'}")
    print(f"  追踪止盈: {'启用' if manager.config.trailing_enabled else '禁用'}")
    print(f"  去重窗口: {manager.config.deduplication_window_ms}ms")

    # 添加持仓
    position = manager.add_position(
        position_id="pos_managed_001",
        token_id="token_yes_xyz",
        market_id="market_123",
        token_type="yes",
        entry_price=0.50,
        size=100.0,
        side="LONG"
    )

    print(f"\n添加持仓到管理器: {position.position_id}")
    print(f"  入场价格: {position.entry_price:.4f}")
    print(f"  持仓数量: {position.size}")

    # 模拟价格更新
    print("\n开始价格更新和止盈检查...")

    test_prices = [0.52, 0.55, 0.60, 0.58, 0.62]

    for price in test_prices:
        profit_pct = (price - position.entry_price) / position.entry_price
        print(f"\n价格更新: {price:.4f} (利润: {profit_pct:.2%})")

        # 更新价格并检查所有止盈服务
        triggers = manager.update_price(position.position_id, price)

        if triggers:
            print(f"  触发 {len(triggers)} 个止盈信号:")
            for i, trigger in enumerate(triggers):
                print(f"    [{i+1}] 服务: {trigger.service_type.value}")
                if trigger.tier:
                    print(f"        档位: Tier {trigger.tier}")
                print(f"        退出比例: {trigger.exit_ratio:.0%}")
                print(f"        原因: {trigger.reason[:50]}...")
        else:
            print("  未触发任何止盈")

    # 获取统计信息
    print("\n管理器统计信息:")
    stats = manager.get_stats()
    print(f"  持仓数量: {stats['positions_count']}")
    print(f"  触发统计:")
    for service, count in stats['trigger_stats'].items():
        print(f"    {service}: {count}")
    print(f"  执行次数: {stats['execution_count']}")
    print(f"  成功次数: {stats['success_count']}")

    print("\n综合止盈管理器示例完成!")


async def main():
    """主函数"""
    print("=" * 60)
    print("止盈服务系统使用示例")
    print("=" * 60)

    # 运行各个示例
    await example_fixed_take_profit()
    await example_partial_exit()
    await example_trailing_stop()
    await example_take_profit_manager()

    print("\n" + "=" * 60)
    print("所有示例运行完成!")
    print("=" * 60)


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
