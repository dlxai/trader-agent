"""
Polymarket预测市场信号生成器使用示例

本示例展示了如何使用五个核心的信号生成器：
1. OddsBiasSignalGenerator - 赔率偏差信号
2. TimeDecaySignalGenerator - 时间衰减信号
3. OrderbookPressureSignalGenerator - 订单簿压力信号
4. CapitalFlowSignalGenerator - 资金流向信号
5. InformationEdgeSignalGenerator - 信息优势信号

以及复合信号生成器 CompoundSignalGenerator
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

# 导入信号生成器
from strategy.polymarket_signals import (
    # 枚举类型
    SignalType,
    SignalStrength,
    SignalDirection,

    # 数据结构
    MarketState,
    OrderBookLevel,
    OrderBookSnapshot,
    Trade,
    CapitalFlowMetrics,
    EventInfo,
    PolymarketSignal,

    # 数据源协议
    MarketDataSource,
    EventDataSource,
    AccountDataSource,

    # 辅助函数
    calculate_kelly_criterion,
    calculate_expected_value,
    time_to_event_decay,

    # 信号生成器
    OddsBiasSignalGenerator,
    TimeDecaySignalGenerator,
    OrderbookPressureSignalGenerator,
    CapitalFlowSignalGenerator,
    InformationEdgeSignalGenerator,
    CompoundSignalGenerator,
)


# =============================================================================
# 模拟数据源实现（实际使用时应连接到真实数据源）
# =============================================================================

class MockMarketDataSource:
    """模拟市场数据源"""

    async def get_market_state(self, market_id: str, token_id: str) -> MarketState:
        """获取市场状态"""
        return MarketState(
            market_id=market_id,
            token_id=token_id,
            yes_price=Decimal('0.65'),  # Yes token价格
            no_price=Decimal('0.38'),   # No token价格（含抽水）
            spread=Decimal('0.01'),
            volume_24h=Decimal('150000'),
            liquidity=Decimal('50000'),
            last_update=datetime.utcnow()
        )

    async def get_orderbook(self, market_id: str, token_id: str, depth: int = 10) -> OrderBookSnapshot:
        """获取订单簿"""
        # 模拟买卖盘
        bids = [
            OrderBookLevel(price=Decimal('0.64'), size=Decimal('5000'), count=3),
            OrderBookLevel(price=Decimal('0.63'), size=Decimal('8000'), count=5),
            OrderBookLevel(price=Decimal('0.62'), size=Decimal('12000'), count=8),
        ]
        asks = [
            OrderBookLevel(price=Decimal('0.66'), size=Decimal('4000'), count=2),
            OrderBookLevel(price=Decimal('0.67'), size=Decimal('6000'), count=4),
            OrderBookLevel(price=Decimal('0.68'), size=Decimal('10000'), count=6),
        ]

        return OrderBookSnapshot(
            market_id=market_id,
            token_id=token_id,
            bids=bids,
            asks=asks,
            timestamp=datetime.utcnow()
        )

    async def get_recent_trades(self, market_id: str, token_id: str, hours: int = 24) -> List[Trade]:
        """获取近期交易"""
        # 模拟一些交易记录
        trades = [
            Trade(
                trade_id='tx001',
                market_id=market_id,
                token_id=token_id,
                side='buy',
                size=Decimal('10000'),
                price=Decimal('0.65'),
                timestamp=datetime.utcnow() - timedelta(minutes=30),
                trader_address='0xsmartmoney1'
            ),
            Trade(
                trade_id='tx002',
                market_id=market_id,
                token_id=token_id,
                side='buy',
                size=Decimal('15000'),
                price=Decimal('0.65'),
                timestamp=datetime.utcnow() - timedelta(hours=2),
                trader_address='0xwhale1'
            ),
            Trade(
                trade_id='tx003',
                market_id=market_id,
                token_id=token_id,
                side='sell',
                size=Decimal('5000'),
                price=Decimal('0.64'),
                timestamp=datetime.utcnow() - timedelta(hours=3),
                trader_address='0xnormal1'
            ),
        ]
        return trades


class MockEventDataSource:
    """模拟事件数据源"""

    async def get_event_info(self, event_id: str) -> EventInfo:
        """获取事件信息"""
        return EventInfo(
            event_id=event_id,
            event_name='NBA Finals: Lakers vs Celtics - Winner?',
            event_type='sports',
            expected_resolution=datetime.utcnow() + timedelta(days=2),
            actual_resolution=None,
            result=None,
            source='sports_api',
            confidence=Decimal('0.85')
        )

    async def get_event_status(self, event_id: str) -> dict:
        """获取事件状态"""
        return {
            'status': 'ongoing',
            'current_score': 'LAL 45 - BOS 42',
            'quarter': 'Q2',
            'time_remaining': '6:30'
        }

    async def check_result_availability(self, event_id: str):
        """检查结果是否可用（模拟：有时比赛已结束但市场未结算）"""
        # 模拟：5% 概率检测到提前结果
        import random
        if random.random() < 0.05:
            return True, 'yes'  # 检测到结果已可获取
        return False, None


class MockAccountDataSource:
    """模拟账户数据源"""

    async def get_smart_money_accounts(
        self,
        min_win_rate: Decimal = Decimal('0.6'),
        min_trades: int = 10
    ) -> List[str]:
        """获取聪明钱地址列表"""
        # 模拟一些聪明钱地址
        return [
            '0xsmartmoney1',
            '0xsmartmoney2',
            '0xsmartmoney3',
        ]

    async def get_account_trades(
        self,
        account_address: str,
        market_id: str = None,
        hours: int = 24
    ) -> List[Trade]:
        """获取账户交易历史"""
        # 模拟返回一些交易
        return [
            Trade(
                trade_id=f'{account_address}_tx1',
                market_id=market_id or 'market1',
                token_id='token1',
                side='buy',
                size=Decimal('5000'),
                price=Decimal('0.65'),
                timestamp=datetime.utcnow() - timedelta(hours=5),
                trader_address=account_address
            )
        ]

    async def get_account_performance(
        self,
        account_address: str,
        days: int = 30
    ) -> dict:
        """获取账户历史表现"""
        # 模拟返回表现数据
        return {
            'account': account_address,
            'win_rate': 0.65,
            'total_trades': 45,
            'profitable_trades': 29,
            'avg_profit': Decimal('1200'),
            'avg_loss': Decimal('-800'),
            'profit_factor': 1.8,
            'sharpe_ratio': 1.5,
        }


# =============================================================================
# 使用示例
# =============================================================================

async def example_odds_bias_signal():
    """
    示例1: 赔率偏差信号生成器使用示例

    当市场价格与估计的真实概率存在偏差时产生信号。
    """
    print("\n" + "="*60)
    print("示例1: 赔率偏差信号 (Odds Bias Signal)")
    print("="*60)

    # 创建数据源
    market_data = MockMarketDataSource()
    event_data = MockEventDataSource()

    # 创建信号生成器
    generator = OddsBiasSignalGenerator(
        market_data_source=market_data,
        event_data_source=event_data,
        safety_margin=Decimal('0.03'),  # 安全边际3%
        min_confidence=Decimal('0.6'),
        min_edge=Decimal('0.02')
    )

    # 生成信号（使用外部提供的估计概率）
    signals = await generator.generate_signals(
        market_id='market_123',
        token_id='token_456',
        estimated_probability=0.75,  # 我们估计的真实概率
        external_confidence=0.8
    )

    # 打印结果
    if signals:
        for signal in signals:
            print(f"\n信号ID: {signal.signal_id}")
            print(f"信号类型: {signal.signal_type.value}")
            print(f"方向: {signal.direction.name}")
            print(f"强度: {signal.strength.name}")
            print(f"当前概率: {signal.current_probability:.2%}")
            print(f"估计概率: {signal.estimated_probability:.2%}")
            print(f"概率优势(Edge): {signal.edge:.2%}")
            print(f"赔率: {signal.odds:.2f}")
            print(f"置信度: {signal.confidence:.1%}")
            print(f"凯利比例: {signal.kelly_fraction:.2%}" if signal.kelly_fraction else "凯利比例: N/A")
            print(f"推理: {signal.reasoning}")
            if signal.warnings:
                print(f"⚠️ 警告: {', '.join(w for w in signal.warnings if w)}")
    else:
        print("未生成信号（可能不满足阈值条件）")


async def example_time_decay_signal():
    """
    示例2: 时间衰减信号生成器使用示例

    利用事件临近时价格向真实结果收敛的特性。
    """
    print("\n" + "="*60)
    print("示例2: 时间衰减信号 (Time Decay Signal)")
    print("="*60)

    market_data = MockMarketDataSource()
    event_data = MockEventDataSource()

    generator = TimeDecaySignalGenerator(
        market_data_source=market_data,
        event_data_source=event_data,
        min_confidence=Decimal('0.6'),
        min_edge=Decimal('0.02'),
        time_decay_threshold=0.5,
        convergence_threshold=Decimal('0.05')
    )

    # 生成信号 - 需要提供event_id
    signals = await generator.generate_signals(
        market_id='market_123',
        token_id='token_456',
        event_id='event_789',
        estimated_result_probability=Decimal('0.85')  # 估计最终结果概率
    )

    if signals:
        for signal in signals:
            print(f"\n信号ID: {signal.signal_id}")
            print(f"类型: {signal.signal_type.value}")
            print(f"方向: {signal.direction.name}")
            print(f"强度: {signal.strength.name}")
            print(f"时间范围: {signal.time_horizon_hours}小时")
            print(f"推理: {signal.reasoning[:200]}...")
    else:
        print("未生成信号（可能不满足阈值条件或事件时间不符合）")


async def example_orderbook_pressure_signal():
    """
    示例3: 订单簿压力信号生成器使用示例

    检测买卖盘不平衡和鲸鱼活动。
    """
    print("\n" + "="*60)
    print("示例3: 订单簿压力信号 (Orderbook Pressure Signal)")
    print("="*60)

    market_data = MockMarketDataSource()

    generator = OrderbookPressureSignalGenerator(
        market_data_source=market_data,
        whale_threshold_usd=Decimal('5000'),  # 降低阈值以触发信号
        min_imbalance_ratio=Decimal('0.2'),
        depth_levels=5,
        min_confidence=Decimal('0.6'),
        min_edge=Decimal('0.01')
    )

    signals = await generator.generate_signals(
        market_id='market_123',
        token_id='token_456'
    )

    if signals:
        for signal in signals:
            print(f"\n信号ID: {signal.signal_id}")
            print(f"类型: {signal.signal_type.value}")
            print(f"方向: {signal.direction.name}")
            print(f"强度: {signal.strength.name}")

            # 显示订单簿分析详情
            ob_analysis = signal.source_data.get('orderbook_analysis', {})
            print(f"买卖盘不平衡度: {float(ob_analysis.get('basic_imbalance', 0)):.2f}")
            print(f"深度不平衡: {float(ob_analysis.get('depth_imbalance', 0)):.2f}")
            print(f"压力指数: {float(ob_analysis.get('pressure_index', 0)):.2f}")

            whale_analysis = signal.source_data.get('whale_analysis', {})
            print(f"鲸鱼交易数: {whale_analysis.get('whale_trades_count', 0)}")

            print(f"\n推理: {signal.reasoning[:300]}...")
    else:
        print("未生成信号")


async def example_capital_flow_signal():
    """
    示例4: 资金流向信号生成器使用示例

    追踪聪明钱和鲸鱼的资金流向。
    """
    print("\n" + "="*60)
    print("示例4: 资金流向信号 (Capital Flow Signal)")
    print("="*60)

    market_data = MockMarketDataSource()
    account_data = MockAccountDataSource()

    generator = CapitalFlowSignalGenerator(
        market_data_source=market_data,
        account_data_source=account_data,
        min_confidence=Decimal('0.6'),
        min_edge=Decimal('0.02'),
        smart_money_min_win_rate=Decimal('0.6'),
        smart_money_min_trades=10,
        flow_window_hours=24,
        whale_threshold_usd=Decimal('5000')
    )

    signals = await generator.generate_signals(
        market_id='market_123',
        token_id='token_456'
    )

    if signals:
        for signal in signals:
            print(f"\n信号ID: {signal.signal_id}")
            print(f"类型: {signal.signal_type.value}")
            print(f"方向: {signal.direction.name}")
            print(f"强度: {signal.strength.name}")

            # 显示资金流向详情
            flow_metrics = signal.source_data.get('flow_metrics', {})
            print(f"\n资金流向概况:")
            print(f"  总流入: ${flow_metrics.get('total_inflow', 0):,.0f}")
            print(f"  总流出: ${flow_metrics.get('total_outflow', 0):,.0f}")
            print(f"  净流入: ${flow_metrics.get('net_flow', 0):,+,.0f}")
            print(f"  聪明钱流入: ${flow_metrics.get('smart_money_inflow', 0):,.0f}")
            print(f"  聪明钱流出: ${flow_metrics.get('smart_money_outflow', 0):,.0f}")
            print(f"  鲸鱼交易数: {flow_metrics.get('whale_trades_count', 0)}")

            flow_analysis = signal.source_data.get('flow_analysis', {})
            print(f"\n流向分析:")
            print(f"  聪明钱流向比率: {flow_analysis.get('smart_flow_ratio', 0):.1%}")
            print(f"  鲸鱼流向比率: {flow_analysis.get('whale_ratio', 0):.1%}")
            print(f"  综合流向指标: {flow_analysis.get('combined_flow', 0):.2f}")

            print(f"\n推理: {signal.reasoning[:400]}...")
    else:
        print("未生成信号")


async def example_information_edge_signal():
    """
    示例5: 信息优势信号生成器使用示例

    检测提前结果和内幕活动。
    """
    print("\n" + "="*60)
    print("示例5: 信息优势信号 (Information Edge Signal)")
    print("="*60)

    market_data = MockMarketDataSource()
    event_data = MockEventDataSource()
    account_data = MockAccountDataSource()

    generator = InformationEdgeSignalGenerator(
        market_data_source=market_data,
        event_data_source=event_data,
        account_data_source=account_data,
        min_confidence=Decimal('0.7'),  # 信息优势需要更高置信度
        min_edge=Decimal('0.03'),
        early_result_threshold=Decimal('0.95'),
        news_impact_window_minutes=30
    )

    signals = await generator.generate_signals(
        market_id='market_123',
        token_id='token_456',
        event_id='event_789'
    )

    if signals:
        for signal in signals:
            print(f"\n信号ID: {signal.signal_id}")
            print(f"类型: {signal.signal_type.value}")
            print(f"子类型: {signal.source_data.get('signal_subtype', 'unknown')}")
            print(f"方向: {signal.direction.name}")
            print(f"强度: {signal.strength.name}")

            # 显示信息优势详情
            insider = signal.source_data.get('insider_analysis', {})
            print(f"\n聪明钱数量: {insider.get('smart_money_count', 0)}")
            print(f"可疑活动数: {insider.get('suspicious_activities', 0)}")

            early_result = signal.source_data.get('early_result')
            if early_result:
                print(f"\n提前结果:")
                print(f"  可用: {early_result.get('available', False)}")
                print(f"  值: {early_result.get('value', 'N/A')}")
                print(f"  置信度: {early_result.get('confidence', 0):.1%}")

            print(f"\n推理: {signal.reasoning}")

            if signal.warnings:
                print(f"\n⚠️ 警告:")
                for warning in signal.warnings:
                    if warning:
                        print(f"  - {warning}")
    else:
        print("未生成信号（信息优势信号通常需要特定条件才能触发）")


async def example_compound_signal():
    """
    示例6: 复合信号生成器使用示例

    整合多个信号生成器的结果，生成综合信号。
    """
    print("\n" + "="*60)
    print("示例6: 复合信号 (Compound Signal)")
    print("="*60)

    # 创建数据源
    market_data = MockMarketDataSource()
    event_data = MockEventDataSource()
    account_data = MockAccountDataSource()

    # 创建多个基础信号生成器
    generators = [
        OddsBiasSignalGenerator(
            market_data_source=market_data,
            event_data_source=event_data,
            min_confidence=Decimal('0.5'),  # 降低阈值以便示例能生成信号
            min_edge=Decimal('0.01')
        ),
        OrderbookPressureSignalGenerator(
            market_data_source=market_data,
            min_confidence=Decimal('0.5'),
            min_edge=Decimal('0.01')
        ),
        CapitalFlowSignalGenerator(
            market_data_source=market_data,
            account_data_source=account_data,
            min_confidence=Decimal('0.5'),
            min_edge=Decimal('0.01')
        ),
    ]

    # 创建复合信号生成器
    compound_generator = CompoundSignalGenerator(
        generators=generators,
        min_agreement_ratio=0.5,  # 50%的生成器需要同意
        min_composite_confidence=Decimal('0.6')
    )

    # 生成复合信号
    signals = await compound_generator.generate_composite_signal(
        market_id='market_123',
        token_id='token_456',
        event_id='event_789',
        estimated_probability=0.75  # 传递给odds bias生成器
    )

    if signals:
        for signal in signals:
            print(f"\n复合信号ID: {signal.signal_id}")
            print(f"类型: {signal.signal_type.value}")
            print(f"方向: {signal.direction.name}")
            print(f"强度: {signal.strength.name}")
            print(f"概率优势: {signal.edge:.2%}")
            print(f"复合置信度: {signal.confidence:.1%}")

            # 显示组成信号
            components = signal.source_data.get('component_signals', [])
            print(f"\n组成信号 ({len(components)}个):")
            for comp in components:
                print(f"  - {comp['signal_type']}: Edge={comp['edge']:.2%}, Confidence={comp['confidence']:.1%}")

            stats = signal.source_data.get('consensus_stats', {})
            print(f"\n一致性统计:")
            print(f"  总信号数: {stats.get('total_signals', 0)}")
            print(f"  共识信号数: {stats.get('consensus_count', 0)}")
            print(f"  一致率: {stats.get('agreement_ratio', 0):.1%}")
            print(f"  平均Edge: {stats.get('avg_edge', 0):.2%}")

            print(f"\n推理: {signal.reasoning[:500]}...")
    else:
        print("未生成复合信号（可能需要调整阈值或确保基础生成器能产生信号）")


async def example_helper_functions():
    """
    示例7: 辅助函数使用示例

    展示如何使用各种辅助计算函数。
    """
    print("\n" + "="*60)
    print("示例7: 辅助函数 (Helper Functions)")
    print("="*60)

    # 1. 凯利公式计算
    print("\n1. 凯利公式 (Kelly Criterion)")
    print("-" * 40)

    edge = Decimal('0.10')  # 10% 概率优势
    odds = Decimal('1.8')   # 十进制赔率 1.8

    kelly = calculate_kelly_criterion(edge, odds)
    print(f"概率优势 (Edge): {edge:.1%}")
    print(f"赔率 (Odds): {odds:.2f}")
    print(f"凯利比例 (Kelly Fraction): {kelly:.2%}")
    print(f"建议仓位: 全仓的 {kelly:.0%}" if kelly > 0 else "建议: 不下注")

    # 2. 期望值计算
    print("\n2. 期望值 (Expected Value)")
    print("-" * 40)

    probabilities = [Decimal('0.55'), Decimal('0.65'), Decimal('0.75')]
    odds_list = [Decimal('1.8'), Decimal('1.9'), Decimal('2.0')]

    print("概率 | 赔率 | 期望值(EV) | 评价")
    print("-" * 50)
    for p, o in zip(probabilities, odds_list):
        ev = calculate_expected_value(p, o)
        rating = "正期望值✓" if ev > 0 else "负期望值✗"
        print(f"{p:.0%} | {o:.2f} | {ev:+.2f} | {rating}")

    # 3. 时间衰减因子
    print("\n3. 时间衰减因子 (Time Decay)")
    print("-" * 40)

    hours_list = [168, 72, 24, 12, 6, 1, 0.5]

    print("距离事件 | 衰减因子 | 时间价值 | 解读")
    print("-" * 60)
    for hours in hours_list:
        decay = time_to_event_decay(hours)
        time_value = 1 - decay
        if hours > 48:
            interpretation = "时间充裕"
        elif hours > 6:
            interpretation = "时间紧迫"
        else:
            interpretation = "即将结算"
        print(f"{hours:6.1f}h | {decay:8.2%} | {time_value:8.2%} | {interpretation}")

    print("\n" + "="*60)


async def main():
    """
    主函数：运行所有示例
    """
    print("\n" + "="*60)
    print("Polymarket预测市场信号生成器使用示例")
    print("="*60)
    print("\n本示例展示了5个核心信号生成器的使用方法：")
    print("1. OddsBiasSignalGenerator - 赔率偏差信号")
    print("2. TimeDecaySignalGenerator - 时间衰减信号")
    print("3. OrderbookPressureSignalGenerator - 订单簿压力信号")
    print("4. CapitalFlowSignalGenerator - 资金流向信号")
    print("5. InformationEdgeSignalGenerator - 信息优势信号")
    print("6. CompoundSignalGenerator - 复合信号")
    print("7. Helper Functions - 辅助函数")

    try:
        # 运行各个示例
        await example_odds_bias_signal()
        await example_time_decay_signal()
        await example_orderbook_pressure_signal()
        await example_capital_flow_signal()
        await example_information_edge_signal()
        await example_compound_signal()
        await example_helper_functions()

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("示例运行完成!")
    print("="*60 + "\n")


if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(main())
