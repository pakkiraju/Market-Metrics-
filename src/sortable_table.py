"""Sortable table infrastructure: sort key extractors and header builders."""

import re
from dash import html

from src.constants import COLORS, SECTOR_NAMES
from src.styles import TABLE_HEADER_STYLE


def _parse_sort_num(val) -> float:
    """Parse value to float for sorting. Handles K/M/B, %, commas."""
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return 0.0
    s = str(val).strip().replace(",", "").replace("$", "").replace("%", "")
    if not s or s == "-":
        return 0.0
    m = re.match(r"([\d.-]+)\s*([KMB])?", s, re.I)
    if m:
        v = float(m.group(1))
        suf = (m.group(2) or "").upper()
        if suf == "K":
            v *= 1e3
        elif suf == "M":
            v *= 1e6
        elif suf == "B":
            v *= 1e9
        return v
    try:
        return float(s)
    except ValueError:
        return 0.0


# Sort key extractors: (row) -> comparable value
SCREENER_SORT_KEYS = {
    "ticker": lambda r: ((r.get("ticker") or "").upper(),),
    "news": lambda r: ((r.get("news") or r.get("news_url") or "").lower(),),
    "price": lambda r: (_parse_sort_num(r.get("price")),),
    "avg_vol": lambda r: (_parse_sort_num(r.get("avg_vol")),),
    "rel_vol": lambda r: (_parse_sort_num(r.get("rel_vol")),),
    "change": lambda r: (
        float(str(r.get("change") or "0").replace("%", "").replace(",", "")) or 0,
    ),
    "volume": lambda r: (_parse_sort_num(r.get("volume")),),
    "atr_pct": lambda r: (r.get("atr_pct") if r.get("atr_pct") is not None else 0.0,),
    "week": lambda r: (r.get("week") or 0.0,),
    "roe": lambda r: (r.get("roe") if r.get("roe") is not None else 0.0,),
    "net_margin": lambda r: (r.get("net_margin") if r.get("net_margin") is not None else 0.0,),
    "tag": lambda r: (str(r.get("tag") or ""),),
    "chg": lambda r: (
        float(str(r.get("chg") or r.get("change") or "0").replace("%", "").replace(",", "")) or 0,
    ),
}

# Sector table sort keys
SECTOR_SORT_KEYS = {
    "sector": lambda r: (SECTOR_NAMES.get(r.get("ticker"), r.get("ticker", "")),),
    "ticker": lambda r: ((r.get("ticker") or "").upper(),),
    "gap": lambda r: (r.get("gap") or 0,),
    "chg": lambda r: (r.get("chg") or 0,),
    "ochg": lambda r: (r.get("ochg") or 0,),
    "week": lambda r: (r.get("week") or 0,),
    "month": lambda r: (r.get("month") or 0,),
    "qtr": lambda r: (r.get("qtr") or 0,),
    "hyear": lambda r: (r.get("hyear") or 0,),
    "year": lambda r: (r.get("year") or 0,),
}

# 20pct weekly sort keys (week column uses "week" key)
# 4pct daily uses "chg" - already in SCREENER_SORT_KEYS

# Leading industries sort keys (no change column; sort by top_both to put best first)
LEADING_SORT_KEYS = {
    "industry": lambda r: ((r.get("industry") or "").lower(),),
    "top_both": lambda r: (1 if r.get("top_both") else 0, (r.get("industry") or "").lower()),
}

# Thematics sort keys (same structure as leading industries)
THEMATICS_SORT_KEYS = {
    "theme": lambda r: ((r.get("theme") or "").lower(),),
    "top_both": lambda r: (1 if r.get("top_both") else 0, (r.get("theme") or "").lower()),
}


def sortable_header(label: str, widget_id: str, col_key: str, sort_col: str | None, sort_asc: bool) -> html.Th:
    """Build a clickable table header for sorting."""
    arrow = ""
    if sort_col == col_key:
        arrow = " ▲" if sort_asc else " ▼"
    btn_style = {
        "background": "none",
        "border": "none",
        "color": "inherit",
        "cursor": "pointer",
        "fontSize": "inherit",
        "fontWeight": "inherit",
        "padding": 0,
        "textAlign": "inherit",
        "width": "100%",
    }
    return html.Th(
        html.Button(
            label + arrow,
            id={"type": "sort-header", "widget": widget_id, "column": col_key},
            n_clicks=0,
            style=btn_style,
        ),
        style=TABLE_HEADER_STYLE,
    )


def sort_data(data: list[dict], col_key: str, asc: bool, sort_keys: dict) -> list[dict]:
    """Sort data by column. sort_keys maps col_key -> extractor(row) -> tuple."""
    extractor = sort_keys.get(col_key)
    if not extractor:
        return data
    reverse = not asc
    return sorted(data, key=extractor, reverse=reverse)
