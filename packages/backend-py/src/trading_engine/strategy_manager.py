"""Strategy Manager and Strategy Instance."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Any


class StrategyState(Enum):
    """Strategy lifecycle state."""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class Decision(Enum):
    """Trading decision."""
    BUY_YES = "buy_yes"
    BUY_NO = "buy_no"
    HOLD = "hold"
    EXIT = "exit"
    REJECT = "reject"


@dataclass
class StrategyConfig:
    """Strategy configuration."""
    edge_threshold: float = 0.4
    ev_threshold: float = 0.6
    risk_threshold: float = 0.5
    sustained_count: int = 3
    time_pressure_threshold: float = 0.85
    max_hold_seconds: int = 3600
    min_size: float = 10.0
    max_size: float = 100.0
    llm_cooldown_seconds: int = 5


@dataclass
class StrategyInstance:
    """Single strategy instance with isolated state."""
    strategy_id: str
    config: StrategyConfig

    state: StrategyState = StrategyState.CREATED
    current_position_id: Optional[str] = None
    last_llm_call: datetime = field(default_factory=datetime.utcnow)
    _direction_history: List[float] = field(default_factory=list)
    on_decision: Optional[Callable] = None

    def __post_init__(self):
        if isinstance(self.config, dict):
            self.config = StrategyConfig(**self.config)

    def start(self) -> None:
        if self.state not in (StrategyState.CREATED, StrategyState.STOPPED, StrategyState.PAUSED):
            return
        self.state = StrategyState.RUNNING

    def stop(self) -> None:
        if self.state == StrategyState.RUNNING:
            self.state = StrategyState.STOPPED

    def pause(self) -> None:
        if self.state == StrategyState.RUNNING:
            self.state = StrategyState.PAUSED

    def resume(self) -> None:
        if self.state == StrategyState.PAUSED:
            self.state = StrategyState.RUNNING

    def should_trigger_llm(self) -> bool:
        elapsed = (datetime.utcnow() - self.last_llm_call).total_seconds()
        return elapsed >= self.config.llm_cooldown_seconds

    def record_direction(self, edge_score: float) -> bool:
        self._direction_history.append(edge_score)

        max_len = self.config.sustained_count * 2
        if len(self._direction_history) > max_len:
            self._direction_history = self._direction_history[-max_len:]

        if len(self._direction_history) < self.config.sustained_count:
            return False

        recent = self._direction_history[-self.config.sustained_count:]
        return all(d > 0.1 for d in recent) or all(d < -0.1 for d in recent)

    def decide(
        self,
        edge_score: float,
        ev_score: float,
        risk_score: float,
        time_pressure: float = 0.0,
    ) -> Decision:
        if self.state != StrategyState.RUNNING:
            return Decision.HOLD

        if risk_score > 0.8:
            return Decision.REJECT

        sustained = self.record_direction(edge_score)
        if not sustained and abs(edge_score) > self.config.edge_threshold:
            return Decision.HOLD

        if abs(edge_score) > self.config.edge_threshold:
            if ev_score > self.config.ev_threshold:
                if risk_score < self.config.risk_threshold:
                    if edge_score > 0:
                        return Decision.BUY_YES
                    else:
                        return Decision.BUY_NO

        return Decision.HOLD


class StrategyManager:
    """Strategy Manager.

    Manages strategy instances lifecycle.
    """

    def __init__(self, event_bus=None):
        self._strategies: Dict[str, StrategyInstance] = {}
        self._event_bus = event_bus

    def create_strategy(
        self,
        strategy_id: str,
        config: Dict[str, Any],
    ) -> StrategyInstance:
        strategy_config = StrategyConfig(**config)
        strategy = StrategyInstance(
            strategy_id=strategy_id,
            config=strategy_config,
        )
        self._strategies[strategy_id] = strategy
        return strategy

    def get(self, strategy_id: str) -> Optional[StrategyInstance]:
        return self._strategies.get(strategy_id)

    def start_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        strategy.start()
        return True

    def stop_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        strategy.stop()
        return True

    def pause_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        strategy.pause()
        return True

    def resume_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        strategy.resume()
        return True

    def remove_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.pop(strategy_id, None)
        return strategy is not None

    def get_all_strategies(self) -> List[StrategyInstance]:
        return list(self._strategies.values())

    def get_running_strategies(self) -> List[StrategyInstance]:
        return [s for s in self._strategies.values() if s.state == StrategyState.RUNNING]
