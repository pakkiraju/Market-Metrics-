"""Qullamaggie-inspired screeners and placeholders.

Each screener returns a list of dicts with at minimum a 'ticker' key
and an optional 'color' key (green/yellow/orange/red/blue).
"""

from src.data_fetcher import (
    load_watchlist,
    load_composite,
    fetch_group_indicators,
    _fetch_screener,
)
from src import cache
from src.cache import FAST, MEDIUM


def _parse_num(s):
    """Parse numeric string with K/M/B suffixes."""
    import re
    if s is None:
        return None
    try:
        import pandas as pd
        if isinstance(s, float) and pd.isna(s):
            return None
    except ImportError:
        pass
    s = str(s).strip().replace(",", "").replace("$", "").replace("%", "")
    if not s or s == "-":
        return None
    m = re.match(r"([\d.-]+)\s*([KMB])?", s, re.I)
    if not m:
        try:
            return float(s)
        except ValueError:
            return None
    val = float(m.group(1))
    suffix = (m.group(2) or "").upper()
    if suffix == "K":
        val *= 1e3
    elif suffix == "M":
        val *= 1e6
    elif suffix == "B":
        val *= 1e9
    return val


# -----------------------------------------------------------------------
# 1. Episodic Pivot: Gap up 10%+, Rel Vol 2+
# -----------------------------------------------------------------------
def episodic_pivot_screener() -> list[dict]:
    """Gap up 10%+ with above-average volume (rel vol 2+)."""
    cached = cache.get("qulla_episodic")
    if cached is not None:
        return cached
    try:
        # ta_gap_u10 = gap up over 10%, sh_relvol_o2 = rel vol over 2
        # Combine S&P 500 and NASDAQ 100
        results = []
        for idx in ["idx_sp500", "idx_ndx"]:
            df = _fetch_screener(
                filters=[idx, "ta_gap_u10", "sh_relvol_o2"],
                table="Performance",
                cache_key=f"qulla_ep_{idx}",
                order="-change",
                ttl=FAST,
            )
            if df.empty:
                continue
            ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
            for _, r in df.iterrows():
                t = str(r.get(ticker_col, "")).strip().upper()
                if t and not any(x["ticker"] == t for x in results):
                    results.append({"ticker": t, "color": "green"})
        if results:
            cache.put("qulla_episodic", results, ttl=FAST)
        return results
    except Exception:
        return []


# -----------------------------------------------------------------------
# 2. Parabolic Short: Up 50-100% (large cap) or 300-1000% (small cap), 3-5 up days
# -----------------------------------------------------------------------
def parabolic_short_screener() -> list[dict]:
    """Stocks up 50-100% (large cap) or 300-1000% (small cap) in days/weeks.
    Note: '3-5 up days' requires OHLCV history; we approximate with week/month chg."""
    cached = cache.get("qulla_parabolic")
    if cached is not None:
        return cached
    try:
        indicators = fetch_group_indicators(load_composite(), cache_key="ind_Composite")
        if indicators.empty:
            return []
        rows = []
        for _, r in indicators.iterrows():
            ticker = r["ticker"]
            mcap = _parse_num(str(r.get("market_cap", 0))) or 0
            week = float(r.get("week_chg") or 0) if r.get("week_chg") is not None else 0
            month = float(r.get("month_chg") or 0) if r.get("month_chg") is not None else 0
            chg = max(week, month)  # best of week/month as proxy
            if mcap >= 10e9:  # large cap: 50-100% in days/weeks
                if 50 <= chg <= 150:
                    rows.append({"ticker": ticker, "color": "orange"})
            elif mcap >= 1e9:  # mid/small cap: 200-1000%
                if 200 <= chg <= 1200:
                    rows.append({"ticker": ticker, "color": "orange"})
        if rows:
            cache.put("qulla_parabolic", rows, ttl=MEDIUM)
        return rows
    except Exception:
        return []


# -----------------------------------------------------------------------
# 3. Breakouts: Big move, pullback, range expansion
# -----------------------------------------------------------------------
def breakouts_screener() -> list[dict]:
    """Approximate: big move (30-100%+) in past 1-3 months, price surfing 10/20/50 MA.
    Note: Full setup (orderly pullback, consolidation) requires OHLCV history."""
    cached = cache.get("qulla_breakouts")
    if cached is not None:
        return cached
    try:
        indicators = fetch_group_indicators(load_composite(), cache_key="ind_Composite")
        if indicators.empty:
            return []
        rows = []
        for _, r in indicators.iterrows():
            ticker = r["ticker"]
            month = float(r.get("month_chg") or 0) if r.get("month_chg") is not None else 0
            qtr = float(r.get("qtr_chg") or 0) if r.get("qtr_chg") is not None else 0
            close = float(r.get("close", 0) or 0)
            sma20 = float(r.get("sma20", 0) or 0)
            sma50 = float(r.get("sma50", 0) or 0)
            high52 = float(r.get("high_52w", 0) or 0)
            if not close or close <= 0:
                continue
            # Big move 30-100%+ in past 1-3 months (month or quarter)
            big_move = (30 <= month <= 150) or (30 <= qtr <= 150)
            # Price near/above rising MAs (surfing)
            near_sma20 = sma20 and sma20 > 0 and 0 <= (close - sma20) / sma20 * 100 <= 10
            near_sma50 = sma50 and sma50 > 0 and 0 <= (close - sma50) / sma50 * 100 <= 15
            # Within 25% of 52w high (consolidation near highs)
            near_high = (not high52 or high52 <= 0) or (high52 - close) / high52 * 100 <= 25
            if big_move and (near_sma20 or near_sma50) and near_high:
                rows.append({"ticker": ticker, "color": "green"})
        if rows:
            cache.put("qulla_breakouts", rows, ttl=MEDIUM)
        return rows
    except Exception:
        return []


def qullamaggie_screener(indicators=None) -> list[dict]:
    """Returns merged list of all scans with tag: EP, BO, or PS."""
    ep = episodic_pivot_screener()
    para = parabolic_short_screener()
    brk = breakouts_screener()
    by_ticker: dict[str, list[str]] = {}
    for r in ep:
        by_ticker.setdefault(r["ticker"], []).append("EP")
    for r in para:
        by_ticker.setdefault(r["ticker"], []).append("PS")
    for r in brk:
        by_ticker.setdefault(r["ticker"], []).append("BO")
    return [
        {"ticker": t, "tag": ", ".join(sorted(tags)), "color": "green"}
        for t, tags in sorted(by_ticker.items(), key=lambda x: x[0])
    ]


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
