"""Market Resolver - determines market type and regime."""

from dataclasses import dataclass
from typing import List, Set


# Sports keywords for Type A detection
SPORTS_KEYWORDS: Set[str] = {
    # Basketball
    "nba", "basketball",
    # Soccer / Football
    "ucl", "soccer", "football", "world cup", "euro",
    # American Football
    "nfl",
    # Hockey
    "nhl", "hockey",
    # Combat Sports
    "ufc", "mma", "boxing",
    # Tennis
    "tennis",
    # Cricket
    "cricket",
    # Baseball
    "mlb", "baseball",
    # Rugby
    "rugby",
    # Golf
    "golf",
    # Racing
    "formula1", "f1", "racing",
    # Esports
    "esports",
}

# Category keywords for Type B sub-detection
POLITICS_KEYWORDS: Set[str] = {
    "election", "president", "trump", "biden", "congress", "senate", "policy",
}

CRYPTO_KEYWORDS: Set[str] = {
    "bitcoin", "btc", "ethereum", "eth", "solana", "crypto",
}

ECONOMICS_KEYWORDS: Set[str] = {
    "cpi", "jobs", "gdp", "fed", "inflation", "unemployment",
}

WEATHER_KEYWORDS: Set[str] = {
    "hurricane", "temperature", "snow", "weather", "storm", "rain",
}

ENTERTAINMENT_KEYWORDS: Set[str] = {
    "oscar", "emmy", "grammy", "award", "wins", "nominee",
}


@dataclass
class MarketProfile:
    """Market profile with type and regime information."""
    market_id: str
    category: str  # "sports", "politics", "crypto", etc.
    subcategory: str  # "basketball", "soccer", etc. for sports
    regime: str  # "event-driven" or "flow-driven"
    data_dependencies: List[str]
    schema: str  # "sports" or "flow-only"


class MarketResolver:
    """Determines market type based on question content."""

    def resolve(self, market_id: str, question: str) -> MarketProfile:
        """Resolve market type from question content."""
        question_lower = question.lower()

        # Type A: Sports (has Sports WS data)
        if self._is_sports(question_lower):
            subcategory = self._detect_sports_subcategory(question_lower)
            return MarketProfile(
                market_id=market_id,
                category="sports",
                subcategory=subcategory,
                regime="event-driven",
                data_dependencies=["activity", "sports_score"],
                schema="sports",
            )

        # Type B: Flow-only (Activity WS only)
        category = self._detect_other_category(question_lower)
        return MarketProfile(
            market_id=market_id,
            category=category,
            subcategory="",
            regime="flow-driven",
            data_dependencies=["activity"],
            schema="flow-only",
        )

    def _is_sports(self, question: str) -> bool:
        """Check if question is about sports."""
        return any(kw in question for kw in SPORTS_KEYWORDS)

    def _detect_sports_subcategory(self, question: str) -> str:
        """Detect specific sports subcategory."""
        if "nba" in question or "basketball" in question:
            return "basketball"
        if "ucl" in question or "soccer" in question or "football" in question:
            return "soccer"
        if "nfl" in question:
            return "football"
        if "nhl" in question or "hockey" in question:
            return "hockey"
        if "ufc" in question or "mma" in question or "boxing" in question:
            return "mma"
        if "tennis" in question:
            return "tennis"
        if "cricket" in question:
            return "cricket"
        if "mlb" in question or "baseball" in question:
            return "baseball"
        if "rugby" in question:
            return "rugby"
        if "golf" in question:
            return "golf"
        if "formula1" in question or "f1" in question or "racing" in question:
            return "racing"
        if "esports" in question:
            return "esports"
        return "other"

    def _detect_other_category(self, question: str) -> str:
        """Detect non-sports market category."""
        if any(k in question for k in POLITICS_KEYWORDS):
            return "politics"
        if any(k in question for k in CRYPTO_KEYWORDS):
            return "crypto"
        if any(k in question for k in ECONOMICS_KEYWORDS):
            return "economics"
        if any(k in question for k in WEATHER_KEYWORDS):
            return "weather"
        if any(k in question for k in ENTERTAINMENT_KEYWORDS):
            return "entertainment"
        return "other"
