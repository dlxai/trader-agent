"""
消息总线实现

提供Agent间通信的基础设施，支持：
- 发布-订阅模式
- 点对点通信
- 消息队列
- 广播
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, Set, Any, AsyncIterator
from enum import Enum, auto

from ..protocol.messages import BaseMessage, MessagePriority

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息总线消息类型"""
    DIRECT = "direct"      # 点对点
    BROADCAST = "broadcast"  # 广播
    PUBLISH = "publish"    # 发布-订阅


@dataclass
class Envelope:
    """消息信封（包装消息，添加路由信息）"""
    envelope_id: str
    message: BaseMessage
    msg_type: MessageType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ttl: Optional[int] = None  # 生存时间（秒）
    delivered_to: Set[str] = field(default_factory=set)
    failed_recipients: Dict[str, str] = field(default_factory=dict)

    @property
    def expired(self) -> bool:
        """检查是否过期"""
        if self.ttl is None:
            return False
        elapsed = (datetime.utcnow() - self.timestamp).total_seconds()
        return elapsed > self.ttl


class Subscription:
    """订阅"""

    def __init__(
        self,
        subscriber_id: str,
        topic: str,
        callback: Callable[[BaseMessage], None],
        message_filter: Optional[Callable[[BaseMessage], bool]] = None,
        priority: MessagePriority = MessagePriority.NORMAL
    ):
        self.subscriber_id = subscriber_id
        self.topic = topic
        self.callback = callback
        self.message_filter = message_filter
        self.priority = priority
        self.created_at = datetime.utcnow()
        self.message_count = 0
        self.active = True

    def should_receive(self, message: BaseMessage) -> bool:
        """检查是否应该接收消息"""
        if not self.active:
            return False
        if self.message_filter:
            return self.message_filter(message)
        return True

    async def deliver(self, message: BaseMessage):
        """投递消息"""
        try:
            if asyncio.iscoroutinefunction(self.callback):
                await self.callback(message)
            else:
                self.callback(message)
            self.message_count += 1
        except Exception as e:
            logger.error(f"Error delivering message to {self.subscriber_id}: {e}")


class MessageQueue:
    """优先级消息队列"""

    def __init__(self, max_size: int = 10000):
        self._queues: Dict[MessagePriority, asyncio.Queue] = {
            priority: asyncio.Queue(maxsize=max_size // 4)
            for priority in MessagePriority
        }
        self._size = 0
        self._max_size = max_size

    async def put(self, envelope: Envelope, priority: MessagePriority = MessagePriority.NORMAL):
        """放入消息"""
        if self._size >= self._max_size:
            # 丢弃低优先级消息
            if priority == MessagePriority.LOW:
                logger.warning("Queue full, dropping low priority message")
                return
            # 等待
            await asyncio.sleep(0.1)

        await self._queues[priority].put(envelope)
        self._size += 1

    async def get(self) -> Optional[Envelope]:
        """获取消息（按优先级）"""
        # 按优先级尝试获取
        for priority in MessagePriority:
            queue = self._queues[priority]
            if not queue.empty():
                envelope = await queue.get()
                self._size -= 1
                return envelope

        # 所有队列为空，等待
        return None

    def empty(self) -> bool:
        """检查是否为空"""
        return self._size == 0

    def qsize(self) -> int:
        """获取队列大小"""
        return self._size


class MessageBus:
    """
    消息总线

    提供Agent间通信的基础设施
    """

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._agent_queues: Dict[str, asyncio.Queue] = {}
        self._message_queue = MessageQueue()
        self._running = False
        self._delivery_task: Optional[asyncio.Task] = None

        # 统计信息
        self._stats = {
            "messages_published": 0,
            "messages_delivered": 0,
            "messages_dropped": 0,
            "subscriptions_created": 0,
        }

        self._initialized = True
        logger.info("MessageBus initialized")

    async def start(self):
        """启动消息总线"""
        if self._running:
            return

        self._running = True
        self._delivery_task = asyncio.create_task(self._delivery_loop())
        logger.info("MessageBus started")

    async def stop(self):
        """停止消息总线"""
        if not self._running:
            return

        self._running = False

        if self._delivery_task:
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass

        logger.info("MessageBus stopped")

    async def _delivery_loop(self):
        """投递循环"""
        while self._running:
            try:
                envelope = await self._message_queue.get()
                if envelope:
                    await self._deliver_envelope(envelope)
            except Exception as e:
                logger.error(f"Error in delivery loop: {e}")

    async def _deliver_envelope(self, envelope: Envelope):
        """投递信封"""
        if envelope.expired:
            self._stats["messages_dropped"] += 1
            logger.warning(f"Message {envelope.envelope_id} expired")
            return

        # 根据类型投递
        if envelope.msg_type == MessageType.DIRECT:
            await self._deliver_direct(envelope)
        elif envelope.msg_type == MessageType.BROADCAST:
            await self._deliver_broadcast(envelope)
        elif envelope.msg_type == MessageType.PUBLISH:
            await self._deliver_publish(envelope)

    async def _deliver_direct(self, envelope: Envelope):
        """点对点投递"""
        recipient = envelope.message.recipient
        if recipient in self._agent_queues:
            await self._agent_queues[recipient].put(envelope.message)
            envelope.delivered_to.add(recipient)
            self._stats["messages_delivered"] += 1

    async def _deliver_broadcast(self, envelope: Envelope):
        """广播投递"""
        for agent_id, queue in self._agent_queues.items():
            if agent_id != envelope.message.sender:
                await queue.put(envelope.message)
                envelope.delivered_to.add(agent_id)
        self._stats["messages_delivered"] += len(self._agent_queues)

    async def _deliver_publish(self, envelope: Envelope):
        """发布-订阅投递"""
        topic = envelope.message.msg_type
        subscriptions = self._subscriptions.get(topic, [])

        for sub in subscriptions:
            if sub.should_receive(envelope.message):
                await sub.deliver(envelope.message)
                envelope.delivered_to.add(sub.subscriber_id)

        self._stats["messages_delivered"] += len(envelope.delivered_to)

    # ==================== 公共API ====================

    def subscribe(
        self,
        subscriber_id: str,
        topic: str,
        callback: Callable[[BaseMessage], None],
        message_filter: Optional[Callable[[BaseMessage], bool]] = None,
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> Subscription:
        """
        订阅主题

        Args:
            subscriber_id: 订阅者ID
            topic: 主题
            callback: 回调函数
            message_filter: 消息过滤器
            priority: 优先级

        Returns:
            订阅对象
        """
        subscription = Subscription(
            subscriber_id=subscriber_id,
            topic=topic,
            callback=callback,
            message_filter=message_filter,
            priority=priority
        )

        self._subscriptions[topic].append(subscription)
        self._stats["subscriptions_created"] += 1

        logger.debug(f"{subscriber_id} subscribed to {topic}")
        return subscription

    def unsubscribe(self, subscription: Subscription):
        """取消订阅"""
        if subscription.topic in self._subscriptions:
            self._subscriptions[subscription.topic] = [
                s for s in self._subscriptions[subscription.topic]
                if s != subscription
            ]
            subscription.active = False
            logger.debug(f"{subscription.subscriber_id} unsubscribed from {subscription.topic}")

    async def publish(self, message: BaseMessage, priority: MessagePriority = MessagePriority.NORMAL):
        """
        发布消息

        Args:
            message: 消息
            priority: 优先级
        """
        envelope = Envelope(
            envelope_id=str(uuid.uuid4()),
            message=message,
            msg_type=MessageType.PUBLISH,
            ttl=message.metadata.get("ttl")
        )

        await self._message_queue.put(envelope, priority)
        self._stats["messages_published"] += 1

    async def send_direct(self, message: BaseMessage, recipient: str, priority: MessagePriority = MessagePriority.NORMAL):
        """
        发送点对点消息

        Args:
            message: 消息
            recipient: 接收者ID
            priority: 优先级
        """
        message.recipient = recipient

        envelope = Envelope(
            envelope_id=str(uuid.uuid4()),
            message=message,
            msg_type=MessageType.DIRECT,
            ttl=message.metadata.get("ttl")
        )

        await self._message_queue.put(envelope, priority)
        self._stats["messages_published"] += 1

    async def broadcast(self, message: BaseMessage, priority: MessagePriority = MessagePriority.NORMAL):
        """
        广播消息

        Args:
            message: 消息
            priority: 优先级
        """
        envelope = Envelope(
            envelope_id=str(uuid.uuid4()),
            message=message,
            msg_type=MessageType.BROADCAST,
            ttl=message.metadata.get("ttl")
        )

        await self._message_queue.put(envelope, priority)
        self._stats["messages_published"] += 1

    def register_agent_queue(self, agent_id: str, queue: asyncio.Queue):
        """注册Agent消息队列"""
        self._agent_queues[agent_id] = queue

    def unregister_agent_queue(self, agent_id: str):
        """注销Agent消息队列"""
        if agent_id in self._agent_queues:
            del self._agent_queues[agent_id]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()
