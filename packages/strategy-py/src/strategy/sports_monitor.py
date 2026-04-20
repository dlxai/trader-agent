"""
体育市场实时监控与动态止损止盈系统
针对 Polymarket 体育市场的特殊处理
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import aiohttp
import websockets

logger = logging.getLogger(__name__)


class ScoreEventType(Enum):
    """比分事件类型"""
    GOAL = "goal"                     # 进球
    RED_CARD = "red_card"            # 红牌
    YELLOW_CARD = "yellow_card"     # 黄牌
    GAME_END = "game_end"            # 比赛结束
    PERIOD_END = "period_end"       # 节/半场结束
    SCORE_CHANGE = "score_change"    # 比分变化（通用）


@dataclass
class ScoreState:
    """比分状态"""
    home_score: int = 0
    away_score: int = 0
    home_team: str = ""
    away_team: str = ""
    game_status: str = "upcoming"    # upcoming, live, halftime, finished
    current_period: int = 1          # 当前节/半场
    time_remaining: str = ""        # 剩余时间（如 "45:00"）
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class ScoreEvent:
    """比分事件"""
    event_type: ScoreEventType
    timestamp: datetime
    score_before: ScoreState
    score_after: ScoreState
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SportsPositionConfig:
    """体育市场持仓配置"""
    # 动态止损触发条件
    trailing_stop_enabled: bool = True
    trailing_stop_drawdown: float = 0.10      # 价格从高点回撤 10% 触发

    # 比分变化触发条件
    score_change_threshold: int = 1              # 比分变化达到此值时重新评估
    goal_conceded_stop_loss: float = 0.20      # 失球后止损收紧到 20%

    # 时间相关
    late_game_threshold_minutes: int = 10      # 比赛最后10分钟视为"末期"
    late_game_stop_loss: float = 0.05          # 末期止损收紧到 5%

    # 极端情况
    red_card_stop_loss: float = 0.15           # 红牌后止损收紧到 15%
    two_goal_lead_take_profit: float = 0.10    # 领先2球后止盈收紧到 10%


@dataclass
class DynamicStopLossState:
    """动态止损状态"""
    original_stop_loss: float                 # 原始止损阈值
    current_stop_loss: float                  # 当前止损阈值（动态调整）
    highest_price_since_entry: float          # 入场后最高价格
    last_trigger_reason: str = ""            # 上次触发调整的原因
    adjustment_history: List[Dict] = field(default_factory=list)  # 调整历史


class SportsMarketMonitor:
    """
    体育市场实时监控器

    职责：
    1. 订阅 Polymarket 体育比分 WebSocket
    2. 监控持仓比赛的实时比分
    3. 根据比分变化动态调整止损止盈
    4. 在极端情况下触发紧急退出
    """

    def __init__(
        self,
        ws_url: str = "wss://ws.prd.polymarket.com/sports",
        api_key: Optional[str] = None,
        on_score_change: Optional[Callable[[ScoreEvent], None]] = None,
        on_stop_loss_trigger: Optional[Callable[[str, float, str], None]] = None,
    ):
        self.ws_url = ws_url
        self.api_key = api_key
        self.on_score_change = on_score_change
        self.on_stop_loss_trigger = on_stop_loss_trigger

        # WebSocket 连接状态
        self._ws = None
        self._running = False
        self._reconnect_interval = 5
        self._max_reconnect_attempts = 10

        # 比分状态缓存
        self._score_cache: Dict[str, ScoreState] = {}
        self._last_event_time: Dict[str, datetime] = {}

        # 持仓监控映射（market_id -> position_ids）
        self._monitored_positions: Dict[str, List[str]] = {}

        # 动态止损配置
        self._position_configs: Dict[str, SportsPositionConfig] = {}
        self._dynamic_stop_loss: Dict[str, DynamicStopLossState] = {}

        logger.info(f"SportsMarketMonitor initialized (ws_url: {ws_url})")

    # ==================== WebSocket 连接管理 ====================

    async def start(self):
        """启动监控"""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        logger.info("Starting SportsMarketMonitor...")

        # 启动 WebSocket 连接循环
        asyncio.create_task(self._ws_connection_loop())

    async def stop(self):
        """停止监控"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping SportsMarketMonitor...")

        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

    async def _ws_connection_loop(self):
        """WebSocket 连接循环（带自动重连）"""
        reconnect_attempts = 0

        while self._running:
            try:
                logger.debug(f"Connecting to {self.ws_url}...")

                # 建立 WebSocket 连接
                self._ws = await websockets.connect(
                    self.ws_url,
                    extra_headers={"X-API-Key": self.api_key} if self.api_key else None
                )

                reconnect_attempts = 0
                logger.info("WebSocket connected")

                # 发送订阅消息
                await self._subscribe_to_sports_events()

                # 处理消息循环
                await self._ws_message_loop()

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

            # 重连逻辑
            if self._running:
                reconnect_attempts += 1
                if reconnect_attempts > self._max_reconnect_attempts:
                    logger.error("Max reconnection attempts reached")
                    break

                wait_time = min(self._reconnect_interval * reconnect_attempts, 60)
                logger.info(f"Reconnecting in {wait_time}s (attempt {reconnect_attempts})...")
                await asyncio.sleep(wait_time)

    async def _subscribe_to_sports_events(self):
        """订阅体育事件"""
        if not self._ws:
            return

        # 构建订阅消息
        # 注意：具体格式需要根据 Polymarket 文档调整
        subscribe_msg = {
            "type": "subscribe",
            "channels": ["sports_scores", "sports_events"],
            "markets": list(self._monitored_positions.keys()) if self._monitored_positions else []
        }

        try:
            await self._ws.send(json.dumps(subscribe_msg))
            logger.debug(f"Subscribed to sports events: {subscribe_msg}")
        except Exception as e:
            logger.error(f"Error subscribing to sports events: {e}")

    async def _ws_message_loop(self):
        """处理 WebSocket 消息循环"""
        while self._running and self._ws:
            try:
                message = await self._ws.recv()
                await self._handle_ws_message(message)
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")

    async def _handle_ws_message(self, message: str):
        """处理单个 WebSocket 消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "score_update":
                await self._handle_score_update(data)
            elif msg_type == "game_event":
                await self._handle_game_event(data)
            elif msg_type == "market_update":
                await self._handle_market_update(data)
            else:
                logger.debug(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    # ==================== 比分事件处理 ====================

    async def _handle_score_update(self, data: Dict):
        """处理比分更新"""
        try:
            market_id = data.get("market_id")
            new_score = ScoreState(
                home_score=data.get("home_score", 0),
                away_score=data.get("away_score", 0),
                home_team=data.get("home_team", ""),
                away_team=data.get("away_team", ""),
                game_status=data.get("game_status", "live"),
                current_period=data.get("current_period", 1),
                time_remaining=data.get("time_remaining", ""),
                last_updated=datetime.now()
            )

            # 检查是否有持仓监控此市场
            if market_id not in self._monitored_positions:
                return

            # 获取之前的比分
            old_score = self._score_cache.get(market_id)

            # 更新缓存
            self._score_cache[market_id] = new_score

            # 创建比分事件
            if old_score:
                event = ScoreEvent(
                    event_type=self._determine_event_type(old_score, new_score, data),
                    timestamp=datetime.now(),
                    score_before=old_score,
                    score_after=new_score,
                    description=self._generate_event_description(old_score, new_score, data),
                    metadata=data
                )

                # 触发回调
                if self.on_score_change:
                    await self.on_score_change(event)

                # 处理动态止损调整
                await self._handle_score_event_for_stop_loss(market_id, event)

            logger.info(f"Score update for {market_id}: {new_score.home_score}-{new_score.away_score}")

        except Exception as e:
            logger.error(f"Error handling score update: {e}")

    def _determine_event_type(self, old_score: ScoreState, new_score: ScoreState, data: Dict) -> ScoreEventType:
        """确定比分事件类型"""
        # 检查是否进球
        if new_score.home_score > old_score.home_score or new_score.away_score > old_score.away_score:
            return ScoreEventType.GOAL

        # 检查比赛结束
        if new_score.game_status == "finished" and old_score.game_status != "finished":
            return ScoreEventType.GAME_END

        # 检查节/半场结束
        if new_score.current_period > old_score.current_period:
            return ScoreEventType.PERIOD_END

        # 检查红牌（从 metadata 中）
        if data.get("red_card"):
            return ScoreEventType.RED_CARD

        return ScoreEventType.SCORE_CHANGE

    def _generate_event_description(self, old_score: ScoreState, new_score: ScoreState, data: Dict) -> str:
        """生成事件描述"""
        event_type = self._determine_event_type(old_score, new_score, data)

        if event_type == ScoreEventType.GOAL:
            if new_score.home_score > old_score.home_score:
                return f"Goal! {new_score.home_team} scores. Score: {new_score.home_score}-{new_score.away_score}"
            else:
                return f"Goal! {new_score.away_team} scores. Score: {new_score.home_score}-{new_score.away_score}"

        elif event_type == ScoreEventType.RED_CARD:
            team = data.get("team", "")
            return f"Red card shown to {team}"

        elif event_type == ScoreEventType.GAME_END:
            return f"Match ended. Final score: {new_score.home_score}-{new_score.away_score}"

        return f"Score update: {new_score.home_score}-{new_score.away_score}"

    async def _handle_score_event_for_stop_loss(self, market_id: str, event: ScoreEvent):
        """根据比分事件处理动态止损"""
        try:
            # 获取监控此市场的持仓
            position_ids = self._monitored_positions.get(market_id, [])
            if not position_ids:
                return

            for position_id in position_ids:
                config = self._position_configs.get(position_id)
                dynamic_sl = self._dynamic_stop_loss.get(position_id)

                if not config or not dynamic_sl:
                    continue

                # 根据事件类型调整止损
                new_stop_loss = None
                trigger_reason = ""

                if event.event_type == ScoreEventType.GOAL:
                    # 进球事件
                    if self._is_conceded_goal(position_id, event):
                        # 失球方，收紧止损
                        new_stop_loss = config.goal_conceded_stop_loss
                        trigger_reason = f"Goal conceded by opponent, tightening stop loss"
                    else:
                        # 进球方，可以放宽止盈
                        # 这里可以调整止盈逻辑
                        pass

                elif event.event_type == ScoreEventType.RED_CARD:
                    # 红牌事件
                    if self._is_red_card_against(position_id, event):
                        new_stop_loss = config.red_card_stop_loss
                        trigger_reason = f"Red card received, emergency stop loss"

                # 检查是否在比赛末期
                time_info = self._get_time_remaining(event.score_after)
                if time_info and time_info <= config.late_game_threshold_minutes:
                    if self._is_losing_position(position_id, event.score_after):
                        # 末期落后，极度收紧止损
                        new_stop_loss = config.late_game_stop_loss
                        trigger_reason = f"Late game and losing, emergency stop loss"

                # 应用新的止损设置
                if new_stop_loss and new_stop_loss != dynamic_sl.current_stop_loss:
                    await self._adjust_stop_loss(
                        position_id=position_id,
                        new_stop_loss=new_stop_loss,
                        reason=trigger_reason,
                        event=event
                    )

        except Exception as e:
            logger.error(f"Error handling score event for stop loss: {e}")

    def _is_conceded_goal(self, position_id: str, event: ScoreEvent) -> bool:
        """判断是否是持仓方失球"""
        # 根据持仓方向和市场信息判断
        # 这里需要访问持仓的详细信息
        # 简化实现：根据比分变化和市场信息推断
        return False  # 占位实现

    def _is_red_card_against(self, position_id: str, event: ScoreEvent) -> bool:
        """判断是否是持仓方被罚红牌"""
        return False  # 占位实现

    def _get_time_remaining(self, score: ScoreState) -> Optional[int]:
        """获取剩余时间（分钟）"""
        if not score.time_remaining:
            return None
        try:
            # 解析时间格式如 "45:00"
            parts = score.time_remaining.split(":")
            minutes = int(parts[0])
            return minutes
        except:
            return None

    def _is_losing_position(self, position_id: str, score: ScoreState) -> bool:
        """判断持仓是否处于落后状态"""
        # 需要根据持仓方向（YES/NO）和当前比分判断
        # 例如：持仓 YES（主场赢），但主场落后
        return False  # 占位实现

    async def _adjust_stop_loss(
        self,
        position_id: str,
        new_stop_loss: float,
        reason: str,
        event: ScoreEvent
    ):
        """调整止损设置"""
        try:
            dynamic_sl = self._dynamic_stop_loss.get(position_id)
            if not dynamic_sl:
                return

            old_stop_loss = dynamic_sl.current_stop_loss
            dynamic_sl.current_stop_loss = new_stop_loss
            dynamic_sl.last_trigger_reason = reason

            # 记录调整历史
            adjustment = {
                "timestamp": datetime.now().isoformat(),
                "old_stop_loss": old_stop_loss,
                "new_stop_loss": new_stop_loss,
                "reason": reason,
                "score_before": {
                    "home": event.score_before.home_score,
                    "away": event.score_before.away_score
                },
                "score_after": {
                    "home": event.score_after.home_score,
                    "away": event.score_after.away_score
                },
                "event_type": event.event_type.value
            }
            dynamic_sl.adjustment_history.append(adjustment)

            logger.info(
                f"Stop loss adjusted for {position_id}: "
                f"{old_stop_loss:.2%} -> {new_stop_loss:.2%} | Reason: {reason}"
            )

            # 触发回调
            if self.on_stop_loss_trigger:
                await self.on_stop_loss_trigger(position_id, new_stop_loss, reason)

        except Exception as e:
            logger.error(f"Error adjusting stop loss: {e}")

    # ==================== 持仓管理接口 ====================

    def add_position_monitoring(
        self,
        position_id: str,
        market_id: str,
        config: Optional[SportsPositionConfig] = None,
        entry_price: float = 0.0,
        original_stop_loss: float = 0.10
    ):
        """添加持仓监控"""
        # 添加到监控映射
        if market_id not in self._monitored_positions:
            self._monitored_positions[market_id] = []
        if position_id not in self._monitored_positions[market_id]:
            self._monitored_positions[market_id].append(position_id)

        # 设置配置
        self._position_configs[position_id] = config or SportsPositionConfig()

        # 初始化动态止损状态
        self._dynamic_stop_loss[position_id] = DynamicStopLossState(
            original_stop_loss=original_stop_loss,
            current_stop_loss=original_stop_loss,
            highest_price_since_entry=entry_price,
            last_trigger_reason="",
            adjustment_history=[]
        )

        logger.info(f"Added monitoring for position {position_id} on market {market_id}")

    def remove_position_monitoring(self, position_id: str):
        """移除持仓监控"""
        # 从监控映射中移除
        for market_id, positions in list(self._monitored_positions.items()):
            if position_id in positions:
                positions.remove(position_id)
                if not positions:
                    del self._monitored_positions[market_id]
                break

        # 移除配置和状态
        self._position_configs.pop(position_id, None)
        self._dynamic_stop_loss.pop(position_id, None)

        logger.info(f"Removed monitoring for position {position_id}")

    def get_position_stop_loss(self, position_id: str) -> Optional[float]:
        """获取持仓的当前止损设置"""
        dynamic_sl = self._dynamic_stop_loss.get(position_id)
        return dynamic_sl.current_stop_loss if dynamic_sl else None

    def get_position_adjustment_history(self, position_id: str) -> List[Dict]:
        """获取持仓的止损调整历史"""
        dynamic_sl = self._dynamic_stop_loss.get(position_id)
        return dynamic_sl.adjustment_history if dynamic_sl else []


# ==================== 辅助函数 ====================

def calculate_implied_probability(price: float) -> float:
    """根据价格计算隐含概率"""
    # 假设价格为 0.6，隐含概率为 60%
    return price


def calculate_expected_value(
    position_size: float,
    entry_price: float,
    current_price: float,
    outcome_probability: float
) -> float:
    """计算期望收益"""
    # 简化的 EV 计算
    potential_gain = position_size * (1 - entry_price) if outcome_probability > 0.5 else 0
    potential_loss = position_size * entry_price if outcome_probability < 0.5 else 0
    return potential_gain * outcome_probability - potential_loss * (1 - outcome_probability)