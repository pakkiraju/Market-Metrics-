"""Fetch market data from FinViz Elite API only.

Uses export.ashx for screeners and quote.ashx for single-ticker data.
Requires FINVIZ_API_KEY in .env. FinViz data is delayed ~15-20 min.
"""

import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import cache
from src.cache import MEDIUM, FAST, KEY_METRICS_TTL
from src.usa_v152_columns import ALIASES, USA_V152, V152_PARSED

logger = logging.getLogger(__name__)

# Live index snapshot: QQQ, SPY, DIA, IWM, VIX (5-min cache for intraday)
LIVE_INDEX_TICKERS = ["QQQ", "SPY", "DIA", "IWM", "VIX"]

# Delay between FinViz fetches to avoid 429 rate limit (override via FINVIZ_DELAY_SEC in .env)
_FINVIZ_DELAY_SEC = float(os.environ.get("FINVIZ_DELAY_SEC", "1.25"))
# Set FINVIZ_PARALLEL_WORKERS=2 (or higher) to overlap multi-screener fetches; default 0 = sequential
_FINVIZ_PARALLEL_WORKERS = int(os.environ.get("FINVIZ_PARALLEL_WORKERS", "0"))

ROOT = Path(__file__).resolve().parent.parent
WATCHLIST_FILE = ROOT / "watchlist.csv"

# Single FinViz USA export (v=152 all columns) for Key Metrics — cached, then filtered per index in Python.
USA_FULL_V152_CACHE_KEY = "usa_full_v152"
USA_V152_PARSED_DF_CACHE_KEY = "usa_v152_parsed_df_v2"

# Leading Industries + Thematics bundle: same cached USA v=152 as Key Metrics (FINVIZ_USA_FULL_V152_EXPORT), then in-app filter.
_THEMATICS_LIQUID_MIN_PRICE = 1.0
_THEMATICS_LIQUID_MIN_AVG_VOL = 1_000_000  # shares (not dollar volume)


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
    """Run multiple Screener calls (e.g. idx_sp500 + idx_ndx) and merge.

    Sequential by default. Set FINVIZ_PARALLEL_WORKERS>=2 to run fetches in parallel
    (staggered by index to reduce burst rate); may trigger 429 if FinViz limits are strict.
    """
    if not filter_sets:
        return pd.DataFrame()

    n = len(filter_sets)
    parallel = min(_FINVIZ_PARALLEL_WORKERS, n) if _FINVIZ_PARALLEL_WORKERS >= 2 else 0

    def _fetch_idx(i: int, filters: list[str]) -> tuple[int, pd.DataFrame]:
        if parallel > 1:
            time.sleep(i * (_FINVIZ_DELAY_SEC / max(n, 1)))
        elif i > 0:
            time.sleep(_FINVIZ_DELAY_SEC)
        ck = f"{cache_key}_{i}_{table}" if cache_key else None
        df = _fetch_screener(filters=filters, table=table, cache_key=ck, order=order, ttl=ttl)
        return i, df

    ordered_dfs: list[pd.DataFrame]
    if parallel > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        by_idx: dict[int, pd.DataFrame] = {}
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            futs = [ex.submit(_fetch_idx, i, f) for i, f in enumerate(filter_sets)]
            for fut in as_completed(futs):
                i, df = fut.result()
                by_idx[i] = df
        ordered_dfs = [by_idx[i] for i in range(n)]
    else:
        ordered_dfs = []
        for i, filters in enumerate(filter_sets):
            _, df = _fetch_idx(i, filters)
            ordered_dfs.append(df)

    dfs_rows = []
    seen = set()
    for df in ordered_dfs:
        if df.empty:
            continue
        ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
        for _, row in df.iterrows():
            t = str(row.get(ticker_col, "")).strip().upper()
            if t and t not in seen:
                seen.add(t)
                dfs_rows.append(row)
    if not dfs_rows:
        return pd.DataFrame()
    return pd.DataFrame(dfs_rows)


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


def _looks_like_earnings_date(val) -> bool:
    """True when value looks like a usable earnings date (legacy / layout guard)."""
    return _coerce_earnings_date_str(val) is not None


def _coerce_earnings_date_str(val) -> str | None:
    """Normalize FinViz cell to a display string: text dates, or Excel serial numbers (common in CSV exports)."""
    if val is None:
        return None
    if isinstance(val, float) and val == val:
        try:
            if abs(val - round(val)) < 1e-6:
                val = int(round(val))
        except (OverflowError, ValueError):
            pass
    s = str(val).strip()
    if not s or s == "-":
        return None
    # Row index / rank (not dates)
    if re.fullmatch(r"\d{1,3}", s):
        return None
    if s.isdigit() and len(s) <= 3:
        return None
    # Excel serial date (FinViz often exports 5-digit integers, e.g. ~45xxx ≈ 2023–2026)
    if s.isdigit() and len(s) == 5:
        n = int(s)
        if 35000 <= n <= 60000:
            try:
                from datetime import datetime, timedelta

                dt = datetime(1899, 12, 30) + timedelta(days=n)
                return dt.strftime("%b %d, %Y")
            except (OverflowError, ValueError, OSError):
                return None
    if re.search(r"[/-]|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec", s, re.I):
        return s
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s
    return None


def _pick_earnings_date_column(keys: list[str], sample_rows: list[dict]) -> str | None:
    """Pick CSV column with earnings dates (handles varied FinViz header names)."""
    bad = frozenset({"no", "no.", "#", "index", "rank"})
    # Exact header (FinViz often uses this)
    for k in keys:
        if str(k).strip().lower() == "earnings date":
            return k
    candidates: list[str] = []
    for k in keys:
        lk = str(k).strip().lower()
        if lk in bad:
            continue
        if "earnings" in lk and "date" in lk:
            candidates.append(k)
        elif "next" in lk and "earnings" in lk and "date" in lk:
            candidates.append(k)
        elif lk == "earnings" or lk.startswith("earnings "):
            candidates.append(k)
    best_k, best_score = None, 0
    for k in candidates:
        score = sum(1 for row in sample_rows[:40] if _coerce_earnings_date_str(row.get(k)))
        if score > best_score:
            best_k, best_score = k, score
    if best_k is not None and best_score >= 1:
        return best_k
    for k in keys:
        lk = str(k).strip().lower()
        if lk in bad or "date" not in lk:
            continue
        if not any(x in lk for x in ("earnings", "report", "next", "eps")):
            continue
        score = sum(1 for row in sample_rows[:40] if _coerce_earnings_date_str(row.get(k)))
        if score > best_score:
            best_k, best_score = k, score
    if best_k is not None and best_score >= 1:
        return best_k
    for k in candidates:
        if str(k).strip().lower() == "earnings date":
            return k
    if len(candidates) == 1:
        return candidates[0]
    return None


def _parse_display_date_to_date(val) -> date | None:
    """Parse coerced earnings display string (e.g. Feb 24, 2025) to a calendar date."""
    s = str(val).strip() if val is not None else ""
    if not s:
        return None
    # ISO or m/d with time suffix
    if " " in s and re.match(r"\d{4}-\d{2}-\d{2}", s):
        s = s.split()[0]
    if " " in s and re.match(r"\d{1,2}/\d{1,2}/\d{4}", s):
        s = s.split()[0]
    for fmt in ("%b %d, %Y", "%b %d %Y", "%m/%d/%Y", "%Y-%m-%d", "%b %d, %y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _strip_earnings_time_suffix(s: str) -> str:
    """Remove BMO/AMC and similar so the leading token is parseable as a date."""
    s = str(s).strip()
    if not s:
        return s
    s = re.split(r"(?:\s+|\s*[/-]\s*)(?:BMO|AMC|A\.?H\.?|before\s+market|after\s+hours)\b", s, maxsplit=1, flags=re.I)[0].strip()
    return s


def _earnings_cell_to_calendar_date(
    ed_coerced: str,
    today_et: date,
    yesterday_et: date,
) -> date | None:
    """Turn FinViz earnings cell text into a calendar date (ET). Handles year-less Mon DD."""
    s = _strip_earnings_time_suffix(ed_coerced)
    if not s:
        return None
    d = _parse_display_date_to_date(s)
    if d is not None:
        return d if d in (today_et, yesterday_et) else None
    # Month + day only (e.g. Mar 24, Mar 24,) — match ET today/yesterday
    m = re.match(r"^([A-Za-z]{3})\s+(\d{1,2})\b", s)
    if m:
        mon_s, day_i = m.group(1), int(m.group(2))
        try:
            md = datetime.strptime(f"{mon_s} {day_i}", "%b %d")
        except ValueError:
            return None
        month, day = md.month, md.day
        if (today_et.month, today_et.day) == (month, day):
            return today_et
        if (yesterday_et.month, yesterday_et.day) == (month, day):
            return yesterday_et
        return None
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
        mcap_col = _find_csv_col(keys, "market", "cap") or _find_csv_col(keys, "marketcap")
        short_float_col = (
            _find_csv_col(keys, "short", "float")
            or _find_csv_col(keys, exact="Short Float")
            or _find_csv_col(keys, "short", "interest")
        )
        # Prefer News Title/Headline (actual news text). "News" alone is often a count (1,2,3). Exclude "No." (row number).
        _exclude_news = frozenset({"no", "no.", "#", "rank"})
        news_col = _find_csv_col(keys, "news", "title") or _find_csv_col(keys, "headline")
        if not news_col:
            c = _find_csv_col(keys, exact="News") or _find_csv_col(keys, "news")
            if c and str(c).strip().lower() not in _exclude_news:
                news_col = c
        news_link_col = (_find_csv_col(keys, "news", "link") or _find_csv_col(keys, "link") or
                        _find_csv_col(keys, "url") or _find_csv_col(keys, "news", "url"))

        earnings_date_col = _pick_earnings_date_column(keys, data)

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
            if mcap_col:
                mc_raw = _val(row, mcap_col, "Market Cap", "market_cap")
                if mc_raw not in (None, "", "-"):
                    row_dict["mkt_cap"] = str(mc_raw).strip()
            if short_float_col:
                sf_raw = _val(row, short_float_col, "Short Float", "Short Interest")
                if sf_raw not in (None, "", "-"):
                    sfs = str(sf_raw).strip().rstrip("%").strip()
                    if sfs:
                        row_dict["short_float_pct"] = f"{sfs}%"
            if earnings_date_col:
                ed = _val(row, earnings_date_col, "Earnings Date")
                coerced = _coerce_earnings_date_str(ed)
                if coerced:
                    row_dict["earnings_date"] = coerced
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


def fetch_pre_market_scanner(ttl: int = MEDIUM) -> list[dict]:
    """Pre-market Scanner: USA v152 parsed cache — gap vs prior close ±3%, liquidity/rel vol filters; news from same v152 row."""
    _cache_key = "pre_market_scanner_v3"
    cached = cache.get(_cache_key)
    if cached is not None:
        return cached

    from src.usa_v152_columns import USA_V152

    df = get_parsed_usa_v152_df()
    if df.empty:
        return []
    U = USA_V152
    pv = V152_PARSED
    close = pd.to_numeric(df["close"], errors="coerce")
    prev = pd.to_numeric(df["prev_close"], errors="coerce")
    op = pd.to_numeric(df["open_price"], errors="coerce")
    avgv = pd.to_numeric(df.get("avg_volume"), errors="coerce")
    vol = pd.to_numeric(df.get("volume"), errors="coerce")
    liq = avgv.where(avgv.notna(), vol).fillna(0)
    rel = pd.to_numeric(df["rel_volume"], errors="coerce").fillna(0)
    gap_pct = (op - prev) / prev * 100.0
    gap_pct = gap_pct.where(prev.notna() & (prev > 0))
    m = (
        (close > 1.0)
        & (liq >= 1000)
        & (rel >= 1.0)
        & gap_pct.notna()
        & ((gap_pct >= 3.0) | (gap_pct <= -3.0))
    )
    sub = df.loc[m].copy()
    if sub.empty:
        return []
    sub["_gap"] = gap_pct.loc[m]
    sub["_ag"] = sub["_gap"].abs()
    sub = sub.sort_values("_ag", ascending=False)

    def _cell(x) -> str:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        s = str(x).strip()
        return s if s and s not in ("-", "—") else ""

    rows: list[dict] = []
    for _, r in sub.iterrows():
        t = str(r["ticker"]).strip().upper()
        g = float(r["_gap"])
        c = float(pd.to_numeric(r.get("close"), errors="coerce") or 0)
        dc = float(pd.to_numeric(r.get("day_chg"), errors="coerce") or 0)
        v_raw = r.get("volume")
        a_raw = r.get("avg_volume")
        rv = float(pd.to_numeric(r.get("rel_volume"), errors="coerce") or 0)
        rows.append({
            U.TICKER: t,
            "ticker": t,
            "Gap": f"{g:.2f}%",
            U.PRICE: f"{c:.2f}",
            U.CHANGE: f"{dc:.2f}%",
            U.VOLUME: v_raw,
            U.AVG_VOLUME: a_raw,
            U.REL_VOLUME: f"{rv:.2f}" if rv else "",
            U.NEWS_TIME: _cell(r.get(pv.NEWS_TIME)),
            U.NEWS_TITLE: _cell(r.get(pv.NEWS_TITLE)),
            U.NEWS_URL: _cell(r.get(pv.NEWS_URL)),
            U.DAILY_DIGEST: _cell(r.get(pv.DAILY_DIGEST)),
        })
    if rows:
        rows = rows[:150]
        cache.put(_cache_key, rows, ttl=ttl)
    return rows


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
    """Thematics universe: Key Metrics USA v152 + in-app filter; same source as Leading / Thematics by Sector."""
    cached = cache.get(cache_key)
    if cached is not None and isinstance(cached, pd.DataFrame):
        return cached
    if cached is not None:
        cache.invalidate(cache_key)  # Bad cache (e.g. string from disk)

    try:
        indicators = fetch_usa_thematics_universe_indicators()
        if indicators.empty:
            return pd.DataFrame()

        # Map industry/sector to theme (Industry = many themes; Sector = 11 fallback)
        ind = indicators.get("industry", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        sec = indicators.get("sector", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        ind_valid = (ind.str.len() > 0) & (ind != "-") & (ind != "")
        sec_valid = (sec.str.len() > 0) & (sec != "-") & (sec != "")
        theme = ind.where(ind_valid, sec.where(sec_valid, "Uncategorized"))

        pv = V152_PARSED
        result = pd.DataFrame({
            pv.TICKER: indicators[pv.TICKER],
            "theme": theme,
            pv.DAY_CHG: indicators[pv.DAY_CHG].fillna(0),
            pv.WEEK_CHG: indicators[pv.WEEK_CHG],
            pv.MONTH_CHG: indicators[pv.MONTH_CHG],
            pv.QTR_CHG: indicators[pv.QTR_CHG],
            pv.YEAR_CHG: indicators[pv.YEAR_CHG],
        })
        if pv.VOLATILITY_WEEK in indicators.columns:
            result[pv.VOLATILITY_WEEK] = indicators[pv.VOLATILITY_WEEK]
        if pv.VOLATILITY_MONTH in indicators.columns:
            result[pv.VOLATILITY_MONTH] = indicators[pv.VOLATILITY_MONTH]
        if not result.empty:
            cache.put(cache_key, result, ttl=ttl)
        return result
    except Exception as e:
        logger.warning("fetch_thematics_data failed: %s", e)
        return pd.DataFrame()


def fetch_earnings_this_week(ttl: int = MEDIUM) -> list[dict]:
    """Earnings this week, sorted by market cap (largest first). Merges Overview (Market Cap) + Performance (Avg Vol, Rel Vol)."""
    cached = cache.get("earnings_this_week")
    if cached is not None:
        return cached

    try:
        from src.finviz_elite import fetch_export_from_url, fetch_elite_by_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS, FINVIZ_SCREENER_URLS

        if not is_elite_configured():
            return []
        # 1. Overview: Market Cap
        url_overview = FINVIZ_EXPORT_URLS.get("earnings_this_week_overview")
        if not url_overview:
            return []
        time.sleep(_FINVIZ_DELAY_SEC)
        overview_data = fetch_export_from_url(url_overview, caller="earnings_this_week_overview")
        if not overview_data:
            # Fallback: use HTML screener when export.ashx redirects to login (some auth configs)
            url_screener = FINVIZ_SCREENER_URLS.get("earnings_this_week")
            if url_screener:
                overview_data = fetch_elite_by_url(url_screener)
            if not overview_data:
                return []
        mcap_map = {}
        ed_map: dict[str, str] = {}
        o_keys = list(overview_data[0].keys())
        o_ticker = _find_csv_col(o_keys, exact="Ticker") or _find_csv_col(o_keys, "ticker") or "Ticker"
        o_mcap = _find_csv_col(o_keys, "market", "cap") or _find_csv_col(o_keys, "marketcap")
        o_ed_col = _pick_earnings_date_column(o_keys, overview_data)
        for row in overview_data:
            t = str(row.get(o_ticker, "") or "").strip().upper()
            if not t:
                continue
            mcap_str = _get_csv_val(row, "Market Cap", "market_cap") or row.get(o_mcap)
            market_cap = _parse_num(mcap_str) if mcap_str else None
            if market_cap and market_cap > 0 and "B" not in str(mcap_str or "").upper() and "M" not in str(mcap_str or "").upper():
                if market_cap >= 1000:
                    market_cap = market_cap * 1e6
            mcap_map[t] = market_cap
            if o_ed_col:
                c = _coerce_earnings_date_str(row.get(o_ed_col))
                if c:
                    ed_map[t] = c

        # 1b. Financial (v=161): Earnings Date is often present here but missing from v=111 overview export.
        url_fin = FINVIZ_EXPORT_URLS.get("earnings_this_week_financial")
        if url_fin:
            time.sleep(_FINVIZ_DELAY_SEC)
            fin_data = fetch_export_from_url(url_fin, caller="earnings_this_week_financial")
            if fin_data:
                fk = list(fin_data[0].keys())
                f_ticker = _find_csv_col(fk, exact="Ticker") or _find_csv_col(fk, "ticker") or "Ticker"
                f_ed_col = _pick_earnings_date_column(fk, fin_data)
                if f_ed_col:
                    for row in fin_data:
                        t = str(row.get(f_ticker, "") or "").strip().upper()
                        if not t:
                            continue
                        c = _coerce_earnings_date_str(row.get(f_ed_col))
                        if c:
                            ed_map[t] = c

        # 2. Performance: Avg Vol, Rel Vol, Price, Change, Volume, ATR
        url_perf = FINVIZ_EXPORT_URLS.get("earnings_this_week_perf")
        if not url_perf:
            return []
        time.sleep(_FINVIZ_DELAY_SEC)
        perf_data = fetch_export_from_url(url_perf, caller="earnings_this_week_perf")
        if not perf_data:
            # Fallback: use HTML screener when export.ashx redirects to login
            url_screener_perf = FINVIZ_SCREENER_URLS.get("earnings_this_week_perf")
            if url_screener_perf:
                perf_data = fetch_elite_by_url(url_screener_perf)
            if not perf_data:
                return []

        keys = list(perf_data[0].keys())
        ticker_col = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"
        price_col = _find_csv_col(keys, exact="Price") or _find_csv_col(keys, "price")
        change_col = _find_csv_col(keys, exact="Change") or _find_csv_col(keys, "change")
        vol_col = _find_csv_col(keys, exact="Volume") or _find_csv_col(keys, "volume")
        avg_vol_col = _find_csv_col(keys, exact="Average Volume") or _find_csv_col(keys, "average", "vol") or _find_csv_col(keys, "avg", "vol")
        rel_vol_col = _find_csv_col(keys, exact="Relative Volume") or _find_csv_col(keys, "relative", "vol") or _find_csv_col(keys, "rel", "vol")
        atr_col = _find_csv_col(keys, exact="ATR") or _find_csv_col(keys, "atr")

        def _v(row, col, *alts):
            if col and row.get(col) not in (None, "", "-"):
                v = row.get(col)
                if v is not None and str(v).strip():
                    return v
            return _get_csv_val(row, *alts) if alts else ""

        rows = []
        for row in perf_data:
            t = str(row.get(ticker_col, "") or "").strip().upper()
            if not t:
                continue
            price = _v(row, price_col, "Price", "price")
            change = _v(row, change_col, "Change", "change")
            vol = _v(row, vol_col, "Volume", "volume")
            avg_vol = row.get("Average Volume") or row.get("Avg Volume") or _v(row, avg_vol_col, "Average Volume", "Avg Volume", "avg_vol", "Avg Vol")
            rel_vol = row.get("Relative Volume") or row.get("Rel Volume") or _v(row, rel_vol_col, "Relative Volume", "Rel Volume", "rel_vol", "Rel Vol")
            if not rel_vol and vol and avg_vol:
                v_num, a_num = _parse_num(vol), _parse_num(avg_vol)
                if v_num and a_num and a_num != 0:
                    rel_vol = f"{v_num / a_num:.2f}"
            atr_val = _parse_num(_v(row, atr_col, "ATR", "atr")) if atr_col else None
            price_num = _parse_num(price) if price else None
            atr_pct = round((atr_val / price_num * 100), 2) if atr_val and price_num and price_num != 0 else None
            # Earnings date: from overview (v=111) only — perf export has no reliable date column here.
            edate = ed_map.get(t, "")
            rows.append({
                "ticker": t,
                "market_cap": mcap_map.get(t),
                "price": price,
                "change": change,
                "volume": vol,
                "avg_vol": avg_vol,
                "rel_vol": rel_vol,
                "atr_pct": atr_pct,
                "earnings_date": edate,
            })
        rows.sort(key=lambda x: (x.get("market_cap") or 0), reverse=True)
        if rows:
            cache.put("earnings_this_week", rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_earnings_this_week failed: %s", e)
        return []


def _merge_earnings_dates_from_financial(rows: list[dict], fin_url_key: str) -> list[dict]:
    """Attach Earnings Date from v=161 Financial export when perf export omits it."""
    if not rows:
        return rows
    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_EXPORT_URLS

        if not is_elite_configured():
            return rows
        url = FINVIZ_EXPORT_URLS.get(fin_url_key)
        if not url:
            return rows
        time.sleep(_FINVIZ_DELAY_SEC)
        fin_data = fetch_export_from_url(url, caller=fin_url_key)
        if not fin_data:
            return rows
        fk = list(fin_data[0].keys())
        ft = _find_csv_col(fk, exact="Ticker") or _find_csv_col(fk, "ticker") or "Ticker"
        f_ed_col = _pick_earnings_date_column(fk, fin_data)
        if not f_ed_col:
            return rows
        ed_map: dict[str, str] = {}
        for row in fin_data:
            t = str(row.get(ft, "") or "").strip().upper()
            if not t:
                continue
            c = _coerce_earnings_date_str(row.get(f_ed_col))
            if c:
                ed_map[t] = c
        if not ed_map:
            return rows
        out: list[dict] = []
        for r in rows:
            rr = dict(r)
            t = str(rr.get("ticker", "") or "").strip().upper()
            if t in ed_map:
                rr["earnings_date"] = ed_map[t]
            out.append(rr)
        return out
    except Exception as e:
        logger.warning("merge earnings dates from financial (%s): %s", fin_url_key, e)
        return rows


def fetch_earnings_yesterday_today_via_finviz_filtered(ttl: int = MEDIUM) -> list[dict]:
    """FinViz `earningsdate_today|yesterday` universe + perf columns; merge Earnings Date from v=161 when needed."""
    rows = fetch_screener_from_url("earnings_yesterday_today_perf", "earnings_yesterday_today_perf_fetch", ttl=ttl)
    rows = _merge_earnings_dates_from_financial(rows, "earnings_yesterday_today_financial")
    if rows:
        cache.put("earnings_yesterday_today", rows, ttl=ttl)
    return rows


def fetch_earnings_yesterday_today(ttl: int = MEDIUM) -> list[dict]:
    """Earnings yesterday or today (ET): prefer USA v152 + Earnings Date column; else FinViz filtered exports."""
    cached = cache.get("earnings_yesterday_today")
    if cached is not None:
        return cached

    raw = fetch_usa_full_v152_raw()
    if not raw:
        return fetch_earnings_yesterday_today_via_finviz_filtered(ttl)
    keys = list(raw[0].keys())
    ed_col = _pick_earnings_date_column(keys, raw)
    if not ed_col:
        logger.info(
            "earnings_yesterday_today: no earnings date column in v152 export; using FinViz earningsdate_today|yesterday exports (sample keys: %s)",
            keys[:20],
        )
        return fetch_earnings_yesterday_today_via_finviz_filtered(ttl)
    ticker_col = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"
    df = get_parsed_usa_v152_df()
    if df.empty:
        return fetch_earnings_yesterday_today_via_finviz_filtered(ttl)
    idx = df.set_index("ticker")
    et = ZoneInfo("America/New_York")
    today = datetime.now(et).date()
    yesterday = today - timedelta(days=1)
    rows_out: list[dict] = []
    seen: set[str] = set()
    for row in raw:
        ed_raw = row.get(ed_col)
        ed = _coerce_earnings_date_str(ed_raw)
        if not ed:
            continue
        d = _earnings_cell_to_calendar_date(ed, today, yesterday)
        if d is None:
            continue
        t = str(row.get(ticker_col, "") or "").strip().upper()
        if not t or t in seen:
            continue
        if t not in idx.index:
            continue
        sel = idx.loc[t]
        ser = sel.iloc[0] if isinstance(sel, pd.DataFrame) else sel
        close = pd.to_numeric(ser.get("close"), errors="coerce")
        avgv = pd.to_numeric(ser.get("avg_volume"), errors="coerce")
        vol = pd.to_numeric(ser.get("volume"), errors="coerce")
        liq = float(avgv) if avgv is not None and not pd.isna(avgv) else None
        if liq is None or pd.isna(liq):
            liq = float(vol) if vol is not None and not pd.isna(vol) else 0.0
        if close is None or pd.isna(close) or close <= 1.0 or liq < 1000:
            continue
        rdict = _intraday_screener_dict_from_parsed_row(ser)
        if not rdict:
            continue
        rdict["earnings_date"] = ed
        rows_out.append(rdict)
        seen.add(t)
    rows_out.sort(key=lambda r: (r.get("earnings_date") or "", r.get("ticker") or ""))
    if not rows_out:
        sample_ed = [
            _coerce_earnings_date_str(raw[i].get(ed_col))
            for i in range(min(8, len(raw)))
        ]
        logger.debug(
            "earnings_yesterday_today: 0 tickers for ET today=%s yesterday=%s; ed_col=%r; sample cells=%s",
            today,
            yesterday,
            ed_col,
            sample_ed,
        )
        fb = fetch_earnings_yesterday_today_via_finviz_filtered(ttl)
        if fb:
            return fb
    else:
        cache.put("earnings_yesterday_today", rows_out, ttl=ttl)
    return rows_out


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


def fetch_sp500_landscape_data(cache_key: str = "sp500_landscape", ttl: int = MEDIUM) -> list[dict]:
    """S&P 500 stocks: Revenue, Net Income, Market Cap, Price, 12M Change, Profit Margin — from USA v152 only (no extra exports)."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from src.finviz_elite import is_elite_configured

        if not is_elite_configured():
            logger.warning("FinViz Elite not configured - S&P 500 Landscape unavailable")
            return []

        raw = fetch_usa_full_v152_raw()
        if not raw:
            return []

        keys = list(raw[0].keys())
        ticker_col = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"
        mcap_col = _find_csv_col(keys, "market", "cap") or _find_csv_col(keys, "marketcap")
        pe_col = _find_csv_col(keys, "p/e", "pe") or _find_csv_col(keys, "price", "earnings")
        ps_col = _find_csv_col(keys, "p/s", "ps") or _find_csv_col(keys, "price", "sales")
        sector_col = _find_csv_col(keys, exact="Sector") or _find_csv_col(keys, "sector")

        def _v(row, col, *alts):
            if col and row.get(col) not in (None, "", "-"):
                v = row.get(col)
                if v is not None and str(v).strip():
                    return v
            return _get_csv_val(row, *alts) if alts else ""

        rows = []
        for row in raw:
            if not _row_matches_key_metrics_group(row, "SPY500"):
                continue
            t = str(row.get(ticker_col, "") or "").strip().upper()
            if not t:
                continue

            mcap_str = _v(row, mcap_col, "Market Cap", "market_cap", "Market Cap.")
            market_cap = _parse_num(mcap_str) if mcap_str else None
            if market_cap and market_cap > 0 and "B" not in str(mcap_str or "").upper() and "M" not in str(mcap_str or "").upper() and "T" not in str(mcap_str or "").upper():
                if market_cap >= 1000:
                    market_cap = market_cap * 1e6

            pe_val = _parse_num(_v(row, pe_col, "P/E", "PE", "Price/Earnings"))
            ps_val = _parse_num(_v(row, ps_col, "P/S", "PS", "Price/Sales"))

            revenue = None
            net_income = None
            profit_margin = None
            if market_cap and market_cap > 0:
                if ps_val is not None and ps_val > 0:
                    revenue = market_cap / ps_val
                if pe_val is not None and pe_val > 0:
                    net_income = market_cap / pe_val
                elif pe_val is not None and pe_val < 0:
                    net_income = market_cap / pe_val
                if revenue and revenue > 0 and net_income is not None:
                    profit_margin = (net_income / revenue) * 100

            price = _parse_num(_v(row, "Price", "price", "Last", "Close"))
            if price is None or price <= 0:
                continue
            ychg = _parse_pct(_v(row, "Performance (YTD)", "Performance (Year)", "Perf Year", "Perf Y", "Perf YTD", "Perf. Year", "Perf 1Y", "1Y"))
            if ychg is None or pd.isna(ychg):
                ychg = 0.0
            else:
                ychg = float(ychg)

            sector = str(_v(row, sector_col, "Sector", "sector") or "").strip() or "Unknown"
            rows.append({
                "ticker": t,
                "sector": sector,
                "revenue": revenue,
                "profitability": profit_margin,
                "net_income": net_income,
                "market_cap": market_cap,
                "price": float(price),
                "change_12m": ychg,
                "profit_margin": profit_margin,
            })

        rows.sort(key=lambda x: (x["market_cap"] or 0), reverse=True)
        if rows:
            cache.put(cache_key, rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_sp500_landscape_data failed: %s", e)
        return []


def fetch_watchlist_sector_options() -> list[dict]:
    """Return dropdown options for watchlist sector selector: My Watchlist first, then sectors from S&P 500 data."""
    from src.constants import SECTOR_NAMES

    options = [{"label": "My Watchlist", "value": "watchlist"}]
    try:
        data = fetch_sp500_landscape_data()
        sectors = sorted(set((str(r.get("sector", "") or "").strip() or "Unknown") for r in data if r.get("sector")))
        for s in sectors:
            if s and s != "Unknown":
                options.append({"label": s, "value": s})
    except Exception:
        # Fallback to standard sector names if landscape fetch fails
        for name in sorted(SECTOR_NAMES.values()):
            if name != "S&P Equal Weight":
                options.append({"label": name, "value": name})
    return options


# Map display names to possible FinViz sector values (FinViz may use different labels)
_SECTOR_NAME_ALIASES = {
    "Communication Svcs": ["Communication Svcs", "Communication Services"],
    "Financials": ["Financials", "Financial Services"],
    "Consumer Defensive": ["Consumer Defensive", "Consumer Staples"],
}


def fetch_stocks_by_sector(sector_name: str, ttl: int = MEDIUM) -> list[dict]:
    """S&P 500 names in a sector — sliced from parsed USA v152 (no extra export)."""
    if not sector_name or not str(sector_name).strip():
        return []
    sector_name = str(sector_name).strip()
    cache_key = f"watchlist_sector_{sector_name.replace(' ', '_').replace('/', '_')}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        df = get_parsed_usa_v152_df()
        if df.empty:
            return []
        raw = fetch_usa_full_v152_raw()
        sp500_tickers: set[str] = set()
        if raw:
            keys = list(raw[0].keys())
            tc = _find_csv_col(keys, exact="Ticker") or _find_csv_col(keys, "ticker") or "Ticker"
            for row in raw:
                if not _row_matches_key_metrics_group(row, "SPY500"):
                    continue
                t = str(row.get(tc, "") or "").strip().upper()
                if t:
                    sp500_tickers.add(t)
        if not sp500_tickers:
            return []
        sector_matches = {sector_name}
        sector_matches.update(_SECTOR_NAME_ALIASES.get(sector_name, []))
        sec_s = df["sector"].fillna("").astype(str).str.strip()
        mask = df["ticker"].isin(sp500_tickers) & sec_s.isin(sector_matches)
        sub = df.loc[mask]
        rows = []
        for _, r in sub.iterrows():
            rows.append({
                "ticker": r["ticker"],
                "price": r["close"],
                "change": r["day_chg"],
                "volume": r["volume"],
                "avg_vol": r["avg_volume"],
                "rel_vol": r["rel_volume"],
                "atr_pct": r["atr_pct"],
            })
        rows.sort(key=lambda x: x["ticker"])
        if rows:
            cache.put(cache_key, rows, ttl=ttl)
        return rows
    except Exception as e:
        logger.warning("fetch_stocks_by_sector failed: %s", e)
        return []


def fetch_stage_indicators(cache_key: str = "ind_stage") -> pd.DataFrame:
    """Stage universe from USA v152: price > $1, avg volume >= 1000 shares (Finviz screener equivalent)."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        from src.finviz_elite import is_elite_configured
        if not is_elite_configured():
            return pd.DataFrame()
        df = get_parsed_usa_v152_df()
        if df.empty:
            return pd.DataFrame()
        m = (df["close"] > 1.0) & (df["avg_volume"].fillna(0) >= 1000)
        result = df.loc[m].copy()
        if not result.empty:
            cache.put(cache_key, result, ttl=MEDIUM)
        return result
    except Exception as e:
        logger.warning("fetch_stage_indicators failed: %s", e)
    return pd.DataFrame()


# Map cache_key to export URL key(s) for single-request fetch. None = use legacy _fetch_screener_multi.
_GROUP_INDICATOR_URL_KEYS = {
    "ind_$1B+": ["ind_1b_km"],
    "ind_97_club": ["ind_1b"],  # ind_1b has Avg Vol, Rel Vol, Volume (ind_1b_km v=152 does not)
    "ind_9m_movers": ["ind_9m"],
    "ind_leading": ["ind_1b"],
    # ind_USA: single v=141 export (same columns as legacy 3-merge; one HTTP request)
    "ind_USA": ["ind_usa"],
    "ind_thematics_rrg": ["ind_thematics_rrg"],
    "ind_NQ100": ["ind_ndx"],
    "ind_RSP": ["ind_sp500"],
    "ind_DJIA": ["ind_dji"],
    "ind_RUS2000": ["ind_rut"],
    "ind_Composite": ["ind_sp500", "ind_ndx", "ind_dji"],
}


def _find_20d_high_column(keys: list[str]) -> str | None:
    """FinViz full export: absolute 20-day high price column (not 50D/52W, not SMA)."""
    for k in keys:
        kl = str(k).strip().lower()
        if "20" not in kl or "high" not in kl:
            continue
        if "sma" in kl or "rsi" in kl:
            continue
        if "52" in kl or "50-day" in kl or "50 day" in kl:
            continue
        return k
    return None


def _find_20d_low_column(keys: list[str]) -> str | None:
    for k in keys:
        kl = str(k).strip().lower()
        if "20" not in kl or "low" not in kl:
            continue
        if "sma" in kl or "rsi" in kl:
            continue
        if "52" in kl or "50-day" in kl or "50 day" in kl:
            continue
        return k
    return None


def _row_matches_key_metrics_group(row: dict, group_name: str) -> bool:
    """Subset of USA full CSV to match FinViz index / $1B+ filters (INDEX_BASE_FILTERS)."""
    if group_name == "NQ100":
        idx = str(_get_csv_val(row, *ALIASES["index"]) or "").upper()
        return "NDX" in idx or "NASDAQ-100" in idx
    if group_name == "SPY500":
        idx = str(_get_csv_val(row, *ALIASES["index"]) or "")
        iu = idx.replace(" ", "").upper()
        return "S&P500" in iu or "S&P 500" in idx or "SP500" in iu
    if group_name == "DJIA":
        idx = str(_get_csv_val(row, *ALIASES["index"]) or "").upper()
        return "DJIA" in idx
    if group_name == "RUS2000":
        idx = str(_get_csv_val(row, *ALIASES["index"]) or "").upper()
        return "RUT" in idx or "RUSSELL 2000" in idx or "RUSSELL2000" in idx.replace(" ", "")
    if group_name == "$1B+":
        mcap_str = _get_csv_val(row, *ALIASES["market_cap"]) or ""
        mcap = _parse_num(mcap_str) if mcap_str else None
        if mcap is not None and mcap > 0 and mcap < 1e7:
            u = str(mcap_str or "").upper()
            if "B" not in u and "M" not in u and "T" not in u:
                mcap = mcap * 1e6
        price = _parse_num(_get_csv_val(row, *ALIASES["price"]))
        avgv = _parse_num(_get_csv_val(row, *ALIASES["avg_volume"]))
        if mcap is None or mcap < 1e9:
            return False
        if price is None or price <= 1.0:
            return False
        if avgv is None or avgv < 1000:
            return False
        return True
    return False


def fetch_usa_full_v152_raw(ttl: int | None = None) -> list[dict]:
    """One Elite export: all US stocks, all v=152 columns. Cached (Key Metrics TTL)."""
    ttl = KEY_METRICS_TTL if ttl is None else ttl
    cached = cache.get(USA_FULL_V152_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        from src.finviz_elite import fetch_export_from_url, is_elite_configured
        from src.constants import FINVIZ_USA_FULL_V152_EXPORT

        if not is_elite_configured():
            return []
        cache.invalidate(USA_V152_PARSED_DF_CACHE_KEY)
        data = fetch_export_from_url(
            FINVIZ_USA_FULL_V152_EXPORT,
            caller="usa_full_v152",
            timeout=120,
        )
        if data:
            cache.put(USA_FULL_V152_CACHE_KEY, data, ttl=ttl)
        return data or []
    except Exception as e:
        logger.warning("fetch_usa_full_v152_raw failed: %s", e)
        return []


def fetch_key_metrics_indicators_for_group(group_name: str) -> tuple[pd.DataFrame, dict]:
    """Key Metrics: filter cached USA full export to one index/universe. meta may request 20d NH/NL URL fallback."""
    meta: dict = {"use_20d_url_fallback": False}
    raw = fetch_usa_full_v152_raw()
    if not raw:
        return pd.DataFrame(), meta
    keys = list(raw[0].keys())
    if _find_20d_high_column(keys) is None or _find_20d_low_column(keys) is None:
        meta["use_20d_url_fallback"] = True
    filtered = [r for r in raw if _row_matches_key_metrics_group(r, group_name)]
    rows = _parse_group_indicators_rows(filtered, None)
    if not rows:
        return pd.DataFrame(), meta
    return pd.DataFrame(rows), meta


def _parse_group_indicators_rows(data: list[dict], ticker_set: set | None) -> list[dict]:
    """Parse export data into group indicator row format. Single DataFrame with all columns."""
    if not data:
        return []
    keys = list(data[0].keys())
    V = USA_V152
    ticker_col = _find_csv_col(keys, exact=V.TICKER) or _find_csv_col(keys, "ticker") or V.TICKER
    hi20_col = _find_20d_high_column(keys)
    lo20_col = _find_20d_low_column(keys)

    def _v(row, *alts):
        return _get_csv_val(row, *alts)

    def _news_cell_raw(val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        s = str(val).strip()
        if not s or s in ("-", "—"):
            return None
        return s

    rows = []
    for row in data:
        t = str(row.get(ticker_col, "") or "").strip().upper()
        if not t or (ticker_set and t not in ticker_set):
            continue
        price = _parse_num(_v(row, *ALIASES["price"]))
        if price is None or price <= 0:
            continue
        change = _parse_pct(_v(row, *ALIASES["change"]))
        if pd.isna(change):
            change = 0.0
        open_price = _parse_num(_v(row, V.OPEN, "open"))
        if open_price is None or open_price <= 0:
            open_price = price
        open_chg_val = _parse_pct(_v(row, V.CHANGE_FROM_OPEN, "Change from Open %", "Change from Open%"))
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

        sma20_pct = _parse_num(_v(row, V.SMA20, "20-Day SMA", "20-Day SMA (Relative)", "20-Day Simple Moving Average", "sma20"))
        sma50_pct = _parse_num(_v(row, V.SMA50, "50-Day SMA", "50-Day SMA (Relative)", "50-Day Simple Moving Average", "sma50"))
        sma200_pct = _parse_num(_v(row, V.SMA200, "200-Day SMA", "200-Day SMA (Relative)", "200-Day Simple Moving Average", "sma200"))
        sma10_pct = _parse_num(_v(row, "SMA10", "10-Day SMA", "sma10"))
        ema10_pct = _parse_num(_v(row, "EMA10", "10-Day EMA", "10-Day Exponential Moving Average", "ema10"))
        sma20 = _pct_to_sma(sma20_pct, price)
        sma50 = _pct_to_sma(sma50_pct, price)
        sma200 = _pct_to_sma(sma200_pct, price)
        sma10 = _pct_to_sma(sma10_pct, price) if sma10_pct is not None else sma20
        ema10 = _pct_to_sma(ema10_pct, price) if ema10_pct is not None else sma20
        vol = _parse_num(_v(row, *ALIASES["volume"]))
        avg_vol = _parse_num(_v(row, *ALIASES["avg_volume"]))
        rel_vol = _parse_num(_v(row, *ALIASES["rel_volume"]))
        if rel_vol is None and vol and avg_vol and avg_vol != 0:
            rel_vol = vol / avg_vol
        mcap_str = _v(row, *ALIASES["market_cap"])
        market_cap = _parse_num(mcap_str) if mcap_str else None
        if market_cap is not None and market_cap > 0 and market_cap < 1e7 and "B" not in str(mcap_str or "").upper() and "M" not in str(mcap_str or "").upper():
            market_cap = market_cap * 1e6
        high52 = _parse_num(_v(row, V.HIGH_52W, "52-Week High"))
        low52 = _parse_num(_v(row, V.LOW_52W, "52-Week Low"))
        atr_val = _parse_num(_v(row, V.ATR, "ATR (14)", "Average True Range", "atr", "ATR(14)"))
        vol_w_raw = _v(row, *ALIASES["volatility_w"])
        vol_m_raw = _v(row, *ALIASES["volatility_m"])
        vol_week = _parse_pct(vol_w_raw) if vol_w_raw not in (None, "", "-", "—") else float("nan")
        vol_month = _parse_pct(vol_m_raw) if vol_m_raw not in (None, "", "-", "—") else float("nan")
        week_chg = _pct(V.PERF_WEEK, "Performance (Week)", "Perf. Week", "Perf Week %", "1W", "Perf 1W")
        month_chg = _pct(V.PERF_MONTH, "Performance (Month)", "Perf. Month", "Perf Month %", "1M", "Perf 1M")
        qtr_chg = _pct(V.PERF_QUART, "Performance (Quarter)", "Perf Quarter", "Perf Q", "Perf. Quarter", "3M", "Perf 3M")
        half_chg = _pct(V.PERF_HALF, "Performance (Half Year)", "Perf Half Y", "Perf. Half", "Perf 6M", "6M")
        year_chg = _pct(V.PERF_YTD, "Performance (YTD)", "Performance (Year)", V.PERF_YEAR, "Perf Y", "Perf YTD", "Perf. Year", "Perf 1Y", "1Y")
        industry = str(_v(row, V.INDUSTRY, "industry") or "").strip()
        sector = str(_v(row, V.SECTOR, "sector") or "").strip()
        news_time = _news_cell_raw(_v(row, V.NEWS_TIME, "News Time"))
        news_title = _news_cell_raw(_v(row, V.NEWS_TITLE, "News Title"))
        news_url = _news_cell_raw(_v(row, V.NEWS_URL, "News URL"))
        daily_digest = _news_cell_raw(_v(row, V.DAILY_DIGEST, "Daily Digest"))
        h20p = _parse_num(row.get(hi20_col)) if hi20_col else None
        l20p = _parse_num(row.get(lo20_col)) if lo20_col else None
        new_hi = bool(
            h20p is not None and h20p > 0 and price >= h20p * 0.999
        )
        new_lo = bool(
            l20p is not None and l20p > 0 and price <= l20p * 1.001
        )
        prev_close = float(price / (1 + change / 100)) if change != -100 else float(price)
        rows.append({
            "ticker": t,
            "close": float(price),
            "prev_close": prev_close,
            "open_price": float(open_price),
            "open": float(open_price),
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
            "volatility_week": None if pd.isna(vol_week) else float(vol_week),
            "volatility_month": None if pd.isna(vol_month) else float(vol_month),
            "high_20": h20p,
            "low_20": l20p,
            "price_to_20_range": 50.0,
            "high_52w": high52,
            "low_52w": low52,
            "volume": vol,
            "avg_volume": avg_vol if avg_vol is not None else vol,
            "rel_volume": rel_vol,
            "market_cap": market_cap,
            "new_20_high": new_hi,
            "new_20_low": new_lo,
            "industry": industry or sector,
            "sector": sector,
            "news_time": news_time,
            "news_title": news_title,
            "news_url": news_url,
            "daily_digest": daily_digest,
        })
    return rows


def get_parsed_usa_v152_df() -> pd.DataFrame:
    """Parsed USA v=152 rows as DataFrame. Cached; invalidated when `usa_full_v152` is refreshed."""
    cached = cache.get(USA_V152_PARSED_DF_CACHE_KEY)
    if cached is not None:
        return cached
    raw = fetch_usa_full_v152_raw()
    if not raw:
        return pd.DataFrame()
    rows = _parse_group_indicators_rows(raw, None)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    cache.put(USA_V152_PARSED_DF_CACHE_KEY, df, ttl=KEY_METRICS_TTL)
    return df


def _intraday_screener_dict_from_parsed_row(r: pd.Series) -> dict | None:
    """Normalize one parsed v152 row for intraday screener tables (Stocks in Play / Earnings)."""
    pv = V152_PARSED
    t = str(r.get(pv.TICKER) or "").strip().upper()
    if not t:
        return None
    close = pd.to_numeric(r.get(pv.CLOSE), errors="coerce")
    if close is None or pd.isna(close) or float(close) <= 0:
        return None
    day_chg = float(pd.to_numeric(r.get(pv.DAY_CHG), errors="coerce") or 0)
    vol = r.get(pv.VOLUME)
    avg_vol = r.get(pv.AVG_VOLUME)
    v_num = pd.to_numeric(vol, errors="coerce")
    a_num = pd.to_numeric(avg_vol, errors="coerce")
    v_num = float(v_num) if v_num is not None and not pd.isna(v_num) else None
    a_num = float(a_num) if a_num is not None and not pd.isna(a_num) else None
    rel = r.get(pv.REL_VOLUME)
    rel_f = pd.to_numeric(rel, errors="coerce")
    rel_f = float(rel_f) if rel_f is not None and not pd.isna(rel_f) else None
    if rel_f is None and v_num and a_num and a_num != 0:
        rel_f = v_num / a_num
    rel_str = f"{rel_f:.2f}" if rel_f is not None else ""
    atr_raw = r.get(pv.ATR_PCT)
    atr_pct = pd.to_numeric(atr_raw, errors="coerce")
    if atr_pct is None or pd.isna(atr_pct):
        p = _parse_pct(atr_raw) if atr_raw not in (None, "", "-") else float("nan")
        atr_pct = None if pd.isna(p) else float(p)
    else:
        atr_pct = float(atr_pct)
    return {
        "ticker": t,
        "price": f"{float(close):.2f}",
        "change": f"{day_chg:.2f}%",
        "volume": vol,
        "avg_vol": avg_vol,
        "rel_vol": rel_str,
        "atr_pct": atr_pct,
    }


def fetch_stocks_in_play_from_usa_v152(ttl: int = MEDIUM) -> list[dict]:
    """Stocks In Play: USA v152 only — price > $1, liq ≥1K sh, rel vol ≥ 2; top rows by |day change|."""
    _sip_key = "stocks_in_play_v2"
    cached = cache.get(_sip_key)
    if cached is not None:
        return cached
    df = get_parsed_usa_v152_df()
    if df.empty:
        return []
    close = pd.to_numeric(df["close"], errors="coerce")
    avgv = pd.to_numeric(df.get("avg_volume"), errors="coerce")
    vol = pd.to_numeric(df.get("volume"), errors="coerce")
    liq = avgv.where(avgv.notna(), vol).fillna(0)
    rel = pd.to_numeric(df["rel_volume"], errors="coerce").fillna(0)
    m = (close > 1.0) & (liq >= 1000) & (rel >= 2.0)
    sub = df.loc[m].copy()
    if sub.empty:
        return []
    sub["abs_day"] = pd.to_numeric(sub["day_chg"], errors="coerce").fillna(0).abs()
    sub = sub.nlargest(75, "abs_day")
    rows: list[dict] = []
    for _, row in sub.iterrows():
        d = _intraday_screener_dict_from_parsed_row(row)
        if d:
            rows.append(d)
    if rows:
        cache.put(_sip_key, rows, ttl=ttl)
    return rows


def fetch_usa_thematics_universe_indicators() -> pd.DataFrame:
    """Key Metrics USA v152 parsed cache, filtered in-app. No separate FinViz export."""
    df = get_parsed_usa_v152_df()
    if df.empty:
        return pd.DataFrame()
    close = pd.to_numeric(df["close"], errors="coerce")
    avgv = pd.to_numeric(df.get("avg_volume"), errors="coerce")
    vol = pd.to_numeric(df.get("volume"), errors="coerce")
    # v152 often has NaN avg_volume in the sheet; use volume when avg is missing (same idea as parser row).
    liq = avgv.where(avgv.notna(), vol).fillna(0)
    m = (close > _THEMATICS_LIQUID_MIN_PRICE) & (liq >= _THEMATICS_LIQUID_MIN_AVG_VOL)
    out = df.loc[m].copy()
    if not out.empty:
        return out
    # If everyone failed (e.g. all liq NaN/0), match Finviz screener floor sh_avgvol_o1000 ≈ ≥1k shares
    m2 = (close > _THEMATICS_LIQUID_MIN_PRICE) & (liq >= 1000)
    return df.loc[m2].copy()


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
        "ind_97_club": [["cap_1to", "geo_usa", "sh_avgvol_o1000", "sh_price_o1"]],
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

        V = USA_V152

        def _v(*alts):
            return _get_csv_val(row, *alts)

        price = _parse_num(_v(*ALIASES["price"]))
        if price is None or price <= 0:
            continue

        change = _parse_pct(_v(*ALIASES["change"]))
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
        sma20_pct = _parse_num(_v(V.SMA20, "20-Day SMA", "20-Day Simple Moving Average", "sma20"))
        sma50_pct = _parse_num(_v(V.SMA50, "50-Day SMA", "50-Day Simple Moving Average", "sma50"))
        sma200_pct = _parse_num(_v(V.SMA200, "200-Day SMA", "200-Day Simple Moving Average", "sma200"))
        ema10_pct = _parse_num(_v("EMA10", "10-Day EMA", "10-Day Exponential Moving Average", "ema10"))
        sma20 = _pct_to_sma(sma20_pct, price)
        sma50 = _pct_to_sma(sma50_pct, price)
        sma200 = _pct_to_sma(sma200_pct, price)
        sma10 = _pct_to_sma(sma10_pct, price) if sma10_pct is not None else sma20
        ema10 = _pct_to_sma(ema10_pct, price) if ema10_pct is not None else sma20
        vol_str = _v(*ALIASES["volume"])
        vol = _parse_num(vol_str) if vol_str else None
        avg_vol_str = _v(*ALIASES["avg_volume"])
        avg_vol = _parse_num(avg_vol_str) if avg_vol_str else None
        rel_vol_str = _v(*ALIASES["rel_volume"])
        rel_vol = _parse_num(rel_vol_str) if rel_vol_str else None
        if rel_vol is None and vol and avg_vol and avg_vol != 0:
            rel_vol = vol / avg_vol
        mcap_str = _v(*ALIASES["market_cap"])
        market_cap = _parse_num(mcap_str) if mcap_str else None
        if market_cap is not None and market_cap > 0 and market_cap < 1e7 and "B" not in str(mcap_str or "").upper() and "M" not in str(mcap_str or "").upper():
            market_cap = market_cap * 1e6
        high52 = _parse_num(_v(V.HIGH_52W, "52-Week High"))
        low52 = _parse_num(_v(V.LOW_52W, "52-Week Low"))
        atr_val = _parse_num(_v(V.ATR, "Average True Range", "atr"))
        vol_w_raw = _v(*ALIASES["volatility_w"])
        vol_m_raw = _v(*ALIASES["volatility_m"])
        vol_week = _parse_pct(vol_w_raw) if vol_w_raw not in (None, "", "-", "—") else float("nan")
        vol_month = _parse_pct(vol_m_raw) if vol_m_raw not in (None, "", "-", "—") else float("nan")

        week_chg = _pct(V.PERF_WEEK, "Performance (Week)", "Perf. Week", "Perf Week %", "1W", "Perf 1W")
        month_chg = _pct(V.PERF_MONTH, "Performance (Month)", "Perf. Month", "Perf Month %", "1M", "Perf 1M")
        qtr_chg = _pct(V.PERF_QUART, "Performance (Quarter)", "Perf Quarter", "Perf Q", "Perf. Quarter", "3M", "Perf 3M")
        half_chg = _pct(V.PERF_HALF, "Performance (Half Year)", "Perf Half Y", "Perf. Half", "Perf 6M", "6M")
        year_chg = _pct(V.PERF_YTD, "Performance (YTD)", "Performance (Year)", V.PERF_YEAR, "Perf Y", "Perf YTD", "Perf. Year", "Perf 1Y", "1Y")

        industry = str(_v(V.INDUSTRY, "industry") or "").strip()
        sector = str(_v(V.SECTOR, "sector") or "").strip()

        pv = V152_PARSED
        rows.append({
            pv.TICKER: t,
            pv.CLOSE: float(price),
            pv.PREV_CLOSE: float(price / (1 + change / 100)) if change != -100 else price,
            pv.OPEN_PRICE: float(price),
            pv.OPEN: float(price),
            pv.DAY_CHG: float(change),
            pv.OPEN_CHG: float(change),
            pv.WEEK_CHG: week_chg,
            pv.MONTH_CHG: month_chg,
            pv.QTR_CHG: qtr_chg,
            pv.HALF_CHG: half_chg,
            pv.YEAR_CHG: year_chg,
            pv.SMA10: sma10,
            pv.SMA20: sma20,
            pv.SMA50: sma50,
            pv.SMA200: sma200,
            pv.EMA10: ema10,
            pv.ATR: atr_val,
            pv.ATR_PCT: round((atr_val / price * 100), 2) if atr_val and price else None,
            pv.VOLATILITY_WEEK: None if pd.isna(vol_week) else float(vol_week),
            pv.VOLATILITY_MONTH: None if pd.isna(vol_month) else float(vol_month),
            pv.HIGH_20: None,
            pv.LOW_20: None,
            pv.PRICE_TO_20_RANGE: 50.0,
            pv.HIGH_52W: high52,
            pv.LOW_52W: low52,
            pv.VOLUME: vol,
            pv.AVG_VOLUME: avg_vol if avg_vol is not None else vol,
            pv.REL_VOLUME: rel_vol,
            pv.MARKET_CAP: market_cap,
            pv.NEW_20_HIGH: False,
            pv.NEW_20_LOW: False,
            pv.INDUSTRY: industry or sector,
            pv.SECTOR: sector,
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
    """Sector SPDR ETF rows from USA v152 parsed cache (no quote.ashx per ticker)."""
    from src.constants import SECTOR_ETFS
    from src.finviz_elite import is_elite_configured

    if not is_elite_configured():
        logger.warning("FinViz Elite not configured - sector data unavailable")
        return []

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    df = get_parsed_usa_v152_df()
    if df.empty:
        return []

    def _sf(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        return float(v)

    rows = []
    for ticker in SECTOR_ETFS:
        sub = df.loc[df["ticker"] == ticker.upper()]
        if sub.empty:
            continue
        r = sub.iloc[0]
        price = _sf(r.get("close"))
        if price <= 0:
            continue
        change = _sf(r.get("day_chg"))
        prev_close = _sf(r.get("prev_close")) or (price / (1 + change / 100) if change != -100 else price)
        open_px = _sf(r.get("open_price")) if r.get("open_price") is not None else price
        open_px = open_px if open_px > 0 else price
        gap = ((open_px - prev_close) / prev_close * 100) if prev_close and prev_close != 0 else 0.0
        open_chg = _sf(r.get("open_chg"))
        rows.append({
            "sector": ticker,
            "ticker": ticker,
            "gap": round(gap, 2),
            "chg": round(change, 2),
            "ochg": round(open_chg, 2),
            "week": round(_sf(r.get("week_chg")), 1),
            "month": round(_sf(r.get("month_chg")), 1),
            "qtr": round(_sf(r.get("qtr_chg")), 1),
            "hyear": round(_sf(r.get("half_chg")), 1),
            "year": round(_sf(r.get("year_chg")), 1),
            "last": round(price, 2),
            "ema10": round(_sf(r.get("ema10")), 2) if r.get("ema10") is not None else round(price, 2),
            "sma20": round(_sf(r.get("sma20")), 2) if r.get("sma20") is not None else round(price, 2),
            "sma50": round(_sf(r.get("sma50")), 2) if r.get("sma50") is not None else round(price, 2),
            "sma200": round(_sf(r.get("sma200")), 2) if r.get("sma200") is not None else round(price, 2),
            "high_52w": round(_sf(r.get("high_52w")), 2) if r.get("high_52w") is not None else round(price, 2),
            "low_52w": round(_sf(r.get("low_52w")), 2) if r.get("low_52w") is not None else round(price, 2),
            "atr_pct": r.get("atr_pct"),
        })

    if rows:
        cache.put(cache_key, rows, ttl=MEDIUM)
    return rows


def fetch_benchmark_performance(benchmark: str = "VTI", cache_key: str = "rrg_benchmark") -> dict | None:
    """Benchmark (e.g. VTI) perf from USA v152 row; quote.ashx only if ticker missing from export."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _row_to_bench(r) -> dict:
        def _sf(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return 0.0
            return float(v)

        pv = V152_PARSED
        return {
            "chg": _sf(r.get(pv.DAY_CHG)),
            "week": _sf(r.get(pv.WEEK_CHG)),
            "month": _sf(r.get(pv.MONTH_CHG)),
            "qtr": _sf(r.get(pv.QTR_CHG)),
            "hyear": _sf(r.get(pv.HALF_CHG)),
            "year": _sf(r.get(pv.YEAR_CHG)),
        }

    try:
        df = get_parsed_usa_v152_df()
        if not df.empty:
            row = df.loc[df[V152_PARSED.TICKER] == benchmark.upper()]
            if not row.empty:
                result = _row_to_bench(row.iloc[0])
                cache.put(cache_key, result, ttl=MEDIUM)
                return result

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

        V = USA_V152
        result = {
            "chg": _safe_pct(_q(V.CHANGE, "change")),
            "week": _safe_pct(_q(V.PERF_WEEK, "Performance (Week)", "Week")),
            "month": _safe_pct(_q(V.PERF_MONTH, "Performance (Month)", "Month")),
            "qtr": _safe_pct(_q(V.PERF_QUART, "Performance (Quarter)", "Quarter")),
            "hyear": _safe_pct(_q(V.PERF_HALF, "Perf Half Y", "Half Y")),
            "year": _safe_pct(_q(V.PERF_YEAR, V.PERF_YTD, "Perf Y", "Return% 1Y", "1Y")),
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


def fetch_watchlist_quotes_from_usa_v152(tickers: list[str]) -> list[dict]:
    """Watchlist rows from parsed USA v152; sorted by sector then ticker. Same shape as fetch_tickers_bulk_csv."""
    if not tickers:
        return []
    pv = V152_PARSED
    df = get_parsed_usa_v152_df()
    if df.empty:
        return [{"ticker": str(t).upper().strip(), "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"} for t in tickers if t]
    tset = {str(t).upper().strip() for t in tickers if t}
    sub = df[df[pv.TICKER].isin(tset)]
    by_t = {r[pv.TICKER]: r for _, r in sub.iterrows()}
    rows = []
    for t in tickers:
        tu = str(t).upper().strip()
        r = by_t.get(tu)
        if r is None:
            rows.append({"ticker": tu, "price": "-", "change": "-", "volume": "-", "avg_vol": "-", "rel_vol": "-"})
            continue
        row = {
            "ticker": tu,
            "price": r[pv.CLOSE],
            "change": r[pv.DAY_CHG],
            "volume": r[pv.VOLUME],
            "avg_vol": r[pv.AVG_VOLUME],
            "rel_vol": r[pv.REL_VOLUME],
            "atr_pct": r[pv.ATR_PCT],
            "sector": str(r.get(pv.SECTOR) or "").strip(),
        }
        vw = r.get(pv.VOLATILITY_WEEK)
        if vw is not None and not pd.isna(vw):
            row[pv.VOLATILITY_WEEK] = vw
        vm = r.get(pv.VOLATILITY_MONTH)
        if vm is not None and not pd.isna(vm):
            row[pv.VOLATILITY_MONTH] = vm
        rows.append(row)
    rows.sort(key=lambda x: (str(x.get("sector") or ""), x["ticker"]))
    return rows


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
        open_v = float(last["Open"]) if "Open" in last.index else price
        return {
            "ticker": "VIX",
            "price": f"{price:.2f}",
            "change": f"{chg:+.2f}%",
            "open": f"{open_v:.2f}",
            "prev_close": f"{prev:.2f}",
            "volume": "",
        }
    except Exception as e:
        logger.warning("yfinance VIX fetch failed: %s", e)
        return None


def _fmt_snapshot_line_price(val) -> str:
    """Format price for snapshot sub-lines (Open / Prev)."""
    if val is None or val == "":
        return ""
    p = _parse_num(val)
    if p is None:
        s = str(val).strip()
        return s if s else ""
    return f"{p:.2f}" if p >= 1 else f"{p:.4f}"


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
            open_raw = _get_csv_val(s, "Open", "open")
            prev_raw = _get_csv_val(s, "Prev Close", "prev close", "Previous Close")
            vol_raw = _get_csv_val(s, "Volume", "volume")
            vol_disp = str(vol_raw).strip() if vol_raw not in (None, "", "-") else ""
            rows.append({
                "ticker": t,
                "price": f"{price:.2f}" if price >= 1 else f"{price:.4f}",
                "change": f"{chg_val:+.2f}%",
                "open": _fmt_snapshot_line_price(open_raw),
                "prev_close": _fmt_snapshot_line_price(prev_raw),
                "volume": vol_disp,
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
