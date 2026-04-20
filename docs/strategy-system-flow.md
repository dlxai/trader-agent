# 策略系统完整流程文档

## 概述

本文档详细描述交易系统的完整流程：
1. 信号生成与筛选
2. 买入执行流程
3. 止盈止损机制
4. 持仓监控与平仓

---

## 一、信号生成与筛选流程

### 1.1 信号来源

```
┌─────────────────────────────────────────────────────────────────┐
│                      信号生成层 (Signal Generation)              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ Technical   │  │ Fundamental │  │   Market    │          │
│  │  Analysis   │  │  Analysis   │  │    Data     │          │
│  │             │  │             │  │             │          │
│  │ - Support/  │  │ - Implied   │  │ - Volume    │          │
│  │   Resistance│  │   Prob      │  │ - Liquidity │          │
│  │ - Moving    │  │ - Edge      │  │ - Spread    │          │
│  │   Averages  │  │ - Odds      │  │ - Depth     │          │
│  │ - Patterns  │  │   Analysis  │  │             │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │                  │                  │               │
│         └──────────────────┼──────────────────┘               │
│                            ↓                                  │
│                   ┌─────────────────┐                         │
│                   │  Signal Fusion  │                         │
│                   │    Engine       │                         │
│                   │                 │                         │
│                   │ Combine multi-  │                         │
│                   │ factor signals  │                         │
│                   │ into unified    │                         │
│                   │ recommendation  │                         │
│                   └────────┬────────┘                         │
│                            │                                  │
│                            ↓                                  │
│                   Raw Signal Candidates                       │
│                   (Pre-filter signals)                        │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 1.2 第一层筛选：基础过滤器

```python
# 1. 价格区间筛选 (Dead Zone Filter)
def check_dead_zone(price: float) -> bool:
    """
    死亡区间: $0.40 - $0.60
    这个区间价格方向不明确，避免交易
    """
    DEAD_ZONE_LOW = 0.40
    DEAD_ZONE_HIGH = 0.60

    if DEAD_ZONE_LOW <= price <= DEAD_ZONE_HIGH:
        return False  # REJECT
    return True  # PASS


# 2. 流动性筛选 (Liquidity Filter)
def check_liquidity(volume_24h: Decimal, min_liquidity: Decimal = 10000) -> bool:
    """
    最小日交易量要求: $10,000
    确保有足够流动性进出
    """
    return volume_24h >= min_liquidity


# 3. 价差筛选 (Spread Filter)
def check_spread(bid: Decimal, ask: Decimal, max_spread_pct: Decimal = 0.02) -> bool:
    """
    最大价差要求: 2%
    避免滑点过大
    """
    mid = (bid + ask) / 2
    spread_pct = (ask - bid) / mid
    return spread_pct <= max_spread_pct


# 4. 时间筛选 (Time Filter)
def check_time_to_expiry(expiry: datetime,
                        min_time: timedelta = timedelta(minutes=30),
                        max_time: timedelta = timedelta(hours=6)) -> bool:
    """
    距离结算时间要求:
    - 最少: 30分钟 (避免时间不够)
    - 最多: 6小时 (资金效率考虑)
    """
    time_remaining = expiry - datetime.utcnow()
    return min_time <= time_remaining <= max_time
```

### 1.3 第二层筛选：策略专用过滤器

```python
# 5. 赔率优势筛选 (Edge Filter)
def check_odds_bias(implied_prob: float,
                   estimated_prob: float,
                   min_edge: float = 0.05) -> bool:
    """
    赔率优势要求: 至少 5% edge

    例子:
    - 市场价格: 0.55 (隐含概率 55%)
    - 估计真实概率: 65%
    - edge = 65% - 55% = 10% > 5% → PASS
    """
    edge = estimated_prob - implied_prob
    return edge >= min_edge


# 6. 资金流筛选 (Capital Flow Filter)
def check_capital_flow(smart_money_flow: float,
                       retail_flow: float,
                       threshold: float = 0.5) -> bool:
    """
    聪明钱流向要求:
    - smart_money_flow > 0.5 (净买入)
    - flow_strength >= 0.6 (流向强度)

    跟随聪明钱，逆向散户
    """
    return smart_money_flow > threshold


# 7. 技术分析筛选 (Technical Filter)
def check_technical_setup(price: float,
                         support: float,
                         resistance: float,
                         trend: str) -> bool:
    """
    技术要求:
    - 价格接近支撑位 (bounce setup)
    - 或价格突破阻力位 (breakout setup)
    - 趋势方向与信号一致
    """
    near_support = abs(price - support) / support < 0.02
    breakout = price > resistance * 1.01
    trend_aligned = (trend == "up" and "buy") or (trend == "down" and "sell")

    return (near_support or breakout) and trend_aligned
```

### 1.4 第三层筛选：LLM 深度分析

```python
# 通过所有基础筛选后，进入 LLM 分析
async def llm_signal_analysis(signal: Signal,
                            market_context: MarketContext,
                            llm_client: LLMClient) -> AnalysisResult:
    """
    LLM 深度分析流程:

    1. 构建完整 prompt (包含所有市场数据、信号信息、风险参数)
    2. 调用 LLM (Claude/GPT) 进行推理
    3. 解析返回结果 (approved/rejected/modify)
    4. 如果 approved，可能包含优化建议 (调整入场价、止损位等)
    5. 返回最终的 AnalysisResult
    """

    prompt = f"""
    ## Trading Signal Analysis Request

    ### Market Context
    - Market: {signal.market_id}
    - Current Price: {market_context.current_price}
    - 24h Volume: {market_context.volume_24h}
    - Spread: {market_context.spread_percent}%

    ### Signal Details
    - Side: {signal.side}
    - Suggested Entry: {signal.suggested_entry}
    - Confidence: {signal.confidence}
    - Stop Loss: {signal.stop_loss}
    - Take Profit: {signal.take_profit}

    ### Risk Parameters
    - Position Size: {signal.suggested_size}
    - Max Risk: ${signal.max_risk_amount}
    - R/R Ratio: {signal.risk_reward_ratio}

    ### Analysis Required

    Please analyze this signal and provide:

    1. **Verdict**: APPROVE / REJECT / MODIFY
    2. **Confidence**: 0-1 score
    3. **Reasoning**: Detailed explanation
    4. **Risk Assessment**: Low/Medium/High with justification
    5. **Suggestions**: If MODIFY, provide adjusted parameters

    Consider:
    - Is the entry price reasonable given current market conditions?
    - Are stop loss and take profit levels technically sound?
    - Is the position size appropriate for the risk?
    - What could go wrong with this trade?
    """

    # Call LLM
    response = await llm_client.analyze(prompt)

    # Parse response
    return AnalysisResult(
        signal_id=signal.signal_id,
        approved=response["verdict"] == "APPROVE",
        action="execute" if response["verdict"] == "APPROVE" else
               "modify" if response["verdict"] == "MODIFY" else "reject",
        approval_reason=response["reasoning"] if response["verdict"] == "APPROVE" else "",
        rejection_reason=response["reasoning"] if response["verdict"] == "REJECT" else "",
        modified_entry=response["suggestions"].get("entry") if response["verdict"] == "MODIFY" else None,
        modified_stop_loss=response["suggestions"].get("stop_loss") if response["verdict"] == "MODIFY" else None,
        modified_take_profit=response["suggestions"].get("take_profit") if response["verdict"] == "MODIFY" else None,
    )
```

## 二、买入执行流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        买入执行流程 (Buy Execution)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. 信号通过所有筛选 → Analyzer 发布 APPROVED 事件                            │
│                       ↓                                                     │
│  Event: SIGNAL_APPROVED → OrderExecutor.subscribe()                          │
│                       ↓                                                     │
│  2. Executor 接收事件 → 创建订单                                              │
│                       ↓                                                     │
│  Order = {                                                                   │
│    symbol: market_id,                                                        │
│    side: "yes"/"no",                                                       │
│    order_type: "market"/"limit",                                            │
│    size: position_size,                                                      │
│    price: limit_price (if limit order),                                      │
│    stop_loss: stop_loss_price,  ← 关键：止损位                                │
│    take_profit: take_profit_price, ← 关键：止盈位                             │
│  }                                                                           │
│                       ↓                                                     │
│  3. 提交到交易所 (Paper/Live)                                                │
│                       ↓                                                     │
│  ExchangeAdapter.submit_order(order) → 返回 fill_result                        │
│                       ↓                                                     │
│  4. 创建 Position 记录                                                        │
│                       ↓                                                     │
│  Position = {                                                                │
│    market_id, symbol, side,                                                   │
│    entry_price: fill_price,                                                   │
│    size: fill_size,                                                           │
│    stop_loss_price: order.stop_loss,  ← 记录止损位                            │
│    take_profit_price: order.take_profit, ← 记录止盈位                         │
│    status: "open",                                                            │
│    opened_at: now(),                                                          │
│  }                                                                           │
│                       ↓                                                     │
│  5. 启动 Position 监控                                                        │
│                       ↓                                                     │
│  PositionTracker.start_monitoring(position_id)                                 │
│                       ↓                                                     │
│  持续监控: current_price vs stop_loss / take_profit                           │
│                       ↓                                                     │
│  触发条件 → 提交平仓订单 → Position 关闭                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 三、止盈止损监控机制

```python
# PositionTracker 监控逻辑

class PositionTracker:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.monitored_positions: Dict[str, asyncio.Task] = {}

    async def start_monitoring(self, position_id: str):
        """开始监控持仓"""
        task = asyncio.create_task(
            self._monitor_loop(position_id),
            name=f"monitor_{position_id}"
        )
        self.monitored_positions[position_id] = task

    async def _monitor_loop(self, position_id: str):
        """持仓监控循环"""
        while True:
            try:
                # 获取最新持仓信息
                position = await self._get_position(position_id)

                if position.status != "open":
                    # 持仓已关闭，停止监控
                    break

                # 获取当前市场价格
                current_price = await self._get_current_price(
                    position.market_id
                )

                # 更新 unrealized_pnl
                position.unrealized_pnl = self._calculate_pnl(
                    position, current_price
                )
                position.current_price = current_price

                # 检查退出条件
                exit_signal = self._check_exit_conditions(
                    position, current_price
                )

                if exit_signal:
                    # 触发平仓
                    await self._trigger_exit(position_id, exit_signal)
                    break

                # 每 5 秒检查一次
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Monitor error for {position_id}: {e}")
                await asyncio.sleep(5)

    def _check_exit_conditions(
        self,
        position: Position,
        current_price: Decimal
    ) -> Optional[ExitSignal]:
        """检查退出条件"""

        # 1. 止损检查
        if position.side == "yes":
            # 多仓: 价格 <= 止损价
            if current_price <= position.stop_loss_price:
                return ExitSignal(
                    reason="stop_loss",
                    trigger_price=current_price,
                    exit_type="market"
                )
        else:  # side == "no"
            # 空仓: 价格 >= 止损价 (注意：Polymarket 反向)
            if current_price >= position.stop_loss_price:
                return ExitSignal(
                    reason="stop_loss",
                    trigger_price=current_price,
                    exit_type="market"
                )

        # 2. 止盈检查
        if position.side == "yes":
            if current_price >= position.take_profit_price:
                return ExitSignal(
                    reason="take_profit",
                    trigger_price=current_price,
                    exit_type="market"
                )
        else:
            if current_price <= position.take_profit_price:
                return ExitSignal(
                    reason="take_profit",
                    trigger_price=current_price,
                    exit_type="market"
                )

        # 3. 移动止损检查 (Trailing Stop)
        # 如果已经盈利，跟随价格上涨调整止损
        if position.side == "yes":
            # 计算当前盈利
            profit_pct = (current_price - position.entry_price) / position.entry_price

            if profit_pct > Decimal("0.05"):  # 盈利超过 5%
                # 启动移动止损: 从最高点回撤 3%
                # trailing_stop = highest_price_since_entry * 0.97
                highest_price = self._get_highest_price_since_entry(position.id)
                trailing_stop = highest_price * Decimal("0.97")

                if current_price <= trailing_stop:
                    return ExitSignal(
                        reason="trailing_stop",
                        trigger_price=current_price,
                        exit_type="market"
                    )

        # 4. 最大持仓时间检查
        time_held = datetime.utcnow() - position.opened_at
        max_hold_time = timedelta(hours=4)  # 最大持仓 4 小时

        if time_held >= max_hold_time:
            return ExitSignal(
                reason="max_hold_time",
                trigger_price=current_price,
                exit_type="market"
            )

        # 没有触发任何退出条件
        return None


@dataclass
class ExitSignal:
    """退出信号"""
    reason: str  # "stop_loss", "take_profit", "trailing_stop", "max_hold_time"
    trigger_price: Decimal
    exit_type: str  # "market", "limit"
```

## 四、完整示例流程

```python
# 示例：完整的买入到止盈流程

async def example_trade_flow():

    # ========== 阶段 1: 信号生成 ==========

    # 市场数据
    market_context = MarketContext(
        market_id="0x123...",
        symbol="TRUMP-2024",
        current_price=Decimal("0.35"),
        bid=Decimal("0.345"),
        ask=Decimal("0.355"),
        spread_percent=Decimal("0.029"),  # 2.9%
        volume_24h=Decimal("50000"),  # $50k
        bid_depth=Decimal("15000"),
        ask_depth=Decimal("12000"),
    )

    # 信号生成 (来自 strategy-py 或其他策略)
    raw_signal = Signal(
        signal_id="sig_001",
        signal_type=SignalType.BUY,
        market_id="0x123...",
        symbol="TRUMP-2024",
        side="yes",
        confidence=Decimal("0.75"),
        urgency="normal",
        suggested_entry=Decimal("0.35"),
        suggested_exit=Decimal("0.45"),
        stop_loss=Decimal("0.32"),  # -8.6%
        take_profit=Decimal("0.45"),  # +28.6%
        risk_reward_ratio=Decimal("3.3"),
        suggested_size=Decimal("100"),  # 100 shares
        max_risk_amount=Decimal("30"),  # $30 max loss
        position_percentage=Decimal("0.10"),  # 10% of portfolio
        signal_reason="Strong odds edge detected",
        technical_factors=["Support bounce", "Volume spike"],
        fundamental_factors=["Recent poll shift"],
        sentiment_factors=["Social media buzz increasing"],
        market_context=market_context,
        timestamp=datetime.utcnow(),
    )

    # ========== 阶段 2: 信号筛选 ==========

    filters = SignalFilters()

    # 第一层: 基础筛选
    checks = [
        ("dead_zone", filters.check_dead_zone(raw_signal.suggested_entry)),
        ("liquidity", filters.check_liquidity(market_context.volume_24h)),
        ("spread", filters.check_spread(market_context.bid, market_context.ask)),
        ("time", filters.check_time_to_expiry(expiry)),
    ]

    for check_name, passed in checks:
        if not passed:
            print(f"❌ Signal REJECTED at {check_name}")
            return None

    # 第二层: 策略筛选
    strategy_checks = [
        ("odds_bias", filters.check_odds_bias(implied=0.55, estimated=0.65)),
        ("capital_flow", filters.check_capital_flow(smart_flow=0.7)),
    ]

    # 第三层: LLM 深度分析
    llm_result = await llm_client.analyze(raw_signal)

    if not llm_result.approved:
        print(f"❌ Signal REJECTED by LLM: {llm_result.reasoning}")
        return None

    # 信号通过所有筛选！
    print(f"✅ Signal APPROVED with confidence: {llm_result.confidence}")

    # ========== 阶段 3: 订单执行 ==========

    # 创建订单
    order = Order(
        market_id=raw_signal.market_id,
        side=raw_signal.side,
        order_type="market",  # 或 "limit"
        size=llm_result.modified_size or raw_signal.suggested_size,
        price=llm_result.modified_entry or raw_signal.suggested_entry,
        stop_loss_price=llm_result.modified_stop_loss or raw_signal.stop_loss,
        take_profit_price=llm_result.modified_take_profit or raw_signal.take_profit,
    )

    # 提交订单
    execution_result = await executor.submit_order(order)

    if execution_result.success:
        print(f"✅ Order filled: {execution_result.filled_size} @ {execution_result.avg_fill_price}")

        # ========== 阶段 4: 持仓监控 ==========

        # 创建 Position
        position = Position(
            market_id=order.market_id,
            side=order.side,
            entry_price=execution_result.avg_fill_price,
            size=execution_result.filled_size,
            stop_loss_price=order.stop_loss_price,
            take_profit_price=order.take_profit_price,
            status="open",
        )

        # 启动监控
        await position_tracker.start_monitoring(position.id)

        print(f"📊 Position created and monitoring started")
        print(f"   Stop Loss: {position.stop_loss_price}")
        print(f"   Take Profit: {position.take_profit_price}")

        # ========== 阶段 5: 等待退出触发 ==========

        # 监控循环会持续运行，直到:
        # - 价格触及 stop_loss → 市价平仓
        # - 价格触及 take_profit → 市价平仓
        # - 持仓时间超过 max_hold_time → 强制平仓
        # - 用户手动平仓

        # 假设止盈触发:
        # current_price = 0.45 (触及 take_profit)
        # → ExitSignal(reason="take_profit", trigger_price=0.45)
        # → executor.close_position(position_id, market_order)
        # → Position status = "closed"
        # → Realized P&L = (0.45 - 0.35) * 100 = $10

        print(f"🎯 Take profit triggered at {position.take_profit_price}")
        print(f"💰 Realized P&L: $10.00")

    else:
        print(f"❌ Order failed: {execution_result.error_message}")
        return None
```

## 五、关键总结

### 信号筛选三层防线

| 层级 | 名称 | 目的 | 示例 |
|------|------|------|------|
| 第一层 | 基础过滤器 | 剔除明显不良信号 | 死亡区间、低流动性、价差过大 |
| 第二层 | 策略过滤器 | 验证信号质量 | 赔率优势、资金流、技术分析 |
| 第三层 | LLM 分析 | 深度推理决策 | 综合判断、风险权衡、情景分析 |

### 止盈止损执行机制

| 类型 | 触发条件 | 执行动作 | 目的 |
|------|----------|----------|------|
| 止损 (Stop Loss) | 价格 <= 止损价 | 市价平仓 | 限制亏损 |
| 止盈 (Take Profit) | 价格 >= 止盈价 | 市价平仓 | 锁定利润 |
| 移动止损 (Trailing) | 从最高点回撤 N% | 市价平仓 | 保护利润 |
| 时间止损 (Time) | 持仓超最大时间 | 市价平仓 | 资金效率 |

这就是完整的策略系统流程！
