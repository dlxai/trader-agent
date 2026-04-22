"""Tests for EventNormalizer."""

from datetime import datetime
from src.trading_engine.event_normalizer import EventNormalizer, NormalizedEvent, EventType


def test_normalizes_activity_trade():
    """Trade events should be normalized to EventType.TRADE."""
    normalizer = EventNormalizer()
    raw_event = {
        "type": "trade",
        "trade_id": "123",
        "market_id": "market_abc",
        "game_id": "game_123",
        "timestamp": "2024-01-01T12:00:00Z",
        "side": "buy",
        "size": 100,
        "price": 0.55,
    }
    result = normalizer.process(raw_event)
    assert isinstance(result, NormalizedEvent)
    assert result.type == EventType.TRADE
    assert result.market_id == "market_abc"
    assert result.game_id == "game_123"
    assert result.payload["side"] == "buy"


def test_normalizes_sports_score():
    """Score events should be normalized to EventType.SCORE."""
    normalizer = EventNormalizer()
    raw_event = {
        "type": "score_update",
        "event_id": "score_456",
        "market_id": "market_abc",
        "game_id": "game_123",
        "timestamp": "2024-01-01T12:00:00Z",
        "home_score": 2,
        "away_score": 1,
    }
    result = normalizer.process(raw_event)
    assert isinstance(result, NormalizedEvent)
    assert result.type == EventType.SCORE
    assert result.payload["home_score"] == 2


def test_normalizes_state_change():
    """State change events should be normalized to EventType.STATE_CHANGE."""
    normalizer = EventNormalizer()
    raw_event = {
        "type": "state_change",
        "market_id": "market_abc",
        "game_id": "game_123",
        "timestamp": "2024-01-01T12:00:00Z",
        "state": {"period": "halftime"},
    }
    result = normalizer.process(raw_event)
    assert isinstance(result, NormalizedEvent)
    assert result.type == EventType.STATE_CHANGE


def test_returns_none_for_unknown_type():
    """Unknown event types should return None."""
    normalizer = EventNormalizer()
    raw_event = {"type": "unknown", "timestamp": datetime.utcnow()}
    result = normalizer.process(raw_event)
    assert result is None
