"""
消息序列化和反序列化

支持JSON和Protobuf格式（预留）
"""

import json
import logging
from typing import Dict, Any, Optional, Type, Union
from datetime import datetime
from dataclasses import asdict, is_dataclass

from .messages import (
    BaseMessage, MessageWrapper, MESSAGE_TYPE_MAP,
    MarketData, TradingSignal, OrderIntent, OrderResult,
    PositionUpdate, RiskAlert, RiskAction, AnalysisResult,
    Heartbeat, AgentStatus
)

logger = logging.getLogger(__name__)


class MessageSerializer:
    """消息序列化器"""

    @staticmethod
    def serialize(message: BaseMessage, compress: bool = False) -> str:
        """
        将消息序列化为JSON字符串

        Args:
            message: 消息对象
            compress: 是否压缩（预留）

        Returns:
            JSON字符串
        """
        try:
            # 转换为字典
            if hasattr(message, 'to_dict'):
                data = message.to_dict()
            elif is_dataclass(message):
                data = asdict(message)
            else:
                data = vars(message)

            # 处理特殊类型
            data = MessageSerializer._convert_special_types(data)

            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error serializing message: {e}")
            raise

    @staticmethod
    def deserialize(data: Union[str, Dict[str, Any]]) -> BaseMessage:
        """
        从JSON字符串或字典反序列化为消息对象

        Args:
            data: JSON字符串或字典

        Returns:
            具体的消息对象
        """
        try:
            if isinstance(data, str):
                data = json.loads(data)

            msg_type = data.get("msg_type")

            if not msg_type:
                # 尝试从payload获取（包装的消息）
                if "payload" in data:
                    return MessageSerializer.deserialize(data["payload"])
                raise ValueError("Message type not found")

            # 获取对应的类
            msg_class = MESSAGE_TYPE_MAP.get(msg_type)
            if not msg_class:
                # 尝试作为BaseMessage处理
                return BaseMessage.from_dict(data)

            return msg_class(**data)

        except Exception as e:
            logger.error(f"Error deserializing message: {e}")
            raise

    @staticmethod
    def wrap_message(message: BaseMessage, version: str = "1.0") -> MessageWrapper:
        """
        包装消息（添加版本、签名等信息）

        Args:
            message: 消息对象
            version: 协议版本

        Returns:
            包装后的消息
        """
        payload = message.to_dict() if hasattr(message, 'to_dict') else asdict(message)

        return MessageWrapper(
            version=version,
            payload=payload,
            compressed=False,
            encryption="none"
        )

    @staticmethod
    def unwrap_message(wrapper: MessageWrapper) -> BaseMessage:
        """
        解包消息

        Args:
            wrapper: 包装的消息

        Returns:
            原始消息对象
        """
        return MessageSerializer.deserialize(wrapper.payload)

    @staticmethod
    def _convert_special_types(obj: Any) -> Any:
        """转换特殊类型（如datetime、Enum）为可序列化类型"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Enum):
            return obj.value
        elif isinstance(obj, dict):
            return {k: MessageSerializer._convert_special_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [MessageSerializer._convert_special_types(item) for item in obj]
        return obj

    @staticmethod
    def create_market_data(
        token_id: str,
        price: float,
        sender: str = "market_data_agent"
    ) -> MarketData:
        """便捷方法：创建市场数据消息"""
        from uuid import uuid4
        return MarketData(
            msg_id=str(uuid4()),
            msg_type="market_data",
            sender=sender,
            token_id=token_id,
            price=price
        )

    @staticmethod
    def create_trading_signal(
        strategy_id: str,
        signal_type: SignalType,
        token_id: str,
        confidence: float,
        sender: str = "strategy_agent"
    ) -> TradingSignal:
        """便捷方法：创建交易信号"""
        from uuid import uuid4
        return TradingSignal(
            msg_id=str(uuid4()),
            msg_type="trading_signal",
            sender=sender,
            strategy_id=strategy_id,
            signal_type=signal_type,
            token_id=token_id,
            confidence=confidence
        )
