"""
Agent注册表

管理Agent的注册、发现和元数据
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Set, Type
from enum import Enum

from ..protocol.constants import AgentType

logger = logging.getLogger(__name__)


@dataclass
class AgentMetadata:
    """Agent元数据"""
    agent_id: str
    agent_type: AgentType
    agent_name: str
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentRegistration:
    """Agent注册信息"""
    metadata: AgentMetadata
    instance: Optional[Any] = None
    state: str = "registered"  # registered, initialized, running, stopped, error
    last_heartbeat: Optional[datetime] = None
    health_score: float = 100.0
    statistics: Dict[str, Any] = field(default_factory=dict)
    error_count: int = 0


class AgentRegistry:
    """
    Agent注册表

    提供Agent的注册、发现和元数据管理
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

        self._registrations: Dict[str, AgentRegistration] = {}
        self._type_index: Dict[AgentType, Set[str]] = defaultdict(set)
        self._capability_index: Dict[str, Set[str]] = defaultdict(set)
        self._state_callbacks: List[Callable[[str, str, str], None]] = []

        self._initialized = True
        logger.info("AgentRegistry initialized")

    def register(
        self,
        metadata: AgentMetadata,
        instance: Optional[Any] = None
    ) -> str:
        """
        注册Agent

        Args:
            metadata: Agent元数据
            instance: Agent实例（可选）

        Returns:
            注册的Agent ID
        """
        agent_id = metadata.agent_id

        registration = AgentRegistration(
            metadata=metadata,
            instance=instance,
            state="registered"
        )

        self._registrations[agent_id] = registration
        self._type_index[metadata.agent_type].add(agent_id)

        for capability in metadata.capabilities:
            self._capability_index[capability].add(agent_id)

        logger.info(f"Registered agent: {agent_id} ({metadata.agent_type.value})")
        return agent_id

    def unregister(self, agent_id: str) -> bool:
        """
        注销Agent

        Args:
            agent_id: Agent ID

        Returns:
            是否成功注销
        """
        if agent_id not in self._registrations:
            return False

        registration = self._registrations[agent_id]
        metadata = registration.metadata

        # 从索引中移除
        self._type_index[metadata.agent_type].discard(agent_id)

        for capability in metadata.capabilities:
            self._capability_index[capability].discard(agent_id)

        # 从注册表中移除
        del self._registrations[agent_id]

        logger.info(f"Unregistered agent: {agent_id}")
        return True

    def get_registration(self, agent_id: str) -> Optional[AgentRegistration]:
        """获取Agent注册信息"""
        return self._registrations.get(agent_id)

    def get_instance(self, agent_id: str) -> Optional[Any]:
        """获取Agent实例"""
        registration = self._registrations.get(agent_id)
        return registration.instance if registration else None

    def find_by_type(self, agent_type: AgentType) -> List[str]:
        """按类型查找Agent"""
        return list(self._type_index.get(agent_type, set()))

    def find_by_capability(self, capability: str) -> List[str]:
        """按能力查找Agent"""
        return list(self._capability_index.get(capability, set()))

    def update_state(self, agent_id: str, new_state: str):
        """更新Agent状态"""
        if agent_id not in self._registrations:
            return

        registration = self._registrations[agent_id]
        old_state = registration.state
        registration.state = new_state
        registration.metadata.updated_at = datetime.utcnow()

        # 触发回调
        for callback in self._state_callbacks:
            try:
                callback(agent_id, old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state callback: {e}")

    def update_heartbeat(self, agent_id: str):
        """更新心跳"""
        if agent_id in self._registrations:
            self._registrations[agent_id].last_heartbeat = datetime.utcnow()
            self._registrations[agent_id].health_score = min(
                100,
                self._registrations[agent_id].health_score + 1
            )

    def update_statistics(self, agent_id: str, statistics: Dict[str, Any]):
        """更新统计信息"""
        if agent_id in self._registrations:
            self._registrations[agent_id].statistics = statistics

    def record_error(self, agent_id: str):
        """记录错误"""
        if agent_id in self._registrations:
            self._registrations[agent_id].error_count += 1
            self._registrations[agent_id].health_score -= 10

    def register_state_callback(self, callback: Callable[[str, str, str], None]):
        """注册状态变更回调"""
        self._state_callbacks.append(callback)

    def get_all_registrations(self) -> Dict[str, AgentRegistration]:
        """获取所有注册信息"""
        return dict(self._registrations)

    def get_registry_stats(self) -> Dict[str, Any]:
        """获取注册表统计"""
        return {
            "total_registered": len(self._registrations),
            "by_type": {
                agent_type.value: len(agent_ids)
                for agent_type, agent_ids in self._type_index.items()
            },
            "by_state": self._count_by_state(),
            "total_capabilities": len(self._capability_index)
        }

    def _count_by_state(self) -> Dict[str, int]:
        """按状态计数"""
        counts = defaultdict(int)
        for registration in self._registrations.values():
            counts[registration.state] += 1
        return dict(counts)

    def clear(self):
        """清空注册表"""
        self._registrations.clear()
        self._type_index.clear()
        self._capability_index.clear()
        self._state_callbacks.clear()
        logger.info("AgentRegistry cleared")
