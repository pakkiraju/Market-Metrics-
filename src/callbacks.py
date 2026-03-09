"""Dash callbacks: progressive per-widget-group refresh, widget toggles,
TradingView modal, watchlist management.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dash import html, dcc, Input, Output, State, callback, no_update, ctx, ALL
import plotly.graph_objects as go

from src import cache
from src.constants import COLORS
from src.data_fetcher import (
    load_nasdaq100, load_sp500, load_composite, load_watchlist,
)
from src.calculations import (
    compute_all_key_metrics,
    compute_sector_data,
    compute_97_club,
    compute_9m_movers,
    compute_20pct_weekly,
    compute_4pct_daily,
    compute_leading_industries,
    compute_stage_analysis,
)
from src.screeners import (
    qullamaggie_screener,
    minervini_screener,
    oneil_screener,
)
from src.layout import (
    build_key_metrics_table,
    build_metrics_bar_chart,
    build_sector_table,
    build_97_club_table,
    build_9m_movers_table,
    build_20pct_weekly_table,
    build_4pct_daily_table,
    build_leading_industries_table,
    build_stage_chart,
    build_stage_summary,
    build_ticker_grid,
    WIDGETS, ALL_WIDGET_IDS,
    CHART_WRAP_STYLE,
)
from src.styles import (
    LOADING_STYLE,
    SETTINGS_OVERLAY_STYLE_HIDDEN,
    SETTINGS_OVERLAY_STYLE_VISIBLE,
    WIDGET_PRIMARY_STYLE,
    WIDGET_SECONDARY_STYLE,
)

logger = logging.getLogger(__name__)

ET = timezone(timedelta(hours=-5))

WATCHLIST_FILE = Path(__file__).resolve().parent.parent / "config" / "watchlist.csv"


def _load_watchlist_from_file() -> list[str]:
    if not WATCHLIST_FILE.exists():
        return []
    lines = WATCHLIST_FILE.read_text().strip().splitlines()
    tickers = []
    for line in lines[1:]:
        t = line.strip()
        if t:
            tickers.append(t.upper())
    return tickers


def _save_watchlist_to_file(tickers: list[str]):
    WATCHLIST_FILE.write_text("ticker\n" + "\n".join(tickers) + "\n")


def _now_str():
    return datetime.now(ET).strftime("Updated %I:%M %p")


def _err_div(e):
    return html.Div(f"Error: {e}", style={
        "color": COLORS["red"], "padding": "8px", "fontSize": "10px",
    })


def register_callbacks(app):
    """Register all Dash callbacks on the app."""

    # ------------------------------------------------------------------
    # 1. Settings drawer toggle
    # ------------------------------------------------------------------
    @app.callback(
        Output("settings-drawer", "style"),
        Input("btn-settings", "n_clicks"),
        State("settings-drawer", "style"),
        prevent_initial_call=True,
    )
    def toggle_settings(n_clicks, current_style):
        if current_style and current_style.get("display") != "none":
            return SETTINGS_OVERLAY_STYLE_HIDDEN
        return SETTINGS_OVERLAY_STYLE_VISIBLE

    # ------------------------------------------------------------------
    # 2. Widget visibility: ALL widgets toggleable
    # ------------------------------------------------------------------
    toggle_inputs = [Input(f"toggle-{wid}", "value") for wid in ALL_WIDGET_IDS]
    widget_outputs = [Output(f"widget-{wid}", "style") for wid in ALL_WIDGET_IDS]

    is_primary_map = {w[0]: w[2] for w in WIDGETS}

    @app.callback(
        widget_outputs,
        toggle_inputs,
        prevent_initial_call=True,
    )
    def update_widget_visibility(*toggle_values):
        results = []
        for wid, val in zip(ALL_WIDGET_IDS, toggle_values):
            if val and "on" in val:
                results.append(
                    WIDGET_PRIMARY_STYLE if is_primary_map[wid]
                    else WIDGET_SECONDARY_STYLE
                )
            else:
                results.append({"display": "none"})
        return results

    # ------------------------------------------------------------------
    # 3. TradingView modal: close via clientside callback
    # ------------------------------------------------------------------
    app.clientside_callback(
        """
        function(n_clicks) {
            return {display: 'none'};
        }
        """,
        Output("tv-modal", "style", allow_duplicate=True),
        Input("btn-tv-close", "n_clicks"),
        prevent_initial_call=True,
    )

    # ------------------------------------------------------------------
    # 4. Watchlist: add ticker
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("watchlist-store", "data"),
            Output("watchlist-input", "value"),
        ],
        [
            Input("btn-watchlist-add", "n_clicks"),
        ],
        [
            State("watchlist-input", "value"),
            State("watchlist-store", "data"),
        ],
        prevent_initial_call=True,
    )
    def add_to_watchlist(n_clicks, ticker_input, current_list):
        if not ticker_input or not ticker_input.strip():
            return no_update, ""
        ticker = ticker_input.strip().upper()
        if current_list is None:
            current_list = []
        if ticker not in current_list:
            current_list.append(ticker)
            _save_watchlist_to_file(current_list)
        return current_list, ""

    # ------------------------------------------------------------------
    # 5. Watchlist: remove ticker (pattern-matching callback)
    # ------------------------------------------------------------------
    @app.callback(
        Output("watchlist-store", "data", allow_duplicate=True),
        Input({"type": "wl-remove", "ticker": ALL}, "n_clicks"),
        State("watchlist-store", "data"),
        prevent_initial_call=True,
    )
    def remove_from_watchlist(n_clicks_list, current_list):
        if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
            return no_update
        ticker = ctx.triggered_id.get("ticker")
        if ticker and current_list and ticker in current_list:
            current_list.remove(ticker)
            _save_watchlist_to_file(current_list)
            return current_list
        return no_update

    # ------------------------------------------------------------------
    # 6. Watchlist: render from store
    # ------------------------------------------------------------------
    @app.callback(
        Output("watchlist-content", "children"),
        Input("watchlist-store", "data"),
    )
    def render_watchlist(wl_data):
        if not wl_data:
            return html.Div("No tickers in watchlist. Add some above.", style={
                "color": COLORS["text_muted"], "fontSize": "9px",
                "padding": "8px",
            })

        from src.styles import ticker_pill_style
        pills = []
        for t in wl_data:
            pill_st = ticker_pill_style("green")
            pill_st["cursor"] = "pointer"
            pill_st["position"] = "relative"
            pill_st["paddingRight"] = "16px"

            pills.append(html.Span([
                html.Span(
                    t,
                    className="tv-ticker",
                    style={"cursor": "pointer"},
                ),
                html.Span(
                    "x",
                    id={"type": "wl-remove", "ticker": t},
                    n_clicks=0,
                    style={
                        "position": "absolute",
                        "top": "-1px",
                        "right": "1px",
                        "fontSize": "8px",
                        "color": COLORS["red_light"],
                        "cursor": "pointer",
                        "fontWeight": 700,
                        "lineHeight": "1",
                    },
                ),
            ], style={**pill_st, "display": "inline-block", "position": "relative"}))

        return html.Div(pills, style={
            "display": "flex", "flexWrap": "wrap", "gap": "3px",
            "padding": "3px",
        })

    # ==================================================================
    #  PROGRESSIVE GROUP CALLBACKS
    #  Each group fires independently on the shared interval / refresh.
    # ==================================================================

    # ------------------------------------------------------------------
    # Group A: Key Metrics + Charts 2 & 3
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("key-metrics-content", "children"),
            Output("chart2-content", "children"),
            Output("chart3-content", "children"),
            Output("last-update", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_a(n_intervals, n_clicks):
        try:
            metrics = compute_all_key_metrics()
            key_metrics_table = build_key_metrics_table(metrics)

            qqqe_data = metrics.get("QQQE", [])
            rsp_data = metrics.get("RSP", [])
            comp_data = metrics.get("Composite", [])
            b1_data = metrics.get("$1B+", [])

            chart2_fig = build_metrics_bar_chart(
                qqqe_data, rsp_data,
                "QQQE", "RSP",
                "#991b1b", "#166534",
                "#dc2626", "#22c55e",
            )
            chart2 = dcc.Graph(
                figure=chart2_fig,
                config={"displayModeBar": False},
                style={"height": "100%", "width": "100%"},
            )

            chart3_fig = build_metrics_bar_chart(
                comp_data, b1_data,
                "Composite", "$1B+",
                "#7f1d1d", "#14532d",
                "#ef4444", "#4ade80",
            )
            chart3 = dcc.Graph(
                figure=chart3_fig,
                config={"displayModeBar": False},
                style={"height": "100%", "width": "100%"},
            )

            return [key_metrics_table, chart2, chart3, _now_str()]
        except Exception as e:
            logger.exception("Group A (Key Metrics) failed: %s", e)
            err = _err_div(e)
            return [err, err, err, f"Error at {_now_str()}"]

    # ------------------------------------------------------------------
    # Group B: Screeners (Qullamaggie, Minervini, O'Neil)
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("qulla-content", "children"),
            Output("minervini-content", "children"),
            Output("oneil-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_b(n_intervals, n_clicks):
        try:
            qulla = build_ticker_grid(qullamaggie_screener())
            minerv = build_ticker_grid(minervini_screener())
            oneil = build_ticker_grid(oneil_screener())
            return [qulla, minerv, oneil]
        except Exception as e:
            logger.exception("Group B (Screeners) failed: %s", e)
            err = _err_div(e)
            return [err, err, err]

    # ------------------------------------------------------------------
    # Group C: Sector SPDRs
    # ------------------------------------------------------------------
    @app.callback(
        Output("sector-content", "children"),
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_c(n_intervals, n_clicks):
        try:
            sector_data = compute_sector_data()
            return build_sector_table(sector_data)
        except Exception as e:
            logger.exception("Group C (Sector) failed: %s", e)
            return _err_div(e)

    # ------------------------------------------------------------------
    # Group D: Fast-refresh — 97 Club, 9M Movers, 20% Weekly, 4% Daily
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("club97-content", "children"),
            Output("movers-content", "children"),
            Output("weekly-content", "children"),
            Output("daily-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_d(n_intervals, n_clicks):
        try:
            composite_tickers = load_composite()

            club_data = compute_97_club(composite_tickers)
            club_table = build_97_club_table(club_data)

            movers_data = compute_9m_movers(composite_tickers)
            movers_table = build_9m_movers_table(movers_data)

            weekly_data = compute_20pct_weekly(composite_tickers)
            weekly_table = build_20pct_weekly_table(weekly_data)

            daily_data = compute_4pct_daily(composite_tickers)
            daily_table = build_4pct_daily_table(daily_data)

            return [club_table, movers_table, weekly_table, daily_table]
        except Exception as e:
            logger.exception("Group D (Fast-refresh) failed: %s", e)
            err = _err_div(e)
            return [err, err, err, err]

    # ------------------------------------------------------------------
    # Group E: Slow — Leading Industries, Stage Analysis
    # ------------------------------------------------------------------
    @app.callback(
        [
            Output("leading-content", "children"),
            Output("stage-content", "children"),
        ],
        [
            Input("interval-refresh", "n_intervals"),
            Input("btn-refresh", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def refresh_group_e(n_intervals, n_clicks):
        try:
            composite_tickers = load_composite()

            leading_data = compute_leading_industries(composite_tickers, {})
            leading_table = build_leading_industries_table(leading_data)

            stage_result = compute_stage_analysis(composite_tickers)
            stage_counts = stage_result["counts"]
            stage_fig = build_stage_chart(stage_counts)
            stage_content = html.Div([
                html.Div(
                    dcc.Graph(
                        figure=stage_fig,
                        config={"displayModeBar": False},
                        style={"width": "100%"},
                    ),
                    style={"padding": "2px"},
                ),
                build_stage_summary(stage_counts),
            ])

            return [leading_table, stage_content]
        except Exception as e:
            logger.exception("Group E (Slow) failed: %s", e)
            err = _err_div(e)
            return [err, err]
