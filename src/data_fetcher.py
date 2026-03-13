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
from src.cache import MEDIUM, FAST

logger = logging.getLogger(__name__)

# Live index snapshot: QQQ, SPY, DIA, IWM, VIX (5-min cache for intraday)
LIVE_INDEX_TICKERS = ["QQQ", "SPY", "DIA", "IWM", "VIX"]

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


def _get_csv_val(row, *candidates: str):
    """Get value from row using first matching key (case-insensitive). Handles FinViz export column variations.
    Accepts dict (csv.DictReader) or pandas Series (DataFrame.iterrows())."""
    if hasattr(row, "to_dict"):
        row = row.to_dict()
    row_lower = {str(k).strip().lower(): (k, v) for k, v in row.items()}
    for c in candidates:
        cl = str(c).strip().lower()
        if cl in row_lower:
            _, v = row_lower[cl]
            if v is not None and str(v).strip() not in ("", "-"):
                return v
    return ""


def _find_csv_col(keys: list, *substrings: str, exact: str | None = None) -> str | None:
    """Find first key where all substrings appear (case-insensitive). exact= prefers key equal to exact (case-insensitive)."""
    if exact:
        el = str(exact).lower()
        for k in keys:
            if str(k).strip().lower() == el:
                return k
    for k in keys:
        kl = str(k).lower()
        if all(s.lower() in kl for s in substrings):
            return k
    return None


def fetch_industry_map_from_overview(cache_key: str = "leading_industry_map", ttl: int = MEDIUM) -> dict[str, str]:
    """Fetch ticker->industry from FinViz Overview export ($1B+, USA). Industry/Sector columns from v=111."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS

        if not is_elite_configured():
            return {}
        url = FINVIZ_EXPORT_URLS.get("club97")
        if not url:
            return {}
        data = fetch_export_from_url(url, caller="club97")
        if not data:
            return {}

        industry_map = {}
        for row in data:
            t = str(_get_csv_val(row, "Ticker", "ticker") or "").strip().upper()
            if not t:
                continue
            ind = str(_get_csv_val(row, "Industry", "industry") or "").strip()
            sec = str(_get_csv_val(row, "Sector", "sector") or "").strip()
            industry_map[t] = ind or sec or ""
        if industry_map:
            cache.put(cache_key, industry_map, ttl=ttl)
        return industry_map
    except Exception as e:
        logger.warning("fetch_industry_map_from_overview failed: %s", e)
        return {}


def fetch_screener_from_url(url_key: str, cache_key: str, ttl: int = MEDIUM) -> list[dict]:
    """Fetch screener data directly from FINVIZ_EXPORT_URLS. Returns list of dicts for table display.
    Same pattern as Minervini/O'Neil - one URL, get the data, display it."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS

        if not is_elite_configured():
            return []
        url = FINVIZ_EXPORT_URLS.get(url_key)
        if not url:
            return []
        data = fetch_export_from_url(url, caller=url_key)
        if not data:
            return []

        # Dynamic column detection (FinViz export column names vary by view)
        keys = list(data[0].keys())
        ticker_col = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"
        price_col = _find_csv_col(keys, exact="Price") or _find_csv_col(keys, "price")
        change_col = _find_csv_col(keys, exact="Change") or _find_csv_col(keys, "change")
        vol_col = _find_csv_col(keys, exact="Volume") or _find_csv_col(keys, "volume")
        avg_vol_col = _find_csv_col(keys, "average", "vol") or _find_csv_col(keys, "avg", "vol")
        rel_vol_col = _find_csv_col(keys, "relative", "vol") or _find_csv_col(keys, "rel", "vol")
        atr_col = _find_csv_col(keys, exact="ATR") or _find_csv_col(keys, "atr") or _find_csv_col(keys, "average", "true", "range")
        # Prefer News Title/Headline (actual news text). "News" alone is often a count (1,2,3). Exclude "No." (row number).
        _exclude_news = frozenset({"no", "no.", "#", "rank"})
        news_col = _find_csv_col(keys, "news", "title") or _find_csv_col(keys, "headline")
        if not news_col:
            c = _find_csv_col(keys, exact="News") or _find_csv_col(keys, "news")
            if c and str(c).strip().lower() not in _exclude_news:
                news_col = c
        news_link_col = (_find_csv_col(keys, "news", "link") or _find_csv_col(keys, "link") or
                        _find_csv_col(keys, "url") or _find_csv_col(keys, "news", "url"))

        def _val(row: dict, col: str | None, *fallbacks: str):
            if col and row.get(col) not in (None, "", "-"):
                v = row.get(col)
                if v is not None and str(v).strip():
                    return v
            return _get_csv_val(row, *fallbacks) if fallbacks else ""

        rows = []
        seen = set()
        for row in data:
            t = str(row.get(ticker_col, "") or "").strip().upper()
            if not t or t in seen:
                continue
            seen.add(t)
            price = _val(row, price_col, "Price", "price", "Last", "Close")
            change = _val(row, change_col, "Change", "change")
            vol = _val(row, vol_col, "Volume", "volume")
            avg_vol = _val(row, avg_vol_col, "Avg Volume", "Average Volume", "avg_volume", "Avg Vol")
            rel_vol = _val(row, rel_vol_col, "Rel Volume", "Relative Volume", "rel_volume", "Rel Vol")
            # Compute rel_vol from volume/avg_vol when missing
            if not rel_vol and vol and avg_vol:
                v_num, a_num = _parse_num(vol), _parse_num(avg_vol)
                if v_num and a_num and a_num != 0:
                    rel_vol = f"{v_num / a_num:.2f}"
            atr_val = _parse_num(_val(row, atr_col, "ATR", "atr", "Average True Range")) if atr_col else None
            price_num = _parse_num(price) if price else None
            atr_pct = round((atr_val / price_num * 100), 2) if atr_val and price_num and price_num != 0 else None
            news_val = _val(row, news_col) if news_col else ""
            news_link_val = _val(row, news_link_col) if news_link_col else ""
            news_url = str(news_link_val).strip() if news_link_val else (str(news_val).strip() if news_val and str(news_val).strip().lower().startswith(("http://", "https://")) else "")
            # Normalize relative URLs (e.g. /news/123/... or /quote.ashx...)
            if news_url and news_url.startswith("/"):
                news_url = "https://finviz.com" + news_url
            # Only use actual news URLs from export - do NOT fallback to quote page (stock view)
            row_dict = {
                "ticker": t,
                "price": price,
                "change": change,
                "volume": vol,
                "avg_vol": avg_vol,
                "rel_vol": rel_vol,
                "atr_pct": atr_pct,
            }
            if news_url:
                row_dict["news_url"] = news_url
            elif news_val:
                s = str(news_val).strip()
                if s and not (s.isdigit() and len(s) <= 4):
                    row_dict["news"] = s[:80] + ("..." if len(s) > 80 else "")
            rows.append(row_dict)
        if rows and not any(r.get("price") or r.get("change") or r.get("volume") for r in rows[:3]):
            logger.info("FinViz export CSV keys (first row): %s", list(data[0].keys()) if data else [])
        if rows:
            cache.put(cache_key, rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_screener_from_url failed: %s", e)
        return []


def _normalize_pre_market_rows(data: list[dict]) -> list[dict]:
    """Normalize pre-market rows: preserve all columns, ensure ticker key and Change column."""
    rows = []
    seen = set()
    for row in data:
        ticker_val = row.get("Ticker") or row.get("ticker") or ""
        t = str(ticker_val).strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        out = dict(row)
        out["ticker"] = t
        if "Ticker" not in out:
            out["Ticker"] = t
        rows.append(out)
    return rows


def fetch_pre_market_scanner(ttl: int = MEDIUM) -> list[dict]:
    """Pre-market Scanner: USA, avg vol 1K+, price $1+, rel vol 1+, up 3% AND down 3%.
    Returns raw rows with ALL columns from FinViz export (no normalization)."""
    cached = cache.get("pre_market_scanner")
    if cached is not None:
        return cached

    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS

        if not is_elite_configured():
            return []
        url_up = FINVIZ_EXPORT_URLS.get("pre_market_scanner")
        url_down = FINVIZ_EXPORT_URLS.get("pre_market_scanner_down")
        if not url_up:
            return []
        data_up = fetch_export_from_url(url_up, caller="pre_market_scanner") or []
        data_down = fetch_export_from_url(url_down, caller="pre_market_scanner_down") or [] if url_down else []
        rows_up = _normalize_pre_market_rows(data_up)
        rows_down = _normalize_pre_market_rows(data_down)
        rows = rows_up + rows_down
        if rows:
            cache.put("pre_market_scanner", rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_pre_market_scanner failed: %s", e)
        return []


def fetch_oneil_from_url(cache_key: str = "oneil_table", ttl: int = MEDIUM) -> list[dict]:
    """Fetch O'Neil/CANSLIM: single export URL with c= for all columns. Filters ROE + Net Margin >= 25%.
    v=161 Fundamental view omits Avg Vol/Rel Vol; enriches via fetch_tickers_bulk_csv (v=141)."""
    cached = cache.get(cache_key)
    if cached is not None:
        sample = cached[0] if cached else {}
        if sample.get("avg_vol") or sample.get("rel_vol"):
            return cached
        cache.invalidate(cache_key)

    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS

        if not is_elite_configured():
            return []
        url = FINVIZ_EXPORT_URLS.get("oneil")
        if not url:
            return []
        data = fetch_export_from_url(url, caller="oneil")
        if not data:
            return []

        keys = list(data[0].keys())
        ticker_col = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"
        price_col = _find_csv_col(keys, exact="Price") or _find_csv_col(keys, "price")
        change_col = _find_csv_col(keys, exact="Change") or _find_csv_col(keys, "change")
        vol_col = _find_csv_col(keys, exact="Volume") or _find_csv_col(keys, "volume")
        avg_vol_col = _find_csv_col(keys, "average", "vol") or _find_csv_col(keys, "avg", "vol")
        rel_vol_col = _find_csv_col(keys, "relative", "vol") or _find_csv_col(keys, "rel", "vol")
        atr_col = _find_csv_col(keys, exact="ATR") or _find_csv_col(keys, "atr")
        roe_col = _find_csv_col(keys, "roe") or _find_csv_col(keys, "return", "equity")
        margin_col = _find_csv_col(keys, "net", "margin") or _find_csv_col(keys, "profit", "margin") or _find_csv_col(keys, "profit m")

        def _parse_pct(val):
            if val is None or val == "" or str(val).strip() in ("-", "—"):
                return None
            s = str(val).strip().replace("%", "").replace(",", "")
            try:
                return float(s)
            except ValueError:
                return None

        def _val(row, col, *fallbacks):
            if col and row.get(col) not in (None, "", "-"):
                v = row.get(col)
                if v is not None and str(v).strip():
                    return v
            return _get_csv_val(row, *fallbacks) if fallbacks else ""

        rows = []
        for row in data:
            t = str(row.get(ticker_col, "") or "").strip().upper()
            if not t:
                continue
            roe_val = _parse_pct(_val(row, roe_col, "ROE", "roe", "Return on Equity"))
            margin_val = _parse_pct(_val(row, margin_col, "Net Profit Margin", "Profit Margin", "profit margin"))
            if (roe_val if roe_val is not None else 0) + (margin_val if margin_val is not None else 0) < 25:
                continue
            price = _val(row, price_col, "Price", "price")
            change = _val(row, change_col, "Change", "change")
            vol = _val(row, vol_col, "Volume", "volume")
            avg_vol = _val(row, avg_vol_col, "Avg Volume", "Average Volume", "avg_volume", "Avg Vol", "Avg. Volume")
            rel_vol = _val(row, rel_vol_col, "Rel Volume", "Relative Volume", "rel_volume", "Rel Vol", "Rel. Volume")
            if not rel_vol and vol and avg_vol:
                v_num, a_num = _parse_num(vol), _parse_num(avg_vol)
                if v_num and a_num and a_num != 0:
                    rel_vol = f"{v_num / a_num:.2f}"
            atr_val = _parse_num(_val(row, atr_col, "ATR", "atr")) if atr_col else None
            price_num = _parse_num(price) if price else None
            atr_pct = round((atr_val / price_num * 100), 2) if atr_val and price_num and price_num != 0 else None
            rows.append({
                "ticker": t,
                "price": price,
                "avg_vol": avg_vol,
                "rel_vol": rel_vol,
                "change": change,
                "volume": vol,
                "atr_pct": atr_pct,
                "roe": roe_val,
                "net_margin": margin_val,
            })
        # v=161 Fundamental view omits Avg Vol/Rel Vol; enrich via bulk fetch (v=141)
        if rows and not any(r.get("avg_vol") or r.get("rel_vol") for r in rows[:3]):
            tickers = [r["ticker"] for r in rows]
            bulk = fetch_tickers_bulk_csv(tickers, cache_key=f"oneil_vol_{','.join(sorted(tickers))}")
            bulk_map = {r["ticker"]: r for r in bulk}
            for r in rows:
                b = bulk_map.get(r["ticker"])
                if b:
                    if not r.get("avg_vol") and b.get("avg_vol"):
                        r["avg_vol"] = b["avg_vol"]
                    if not r.get("rel_vol") and b.get("rel_vol"):
                        r["rel_vol"] = b["rel_vol"]
        if rows:
            cache.put(cache_key, rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_oneil_from_url failed: %s", e)
        return []


def fetch_20pct_weekly_from_urls(ttl: int = MEDIUM) -> list[dict]:
    """Fetch 20% weekly movers from both +20 and -20 FinViz URLs. Merges Performance + Technical for ATR."""
    cached = cache.get("20pct_weekly")
    if cached is not None:
        sample = cached[0] if cached else {}
        if "price" not in sample:
            cache.invalidate("20pct_weekly")
        else:
            return cached

    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS

        if not is_elite_configured():
            return []

        rows = []
        seen = set()

        def _val(row: dict, col: str | None, *fallbacks: str):
            if col and row.get(col) not in (None, "", "-"):
                v = row.get(col)
                if v is not None and str(v).strip():
                    return v
            return _get_csv_val(row, *fallbacks) if fallbacks else ""

        for url_key in ("20pct_weekly_up", "20pct_weekly_down"):
            url = FINVIZ_EXPORT_URLS.get(url_key)
            if not url:
                continue
            time.sleep(_FINVIZ_DELAY_SEC)  # Delay before each fetch to avoid rate limit
            data = fetch_export_from_url(url, caller=f"20pct_weekly/{url_key}")
            if not data:
                # Retry once after longer delay (rate limit may clear)
                time.sleep(5)
                data = fetch_export_from_url(url, caller=f"20pct_weekly/{url_key}")
            if not data:
                logger.warning("20pct_weekly %s returned no data", url_key)
                continue

            keys = list(data[0].keys())
            ticker_col = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"
            week_col = _find_csv_col(keys, "perf", "week") or _find_csv_col(keys, "week") or "Perf Week"
            price_col = _find_csv_col(keys, exact="Price") or _find_csv_col(keys, "price")
            change_col = _find_csv_col(keys, exact="Change") or _find_csv_col(keys, "change")
            vol_col = _find_csv_col(keys, exact="Volume") or _find_csv_col(keys, "volume")
            avg_vol_col = _find_csv_col(keys, "average", "vol") or _find_csv_col(keys, "avg", "vol")
            rel_vol_col = _find_csv_col(keys, "relative", "vol") or _find_csv_col(keys, "rel", "vol")
            atr_col = _find_csv_col(keys, exact="ATR") or _find_csv_col(keys, "atr")

            for row in data:
                t = str(row.get(ticker_col, "") or "").strip().upper()
                if not t or t in seen:
                    continue
                seen.add(t)

                week_val = _get_csv_val(row, "Performance (Week)", "Perf Week", "perf week")
                week = _parse_pct(week_val)
                week = round(float(week), 1) if not pd.isna(week) else 0.0

                price = _val(row, price_col, "Price", "price", "Last", "Close")
                change = _val(row, change_col, "Change", "change")
                vol = _val(row, vol_col, "Volume", "volume")
                avg_vol = _val(row, avg_vol_col, "Avg Volume", "Average Volume", "avg_volume", "Avg Vol")
                rel_vol = _val(row, rel_vol_col, "Rel Volume", "Relative Volume", "rel_volume", "Rel Vol")
                if not rel_vol and vol and avg_vol:
                    v_num, a_num = _parse_num(vol), _parse_num(avg_vol)
                    if v_num and a_num and a_num != 0:
                        rel_vol = f"{v_num / a_num:.2f}"
                atr_val = _parse_num(_val(row, atr_col, "ATR", "atr")) if atr_col else None
                price_num = _parse_num(price) if price else None
                atr_pct = round((atr_val / price_num * 100), 2) if atr_val and price_num and price_num != 0 else None
                rows.append({
                    "ticker": t,
                    "week": week,
                    "price": price,
                    "avg_vol": avg_vol,
                    "rel_vol": rel_vol,
                    "change": change,
                    "volume": vol,
                    "atr_pct": atr_pct,
                })

        rows.sort(key=lambda x: abs(x["week"]), reverse=True)
        if rows:
            cache.put("20pct_weekly", rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_20pct_weekly_from_urls failed: %s", e)
        return []


def fetch_4pct_daily_from_url(ttl: int = MEDIUM) -> list[dict]:
    """Fetch 4% daily gainers from FinViz URL. Merges Performance (price, vol) + Technical (ATR) for full data."""
    cached = cache.get("4pct_daily")
    if cached is not None:
        sample = cached[0] if cached else {}
        if "price" not in sample:
            cache.invalidate("4pct_daily")
        elif not sample.get("avg_vol") and not sample.get("rel_vol"):
            cache.invalidate("4pct_daily")
        else:
            return cached

    return fetch_screener_from_url("4pct_daily", "4pct_daily", ttl=ttl)


def fetch_thematics_data(cache_key: str = "thematics_data", ttl: int = MEDIUM) -> pd.DataFrame:
    """Fetch thematics universe (geo_usa, sh_avgvol_o1000, sh_price_o1).
    Uses ind_USA export (same as leading industries) for Industry, Sector, PerfWeek, PerfMonth, etc."""
    cached = cache.get(cache_key)
    if cached is not None and isinstance(cached, pd.DataFrame):
        return cached
    if cached is not None:
        cache.invalidate(cache_key)  # Bad cache (e.g. string from disk)

    try:
        indicators = fetch_group_indicators([], cache_key="ind_USA")
        if indicators.empty:
            return pd.DataFrame()

        # Map industry/sector to theme (Industry = many themes; Sector = 11 fallback)
        ind = indicators.get("industry", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        sec = indicators.get("sector", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        ind_valid = (ind.str.len() > 0) & (ind != "-") & (ind != "")
        sec_valid = (sec.str.len() > 0) & (sec != "-") & (sec != "")
        theme = ind.where(ind_valid, sec.where(sec_valid, "Uncategorized"))

        result = pd.DataFrame({
            "ticker": indicators["ticker"],
            "theme": theme,
            "day_chg": indicators["day_chg"].fillna(0),
            "week_chg": indicators["week_chg"],
            "month_chg": indicators["month_chg"],
            "qtr_chg": indicators["qtr_chg"],
            "year_chg": indicators["year_chg"],
        })
        if not result.empty:
            cache.put(cache_key, result, ttl=ttl)
        return result
    except Exception as e:
        logger.warning("fetch_thematics_data failed: %s", e)
        return pd.DataFrame()


def fetch_earnings_yesterday_today(ttl: int = MEDIUM) -> list[dict]:
    """Earnings yesterday or today. Use Performance view (v=141) - has Avg Vol, Rel Vol, Change, Volume."""
    cached = cache.get("earnings_yesterday_today")
    if cached:
        s = cached[0]
        if not s.get("avg_vol") and not s.get("rel_vol"):
            cache.invalidate("earnings_yesterday_today")
    return fetch_screener_from_url("earnings_yesterday_today_perf", "earnings_yesterday_today", ttl=ttl)


def fetch_metric_count(url: str, cache_key: str, skip_delay: bool = False) -> int:
    """Fetch screener URL, return row count. Cached 1hr. 2s delay before each fetch to avoid rate limit.
    skip_delay=True when caller handles delay (e.g. Key Metrics batches with 2s between URLs)."""
    cached = cache.get(cache_key)
    if cached is not None:
        return int(cached)
    try:
        from src.finviz_elite import fetch_csv_from_url, is_elite_configured
        if not is_elite_configured():
            return 0
        if not skip_delay:
            time.sleep(_FINVIZ_DELAY_SEC)
        data = fetch_csv_from_url(url, caller=cache_key)
        count = len(data) if data else 0
        if cache_key:
            cache.put(cache_key, count, ttl=MEDIUM)
        return count
    except Exception as e:
        logger.warning("fetch_metric_count failed %s: %s", cache_key, e)
        return 0


def fetch_stage_indicators(cache_key: str = "ind_stage") -> pd.DataFrame:
    """Fetch stage analysis data from single export URL (geo_usa, avgvol 1000+, price $1+). Returns DataFrame with close, ema10, sma20, sma50, week_chg, month_chg."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS
        if not is_elite_configured():
            return pd.DataFrame()
        url = FINVIZ_EXPORT_URLS.get("ind_stage")
        if not url:
            return pd.DataFrame()
        data = fetch_export_from_url(url, caller="stage")
        rows = _parse_group_indicators_rows(data, None)
        if rows:
            result = pd.DataFrame(rows)
            cache.put(cache_key, result, ttl=MEDIUM)
            return result
    except Exception as e:
        logger.warning("fetch_stage_indicators failed: %s", e)
    return pd.DataFrame()


# Map cache_key to export URL key(s) for single-request fetch. None = use legacy _fetch_screener_multi.
_GROUP_INDICATOR_URL_KEYS = {
    "ind_$1B+": ["ind_1b_km"],
    "ind_9m_movers": ["ind_9m"],
    "ind_leading": ["ind_1b"],
    # ind_USA: use legacy Overview+Performance+Technical merge (has Industry/Sector + Perf Quarter/YTD)
    "ind_USA": None,
    "ind_thematics_rrg": ["ind_thematics_rrg"],
    "ind_NQ100": ["ind_ndx"],
    "ind_RSP": ["ind_sp500"],
    "ind_DJIA": ["ind_dji"],
    "ind_RUS2000": ["ind_rut"],
    "ind_Composite": ["ind_sp500", "ind_ndx", "ind_dji"],
}


def _parse_group_indicators_rows(data: list[dict], ticker_set: set | None) -> list[dict]:
    """Parse export data into group indicator row format. Single DataFrame with all columns."""
    if not data:
        return []
    keys = list(data[0].keys())
    ticker_col = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"

    def _v(row, *alts):
        return _get_csv_val(row, *alts)

    rows = []
    for row in data:
        t = str(row.get(ticker_col, "") or "").strip().upper()
        if not t or (ticker_set and t not in ticker_set):
            continue
        # v=152 c=60,66 = Price, Change; support various header names
        price = _parse_num(_v(row, "Price", "price", "Last", "Close", "Last Price"))
        if price is None or price <= 0:
            continue
        change = _parse_pct(_v(row, "Change", "change", "Change %", "Change%"))
        if pd.isna(change):
            change = 0.0
        open_chg_val = _parse_pct(_v(row, "Change from Open", "Change from Open %", "Change from Open%"))
        open_chg = float(open_chg_val) if not pd.isna(open_chg_val) else change

        def _pct(*alts):
            v = _v(row, *alts)
            p = _parse_pct(v)
            return p if not pd.isna(p) else float("nan")

        def _pct_to_sma(pct, p):
            if pct is None or p is None or p <= 0:
                return None
            denom = 1 + pct / 100
            if abs(denom) < 0.01:
                return None
            return p / denom

        sma20_pct = _parse_num(_v(row, "SMA20", "20-Day SMA", "20-Day SMA (Relative)", "20-Day Simple Moving Average", "sma20"))
        sma50_pct = _parse_num(_v(row, "SMA50", "50-Day SMA", "50-Day SMA (Relative)", "50-Day Simple Moving Average", "sma50"))
        sma200_pct = _parse_num(_v(row, "SMA200", "200-Day SMA", "200-Day SMA (Relative)", "200-Day Simple Moving Average", "sma200"))
        sma10_pct = _parse_num(_v(row, "SMA10", "10-Day SMA", "sma10"))
        ema10_pct = _parse_num(_v(row, "EMA10", "10-Day EMA", "10-Day Exponential Moving Average", "ema10"))
        sma20 = _pct_to_sma(sma20_pct, price)
        sma50 = _pct_to_sma(sma50_pct, price)
        sma200 = _pct_to_sma(sma200_pct, price)
        sma10 = _pct_to_sma(sma10_pct, price) if sma10_pct is not None else sma20
        ema10 = _pct_to_sma(ema10_pct, price) if ema10_pct is not None else sma20
        vol = _parse_num(_v(row, "Volume", "volume"))
        avg_vol = _parse_num(_v(row, "Avg Volume", "Average Volume", "avg_volume"))
        rel_vol = _parse_num(_v(row, "Rel Volume", "Relative Volume", "rel_volume"))
        if rel_vol is None and vol and avg_vol and avg_vol != 0:
            rel_vol = vol / avg_vol
        mcap_str = _v(row, "Market Cap", "market_cap")
        market_cap = _parse_num(mcap_str) if mcap_str else None
        if market_cap is not None and market_cap > 0 and market_cap < 1e7 and "B" not in str(mcap_str or "").upper() and "M" not in str(mcap_str or "").upper():
            market_cap = market_cap * 1e6
        high52 = _parse_num(_v(row, "52W High", "52-Week High"))
        low52 = _parse_num(_v(row, "52W Low", "52-Week Low"))
        atr_val = _parse_num(_v(row, "ATR", "ATR (14)", "Average True Range", "atr", "ATR(14)"))
        # v=152 uses c=42,43,44,45,47 for perf columns; support various header names
        week_chg = _pct("Performance (Week)", "Perf Week", "Perf. Week", "Perf Week %", "1W", "Perf 1W")
        month_chg = _pct("Performance (Month)", "Perf Month", "Perf. Month", "Perf Month %", "1M", "Perf 1M")
        qtr_chg = _pct("Performance (Quarter)", "Perf Quart", "Perf Quarter", "Perf Q", "Perf. Quarter", "3M", "Perf 3M")
        half_chg = _pct("Performance (Half Year)", "Perf Half", "Perf Half Y", "Perf. Half", "Perf 6M", "6M")
        year_chg = _pct("Performance (YTD)", "Performance (Year)", "Perf Year", "Perf Y", "Perf YTD", "Perf. Year", "Perf 1Y", "1Y")
        industry = str(_v(row, "Industry", "industry") or "").strip()
        sector = str(_v(row, "Sector", "sector") or "").strip()
        rows.append({
            "ticker": t,
            "close": float(price),
            "prev_close": float(price / (1 + change / 100)) if change != -100 else price,
            "open": price,
            "day_chg": float(change),
            "open_chg": float(open_chg),
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
    return rows


def fetch_single_indicator_url(group_cache_key: str, url_key: str) -> pd.DataFrame:
    """Fetch one indicator URL for a Key Metrics group. One request, then update UI.
    Used for per-URL progressive loading to avoid rate limits."""
    cached = cache.get(group_cache_key)
    if cached is not None:
        return cached
    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS
        if not is_elite_configured():
            return pd.DataFrame()
        url = FINVIZ_EXPORT_URLS.get(url_key)
        if not url:
            return pd.DataFrame()
        time.sleep(_FINVIZ_DELAY_SEC)
        data = fetch_export_from_url(url, caller=f"group_indicators/{url_key}")
        rows = _parse_group_indicators_rows(data, None)
        if rows:
            result = pd.DataFrame(rows)
            cache.put(group_cache_key, result, ttl=MEDIUM)
            return result
    except Exception as e:
        logger.warning("fetch_single_indicator_url failed %s/%s: %s", group_cache_key, url_key, e)
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

    url_keys = _GROUP_INDICATOR_URL_KEYS.get(cache_key) if cache_key else None
    ticker_set = set(t.upper() for t in tickers) if tickers else None

    if url_keys:
        try:
            from src.finviz_elite import fetch_export_from_url, is_elite_configured
            from src.constants import FINVIZ_EXPORT_URLS
            if is_elite_configured():
                all_rows = []
                seen = set()
                for url_key in url_keys:
                    url = FINVIZ_EXPORT_URLS.get(url_key)
                    if not url:
                        continue
                    data = fetch_export_from_url(url, caller=f"group_indicators/{url_key}")
                    for r in _parse_group_indicators_rows(data, ticker_set):
                        if r["ticker"] not in seen:
                            seen.add(r["ticker"])
                            all_rows.append(r)
                if all_rows:
                    result = pd.DataFrame(all_rows)
                    cache.put(cache_key, result, ttl=MEDIUM)
                    return result
        except Exception as e:
            logger.warning("fetch_group_indicators (single-URL) failed: %s", e)

    # Fallback: legacy 3-view fetch
    filter_sets_by_group = {
        "ind_NQ100": [["idx_ndx"]],
        "ind_RSP": [["idx_sp500"]],
        "ind_DJIA": [["idx_dji"]],
        "ind_RUS2000": [["idx_rut"]],
        "ind_Composite": [["idx_sp500"], ["idx_ndx"], ["idx_dji"]],
        "ind_leading": [["cap_1to", "geo_usa", "sh_avgvol_o1000", "sh_price_o1"]],
        "ind_$1B+": [["cap_1to", "geo_usa", "sh_avgvol_o1000", "sh_price_o1"]],
        "ind_9m_movers": [["cap_1to", "geo_usa", "sh_curvol_9000tox", "sh_price_o1", "sh_relvol_1.25to"]],
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
        t = str(row.get(ticker_col, "") or "").strip().upper()
        if not t:
            continue
        if ticker_set and t not in ticker_set:
            continue

        def _v(*alts):
            return _get_csv_val(row, *alts)

        price = _parse_num(_v("Price", "price", "Last", "Close"))
        if price is None or price <= 0:
            continue

        change = _parse_pct(_v("Change", "change"))
        if pd.isna(change):
            change = 0.0

        def _pct(*alts):
            v = _v(*alts)
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

        sma10_pct = _parse_num(_v("SMA10", "10-Day SMA", "10-Day Simple Moving Average", "sma10"))
        sma20_pct = _parse_num(_v("SMA20", "20-Day SMA", "20-Day Simple Moving Average", "sma20"))
        sma50_pct = _parse_num(_v("SMA50", "50-Day SMA", "50-Day Simple Moving Average", "sma50"))
        sma200_pct = _parse_num(_v("SMA200", "200-Day SMA", "200-Day Simple Moving Average", "sma200"))
        ema10_pct = _parse_num(_v("EMA10", "10-Day EMA", "10-Day Exponential Moving Average", "ema10"))
        sma20 = _pct_to_sma(sma20_pct, price)
        sma50 = _pct_to_sma(sma50_pct, price)
        sma200 = _pct_to_sma(sma200_pct, price)
        sma10 = _pct_to_sma(sma10_pct, price) if sma10_pct is not None else sma20
        ema10 = _pct_to_sma(ema10_pct, price) if ema10_pct is not None else sma20
        vol_str = _v("Volume", "volume")
        vol = _parse_num(vol_str) if vol_str else None
        avg_vol_str = _v("Avg Volume", "Average Volume", "avg_volume")
        avg_vol = _parse_num(avg_vol_str) if avg_vol_str else None
        rel_vol_str = _v("Rel Volume", "Relative Volume", "rel_volume")
        rel_vol = _parse_num(rel_vol_str) if rel_vol_str else None
        if rel_vol is None and vol and avg_vol and avg_vol != 0:
            rel_vol = vol / avg_vol
        mcap_str = _v("Market Cap", "market_cap")
        market_cap = _parse_num(mcap_str) if mcap_str else None
        if market_cap is not None and market_cap > 0 and market_cap < 1e7 and "B" not in str(mcap_str or "").upper() and "M" not in str(mcap_str or "").upper():
            market_cap = market_cap * 1e6
        high52 = _parse_num(_v("52W High", "52-Week High"))
        low52 = _parse_num(_v("52W Low", "52-Week Low"))
        atr_val = _parse_num(_v("ATR", "Average True Range", "atr"))

        # v=152 uses c=42,43,44,45,47 for perf columns; support various header names
        week_chg = _pct("Performance (Week)", "Perf Week", "Perf. Week", "Perf Week %", "1W", "Perf 1W")
        month_chg = _pct("Performance (Month)", "Perf Month", "Perf. Month", "Perf Month %", "1M", "Perf 1M")
        qtr_chg = _pct("Performance (Quarter)", "Perf Quart", "Perf Quarter", "Perf Q", "Perf. Quarter", "3M", "Perf 3M")
        half_chg = _pct("Performance (Half Year)", "Perf Half", "Perf Half Y", "Perf. Half", "Perf 6M", "6M")
        year_chg = _pct("Performance (YTD)", "Performance (Year)", "Perf Year", "Perf Y", "Perf YTD", "Perf. Year", "Perf 1Y", "1Y")

        industry = str(_v("Industry", "industry") or "").strip()
        sector = str(_v("Sector", "sector") or "").strip()

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
            atr_val = _parse_num(s.get("ATR (14)", s.get("ATR", "")))
            atr_pct = round((atr_val / price * 100), 2) if atr_val and price and price != 0 else None

            def _safe_pct(val):
                p = _parse_pct(val)
                return 0.0 if pd.isna(p) else float(p)

            def _q(key, *fallbacks):
                v = s.get(key)
                if v is not None and str(v).strip() and str(v).strip() != "-":
                    return v
                for k in fallbacks:
                    v = s.get(k)
                    if v is not None and str(v).strip() and str(v).strip() != "-":
                        return v
                return ""

            rows.append({
                "sector": ticker,
                "ticker": ticker,
                "gap": round(gap, 2),
                "chg": round(change if not pd.isna(change) else 0, 2),
                "ochg": round(change if not pd.isna(change) else 0, 2),
                "week": round(_safe_pct(_q("Perf Week", "Week")), 1),
                "month": round(_safe_pct(_q("Perf Month", "Month")), 1),
                "qtr": round(_safe_pct(_q("Perf Quarter", "Perf Quarter", "Quarter")), 1),
                "hyear": round(_safe_pct(_q("Perf Half Y", "Perf Half Y", "Half Y")), 1),
                "year": round(_safe_pct(_q("Perf Year", "Perf Y", "Perf YTD", "Return% 1Y", "1Y")), 1),
                "last": round(price, 2),
                "ema10": round(price, 2),
                "sma20": round(_parse_num(s.get("SMA20", "")) or price, 2),
                "sma50": round(_parse_num(s.get("SMA50", "")) or price, 2),
                "sma200": round(_parse_num(s.get("SMA200", "")) or price, 2),
                "high_52w": round(_parse_num(s.get("52W High", "")) or price, 2),
                "low_52w": round(_parse_num(s.get("52W Low", "")) or price, 2),
                "atr_pct": atr_pct,
            })
        except Exception as e:
            logger.warning("FinViz Elite quote %s failed: %s", ticker, e)

    if rows:
        cache.put(cache_key, rows, ttl=MEDIUM)
    return rows


def fetch_benchmark_performance(benchmark: str = "VTI", cache_key: str = "rrg_benchmark") -> dict | None:
    """Fetch benchmark (VTI) performance from FinViz via same quote.ashx as sector ETFs.
    Returns {chg, week, month, qtr, hyear, year} or None if unavailable."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from src.finviz_elite import fetch_elite_stock, is_elite_configured
        if not is_elite_configured():
            return None
        s = fetch_elite_stock(benchmark)
        if not s:
            return None

        def _safe_pct(val):
            p = _parse_pct(val)
            return 0.0 if pd.isna(p) else float(p)

        def _q(key, *fallbacks):
            v = s.get(key)
            if v is not None and str(v).strip() and str(v).strip() != "-":
                return v
            for k in fallbacks:
                v = s.get(k)
                if v is not None and str(v).strip() and str(v).strip() != "-":
                    return v
            return ""

        result = {
            "chg": _safe_pct(_q("Change", "change")),
            "week": _safe_pct(_q("Perf Week", "Week")),
            "month": _safe_pct(_q("Perf Month", "Month")),
            "qtr": _safe_pct(_q("Perf Quarter", "Perf Quarter", "Quarter")),
            "hyear": _safe_pct(_q("Perf Half Y", "Perf Half Y", "Half Y")),
            "year": _safe_pct(_q("Perf Year", "Perf Y", "Perf YTD", "Return% 1Y", "1Y")),
        }
        cache.put(cache_key, result, ttl=MEDIUM)
        return result
    except Exception as e:
        logger.warning("fetch_benchmark_performance %s failed: %s", benchmark, e)
        return None


def fetch_gainers_screener(cache_key: str = "finviz_gainers", ttl: int = MEDIUM) -> list[dict]:
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


def fetch_tickers_bulk_csv(tickers: list[str], cache_key: str | None = None, ttl: int = MEDIUM) -> list[dict]:
    """Fetch multiple tickers in one request via FinViz export.ashx.
    Uses v=141 (Performance) for Avg Vol, Rel Vol. URL format: v=141&f=geo_usa&t=AMD,NVDA,GOOGL
    Returns list of dicts with ticker, price, change, volume, avg_vol, rel_vol, atr_pct."""
    if not tickers:
        return []
    tickers = [t.strip().upper() for t in tickers if t and str(t).strip()]
    if not tickers:
        return []

    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            s = cached[0] if cached else {}
            if s.get("avg_vol") or s.get("rel_vol"):
                return cached
            cache.invalidate(cache_key)

    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured

        if not is_elite_configured():
            return []
        ticker_str = ",".join(tickers)
        # c=1,47,61,62,63,64,65 = Ticker,ATR,AvgVol,RelVol,Price,Change,Volume
        url = f"https://elite.finviz.com/export.ashx?v=141&f=geo_usa&t={ticker_str}&c=1,47,61,62,63,64,65"
        data = fetch_export_from_url(url, caller=cache_key or "watchlist")
        if not data:
            return []

        keys = list(data[0].keys())
        ticker_col = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"
        price_col = _find_csv_col(keys, exact="Price") or _find_csv_col(keys, "price")
        change_col = _find_csv_col(keys, exact="Change") or _find_csv_col(keys, "change")
        vol_col = _find_csv_col(keys, exact="Volume") or _find_csv_col(keys, "volume")
        avg_vol_col = _find_csv_col(keys, "average", "vol") or _find_csv_col(keys, "avg", "vol")
        rel_vol_col = _find_csv_col(keys, "relative", "vol") or _find_csv_col(keys, "rel", "vol")
        atr_col = _find_csv_col(keys, exact="ATR") or _find_csv_col(keys, "atr")

        def _val(row: dict, col: str | None, *fallbacks: str):
            if col and row.get(col) not in (None, "", "-"):
                v = row.get(col)
                if v is not None and str(v).strip():
                    return v
            return _get_csv_val(row, *fallbacks) if fallbacks else ""

        rows = []
        for row in data:
            t = str(row.get(ticker_col, "") or "").strip().upper()
            if not t:
                continue
            price = _val(row, price_col, "Price", "price", "Last", "Close")
            change = _val(row, change_col, "Change", "change")
            vol = _val(row, vol_col, "Volume", "volume")
            avg_vol = _val(row, avg_vol_col, "Avg Volume", "Average Volume", "avg_volume", "Avg Vol")
            rel_vol = _val(row, rel_vol_col, "Rel Volume", "Relative Volume", "rel_volume", "Rel Vol")
            if not rel_vol and vol and avg_vol:
                v_num, a_num = _parse_num(vol), _parse_num(avg_vol)
                if v_num and a_num and a_num != 0:
                    rel_vol = f"{v_num / a_num:.2f}"
            atr_val = _parse_num(_val(row, atr_col, "ATR", "atr")) if atr_col else None
            price_num = _parse_num(price) if price else None
            atr_pct = round((atr_val / price_num * 100), 2) if atr_val and price_num and price_num != 0 else None
            rows.append({
                "ticker": t,
                "price": price,
                "change": change,
                "volume": vol,
                "avg_vol": avg_vol,
                "rel_vol": rel_vol,
                "atr_pct": atr_pct,
            })
        if rows and cache_key:
            cache.put(cache_key, rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_tickers_bulk_csv failed: %s", e)
        return []


def _fetch_vix_via_yfinance() -> dict | None:
    """Fetch VIX quote via yfinance (^VIX)."""
    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="5d")
        if hist.empty or len(hist) < 1:
            return None
        last = hist.iloc[-1]
        price = float(last["Close"])
        prev = float(hist.iloc[-2]["Close"]) if len(hist) >= 2 else price
        chg = ((price - prev) / prev * 100) if prev and prev != 0 else 0.0
        return {
            "ticker": "VIX",
            "price": f"{price:.2f}",
            "change": f"{chg:+.2f}%",
        }
    except Exception as e:
        logger.warning("yfinance VIX fetch failed: %s", e)
        return None


def fetch_live_index_quotes(ttl: int = FAST) -> list[dict]:
    """Fetch live quotes for QQQ, SPY, DIA, IWM, VIX. Cached 5 min for intraday snapshot.
    Uses FinViz for ETFs; yfinance for VIX."""
    cache_key = "live_index_quotes"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from src.finviz_elite import fetch_elite_stock, is_elite_configured

        rows: list[dict] = []

        for t in LIVE_INDEX_TICKERS:
            if t == "VIX":
                vix_row = _fetch_vix_via_yfinance()
                if vix_row:
                    rows.append(vix_row)
                continue

            if not is_elite_configured():
                continue
            s = fetch_elite_stock(t)
            if not s:
                time.sleep(_FINVIZ_DELAY_SEC)
                continue
            price = _parse_num(_get_csv_val(s, "Price", "price", "Last", "Close"))
            if price is None:
                time.sleep(_FINVIZ_DELAY_SEC)
                continue
            change = _parse_pct(_get_csv_val(s, "Change", "change"))
            chg_val = 0.0 if (change is None or (isinstance(change, float) and change != change)) else float(change)
            rows.append({
                "ticker": t,
                "price": f"{price:.2f}" if price >= 1 else f"{price:.4f}",
                "change": f"{chg_val:+.2f}%",
            })
            time.sleep(_FINVIZ_DELAY_SEC)

        if rows:
            cache.put(cache_key, rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_live_index_quotes failed: %s", e)
        return []


def fetch_watchlist_quotes(tickers: list[str]) -> list[dict]:
    """Fetch day's data from Finviz quote.ashx for watchlist tickers.
    Returns list of dicts with ticker, price, change, volume, avg_vol, rel_vol."""
    from src.finviz_elite import fetch_elite_stock, is_elite_configured

    if not is_elite_configured() or not tickers:
        return []

    cache_key = f"watchlist_quotes_{','.join(sorted(tickers))}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    rows = []
    for t in tickers[:50]:
        try:
            s = fetch_elite_stock(t)
            if not s:
                continue
            price = _get_csv_val(s, "Price", "price", "Last", "Close")
            change = _get_csv_val(s, "Change", "change")
            volume = _get_csv_val(s, "Volume", "volume")
            avg_vol = _get_csv_val(s, "Avg Volume", "Average Volume", "avg_volume")
            rel_vol = _get_csv_val(s, "Rel Volume", "Relative Volume", "rel_volume")
            atr_val = _parse_num(_get_csv_val(s, "ATR (14)", "ATR", "atr", "Average True Range"))
            price_num = _parse_num(price) if price else None
            atr_pct = round((atr_val / price_num * 100), 2) if atr_val and price_num and price_num != 0 else None
            rows.append({
                "ticker": t,
                "price": price,
                "change": change,
                "volume": volume,
                "avg_vol": avg_vol,
                "rel_vol": rel_vol,
                "atr_pct": atr_pct,
            })
            time.sleep(_FINVIZ_DELAY_SEC)
        except Exception:
            pass

    if rows:
        cache.put(cache_key, rows, ttl=MEDIUM)
    return rows


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
            price = _parse_num(_get_csv_val(s, "Price", "price", "Last", "Close"))
            if price is None:
                continue
            change = _parse_pct(_get_csv_val(s, "Change", "change"))
            prev = price / (1 + change / 100) if not pd.isna(change) and change != -100 else price
            rows.append({
                "ticker": t,
                "close": price,
                "open": price,
                "high": price,
                "low": price,
                "volume": _parse_num(_get_csv_val(s, "Volume", "volume")),
                "prev_close": prev,
            })
        except Exception:
            pass
    df = pd.DataFrame(rows)
    if cache_key and not df.empty:
        cache.put(cache_key, df, ttl=MEDIUM)
    return df
