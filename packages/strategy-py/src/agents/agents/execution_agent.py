"""
执行Agent (ExecutionAgent)

职责：
1. 执行策略Agent的决策（下单、撤单、调整）
2. 订单管理和状态跟踪
3. 执行优化（TWAP、滑点控制、分批执行）
4. 执行结果反馈

输入：
- 订单意图（来自策略Agent）
- 当前市场状态
- 风控指令

输出：
- 实际订单
- 执行结果
- 订单状态更新
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from collections import defaultdict
import uuid

from ..core.agent_base import Agent, AgentConfig, AgentState
from ..protocol.messages import (
    BaseMessage, OrderIntent, OrderResult, MarketData,
    PositionUpdate, RiskAction, TradingSignal
)
from ..protocol.constants import (
    OrderType, OrderSide, ExecutionStrategy, MessagePriority
)

logger = logging.getLogger(__name__)


class OrderState(Enum):
    """订单状态"""
    PENDING = "pending"                # 等待提交
    SUBMITTING = "submitting"          # 正在提交
    OPEN = "open"                      # 已提交，等待成交
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    FILLED = "filled"                  # 完全成交
    CANCELLING = "cancelling"          # 正在取消
    CANCELLED = "cancelled"            # 已取消
    REJECTED = "rejected"              # 被拒绝
    ERROR = "error"                    # 错误


class ExecutionState(Enum):
    """执行状态"""
    IDLE = "idle"
    EXECUTING = "executing"
    SPLITTING = "splitting"        # 拆单中
    ADJUSTING = "adjusting"        # 调整中
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ActiveOrder:
    """活跃订单"""
    order_id: str
    intent_id: str
    external_order_id: Optional[str] = None
    state: OrderState = OrderState.PENDING
    token_id: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.LIMIT
    price: float = 0.0
    size: float = 0.0
    filled_size: float = 0.0
    remaining_size: float = 0.0
    average_fill_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionJob:
    """执行任务"""
    job_id: str
    intent: OrderIntent
    state: ExecutionState = ExecutionState.IDLE
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sub_orders: List[ActiveOrder] = field(default_factory=list)
    execution_plan: List[Dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    result: Optional[OrderResult] = None


@dataclass
class ExecutionConfig(AgentConfig):
    """执行Agent配置"""
    # 执行参数
    max_concurrent_orders: int = 10
    default_execution_strategy: ExecutionStrategy = ExecutionStrategy.ADAPTIVE
    max_slippage_bps: int = 50  # 最大滑点（基点）

    # 拆单参数
    enable_order_splitting: bool = True
    min_child_order_size: float = 10.0
    max_child_orders: int = 10

    # TWAP参数
    twap_slices: int = 5
    twap_interval_seconds: float = 60.0

    # 重试参数
    max_submission_retries: int = 3
    retry_delay_seconds: float = 1.0

    # 超时参数
    order_timeout_seconds: float = 300.0
    execution_timeout_seconds: float = 600.0

    # 回调
    on_order_filled: Optional[Callable[[ActiveOrder], None]] = None
    on_execution_complete: Optional[Callable[[ExecutionJob], None]] = None

    agent_type: str = "execution_agent"


class ExecutionAgent(Agent):
    """
    执行Agent

    负责执行订单和交易策略
    """

    def __init__(self, config: Optional[ExecutionConfig] = None):
        super().__init__(config or ExecutionConfig())
        self._config: ExecutionConfig = self._config

        # 执行任务
        self._active_jobs: Dict[str, ExecutionJob] = {}
        self._completed_jobs: deque = deque(maxlen=100)

        # 活跃订单（按外部订单ID索引）
        self._active_orders: Dict[str, ActiveOrder] = {}
        self._orders_by_intent: Dict[str, List[str]] = defaultdict(list)

        # 执行统计
        self._execution_stats = {
            "total_orders_submitted": 0,
            "total_orders_filled": 0,
            "total_orders_cancelled": 0,
            "total_orders_rejected": 0,
            "total_volume_traded": 0.0,
            "average_fill_price_deviation": 0.0,
            "average_slippage_bps": 0.0,
        }

        # 订单驱动（模拟或真实）
        self._order_driver: Optional[Any] = None

        # 执行锁
        self._execution_lock = asyncio.Lock()

        logger.info(f"ExecutionAgent {self._agent_id} initialized")

    # ==================== 生命周期方法 ====================

    async def _initialize(self):
        """初始化执行Agent"""
        logger.info("Initializing ExecutionAgent...")

        # 初始化订单驱动
        # self._order_driver = await self._create_order_driver()

        # 注册消息处理器
        self.register_message_handler("order_intent", self._on_order_intent)
        self.register_message_handler("market_data", self._on_market_data)
        self.register_message_handler("risk_action", self._on_risk_action)

        # 恢复未完成的订单
        await self._recover_pending_orders()

        logger.info("ExecutionAgent initialized successfully")

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
        """主运行逻辑 - 监控订单状态"""
        while self._running:
            try:
                # 检查活跃订单状态
                await self._check_active_orders()

                # 清理已完成的作业
                await self._cleanup_completed_jobs()

                # 更新执行统计
                await self._update_execution_stats()

                await asyncio.sleep(1)

            except Exception as e:
                logger.exception(f"Error in execution loop: {e}")
                await asyncio.sleep(5)

    async def _cleanup(self):
        """清理资源"""
        logger.info("Cleaning up ExecutionAgent...")

        # 取消所有未完成的订单
        for order in list(self._active_orders.values()):
            if order.state in [OrderState.OPEN, OrderState.PARTIALLY_FILLED]:
                await self._cancel_order(order.order_id)

        # 保存执行状态
        await self._save_execution_state()

        # 关闭订单驱动
        # if self._order_driver:
        #     await self._order_driver.close()

        logger.info("ExecutionAgent cleanup complete")

    # ==================== 消息处理器 ====================

    async def _on_order_intent(self, message):
        """处理订单意图"""
        if not isinstance(message, OrderIntent):
            return

        logger.info(f"Received order intent: {message.side} {message.size} {message.token_id}")

        # 创建执行任务
        job = await self._create_execution_job(message)

        # 执行
        asyncio.create_task(self._execute_job(job))

    async def _on_market_data(self, message):
        """处理市场数据"""
        # 更新最新价格，用于执行决策
        pass

    async def _on_risk_action(self, message):
        """处理风控动作"""
        from ..protocol.messages import RiskAction
        if isinstance(message, RiskAction):
            if message.action_type == "close_position":
                # 立即平仓
                await self._emergency_close_position(
                    message.position_id,
                    message.token_id
                )
            elif message.action_type == "halt_trading":
                # 停止交易
                await self._halt_trading()

    # ==================== 执行逻辑 ====================

    async def _create_execution_job(self, intent: OrderIntent) -> ExecutionJob:
        """创建执行任务"""
        job = ExecutionJob(
            job_id=str(uuid.uuid4()),
            intent=intent,
            state=ExecutionState.IDLE
        )
        self._active_jobs[job.job_id] = job
        return job

    async def _execute_job(self, job: ExecutionJob):
        """执行作业"""
        try:
            job.state = ExecutionState.EXECUTING
            job.started_at = datetime.utcnow()

            intent = job.intent

            # 检查是否需要拆单
            if self._should_split_order(intent):
                await self._execute_split_order(job)
            else:
                # 直接执行
                await self._execute_single_order(job)

            job.state = ExecutionState.COMPLETED
            job.completed_at = datetime.utcnow()

            # 调用回调
            if self._config.on_execution_complete:
                try:
                    if asyncio.iscoroutinefunction(self._config.on_execution_complete):
                        await self._config.on_execution_complete(job)
                    else:
                        self._config.on_execution_complete(job)
                except Exception as e:
                    logger.error(f"Error in execution complete callback: {e}")

        except Exception as e:
            logger.exception(f"Error executing job {job.job_id}: {e}")
            job.state = ExecutionState.FAILED
            raise

    def _should_split_order(self, intent: OrderIntent) -> bool:
        """判断是否需要拆单"""
        if not self._config.enable_order_splitting:
            return False

        # 根据执行策略判断
        if intent.execution_strategy == ExecutionStrategy.TWAP:
            return True

        # 根据订单大小判断
        if intent.size > self._config.min_child_order_size * 2:
            return True

        return False

    async def _execute_split_order(self, job: ExecutionJob):
        """执行拆单"""
        intent = job.intent

        # 计算拆单计划
        slices = self._calculate_slices(intent)
        job.execution_plan = slices

        logger.info(f"Executing split order: {len(slices)} slices")

        # 依次执行每个子订单
        for i, slice_plan in enumerate(slices):
            job.current_step = i

            # 创建子订单
            child_intent = self._create_child_intent(intent, slice_plan)
            child_job = await self._create_execution_job(child_intent)

            # 执行子订单
            await self._execute_single_order(child_job)

            # 等待下一个执行窗口（TWAP）
            if i < len(slices) - 1 and intent.execution_strategy == ExecutionStrategy.TWAP:
                await asyncio.sleep(self._config.twap_interval_seconds)

        logger.info(f"Split order execution completed: {job.job_id}")

    def _calculate_slices(self, intent: OrderIntent) -> List[Dict[str, Any]]:
        """计算拆单计划"""
        if intent.execution_strategy == ExecutionStrategy.TWAP:
            n_slices = self._config.twap_slices
        else:
            n_slices = min(
                int(intent.size / self._config.min_child_order_size),
                self._config.max_child_orders
            )

        base_size = intent.size / n_slices
        slices = []

        for i in range(n_slices):
            slice_size = base_size
            # 最后一个slice包含余数
            if i == n_slices - 1:
                slice_size = intent.size - sum(s["size"] for s in slices)

            slices.append({
                "slice_index": i,
                "size": slice_size,
                "delay_ms": i * self._config.twap_interval_seconds * 1000,
            })

        return slices

    def _create_child_intent(self, parent_intent: OrderIntent, slice_plan: Dict[str, Any]) -> OrderIntent:
        """创建子订单意图"""
        return OrderIntent(
            msg_id=str(uuid.uuid4()),
            msg_type="order_intent",
            sender=self._agent_id,
            token_id=parent_intent.token_id,
            side=parent_intent.side,
            order_type=parent_intent.order_type,
            price=parent_intent.price,
            size=slice_plan["size"],
            execution_strategy=ExecutionStrategy.IMMEDIATE,
            parent_signal_id=parent_intent.parent_signal_id,
            metadata={
                "parent_intent_id": parent_intent.msg_id,
                "slice_index": slice_plan["slice_index"],
            }
        )

    async def _execute_single_order(self, job: ExecutionJob):
        """执行单个订单"""
        intent = job.intent

        logger.info(f"Executing order: {intent.side} {intent.size} {intent.token_id} @ {intent.price}")

        # 创建订单记录
        order = ActiveOrder(
            order_id=str(uuid.uuid4()),
            intent_id=intent.msg_id,
            token_id=intent.token_id,
            side=intent.side,
            order_type=intent.order_type,
            price=intent.price or 0.0,
            size=intent.size,
            remaining_size=intent.size
        )

        self._active_orders[order.order_id] = order
        self._orders_by_intent[intent.msg_id].append(order.order_id)

        try:
            # 提交订单
            await self._submit_order(order)

            # 等待订单完成或超时
            start_time = datetime.utcnow()
            while order.state not in [OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.ERROR]:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                if elapsed > self._config.order_timeout_seconds:
                    logger.warning(f"Order {order.order_id} timeout, cancelling...")
                    await self._cancel_order(order.order_id)
                    break

                await asyncio.sleep(0.5)

            # 创建结果
            result = OrderResult(
                msg_id=str(uuid.uuid4()),
                msg_type="order_result",
                sender=self._agent_id,
                recipient=intent.sender,
                correlation_id=intent.msg_id,
                order_id=order.order_id,
                success=order.state == OrderState.FILLED,
                status=order.state.value,
                filled_size=order.filled_size,
                remaining_size=order.remaining_size,
                average_fill_price=order.average_fill_price,
                error_message=order.error_message,
                execution_time_ms=(order.filled_at - order.submitted_at).total_seconds() * 1000 if order.filled_at and order.submitted_at else 0
            )

            job.result = result

            # 发送结果
            await self.send_message(result)

            # 调用回调
            if order.state == OrderState.FILLED and self._config.on_order_filled:
                try:
                    if asyncio.iscoroutinefunction(self._config.on_order_filled):
                        await self._config.on_order_filled(order)
                    else:
                        self._config.on_order_filled(order)
                except Exception as e:
                    logger.error(f"Error in order filled callback: {e}")

        except Exception as e:
            logger.exception(f"Error executing order {order.order_id}: {e}")
            order.state = OrderState.ERROR
            order.error_message = str(e)
            raise

    async def _submit_order(self, order: ActiveOrder):
        """提交订单"""
        order.state = OrderState.SUBMITTING
        order.submitted_at = datetime.utcnow()

        logger.info(f"Submitting order: {order.side.value} {order.size} {order.token_id} @ {order.price}")

        try:
            # 这里应该调用实际的订单提交接口
            # 例如：调用Polymarket API
            external_id = await self._submit_to_exchange(order)

            if external_id:
                order.external_order_id = external_id
                order.state = OrderState.OPEN
                self._execution_stats["total_orders_submitted"] += 1
                logger.info(f"Order submitted successfully: {order.order_id} -> {external_id}")
            else:
                order.state = OrderState.ERROR
                order.error_message = "Failed to get external order ID"
                raise Exception("Failed to submit order")

        except Exception as e:
            logger.exception(f"Error submitting order {order.order_id}: {e}")
            order.state = OrderState.ERROR
            order.error_message = str(e)

            # 重试逻辑
            if order.metadata.get("retry_count", 0) < self._config.max_submission_retries:
                order.metadata["retry_count"] = order.metadata.get("retry_count", 0) + 1
                logger.info(f"Retrying order submission ({order.metadata['retry_count']}/{self._config.max_submission_retries})")
                await asyncio.sleep(self._config.retry_delay_seconds * order.metadata["retry_count"])
                await self._submit_order(order)
            else:
                raise

    async def _submit_to_exchange(self, order: ActiveOrder) -> Optional[str]:
        """
        提交订单到交易所

        这里应该实现与Polymarket或其他交易所的集成
        返回外部订单ID
        """
        # 模拟提交
        await asyncio.sleep(0.1)

        # 生成模拟的外部订单ID
        external_id = f"ext_{order.order_id[:8]}_{int(datetime.utcnow().timestamp())}"

        return external_id

    async def _cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        order = self._active_orders.get(order_id)
        if not order:
            logger.warning(f"Order not found for cancellation: {order_id}")
            return False

        if order.state not in [OrderState.OPEN, OrderState.PARTIALLY_FILLED, OrderState.SUBMITTING]:
            logger.warning(f"Cannot cancel order in state {order.state}: {order_id}")
            return False

        order.state = OrderState.CANCELLING

        try:
            # 这里应该调用实际的取消接口
            success = await self._cancel_on_exchange(order)

            if success:
                order.state = OrderState.CANCELLED
                order.updated_at = datetime.utcnow()
                self._execution_stats["total_orders_cancelled"] += 1
                logger.info(f"Order cancelled successfully: {order_id}")
                return True
            else:
                order.state = OrderState.ERROR
                order.error_message = "Failed to cancel order"
                return False

        except Exception as e:
            logger.exception(f"Error cancelling order {order_id}: {e}")
            order.state = OrderState.ERROR
            order.error_message = str(e)
            return False

    async def _cancel_on_exchange(self, order: ActiveOrder) -> bool:
        """在交易所取消订单"""
        # 模拟取消
        await asyncio.sleep(0.05)
        return True

    async def _check_active_orders(self):
        """检查活跃订单状态"""
        for order in list(self._active_orders.values()):
            if order.state in [OrderState.OPEN, OrderState.PARTIALLY_FILLED]:
                try:
                    # 查询订单状态
                    await self._query_order_status(order)
                except Exception as e:
                    logger.error(f"Error checking order status for {order.order_id}: {e}")

    async def _query_order_status(self, order: ActiveOrder):
        """查询订单状态"""
        # 这里应该调用实际的查询接口
        # 模拟状态更新
        pass

    async def _cleanup_completed_jobs(self):
        """清理已完成的作业"""
        completed_jobs = [
            job_id for job_id, job in self._active_jobs.items()
            if job.state in [ExecutionState.COMPLETED, ExecutionState.FAILED]
        ]

        for job_id in completed_jobs:
            job = self._active_jobs.pop(job_id)
            self._completed_jobs.append(job)

    async def _update_execution_stats(self):
        """更新执行统计"""
        # 可以在这里计算更多统计指标
        pass

    async def _recover_pending_orders(self):
        """恢复待处理的订单"""
        # 从持久化存储恢复未完成的订单
        pass

    async def _save_execution_state(self):
        """保存执行状态"""
        # 持久化当前执行状态
        pass

    async def _emergency_close_position(self, position_id: str, token_id: str):
        """紧急平仓"""
        logger.warning(f"Emergency close position: {position_id} {token_id}")

        # 创建市价卖出意图
        intent = OrderIntent(
            msg_id=str(uuid.uuid4()),
            msg_type="order_intent",
            sender=self._agent_id,
            token_id=token_id,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            size=0,  # 全部
            urgency=10,
            metadata={"emergency": True, "position_id": position_id}
        )

        # 立即执行
        job = await self._create_execution_job(intent)
        await self._execute_job(job)

    async def _halt_trading(self):
        """停止交易"""
        logger.warning("Halting trading...")

        # 取消所有待处理作业
        for job in list(self._active_jobs.values()):
            if job.state in [ExecutionState.IDLE, ExecutionState.EXECUTING]:
                job.state = ExecutionState.FAILED
                # 取消相关订单
                for order_id in self._orders_by_intent.get(job.intent.msg_id, []):
                    await self._cancel_order(order_id)

    # ==================== 公共API ====================

    async def submit_order_direct(self, intent: OrderIntent) -> OrderResult:
        """直接提交订单（用于程序化交易）"""
        job = await self._create_execution_job(intent)
        await self._execute_job(job)
        return job.result if job.result else OrderResult(
            msg_id=str(uuid.uuid4()),
            msg_type="order_result",
            sender=self._agent_id,
            success=False,
            error_message="Execution failed"
        )

    def get_active_orders(self, token_id: Optional[str] = None) -> List[ActiveOrder]:
        """获取活跃订单"""
        orders = list(self._active_orders.values())
        if token_id:
            orders = [o for o in orders if o.token_id == token_id]
        return orders

    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        return {
            **self._execution_stats,
            "active_orders": len(self._active_orders),
            "active_jobs": len(self._active_jobs),
        }
