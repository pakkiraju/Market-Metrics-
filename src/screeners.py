"""Qullamaggie-inspired screeners and placeholders.

Each screener returns a list of dicts with at minimum a 'ticker' key
and an optional 'color' key (green/yellow/orange/red/blue).
"""

import pandas as pd

from src.data_fetcher import (
    _get_csv_val,
    load_watchlist,
    fetch_group_indicators,
    fetch_screener_from_url,
)
from src import cache
from src.cache import MEDIUM


def _get_atr_pct_from_row(row: dict) -> float | None:
    """Extract ATR % from FinViz Technical row. Tries multiple column names."""
    atr = _parse_num(_get_csv_val(row, "ATR", "ATR (14)", "ATR(14)", "atr", "Average True Range"))
    if atr is None:
        for k, v in row.items():
            if "atr" in str(k).lower() and "average" not in str(k).lower():
                atr = _parse_num(v)
                break
    price = _parse_num(_get_csv_val(row, "Price", "price", "Last", "Close"))
    return round((atr / price * 100), 2) if atr and price and price != 0 else None


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
    """Gap up 10%+ with above-average volume (rel vol 2+). US-wide. Single export URL with c= for all columns."""
    cached = cache.get("qulla_episodic_v2")
    if cached is not None:
        return cached
    try:
        rows = fetch_screener_from_url("qulla_episodic", "qulla_ep_usa", ttl=MEDIUM)
        for r in rows:
            r["tag"] = "EP"
        if rows:
            cache.put("qulla_episodic_v2", rows, ttl=MEDIUM)
        return rows
    except Exception:
        return []


# -----------------------------------------------------------------------
# 2. Parabolic Short: Large cap 50-100%, Small cap 300-1000% (FinViz screeners)
# -----------------------------------------------------------------------
def parabolic_short_screener() -> list[dict]:
    """Parabolic Short via FinViz: large cap Month +50%, small cap Year +300%. Single URL per filter set."""
    cached = cache.get("qulla_parabolic_v2")
    if cached is not None:
        return cached
    try:
        rows = []
        seen = set()
        for url_key, cache_key in [
            ("qulla_ps_large", "qulla_ps_large"),
            ("qulla_ps_small", "qulla_ps_small"),
        ]:
            data = fetch_screener_from_url(url_key, cache_key, ttl=MEDIUM)
            for r in data:
                t = r.get("ticker", "").strip().upper()
                if not t or t in seen:
                    continue
                seen.add(t)
                rows.append({**r, "tag": "PS"})
        if rows:
            cache.put("qulla_parabolic_v2", rows, ttl=MEDIUM)
        return rows
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("parabolic_short_screener failed: %s", e)
        return []


# -----------------------------------------------------------------------
# 3. Breakouts: FinViz screener (52w high 0-25%, perf 30d to -4w, price above SMA20)
# -----------------------------------------------------------------------
def breakouts_screener() -> list[dict]:
    """Breakouts via FinViz: within 25% of 52w high, 30d perf -4% to 30%, price above SMA20. Single export URL."""
    cached = cache.get("qulla_breakouts_v2")
    if cached is not None:
        return cached
    try:
        rows = fetch_screener_from_url("qulla_breakouts", "qulla_breakouts", ttl=MEDIUM)
        for r in rows:
            r["tag"] = "BO"
        if rows:
            cache.put("qulla_breakouts_v2", rows, ttl=MEDIUM)
        return rows
    except Exception:
        return []


def qullamaggie_screener(indicators=None) -> list[dict]:
    """Returns merged list of all scans with tag: EP, BO, or PS. Same columns as Minervini + Tag."""
    ep = episodic_pivot_screener()
    para = parabolic_short_screener()
    brk = breakouts_screener()
    by_ticker: dict[str, dict] = {}
    for r in ep:
        t = r["ticker"]
        if t not in by_ticker:
            by_ticker[t] = {**r, "tag": "EP"}
        else:
            by_ticker[t]["tag"] = ", ".join(sorted(set(by_ticker[t]["tag"].split(", ") + ["EP"])))
    for r in para:
        t = r["ticker"]
        if t not in by_ticker:
            by_ticker[t] = {**r, "tag": "PS"}
        else:
            by_ticker[t]["tag"] = ", ".join(sorted(set(by_ticker[t]["tag"].split(", ") + ["PS"])))
    for r in brk:
        t = r["ticker"]
        if t not in by_ticker:
            by_ticker[t] = {**r, "tag": "BO"}
        else:
            by_ticker[t]["tag"] = ", ".join(sorted(set(by_ticker[t]["tag"].split(", ") + ["BO"])))
    # Sort by change descending (biggest gainers first)
    def _chg(r):
        v = r.get("change")
        if v is None or v == "":
            return 0.0
        try:
            return float(str(v).replace("%", "").replace(",", "")) or 0
        except (ValueError, TypeError):
            return 0.0
    return sorted([by_ticker[t] for t in by_ticker], key=_chg, reverse=True)


def minervini_screener(indicators=None) -> list[dict]:
    """Minervini Trend Template screener. Single export URL with c= for all columns (incl. ATR)."""
    cached = cache.get("minervini_table")
    if cached is not None:
        return cached
    try:
        rows = fetch_screener_from_url("minervini", "minervini_table", ttl=MEDIUM)
        if rows:
            return rows

        # Fallback: Python filtering (no Elite or tad_* not supported)
        indicators = fetch_group_indicators([], cache_key="ind_USA")
        if indicators.empty:
            return []

        valid = indicators.dropna(subset=["close", "sma50", "sma200", "low_52w", "high_52w"]).copy()
        if valid.empty:
            return []

        for period in ["month_chg", "week_chg"]:
            if period in valid.columns:
                valid[f"rs_rank_{period}"] = valid[period].rank(pct=True, method="average") * 100

        rows = []
        for _, r in valid.iterrows():
            close = float(r.get("close", 0) or 0)
            sma50 = float(r.get("sma50", 0) or 0)
            sma200 = float(r.get("sma200", 0) or 0)
            low52 = float(r.get("low_52w", 0) or 0)
            high52 = float(r.get("high_52w", 0) or 0)

            if not close or close <= 0 or not sma50 or not sma200:
                continue

            sma150_approx = (sma50 + sma200) / 2
            if close <= sma150_approx or close <= sma200 or sma150_approx <= sma200:
                continue
            if sma50 <= sma150_approx or sma50 <= sma200 or close <= sma50:
                continue
            # Close must be at least 30% above 52-week low (30 or above), not within 30% of low
            if low52 <= 0 or (close - low52) / low52 < 0.30:
                continue
            if high52 <= 0 or (high52 - close) / high52 > 0.25:
                continue
            if float(r.get("rs_rank_month_chg") or 0) < 70:
                continue

            atr_pct = r.get("atr_pct")
            rows.append({
                "ticker": r["ticker"],
                "price": r.get("close"),
                "avg_vol": r.get("avg_volume"),
                "rel_vol": r.get("rel_volume"),
                "change": r.get("day_chg"),
                "volume": r.get("volume"),
                "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
            })

        if rows:
            cache.put("minervini_table", rows, ttl=MEDIUM)
        return rows
    except Exception:
        return []


def _parse_pct(val) -> float | None:
    """Parse percentage string (e.g. '25.5%', '25.5', '-') to float or None."""
    if val is None or val == "" or str(val).strip() in ("-", "—"):
        return None
    s = str(val).strip().replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def oneil_screener(indicators=None) -> list[dict]:
    """O'Neil / CANSLIM screener. Single export URL with c= for all columns. Filters ROE + Net Margin >= 25%."""
    from src.data_fetcher import fetch_oneil_from_url
    return fetch_oneil_from_url(cache_key="oneil_table", ttl=MEDIUM)


def watchlist_tickers() -> list[dict]:
    """Load personal watchlist from config CSV."""
    tickers = load_watchlist()
    return [{"ticker": t, "color": "green"} for t in tickers]
