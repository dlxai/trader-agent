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
