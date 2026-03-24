"""Rule-based hawkish/dovish signal tags and bottom-line narrative for Macro Monitor."""

from __future__ import annotations

from typing import Any, Literal

Signal = Literal["hawkish", "dovish", "neutral", "mixed", "tightening"]


def classify_metric(metric_id: str, kpi: dict[str, Any]) -> Signal:
    """Map one KPI to a coarse policy signal. Tune thresholds here."""
    val = kpi.get("value_num")
    tr = kpi.get("trend")  # "up", "down", "flat" if set

    if val is None:
        return "neutral"

    if metric_id == "fed_funds":
        return "tightening" if isinstance(val, (int, float)) and val > 4.0 else "neutral"

    if metric_id in ("cpi_yoy", "core_cpi_yoy", "ppi_yoy", "pce_yoy", "core_pce_yoy"):
        if val > 3.0:
            return "hawkish"
        if val < 2.0:
            return "dovish"
        return "neutral"

    if metric_id == "unemployment":
        if val > 5.0:
            return "dovish"
        if val < 4.0:
            return "hawkish"
        return "neutral"

    if metric_id == "nfp":
        if isinstance(val, (int, float)):
            if val < 0:
                return "dovish"
            if val > 200:
                return "hawkish"
        return "neutral"

    if metric_id == "brent":
        if isinstance(val, (int, float)) and val > 90:
            return "hawkish"
        return "neutral"

    if metric_id == "sp500":
        if tr == "down":
            return "dovish"
        if tr == "up":
            return "hawkish"
        return "neutral"

    if metric_id == "sentiment":
        if isinstance(val, (int, float)):
            if val < 70:
                return "dovish"
            if val > 95:
                return "hawkish"
        return "neutral"

    if metric_id == "deficit":
        return "tightening"

    return "neutral"


def count_signals(kpis: dict[str, dict[str, Any]]) -> dict[Signal, int]:
    counts: dict[Signal, int] = {
        "hawkish": 0, "dovish": 0, "neutral": 0, "mixed": 0, "tightening": 0,
    }
    for mid, k in kpis.items():
        sig = k.get("signal") or classify_metric(mid, k)
        if sig in counts:
            counts[sig] += 1
    return counts


def dominant_label(counts: dict[Signal, int]) -> str:
    total = sum(counts.values()) or 1
    h, d = counts["hawkish"], counts["dovish"]
    if h / total > 0.35 and h > d:
        return "Leaning Hawkish"
    if d / total > 0.35 and d > h:
        return "Leaning Dovish"
    if counts["tightening"] >= 2:
        return "Fiscal / rate pressure"
    return "Mixed / data-dependent"


def build_narrative(kpis: dict[str, dict[str, Any]], counts: dict[Signal, int]) -> str:
    """2–4 sentences from latest KPI display strings."""
    parts = []
    label = dominant_label(counts)
    parts.append(f"Signal balance: {label}. ")

    cpi = kpis.get("cpi_yoy", {}).get("display")
    core = kpis.get("core_cpi_yoy", {}).get("display")
    if cpi and core:
        parts.append(f"Headline CPI is {cpi}; core CPI {core}. ")

    un = kpis.get("unemployment", {}).get("display")
    nfp = kpis.get("nfp", {}).get("display")
    if un and nfp:
        parts.append(f"Labor: unemployment {un}, payroll change {nfp}. ")

    br = kpis.get("brent", {}).get("display")
    if br:
        parts.append(f"Energy: Brent {br}. ")

    ff = kpis.get("fed_funds", {}).get("display")
    if ff:
        parts.append(f"Policy rate context: {ff}. ")

    return "".join(parts).strip() or "Configure FRED_API_KEY and refresh to load macro data."
