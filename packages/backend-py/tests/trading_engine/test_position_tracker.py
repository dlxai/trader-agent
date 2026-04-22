"""Tests for PositionTracker."""

import pytest
from datetime import datetime
from decimal import Decimal
from src.trading_engine.position_tracker import PositionTracker, Position, PositionStatus


def test_add_position():
    """Positions should be addable and retrievable."""
    tracker = PositionTracker()
    position = Position(
        position_id="pos_1",
        market_id="market_abc",
        token_id="token_123",
        strategy_id="strat_1",
        side="yes",
        size=Decimal("100"),
        entry_price=Decimal("0.55"),
    )

    tracker.add(position)
    assert tracker.get("pos_1") == position


def test_get_by_token():
    """Positions should be retrievable by token_id."""
    tracker = PositionTracker()
    position = Position(
        position_id="pos_1",
        market_id="market_abc",
        token_id="token_123",
        strategy_id="strat_1",
        side="yes",
        size=Decimal("100"),
        entry_price=Decimal("0.55"),
    )
    tracker.add(position)

    positions = tracker.get_by_token("token_123")
    assert len(positions) == 1
    assert positions[0].position_id == "pos_1"


def test_cannot_close_nonexistent():
    """Closing nonexistent position should return False."""
    tracker = PositionTracker()
    result = tracker.close("nonexistent", "stop_loss")
    assert result is False


def test_status_transition_validation():
    """Invalid status transitions should be rejected."""
    tracker = PositionTracker()
    position = Position(
        position_id="pos_1",
        market_id="market_abc",
        token_id="token_123",
        strategy_id="strat_1",
        side="yes",
        size=Decimal("100"),
        entry_price=Decimal("0.55"),
        status=PositionStatus.OPEN,
    )
    tracker.add(position)

    # OPEN -> CLOSING is valid
    result = tracker.update_status("pos_1", PositionStatus.CLOSING)
    assert result is True

    # CLOSING -> OPEN is invalid
    result = tracker.update_status("pos_1", PositionStatus.OPEN)
    assert result is False


def test_get_all_open():
    """get_all_open should only return OPEN positions."""
    tracker = PositionTracker()

    pos1 = Position(
        position_id="pos_1", market_id="m1", token_id="t1",
        strategy_id="s1", side="yes", size=Decimal("100"), entry_price=Decimal("0.5"),
        status=PositionStatus.OPEN,
    )
    pos2 = Position(
        position_id="pos_2", market_id="m2", token_id="t2",
        strategy_id="s1", side="no", size=Decimal("50"), entry_price=Decimal("0.6"),
        status=PositionStatus.CLOSED,
    )
    tracker.add(pos1)
    tracker.add(pos2)

    open_positions = tracker.get_all_open()
    assert len(open_positions) == 1
    assert open_positions[0].position_id == "pos_1"


def test_stop_loss_price_calculation():
    """stop_loss_price should be calculated correctly."""
    position = Position(
        position_id="pos_1", market_id="m1", token_id="t1",
        strategy_id="s1", side="yes", size=Decimal("100"),
        entry_price=Decimal("0.50"),
        stop_loss_pct=0.1,
    )

    # YES position: stop_loss = entry * (1 - stop_loss_pct)
    expected = Decimal("0.50") * Decimal("0.9")  # 0.45
    assert abs(position.stop_loss_price() - expected) < Decimal("0.001")
