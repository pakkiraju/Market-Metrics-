"""Macro Monitor tab — terminal-style layout (FRED-backed)."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from dash import dcc, html

from src.constants import COLORS, GRAPH_CONFIG
from src.macro_fred_series import KPI_ORDER

# Sparks must not use responsive Plotly — otherwise the first card (Fed funds) can expand vertically.
SPARK_GRAPH_CONFIG = {**GRAPH_CONFIG, "displayModeBar": False, "responsive": False}

# Hex for HTML + Plotly (terminal-style red/green/amber on dark)
_TERM_HEX = {
    "hawkish": "#f87171",
    "dovish": "#4ade80",
    "tightening": "#fbbf24",
    "neutral": "#94a3b8",
    "mixed": "#c4b5fd",
}


def _terminal_value_color(kpi: dict[str, Any]) -> str:
    sig = kpi.get("signal", "neutral")
    return _TERM_HEX.get(sig, _TERM_HEX["neutral"])


def _spark_fig(dates: list, vals: list, color: str) -> go.Figure | None:
    if not vals or len(vals) < 2:
        return None
    fig = go.Figure(
        data=[
            go.Scatter(
                x=list(range(len(vals))),
                y=vals,
                mode="lines",
                line=dict(color=color, width=1.2),
                showlegend=False,
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, showgrid=False, fixedrange=True),
        yaxis=dict(visible=False, showgrid=False, fixedrange=True),
        height=40,
        width=200,
        autosize=False,
        font=dict(size=1),
    )
    return fig


def build_macro_monitor_tab() -> html.Div:
    """Full Macro Monitor tab: interval + shell (KPI sparklines only; no full-width history chart)."""
    return html.Div(
        [
            dcc.Interval(id="interval-macro", interval=1_800_000, n_intervals=0),  # 30 min
            build_macro_monitor_shell(),
        ],
        id="macro-monitor-tab-wrapper",
    )


def build_macro_monitor_shell() -> html.Div:
    """Outer shell; body filled by callback."""
    return html.Div(
        [
            html.Div(id="macro-monitor-content", className="macro-monitor-shell", children=_loading_placeholder()),
        ],
        id="macro-monitor-root",
        className="macro-monitor-root",
    )


def _loading_placeholder() -> html.Div:
    return html.Div("Loading macro data…", className="macro-loading-msg")


def build_macro_monitor_content(bundle: dict[str, Any]) -> html.Div:
    """Populate KPI strip, donut, narrative, fiscal grid from fetch_macro_bundle()."""
    err = bundle.get("error")
    if err == "missing_key":
        return html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span("◉", className="macro-header-icon"),
                                html.Div(
                                    [
                                        html.Div("Macro Monitor", className="macro-title"),
                                        html.Div(
                                            "Real-time policy & market signals",
                                            className="macro-subtitle",
                                            style={"marginTop": "4px"},
                                        ),
                                    ],
                                ),
                            ],
                            className="macro-header-left",
                        ),
                    ],
                    className="macro-header-row",
                ),
                html.Div(
                    "Set FRED_API_KEY in your environment or .env (free from fred.stlouisfed.org).",
                    className="macro-err-msg",
                    style={"maxWidth": "560px", "color": "#fbbf24", "lineHeight": 1.5},
                ),
            ],
            className="macro-monitor-inner macro-terminal-frame",
        )

    if err and err != "missing_key":
        return html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span("◉", className="macro-header-icon"),
                                html.Div([html.Div("Macro Monitor", className="macro-title")]),
                            ],
                            className="macro-header-left",
                        ),
                    ],
                    className="macro-header-row",
                ),
                html.Div(str(err), className="macro-err-msg"),
            ],
            className="macro-monitor-inner macro-terminal-frame",
        )

    kpis = bundle.get("kpis") or {}
    counts = bundle.get("signal_counts") or {}
    narrative = bundle.get("narrative") or ""
    dominant = bundle.get("dominant") or ""
    fiscal = bundle.get("fiscal") or []

    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = datetime.now()
    ts = now.strftime("%a, %b %d, %I:%M %p %Z")
    next_u = now.strftime("%a, %b %d, %I:%M %p")  # simplified

    kpi_cards = []
    for mid in KPI_ORDER:
        k = kpis.get(mid, {})
        col = _terminal_value_color(k)
        spark = None
        if k.get("spark_vals"):
            spark = _spark_fig(k.get("spark_dates"), k["spark_vals"], col)
        inner = [
            html.Div(k.get("short") or k.get("label", mid), className="macro-kpi-label"),
            html.Div(k.get("display", "—"), className="macro-kpi-value", style={"color": col}),
            html.Div(k.get("subtitle", ""), className="macro-kpi-sub"),
        ]
        if spark:
            inner.append(
                html.Div(
                    dcc.Graph(
                        figure=spark,
                        config=SPARK_GRAPH_CONFIG,
                        style={"height": "40px", "width": "100%", "maxHeight": "40px", "minHeight": "40px"},
                        className="macro-kpi-spark-graph",
                    ),
                    className="macro-kpi-spark-shell",
                )
            )
        kpi_cards.append(
            html.Div(
                inner,
                className="macro-kpi-card",
            )
        )

    labels_map = [
        ("hawkish", "Hawkish"),
        ("dovish", "Dovish"),
        ("neutral", "Neutral"),
        ("mixed", "Mixed"),
        ("tightening", "Tightening"),
    ]
    pie_labels = []
    pie_vals = []
    pie_colors = []
    color_map = {
        "hawkish": "#ef6b6b",
        "dovish": "#22c55e",
        "neutral": "#6b7280",
        "mixed": "#a78bfa",
        "tightening": "#ea580c",
    }
    for key, lab in labels_map:
        v = int(counts.get(key, 0) or 0)
        if v > 0:
            pie_labels.append(f"{lab} ({v})")
            pie_vals.append(v)
            pie_colors.append(color_map[key])

    if not pie_vals:
        pie_labels = ["No data"]
        pie_vals = [1]
        pie_colors = ["#374151"]

    donut = dcc.Graph(
        figure=_donut_fig(pie_labels, pie_vals, pie_colors, dominant),
        config=GRAPH_CONFIG,
        style={"height": "240px"},
        className="macro-donut",
    )

    # Fiscal: split rows into 3 columns
    nf = len(fiscal) or 1
    step = max(1, (nf + 2) // 3)
    col1 = fiscal[0:step]
    col2 = fiscal[step : 2 * step]
    col3 = fiscal[2 * step :]

    def _fiscal_col(rows: list[dict[str, Any]], title: str) -> html.Div:
        items = []
        for r in rows:
            items.append(
                html.Div(
                    [
                        html.Span(r.get("label", ""), className="macro-fiscal-label"),
                        html.Span(r.get("display", "—"), className="macro-fiscal-val"),
                    ],
                    className="macro-fiscal-row",
                )
            )
        return html.Div([html.Div(title, className="macro-fiscal-col-title"), *items], className="macro-fiscal-col")

    fiscal_block = html.Div(
        [
            html.Div("U.S. fiscal snapshot (latest available)", className="macro-section-title"),
            html.Div(
                [
                    _fiscal_col(col1, "Debt & balance"),
                    _fiscal_col(col2, "Revenue & spending"),
                    _fiscal_col(col3, "Interest & ratios"),
                ],
                className="macro-fiscal-grid",
            ),
        ],
        className="macro-fiscal-block",
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("◉", className="macro-header-icon"),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span("Macro Monitor", className="macro-title"),
                                            html.Span(
                                                " — Policy & market signals",
                                                className="macro-subtitle",
                                            ),
                                        ]
                                    ),
                                ],
                            ),
                        ],
                        className="macro-header-left",
                    ),
                    html.Div(
                        [
                            html.Span(ts, className="macro-clock"),
                            html.Br(),
                            html.Span("Next refresh ~30m", className="macro-next"),
                        ],
                        className="macro-header-right",
                    ),
                ],
                className="macro-header-row",
            ),
            html.Div(kpi_cards, className="macro-kpi-row"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Signal balance", className="macro-section-title"),
                            html.Div(dominant, className="macro-donut-head"),
                            donut,
                        ],
                        className="macro-donut-wrap",
                    ),
                    html.Div(
                        [
                            html.Div("Bottom line", className="macro-bl-title"),
                            html.Div(narrative, className="macro-bl-text"),
                        ],
                        className="macro-bottom-line",
                    ),
                ],
                className="macro-mid-row",
            ),
            fiscal_block,
        ],
        className="macro-monitor-inner macro-terminal-frame",
    )


def _donut_fig(labels: list[str], values: list[float], colors: list[str], heading: str) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.62,
                marker=dict(colors=colors, line=dict(color="#1a1d26", width=1)),
                textinfo="label+percent",
                textposition="outside",
                insidetextorientation="radial",
                showlegend=True,
            )
        ]
    )
    fig.add_annotation(
        text=f"<b>{heading}</b>",
        x=0.5,
        y=0.5,
        font=dict(size=11, color="hsl(142, 70%, 68%)"),
        showarrow=False,
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=28, b=20),
        showlegend=True,
        legend=dict(orientation="v", font=dict(size=9, color="hsl(220, 10%, 55%)")),
        font=dict(family="JetBrains Mono, monospace", size=9, color="hsl(142, 65%, 72%)"),
        height=240,
    )
    return fig
