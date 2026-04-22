"""Layer 5: Score Aggregator - compute EdgeScore, EV_Score, RiskScore."""

from dataclasses import dataclass


@dataclass
class ScoreConfig:
    """Score computation configuration."""
    time_pressure_threshold: float = 0.85
    llm_weight: float = 0.4
    market_deviation_weight: float = 0.6


@dataclass
class CompositeScores:
    """Three core scores."""
    edge_score: float
    ev_score: float
    risk_score: float


class ScoreAggregator:
    """Layer 5: Score Aggregator.

    Computes EdgeScore, EV_Score, RiskScore from factors.
    """

    def __init__(self, config: ScoreConfig = None):
        self.config = config or ScoreConfig()

    def compute_edge_score(
        self,
        net_flow_rate: float,
        strength: float,
        acceleration: float,
        time_pressure: float = 0.0,
    ) -> float:
        """Compute EdgeScore = Direction x Strength x Acceleration.

        Range: [-1, 1]
        """
        # Time decay at high pressure
        if time_pressure > self.config.time_pressure_threshold:
            strength *= 0.5

        # Clamp strength and acceleration to [0, 1]
        strength = max(0.0, min(1.0, abs(strength)))
        acceleration = max(0.0, min(1.0, acceleration))

        # Direction from net_flow_rate
        direction = 1 if net_flow_rate > 0 else (-1 if net_flow_rate < 0 else 0)

        return direction * strength * acceleration

    def compute_ev_score(
        self,
        llm_ev: float,
        market_deviation: float,
    ) -> float:
        """Compute EV_Score = LLM_EV x MarketDeviation.

        Range: [0, 1]
        """
        llm_ev = max(0.0, min(1.0, llm_ev))
        market_deviation = max(0.0, min(1.0, market_deviation))

        return (
            self.config.llm_weight * llm_ev +
            self.config.market_deviation_weight * market_deviation
        )

    def compute_risk_score(
        self,
        volatility: float,
        spread: float,
        time_instability: float,
        latency: float = 0.0,
    ) -> float:
        """Compute RiskScore = max(V, S, T, L).

        Range: [0, 1]
        """
        V = max(0.0, min(1.0, volatility))
        S = max(0.0, min(1.0, spread))
        T = max(0.0, min(1.0, time_instability))
        L = max(0.0, min(1.0, latency))

        return max(V, S, T, L)

    def compute_all_scores(
        self,
        net_flow_rate: float,
        strength: float,
        acceleration: float,
        llm_ev: float,
        market_deviation: float,
        volatility: float,
        spread: float,
        time_instability: float,
        time_pressure: float = 0.0,
        latency: float = 0.0,
    ) -> CompositeScores:
        """Compute all three scores at once."""
        edge = self.compute_edge_score(
            net_flow_rate, strength, acceleration, time_pressure
        )
        ev = self.compute_ev_score(llm_ev, market_deviation)
        risk = self.compute_risk_score(
            volatility, spread, time_instability, latency
        )

        return CompositeScores(edge_score=edge, ev_score=ev, risk_score=risk)
