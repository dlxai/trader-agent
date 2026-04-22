"""Tests for TemporalBuffer."""

import pytest
import asyncio
from datetime import datetime, timedelta
from src.trading_engine.temporal_buffer import TemporalBuffer, GameBuffer


def test_adds_events_to_timeline():
    """Events should be added to appropriate timeline."""
    buffer = TemporalBuffer()
    event = {
        "market_id": "market_abc",
        "game_id": "game_123",
        "timestamp": datetime.utcnow(),
        "type": "trade",
    }
    asyncio.run(buffer.add(event))

    game_buffer = buffer.get_game_buffer("game_123")
    assert game_buffer is not None
    assert len(game_buffer.trade_timeline) == 1


def test_rolling_window_expiry():
    """Old events should be removed from rolling window."""
    buffer = TemporalBuffer(window_seconds=30)
    old_time = datetime.utcnow() - timedelta(seconds=60)

    event_old = {"market_id": "a", "game_id": "g", "timestamp": old_time, "type": "trade"}
    event_new = {"market_id": "a", "game_id": "g", "timestamp": datetime.utcnow(), "type": "trade"}

    asyncio.run(buffer.add(event_old))
    asyncio.run(buffer.add(event_new))

    game_buffer = buffer.get_game_buffer("g")
    # Old event should have expired from rolling window
    assert len(game_buffer.trade_timeline) == 1


def test_multiple_timelines():
    """Different event types should go to different timelines."""
    buffer = TemporalBuffer()
    trade = {"market_id": "m", "game_id": "g", "timestamp": datetime.utcnow(), "type": "trade"}
    score = {"market_id": "m", "game_id": "g", "timestamp": datetime.utcnow(), "type": "score"}

    asyncio.run(buffer.add(trade))
    asyncio.run(buffer.add(score))

    gb = buffer.get_game_buffer("g")
    assert len(gb.trade_timeline) == 1
    assert len(gb.score_timeline) == 1


def test_get_window_filters_by_time():
    """get_window should only return recent events."""
    from src.trading_engine.temporal_buffer import TimelineEntry

    buffer = TemporalBuffer()
    recent = datetime.utcnow()
    old = datetime.utcnow() - timedelta(seconds=120)

    buffer._buffers["g"] = GameBuffer(game_id="g", market_id="m")
    buffer._buffers["g"].trade_timeline.append(TimelineEntry(timestamp=old, data={}, sequence=1))
    buffer._buffers["g"].trade_timeline.append(TimelineEntry(timestamp=recent, data={}, sequence=2))

    entries = buffer.get_window("g", "trade", seconds=60)
    assert len(entries) == 1
