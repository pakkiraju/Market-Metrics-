"""Fetch market data from Yahoo Finance via yfinance with caching."""

import os
import logging
from pathlib import Path

import pandas as pd
import yfinance as yf

from src import cache
from src.cache import MEDIUM

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# ---------------------------------------------------------------------------
# Config loaders
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
# yfinance bulk download
# ---------------------------------------------------------------------------

def _batch_download(tickers: list[str], period: str = "1y",
                    interval: str = "1d", batch_size: int = 80) -> pd.DataFrame:
    """Download historical data in batches with retry to avoid rate limits."""
    import time
    frames = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        success = False
        for attempt in range(3):
            try:
                df = yf.download(
                    batch,
                    period=period,
                    interval=interval,
                    group_by="ticker",
                    auto_adjust=True,
                    threads=True,
                    progress=False,
                )
                if df is not None and not df.empty:
                    frames.append(df)
                success = True
                break
            except Exception as e:
                logger.warning("Batch %d-%d attempt %d failed: %s",
                               i, i + len(batch), attempt + 1, e)
                time.sleep(2 * (attempt + 1))
        if not success:
            logger.error("Batch %d-%d failed after 3 attempts", i, i + len(batch))
        if i + batch_size < len(tickers):
            time.sleep(0.5)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def fetch_history(tickers: list[str], period: str = "1y",
                  cache_key: str | None = None) -> pd.DataFrame:
    """Return OHLCV history for *tickers*, cached."""
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    df = _batch_download(tickers, period=period)

    if cache_key and not df.empty:
        cache.put(cache_key, df, ttl=MEDIUM)
    return df


def fetch_sector_history() -> pd.DataFrame:
    from src.constants import SECTOR_ETFS
    return fetch_history(SECTOR_ETFS, period="1y", cache_key="sector_hist")


def fetch_index_group_history(group_name: str) -> pd.DataFrame:
    """Fetch history for a named index group."""
    loaders = {
        "QQQE": load_nasdaq100,
        "RSP": load_sp500,
        "Composite": load_composite,
    }
    loader = loaders.get(group_name)
    if loader is None:
        return pd.DataFrame()
    tickers = loader()
    return fetch_history(tickers, period="1y",
                         cache_key=f"hist_{group_name}")


def get_single_ticker_df(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Extract a single ticker's OHLCV from a multi-ticker download."""
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        level_values = raw.columns.get_level_values(0)
        if ticker in level_values:
            df = raw[ticker].copy()
            col_map = {}
            for c in df.columns:
                if isinstance(c, str):
                    cap = c.capitalize()
                    if cap in ("Open", "High", "Low", "Close", "Volume"):
                        col_map[c] = cap
            if col_map:
                df = df.rename(columns=col_map)
            needed = [c for c in ["Open", "High", "Low", "Close", "Volume"]
                      if c in df.columns]
            if needed:
                df = df[needed]
            return df.dropna(how="all")
        return pd.DataFrame()
    flat_cols = list(raw.columns)
    if "Close" in flat_cols or "close" in flat_cols:
        return raw.copy()
    return pd.DataFrame()


def fetch_current_quotes(tickers: list[str],
                         cache_key: str | None = None) -> pd.DataFrame:
    """Fetch latest quote snapshot for a list of tickers."""
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    rows = []
    for i in range(0, len(tickers), 400):
        batch = tickers[i : i + 400]
        try:
            data = yf.download(
                batch,
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            if data is None or data.empty:
                continue
            for t in batch:
                tdf = get_single_ticker_df(data, t)
                if tdf.empty:
                    continue
                last = tdf.iloc[-1]
                prev = tdf.iloc[-2] if len(tdf) >= 2 else last
                rows.append({
                    "ticker": t,
                    "close": last.get("Close", None),
                    "open": last.get("Open", None),
                    "high": last.get("High", None),
                    "low": last.get("Low", None),
                    "volume": last.get("Volume", None),
                    "prev_close": prev.get("Close", None),
                })
        except Exception as e:
            logger.error("Quote fetch failed: %s", e)

    df = pd.DataFrame(rows)
    if cache_key and not df.empty:
        cache.put(cache_key, df, ttl=MEDIUM)
    return df
