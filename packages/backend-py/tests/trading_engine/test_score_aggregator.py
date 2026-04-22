"""Tests for ScoreAggregator."""

import pytest
from src.trading_engine.score_aggregator import ScoreAggregator, ScoreConfig


def test_edge_score_range():
    """EdgeScore should be in range [-1, 1]."""
    agg = ScoreAggregator()
    edge = agg.compute_edge_score(1.0, 0.8, 0.9)
    assert -1 <= edge <= 1


def test_edge_score_calculation():
    """EdgeScore should be Direction x Strength x Acceleration."""
    agg = ScoreAggregator()
    edge = agg.compute_edge_score(1.0, 0.8, 0.9)
    expected = 1.0 * 0.8 * 0.9  # 0.72
    assert abs(edge - expected) < 0.01


def test_edge_score_negative_direction():
    """EdgeScore should be negative for negative flow."""
    agg = ScoreAggregator()
    edge = agg.compute_edge_score(-0.5, 0.8, 0.9)
    assert edge < 0


def test_risk_score_takes_max():
    """RiskScore should take the maximum of all components."""
    agg = ScoreAggregator()
    risk = agg.compute_risk_score(0.3, 0.5, 0.8, 0.2)
    assert risk == 0.8


def test_ev_score_combines_llm_and_market():
    """EV_Score should combine LLM and MarketDeviation."""
    agg = ScoreAggregator()
    ev = agg.compute_ev_score(llm_ev=0.7, market_deviation=0.8)
    expected = 0.4 * 0.7 + 0.6 * 0.8  # 0.76
    assert abs(ev - expected) < 0.01


def test_all_scores_computation():
    """compute_all_scores should return all three scores."""
    agg = ScoreAggregator()
    scores = agg.compute_all_scores(
        net_flow_rate=0.5,
        strength=0.8,
        acceleration=0.9,
        llm_ev=0.7,
        market_deviation=0.6,
        volatility=0.3,
        spread=0.2,
        time_instability=0.4,
    )
    assert hasattr(scores, 'edge_score')
    assert hasattr(scores, 'ev_score')
    assert hasattr(scores, 'risk_score')
