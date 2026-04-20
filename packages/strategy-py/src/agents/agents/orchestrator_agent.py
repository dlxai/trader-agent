"""
编排Agent (OrchestratorAgent)

职责：
1. 协调各Agent之间的协作
2. 管理Agent生命周期
3. 处理系统级事件
4. 监控系统健康状态
5. 管理配置和状态同步

输入：
- Agent状态更新
- 系统事件
- 用户命令

输出：
- 协调指令
- 系统状态
- 配置更新

特点：
- 中央协调者
- 具有全局视野
- 可干预其他Agent
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set, Type
from enum import Enum
from collections import defaultdict
import uuid

from ..core.agent_base import Agent, AgentConfig, AgentState
from ..core.registry import AgentRegistry
from ..core.message_bus import MessageBus
from ..protocol.messages import (
    BaseMessage, AgentStatus, Heartbeat, TradingSignal,
    OrderIntent, OrderResult, RiskAlert, RiskAction,
    AnalysisResult, PositionUpdate
)
from ..protocol.constants import AgentType, RiskLevel, MessagePriority

logger = logging.getLogger(__name__)


class SystemState(Enum):
    """系统状态"""
    INITIALIZING = "initializing"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"          # 降级运行
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class OrchestratorMode(Enum):
    """编排模式"""
    AUTONOMOUS = "autonomous"      # 完全自主
    SUPERVISED = "supervised"        # 监督模式（需要确认）
    MANUAL = "manual"                # 手动模式
    BACKTEST = "backtest"            # 回测模式


@dataclass
class AgentInfo:
    """Agent信息"""
    agent_id: str
    agent_type: AgentType
    agent_name: str
    state: AgentState
    last_heartbeat: Optional[datetime] = None
    capabilities: List[str] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    health_score: float = 100.0  # 0-100
    errors_count: int = 0


@dataclass
class SystemConfig:
    """系统配置"""
    mode: OrchestratorMode = OrchestratorMode.AUTONOMOUS
    trading_enabled: bool = True
    risk_checks_enabled: bool = True
    auto_recovery_enabled: bool = True
    max_concurrent_agents: int = 10
    heartbeat_timeout_seconds: float = 60.0
    agent_restart_limit: int = 3


@dataclass
class OrchestratorConfig(AgentConfig):
    """编排Agent配置"""
    # 系统配置
    system_config: SystemConfig = field(default_factory=SystemConfig)

    # 检查间隔
    health_check_interval: float = 10.0
    state_sync_interval: float = 30.0

    # 恢复参数
    auto_restart_failed_agents: bool = True
    restart_cooldown_seconds: float = 60.0

    agent_type: str = "orchestrator_agent"
    agent_name: str = "orchestrator"


class OrchestratorAgent(Agent):
    """
    编排Agent

    协调和管理所有其他Agent
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        super().__init__(config or OrchestratorConfig())
        self._config: OrchestratorConfig = self._config

        # 系统状态
        self._system_state = SystemState.INITIALIZING
        self._system_start_time: Optional[datetime] = None

        # Agent注册表
        self._agent_registry: Dict[str, AgentInfo] = {}
        self._agent_instances: Dict[str, Agent] = {}  # 管理的Agent实例

        # 消息总线
        self._message_bus: Optional[MessageBus] = None

        # 系统配置
        self._system_config = self._config.system_config

        # 故障记录
        self._agent_failures: Dict[str, List[datetime]] = defaultdict(list)

        # 回调注册
        self._state_change_callbacks: List[Callable[[SystemState, SystemState], None]] = []
        self._agent_state_callbacks: List[Callable[[str, AgentState, AgentState], None]] = []

        logger.info(f"OrchestratorAgent {self._agent_id} initialized")

    # ==================== 生命周期方法 ====================

    async def _initialize(self):
        """初始化编排Agent"""
        logger.info("Initializing OrchestratorAgent...")

        # 初始化消息总线
        self._message_bus = MessageBus()
        await self._message_bus.start()

        # 注册消息处理器
        self.register_message_handler("heartbeat", self._on_heartbeat)
        self.register_message_handler("agent_status", self._on_agent_status)
        self.register_message_handler("risk_alert", self._on_risk_alert)
        self.register_message_handler("analysis_result", self._on_analysis_result)

        # 初始化管理的Agent
        await self._initialize_managed_agents()

        logger.info("OrchestratorAgent initialized successfully")

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
        """主运行逻辑"""
        # 启动系统
        await self._start_system()

        # 主监控循环
        while self._running:
            try:
                # 健康检查
                await self._perform_health_check()

                # 状态同步
                await self._sync_agent_states()

                # 检查Agent故障
                await self._check_agent_failures()

                await asyncio.sleep(self._config.health_check_interval)

            except Exception as e:
                logger.exception(f"Error in orchestrator main loop: {e}")
                await asyncio.sleep(5)

    async def _cleanup(self):
        """清理资源"""
        logger.info("Cleaning up OrchestratorAgent...")

        # 停止系统
        await self._stop_system()

        # 停止消息总线
        if self._message_bus:
            await self._message_bus.stop()

        logger.info("OrchestratorAgent cleanup complete")

    # ==================== 系统管理 ====================

    async def _start_system(self):
        """启动系统"""
        logger.info("Starting system...")
        self._system_state = SystemState.STARTING
        self._system_start_time = datetime.utcnow()

        # 启动所有管理的Agent
        for agent_id, agent in self._agent_instances.items():
            try:
                if agent.state == AgentState.READY:
                    await agent.start()
                    logger.info(f"Started agent: {agent_id}")
            except Exception as e:
                logger.error(f"Error starting agent {agent_id}: {e}")

        self._system_state = SystemState.RUNNING
        logger.info("System started successfully")

    async def _stop_system(self):
        """停止系统"""
        logger.info("Stopping system...")
        self._system_state = SystemState.STOPPING

        # 停止所有管理的Agent
        for agent_id, agent in list(self._agent_instances.items()):
            try:
                await agent.stop()
                logger.info(f"Stopped agent: {agent_id}")
            except Exception as e:
                logger.error(f"Error stopping agent {agent_id}: {e}")

        self._system_state = SystemState.STOPPED
        logger.info("System stopped")

    async def _initialize_managed_agents(self):
        """初始化管理的Agent"""
        # 这里应该根据配置初始化各种Agent
        # 例如：StrategyAgent, ExecutionAgent, RiskAgent, AnalyticsAgent
        pass

    def register_agent(self, agent: Agent, agent_type: AgentType) -> str:
        """注册Agent"""
        agent_id = agent.agent_id

        # 创建Agent信息
        info = AgentInfo(
            agent_id=agent_id,
            agent_type=agent_type,
            agent_name=agent.agent_name,
            state=agent.state,
            capabilities=[]  # 可以从Agent获取
        )

        self._agent_registry[agent_id] = info
        self._agent_instances[agent_id] = agent

        # 注册消息队列
        if self._message_bus:
            self._message_bus.register_agent_queue(agent_id, asyncio.Queue())

        logger.info(f"Registered agent: {agent_id} ({agent_type.value})")
        return agent_id

    def unregister_agent(self, agent_id: str):
        """注销Agent"""
        if agent_id in self._agent_registry:
            del self._agent_registry[agent_id]

        if agent_id in self._agent_instances:
            del self._agent_instances[agent_id]

        if self._message_bus:
            self._message_bus.unregister_agent_queue(agent_id)

        logger.info(f"Unregistered agent: {agent_id}")

    # ==================== 监控和健康管理 ====================

    async def _perform_health_check(self):
        """执行健康检查"""
        for agent_id, info in list(self._agent_registry.items()):
            # 检查心跳超时
            if info.last_heartbeat:
                elapsed = (datetime.utcnow() - info.last_heartbeat).total_seconds()
                if elapsed > self._config.system_config.heartbeat_timeout_seconds:
                    logger.warning(f"Agent {agent_id} heartbeat timeout")
                    info.health_score -= 20

            # 检查错误次数
            if info.errors_count > 10:
                logger.warning(f"Agent {agent_id} has too many errors")
                info.health_score -= 30

            # 健康分数限制在0-100
            info.health_score = max(0, min(100, info.health_score))

    async def _sync_agent_states(self):
        """同步Agent状态"""
        for agent_id, agent in self._agent_instances.items():
            if agent_id in self._agent_registry:
                info = self._agent_registry[agent_id]
                if info.state != agent.state:
                    old_state = info.state
                    info.state = agent.state
                    # 触发状态变更回调
                    for callback in self._agent_state_callbacks:
                        try:
                            callback(agent_id, old_state, agent.state)
                        except Exception as e:
                            logger.error(f"Error in agent state callback: {e}")

    async def _check_agent_failures(self):
        """检查Agent故障"""
        if not self._config.auto_restart_failed_agents:
            return

        for agent_id, info in list(self._agent_registry.items()):
            if info.state == AgentState.ERROR:
                # 检查重启次数
                failures = self._agent_failures.get(agent_id, [])
                recent_failures = [
                    f for f in failures
                    if (datetime.utcnow() - f).total_seconds() < 3600
                ]

                if len(recent_failures) >= self._config.system_config.agent_restart_limit:
                    logger.error(f"Agent {agent_id} has too many recent failures, not restarting")
                    continue

                # 尝试重启
                logger.info(f"Attempting to restart failed agent: {agent_id}")
                await asyncio.sleep(self._config.restart_cooldown_seconds)

                agent = self._agent_instances.get(agent_id)
                if agent:
                    try:
                        # 重新初始化
                        success = await agent.initialize()
                        if success:
                            await agent.start()
                            self._agent_failures[agent_id].append(datetime.utcnow())
                            logger.info(f"Agent {agent_id} restarted successfully")
                    except Exception as e:
                        logger.error(f"Failed to restart agent {agent_id}: {e}")

    # ==================== 消息处理器 ====================

    async def _on_heartbeat(self, message: Heartbeat):
        """处理心跳"""
        if message.agent_id in self._agent_registry:
            info = self._agent_registry[message.agent_id]
            info.last_heartbeat = datetime.utcnow()
            info.health_score = min(100, info.health_score + 5)
            info.statistics = message.metrics

    async def _on_agent_status(self, message: AgentStatus):
        """处理Agent状态"""
        if message.agent_id in self._agent_registry:
            info = self._agent_registry[message.agent_id]
            old_state = info.state
            info.state = AgentState(message.state)

            # 触发回调
            for callback in self._agent_state_callbacks:
                try:
                    callback(message.agent_id, old_state, info.state)
                except Exception as e:
                    logger.error(f"Error in state callback: {e}")

    async def _on_risk_alert(self, message: RiskAlert):
        """处理风险警报"""
        if message.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            logger.critical(f"High risk alert received: {message.message}")
            # 可以在这里触发系统级响应

    async def _on_analysis_result(self, message: AnalysisResult):
        """处理分析结果"""
        logger.info(f"Analysis result received: {message.analysis_type}")
        # 可以在这里处理分析结果，如更新策略参数

    # ==================== 公共API ====================

    def get_system_state(self) -> SystemState:
        """获取系统状态"""
        return self._system_state

    def get_agent_info(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """获取Agent信息"""
        if agent_id:
            info = self._agent_registry.get(agent_id)
            return {
                "agent_id": info.agent_id,
                "agent_type": info.agent_type.value,
                "agent_name": info.agent_name,
                "state": info.state.value,
                "health_score": info.health_score,
                "last_heartbeat": info.last_heartbeat.isoformat() if info.last_heartbeat else None,
                "errors_count": info.errors_count,
                "statistics": info.statistics
            } if info else None

        return {
            agent_id: {
                "agent_type": info.agent_type.value,
                "agent_name": info.agent_name,
                "state": info.state.value,
                "health_score": info.health_score
            }
            for agent_id, info in self._agent_registry.items()
        }

    def register_state_change_callback(self, callback: Callable[[SystemState, SystemState], None]):
        """注册系统状态变更回调"""
        self._state_change_callbacks.append(callback)

    def register_agent_state_callback(self, callback: Callable[[str, AgentState, AgentState], None]):
        """注册Agent状态变更回调"""
        self._agent_state_callbacks.append(callback)

    async def halt_trading(self, reason: str):
        """停止交易"""
        logger.critical(f"Halting trading: {reason}")
        # 通知风控Agent
        if self._message_bus:
            from ..protocol.messages import RiskAction
            action = RiskAction(
                msg_id=str(uuid.uuid4()),
                msg_type="risk_action",
                sender=self._agent_id,
                action_type="halt_trading",
                reason=reason,
                authorized_by="orchestrator",
                force_execute=True
            )
            await self._message_bus.publish(action, MessagePriority.CRITICAL)

    async def resume_trading(self, reason: str):
        """恢复交易"""
        logger.warning(f"Resuming trading: {reason}")
        if self._message_bus:
            from ..protocol.messages import RiskAction
            action = RiskAction(
                msg_id=str(uuid.uuid4()),
                msg_type="risk_action",
                sender=self._agent_id,
                action_type="resume_trading",
                reason=reason,
                authorized_by="orchestrator",
                force_execute=True
            )
            await self._message_bus.publish(action, MessagePriority.HIGH)

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "system_state": self._system_state.value,
            "system_start_time": self._system_start_time.isoformat() if self._system_start_time else None,
            "uptime_seconds": (datetime.utcnow() - self._system_start_time).total_seconds() if self._system_start_time else 0,
            "registered_agents": len(self._agent_registry),
            "active_agents": sum(1 for info in self._agent_registry.values() if info.state == AgentState.RUNNING),
            "system_config": {
                "mode": self._system_config.mode.value,
                "trading_enabled": self._system_config.trading_enabled,
                "risk_checks_enabled": self._system_config.risk_checks_enabled
            }
        }
