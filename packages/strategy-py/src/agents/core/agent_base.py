"""
Agent基类定义

提供所有Agent的基础功能，包括生命周期管理、消息处理和状态管理
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable, Set, TypeVar

from ..protocol.messages import BaseMessage, Heartbeat, AgentStatus

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent状态"""
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AgentConfig:
    """Agent配置"""
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_name: str = "agent"
    agent_type: str = "base"
    heartbeat_interval: float = 30.0  # 心跳间隔（秒）
    max_queue_size: int = 1000  # 消息队列最大大小
    processing_interval: float = 0.1  # 处理间隔（秒）
    enable_heartbeat: bool = True
    auto_recover: bool = True  # 是否自动恢复
    max_retries: int = 3  # 最大重试次数
    timeout: float = 30.0  # 操作超时（秒）
    # 扩展配置
    extra_config: Dict[str, Any] = field(default_factory=dict)


T = TypeVar('T', bound=BaseMessage)


class Agent(ABC):
    """
    Agent基类

    所有Agent的抽象基类，提供：
    1. 生命周期管理（初始化、启动、停止）
    2. 消息处理（接收、处理、发送）
    3. 状态管理
    4. 心跳机制
    5. 错误处理和恢复

    子类需要实现：
    - _initialize(): 初始化逻辑
    - _process_message(): 消息处理逻辑
    - _run(): 主运行逻辑（如果需要）
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        """
        初始化Agent

        Args:
            config: Agent配置，如果为None则使用默认配置
        """
        self._config = config or AgentConfig()
        self._agent_id = self._config.agent_id
        self._agent_name = self._config.agent_name
        self._agent_type = self._config.agent_type

        # 状态管理
        self._state = AgentState.INITIALIZING
        self._state_lock = asyncio.Lock()
        self._last_state_change = datetime.utcnow()

        # 消息队列
        self._message_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self._config.max_queue_size
        )
        self._subscribed_topics: Set[str] = set()

        # 消息处理器映射
        self._message_handlers: Dict[str, Callable[[BaseMessage], None]] = {}

        # 运行控制
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
        self._stop_event = asyncio.Event()

        # 统计信息
        self._stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "messages_processed": 0,
            "errors": 0,
            "start_time": None,
            "last_heartbeat": None,
        }

        # 注册默认消息处理器
        self._register_default_handlers()

        logger.info(f"Agent {self._agent_name} ({self._agent_id}) initialized")

    # ==================== 属性 ====================

    @property
    def agent_id(self) -> str:
        """Agent ID"""
        return self._agent_id

    @property
    def agent_name(self) -> str:
        """Agent名称"""
        return self._agent_name

    @property
    def agent_type(self) -> str:
        """Agent类型"""
        return self._agent_type

    @property
    def state(self) -> AgentState:
        """当前状态"""
        return self._state

    @property
    def is_running(self) -> bool:
        """是否运行中"""
        return self._running

    @property
    def stats(self) -> Dict[str, Any]:
        """统计信息"""
        return self._stats.copy()

    # ==================== 生命周期管理 ====================

    async def initialize(self) -> bool:
        """
        初始化Agent

        Returns:
            bool: 是否初始化成功
        """
        async with self._state_lock:
            if self._state != AgentState.INITIALIZING:
                logger.warning(f"Agent not in INITIALIZING state: {self._state}")
                return False

            try:
                await self._initialize()
                self._state = AgentState.READY
                self._last_state_change = datetime.utcnow()
                logger.info(f"Agent {self._agent_name} initialized successfully")
                return True
            except Exception as e:
                logger.exception(f"Error initializing agent {self._agent_name}: {e}")
                self._state = AgentState.ERROR
                self._stats["errors"] += 1
                return False

    async def start(self) -> bool:
        """
        启动Agent

        Returns:
            bool: 是否启动成功
        """
        async with self._state_lock:
            if self._state not in [AgentState.READY, AgentState.STOPPED]:
                logger.warning(f"Agent not ready to start: {self._state}")
                return False

            try:
                self._running = True
                self._state = AgentState.RUNNING
                self._last_state_change = datetime.utcnow()
                self._stats["start_time"] = datetime.utcnow()

                # 启动主任务
                main_task = asyncio.create_task(self._run())
                self._tasks.add(main_task)
                main_task.add_done_callback(self._tasks.discard)

                # 启动消息处理任务
                process_task = asyncio.create_task(self._message_loop())
                self._tasks.add(process_task)
                process_task.add_done_callback(self._tasks.discard)

                # 启动心跳任务
                if self._config.enable_heartbeat:
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    self._tasks.add(heartbeat_task)
                    heartbeat_task.add_done_callback(self._tasks.discard)

                logger.info(f"Agent {self._agent_name} started")
                return True

            except Exception as e:
                logger.exception(f"Error starting agent {self._agent_name}: {e}")
                self._state = AgentState.ERROR
                self._running = False
                return False

    async def stop(self, timeout: float = 30.0) -> bool:
        """
        停止Agent

        Args:
            timeout: 停止超时时间（秒）

        Returns:
            bool: 是否停止成功
        """
        async with self._state_lock:
            if not self._running:
                return True

            try:
                logger.info(f"Stopping agent {self._agent_name}...")
                self._state = AgentState.STOPPING
                self._running = False
                self._stop_event.set()

                # 取消所有任务
                if self._tasks:
                    for task in list(self._tasks):
                        if not task.done():
                            task.cancel()

                    # 等待任务完成
                    done, pending = await asyncio.wait(
                        self._tasks,
                        timeout=timeout,
                        return_when=asyncio.ALL_COMPLETED
                    )

                    # 强制取消未完成的任务
                    for task in pending:
                        task.cancel()

                # 执行清理
                await self._cleanup()

                self._state = AgentState.STOPPED
                self._last_state_change = datetime.utcnow()
                logger.info(f"Agent {self._agent_name} stopped")
                return True

            except Exception as e:
                logger.exception(f"Error stopping agent {self._agent_name}: {e}")
                self._state = AgentState.ERROR
                return False

    async def pause(self) -> bool:
        """暂停Agent"""
        async with self._state_lock:
            if self._state != AgentState.RUNNING:
                return False
            self._state = AgentState.PAUSED
            logger.info(f"Agent {self._agent_name} paused")
            return True

    async def resume(self) -> bool:
        """恢复Agent"""
        async with self._state_lock:
            if self._state != AgentState.PAUSED:
                return False
            self._state = AgentState.RUNNING
            logger.info(f"Agent {self._agent_name} resumed")
            return True

    # ==================== 消息处理 ====================

    def register_message_handler(
        self,
        msg_type: str,
        handler: Callable[[BaseMessage], None]
    ):
        """
        注册消息处理器

        Args:
            msg_type: 消息类型
            handler: 处理函数
        """
        self._message_handlers[msg_type] = handler
        logger.debug(f"Registered handler for {msg_type}")

    def unregister_message_handler(self, msg_type: str):
        """注销消息处理器"""
        if msg_type in self._message_handlers:
            del self._message_handlers[msg_type]

    async def send_message(self, message: BaseMessage) -> bool:
        """
        发送消息

        Args:
            message: 要发送的消息

        Returns:
            bool: 是否发送成功
        """
        try:
            # 设置发送者
            if not message.sender:
                message.sender = self._agent_id

            # 将消息放入队列
            await self._message_queue.put(message)
            self._stats["messages_sent"] += 1

            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def receive_message(self, timeout: Optional[float] = None) -> Optional[BaseMessage]:
        """
        接收消息

        Args:
            timeout: 超时时间（秒），None表示无限等待

        Returns:
            接收到的消息，超时返回None
        """
        try:
            message = await asyncio.wait_for(
                self._message_queue.get(),
                timeout=timeout
            )
            self._stats["messages_received"] += 1
            return message
        except asyncio.TimeoutError:
            return None

    # ==================== 内部方法 ====================

    def _register_default_handlers(self):
        """注册默认消息处理器"""
        self.register_message_handler("heartbeat", self._handle_heartbeat)
        self.register_message_handler("agent_status", self._handle_agent_status)

    def _handle_heartbeat(self, message: Heartbeat):
        """处理心跳消息"""
        # 可以在这里更新Agent健康状态
        pass

    def _handle_agent_status(self, message: AgentStatus):
        """处理Agent状态消息"""
        # 可以在这里处理其他Agent的状态变更
        pass

    async def _message_loop(self):
        """消息处理循环"""
        logger.debug(f"Message loop started for {self._agent_name}")

        while self._running:
            try:
                # 检查是否暂停
                if self._state == AgentState.PAUSED:
                    await asyncio.sleep(0.5)
                    continue

                # 从队列获取消息
                try:
                    message = await asyncio.wait_for(
                        self._message_queue.get(),
                        timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                # 处理消息
                await self._process_message(message)
                self._stats["messages_processed"] += 1

            except Exception as e:
                logger.exception(f"Error in message loop: {e}")
                self._stats["errors"] += 1

        logger.debug(f"Message loop stopped for {self._agent_name}")

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._running:
            try:
                # 等待心跳间隔
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._config.heartbeat_interval
                )
                # 如果_stop_event被设置，退出循环
                break
            except asyncio.TimeoutError:
                # 发送心跳
                await self._send_heartbeat()

    async def _send_heartbeat(self):
        """发送心跳"""
        try:
            heartbeat = Heartbeat(
                msg_id=str(uuid.uuid4()),
                msg_type="heartbeat",
                sender=self._agent_id,
                agent_type=self._agent_type,
                agent_id=self._agent_id,
                status="healthy" if self._state == AgentState.RUNNING else "warning",
                uptime_seconds=self._get_uptime(),
                messages_processed=self._stats["messages_processed"],
                queue_depth=self._message_queue.qsize()
            )

            # 发送到消息总线（如果有）
            # 这里可以通过回调或消息总线发送
            await self._on_heartbeat(heartbeat)

            self._stats["last_heartbeat"] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")

    def _get_uptime(self) -> float:
        """获取运行时间（秒）"""
        if self._stats["start_time"]:
            return (datetime.utcnow() - self._stats["start_time"]).total_seconds()
        return 0.0

    # ==================== 抽象方法（子类必须实现） ====================

    @abstractmethod
    async def _initialize(self):
        """
        初始化Agent

        子类必须实现，执行具体的初始化逻辑
        """
        pass

    @abstractmethod
    async def _process_message(self, message: BaseMessage):
        """
        处理消息

        子类必须实现，执行具体的消息处理逻辑

        Args:
            message: 要处理的消息
        """
        pass

    async def _run(self):
        """
        Agent主运行逻辑

        子类可以选择性实现，用于执行定时任务或后台逻辑
        """
        # 默认实现：空循环
        while self._running:
            await asyncio.sleep(1)

    async def _cleanup(self):
        """
        清理资源

        子类可以选择性实现，执行清理逻辑
        """
        pass

    async def _on_heartbeat(self, heartbeat: Heartbeat):
        """
        心跳发送回调

        子类可以选择性实现，用于处理心跳发送

        Args:
            heartbeat: 心跳消息
        """
        pass
