"""Dash layout: widget-based Bloomberg-terminal-style dashboard.

All sections are toggleable widgets. Key Metrics, NASDAQ/S&P chart, and
Combined chart are full-size (no internal scroll). Other widgets have
max-height with internal scroll. Clicking any ticker opens a TradingView
chart modal. Watchlist supports user add/remove.
"""

import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from dash import html, dcc
import plotly.graph_objects as go

from src.constants import (
    COLORS, KEY_METRIC_ROWS, INDEX_GROUPS, SECTOR_NAMES,
    STAGE_BAR_COLORS, STAGE_LABELS, FINVIZ_SCREENER_URLS,
    build_metric_screener_url, RRG_BENCHMARK, RRG_COLORS,
    STOCKBEE_LINKS, GRAPH_CONFIG,
)
from src.styles import (
    DASHBOARD_STYLE, HEADER_STYLE, HEADER_LOGO_STYLE,
    SCROLLABLE_BODY_HEIGHT,
    HEADER_DATE_STYLE, REFRESH_BTN_STYLE,
    SETTINGS_BTN_STYLE,
    CONTENT_AREA_STYLE,
    PRIMARY_ROW_STYLE, QUARTER_ROW_STYLE, THIRD_ROW_STYLE, WIDE_ROW_STYLE, HALF_ROW_STYLE,
    SNAPSHOT_MOVERS_ROW_STYLE,
    INTRADAY_TOP_MOVERS_BODY_STYLE, INTRADAY_SNAPSHOT_BODY_STYLE, INTRADAY_INDEX_ROW_CARD_STYLE,
    WIDGET_STYLE, WIDGET_PRIMARY_STYLE, WIDGET_SECONDARY_STYLE, WIDGET_KEY_METRICS_STYLE,
    section_header_style, SECTION_BODY_STYLE, KEY_METRICS_BODY_STYLE,
    TICKER_GRID_STYLE, ticker_pill_style,
    TABLE_STYLE, TABLE_HEADER_STYLE, TABLE_CELL_STYLE,
    CHART_WRAP_STYLE, BREADTH_CHART_BODY_STYLE, BREADTH_CHART_WRAP_STYLE, RRG_CHART_BODY_STYLE, SP500_LANDSCAPE_CHART_HEIGHT, STAGE_CHART_HEIGHT, LOADING_STYLE,
    SETTINGS_OVERLAY_STYLE_HIDDEN, SETTINGS_TITLE_STYLE,
    SETTINGS_ITEM_STYLE, TOGGLE_LABEL_STYLE,
    stage_badge_style,
)
from src.constants import pct_color, chg_color
from src.data_fetcher import _coerce_earnings_date_str
from src.macro_monitor_layout import build_macro_monitor_tab

ET = timezone(timedelta(hours=-5))

# Sidebar-only navigation: no dcc.Tabs (Dash would render a tab strip above content).
_TAB_PANE_HIDE = {"display": "none"}
_TAB_PANE_SHOW = {
    "display": "flex",
    "flexDirection": "column",
    "flex": "1",
    "minHeight": "0",
    "minWidth": "0",
    "overflow": "auto",
    "backgroundColor": COLORS["bg"],
}

# Widget registry: (id_suffix, display_name, is_primary_size)
# is_primary_size only controls sizing (full-size vs max-height), NOT toggleability
# Market Metrics tab widgets (excludes in_play — moved to Intraday)
MARKET_METRICS_WIDGETS = [
    ("key-metrics",    "Key Metrics",                True),
    ("chart2",         "NQ100, SPY500 & DJIA Metrics", True),
    ("chart3",         "RUS2000 & $1B+ Stocks", True),
    ("watchlist",      "Watchlist",                  False),
    ("sector",         "Sector SPDR ETFs",           False),
    ("rrg",            "RRG Sector Rotation",        False),
    ("sp500-landscape", "S&P 500 Landscape Bubble Chart", False),
    ("leading",        "Leading Industries",         False),
    ("thematics",      "Thematics Tracker",          False),
    ("thematics-sector", "Thematics by Sector (Top YTD)", False),
    ("thematics-rrg",  "Thematics RRG (vs VTI)",     False),
    ("stockbee",       "Stockbee Momentum50",        False),
    ("breadth",        "StockBee Market Breadth Monitor", False),
    ("breadth-primary", "StockBee - Primary Breadth — Up/Down 4%+ Today", False),
    ("breadth-ratios", "StockBee - Breadth Ratios — 5-Day & 10-Day", False),
    ("breadth-secondary", "StockBee - Secondary Breadth — Up/Down 25%+ Qtr", False),
    ("breadth-sp500",  "StockBee - S&P 500 — Last 60 Days",    False),
    ("stage",          "Stage Analysis",             False),
]
# Super Scanners tab — FinViz / StockBee screeners (moved from Market Metrics)
SUPER_SCANNERS_WIDGETS = [
    ("qulla",          "Qullamaggie",                False),
    ("minervini",      "Minervini",                  False),
    ("oneil",          "O'Neil",                     False),
    ("jeff_sun_canslim", "Jeff Sun - CANSLIM",       False),
    ("jeff_sun_high_adr", "Jeff Sun - High ADR% Hottest Stock", False),
    ("jeff_sun_extended_bases", "Jeff Sun - Extended Bases/Prolonged Consolidations", False),
    ("jeff_sun_1w20", "Jeff Sun - Strongest 1-Week Mover Exceeding 20%", False),
    ("jeff_sun_4w30", "Jeff Sun - Strongest 1-Month Mover Exceeding 30%", False),
    ("jeff_sun_4w50", "Jeff Sun - Strongest 1-Month Mover Exceeding 50%", False),
    ("jeff_sun_13w50", "Jeff Sun - Strongest 3-Month Mover Exceeding 50%", False),
    ("jeff_sun_26w100", "Jeff Sun - Strongest 6-Month Mover Exceeding 100%", False),
    ("jeff_sun_ipo_thisweek", "Jeff Sun - IPO", False),
    ("jeff_sun_high_short_float", "Jeff Sun - High Short Float", False),
    ("jeff_sun_liquid_etfs", "Jeff Sun - Liquid ETF's", False),
    ("julian_komar_strongest", "Julian Komar - Strongest Stocks", False),
    ("club97",         "97 Club",                    False),
    ("movers",         "StockBee - 9 Million Movers",           False),
    ("weekly",         "StockBee - 20% Weekly Movers",          False),
    ("daily",          "StockBee - 4% Daily Gainers",           False),
    ("earnings-calendar-week", "Earnings Calendar — This Week", False),
]
# Intraday tab widgets (in_play and earnings here)
INTRADAY_WIDGETS = [
    ("live_index",     "Market Snapshot",             False),
    ("in_play",        "Stocks In Play",             False),
    ("intraday-earnings", "Earnings Yesterday + Today", False),
    ("top_gainers",    "Top Gainers",                False),
    ("top_losers",     "Top Losers",                 False),
    ("pre_market",     "Pre-market Scanner",         False),
    ("cnbc_premarket", "CNBC Pre-Market Watchlist", False),
]
# Combined for backward compatibility and visibility callback
WIDGETS = MARKET_METRICS_WIDGETS + SUPER_SCANNERS_WIDGETS + INTRADAY_WIDGETS
ALL_WIDGET_IDS = [w[0] for w in WIDGETS]
# Default visibility: Market Metrics widgets + Intraday widgets
DEFAULT_VISIBILITY = {
    w[0]: w[0] in ("key-metrics", "chart2", "chart3", "qulla", "minervini", "oneil", "jeff_sun_canslim", "jeff_sun_high_adr", "jeff_sun_extended_bases", "jeff_sun_1w20", "jeff_sun_4w30", "jeff_sun_4w50", "jeff_sun_13w50", "jeff_sun_26w100", "jeff_sun_ipo_thisweek", "jeff_sun_high_short_float", "jeff_sun_liquid_etfs", "julian_komar_strongest", "watchlist", "sector", "rrg", "sp500-landscape", "club97", "movers", "weekly", "daily", "leading", "thematics", "thematics-sector", "thematics-rrg", "stockbee", "breadth", "breadth-primary", "breadth-ratios", "breadth-secondary", "breadth-sp500", "stage", "earnings-calendar-week", "live_index", "in_play", "intraday-earnings", "top_gainers", "top_losers", "pre_market", "cnbc_premarket") for w in WIDGETS
}

CLICKABLE_TICKER_STYLE = {
    "cursor": "pointer",
    "textDecoration": "none",
}


# -----------------------------------------------------------------------
# Helper: clickable ticker
# -----------------------------------------------------------------------

def _clickable_ticker(symbol, style=None):
    """Wrap a ticker symbol so clicking it opens the TradingView modal."""
    base_style = {**CLICKABLE_TICKER_STYLE}
    if style:
        base_style.update(style)
    return html.Span(
        symbol,
        className="tv-ticker",
        style=base_style,
    )


# -----------------------------------------------------------------------
# Helper builders
# -----------------------------------------------------------------------

# Small refresh button for per-widget reload (clears cache, refetches that widget only)
WIDGET_REFRESH_BTN_STYLE = {
    "background": "rgba(255,255,255,0.15)",
    "border": "none",
    "borderRadius": "3px",
    "color": "#fff",
    "cursor": "pointer",
    "fontSize": "10px",
    "fontWeight": 600,
    "padding": "1px 5px",
    "marginLeft": "4px",
    "lineHeight": 1,
}
WIDGET_EXPORT_BTN_STYLE = {
    **WIDGET_REFRESH_BTN_STYLE,
    "fontSize": "8px",
    "padding": "1px 4px",
    "background": "rgba(255,255,255,0.16)",
}
def _widget(widget_id, header_text, body_children, variant="default",
            count=None, extra_header=None, primary=False, initial_hidden=False,
            body_style=None, card_style_override=None, refreshable=True,
            watchlist_export=True):
    left_kids = [html.Span(header_text)]
    if count is not None:
        left_kids.append(html.Span(
            str(count),
            style={
                "background": "rgba(255,255,255,0.2)",
                "padding": "0 5px",
                "borderRadius": "2px",
                "fontSize": "9px",
                "marginLeft": "6px",
            },
        ))
    if extra_header:
        left_kids.append(extra_header)

    header_kids = [html.Div(left_kids, style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"})]
    right_header = []
    if refreshable:
        right_header.append(
            html.Button("↻", id=f"btn-refresh-{widget_id}", title="Refresh this widget",
                        style=WIDGET_REFRESH_BTN_STYLE, n_clicks=0)
        )
    if watchlist_export:
        right_header.append(
            html.Button(
                "Export WL",
                id={"type": "export-watchlist", "widget": widget_id},
                title="Download symbols as TradingView watchlist (.txt)",
                style=WIDGET_EXPORT_BTN_STYLE,
                n_clicks=0,
            )
        )
    if right_header:
        header_kids.append(
            html.Div(right_header, style={"display": "flex", "alignItems": "center", "gap": "3px", "flexShrink": 0}),
        )

    card_style = card_style_override or (WIDGET_PRIMARY_STYLE if primary else WIDGET_SECONDARY_STYLE)
    if initial_hidden:
        card_style = {**card_style, "display": "none"}

    body_style = body_style or SECTION_BODY_STYLE
    return html.Div(
        [
            html.Div(header_kids, style=section_header_style(variant)),
            html.Div(body_children, style=body_style),
        ],
        style=card_style,
        id=f"widget-{widget_id}",
    )


def _table(headers, rows, col_widths=None, widget_id=None, sort_col=None, sort_asc=True):
    """Build table. headers: list of (label, col_key) for sortable, or (label, None) for non-sortable.
    When widget_id is set and col_key is not None, header is clickable for sorting."""
    from src.sortable_table import sortable_header

    ths = []
    for i, h in enumerate(headers):
        st = {**TABLE_HEADER_STYLE}
        if col_widths and i < len(col_widths):
            st["width"] = col_widths[i]
        if isinstance(h, (list, tuple)) and len(h) >= 2:
            label, col_key = h[0], h[1]
            if widget_id and col_key:
                ths.append(sortable_header(label, widget_id, col_key, sort_col, sort_asc))
            else:
                ths.append(html.Th(label, style=st))
        else:
            label = h[0] if isinstance(h, (list, tuple)) else str(h)
            ths.append(html.Th(label, style=st))

    trs = []
    for row in rows:
        tds = []
        for cell in row:
            if isinstance(cell, dict):
                st = {**TABLE_CELL_STYLE, **cell.get("style", {})}
                tds.append(html.Td(cell["text"], style=st))
            else:
                tds.append(html.Td(str(cell), style=TABLE_CELL_STYLE))
        trs.append(html.Tr(tds))

    return html.Table(
        [html.Thead(html.Tr(ths)), html.Tbody(trs)],
        style=TABLE_STYLE,
    )


# -----------------------------------------------------------------------
# Section 1: Key Metrics Table
# -----------------------------------------------------------------------

def _finviz_link(text: str, url_key: str, style=None) -> html.A:
    """Inline link to FinViz screener."""
    url = FINVIZ_SCREENER_URLS.get(url_key, "#")
    base = {"fontSize": "8px", "fontWeight": 500, "color": COLORS["accent"], "textDecoration": "none"}
    if style:
        base.update(style)
    return html.A(text, href=url, target="_blank", rel="noopener noreferrer", style=base)


def _stockbee_link(text: str, url_key: str, style=None) -> html.A:
    """Inline link to Stockbee Google Sheet."""
    url = STOCKBEE_LINKS.get(url_key, "#")
    base = {"fontSize": "8px", "fontWeight": 500, "color": COLORS["accent"], "textDecoration": "none"}
    if style:
        base.update(style)
    return html.A(text, href=url, target="_blank", rel="noopener noreferrer", style=base)


def _screener_link(label: str, url_key: str) -> html.Th:
    """Header cell with clickable FinViz screener link."""
    url = FINVIZ_SCREENER_URLS.get(url_key, "")
    style = {
        **TABLE_HEADER_STYLE,
        "background": "#1e3a5f",
        "color": "#93c5fd",
        "fontWeight": 700,
        "fontSize": "8px",
        "borderBottom": f"2px solid {COLORS['accent']}",
    }
    if url:
        content = html.A(
            label,
            href=url,
            target="_blank",
            rel="noopener noreferrer",
            style={"color": "#93c5fd", "textDecoration": "none", "cursor": "pointer"},
        )
    else:
        content = label
    return html.Th(content, colSpan=3, style=style)


def build_key_metrics_table(metrics: dict) -> html.Table:
    # (display_label, url_key for FinViz link)
    group_config = [
        ("NQ100", "NQ100"),
        ("SPY500", "SPY500"),
        ("DJIA", "DJIA"),
        ("RUS2000", "RUS2000"),
        ("$1B+ Universe", "$1B+"),
    ]
    sub_headers = ["Above", "Below", "Pct"]

    header_row1 = [html.Th("Metric", style={
        **TABLE_HEADER_STYLE, "textAlign": "left", "width": "120px",
    })]
    for label, url_key in group_config:
        header_row1.append(_screener_link(label, url_key))

    header_row2 = [html.Th("", style=TABLE_HEADER_STYLE)]
    for _ in range(5):
        for sh in sub_headers:
            header_row2.append(html.Th(sh, style=TABLE_HEADER_STYLE))

    body_rows = []
    groups_ordered = ["NQ100", "SPY500", "DJIA", "RUS2000", "$1B+"]
    for i, label in enumerate(KEY_METRIC_ROWS):
        cells = [html.Td(label, style={
            **TABLE_CELL_STYLE,
            "textAlign": "left",
            "fontWeight": 500,
            "color": COLORS["text_muted"],
            "fontSize": "8px",
            "paddingLeft": "4px",
            "backgroundColor": COLORS["surface"],
        })]
        for gname in groups_ordered:
            group_rows = metrics.get(gname, [])
            if i < len(group_rows):
                r = group_rows[i]
                above = r["above"]
                below = r["below"]
                pct = r["pct"]

                is_info_row = label == "Stocks"
                if is_info_row:
                    st = {**TABLE_CELL_STYLE, "backgroundColor": COLORS["surface"],
                          "color": COLORS["text_muted"]}
                    cells.append(html.Td(
                        str(above) if above is not None else "—", style=st))
                    cells.append(html.Td(
                        str(below) if below is not None else "—", style=st))
                    cells.append(html.Td(
                        f"{pct}%" if pct is not None else "—", style=st))
                else:
                    bg, fg = pct_color(pct)
                    cell_st = {**TABLE_CELL_STYLE,
                               "backgroundColor": bg, "color": fg}
                    # Make Above/Below cells clickable when we have a metric filter
                    above_url = build_metric_screener_url(gname, label, "above")
                    below_url = build_metric_screener_url(gname, label, "below")
                    above_content = str(above) if above is not None else "—"
                    below_content = str(below) if below is not None else "—"
                    link_style = {**cell_st, "textDecoration": "none", "display": "block"}
                    above_cell = (
                        html.Td(html.A(above_content, href=above_url, target="_blank",
                                       rel="noopener noreferrer", style=link_style), style=cell_st)
                        if above_url else html.Td(above_content, style=cell_st)
                    )
                    below_cell = (
                        html.Td(html.A(below_content, href=below_url, target="_blank",
                                       rel="noopener noreferrer", style=link_style), style=cell_st)
                        if below_url else html.Td(below_content, style=cell_st)
                    )
                    cells.append(above_cell)
                    cells.append(below_cell)
                    cells.append(html.Td(
                        f"{pct}%" if pct is not None else "—", style=cell_st))
            else:
                for _ in range(3):
                    cells.append(html.Td("—", style=TABLE_CELL_STYLE))
        body_rows.append(html.Tr(cells))

    # colgroup ensures narrow data columns (Above/Below/Pct)
    cols = [html.Col(style={"width": "120px"})]  # Metric
    for _ in range(15):
        cols.append(html.Col(style={"width": "38px"}))  # 5 groups × 3 cols
    return html.Table(
        [
            html.Colgroup(cols),
            html.Thead([html.Tr(header_row1), html.Tr(header_row2)]),
            html.Tbody(body_rows),
        ],
        style={**TABLE_STYLE, "tableLayout": "fixed", "width": "max-content"},
    )


# -----------------------------------------------------------------------
# Sections 2-3: Stacked bar charts (Key Metrics pct visualization)
# -----------------------------------------------------------------------

def build_metrics_bar_chart(groups: list[tuple]) -> go.Figure:
    """Build horizontal stacked bar chart from Key Metrics data.

    groups: list of (data_list, label, color_down, color_up) tuples.
    data_list: list of dicts with 'above' and 'below' keys (from Key Metrics).
    Uses actual counts, not percentages.
    """
    labels = KEY_METRIC_ROWS[:-2]  # Exclude "New 20-Day Lows", "Stocks"

    n = len(groups)
    if n == 0:
        return go.Figure()

    # Bar width and offsets: 2 groups -> width 0.35, offsets -0.18, 0.18
    # 3 groups -> width 0.25, offsets -0.25, 0, 0.25
    width = 0.25 if n == 3 else 0.35
    offsets = ([-0.25, 0, 0.25] if n == 3 else [-0.18, 0.18])[:n]

    max_extent = 0
    fig = go.Figure()
    for i, (data_rows, label, color_down, color_up) in enumerate(groups):
        aboves_left = []
        belows_right = []
        for d in data_rows[:len(labels)]:
            above = d.get("above")
            below = d.get("below")
            a = int(above) if above is not None else 0
            b = int(below) if below is not None else 0
            aboves_left.append(-a)   # Left side: Above (negative x)
            belows_right.append(b)   # Right side: Below (positive x)
            max_extent = max(max_extent, a, b)
        off = offsets[i]
        fig.add_trace(go.Bar(
            y=labels, x=aboves_left, orientation="h", name=f"{label} Above",
            marker_color=color_up, width=width, offset=off,
        ))
        fig.add_trace(go.Bar(
            y=labels, x=belows_right, orientation="h", name=f"{label} Below",
            marker_color=color_down, width=width, offset=off,
        ))

    x_range = max(max_extent * 1.1, 50)
    fig.update_layout(
        autosize=True,
        barmode="relative",
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=2, r=4, t=2, b=2),
        showlegend=False,
        xaxis=dict(
            range=[-x_range, x_range],
            showticklabels=True,
            tickfont=dict(size=8, color=COLORS["text_muted"]),
            showgrid=True,
            gridcolor="rgba(255,255,255,0.05)",
            zeroline=True,
            zerolinecolor="rgba(255,255,255,0.15)",
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=7, color=COLORS["text_muted"]),
            showgrid=False,
        ),
        font=dict(family="Inter", size=8),
        height=SCROLLABLE_BODY_HEIGHT,
    )
    return fig


# -----------------------------------------------------------------------
# Sections 4-7: Ticker grids (clickable)
# -----------------------------------------------------------------------

def build_ticker_grid(tickers: list[dict]) -> html.Div:
    pills = []
    for t in tickers:
        color = t.get("color", "green")
        pill_st = ticker_pill_style(color)
        pill_st["cursor"] = "pointer"
        pills.append(html.Span(
            t["ticker"],
            className="tv-ticker",
            style=pill_st,
        ))
    if not pills:
        pills = [html.Span("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "4px",
        })]
    return html.Div(pills, style=TICKER_GRID_STYLE)


def _build_screener_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Shared table for screener data: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %."""
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, SCREENER_SORT_KEYS)
    headers = [
        ("Ticker", "ticker"), ("Price", "price"), ("Avg Vol", "avg_vol"), ("Rel Vol", "rel_vol"),
        ("Change", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"),
    ]
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        atr_pct = r.get("atr_pct")
        atr_str = f"{atr_pct:.2f}%" if atr_pct is not None else ""
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            atr_str,
        ])
    return _table(headers, rows, col_widths=["70px", "55px", "65px", "55px", "55px", "65px", "55px"],
                  widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


def build_minervini_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Minervini screener: Ticker, Price, Avg Vol, Rel Vol, Change, Vol."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id, sort_col, sort_asc)


def build_earnings_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Earnings Yesterday + Today: screener columns + Earnings Date (rightmost)."""
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, SCREENER_SORT_KEYS)
    headers = [
        ("Ticker", "ticker"), ("Price", "price"), ("Avg Vol", "avg_vol"), ("Rel Vol", "rel_vol"),
        ("Change", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"),
        ("Earnings Date", "earnings_date"),
    ]
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        atr_pct = r.get("atr_pct")
        atr_str = f"{atr_pct:.2f}%" if atr_pct is not None else ""
        ed = _coerce_earnings_date_str(r.get("earnings_date")) or ""
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            atr_str,
            ed,
        ])
    return _table(
        headers,
        rows,
        col_widths=["62px", "55px", "65px", "55px", "55px", "65px", "50px", "82px"],
        widget_id=widget_id,
        sort_col=sort_col,
        sort_asc=sort_asc,
    )


def _fmt_mcap(val) -> str:
    """Format market cap for display."""
    if val is None or (isinstance(val, float) and (val != val or val == 0)):
        return "-"
    if val >= 1e12:
        return f"${val/1e12:.2f}T"
    if val >= 1e9:
        return f"${val/1e9:.2f}B"
    if val >= 1e6:
        return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"


def build_earnings_calendar_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Earnings This Week: Ticker, Mkt Cap, …, ATR %, Earnings Date (rightmost). Sorted by market cap by default."""
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if not data:
        return html.Div("No earnings this week", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    sort_keys = {**SCREENER_SORT_KEYS}
    if widget_id and sort_col and sort_col in sort_keys:
        data = sort_data(data, sort_col, sort_asc, sort_keys)
    elif not sort_col:
        data = sort_data(data, "market_cap", False, sort_keys)
    headers = [
        ("Ticker", "ticker"), ("Mkt Cap", "market_cap"), ("Price", "price"), ("Avg Vol", "avg_vol"), ("Rel Vol", "rel_vol"),
        ("Change", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"),
        ("Earnings Date", "earnings_date"),
    ]
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        atr_pct = r.get("atr_pct")
        atr_str = f"{atr_pct:.2f}%" if atr_pct is not None else ""
        ed = _coerce_earnings_date_str(r.get("earnings_date")) or ""
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}), "style": TABLE_CELL_STYLE},
            _fmt_mcap(r.get("market_cap")),
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "", "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            atr_str,
            ed,
        ])
    return _table(
        headers,
        rows,
        col_widths=["65px", "60px", "55px", "65px", "50px", "55px", "65px", "50px", "82px"],
        widget_id=widget_id,
        sort_col=sort_col or "market_cap",
        sort_asc=sort_asc,
    )


def build_pre_market_scanner_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Pre-market Scanner: USA, avg vol 1K+, price $1+, rel vol 1+, up 3% and down 3%."""
    if not data:
        return html.Div("No results. Set FINVIZ_API_KEY in .env for FinViz Elite.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    from src.sortable_table import sort_data_pre_market

    skip_cols = frozenset({"No.", "No", "#", "Rank", "Analyst Recom", "Analyst Recommendation"})
    seen_ticker = False
    cols = []
    for k in data[0].keys():
        if not k or not str(k).strip() or str(k).strip() in skip_cols:
            continue
        if "analyst" in k.lower() or "recom" in k.lower():
            continue
        if "performance" in k.lower():
            continue
        if "ticker" in k.lower():
            if seen_ticker:
                continue
            seen_ticker = True
        cols.append(k)
    # Skip Change column (redundant with Gap in pre-market); move News URL to last
    cols = [c for c in cols if not ("change" in c.lower() and "url" not in c.lower())]
    news_url_cols = [c for c in cols if "news" in c.lower() and "url" in c.lower()]
    other_cols = [c for c in cols if c not in news_url_cols]
    cols = other_cols + news_url_cols
    if not cols:
        return html.Div("No columns", style={"color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px"})

    if widget_id and sort_col and sort_col in cols:
        data = sort_data_pre_market(data, sort_col, sort_asc)
    elif not sort_col and cols:
        gap_col = next((c for c in cols if "gap" in c.lower() and "url" not in c.lower()), None)
        if gap_col:
            data = sort_data_pre_market(data, gap_col, False)

    # Column widths: News Title gets more space; others stay compact
    def _col_width(col_name: str) -> str:
        c = (col_name or "").lower()
        if "news" in c and "title" in c:
            return "380px"
        if "daily" in c and "digest" in c:
            return "380px"
        if "ticker" in c:
            return "70px"
        if "gap" in c and "url" not in c:
            return "55px"
        if "price" in c:
            return "55px"
        if "relative" in c or "rel" in c:
            return "60px"
        if "news" in c and "url" in c:
            return "50px"
        return "65px"  # avg vol, etc.
    col_widths = [_col_width(c) for c in cols]

    headers = [(c, c) for c in cols]
    rows = []
    for r in data:
        row_cells = []
        for col in cols:
            val = r.get(col)
            if col and "ticker" in col.lower():
                cell = {"text": _clickable_ticker(r.get("ticker", r.get(col, "") or ""), {"fontWeight": 700}),
                        "style": TABLE_CELL_STYLE}
            elif "gap" in col.lower() and "url" not in col.lower():
                try:
                    chg_num = float(str(val or "0").replace("%", "").replace(",", "")) if val not in (None, "") else 0
                except (ValueError, TypeError):
                    chg_num = 0
                cell = {"text": str(val) if val not in (None, "") else "",
                        "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}}
            elif col and (("average" in col.lower() and "volume" in col.lower()) or ("avg" in col.lower() and "vol" in col.lower())):
                _, avg_str = _format_screener_vol(None, val)
                cell = (avg_str or str(val)) if val not in (None, "") else ""
            elif col and "news" in col.lower() and "url" in col.lower() and val:
                url = str(val).strip()
                if url.startswith("/"):
                    url = "https://finviz.com" + url
                if url.startswith(("http://", "https://")):
                    cell = {"text": html.A("Open", href=url, target="_blank", rel="noopener noreferrer",
                                          style={"color": COLORS["accent"], "textDecoration": "underline", "fontSize": "9px"}),
                            "style": TABLE_CELL_STYLE}
                else:
                    cell = str(val)
            elif col and (("news" in col.lower() and "title" in col.lower()) or "daily digest" in col.lower()):
                text = str(val) if val not in (None, "") else ""
                cell = {"text": text,
                        "style": {**TABLE_CELL_STYLE, "fontSize": "12px", "lineHeight": "1.45",
                                  "whiteSpace": "normal", "overflow": "visible",
                                  "textOverflow": "unset", "wordWrap": "break-word", "textAlign": "left",
                                  "minWidth": "360px", "maxWidth": "none"}}
            else:
                cell = str(val) if val not in (None, "") else ""
            row_cells.append(cell)
        rows.append(row_cells)
    return _table(headers, rows, col_widths=col_widths, widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


def build_stocks_in_play_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Stocks In Play: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %, News (rightmost). Sorted by change desc."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, SCREENER_SORT_KEYS)
    has_news = any(r.get("news") or r.get("news_url") for r in data)
    if has_news:
        headers = [
            ("Ticker", "ticker"), ("Price", "price"), ("Avg Vol", "avg_vol"), ("Rel Vol", "rel_vol"),
            ("Change", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"), ("News", "news"),
        ]
        col_widths = ["70px", "55px", "65px", "55px", "55px", "65px", "55px", "45px"]
    else:
        headers = [
            ("Ticker", "ticker"), ("Price", "price"), ("Avg Vol", "avg_vol"), ("Rel Vol", "rel_vol"),
            ("Change", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"),
        ]
        col_widths = ["70px", "55px", "65px", "55px", "55px", "65px", "55px"]
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        atr_pct = r.get("atr_pct")
        atr_str = f"{atr_pct:.2f}%" if atr_pct is not None else ""
        row_cells = [
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            atr_str,
        ]
        if has_news:
            news_url = r.get("news_url")
            if news_url:
                row_cells.append({
                    "text": html.A("News", href=news_url, target="_blank", rel="noopener noreferrer",
                                  style={"color": COLORS["accent"], "textDecoration": "underline", "fontSize": "9px"}),
                    "style": TABLE_CELL_STYLE,
                })
            else:
                row_cells.append(str(r.get("news", "")))
        rows.append(row_cells)
    return _table(headers, rows, col_widths=col_widths,
                  widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


def build_cnbc_premarket_watchlist_table(data: list[dict], article_url: str = "") -> html.Div:
    """CNBC Pre-Market Watchlist: Ticker, News from latest CNBC Market Insider premarket report."""
    if not data:
        return html.Div("No premarket data. Check CNBC Market Insider.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    headers = [("Ticker", None), ("News", None), ("", None)]
    rows = []
    for r in data:
        url = r.get("url", article_url)
        link_cell = ""
        if url:
            link_cell = {"text": html.A("Article", href=url, target="_blank", rel="noopener noreferrer",
                                       style={"color": COLORS["accent"], "textDecoration": "underline", "fontSize": "9px"}),
                        "style": TABLE_CELL_STYLE}
        rows.append([
            {"text": _clickable_ticker(r.get("ticker", ""), {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            {"text": r.get("news", ""),
             "style": {**TABLE_CELL_STYLE, "fontSize": "12px", "lineHeight": "1.45",
                       "whiteSpace": "normal", "wordWrap": "break-word", "textAlign": "left",
                       "minWidth": "320px", "maxWidth": "none"}},
            link_cell or "",
        ])
    col_widths = ["70px", "1fr", "50px"]
    def _cell(content):
        if isinstance(content, dict):
            return html.Td(content.get("text", ""), style=content.get("style", TABLE_CELL_STYLE))
        return html.Td(content, style=TABLE_CELL_STYLE)

    table = html.Table(
        [html.Thead(html.Tr([html.Th(h[0], style=TABLE_HEADER_STYLE) for h in headers])),
         html.Tbody([html.Tr([_cell(c) for c in row]) for row in rows])],
        style={**TABLE_STYLE, "tableLayout": "fixed"},
    )
    article_date = data[0].get("article_date", "") if data else ""
    if not article_date and data:
        import re
        url = data[0].get("url", "")
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
        if m:
            from datetime import datetime
            try:
                dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                article_date = dt.strftime("%b %d, %Y")
            except (ValueError, TypeError):
                article_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    date_label = html.Span(article_date, style={"fontSize": "10px", "color": COLORS["text_muted"], "marginBottom": "4px"}) if article_date else html.Div()
    return html.Div([
        html.Div([date_label], style={"marginBottom": "4px"}) if article_date else html.Div(),
        table,
    ], style={"display": "flex", "flexDirection": "column"})


def build_top_gainers_table(data: list[dict]) -> html.Div:
    """Top gainers on the day — from thematics universe (same data as Thematics Tracker)."""
    if not data:
        return html.Div("No data. Set FINVIZ_API_KEY in .env for FinViz Elite.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    cell = {**TABLE_CELL_STYLE, "padding": "0px 3px 1px 3px", "lineHeight": 1.25}
    headers = [("Ticker", None), ("Chg", None)]
    rows = []
    for r in data:
        chg = r.get("change", 0)
        try:
            chg_num = float(chg) if chg is not None else 0
        except (ValueError, TypeError):
            chg_num = 0
        rows.append([
            {"text": _clickable_ticker(r.get("ticker", ""), {"fontWeight": 700}),
             "style": cell},
            {"text": f"{chg_num:+.2f}%",
             "style": {**cell, "color": chg_color(chg_num), "fontWeight": 600}},
        ])
    return _table(headers, rows, col_widths=["70px", "55px"])


def build_top_losers_table(data: list[dict]) -> html.Div:
    """Top losers on the day — from thematics universe (same data as Thematics Tracker)."""
    if not data:
        return html.Div("No data. Set FINVIZ_API_KEY in .env for FinViz Elite.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    cell = {**TABLE_CELL_STYLE, "padding": "0px 3px 1px 3px", "lineHeight": 1.25}
    headers = [("Ticker", None), ("Chg", None)]
    rows = []
    for r in data:
        chg = r.get("change", 0)
        try:
            chg_num = float(chg) if chg is not None else 0
        except (ValueError, TypeError):
            chg_num = 0
        rows.append([
            {"text": _clickable_ticker(r.get("ticker", ""), {"fontWeight": 700}),
             "style": cell},
            {"text": f"{chg_num:+.2f}%",
             "style": {**cell, "color": chg_color(chg_num), "fontWeight": 600}},
        ])
    return _table(headers, rows, col_widths=["70px", "55px"])


def _parse_vol(val):
    """Parse volume string (e.g. '48.29M', '28,578,735') to float. Handles K/M/B suffixes."""
    if val is None or val == "":
        return 0
    import re
    s = str(val).strip().replace(",", "").replace("$", "").replace("%", "")
    if not s or s == "-":
        return 0
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
        return 0


def _format_screener_vol(vol_raw, avg_raw):
    """Format volume and avg vol for screener tables (FinViz avg_vol often in thousands)."""
    vol_num = _parse_vol(vol_raw)
    avg_num = _parse_vol(avg_raw)
    vol_str = f"{vol_num/1e6:.2f}M" if vol_num >= 1e6 else f"{vol_num/1e3:.1f}K" if vol_num >= 1e3 else str(int(vol_num)) if vol_num else ""
    avg_adj = avg_num * 1000 if (avg_num and avg_num < 50000) else avg_num
    avg_str = f"{avg_adj/1e6:.2f}M" if avg_adj and avg_adj >= 1e6 else f"{avg_adj/1e3:.1f}K" if avg_adj and avg_adj >= 1e3 else str(int(avg_adj)) if avg_adj else ""
    return vol_str, avg_str


def _tag_badge(tag: str) -> html.Span:
    """Style tag: PS = red background, EP = green background."""
    tag = (tag or "").strip()
    if not tag:
        return html.Span("")
    if tag == "PS":
        style = {"backgroundColor": COLORS["red_cell"], "color": COLORS["red_light"],
                 "padding": "1px 4px", "borderRadius": "2px", "fontSize": "8px", "fontWeight": 600}
    elif tag == "EP":
        style = {"backgroundColor": COLORS["green_cell"], "color": COLORS["green_light"],
                 "padding": "1px 4px", "borderRadius": "2px", "fontSize": "8px", "fontWeight": 600}
    else:
        style = {"fontSize": "8px"}
    return html.Span(tag, style=style)


def build_qullamaggie_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Qullamaggie: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %, Tag."""
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, SCREENER_SORT_KEYS)
    headers = [
        ("Ticker", "ticker"), ("Price", "price"), ("Avg Vol", "avg_vol"), ("Rel Vol", "rel_vol"),
        ("Change", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"), ("Tag", "tag"),
    ]
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        tag_raw = r.get("tag", "")
        # Tag can be "EP", "PS", "EP, PS", etc. — render each with its color
        tag_parts = [p.strip() for p in str(tag_raw).split(",") if p.strip()]
        tag_content = html.Span([
            _tag_badge(t) for t in tag_parts
        ], style={"display": "flex", "gap": "4px", "flexWrap": "wrap"}) if tag_parts else html.Span("")
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            f"{r.get('atr_pct', 0):.2f}%" if r.get("atr_pct") is not None else "",
            {"text": tag_content, "style": TABLE_CELL_STYLE},
        ])
    return _table(headers, rows, col_widths=["70px", "55px", "65px", "55px", "55px", "65px", "55px", "55px"],
                  widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


def build_watchlist_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True, show_remove: bool = True) -> html.Table:
    """Watchlist: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %, Remove (optional)."""
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if not data:
        return html.Div("No tickers in watchlist. Add some above.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, SCREENER_SORT_KEYS)
    headers = [
        ("Ticker", "ticker"), ("Price", "price"), ("Avg Vol", "avg_vol"), ("Rel Vol", "rel_vol"),
        ("Change", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"),
    ]
    if show_remove:
        headers.append(("", None))
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        t = r["ticker"]
        row_cells = [
            {"text": _clickable_ticker(t, {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            f"{r.get('atr_pct', 0):.2f}%" if r.get("atr_pct") is not None else "",
        ]
        if show_remove:
            remove_btn = html.Button(
                "×",
                id={"type": "wl-remove", "ticker": t},
                n_clicks=0,
                style={
                    "background": "transparent",
                    "border": "none",
                    "color": COLORS["red_light"],
                    "cursor": "pointer",
                    "fontSize": "12px",
                    "fontWeight": 700,
                    "padding": "0 4px",
                    "lineHeight": 1,
                },
            )
            row_cells.append({"text": remove_btn, "style": {**TABLE_CELL_STYLE, "width": "24px", "padding": "2px"}})
        rows.append(row_cells)
    col_widths = ["70px", "55px", "65px", "55px", "55px", "65px", "55px"]
    if show_remove:
        col_widths.append("28px")
    return _table(
        headers,
        rows,
        col_widths=col_widths,
        widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc,
    )


def build_oneil_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """O'Neil / CANSLIM screener: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %, ROE, Net Margin."""
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, SCREENER_SORT_KEYS)
    headers = [
        ("Ticker", "ticker"), ("Price", "price"), ("Avg Vol", "avg_vol"), ("Rel Vol", "rel_vol"),
        ("Change", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"), ("ROE", "roe"), ("Net Margin", "net_margin"),
    ]
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        roe_val = r.get("roe")
        margin_val = r.get("net_margin")
        roe_str = f"{roe_val:.1f}%" if roe_val is not None else ""
        margin_str = f"{margin_val:.1f}%" if margin_val is not None else ""
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            f"{r.get('atr_pct', 0):.2f}%" if r.get("atr_pct") is not None else "",
            roe_str,
            margin_str,
        ])
    return _table(
        headers,
        rows,
        col_widths=["70px", "55px", "65px", "55px", "55px", "65px", "55px", "55px", "65px"],
        widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc,
    )


# -----------------------------------------------------------------------
# Section 8: Sector SPDR table (clickable tickers)
# -----------------------------------------------------------------------

def build_sector_table(sector_data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    from src.sortable_table import sort_data, SECTOR_SORT_KEYS

    if widget_id and sort_col:
        sector_data = sort_data(sector_data, sort_col, sort_asc, SECTOR_SORT_KEYS)
    headers = [
        ("Sector", "sector"), ("Ticker", "ticker"), ("Gap", "gap"), ("Chg", "chg"), ("O Chg", "ochg"),
        ("Week", "week"), ("Month", "month"), ("Qtr", "qtr"), ("H.Year", "hyear"), ("Year", "year"),
        ("Last", None), ("EMA10", None), ("SMA20", None), ("SMA50", None),
        ("SMA200", None), ("52W Hi", None), ("52W Lo", None), ("ATR %", None),
    ]
    rows = []
    for r in sector_data:
        chg_val = r.get("chg", 0)
        name = SECTOR_NAMES.get(r["ticker"], r["ticker"])

        def _chg_cell(val, suffix="%"):
            v = val
            if v is None or (isinstance(v, float) and v != v):  # v != v catches NaN
                v = 0
            color = chg_color(v)
            return {"text": f"{v}{suffix}", "style": {"color": color}}

        atr_pct = r.get("atr_pct")
        atr_str = f"{atr_pct:.2f}%" if atr_pct is not None else ""

        row = [
            {"text": name, "style": {
                "textAlign": "left", "fontWeight": 600,
                "color": chg_color(chg_val),
            }},
            {"text": _clickable_ticker(r["ticker"], {
                "fontWeight": 700, "color": "#60a5fa",
            }), "style": TABLE_CELL_STYLE},
            _chg_cell(r.get("gap")),
            _chg_cell(r.get("chg")),
            _chg_cell(r.get("ochg")),
            _chg_cell(r.get("week")),
            _chg_cell(r.get("month")),
            _chg_cell(r.get("qtr")),
            _chg_cell(r.get("hyear")),
            _chg_cell(r.get("year")),
            str(r.get("last", "")),
            str(r.get("ema10", "")),
            str(r.get("sma20", "")),
            str(r.get("sma50", "")),
            str(r.get("sma200", "")),
            str(r.get("high_52w", "")),
            str(r.get("low_52w", "")),
            atr_str,
        ]
        rows.append(row)

    return _table(headers, rows, widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


# -----------------------------------------------------------------------
# Section 8b: Thematics by Sector (Sector SPDR-style, top YTD)
# -----------------------------------------------------------------------

def build_thematics_sector_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Thematics aggregated by theme: Theme, Week, Month, Qtr, H.Year, YTD. Top YTD. No Chg/O Chg."""
    from src.sortable_table import sort_data, THEMATICS_SECTOR_SORT_KEYS

    if not data:
        return html.Div("No thematics data. Set FINVIZ_API_KEY in .env for FinViz Elite.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })

    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, THEMATICS_SECTOR_SORT_KEYS)
    headers = [
        ("Theme", "theme"),
        ("Week", "week"), ("Month", "month"), ("Qtr", "qtr"), ("H.Year", "hyear"), ("YTD", "year"),
    ]
    rows = []
    for r in data:
        def _pct_cell(val, suffix="%"):
            v = val
            if v is None or (isinstance(v, float) and v != v):
                v = 0
            color = chg_color(v)
            return {"text": f"{v}{suffix}", "style": {"color": color}}

        row = [
            {"text": r.get("theme", ""), "style": {"textAlign": "left", "fontWeight": 600, "color": COLORS["text"]}},
            _pct_cell(r.get("week")),
            _pct_cell(r.get("month")),
            _pct_cell(r.get("qtr")),
            _pct_cell(r.get("hyear")),
            _pct_cell(r.get("year")),
        ]
        rows.append(row)

    return _table(headers, rows, widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


# -----------------------------------------------------------------------
# Section 9: 97 Club table (clickable tickers)
# -----------------------------------------------------------------------

def build_97_club_table(club_data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """97 Club: same layout as Minervini (Ticker, Price, Avg Vol, Rel Vol, Change, Vol) from export URL."""
    if not club_data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(club_data, widget_id, sort_col, sort_asc)


def build_jeff_sun_canslim_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun CANSLIM: same layout as Minervini (Ticker, Price, Avg Vol, Rel Vol, Change, Vol) from export URL."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id, sort_col, sort_asc)


def build_jeff_sun_high_adr_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun High ADR% Hottest Stock: same layout as Minervini (Ticker, Price, Avg Vol, Rel Vol, Change, Vol)."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id, sort_col, sort_asc)


def build_jeff_sun_extended_bases_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun Extended Bases/Prolonged Consolidations: same layout as Minervini."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id, sort_col, sort_asc)


def build_jeff_sun_1w20_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun Strongest 1-Week Mover Exceeding 20%: same layout as Minervini."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "jeff_sun_1w20", sort_col, sort_asc)


def build_jeff_sun_4w30_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun Strongest 1-Month Mover Exceeding 30%: same layout as Minervini."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "jeff_sun_4w30", sort_col, sort_asc)


def build_jeff_sun_4w50_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun Strongest 1-Month Mover Exceeding 50%: same layout as Minervini."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "jeff_sun_4w50", sort_col, sort_asc)


def build_jeff_sun_13w50_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun Strongest 3-Month Mover Exceeding 50%: same layout as Minervini."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "jeff_sun_13w50", sort_col, sort_asc)


def build_jeff_sun_26w100_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun Strongest 6-Month Mover Exceeding 100%: same layout as Minervini."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "jeff_sun_26w100", sort_col, sort_asc)


def build_jeff_sun_ipo_thisweek_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun IPO: mid+ cap, EPS growth, USA, IPO previous year. Cached weekly."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "jeff_sun_ipo_thisweek", sort_col, sort_asc)


def build_jeff_sun_high_short_float_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun High Short Float: small+ cap, float <100M, short >30%. Cached weekly."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "jeff_sun_high_short_float", sort_col, sort_asc)


def build_jeff_sun_liquid_etfs_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Jeff Sun Liquid ETFs: ETFs, high volume, week volatility."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "jeff_sun_liquid_etfs", sort_col, sort_asc)


def build_julian_komar_strongest_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Julian Komar Strongest Stocks: 52w high proximity, SMA50, liquid small+ names."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id or "julian_komar_strongest", sort_col, sort_asc)


# -----------------------------------------------------------------------
# Sections 10-12: Stockbee tables (clickable tickers)
# -----------------------------------------------------------------------

def build_9m_movers_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """9M Movers: same layout as Minervini (Ticker, Price, Avg Vol, Rel Vol, Change, Vol) from export URL."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data, widget_id, sort_col, sort_asc)


def build_20pct_weekly_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """20% Weekly Movers: Ticker, Week %, Price, Avg Vol, Rel Vol, Chg, Vol, ATR %."""
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, SCREENER_SORT_KEYS)
    headers = [
        ("Ticker", "ticker"), ("Week", "week"), ("Price", "price"), ("Avg Vol", "avg_vol"),
        ("Rel Vol", "rel_vol"), ("Chg", "change"), ("Vol", "volume"), ("ATR %", "atr_pct"),
    ]
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            {"text": f"{r.get('week', 0)}%",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(r.get("week", 0)),
                        "fontWeight": 600}},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            f"{r.get('atr_pct'):.2f}%" if r.get("atr_pct") is not None else "",
        ])
    return _table(headers, rows, col_widths=["70px", "55px", "55px", "65px", "55px", "55px", "65px", "55px"],
                  widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


def build_4pct_daily_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """4% Daily Gainers: Ticker, Chg, Price, Avg Vol, Rel Vol, Vol, ATR %."""
    from src.sortable_table import sort_data, SCREENER_SORT_KEYS

    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, SCREENER_SORT_KEYS)
    headers = [
        ("Ticker", "ticker"), ("Chg", "chg"), ("Price", "price"), ("Avg Vol", "avg_vol"),
        ("Rel Vol", "rel_vol"), ("Vol", "volume"), ("ATR %", "atr_pct"),
    ]
    rows = []
    for r in data:
        chg_val = r.get("chg") or r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        atr_pct = r.get("atr_pct")
        atr_str = f"{atr_pct:.2f}%" if atr_pct is not None else ""
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", r.get("min_rel_vol", ""))),
            vol_str,
            atr_str,
        ])
    return _table(headers, rows, col_widths=["70px", "55px", "55px", "65px", "55px", "65px", "55px"],
                  widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


# -----------------------------------------------------------------------
# Section 13: Leading Industries (clickable tickers)
# -----------------------------------------------------------------------

def build_leading_industries_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    from src.sortable_table import sort_data, LEADING_SORT_KEYS

    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, LEADING_SORT_KEYS)
    headers = [("Industry", None), ("1st", None), ("2nd", None), ("3rd", None), ("4th", None)]
    return _build_theme_industry_table(data, headers, "industry", widget_id, sort_col, sort_asc)


def build_thematics_table(data: list[dict], widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    """Thematics Tracker: Theme, top 4 stocks. Same layout as leading industries."""
    if not data:
        return html.Div([
            "No thematics data. ",
            html.Span("Set FINVIZ_API_KEY in .env for FinViz Elite.", style={"color": COLORS["text_muted"]}),
            " Other FinViz widgets working? Try Refresh.",
        ], style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    from src.sortable_table import sort_data, THEMATICS_SORT_KEYS

    if widget_id and sort_col:
        data = sort_data(data, sort_col, sort_asc, THEMATICS_SORT_KEYS)
    headers = [("Theme", None), ("1st", None), ("2nd", None), ("3rd", None), ("4th", None)]
    return _build_theme_industry_table(data, headers, "theme", widget_id, sort_col, sort_asc)


def _build_theme_industry_table(data: list[dict], headers: list, name_key: str, widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Table:
    rows = []
    for r in data:
        ind_color = COLORS["green_light"] if r.get("top_both") else COLORS["text_muted"]
        row_bg = "rgba(34,197,94,0.08)" if r.get("top_both") else "transparent"
        row = [
            {"text": r.get(name_key, ""), "style": {
                **TABLE_CELL_STYLE, "textAlign": "left",
                "fontWeight": 500, "color": ind_color, "fontSize": "8px",
                "backgroundColor": row_bg,
            }},
        ]
        for key in ["t1", "t2", "t3", "t4"]:
            val = r.get(key, "—")
            if val and val != "—":
                cell_content = _clickable_ticker(val, {
                    "fontWeight": 700, "fontSize": "9px",
                })
            else:
                cell_content = "—"
            row.append({"text": cell_content, "style": {
                **TABLE_CELL_STYLE, "fontWeight": 700, "fontSize": "9px",
                "backgroundColor": row_bg,
            }})
        rows.append(row)
    return _table(headers, rows, col_widths=["200px", None, None, None, None],
                  widget_id=widget_id, sort_col=sort_col, sort_asc=sort_asc)


# -----------------------------------------------------------------------
# Stockbee Momentum50 (Pradeep Bonde)
# -----------------------------------------------------------------------

def build_stockbee_momentum50_table(data: list[dict], date_label: str = "", widget_id: str = None, sort_col: str = None, sort_asc: bool = True) -> html.Div:
    """Stockbee Momentum50: default = spreadsheet order; user can sort by any column via header click."""
    if not data:
        return html.Div("No Momentum50 data. Check Stockbee sheet.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    table = _build_screener_table(data, widget_id, sort_col, sort_asc)
    children = [table]
    if date_label:
        children.insert(0, html.Span(date_label, style={"fontSize": "9px", "color": COLORS["text_muted"], "marginBottom": "4px"}))
    return html.Div(children, style={"display": "flex", "flexDirection": "column", "gap": "4px"})


# -----------------------------------------------------------------------
# Stock Market Breadth Monitor
# -----------------------------------------------------------------------

def _breadth_chart_layout(dates: list | None = None):
    """Shared layout for breadth charts. Fixed height to avoid zoom on tab switch.
    If dates provided, x-axis shows full range (oldest left, newest right) so user sees all data by default.
    autosize=True so chart fits widget width (no horizontal overflow)."""
    xaxis = dict(
        tickfont=dict(size=8, color=COLORS["text_muted"]),
        showgrid=True, gridcolor="rgba(255,255,255,0.05)",
    )
    if dates:
        n = len(dates)
        xaxis["range"] = [-0.5, n - 0.5]
        xaxis["autorange"] = False
    return dict(
        autosize=True,
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=4, r=4, t=4, b=4),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=8)),
        xaxis=xaxis,
        yaxis=dict(
            tickfont=dict(size=8, color=COLORS["text_muted"]),
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
        ),
        font=dict(family="Inter", size=8),
        height=200,
    )


def build_primary_breadth_chart(history: list[dict]) -> go.Figure:
    """Primary Breadth — Stocks Up/Down 4%+ Today (last 60 days)."""
    if not history:
        return go.Figure()
    dates = [h["date"] for h in history]
    up4 = [h.get("up4", 0) for h in history]
    down4 = [h.get("down4", 0) for h in history]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=up4, name="Up 4%+", fill="tozeroy",
        line=dict(color=COLORS["green_light"], width=1.5),
        fillcolor=_hex_to_rgba(COLORS["green"], 0.3)))
    fig.add_trace(go.Scatter(x=dates, y=down4, name="Down 4%+", fill="tozeroy",
        line=dict(color=COLORS["red_light"], width=1.5),
        fillcolor=_hex_to_rgba(COLORS["red"], 0.3)))
    fig.update_layout(**_breadth_chart_layout(dates))
    return fig


def build_breadth_ratios_chart(history: list[dict]) -> go.Figure:
    """Breadth Ratios — 5-Day & 10-Day (with 1.0 reference)."""
    if not history:
        return go.Figure()
    dates = [h["date"] for h in history]
    r5 = [h.get("ratio5", 1) for h in history]
    r10 = [h.get("ratio10", 1) for h in history]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=r5, name="5-Day Ratio", line=dict(color=COLORS["green_light"], width=2)))
    fig.add_trace(go.Scatter(x=dates, y=r10, name="10-Day Ratio", line=dict(color=COLORS["accent"], width=2)))
    fig.add_hline(y=1.0, line_dash="dot", line_color=COLORS["border_light"], opacity=0.8)
    fig.update_layout(**_breadth_chart_layout(dates))
    return fig


def build_secondary_breadth_chart(history: list[dict]) -> go.Figure:
    """Secondary Breadth — Up/Down 25%+ in Quarter (last 60 days)."""
    if not history:
        return go.Figure()
    dates = [h["date"] for h in history]
    up25 = [h.get("up25q", 0) for h in history]
    down25 = [h.get("down25q", 0) for h in history]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=up25, name="Up 25%+ Qtr", fill="tozeroy",
        line=dict(color=COLORS["green_light"], width=1.5),
        fillcolor=_hex_to_rgba(COLORS["green"], 0.3)))
    fig.add_trace(go.Scatter(x=dates, y=down25, name="Down 25%+ Qtr", fill="tozeroy",
        line=dict(color=COLORS["red_light"], width=1.5),
        fillcolor=_hex_to_rgba(COLORS["red"], 0.3)))
    fig.update_layout(**_breadth_chart_layout(dates))
    return fig


def build_sp500_chart(history: list[dict]) -> go.Figure:
    """S&P 500 — Last 60 Trading Days."""
    if not history:
        return go.Figure()
    dates = [h["date"] for h in history]
    sp500 = [h.get("sp500", 0) for h in history]
    valid = [v for v in sp500 if v and v > 0]
    y_min, y_max = None, None
    if valid:
        low = min(valid)
        high = max(valid)
        y_min = math.floor(low / 1000) * 1000
        y_max = math.ceil(high / 1000) * 1000
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=sp500, name="S&P 500", fill="tozeroy",
        line=dict(color=COLORS["accent"], width=2),
        fillcolor=_hex_to_rgba(COLORS["accent"], 0.15)))
    layout = dict(**_breadth_chart_layout(dates))
    if y_min is not None and y_max is not None:
        layout["yaxis"] = dict(**layout.get("yaxis", {}), range=[y_min, y_max])
    fig.update_layout(**layout)
    return fig


def build_live_index_snapshot(data: list[dict]) -> html.Div:
    """Live QQQ, SPY, DIA, IWM, VIX snapshot for intraday traders."""
    if not data:
        return html.Div("Live data unavailable. Set FINVIZ_API_KEY in .env.", style={
            "color": COLORS["text_muted"], "fontSize": "10px", "padding": "8px",
        })

    muted = {"color": COLORS["text_muted"], "fontSize": "8px", "fontWeight": 500}

    def _card(r: dict) -> html.Div:
        ticker = r.get("ticker", "")
        price = r.get("price", "—")
        change = r.get("change", "")
        try:
            chg_val = float(str(change or "").replace("%", "").replace(",", "").strip()) if change else 0.0
        except (ValueError, TypeError):
            chg_val = 0.0
        color = chg_color(chg_val)
        o = (r.get("open") or "").strip()
        p = (r.get("prev_close") or "").strip()
        vol = (r.get("volume") or "").strip()
        sub: list = []
        if o or p:
            sub.append(html.Div([
                html.Span("O ", style=muted),
                html.Span(o or "—", style={"fontSize": "8px", "color": COLORS["text"]}),
                html.Span(" · P ", style=muted),
                html.Span(p or "—", style={"fontSize": "8px", "color": COLORS["text"]}),
            ], style={"lineHeight": 1.25}))
        if vol:
            sub.append(html.Div([
                html.Span("Vol ", style=muted),
                html.Span(vol, style={"fontSize": "8px", "color": COLORS["text"]}),
            ], style={"lineHeight": 1.25}))
        kids = [
            html.Div(_clickable_ticker(ticker, {"fontSize": "9px", "fontWeight": 600}),
                     style={"color": COLORS["text_muted"], "marginBottom": "2px"}),
            html.Div(price, style={"fontSize": "14px", "fontWeight": 700, "color": COLORS["text"], "lineHeight": 1.15}),
            html.Div(change or "—", style={"fontSize": "10px", "fontWeight": 600, "color": color, "marginTop": "1px"}),
        ]
        if sub:
            kids.append(html.Div(sub, style={"marginTop": "auto", "paddingTop": "4px", "display": "flex", "flexDirection": "column", "gap": "3px"}))
        return html.Div(kids, style={
            "padding": "6px 6px",
            "borderRadius": "4px",
            "background": COLORS["surface2"],
            "border": f"1px solid {COLORS['border']}",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "flex-start",
            "flex": 1,
            "minWidth": 0,
            "minHeight": 0,
            "height": "100%",
        })

    cards = [_card(r) for r in data if r.get("ticker")]
    return html.Div(cards, style={
        "display": "flex",
        "flexDirection": "row",
        "gap": "5px",
        "alignItems": "stretch",
        "flex": 1,
        "minHeight": 0,
        "height": "100%",
        "width": "100%",
    })


# -----------------------------------------------------------------------
# Should I Be Trading? — Bloomberg Terminal-style decision dashboard
# -----------------------------------------------------------------------

SIT_TAB_STYLE = {
    "backgroundColor": COLORS["surface2"],
    "color": COLORS["text_muted"],
    "border": f"1px solid {COLORS['border']}",
    "padding": "6px 16px",
    "fontSize": "11px",
    "fontWeight": 600,
}
SIT_TAB_SELECTED = {
    "backgroundColor": COLORS["surface"],
    "color": COLORS["accent"],
    "borderBottom": "none",
    "borderTop": f"2px solid {COLORS['accent']}",
}


def build_should_i_trade_tab() -> html.Div:
    """Build Should I Trade? tab content: top bar, hero, panels, heatmap, alerts, mode toggle."""
    loading = html.Div("Loading...", style={"color": COLORS["text_muted"], "padding": "24px"})
    return html.Div([
        # Top bar: mode toggle, status, last updated, refresh
        html.Div([
            html.Div([
                html.Span("Mode: ", style={"fontSize": "10px", "color": COLORS["text_muted"], "marginRight": "4px"}),
                dcc.RadioItems(
                    id="sit-mode-toggle",
                    options=[
                        {"label": "Swing Trading", "value": "swing"},
                        {"label": "Day Trading", "value": "day"},
                    ],
                    value="swing",
                    inline=True,
                    style={"fontSize": "10px", "color": COLORS["text"]},
                ),
            ], style={"display": "flex", "alignItems": "center"}),
            html.Div([
                html.Span(id="sit-status", children="LIVE", style={
                    "fontSize": "10px", "fontWeight": 600, "color": COLORS["green"],
                    "marginRight": "12px",
                }),
                html.Span(id="sit-last-updated", children="Updated —", style={
                    "fontSize": "10px", "color": COLORS["text_muted"], "marginRight": "12px",
                }),
                html.Button("↻ Refresh", id="btn-refresh-should-i-trade", style={
                    "background": "rgba(255,255,255,0.1)", "border": f"1px solid {COLORS['border']}",
                    "color": COLORS["text"], "fontSize": "10px", "padding": "4px 8px",
                    "borderRadius": "4px", "cursor": "pointer",
                }),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={
            "display": "flex", "justifyContent": "space-between", "alignItems": "center",
            "padding": "8px 12px", "borderBottom": f"1px solid {COLORS['border']}",
            "backgroundColor": COLORS["surface2"],
        }),
        # Main content (populated by callback)
        html.Div(
            id="should-i-trade-content",
            children=loading,
            style={"padding": "12px", "minHeight": "400px"},
        ),
        dcc.Interval(id="sit-interval", interval=45000, n_intervals=0),
    ], style=CONTENT_AREA_STYLE)


def build_should_i_trade_content(data: dict, scores: dict, summary: str | dict) -> html.Div:
    """Build full Should I Trade dashboard content from aggregated data and scores."""
    vol = data.get("volatility", {})
    trend = data.get("trend", {})
    breadth = data.get("breadth", {})
    momentum = data.get("momentum", {})
    macro = data.get("macro", {})

    decision = scores.get("decision", "CAUTION")
    mqs = scores.get("market_quality_score", 0)
    ews = scores.get("execution_window_score", 0)
    cat = scores.get("category_scores", {})

    dec_color = COLORS["green"] if decision == "YES" else (COLORS["yellow"] if decision == "CAUTION" else COLORS["red"])

    # Card theme colors (Bloomberg-style)
    CARD_THEMES = {
        "volatility": COLORS["red"],
        "trend": "#3b82f6",
        "breadth": COLORS["accent"],
        "momentum": COLORS["orange"],
        "macro": "#a855f7",
    }

    def _badge(text: str, color: str, size: str = "normal"):
        fs = "10px" if size == "large" else "8px"
        pad = "4px 8px" if size == "large" else "2px 6px"
        return html.Span(text, style={
            "fontSize": fs, "fontWeight": 600, "padding": pad, "borderRadius": "4px",
            "background": f"{color}22", "color": color,
        })

    def _detail_card(title: str, icon: str, score: float, theme: str, rows: list, large_text: bool = False):
        """Build a detailed card with header, progress bar, and metric rows (label, value, badge)."""
        sz = "large" if large_text else "normal"
        bar_color = COLORS["red"] if score < 40 else (COLORS["yellow"] if score < 70 else COLORS["green"])
        h_fs = "12px" if large_text else "10px"
        score_fs = "18px" if large_text else "14px"
        bar_h = "4px" if large_text else "3px"
        pad = "16px" if large_text else "12px"
        return html.Div([
            html.Div([
                html.Span(icon, style={"fontSize": "14px" if large_text else "12px", "marginRight": "6px", "opacity": 0.9}),
                html.Span(title.upper(), style={"fontSize": h_fs, "fontWeight": 700, "color": COLORS["text_muted"], "letterSpacing": "0.5px"}),
                html.Span(f"{int(score)}", className="sit-mono", style={"fontSize": score_fs, "fontWeight": 700, "color": bar_color, "marginLeft": "auto"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px" if large_text else "6px"}),
            html.Div([
                html.Div(style={"width": f"{min(100, max(0, score))}%", "height": bar_h, "background": bar_color, "borderRadius": "2px"}),
            ], style={"width": "100%", "height": bar_h, "background": COLORS["surface3"], "borderRadius": "2px", "overflow": "hidden", "marginBottom": "12px" if large_text else "10px"}),
            html.Div([
                _metric_row(dot_color, label, value, badge_text, badge_color, sz)
                for dot_color, label, value, badge_text, badge_color in rows
            ]),
        ], style={
            "padding": pad, "borderRadius": "6px", "background": COLORS["surface2"],
            "border": f"1px solid {COLORS['border']}", "minWidth": "160px",
            **({"height": "100%", "display": "flex", "flexDirection": "column"} if large_text else {}),
        })

    def _metric_row(dot_color: str, label: str, value, badge_text: str, badge_color: str, size: str = "normal"):
        fs = "12px" if size == "large" else "9px"
        dot_fs = "10px" if size == "large" else "8px"
        row_mb = "10px" if size == "large" else "6px"
        label_w = "120px" if size == "large" else "90px"
        return html.Div([
            html.Span("●", style={"fontSize": dot_fs, "color": dot_color, "marginRight": "8px"}),
            html.Span(label, style={"fontSize": fs, "color": COLORS["text_muted"], "flex": f"0 0 {label_w}"}),
            html.Span(str(value) if value is not None else "—", className="sit-mono", style={"fontSize": fs, "color": COLORS["text"], "flex": "1"}),
            _badge(badge_text, badge_color, size) if badge_text else html.Span(),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px", "marginBottom": row_mb})

    def _status_dot(v, low, high):
        if v is None: return COLORS["text_faint"]
        return COLORS["green"] if v < low else (COLORS["red"] if v > high else COLORS["yellow"])
    def _status_dot_slope(s):
        if s is None: return COLORS["text_faint"]
        return COLORS["red"] if s and s > 0.5 else (COLORS["green"] if s and s < -0.5 else COLORS["yellow"])
    def _vix_status(v):
        if v is None: return "—"
        return "Low" if v < 15 else ("High" if v > 22 else "Normal")
    def _vix_badge_color(v):
        if v is None: return COLORS["text_faint"]
        return COLORS["green"] if v < 15 else (COLORS["red"] if v > 22 else COLORS["yellow"])
    def _vix_trend_badge(s):
        if s is None: return "—"
        return "Spiking" if s > 0.5 else ("Declining" if s < -0.5 else "Flat")
    def _vix_trend_color(s):
        if s is None: return COLORS["text_faint"]
        return COLORS["red"] if s > 0.5 else (COLORS["green"] if s < -0.5 else COLORS["yellow"])
    def _pct_status(p):
        if p is None: return "—"
        return "Low" if p < 20 else ("High" if p > 80 else "Normal")
    def _pct_badge_color(p):
        if p is None: return COLORS["text_faint"]
        return COLORS["green"] if p > 50 else (COLORS["red"] if p < 25 else COLORS["yellow"])
    def _pc_dot(p):
        if p is None: return COLORS["text_faint"]
        return COLORS["red"] if p > 1.1 else (COLORS["green"] if p < 0.9 else COLORS["yellow"])
    def _pc_badge(p):
        if p is None: return "—"
        return "Fear elevated" if p > 1.1 else ("Complacent" if p < 0.85 else "Neutral")
    def _pc_color(p):
        if p is None: return COLORS["text_faint"]
        return COLORS["orange"] if p > 1.05 else (COLORS["green"] if p < 0.9 else COLORS["yellow"])

    # Build metric rows for each card
    vix = vol.get("vix")
    slope = vol.get("vix_5d_slope")
    pct = vol.get("vix_1y_pct")
    pc = vol.get("put_call_est")
    vol_rows = [
        (_status_dot(vix, 15, 25), "VIX Level", f"{vix:.2f}" if vix is not None else "—", _vix_status(vix), _vix_badge_color(vix)),
        (_status_dot_slope(slope), "VIX Trend", "Rising" if slope and slope > 0.5 else ("Falling" if slope and slope < -0.5 else "Flat"), _vix_trend_badge(slope), _vix_trend_color(slope)),
        (COLORS["green"] if pct and pct > 30 else (COLORS["red"] if pct and pct < 20 else COLORS["yellow"]), "VIX 1Y %ile", f"{int(pct)}th" if pct is not None else "—", _pct_status(pct), _pct_badge_color(pct)),
        (_pc_dot(pc), "Put/Call", f"{pc:.2f}" if pc is not None else "—", _pc_badge(pc), _pc_color(pc)),
    ]

    spy_a20 = trend.get("spy_above_20")
    spy_a50 = trend.get("spy_above_50")
    spy_a200 = trend.get("spy_above_200")
    qqq_a50 = trend.get("qqq_above_50")
    regime = trend.get("regime", "chop")

    def _ma_label(above):
        if above is None: return "—"
        return "Above" if above else "Below"
    def _ma_dot(above):
        if above is None: return COLORS["text_faint"]
        return COLORS["green"] if above else COLORS["red"]
    def _ma_badge(above):
        if above is None: return "—"
        return "Intact" if above else "Weak"
    def _ma_badge_color(above):
        if above is None: return COLORS["text_faint"]
        return COLORS["green"] if above else COLORS["red"]
    def _at_ma(above):
        return "At MA" if above is None else (_ma_label(above))

    trend_rows = [
        (_ma_dot(spy_a20), "SPX vs 20d", _at_ma(spy_a20), "Neutral" if spy_a20 is None else _ma_badge(spy_a20), COLORS["text_muted"] if spy_a20 is None else _ma_badge_color(spy_a20)),
        (_ma_dot(spy_a50), "SPX vs 50d", _ma_label(spy_a50), _ma_badge(spy_a50), _ma_badge_color(spy_a50)),
        (_ma_dot(spy_a200), "SPX vs 200d", _ma_label(spy_a200), _ma_badge(spy_a200), _ma_badge_color(spy_a200)),
        (_ma_dot(qqq_a50), "QQQ Trend", "Below 50d" if qqq_a50 is False else ("Above 50d" if qqq_a50 else "—"), "Correcting" if qqq_a50 is False else ("Strong" if qqq_a50 else "—"), COLORS["red"] if qqq_a50 is False else (COLORS["green"] if qqq_a50 else COLORS["text_faint"])),
        (COLORS["red"] if regime == "downtrend" else (COLORS["green"] if regime == "uptrend" else COLORS["yellow"]), "Regime", regime.title(), regime.title(), COLORS["red"] if regime == "downtrend" else (COLORS["green"] if regime == "uptrend" else COLORS["orange"])),
    ]

    p20 = breadth.get("pct_above_20")
    p50 = breadth.get("pct_above_50")
    p200 = breadth.get("pct_above_200")
    up4 = breadth.get("up4")
    down4 = breadth.get("down4")
    nh = breadth.get("new_highs")
    nl = breadth.get("new_lows")

    def _pct_badge(p):
        if p is None: return "—"
        return "Very weak" if p < 25 else ("Weak" if p < 40 else ("Healthy" if p > 55 else "Neutral"))
    def _pct_dot(p):
        if p is None: return COLORS["text_faint"]
        return COLORS["green"] if p > 50 else (COLORS["red"] if p < 35 else COLORS["yellow"])
    ad_ratio = (up4 / down4) if (up4 is not None and down4 is not None and down4 > 0) else None
    ad_display = f"{ad_ratio:.1f}:1" if ad_ratio is not None else (f"{up4 or 0}/{down4 or 0}" if (up4 or down4) else "—")
    breadth_rows = [
        (_pct_dot(p50), "% > 50d MA", f"{p50}%" if p50 is not None else "—", _pct_badge(p50), _pct_dot(p50)),
        (_pct_dot(p200), "% > 200d MA", f"{p200}%" if p200 is not None else "—", _pct_badge(p200), _pct_dot(p200)),
        (_pct_dot(p20), "% > 20d MA", f"{p20}%" if p20 is not None else "—", _pct_badge(p20), _pct_dot(p20)),
        (COLORS["green"] if ad_ratio and ad_ratio > 1 else (COLORS["red"] if ad_ratio else COLORS["text_faint"]), "NYSE A/D", ad_display, "Positive" if ad_ratio and ad_ratio > 1 else ("Negative" if ad_ratio and ad_ratio < 1 else "—"), COLORS["green"] if ad_ratio and ad_ratio > 1 else (COLORS["red"] if ad_ratio else COLORS["text_faint"])),
        (COLORS["green"] if nh and nl and nh > nl else (COLORS["red"] if nh and nl else COLORS["text_faint"]), "NAS Highs/Lows", f"{nh or 0}/{nl or 0}" if (nh or nl) is not None else "—", "Highs dominate" if nh and nl and nh > nl else ("Lows dominate" if nh and nl else "—"), COLORS["green"] if nh and nl and nh > nl else (COLORS["red"] if nh and nl else COLORS["text_faint"])),
    ]

    sectors = momentum.get("sectors", [])
    pos_count = sum(1 for s in sectors if (s.get("chg") or 0) >= 0)
    leader = momentum.get("top3", [{}])[0] if momentum.get("top3") else {}
    laggard = momentum.get("bottom3", [{}])[-1] if momentum.get("bottom3") else {}
    participation = "Low" if pos_count <= 3 else ("High" if pos_count >= 8 else "Mixed")

    def _sector_label(s):
        if not s: return "—"
        t = s.get("ticker", "")
        name = SECTOR_NAMES.get(t, t)
        chg = s.get("chg") or 0
        return f"{name} ({chg:+.2f}%)"

    mom_rows = [
        (COLORS["green"] if pos_count >= 6 else (COLORS["red"] if pos_count <= 2 else COLORS["yellow"]), "Sectors +", f"{pos_count}/11", "Very thin" if pos_count <= 2 else ("Narrow" if pos_count <= 5 else "Broad"), COLORS["red"] if pos_count <= 2 else (COLORS["yellow"] if pos_count <= 5 else COLORS["green"])),
        (COLORS["green"] if (leader.get("chg") or 0) >= 0 else COLORS["red"], "Leader", _sector_label(leader), "", COLORS["text_muted"]),
        (COLORS["red"] if (laggard.get("chg") or 0) < 0 else COLORS["green"], "Laggard", _sector_label(laggard), "", COLORS["text_muted"]),
        (COLORS["green"] if participation == "High" else (COLORS["red"] if participation == "Low" else COLORS["yellow"]), "Participation", participation, "Narrow" if participation == "Low" else ("Broad" if participation == "High" else "Mixed"), COLORS["red"] if participation == "Low" else (COLORS["green"] if participation == "High" else COLORS["yellow"])),
    ]

    fomc_status = "TODAY" if macro.get("fomc_today") else ("72h" if macro.get("fomc_within_72h") else "Clear")
    tnx = macro.get("tnx")
    dxy = macro.get("dxy")
    fed = macro.get("fed_stance", "neutral")
    fed_rate = macro.get("fed_rate_str", "")
    tnx_trend = macro.get("tnx_5d_trend")
    dxy_trend = macro.get("dxy_trend")

    macro_rows = [
        (COLORS["red"] if macro.get("fomc_today") else (COLORS["yellow"] if macro.get("fomc_within_72h") else COLORS["green"]), "FOMC", fomc_status, "Event risk!" if macro.get("fomc_today") else ("Watch" if macro.get("fomc_within_72h") else "Clear"), COLORS["red"] if macro.get("fomc_today") else (COLORS["yellow"] if macro.get("fomc_within_72h") else COLORS["green"])),
        (COLORS["red"] if tnx_trend and tnx_trend > 0.1 else (COLORS["green"] if tnx_trend and tnx_trend < -0.05 else COLORS["yellow"]), "10Y Yield", f"{tnx:.2f}%" if tnx is not None else "—", "Rising" if tnx_trend and tnx_trend > 0.05 else ("Falling" if tnx_trend and tnx_trend < -0.05 else "Stable"), COLORS["orange"] if tnx_trend and tnx_trend > 0.05 else (COLORS["green"] if tnx_trend and tnx_trend < -0.05 else COLORS["yellow"])),
        (COLORS["orange"] if dxy_trend and dxy_trend > 0.3 else (COLORS["green"] if dxy_trend and dxy_trend < -0.3 else COLORS["yellow"]), "DXY", f"{dxy:.2f}" if dxy is not None else "—", "Strengthening" if dxy_trend and dxy_trend > 0.2 else ("Weakening" if dxy_trend and dxy_trend < -0.2 else "Stable"), COLORS["orange"] if dxy_trend and dxy_trend > 0.2 else (COLORS["green"] if dxy_trend and dxy_trend < -0.2 else COLORS["yellow"])),
        (COLORS["blue_tml"] if fed == "neutral" else (COLORS["green"] if fed == "dovish" else COLORS["orange"]), "Fed Stance", f"{fed.title()} ({fed_rate})" if fed_rate else fed.title(), fed.title(), COLORS["blue_tml"] if fed == "neutral" else (COLORS["green"] if fed == "dovish" else COLORS["orange"])),
        (COLORS["text_faint"], "Geopolitical", "—", "Monitor", COLORS["text_muted"]),
    ]

    panels = html.Div([
        _detail_card("Volatility", "▽", cat.get("volatility", {}).get("score", 50), CARD_THEMES["volatility"], vol_rows),
        _detail_card("Trend", "↗", cat.get("trend", {}).get("score", 50), CARD_THEMES["trend"], trend_rows),
        _detail_card("Breadth", "◇", cat.get("breadth", {}).get("score", 50), CARD_THEMES["breadth"], breadth_rows),
        _detail_card("Momentum", "↑", cat.get("momentum", {}).get("score", 50), CARD_THEMES["momentum"], mom_rows),
        _detail_card("Macro", "◉", cat.get("macro", {}).get("score", 50), CARD_THEMES["macro"], macro_rows),
    ], style={"display": "grid", "gridTemplateColumns": "repeat(5, 1fr)", "gap": "8px", "marginBottom": "12px"})

    mode_label = "Swing Trading" if scores.get("mode") == "swing" else "Day Trading"
    position_size = "FULL" if mqs >= 80 else ("HALF" if mqs >= 60 else "MINIMAL")
    position_instruction = "Press risk" if mqs >= 80 else ("A+ setups only" if mqs >= 60 else "Preserve capital")

    def _score_color(s):
        return COLORS["red"] if s < 40 else (COLORS["yellow"] if s < 70 else COLORS["green"])

    cat_items = [
        ("Volatility", "〰", cat.get("volatility", {}).get("score", 0), CARD_THEMES["volatility"]),
        ("Trend", "↗", cat.get("trend", {}).get("score", 0), CARD_THEMES["trend"]),
        ("Breadth", "⊞", cat.get("breadth", {}).get("score", 0), CARD_THEMES["breadth"]),
        ("Momentum", "↑", cat.get("momentum", {}).get("score", 0), CARD_THEMES["momentum"]),
        ("Macro", "◉", cat.get("macro", {}).get("score", 0), CARD_THEMES["macro"]),
    ]
    cat_columns = []
    for name, icon, s, theme in cat_items:
        sc = _score_color(s)
        cat_columns.append(html.Div([
            html.Div(icon, style={"fontSize": "14px", "color": theme, "marginBottom": "4px"}),
            html.Div(name.upper(), style={"fontSize": "9px", "color": COLORS["text_muted"], "letterSpacing": "0.5px", "marginBottom": "2px"}),
            html.Div(f"{int(s)}", className="sit-mono", style={"fontSize": "16px", "fontWeight": 700, "color": sc, "marginBottom": "6px"}),
            html.Div([
                html.Div(style={"width": f"{min(100, s)}%", "height": "4px", "background": sc, "borderRadius": "2px"}),
            ], style={"width": "100%", "height": "4px", "background": COLORS["surface3"], "borderRadius": "2px", "overflow": "hidden"}),
        ], style={"display": "flex", "flexDirection": "column", "alignItems": "center", "minWidth": "72px"}))

    mqs_pct = min(100, max(0, mqs))
    gauge_fill = _score_color(mqs)

    hero = html.Div([
        # Decision section
        html.Div([
            html.Div("DECISION", style={"fontSize": "9px", "color": COLORS["text_muted"], "letterSpacing": "1px", "marginBottom": "6px"}),
            html.Div(decision, className="sit-mono", style={
                "fontSize": "32px", "fontWeight": 800, "color": dec_color,
                "letterSpacing": "3px", "padding": "12px 20px", "border": f"2px solid {dec_color}",
                "borderRadius": "6px", "boxShadow": f"0 0 12px {dec_color}40",
            }),
            html.Div(mode_label, style={"fontSize": "10px", "color": COLORS["text_muted"], "marginTop": "8px"}),
        ], style={"display": "flex", "flexDirection": "column", "alignItems": "center", "marginRight": "32px"}),
        # Circular gauge
        html.Div([
            html.Div(style={
                "width": "80px", "height": "80px", "borderRadius": "50%",
                "background": f"conic-gradient({gauge_fill} 0% {mqs_pct}%, {COLORS['surface3']} {mqs_pct}% 100%)",
                "padding": "6px", "boxSizing": "border-box",
            }, children=[
                html.Div([
                    html.Div(f"{int(mqs)}", className="sit-mono", style={"fontSize": "22px", "fontWeight": 800, "color": gauge_fill, "lineHeight": 1}),
                    html.Div("/ 100", style={"fontSize": "10px", "color": COLORS["text_muted"]}),
                ], style={"width": "100%", "height": "100%", "borderRadius": "50%", "background": COLORS["surface2"], "display": "flex", "flexDirection": "column", "alignItems": "center", "justifyContent": "center"}),
            ]),
        ], style={"marginRight": "40px"}),
        # Five category columns
        html.Div(cat_columns, style={"display": "flex", "gap": "40px", "flex": "1", "justifyContent": "space-evenly", "alignItems": "center"}),
        # Vertical divider
        html.Div(style={"width": "1px", "height": "60px", "background": COLORS["border"], "marginRight": "24px"}),
        # Position size
        html.Div([
            html.Div("POSITION SIZE", style={"fontSize": "9px", "color": COLORS["text_muted"], "letterSpacing": "1px", "marginBottom": "6px"}),
            html.Div([
                html.Span("🛡", style={"fontSize": "18px", "marginRight": "6px"}),
                html.Div([
                    html.Div(position_size, className="sit-mono", style={"fontSize": "16px", "fontWeight": 700, "color": dec_color}),
                    html.Div(position_instruction, style={"fontSize": "10px", "color": COLORS["text_muted"], "marginTop": "2px"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={"display": "flex", "flexDirection": "column", "alignItems": "flex-start"}),
    ], style={"display": "flex", "alignItems": "center", "padding": "24px 28px", "background": COLORS["surface2"], "borderRadius": "8px", "border": f"1px solid {COLORS['border']}", "marginBottom": "12px"})

    ew_factors = scores.get("execution_window_factors", {})
    def _ew_row(key, label):
        v = ew_factors.get(key, ("—", "—"))
        yes_no = v[0] if len(v) > 0 else "—"
        detail = v[1] if len(v) > 1 else "—"
        dot = COLORS["green"] if yes_no == "Yes" else (COLORS["red"] if yes_no == "No" else COLORS["yellow"])
        badge_c = COLORS["green"] if yes_no == "Yes" else (COLORS["red"] if yes_no == "No" else COLORS["yellow"])
        return (dot, label, yes_no, detail, badge_c)
    ew_rows = [
        _ew_row("breakouts_working", "Breakouts working?"),
        _ew_row("leaders_holding", "Leaders holding?"),
        _ew_row("pullbacks_bought", "Pullbacks bought?"),
        _ew_row("follow_through", "Follow-through?"),
    ]
    execution_card = _detail_card("Execution Window", "◐", ews, COLORS["accent"], ew_rows, large_text=True)

    sectors = momentum.get("sectors", [])
    sector_bars = []
    for s in sorted(sectors, key=lambda x: x.get("chg") or 0, reverse=True):
        chg = s.get("chg") or 0
        bar_color = COLORS["green"] if chg >= 0 else COLORS["red"]
        sector_bars.append(html.Div([
            html.Span(s.get("ticker", ""), style={"fontSize": "10px", "width": "40px", "display": "inline-block"}),
            html.Div([
                html.Div(style={
                    "width": f"{min(100, max(0, 50 + chg * 2))}%", "height": "100%",
                    "background": bar_color, "borderRadius": "2px",
                }),
            ], style={"flex": 1, "height": "14px", "background": COLORS["surface3"], "borderRadius": "2px", "overflow": "hidden"}),
            html.Span(f"{chg:+.2f}%", className="sit-mono", style={"fontSize": "10px", "width": "50px", "textAlign": "right", "color": bar_color}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "4px"}))

    heatmap = html.Div([
        html.Div("Sector Performance", style={"fontSize": "11px", "fontWeight": 600, "marginBottom": "8px", "color": COLORS["text_muted"]}),
        html.Div(sector_bars or [html.Span("No sector data", style={"color": COLORS["text_muted"]})], style={"flex": "1", "minHeight": "0", "overflowY": "auto"}),
    ], style={"padding": "12px", "background": COLORS["surface2"], "borderRadius": "6px", "border": f"1px solid {COLORS['border']}", "display": "flex", "flexDirection": "column", "height": "100%"})

    def _weight_row_color(s):
        return COLORS["red"] if s < 40 else (COLORS["orange"] if s < 70 else COLORS["green"])
    weight_order = ["volatility", "momentum", "trend", "breadth", "macro"]
    weight_rows = []
    for name in weight_order:
        cfg = cat.get(name, {})
        s = cfg.get("score", 0)
        w = cfg.get("weight", 0) * 100
        bar_c = _weight_row_color(s)
        weight_rows.append(html.Div([
            html.Span(name.title(), style={"fontSize": "10px", "color": COLORS["text_muted"], "width": "72px", "flexShrink": 0}),
            html.Div([
                html.Div(style={"width": f"{min(100, max(0, s))}%", "height": "100%", "background": bar_c, "borderRadius": "4px"}),
            ], style={"flex": 1, "height": "8px", "background": COLORS["surface3"], "borderRadius": "4px", "overflow": "hidden", "minWidth": "60px"}),
            html.Span(f"{int(s)}", className="sit-mono", style={"fontSize": "10px", "fontWeight": 600, "color": bar_c, "width": "24px", "textAlign": "right"}),
            html.Span(f"×{w:.0f}%", style={"fontSize": "9px", "color": COLORS["text_faint"], "width": "36px", "textAlign": "right"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "6px"}))
    total_color = _weight_row_color(mqs)
    legend = html.Div([
        html.Span("●", style={"color": COLORS["green"], "fontSize": "8px", "marginRight": "4px"}),
        html.Span("80-100: YES (press risk)  ", style={"fontSize": "9px", "color": COLORS["text_muted"]}),
        html.Span("●", style={"color": COLORS["orange"], "fontSize": "8px", "marginRight": "4px"}),
        html.Span("60-79: CAUTION (selective)  ", style={"fontSize": "9px", "color": COLORS["text_muted"]}),
        html.Span("●", style={"color": COLORS["red"], "fontSize": "8px", "marginLeft": "4px", "marginRight": "4px"}),
        html.Span("<60: NO (preserve capital)", style={"fontSize": "9px", "color": COLORS["text_muted"]}),
    ], style={"marginTop": "10px", "display": "flex", "flexWrap": "wrap", "alignItems": "center"})

    breakdown = html.Div([
        html.Div([
            html.Span("〰", style={"fontSize": "12px", "color": COLORS["accent"], "marginRight": "6px"}),
            html.Span("SCORING WEIGHTS", style={"fontSize": "11px", "fontWeight": 700, "color": COLORS["accent"], "letterSpacing": "0.5px"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
        html.Div(weight_rows),
        html.Div(style={"height": "1px", "background": COLORS["border"], "margin": "8px 0"}),
        html.Div([
            html.Span("TOTAL SCORE", style={"fontSize": "10px", "color": COLORS["text_muted"]}),
            html.Span(f"{int(mqs)}/100", className="sit-mono", style={"fontSize": "18px", "fontWeight": 800, "color": total_color}),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),
        legend,
    ], style={"padding": "12px", "background": COLORS["surface2"], "borderRadius": "6px", "border": f"1px solid {COLORS['border']}", "display": "flex", "flexDirection": "column", "height": "100%"})

    alert_banner = html.Div()
    if macro.get("major_event_within_72h"):
        events = macro.get("events_72h", [])
        evt_str = "; ".join(e.get("title", "") for e in events[:3])
        fomc_note = "FOMC DECISION TODAY: " if macro.get("fomc_today") else "Major event within 72h: "
        fed_rate = macro.get("fed_rate_str", "")
        hold_str = f" at {fed_rate}" if fed_rate else ""
        fomc_detail = f"Rate decision at 2:00 PM ET. Fed widely expected to hold{hold_str}. Press conference at 2:30 PM." if macro.get("fomc_today") else evt_str
        alert_banner = html.Div([
            html.Span("⚠ ", style={"color": COLORS["orange"], "fontSize": "14px"}),
            html.Span(f"{fomc_note}{fomc_detail}", style={"fontSize": "11px", "color": COLORS["orange"]}),
        ], style={
            "padding": "8px 12px", "background": "rgba(249,115,22,0.15)", "borderRadius": "4px",
            "border": f"1px solid {COLORS['orange']}", "marginBottom": "12px",
        })

    summary_text = summary.get("text", summary) if isinstance(summary, dict) else summary
    suggested_action = summary.get("suggested_action", "") if isinstance(summary, dict) else ""

    analysis = html.Div([
        html.Div("AI-Generated Market Assessment", style={"fontSize": "11px", "fontWeight": 600, "marginBottom": "6px", "color": COLORS["text_muted"]}),
        html.Div(summary_text, style={"fontSize": "11px", "color": COLORS["text"], "lineHeight": 1.5, "marginBottom": "8px", "flex": "1", "minHeight": "0", "overflowY": "auto"}),
        html.Div([
            html.Span("Suggested action: ", style={"fontSize": "10px", "color": COLORS["text_muted"]}),
            html.Span(suggested_action, style={"fontSize": "11px", "fontWeight": 700, "color": dec_color}),
        ], style={"paddingTop": "8px", "borderTop": f"1px solid {COLORS['border']}"}) if suggested_action else html.Span(),
    ], style={"padding": "12px", "background": COLORS["surface2"], "borderRadius": "6px", "border": f"1px solid {COLORS['border']}", "display": "flex", "flexDirection": "column", "height": "100%"})

    ticker_tape = data.get("ticker_tape", [])
    def _tape_item(t):
        chg = t.get("change", "")
        is_pos = "+" in str(chg)
        return html.Span([
            html.Span(t.get("ticker", ""), style={"fontWeight": 600, "marginRight": "4px"}),
            html.Span(chg, className="sit-mono", style={"color": COLORS["green"] if is_pos else COLORS["red"], "fontSize": "10px"}),
        ], style={"display": "inline-flex", "marginRight": "24px", "whiteSpace": "nowrap"})
    tape_items = [_tape_item(t) for t in ticker_tape]
    tape_duplicated = tape_items + tape_items if tape_items else []
    ticker_marquee = html.Div([
        html.Div(tape_duplicated, className="sit-ticker-marquee-inner"),
    ], className="sit-ticker-marquee") if tape_items else html.Div("Loading ticker data...", style={"color": COLORS["text_muted"], "fontSize": "10px"})

    return html.Div([
        html.Div([
            html.Div("SHOULD I BE TRADING?", style={"fontSize": "14px", "fontWeight": 800, "color": COLORS["text"], "letterSpacing": "1px"}),
            html.Div("MARKET QUALITY TERMINAL.", style={"fontSize": "10px", "color": COLORS["text_muted"], "marginTop": "2px"}),
        ], style={"marginBottom": "8px"}),
        html.Div(ticker_marquee, style={
            "padding": "8px 0", "borderBottom": f"1px solid {COLORS['border']}", "marginBottom": "12px",
        }),
        hero,
        alert_banner,
        panels,
        html.Div([
            execution_card,
            heatmap,
            breakdown,
            analysis,
        ], style={
            "display": "grid",
            "gridTemplateColumns": "1fr 2fr",
            "gridTemplateRows": "1fr 1fr",
            "gap": "12px",
            "alignItems": "stretch",
            "minHeight": "320px",
        }),
    ])


def build_stockbee_breadth(breadth: dict | None) -> html.Div:
    """Stockbee-style breadth metric cards: S&P 500, T2108, 5-Day Ratio, 10-Day Ratio, Up 4%+, Down 4%+."""
    if not breadth:
        return html.Div("Breadth data unavailable. Start Stockbee API or check Sheets.", style={
            "color": COLORS["text_muted"], "fontSize": "12px", "padding": "8px",
        })
    sp_up = (breadth.get("sp500_change") or 0) >= 0
    t2108 = breadth.get("t2108") or 50
    t2108_color = COLORS["green_light"] if t2108 > 50 else COLORS["red_light"] if t2108 < 30 else COLORS["accent"]
    r5 = breadth.get("ratio5") or 1.0
    r10 = breadth.get("ratio10") or 1.0
    r5_bull = r5 >= 1
    r10_bull = r10 >= 1

    def _card(label: str, value, sub: str, color: str):
        return html.Div([
            html.Div(label, style={"fontSize": "12px", "color": COLORS["text_muted"], "marginBottom": "6px"}),
            html.Div(str(value), style={"fontSize": "22px", "fontWeight": 700, "color": color}),
            html.Div(sub, style={"fontSize": "11px", "color": COLORS["text_faint"], "marginTop": "6px"}),
        ], style={
            "padding": "16px 12px", "borderRadius": "6px", "background": COLORS["surface2"],
            "border": f"1px solid {COLORS['border']}",
            "display": "flex", "flexDirection": "column", "justifyContent": "center",
        })

    grid = html.Div([
        _card("S&P 500", f"{breadth.get('sp500', 0):,.2f}",
              f"{'▲' if sp_up else '▼'} {abs(breadth.get('sp500_change') or 0):.2f} ({breadth.get('sp500_change_pct') or 0:.2f}%)",
              COLORS["green_light"] if sp_up else COLORS["red_light"]),
        _card("T2108", f"{t2108:.2f}", "% above 40-day MA", t2108_color),
        _card("5-Day Ratio", f"{r5:.2f}", "BULLISH" if r5_bull else "BEARISH",
              COLORS["green_light"] if r5_bull else COLORS["red_light"]),
        _card("10-Day Ratio", f"{r10:.2f}", "BULLISH" if r10_bull else "BEARISH",
              COLORS["green_light"] if r10_bull else COLORS["red_light"]),
        _card("Up 4%+", f"{breadth.get('up4', 0):,}", "today", COLORS["green_light"]),
        _card("Down 4%+", f"{breadth.get('down4', 0):,}", "today", COLORS["red_light"]),
    ], style={
        "display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gridTemplateRows": "1fr 1fr",
        "gap": "12px", "minHeight": "330px", "padding": "8px", "boxSizing": "border-box",
    })
    return grid


# -----------------------------------------------------------------------
# Section 14: Stage Analysis
# -----------------------------------------------------------------------

def build_stage_chart(counts: dict) -> go.Figure:
    labels = [f"Stage {s}" for s in STAGE_LABELS]
    values = [counts.get(s, 0) for s in STAGE_LABELS]
    colors = [STAGE_BAR_COLORS[s] for s in STAGE_LABELS]

    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        width=0.6,
    ))
    fig.update_layout(
        autosize=True,
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=4, r=4, t=4, b=4),
        showlegend=False,
        xaxis=dict(
            tickfont=dict(size=8, color=COLORS["text_muted"]),
            showgrid=False,
        ),
        yaxis=dict(
            tickfont=dict(size=8, color=COLORS["text_faint"]),
            gridcolor="rgba(255,255,255,0.05)",
        ),
        font=dict(family="Inter"),
        height=STAGE_CHART_HEIGHT,
    )
    return fig


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert #RRGGBB to rgba(r,g,b,alpha)."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def build_rrg_chart(rrg_data: list[dict]) -> go.Figure:
    """RRG scatter: one point per sector with distinct color (no tails)."""
    if not rrg_data:
        return go.Figure()

    fig = go.Figure()

    for i, r in enumerate(rrg_data):
        color = RRG_COLORS[i % len(RRG_COLORS)]
        fig.add_trace(go.Scatter(
            x=[r["rs_ratio"]], y=[r["rs_momentum"]], mode="markers+text",
            text=[r["ticker"]], textposition="top center",
            textfont=dict(size=9, color=color),
            marker=dict(size=10, color=color, line=dict(width=1, color=COLORS["border"]), symbol="circle"),
            name=r["name"],
            customdata=[r["name"]],
            hovertemplate="%{customdata}<br>RS-Ratio: %{x:.1f}<br>RS-Momentum: %{y:.1f}<extra></extra>",
        ))

    # Quadrant lines at 100; range from current points only
    all_x = [r["rs_ratio"] for r in rrg_data]
    all_y = [r["rs_momentum"] for r in rrg_data]
    x_range = [min(all_x) - 5, max(all_x) + 5] if all_x else [90, 110]
    y_range = [min(all_y) - 5, max(all_y) + 5] if all_y else [90, 110]
    fig.add_vline(x=100, line_dash="dot", line_color=COLORS["border_light"], opacity=0.6)
    fig.add_hline(y=100, line_dash="dot", line_color=COLORS["border_light"], opacity=0.6)
    fig.update_layout(
        autosize=True,
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=4, r=4, t=24, b=4),
        showlegend=False,
        xaxis=dict(
            title=dict(text="RS-Ratio (1Y vs " + RRG_BENCHMARK + ")", font=dict(size=9, color=COLORS["text_muted"])),
            tickfont=dict(size=8, color=COLORS["text_muted"]),
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
            zeroline=False, range=x_range,
        ),
        yaxis=dict(
            title=dict(text="RS-Momentum (Qtr vs " + RRG_BENCHMARK + ")", font=dict(size=9, color=COLORS["text_muted"])),
            tickfont=dict(size=8, color=COLORS["text_muted"]),
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
            zeroline=False, range=y_range,
        ),
        font=dict(family="Inter"),
        height=SCROLLABLE_BODY_HEIGHT,
        annotations=[
            dict(x=0.98, y=0.98, xref="paper", yref="paper", text="Leading", showarrow=False,
                 font=dict(size=8, color=COLORS["green_light"])),
            dict(x=0.02, y=0.98, xref="paper", yref="paper", text="Weakening", showarrow=False,
                 font=dict(size=8, color=COLORS["yellow"])),
            dict(x=0.02, y=0.02, xref="paper", yref="paper", text="Lagging", showarrow=False,
                 font=dict(size=8, color=COLORS["red_light"])),
            dict(x=0.98, y=0.02, xref="paper", yref="paper", text="Improving", showarrow=False,
                 font=dict(size=8, color=COLORS["accent"])),
        ],
    )
    return fig


def _fmt_b(val, suffix="B"):
    """Format billions with suffix."""
    if val is None or (isinstance(val, float) and (val != val or val == 0)):
        return "-"
    if abs(val) >= 1e12:
        return f"${val/1e12:.1f}T"
    if abs(val) >= 1e9:
        return f"${val/1e9:.1f}{suffix}"
    if abs(val) >= 1e6:
        return f"${val/1e6:.1f}M"
    return f"${val:,.0f}"


def build_sp500_landscape_chart(data: list[dict], sector_filter: list[str] | None = None) -> go.Figure:
    """S&P 500 Landscape Bubble Chart: Revenue (X) vs Net Income (Y), size=Market Cap, color=12M Change."""
    if not data:
        return go.Figure()

    # Apply sector filter if set
    if sector_filter and len(sector_filter) > 0:
        sector_set = set(s.strip() for s in sector_filter if s and str(s).strip())
        if sector_set:
            data = [r for r in data if r.get("sector", "").strip() in sector_set]

    # Filter valid points for axes (need revenue for X; net_income can be negative)
    valid = [
        r for r in data
        if r.get("revenue") is not None and r.get("revenue") > 0
        and r.get("net_income") is not None
        and r.get("market_cap") and r.get("market_cap") > 0
    ]
    if not valid:
        return go.Figure()

    # Sort by market cap (largest first) for layering
    valid.sort(key=lambda x: x.get("market_cap") or 0, reverse=True)

    rev_b = [r["revenue"] / 1e9 for r in valid]
    ni_b = [r["net_income"] / 1e9 for r in valid]
    mcap = [r["market_cap"] for r in valid]
    chg12m = [r.get("change_12m") or 0 for r in valid]
    tickers = [r["ticker"] for r in valid]

    # Bubble size: scale by sqrt(mcap) for visibility (log-like)
    import math
    mcap_min, mcap_max = min(mcap), max(mcap)
    size_min, size_max = 4, 50
    if mcap_max <= mcap_min:
        sizes = [20] * len(mcap)
    else:
        log_min, log_max = math.log10(max(1e6, mcap_min)), math.log10(max(1e6, mcap_max))
        sizes = [
            size_min + (size_max - size_min) * (math.log10(max(1e6, m)) - log_min) / (log_max - log_min)
            for m in mcap
        ]

    # Color scale: red (-50%) -> grey (0) -> green (100%)
    def _color_for_chg(chg):
        if chg >= 0:
            t = min(1.0, chg / 100)
            r, g = int(120 + 100 * (1 - t)), int(200 + 55 * t)
            return f"rgb({r},{g},94)"
        t = max(-1.0, chg / -50)
        r, g = int(239 - 100 * (1 - t)), int(68 + 100 * (1 - t))
        return f"rgb({r},{g},68)"

    colors = [_color_for_chg(c) for c in chg12m]

    # Hover: all fields
    def _hover(r):
        rev = _fmt_b(r.get("revenue"), "B")
        ni = _fmt_b(r.get("net_income"), "B")
        mcap_str = _fmt_b(r.get("market_cap"), "B")
        pm = r.get("profit_margin")
        pm_str = f"{pm:.1f}%" if pm is not None and not (isinstance(pm, float) and (pm != pm)) else "-"
        prof = r.get("profitability")
        prof_str = f"{prof:.1f}%" if prof is not None and not (isinstance(prof, float) and (prof != prof)) else pm_str
        chg = r.get("change_12m") or 0
        sector = r.get("sector", "") or "-"
        return (
            f"<b>{r['ticker']}</b> ({sector})<br>"
            f"Revenue: {rev}<br>"
            f"Net Income: {ni}<br>"
            f"Market Cap: {mcap_str}<br>"
            f"Price: ${r.get('price', 0):.2f}<br>"
            f"12M Change: {chg:+.1f}%<br>"
            f"Profit Margin: {pm_str}<br>"
            f"Profitability: {prof_str}"
        )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rev_b, y=ni_b,
        mode="markers+text",
        text=[t if m >= (mcap_max * 0.02) else "" for t, m in zip(tickers, mcap)],
        textposition="top center",
        textfont=dict(size=9, color=COLORS["text"]),
        marker=dict(
            size=sizes,
            color=colors,
            line=dict(width=0.5, color=COLORS["border"]),
            opacity=0.75,
        ),
        customdata=[_hover(r) for r in valid],
        hovertemplate="%{customdata}<extra></extra>",
        hoverlabel=dict(bgcolor=COLORS["surface2"], font=dict(size=10)),
    ))

    fig.update_layout(
        autosize=True,
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=50, r=20, t=24, b=60),
        showlegend=False,
        xaxis=dict(
            type="log",
            title=dict(text="Trailing 12-Month Revenue (B$)", font=dict(size=9, color=COLORS["text_muted"])),
            tickfont=dict(size=8, color=COLORS["text_muted"]),
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
            zeroline=False,
            fixedrange=False,
        ),
        yaxis=dict(
            title=dict(text="Trailing 12-Month Net Income (B$)", font=dict(size=9, color=COLORS["text_muted"])),
            tickfont=dict(size=8, color=COLORS["text_muted"]),
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
            zeroline=True, zerolinecolor=COLORS["border_light"], zerolinewidth=1,
            fixedrange=False,
        ),
        font=dict(family="Inter"),
        height=SP500_LANDSCAPE_CHART_HEIGHT,
        annotations=[
            dict(x=0.02, y=0.02, xref="paper", yref="paper", showarrow=False,
                 text="12M Change: -50% (red) → 0% → 100% (green)<br>Size: Market Cap ($1B → $1T)",
                 font=dict(size=8, color=COLORS["text_muted"]), align="left"),
        ],
    )
    return fig


def build_stage_summary(counts: dict) -> html.Div:
    stage1_total = counts.get("1A", 0) + counts.get("1B", 0)
    stage2_total = counts.get("2A", 0) + counts.get("2B", 0) + counts.get("2C", 0)
    stage3_total = counts.get("3A", 0) + counts.get("3B", 0)
    stage4_total = counts.get("4A", 0) + counts.get("4B", 0) + counts.get("4C", 0)
    bullish = stage2_total > (stage3_total + stage4_total)

    items = [
        html.Span([
            html.Span("Stage 1: ", style={"color": COLORS["text_muted"]}),
            html.Span(str(stage1_total), style={"fontWeight": 700}),
        ]),
        html.Span([
            html.Span("Stage 2: ", style={"color": COLORS["text_muted"]}),
            html.Span(str(stage2_total),
                       style={"fontWeight": 700, "color": COLORS["green"]}),
        ]),
        html.Span([
            html.Span("Stage 3: ", style={"color": COLORS["text_muted"]}),
            html.Span(str(stage3_total),
                       style={"fontWeight": 700, "color": COLORS["red"]}),
        ]),
        html.Span([
            html.Span("Stage 4: ", style={"color": COLORS["text_muted"]}),
            html.Span(str(stage4_total),
                       style={"fontWeight": 700, "color": COLORS["red_strong"]}),
        ]),
        html.Span(
            "Bullish" if bullish else "Bearish",
            style={
                "marginLeft": "12px",
                "padding": "1px 8px",
                "backgroundColor": COLORS["green_bg"] if bullish else COLORS["red_bg"],
                "borderRadius": "3px",
                "fontWeight": 700,
                "color": COLORS["green"] if bullish else COLORS["red"],
            },
        ),
    ]
    return html.Div(items, style={
        "display": "flex",
        "justifyContent": "center",
        "gap": "8px",
        "padding": "4px",
        "fontSize": "9px",
    })


# -----------------------------------------------------------------------
# Watchlist widget body (with add/remove)
# -----------------------------------------------------------------------

def build_watchlist_body() -> html.Div:
    return html.Div([
        dcc.Store(id="watchlist-data-store"),
        dcc.Store(id="watchlist-sort-store", data={"col": "change", "asc": False}),
        dcc.Store(id="watchlist-view-store", data="watchlist"),
        html.Div([
            html.Label("View:", style={"fontSize": "10px", "color": COLORS["text_muted"], "marginRight": "6px"}),
            dcc.Dropdown(
                id="watchlist-sector-dropdown",
                options=[{"label": "My Watchlist", "value": "watchlist"}],
                value="watchlist",
                clearable=False,
                style={"minWidth": "160px", "fontSize": "10px"},
            ),
            html.Div([
                dcc.Input(
                    id="watchlist-input",
                    type="text",
                    placeholder="Add ticker (e.g. AAPL or AMD, aapl, GOOGL)",
                    debounce=True,
                    style={
                        "backgroundColor": COLORS["surface2"],
                        "border": f"1px solid {COLORS['border']}",
                        "color": COLORS["text"],
                        "padding": "3px 6px",
                        "borderRadius": "3px",
                        "fontSize": "10px",
                        "width": "120px",
                        "outline": "none",
                    },
                ),
                html.Button("Add", id="btn-watchlist-add", style={
                    "backgroundColor": COLORS["green_cell"],
                    "border": f"1px solid {COLORS['green_strong']}",
                    "color": COLORS["green_light"],
                    "padding": "3px 8px",
                    "borderRadius": "3px",
                    "cursor": "pointer",
                    "fontSize": "10px",
                    "fontWeight": 600,
                }),
            ], id="watchlist-add-row", style={
                "display": "flex", "gap": "4px", "alignItems": "center",
            }),
        ], style={
            "display": "flex", "alignItems": "center", "padding": "4px 4px 2px 4px",
            "gap": "8px", "flexWrap": "wrap",
        }),
        html.Div(id="watchlist-content"),
    ])


# -----------------------------------------------------------------------
# TradingView chart modal
# -----------------------------------------------------------------------

def build_tv_modal() -> html.Div:
    return html.Div([
        html.Div([
            html.Div([
                html.Span("", id="tv-modal-title", style={
                    "fontSize": "13px", "fontWeight": 700,
                    "color": COLORS["accent"],
                }),
                html.Button("X", id="btn-tv-close", style={
                    "background": "transparent",
                    "border": "none",
                    "color": COLORS["text_muted"],
                    "fontSize": "14px",
                    "cursor": "pointer",
                    "fontWeight": 700,
                    "padding": "0 4px",
                }),
            ], style={
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "center", "padding": "6px 10px",
                "borderBottom": f"1px solid {COLORS['border']}",
            }),
            html.Iframe(
                id="tv-iframe",
                style={
                    "width": "100%",
                    "height": "calc(100% - 32px)",
                    "border": "none",
                },
            ),
        ], style={
            "width": "80vw",
            "height": "75vh",
            "maxWidth": "1200px",
            "backgroundColor": COLORS["surface"],
            "borderRadius": "6px",
            "border": f"1px solid {COLORS['border']}",
            "overflow": "hidden",
            "boxShadow": "0 8px 32px rgba(0,0,0,0.6)",
        }),
    ], id="tv-modal", style={
        "display": "none",
        "position": "fixed",
        "top": 0, "left": 0, "right": 0, "bottom": 0,
        "backgroundColor": "rgba(0,0,0,0.7)",
        "zIndex": 99999,
        "justifyContent": "center",
        "alignItems": "center",
    })


# -----------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------

def build_header() -> html.Div:
    now = datetime.now(ZoneInfo("America/New_York"))
    date_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M:%S %p")
    date_time_str = f"{date_str} · {time_str}"

    return html.Div([
        html.Div([
            html.Span("Pradly Portal", style=HEADER_LOGO_STYLE),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
        html.Div([
            html.Span(date_time_str, id="header-date", style=HEADER_DATE_STYLE),
        ], style={"display": "flex", "alignItems": "center", "gap": "12px"}),
        html.Div([
            html.Button("Refresh", id="btn-refresh", style=REFRESH_BTN_STYLE),
            html.Button("Widgets", id="btn-settings", style=SETTINGS_BTN_STYLE),
            html.Span("", id="last-update", style={
                "fontSize": "10px", "color": COLORS["text_muted"],
            }),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
    ], style=HEADER_STYLE)


# -----------------------------------------------------------------------
# Settings drawer (tab-specific widget toggles)
# -----------------------------------------------------------------------

def _build_toggle_item(wid: str, name: str) -> html.Div:
    """Single toggle row for a widget."""
    return html.Div([
        html.Label([
            dcc.Checklist(
                id=f"toggle-{wid}",
                options=[{"label": "", "value": "on"}],
                value=["on"] if DEFAULT_VISIBILITY.get(wid, False) else [],
                style={"display": "inline-block", "marginRight": "6px"},
                inputStyle={"cursor": "pointer"},
            ),
            html.Span(name, style=TOGGLE_LABEL_STYLE),
        ], style={"display": "flex", "alignItems": "center"}),
    ], style=SETTINGS_ITEM_STYLE)


def build_settings_drawer() -> html.Div:
    """Settings drawer with tab-specific sections. Content shown based on active tab."""
    market_toggles = [_build_toggle_item(wid, name) for wid, name, _ in MARKET_METRICS_WIDGETS]
    super_scanners_toggles = [_build_toggle_item(wid, name) for wid, name, _ in SUPER_SCANNERS_WIDGETS]
    intraday_toggles = [_build_toggle_item(wid, name) for wid, name, _ in INTRADAY_WIDGETS]

    return html.Div([
        html.Div("Widget Settings", style=SETTINGS_TITLE_STYLE),
        html.Div([
            html.Div("Macro Monitor", style={**SETTINGS_TITLE_STYLE, "fontSize": "10px", "marginTop": "8px", "color": COLORS["text_muted"]}),
            html.Div(
                "Single full-page view (FRED). No per-widget toggles.",
                style={"fontSize": "10px", "color": COLORS["text_faint"], "lineHeight": 1.4, "maxWidth": "220px"},
            ),
        ], id="settings-macro-monitor"),
        html.Div([
            html.Div("Market Metrics", style={**SETTINGS_TITLE_STYLE, "fontSize": "10px", "marginTop": "8px", "color": COLORS["text_muted"]}),
            *market_toggles,
        ], id="settings-market-metrics"),
        html.Div([
            html.Div("Super Scanners", style={**SETTINGS_TITLE_STYLE, "fontSize": "10px", "marginTop": "8px", "color": COLORS["text_muted"]}),
            *super_scanners_toggles,
        ], id="settings-super-scanners"),
        html.Div([
            html.Div("Intraday Inspector", style={**SETTINGS_TITLE_STYLE, "fontSize": "10px", "marginTop": "8px", "color": COLORS["text_muted"]}),
            *intraday_toggles,
        ], id="settings-intraday"),
    ], id="settings-drawer", style=SETTINGS_OVERLAY_STYLE_HIDDEN)


# -----------------------------------------------------------------------
# Full layout assembly
# -----------------------------------------------------------------------

def _initial_watchlist() -> list[str]:
    from pathlib import Path
    wl_path = Path(__file__).resolve().parent.parent / "watchlist.csv"
    if not wl_path.exists():
        return []
    lines = wl_path.read_text().strip().splitlines()
    return [l.strip().upper() for l in lines[1:] if l.strip()]


def _loading_wrap(content_id, children=None, style=None):
    """Wrap a content div in dcc.Loading so a spinner shows while its callback runs."""
    inner = html.Div(id=content_id, children=children or [], style=style or {})
    return dcc.Loading(
        inner,
        type="circle",
        color=COLORS["accent"],
        style={"minHeight": "40px"},
    )


def _intraday_loading_wrap(content_id: str):
    """Loading wrapper that fills compact intraday widget bodies (no 40px min gap)."""
    inner = html.Div(
        id=content_id,
        children=[],
        style={
            "minHeight": 0,
            "height": "100%",
            "flex": 1,
            "display": "flex",
            "flexDirection": "column",
            "overflow": "hidden",
        },
    )
    return dcc.Loading(
        inner,
        type="circle",
        color=COLORS["accent"],
        style={"minHeight": 0, "flex": 1, "display": "flex", "flexDirection": "column"},
    )


def _sortable_table_wrap(widget_id: str, default_sort_col: str = "change", default_sort_asc: bool = False):
    """Wrap content with data and sort stores for sortable tables.
    Default: sort by change descending (biggest gainers at top). Users can click headers to change."""
    return html.Div([
        dcc.Store(id=f"{widget_id}-data-store"),
        dcc.Store(id=f"{widget_id}-sort-store", data={"col": default_sort_col, "asc": default_sort_asc}),
        _loading_wrap(f"{widget_id}-content"),
    ])


def build_super_scanners_tab() -> html.Div:
    """FinViz / StockBee scanner widgets (moved from Market Metrics)."""
    return html.Div([
        html.Div([
            html.Div([
                _widget("qulla", "Qullamaggie",
                        _sortable_table_wrap("qulla"),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("qulla", True),
                        extra_header=html.Span([
                            _finviz_link("EP", "qullamaggie", {"marginLeft": "8px"}),
                            html.Span(" | ", style={"marginLeft": "2px", "marginRight": "2px", "color": COLORS["text_muted"]}),
                            _finviz_link("Breakouts", "qulla_breakouts"),
                            html.Span(" | ", style={"marginLeft": "2px", "marginRight": "2px", "color": COLORS["text_muted"]}),
                            _finviz_link("PS Small", "qulla_ps_small"),
                            html.Span(" | ", style={"marginLeft": "2px", "marginRight": "2px", "color": COLORS["text_muted"]}),
                            _finviz_link("PS Large", "qulla_ps_large"),
                        ])),
                _widget("minervini", "Minervini",
                        _sortable_table_wrap("minervini"),
                        variant="purple",
                        initial_hidden=not DEFAULT_VISIBILITY.get("minervini", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "minervini", {"marginLeft": "8px"}),
                        ])),
                _widget("oneil", "O'Neil",
                        _sortable_table_wrap("oneil"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("oneil", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "oneil", {"marginLeft": "8px"}),
                        ])),
            ], id="row-super-screeners", style=THIRD_ROW_STYLE),
            html.Div([
                _widget("jeff_sun_canslim", "Jeff Sun - CANSLIM",
                        _sortable_table_wrap("jeff_sun_canslim"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_canslim", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_canslim", {"marginLeft": "8px"}),
                        ])),
                _widget("jeff_sun_high_adr", "Jeff Sun - High ADR% Hottest Stock",
                        _sortable_table_wrap("jeff_sun_high_adr"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_high_adr", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_high_adr", {"marginLeft": "8px"}),
                        ])),
                _widget("jeff_sun_extended_bases", "Jeff Sun - Extended Bases",
                        _sortable_table_wrap("jeff_sun_extended_bases"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_extended_bases", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_extended_bases", {"marginLeft": "8px"}),
                        ])),
                _widget("jeff_sun_1w20", "Jeff Sun - 1W Mover +20%",
                        _sortable_table_wrap("jeff_sun_1w20"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_1w20", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_1w20", {"marginLeft": "8px"}),
                        ])),
            ], id="row-jeff-sun", style=QUARTER_ROW_STYLE),
            html.Div([
                _widget("jeff_sun_4w30", "Jeff Sun - 1M Mover +30%",
                        _sortable_table_wrap("jeff_sun_4w30"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_4w30", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_4w30", {"marginLeft": "8px"}),
                        ])),
                _widget("jeff_sun_4w50", "Jeff Sun - 1M Mover +50%",
                        _sortable_table_wrap("jeff_sun_4w50"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_4w50", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_4w50", {"marginLeft": "8px"}),
                        ])),
                _widget("jeff_sun_13w50", "Jeff Sun - 3M Mover +50%",
                        _sortable_table_wrap("jeff_sun_13w50"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_13w50", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_13w50", {"marginLeft": "8px"}),
                        ])),
                _widget("jeff_sun_26w100", "Jeff Sun - 6M Mover +100%",
                        _sortable_table_wrap("jeff_sun_26w100"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_26w100", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_26w100", {"marginLeft": "8px"}),
                        ])),
            ], id="row-jeff-sun-movers", style=QUARTER_ROW_STYLE),
            html.Div([
                _widget("jeff_sun_ipo_thisweek", "Jeff Sun - IPO",
                        _sortable_table_wrap("jeff_sun_ipo_thisweek"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_ipo_thisweek", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_ipo_thisweek", {"marginLeft": "8px"}),
                        ])),
                _widget("jeff_sun_high_short_float", "Jeff Sun - High Short Float",
                        _sortable_table_wrap("jeff_sun_high_short_float"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_high_short_float", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_high_short_float", {"marginLeft": "8px"}),
                        ])),
                _widget("jeff_sun_liquid_etfs", "Jeff Sun - Liquid ETF's",
                        _sortable_table_wrap("jeff_sun_liquid_etfs"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("jeff_sun_liquid_etfs", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "jeff_sun_liquid_etfs", {"marginLeft": "8px"}),
                        ])),
                _widget("julian_komar_strongest", "Julian Komar - Strongest Stocks",
                        _sortable_table_wrap("julian_komar_strongest"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("julian_komar_strongest", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "julian_komar_strongest", {"marginLeft": "8px"}),
                        ])),
            ], id="row-jeff-sun-weekly", style=QUARTER_ROW_STYLE),
            html.Div([
                _widget("club97", "97 Club",
                        html.Div([
                            dcc.Store(id="club97-data-store"),
                            dcc.Store(id="club97-sort-store", data={"col": "change", "asc": False}, storage_type="memory"),
                            _loading_wrap("club97-content"),
                        ]),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("club97", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "club97", {"marginLeft": "8px"}),
                        ])),
                _widget("movers", "StockBee - 9 Million Movers",
                        _sortable_table_wrap("movers"),
                        initial_hidden=not DEFAULT_VISIBILITY.get("movers", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "9m_movers", {"marginLeft": "8px"}),
                        ])),
                _widget("weekly", "StockBee - 20% Weekly Movers",
                        _sortable_table_wrap("weekly", default_sort_col="week", default_sort_asc=False),
                        variant="red",
                        initial_hidden=not DEFAULT_VISIBILITY.get("weekly", True),
                        extra_header=html.Span([
                            _finviz_link("+20", "20pct_weekly_up", {"marginLeft": "8px"}),
                            html.Span(" | ", style={"marginLeft": "2px", "marginRight": "2px", "color": COLORS["text_muted"]}),
                            _finviz_link("-20", "20pct_weekly_down"),
                        ], style={"marginLeft": "6px"})),
                _widget("daily", "StockBee - 4% Daily Gainers",
                        _sortable_table_wrap("daily"),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("daily", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "4pct_daily", {"marginLeft": "8px"}),
                        ])),
            ], id="row-super-middle4", style=QUARTER_ROW_STYLE),
            html.Div([
                _widget("earnings-calendar-week", "Earnings Calendar — This Week",
                        html.Div([
                            dcc.Store(id="earnings-calendar-week-data-store"),
                            dcc.Store(id="earnings-calendar-week-sort-store", data={"col": "market_cap", "asc": False}),
                            _loading_wrap("earnings-calendar-week-content"),
                        ]),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("earnings-calendar-week", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "earnings_this_week", {"marginLeft": "8px"}),
                        ])),
            ], id="row-super-earnings-week", style=WIDE_ROW_STYLE),
        ], style=CONTENT_AREA_STYLE),
    ])


def build_nav_sidebar() -> html.Div:
    """Collapsible left rail; updates main-tabs store (dcc.Tabs removed — no built-in tab strip)."""
    nav_btns = [
        ("should-i-trade", "Should I Trade?"),
        ("macro-monitor", "Macro Monitor"),
        ("market-metrics", "Market Metrics"),
        ("super-scanners", "Super Scanners"),
        ("intraday", "Intraday Inspector"),
    ]
    return html.Div(
        [
            html.Button(
                "☰",
                id="nav-sidebar-toggle",
                n_clicks=0,
                className="nav-sidebar-toggle",
                title="Collapse / expand sidebar",
            ),
            html.Div(
                [
                    html.Button(
                        label,
                        id=f"nav-tab-{value}",
                        n_clicks=0,
                        className=(
                            "nav-tab-btn nav-tab-active"
                            if value == "market-metrics"
                            else "nav-tab-btn"
                        ),
                    )
                    for value, label in nav_btns
                ],
                id="nav-sidebar-inner",
                className="nav-sidebar-inner",
            ),
        ],
        id="nav-sidebar",
        className="nav-sidebar",
    )


def build_layout() -> html.Div:
    loading = html.Div("Loading data...", style=LOADING_STYLE)
    empty_table = build_key_metrics_table({})

    return html.Div([
        dcc.Interval(id="interval-refresh", interval=3600_000, n_intervals=0),
        dcc.Interval(id="interval-live-snapshot", interval=300_000, n_intervals=0),
        dcc.Interval(id="market-hours-check", interval=60_000, n_intervals=0),
        dcc.Interval(id="interval-header-clock", interval=60_000, n_intervals=0),
        dcc.Interval(id="interval-chart-resize", interval=500, n_intervals=0, max_intervals=1),
        dcc.Store(id="watchlist-store", data=_initial_watchlist()),
        dcc.Store(id="chart-resize-trigger"),
        dcc.Store(id="main-tabs", data="market-metrics"),
        dcc.Download(id="download-watchlist-tv"),

        build_header(),
        build_settings_drawer(),
        build_tv_modal(),

        html.Div(
            [
                build_nav_sidebar(),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [build_should_i_trade_tab()],
                                    id="tab-pane-should-i-trade",
                                    className="pradly-tab-content-pane",
                                    style=_TAB_PANE_HIDE,
                                ),
                                html.Div(
                                    [build_macro_monitor_tab()],
                                    id="tab-pane-macro-monitor",
                                    className="pradly-tab-content-pane",
                                    style=_TAB_PANE_HIDE,
                                ),
                                html.Div(
                                    [
                        html.Div([
            # ---- PRIMARY ROW: full-size widgets ----
            html.Div([
                _widget("key-metrics", "Key Metrics",
                        _loading_wrap("key-metrics-content", [empty_table], style={"minHeight": "40px"}),
                        primary=True,
                        initial_hidden=not DEFAULT_VISIBILITY.get("key-metrics", True),
                        body_style=KEY_METRICS_BODY_STYLE,
                        card_style_override=WIDGET_KEY_METRICS_STYLE),
                _widget("chart2", "NQ100, SPY500 & DJIA Metrics",
                        _loading_wrap("chart2-content", [loading],
                                      style={**CHART_WRAP_STYLE, "height": f"{SCROLLABLE_BODY_HEIGHT}px", "overflow": "hidden"}),
                        variant="teal", primary=True,
                        initial_hidden=not DEFAULT_VISIBILITY.get("chart2", True),
                        body_style=RRG_CHART_BODY_STYLE),
                _widget("chart3", "RUS2000 & $1B+ Stocks",
                        _loading_wrap("chart3-content", [loading],
                                      style={**CHART_WRAP_STYLE, "height": f"{SCROLLABLE_BODY_HEIGHT}px", "overflow": "hidden"}),
                        variant="teal", primary=True,
                        initial_hidden=not DEFAULT_VISIBILITY.get("chart3", True),
                        body_style=RRG_CHART_BODY_STYLE),
            ], id="row-primary", style=PRIMARY_ROW_STYLE),

            # ---- STOCKBEE ROW (under Key Metrics): Breadth | Momentum50 ----
            html.Div([
                _widget("breadth", "StockBee Market Breadth Monitor",
                        _loading_wrap("breadth-content", [loading]),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth", True),
                        watchlist_export=False,
                        extra_header=html.Span([
                            _stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"}),
                        ])),
                _widget("stockbee", "Stockbee Momentum50",
                        html.Div([
                            dcc.Store(id="stockbee-data-store"),
                            dcc.Store(id="stockbee-sort-store", data={"col": None, "asc": True}),
                            _loading_wrap("stockbee-content", [loading]),
                        ]),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("stockbee", True),
                        extra_header=html.Span([
                            _stockbee_link("Sheet", "momentum50", {"marginLeft": "8px"}),
                        ])),
            ], id="row-stockbee", style=HALF_ROW_STYLE),

            # ---- BREADTH CHARTS ROW (Stockbee-style) ----
            html.Div([
                _widget("breadth-primary", "StockBee - Primary Breadth — Up/Down 4%+ Today",
                        _loading_wrap("breadth-primary-content", [loading], style=BREADTH_CHART_WRAP_STYLE),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth-primary", True),
                        watchlist_export=False,
                        body_style=BREADTH_CHART_BODY_STYLE,
                        extra_header=html.Span([_stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"})])),
                _widget("breadth-ratios", "StockBee - Breadth Ratios — 5-Day & 10-Day",
                        _loading_wrap("breadth-ratios-content", [loading], style=BREADTH_CHART_WRAP_STYLE),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth-ratios", True),
                        watchlist_export=False,
                        body_style=BREADTH_CHART_BODY_STYLE,
                        extra_header=html.Span([_stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"})])),
                _widget("breadth-secondary", "StockBee - Secondary Breadth — Up/Down 25%+ Qtr",
                        _loading_wrap("breadth-secondary-content", [loading], style=BREADTH_CHART_WRAP_STYLE),
                        variant="purple",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth-secondary", True),
                        watchlist_export=False,
                        body_style=BREADTH_CHART_BODY_STYLE,
                        extra_header=html.Span([_stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"})])),
                _widget("breadth-sp500", "StockBee - S&P 500 — Last 60 Days",
                        _loading_wrap("breadth-sp500-content", [loading], style=BREADTH_CHART_WRAP_STYLE),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth-sp500", True),
                        watchlist_export=False,
                        body_style=BREADTH_CHART_BODY_STYLE,
                        extra_header=html.Span([_stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"})])),
            ], id="row-breadth-charts", style=QUARTER_ROW_STYLE),

            # ---- BUBBLE CHART (moved to former watchlist slot) ----
            html.Div([
                _widget("sp500-landscape", "S&P 500 Landscape Bubble Chart",
                        html.Div([
                            dcc.Store(id="sp500-landscape-data-store"),
                            html.Div([
                                html.Label("Sector filter:", style={"fontSize": "10px", "color": COLORS["text_muted"], "marginRight": "6px"}),
                                dcc.Dropdown(
                                    id="sp500-landscape-sector-filter",
                                    options=[],
                                    value=[],
                                    multi=True,
                                    placeholder="All sectors",
                                    clearable=True,
                                    style={"minWidth": "180px", "fontSize": "10px"},
                                ),
                            ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px", "flexWrap": "wrap"}),
                            dcc.Loading(
                                html.Div(id="sp500-landscape-content", children=[loading], style={**CHART_WRAP_STYLE, "height": f"{SP500_LANDSCAPE_CHART_HEIGHT}px", "overflow": "hidden"}),
                                type="circle", color=COLORS["accent"], style={"minHeight": "40px"},
                            ),
                        ], style={"height": f"{SCROLLABLE_BODY_HEIGHT}px", "overflow": "hidden", "display": "flex", "flexDirection": "column"}),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("sp500-landscape", True),
                        body_style=RRG_CHART_BODY_STYLE),
            ], id="row-screeners", style=WIDE_ROW_STYLE),

            # ---- SECTOR + RRG ROW ----
            html.Div([
                _widget("sector", "Sector SPDR ETFs",
                        html.Div([
                            dcc.Store(id="sector-data-store"),
                            dcc.Store(id="sector-sort-store", data={"col": "chg", "asc": False}),
                            _loading_wrap("sector-content", [loading]),
                        ]),
                        initial_hidden=not DEFAULT_VISIBILITY.get("sector", True)),
                _widget("rrg", "RRG Sector Rotation (vs " + RRG_BENCHMARK + ")",
                        html.Div([
                            dcc.Store(id="rrg-figure-store"),
                            dcc.Loading(
                                html.Div(id="rrg-content", children=[loading], style={**CHART_WRAP_STYLE, "height": f"{SCROLLABLE_BODY_HEIGHT}px", "overflow": "hidden"}),
                                type="circle", color=COLORS["accent"], style={"minHeight": "40px"},
                            ),
                        ], style={"height": f"{SCROLLABLE_BODY_HEIGHT}px", "overflow": "hidden"}),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("rrg", True),
                        body_style=RRG_CHART_BODY_STYLE),
                _widget("watchlist", "Watchlist",
                        build_watchlist_body(),
                        initial_hidden=not DEFAULT_VISIBILITY.get("watchlist", True)),
            ], id="row-sector", style=THIRD_ROW_STYLE),

            # ---- LEADING + STAGE (earnings this week → Super Scanners tab) ----
            html.Div([
                _widget("leading", "Leading Industries — Top 20%",
                        html.Div([
                            dcc.Store(id="leading-data-store"),
                            dcc.Store(id="leading-sort-store", data={"col": "top_both", "asc": False}),
                            _loading_wrap("leading-content", [loading]),
                        ]),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("leading", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "leading", {"marginLeft": "8px"}),
                        ])),
                _widget("stage", "Stage Analysis",
                        _loading_wrap("stage-content", [loading],
                                      style={**CHART_WRAP_STYLE, "height": f"{SCROLLABLE_BODY_HEIGHT}px", "overflow": "hidden"}),
                        initial_hidden=not DEFAULT_VISIBILITY.get("stage", True),
                        body_style=RRG_CHART_BODY_STYLE),
            ], id="row-bottom", style=HALF_ROW_STYLE),

            # ---- THEMATICS ROW ----
            html.Div([
                _widget("thematics", "Thematics Tracker — Top 20%",
                        html.Div([
                            dcc.Store(id="thematics-data-store"),
                            dcc.Store(id="thematics-sort-store", data={"col": "top_both", "asc": False}),
                            _loading_wrap("thematics-content", [loading]),
                        ]),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("thematics", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "thematics", {"marginLeft": "8px"}),
                        ])),
                _widget("thematics-sector", "Thematics by Sector — Top YTD",
                        html.Div([
                            dcc.Store(id="thematics-sector-data-store"),
                            dcc.Store(id="thematics-sector-sort-store", data={"col": "year", "asc": False}),
                            _loading_wrap("thematics-sector-content", [loading]),
                        ]),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("thematics-sector", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "thematics", {"marginLeft": "8px"}),
                        ])),
                _widget("thematics-rrg", "Thematics RRG (vs " + RRG_BENCHMARK + ")",
                        html.Div([
                            dcc.Store(id="thematics-rrg-figure-store"),
                            dcc.Loading(
                                html.Div(id="thematics-rrg-content", children=[loading], style={**CHART_WRAP_STYLE, "height": f"{SCROLLABLE_BODY_HEIGHT}px", "overflow": "hidden"}),
                                type="circle", color=COLORS["accent"], style={"minHeight": "40px"},
                            ),
                        ], style={"height": f"{SCROLLABLE_BODY_HEIGHT}px", "overflow": "hidden"}),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("thematics-rrg", True),
                        body_style=RRG_CHART_BODY_STYLE),
            ], id="row-thematics", style=THIRD_ROW_STYLE),
        ], style=CONTENT_AREA_STYLE),
                                    ],
                                    id="tab-pane-market-metrics",
                                    className="pradly-tab-content-pane",
                                    style=_TAB_PANE_SHOW,
                                ),
                                html.Div(
                                    [build_super_scanners_tab()],
                                    id="tab-pane-super-scanners",
                                    className="pradly-tab-content-pane",
                                    style=_TAB_PANE_HIDE,
                                ),
                                html.Div(
                                    [
                        html.Div([
                        html.Div([
                            _widget("live_index", "Market Snapshot",
                                    _intraday_loading_wrap("live_index-content"),
                                    variant="teal",
                                    initial_hidden=not DEFAULT_VISIBILITY.get("live_index", True),
                                    body_style=INTRADAY_SNAPSHOT_BODY_STYLE,
                                    card_style_override=INTRADAY_INDEX_ROW_CARD_STYLE),
                            _widget("top_gainers", "Top Gainers",
                                    _intraday_loading_wrap("top_gainers-content"),
                                    variant="teal",
                                    initial_hidden=not DEFAULT_VISIBILITY.get("top_gainers", True),
                                    body_style=INTRADAY_TOP_MOVERS_BODY_STYLE,
                                    card_style_override=INTRADAY_INDEX_ROW_CARD_STYLE,
                                    extra_header=html.Span([
                                        _finviz_link("FinViz", "thematics", {"marginLeft": "8px"}),
                                    ])),
                            _widget("top_losers", "Top Losers",
                                    _intraday_loading_wrap("top_losers-content"),
                                    variant="teal",
                                    initial_hidden=not DEFAULT_VISIBILITY.get("top_losers", True),
                                    body_style=INTRADAY_TOP_MOVERS_BODY_STYLE,
                                    card_style_override=INTRADAY_INDEX_ROW_CARD_STYLE,
                                    extra_header=html.Span([
                                        _finviz_link("FinViz", "thematics", {"marginLeft": "8px"}),
                                    ])),
                        ], id="row-intraday-snapshot", style=SNAPSHOT_MOVERS_ROW_STYLE),
                        html.Div([
                            _widget("in_play", "Stocks In Play",
                                    _sortable_table_wrap("in_play"),
                                    variant="teal",
                                    initial_hidden=not DEFAULT_VISIBILITY.get("in_play", True),
                                    extra_header=html.Span([
                                        _finviz_link("FinViz", "stocks_in_play", {"marginLeft": "8px"}),
                                    ])),
                            _widget("intraday-earnings", "Earnings Yesterday + Today",
                                    _sortable_table_wrap("intraday-earnings"),
                                    variant="orange",
                                    initial_hidden=not DEFAULT_VISIBILITY.get("intraday-earnings", True),
                                    extra_header=html.Span([
                                        _finviz_link("FinViz", "earnings_yesterday_today", {"marginLeft": "8px"}),
                                    ])),
                        ], id="row-intraday-earnings", style=HALF_ROW_STYLE),
                        html.Div([
                            _widget("pre_market", "Pre-market Scanner",
                                    _sortable_table_wrap("pre_market", default_sort_col="Gap", default_sort_asc=False),
                                    variant="teal",
                                    initial_hidden=not DEFAULT_VISIBILITY.get("pre_market", True),
                                    extra_header=html.Span([
                                        _finviz_link("+3%", "pre_market_scanner", {"marginRight": "6px"}),
                                        html.Span(" | ", style={"color": COLORS["text_faint"], "fontSize": "8px", "margin": "0 2px"}),
                                        _finviz_link("-3%", "pre_market_scanner_down"),
                                    ])),
                        ], style=WIDE_ROW_STYLE),
                        html.Div([
                            _widget("cnbc_premarket", "CNBC Pre-Market Watchlist",
                                    _loading_wrap("cnbc_premarket-content"),
                                    variant="teal",
                                    initial_hidden=not DEFAULT_VISIBILITY.get("cnbc_premarket", True),
                                    extra_header=html.Span([
                                        html.A("Market Insider", href="https://www.cnbc.com/market-insider/",
                                               target="_blank", rel="noopener noreferrer",
                                               style={"fontSize": "8px", "fontWeight": 500, "color": COLORS["accent"],
                                                      "textDecoration": "none", "marginLeft": "8px"}),
                                    ])),
                        ], style=WIDE_ROW_STYLE),
                        ], style=CONTENT_AREA_STYLE),
                    ],
                                    id="tab-pane-intraday",
                                    className="pradly-tab-content-pane",
                                    style=_TAB_PANE_HIDE,
                                ),
                            ],
                        ),
                    ],
                    id="app-main-tabs-host",
                    style={
                        "flex": "1",
                        "minWidth": "0",
                        "minHeight": "0",
                        "display": "flex",
                        "flexDirection": "column",
                        "overflow": "hidden",
                    },
                ),
            ],
            id="app-layout-row",
            style={
                "display": "flex",
                "flexDirection": "row",
                "flex": "1",
                "minHeight": "0",
                "overflow": "hidden",
                "width": "100%",
            },
        ),

    ], style=DASHBOARD_STYLE)
