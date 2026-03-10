"""Fetch market data from FinViz via the unofficial finviz Python API.

Replaces yfinance. Uses finviz Screener for bulk data and get_stock for
individual tickers. FinViz data is delayed ~15-20 min.
"""

import logging
import re
from pathlib import Path

import pandas as pd

import finviz
from finviz.screener import Screener

from src import cache
from src.cache import FAST, MEDIUM, SLOW

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


# ---------------------------------------------------------------------------
# Config loaders (unchanged)
# ---------------------------------------------------------------------------

def _load_tickers(filename: str) -> list[str]:
    path = CONFIG_DIR / filename
    if not path.exists():
        logger.warning("Config file not found: %s", path)
        return []
    df = pd.read_csv(path)
    col = df.columns[0]
    return df[col].dropna().str.strip().tolist()


def load_nasdaq100() -> list[str]:
    return _load_tickers("nasdaq100.csv")


def load_sp500() -> list[str]:
    return _load_tickers("sp500.csv")


def load_djia() -> list[str]:
    return _load_tickers("djia.csv")


def load_watchlist() -> list[str]:
    return _load_tickers("watchlist.csv")


def load_sectors() -> pd.DataFrame:
    path = CONFIG_DIR / "sectors.csv"
    return pd.read_csv(path)


def load_composite() -> list[str]:
    """Combined unique tickers from NASDAQ-100 + S&P 500 + DJIA."""
    tickers = set(load_nasdaq100()) | set(load_sp500()) | set(load_djia())
    return sorted(tickers)


# ---------------------------------------------------------------------------
# FinViz helpers
# ---------------------------------------------------------------------------

def _parse_pct(s: str) -> float:
    """Parse percentage string like '5.2%' or '-3.1%' to float."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return float("nan")
    s = str(s).strip().replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _parse_num(s: str) -> float | None:
    """Parse numeric string, handling K/M/B suffixes."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
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


def _screener_to_df(screener: Screener) -> pd.DataFrame:
    """Convert Screener result to DataFrame."""
    if not screener.data:
        return pd.DataFrame()
    return pd.DataFrame(screener.data)


def _fetch_screener(filters: list[str], table: str, cache_key: str | None = None,
                    order: str = "", ttl: int = MEDIUM) -> pd.DataFrame:
    """Run FinViz Screener and return DataFrame. Cached."""
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        s = Screener(filters=filters, table=table, order=order)
        df = _screener_to_df(s)
        if cache_key and not df.empty:
            cache.put(cache_key, df, ttl=ttl)
        return df
    except Exception as e:
        logger.warning("FinViz Screener failed: %s", e)
        return pd.DataFrame()


def _merge_perf_tech(perf_df: pd.DataFrame, tech_df: pd.DataFrame) -> pd.DataFrame:
    """Merge Performance and Technical DataFrames on Ticker."""
    if perf_df.empty and tech_df.empty:
        return pd.DataFrame()
    if perf_df.empty:
        return tech_df
    if tech_df.empty:
        return perf_df

    ticker_col = "Ticker" if "Ticker" in perf_df.columns else "ticker"
    if ticker_col not in perf_df.columns or ticker_col not in tech_df.columns:
        return perf_df if not perf_df.empty else tech_df

    merged = perf_df.merge(
        tech_df,
        on=ticker_col,
        how="outer",
        suffixes=("", "_tech"),
    )
    for c in merged.columns:
        if c.endswith("_tech"):
            base = c.replace("_tech", "")
            if base in merged.columns and merged[base].isna().all():
                merged[base] = merged[c]
            merged = merged.drop(columns=[c])
    return merged


# ---------------------------------------------------------------------------
# Indicator-style DataFrame (compatible with calculations.py)
# ---------------------------------------------------------------------------

def _fetch_screener_multi(filter_sets: list[list[str]], table: str,
                          cache_key: str | None, order: str = "",
                          ttl: int = MEDIUM) -> pd.DataFrame:
    """Run multiple Screener calls (e.g. idx_sp500 + idx_ndx) and merge."""
    dfs = []
    seen = set()
    for i, filters in enumerate(filter_sets):
        ck = f"{cache_key}_{i}_{table}" if cache_key else None
        df = _fetch_screener(filters=filters, table=table, cache_key=ck, order=order, ttl=ttl)
        if df.empty:
            continue
        ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
        for _, row in df.iterrows():
            t = str(row.get(ticker_col, "")).strip().upper()
            if t and t not in seen:
                seen.add(t)
                dfs.append(row)
    if not dfs:
        return pd.DataFrame()
    return pd.DataFrame(dfs)


def fetch_group_indicators(tickers: list[str], cache_key: str | None = None) -> pd.DataFrame:
    """
    Fetch FinViz data for tickers and return a DataFrame in the format
    expected by compute_key_metrics_for_group and related functions.
    """
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    # FinViz: idx_sp500 = S&P 500, idx_ndx = NASDAQ 100. Use separate calls for composite.
    filter_sets_by_group = {
        "ind_QQQE": [["idx_ndx"]],
        "ind_RSP": [["idx_sp500"]],
        "ind_Composite": [["idx_sp500"], ["idx_ndx"]],
    }
    filter_sets = filter_sets_by_group.get(cache_key, [["idx_sp500"], ["idx_ndx"]])

    overview_df = _fetch_screener_multi(
        filter_sets, "Overview",
        cache_key=f"{cache_key}_overview" if cache_key else None,
        order="-change",
        ttl=MEDIUM,
    )
    perf_df = _fetch_screener_multi(
        filter_sets, "Performance",
        cache_key=f"{cache_key}_perf" if cache_key else None,
        order="-change",
        ttl=MEDIUM,
    )
    tech_df = _fetch_screener_multi(
        filter_sets, "Technical",
        cache_key=f"{cache_key}_tech" if cache_key else None,
        order="-change",
        ttl=MEDIUM,
    )
    merged = _merge_perf_tech(overview_df, perf_df)
    merged = _merge_perf_tech(merged, tech_df)

    if merged.empty:
        return pd.DataFrame()

    ticker_col = "Ticker" if "Ticker" in merged.columns else "ticker"
    ticker_set = set(t.upper() for t in tickers) if tickers else None

    rows = []
    for _, row in merged.iterrows():
        t = str(row.get(ticker_col, "")).strip().upper()
        if not t:
            continue
        if ticker_set and t not in ticker_set:
            continue

        price = _parse_num(row.get("Price", row.get("price", "")))
        if price is None or price <= 0:
            continue

        change = _parse_pct(row.get("Change", row.get("change", "")))
        if pd.isna(change):
            change = 0.0

        def _pct(key: str, *alts: str) -> float:
            v = row.get(key)
            for alt in alts:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    v = row.get(alt)
            p = _parse_pct(v)
            return p if not pd.isna(p) else float("nan")

        sma20 = _parse_num(row.get("SMA20", row.get("sma20", "")))
        sma50 = _parse_num(row.get("SMA50", row.get("sma50", "")))
        sma200 = _parse_num(row.get("SMA200", row.get("sma200", "")))
        vol_str = row.get("Volume", row.get("volume", ""))
        vol = _parse_num(vol_str) if vol_str else None
        high52 = _parse_num(row.get("52W High", row.get("52W High", "")))
        low52 = _parse_num(row.get("52W Low", row.get("52W Low", "")))
        atr_val = _parse_num(row.get("ATR", row.get("atr", "")))

        week_chg = _pct("Perf Week", "Perf Week")
        month_chg = _pct("Perf Month", "Perf Month")
        qtr_chg = _pct("Perf Quart", "Perf Quarter", "Perf Q")
        half_chg = _pct("Perf Half", "Perf Half Y", "Perf Half")
        year_chg = _pct("Perf Year", "Perf Y", "Perf YTD")

        industry = str(row.get("Industry") or row.get("industry") or "").strip()
        sector = str(row.get("Sector") or row.get("sector") or "").strip()

        rows.append({
            "ticker": t,
            "close": float(price),
            "prev_close": float(price / (1 + change / 100)) if change != -100 else price,
            "open": price,
            "day_chg": float(change),
            "open_chg": float(change),
            "week_chg": week_chg,
            "month_chg": month_chg,
            "qtr_chg": qtr_chg,
            "half_chg": half_chg,
            "year_chg": year_chg,
            "sma10": sma20,
            "sma20": sma20,
            "sma50": sma50,
            "sma200": sma200,
            "ema10": sma20,
            "atr": atr_val,
            "atr_pct": round((atr_val / price * 100), 2) if atr_val and price else None,
            "high_20": None,
            "low_20": None,
            "price_to_20_range": 50.0,
            "high_52w": high52,
            "low_52w": low52,
            "volume": vol,
            "avg_volume": vol,
            "new_20_high": False,
            "new_20_low": False,
            "industry": industry or sector,
            "sector": sector,
        })

    result = pd.DataFrame(rows)
    if cache_key and not result.empty:
        cache.put(cache_key, result, ttl=MEDIUM)
    return result


def fetch_history(tickers: list[str], period: str = "1y",
                  cache_key: str | None = None) -> pd.DataFrame:
    """
    FinViz does not provide OHLCV history. This returns an empty DataFrame.
    The dashboard uses fetch_group_indicators instead for FinViz data.
    """
    return pd.DataFrame()


def get_single_ticker_df(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """FinViz does not use OHLCV DataFrames. Return empty."""
    return pd.DataFrame()


def fetch_sector_data(cache_key: str = "sector_data") -> list[dict]:
    """Fetch sector ETF data via get_stock. Returns list of dicts for sector table."""
    from src.constants import SECTOR_ETFS

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rows = []
    for ticker in SECTOR_ETFS:
        try:
            s = finviz.get_stock(ticker)
            if not s:
                continue
            price = _parse_num(s.get("Price", ""))
            if price is None:
                continue
            change = _parse_pct(s.get("Change", ""))
            prev = price / (1 + change / 100) if not pd.isna(change) and change != -100 else price
            open_p = price
            gap = 0.0
            if prev and prev != 0:
                gap = (open_p - prev) / prev * 100
            rows.append({
                "sector": ticker,
                "ticker": ticker,
                "gap": round(gap, 2),
                "chg": round(change if not pd.isna(change) else 0, 2),
                "ochg": round(change if not pd.isna(change) else 0, 2),
                "week": round(_parse_pct(s.get("Perf Week", "")) or 0, 1),
                "month": round(_parse_pct(s.get("Perf Month", "")) or 0, 1),
                "qtr": round(_parse_pct(s.get("Perf Quarter", "")) or 0, 1),
                "hyear": round(_parse_pct(s.get("Perf Half Y", "")) or 0, 1),
                "year": round(_parse_pct(s.get("Perf Y", "")) or 0, 1),
                "last": round(price, 2),
                "ema10": round(price, 2),
                "sma20": round(_parse_num(s.get("SMA20", "")) or price, 2),
                "sma50": round(_parse_num(s.get("SMA50", "")) or price, 2),
                "sma200": round(_parse_num(s.get("SMA200", "")) or price, 2),
                "high_52w": round(_parse_num(s.get("52W High", "")) or price, 2),
                "low_52w": round(_parse_num(s.get("52W Low", "")) or price, 2),
                "atr_pct": 0.0,
                "atr_ext": 0.0,
                "atr_rs": 0,
            })
        except Exception as e:
            logger.warning("FinViz get_stock %s failed: %s", ticker, e)

    if rows:
        cache.put(cache_key, rows, ttl=MEDIUM)
    return rows


def fetch_gainers_screener(cache_key: str = "finviz_gainers", ttl: int = FAST) -> list[dict]:
    """Top gainers from FinViz (pre-built screen)."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        s = Screener(filters=["ta_change_u4"], table="Performance", order="-change")
        df = _screener_to_df(s)
        rows = []
        for _, r in df.head(50).iterrows():
            t = str(r.get("Ticker", "")).strip()
            if not t:
                continue
            chg = _parse_pct(r.get("Change", ""))
            rows.append({"ticker": t, "chg": chg, "stage": "2A", "atr_pct": 0, "min_rel_vol": 0})
        if rows:
            cache.put(cache_key, rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("FinViz gainers failed: %s", e)
        return []


def fetch_current_quotes(tickers: list[str], cache_key: str | None = None) -> pd.DataFrame:
    """Fetch latest quote snapshot. Uses get_stock per ticker (slow for large lists)."""
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    rows = []
    for t in tickers[:100]:
        try:
            s = finviz.get_stock(t)
            if not s:
                continue
            price = _parse_num(s.get("Price", ""))
            if price is None:
                continue
            change = _parse_pct(s.get("Change", ""))
            prev = price / (1 + change / 100) if not pd.isna(change) and change != -100 else price
            rows.append({
                "ticker": t,
                "close": price,
                "open": price,
                "high": price,
                "low": price,
                "volume": _parse_num(s.get("Volume", "")),
                "prev_close": prev,
            })
        except Exception:
            pass
    df = pd.DataFrame(rows)
    if cache_key and not df.empty:
        cache.put(cache_key, df, ttl=MEDIUM)
    return df
