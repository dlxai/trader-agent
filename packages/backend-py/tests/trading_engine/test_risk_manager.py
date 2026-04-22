"""Tests for RiskManager."""

import pytest
from src.trading_engine.risk_manager import RiskManager, RiskConfig


def test_rejects_low_confidence():
    """Signals with confidence below threshold should be rejected."""
    config = RiskConfig(min_confidence=0.6)
    manager = RiskManager(config)

    signal = {"confidence": 0.4, "market_id": "m1", "size": 100}
    result = manager.approve(signal)
    assert result.approved is False
    assert "confidence" in result.reason


def test_rejects_cooldown_market():
    """Markets in cooldown should be rejected."""
    config = RiskConfig(cooldown_seconds=30)
    manager = RiskManager(config)

    signal = {"confidence": 0.8, "market_id": "m1", "size": 100}
    result1 = manager.approve(signal)
    assert result1.approved is True

    # Second approval should be rejected (cooldown)
    result2 = manager.approve(signal)
    assert result2.approved is False
    assert "cooldown" in result2.reason


def test_rejects_exposure_limit():
    """Exceeding exposure limit should be rejected."""
    config = RiskConfig(max_total_exposure=500)
    manager = RiskManager(config)

    manager._current_exposure = 450

    signal = {"confidence": 0.8, "market_id": "m2", "size": 100}
    result = manager.approve(signal)
    assert result.approved is False
    assert "exposure" in result.reason


def test_approves_valid_signal():
    """Valid signals should be approved."""
    manager = RiskManager()
    signal = {"confidence": 0.8, "market_id": "m1", "size": 100}
    result = manager.approve(signal)
    assert result.approved is True
    assert result.order_id is not None


def test_on_fill_updates_exposure():
    """on_fill should update current exposure."""
    manager = RiskManager()
    initial_exposure = manager.get_exposure()

    manager.on_fill({"market_id": "m1", "size": 100, "price": 0.5, "side": "yes"})

    assert manager.get_exposure() > initial_exposure
