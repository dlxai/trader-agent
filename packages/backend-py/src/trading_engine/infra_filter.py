"""Layer 1: Infra Filter - data quality only, no strategy preferences."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class FilterConfig:
    """Infrastructure filter configuration.

    Only data quality filters - no strategy preferences.
    """
    min_trade_size: float = 10.0
    min_liquidity: float = 1000.0
    max_spread_percent: float = 0.05
    require_live_market: bool = False


class InfraFilter:
    """Layer 1: Infrastructure Filter.

    Filters based on data quality only.
    Strategy preferences (dead_zone, keywords) belong in Strategy layer.
    """

    def __init__(self, config: FilterConfig):
        self.config = config

    def process(self, event: dict) -> Optional[dict]:
        """Process event through infrastructure filters.

        Returns None if event should be dropped.
        """
        # Size filter
        size = event.get("size", 0)
        if size < self.config.min_trade_size:
            return None

        # Liquidity filter
        volume = event.get("volume_24h", 0)
        if volume < self.config.min_liquidity:
            return None

        # Spread filter
        spread = event.get("spread_percent", 0)
        if spread > self.config.max_spread_percent:
            return None

        # Live market filter (optional)
        if self.config.require_live_market:
            status = event.get("match_status", "")
            if status not in ("live", "in_progress"):
                return None

        return event
