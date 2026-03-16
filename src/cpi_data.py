"""Scrape economic calendar detail data from FinViz Elite pages.

Pulls Expected (forecast) vs Actual from embedded JSON. Supports:
- CPI (Consumer Price Index)
- Core Inflation Rate MoM
- Core Inflation Rate YoY
"""

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from src import cache
from src.cache import MEDIUM

logger = logging.getLogger(__name__)

CPI_URL = "https://elite.finviz.com/calendar/economic/detail/UNITEDSTACONPRIINDCP"
CORE_MOM_URL = "https://elite.finviz.com/calendar/economic/detail/USACIRM"
CORE_YOY_URL = "https://elite.finviz.com/calendar/economic/detail/USACORECPIRATE"
NY = ZoneInfo("America/New_York")

# Generic pattern: any event with referenceDate (excludes referenceDate:null)
_DETAIL_PATTERN = r'\{"calendarId":(\d+),"ticker":"[^"]+","event":"[^"]+","category":"[^"]+","date":"(\d{4}-\d{2}-\d{2})[^"]*"[^}]*"reference":"([^"]+)"[^}]*"referenceDate":"(\d{4}-\d{2}-\d{2})"[^}]*"actual":([^,}]+)[^}]*"forecast":([^,}]+)'


def _parse_val(v) -> float | None:
    """Parse numeric value from string or number. Handles %, commas, quotes."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "").strip('"')
    if not s or s.lower() in ("null", "none", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fetch_from_finviz_url(url: str) -> list[dict]:
    """Scrape Expected vs Actual from any FinViz calendar detail URL."""
    try:
        r = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        r.raise_for_status()
        text = r.text
    except Exception as e:
        logger.warning("FinViz fetch failed %s: %s", url[-20:], e)
        return []

    rows = []
    seen_ids = set()
    for m in re.finditer(_DETAIL_PATTERN, text):
        cid, _date_str, ref, ref_date_str, actual, forecast = m.groups()
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        actual_f = _parse_val(actual)
        forecast_f = _parse_val(forecast)
        if actual_f is None and forecast_f is None:
            continue
        try:
            ref_dt = datetime.strptime(ref_date_str, "%Y-%m-%d").replace(tzinfo=NY)
            now = datetime.now(NY)
            if ref_dt > now:
                continue
            month_label = f"{ref} {ref_dt.year}"
        except ValueError:
            month_label = ref
        rows.append({
            "month": month_label,
            "expected": forecast_f,
            "actual": actual_f,
        })

    def sort_key(r):
        m = r["month"]
        parts = m.split()
        if len(parts) == 2:
            mon, yr = parts
            months = "JanFebMarAprMayJunJulAugSepOctNovDec"
            mi = months.find(mon) // 3
            return (int(yr), mi)
        return (0, 0)

    rows.sort(key=sort_key)
    return rows[-12:] if rows else []


def _fetch_from_finviz() -> list[dict]:
    """Scrape CPI data from FinViz Elite page."""
    return _fetch_from_finviz_url(CPI_URL)


def fetch_cpi_ytd(ttl: int = MEDIUM) -> list[dict]:
    """Fetch CPI Expected vs Actual YTD from FinViz."""
    cached = cache.get("cpi_ytd")
    if cached is not None:
        return cached
    rows = _fetch_from_finviz()
    if rows:
        cache.put("cpi_ytd", rows, ttl=ttl)
    return rows


def fetch_core_inflation_mom_ytd(ttl: int = MEDIUM) -> list[dict]:
    """Fetch Core Inflation Rate MoM Expected vs Actual YTD from FinViz."""
    cached = cache.get("core_inflation_mom_ytd")
    if cached is not None:
        return cached
    rows = _fetch_from_finviz_url(CORE_MOM_URL)
    if rows:
        cache.put("core_inflation_mom_ytd", rows, ttl=ttl)
    return rows


def fetch_core_inflation_yoy_ytd(ttl: int = MEDIUM) -> list[dict]:
    """Fetch Core Inflation Rate YoY Expected vs Actual YTD from FinViz."""
    cached = cache.get("core_inflation_yoy_ytd")
    if cached is not None:
        return cached
    rows = _fetch_from_finviz_url(CORE_YOY_URL)
    if rows:
        cache.put("core_inflation_yoy_ytd", rows, ttl=ttl)
    return rows
