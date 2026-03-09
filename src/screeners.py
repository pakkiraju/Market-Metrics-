"""Placeholder screener functions for V2 expansion.

Each screener returns a list of dicts with at minimum a 'ticker' key
and an optional 'color' key (green/yellow/orange/red/blue).
"""

from src.data_fetcher import load_watchlist


def qullamaggie_screener(indicators=None) -> list[dict]:
    """Placeholder: Qullamaggie-inspired breakout screener.

    V2 will implement:
    - Tight consolidation near highs (volatility contraction)
    - Price within 5-10% of 52-week high
    - Volume dry-up during consolidation
    - Breakout above consolidation range on volume
    """
    return []


def minervini_screener(indicators=None) -> list[dict]:
    """Placeholder: Minervini Trend Template screener.

    V2 will implement:
    - Price > SMA50 > SMA150 > SMA200
    - SMA200 trending up for >= 1 month
    - Price >= 25% above 52-week low
    - Price within 25% of 52-week high
    - RS rating >= 70
    """
    return []


def oneil_screener(indicators=None) -> list[dict]:
    """Placeholder: William O'Neil / CANSLIM screener.

    V2 will implement CAN SLIM criteria:
    - C: Current quarterly earnings growth
    - A: Annual earnings growth
    - N: New highs / new products
    - S: Supply and demand (volume)
    - L: Leader or laggard (RS)
    - I: Institutional sponsorship
    - M: Market direction
    """
    return []


def watchlist_tickers() -> list[dict]:
    """Load personal watchlist from config CSV."""
    tickers = load_watchlist()
    return [{"ticker": t, "color": "green"} for t in tickers]
