"""Risk Manager - Unified risk control."""

from dataclasses import dataclass
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
        """Approve or reject a trading signal."""
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
        self._cooldowns[market_id] = datetime.utcnow()
        return ApprovalResult(approved=True, order_id=order_id)

    def on_fill(self, order: dict) -> None:
        """Record filled order."""
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
        """Record closed position."""
        if market_id in self._positions:
            self._current_exposure -= size
            del self._positions[market_id]

        self._cooldowns[market_id] = datetime.utcnow()

    def get_exposure(self) -> float:
        """Get current total exposure."""
        return self._current_exposure

    def get_market_position(self, market_id: str) -> Optional[dict]:
        """Get position for a market."""
        return self._positions.get(market_id)
