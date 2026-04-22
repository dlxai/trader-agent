"""Layer 0: Data Integrity - timestamps, dedup, reorder."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, Set
from uuid import UUID, uuid4


@dataclass
class CleanEvent:
    """Output of DataIntegrityLayer."""
    event_id: str
    original_event: dict
    timestamp: datetime
    sequence: int = 0


class DataIntegrityLayer:
    """Layer 0: Data Integrity.

    Responsibilities:
    - Timestamp validation (drop future/stale data)
    - Duplicate removal (by event_id)
    - Order reordering (by timestamp)
    """

    def __init__(
        self,
        max_future_seconds: int = 300,
        max_age_seconds: int = 60,
    ):
        self.max_future = timedelta(seconds=max_future_seconds)
        self.max_age = timedelta(seconds=max_age_seconds)
        self._seen_ids: Set[str] = set()
        self._sequence: int = 0

    async def process(self, event: dict) -> Optional[CleanEvent]:
        """Process raw event through integrity checks.

        Returns None if event should be dropped.
        """
        event_id = event.get("trade_id") or event.get("event_id") or str(uuid4())
        timestamp_str = event.get("timestamp")

        timestamp = self._parse_timestamp(timestamp_str)
        now = datetime.utcnow()

        # Check future timestamp
        if timestamp > now + self.max_future:
            return None  # Drop future data

        # Check stale timestamp
        if now - timestamp > self.max_age:
            return None  # Drop stale data

        # Check duplicate
        if event_id in self._seen_ids:
            return None  # Drop duplicate

        self._seen_ids.add(event_id)
        self._sequence += 1

        return CleanEvent(
            event_id=event_id,
            original_event=event,
            timestamp=timestamp,
            sequence=self._sequence,
        )

    def process_sync(self, event: dict) -> Optional[CleanEvent]:
        """Synchronous version for non-async contexts."""
        event_id = event.get("trade_id") or str(uuid4())
        timestamp_str = event.get("timestamp")

        timestamp = self._parse_timestamp(timestamp_str)
        now = datetime.utcnow()

        if timestamp > now + self.max_future:
            return None
        if now - timestamp > self.max_age:
            return None

        if event_id in self._seen_ids:
            return None

        self._seen_ids.add(event_id)
        self._sequence += 1

        return CleanEvent(
            event_id=event_id,
            original_event=event,
            timestamp=timestamp,
            sequence=self._sequence,
        )

    def _parse_timestamp(self, ts: Any) -> datetime:
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.utcnow()

    def reset(self) -> None:
        """Reset seen IDs and sequence (for testing)."""
        self._seen_ids.clear()
        self._sequence = 0
