"""Tests for InfraFilter."""

from src.trading_engine.infra_filter import InfraFilter, FilterConfig


def test_passes_min_trade_size():
    """Events with size >= min_trade_size should pass."""
    config = FilterConfig(min_trade_size=10)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 50, "volume_24h": 10000, "spread_percent": 0.02}
    result = layer.process(event)
    assert result is not None


def test_drops_small_trade():
    """Events with size < min_trade_size should be dropped."""
    config = FilterConfig(min_trade_size=10)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 5, "volume_24h": 10000}
    result = layer.process(event)
    assert result is None


def test_drops_low_liquidity():
    """Events with volume < min_liquidity should be dropped."""
    config = FilterConfig(min_liquidity=1000)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 100, "volume_24h": 500}
    result = layer.process(event)
    assert result is None


def test_drops_wide_spread():
    """Events with spread > max_spread_percent should be dropped."""
    config = FilterConfig(max_spread_percent=0.05)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 100, "volume_24h": 10000, "spread_percent": 0.10}
    result = layer.process(event)
    assert result is None


def test_passes_without_live_market_check():
    """Events should pass when require_live_market is False."""
    config = FilterConfig(require_live_market=False)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 100, "volume_24h": 10000, "match_status": "closed"}
    result = layer.process(event)
    assert result is not None


def test_drops_non_live_when_required():
    """Events should be dropped when require_live_market is True and status is not live."""
    config = FilterConfig(require_live_market=True)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 100, "volume_24h": 10000, "match_status": "closed"}
    result = layer.process(event)
    assert result is None


def test_passes_live_market_when_required():
    """Events should pass when require_live_market is True and status is live."""
    config = FilterConfig(require_live_market=True)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 100, "volume_24h": 10000, "match_status": "live"}
    result = layer.process(event)
    assert result is not None
