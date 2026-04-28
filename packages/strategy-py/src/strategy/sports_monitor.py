"""
体育市场实时监控与动态止损止盈系统
针对 Polymarket 体育市场的特殊处理
"""

import asyncio
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import urlparse

import websocket

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
    # 持仓方向 (yes/no)
    side: str = "yes"  # "yes" = 押事件发生（如主队赢）, "no" = 押事件不发生

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
        ws_url: str = "wss://sports-api.polymarket.com/ws",
        api_key: Optional[str] = None,
        proxy_url: Optional[str] = None,
        on_score_change: Optional[Callable[[ScoreEvent], None]] = None,
        on_stop_loss_trigger: Optional[Callable[[str, float, str], None]] = None,
    ):
        self.ws_url = ws_url
        self.api_key = api_key
        self.proxy_url = proxy_url
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

        # 持仓监控映射（market_id / game_id -> position_ids）
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
        self._event_loop = asyncio.get_event_loop()
        logger.info("Starting SportsMarketMonitor...")

        self._ws_thread = threading.Thread(target=self._ws_run_loop, daemon=True)
        self._ws_thread.start()

    async def stop(self):
        """停止监控"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping SportsMarketMonitor...")

        if self._ws:
            try:
                await asyncio.to_thread(self._ws.close)
            except Exception as e:
                logger.error("Error closing WebSocket: %s", e)

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=3)

        logger.info("SportsMarketMonitor stopped")

    def _ws_run_loop(self):
        """在线程中运行 WebSocket 连接与重连"""
        reconnect_attempts = 0
        while self._running:
            try:
                logger.debug("Connecting to %s...", self.ws_url)
                kwargs = {}
                if self.proxy_url:
                    parsed = urlparse(self.proxy_url)
                    kwargs["http_proxy_host"] = parsed.hostname
                    kwargs["http_proxy_port"] = parsed.port or 7890
                    kwargs["proxy_type"] = "http"
                    logger.info("SportsMonitor using proxy: %s", self.proxy_url)

                self._ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_close=self._on_close,
                    on_error=self._on_error,
                )
                self._ws.run_forever(**kwargs)
            except Exception as e:
                logger.error("SportsMonitor run_forever error: %s", e)

            if not self._running:
                break

            reconnect_attempts += 1
            wait_time = min(5 * reconnect_attempts, 60)
            logger.info("SportsMonitor reconnecting in %ds (attempt %d)...", wait_time, reconnect_attempts)
            time.sleep(wait_time)

    def _on_open(self, ws):
        logger.info("SportsMonitor WebSocket connected")
        if "sports-api" not in self.ws_url:
            try:
                subscribe_msg = {
                    "type": "subscribe",
                    "channels": ["sports_scores", "sports_events"],
                    "markets": list(self._monitored_positions.keys()) if self._monitored_positions else []
                }
                ws.send(json.dumps(subscribe_msg))
                logger.debug("Subscribed to sports events")
            except Exception as e:
                logger.error("Error subscribing to sports events: %s", e)

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            if isinstance(data, list):
                return
            if self._event_loop and self._event_loop.is_running():
                asyncio.run_coroutine_threadsafe(self._handle_ws_message(data), self._event_loop)
            else:
                logger.warning("No running event loop to handle sports message")
        except Exception as e:
            logger.error("Error scheduling message handler: %s", e)

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info("SportsMonitor WebSocket closed: %s %s", close_status_code, close_msg)

    def _on_error(self, ws, error):
        logger.error("SportsMonitor WebSocket error: %s", error)

    async def _handle_ws_message(self, data: Dict):
        """处理单个 WebSocket 消息"""
        try:
            msg_type = data.get("type", "")

            # Real sports-api format has no 'type' but has gameId + eventState
            if "gameId" in data and "eventState" in data:
                await self._handle_score_update(data)
                return

            if msg_type == "score_update":
                await self._handle_score_update(data)
            elif msg_type == "game_event":
                await self._handle_game_event(data)
            elif msg_type == "market_update":
                await self._handle_market_update(data)
            else:
                logger.debug("Unknown message type: %s", msg_type)

        except Exception as e:
            logger.error("Error processing WebSocket message: %s", e)

    # ==================== 比分事件处理 ====================

    async def _handle_score_update(self, data: Dict):
        """处理比分更新（适配真实 sports-api 数据格式）"""
        try:
            # Real API uses gameId; legacy code used market_id
            game_id = data.get("gameId")
            market_id = data.get("market_id") or (str(game_id) if game_id is not None else None)
            if market_id is None:
                return

            # Parse score string like "1-2" or "49-59"
            score_str = data.get("score", "")
            event_state = data.get("eventState", {}) or {}
            if not score_str and isinstance(event_state, dict):
                score_str = event_state.get("score", "")

            home_score = 0
            away_score = 0
            if isinstance(score_str, str) and "-" in score_str:
                parts = score_str.split("-")
                if len(parts) >= 2:
                    try:
                        home_score = int(parts[0].strip())
                        away_score = int(parts[1].strip())
                    except ValueError:
                        pass

            # Determine game status from real API fields
            status = data.get("status", "live")
            if isinstance(event_state, dict):
                if event_state.get("ended"):
                    status = "finished"
                elif event_state.get("live") and status not in ("finished", "halftime"):
                    status = "live"

            new_score = ScoreState(
                home_score=home_score,
                away_score=away_score,
                home_team=data.get("homeTeam", ""),
                away_team=data.get("awayTeam", ""),
                game_status=status,
                current_period=data.get("period", ""),
                time_remaining=event_state.get("elapsed", "") if isinstance(event_state, dict) else "",
                last_updated=datetime.now()
            )

            # 获取之前的比分
            old_score = self._score_cache.get(market_id)

            # 更新缓存（所有市场都缓存，不只持仓）
            self._score_cache[market_id] = new_score

            # 检查是否有持仓监控此市场（支持 market_id 或 game_id 作为 key）
            position_ids = self._monitored_positions.get(market_id, [])
            if not position_ids and game_id is not None:
                position_ids = self._monitored_positions.get(str(game_id), [])

            logger.debug(
                f"Score update for {market_id}: positions={position_ids}, "
                f"score={new_score.home_score}-{new_score.away_score}"
            )

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

                # 处理动态止损调整（仅针对持仓）
                if position_ids:
                    await self._handle_score_event_for_stop_loss(market_id, event)

            logger.info(
                f"Score update for {market_id} ({new_score.home_team} vs {new_score.away_team}): "
                f"{new_score.home_score}-{new_score.away_score} | status={new_score.game_status}"
            )

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
        """判断是否是持仓方失球

        逻辑：
        - side=YES（押主队赢/事件发生）: 对手进球 = 失球
        - side=NO（押主队输/事件不发生）: 主队进球 = 对持仓有利（反向判断）
        """
        config = self._position_configs.get(position_id)
        if not config:
            return False

        side = config.side.lower()

        # 判断进球的是哪一方
        home_scored = event.score_after.home_score > event.score_before.home_score
        away_scored = event.score_after.away_score > event.score_before.away_score

        if side == "yes":
            # 押主队赢/事件发生: 对手进球才算失球
            # Polymarket 体育市场 YES = 事件发生（如"主队赢"）
            # 如果是主队市场，away_scored = 对手进球 = 失球
            return away_scored
        else:  # side == "no"
            # 押主队输/事件不发生: 主队进球算失球
            return home_scored

    def _is_red_card_against(self, position_id: str, event: ScoreEvent) -> bool:
        """判断是否是持仓方被罚红牌

        逻辑：
        - side=YES: 如果红牌是给主队（away_scored 时主队被罚 = 不利）
        - side=NO: 如果红牌是给客队（home_scored 时客队被罚 = 不利）
        """
        config = self._position_configs.get(position_id)
        if not config:
            return False

        # 从 event.metadata 中获取红牌信息
        metadata = event.metadata or {}
        red_card_team = metadata.get("red_card_team", "")

        # 如果没有明确 team 信息，根据进球方向推断
        # 一般情况下：先进球方可能在之后吃到红牌
        if not red_card_team:
            # 通过 metadata 中的 team 字段判断
            red_card_team = metadata.get("team", "")

        if not red_card_team:
            # 无法判断，保守返回 False
            return False

        side = config.side.lower()
        red_card_team_lower = red_card_team.lower()

        # 判断主队还是客队被罚
        # 假设 red_card_team 包含 "home" 或 "away" 的标识
        is_home_team = "home" in red_card_team_lower and "away" not in red_card_team_lower
        is_away_team = "away" in red_card_team_lower

        if side == "yes":
            # 押主队赢: 主队被罚红牌 = 不利
            return is_home_team
        else:  # side == "no"
            # 押主队输: 客队被罚红牌 = 不利
            return is_away_team

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
        """判断持仓是否处于落后状态

        逻辑：
        - side=YES（押主队赢）: 主队落后 → True（持仓亏损）
        - side=NO（押主队输）: 主队领先 → True（持仓亏损）
        """
        config = self._position_configs.get(position_id)
        if not config:
            return False

        side = config.side.lower()

        if side == "yes":
            # 押主队赢: 主队落后则持仓亏损
            return score.home_score < score.away_score
        else:  # side == "no"
            # 押主队输: 主队领先则持仓亏损
            return score.home_score > score.away_score

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
        game_id: Optional[str] = None,
        config: Optional[SportsPositionConfig] = None,
        entry_price: float = 0.0,
        original_stop_loss: float = 0.10,
        side: str = "yes"
    ):
        """添加持仓监控

        Args:
            position_id: 持仓ID
            market_id: Polymarket 市场ID
            game_id: 体育比赛 gameId（WS 消息中的 gameId，用于关联比分推送）
            config: 体育持仓配置
            entry_price: 入场价格
            original_stop_loss: 原始止损比例
            side: 持仓方向 ("yes" 或 "no")
        """
        # 添加到监控映射（同时支持 market_id 和 game_id 作为 key）
        for key in [market_id, game_id]:
            if key:
                if key not in self._monitored_positions:
                    self._monitored_positions[key] = []
                if position_id not in self._monitored_positions[key]:
                    self._monitored_positions[key].append(position_id)

        # 设置配置（传入 side）
        if config is None:
            config = SportsPositionConfig(side=side)
        else:
            config.side = side
        self._position_configs[position_id] = config

        # 初始化动态止损状态
        self._dynamic_stop_loss[position_id] = DynamicStopLossState(
            original_stop_loss=original_stop_loss,
            current_stop_loss=original_stop_loss,
            highest_price_since_entry=entry_price,
            last_trigger_reason="",
            adjustment_history=[]
        )

        logger.info(
            f"Added monitoring for position {position_id} on market {market_id}"
            f" (game_id={game_id}, side={side})"
        )

    def remove_position_monitoring(self, position_id: str):
        """移除持仓监控"""
        # 从监控映射中移除（所有 key）
        for key, positions in list(self._monitored_positions.items()):
            if position_id in positions:
                positions.remove(position_id)
                if not positions:
                    del self._monitored_positions[key]

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

    def get_sports_signal(self, market_id: str) -> Optional[Dict[str, Any]]:
        """从缓存的比分数据生成交易信号，用于开仓信号层。

        Returns:
            dict with keys:
                - strength: "strong" | "moderate" | "weak"
                - direction: "buy" | "sell" | "neutral"
                - reason: str
                - score_state: dict
        """
        score = self._score_cache.get(market_id)
        if not score:
            return None

        if score.game_status != "live":
            return None

        time_remaining = self._get_time_remaining(score)
        if time_remaining is None:
            time_remaining = 45

        signal: Dict[str, Any] = {
            "strength": "weak",
            "direction": "neutral",
            "reason": "",
            "score_state": {
                "home_score": score.home_score,
                "away_score": score.away_score,
                "game_status": score.game_status,
                "time_remaining": time_remaining,
            },
        }

        score_diff = abs(score.home_score - score.away_score)

        # Late game clear leader -> strong signal
        # Note: time_remaining is approximate (may not include extra time)
        if time_remaining <= 15 and score_diff >= 1:
            signal["strength"] = "strong"
            signal["direction"] = "buy" if score.home_score > score.away_score else "sell"
            signal["reason"] = (
                f"Late game (~{time_remaining}m remaining) with {score_diff} goal lead"
            )
        # Dominating lead (>=2 goals) -> strong signal
        elif score_diff >= 2:
            signal["strength"] = "strong"
            signal["direction"] = "buy" if score.home_score > score.away_score else "sell"
            signal["reason"] = (
                f"Dominating lead {score.home_score}-{score.away_score}"
            )
        # Single goal lead -> moderate signal
        elif score_diff == 1:
            signal["strength"] = "moderate"
            signal["direction"] = "buy" if score.home_score > score.away_score else "sell"
            signal["reason"] = (
                f"Single goal lead {score.home_score}-{score.away_score}"
            )
        else:
            signal["reason"] = f"Tight game {score.home_score}-{score.away_score}"

        return signal


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