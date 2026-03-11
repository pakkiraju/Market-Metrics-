"""Qullamaggie-inspired screeners and placeholders.

Each screener returns a list of dicts with at minimum a 'ticker' key
and an optional 'color' key (green/yellow/orange/red/blue).
"""

import pandas as pd

from src.data_fetcher import (
    load_watchlist,
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
    """Gap up 10%+ with above-average volume (rel vol 2+). US-wide."""
    cached = cache.get("qulla_episodic_v2")
    if cached is not None:
        return cached
    try:
        df = _fetch_screener(
            filters=["geo_usa", "ta_gap_u10", "sh_relvol_o2", "sh_price_o1", "sh_avgvol_o1000"],
            table="Performance",
            cache_key="qulla_ep_usa",
            order="-change",
            ttl=FAST,
        )
        results = []
        if not df.empty:
            ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
            for _, r in df.iterrows():
                t = str(r.get(ticker_col, "")).strip().upper()
                if not t:
                    continue
                results.append({
                    "ticker": t,
                    "price": r.get("Price", r.get("price", "")),
                    "avg_vol": r.get("Average Volume", r.get("avg_volume", "")),
                    "rel_vol": r.get("Relative Volume", r.get("rel_volume", "")),
                    "change": r.get("Change", r.get("change", "")),
                    "volume": r.get("Volume", r.get("volume", "")),
                    "tag": "EP",
                })
        if results:
            cache.put("qulla_episodic_v2", results, ttl=FAST)
        return results
    except Exception:
        return []


# -----------------------------------------------------------------------
# 2. Parabolic Short: Large cap 50-100%, Small cap 300-1000% (FinViz screeners)
# -----------------------------------------------------------------------
PS_LARGE_FILTERS = "cap_largeover,geo_usa,ta_perf_50to-1w"
PS_SMALL_FILTERS = "cap_to9,geo_usa,ta_perf_300to-1w"


def parabolic_short_screener() -> list[dict]:
    """Parabolic Short via FinViz: large cap 50-100%, small cap 300-1000%."""
    cached = cache.get("qulla_parabolic_v2")
    if cached is not None:
        return cached
    try:
        rows = []
        seen = set()
        for filters, cache_key, ft in [
            ([PS_LARGE_FILTERS], "qulla_ps_large", "3"),
            ([PS_SMALL_FILTERS], "qulla_ps_small", "4"),
        ]:
            df = _fetch_screener(
                filters=filters,
                table="Performance",
                cache_key=cache_key,
                order="-change",
                ttl=MEDIUM,
                ft=ft,
            )
            if not df.empty:
                ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
                for _, r in df.iterrows():
                    t = str(r.get(ticker_col, "")).strip().upper()
                    if not t or t in seen:
                        continue
                    seen.add(t)
                    rows.append({
                        "ticker": t,
                        "price": r.get("Price", r.get("price", "")),
                        "avg_vol": r.get("Average Volume", r.get("avg_volume", "")),
                        "rel_vol": r.get("Relative Volume", r.get("rel_volume", "")),
                        "change": r.get("Change", r.get("change", "")),
                        "volume": r.get("Volume", r.get("volume", "")),
                        "tag": "PS",
                    })
        if rows:
            cache.put("qulla_parabolic_v2", rows, ttl=MEDIUM)
        return rows
    except Exception:
        return []


# -----------------------------------------------------------------------
# 3. Breakouts: FinViz screener (52w high 0-25%, perf 30d to -4w, price above SMA20)
# -----------------------------------------------------------------------
BREAKOUTS_FILTERS = "geo_usa,sh_avgvol_o1000,sh_price_o1,ta_highlow52w_0to25-bhx,ta_perf_30to-4w,tad_0_close::close:d|abvpct::10:|sma:20:sma:d"


def breakouts_screener() -> list[dict]:
    """Breakouts via FinViz: within 25% of 52w high, 30d perf -4% to 30%, price above SMA20."""
    cached = cache.get("qulla_breakouts_v2")
    if cached is not None:
        return cached
    try:
        df = _fetch_screener(
            filters=[BREAKOUTS_FILTERS],  # Single filter string (contains tad_)
            table="Performance",
            cache_key="qulla_breakouts",
            order="-change",
            ttl=MEDIUM,
        )
        rows = []
        if not df.empty:
            ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
            for _, r in df.iterrows():
                t = str(r.get(ticker_col, "")).strip().upper()
                if not t:
                    continue
                rows.append({
                    "ticker": t,
                    "price": r.get("Price", r.get("price", "")),
                    "avg_vol": r.get("Average Volume", r.get("avg_volume", "")),
                    "rel_vol": r.get("Relative Volume", r.get("rel_volume", "")),
                    "change": r.get("Change", r.get("change", "")),
                    "volume": r.get("Volume", r.get("volume", "")),
                    "tag": "BO",
                })
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
    return [by_ticker[t] for t in sorted(by_ticker.keys())]


# Minervini Trend Template: FinViz Elite filters (same as screener.ashx URL)
# Use export.ashx (CSV) - screener.ashx returns "0 Total" without session cookie; export.ashx works with auth param
MINERVINI_FILTERS = (
    "geo_usa,sh_avgvol_o1000,sh_price_o1,ta_sma200_pa,"
    "tad_0_sma:150:sma:d|abv:::1|close::close:d,tad_1_sma:200:sma:d|abv:::1|close::close:d,"
    "tad_2_sma:200:sma:d|abv:::1|sma:150:sma:d,tad_3_sma:50:sma:d|abv:::|sma:150:sma:d,"
    "tad_4_sma:50:sma:d|abv:::|sma:200:sma:d,tad_5_sma:50:sma:d|abv:::1|close::close:d,"
    "tad_6_close::close:d|abvpct:30::|hilo:52:low:d,tad_7_close::close:d|blwpct::25:|hilo:52:high:d,"
    "tad_8_rsi:14:rsi:d|abveq:::|value:::70"
)


def _fetch_minervini_from_url() -> pd.DataFrame | None:
    """Fetch Minervini via Elite export.ashx (CSV). Auth param works; screener.ashx HTML does not."""
    from src.finviz_elite import _fetch_elite_csv, is_elite_configured

    if not is_elite_configured():
        return None
    data = _fetch_elite_csv(MINERVINI_FILTERS, "Performance", "-change")
    if not data:
        return None
    return pd.DataFrame(data)


def minervini_screener(indicators=None) -> list[dict]:
    """Minervini Trend Template screener.

    Returns list of dicts with ticker, price, avg_vol, rel_vol, change, volume for table display.
    """
    cached = cache.get("minervini_table")
    if cached is not None:
        return cached
    try:
        df = _fetch_minervini_from_url()
        if df is not None and not df.empty:
            ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
            rows = []
            for _, r in df.iterrows():
                t = str(r.get(ticker_col, "")).strip().upper()
                if not t:
                    continue
                price = r.get("Price", r.get("price", ""))
                change = r.get("Change", r.get("change", ""))
                vol = r.get("Volume", r.get("volume", ""))
                avg_vol = r.get("Average Volume", r.get("avg_volume", ""))
                rel_vol = r.get("Relative Volume", r.get("rel_volume", ""))
                rows.append({
                    "ticker": t,
                    "price": price,
                    "avg_vol": avg_vol,
                    "rel_vol": rel_vol,
                    "change": change,
                    "volume": vol,
                })
            if rows:
                cache.put("minervini_table", rows, ttl=MEDIUM)
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
            if low52 <= 0 or (close - low52) / low52 < 0.30:
                continue
            if high52 <= 0 or (high52 - close) / high52 > 0.25:
                continue
            if float(r.get("rs_rank_month_chg") or 0) < 70:
                continue

            rows.append({
                "ticker": r["ticker"],
                "price": r.get("close"),
                "avg_vol": r.get("avg_volume"),
                "rel_vol": r.get("rel_volume"),
                "change": r.get("day_chg"),
                "volume": r.get("volume"),
            })

        if rows:
            cache.put("minervini_table", rows, ttl=MEDIUM)
        return rows
    except Exception:
        return []


# O'Neil / CANSLIM: EPS growth, positive ROE, positive net margin, US
ONEIL_FILTERS = (
    "fa_epsyoy_o25,fa_epsyoy1_o25,fa_epsyoyttm_pos,"
    "fa_netmargin_pos,fa_roe_pos,geo_usa"
)


def _parse_pct(val) -> float | None:
    """Parse percentage string (e.g. '25.5%', '25.5', '-') to float or None."""
    if val is None or val == "" or str(val).strip() in ("-", "—"):
        return None
    s = str(val).strip().replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _fetch_oneil_from_url() -> tuple[pd.DataFrame | None, dict[str, dict]]:
    """Fetch O'Neil via Elite export.ashx. Returns (Financial df, ticker->{avg_vol,rel_vol} from Performance)."""
    from src.finviz_elite import _fetch_elite_csv, is_elite_configured

    if not is_elite_configured():
        return None, {}
    # ft=2 = fundamental filter type for fa_* filters
    financial_data = _fetch_elite_csv(ONEIL_FILTERS, "Financial", "-change", ft="2")
    perf_data = _fetch_elite_csv(ONEIL_FILTERS, "Performance", "-change", ft="2")
    df = pd.DataFrame(financial_data) if financial_data else None
    # Build ticker -> {avg_vol, rel_vol} from Performance (has Avg Vol, Rel Vol)
    vol_map = {}
    if perf_data:
        first = perf_data[0]
        ticker_col = "Ticker" if "Ticker" in first else "ticker"
        avg_col = next((c for c in first if "average" in c.lower() and "vol" in c.lower()), "Average Volume")
        rel_col = next((c for c in first if "relative" in c.lower() and "vol" in c.lower()), "Relative Volume")
        for r in perf_data:
            t = str(r.get(ticker_col, "")).strip().upper()
            if t:
                vol_map[t] = {
                    "avg_vol": r.get(avg_col, r.get("Average Volume", r.get("avg_volume", ""))),
                    "rel_vol": r.get(rel_col, r.get("Relative Volume", r.get("rel_volume", ""))),
                }
    return df, vol_map


def oneil_screener(indicators=None) -> list[dict]:
    """O'Neil / CANSLIM screener.

    Uses Finviz filters: EPS YoY >25%, EPS YoY1 >25%, EPS TTM pos, Net Margin pos, ROE pos, USA.
    Fetches ROE and Net Profit Margin, filters to ROE + Net Margin >= 25%.
    """
    cached = cache.get("oneil_table")
    if cached is not None:
        return cached
    try:
        df, vol_map = _fetch_oneil_from_url()
        if df is None or df.empty:
            return []

        ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
        # Finviz Financial view: ROE, Profit M (Net Profit Margin); Performance has Avg Vol, Rel Vol
        roe_col = next(
            (c for c in df.columns if "roe" in c.lower() or "return on equity" in c.lower()),
            None,
        )
        margin_col = next(
            (
                c
                for c in df.columns
                if ("net" in c.lower() and "margin" in c.lower())
                or c.lower() in ("profit m", "profit margin", "net margin")
            ),
            None,
        )

        rows = []
        for _, r in df.iterrows():
            t = str(r.get(ticker_col, "")).strip().upper()
            if not t:
                continue

            roe_val = _parse_pct(r.get(roe_col) if roe_col else None)
            margin_val = _parse_pct(r.get(margin_col) if margin_col else None)

            # Filter: ROE + Net Profit Margin >= 25%
            roe_num = roe_val if roe_val is not None else 0
            margin_num = margin_val if margin_val is not None else 0
            if roe_num + margin_num < 25:
                continue

            vol_info = vol_map.get(t, {})
            rows.append({
                "ticker": t,
                "price": r.get("Price", r.get("price", "")),
                "avg_vol": vol_info.get("avg_vol", ""),
                "rel_vol": vol_info.get("rel_vol", ""),
                "change": r.get("Change", r.get("change", "")),
                "volume": r.get("Volume", r.get("volume", "")),
                "roe": roe_val,
                "net_margin": margin_val,
            })

        if rows:
            cache.put("oneil_table", rows, ttl=MEDIUM)
        return rows
    except Exception:
        return []


def watchlist_tickers() -> list[dict]:
    """Load personal watchlist from config CSV."""
    tickers = load_watchlist()
    return [{"ticker": t, "color": "green"} for t in tickers]
