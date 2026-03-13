"""Scrape today's economic calendar from Forex Factory JSON export.

Uses https://nfs.faireconomy.media/ff_calendar_thisweek.json — no auth required.
Filters for events on the current date (US Eastern).
"""

import logging
from datetime import datetime, timezone, timedelta
import requests

from src import cache
from src.cache import MEDIUM

logger = logging.getLogger(__name__)

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
ET = timezone(timedelta(hours=-5))


def fetch_todays_economic_calendar(ttl: int = MEDIUM) -> list[dict]:
    """Fetch economic calendar events for today (US Eastern).
    Returns list of {time, country, impact, title, forecast, actual, previous}."""
    cached = cache.get("economic_calendar_today")
    if cached is not None:
        return cached

    try:
        r = requests.get(
            FF_CALENDAR_URL,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("Economic calendar fetch failed: %s", e)
        return []

    if not isinstance(data, list):
        return []

    # Today in ET (date only for filtering)
    now_et = datetime.now(ET)
    today_str = now_et.strftime("%Y-%m-%d")

    rows = []
    for evt in data:
        date_str = evt.get("date") or ""
        if not date_str:
            continue
        dt_part = date_str.split("T")[0] if "T" in date_str else date_str[:10]
        if dt_part != today_str:
            continue
        time_str = ""
        if len(date_str) >= 16:
            try:
                time_part = date_str[11:16]
                h, m = int(time_part[:2]), int(time_part[3:5])
                ampm = "AM" if h < 12 else "PM"
                h12 = 12 if h in (0, 12) else (h % 12)
                time_str = f"{h12}:{time_part[3:5]} {ampm}"
            except (ValueError, IndexError):
                time_str = date_str[11:16]

        rows.append({
            "time": time_str,
            "country": evt.get("country", ""),
            "impact": evt.get("impact", ""),
            "title": evt.get("title", ""),
            "forecast": evt.get("forecast", "") or "—",
            "actual": evt.get("actual", "") or "—",
            "previous": evt.get("previous", "") or "—",
        })

    # Sort by time (events without time go first or last)
    def _sort_key(r):
        t = r.get("time", "")
        if not t:
            return "99:99"
        return t

    rows.sort(key=_sort_key)

    if rows:
        cache.put("economic_calendar_today", rows, ttl=ttl)
    return rows
