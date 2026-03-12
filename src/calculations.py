"""Technical indicator calculations and metric aggregation."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src import cache
from src.cache import FAST, MEDIUM
from src.data_fetcher import (
    fetch_group_indicators,
    fetch_industry_map_from_overview,
    fetch_sector_data as fetch_sector_data_raw,
    fetch_20pct_weekly_from_urls,
    fetch_4pct_daily_from_url,
    fetch_earnings_yesterday_today,
    fetch_screener_from_url,
    fetch_benchmark_performance,
    fetch_thematics_data,
)
from src.constants import SECTOR_ETFS, SECTOR_SPDRS_RRG, RRG_BENCHMARK, SECTOR_NAMES, KEY_METRIC_ROWS

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
        "NQ100": ("ind_NQ100", []),
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

    # Price to SMA, EMA>SMA, SMA>SMA, New 20-Day High/Low: use existing URLs (unchanged). Do not compute from base export.
    URL_FETCH_METRICS = [
        "Open Chg",
        "Price to SMA10", "Price to SMA20", "Price to SMA50", "Price to SMA200",
        "EMA10>SMA20", "SMA20<SMA50", "SMA50<SMA200", "SMA20<SMA50<SMA200",
        "New 20-Day Highs", "New 20-Day Lows",
    ]
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
    """Compute key metrics for all index groups. Fetches all URLs, caches full result, returns when done."""
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
# RRG (Relative Rotation Graph) — Sector SPDRs and Thematics vs VTI
# Same math for both: RS-Ratio = year outperformance vs VTI; RS-Momentum = qtr outperformance.
# Normalize to ~100 baseline (mean=100, spread by std*10).
# -----------------------------------------------------------------------

def _normalize_rrg_rows(rows: list[dict]) -> None:
    """Apply same RRG normalization as sector SPDRs. Mutates rows in place."""
    if not rows:
        return
    ratio_vals = np.array([x["rs_ratio_raw"] for x in rows])
    mom_vals = np.array([x["rs_momentum_raw"] for x in rows])
    r_mean, r_std = ratio_vals.mean(), max(ratio_vals.std(), 1e-6)
    m_mean, m_std = mom_vals.mean(), max(mom_vals.std(), 1e-6)

    def _norm_r(v):
        return float(100 + (v - r_mean) / r_std * 10)

    def _norm_m(v):
        return float(100 + (v - m_mean) / m_std * 10)

    for i, row in enumerate(rows):
        row["rs_ratio"] = _norm_r(ratio_vals[i])
        row["rs_momentum"] = _norm_m(mom_vals[i])
        del row["rs_ratio_raw"]
        del row["rs_momentum_raw"]


def compute_rrg_data(
    benchmark: str = RRG_BENCHMARK,
    cache_key: str = "rrg_data",
) -> list[dict]:
    """Compute RRG points from sector SPDR data vs VTI. Uses fetch_sector_data + fetch_benchmark_performance."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sector_rows = fetch_sector_data_raw(cache_key="sector_data")
    vti = fetch_benchmark_performance(benchmark=benchmark)
    if not vti:
        return []

    vti_qtr = vti.get("qtr") or 0.0
    vti_year = vti.get("year") or 0.0

    sector_by_ticker = {r["ticker"]: r for r in sector_rows}
    rows = []
    for t in SECTOR_SPDRS_RRG:
        r = sector_by_ticker.get(t)
        if not r:
            continue
        year_val = r.get("year") or 0.0
        qtr_val = r.get("qtr") or 0.0
        rows.append({
            "ticker": t,
            "name": SECTOR_NAMES.get(t, t),
            "rs_ratio_raw": year_val - vti_year,
            "rs_momentum_raw": qtr_val - vti_qtr,
        })

    if not rows:
        return []

    _normalize_rrg_rows(rows)
    cache.put(cache_key, rows, ttl=MEDIUM)
    return rows


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


def _within_pct(close: float, ma: float, pct: float = 0.25) -> bool:
    """True if close is within pct (e.g. 25%) of ma: 0.75*ma <= close <= 1.25*ma."""
    if ma is None or ma <= 0:
        return False
    lo, hi = (1 - pct) * ma, (1 + pct) * ma
    return lo <= close <= hi


def classify_stage(ind: dict) -> str:
    """Classify into stages 1A/1B/2A/2B/2C/3A/3B/4A/4B/4C using price, EMA10, SMA20, SMA50."""
    close = _to_float(ind.get("close"))
    ema10 = _to_float(ind.get("ema10"))
    sma20 = _to_float(ind.get("sma20"))
    sma50 = _to_float(ind.get("sma50"))

    if close is None or sma50 is None or sma50 <= 0:
        return "1A"
    if ema10 is None:
        ema10 = sma20 if sma20 is not None else sma50
    if sma20 is None:
        sma20 = ema10 if ema10 is not None else sma50
    if ema10 is None or sma20 is None:
        return "1A"

    ext = close / sma50  # extension from SMA50

    # Above all MAs (ext = close/sma50; 5%/6%/7% above = 1.05/1.06/1.07)
    if close > ema10 and close > sma20 and close > sma50:
        if ext >= 1.07:
            return "2C"   # 7%+ above SMA50
        if ext >= 1.06:
            return "2B"   # 6–7% above
        if ext >= 1.05:
            return "2A"   # 5–6% above
        return "1B"       # above MAs but within 5% of SMA50

    # Below all MAs (ext = close/sma50; 5%/6%/7% below = 0.95/0.94/0.93)
    if close < ema10 and close < sma20 and close < sma50:
        if ext <= 0.93:
            return "4C"   # 7%+ below SMA50
        if ext <= 0.94:
            return "4B"   # 6–7% below
        if ext <= 0.95:
            return "4A"   # 5–6% below
        return "3B"       # 0.95 < ext < 1 (within 5% of SMA50, just below)

    # Above SMA50 but below EMA10/SMA20 (distribution)
    if close > sma50 and close < ema10:
        if _within_pct(close, ema10, 0.25) and _within_pct(close, sma20, 0.25):
            return "3A"
        return "3A"  # fallback for distribution above sma50

    # Below SMA50, within 25% of EMA10 and SMA20 (basing)
    if close < sma50 and _within_pct(close, ema10, 0.25) and _within_pct(close, sma20, 0.25):
        return "1A"

    return "1A"


def compute_stage_analysis(tickers: list[str],
                           cache_key: str = "stage_analysis") -> dict:
    """Return stage counts and per-ticker stages. Fetches from export.ashx (geo_usa, avgvol 1000+, price $1+), does stage math."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from src.data_fetcher import fetch_stage_indicators
    indicators = fetch_stage_indicators(cache_key="ind_stage")
    if indicators.empty:
        return {"counts": {s: 0 for s in ["1A", "1B", "2A", "2B", "2C", "3A", "3B", "4A", "4B", "4C"]},
                "tickers": []}

    stages = []
    for _, row in indicators.iterrows():
        stage = classify_stage(row.to_dict())
        stages.append({"ticker": row["ticker"], "stage": stage})

    stage_series = pd.Series([s["stage"] for s in stages])
    counts = {}
    for s in ["1A", "1B", "2A", "2B", "2C", "3A", "3B", "4A", "4B", "4C"]:
        counts[s] = int((stage_series == s).sum())

    result = {"counts": counts, "tickers": stages}
    cache.put(cache_key, result, ttl=MEDIUM)
    return result


# -----------------------------------------------------------------------
# Section 9: 97 Club
# -----------------------------------------------------------------------

def compute_97_club(tickers: list[str]) -> list[dict]:
    """$1B+ stocks in top 3% relative strength across Day, Week, Month. Data from FinViz API (Overview+Performance+Technical)."""
    cached = cache.get("97_club")
    if cached is not None and len(cached) > 0:
        if any(r.get("atr_pct") is not None for r in cached[:5]):
            return cached
        cache.invalidate("97_club")

    indicators = fetch_group_indicators([], cache_key="ind_$1B+")
    if indicators.empty:
        return []

    # Work on copy to avoid mutating cached DataFrame
    indicators = indicators.copy()

    # Relative strength: top 3% = percentile rank >= 0.97 (same scale as leading industries/thematics)
    for col in ["day_chg", "week_chg", "month_chg"]:
        if col in indicators.columns:
            indicators[f"rs_rank_{col}"] = indicators[col].rank(pct=True, method="average")

    mask = True
    for col in ["day_chg", "week_chg", "month_chg"]:
        rcol = f"rs_rank_{col}"
        if rcol in indicators.columns:
            mask = mask & (indicators[rcol] >= 0.97)

    valid = indicators[mask].copy()
    valid = valid.sort_values("day_chg", ascending=False).head(35)

    # Enrich ATR% if missing (ind_1b v=141 may omit ATR with many columns)
    if valid["atr_pct"].isna().all() and len(valid) > 0:
        from src.data_fetcher import fetch_tickers_bulk_csv
        tickers = valid["ticker"].tolist()
        bulk = fetch_tickers_bulk_csv(tickers, cache_key=f"97_club_atr_{','.join(sorted(tickers))}")
        atr_map = {r["ticker"]: r.get("atr_pct") for r in bulk if r.get("atr_pct") is not None}
        if atr_map:
            valid["atr_pct"] = valid["ticker"].map(atr_map)

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
    # Ensure change descending (biggest gainers first)
    def _chg_val(r):
        v = r.get("change")
        if v is None: return 0.0
        if isinstance(v, (int, float)): return float(v)
        try: return float(str(v).replace("%", "").replace(",", "")) or 0
        except (ValueError, TypeError): return 0.0
    rows.sort(key=_chg_val, reverse=True)
    if rows:
        cache.put("97_club", rows, ttl=MEDIUM)
    return rows


# -----------------------------------------------------------------------
# Section 10: 9 Million Movers
# -----------------------------------------------------------------------

def compute_9m_movers(tickers: list[str]) -> list[dict]:
    """9M+ volume, 1.25+ rel vol. Data from FinViz API (Overview+Performance+Technical) with Avg Vol, Rel Vol."""
    cached = cache.get("9m_movers")
    if cached is not None:
        if any(r.get("atr_pct") is not None for r in cached[:5]):
            return cached
        cache.invalidate("9m_movers")

    indicators = fetch_group_indicators([], cache_key="ind_9m_movers")
    if indicators.empty:
        return []

    valid = indicators.sort_values("day_chg", ascending=False).head(40)

    # Enrich ATR% if missing (ind_9m v=141 may omit ATR with many columns)
    if valid["atr_pct"].isna().all() and len(valid) > 0:
        from src.data_fetcher import fetch_tickers_bulk_csv
        tickers = valid["ticker"].tolist()
        bulk = fetch_tickers_bulk_csv(tickers, cache_key=f"9m_atr_{','.join(sorted(tickers))}")
        atr_map = {r["ticker"]: r.get("atr_pct") for r in bulk if r.get("atr_pct") is not None}
        if atr_map:
            valid["atr_pct"] = valid["ticker"].map(atr_map)

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
        cache.put("9m_movers", rows, ttl=MEDIUM)
    return rows


# -----------------------------------------------------------------------
# Section 11: 20% Weekly Movers
# -----------------------------------------------------------------------

def compute_20pct_weekly(tickers: list[str]) -> list[dict]:
    """20% weekly movers from FinViz ta_perf_1w20o (up) and ta_perf_1w20u (down) URLs."""
    return fetch_20pct_weekly_from_urls(ttl=MEDIUM)


# -----------------------------------------------------------------------
# Section 12: 4% Daily Gainers
# -----------------------------------------------------------------------

def compute_earnings_yesterday_today(tickers: list[str]) -> list[dict]:
    """Earnings yesterday or today from FinViz. USA, avg vol 1K+, price $1+. Merges Performance view for avg_vol/rel_vol."""
    return fetch_earnings_yesterday_today(ttl=MEDIUM)


def compute_stocks_in_play(tickers: list[str]) -> list[dict]:
    """Stocks In Play: news yesterday|today, avg vol 1K+, price $1+, rel vol 2+. Sorted by change desc.
    Uses v=141 with c=1,137,47,61,62,63,64,65 for Ticker,News/Link,ATR,AvgVol,RelVol,Price,Change,Volume."""
    return fetch_screener_from_url("stocks_in_play", "stocks_in_play", ttl=MEDIUM)


def compute_4pct_daily(tickers: list[str]) -> list[dict]:
    """4% daily gainers from FinViz ta_perf_4to-d URL (all US stocks, not just composite indices)."""
    rows = fetch_4pct_daily_from_url(ttl=MEDIUM)
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
    """Top 20% industries by weekly+monthly relative strength. Data from FinViz: $1B+, USA, RSI>60.
    Green = top 20% on BOTH weekly and monthly RS. Shows 4 best-performing stocks for the day per industry."""
    cached = cache.get("leading_industries")
    if cached is not None:
        return cached

    # Use ind_$1B+ (same universe as 97 Club). ind_1b export includes Industry/Sector, so no need for club97 URL.
    indicators = compute_group_indicators([], cache_key="ind_$1B+")
    if indicators.empty:
        cache.put("leading_industries", [], ttl=FAST)  # cache empty to avoid refetching every interval
        return []

    # Industry from ind_1b (has Industry, Sector). Only fetch club97 if indicators lacks industry.
    if industry_map:
        indicators["industry"] = indicators["ticker"].map(industry_map)
    elif "industry" in indicators.columns and indicators["industry"].fillna("").astype(str).str.strip().str.len().gt(0).any():
        pass  # Use industry from ind_1b — avoids redundant club97 URL (same filters as ind_1b)
    else:
        overview_map = fetch_industry_map_from_overview()
        if overview_map:
            indicators["industry"] = indicators["ticker"].map(overview_map)
        else:
            indicators["industry"] = indicators.get("sector", pd.Series(dtype=str))
    # Fill empty with sector, then "Uncategorized"
    indicators["industry"] = indicators["industry"].fillna("").astype(str).str.strip()
    sector_fallback = indicators.get("sector", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    indicators["industry"] = indicators["industry"].where(indicators["industry"] != "", sector_fallback)
    indicators["industry"] = indicators["industry"].where(indicators["industry"] != "", "Uncategorized")
    indicators = indicators[indicators["industry"] != ""]

    grouped = indicators.groupby("industry").agg(
        week_avg=("week_chg", "mean"),
        month_avg=("month_chg", "mean"),
    ).reset_index()

    grouped["week_rank"] = grouped["week_avg"].rank(pct=True)
    grouped["month_rank"] = grouped["month_avg"].rank(pct=True)

    top_20_week = set(grouped[grouped["week_rank"] >= 0.80]["industry"].dropna())
    top_20_month = set(grouped[grouped["month_rank"] >= 0.80]["industry"].dropna())
    top_industries = top_20_week | top_20_month
    # If ranks are all NaN (e.g. missing Perf Week/Month), show all industries by week strength
    if not top_industries:
        top_industries = set(grouped["industry"].dropna())

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

    if rows:
        cache.put("leading_industries", rows, ttl=MEDIUM)
    return rows


# -----------------------------------------------------------------------
# Section 14: Thematics Tracker
# -----------------------------------------------------------------------

def compute_thematics(tickers: list[str]) -> list[dict]:
    """Top 20% themes by weekly+monthly relative strength. USA, avg vol 1K+, price $1+.
    Green = top 20% on BOTH weekly and monthly. Shows top 4 stocks per theme by day change."""
    cached = cache.get("thematics")
    if cached is not None:
        return cached

    indicators = fetch_thematics_data(cache_key="thematics_data", ttl=MEDIUM)
    if not isinstance(indicators, pd.DataFrame) or indicators.empty:
        cache.invalidate("thematics_data")
        cache.invalidate("thematics")  # Don't persist empty; retry on next refresh
        return []

    indicators["theme"] = indicators["theme"].fillna("").astype(str).str.strip()
    indicators = indicators[indicators["theme"] != ""]
    indicators["theme"] = indicators["theme"].where(indicators["theme"] != "", "Uncategorized")

    grouped = indicators.groupby("theme").agg(
        week_avg=("week_chg", "mean"),
        month_avg=("month_chg", "mean"),
    ).reset_index()

    grouped["week_rank"] = grouped["week_avg"].rank(pct=True)
    grouped["month_rank"] = grouped["month_avg"].rank(pct=True)

    top_20_week = set(grouped[grouped["week_rank"] >= 0.80]["theme"].dropna())
    top_20_month = set(grouped[grouped["month_rank"] >= 0.80]["theme"].dropna())
    top_themes = top_20_week | top_20_month
    if not top_themes:
        top_themes = set(grouped["theme"].dropna())

    grouped = grouped[grouped["theme"].isin(top_themes)]
    grouped = grouped.sort_values("week_avg", ascending=False)

    rows = []
    for _, g in grouped.iterrows():
        theme_name = g["theme"]
        both = theme_name in top_20_week and theme_name in top_20_month
        theme_tickers = indicators[indicators["theme"] == theme_name]
        top4 = theme_tickers.nlargest(4, "day_chg", keep="first")["ticker"].tolist()
        while len(top4) < 4:
            top4.append("—")
        rows.append({
            "theme": theme_name,
            "top_both": both,
            "t1": top4[0], "t2": top4[1], "t3": top4[2], "t4": top4[3],
        })

    if rows:
        cache.put("thematics", rows, ttl=MEDIUM)
    else:
        cache.invalidate("thematics")  # Don't persist empty; retry on next refresh
    return rows


def compute_thematics_sector_data(cache_key: str = "thematics_sector_data") -> list[dict]:
    """Thematics aggregated by theme (industry), Sector SPDR-style: Chg, O Chg, Week, Month, Qtr, H.Year, Year.
    Uses ind_USA (same as Thematics Tracker) for Industry/Sector. Filtered by top YTD (year) change. Feeds RRG."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    indicators = fetch_group_indicators([], cache_key="ind_USA")
    if indicators.empty:
        return []

    # Theme = industry (sector fallback)
    ind = indicators.get("industry", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    sec = indicators.get("sector", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    ind_valid = (ind.str.len() > 0) & (ind != "-") & (ind != "")
    sec_valid = (sec.str.len() > 0) & (sec != "-") & (sec != "")
    indicators = indicators.copy()
    indicators["theme"] = ind.where(ind_valid, sec.where(sec_valid, "Uncategorized"))

    grouped = indicators.groupby("theme").agg(
        chg=("day_chg", "mean"),
        ochg=("open_chg", "mean"),
        week=("week_chg", "mean"),
        month=("month_chg", "mean"),
        qtr=("qtr_chg", "mean"),
        hyear=("half_chg", "mean"),
        year=("year_chg", "mean"),
    ).reset_index()

    # Filter themes with 3+ stocks; sort by YTD (year) descending; top 30
    theme_counts = indicators.groupby("theme").size()
    grouped = grouped[grouped["theme"].map(theme_counts) >= 3]
    grouped = grouped.sort_values("year", ascending=False, na_position="last").head(30)

    rows = []
    for _, g in grouped.iterrows():
        def _r(val):
            v = g.get(val)
            return round(float(v), 1) if v is not None and not pd.isna(v) else 0.0
        rows.append({
            "theme": g["theme"],
            "chg": _r("chg"),
            "ochg": _r("ochg"),
            "week": _r("week"),
            "month": _r("month"),
            "qtr": _r("qtr"),
            "hyear": _r("hyear"),
            "year": _r("year"),
        })

    if rows:
        cache.put(cache_key, rows, ttl=MEDIUM)
    return rows


def compute_thematics_rrg_data(
    benchmark: str = RRG_BENCHMARK,
    cache_key: str = "thematics_rrg_data",
) -> list[dict]:
    """RRG for themes vs VTI. Same math as sector SPDR RRG: RS-Ratio = year vs VTI, RS-Momentum = qtr vs VTI.
    Uses thematics_sector_data (same source as Thematics by Sector table) for consistency."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sector_rows = compute_thematics_sector_data()
    if not sector_rows:
        return []

    vti = fetch_benchmark_performance(benchmark=benchmark)
    if not vti:
        return []

    vti_qtr = vti.get("qtr") or 0.0
    vti_year = vti.get("year") or 0.0

    rows = []
    for r in sector_rows:
        year_val = r.get("year") or 0.0
        qtr_val = r.get("qtr") or 0.0
        theme = r.get("theme", "")
        short_label = (theme[:12] + "..") if len(theme) > 12 else theme
        rows.append({
            "ticker": short_label,
            "name": theme,
            "rs_ratio_raw": year_val - vti_year,
            "rs_momentum_raw": qtr_val - vti_qtr,
        })

    if not rows:
        return []

    _normalize_rrg_rows(rows)
    cache.put(cache_key, rows, ttl=MEDIUM)
    return rows
