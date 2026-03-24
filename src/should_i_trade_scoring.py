"""Should I Be Trading? — Scoring engine.

Computes category scores (0–100), Market Quality Score, Execution Window Score,
and YES/CAUTION/NO decision. Configurable weights and thresholds.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Editable config (can be loaded from JSON)
DEFAULT_WEIGHTS = {
    "volatility": 0.25,
    "momentum": 0.25,
    "trend": 0.20,
    "breadth": 0.20,
    "macro": 0.10,
}

# Swing trading thresholds
SWING_THRESHOLDS = {
    "yes_min": 80,
    "caution_min": 60,
}

# Day trading: tighter
DAY_THRESHOLDS = {
    "yes_min": 85,
    "caution_min": 65,
}

CONFIG_PATH = Path(__file__).resolve().parent / "should_i_trade_config.json"


def _load_config() -> dict:
    """Load config from JSON if present."""
    try:
        import json
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text())
            return {
                "weights": data.get("weights", DEFAULT_WEIGHTS),
                "swing": data.get("swing_thresholds", SWING_THRESHOLDS),
                "day": data.get("day_thresholds", DAY_THRESHOLDS),
            }
    except Exception as e:
        logger.debug("Config load failed: %s", e)
    return {
        "weights": DEFAULT_WEIGHTS,
        "swing": SWING_THRESHOLDS,
        "day": DAY_THRESHOLDS,
    }


def score_volatility(data: dict) -> tuple[float, str]:
    """Score volatility 0–100. Lower VIX = higher score. Penalize rising VIX."""
    vix = data.get("vix")
    slope = data.get("vix_5d_slope")
    if vix is None:
        return 50.0, "unknown"
    base = 100.0
    if vix < 12:
        base = 95
    elif vix < 15:
        base = 88
    elif vix < 18:
        base = 78
    elif vix < 20:
        base = 68
    elif vix < 25:
        base = 55
    elif vix < 30:
        base = 40
    else:
        base = 25
    penalty = 0
    if slope is not None:
        if slope > 1.0:
            penalty = 15
        elif slope > 0.5:
            penalty = 8
        elif slope < -0.5:
            penalty = -5  # bonus for falling VIX
    score = max(0, min(100, base - penalty))
    if score >= 75:
        interp = "healthy"
    elif score >= 50:
        interp = "moderate"
    else:
        interp = "risk-off"
    return round(score, 1), interp


def score_trend(data: dict) -> tuple[float, str]:
    """Score trend 0–100. Uptrend + QQQ above 50 + RSI 40–70 = high."""
    regime = data.get("regime", "chop")
    qqq_above = data.get("qqq_above_50")
    rsi = data.get("spy_rsi")
    spy_above_20 = data.get("spy_above_20")
    spy_above_50 = data.get("spy_above_50")
    spy_above_200 = data.get("spy_above_200")
    if regime == "uptrend":
        base = 85
    elif regime == "downtrend":
        base = 25
    else:
        base = 55
    if qqq_above:
        base += 5
    elif qqq_above is False:
        base -= 10
    if rsi is not None:
        if 40 <= rsi <= 70:
            base += 5
        elif rsi > 75:
            base -= 5
        elif rsi < 30:
            base -= 10
    score = max(0, min(100, base))
    if score >= 75:
        interp = "healthy"
    elif score >= 50:
        interp = "weakening"
    else:
        interp = "risk-off"
    return round(score, 1), interp


def score_breadth(data: dict) -> tuple[float, str]:
    """Score breadth 0–100. % above 200d >50%, ratio5 >1.2, new highs > new lows."""
    pct_200 = data.get("pct_above_200")
    pct_50 = data.get("pct_above_50")
    pct_20 = data.get("pct_above_20")
    ratio5 = data.get("ratio5")
    new_highs = data.get("new_highs")
    new_lows = data.get("new_lows")
    base = 50
    if pct_200 is not None:
        if pct_200 >= 60:
            base = 85
        elif pct_200 >= 50:
            base = 75
        elif pct_200 >= 40:
            base = 60
        else:
            base = 40
    if ratio5 is not None:
        if ratio5 > 1.2:
            base += 10
        elif ratio5 > 1.0:
            base += 5
        elif ratio5 < 0.8:
            base -= 15
    if new_highs is not None and new_lows is not None and new_lows > 0:
        if new_highs > new_lows:
            base += 5
    score = max(0, min(100, base))
    if score >= 75:
        interp = "healthy"
    elif score >= 50:
        interp = "weakening"
    else:
        interp = "risk-off"
    return round(score, 1), interp


def score_momentum(data: dict) -> tuple[float, str]:
    """Score momentum 0–100. Sector spread positive, leaders > laggards."""
    spread = data.get("spread")
    pct_hh = data.get("pct_higher_highs")
    sectors = data.get("sectors", [])
    base = 50
    if spread is not None:
        if spread > 1.5:
            base = 85
        elif spread > 0.5:
            base = 75
        elif spread > 0:
            base = 65
        elif spread < -1.0:
            base = 30
        else:
            base = 50
    if pct_hh is not None and pct_hh > 5:
        base += 5
    score = max(0, min(100, base))
    if score >= 75:
        interp = "healthy"
    elif score >= 50:
        interp = "weakening"
    else:
        interp = "risk-off"
    return round(score, 1), interp


def score_macro(data: dict) -> tuple[float, str]:
    """Score macro 0–100 from yield stability (10Y 5d change)."""
    base = 70
    tnx_trend = data.get("tnx_5d_trend")
    if tnx_trend is not None and abs(tnx_trend) > 0.15:
        base -= 5
    score = max(0, min(100, base))
    if score >= 75:
        interp = "healthy"
    elif score >= 50:
        interp = "weakening"
    else:
        interp = "risk-off"
    return round(score, 1), interp


def _breakout_health_from_breadth(breadth: dict) -> tuple[float | None, str]:
    """Combine $1B+ Key Metrics (SMA stack, new highs, NH/NL) with StockBee 5-day ratio.

    Returns (0–100 score or None if no usable inputs, short detail string for UI).
    """
    u = breadth.get("universe_1b") or {}
    ratio5 = breadth.get("ratio5")
    p20 = u.get("pct_sma20")
    p50 = u.get("pct_sma50")
    p200 = u.get("pct_sma200")
    pnh = u.get("pct_new_highs")
    nh_nl = u.get("nh_nl_ratio")
    r5_score = min(100, max(0, (ratio5 - 0.5) * 80)) if ratio5 is not None else None

    smas = [x for x in (p20, p50, p200) if x is not None]
    avg_sma = sum(smas) / len(smas) if smas else None

    parts: list[tuple[float, float]] = []
    if avg_sma is not None:
        parts.append((float(avg_sma), 0.38))
    if pnh is not None:
        parts.append((min(100.0, float(pnh) * 3.5), 0.28))
    if nh_nl is not None:
        parts.append((float(nh_nl) * 100.0, 0.17))
    if r5_score is not None:
        parts.append((float(r5_score), 0.17))

    if not parts:
        return None, ""

    tw = sum(w for _, w in parts)
    score = sum(s * w for s, w in parts) / tw if tw else None
    if score is None:
        return None, ""

    bits = []
    if avg_sma is not None:
        bits.append(f"$1B+ above SMAs ~{avg_sma:.0f}%")
    if pnh is not None:
        bits.append(f"new 20d highs {pnh:.1f}%")
    if nh_nl is not None:
        bits.append(f"NH/(NH+NL) {nh_nl * 100:.0f}%")
    if ratio5 is not None:
        bits.append(f"5d breadth r {ratio5:.2f}")
    detail = " · ".join(bits) if bits else "breadth blend"
    return round(max(0, min(100, score)), 1), detail


def _breakout_yes_no_mixed(
    health: float | None,
    u: dict,
    ratio5: float | None,
) -> tuple[str, str]:
    """Map breakout health + raw $1B+ fields to Yes/No/Mixed and a detail line."""
    pnh = u.get("pct_new_highs")
    nh_nl = u.get("nh_nl_ratio")

    if health is None:
        if ratio5 is None:
            return "Mixed", "Insufficient breadth data"
        if ratio5 > 1.1:
            return "Yes", "Working (5d ratio only — refresh Key Metrics for $1B+ detail)"
        if ratio5 < 0.9:
            return "No", "Failing (5d ratio only)"
        return "Mixed", "Unclear (5d ratio only)"

    # Primary: composite health score
    if health >= 58 and (pnh is None or pnh >= 7.5) and (nh_nl is None or nh_nl >= 0.42):
        tag = "Working"
    elif health < 40 or (pnh is not None and pnh < 4.0) or (nh_nl is not None and nh_nl < 0.33):
        tag = "Failing"
    else:
        tag = "Unclear"

    if tag == "Working":
        return "Yes", tag
    if tag == "Failing":
        return "No", tag
    return "Mixed", tag


def score_execution_window(data: dict) -> tuple[float, dict]:
    """Execution Window Score 0–100 and qualitative factors.
    Returns (score, {breakouts_working, leaders_holding, pullbacks_bought, follow_through}).

    Breakout quality uses $1B+ Key Metrics (Price>SMA20/50/200, new 20d highs, NH vs NL share)
    blended with StockBee 5-day advance/decline ratio when available.
    """
    breadth = data.get("breadth", {})
    momentum = data.get("momentum", {})
    ratio5 = breadth.get("ratio5")
    pct_20 = breadth.get("pct_above_20")
    spread = momentum.get("spread")
    pct_hh = momentum.get("pct_higher_highs")
    pos_count = sum(1 for s in momentum.get("sectors", []) if (s.get("chg") or 0) >= 0)
    u = breadth.get("universe_1b") or {}

    breakout_health, breakout_detail = _breakout_health_from_breadth(breadth)
    breakouts, breakouts_tag = _breakout_yes_no_mixed(breakout_health, u, ratio5)
    breakouts_detail = breakout_detail if breakout_detail else breakouts_tag

    parts: list[tuple[float, float]] = []
    if breakout_health is not None:
        parts.append((breakout_health, 0.45))
    elif ratio5 is not None:
        r5_score = min(100, max(0, (ratio5 - 0.5) * 80))
        parts.append((r5_score, 0.4))
    if pct_20 is not None:
        w = 0.28 if breakout_health is not None else 0.3
        parts.append((pct_20, w))
    if spread is not None:
        sp_score = min(100, max(0, 50 + spread * 15))
        w = 0.17 if breakout_health is not None else 0.2
        parts.append((sp_score, w))
    if pct_hh is not None:
        hh_score = min(100, pct_hh * 5)
        w = 0.1 if breakout_health is not None else 0.1
        parts.append((hh_score, w))

    if not parts:
        score = 50.0
    else:
        total_w = sum(w for _, w in parts)
        score = sum(s * w for s, w in parts) / total_w if total_w else 50
    score = round(max(0, min(100, score)), 1)

    leaders = "Yes" if pos_count >= 6 else ("No" if pos_count <= 2 else "Mixed")
    leaders_detail = "Holding" if leaders == "Yes" else ("Fading" if leaders == "No" else "Mixed")

    # Pullbacks bought: blend ratio5 with $1B+ SMA participation when present
    smas = [x for x in (u.get("pct_sma20"), u.get("pct_sma50"), u.get("pct_sma200")) if x is not None]
    avg_sma = sum(smas) / len(smas) if smas else None
    pullback_score = None
    if ratio5 is not None:
        pullback_score = min(100, max(0, (ratio5 - 0.5) * 80))
    if avg_sma is not None and pullback_score is not None:
        pullback_score = 0.55 * pullback_score + 0.45 * float(avg_sma)
    elif avg_sma is not None:
        pullback_score = float(avg_sma)

    if pullback_score is not None:
        pullbacks = "Yes" if pullback_score >= 52 else ("No" if pullback_score < 38 else "Mixed")
        pullbacks_detail = "Support" if pullbacks == "Yes" else ("Selling" if pullbacks == "No" else "Mixed")
    else:
        pullbacks = "Yes" if ratio5 and ratio5 > 0.95 else ("No" if ratio5 and ratio5 < 0.7 else "Mixed")
        pullbacks_detail = "Support" if pullbacks == "Yes" else ("Selling" if pullbacks == "No" else "Mixed")

    follow = "Strong" if score >= 70 else ("Weak" if score < 40 else "Moderate")
    follow_detail = "High conviction" if follow == "Strong" else ("Low conviction" if follow == "Weak" else "Moderate")
    factors = {
        "breakouts_working": (breakouts, f"{breakouts_tag} — {breakouts_detail}"),
        "leaders_holding": (leaders, leaders_detail),
        "pullbacks_bought": (pullbacks, pullbacks_detail),
        "follow_through": (follow, follow_detail),
    }
    return score, factors


def compute_scores(data: dict, mode: str = "swing") -> dict:
    """Compute all category scores, MQS, EWS, and decision.
    mode: 'swing' or 'day'."""
    config = _load_config()
    weights = config["weights"]
    thresholds = config["swing"] if mode == "swing" else config["day"]

    vol = data.get("volatility", {})
    trend = data.get("trend", {})
    breadth = data.get("breadth", {})
    momentum = data.get("momentum", {})
    macro = data.get("macro", {})

    s_vol, interp_vol = score_volatility(vol)
    s_trend, interp_trend = score_trend(trend)
    s_breadth, interp_breadth = score_breadth(breadth)
    s_mom, interp_mom = score_momentum(momentum)
    s_macro, interp_macro = score_macro(macro)

    w_vol = weights.get("volatility", 0.25)
    w_mom = weights.get("momentum", 0.25)
    w_trend = weights.get("trend", 0.20)
    w_breadth = weights.get("breadth", 0.20)
    w_macro = weights.get("macro", 0.10)

    mqs = (
        s_vol * w_vol
        + s_mom * w_mom
        + s_trend * w_trend
        + s_breadth * w_breadth
        + s_macro * w_macro
    )
    mqs = round(mqs, 1)

    ews_result = score_execution_window(data)
    ews = ews_result[0] if isinstance(ews_result, tuple) else ews_result
    ew_factors = ews_result[1] if isinstance(ews_result, tuple) and len(ews_result) > 1 else {}

    if mqs >= thresholds["yes_min"]:
        decision = "YES"
    elif mqs >= thresholds["caution_min"]:
        decision = "CAUTION"
    else:
        decision = "NO"

    return {
        "category_scores": {
            "volatility": {"score": s_vol, "weight": w_vol, "interpretation": interp_vol},
            "trend": {"score": s_trend, "weight": w_trend, "interpretation": interp_trend},
            "breadth": {"score": s_breadth, "weight": w_breadth, "interpretation": interp_breadth},
            "momentum": {"score": s_mom, "weight": w_mom, "interpretation": interp_mom},
            "macro": {"score": s_macro, "weight": w_macro, "interpretation": interp_macro},
        },
        "market_quality_score": mqs,
        "execution_window_score": ews,
        "execution_window_factors": ew_factors,
        "decision": decision,
        "mode": mode,
    }


def generate_terminal_analysis(data: dict, scores: dict) -> str:
    """Generate plain-English summary from regime, scores, and sector leadership."""
    trend = data.get("trend", {})
    vol = data.get("volatility", {})
    breadth = data.get("breadth", {})
    momentum = data.get("momentum", {})
    decision = scores.get("decision", "CAUTION")

    regime = trend.get("regime", "chop")
    if regime == "uptrend":
        trend_desc = "strong trend"
    elif regime == "downtrend":
        trend_desc = "weak trend"
    else:
        trend_desc = "choppy"

    vix = vol.get("vix")
    if vix is None:
        vol_desc = "unknown volatility"
    elif vix < 15:
        vol_desc = "low volatility"
    elif vix < 20:
        vol_desc = "moderate volatility"
    else:
        vol_desc = "elevated volatility"

    ratio5 = breadth.get("ratio5")
    u1b = breadth.get("universe_1b") or {}
    smas = [x for x in (u1b.get("pct_sma20"), u1b.get("pct_sma50"), u1b.get("pct_sma200")) if x is not None]
    avg1b = sum(smas) / len(smas) if smas else None
    if avg1b is not None and u1b.get("pct_new_highs") is not None:
        breadth_desc = (
            f"$1B+ tape ~{avg1b:.0f}% above key SMAs, {u1b['pct_new_highs']:.1f}% new 20d highs"
        )
        if ratio5 is not None:
            breadth_desc += f", StockBee 5d ratio {ratio5:.2f}"
    elif ratio5 is None:
        breadth_desc = "neutral breadth"
    elif ratio5 > 1.2:
        breadth_desc = "expanding breadth"
    elif ratio5 < 0.8:
        breadth_desc = "contracting breadth"
    else:
        breadth_desc = "neutral breadth"

    leaders = [s.get("ticker", "") for s in momentum.get("top3", [])[:3]]
    leader_names = ", ".join(leaders) if leaders else "mixed"

    if decision == "YES":
        action = "Favor selective swing trades with disciplined risk."
        suggested = "Full size, press risk"
    elif decision == "CAUTION":
        action = "Reduce size, A+ setups only."
        suggested = "Half size, A+ setups only"
    else:
        action = "Avoid trading, preserve capital."
        suggested = "Sit on hands"

    summary = (
        f"This is a {trend_desc} environment with {breadth_desc} and {vol_desc}"
        + (f" (VIX {vix:.1f})" if vix is not None else "")
        + f". Sector leadership in {leader_names}. {action}"
    )
    return {"text": summary, "suggested_action": suggested}
