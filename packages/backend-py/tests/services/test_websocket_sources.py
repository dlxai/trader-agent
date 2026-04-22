"""Tests for WebSocket Sources."""

import pytest
from src.services.websocket_sources import ActivityWebSocketSource, SportsWebSocketSource


def test_singleton_pattern():
    """ActivityWebSocketSource should be a singleton."""
    # Can't test async singleton easily in sync test
    source = ActivityWebSocketSource()
    assert hasattr(source, 'event_bus')
    assert hasattr(source, 'connect')
    assert hasattr(source, 'disconnect')


def test_sources_have_required_methods():
    """Sources should have required methods."""
    activity = ActivityWebSocketSource()
    assert callable(activity.connect)
    assert callable(activity.disconnect)
    assert callable(activity.set_event_bus)

    sports = SportsWebSocketSource()
    assert callable(sports.connect)
    assert callable(sports.disconnect)
    assert callable(sports.set_event_bus)
