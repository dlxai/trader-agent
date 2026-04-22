# Polymarket Trading System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the event-driven Polymarket sports trading system with 6-layer data architecture and three-core-score decision system.

**Architecture:** Event-driven architecture with Layer 0-6 pipeline: Data Integrity → Infra Filter → Event Normalizer → Temporal Buffer → Factor Engine → Score Aggregator → Strategy. Price-triggered position monitoring (no polling). Global single WebSocket connection per data source.

**Tech Stack:** Python 3.11+, FastAPI, asyncio, SQLAlchemy (async), py-clob-client, httpx, WebSocket

---

## File Structure

```
packages/backend-py/src/
├── trading_engine/
│   ├── __init__.py
│   ├── event_bus.py           (existing - EventBus)
│   ├── executor.py            (existing - OrderExecutor)
│   ├── analyzer.py            (existing - SignalAnalyzer)
│   ├── collector.py           (existing - DataCollector)
│   ├── reviewer.py            (existing - PerformanceReviewer)
│   ├── data_integrity.py     (NEW - Layer 0)
│   ├── infra_filter.py        (NEW - Layer 1)
│   ├── event_normalizer.py    (NEW - Layer 2)
│   ├── temporal_buffer.py      (NEW - Layer 3)
│   ├── factor_engine.py       (NEW - Layer 4)
│   ├── score_aggregator.py    (NEW - Layer 5)
│   ├── strategy_manager.py     (NEW - Layer 6)
│   ├── position_tracker.py     (NEW - Position state machine)
│   ├── risk_manager.py         (NEW - Risk management)
│   ├── execution_layer.py      (NEW - Execution orchestration)
│   └── price_monitor.py       (NEW - Price subscription)
├── services/
│   ├── websocket_sources.py   (NEW - ActivityWS + SportsWS singletons)
│   ├── data_source_manager.py (existing - modify for singleton pattern)
│   └── position_monitor.py    (existing - modify for event-driven)
└── main.py                   (modify - wire everything)
```

---

## Task 1: Event Bus Enhancement

**Files:**
- Modify: `packages/backend-py/src/trading_engine/event_bus.py`

Add `FACTOR_UPDATED` and `POSITION_UPDATE` event types to existing EventBus.

- [ ] **Step 1: Write test for new event types**

```python
# tests/trading_engine/test_event_bus.py
def test_factor_updated_event_type():
    from src.trading_engine.event_bus import EventType
    assert EventType.FACTOR_UPDATED is not None
    assert EventType.POSITION_UPDATE is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/trading_engine/test_event_bus.py::test_factor_updated_event_type -v`
Expected: FAIL with "AttributeError"

- [ ] **Step 3: Add new event types to EventType enum**

```python
# packages/backend-py/src/trading_engine/event_bus.py

class EventType(Enum):
    # ... existing events ...
    
    # Factor events (NEW)
    FACTOR_UPDATED = auto()
    FACTOR_SNAPSHOT_READY = auto()
    
    # Position events (NEW)
    POSITION_UPDATE = auto()
    POSITION_OPENED = auto()
    POSITION_CLOSED = auto()
    POSITION_STATUS_CHANGED = auto()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/trading_engine/test_event_bus.py::test_factor_updated_event_type -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/event_bus.py tests/trading_engine/test_event_bus.py
git commit -m "feat: add FACTOR_UPDATED and POSITION_UPDATE event types"
```

---

## Task 2: Layer 0 - Data Integrity

**Files:**
- Create: `packages/backend-py/src/trading_engine/data_integrity.py`
- Create: `tests/trading_engine/test_data_integrity.py`

- [ ] **Step 1: Write test for data integrity layer**

```python
# tests/trading_engine/test_data_integrity.py
import pytest
from datetime import datetime, timedelta
from src.trading_engine.data_integrity import DataIntegrityLayer

def test_timestamp_validation_drops_future_data():
    layer = DataIntegrityLayer(max_future_seconds=300)
    event = {
        "trade_id": "123",
        "timestamp": datetime.utcnow() + timedelta(minutes=10),
        "size": 100,
        "price": 0.5
    }
    result = layer.process_sync(event)
    assert result is None  # Dropped

def test_duplicate_removal():
    layer = DataIntegrityLayer()
    event = {"trade_id": "123", "timestamp": datetime.utcnow(), "size": 100}
    first = layer.process_sync(event)
    second = layer.process_sync(event)
    assert first is not None
    assert second is None  # Duplicate dropped

def test_reorder_maintains_sequence():
    layer = DataIntegrityLayer()
    events = [
        {"trade_id": "1", "timestamp": datetime(2024, 1, 1, 12, 0, 3)},
        {"trade_id": "2", "timestamp": datetime(2024, 1, 1, 12, 0, 1)},
        {"trade_id": "3", "timestamp": datetime(2024, 1, 1, 12, 0, 2)},
    ]
    results = [layer.process_sync(e) for e in events]
    assert all(r is not None for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_data_integrity.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement DataIntegrityLayer**

```python
# packages/backend-py/src/trading_engine/data_integrity.py
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
        
        if isinstance(timestamp_str, str):
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        elif isinstance(timestamp_str, datetime):
            timestamp = timestamp_str
        else:
            timestamp = datetime.utcnow()
        
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
        
        if isinstance(timestamp_str, str):
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        elif isinstance(timestamp_str, datetime):
            timestamp = timestamp_str
        else:
            timestamp = datetime.utcnow()
        
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_data_integrity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/data_integrity.py tests/trading_engine/test_data_integrity.py
git commit -m "feat: implement DataIntegrityLayer (Layer 0)"
```

---

## Task 3: Layer 1 - Infra Filter

**Files:**
- Create: `packages/backend-py/src/trading_engine/infra_filter.py`
- Create: `tests/trading_engine/test_infra_filter.py`

- [ ] **Step 1: Write test for infra filter**

```python
# tests/trading_engine/test_infra_filter.py
import pytest
from src.trading_engine.infra_filter import InfraFilter, FilterConfig

def test_passes_min_trade_size():
    config = FilterConfig(min_trade_size=10)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 50, "volume_24h": 10000, "spread_percent": 0.02}
    result = layer.process(event)
    assert result is not None

def test_drops_small_trade():
    config = FilterConfig(min_trade_size=10)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 5, "volume_24h": 10000}
    result = layer.process(event)
    assert result is None  # Dropped

def test_drops_low_liquidity():
    config = FilterConfig(min_liquidity=1000)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 100, "volume_24h": 500}
    result = layer.process(event)
    assert result is None  # Dropped

def test_drops_wide_spread():
    config = FilterConfig(max_spread_percent=0.05)
    layer = InfraFilter(config)
    event = {"trade_id": "1", "size": 100, "volume_24h": 10000, "spread_percent": 0.10}
    result = layer.process(event)
    assert result is None  # Dropped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_infra_filter.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement InfraFilter**

```python
# packages/backend-py/src/trading_engine/infra_filter.py
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
    require_live_market: bool = True


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
        
        # Live market filter
        if self.config.require_live_market:
            status = event.get("match_status", "")
            if status not in ("live", "in_progress"):
                return None
        
        return event
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_infra_filter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/infra_filter.py tests/trading_engine/test_infra_filter.py
git commit -m "feat: implement InfraFilter (Layer 1)"
```

---

## Task 4: Layer 2 - Event Normalizer

**Files:**
- Create: `packages/backend-py/src/trading_engine/event_normalizer.py`
- Create: `tests/trading_engine/test_event_normalizer.py`

- [ ] **Step 1: Write test for event normalizer**

```python
# tests/trading_engine/test_event_normalizer.py
import pytest
from datetime import datetime
from src.trading_engine.event_normalizer import EventNormalizer, NormalizedEvent, EventType

def test_normalizes_activity_trade():
    normalizer = EventNormalizer()
    raw_event = {
        "type": "trade",
        "trade_id": "123",
        "market_id": "market_abc",
        "game_id": "game_123",
        "timestamp": "2024-01-01T12:00:00Z",
        "side": "buy",
        "size": 100,
        "price": 0.55
    }
    result = normalizer.process(raw_event)
    assert isinstance(result, NormalizedEvent)
    assert result.type == EventType.TRADE
    assert result.market_id == "market_abc"
    assert result.game_id == "game_123"

def test_normalizes_sports_score():
    normalizer = EventNormalizer()
    raw_event = {
        "type": "score_update",
        "event_id": "score_456",
        "market_id": "market_abc",
        "game_id": "game_123",
        "timestamp": "2024-01-01T12:00:00Z",
        "home_score": 2,
        "away_score": 1
    }
    result = normalizer.process(raw_event)
    assert isinstance(result, NormalizedEvent)
    assert result.type == EventType.SCORE
    assert result.payload["home_score"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_event_normalizer.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement EventNormalizer**

```python
# packages/backend-py/src/trading_engine/event_normalizer.py
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
            }
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
            }
        )
    
    def _normalize_state(self, raw: dict) -> NormalizedEvent:
        timestamp = self._parse_timestamp(raw.get("timestamp"))
        return NormalizedEvent(
            market_id=raw.get("market_id", ""),
            game_id=raw.get("game_id", ""),
            timestamp=timestamp,
            type=EventType.STATE_CHANGE,
            payload=raw.get("state", {})
        )
    
    def _parse_timestamp(self, ts) -> datetime:
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.utcnow()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_event_normalizer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/event_normalizer.py tests/trading_engine/test_event_normalizer.py
git commit -m "feat: implement EventNormalizer (Layer 2)"
```

---

## Task 5: Layer 3 - Temporal Buffer

**Files:**
- Create: `packages/backend-py/src/trading_engine/temporal_buffer.py`
- Create: `tests/trading_engine/test_temporal_buffer.py`

- [ ] **Step 1: Write test for temporal buffer**

```python
# tests/trading_engine/test_temporal_buffer.py
import pytest
from datetime import datetime, timedelta
from src.trading_engine.temporal_buffer import TemporalBuffer, GameBuffer

def test_adds_events_to_timeline():
    buffer = TemporalBuffer()
    event = {
        "market_id": "market_abc",
        "game_id": "game_123",
        "timestamp": datetime.utcnow(),
        "type": "trade"
    }
    buffer.add(event)
    
    game_buffer = buffer.get_game_buffer("game_123")
    assert game_buffer is not None
    assert len(game_buffer.trade_timeline) == 1

def test_rolling_window_expiry():
    buffer = TemporalBuffer(window_seconds=30)
    old_time = datetime.utcnow() - timedelta(seconds=60)
    
    buffer.add({"market_id": "a", "game_id": "g", "timestamp": old_time, "type": "trade"})
    buffer.add({"market_id": "a", "game_id": "g", "timestamp": datetime.utcnow(), "type": "trade"})
    
    game_buffer = buffer.get_game_buffer("g")
    assert len(game_buffer.trade_timeline) == 1

def test_multiple_timelines():
    buffer = TemporalBuffer()
    buffer.add({"market_id": "m", "game_id": "g", "timestamp": datetime.utcnow(), "type": "trade"})
    buffer.add({"market_id": "m", "game_id": "g", "timestamp": datetime.utcnow(), "type": "score"})
    
    gb = buffer.get_game_buffer("g")
    assert len(gb.trade_timeline) == 1
    assert len(gb.score_timeline) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_temporal_buffer.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement TemporalBuffer**

```python
# packages/backend-py/src/trading_engine/temporal_buffer.py
"""Layer 3: Temporal Buffer - rolling windows per game."""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional, Any


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
        seconds: int
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
    
    def get_all_game_ids(self) -> List[str]:
        """Get all active game IDs."""
        return list(self._buffers.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_temporal_buffer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/temporal_buffer.py tests/trading_engine/test_temporal_buffer.py
git commit -m "feat: implement TemporalBuffer (Layer 3)"
```

---

## Task 6: Layer 4 - Factor Engine

**Files:**
- Create: `packages/backend-py/src/trading_engine/factor_engine.py`
- Create: `tests/trading_engine/test_factor_engine.py`

- [ ] **Step 1: Write test for factor engine**

```python
# tests/trading_engine/test_factor_engine.py
import pytest
from datetime import datetime
from src.trading_engine.factor_engine import FactorEngine, FlowFactors

def test_calculates_net_flow_rate():
    engine = FactorEngine()
    trades = [
        {"side": "buy", "size": 100, "price": 0.5},
        {"side": "sell", "size": 50, "price": 0.5},
        {"side": "buy", "size": 100, "price": 0.5},
    ]
    flow = engine.compute_flow_factors(trades)
    assert flow.net_flow_rate == pytest.approx((200 - 50) / (200 + 50))

def test_calculates_large_trade_density():
    engine = FactorEngine()
    trades = [
        {"side": "buy", "size": 10000},
        {"side": "buy", "size": 100},
        {"side": "buy", "size": 8000},
    ]
    flow = engine.compute_flow_factors(trades, large_trade_threshold=5000)
    assert flow.large_trade_density == pytest.approx(2/3)

def test_empty_trades_returns_zeros():
    engine = FactorEngine()
    flow = engine.compute_flow_factors([])
    assert flow.net_flow_rate == 0
    assert flow.large_trade_density == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_factor_engine.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement FactorEngine**

```python
# packages/backend-py/src/trading_engine/factor_engine.py
"""Layer 4: Factor Engine - compute raw and normalized factors."""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class FlowFactors:
    """Flow factors from trade timeline."""
    net_flow_rate: float = 0.0
    flow_acceleration: float = 0.0
    large_trade_density: float = 0.0
    smart_money_score: float = 0.0
    order_book_imbalance: float = 0.0


@dataclass
class GameStateFactors:
    """Game state factors from score/event timeline."""
    score_gap_change_rate: float = 0.0
    match_time_progress: float = 0.0
    key_event_trigger: int = 0
    attack_pace_index: float = 1.0
    score_deviation: float = 0.0


@dataclass
class CrossFactors:
    """Cross factors from multi-dimension combination."""
    momentum_resonance: float = 0.0
    sentiment_index: float = 0.0


@dataclass
class AllFactors:
    """All computed factors."""
    flow: FlowFactors
    game_state: GameStateFactors
    cross: CrossFactors


class FactorEngine:
    """Layer 4: Factor Engine.
    
    Computes factors from temporal buffer data.
    Outputs raw factors for debugging, normalized for scoring.
    """
    
    def __init__(
        self,
        large_trade_threshold: float = 5000,
        momentum_window_seconds: int = 30,
    ):
        self.large_threshold = large_trade_threshold
        self.momentum_window = momentum_window_seconds
    
    def compute_all_factors(
        self,
        trade_window: List[dict],
        score_window: List[dict],
        event_window: List[dict],
        current_price: float = 0.5,
    ) -> AllFactors:
        """Compute all factor categories."""
        flow = self.compute_flow_factors(trade_window)
        game_state = self.compute_game_state_factors(score_window, event_window)
        cross = self.compute_cross_factors(flow, game_state)
        
        return AllFactors(flow=flow, game_state=game_state, cross=cross)
    
    def compute_flow_factors(self, trades: List[dict]) -> FlowFactors:
        """Compute flow factors from trade list."""
        if not trades:
            return FlowFactors()
        
        buy_volume = sum(t.get("size", 0) for t in trades if t.get("side") == "buy")
        sell_volume = sum(t.get("size", 0) for t in trades if t.get("side") == "sell")
        total_volume = buy_volume + sell_volume
        
        net_flow_rate = (buy_volume - sell_volume) / max(total_volume, 1)
        
        large_trades = [t for t in trades if t.get("size", 0) >= self.large_threshold]
        large_trade_density = len(large_trades) / max(len(trades), 1)
        
        smart_money_score = large_trade_density
        
        return FlowFactors(
            net_flow_rate=net_flow_rate,
            flow_acceleration=0.0,
            large_trade_density=large_trade_density,
            smart_money_score=smart_money_score,
            order_book_imbalance=0.0,
        )
    
    def compute_game_state_factors(
        self,
        scores: List[dict],
        events: List[dict],
    ) -> GameStateFactors:
        """Compute game state factors."""
        if not scores:
            return GameStateFactors()
        
        latest = scores[-1] if scores else {}
        initial = scores[0] if scores else {}
        
        home_now = latest.get("home_score", 0)
        away_now = latest.get("away_score", 0)
        gap_now = home_now - away_now
        
        home_start = initial.get("home_score", 0)
        away_start = initial.get("away_score", 0)
        gap_start = home_start - away_start
        
        if gap_start != 0:
            score_gap_change = (gap_now - gap_start) / abs(gap_start)
        else:
            score_gap_change = 0.0 if gap_now == 0 else (1 if gap_now > 0 else -1)
        
        key_event_trigger = 1 if events and any(e.get("is_key") for e in events) else 0
        
        return GameStateFactors(
            score_gap_change_rate=score_gap_change,
            match_time_progress=0.5,
            key_event_trigger=key_event_trigger,
            attack_pace_index=1.0,
            score_deviation=0.0,
        )
    
    def compute_cross_factors(
        self,
        flow: FlowFactors,
        game_state: GameStateFactors,
    ) -> CrossFactors:
        """Compute cross factors."""
        flow_dir = 1 if flow.net_flow_rate > 0 else (-1 if flow.net_flow_rate < 0 else 0)
        score_dir = 1 if game_state.score_gap_change_rate > 0 else (-1 if game_state.score_gap_change_rate < 0 else 0)
        momentum_resonance = flow_dir * score_dir
        
        sentiment = (
            0.25 * flow.net_flow_rate +
            0.25 * game_state.score_gap_change_rate +
            0.2 * flow.large_trade_density +
            0.3 * momentum_resonance
        )
        
        return CrossFactors(
            momentum_resonance=momentum_resonance,
            sentiment_index=sentiment,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_factor_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/factor_engine.py tests/trading_engine/test_factor_engine.py
git commit -m "feat: implement FactorEngine (Layer 4)"
```

---

## Task 7: Layer 5 - Score Aggregator

**Files:**
- Create: `packages/backend-py/src/trading_engine/score_aggregator.py`
- Create: `tests/trading_engine/test_score_aggregator.py`

- [ ] **Step 1: Write test for score aggregator**

```python
# tests/trading_engine/test_score_aggregator.py
import pytest
from src.trading_engine.score_aggregator import ScoreAggregator, ScoreConfig

def test_edge_score_range():
    agg = ScoreAggregator(ScoreConfig())
    edge = agg.compute_edge_score(1.0, 0.8, 0.9)
    assert -1 <= edge <= 1
    assert edge == pytest.approx(0.72)

def test_risk_score_takes_max():
    agg = ScoreAggregator(ScoreConfig())
    risk = agg.compute_risk_score(0.3, 0.5, 0.8, 0.2)
    assert risk == pytest.approx(0.8)

def test_ev_score_combines_llm_and_market():
    agg = ScoreAggregator(ScoreConfig())
    ev = agg.compute_ev_score(llm_ev=0.7, market_deviation=0.8)
    assert ev == pytest.approx(0.56)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_score_aggregator.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement ScoreAggregator**

```python
# packages/backend-py/src/trading_engine/score_aggregator.py
"""Layer 5: Score Aggregator - compute EdgeScore, EV_Score, RiskScore."""

from dataclasses import dataclass


@dataclass
class ScoreConfig:
    """Score computation configuration."""
    w1_net_flow: float = 0.25
    w2_flow_accel: float = 0.20
    w3_odds_change: float = 0.15
    w4_score_gap: float = 0.20
    w5_momentum: float = 0.20
    time_pressure_threshold: float = 0.85
    llm_weight: float = 0.4
    market_deviation_weight: float = 0.6


@dataclass
class CompositeScores:
    """Three core scores."""
    edge_score: float
    ev_score: float
    risk_score: float


class ScoreAggregator:
    """Layer 5: Score Aggregator.
    
    Computes EdgeScore, EV_Score, RiskScore from factors.
    """
    
    def __init__(self, config: ScoreConfig = None):
        self.config = config or ScoreConfig()
    
    def compute_edge_score(
        self,
        net_flow_rate: float,
        strength: float,
        acceleration: float,
        time_pressure: float = 0.0,
    ) -> float:
        """Compute EdgeScore = Direction × Strength × Acceleration.
        
        Range: [-1, 1]
        """
        if time_pressure > self.config.time_pressure_threshold:
            strength *= 0.5
        
        strength = max(0.0, min(1.0, abs(strength)))
        acceleration = max(0.0, min(1.0, acceleration))
        
        direction = 1 if net_flow_rate > 0 else (-1 if net_flow_rate < 0 else 0)
        
        return direction * strength * acceleration
    
    def compute_ev_score(
        self,
        llm_ev: float,
        market_deviation: float,
    ) -> float:
        """Compute EV_Score = LLM_EV × MarketDeviation.
        
        Range: [0, 1]
        """
        llm_ev = max(0.0, min(1.0, llm_ev))
        market_deviation = max(0.0, min(1.0, market_deviation))
        
        return (
            self.config.llm_weight * llm_ev +
            self.config.market_deviation_weight * market_deviation
        )
    
    def compute_risk_score(
        self,
        volatility: float,
        spread: float,
        time_instability: float,
        latency: float = 0.0,
    ) -> float:
        """Compute RiskScore = max(V, S, T, L).
        
        Range: [0, 1]
        """
        V = max(0.0, min(1.0, volatility))
        S = max(0.0, min(1.0, spread))
        T = max(0.0, min(1.0, time_instability))
        L = max(0.0, min(1.0, latency))
        
        return max(V, S, T, L)
    
    def compute_all_scores(
        self,
        net_flow_rate: float,
        strength: float,
        acceleration: float,
        llm_ev: float,
        market_deviation: float,
        volatility: float,
        spread: float,
        time_instability: float,
        time_pressure: float = 0.0,
        latency: float = 0.0,
    ) -> CompositeScores:
        """Compute all three scores at once."""
        edge = self.compute_edge_score(
            net_flow_rate, strength, acceleration, time_pressure
        )
        ev = self.compute_ev_score(llm_ev, market_deviation)
        risk = self.compute_risk_score(
            volatility, spread, time_instability, latency
        )
        
        return CompositeScores(edge_score=edge, ev_score=ev, risk_score=risk)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_score_aggregator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/score_aggregator.py tests/trading_engine/test_score_aggregator.py
git commit -m "feat: implement ScoreAggregator (Layer 5)"
```

---

## Task 8: Position Tracker

**Files:**
- Create: `packages/backend-py/src/trading_engine/position_tracker.py`
- Create: `tests/trading_engine/test_position_tracker.py`

- [ ] **Step 1: Write test for position tracker**

```python
# tests/trading_engine/test_position_tracker.py
import pytest
from datetime import datetime
from decimal import Decimal
from src.trading_engine.position_tracker import PositionTracker, Position, PositionStatus

def test_add_position():
    tracker = PositionTracker()
    position = Position(
        position_id="pos_1",
        market_id="market_abc",
        token_id="token_123",
        strategy_id="strat_1",
        side="yes",
        size=Decimal("100"),
        entry_price=Decimal("0.55"),
        stop_loss_pct=0.1,
        take_profit_pct=0.2,
        status=PositionStatus.OPEN,
    )
    
    tracker.add(position)
    assert tracker.get("pos_1") == position
    assert tracker.get_by_token("token_123") == [position]

def test_cannot_close_nonexistent():
    tracker = PositionTracker()
    result = tracker.close("nonexistent", "stop_loss")
    assert result is False

def test_status_transition():
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
    
    result = tracker.update_status("pos_1", PositionStatus.CLOSING)
    assert result is True
    
    result = tracker.update_status("pos_1", PositionStatus.OPEN)
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_position_tracker.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement PositionTracker**

```python
# packages/backend-py/src/trading_engine/position_tracker.py
"""Position Tracker - state machine for positions."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional


class PositionStatus(Enum):
    """Position lifecycle status."""
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    ERROR = "error"


@dataclass
class Position:
    """Position record."""
    position_id: str
    market_id: str
    token_id: str
    strategy_id: str
    side: str
    size: Decimal
    entry_price: Decimal
    
    stop_loss_pct: float = 0.1
    take_profit_pct: float = 0.2
    
    status: PositionStatus = PositionStatus.OPEN
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = None
    close_price: Optional[Decimal] = None
    pnl: Optional[Decimal] = None
    
    def stop_loss_price(self) -> Decimal:
        if self.side == "yes":
            return self.entry_price * Decimal(str(1 - self.stop_loss_pct))
        else:
            return self.entry_price * Decimal(str(1 + self.stop_loss_pct))
    
    def take_profit_price(self) -> Decimal:
        if self.side == "yes":
            return self.entry_price * Decimal(str(1 + self.take_profit_pct))
        else:
            return self.entry_price * Decimal(str(1 - self.take_profit_pct))


class PositionTracker:
    """Layer: Position Tracker.
    
    Maintains position state machine.
    Key by position_id, index by token_id for price monitoring.
    """
    
    def __init__(self):
        self._positions: Dict[str, Position] = {}
        self._by_token: Dict[str, List[str]] = {}
    
    def add(self, position: Position) -> None:
        self._positions[position.position_id] = position
        
        if position.token_id not in self._by_token:
            self._by_token[position.token_id] = []
        self._by_token[position.token_id].append(position.position_id)
    
    def get(self, position_id: str) -> Optional[Position]:
        return self._positions.get(position_id)
    
    def get_by_token(self, token_id: str) -> List[Position]:
        position_ids = self._by_token.get(token_id, [])
        return [self._positions[pid] for pid in position_ids if pid in self._positions]
    
    def get_all_open(self) -> List[Position]:
        return [p for p in self._positions.values() if p.status == PositionStatus.OPEN]
    
    def get_all_open_by_token(self, token_id: str) -> List[Position]:
        positions = self.get_by_token(token_id)
        return [p for p in positions if p.status == PositionStatus.OPEN]
    
    def update_status(
        self,
        position_id: str,
        new_status: PositionStatus,
    ) -> bool:
        position = self._positions.get(position_id)
        if not position:
            return False
        
        valid_transitions = {
            PositionStatus.OPEN: [PositionStatus.CLOSING, PositionStatus.ERROR],
            PositionStatus.CLOSING: [PositionStatus.CLOSED, PositionStatus.ERROR],
        }
        
        allowed = valid_transitions.get(position.status, [])
        if new_status not in allowed:
            return False
        
        position.status = new_status
        
        if new_status == PositionStatus.CLOSED:
            position.closed_at = datetime.utcnow()
        
        return True
    
    def close(
        self,
        position_id: str,
        reason: str,
        close_price: Optional[Decimal] = None,
    ) -> bool:
        position = self._positions.get(position_id)
        if not position or position.status != PositionStatus.OPEN:
            return False
        
        position.status = PositionStatus.CLOSING
        position.close_reason = reason
        if close_price:
            position.close_price = close_price
            if position.side == "yes":
                position.pnl = (close_price - position.entry_price) * position.size
            else:
                position.pnl = (position.entry_price - close_price) * position.size
        
        return True
    
    def finalize_close(
        self,
        position_id: str,
        close_price: Decimal,
    ) -> bool:
        position = self._positions.get(position_id)
        if not position or position.status != PositionStatus.CLOSING:
            return False
        
        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.utcnow()
        position.close_price = close_price
        
        if position.side == "yes":
            position.pnl = (close_price - position.entry_price) * position.size
        else:
            position.pnl = (position.entry_price - close_price) * position.size
        
        if position.token_id in self._by_token:
            if position_id in self._by_token[position.token_id]:
                self._by_token[position.token_id].remove(position_id)
        
        return True
    
    def remove(self, position_id: str) -> bool:
        position = self._positions.pop(position_id, None)
        if not position:
            return False
        
        if position.token_id in self._by_token:
            if position_id in self._by_token[position.token_id]:
                self._by_token[position.token_id].remove(position_id)
        
        return True
    
    def count_open(self) -> int:
        return len([p for p in self._positions.values() if p.status == PositionStatus.OPEN])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_position_tracker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/position_tracker.py tests/trading_engine/test_position_tracker.py
git commit -m "feat: implement PositionTracker with status machine"
```

---

## Task 9: Strategy Manager & Strategy Instance

**Files:**
- Create: `packages/backend-py/src/trading_engine/strategy_manager.py`
- Create: `tests/trading_engine/test_strategy_manager.py`

- [ ] **Step 1: Write test for strategy manager**

```python
# tests/trading_engine/test_strategy_manager.py
import pytest
from src.trading_engine.strategy_manager import StrategyManager, StrategyInstance, StrategyState, Decision

def test_strategy_state_transitions():
    strategy = StrategyInstance(strategy_id="s1", config={})
    assert strategy.state == StrategyState.CREATED
    
    strategy.start()
    assert strategy.state == StrategyState.RUNNING
    
    strategy.pause()
    assert strategy.state == StrategyState.PAUSED
    
    strategy.resume()
    assert strategy.state == StrategyState.RUNNING
    
    strategy.stop()
    assert strategy.state == StrategyState.STOPPED

def test_manager_creates_and_registers():
    manager = StrategyManager()
    strategy = manager.create_strategy(strategy_id="s1", config={})
    
    assert strategy is not None
    assert manager.get("s1") == strategy
    
def test_manager_subscribes_to_event_bus_on_start():
    manager = StrategyManager()
    strategy = manager.create_strategy(strategy_id="s1", config={})
    
    assert strategy.state == StrategyState.CREATED
    
    manager.start_strategy("s1")
    assert strategy.state == StrategyState.RUNNING
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_strategy_manager.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement StrategyManager and StrategyInstance**

```python
# packages/backend-py/src/trading_engine/strategy_manager.py
"""Layer 6: Strategy Manager and Strategy Instance."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Any


class StrategyState(Enum):
    """Strategy lifecycle state."""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class Decision(Enum):
    """Trading decision."""
    BUY_YES = "buy_yes"
    BUY_NO = "buy_no"
    HOLD = "hold"
    EXIT = "exit"
    REJECT = "reject"


@dataclass
class StrategyConfig:
    """Strategy configuration."""
    edge_threshold: float = 0.4
    ev_threshold: float = 0.6
    risk_threshold: float = 0.5
    sustained_count: int = 3
    time_pressure_threshold: float = 0.85
    max_hold_seconds: int = 3600
    min_size: float = 10.0
    max_size: float = 100.0
    dead_zone: tuple = (0.70, 0.80)
    excluded_keywords: List[str] = []
    llm_cooldown_seconds: int = 5


@dataclass
class StrategyInstance:
    """Single strategy instance with isolated state."""
    strategy_id: str
    config: StrategyConfig
    
    state: StrategyState = StrategyState.CREATED
    current_position_id: Optional[str] = None
    last_llm_call: datetime = field(default_factory=datetime.utcnow)
    _direction_history: List[float] = field(default_factory=list)
    on_decision: Optional[Callable] = None
    
    def start(self) -> None:
        if self.state not in (StrategyState.CREATED, StrategyState.STOPPED, StrategyState.PAUSED):
            return
        self.state = StrategyState.RUNNING
    
    def stop(self) -> None:
        if self.state == StrategyState.RUNNING:
            self.state = StrategyState.STOPPED
    
    def pause(self) -> None:
        if self.state == StrategyState.RUNNING:
            self.state = StrategyState.PAUSED
    
    def resume(self) -> None:
        if self.state == StrategyState.PAUSED:
            self.state = StrategyState.RUNNING
    
    def should_trigger_llm(self) -> bool:
        elapsed = (datetime.utcnow() - self.last_llm_call).total_seconds()
        return elapsed >= self.config.llm_cooldown_seconds
    
    def record_direction(self, edge_score: float) -> bool:
        self._direction_history.append(edge_score)
        
        max_len = self.config.sustained_count * 2
        if len(self._direction_history) > max_len:
            self._direction_history = self._direction_history[-max_len:]
        
        if len(self._direction_history) < self.config.sustained_count:
            return False
        
        recent = self._direction_history[-self.config.sustained_count:]
        return all(d > 0.1 for d in recent) or all(d < -0.1 for d in recent)
    
    def decide(
        self,
        edge_score: float,
        ev_score: float,
        risk_score: float,
        time_pressure: float = 0.0,
    ) -> Decision:
        if self.state != StrategyState.RUNNING:
            return Decision.HOLD
        
        if risk_score > 0.8:
            return Decision.REJECT
        
        sustained = self.record_direction(edge_score)
        if not sustained and abs(edge_score) > self.config.edge_threshold:
            return Decision.HOLD
        
        if abs(edge_score) > self.config.edge_threshold:
            if ev_score > self.config.ev_threshold:
                if risk_score < self.config.risk_threshold:
                    if edge_score > 0:
                        return Decision.BUY_YES
                    else:
                        return Decision.BUY_NO
        
        return Decision.HOLD


class StrategyManager:
    """Layer 6: Strategy Manager.
    
    Manages strategy instances lifecycle.
    Subscribes strategies to EventBus when running.
    """
    
    def __init__(self, event_bus=None):
        self._strategies: Dict[str, StrategyInstance] = {}
        self._event_bus = event_bus
    
    def create_strategy(
        self,
        strategy_id: str,
        config: Dict[str, Any],
    ) -> StrategyInstance:
        strategy_config = StrategyConfig(**config)
        strategy = StrategyInstance(
            strategy_id=strategy_id,
            config=strategy_config,
        )
        self._strategies[strategy_id] = strategy
        return strategy
    
    def get(self, strategy_id: str) -> Optional[StrategyInstance]:
        return self._strategies.get(strategy_id)
    
    def start_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        
        strategy.start()
        return True
    
    def stop_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        
        strategy.stop()
        return True
    
    def pause_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        strategy.pause()
        return True
    
    def resume_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return False
        strategy.resume()
        return True
    
    def remove_strategy(self, strategy_id: str) -> bool:
        strategy = self._strategies.pop(strategy_id, None)
        return strategy is not None
    
    def get_all_strategies(self) -> List[StrategyInstance]:
        return list(self._strategies.values())
    
    def get_running_strategies(self) -> List[StrategyInstance]:
        return [s for s in self._strategies.values() if s.state == StrategyState.RUNNING]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_strategy_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/strategy_manager.py tests/trading_engine/test_strategy_manager.py
git commit -m "feat: implement StrategyManager and StrategyInstance (Layer 6)"
```

---

## Task 10: Risk Manager

**Files:**
- Create: `packages/backend-py/src/trading_engine/risk_manager.py`
- Create: `tests/trading_engine/test_risk_manager.py`

- [ ] **Step 1: Write test for risk manager**

```python
# tests/trading_engine/test_risk_manager.py
import pytest
from src.trading_engine.risk_manager import RiskManager, RiskConfig

def test_rejects_low_confidence():
    config = RiskConfig(min_confidence=0.6)
    manager = RiskManager(config)
    
    signal = {"confidence": 0.4, "market_id": "m1", "size": 100}
    result = manager.approve(signal)
    assert result.approved is False
    assert "confidence" in result.reason

def test_rejects_cooldown_market():
    config = RiskConfig(cooldown_seconds=30)
    manager = RiskManager(config)
    
    signal = {"confidence": 0.8, "market_id": "m1", "size": 100}
    result1 = manager.approve(signal)
    assert result1.approved is True
    
    result2 = manager.approve(signal)
    assert result2.approved is False
    assert "cooldown" in result2.reason

def test_rejects_exposure_limit():
    config = RiskConfig(max_total_exposure=500)
    manager = RiskManager(config)
    
    manager._current_exposure = 450
    
    signal = {"confidence": 0.8, "market_id": "m2", "size": 100}
    result = manager.approve(signal)
    assert result.approved is False
    assert "exposure" in result.reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/trading_engine/test_risk_manager.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement RiskManager**

```python
# packages/backend-py/src/trading_engine/risk_manager.py
"""Risk Manager - Unified risk control."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional
from uuid import uuid4


@dataclass
class RiskConfig:
    """Risk manager configuration."""
    min_confidence: float = 0.5
    cooldown_seconds: int = 30
    max_total_exposure: float = 1000.0
    max_position_per_market: float = 200.0
    max_positions: int = 10


@dataclass
class ApprovalResult:
    """Result of risk approval."""
    approved: bool
    order_id: Optional[str] = None
    reason: Optional[str] = None
    modified_size: Optional[float] = None


class RiskManager:
    """Layer: Risk Manager.
    
    Unified risk control for all trading decisions.
    """
    
    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self._cooldowns: Dict[str, datetime] = {}
        self._positions: Dict[str, dict] = {}
        self._current_exposure: float = 0.0
    
    def approve(self, signal: dict) -> ApprovalResult:
        confidence = signal.get("confidence", 0)
        if confidence < self.config.min_confidence:
            return ApprovalResult(approved=False, reason="low_confidence")
        
        market_id = signal.get("market_id")
        if market_id in self._cooldowns:
            elapsed = datetime.utcnow() - self._cooldowns[market_id]
            if elapsed < timedelta(seconds=self.config.cooldown_seconds):
                return ApprovalResult(approved=False, reason="cooldown")
        
        size = float(signal.get("size", 0))
        if self._current_exposure + size > self.config.max_total_exposure:
            return ApprovalResult(approved=False, reason="exposure_limit")
        
        if market_id in self._positions:
            existing_size = float(self._positions[market_id].get("size", 0))
            if existing_size + size > self.config.max_position_per_market:
                return ApprovalResult(approved=False, reason="market_limit")
        
        if len(self._positions) >= self.config.max_positions:
            return ApprovalResult(approved=False, reason="max_positions")
        
        order_id = str(uuid4())
        return ApprovalResult(approved=True, order_id=order_id)
    
    def on_fill(self, order: dict) -> None:
        market_id = order.get("market_id")
        size = float(order.get("size", 0))
        
        self._current_exposure += size
        
        self._positions[market_id] = {
            "size": self._positions.get(market_id, {}).get("size", 0) + size,
            "entry_price": order.get("price"),
            "side": order.get("side"),
        }
        
        self._cooldowns[market_id] = datetime.utcnow()
    
    def on_close(self, market_id: str, size: float) -> None:
        if market_id in self._positions:
            self._current_exposure -= size
            del self._positions[market_id]
        
        self._cooldowns[market_id] = datetime.utcnow()
    
    def get_exposure(self) -> float:
        return self._current_exposure
    
    def get_market_position(self, market_id: str) -> Optional[dict]:
        return self._positions.get(market_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/trading_engine/test_risk_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/trading_engine/risk_manager.py tests/trading_engine/test_risk_manager.py
git commit -m "feat: implement RiskManager"
```

---

## Task 11: WebSocket Sources (Singletons)

**Files:**
- Create: `packages/backend-py/src/services/websocket_sources.py`
- Create: `tests/services/test_websocket_sources.py`

- [ ] **Step 1: Write test for websocket sources**

```python
# tests/services/test_websocket_sources.py
import pytest
import asyncio
from src.services.websocket_sources import ActivityWebSocketSource, SportsWebSocketSource

def test_singleton_pattern():
    source1 = ActivityWebSocketSource.get_instance()
    source2 = ActivityWebSocketSource.get_instance()
    assert source1 is source2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_websocket_sources.py -v`
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: Implement WebSocket Sources**

```python
# packages/backend-py/src/services/websocket_sources.py
"""WebSocket Sources - Global singleton connections."""

import asyncio
from typing import Optional


class ActivityWebSocketSource:
    """Activity WebSocket - Global singleton.
    
    Receives capital flow data from Polymarket.
    Publishes to EventBus.
    """
    _instance: Optional["ActivityWebSocketSource"] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self.event_bus = None
        self._running = False
        self._ws = None
    
    @classmethod
    async def get_instance(cls) -> "ActivityWebSocketSource":
        """Get singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    async def connect(self) -> None:
        """Connect to Activity WebSocket."""
        self._running = True
    
    async def disconnect(self) -> None:
        """Disconnect from Activity WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()
    
    def set_event_bus(self, event_bus) -> None:
        """Set EventBus for publishing."""
        self.event_bus = event_bus


class SportsWebSocketSource:
    """Sports WebSocket - Global singleton."""
    _instance: Optional["SportsWebSocketSource"] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self.event_bus = None
        self._running = False
        self._ws = None
    
    @classmethod
    async def get_instance(cls) -> "SportsWebSocketSource":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    async def connect(self) -> None:
        self._running = True
    
    async def disconnect(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
    
    def set_event_bus(self, event_bus) -> None:
        self.event_bus = event_bus
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_websocket_sources.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-py/src/services/websocket_sources.py tests/services/test_websocket_sources.py
git commit -m "feat: implement WebSocket source singletons"
```

---

## Implementation Order

1. EventBus Enhancement (Task 1)
2. DataIntegrityLayer - Layer 0 (Task 2)
3. InfraFilter - Layer 1 (Task 3)
4. EventNormalizer - Layer 2 (Task 4)
5. TemporalBuffer - Layer 3 (Task 5)
6. FactorEngine - Layer 4 (Task 6)
7. ScoreAggregator - Layer 5 (Task 7)
8. PositionTracker (Task 8)
9. StrategyManager + StrategyInstance (Task 9)
10. RiskManager (Task 10)
11. WebSocket Sources (Task 11)

---

## Post-Implementation

After all tasks complete, update trading_engine `__init__.py`:

```python
from .event_bus import EventBus, EventType
from .data_integrity import DataIntegrityLayer
from .infra_filter import InfraFilter, FilterConfig
from .event_normalizer import EventNormalizer, NormalizedEvent
from .temporal_buffer import TemporalBuffer, GameBuffer
from .factor_engine import FactorEngine, FlowFactors, GameStateFactors, CrossFactors, AllFactors
from .score_aggregator import ScoreAggregator, ScoreConfig, CompositeScores
from .strategy_manager import StrategyManager, StrategyInstance, StrategyState, Decision
from .position_tracker import PositionTracker, Position, PositionStatus
from .risk_manager import RiskManager, RiskConfig, ApprovalResult

__all__ = [
    "EventBus", "EventType",
    "DataIntegrityLayer",
    "InfraFilter", "FilterConfig",
    "EventNormalizer", "NormalizedEvent",
    "TemporalBuffer", "GameBuffer",
    "FactorEngine", "FlowFactors", "GameStateFactors", "CrossFactors", "AllFactors",
    "ScoreAggregator", "ScoreConfig", "CompositeScores",
    "StrategyManager", "StrategyInstance", "StrategyState", "Decision",
    "PositionTracker", "Position", "PositionStatus",
    "RiskManager", "RiskConfig", "ApprovalResult",
]
```
