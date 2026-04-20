"""
风控Agent (RiskAgent)

职责：
1. 监控和干预风险（止损、仓位限制、熔断）
2. 实时风险评估和预警
3. 强制操作执行（平仓、暂停）
4. 风险指标计算和报告

输入：
- 实时价格和持仓状态
- 订单执行结果
- 外部事件（市场熔断等）

输出：
- 风险警报
- 强制操作指令
- 风险报告

权限：
- 可强制平仓
- 可暂停交易
- 可拒绝订单
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set
from enum import Enum
from collections import deque, defaultdict
import uuid

from ..core.agent_base import Agent, AgentConfig, AgentState
from ..protocol.messages import (
    BaseMessage, RiskAlert, RiskAction, PositionUpdate,
    OrderResult, MarketData, OrderIntent
)
from ..protocol.constants import RiskLevel, OrderSide, MessagePriority

logger = logging.getLogger(__name__)


class RiskEventType(Enum):
    """风险事件类型"""
    STOP_LOSS = "stop_loss"                    # 止损触发
    TAKE_PROFIT = "take_profit"                # 止盈触发
    POSITION_LIMIT = "position_limit"          # 仓位限制
    DAILY_LOSS_LIMIT = "daily_loss_limit"      # 日亏损限制
    DRAWDOWN_LIMIT = "drawdown_limit"          # 回撤限制
    CONCENTRATION_RISK = "concentration_risk"  # 集中度风险
    LIQUIDITY_RISK = "liquidity_risk"          # 流动性风险
    MARKET_HALT = "market_halt"                  # 市场熔断
    MARGIN_CALL = "margin_call"                # 保证金不足
    CIRCUIT_BREAKER = "circuit_breaker"        # 熔断机制


@dataclass
class RiskThreshold:
    """风险阈值"""
    level: RiskLevel
    warning_threshold: float
    critical_threshold: float
    action: str  # alert, reduce, close, halt
    cooldown_minutes: int = 5


@dataclass
class PositionRisk:
    """持仓风险"""
    position_id: str
    token_id: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_pct: float
    from_high_pct: float
    risk_score: float  # 0-100
    stop_loss_triggered: bool = False
    take_profit_triggered: bool = False


@dataclass
class PortfolioRisk:
    """组合风险"""
    total_exposure: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    daily_pnl: float
    max_drawdown_pct: float
    sharpe_ratio: float
    var_95: float  # 95% VaR
    concentration_risk: Dict[str, float]  # 各token集中度
    risk_level: RiskLevel


@dataclass
class RiskEvent:
    """风险事件"""
    event_id: str
    event_type: RiskEventType
    risk_level: RiskLevel
    position_id: Optional[str]
    token_id: Optional[str]
    message: str
    timestamp: datetime
    metrics: Dict[str, Any]
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    actions_taken: List[str] = field(default_factory=list)


@dataclass
class RiskConfig(AgentConfig):
    """风控Agent配置"""
    # 风险阈值配置
    max_position_size: float = 10000.0
    max_position_pct: float = 0.2  # 单仓位最大占比
    max_daily_loss: float = -0.05  # 日最大亏损 -5%
    max_drawdown: float = -0.1     # 最大回撤 -10%
    stop_loss_enabled: bool = True
    take_profit_enabled: bool = True

    # 自动操作
    auto_close_on_stop_loss: bool = True
    auto_close_on_take_profit: bool = False
    auto_pause_on_daily_loss: bool = True
    auto_pause_on_drawdown: bool = True

    # 监控参数
    risk_check_interval: float = 1.0  # 风险检查间隔
    price_update_timeout: float = 30.0  # 价格更新超时

    # 风险计算参数
    var_confidence_level: float = 0.95  # VaR置信水平
    risk_free_rate: float = 0.02  # 无风险利率

    agent_type: str = "risk_agent"


class RiskAgent(Agent):
    """
    风控Agent

    负责实时监控风险并执行风控操作
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        super().__init__(config or RiskConfig())
        self._config: RiskConfig = self._config

        # 持仓风险
        self._position_risks: Dict[str, PositionRisk] = {}

        # 组合风险
        self._portfolio_risk: Optional[PortfolioRisk] = None

        # 风险事件
        self._active_risk_events: Dict[str, RiskEvent] = {}
        self._risk_event_history: deque = deque(maxlen=1000)

        # 风险阈值配置
        self._risk_thresholds: Dict[RiskEventType, RiskThreshold] = self._setup_risk_thresholds()

        # 风控操作回调
        self._risk_action_callbacks: List[Callable[[RiskAction], None]] = []

        # 交易暂停状态
        self._trading_halted = False
        self._halt_reason: Optional[str] = None
        self._halted_at: Optional[datetime] = None

        # 白名单（不受风控限制的Agent）
        self._whitelist: Set[str] = set()

        logger.info(f"RiskAgent {self._agent_id} initialized")

    # ==================== 生命周期方法 ====================

    async def _initialize(self):
        """初始化风控Agent"""
        logger.info("Initializing RiskAgent...")

        # 注册消息处理器
        self.register_message_handler("position_update", self._on_position_update)
        self.register_message_handler("order_result", self._on_order_result)
        self.register_message_handler("market_data", self._on_market_data)
        self.register_message_handler("order_intent", self._on_order_intent)

        # 加载历史风险事件（如果有持久化）
        await self._load_risk_history()

        logger.info("RiskAgent initialized successfully")

    async def _process_message(self, message: BaseMessage):
        """处理消息"""
        handler = self._message_handlers.get(message.msg_type)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.exception(f"Error handling message {message.msg_type}: {e}")

    async def _run(self):
        """主运行逻辑 - 持续风险监控"""
        while self._running:
            try:
                # 执行风险评估
                await self._perform_risk_assessment()

                # 检查风险事件
                await self._check_risk_events()

                # 更新组合风险
                await self._update_portfolio_risk()

                # 检查是否需要恢复交易
                if self._trading_halted:
                    await self._check_trading_resumption()

                await asyncio.sleep(self._config.risk_check_interval)

            except Exception as e:
                logger.exception(f"Error in risk assessment loop: {e}")
                await asyncio.sleep(5)

    async def _cleanup(self):
        """清理资源"""
        logger.info("Cleaning up RiskAgent...")

        # 保存风险历史
        await self._save_risk_history()

        # 如果交易被暂停，恢复它
        if self._trading_halted:
            await self.resume_trading("agent_shutdown")

        logger.info("RiskAgent cleanup complete")

    # ==================== 业务逻辑 ====================

    async def _on_position_update(self, message):
        """处理持仓更新"""
        if isinstance(message, PositionUpdate):
            # 更新持仓风险
            await self._update_position_risk(message)

    async def _on_order_result(self, message):
        """处理订单结果"""
        if isinstance(message, OrderResult):
            # 更新实现盈亏
            pass

    async def _on_market_data(self, message):
        """处理市场数据"""
        if isinstance(message, MarketData):
            # 更新价格用于风险计算
            position_risk = self._position_risks.get(message.token_id)
            if position_risk:
                position_risk.current_price = message.price
                position_risk.unrealized_pnl = (
                    message.price - position_risk.entry_price
                ) * position_risk.size
                position_risk.pnl_pct = (
                    message.price - position_risk.entry_price
                ) / position_risk.entry_price if position_risk.entry_price else 0

    async def _on_order_intent(self, message):
        """处理订单意图 - 风控检查"""
        if not isinstance(message, OrderIntent):
            return

        # 检查交易是否被暂停
        if self._trading_halted:
            logger.warning(f"Trading halted, rejecting order intent: {message.msg_id}")
            await self._reject_order_intent(message, f"Trading halted: {self._halt_reason}")
            return

        # 执行风控检查
        risk_level, risk_message = await self._check_order_risk(message)

        if risk_level == RiskLevel.CRITICAL:
            logger.warning(f"Critical risk detected, rejecting order: {risk_message}")
            await self._reject_order_intent(message, risk_message)

            # 触发风险警报
            await self._trigger_risk_alert(
                RiskEventType.CIRCUIT_BREAKER,
                RiskLevel.CRITICAL,
                risk_message,
                {"order_intent_id": message.msg_id}
            )
            return

        elif risk_level == RiskLevel.HIGH:
            logger.warning(f"High risk detected, requiring confirmation: {risk_message}")
            # 可以在这里实现确认机制
            # 暂时继续执行，但记录警告

        # 批准订单意图
        logger.info(f"Order intent approved: {message.msg_id}")

    async def _check_order_risk(self, intent: OrderIntent) -> tuple[RiskLevel, str]:
        """检查订单风险"""
        # 检查仓位限制
        current_position = self._position_risks.get(intent.token_id)
        if current_position:
            new_size = current_position.size + intent.size
            if new_size > self._config.max_position_size:
                return RiskLevel.CRITICAL, f"Position size limit exceeded: {new_size} > {self._config.max_position_size}"

        # 检查日亏损限制
        # TODO: 实现日亏损检查

        # 检查最大回撤
        # TODO: 实现回撤检查

        return RiskLevel.NONE, ""

    async def _reject_order_intent(self, intent: OrderIntent, reason: str):
        """拒绝订单意图"""
        result = OrderResult(
            msg_id=str(uuid.uuid4()),
            msg_type="order_result",
            sender=self._agent_id,
            recipient=intent.sender,
            correlation_id=intent.msg_id,
            success=False,
            error_message=reason,
            error_code="RISK_REJECTED"
        )
        await self.send_message(result)

    async def _perform_risk_assessment(self):
        """执行风险评估"""
        # 检查每个持仓的风险
        for position_risk in list(self._position_risks.values()):
            await self._assess_position_risk(position_risk)

    async def _assess_position_risk(self, position_risk: PositionRisk):
        """评估单个持仓风险"""
        # 检查止损
        if position_risk.pnl_pct <= self._config.max_daily_loss:
            if not position_risk.stop_loss_triggered:
                position_risk.stop_loss_triggered = True
                await self._trigger_risk_alert(
                    RiskEventType.STOP_LOSS,
                    RiskLevel.HIGH,
                    f"Stop loss triggered for position {position_risk.position_id}",
                    {
                        "position_id": position_risk.position_id,
                        "pnl_pct": position_risk.pnl_pct,
                        "threshold": self._config.max_daily_loss
                    },
                    auto_action="close_position"
                )

        # 检查止盈
        if position_risk.pnl_pct >= self._config.default_take_profit_pct:
            if not position_risk.take_profit_triggered:
                position_risk.take_profit_triggered = True
                await self._trigger_risk_alert(
                    RiskEventType.TAKE_PROFIT,
                    RiskLevel.LOW,
                    f"Take profit triggered for position {position_risk.position_id}",
                    {
                        "position_id": position_risk.position_id,
                        "pnl_pct": position_risk.pnl_pct
                    }
                )

    async def _trigger_risk_alert(
        self,
        event_type: RiskEventType,
        risk_level: RiskLevel,
        message: str,
        metrics: Dict[str, Any],
        position_id: Optional[str] = None,
        auto_action: Optional[str] = None
    ):
        """触发风险警报"""
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            risk_level=risk_level,
            position_id=position_id,
            message=message,
            timestamp=datetime.utcnow(),
            metrics=metrics,
            auto_action=auto_action
        )

        self._active_risk_events[event.event_id] = event
        self._risk_event_history.append(event)

        # 创建警报消息
        alert = RiskAlert(
            msg_id=str(uuid.uuid4()),
            msg_type="risk_alert",
            sender=self._agent_id,
            alert_type=event_type.value,
            risk_level=risk_level,
            position_id=position_id,
            message=message,
            current_value=metrics.get("current_value", 0),
            threshold_value=metrics.get("threshold_value", 0),
            suggested_action=auto_action or "review",
            auto_action=auto_action,
            requires_ack=risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        )

        # 发送高优先级警报
        await self.send_message(alert)

        logger.warning(f"Risk alert triggered: {event_type.value} - {message}")

        # 执行自动操作
        if auto_action:
            await self._execute_risk_action(auto_action, event)

    async def _execute_risk_action(self, action: str, event: RiskEvent):
        """执行风险操作"""
        action_msg = RiskAction(
            msg_id=str(uuid.uuid4()),
            msg_type="risk_action",
            sender=self._agent_id,
            action_type=action,
            position_id=event.position_id,
            reason=event.message,
            authorized_by="risk_agent",
            force_execute=True
        )

        if action == "close_position":
            # 发送平仓指令
            await self.send_message(action_msg)
            event.actions_taken.append("sent_close_position")

        elif action == "halt_trading":
            await self.halt_trading(event.message)
            event.actions_taken.append("halted_trading")

        elif action == "reduce_position":
            await self.send_message(action_msg)
            event.actions_taken.append("sent_reduce_position")

        logger.info(f"Risk action executed: {action} for event {event.event_id}")

    async def _update_position_risk(self, position_update: PositionUpdate):
        """更新持仓风险"""
        position_risk = PositionRisk(
            position_id=position_update.position_id,
            token_id=position_update.token_id,
            size=position_update.size,
            entry_price=position_update.entry_price,
            current_price=position_update.current_price,
            unrealized_pnl=position_update.unrealized_pnl,
            pnl_pct=position_update.pnl_pct,
            from_high_pct=position_update.from_high_pct,
            risk_score=self._calculate_risk_score(position_update)
        )

        self._position_risks[position_update.position_id] = position_risk

    def _calculate_risk_score(self, position_update: PositionUpdate) -> float:
        """计算风险分数 (0-100)"""
        score = 0.0

        # 基于盈亏百分比
        if position_update.pnl_pct < -0.1:
            score += 40
        elif position_update.pnl_pct < -0.05:
            score += 25
        elif position_update.pnl_pct < -0.02:
            score += 10

        # 基于回撤
        if position_update.from_high_pct < -0.15:
            score += 30
        elif position_update.from_high_pct < -0.1:
            score += 15

        # 基于规模
        if position_update.size > self._config.max_position_size * 0.8:
            score += 20

        return min(100, score)

    async def _check_risk_events(self):
        """检查风险事件"""
        # 检查组合风险
        await self._check_portfolio_risk()

        # 检查过期事件
        now = datetime.utcnow()
        for event in list(self._active_risk_events.values()):
            if event.risk_level == RiskLevel.LOW and not event.acknowledged:
                # 低级别未确认事件，5分钟后自动解决
                if (now - event.timestamp).total_seconds() > 300:
                    event.resolved = True
                    event.resolved_at = now
                    del self._active_risk_events[event.event_id]

    async def _check_portfolio_risk(self):
        """检查组合风险"""
        if not self._portfolio_risk:
            return

        # 检查日亏损限制
        if self._portfolio_risk.daily_pnl <= self._config.max_daily_loss:
            await self._trigger_risk_alert(
                RiskEventType.DAILY_LOSS_LIMIT,
                RiskLevel.CRITICAL,
                f"Daily loss limit reached: {self._portfolio_risk.daily_pnl:.2%}",
                {
                    "daily_pnl": self._portfolio_risk.daily_pnl,
                    "limit": self._config.max_daily_loss
                },
                auto_action="halt_trading"
            )

        # 检查最大回撤
        if self._portfolio_risk.max_drawdown_pct <= self._config.max_drawdown:
            await self._trigger_risk_alert(
                RiskEventType.DRAWDOWN_LIMIT,
                RiskLevel.CRITICAL,
                f"Max drawdown limit reached: {self._portfolio_risk.max_drawdown_pct:.2%}",
                {
                    "drawdown": self._portfolio_risk.max_drawdown_pct,
                    "limit": self._config.max_drawdown
                },
                auto_action="halt_trading"
            )

    async def _update_portfolio_risk(self):
        """更新组合风险"""
        # 计算组合风险指标
        total_exposure = sum(pr.size * pr.current_price for pr in self._position_risks.values())
        total_unrealized_pnl = sum(pr.unrealized_pnl for pr in self._position_risks.values())

        # 计算风险等级
        risk_level = RiskLevel.NONE
        for pr in self._position_risks.values():
            if pr.risk_score >= 70:
                risk_level = RiskLevel.CRITICAL
                break
            elif pr.risk_score >= 50 and risk_level.value < RiskLevel.HIGH.value:
                risk_level = RiskLevel.HIGH
            elif pr.risk_score >= 30 and risk_level.value < RiskLevel.MEDIUM.value:
                risk_level = RiskLevel.MEDIUM

        self._portfolio_risk = PortfolioRisk(
            total_exposure=total_exposure,
            total_unrealized_pnl=total_unrealized_pnl,
            total_realized_pnl=0.0,  # 需要跟踪
            daily_pnl=0.0,  # 需要按日计算
            max_drawdown_pct=0.0,  # 需要计算历史回撤
            sharpe_ratio=0.0,
            var_95=0.0,
            concentration_risk={},
            risk_level=risk_level
        )

    # ==================== 公共API ====================

    async def halt_trading(self, reason: str):
        """暂停交易"""
        if self._trading_halted:
            return

        self._trading_halted = True
        self._halt_reason = reason
        self._halted_at = datetime.utcnow()

        logger.critical(f"Trading halted: {reason}")

        # 发送暂停交易的动作
        action = RiskAction(
            msg_id=str(uuid.uuid4()),
            msg_type="risk_action",
            sender=self._agent_id,
            action_type="halt_trading",
            reason=reason,
            authorized_by="risk_agent",
            force_execute=True
        )
        await self.send_message(action)

    async def resume_trading(self, reason: str):
        """恢复交易"""
        if not self._trading_halted:
            return

        self._trading_halted = False
        self._halt_reason = None

        logger.warning(f"Trading resumed: {reason}")

        # 发送恢复交易的动作
        action = RiskAction(
            msg_id=str(uuid.uuid4()),
            msg_type="risk_action",
            sender=self._agent_id,
            action_type="resume_trading",
            reason=reason,
            authorized_by="risk_agent",
            force_execute=True
        )
        await self.send_message(action)

    async def _check_trading_resumption(self):
        """检查是否应恢复交易"""
        if not self._trading_halted:
            return

        # 检查风险是否已经降低
        if self._portfolio_risk and self._portfolio_risk.risk_level in [RiskLevel.NONE, RiskLevel.LOW]:
            # 检查是否已经过了足够时间（例如30分钟）
            if self._halted_at:
                elapsed = (datetime.utcnow() - self._halted_at).total_seconds()
                if elapsed > 1800:  # 30分钟
                    await self.resume_trading("Risk levels normalized")

    def add_to_whitelist(self, agent_id: str):
        """添加Agent到白名单"""
        self._whitelist.add(agent_id)

    def remove_from_whitelist(self, agent_id: str):
        """从白名单移除Agent"""
        self._whitelist.discard(agent_id)

    def get_risk_report(self) -> Dict[str, Any]:
        """获取风险报告"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "portfolio_risk": self._portfolio_risk,
            "position_risks": list(self._position_risks.values()),
            "active_risk_events": len(self._active_risk_events),
            "trading_halted": self._trading_halted,
            "halt_reason": self._halt_reason,
        }

    def add_risk_action_callback(self, callback: Callable[[RiskAction], None]):
        """添加风控动作回调"""
        self._risk_action_callbacks.append(callback)

    async def _load_risk_history(self):
        """加载风险历史"""
        pass

    async def _save_risk_history(self):
        """保存风险历史"""
        pass

    def _setup_risk_thresholds(self) -> Dict[RiskEventType, RiskThreshold]:
        """设置风险阈值"""
        return {
            RiskEventType.STOP_LOSS: RiskThreshold(
                level=RiskLevel.HIGH,
                warning_threshold=-0.05,
                critical_threshold=-0.10,
                action="close",
                cooldown_minutes=5
            ),
            RiskEventType.DAILY_LOSS_LIMIT: RiskThreshold(
                level=RiskLevel.CRITICAL,
                warning_threshold=-0.03,
                critical_threshold=-0.05,
                action="halt",
                cooldown_minutes=60
            ),
        }
