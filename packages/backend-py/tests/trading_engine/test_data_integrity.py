"""Tests for DataIntegrityLayer."""

import pytest
from datetime import datetime, timedelta
from src.trading_engine.data_integrity import DataIntegrityLayer


def test_timestamp_validation_drops_future_data():
    """Future timestamps should be dropped."""
    layer = DataIntegrityLayer(max_future_seconds=300)
    layer.reset()
    event = {
        "trade_id": "123",
        "timestamp": datetime.utcnow() + timedelta(minutes=10),
        "size": 100,
        "price": 0.5
    }
    result = layer.process_sync(event)
    assert result is None  # Dropped


def test_timestamp_validation_drops_stale_data():
    """Stale timestamps should be dropped."""
    layer = DataIntegrityLayer(max_age_seconds=60)
    layer.reset()
    event = {
        "trade_id": "123",
        "timestamp": datetime.utcnow() - timedelta(minutes=5),
        "size": 100,
        "price": 0.5
    }
    result = layer.process_sync(event)
    assert result is None  # Dropped


def test_duplicate_removal():
    """Duplicate events should be dropped."""
    layer = DataIntegrityLayer()
    layer.reset()
    event = {"trade_id": "123", "timestamp": datetime.utcnow(), "size": 100}
    first = layer.process_sync(event)
    second = layer.process_sync(event)
    assert first is not None
    assert second is None  # Duplicate dropped


def test_passes_valid_event():
    """Valid events should pass through."""
    layer = DataIntegrityLayer()
    layer.reset()
    event = {
        "trade_id": "123",
        "timestamp": datetime.utcnow(),
        "size": 100,
        "price": 0.5
    }
    result = layer.process_sync(event)
    assert result is not None
    assert result.event_id == "123"
    assert result.original_event == event


def test_generates_event_id_if_missing():
    """Events without ID should get a generated one."""
    layer = DataIntegrityLayer()
    layer.reset()
    event = {"timestamp": datetime.utcnow(), "size": 100}
    result = layer.process_sync(event)
    assert result is not None
    assert result.event_id is not None


def test_sequence_increments():
    """Sequence should increment for each valid event."""
    layer = DataIntegrityLayer()
    layer.reset()
    events = [
        {"trade_id": "1", "timestamp": datetime.utcnow()},
        {"trade_id": "2", "timestamp": datetime.utcnow()},
        {"trade_id": "3", "timestamp": datetime.utcnow()},
    ]
    results = [layer.process_sync(e) for e in events]
    assert all(r is not None for r in results)
    assert results[0].sequence == 1
    assert results[1].sequence == 2
    assert results[2].sequence == 3
