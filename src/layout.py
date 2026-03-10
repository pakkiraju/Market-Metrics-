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
    STAGE_BAR_COLORS, STAGE_LABELS,
)
from src.styles import (
    DASHBOARD_STYLE, HEADER_STYLE, HEADER_LOGO_STYLE,
    HEADER_DATE_STYLE, MARKET_STATUS_STYLE_CLOSED, REFRESH_BTN_STYLE,
    SETTINGS_BTN_STYLE,
    CONTENT_AREA_STYLE,
    PRIMARY_ROW_STYLE, QUARTER_ROW_STYLE, WIDE_ROW_STYLE, HALF_ROW_STYLE,
    WIDGET_STYLE, WIDGET_PRIMARY_STYLE, WIDGET_SECONDARY_STYLE,
    section_header_style, SECTION_BODY_STYLE,
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
    ("chart2",         "NASDAQ100 & S&P500 Metrics", True),
    ("chart3",         "Combined Index & $1B+ Stocks", True),
    ("qulla",          "Qullamaggie",                False),
    ("minervini",      "Minervini",                  False),
    ("oneil",          "O'Neil",                     False),
    ("watchlist",      "Watchlist",                  False),
    ("sector",         "Sector SPDR ETFs",           False),
    ("club97",         "97 Club",                    False),
    ("movers",         "9 Million Movers",           False),
    ("weekly",         "20% Weekly Movers",          False),
    ("daily",          "4% Daily Gainers",           False),
    ("leading",        "Leading Industries",         False),
    ("stage",          "Stage Analysis",             False),
]

ALL_WIDGET_IDS = [w[0] for w in WIDGETS]
DEFAULT_VISIBILITY = {w[0]: True for w in WIDGETS}

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
            count=None, extra_header=None, primary=False):
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

    card_style = WIDGET_PRIMARY_STYLE if primary else WIDGET_SECONDARY_STYLE

    return html.Div(
        [
            html.Div(header_kids, style=section_header_style(variant)),
            html.Div(body_children, style=SECTION_BODY_STYLE),
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

def build_key_metrics_table(metrics: dict) -> html.Table:
    group_headers = ["NASDAQ (QQQE)", "S&P500 (RSP)", "RSP+QQQE+DIA", "$1B+ Universe"]
    sub_headers = ["Above", "Below", "Pct"]

    header_row1 = [html.Th("Metric", style={
        **TABLE_HEADER_STYLE, "textAlign": "left", "width": "120px",
    })]
    for gh in group_headers:
        header_row1.append(html.Th(gh, colSpan=3, style={
            **TABLE_HEADER_STYLE,
            "background": "#1e3a5f",
            "color": "#93c5fd",
            "fontWeight": 700,
            "fontSize": "8px",
            "borderBottom": f"2px solid {COLORS['accent']}",
        }))

    header_row2 = [html.Th("", style=TABLE_HEADER_STYLE)]
    for _ in range(4):
        for sh in sub_headers:
            header_row2.append(html.Th(sh, style=TABLE_HEADER_STYLE))

    body_rows = []
    groups_ordered = ["QQQE", "RSP", "Composite", "$1B+"]
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

                is_info_row = label in ("Stocks", "Price-to 20 Day Range")
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
                    cells.append(html.Td(
                        str(above) if above is not None else "—", style=cell_st))
                    cells.append(html.Td(
                        str(below) if below is not None else "—", style=cell_st))
                    cells.append(html.Td(
                        f"{pct}%" if pct is not None else "—", style=cell_st))
            else:
                for _ in range(3):
                    cells.append(html.Td("—", style=TABLE_CELL_STYLE))
        body_rows.append(html.Tr(cells))

    return html.Table(
        [
            html.Thead([html.Tr(header_row1), html.Tr(header_row2)]),
            html.Tbody(body_rows),
        ],
        style={**TABLE_STYLE, "tableLayout": "auto"},
    )


# -----------------------------------------------------------------------
# Sections 2-3: Stacked bar charts
# -----------------------------------------------------------------------

def build_metrics_bar_chart(data1_pcts, data2_pcts,
                            label1, label2,
                            color1_down, color1_up,
                            color2_down, color2_up) -> go.Figure:
    labels = KEY_METRIC_ROWS[:-2]

    pct1 = [d["pct"] if d["pct"] is not None else 50 for d in data1_pcts[:len(labels)]]
    pct2 = [d["pct"] if d["pct"] is not None else 50 for d in data2_pcts[:len(labels)]]

    down1 = [-(100 - p) for p in pct1]
    down2 = [-(100 - p) for p in pct2]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=down1, orientation="h", name=f"{label1} Down",
        marker_color=color1_down, width=0.35, offset=-0.18,
    ))
    fig.add_trace(go.Bar(
        y=labels, x=down2, orientation="h", name=f"{label2} Down",
        marker_color=color2_down, width=0.35, offset=0.18,
    ))
    fig.add_trace(go.Bar(
        y=labels, x=pct2, orientation="h", name=f"{label2} Up",
        marker_color=color2_up, width=0.35, offset=0.18,
    ))
    fig.add_trace(go.Bar(
        y=labels, x=pct1, orientation="h", name=f"{label1} Up",
        marker_color=color1_up, width=0.35, offset=-0.18,
    ))

    fig.update_layout(
        barmode="relative",
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=2, r=4, t=2, b=2),
        showlegend=False,
        xaxis=dict(
            range=[-100, 100],
            showticklabels=False,
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
        height=340,
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


def build_qullamaggie_content(data: list[dict]) -> html.Div:
    """Single table: Ticker, Tag (EP, BO, PS)."""
    if not data:
        return html.Div("No results", style={
            "color": COLORS["text_muted"], "fontSize": "9px", "padding": "8px",
        })
    rows = [
        [
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            r.get("tag", ""),
        ]
        for r in data
    ]
    return _table(["Ticker", "Tag"], rows, col_widths=["120px", "60px"])


# -----------------------------------------------------------------------
# Section 8: Sector SPDR table (clickable tickers)
# -----------------------------------------------------------------------

def build_sector_table(sector_data: list[dict]) -> html.Table:
    headers = [
        "Sector", "Ticker", "Gap", "Chg", "O Chg", "Week", "Month",
        "Qtr", "H.Year", "Year", "Last", "EMA10", "SMA20", "SMA50",
        "SMA200", "52W Hi", "52W Lo", "ATR %", "ATR Ext",
    ]
    rows = []
    for r in sector_data:
        chg_val = r.get("chg", 0)
        name = SECTOR_NAMES.get(r["ticker"], r["ticker"])

        def _chg_cell(val, suffix="%"):
            v = val if val is not None else 0
            color = chg_color(v)
            return {"text": f"{v}{suffix}", "style": {"color": color}}

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
            f"{r.get('atr_pct', 0)}%",
            str(r.get("atr_ext", "")),
        ]
        rows.append(row)

    return _table(headers, rows)


# -----------------------------------------------------------------------
# Section 9: 97 Club table (clickable tickers)
# -----------------------------------------------------------------------

def build_97_club_table(club_data: list[dict]) -> html.Table:
    headers = ["Ticker", "Stage", "Day RS", "Week RS", "Month RS", "ATR %", "ATR Ext", "TML"]
    rows = []
    for r in club_data:
        ticker_st = {"fontWeight": 700, "cursor": "pointer"}
        if r.get("tml"):
            ticker_st["color"] = "#60a5fa"
            ticker_st["backgroundColor"] = COLORS["blue_tml_bg"]

        rows.append([
            {"text": _clickable_ticker(r["ticker"], ticker_st),
             "style": TABLE_CELL_STYLE},
            {"text": html.Span(r["stage"], style=stage_badge_style(r["stage"])),
             "style": TABLE_CELL_STYLE},
            f"{r.get('rs_day', 0):.1f}",
            f"{r.get('rs_week', 0):.1f}",
            f"{r.get('rs_month', 0):.1f}",
            f"{r.get('atr_pct', 0)}%",
            str(r.get("atr_ext", "")),
            {"text": "Y" if r.get("tml") else "",
             "style": {**TABLE_CELL_STYLE, "color": "#60a5fa"}},
        ])
    return _table(headers, rows)


# -----------------------------------------------------------------------
# Sections 10-12: Stockbee tables (clickable tickers)
# -----------------------------------------------------------------------

def build_9m_movers_table(data: list[dict]) -> html.Table:
    headers = ["Ticker", "Vol.", "Rel Vol", "Chg", "Stage", "ATR %", "ATR Ext"]
    rows = []
    for r in data:
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            {"text": f"{r.get('volume', 0):,}", "style": {**TABLE_CELL_STYLE, "fontSize": "8px"}},
            str(r.get("rel_vol", "")),
            {"text": f"{r.get('chg', 0)}%",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(r.get("chg", 0))}},
            {"text": html.Span(r.get("stage", ""), style=stage_badge_style(r.get("stage", "1"))),
             "style": TABLE_CELL_STYLE},
            f"{r.get('atr_pct', 0)}%",
            str(r.get("atr_ext", "")),
        ])
    return _table(headers, rows)


def build_20pct_weekly_table(data: list[dict]) -> html.Table:
    headers = ["Ticker", "Week", "Stage", "ATR %", "ATR Ext"]
    rows = []
    for r in data:
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            {"text": f"{r.get('week', 0)}%",
             "style": {**TABLE_CELL_STYLE, "color": chg_color(r.get("week", 0)),
                        "fontWeight": 600}},
            {"text": html.Span(r.get("stage", ""), style=stage_badge_style(r.get("stage", "1"))),
             "style": TABLE_CELL_STYLE},
            f"{r.get('atr_pct', 0)}%",
            str(r.get("atr_ext", "")),
        ])
    return _table(headers, rows)


def build_4pct_daily_table(data: list[dict]) -> html.Table:
    headers = ["Ticker", "Chg", "Stage", "ATR %", "Rel Vol"]
    rows = []
    for r in data:
        rows.append([
            {"text": _clickable_ticker(r["ticker"], {"fontWeight": 700}),
             "style": TABLE_CELL_STYLE},
            {"text": f"{r.get('chg', 0)}%",
             "style": {**TABLE_CELL_STYLE, "color": COLORS["green_light"],
                        "fontWeight": 600}},
            {"text": html.Span(r.get("stage", ""), style=stage_badge_style(r.get("stage", "1"))),
             "style": TABLE_CELL_STYLE},
            f"{r.get('atr_pct', 0)}%",
            str(r.get("min_rel_vol", "")),
        ])
    return _table(headers, rows)


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
                placeholder="Add ticker (e.g. AAPL)",
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
                    value=["on"],
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
    wl_path = Path(__file__).resolve().parent.parent / "config" / "watchlist.csv"
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
                        _loading_wrap("key-metrics-content", [loading]),
                        primary=True),
                _widget("chart2", "NASDAQ100 & S&P500 Metrics",
                        _loading_wrap("chart2-content", [loading],
                                      style=CHART_WRAP_STYLE),
                        variant="teal", primary=True),
                _widget("chart3", "Combined Index & $1B+ Stocks",
                        _loading_wrap("chart3-content", [loading],
                                      style=CHART_WRAP_STYLE),
                        variant="teal", primary=True),
            ], id="row-primary", style=PRIMARY_ROW_STYLE),

            # ---- SCREENERS ROW (4 across) ----
            html.Div([
                _widget("qulla", "Qullamaggie",
                        _loading_wrap("qulla-content"),
                        variant="green"),
                _widget("minervini", "Minervini",
                        _loading_wrap("minervini-content"),
                        variant="purple"),
                _widget("oneil", "O'Neil",
                        _loading_wrap("oneil-content"),
                        variant="orange"),
                _widget("watchlist", "Watchlist",
                        build_watchlist_body()),
            ], id="row-screeners", style=QUARTER_ROW_STYLE),

            # ---- SECTOR ROW (full width) ----
            html.Div([
                _widget("sector", "Sector SPDR ETFs",
                        _loading_wrap("sector-content", [loading])),
            ], id="row-sector", style=WIDE_ROW_STYLE),

            # ---- MIDDLE 4 ----
            html.Div([
                _widget("club97", "97 Club",
                        _loading_wrap("club97-content", [loading]),
                        variant="green"),
                _widget("movers", "9 Million Movers",
                        _loading_wrap("movers-content", [loading])),
                _widget("weekly", "20% Weekly Movers",
                        _loading_wrap("weekly-content", [loading]),
                        variant="red"),
                _widget("daily", "4% Daily Gainers",
                        _loading_wrap("daily-content", [loading]),
                        variant="green"),
            ], id="row-middle4", style=QUARTER_ROW_STYLE),

            # ---- BOTTOM ROW ----
            html.Div([
                _widget("leading", "Leading Industries — Top 20%",
                        _loading_wrap("leading-content", [loading]),
                        variant="teal"),
                _widget("stage", "Stage Analysis",
                        _loading_wrap("stage-content", [loading])),
            ], id="row-bottom", style=HALF_ROW_STYLE),
        ], style=CONTENT_AREA_STYLE),

    ], style=DASHBOARD_STYLE)
