"""Tests for StrategyManager and StrategyInstance."""

import pytest
from src.trading_engine.strategy_manager import StrategyManager, StrategyInstance, StrategyState, Decision


def test_strategy_state_transitions():
    """Strategy should transition states correctly."""
    strategy = StrategyInstance(strategy_id="s1", config={})
    assert strategy.state == StrategyState.CREATED

    strategy.start()
    assert strategy.state == StrategyState.RUNNING

    strategy.pause()
    assert strategy.state == StrategyState.PAUSED

    strategy.resume()
    assert strategy.state == StrategyState.RUNNING

    strategy.stop()
    assert strategy.state == StrategyState.STOPPED


def test_manager_creates_and_registers():
    """Manager should create and register strategies."""
    manager = StrategyManager()
    strategy = manager.create_strategy(strategy_id="s1", config={})

    assert strategy is not None
    assert manager.get("s1") == strategy


def test_manager_start_stop():
    """Manager should start and stop strategies."""
    manager = StrategyManager()
    manager.create_strategy(strategy_id="s1", config={})

    assert manager.get("s1").state == StrategyState.CREATED

    manager.start_strategy("s1")
    assert manager.get("s1").state == StrategyState.RUNNING

    manager.stop_strategy("s1")
    assert manager.get("s1").state == StrategyState.STOPPED


def test_decision_hold_when_not_running():
    """Strategy should return HOLD when not RUNNING."""
    strategy = StrategyInstance(strategy_id="s1", config={})
    strategy.state = StrategyState.PAUSED

    decision = strategy.decide(0.5, 0.7, 0.3)
    assert decision == Decision.HOLD


def test_decision_reject_high_risk():
    """Strategy should REJECT high risk signals."""
    strategy = StrategyInstance(strategy_id="s1", config={"risk_threshold": 0.5})
    strategy.state = StrategyState.RUNNING

    # Risk > 0.8 should REJECT
    decision = strategy.decide(0.5, 0.7, 0.9)
    assert decision == Decision.REJECT


def test_decision_buy_yes():
    """Strategy should BUY_YES when all conditions met."""
    strategy = StrategyInstance(
        strategy_id="s1",
        config={"edge_threshold": 0.4, "ev_threshold": 0.6, "risk_threshold": 0.5},
    )
    strategy.state = StrategyState.RUNNING

    # Set direction history to pass sustained check
    strategy._direction_history = [0.5, 0.5, 0.5]

    decision = strategy.decide(0.6, 0.7, 0.3)
    assert decision == Decision.BUY_YES
