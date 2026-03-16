"""Stockbee data fetchers — Momentum50 and Market Breadth from Google Sheets / Stockbee API.

Same data sources as Stockbee Dashboard:
- Momentum50: https://docs.google.com/spreadsheets/d/1xjbe9SF0HsxwY_Uy3NC2tT92BqK0nhArUaYU16Q0p9M/
- Market Breadth: Google Sheets or Stockbee API (http://localhost:8000)
"""

import json
import logging
import os
from pathlib import Path

import requests

from src import cache
from src.cache import MEDIUM

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

# Google Sheets (Stockbee by Pradeep Bonde)
MOMENTUM50_SHEET_URL = "https://docs.google.com/spreadsheets/d/1xjbe9SF0HsxwY_Uy3NC2tT92BqK0nhArUaYU16Q0p9M/gviz/tq?gid=1499398020&tqx=out:json"
MARKET_BREADTH_SHEET_URL = "https://docs.google.com/spreadsheets/d/1O6OhS7ciA8zwfycBfGPbP2fWJnR0pn2UUvFZVDP9jpE/gviz/tq?gid=1585697958&tqx=out:json"

# Stockbee API (optional, from Stockbee Dashboard api_server)
STOCKBEE_API_URL = os.environ.get("STOCKBEE_API_URL", "http://localhost:8000")


def _fetch_gviz(sheet_url: str, cache_key: str | None = None, ttl: int = MEDIUM) -> dict | None:
    """Fetch Google Sheets via gviz/tq. Returns parsed table or None."""
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        r = requests.get(sheet_url, timeout=15, headers={"User-Agent": "MarketMetrics/1.0"})
        r.raise_for_status()
        text = r.text
        # gviz may wrap: )]}'\n{...} or google.visualization.Query.setResponse({...})
        start = text.find("{")
        if start < 0:
            return None
        end = text.rfind("}") + 1
        if end <= start:
            return None
        data = json.loads(text[start:end])
        if cache_key and data:
            cache.put(cache_key, data, ttl=ttl)
        return data
    except Exception as e:
        logger.warning("gviz fetch failed %s: %s", sheet_url[:60], e)
        return None


def fetch_stockbee_momentum50(cache_key: str = "stockbee_momentum50", ttl: int = MEDIUM) -> dict:
    """Fetch Stockbee Momentum50 from Google Sheets. Returns {dates: [str], tickers: {date: [ticker, ...]}}."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = _fetch_gviz(MOMENTUM50_SHEET_URL, cache_key=None, ttl=ttl)
    result = {"dates": [], "tickers": {}}
    if not data or "table" not in data:
        return result

    table = data["table"]
    rows = table.get("rows", [])
    num_cols = len(table.get("cols", []))
    if not rows or num_cols == 0:
        return result

    # Row 0 = dates
    date_row = rows[0].get("c", [])
    dates = []
    for col in range(num_cols):
        cell = date_row[col] if col < len(date_row) else None
        v = cell.get("v") if cell else None
        if v is not None:
            s = str(v).strip()
            if s:
                dates.append(s)

    # Rows 1+ = tickers per column
    for col_idx, date_str in enumerate(dates):
        tickers = []
        for r in rows[1:]:
            cells = r.get("c", [])
            cell = cells[col_idx] if col_idx < len(cells) else None
            v = cell.get("v") if cell else None
            if v is not None:
                t = str(v).strip()
                if t:
                    tickers.append(t.upper())
        result["tickers"][date_str] = tickers
    result["dates"] = dates

    if result["dates"]:
        cache.put(cache_key, result, ttl=ttl)
    return result


def fetch_stockbee_breadth(cache_key: str = "stockbee_breadth", ttl: int = MEDIUM) -> dict | None:
    """Fetch market breadth. Tries Stockbee API first, then Google Sheets."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Try Stockbee API (PPLX breadth)
    try:
        url = f"{STOCKBEE_API_URL.rstrip('/')}/api/pplx-market-data"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if "error" not in data:
                cache.put(cache_key, data, ttl=ttl)
                return data
    except Exception as e:
        logger.debug("Stockbee API not available: %s", e)

    # Fallback: Google Sheets Market Monitor
    gviz = _fetch_gviz(MARKET_BREADTH_SHEET_URL, cache_key=None, ttl=ttl)
    if not gviz or "table" not in gviz:
        return None

    rows = gviz["table"].get("rows", [])
    if len(rows) < 2:
        return None

    def _cell(row_idx: int, col_idx: int):
        r = rows[row_idx] if row_idx < len(rows) else {}
        c = r.get("c", [])
        cell = c[col_idx] if col_idx < len(c) else None
        return cell.get("v") if cell else None

    # Newest first: row 0 = latest
    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else latest

    def _v(row, i, default=0):
        c = row.get("c", [])
        cell = c[i] if i < len(c) else None
        v = cell.get("v") if cell else None
        if v is None:
            return default
        try:
            return float(v) if isinstance(v, (int, float)) else float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return default

    up4 = int(_v(latest, 1, 0))
    down4 = int(_v(latest, 2, 0))
    ratio5 = _v(latest, 3, 1.0)
    ratio10 = _v(latest, 4, 1.0)
    sp500 = _v(latest, 15, 0)
    sp500_prev = _v(prev, 15, sp500)
    sp500_change = sp500 - sp500_prev
    sp500_change_pct = (sp500_change / sp500_prev * 100) if sp500_prev else 0
    t2108 = _v(latest, 14, 50)
    universe = int(_v(latest, 13, 0))

    raw_date = _cell(0, 0)
    date_str = ""
    if raw_date:
        s = str(raw_date)
        if s.startswith("Date("):
            import re
            m = re.search(r"Date\((\d+),(\d+),(\d+)\)", s)
            if m:
                y, mo, d = m.group(1), m.group(2), m.group(3)
                date_str = f"{int(mo):02d}/{int(d):02d}/{y}"
        else:
            date_str = s

    result = {
        "date": date_str,
        "up4": up4,
        "down4": down4,
        "ratio5": round(ratio5, 2),
        "ratio10": round(ratio10, 2),
        "universe": universe,
        "t2108": round(t2108, 2),
        "sp500": round(sp500, 2),
        "sp500_change": round(sp500_change, 2),
        "sp500_change_pct": round(sp500_change_pct, 2),
        "source": "google_sheets",
    }
    cache.put(cache_key, result, ttl=ttl)
    return result


def fetch_stockbee_breadth_history(days: int = 60, cache_key: str = "stockbee_breadth_history", ttl: int = MEDIUM) -> list[dict]:
    """Fetch breadth history for charts. Returns list of {date, up4, down4, ratio5, ratio10, up25q, down25q, sp500} newest first."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Try Stockbee API first
    try:
        url = f"{STOCKBEE_API_URL.rstrip('/')}/api/pplx-market-data"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if "error" not in data and "history" in data:
                hist = data["history"][:days]
                if hist:
                    # Chronological order (oldest first) for charts: oldest left, newest right
                    hist = list(reversed(hist))
                    cache.put(cache_key, hist, ttl=ttl)
                    return hist
    except Exception as e:
        logger.debug("Stockbee API history not available: %s", e)

    # Fallback: Google Sheets - parse all rows
    gviz = _fetch_gviz(MARKET_BREADTH_SHEET_URL, cache_key=None, ttl=ttl)
    if not gviz or "table" not in gviz:
        return []

    rows = gviz["table"].get("rows", [])[:days]
    import re
    result = []
    for i, row in enumerate(rows):
        c = row.get("c", [])
        if len(c) < 16:
            continue

        def _v(col_idx, default=0):
            cell = c[col_idx] if col_idx < len(c) else None
            v = cell.get("v") if cell else None
            if v is None:
                return default
            try:
                return float(v) if isinstance(v, (int, float)) else float(str(v).replace(",", ""))
            except (ValueError, TypeError):
                return default

        raw_date = c[0].get("v") if c else None
        date_str = ""
        if raw_date:
            s = str(raw_date)
            if s.startswith("Date("):
                m = re.search(r"Date\((\d+),(\d+),(\d+)\)", s)
                if m:
                    date_str = f"{int(m.group(2)):02d}/{int(m.group(3)):02d}/{m.group(1)}"
            else:
                date_str = s

        up4 = int(_v(1, 0))
        down4 = int(_v(2, 0))
        sp500 = _v(15, 0)
        if not sp500:
            continue

        h5 = rows[i : i + 5]
        h10 = rows[i : i + 10]
        s_up5 = sum(int(r.get("c", [{}])[1].get("v", 0) or 0) for r in h5 if len(r.get("c", [])) > 1)
        s_dn5 = sum(int(r.get("c", [{}])[2].get("v", 0) or 0) for r in h5 if len(r.get("c", [])) > 2) or 1
        s_up10 = sum(int(r.get("c", [{}])[1].get("v", 0) or 0) for r in h10 if len(r.get("c", [])) > 1)
        s_dn10 = sum(int(r.get("c", [{}])[2].get("v", 0) or 0) for r in h10 if len(r.get("c", [])) > 2) or 1

        result.append({
            "date": date_str,
            "up4": up4,
            "down4": down4,
            "ratio5": round(s_up5 / s_dn5, 2),
            "ratio10": round(s_up10 / s_dn10, 2),
            "up25q": int(_v(5, 0)),
            "down25q": int(_v(6, 0)),
            "sp500": round(sp500, 2),
        })

    # Chronological order (oldest first) for charts
    result.reverse()
    if result:
        cache.put(cache_key, result, ttl=ttl)
    return result
