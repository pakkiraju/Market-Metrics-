"""FRED API v2 — series observations."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"


def get_api_key() -> str | None:
    return os.environ.get("FRED_API_KEY") or os.environ.get("FRED_API_KEY".lower())


def fetch_observations(
    series_id: str,
    *,
    observation_start: str | None = None,
    observation_end: str | None = None,
    sort_order: str = "asc",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return list of {date: str, value: float|None}."""
    key = get_api_key()
    if not key:
        return []

    params: dict[str, Any] = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "sort_order": sort_order,
    }
    if observation_start:
        params["observation_start"] = observation_start
    if observation_end:
        params["observation_end"] = observation_end
    if limit:
        params["limit"] = limit

    try:
        r = requests.get(FRED_OBS_URL, params=params, timeout=45)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        logger.warning("FRED fetch failed %s: %s", series_id, e)
        return []

    obs = payload.get("observations") or []
    out = []
    for o in obs:
        d = o.get("date")
        v = o.get("value")
        if v in (".", "", None):
            out.append({"date": d, "value": None})
        else:
            try:
                out.append({"date": d, "value": float(v)})
            except (TypeError, ValueError):
                out.append({"date": d, "value": None})
    return out


def default_start_years(years: int = 22) -> str:
    return (datetime.utcnow() - timedelta(days=365 * years)).strftime("%Y-%m-%d")
