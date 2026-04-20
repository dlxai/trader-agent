"""
Agent间通信协议定义

定义消息格式、消息类型、序列化/反序列化
"""

from .messages import (
    BaseMessage,
    TradingSignal,
    OrderIntent,
    OrderResult,
    RiskAlert,
    RiskAction,
    MarketData,
    PositionUpdate,
    AnalysisResult,
    Heartbeat,
    AgentStatus,
    MessageWrapper,
)
from .serializer import MessageSerializer
from .constants import (
    MessagePriority,
    OrderType,
    OrderSide,
    RiskLevel,
    AgentType,
)

__all__ = [
    # Messages
    'BaseMessage',
    'TradingSignal',
    'OrderIntent',
    'OrderResult',
    'RiskAlert',
    'RiskAction',
    'MarketData',
    'PositionUpdate',
    'AnalysisResult',
    'Heartbeat',
    'AgentStatus',
    'MessageWrapper',
    # Protocol utilities
    'MessageSerializer',
    # Constants
    'MessagePriority',
    'OrderType',
    'OrderSide',
    'RiskLevel',
    'AgentType',
]
