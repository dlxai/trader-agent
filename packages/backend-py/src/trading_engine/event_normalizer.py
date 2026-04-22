"""Layer 2: Event Normalizer - unified event format."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class EventType(Enum):
    """Normalized event types."""
    TRADE = "trade"
    SCORE = "score"
    STATE_CHANGE = "state_change"


@dataclass
class NormalizedEvent:
    """Standardized event format from all sources."""
    market_id: str
    game_id: str
    timestamp: datetime
    type: EventType
    payload: Dict[str, Any]


class EventNormalizer:
    """Layer 2: Event Normalizer.

    Converts Activity + Sports data into unified NormalizedEvent format.
    """

    def process(self, raw_event: dict) -> Optional[NormalizedEvent]:
        """Normalize raw event to standard format."""
        event_type = raw_event.get("type", "")

        if event_type == "trade":
            return self._normalize_trade(raw_event)
        elif event_type in ("score_update", "score"):
            return self._normalize_score(raw_event)
        elif event_type == "state_change":
            return self._normalize_state(raw_event)
        else:
            return None

    def _normalize_trade(self, raw: dict) -> NormalizedEvent:
        timestamp = self._parse_timestamp(raw.get("timestamp"))
        return NormalizedEvent(
            market_id=raw.get("market_id", ""),
            game_id=raw.get("game_id", ""),
            timestamp=timestamp,
            type=EventType.TRADE,
            payload={
                "trade_id": raw.get("trade_id"),
                "side": raw.get("side"),
                "size": raw.get("size"),
                "price": raw.get("price"),
                "volume_24h": raw.get("volume_24h"),
                "address": raw.get("address"),
            },
        )

    def _normalize_score(self, raw: dict) -> NormalizedEvent:
        timestamp = self._parse_timestamp(raw.get("timestamp"))
        return NormalizedEvent(
            market_id=raw.get("market_id", ""),
            game_id=raw.get("game_id", ""),
            timestamp=timestamp,
            type=EventType.SCORE,
            payload={
                "home_score": raw.get("home_score"),
                "away_score": raw.get("away_score"),
                "period": raw.get("period"),
                "event_type": raw.get("event_type"),
            },
        )

    def _normalize_state(self, raw: dict) -> NormalizedEvent:
        timestamp = self._parse_timestamp(raw.get("timestamp"))
        return NormalizedEvent(
            market_id=raw.get("market_id", ""),
            game_id=raw.get("game_id", ""),
            timestamp=timestamp,
            type=EventType.STATE_CHANGE,
            payload=raw.get("state", {}),
        )

    def _parse_timestamp(self, ts: Any) -> datetime:
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.utcnow()
