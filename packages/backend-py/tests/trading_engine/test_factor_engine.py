"""Tests for FactorEngine."""

import pytest
from src.trading_engine.factor_engine import FactorEngine, FlowFactors


def test_calculates_net_flow_rate():
    """Net flow rate should be calculated correctly."""
    engine = FactorEngine()
    trades = [
        {"side": "buy", "size": 100, "price": 0.5},
        {"side": "sell", "size": 50, "price": 0.5},
        {"side": "buy", "size": 100, "price": 0.5},
    ]
    flow = engine.compute_flow_factors(trades)
    expected = (200 - 50) / (200 + 50)  # 0.6
    assert abs(flow.net_flow_rate - expected) < 0.01


def test_calculates_large_trade_density():
    """Large trade density should be calculated correctly."""
    engine = FactorEngine(large_trade_threshold=5000)
    trades = [
        {"side": "buy", "size": 10000},  # large
        {"side": "buy", "size": 100},  # small
        {"side": "buy", "size": 8000},  # large
    ]
    flow = engine.compute_flow_factors(trades)
    assert abs(flow.large_trade_density - 2/3) < 0.01


def test_empty_trades_returns_zeros():
    """Empty trades should return zero factors."""
    engine = FactorEngine()
    flow = engine.compute_flow_factors([])
    assert flow.net_flow_rate == 0
    assert flow.large_trade_density == 0


def test_all_factors_composition():
    """compute_all_factors should return all factor types."""
    engine = FactorEngine()
    trades = [{"side": "buy", "size": 100}]
    scores = [{"home_score": 2, "away_score": 1}]
    all_factors = engine.compute_all_factors(trades, scores, [])
    assert hasattr(all_factors, "flow")
    assert hasattr(all_factors, "game_state")
    assert hasattr(all_factors, "cross")
