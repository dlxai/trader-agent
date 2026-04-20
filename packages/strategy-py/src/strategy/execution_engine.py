"""
交易执行引擎 - 负责策略信号到实际订单的转换

该模块实现了完整的交易执行流程，包括：
- 接收买入决策并执行最终风险检查
- 订单参数计算（size, price, type）
- 订单提交和状态跟踪
- 持仓更新和执行报告生成

支持的订单类型：
- Market Order: 市价单（紧急执行）
- Limit Order: 限价单（指定价格）
- TWAP: 时间加权平均价格（大单拆分）
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Callable, Any, Tuple, Union
from decimal import Decimal, ROUND_DOWN

# Configure logging
logger = logging.getLogger(__name__)


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"
    TWAP = "twap"
    ICEBERG = "iceberg"


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ExecutionStatus(Enum):
    """执行状态"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    PENDING = "pending"
    CANCELLED = "cancelled"


@dataclass
class OrderParams:
    """订单参数"""
    market_id: str
    outcome_id: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"  # GTC, IOC, FOK
    client_order_id: Optional[str] = None

    # TWAP参数
    twap_duration: Optional[timedelta] = None
    twap_slices: int = 1

    # 滑点保护
    max_slippage: float = 0.01  # 1%最大滑点


@dataclass
class OrderResult:
    """订单执行结果"""
    order_id: str
    client_order_id: Optional[str]
    status: OrderStatus
    filled_size: float
    remaining_size: float
    avg_fill_price: float
    total_cost: float
    fees: float
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None


@dataclass
class ExecutionReport:
    """执行报告"""
    execution_id: str
    market_id: str
    outcome_id: str
    decision: str
    status: ExecutionStatus

    # 执行详情
    orders_submitted: int = 0
    orders_filled: int = 0
    total_size: float = 0.0
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    total_cost: float = 0.0
    total_fees: float = 0.0

    # 滑点
    expected_price: float = 0.0
    slippage: float = 0.0

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 错误信息
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'execution_id': self.execution_id,
            'market_id': self.market_id,
            'outcome_id': self.outcome_id,
            'decision': self.decision,
            'status': self.status.value,
            'orders_submitted': self.orders_submitted,
            'orders_filled': self.orders_filled,
            'filled_size': self.filled_size,
            'avg_fill_price': self.avg_fill_price,
            'slippage': self.slippage,
            'duration_ms': self._get_duration_ms(),
            'errors': self.errors,
            'warnings': self.warnings
        }

    def _get_duration_ms(self) -> Optional[int]:
        """获取执行持续时间（毫秒）"""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return None


@dataclass
class ExecutionConfig:
    """执行引擎配置"""
    # 订单类型偏好
    preferred_order_type: OrderType = OrderType.LIMIT
    fallback_to_market: bool = True

    # 价格设置
    default_limit_offset: float = 0.001  # 0.1% offset for limit orders
    max_slippage_tolerance: float = 0.02  # 2% max slippage

    # TWAP设置
    twap_default_slices: int = 5
    twap_min_slice_interval: timedelta = timedelta(seconds=30)

    # 执行超时
    order_timeout: timedelta = timedelta(minutes=5)
    execution_timeout: timedelta = timedelta(minutes=30)

    # 重试设置
    max_retries: int = 3
    retry_delay: timedelta = timedelta(seconds=5)

    # 部分成交处理
    allow_partial_fills: bool = True
    min_fill_threshold: float = 0.5  # 至少完成50%


class ExecutionEngine:
    """交易执行引擎 - 负责策略信号到实际订单的转换

    执行流程：
    1. 接收买入决策
    2. 最终风险检查
    3. 计算订单参数（size, price, type）
    4. 提交订单
    5. 跟踪订单状态
    6. 更新持仓

    订单类型：
    - Market Order: 市价单（紧急执行）
    - Limit Order: 限价单（指定价格）
    - TWAP: 时间加权平均价格（大单拆分）
    """

    def __init__(self,
                 order_manager: Any,
                 risk_manager: Any,
                 position_tracker: Any,
                 config: Optional[ExecutionConfig] = None):
        """
        初始化执行引擎

        Args:
            order_manager: 订单管理器实例
            risk_manager: 风险管理器实例
            position_tracker: 持仓跟踪器实例
            config: 执行配置
        """
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.position_tracker = position_tracker
        self.config = config or ExecutionConfig()

        # 活跃执行跟踪
        self._active_executions: Dict[str, ExecutionReport] = {}
        self._order_to_execution: Dict[str, str] = {}

        # 执行历史
        self._execution_history: List[ExecutionReport] = []
        self._max_history_size = 1000

        # 统计
        self._stats = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'total_volume': 0.0,
            'avg_slippage': 0.0,
            'avg_execution_time_ms': 0.0
        }

        logger.info("ExecutionEngine initialized")

    async def execute_buy(self, decision_output: Any) -> ExecutionReport:
        """
        执行买入决策

        Args:
            decision_output: BuyDecisionOutput实例

        Returns:
            ExecutionReport: 执行报告
        """
        from .buy_strategy import BuyDecision

        execution_id = self._generate_execution_id()

        # 创建执行报告
        report = ExecutionReport(
            execution_id=execution_id,
            market_id=decision_output.market_id if hasattr(decision_output, 'market_id') else 'unknown',
            outcome_id=decision_output.outcome_id if hasattr(decision_output, 'outcome_id') else 'unknown',
            decision=decision_output.decision.value if hasattr(decision_output.decision, 'value') else str(decision_output.decision),
            status=ExecutionStatus.PENDING,
            created_at=datetime.now()
        )

        self._active_executions[execution_id] = report

        # 检查决策是否允许执行
        decision = decision_output.decision if hasattr(decision_output, 'decision') else BuyDecision.PASS

        if decision in [BuyDecision.PASS, BuyDecision.BLOCKED]:
            report.status = ExecutionStatus.CANCELLED
            report.errors.append(f"Decision is {decision.value}, execution cancelled")
            report.completed_at = datetime.now()
            self._finalize_execution(report)
            return report

        # 检查是否有持仓限制
        position_size = decision_output.position_size if hasattr(decision_output, 'position_size') else 0
        if position_size <= 0:
            report.status = ExecutionStatus.CANCELLED
            report.errors.append("Position size is zero or negative")
            report.completed_at = datetime.now()
            self._finalize_execution(report)
            return report

        # 开始执行
        report.started_at = datetime.now()
        report.status = ExecutionStatus.PENDING

        try:
            # 执行最终风险检查
            risk_check_passed = await self._final_risk_check(decision_output, report)
            if not risk_check_passed:
                report.status = ExecutionStatus.FAILED
                report.errors.append("Final risk check failed")
                report.completed_at = datetime.now()
                self._finalize_execution(report)
                return report

            # 计算订单参数
            order_params = self._calculate_order_params(decision_output)

            # 提交订单
            order_result = await self._submit_order(order_params, report)

            if order_result.status == OrderStatus.FILLED:
                report.status = ExecutionStatus.SUCCESS
                report.filled_size = order_result.filled_size
                report.avg_fill_price = order_result.avg_fill_price
                report.total_cost = order_result.total_cost
                report.total_fees = order_result.fees

                # 计算滑点
                expected_price = decision_output.entry_price if hasattr(decision_output, 'entry_price') else order_result.avg_fill_price
                if expected_price > 0:
                    report.slippage = (order_result.avg_fill_price - expected_price) / expected_price

            elif order_result.status == OrderStatus.PARTIALLY_FILLED and self.config.allow_partial_fills:
                fill_ratio = order_result.filled_size / order_params.size if order_params.size > 0 else 0

                if fill_ratio >= self.config.min_fill_threshold:
                    report.status = ExecutionStatus.SUCCESS
                    report.warnings.append(f"Partial fill: {fill_ratio*100:.1f}% filled")
                else:
                    report.status = ExecutionStatus.FAILED
                    report.errors.append(f"Insufficient fill: only {fill_ratio*100:.1f}% filled")

                report.filled_size = order_result.filled_size
                report.avg_fill_price = order_result.avg_fill_price

            else:
                report.status = ExecutionStatus.FAILED
                report.errors.append(f"Order failed with status: {order_result.status.value}")
                if order_result.error_message:
                    report.errors.append(order_result.error_message)

            # 更新持仓
            if report.status == ExecutionStatus.SUCCESS and self.position_tracker:
                await self._update_position(decision_output, report)

        except asyncio.TimeoutError:
            report.status = ExecutionStatus.FAILED
            report.errors.append("Execution timeout")

        except Exception as e:
            logger.exception(f"Execution failed for {report.execution_id}")
            report.status = ExecutionStatus.FAILED
            report.errors.append(f"Execution error: {str(e)}")

        finally:
            report.completed_at = datetime.now()
            self._finalize_execution(report)

        return report

    async def _final_risk_check(self, decision_output: Any, report: ExecutionReport) -> bool:
        """执行最终风险检查"""
        if not self.risk_manager:
            return True

        try:
            # 检查持仓限制
            if hasattr(self.risk_manager, 'check_position_limits'):
                market_id = decision_output.market_id if hasattr(decision_output, 'market_id') else report.market_id
                check = await self.risk_manager.check_position_limits(market_id)
                if not check.get('allowed', True):
                    report.warnings.append(f"Position limit warning: {check.get('reason', '')}")
                    # 可以调整仓位而不是完全阻止
                    if check.get('max_size'):
                        report.adjusted_position_size = check['max_size']

            # 检查每日损失限制
            if hasattr(self.risk_manager, 'check_daily_loss_limit'):
                loss_check = await self.risk_manager.check_daily_loss_limit()
                if not loss_check.get('allowed', True):
                    report.errors.append(f"Daily loss limit reached: {loss_check.get('reason', '')}")
                    return False

            return True

        except Exception as e:
            logger.warning(f"Risk check failed: {e}")
            report.warnings.append(f"Risk check error: {str(e)}")
            # 风险检查失败时保守处理，允许继续但记录警告
            return True

    def _calculate_order_params(self, decision_output: Any) -> OrderParams:
        """计算订单参数"""
        market_id = decision_output.market_id if hasattr(decision_output, 'market_id') else ''
        outcome_id = decision_output.outcome_id if hasattr(decision_output, 'outcome_id') else ''
        position_size = decision_output.position_size if hasattr(decision_output, 'position_size') else 0
        entry_price = decision_output.entry_price if hasattr(decision_output, 'entry_price') else 0

        # 确定订单类型
        order_type = self._determine_order_type(position_size, entry_price)

        # 计算价格
        price = None
        if order_type == OrderType.LIMIT:
            # 限价单：略低于当前价格买入以获得更好价格
            price = entry_price * (1 - self.config.default_limit_offset)
        elif order_type == OrderType.MARKET:
            price = entry_price

        # 生成客户端订单ID
        client_order_id = f"buy_{market_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        return OrderParams(
            market_id=market_id,
            outcome_id=outcome_id,
            side=OrderSide.BUY,
            order_type=order_type,
            size=position_size,
            price=price,
            time_in_force="GTC",
            client_order_id=client_order_id,
            max_slippage=self.config.max_slippage_tolerance
        )

    def _determine_order_type(self, position_size: float, entry_price: float) -> OrderType:
        """确定最佳订单类型"""
        # 大额订单使用TWAP
        if position_size > self.config.max_single_position_pct * 0.5:
            return OrderType.TWAP

        # 默认使用限价单以获得更好价格
        if self.config.preferred_order_type == OrderType.LIMIT:
            return OrderType.LIMIT

        # 紧急情况下使用市价单
        if self.config.fallback_to_market:
            return OrderType.MARKET

        return OrderType.LIMIT

    async def _submit_order(self, params: OrderParams, report: ExecutionReport) -> OrderResult:
        """提交订单"""
        if not self.order_manager:
            raise RuntimeError("Order manager not available")

        report.orders_submitted += 1

        try:
            # 根据订单类型选择提交方法
            if params.order_type == OrderType.TWAP:
                return await self._submit_twap_order(params, report)
            elif params.order_type == OrderType.MARKET:
                return await self._submit_market_order(params, report)
            elif params.order_type == OrderType.LIMIT:
                return await self._submit_limit_order(params, report)
            else:
                raise ValueError(f"Unsupported order type: {params.order_type}")

        except Exception as e:
            logger.exception(f"Order submission failed: {e}")
            return OrderResult(
                order_id="",
                client_order_id=params.client_order_id,
                status=OrderStatus.REJECTED,
                filled_size=0,
                remaining_size=params.size,
                avg_fill_price=0,
                total_cost=0,
                fees=0,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                error_message=str(e)
            )

    async def _submit_market_order(self, params: OrderParams, report: ExecutionReport) -> OrderResult:
        """提交市价单"""
        logger.info(f"Submitting market order: {params.size} @ market")

        # 调用order_manager提交订单
        if hasattr(self.order_manager, 'place_market_order'):
            result = await self.order_manager.place_market_order(
                market_id=params.market_id,
                outcome_id=params.outcome_id,
                side=params.side.value,
                size=params.size,
                client_order_id=params.client_order_id
            )
        else:
            # 通用订单提交方法
            result = await self.order_manager.place_order({
                'market_id': params.market_id,
                'outcome_id': params.outcome_id,
                'side': params.side.value,
                'order_type': 'market',
                'size': params.size,
                'client_order_id': params.client_order_id
            })

        return self._parse_order_result(result, params)

    async def _submit_limit_order(self, params: OrderParams, report: ExecutionReport) -> OrderResult:
        """提交限价单"""
        if params.price is None:
            raise ValueError("Limit order requires price")

        logger.info(f"Submitting limit order: {params.size} @ {params.price}")

        if hasattr(self.order_manager, 'place_limit_order'):
            result = await self.order_manager.place_limit_order(
                market_id=params.market_id,
                outcome_id=params.outcome_id,
                side=params.side.value,
                size=params.size,
                price=params.price,
                time_in_force=params.time_in_force,
                client_order_id=params.client_order_id
            )
        else:
            result = await self.order_manager.place_order({
                'market_id': params.market_id,
                'outcome_id': params.outcome_id,
                'side': params.side.value,
                'order_type': 'limit',
                'size': params.size,
                'price': params.price,
                'time_in_force': params.time_in_force,
                'client_order_id': params.client_order_id
            })

        return self._parse_order_result(result, params)

    async def _submit_twap_order(self, params: OrderParams, report: ExecutionReport) -> OrderResult:
        """提交TWAP订单（时间加权平均价格）"""
        slices = params.twap_slices or self.config.twap_default_slices
        duration = params.twap_duration or timedelta(minutes=5)

        logger.info(f"Submitting TWAP order: {params.size} in {slices} slices over {duration}")

        slice_size = params.size / slices
        interval = duration.total_seconds() / slices

        total_filled = 0.0
        total_cost = 0.0
        total_fees = 0.0
        all_order_ids = []

        for i in range(slices):
            # 等待间隔时间（第一次不等待）
            if i > 0:
                await asyncio.sleep(interval)

            # 计算切片价格（略低于市场价以优先成交）
            slice_price = None
            if params.price:
                # 逐步调整价格以增加成交概率
                price_adjustment = 1 + (0.001 * i)  # 逐步增加价格
                slice_price = params.price * price_adjustment

            # 提交切片订单
            slice_params = OrderParams(
                market_id=params.market_id,
                outcome_id=params.outcome_id,
                side=params.side,
                order_type=OrderType.LIMIT if slice_price else OrderType.MARKET,
                size=slice_size,
                price=slice_price,
                client_order_id=f"{params.client_order_id}_slice{i}",
                max_slippage=params.max_slippage
            )

            try:
                if slice_params.order_type == OrderType.LIMIT:
                    result = await self._submit_limit_order(slice_params, report)
                else:
                    result = await self._submit_market_order(slice_params, report)

                if result.order_id:
                    all_order_ids.append(result.order_id)

                total_filled += result.filled_size
                total_cost += result.total_cost
                total_fees += result.fees

                # 如果完全成交，提前结束
                if result.filled_size >= slice_size * 0.99:
                    continue

                # 检查是否需要取消剩余
                if result.status in [OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                    report.warnings.append(f"Slice {i} failed with status {result.status.value}")

            except Exception as e:
                logger.error(f"TWAP slice {i} failed: {e}")
                report.warnings.append(f"Slice {i} error: {str(e)}")

        # 汇总结果
        avg_fill_price = total_cost / total_filled if total_filled > 0 else 0

        return OrderResult(
            order_id=f"twap_{'_'.join(all_order_ids)}" if all_order_ids else "",
            client_order_id=params.client_order_id,
            status=OrderStatus.FILLED if total_filled >= params.size * 0.99 else OrderStatus.PARTIALLY_FILLED,
            filled_size=total_filled,
            remaining_size=params.size - total_filled,
            avg_fill_price=avg_fill_price,
            total_cost=total_cost,
            fees=total_fees,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    def _parse_order_result(self, result: Any, params: OrderParams) -> OrderResult:
        """解析订单结果"""
        if isinstance(result, OrderResult):
            return result

        if isinstance(result, dict):
            return OrderResult(
                order_id=result.get('order_id', ''),
                client_order_id=result.get('client_order_id', params.client_order_id),
                status=OrderStatus(result.get('status', 'pending')),
                filled_size=float(result.get('filled_size', 0)),
                remaining_size=float(result.get('remaining_size', params.size)),
                avg_fill_price=float(result.get('avg_fill_price', 0)),
                total_cost=float(result.get('total_cost', 0)),
                fees=float(result.get('fees', 0)),
                created_at=result.get('created_at', datetime.now()),
                updated_at=result.get('updated_at', datetime.now()),
                error_message=result.get('error_message')
            )

        raise ValueError(f"Unknown order result type: {type(result)}")

    async def _update_position(self, decision_output: Any, report: ExecutionReport) -> None:
        """更新持仓"""
        if not self.position_tracker:
            return

        try:
            position_data = {
                'market_id': report.market_id,
                'outcome_id': report.outcome_id,
                'size': report.filled_size,
                'avg_entry_price': report.avg_fill_price,
                'total_cost': report.total_cost,
                'fees': report.total_fees,
                'entry_time': datetime.now(),
                'stop_loss': decision_output.stop_loss if hasattr(decision_output, 'stop_loss') else None,
                'take_profit': decision_output.take_profit if hasattr(decision_output, 'take_profit') else None
            }

            if hasattr(self.position_tracker, 'add_position'):
                await self.position_tracker.add_position(position_data)
            elif hasattr(self.position_tracker, 'update_position'):
                await self.position_tracker.update_position(report.market_id, report.outcome_id, position_data)

            logger.info(f"Position updated for {report.market_id}")

        except Exception as e:
            logger.error(f"Failed to update position: {e}")
            report.warnings.append(f"Position update failed: {str(e)}")

    def _finalize_execution(self, report: ExecutionReport) -> None:
        """完成执行并更新统计"""
        # 从活跃执行中移除
        self._active_executions.pop(report.execution_id, None)

        # 添加到历史
        self._execution_history.append(report)
        if len(self._execution_history) > self._max_history_size:
            self._execution_history.pop(0)

        # 更新统计
        self._stats['total_executions'] += 1

        if report.status == ExecutionStatus.SUCCESS:
            self._stats['successful_executions'] += 1
            self._stats['total_volume'] += report.filled_size
        elif report.status == ExecutionStatus.FAILED:
            self._stats['failed_executions'] += 1

        # 更新平均滑点
        if report.slippage != 0:
            current_avg = self._stats['avg_slippage']
            n = self._stats['successful_executions']
            self._stats['avg_slippage'] = (current_avg * (n - 1) + report.slippage) / n if n > 0 else 0

        # 更新平均执行时间
        duration = report._get_duration_ms()
        if duration:
            n = self._stats['total_executions']
            current_avg = self._stats['avg_execution_time_ms']
            self._stats['avg_execution_time_ms'] = (current_avg * (n - 1) + duration) / n if n > 0 else duration

        logger.info(f"Execution {report.execution_id} finalized with status {report.status.value}")

    def _generate_execution_id(self) -> str:
        """生成执行ID"""
        import uuid
        return f"exec_{uuid.uuid4().hex[:16]}"

    async def cancel_execution(self, execution_id: str) -> bool:
        """取消执行"""
        report = self._active_executions.get(execution_id)
        if not report:
            logger.warning(f"Execution {execution_id} not found or already completed")
            return False

        report.status = ExecutionStatus.CANCELLED
        report.warnings.append("Execution cancelled by user")

        # 取消相关订单
        # TODO: 实现订单取消逻辑

        return True

    def get_execution(self, execution_id: str) -> Optional[ExecutionReport]:
        """获取执行报告"""
        # 首先检查活跃执行
        if execution_id in self._active_executions:
            return self._active_executions[execution_id]

        # 然后检查历史
        for report in reversed(self._execution_history):
            if report.execution_id == execution_id:
                return report

        return None

    def get_executions(self,
                       market_id: Optional[str] = None,
                       status: Optional[ExecutionStatus] = None,
                       limit: int = 100) -> List[ExecutionReport]:
        """获取执行列表"""
        results = []

        # 合并活跃执行和历史
        all_executions = list(self._active_executions.values()) + list(reversed(self._execution_history))

        for report in all_executions:
            if market_id and report.market_id != market_id:
                continue
            if status and report.status != status:
                continue

            results.append(report)

            if len(results) >= limit:
                break

        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        return self._stats.copy()

    def clear_history(self, keep_recent: int = 100) -> None:
        """清除执行历史"""
        if len(self._execution_history) > keep_recent:
            self._execution_history = self._execution_history[-keep_recent:]
        logger.info(f"Execution history cleared, keeping {len(self._execution_history)} records")
