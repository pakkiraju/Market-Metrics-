"""Dash layout: widget-based Bloomberg-terminal-style dashboard.

All sections are toggleable widgets. Key Metrics, NASDAQ/S&P chart, and
Combined chart are full-size (no internal scroll). Other widgets have
max-height with internal scroll. Clicking any ticker opens a TradingView
chart modal. Watchlist supports user add/remove.
"""

from datetime import datetime, timezone, timedelta

from dash import html, dcc
import plotly.graph_objects as go

from src.constants import (
    COLORS, KEY_METRIC_ROWS, INDEX_GROUPS, SECTOR_NAMES,
    STAGE_BAR_COLORS, STAGE_LABELS, FINVIZ_SCREENER_URLS,
    build_metric_screener_url, RRG_BENCHMARK, RRG_COLORS,
    STOCKBEE_LINKS,
)
from src.styles import (
    DASHBOARD_STYLE, HEADER_STYLE, HEADER_LOGO_STYLE,
    HEADER_DATE_STYLE, MARKET_STATUS_STYLE_CLOSED, REFRESH_BTN_STYLE,
    SETTINGS_BTN_STYLE,
    CONTENT_AREA_STYLE,
    PRIMARY_ROW_STYLE, QUARTER_ROW_STYLE, WIDE_ROW_STYLE, HALF_ROW_STYLE,
    WIDGET_STYLE, WIDGET_PRIMARY_STYLE, WIDGET_SECONDARY_STYLE, WIDGET_KEY_METRICS_STYLE,
    section_header_style, SECTION_BODY_STYLE, KEY_METRICS_BODY_STYLE,
    TICKER_GRID_STYLE, ticker_pill_style,
    TABLE_STYLE, TABLE_HEADER_STYLE, TABLE_CELL_STYLE,
    CHART_WRAP_STYLE, LOADING_STYLE,
    SETTINGS_OVERLAY_STYLE_HIDDEN, SETTINGS_TITLE_STYLE,
    SETTINGS_ITEM_STYLE, TOGGLE_LABEL_STYLE,
    stage_badge_style,
)
from src.constants import pct_color, chg_color

ET = timezone(timedelta(hours=-5))

# Widget registry: (id_suffix, display_name, is_primary_size)
# is_primary_size only controls sizing (full-size vs max-height), NOT toggleability
WIDGETS = [
    ("key-metrics",    "Key Metrics",                True),
    ("chart2",         "NQ100, SPY500 & DJIA Metrics", True),
    ("chart3",         "RUS2000 & $1B+ Stocks", True),
    ("qulla",          "Qullamaggie",                False),
    ("minervini",      "Minervini",                  False),
    ("oneil",          "O'Neil",                     False),
    ("watchlist",      "Watchlist",                  False),
    ("sector",         "Sector SPDR ETFs",           False),
    ("rrg",            "RRG Sector Rotation",        False),
    ("club97",         "97 Club",                    False),
    ("movers",         "StockBee - 9 Million Movers",           False),
    ("weekly",         "StockBee - 20% Weekly Movers",          False),
    ("daily",          "StockBee - 4% Daily Gainers",           False),
    ("leading",        "Leading Industries",         False),
    ("stockbee",       "Stockbee Momentum50",        False),
    ("breadth",        "StockBee Market Breadth Monitor", False),
    ("breadth-primary", "StockBee - Primary Breadth — Up/Down 4%+ Today", False),
    ("breadth-ratios", "StockBee - Breadth Ratios — 5-Day & 10-Day", False),
    ("breadth-secondary", "StockBee - Secondary Breadth — Up/Down 25%+ Qtr", False),
    ("breadth-sp500",  "StockBee - S&P 500 — Last 60 Days",    False),
    ("stage",          "Stage Analysis",             False),
]

ALL_WIDGET_IDS = [w[0] for w in WIDGETS]
# Key Metrics + bar charts + Qullamaggie + Minervini + O'Neil + Watchlist + Sector SPDR + 97 Club + 9M Movers + 20% Weekly + 4% Daily + Leading Industries enabled by default
DEFAULT_VISIBILITY = {
    w[0]: w[0] in ("key-metrics", "chart2", "chart3", "qulla", "minervini", "oneil", "watchlist", "sector", "rrg", "club97", "movers", "weekly", "daily", "leading", "stockbee", "breadth", "breadth-primary", "breadth-ratios", "breadth-secondary", "breadth-sp500", "stage") for w in WIDGETS
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

def _widget(widget_id, header_text, body_children, variant="default",
            count=None, extra_header=None, primary=False, initial_hidden=False,
            body_style=None, card_style_override=None):
    header_kids = [html.Span(header_text)]
    if count is not None:
        header_kids.append(html.Span(
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
        header_kids.append(extra_header)

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


def _table(headers, rows, col_widths=None):
    ths = []
    for i, h in enumerate(headers):
        st = {**TABLE_HEADER_STYLE}
        if col_widths and i < len(col_widths):
            st["width"] = col_widths[i]
        ths.append(html.Th(h, style=st))

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
        height=420,
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


def _build_screener_table(data: list[dict]) -> html.Table:
    """Shared table for screener data: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %."""
    headers = ["Ticker", "Price", "Avg Vol", "Rel Vol", "Change", "Vol", "ATR %"]
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
    return _table(headers, rows, col_widths=["70px", "55px", "65px", "55px", "55px", "65px", "55px"])


def build_minervini_table(data: list[dict]) -> html.Table:
    """Minervini screener: Ticker, Price, Avg Vol, Rel Vol, Change, Vol."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data)


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


def build_qullamaggie_table(data: list[dict]) -> html.Table:
    """Qullamaggie: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %, Tag."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    headers = ["Ticker", "Price", "Avg Vol", "Rel Vol", "Change", "Vol", "ATR %", "Tag"]
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
    return _table(headers, rows, col_widths=["70px", "55px", "65px", "55px", "55px", "65px", "55px", "55px"])


def build_watchlist_table(data: list[dict]) -> html.Table:
    """Watchlist: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %, Remove."""
    if not data:
        return html.Div("No tickers in watchlist. Add some above.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    headers = ["Ticker", "Price", "Avg Vol", "Rel Vol", "Change", "Vol", "ATR %", ""]
    rows = []
    for r in data:
        chg_val = r.get("change")
        try:
            chg_num = float(str(chg_val).replace("%", "")) if chg_val not in (None, "") else 0
        except (ValueError, TypeError):
            chg_num = 0
        vol_str, avg_str = _format_screener_vol(r.get("volume"), r.get("avg_vol"))
        t = r["ticker"]
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
        rows.append([
            {"text": _clickable_ticker(t, {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            str(r.get("price", "")),
            avg_str,
            str(r.get("rel_vol", "")),
            {"text": f"{chg_num}%" if chg_val not in (None, "") else "",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(chg_num), "fontWeight": 600}},
            vol_str,
            f"{r.get('atr_pct', 0):.2f}%" if r.get("atr_pct") is not None else "",
            {"text": remove_btn, "style": {**TABLE_CELL_STYLE, "width": "24px", "padding": "2px"}},
        ])
    return _table(
        headers,
        rows,
        col_widths=["70px", "55px", "65px", "55px", "55px", "65px", "55px", "28px"],
    )


def build_oneil_table(data: list[dict]) -> html.Table:
    """O'Neil / CANSLIM screener: Ticker, Price, Avg Vol, Rel Vol, Change, Vol, ATR %, ROE, Net Margin."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    headers = ["Ticker", "Price", "Avg Vol", "Rel Vol", "Change", "Vol", "ATR %", "ROE", "Net Margin"]
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
    )


# -----------------------------------------------------------------------
# Section 8: Sector SPDR table (clickable tickers)
# -----------------------------------------------------------------------

def build_sector_table(sector_data: list[dict]) -> html.Table:
    headers = [
        "Sector", "Ticker", "Gap", "Chg", "O Chg", "Week", "Month",
        "Qtr", "H.Year", "Year", "Last", "EMA10", "SMA20", "SMA50",
        "SMA200", "52W Hi", "52W Lo", "ATR %",
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

    return _table(headers, rows)


# -----------------------------------------------------------------------
# Section 9: 97 Club table (clickable tickers)
# -----------------------------------------------------------------------

def build_97_club_table(club_data: list[dict]) -> html.Table:
    """97 Club: same layout as Minervini (Ticker, Price, Avg Vol, Rel Vol, Change, Vol) from export URL."""
    if not club_data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(club_data)


# -----------------------------------------------------------------------
# Sections 10-12: Stockbee tables (clickable tickers)
# -----------------------------------------------------------------------

def build_9m_movers_table(data: list[dict]) -> html.Table:
    """9M Movers: same layout as Minervini (Ticker, Price, Avg Vol, Rel Vol, Change, Vol) from export URL."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    return _build_screener_table(data)


def build_20pct_weekly_table(data: list[dict]) -> html.Table:
    """20% Weekly Movers: Ticker, Week %, Price, Avg Vol, Rel Vol, Chg, Vol, ATR %."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    headers = ["Ticker", "Week", "Price", "Avg Vol", "Rel Vol", "Chg", "Vol", "ATR %"]
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
    return _table(headers, rows, col_widths=["70px", "55px", "55px", "65px", "55px", "55px", "65px", "55px"])


def build_4pct_daily_table(data: list[dict]) -> html.Table:
    """4% Daily Gainers: Ticker, Chg, Price, Avg Vol, Rel Vol, Vol, ATR %."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    headers = ["Ticker", "Chg", "Price", "Avg Vol", "Rel Vol", "Vol", "ATR %"]
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
    return _table(headers, rows, col_widths=["70px", "55px", "55px", "65px", "55px", "65px", "55px"])


# -----------------------------------------------------------------------
# Section 13: Leading Industries (clickable tickers)
# -----------------------------------------------------------------------

def build_leading_industries_table(data: list[dict]) -> html.Table:
    headers = ["Industry", "1st", "2nd", "3rd", "4th"]
    rows = []
    for r in data:
        ind_color = COLORS["green_light"] if r.get("top_both") else COLORS["text_muted"]
        row_bg = "rgba(34,197,94,0.08)" if r.get("top_both") else "transparent"
        row = [
            {"text": r["industry"], "style": {
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
    return _table(headers, rows, col_widths=["200px", None, None, None, None])


# -----------------------------------------------------------------------
# Stockbee Momentum50 (Pradeep Bonde)
# -----------------------------------------------------------------------

def build_stockbee_momentum50_table(data: list[dict], date_label: str = "") -> html.Div:
    """Stockbee Momentum50: ticker table with FinViz quotes. Same layout as Minervini."""
    if not data:
        return html.Div("No Momentum50 data. Check Stockbee sheet.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    table = _build_screener_table(data)
    children = [table]
    if date_label:
        children.insert(0, html.Span(date_label, style={"fontSize": "9px", "color": COLORS["text_muted"], "marginBottom": "4px"}))
    return html.Div(children, style={"display": "flex", "flexDirection": "column", "gap": "4px"})


# -----------------------------------------------------------------------
# Stock Market Breadth Monitor
# -----------------------------------------------------------------------

def _breadth_chart_layout():
    """Shared layout for breadth charts."""
    return dict(
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=4, r=4, t=4, b=4),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=8)),
        xaxis=dict(
            tickfont=dict(size=8, color=COLORS["text_muted"]),
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
        ),
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
    fig.update_layout(**_breadth_chart_layout())
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
    fig.update_layout(**_breadth_chart_layout())
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
    fig.update_layout(**_breadth_chart_layout())
    return fig


def build_sp500_chart(history: list[dict]) -> go.Figure:
    """S&P 500 — Last 60 Trading Days."""
    if not history:
        return go.Figure()
    dates = [h["date"] for h in history]
    sp500 = [h.get("sp500", 0) for h in history]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=sp500, name="S&P 500", fill="tozeroy",
        line=dict(color=COLORS["accent"], width=2),
        fillcolor=_hex_to_rgba(COLORS["accent"], 0.15)))
    fig.update_layout(**_breadth_chart_layout())
    return fig


def build_stockbee_breadth(breadth: dict | None) -> html.Div:
    """Stockbee-style breadth metric cards: S&P 500, T2108, 5-Day Ratio, 10-Day Ratio, Up 4%+, Down 4%+."""
    if not breadth:
        return html.Div("Breadth data unavailable. Start Stockbee API or check Sheets.", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
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
            html.Div(label, style={"fontSize": "8px", "color": COLORS["text_muted"], "marginBottom": "2px"}),
            html.Div(str(value), style={"fontSize": "11px", "fontWeight": 700, "color": color}),
            html.Div(sub, style={"fontSize": "8px", "color": COLORS["text_faint"], "marginTop": "2px"}),
        ], style={
            "padding": "6px 8px", "borderRadius": "4px", "background": COLORS["surface2"],
            "border": f"1px solid {COLORS['border']}",
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
        "display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "6px",
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
        height=280,
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
    """RRG scatter: one trace per sector with distinct color. Tail: year → hyear → qtr → month → week → today."""
    if not rrg_data:
        return go.Figure()

    has_tails = "tail" in rrg_data[0]
    fig = go.Figure()

    for i, r in enumerate(rrg_data):
        color = RRG_COLORS[i % len(RRG_COLORS)]
        xs, ys = [r["rs_ratio"]], [r["rs_momentum"]]
        if has_tails:
            for tx, ty in reversed(r["tail"]):
                xs.insert(0, tx)
                ys.insert(0, ty)
        # Text only at head (last point)
        text_vals = [""] * (len(xs) - 1) + [r["ticker"]]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines+markers+text",
            text=text_vals, textposition="top center",
            textfont=dict(size=9, color=color),
            line=dict(color=color, width=2, shape="spline", smoothing=0.3),
            marker=dict(size=10, color=color, line=dict(width=1, color=COLORS["border"]), symbol="circle"),
            name=r["name"],
            customdata=[r["name"]] * len(xs),
            hovertemplate="%{customdata} (%{text})<br>RS-Ratio: %{x:.1f}<br>RS-Momentum: %{y:.1f}<extra></extra>",
        ))

    # Quadrant lines at 100; extend range to include all points
    all_x, all_y = [], []
    for r in rrg_data:
        all_x.append(r["rs_ratio"])
        all_y.append(r["rs_momentum"])
        if has_tails:
            for tx, ty in r["tail"]:
                all_x.append(tx)
                all_y.append(ty)
    x_range = [min(all_x) - 5, max(all_x) + 5] if all_x else [90, 110]
    y_range = [min(all_y) - 5, max(all_y) + 5] if all_y else [90, 110]
    fig.add_vline(x=100, line_dash="dot", line_color=COLORS["border_light"], opacity=0.6)
    fig.add_hline(y=100, line_dash="dot", line_color=COLORS["border_light"], opacity=0.6)
    fig.update_layout(
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
        height=340,
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


def build_stage_summary(counts: dict) -> html.Div:
    stage2_total = counts.get("2A", 0) + counts.get("2B", 0) + counts.get("2C", 0)
    bullish = stage2_total > (counts.get("3", 0) + counts.get("4", 0))

    items = [
        html.Span([
            html.Span("Stage 1: ", style={"color": COLORS["text_muted"]}),
            html.Span(str(counts.get("1", 0)), style={"fontWeight": 700}),
        ]),
        html.Span([
            html.Span("Stage 2: ", style={"color": COLORS["text_muted"]}),
            html.Span(str(stage2_total),
                       style={"fontWeight": 700, "color": COLORS["green"]}),
        ]),
        html.Span([
            html.Span("Stage 3: ", style={"color": COLORS["text_muted"]}),
            html.Span(str(counts.get("3", 0)),
                       style={"fontWeight": 700, "color": COLORS["red"]}),
        ]),
        html.Span([
            html.Span("Stage 4: ", style={"color": COLORS["text_muted"]}),
            html.Span(str(counts.get("4", 0)),
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
        ], style={
            "display": "flex", "gap": "4px", "padding": "4px 4px 2px 4px",
            "alignItems": "center",
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
    now = datetime.now(ET)
    date_str = now.strftime("%A, %B %d, %Y")

    is_weekday = now.weekday() < 5
    t = now.hour * 60 + now.minute
    is_open = is_weekday and 9 * 60 + 30 <= t < 16 * 60

    return html.Div([
        html.Div([
            html.Span("Market Metrics", style=HEADER_LOGO_STYLE),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
        html.Div([
            html.Span(date_str, id="header-date", style=HEADER_DATE_STYLE),
            html.Span(
                "OPEN" if is_open else "CLOSED",
                id="market-status",
                style=MARKET_STATUS_STYLE_CLOSED if not is_open else {
                    **MARKET_STATUS_STYLE_CLOSED,
                    "backgroundColor": COLORS["green_cell"],
                    "color": COLORS["green_light"],
                },
            ),
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
# Settings drawer (ALL widgets toggleable)
# -----------------------------------------------------------------------

def build_settings_drawer() -> html.Div:
    toggle_items = []
    for wid, name, _ in WIDGETS:
        toggle_items.append(html.Div([
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
        ], style=SETTINGS_ITEM_STYLE))

    return html.Div([
        html.Div("Widget Settings", style=SETTINGS_TITLE_STYLE),
        *toggle_items,
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


def build_layout() -> html.Div:
    loading = html.Div("Loading data...", style=LOADING_STYLE)
    empty_table = build_key_metrics_table({})

    return html.Div([
        dcc.Interval(id="interval-refresh", interval=300_000, n_intervals=0),
        dcc.Store(id="watchlist-store", data=_initial_watchlist()),

        build_header(),
        build_settings_drawer(),
        build_tv_modal(),

        html.Div([
            # ---- PRIMARY ROW: full-size widgets ----
            html.Div([
                _widget("key-metrics", "Key Metrics",
                        html.Div(id="key-metrics-content", children=[empty_table], style={"minHeight": "40px"}),
                        primary=True,
                        initial_hidden=not DEFAULT_VISIBILITY.get("key-metrics", True),
                        body_style=KEY_METRICS_BODY_STYLE,
                        card_style_override=WIDGET_KEY_METRICS_STYLE),
                _widget("chart2", "NQ100, SPY500 & DJIA Metrics",
                        _loading_wrap("chart2-content", [loading],
                                      style=CHART_WRAP_STYLE),
                        variant="teal", primary=True,
                        initial_hidden=not DEFAULT_VISIBILITY.get("chart2", True)),
                _widget("chart3", "RUS2000 & $1B+ Stocks",
                        _loading_wrap("chart3-content", [loading],
                                      style=CHART_WRAP_STYLE),
                        variant="teal", primary=True,
                        initial_hidden=not DEFAULT_VISIBILITY.get("chart3", True)),
            ], id="row-primary", style=PRIMARY_ROW_STYLE),

            # ---- STOCKBEE ROW (under Key Metrics): Breadth | Momentum50 ----
            html.Div([
                _widget("breadth", "StockBee Market Breadth Monitor",
                        _loading_wrap("breadth-content", [loading]),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth", True),
                        extra_header=html.Span([
                            _stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"}),
                        ])),
                _widget("stockbee", "Stockbee Momentum50",
                        _loading_wrap("stockbee-content", [loading]),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("stockbee", True),
                        extra_header=html.Span([
                            _stockbee_link("Sheet", "momentum50", {"marginLeft": "8px"}),
                        ])),
            ], id="row-stockbee", style=HALF_ROW_STYLE),

            # ---- BREADTH CHARTS ROW (Stockbee-style) ----
            html.Div([
                _widget("breadth-primary", "StockBee - Primary Breadth — Up/Down 4%+ Today",
                        _loading_wrap("breadth-primary-content", [loading], style=CHART_WRAP_STYLE),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth-primary", True),
                        extra_header=html.Span([_stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"})])),
                _widget("breadth-ratios", "StockBee - Breadth Ratios — 5-Day & 10-Day",
                        _loading_wrap("breadth-ratios-content", [loading], style=CHART_WRAP_STYLE),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth-ratios", True),
                        extra_header=html.Span([_stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"})])),
                _widget("breadth-secondary", "StockBee - Secondary Breadth — Up/Down 25%+ Qtr",
                        _loading_wrap("breadth-secondary-content", [loading], style=CHART_WRAP_STYLE),
                        variant="purple",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth-secondary", True),
                        extra_header=html.Span([_stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"})])),
                _widget("breadth-sp500", "StockBee - S&P 500 — Last 60 Days",
                        _loading_wrap("breadth-sp500-content", [loading], style=CHART_WRAP_STYLE),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("breadth-sp500", True),
                        extra_header=html.Span([_stockbee_link("Monitor", "market_monitor", {"marginLeft": "8px"})])),
            ], id="row-breadth-charts", style=QUARTER_ROW_STYLE),

            # ---- SCREENERS ROW (4 across) ----
            html.Div([
                _widget("qulla", "Qullamaggie",
                        _loading_wrap("qulla-content"),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("qulla", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "qullamaggie", {"marginLeft": "8px"}),
                        ])),
                _widget("minervini", "Minervini",
                        _loading_wrap("minervini-content"),
                        variant="purple",
                        initial_hidden=not DEFAULT_VISIBILITY.get("minervini", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "minervini", {"marginLeft": "8px"}),
                        ])),
                _widget("oneil", "O'Neil",
                        _loading_wrap("oneil-content"),
                        variant="orange",
                        initial_hidden=not DEFAULT_VISIBILITY.get("oneil", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "oneil", {"marginLeft": "8px"}),
                        ])),
                _widget("watchlist", "Watchlist",
                        build_watchlist_body(),
                        initial_hidden=not DEFAULT_VISIBILITY.get("watchlist", True)),
            ], id="row-screeners", style=QUARTER_ROW_STYLE),

            # ---- SECTOR + RRG ROW ----
            html.Div([
                _widget("sector", "Sector SPDR ETFs",
                        _loading_wrap("sector-content", [loading]),
                        initial_hidden=not DEFAULT_VISIBILITY.get("sector", True)),
                _widget("rrg", "RRG Sector Rotation (vs " + RRG_BENCHMARK + ")",
                        html.Div([
                            dcc.Store(id="rrg-figure-store"),
                            dcc.Loading(
                                html.Div(id="rrg-content", children=[loading], style=CHART_WRAP_STYLE),
                                type="circle", color=COLORS["accent"], style={"minHeight": "40px"},
                            ),
                        ], style={"minHeight": "340px"}),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("rrg", True)),
            ], id="row-sector", style=HALF_ROW_STYLE),

            # ---- MIDDLE 4 ----
            html.Div([
                _widget("club97", "97 Club",
                        _loading_wrap("club97-content", [loading]),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("club97", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "club97", {"marginLeft": "8px"}),
                        ])),
                _widget("movers", "StockBee - 9 Million Movers",
                        _loading_wrap("movers-content", [loading]),
                        initial_hidden=not DEFAULT_VISIBILITY.get("movers", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "9m_movers", {"marginLeft": "8px"}),
                        ])),
                _widget("weekly", "StockBee - 20% Weekly Movers",
                        _loading_wrap("weekly-content", [loading]),
                        variant="red",
                        initial_hidden=not DEFAULT_VISIBILITY.get("weekly", True),
                        extra_header=html.Span([
                            _finviz_link("+20", "20pct_weekly_up", {"marginLeft": "8px"}),
                            html.Span(" | ", style={"marginLeft": "2px", "marginRight": "2px", "color": COLORS["text_muted"]}),
                            _finviz_link("-20", "20pct_weekly_down"),
                        ], style={"marginLeft": "6px"})),
                _widget("daily", "StockBee - 4% Daily Gainers",
                        _loading_wrap("daily-content", [loading]),
                        variant="green",
                        initial_hidden=not DEFAULT_VISIBILITY.get("daily", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "4pct_daily", {"marginLeft": "8px"}),
                        ])),
            ], id="row-middle4", style=QUARTER_ROW_STYLE),

            # ---- BOTTOM ROW ----
            html.Div([
                _widget("leading", "Leading Industries — Top 20%",
                        _loading_wrap("leading-content", [loading]),
                        variant="teal",
                        initial_hidden=not DEFAULT_VISIBILITY.get("leading", True),
                        extra_header=html.Span([
                            _finviz_link("FinViz", "leading", {"marginLeft": "8px"}),
                        ])),
                _widget("stage", "Stage Analysis",
                        _loading_wrap("stage-content", [loading]),
                        initial_hidden=not DEFAULT_VISIBILITY.get("stage", True)),
            ], id="row-bottom", style=HALF_ROW_STYLE),
        ], style=CONTENT_AREA_STYLE),

    ], style=DASHBOARD_STYLE)
