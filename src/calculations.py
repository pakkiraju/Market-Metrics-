"""Technical indicator calculations and metric aggregation."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src import cache
from src.cache import FAST, MEDIUM, SLOW
from src.data_fetcher import (
    fetch_group_indicators,
    fetch_group_indicators_from_url,
    fetch_sector_data as fetch_sector_data_raw,
    fetch_20pct_weekly_from_urls,
    fetch_4pct_daily_from_url,
)
from src.constants import SECTOR_ETFS, KEY_METRIC_ROWS

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Low-level indicator helpers
# -----------------------------------------------------------------------

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def relative_strength_pct_rank(changes: pd.Series) -> pd.Series:
    """Percentile rank (0-100) of each value within the series."""
    return changes.rank(pct=True) * 100


# -----------------------------------------------------------------------
# Per-ticker indicator computation
# -----------------------------------------------------------------------

def _scalar(val) -> float:
    """Force any value (numpy scalar, Series of len 1, etc.) to a Python float."""
    if val is None:
        return float("nan")
    if isinstance(val, pd.Series):
        if len(val) == 1:
            val = val.iloc[0]
        else:
            return float("nan")
    try:
        f = float(val)
        return f
    except (TypeError, ValueError):
        return float("nan")


def compute_indicators(df: pd.DataFrame) -> dict:
    """Given a single-ticker OHLCV DataFrame, return a dict of indicators."""
    if df.empty or len(df) < 10:
        return {}

    c = df["Close"].astype(float)
    h = df["High"].astype(float)
    lo = df["Low"].astype(float)
    v = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(dtype=float)

    last_close = _scalar(c.iloc[-1])
    prev_close = _scalar(c.iloc[-2]) if len(c) >= 2 else last_close
    last_open = _scalar(df["Open"].iloc[-1]) if "Open" in df.columns else last_close

    if np.isnan(last_close):
        return {}

    sma10 = sma(c, 10)
    sma20 = sma(c, 20)
    sma50 = sma(c, 50)
    sma200 = sma(c, 200)
    ema10 = ema(c, 10)

    atr_val = atr(h, lo, c, 14)
    atr_pct = (atr_val / c * 100) if last_close != 0 else atr_val

    high_20 = c.rolling(20).max()
    low_20 = c.rolling(20).min()
    range_20 = high_20 - low_20
    price_to_20_range = np.where(
        range_20 != 0,
        (c - low_20) / range_20 * 100,
        50,
    )

    high_52w = c.rolling(252, min_periods=50).max()
    low_52w = c.rolling(252, min_periods=50).min()

    def _safe_last(s):
        try:
            val = s.iloc[-1]
            f = _scalar(val)
            return None if np.isnan(f) else f
        except (IndexError, TypeError):
            return None

    def _pct_chg(periods):
        if len(c) > periods:
            old = _scalar(c.iloc[-(periods + 1)])
            if np.isnan(old) or old == 0:
                return float("nan")
            return float((last_close - old) / old * 100)
        return float("nan")

    h20 = _safe_last(high_20)
    l20 = _safe_last(low_20)

    return {
        "close": last_close,
        "prev_close": prev_close,
        "open": last_open,
        "day_chg": float((last_close - prev_close) / prev_close * 100) if prev_close != 0 else 0.0,
        "open_chg": float((last_close - last_open) / last_open * 100) if last_open != 0 else 0.0,
        "week_chg": _pct_chg(5),
        "month_chg": _pct_chg(21),
        "qtr_chg": _pct_chg(63),
        "half_chg": _pct_chg(126),
        "year_chg": _pct_chg(252),
        "sma10": _safe_last(sma10),
        "sma20": _safe_last(sma20),
        "sma50": _safe_last(sma50),
        "sma200": _safe_last(sma200),
        "ema10": _safe_last(ema10),
        "atr": _safe_last(atr_val),
        "atr_pct": _safe_last(atr_pct),
        "high_20": h20,
        "low_20": l20,
        "price_to_20_range": _safe_last(pd.Series(price_to_20_range, index=c.index)),
        "high_52w": _safe_last(high_52w),
        "low_52w": _safe_last(low_52w),
        "volume": _safe_last(v) if not v.empty else None,
        "avg_volume": _safe_last(v.rolling(50).mean()) if not v.empty else None,
        "new_20_high": bool(last_close >= h20) if h20 is not None else False,
        "new_20_low": bool(last_close <= l20) if l20 is not None else False,
    }


# -----------------------------------------------------------------------
# Batch indicator computation for a group of tickers
# -----------------------------------------------------------------------

def compute_group_indicators(tickers: list[str],
                             cache_key: str | None = None) -> pd.DataFrame:
    """Fetch FinViz indicators for tickers. Returns a DataFrame."""
    result = fetch_group_indicators(tickers, cache_key=cache_key)
    if not result.empty:
        numeric_cols = [c for c in result.columns
                        if c not in ("ticker",) and result[c].dtype == object]
        for col in numeric_cols:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    return result


# -----------------------------------------------------------------------
# Section 1: Key Metrics aggregation
# -----------------------------------------------------------------------

def _above_below(series: pd.Series, n: int, threshold: float = 0):
    """Return (above, below, pct). pct = above / n * 100 (percent of total stocks above)."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    above = int((s > threshold).sum())
    below = int((s <= threshold).sum())
    pct = round(above / n * 100, 1) if n > 0 else 0
    return above, below, pct


def compute_key_metrics_for_group(indicators: pd.DataFrame) -> list[dict]:
    """Produce the rows for the Key Metrics table for one index group."""
    if indicators.empty:
        return [{"above": 0, "below": 0, "pct": 0}] * len(KEY_METRIC_ROWS)

    rows = []
    n = len(indicators)

    # Day Chg
    rows.append(_above_below(indicators["day_chg"], n))
    # Open Chg (URL-fetched via ta_changeopen_u/d, placeholder here)
    rows.append(_above_below(indicators["open_chg"], n))
    # Week
    rows.append(_above_below(indicators["week_chg"].dropna(), n))
    # Month
    rows.append(_above_below(indicators["month_chg"].dropna(), n))
    # Qtr
    rows.append(_above_below(indicators["qtr_chg"].dropna(), n))
    # Half Year
    rows.append(_above_below(indicators["half_chg"].dropna(), n))
    # Year
    rows.append(_above_below(indicators["year_chg"].dropna(), n))

    # Price to SMA10/20/50/200
    for col in ["sma10", "sma20", "sma50", "sma200"]:
        valid = indicators.dropna(subset=["close", col])
        above = int((valid["close"] > valid[col]).sum())
        below = len(valid) - above
        pct = round(above / n * 100, 1) if n > 0 else 0
        rows.append((above, below, pct))

    # EMA10 > SMA20
    valid = indicators.dropna(subset=["ema10", "sma20"])
    a = int((valid["ema10"] > valid["sma20"]).sum())
    rows.append((a, len(valid) - a, round(a / n * 100, 1) if n > 0 else 0))

    # SMA20 > SMA50
    valid = indicators.dropna(subset=["sma20", "sma50"])
    a = int((valid["sma20"] > valid["sma50"]).sum())
    rows.append((a, len(valid) - a, round(a / n * 100, 1) if n > 0 else 0))

    # SMA50 > SMA200
    valid = indicators.dropna(subset=["sma50", "sma200"])
    a = int((valid["sma50"] > valid["sma200"]).sum())
    rows.append((a, len(valid) - a, round(a / n * 100, 1) if n > 0 else 0))

    # SMA20 > SMA50 > SMA200
    valid = indicators.dropna(subset=["sma20", "sma50", "sma200"])
    a = int(((valid["sma20"] > valid["sma50"]) &
             (valid["sma50"] > valid["sma200"])).sum())
    rows.append((a, len(valid) - a, round(a / n * 100, 1) if n > 0 else 0))

    # 4% Up vs 4% Down
    up4 = int((indicators["day_chg"] >= 4).sum())
    dn4 = int((indicators["day_chg"] <= -4).sum())
    rows.append((up4, dn4, round(up4 / n * 100, 1) if n > 0 else 50))

    # New 20-Day Highs
    highs = int(indicators["new_20_high"].sum())
    rows.append((highs, None, round(highs / n * 100, 1) if n > 0 else 0))

    # New 20-Day Lows
    lows = int(indicators["new_20_low"].sum())
    rows.append((lows, None, round(lows / n * 100, 1) if n > 0 else 0))

    # Stocks count
    rows.append((n, None, None))

    return [{"above": r[0], "below": r[1], "pct": r[2]} for r in rows]


def compute_key_metrics_single_group(name: str) -> list[dict]:
    """Compute key metrics for one index group. Data from FinViz screeners directly."""
    from src.constants import build_metric_screener_url
    from src.data_fetcher import fetch_group_indicators, fetch_metric_count

    groups = {
        "NQ100": ("ind_QQQE", []),
        "SPY500": ("ind_RSP", []),
        "DJIA": ("ind_DJIA", []),
        "RUS2000": ("ind_RUS2000", []),
        "$1B+": ("ind_$1B+", []),
    }
    ck, tickers = groups.get(name, (None, []))
    if not ck:
        return []

    ind = fetch_group_indicators(tickers, cache_key=ck)
    rows = compute_key_metrics_for_group(ind)
    n = len(ind) if not ind.empty else 0

    URL_FETCH_METRICS = ["Open Chg", "EMA10>SMA20", "New 20-Day Highs", "New 20-Day Lows"]
    url_fetch_indices = {m: KEY_METRIC_ROWS.index(m) for m in URL_FETCH_METRICS if m in KEY_METRIC_ROWS}

    for metric_label, row_idx in url_fetch_indices.items():
        above_url = build_metric_screener_url(name, metric_label, "above", for_export=True)
        below_url = build_metric_screener_url(name, metric_label, "below", for_export=True)
        if not above_url:
            continue
        above = fetch_metric_count(above_url, f"km_{name}_{metric_label}_above")
        if below_url:
            below = fetch_metric_count(below_url, f"km_{name}_{metric_label}_below")
        else:
            below = None
        pct = round(above / n * 100, 1) if n > 0 else 0
        rows[row_idx] = {"above": above, "below": below, "pct": pct}

    return rows


def compute_all_key_metrics() -> dict:
    """Compute key metrics for all index groups. Uses cache when full result exists."""
    import time

    groups_order = ["NQ100", "SPY500", "DJIA", "RUS2000", "$1B+"]
    cached = cache.get("all_key_metrics")
    if cached is not None:
        return cached

    result = {}
    for i, name in enumerate(groups_order):
        if i > 0:
            time.sleep(2)
        result[name] = compute_key_metrics_single_group(name)

    cache.put("all_key_metrics", result, ttl=cache.KEY_METRICS_TTL)
    return result


# -----------------------------------------------------------------------
# Section 8: Sector SPDR ETF computations
# -----------------------------------------------------------------------

def compute_sector_data() -> list[dict]:
    """Fetch sector ETF data from FinViz."""
    rows = fetch_sector_data_raw(cache_key="sector_data")
    rows.sort(key=lambda r: (r.get("atr_pct") or 0, r.get("chg", 0)), reverse=True)
    return rows


# -----------------------------------------------------------------------
# Stage Analysis
# -----------------------------------------------------------------------

def _to_float(val) -> float | None:
    """Safely convert a value to float, handling numpy scalars and None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def classify_stage(ind: dict) -> str:
    """Classify a stock into Weinstein-style stages (1, 2A, 2B, 2C, 3, 4)."""
    close = _to_float(ind.get("close"))
    sma50_val = _to_float(ind.get("sma50"))
    sma200_val = _to_float(ind.get("sma200"))
    sma20_val = _to_float(ind.get("sma20"))

    if close is None or sma50_val is None or sma200_val is None:
        return "1"

    if close < sma50_val and sma50_val < sma200_val:
        return "4"

    if close < sma50_val and sma50_val >= sma200_val:
        return "3"

    if close > sma50_val and sma50_val > sma200_val:
        if sma20_val is not None and close < sma20_val:
            return "2C"
        week_chg = _to_float(ind.get("week_chg")) or 0.0
        month_chg = _to_float(ind.get("month_chg")) or 0.0
        if week_chg > 0 and month_chg > 0:
            return "2A"
        return "2B"

    return "1"


def compute_stage_analysis(tickers: list[str],
                           cache_key: str = "stage_analysis") -> dict:
    """Return stage counts and per-ticker stages."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    indicators = compute_group_indicators([], cache_key="ind_Composite")
    if indicators.empty:
        return {"counts": {s: 0 for s in ["1", "2A", "2B", "2C", "3", "4"]},
                "tickers": []}

    stages = []
    for _, row in indicators.iterrows():
        stage = classify_stage(row.to_dict())
        stages.append({"ticker": row["ticker"], "stage": stage})

    stage_series = pd.Series([s["stage"] for s in stages])
    counts = {}
    for s in ["1", "2A", "2B", "2C", "3", "4"]:
        counts[s] = int((stage_series == s).sum())

    result = {"counts": counts, "tickers": stages}
    cache.put(cache_key, result, ttl=SLOW)
    return result


# -----------------------------------------------------------------------
# Section 9: 97 Club
# -----------------------------------------------------------------------

def compute_97_club(tickers: list[str]) -> list[dict]:
    """$1B+ stocks in top 3% relative strength across Day, Week, Month. Data from FinViz API (Overview+Performance+Technical)."""
    cached = cache.get("97_club")
    if cached is not None:
        return cached

    indicators = fetch_group_indicators([], cache_key="ind_$1B+")
    if indicators.empty:
        return []

    # Relative strength: top 3% = rank >= 97
    for col in ["day_chg", "week_chg", "month_chg"]:
        if col in indicators.columns:
            indicators[f"rs_rank_{col}"] = indicators[col].rank(pct=True, method="average") * 100

    mask = True
    for col in ["day_chg", "week_chg", "month_chg"]:
        rcol = f"rs_rank_{col}"
        if rcol in indicators.columns:
            mask = mask & (indicators[rcol] >= 97)

    valid = indicators[mask].copy()
    valid = valid.sort_values("day_chg", ascending=False).head(35)

    rows = []
    for _, r in valid.iterrows():
        avg_v = r.get("avg_volume")
        rel_v = r.get("rel_volume")
        vol = r.get("volume")
        if rel_v is None and vol and avg_v and avg_v != 0:
            rel_v = vol / avg_v
        atr_pct = r.get("atr_pct")
        rows.append({
            "ticker": r["ticker"],
            "price": r.get("close") or "",
            "change": r.get("day_chg") if r.get("day_chg") is not None else "",
            "volume": vol or "",
            "avg_vol": avg_v if avg_v is not None else "",
            "rel_vol": round(rel_v, 2) if rel_v is not None else "",
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
        })
    if rows:
        cache.put("97_club", rows, ttl=FAST)
    return rows


# -----------------------------------------------------------------------
# Section 10: 9 Million Movers
# -----------------------------------------------------------------------

def compute_9m_movers(tickers: list[str]) -> list[dict]:
    """9M+ volume, 1.25+ rel vol. Data from FinViz API (Overview+Performance+Technical) with Avg Vol, Rel Vol."""
    cached = cache.get("9m_movers")
    if cached is not None:
        return cached

    indicators = fetch_group_indicators([], cache_key="ind_9m_movers")
    if indicators.empty:
        return []

    valid = indicators.sort_values("day_chg", ascending=False).head(40)

    rows = []
    for _, r in valid.iterrows():
        avg_v = r.get("avg_volume")
        rel_v = r.get("rel_volume")
        vol = r.get("volume")
        if rel_v is None and vol and avg_v and avg_v != 0:
            rel_v = vol / avg_v
        atr_pct = r.get("atr_pct")
        rows.append({
            "ticker": r["ticker"],
            "price": r.get("close") or "",
            "change": r.get("day_chg") if r.get("day_chg") is not None else "",
            "volume": vol or "",
            "avg_vol": avg_v if avg_v is not None else "",
            "rel_vol": round(rel_v, 2) if rel_v is not None else "",
            "atr_pct": round(atr_pct, 2) if atr_pct is not None else None,
        })
    if rows:
        cache.put("9m_movers", rows, ttl=FAST)
    return rows


# -----------------------------------------------------------------------
# Section 11: 20% Weekly Movers
# -----------------------------------------------------------------------

def compute_20pct_weekly(tickers: list[str]) -> list[dict]:
    """20% weekly movers from FinViz ta_perf_1w20o (up) and ta_perf_1w20u (down) URLs."""
    return fetch_20pct_weekly_from_urls(ttl=FAST)


# -----------------------------------------------------------------------
# Section 12: 4% Daily Gainers
# -----------------------------------------------------------------------

def compute_4pct_daily(tickers: list[str]) -> list[dict]:
    """4% daily gainers from FinViz ta_perf_4to-d URL (all US stocks, not just composite indices)."""
    rows = fetch_4pct_daily_from_url(ttl=FAST)
    for r in rows:
        r["chg"] = r.get("change", "")
    def _chg_val(r):
        v = r.get("chg") or r.get("change") or ""
        try:
            return float(str(v).replace("%", "").replace(",", "")) if v else 0
        except (ValueError, TypeError):
            return 0
    rows.sort(key=_chg_val, reverse=True)
    return rows


# -----------------------------------------------------------------------
# Section 13: Leading Industries
# -----------------------------------------------------------------------

def compute_leading_industries(tickers: list[str],
                               industry_map: dict[str, str]) -> list[dict]:
    """Top 20% industries by weekly+monthly strength."""
    cached = cache.get("leading_industries")
    if cached is not None:
        return cached

    indicators = compute_group_indicators([], cache_key="ind_Composite")
    if indicators.empty:
        return []

    if industry_map:
        indicators["industry"] = indicators["ticker"].map(industry_map)
    elif "industry" not in indicators.columns:
        indicators["industry"] = indicators.get("sector", pd.Series(dtype=str))
    indicators["industry"] = indicators["industry"].fillna("").astype(str).str.strip()
    indicators = indicators[indicators["industry"] != ""]

    grouped = indicators.groupby("industry").agg(
        week_avg=("week_chg", "mean"),
        month_avg=("month_chg", "mean"),
    ).reset_index()

    grouped["week_rank"] = grouped["week_avg"].rank(pct=True)
    grouped["month_rank"] = grouped["month_avg"].rank(pct=True)

    top_20_week = set(grouped[grouped["week_rank"] >= 0.80]["industry"])
    top_20_month = set(grouped[grouped["month_rank"] >= 0.80]["industry"])
    top_industries = top_20_week | top_20_month

    grouped = grouped[grouped["industry"].isin(top_industries)]
    grouped = grouped.sort_values("week_avg", ascending=False)

    rows = []
    for _, g in grouped.iterrows():
        ind_name = g["industry"]
        both = ind_name in top_20_week and ind_name in top_20_month
        ind_tickers = indicators[indicators["industry"] == ind_name]
        top4 = ind_tickers.nlargest(4, "day_chg")["ticker"].tolist()
        while len(top4) < 4:
            top4.append("—")
        rows.append({
            "industry": ind_name,
            "top_both": both,
            "t1": top4[0], "t2": top4[1], "t3": top4[2], "t4": top4[3],
        })

    cache.put("leading_industries", rows, ttl=SLOW)
    return rows
