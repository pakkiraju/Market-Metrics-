"""Export widget table data as a TradingView-friendly symbol list (download)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

TRADINGVIEW_HEADER = (
    "# TradingView watchlist — one symbol per line.\n"
    "# US equities: use plain symbols (e.g. AAPL); TradingView resolves the exchange.\n"
    "# Import: Watchlist → ⋮ → Import list… → paste these lines.\n"
)


def extract_tickers_from_rows(rows: Any) -> list[str]:
    """Collect unique ticker symbols from list[dict] table rows (FinViz / app format)."""
    if not rows or not isinstance(rows, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        t = r.get("ticker") or r.get("Ticker") or r.get("symbol") or r.get("Symbol")
        if not t:
            continue
        t = str(t).strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def build_tradingview_file_body(symbols: list[str]) -> str:
    """Plaintext body: header comment block + one symbol per line."""
    body = TRADINGVIEW_HEADER + "\n"
    for s in symbols:
        body += s + "\n"
    return body


# Widget IDs that have a matching `{id}-data-store` in layout (order must match callback States).
WIDGET_DATA_STORE_IDS: tuple[str, ...] = (
    "watchlist",
    "qulla",
    "minervini",
    "oneil",
    "jeff_sun_canslim",
    "jeff_sun_high_adr",
    "jeff_sun_extended_bases",
    "jeff_sun_1w20",
    "jeff_sun_4w30",
    "jeff_sun_4w50",
    "jeff_sun_13w50",
    "jeff_sun_26w100",
    "jeff_sun_ipo_thisweek",
    "jeff_sun_high_short_float",
    "jeff_sun_liquid_etfs",
    "julian_komar_strongest",
    "club97",
    "movers",
    "weekly",
    "daily",
    "earnings-calendar-week",
    "stockbee",
    "sector",
    "leading",
    "thematics",
    "thematics-sector",
    "sp500-landscape",
    "in_play",
    "intraday-earnings",
    "pre_market",
)


def tickers_from_fallback(widget_id: str) -> list[str]:
    """When no data-store row exists, fetch tickers from the same sources as refresh callbacks."""
    try:
        if widget_id == "top_gainers":
            from src.calculations import compute_top_gainers_losers
            g, _ = compute_top_gainers_losers(12)
            return extract_tickers_from_rows(g)
        if widget_id == "top_losers":
            from src.calculations import compute_top_gainers_losers
            _, l = compute_top_gainers_losers(12)
            return extract_tickers_from_rows(l)
        if widget_id == "live_index":
            from src.data_fetcher import fetch_live_index_quotes
            data = fetch_live_index_quotes()
            return extract_tickers_from_rows(data if isinstance(data, list) else [])
        if widget_id == "cnbc_premarket":
            from src.cnbc_premarket import fetch_cnbc_premarket_watchlist
            data = fetch_cnbc_premarket_watchlist()
            return extract_tickers_from_rows(data if isinstance(data, list) else [])
        if widget_id == "stage":
            from src import cache
            data = cache.get("stage_analysis")
            if isinstance(data, dict) and isinstance(data.get("tickers"), list):
                return extract_tickers_from_rows(data["tickers"])
        if widget_id == "key-metrics":
            # Index aggregates, not a flat ticker list
            return []
    except Exception as e:
        logger.warning("tickers_from_fallback(%s): %s", widget_id, e)
    return []
