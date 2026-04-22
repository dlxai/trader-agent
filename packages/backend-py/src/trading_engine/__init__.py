"""Trading engine package.

This package implements the trading engine architecture:
- Collector: Market data collection
- Analyzer: Signal analysis using LLM
- Executor: Order execution
- Reviewer: Performance review
- Risk Manager: Risk management
"""

from .event_bus import EventBus, EventType
from .collector import DataCollector
from .analyzer import SignalAnalyzer
from .executor import OrderExecutor
from .reviewer import PerformanceReviewer
# from .risk_manager import RiskManager  # TODO: implement

__all__ = [
    "EventBus",
    "EventType",
    "DataCollector",
    "SignalAnalyzer",
    "OrderExecutor",
    "PerformanceReviewer",
    "RiskManager",
]
