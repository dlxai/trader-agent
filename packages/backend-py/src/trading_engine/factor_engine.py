"""Layer 4: Factor Engine - compute raw and normalized factors."""

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class FlowFactors:
    """Flow factors from trade timeline."""
    net_flow_rate: float = 0.0
    flow_acceleration: float = 0.0
    large_trade_density: float = 0.0
    smart_money_score: float = 0.0
    order_book_imbalance: float = 0.0


@dataclass
class GameStateFactors:
    """Game state factors from score/event timeline."""
    score_gap_change_rate: float = 0.0
    match_time_progress: float = 0.0
    key_event_trigger: int = 0
    attack_pace_index: float = 1.0
    score_deviation: float = 0.0


@dataclass
class CrossFactors:
    """Cross factors from multi-dimension combination."""
    momentum_resonance: float = 0.0
    sentiment_index: float = 0.0


@dataclass
class AllFactors:
    """All computed factors."""
    flow: FlowFactors
    game_state: GameStateFactors
    cross: CrossFactors


class FactorEngine:
    """Layer 4: Factor Engine.

    Computes factors from temporal buffer data.
    """

    def __init__(
        self,
        large_trade_threshold: float = 5000,
    ):
        self.large_threshold = large_trade_threshold

    def compute_all_factors(
        self,
        trade_window: List[dict],
        score_window: List[dict],
        event_window: List[dict],
    ) -> AllFactors:
        """Compute all factor categories."""
        flow = self.compute_flow_factors(trade_window)
        game_state = self.compute_game_state_factors(score_window, event_window)
        cross = self.compute_cross_factors(flow, game_state)

        return AllFactors(flow=flow, game_state=game_state, cross=cross)

    def compute_flow_factors(self, trades: List[dict]) -> FlowFactors:
        """Compute flow factors from trade list."""
        if not trades:
            return FlowFactors()

        buy_volume = sum(t.get("size", 0) for t in trades if t.get("side") == "buy")
        sell_volume = sum(t.get("size", 0) for t in trades if t.get("side") == "sell")
        total_volume = buy_volume + sell_volume

        net_flow_rate = (buy_volume - sell_volume) / max(total_volume, 1)

        # Large trade density
        large_trades = [t for t in trades if t.get("size", 0) >= self.large_threshold]
        large_trade_density = len(large_trades) / max(len(trades), 1)

        # Smart money score (simplified)
        smart_money_score = large_trade_density

        return FlowFactors(
            net_flow_rate=net_flow_rate,
            flow_acceleration=0.0,  # Computed with historical comparison
            large_trade_density=large_trade_density,
            smart_money_score=smart_money_score,
            order_book_imbalance=0.0,
        )

    def compute_game_state_factors(
        self,
        scores: List[dict],
        events: List[dict],
    ) -> GameStateFactors:
        """Compute game state factors."""
        if not scores:
            return GameStateFactors()

        # Score gap change rate
        latest = scores[-1] if scores else {}
        initial = scores[0] if scores else {}

        home_now = latest.get("home_score", 0)
        away_now = latest.get("away_score", 0)
        gap_now = home_now - away_now

        home_start = initial.get("home_score", 0)
        away_start = initial.get("away_score", 0)
        gap_start = home_start - away_start

        if gap_start != 0:
            score_gap_change = (gap_now - gap_start) / abs(gap_start)
        else:
            score_gap_change = 0.0 if gap_now == 0 else (1 if gap_now > 0 else -1)

        # Key event trigger
        key_event_trigger = 1 if events and any(e.get("is_key") for e in events) else 0

        return GameStateFactors(
            score_gap_change_rate=score_gap_change,
            match_time_progress=0.5,  # Would need match start/end times
            key_event_trigger=key_event_trigger,
            attack_pace_index=1.0,
            score_deviation=0.0,
        )

    def compute_cross_factors(
        self,
        flow: FlowFactors,
        game_state: GameStateFactors,
    ) -> CrossFactors:
        """Compute cross factors."""
        # Momentum resonance
        flow_dir = 1 if flow.net_flow_rate > 0 else (-1 if flow.net_flow_rate < 0 else 0)
        score_dir = 1 if game_state.score_gap_change_rate > 0 else (
            -1 if game_state.score_gap_change_rate < 0 else 0
        )
        momentum_resonance = flow_dir * score_dir

        # Sentiment index
        sentiment = (
            0.25 * flow.net_flow_rate +
            0.25 * game_state.score_gap_change_rate +
            0.2 * flow.large_trade_density +
            0.3 * momentum_resonance
        )

        return CrossFactors(
            momentum_resonance=momentum_resonance,
            sentiment_index=sentiment,
        )
