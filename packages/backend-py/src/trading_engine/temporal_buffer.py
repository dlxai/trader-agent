"""Layer 3: Temporal Buffer - rolling windows per game."""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional


@dataclass
class TimelineEntry:
    """Single entry in a timeline."""
    timestamp: datetime
    data: dict
    sequence: int = 0


@dataclass
class GameBuffer:
    """Buffer for a single game with multiple timelines."""
    game_id: str
    market_id: str
    trade_timeline: Deque = field(default_factory=lambda: deque(maxlen=1000))
    score_timeline: Deque = field(default_factory=lambda: deque(maxlen=100))
    event_timeline: Deque = field(default_factory=lambda: deque(maxlen=500))
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_update: datetime = field(default_factory=datetime.utcnow)


class TemporalBuffer:
    """Layer 3: Temporal Buffer.

    Maintains rolling windows per game:
    - trade_timeline: recent trades
    - score_timeline: score updates
    - event_timeline: key events (goals, fouls, etc)

    Auto-expires old entries based on window.
    """

    def __init__(
        self,
        window_seconds: int = 300,
        max_ttl_seconds: int = 3600,
    ):
        self.window = timedelta(seconds=window_seconds)
        self.max_ttl = timedelta(seconds=max_ttl_seconds)
        self._buffers: Dict[str, GameBuffer] = {}
        self._lock = asyncio.Lock()
        self._sequence: int = 0

    async def add(self, event: dict) -> None:
        """Add event to appropriate timeline."""
        game_id = event.get("game_id")
        if not game_id:
            return

        event_type = event.get("type", "trade")
        timestamp = event.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif not isinstance(timestamp, datetime):
            timestamp = datetime.utcnow()

        async with self._lock:
            if game_id not in self._buffers:
                self._buffers[game_id] = GameBuffer(
                    game_id=game_id,
                    market_id=event.get("market_id", ""),
                )

            self._sequence += 1
            entry = TimelineEntry(
                timestamp=timestamp,
                data=event,
                sequence=self._sequence,
            )

            buffer = self._buffers[game_id]
            buffer.last_update = datetime.utcnow()

            if event_type == "trade":
                buffer.trade_timeline.append(entry)
            elif event_type == "score":
                buffer.score_timeline.append(entry)
            else:
                buffer.event_timeline.append(entry)

    def get_game_buffer(self, game_id: str) -> Optional[GameBuffer]:
        """Get buffer for a game."""
        return self._buffers.get(game_id)

    def get_window(
        self,
        game_id: str,
        timeline_type: str,
        seconds: int,
    ) -> List[TimelineEntry]:
        """Get events from timeline within time window."""
        buffer = self._buffers.get(game_id)
        if not buffer:
            return []

        cutoff = datetime.utcnow() - timedelta(seconds=seconds)

        if timeline_type == "trade":
            timeline = buffer.trade_timeline
        elif timeline_type == "score":
            timeline = buffer.score_timeline
        else:
            timeline = buffer.event_timeline

        return [e for e in timeline if e.timestamp >= cutoff]

    async def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = datetime.utcnow()
        cutoff = now - self.max_ttl
        removed = 0

        async with self._lock:
            for game_id, buffer in list(self._buffers.items()):
                if buffer.last_update < cutoff:
                    del self._buffers[game_id]
                    removed += 1
                    continue

                while buffer.trade_timeline and buffer.trade_timeline[0].timestamp < cutoff:
                    buffer.trade_timeline.popleft()
                    removed += 1

        return removed

    def get_all_game_ids(self) -> List[str]:
        """Get all active game IDs."""
        return list(self._buffers.keys())
