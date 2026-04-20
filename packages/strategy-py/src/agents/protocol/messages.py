"""
Agent间通信消息定义

定义所有Agent之间通信的消息格式
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from .constants import (
    MessagePriority, OrderType, OrderSide, RiskLevel,
    SignalType, ExecutionStrategy, AgentType, EventType
)


@dataclass
class BaseMessage:
    """消息基类"""
    msg_id: str
    msg_type: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sender: str = ""
    recipient: str = ""  # 空字符串表示广播
    correlation_id: Optional[str] = None  # 用于请求-响应关联
    priority: MessagePriority = MessagePriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type,
            "timestamp": self.timestamp.isoformat(),
            "sender": self.sender,
            "recipient": self.recipient,
            "correlation_id": self.correlation_id,
            "priority": self.priority.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseMessage":
        """从字典创建"""
        return cls(
            msg_id=data["msg_id"],
            msg_type=data["msg_type"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            sender=data.get("sender", ""),
            recipient=data.get("recipient", ""),
            correlation_id=data.get("correlation_id"),
            priority=MessagePriority(data.get("priority", 2)),
            metadata=data.get("metadata", {}),
        )


@dataclass
class MarketData(BaseMessage):
    """市场数据消息"""
    token_id: str = ""
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    volume_24h: float = 0.0
    change_24h: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    timestamp_exchange: Optional[datetime] = None

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "market_data"


@dataclass
class TradingSignal(BaseMessage):
    """交易信号消息"""
    strategy_id: str = ""
    signal_type: SignalType = SignalType.HOLD
    token_id: str = ""
    market_id: str = ""
    confidence: float = 0.0  # 置信度 0-1
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    size_recommendation: Optional[float] = None
    reasoning: str = ""  # 决策理由
    indicators: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "trading_signal"


@dataclass
class OrderIntent(BaseMessage):
    """订单意图消息（策略Agent -> 执行Agent）"""
    token_id: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.LIMIT
    price: Optional[float] = None
    size: float = 0.0
    time_in_force: str = "GTC"
    execution_strategy: ExecutionStrategy = ExecutionStrategy.IMMEDIATE
    max_slippage: float = 0.01  # 最大滑点 1%
    urgency: int = 5  # 紧急程度 1-10
    parent_signal_id: Optional[str] = None  # 关联的信号ID
    constraints: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "order_intent"


@dataclass
class OrderResult(BaseMessage):
    """订单执行结果（执行Agent -> 策略Agent/RiskAgent）"""
    order_id: str = ""
    success: bool = False
    status: str = ""  # PENDING, OPEN, FILLED, REJECTED, etc.
    filled_size: float = 0.0
    remaining_size: float = 0.0
    average_fill_price: float = 0.0
    fees: float = 0.0
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    execution_time_ms: float = 0.0
    slippage: float = 0.0

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "order_result"


@dataclass
class PositionUpdate(BaseMessage):
    """持仓更新消息"""
    position_id: str = ""
    token_id: str = ""
    market_id: str = ""
    side: str = ""
    entry_price: float = 0.0
    current_price: float = 0.0
    size: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    pnl_pct: float = 0.0
    highest_price: float = 0.0
    from_high_pct: float = 0.0
    opened_at: Optional[datetime] = None
    last_update: Optional[datetime] = None

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "position_update"


@dataclass
class RiskAlert(BaseMessage):
    """风险警报消息"""
    alert_type: str = ""  # stop_loss, position_limit, exposure, etc.
    risk_level: RiskLevel = RiskLevel.LOW
    position_id: Optional[str] = None
    token_id: Optional[str] = None
    current_value: float = 0.0
    threshold_value: float = 0.0
    message: str = ""
    suggested_action: str = ""
    auto_action: Optional[str] = None  # 自动执行的操作
    requires_ack: bool = False

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "risk_alert"


@dataclass
class RiskAction(BaseMessage):
    """风控执行动作"""
    action_type: str = ""  # close_position, reduce_position, halt_trading, etc.
    position_id: Optional[str] = None
    token_id: Optional[str] = None
    order_intent: Optional[OrderIntent] = None  # 关联的订单
    reason: str = ""
    authorized_by: str = ""  # 授权来源（risk_agent, manual, system）
    force_execute: bool = False  # 是否强制执行

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "risk_action"


@dataclass
class AnalysisResult(BaseMessage):
    """分析结果消息"""
    analysis_type: str = ""  # backtest, performance, signal_eval, prediction
    strategy_id: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    # 性能指标
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    # 分析详情
    signals_evaluated: int = 0
    recommendations: List[str] = field(default_factory=list)
    anomalies_detected: List[Dict[str, Any]] = field(default_factory=list)
    model_predictions: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "analysis_result"


@dataclass
class Heartbeat(BaseMessage):
    """心跳消息"""
    agent_type: str = ""
    agent_id: str = ""
    status: str = "healthy"  # healthy, warning, error, stopped
    uptime_seconds: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    # 负载指标
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    queue_depth: int = 0
    # 业务指标
    messages_processed: int = 0
    errors_count: int = 0
    last_error: Optional[str] = None

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "heartbeat"


@dataclass
class AgentStatus(BaseMessage):
    """Agent状态消息"""
    agent_type: str = ""
    agent_id: str = ""
    state: str = ""  # initializing, running, paused, stopping, stopped, error
    capabilities: List[str] = field(default_factory=list)
    config_version: str = ""
    started_at: Optional[datetime] = None
    current_task: Optional[str] = None
    task_progress: float = 0.0
    # 统计信息
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_task_duration_ms: float = 0.0

    def __post_init__(self):
        if not self.msg_type:
            self.msg_type = "agent_status"


@dataclass
class MessageWrapper:
    """消息包装器 - 用于序列化和传输"""
    version: str = "1.0"
    payload: Dict[str, Any] = field(default_factory=dict)
    signature: Optional[str] = None  # 消息签名（可选）
    compressed: bool = False
    encryption: str = "none"  # none, aes, rsa

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "payload": self.payload,
            "signature": self.signature,
            "compressed": self.compressed,
            "encryption": self.encryption,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageWrapper":
        return cls(
            version=data.get("version", "1.0"),
            payload=data.get("payload", {}),
            signature=data.get("signature"),
            compressed=data.get("compressed", False),
            encryption=data.get("encryption", "none"),
        )


# 消息类型到类的映射
MESSAGE_TYPE_MAP = {
    "market_data": MarketData,
    "trading_signal": TradingSignal,
    "order_intent": OrderIntent,
    "order_result": OrderResult,
    "position_update": PositionUpdate,
    "risk_alert": RiskAlert,
    "risk_action": RiskAction,
    "analysis_result": AnalysisResult,
    "heartbeat": Heartbeat,
    "agent_status": AgentStatus,
}
