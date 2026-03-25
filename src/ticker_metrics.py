"""Ticker metrics for TradingView modal: raw USA v=152 row + quote fallback."""

from __future__ import annotations

import re
from typing import Any

from src.data_fetcher import _parse_num
from src.usa_v152_columns import USA_V152

U = USA_V152

# Large numeric fields: show with commas and K/M/B (same idea as Market Cap, Volume, etc.)
_FORMAT_VALUE_LABELS: frozenset[str] = frozenset({
    U.MARKET_CAP,
    U.ENTERPRISE_VALUE,
    U.VOLUME,
    U.AVG_VOLUME,
    U.INCOME,
    U.SALES,
    U.OUTSTANDING,
    U.FLOAT,
    U.SHORT_INTEREST,
    U.TRADES,
    U.AH_VOLUME,
    U.AUM,
    U.HOLDINGS,
    "Average Volume",  # quote.ashx / alternate header
})

# Finviz-like flow: identity → valuation → income/dividends → balance/liquidity →
# ownership/short → margins → intraday perf → longer perf → technicals → price/flow → ETF extras → tags.
V152_DISPLAY_ORDER: tuple[str, ...] = (
    U.NO,
    U.TICKER,
    U.COMPANY,
    U.INDEX,
    U.SECTOR,
    U.INDUSTRY,
    U.COUNTRY,
    U.EXCHANGE,
    U.MARKET_CAP,
    U.ENTERPRISE_VALUE,
    U.INCOME,
    U.SALES,
    U.BOOK_SH,
    U.CASH_SH,
    U.DIVIDEND,
    U.DIVIDEND_TTM,
    U.DIVIDEND_EX_DATE,
    U.DIVIDEND_GR_1Y,
    U.DIVIDEND_GR_3Y,
    U.DIVIDEND_GR_5Y,
    U.PAYOUT_RATIO,
    U.EMPLOYEES,
    U.IPO_DATE,
    U.PE,
    U.FWD_PE,
    U.PEG,
    U.PS,
    U.PB,
    U.PC,
    U.P_FCF,
    U.EV_EBITDA,
    U.EV_SALES,
    U.QUICK_R,
    U.CURR_R,
    U.DEBT_EQ,
    U.LTDEBT_EQ,
    U.EPS,
    U.EPS_NEXT_Q,
    U.EPS_NEXT_Y,
    U.EPS_THIS_Y,
    U.EPS_NEXT_5Y,
    U.EPS_PAST_5Y,
    U.EPS_PAST_3Y,
    U.SALES_PAST_5Y,
    U.SALES_PAST_3Y,
    U.SALES_YOY_TTM,
    U.SALES_Q_Q,
    U.EPS_YOY_TTM,
    U.EPS_Q_Q,
    U.EPS_SURPRISE,
    U.REVENUE_SURPRISE,
    U.EARNINGS,
    U.INSIDER_OWN,
    U.INSIDER_TRANS,
    U.INST_OWN,
    U.INST_TRANS,
    U.ROA,
    U.ROE,
    U.ROIC,
    U.GROSS_M,
    U.OPER_M,
    U.PROFIT_M,
    U.SMA20,
    U.SMA50,
    U.SMA200,
    U.OUTSTANDING,
    U.FLOAT,
    U.FLOAT_PCT,
    U.SHORT_FLOAT,
    U.SHORT_RATIO,
    U.SHORT_INTEREST,
    U.HIGH_52W,
    U.LOW_52W,
    U.RANGE_52W,
    U.HIGH_50D,
    U.LOW_50D,
    U.ALL_TIME_HIGH,
    U.ALL_TIME_LOW,
    U.VOLATILITY_W,
    U.VOLATILITY_M,
    U.ATR,
    U.RSI,
    U.BETA,
    U.REL_VOLUME,
    U.AVG_VOLUME,
    U.VOLUME,
    U.TRADES,
    U.PERF_WEEK,
    U.PERF_MONTH,
    U.PERF_QUART,
    U.PERF_HALF,
    U.PERF_YTD,
    U.PERF_YEAR,
    U.PERF_3Y,
    U.PERF_5Y,
    U.PERF_10Y,
    U.PERF_1_MIN,
    U.PERF_2_MIN,
    U.PERF_3_MIN,
    U.PERF_5_MIN,
    U.PERF_10_MIN,
    U.PERF_15_MIN,
    U.PERF_30_MIN,
    U.PERF_1_HR,
    U.PERF_2_HR,
    U.PERF_4_HR,
    U.RECOM,
    U.TARGET_PRICE,
    U.PREV_CLOSE,
    U.PRICE,
    U.CHANGE,
    U.OPEN,
    U.HIGH,
    U.LOW,
    U.CHANGE_FROM_OPEN,
    U.GAP,
    U.AH_CLOSE,
    U.AH_CHANGE,
    U.AH_VOLUME,
    U.NEWS_TIME,
    U.NEWS_TITLE,
    U.NEWS_URL,
    U.DAILY_DIGEST,
    U.SINGLE_CATEGORY,
    U.ASSET_TYPE,
    U.ETF_TYPE,
    U.SECTOR_THEME,
    U.REGION,
    U.ACTIVE,
    U.EXPENSE,
    U.HOLDINGS,
    U.AUM,
    U.NAV,
    U.NAV_PCT,
    U.FLOWS_1M,
    U.FLOWS_PCT_1M,
    U.FLOWS_3M,
    U.FLOWS_PCT_3M,
    U.FLOWS_YTD,
    U.FLOWS_PCT_YTD,
    U.FLOWS_1Y,
    U.FLOWS_PCT_1Y,
    U.RETURN_PCT_1Y,
    U.RETURN_PCT_3Y,
    U.RETURN_PCT_5Y,
    U.RETURN_PCT_10Y,
    U.RETURN_PCT_SI,
    U.OPTIONABLE,
    U.SHORTABLE,
    U.TAG,
    U.TAGS,
)


def _fmt_val(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if v != v:  # NaN
            return "—"
    s = str(v).strip()
    if not s or s in ("-", "—"):
        return "—"
    return s


def _label_formats_large_numbers(label: str) -> bool:
    key = str(label).strip().lower()
    return key in {x.lower() for x in _FORMAT_VALUE_LABELS}


def _format_finance_number(n: float) -> str:
    """Format a scalar with comma separators and K / M / B suffix when appropriate."""
    if n != n:  # NaN
        return "—"
    sign = "-" if n < 0 else ""
    x = abs(n)
    if x >= 1e9:
        t = f"{x / 1e9:,.2f}".rstrip("0").rstrip(".")
        return f"{sign}{t}B"
    if x >= 1e6:
        t = f"{x / 1e6:,.2f}".rstrip("0").rstrip(".")
        return f"{sign}{t}M"
    if x >= 1e3:
        t = f"{x / 1e3:,.2f}".rstrip("0").rstrip(".")
        return f"{sign}{t}K"
    if x >= 1 and abs(x - round(x)) < 1e-9:
        return f"{sign}{int(round(x)):,}"
    return f"{sign}{x:,.2f}"


def _fmt_metric_value(label: str, raw: Any) -> str:
    """Display string; large-number columns get commas + K/M/B."""
    base = _fmt_val(raw)
    if base == "—":
        return base
    if not _label_formats_large_numbers(label):
        return base
    n = _parse_num(str(raw).strip()) if raw is not None else None
    if n is None:
        return base
    return _format_finance_number(n)


def get_raw_v152_row_for_ticker(symbol: str) -> dict | None:
    """Return the raw CSV row dict for ``symbol`` from cached USA v=152 export, or None."""
    from src.data_fetcher import fetch_usa_full_v152_raw

    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    raw = fetch_usa_full_v152_raw()
    if not raw:
        return None
    keys = list(raw[0].keys())
    ticker_col = None
    for k in keys:
        if str(k).strip().lower() in ("ticker",):
            ticker_col = k
            break
    if ticker_col is None:
        ticker_col = U.TICKER
    for row in raw:
        t = str(row.get(ticker_col, "") or "").strip().upper()
        if t == sym:
            return row
    return None


def _pairs_from_raw_row(row: dict) -> list[dict[str, str]]:
    """Ordered label/value pairs; known order first, then extras sorted alphabetically."""
    seen: set[str] = set()
    pairs: list[dict[str, str]] = []
    for col in V152_DISPLAY_ORDER:
        if col not in row:
            continue
        seen.add(col)
        pairs.append({"label": col, "value": _fmt_metric_value(col, row.get(col))})
    extras = [k for k in row.keys() if k not in seen and str(k).strip()]
    extras.sort(key=lambda x: str(x).lower())
    for k in extras:
        pairs.append({"label": str(k), "value": _fmt_metric_value(str(k), row.get(k))})
    return pairs


def get_ticker_metrics_payload(symbol: str) -> dict:
    """
    Return JSON-serializable payload for the modal metrics panel.

    Keys: ok (bool), symbol (str), source (str), pairs (list), message (optional).
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return {
            "ok": False,
            "symbol": "",
            "source": "unavailable",
            "pairs": [],
            "message": "Missing symbol.",
        }

    row = get_raw_v152_row_for_ticker(sym)
    if row:
        return {
            "ok": True,
            "symbol": sym,
            "source": "usa_v152",
            "pairs": _pairs_from_raw_row(row),
        }

    from src.finviz_elite import fetch_elite_stock, is_elite_configured

    if not is_elite_configured():
        return {
            "ok": False,
            "symbol": sym,
            "source": "unavailable",
            "pairs": [],
            "message": "FinViz Elite not configured and symbol not in cached USA export.",
        }

    q = fetch_elite_stock(sym)
    if not q:
        return {
            "ok": False,
            "symbol": sym,
            "source": "unavailable",
            "pairs": [],
            "message": "No data for this symbol (try refreshing the dashboard to load the USA export).",
        }

    pairs = [{"label": k, "value": _fmt_metric_value(str(k), v)} for k, v in q.items()]
    return {
        "ok": True,
        "symbol": sym,
        "source": "quote",
        "pairs": pairs,
    }


SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9.\-^]+$")


def is_valid_symbol_param(symbol: str) -> bool:
    s = (symbol or "").strip()
    return bool(s) and bool(SYMBOL_PATTERN.fullmatch(s))
