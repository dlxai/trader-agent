"""
通信协议常量定义
"""

from enum import Enum, auto


class MessagePriority(Enum):
    """消息优先级"""
    CRITICAL = 0      # 紧急：风控干预、强制平仓
    HIGH = 1          # 高：交易执行、止损触发
    NORMAL = 2        # 普通：策略信号、状态更新
    LOW = 3           # 低：日志、监控数据


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TWAP = "twap"           # 时间加权平均价
    VWAP = "vwap"           # 成交量加权平均价
    ICEBERG = "iceberg"     # 冰山订单


class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class RiskLevel(Enum):
    """风险等级"""
    NONE = 0           # 无风险
    LOW = 1            # 低风险（提示）
    MEDIUM = 2         # 中风险（警告）
    HIGH = 3           # 高风险（限制）
    CRITICAL = 4       # 严重风险（停止）


class AgentType(Enum):
    """Agent类型"""
    STRATEGY = "strategy_agent"
    EXECUTION = "execution_agent"
    RISK = "risk_agent"
    ANALYTICS = "analytics_agent"
    ORCHESTRATOR = "orchestrator"
    MONITOR = "monitor_agent"


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    PARTIAL_EXIT = "partial_exit"
    INCREASE = "increase"
    DECREASE = "decrease"


class ExecutionStrategy(Enum):
    """执行策略"""
    IMMEDIATE = "immediate"        # 立即执行
    TWAP = "twap"                  # 时间加权
    VWAP = "vwap"                  # 成交量加权
    ADAPTIVE = "adaptive"          # 自适应
    PASSIVE = "passive"            # 被动挂单
    AGGRESSIVE = "aggressive"      # 激进吃单


class EventType(Enum):
    """事件类型"""
    # 市场数据事件
    PRICE_UPDATE = "price_update"
    ORDER_BOOK_UPDATE = "order_book_update"
    TRADE_UPDATE = "trade_update"
    MARKET_STATE_CHANGE = "market_state_change"

    # 交易事件
    ORDER_CREATED = "order_created"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"

    # 风险事件
    RISK_ALERT = "risk_alert"
    RISK_THRESHOLD_BREACH = "risk_threshold_breach"
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    TAKE_PROFIT_TRIGGERED = "take_profit_triggered"

    # Agent事件
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_ERROR = "agent_error"
    AGENT_HEARTBEAT = "agent_heartbeat"

    # 系统事件
    SYSTEM_SHUTDOWN = "system_shutdown"
    CONFIG_UPDATED = "config_updated"
