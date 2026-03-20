"""Aggregate FRED data for Macro Monitor KPI strip, fiscal block, and charts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src import cache
from src.macro_fred_client import default_start_years, fetch_observations, get_api_key
from src.macro_fred_series import FISCAL_ROWS, KPI_ORDER, METRICS
from src.macro_signals import build_narrative, classify_metric, count_signals, dominant_label

logger = logging.getLogger(__name__)

MACRO_CACHE_KEY = "macro_fred_bundle"
MACRO_TTL = 1800  # 30 minutes

_CBO_CACHE: dict[str, Any] | None = None


def load_cbo_yaml() -> dict[str, Any]:
    global _CBO_CACHE
    if _CBO_CACHE is not None:
        return _CBO_CACHE
    path = Path(__file__).resolve().parent.parent / "config" / "macro_cbo.yaml"
    if not path.exists():
        _CBO_CACHE = {}
        return _CBO_CACHE
    try:
        import yaml
        _CBO_CACHE = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.debug("macro_cbo.yaml load failed: %s", e)
        _CBO_CACHE = {}
    return _CBO_CACHE


def _df(obs: list[dict[str, Any]]) -> pd.DataFrame:
    if not obs:
        return pd.DataFrame(columns=["date", "value"])
    d = pd.DataFrame(obs)
    d["date"] = pd.to_datetime(d["date"])
    d = d.dropna(subset=["value"])
    return d.sort_values("date")


def _yoy_pct_from_index(d: pd.DataFrame) -> float | None:
    if len(d) < 13:
        return None
    a, b = d["value"].iloc[-1], d["value"].iloc[-13]
    if b and b != 0:
        return float((a / b - 1) * 100)
    return None


def _yoy_sparkline(d: pd.DataFrame, n: int = 24) -> tuple[list[str], list[float]]:
    """Last n months of YoY % for index series."""
    if len(d) < 14:
        return [], []
    d = d.tail(n + 12).reset_index(drop=True)
    dates, vals = [], []
    for i in range(12, len(d)):
        a, b = d["value"].iloc[i], d["value"].iloc[i - 12]
        if b and b != 0:
            dates.append(str(d["date"].iloc[i].date()))
            vals.append(float((a / b - 1) * 100))
    return dates[-n:], vals[-n:]


def _trend_arrow(current: float | None, prev: float | None) -> str | None:
    if current is None or prev is None:
        return None
    if current > prev * 1.001:
        return "up"
    if current < prev * 0.999:
        return "down"
    return "flat"


def _fmt_num(x: float | None, nd: int = 1) -> str:
    if x is None:
        return "—"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:.{nd}f}"


def compute_kpi(metric_id: str, raw: dict[str, pd.DataFrame]) -> dict[str, Any]:
    cfg = METRICS[metric_id]
    transform = cfg["transform"]
    fred_ids = cfg["fred_ids"]
    out: dict[str, Any] = {
        "metric_id": metric_id,
        "label": cfg["label"],
        "display": "—",
        "subtitle": "",
        "value_num": None,
        "spark_dates": [],
        "spark_vals": [],
        "trend": None,
        "source": cfg.get("source", "FRED"),
    }

    if transform == "range_pair":
        lo_id, hi_id, spot_id = fred_ids
        dlo = raw.get(lo_id, _df([]))
        dhi = raw.get(hi_id, _df([]))
        dsp = raw.get(spot_id, _df([]))
        if len(dlo) and len(dhi):
            lo, hi = float(dlo["value"].iloc[-1]), float(dhi["value"].iloc[-1])
            out["display"] = f"{lo:.2f}%–{hi:.2f}%"
            out["value_num"] = (lo + hi) / 2
            out["subtitle"] = "Target range · FFR eff. " + (
                f"{dsp['value'].iloc[-1]:.2f}%" if len(dsp) else "—"
            )
        if len(dsp) >= 2:
            out["trend"] = _trend_arrow(float(dsp["value"].iloc[-1]), float(dsp["value"].iloc[-2]))
        if len(dsp) >= 30:
            s = dsp.tail(30)
            out["spark_dates"] = [str(x.date()) for x in s["date"]]
            out["spark_vals"] = [float(x) for x in s["value"]]
        return out

    sid = fred_ids[0]
    d = raw.get(sid, _df([]))

    if transform == "yoy_pct_index":
        yoy = _yoy_pct_from_index(d)
        m = d["date"].iloc[-1].strftime("%b %Y") if len(d) else ""
        out["display"] = f"{yoy:.1f}%" if yoy is not None else "—"
        out["subtitle"] = m
        out["value_num"] = yoy
        sd, sv = _yoy_sparkline(d, 24)
        out["spark_dates"], out["spark_vals"] = sd, sv
        if len(sv) >= 2:
            out["trend"] = _trend_arrow(sv[-1], sv[-2])
        return out

    if transform == "pct_level":
        if len(d) < 1:
            return out
        v = float(d["value"].iloc[-1])
        out["display"] = f"{v:.1f}%"
        out["subtitle"] = d["date"].iloc[-1].strftime("%b %Y")
        out["value_num"] = v
        if len(d) >= 2:
            out["trend"] = _trend_arrow(v, float(d["value"].iloc[-2]))
        s = d.tail(24)
        out["spark_dates"] = [str(x.date()) for x in s["date"]]
        out["spark_vals"] = [float(x) for x in s["value"]]
        return out

    if transform == "diff_1m_thousands":
        if len(d) < 2:
            return out
        diff = (d["value"].iloc[-1] - d["value"].iloc[-2])  # thousands of jobs
        out["display"] = f"{diff:+.0f}K" if diff == diff else "—"
        out["subtitle"] = "Nonfarm payrolls m/m"
        out["value_num"] = float(diff)
        if len(d) >= 3:
            prev_diff = d["value"].iloc[-2] - d["value"].iloc[-3]
            out["trend"] = _trend_arrow(diff, prev_diff)
        s = d.tail(24)
        diffs = s["value"].diff().dropna()
        out["spark_dates"] = [str(x.date()) for x in s["date"].iloc[1:]]
        out["spark_vals"] = [float(x) for x in diffs.tail(24)]
        return out

    if transform == "level":
        if len(d) < 1:
            return out
        v = float(d["value"].iloc[-1])
        if metric_id == "deficit":
            # FYFSDF (millions USD): negative = deficit in published FRED convention
            mag = abs(v) / 1e6
            if v < 0:
                out["display"] = f"${mag:.2f}T deficit"
            else:
                out["display"] = f"${mag:.2f}T surplus"
            cbo = load_cbo_yaml()
            if cbo.get("deficit_label"):
                out["subtitle"] = str(cbo.get("deficit_label"))
            else:
                out["subtitle"] = "Federal surplus/deficit (FY)"
            out["value_num"] = v
        else:
            out["display"] = f"${v:.2f}"
            out["subtitle"] = d["date"].iloc[-1].strftime("%Y-%m-%d")
            out["value_num"] = v
        if len(d) >= 30:
            s = d.tail(60)
            out["spark_dates"] = [str(x.date()) for x in s["date"]]
            out["spark_vals"] = [float(x) for x in s["value"]]
        elif len(d) >= 2:
            out["trend"] = _trend_arrow(float(d["value"].iloc[-1]), float(d["value"].iloc[-2]))
        return out

    if transform == "price_index":
        if len(d) < 1:
            return out
        v = float(d["value"].iloc[-1])
        out["display"] = f"{v:,.0f}"
        out["subtitle"] = d["date"].iloc[-1].strftime("%Y-%m-%d")
        out["value_num"] = v
        if len(d) >= 21:
            out["trend"] = _trend_arrow(v, float(d["value"].iloc[-21]))
        s = d.tail(60)
        out["spark_dates"] = [str(x.date()) for x in s["date"]]
        out["spark_vals"] = [float(x) for x in s["value"]]
        return out

    return out


def _collect_series_ids() -> set[str]:
    ids: set[str] = set()
    for m in METRICS.values():
        for x in m["fred_ids"]:
            ids.add(x)
    for row in FISCAL_ROWS:
        ids.add(row["fred_id"])
    return ids


def _fetch_all_raw() -> dict[str, pd.DataFrame]:
    start = default_start_years(24)
    raw: dict[str, pd.DataFrame] = {}
    for sid in _collect_series_ids():
        obs = fetch_observations(sid, observation_start=start, sort_order="asc")
        raw[sid] = _df(obs)
    return raw


def _fmt_fiscal_value(v: float, usd_unit: str) -> str:
    if usd_unit == "percent":
        return f"{v:.1f}%"
    if usd_unit == "millions":
        return f"${abs(v) / 1e6:.2f}T"
    if usd_unit == "billions":
        av = abs(v)
        if av >= 1000:
            return f"${av / 1000:.2f}T"
        return f"${av:.1f}B"
    return _fmt_num(v, 2)


def _fiscal_block(raw: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows_out = []
    for row in FISCAL_ROWS:
        sid = row["fred_id"]
        uu = row.get("usd_unit", "millions")
        d = raw.get(sid, _df([]))
        if len(d) < 1:
            rows_out.append({**row, "display": "—", "date": ""})
            continue
        v = float(d["value"].iloc[-1])
        if sid == "FYFSDF":
            mag = abs(v) / 1e6
            disp = f"${mag:.2f}T deficit" if v < 0 else f"${mag:.2f}T surplus"
        else:
            disp = _fmt_fiscal_value(v, uu)
        rows_out.append({
            **row,
            "display": disp,
            "date": str(d["date"].iloc[-1].date()),
        })
    return rows_out


def fetch_macro_bundle(ttl: int = MACRO_TTL, force: bool = False) -> dict[str, Any]:
    """Return {kpis, fiscal, signal_counts, narrative, dominant, error, raw_series_ids}."""
    if not force:
        cached = cache.get(MACRO_CACHE_KEY)
        if cached is not None:
            return cached

    if not get_api_key():
        err = {
            "error": "missing_key",
            "kpis": {},
            "fiscal": [],
            "signal_counts": {},
            "narrative": "Set FRED_API_KEY in your environment or .env file to load macro data from the St. Louis Fed.",
            "dominant": "—",
        }
        cache.put(MACRO_CACHE_KEY, err, ttl=60)
        return err

    try:
        raw = _fetch_all_raw()
        kpis: dict[str, dict[str, Any]] = {}
        for mid in KPI_ORDER:
            kpis[mid] = compute_kpi(mid, raw)
            kpis[mid]["signal"] = classify_metric(mid, kpis[mid])

        counts = count_signals(kpis)
        narrative = build_narrative(kpis, counts)
        dom = dominant_label(counts)

        fiscal = _fiscal_block(raw)

        bundle = {
            "error": None,
            "kpis": kpis,
            "fiscal": fiscal,
            "signal_counts": counts,
            "narrative": narrative,
            "dominant": dom,
        }
        cache.put(MACRO_CACHE_KEY, bundle, ttl=ttl)
        return bundle
    except Exception as e:
        logger.exception("macro bundle failed: %s", e)
        err = {
            "error": str(e),
            "kpis": {},
            "fiscal": [],
            "signal_counts": {},
            "narrative": f"Error loading macro data: {e}",
            "dominant": "—",
        }
        cache.put(MACRO_CACHE_KEY, err, ttl=120)
        return err


def get_series_for_chart(metric_id: str, lookback_years: int) -> dict[str, Any]:
    """Build dates + y values for modal chart (levels or YoY % as appropriate)."""
    if metric_id not in METRICS:
        return {"error": "unknown metric", "title": "", "dates": [], "values": [], "y_label": ""}
    cfg = METRICS[metric_id]
    transform = cfg["transform"]
    start = default_start_years(lookback_years)

    if transform == "range_pair":
        sid = "DFF"
        title = cfg["label"] + " — effective rate"
        y_label = "%"
    else:
        sid = cfg["fred_ids"][0]
        title = cfg["label"]
        y_label = ""

    obs = fetch_observations(sid, observation_start=start, sort_order="asc")
    d = _df(obs)
    if d.empty:
        return {"error": "no data", "title": title, "dates": [], "values": [], "y_label": y_label}

    if transform == "yoy_pct_index":
        dates, vals = [], []
        for i in range(12, len(d)):
            a, b = float(d["value"].iloc[i]), float(d["value"].iloc[i - 12])
            if b and b != 0:
                dates.append(d["date"].iloc[i])
                vals.append((a / b - 1) * 100)
        return {
            "error": None,
            "title": title + " (YoY %)",
            "dates": [str(x.date()) for x in dates],
            "values": vals,
            "y_label": "% YoY",
            "fred_id": sid,
        }

    if transform == "diff_1m_thousands":
        dates = [str(d["date"].iloc[i].date()) for i in range(1, len(d))]
        vals = [float(d["value"].iloc[i] - d["value"].iloc[i - 1]) for i in range(1, len(d))]
        return {
            "error": None,
            "title": title + " (monthly change, thousands)",
            "dates": dates,
            "values": vals,
            "y_label": "K jobs",
            "fred_id": sid,
        }

    dates = [str(x.date()) for x in d["date"]]
    vals = [float(x) for x in d["value"]]
    if transform == "pct_level":
        y_label = "%"
    elif transform == "level" and metric_id == "deficit":
        y_label = "Millions USD"
    elif transform == "price_index":
        y_label = "Index"
    else:
        y_label = y_label or "Value"

    return {
        "error": None,
        "title": title,
        "dates": dates,
        "values": vals,
        "y_label": y_label,
        "fred_id": sid,
    }


def invalidate_macro_cache():
    cache.invalidate(MACRO_CACHE_KEY)
