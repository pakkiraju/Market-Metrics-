"""Fetch market data from FinViz Elite API only.

Uses export.ashx for screeners and quote.ashx for single-ticker data.
Requires FINVIZ_API_KEY in .env. FinViz data is delayed ~15-20 min.
"""

import logging
import re
import time
from pathlib import Path

import pandas as pd

from src import cache
from src.cache import FAST, MEDIUM, SLOW

logger = logging.getLogger(__name__)

# Delay between FinViz fetches to avoid 429 rate limit
_FINVIZ_DELAY_SEC = 2.0

ROOT = Path(__file__).resolve().parent.parent
WATCHLIST_FILE = ROOT / "watchlist.csv"


def load_watchlist() -> list[str]:
    """Load tickers from watchlist.csv in project root."""
    if not WATCHLIST_FILE.exists():
        return []
    try:
        df = pd.read_csv(WATCHLIST_FILE)
        col = df.columns[0]
        return df[col].dropna().str.strip().str.upper().tolist()
    except Exception as e:
        logger.warning("Failed to load watchlist: %s", e)
        return []


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


def _fetch_screener(filters: list[str], table: str, cache_key: str | None = None,
                    order: str = "", ttl: int = MEDIUM, ft: str = "3") -> pd.DataFrame:
    """Run FinViz Elite Screener (export.ashx). Cached. Returns empty if Elite not configured.
    ft: filter type (3=technical, 4=performance)."""
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        from src.finviz_elite import is_elite_configured, fetch_elite_screener

        if not is_elite_configured():
            logger.warning("FinViz Elite not configured (FINVIZ_API_KEY in .env required)")
            return pd.DataFrame()

        data = fetch_elite_screener(filters=filters, table=table, order=order, ft=ft)
        df = pd.DataFrame(data) if data else pd.DataFrame()
        if cache_key and not df.empty:
            cache.put(cache_key, df, ttl=ttl)
        return df
    except Exception as e:
        logger.warning("FinViz Elite Screener failed: %s", e)
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
        if i > 0:
            time.sleep(_FINVIZ_DELAY_SEC)
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


def fetch_metric_count(url: str, cache_key: str) -> int:
    """Fetch screener URL, return row count. Cached 1hr. 2s delay before each fetch to avoid rate limit."""
    cached = cache.get(cache_key)
    if cached is not None:
        return int(cached)
    try:
        from src.finviz_elite import fetch_csv_from_url, is_elite_configured
        if not is_elite_configured():
            return 0
        time.sleep(_FINVIZ_DELAY_SEC)
        data = fetch_csv_from_url(url)
        count = len(data) if data else 0
        if cache_key:
            cache.put(cache_key, count, ttl=MEDIUM)
        return count
    except Exception as e:
        logger.warning("fetch_metric_count failed %s: %s", cache_key, e)
        return 0


def fetch_group_indicators_from_url(cache_key: str) -> pd.DataFrame:
    """
    Fetch Key Metrics data from a single export.ashx URL. One request per group, fast.
    Uses URLs from FINVIZ_SCREENER_URLS - same URLs user clicks in browser.
    """
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from src.finviz_elite import fetch_csv_from_url, is_elite_configured
        from src.constants import FINVIZ_SCREENER_URLS

        if not is_elite_configured():
            return pd.DataFrame()

        url_key = {"ind_QQQE": "NQ100", "ind_RSP": "SPY500", "ind_DJIA": "DJIA",
                   "ind_RUS2000": "RUS2000", "ind_$1B+": "$1B+"}.get(cache_key, "")
        fetch_url = FINVIZ_SCREENER_URLS.get(url_key)
        if not fetch_url:
            return pd.DataFrame()

        data = fetch_csv_from_url(fetch_url)
        if not data:
            return pd.DataFrame()

        rows = []
        for row in data:
            t = str(row.get("Ticker", row.get("ticker", ""))).strip().upper()
            if not t:
                continue
            price = _parse_num(row.get("Price") or row.get("price") or row.get("Last") or row.get("Close") or "")
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

            def _pct_to_sma(pct, p):
                if pct is None or p is None or p <= 0:
                    return None
                denom = 1 + pct / 100
                if abs(denom) < 0.01:
                    return None
                return p / denom

            sma20_pct = _parse_num(row.get("SMA20", row.get("20-Day Simple Moving Average", "")))
            sma50_pct = _parse_num(row.get("SMA50", row.get("50-Day Simple Moving Average", "")))
            sma200_pct = _parse_num(row.get("SMA200", row.get("200-Day Simple Moving Average", "")))
            sma20 = _pct_to_sma(sma20_pct, price)
            sma50 = _pct_to_sma(sma50_pct, price)
            sma200 = _pct_to_sma(sma200_pct, price)

            week_chg = _pct("Performance (Week)", "Perf Week", "Perf Week")
            month_chg = _pct("Performance (Month)", "Perf Month", "Perf Month")
            qtr_chg = _pct("Performance (Quarter)", "Perf Quart", "Perf Quarter", "Perf Q")
            half_chg = _pct("Performance (Half Year)", "Perf Half", "Perf Half Y", "Perf Half")
            year_chg = _pct("Performance (Year)", "Perf Year", "Perf Y", "Perf YTD")

            vol = _parse_num(row.get("Volume", row.get("volume", "")))
            avg_vol = _parse_num(row.get("Avg Volume", row.get("Average Volume", row.get("avg_volume", ""))))
            rel_vol = _parse_num(row.get("Rel Volume", row.get("Relative Volume", row.get("rel_volume", ""))))
            if rel_vol is None and vol and avg_vol and avg_vol != 0:
                rel_vol = vol / avg_vol
            mcap_str = row.get("Market Cap", row.get("market_cap", ""))
            market_cap = _parse_num(mcap_str)
            if market_cap and market_cap > 0 and market_cap < 1e7 and "B" not in str(mcap_str or "").upper() and "M" not in str(mcap_str or "").upper():
                market_cap = market_cap * 1e6

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
                "atr": None,
                "atr_pct": None,
                "high_20": None,
                "low_20": None,
                "price_to_20_range": 50.0,
                "high_52w": _parse_num(row.get("52W High", row.get("52-Week High", ""))),
                "low_52w": _parse_num(row.get("52W Low", row.get("52-Week Low", ""))),
                "volume": vol,
                "avg_volume": avg_vol if avg_vol is not None else vol,
                "rel_volume": rel_vol,
                "market_cap": market_cap,
                "new_20_high": False,
                "new_20_low": False,
                "industry": str(row.get("Industry", row.get("industry", "")) or ""),
                "sector": str(row.get("Sector", row.get("sector", "")) or ""),
            })

        result = pd.DataFrame(rows)
        if cache_key and not result.empty:
            cache.put(cache_key, result, ttl=MEDIUM)
        return result
    except Exception as e:
        logger.warning("fetch_group_indicators_from_url failed: %s", e)
        return pd.DataFrame()


def fetch_group_indicators(tickers: list[str], cache_key: str | None = None) -> pd.DataFrame:
    """
    Fetch FinViz data for tickers and return a DataFrame in the format
    expected by compute_key_metrics_for_group and related functions.
    """
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    # FinViz: idx_sp500 = S&P 500, idx_ndx = NASDAQ 100, idx_dji = DJIA, idx_rut = Russell 2000.
    # geo_usa = all US-listed; sh_price_o1 = price over $1; sh_avgvol_o1000 = 1M; cap_1to = $1B+ mcap.
    # All data comes from FinViz screeners; no CSV ticker lists used.
    filter_sets_by_group = {
        "ind_QQQE": [["idx_ndx"]],
        "ind_RSP": [["idx_sp500"]],
        "ind_DJIA": [["idx_dji"]],
        "ind_RUS2000": [["idx_rut"]],
        "ind_Composite": [["idx_sp500"], ["idx_ndx"], ["idx_dji"]],
        "ind_$1B+": [["cap_1to", "geo_usa", "sh_avgvol_o1000", "sh_price_o1"]],
        "ind_USA": [["geo_usa", "sh_price_o1", "sh_avgvol_o1000"]],
    }
    filter_sets = filter_sets_by_group.get(cache_key, [["idx_sp500"], ["idx_ndx"]])

    overview_df = _fetch_screener_multi(
        filter_sets, "Overview",
        cache_key=f"{cache_key}_overview" if cache_key else None,
        order="-change",
        ttl=MEDIUM,
    )
    time.sleep(_FINVIZ_DELAY_SEC)
    perf_df = _fetch_screener_multi(
        filter_sets, "Performance",
        cache_key=f"{cache_key}_perf" if cache_key else None,
        order="-change",
        ttl=MEDIUM,
    )
    time.sleep(_FINVIZ_DELAY_SEC)
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

        # FinViz Technical table stores SMA as % above/below price (e.g. -5.36% = price 5.36% below SMA)
        # Convert to actual SMA: sma = price / (1 + pct/100)
        def _pct_to_sma(pct, p):
            if pct is None or p is None or p <= 0:
                return None
            denom = 1 + pct / 100
            if abs(denom) < 0.01:
                return None
            return p / denom

        sma10_pct = _parse_num(row.get("SMA10", row.get("10-Day SMA", row.get("10-Day Simple Moving Average", row.get("sma10", "")))))
        sma20_pct = _parse_num(row.get("SMA20", row.get("20-Day Simple Moving Average", row.get("sma20", ""))))
        sma50_pct = _parse_num(row.get("SMA50", row.get("50-Day Simple Moving Average", row.get("sma50", ""))))
        sma200_pct = _parse_num(row.get("SMA200", row.get("200-Day Simple Moving Average", row.get("sma200", ""))))
        ema10_pct = _parse_num(row.get("EMA10", row.get("10-Day EMA", row.get("10-Day Exponential Moving Average", row.get("ema10", "")))))
        sma20 = _pct_to_sma(sma20_pct, price)
        sma50 = _pct_to_sma(sma50_pct, price)
        sma200 = _pct_to_sma(sma200_pct, price)
        sma10 = _pct_to_sma(sma10_pct, price) if sma10_pct is not None else sma20
        ema10 = _pct_to_sma(ema10_pct, price) if ema10_pct is not None else sma20
        vol_str = row.get("Volume", row.get("volume", ""))
        vol = _parse_num(vol_str) if vol_str else None
        avg_vol_str = row.get("Avg Volume", row.get("Average Volume", row.get("avg_volume", "")))
        avg_vol = _parse_num(avg_vol_str) if avg_vol_str else None
        rel_vol_str = row.get("Rel Volume", row.get("Relative Volume", row.get("rel_volume", "")))
        rel_vol = _parse_num(rel_vol_str) if rel_vol_str else None
        if rel_vol is None and vol and avg_vol and avg_vol != 0:
            rel_vol = vol / avg_vol
        mcap_str = row.get("Market Cap", row.get("market_cap", ""))
        market_cap = _parse_num(mcap_str) if mcap_str else None
        if market_cap is not None and market_cap > 0 and market_cap < 1e7 and "B" not in str(mcap_str or "").upper() and "M" not in str(mcap_str or "").upper():
            market_cap = market_cap * 1e6
        high52 = _parse_num(row.get("52W High", row.get("52-Week High", row.get("52W High", ""))))
        low52 = _parse_num(row.get("52W Low", row.get("52-Week Low", row.get("52W Low", ""))))
        atr_val = _parse_num(row.get("ATR", row.get("Average True Range", row.get("atr", ""))))

        week_chg = _pct("Performance (Week)", "Perf Week", "Perf Week")
        month_chg = _pct("Performance (Month)", "Perf Month", "Perf Month")
        qtr_chg = _pct("Performance (Quarter)", "Perf Quart", "Perf Quarter", "Perf Q")
        half_chg = _pct("Performance (Half Year)", "Perf Half", "Perf Half Y", "Perf Half")
        year_chg = _pct("Performance (Year)", "Perf Year", "Perf Y", "Perf YTD")

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
            "sma10": sma10,
            "sma20": sma20,
            "sma50": sma50,
            "sma200": sma200,
            "ema10": ema10,
            "atr": atr_val,
            "atr_pct": round((atr_val / price * 100), 2) if atr_val and price else None,
            "high_20": None,
            "low_20": None,
            "price_to_20_range": 50.0,
            "high_52w": high52,
            "low_52w": low52,
            "volume": vol,
            "avg_volume": avg_vol if avg_vol is not None else vol,
            "rel_volume": rel_vol,
            "market_cap": market_cap,
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
    """Fetch sector ETF data via Elite quote.ashx. Returns list of dicts for sector table."""
    from src.constants import SECTOR_ETFS
    from src.finviz_elite import fetch_elite_stock, is_elite_configured

    if not is_elite_configured():
        logger.warning("FinViz Elite not configured - sector data unavailable")
        return []

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rows = []
    for ticker in SECTOR_ETFS:
        try:
            s = fetch_elite_stock(ticker)
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
            logger.warning("FinViz Elite quote %s failed: %s", ticker, e)

    if rows:
        cache.put(cache_key, rows, ttl=MEDIUM)
    return rows


def fetch_gainers_screener(cache_key: str = "finviz_gainers", ttl: int = FAST) -> list[dict]:
    """Top gainers from FinViz (pre-built screen). Uses Elite export.ashx when configured."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        df = _fetch_screener(
            filters=["ta_change_u4"],
            table="Performance",
            cache_key=f"{cache_key}_df",
            order="-change",
            ttl=ttl,
        )
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
    """Fetch latest quote snapshot via Elite quote.ashx (slow for large lists)."""
    from src.finviz_elite import fetch_elite_stock, is_elite_configured

    if not is_elite_configured():
        return pd.DataFrame()

    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    rows = []
    for t in tickers[:100]:
        try:
            s = fetch_elite_stock(t)
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
