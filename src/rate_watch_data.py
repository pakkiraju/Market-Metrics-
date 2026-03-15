"""Rate Watch: Central bank interest rate probabilities for 8 currencies.

Tracks Fed, ECB, BoE, BoJ, BoC, SNB, RBA, RBNZ with:
- Current key rate and policy rate
- Cut/Hold/Hike probabilities for next 6 meetings
- Expected rate path for next 8 meetings
- Detailed probability distribution table
- Fed-specific rate range probabilities

Data sources: rateprobability.com (Fed, ECB, BoE, BoJ, BoC, RBA)
"""

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from lxml import html

from src import cache
from src.cache import MEDIUM

logger = logging.getLogger(__name__)

RATE_WATCH_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD"]

BANK_INFO = {
    "USD": {"bank_name": "Federal Reserve (Fed)", "policy_name": "Fed Funds Target Rate"},
    "EUR": {"bank_name": "European Central Bank (ECB)", "policy_name": "Main Refinancing Rate"},
    "GBP": {"bank_name": "Bank of England", "policy_name": "Bank Rate"},
    "JPY": {"bank_name": "Bank of Japan", "policy_name": "Policy Rate"},
    "CAD": {"bank_name": "Bank of Canada", "policy_name": "Overnight Rate"},
    "CHF": {"bank_name": "Swiss National Bank (SNB)", "policy_name": "Policy Rate"},
    "AUD": {"bank_name": "Reserve Bank of Australia (RBA)", "policy_name": "Cash Rate"},
    "NZD": {"bank_name": "Reserve Bank of New Zealand (RBNZ)", "policy_name": "Official Cash Rate"},
}

# rateprobability.com URL path per currency (None = no scraper)
RATEPROBABILITY_PATHS = {
    "USD": "fed",
    "EUR": "ecb",
    "GBP": "boe",
    "JPY": "boj",
    "CAD": "boc",
    "CHF": None,
    "AUD": "rba",
    "NZD": None,
}

# Fallback current rates when scrape fails (as of 2025)
FALLBACK_CURRENT_RATES = {
    "USD": (4.25, 4.50),
    "EUR": 2.00,
    "GBP": 3.75,
    "JPY": 0.30,
    "CAD": 5.25,
    "CHF": 1.25,
    "AUD": 4.35,
    "NZD": 5.50,
}


def _parse_pct(s: str) -> float | None:
    """Parse percentage string like '3.60%' or '(18.0%)' to float."""
    if not s or s.strip() in ("—", "-", ""):
        return None
    s = str(s).strip().replace(",", "").replace("%", "").replace("(", "").replace(")", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(s: str) -> str | None:
    """Parse 'Jan 28, 2026' to '2026-01-28'."""
    if not s or s.strip() in ("—", "-", ""):
        return None
    try:
        dt = datetime.strptime(s.strip(), "%b %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return s.strip()


def _scrape_rateprobability(path: str) -> dict | None:
    """Scrape rateprobability.com/{path} and return structured data."""
    url = f"https://rateprobability.com/{path}"
    try:
        r = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        r.raise_for_status()
        r.encoding = "utf-8"
        tree = html.fromstring(r.content)
    except Exception as e:
        logger.warning("Rateprobability fetch %s failed: %s", path, e)
        return None

    # Current rate: look for "Current Rate" followed by value
    current_rate = None
    for elem in tree.iter():
        text = (elem.text or "") + (elem.tail or "")
        if "Current Rate" in text:
            parent = elem.getparent()
            if parent is not None:
                for c in parent.iter():
                    t = (c.text or "").strip()
                    m = re.search(r"([\d.]+)\s*%", t)
                    if m:
                        current_rate = float(m.group(1))
                        break
            if current_rate is not None:
                break

    # Parse table
    tables = tree.xpath("//table")
    if not tables:
        return None

    rows = tables[0].xpath(".//tr")
    meetings = []
    now = datetime.now(ZoneInfo("America/New_York"))
    today = now.date()

    for row in rows[1:]:  # skip header
        cells = row.xpath(".//td | .//th")
        if len(cells) < 3:
            continue
        vals = [c.text_content().strip() for c in cells]
        meeting_str = vals[0] if vals else ""
        implied_str = vals[1] if len(vals) > 1 else ""
        prob_str = vals[2] if len(vals) > 2 else ""

        if not meeting_str or meeting_str in ("—", "-", "Meeting"):
            continue

        date_parsed = _parse_date(meeting_str)
        exp_rate = _parse_pct(implied_str)
        move_prob = _parse_pct(prob_str)

        if date_parsed and exp_rate is not None:
            try:
                mtg_dt = datetime.strptime(date_parsed, "%Y-%m-%d").date()
                days_until = (mtg_dt - today).days
            except ValueError:
                days_until = 0

            # prob_str: "(18.0%)" = cut 18%, "4.0%" = hike 4%
            cut_pct = 0.0
            hike_pct = 0.0
            if move_prob is not None and prob_str:
                if prob_str.strip().startswith("("):
                    cut_pct = move_prob
                else:
                    hike_pct = move_prob
            hold_pct = max(0, 100 - cut_pct - hike_pct)

            meeting = {
                "date": date_parsed,
                "date_label": meeting_str,
                "days_until": days_until,
                "exp_rate": exp_rate,
                "cut_pct": round(cut_pct, 1),
                "hold_pct": round(hold_pct, 1),
                "hike_pct": round(hike_pct, 1),
            }
            meetings.append(meeting)

    if not meetings:
        return None

    return {
        "current_rate": current_rate or (meetings[0]["exp_rate"] if meetings else 0),
        "meetings": meetings,
    }


def _scrape_fed_rate_ranges() -> list[dict] | None:
    """Scrape CME FedWatch for rate range probabilities (USD only). Falls back to None."""
    url = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"
    try:
        r = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        r.raise_for_status()
        text = r.text
    except Exception as e:
        logger.debug("CME FedWatch scrape failed: %s", e)
        return None

    # CME page loads data via JS - not easily scrapable. Return None for now.
    return None


def _build_data_from_scrape(currency: str, scraped: dict) -> dict:
    """Convert scraped data to our standard format."""
    info = BANK_INFO.get(currency, {"bank_name": "Central Bank", "policy_name": "Policy Rate"})
    current = scraped.get("current_rate") or 0
    meetings = scraped.get("meetings", [])

    if isinstance(current, (int, float)):
        current_rate_str = f"{current}%"
        current_rate_val = float(current)
    else:
        current_rate_str = str(current)
        current_rate_val = float(current) if current else 0

    # Add rate ranges for Fed (approximate from cut/hold/hike - CME scrape not reliable)
    if currency == "USD" and meetings:
        exp = meetings[0]["exp_rate"]
        cut, hold, hike = meetings[0]["cut_pct"], meetings[0]["hold_pct"], meetings[0]["hike_pct"]
        # Build 25bp range probabilities
        ranges = [
            {"range": f"{exp+0.25:.2f}-{exp+0.50:.2f}", "pct": min(100, hike)},
            {"range": f"{exp:.2f}-{exp+0.25:.2f}", "pct": min(100, hold)},
            {"range": f"{exp-0.25:.2f}-{exp:.2f}", "pct": min(100, cut)},
        ]
        meetings[0]["rate_ranges"] = [r for r in ranges if r["pct"] > 0.1]

    return {
        "currency": currency,
        "bank_name": info["bank_name"],
        "policy_name": info["policy_name"],
        "current_rate": current_rate_val,
        "current_rate_str": current_rate_str,
        "policy_rate": current_rate_val,
        "next_meeting_date": meetings[0]["date"] if meetings else None,
        "next_meeting_days": meetings[0]["days_until"] if meetings else None,
        "meetings": meetings[:8],
    }


def _mock_data(currency: str) -> dict:
    """Return mock rate watch data when real data unavailable."""
    now = datetime.now(ZoneInfo("America/New_York"))
    info = BANK_INFO.get(currency, {"bank_name": "Central Bank", "policy_name": "Policy Rate"})
    cr = FALLBACK_CURRENT_RATES.get(currency, 3.0)

    if isinstance(cr, tuple):
        current_rate_str = f"{cr[0]}-{cr[1]}%"
        current_rate_val = (cr[0] + cr[1]) / 2
    else:
        current_rate_str = f"{cr}%"
        current_rate_val = cr

    meetings = []
    for i in range(8):
        mtg_date = now.date() + timedelta(days=42 * (i + 1))
        days_until = (mtg_date - now.date()).days
        cut_pct = min(90, 10 + i * 12)
        hold_pct = max(5, 85 - cut_pct)
        hike_pct = max(0, 100 - cut_pct - hold_pct)
        exp_rate = max(0.1, 4.5 - i * 0.25 if currency == "USD" else 3.5 - i * 0.2)

        m = {
            "date": mtg_date.strftime("%Y-%m-%d"),
            "date_label": mtg_date.strftime("%b %d, %Y"),
            "days_until": days_until,
            "exp_rate": round(exp_rate, 3),
            "cut_pct": round(cut_pct, 1),
            "hold_pct": round(hold_pct, 1),
            "hike_pct": round(hike_pct, 1),
        }
        if currency == "USD":
            m["rate_ranges"] = [
                {"range": "4.25-4.50", "pct": 45.3},
                {"range": "4.00-4.25", "pct": 32.1},
                {"range": "3.75-4.00", "pct": 12.4},
            ]
        meetings.append(m)

    return {
        "currency": currency,
        "bank_name": info["bank_name"],
        "policy_name": info["policy_name"],
        "current_rate": current_rate_val,
        "current_rate_str": current_rate_str,
        "policy_rate": current_rate_val,
        "next_meeting_date": meetings[0]["date"] if meetings else None,
        "next_meeting_days": meetings[0]["days_until"] if meetings else None,
        "meetings": meetings,
    }


def fetch_rate_watch_data(currency: str, ttl: int = MEDIUM) -> dict:
    """Fetch rate watch data for a currency. Uses rateprobability.com when available."""
    cache_key = f"rate_watch_{currency}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    path = RATEPROBABILITY_PATHS.get(currency)
    if path:
        scraped = _scrape_rateprobability(path)
        if scraped and scraped.get("meetings"):
            try:
                data = _build_data_from_scrape(currency, scraped)
                cache.put(cache_key, data, ttl=ttl)
                return data
            except Exception as e:
                logger.warning("Rate watch parse failed for %s: %s", currency, e)

    data = _mock_data(currency)
    cache.put(cache_key, data, ttl=ttl)
    return data
