"""
策略Agent (StrategyAgent)

职责：
1. 制定交易决策（买什么、何时买、买多少）
2. 分析市场数据和信号
3. 生成交易意图
4. 管理策略状态和历史决策

输入：
- 市场数据（价格、成交量、订单簿）
- 外部信号（技术分析、基本面、新闻情绪）
- 资金流分析数据

输出：
- 交易意图（买入/卖出信号）
- 策略状态更新
- 决策理由
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set
from enum import Enum
from collections import deque
import uuid

from ..core.agent_base import Agent, AgentConfig, AgentState
from ..protocol.messages import (
    BaseMessage, TradingSignal, OrderIntent, MarketData,
    PositionUpdate, AnalysisResult, SignalType
)
from ..protocol.constants import (
    OrderSide, OrderType, ExecutionStrategy, MessagePriority
)

logger = logging.getLogger(__name__)


class StrategyState(Enum):
    """策略状态"""
    IDLE = "idle"                      # 空闲
    ANALYZING = "analyzing"            # 分析中
    SIGNAL_GENERATED = "signal_generated"  # 信号已生成
    AWAITING_EXECUTION = "awaiting_execution"  # 等待执行
    EXECUTED = "executed"              # 已执行


@dataclass
class MarketSnapshot:
    """市场快照"""
    token_id: str
    price: float
    bid: float
    ask: float
    volume_24h: float
    timestamp: datetime
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionRecord:
    """决策记录"""
    decision_id: str
    timestamp: datetime
    signal_type: SignalType
    token_id: str
    confidence: float
    reasoning: str
    market_data: Dict[str, Any]
    result: Optional[str] = None  # success, failure, pending
    execution_time_ms: Optional[float] = None


@dataclass
class StrategyConfig(AgentConfig):
    """策略Agent配置"""
    # 信号生成参数
    min_confidence_threshold: float = 0.6  # 最小置信度
    max_signals_per_minute: int = 10      # 每分钟最大信号数
    signal_cooldown_seconds: float = 5.0   # 信号冷却时间

    # 分析参数
    market_data_window: int = 100          # 市场数据窗口大小
    analysis_interval: float = 1.0         # 分析间隔（秒）

    # 策略参数
    default_order_type: OrderType = OrderType.LIMIT
    default_execution_strategy: ExecutionStrategy = ExecutionStrategy.ADAPTIVE
    max_position_size: float = 1000.0      # 最大持仓规模

    # 风险管理
    enable_auto_stop_loss: bool = True
    default_stop_loss_pct: float = -0.05   # 默认止损比例
    default_take_profit_pct: float = 0.1   # 默认止盈比例

    # 历史记录
    max_decision_history: int = 1000     # 最大决策历史

    agent_type: str = "strategy_agent"


class StrategyAgent(Agent):
    """
    策略Agent

    负责生成交易信号和决策
    """

    def __init__(self, config: Optional[StrategyConfig] = None):
        super().__init__(config or StrategyConfig())
        self._config: StrategyConfig = self._config

        # 策略状态
        self._strategy_state = StrategyState.IDLE
        self._last_signal_time: Optional[datetime] = None
        self._signal_count_this_minute = 0
        self._last_minute_reset = datetime.utcnow()

        # 市场数据缓存
        self._market_data_cache: Dict[str, deque] = {}  # token_id -> MarketSnapshot队列
        self._latest_market_data: Dict[str, MarketSnapshot] = {}

        # 持仓状态
        self._positions: Dict[str, Dict[str, Any]] = {}  # position_id -> position info

        # 决策历史
        self._decision_history: deque = deque(maxlen=self._config.max_decision_history)

        # 分析回调
        self._analysis_callbacks: List[Callable[[MarketSnapshot], None]] = []

        # 信号过滤器
        self._signal_filters: List[Callable[[TradingSignal], bool]] = []

        logger.info(f"StrategyAgent {self._agent_id} initialized")

    # ==================== 生命周期方法 ====================

    async def _initialize(self):
        """初始化策略Agent"""
        logger.info("Initializing StrategyAgent...")

        # 初始化市场数据缓存
        for token_id in self._get_monitored_tokens():
            self._market_data_cache[token_id] = deque(
                maxlen=self._config.market_data_window
            )

        # 加载历史决策（如果有持久化）
        await self._load_decision_history()

        # 注册消息处理器
        self.register_message_handler("market_data", self._on_market_data)
        self.register_message_handler("position_update", self._on_position_update)
        self.register_message_handler("order_result", self._on_order_result)
        self.register_message_handler("analysis_result", self._on_analysis_result)

        logger.info("StrategyAgent initialized successfully")

    async def _process_message(self, message: BaseMessage):
        """处理消息"""
        # 查找对应的处理器
        handler = self._message_handlers.get(message.msg_type)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.exception(f"Error handling message {message.msg_type}: {e}")
        else:
            logger.warning(f"No handler for message type: {message.msg_type}")

    async def _run(self):
        """主运行逻辑 - 定期分析"""
        while self._running:
            try:
                if self._strategy_state != StrategyState.PAUSED:
                    await self._perform_analysis()

                # 重置每分钟信号计数
                now = datetime.utcnow()
                if (now - self._last_minute_reset).total_seconds() >= 60:
                    self._signal_count_this_minute = 0
                    self._last_minute_reset = now

                await asyncio.sleep(self._config.analysis_interval)

            except Exception as e:
                logger.exception(f"Error in analysis loop: {e}")
                await asyncio.sleep(5)

    async def _cleanup(self):
        """清理资源"""
        logger.info("Cleaning up StrategyAgent...")

        # 保存决策历史
        await self._save_decision_history()

        # 清理缓存
        self._market_data_cache.clear()
        self._latest_market_data.clear()

        logger.info("StrategyAgent cleanup complete")

    # ==================== 业务逻辑 ====================

    async def _on_market_data(self, message):
        """处理市场数据"""
        from ..protocol.messages import MarketData
        if isinstance(message, MarketData):
            snapshot = MarketSnapshot(
                token_id=message.token_id,
                price=message.price,
                bid=message.bid,
                ask=message.ask,
                volume_24h=message.volume_24h,
                timestamp=message.timestamp or datetime.utcnow()
            )

            # 更新缓存
            if message.token_id not in self._market_data_cache:
                self._market_data_cache[message.token_id] = deque(
                    maxlen=self._config.market_data_window
                )

            self._market_data_cache[message.token_id].append(snapshot)
            self._latest_market_data[message.token_id] = snapshot

            # 触发分析回调
            for callback in self._analysis_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(snapshot)
                    else:
                        callback(snapshot)
                except Exception as e:
                    logger.error(f"Error in analysis callback: {e}")

    async def _on_position_update(self, message):
        """处理持仓更新"""
        from ..protocol.messages import PositionUpdate
        if isinstance(message, PositionUpdate):
            self._positions[message.position_id] = {
                "token_id": message.token_id,
                "size": message.size,
                "entry_price": message.entry_price,
                "current_price": message.current_price,
                "unrealized_pnl": message.unrealized_pnl,
                "updated_at": datetime.utcnow()
            }

    async def _on_order_result(self, message):
        """处理订单结果"""
        from ..protocol.messages import OrderResult
        if isinstance(message, OrderResult):
            # 更新决策记录
            for decision in self._decision_history:
                if decision.decision_id == message.correlation_id:
                    decision.result = "success" if message.success else "failure"
                    break

    async def _on_analysis_result(self, message):
        """处理分析结果"""
        from ..protocol.messages import AnalysisResult
        if isinstance(message, AnalysisResult):
            # 可以在这里处理分析结果，调整策略参数
            pass

    async def _perform_analysis(self):
        """执行分析 - 子类应该重写此方法"""
        # 基础实现：检查是否需要生成信号
        for token_id, snapshot in self._latest_market_data.items():
            signal = await self._generate_signal(token_id, snapshot)
            if signal:
                await self._process_signal(signal)

    async def _generate_signal(self, token_id: str, snapshot: MarketSnapshot) -> Optional[TradingSignal]:
        """
        生成交易信号 - 子类应该重写此方法

        Args:
            token_id: 代币ID
            snapshot: 市场快照

        Returns:
            TradingSignal 或 None
        """
        # 基础实现：不生成信号
        # 子类应该实现具体的策略逻辑
        return None

    async def _process_signal(self, signal: TradingSignal):
        """处理交易信号"""
        # 检查信号过滤
        for filter_fn in self._signal_filters:
            if not filter_fn(signal):
                logger.debug(f"Signal filtered out: {signal.signal_type}")
                return

        # 检查频率限制
        if not self._check_signal_frequency():
            logger.warning("Signal frequency limit reached, skipping signal")
            return

        # 记录决策
        decision = DecisionRecord(
            decision_id=signal.msg_id,
            timestamp=datetime.utcnow(),
            signal_type=signal.signal_type,
            token_id=signal.token_id,
            confidence=signal.confidence,
            reasoning=signal.reasoning,
            market_data={
                "price": self._latest_market_data.get(signal.token_id, {}).price if self._latest_market_data.get(signal.token_id) else None
            }
        )
        self._decision_history.append(decision)

        # 创建订单意图
        order_intent = self._create_order_intent(signal)

        # 发送信号和意图
        await self.send_message(signal)
        if order_intent:
            await self.send_message(order_intent)

        self._last_signal_time = datetime.utcnow()
        self._signal_count_this_minute += 1

        logger.info(f"Signal processed: {signal.signal_type} for {signal.token_id} "
                   f"with confidence {signal.confidence:.2f}")

    def _create_order_intent(self, signal: TradingSignal) -> Optional[OrderIntent]:
        """根据信号创建订单意图"""
        if signal.signal_type == SignalType.HOLD:
            return None

        side = OrderSide.BUY if signal.signal_type in [SignalType.BUY, SignalType.INCREASE] else OrderSide.SELL

        # 获取当前价格
        snapshot = self._latest_market_data.get(signal.token_id)
        if not snapshot:
            logger.warning(f"No market data for {signal.token_id}")
            return None

        price = signal.price_target or snapshot.price

        # 计算数量
        size = signal.size_recommendation or self._calculate_position_size(signal)

        return OrderIntent(
            msg_id=str(uuid.uuid4()),
            msg_type="order_intent",
            sender=self._agent_id,
            token_id=signal.token_id,
            side=side,
            order_type=self._config.default_order_type,
            price=price,
            size=size,
            execution_strategy=self._config.default_execution_strategy,
            parent_signal_id=signal.msg_id,
            metadata={
                "confidence": signal.confidence,
                "reasoning": signal.reasoning,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
            }
        )

    def _calculate_position_size(self, signal: TradingSignal) -> float:
        """计算持仓规模 - 子类可以重写"""
        # 基础实现：使用固定规模
        return 100.0

    def _check_signal_frequency(self) -> bool:
        """检查信号频率限制"""
        # 检查每分钟信号数
        if self._signal_count_this_minute >= self._config.max_signals_per_minute:
            return False

        # 检查冷却时间
        if self._last_signal_time:
            elapsed = (datetime.utcnow() - self._last_signal_time).total_seconds()
            if elapsed < self._config.signal_cooldown_seconds:
                return False

        return True

    def add_signal_filter(self, filter_fn: Callable[[TradingSignal], bool]):
        """添加信号过滤器"""
        self._signal_filters.append(filter_fn)

    def remove_signal_filter(self, filter_fn: Callable[[TradingSignal], bool]):
        """移除信号过滤器"""
        if filter_fn in self._signal_filters:
            self._signal_filters.remove(filter_fn)

    def add_analysis_callback(self, callback: Callable[[MarketSnapshot], None]):
        """添加分析回调"""
        self._analysis_callbacks.append(callback)

    def get_decision_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        token_id: Optional[str] = None
    ) -> List[DecisionRecord]:
        """获取决策历史"""
        decisions = list(self._decision_history)

        if start_time:
            decisions = [d for d in decisions if d.timestamp >= start_time]
        if end_time:
            decisions = [d for d in decisions if d.timestamp <= end_time]
        if token_id:
            decisions = [d for d in decisions if d.token_id == token_id]

        return decisions

    def _get_monitored_tokens(self) -> List[str]:
        """获取监控的代币列表 - 子类可以重写"""
        return []

    async def _load_decision_history(self):
        """加载决策历史 - 可以持久化到数据库"""
        pass

    async def _save_decision_history(self):
        """保存决策历史 - 可以持久化到数据库"""
        pass
