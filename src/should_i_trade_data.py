"""Should I Be Trading? — Data aggregation for market environment evaluation.

Aggregates volatility, trend, breadth, momentum, and macro data from existing
fetchers (FinViz, yfinance, Stockbee, economic calendar, rate watch).
"""

import logging
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import requests

from src import cache
from src.cache import MEDIUM
from src.constants import KEY_METRIC_ROWS, SECTOR_SPDRS_RRG
from src.data_fetcher import (
    fetch_sector_data,
    fetch_live_index_quotes,
)
from src.stockbee import fetch_stockbee_breadth
from src.rate_watch_data import fetch_rate_watch_data

logger = logging.getLogger(__name__)

ET = timezone(timedelta(hours=-5))
SIT_CACHE_TTL = 30  # 30 seconds for should_i_trade aggregate

# Keywords for major macro events (FOMC, CPI, NFP, etc.)
MACRO_EVENT_KEYWORDS = (
    "fomc", "fed", "rate decision", "interest rate",
    "cpi", "consumer price", "inflation",
    "nfp", "nonfarm", "employment", "jobs report", "payroll",
)

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def _fetch_yf(ticker: str, period: str = "5d") -> pd.DataFrame | None:
    """Fetch yfinance history. Returns DataFrame or None."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=period)
        return hist if not hist.empty else None
    except Exception as e:
        logger.debug("yfinance %s failed: %s", ticker, e)
        return None


def _vix_slope(hist: pd.DataFrame) -> float | None:
    """Compute 5-day linear regression slope of VIX close."""
    if hist is None or len(hist) < 2:
        return None
    closes = hist["Close"].values.astype(float)
    x = np.arange(len(closes))
    try:
        slope = np.polyfit(x, closes, 1)[0]
        return float(slope)
    except Exception:
        return None


def _vix_percentile(vix_now: float, hist_1y: pd.DataFrame) -> float | None:
    """Compute 1-year percentile rank of current VIX."""
    if hist_1y is None or len(hist_1y) < 5 or vix_now is None:
        return None
    closes = hist_1y["Close"].dropna().values
    if len(closes) == 0:
        return None
    pct = (closes < vix_now).sum() / len(closes) * 100
    return float(pct)


def _estimate_put_call(vix: float) -> float:
    """Estimate Put/Call ratio from VIX regime."""
    if vix < 15:
        return 0.8
    if vix < 20:
        return 1.0
    if vix < 25:
        return 1.1
    return 1.2


def _fetch_volatility() -> dict:
    """Fetch volatility data: VIX, 5d slope, 1y percentile, VVIX, Put/Call estimate."""
    out = {
        "vix": None,
        "vix_5d_slope": None,
        "vix_1y_pct": None,
        "vvix": None,
        "put_call_est": None,
        "direction": "→",
    }
    hist_5d = _fetch_yf("^VIX", "5d")
    hist_1y = _fetch_yf("^VIX", "1y")
    if hist_5d is not None and len(hist_5d) >= 1:
        out["vix"] = float(hist_5d["Close"].iloc[-1])
        out["vix_5d_slope"] = _vix_slope(hist_5d)
        out["vix_1y_pct"] = _vix_percentile(out["vix"], hist_1y)
        out["put_call_est"] = _estimate_put_call(out["vix"])
        if out["vix_5d_slope"] is not None:
            out["direction"] = "↑" if out["vix_5d_slope"] > 0.5 else ("↓" if out["vix_5d_slope"] < -0.5 else "→")
    try:
        vvix_hist = _fetch_yf("^VVIX", "5d")
        if vvix_hist is not None and len(vvix_hist) >= 1:
            out["vvix"] = float(vvix_hist["Close"].iloc[-1])
    except Exception:
        pass
    return out


def _compute_rsi(series: pd.Series, period: int = 14) -> float | None:
    """Compute RSI from close series."""
    if series is None or len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else None


def _fetch_trend() -> dict:
    """Fetch trend data: SPY vs MAs, QQQ vs 50 MA, SPY RSI, regime."""
    out = {
        "spy_price": None,
        "spy_sma20": None,
        "spy_sma50": None,
        "spy_sma200": None,
        "spy_above_20": None,
        "spy_above_50": None,
        "spy_above_200": None,
        "qqq_price": None,
        "qqq_sma50": None,
        "qqq_above_50": None,
        "spy_rsi": None,
        "regime": "chop",
        "direction": "→",
    }
    # SPY (SPX proxy) — use yfinance as primary: ind_sp500 has S&P 500 stocks, not SPY ETF,
    # so we'd wrongly use another stock's data. yfinance gives correct SPY price and MAs.
    hist = _fetch_yf("SPY", "1y")
    if hist is not None and len(hist) >= 200:
        c = hist["Close"]
        out["spy_price"] = float(c.iloc[-1])
        out["spy_sma20"] = float(c.rolling(20).mean().iloc[-1])
        out["spy_sma50"] = float(c.rolling(50).mean().iloc[-1])
        out["spy_sma200"] = float(c.rolling(200).mean().iloc[-1])
        out["spy_above_20"] = out["spy_price"] > out["spy_sma20"]
        out["spy_above_50"] = out["spy_price"] > out["spy_sma50"]
        out["spy_above_200"] = out["spy_price"] > out["spy_sma200"]
    hist_spy = _fetch_yf("SPY", "1mo")
    if hist_spy is not None and len(hist_spy) >= 15:
        out["spy_rsi"] = _compute_rsi(hist_spy["Close"], 14)
    # Regime
    a20, a50, a200 = out["spy_above_20"], out["spy_above_50"], out["spy_above_200"]
    if a20 and a50 and a200:
        out["regime"] = "uptrend"
        out["direction"] = "↑"
    elif a20 is False and a50 is False and a200 is False:
        out["regime"] = "downtrend"
        out["direction"] = "↓"
    # QQQ — use yfinance as primary: FinViz quote.ashx "50-Day SMA" may be a percentage
    # (price vs SMA), not absolute price, which would wrongly compare price > pct.
    hist_qqq = _fetch_yf("QQQ", "1y")
    if hist_qqq is not None and len(hist_qqq) >= 50:
        c = hist_qqq["Close"]
        out["qqq_price"] = float(c.iloc[-1])
        out["qqq_sma50"] = float(c.rolling(50).mean().iloc[-1])
        out["qqq_above_50"] = out["qqq_price"] > out["qqq_sma50"]
    return out


def _fetch_breadth() -> dict:
    """Fetch breadth data: % above 20/50/200, A/D ratio, new highs vs lows."""
    out = {
        "pct_above_20": None,
        "pct_above_50": None,
        "pct_above_200": None,
        "ratio5": None,
        "ratio10": None,
        "up4": None,
        "down4": None,
        "new_highs": None,
        "new_lows": None,
        "direction": "→",
    }
    # Key metrics for SPY500
    metrics = cache.get("all_key_metrics")
    if metrics is None:
        from src.calculations import compute_all_key_metrics
        metrics = compute_all_key_metrics()
    sp500 = metrics.get("SPY500", [])
    if sp500:
        idx = {r: i for i, r in enumerate(KEY_METRIC_ROWS)}
        row_sma20 = sp500[idx["Price to SMA20"]] if "Price to SMA20" in idx and len(sp500) > idx["Price to SMA20"] else {}
        row_sma50 = sp500[idx["Price to SMA50"]] if "Price to SMA50" in idx and len(sp500) > idx["Price to SMA50"] else {}
        row_sma200 = sp500[idx["Price to SMA200"]] if "Price to SMA200" in idx and len(sp500) > idx["Price to SMA200"] else {}
        out["pct_above_20"] = row_sma20.get("pct")
        out["pct_above_50"] = row_sma50.get("pct")
        out["pct_above_200"] = row_sma200.get("pct")
        row_4pct = sp500[idx["4% Up vs 4% Down"]] if "4% Up vs 4% Down" in idx and len(sp500) > idx["4% Up vs 4% Down"] else {}
        out["up4"] = row_4pct.get("above")
        out["down4"] = row_4pct.get("below")
        row_highs = sp500[idx["New 20-Day Highs"]] if "New 20-Day Highs" in idx and len(sp500) > idx["New 20-Day Highs"] else {}
        row_lows = sp500[idx["New 20-Day Lows"]] if "New 20-Day Lows" in idx and len(sp500) > idx["New 20-Day Lows"] else {}
        out["new_highs"] = row_highs.get("above")
        out["new_lows"] = row_lows.get("above")
    breadth = fetch_stockbee_breadth()
    if breadth:
        out["ratio5"] = breadth.get("ratio5")
        out["ratio10"] = breadth.get("ratio10")
        if out["up4"] is None:
            out["up4"] = breadth.get("up4")
        if out["down4"] is None:
            out["down4"] = breadth.get("down4")
    if out["ratio5"] is not None:
        out["direction"] = "↑" if out["ratio5"] > 1.1 else ("↓" if out["ratio5"] < 0.9 else "→")
    return out


def _fetch_momentum() -> dict:
    """Fetch momentum data: 11 sector ETFs, top 3 vs bottom 3 spread, % higher highs."""
    out = {
        "sectors": [],
        "top3": [],
        "bottom3": [],
        "spread": None,
        "pct_higher_highs": None,
        "direction": "→",
    }
    sectors = fetch_sector_data()
    if not sectors:
        return out
    # Use 11 sector SPDRs (exclude RSP)
    sector_spdrs = [s for s in sectors if s.get("ticker") in SECTOR_SPDRS_RRG]
    if not sector_spdrs:
        sector_spdrs = sectors[:11]
    out["sectors"] = sector_spdrs
    sorted_chg = sorted(sector_spdrs, key=lambda x: x.get("chg") or 0, reverse=True)
    out["top3"] = sorted_chg[:3]
    out["bottom3"] = sorted_chg[-3:]
    if len(sorted_chg) >= 6:
        top_avg = sum((s.get("chg") or 0) for s in out["top3"]) / 3
        bot_avg = sum((s.get("chg") or 0) for s in out["bottom3"]) / 3
        out["spread"] = round(top_avg - bot_avg, 2)
        out["direction"] = "↑" if out["spread"] > 0.5 else ("↓" if out["spread"] < -0.5 else "→")
    metrics = cache.get("all_key_metrics")
    if metrics is None:
        from src.calculations import compute_all_key_metrics
        metrics = compute_all_key_metrics()
    sp500 = metrics.get("SPY500", [])
    idx = {r: i for i, r in enumerate(KEY_METRIC_ROWS)}
    if sp500 and "Stocks" in idx and "New 20-Day Highs" in idx:
        n = sp500[idx["Stocks"]].get("above") or 1
        highs = sp500[idx["New 20-Day Highs"]].get("above") or 0
        out["pct_higher_highs"] = round(highs / n * 100, 1) if n else None
    return out


def _fetch_macro() -> dict:
    """Fetch macro data: 10Y Treasury, DXY, Fed stance, FOMC/CPI within 72h."""
    out = {
        "tnx": None,
        "tnx_5d_trend": None,
        "dxy": None,
        "dxy_trend": None,
        "fed_stance": "neutral",
        "fed_rate_str": None,
        "fomc_within_72h": False,
        "fomc_today": False,
        "cpi_within_72h": False,
        "major_event_within_72h": False,
        "events_72h": [],
        "direction": "→",
    }
    hist_tnx = _fetch_yf("^TNX", "5d")
    if hist_tnx is not None and len(hist_tnx) >= 2:
        out["tnx"] = float(hist_tnx["Close"].iloc[-1])
        out["tnx_5d_trend"] = float(hist_tnx["Close"].iloc[-1]) - float(hist_tnx["Close"].iloc[0])
        out["direction"] = "↑" if out["tnx_5d_trend"] > 0.05 else ("↓" if out["tnx_5d_trend"] < -0.05 else "→")
    hist_dxy = _fetch_yf("DX-Y.NYB", "5d")
    if hist_dxy is not None and len(hist_dxy) >= 2:
        out["dxy"] = float(hist_dxy["Close"].iloc[-1])
        out["dxy_trend"] = float(hist_dxy["Close"].iloc[-1]) - float(hist_dxy["Close"].iloc[0])
    rate = fetch_rate_watch_data("USD")
    if rate:
        out["fed_rate_str"] = rate.get("current_rate_str")
        if rate.get("meetings"):
            m = rate["meetings"][0]
            cut = m.get("cut_pct") or 0
            hold = m.get("hold_pct") or 0
            hike = m.get("hike_pct") or 0
            if cut > hold and cut > hike:
                out["fed_stance"] = "dovish"
            elif hike > hold and hike > cut:
                out["fed_stance"] = "hawkish"
            else:
                out["fed_stance"] = "neutral"
    # Economic calendar within 72 hours
    try:
        r = requests.get(
            FF_CALENDAR_URL,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.debug("Economic calendar fetch failed: %s", e)
        return out
    if not isinstance(data, list):
        return out
    now_et = datetime.now(ET)
    for evt in data:
        date_str = evt.get("date") or ""
        if not date_str:
            continue
        try:
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                dt_et = dt.astimezone(ET)
            else:
                dt_et = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=ET)
            delta = (dt_et - now_et).total_seconds()
            if 0 <= delta <= 72 * 3600:
                title = (evt.get("title") or "").lower()
                if any(kw in title for kw in MACRO_EVENT_KEYWORDS):
                    out["major_event_within_72h"] = True
                    out["events_72h"].append({
                        "title": evt.get("title", ""),
                        "date": date_str[:16],
                    })
                    if any(x in title for x in ["fomc", "fed", "rate decision"]):
                        out["fomc_within_72h"] = True
                        # Check if event is today (same calendar day)
                        try:
                            evt_date = date_str.split("T")[0] if "T" in date_str else date_str[:10]
                            today_str = now_et.strftime("%Y-%m-%d")
                            if evt_date == today_str:
                                out["fomc_today"] = True
                        except Exception:
                            pass
                    if any(x in title for x in ["cpi", "consumer price", "inflation"]):
                        out["cpi_within_72h"] = True
        except (ValueError, TypeError):
            continue
    return out


def _fetch_ticker_tape() -> list[dict]:
    """Build ticker tape: SPY, QQQ, VIX, TNX, DXY, sector ETFs with % change."""
    tape = []
    # Live index quotes (SPY, QQQ, DIA, IWM, VIX)
    live = fetch_live_index_quotes()
    live_map = {str(r.get("ticker", "")).upper(): r for r in live}
    for t in ["QQQ", "SPY", "VIX", "DIA", "IWM"]:
        r = live_map.get(t)
        if r:
            chg = r.get("change", "0%")
            tape.append({"ticker": t if t != "SPY" else "SPX", "change": chg})
    # TNX, DXY from yfinance
    for sym, label in [("^TNX", "TNX"), ("DX-Y.NYB", "DXY")]:
        hist = _fetch_yf(sym, "5d")
        if hist is not None and len(hist) >= 2:
            now = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            pct = ((now - prev) / prev * 100) if prev else 0
            tape.append({"ticker": label, "change": f"{pct:+.2f}%"})
    # Sector ETFs (top movers)
    sectors = fetch_sector_data()
    for s in (sectors or [])[:8]:
        t = s.get("ticker", "")
        if t and t != "RSP":
            chg = s.get("chg") or 0
            tape.append({"ticker": t, "change": f"{chg:+.2f}%"})
    return tape


def fetch_should_i_trade_data(ttl: int = SIT_CACHE_TTL) -> dict:
    """Aggregate all data for Should I Be Trading? dashboard.
    Returns dict with volatility, trend, breadth, momentum, macro, ticker_tape, and timestamp."""
    cache_key = "should_i_trade_aggregate"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        vol = _fetch_volatility()
        trend = _fetch_trend()
        breadth = _fetch_breadth()
        momentum = _fetch_momentum()
        macro = _fetch_macro()
        ticker_tape = _fetch_ticker_tape()
        result = {
            "volatility": vol,
            "trend": trend,
            "breadth": breadth,
            "momentum": momentum,
            "macro": macro,
            "ticker_tape": ticker_tape,
            "timestamp": datetime.now(ET).isoformat(),
        }
        cache.put(cache_key, result, ttl=ttl)
        return result
    except Exception as e:
        logger.exception("Should I Trade data aggregation failed: %s", e)
        return {
            "volatility": {},
            "trend": {},
            "breadth": {},
            "momentum": {},
            "macro": {},
            "timestamp": datetime.now(ET).isoformat(),
            "error": str(e),
        }
